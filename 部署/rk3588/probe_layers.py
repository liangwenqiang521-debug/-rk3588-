# -*- coding: utf-8 -*-
"""
逐层探针：定位 RKNN 编译后从哪一层开始与 onnxruntime 不一致。

做法
----
在 ONNX 图里把若干"中间张量"提升为图输出，然后分别用
  ort  : onnxruntime (CPU, 真值)
  lite : RKNNLite  (NPU, 实际部署)
跑同一个输入，逐个张量对比统计量。哪一层开始分道扬镳，问题就在那一层。

探针张量（自动按名字匹配，匹配不到会打印候选供调整）：
  head_in_*  : Detect 头三个尺度的输入特征 (cv2.x.0 / cv3.x.0 的卷积输入)
  cls_out_*  : 三个尺度分类分支最后一个卷积(6 通道)的输出
  box_cat    : /model.23/Mul_2_output_0      —— box 解码结果
  cls_cat    : /model.23/Concat_1_output_0   —— 分类 logits（Concat 后）

用法
----
# 生成探针 onnx
PYTHONPATH=/root/rknn_convert/libs python3 probe_layers.py make  best_neu6.onnx probe.onnx
# onnxruntime 基线
PYTHONPATH=/root/rknn_convert/libs python3 probe_layers.py ort   probe.onnx --blob /tmp/blob.npy
# 转换（外层另跑 export_rknn.py），再 NPU 对照
python3 probe_layers.py lite probe.rknn --blob /tmp/blob.npy
"""

import argparse
import sys

import numpy as np

# 后缀匹配：节点名以此结尾即命中。取 Conv 的输入(input[0])或输出(output[0])。
# cls_* 用 cv3.*、box_* 用 cv2.*（ultralytics Detect 头的两条分支）
PROBE_PATTERNS = [
    ("head_in_P3", "cv2.0.0/conv/Conv", "in"),
    ("head_in_P4", "cv2.1.0/conv/Conv", "in"),
    ("head_in_P5", "cv2.2.0/conv/Conv", "in"),
    ("box_out_P3", "cv2.0.2/Conv", "out"),
    ("box_out_P4", "cv2.1.2/Conv", "out"),
    ("box_out_P5", "cv2.2.2/Conv", "out"),
    ("cls_out_P3", "cv3.0.2/Conv", "out"),
    ("cls_out_P4", "cv3.1.2/Conv", "out"),
    ("cls_out_P5", "cv3.2.2/Conv", "out"),
    ("dfl_out",    "dfl/conv/Conv", "out"),
]

TAIL_NODES = [
    ("box_cat", "/model.23/Concat"),     # 三个尺度的 box 特征拼接
    ("cls_cat", "/model.23/Concat_1"),   # 三个尺度的分类 logits 拼接
]


def find_probe_tensors(g):
    """返回 ({probe_name: tensor_name}, missing_list)。"""
    probes, missing = {}, []

    for label, suffix, which in PROBE_PATTERNS:
        hits = [n for n in g.node if n.name.endswith(suffix)]
        if len(hits) != 1:
            missing.append((label, suffix, "命中 %d 个" % len(hits)))
            continue
        n = hits[0]
        probes[label] = n.input[0] if which == "in" else n.output[0]

    for label, node_name in TAIL_NODES:
        hits = [n for n in g.node if n.name == node_name]
        if len(hits) != 1:
            missing.append((label, node_name, "命中 %d 个" % len(hits)))
            continue
        probes[label] = hits[0].output[0]

    return probes, missing


def make(src, dst):
    import onnx
    m = onnx.load(src)
    # 先做一次形状推断，否则中间张量没有 shape，check_model 会拒绝追加输出
    m = onnx.shape_inference.infer_shapes(m)
    g = m.graph
    probes, missing = find_probe_tensors(g)
    if missing:
        print("⚠️ 未匹配到的探针:", missing)
        print("   可选节点名(含 model.23):")
        for n in g.node:
            if "model.23" in n.name and n.op_type in ("Conv", "Concat", "Mul", "Split"):
                print("     %-12s %s" % (n.op_type, n.name))
    if not probes:
        raise SystemExit("没有任何探针张量可用")

    have = {o.name for o in g.output}
    vi_by_name = {}
    for t in list(g.value_info) + list(g.input) + list(g.output):
        vi_by_name[t.name] = t

    for label, tname in probes.items():
        if tname in have:
            print("  跳过(已是输出): %s" % tname)
            continue
        vi = vi_by_name.get(tname)
        dims = None
        if vi is not None:
            dims = [d.dim_value for d in vi.type.tensor_type.shape.dim]
            if not dims or any(d == 0 for d in dims):
                dims = None
        if dims is None:
            # 形状未知 -> 声明为动态维，避免 check_model 报 shape 缺失
            dims = [None] * (len(vi.type.tensor_type.shape.dim) if vi is not None else 4)
            if not dims:
                dims = [None, None, None, None]
        g.output.append(onnx.helper.make_tensor_value_info(tname, onnx.TensorProto.FLOAT, dims))
        print("  + %-11s -> %s  %s" % (label, tname, dims))

    onnx.checker.check_model(m)
    onnx.save(m, dst)
    print("✅ 探针模型: %s  共 %d 个输出" % (dst, len(g.output)))


def stats(idx, tag, arr):
    a = np.asarray(arr, dtype=np.float32)
    print("  [%2d] %-22s shape=%-17s min=%9.4f max=%9.4f mean=%9.4f std=%8.4f" %
          (idx, tag, str(tuple(a.shape)), a.min(), a.max(), a.mean(), a.std()))


def run_ort(model, blob):
    import onnxruntime as ort
    s = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
    iname = s.get_inputs()[0].name
    names = [o.name for o in s.get_outputs()]
    outs = s.run(None, {iname: blob})
    print("ORT 输出 %d 个:" % len(names))
    for i, (n, o) in enumerate(zip(names, outs)):
        stats(i, n.split("/model.23/")[-1].split("/")[-1][:22], o)
    print("顺序表: %s" % [n.split("/")[-1] for n in names])


def run_lite(model, blob):
    from rknnlite.api import RKNNLite
    rk = RKNNLite()
    if rk.load_rknn(model) != 0:
        raise SystemExit("load_rknn 失败")
    if rk.init_runtime() != 0:
        raise SystemExit("init_runtime 失败")
    outs = rk.inference(inputs=[blob])
    print("RKNN 输出 %d 个:" % len(outs))
    for i, o in enumerate(outs):
        stats(i, "rknn", o)
    rk.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["make", "ort", "lite"])
    ap.add_argument("model")
    ap.add_argument("dst", nargs="?", default="probe.onnx")
    ap.add_argument("--blob", default="/tmp/blob.npy")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    if args.mode == "make":
        make(args.model, args.dst)
        return

    blob = np.load(args.blob)
    if blob.ndim == 3:
        blob = blob[None, ...]
    if args.mode == "ort":
        run_ort(args.model, blob)
    else:
        run_lite(args.model, blob)


if __name__ == "__main__":
    main()
