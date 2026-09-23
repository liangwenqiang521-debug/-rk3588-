# -*- coding: utf-8 -*-
"""
RKNN 转换保真度 A/B 对照（在 RK3588 板子上运行）
====================================================================
目的：定位「RKNN 输出类别置信度远小于 ONNX」到底出在哪一环。

同一次预处理(与 board_infer.preprocess 完全一致) 之后，分别跑三条路径：

  ort    : onnxruntime 跑原始 .onnx          -> 真值基线
  sim    : rknn-toolkit2 模拟器(load_onnx 后直接 inference) -> 图优化前的等价图
  lite   : RKNNLite 跑 .rknn (FP16, NPU)     -> 实际部署路径

用法（三选一，分开跑避免 toolkit/runtime 冲突）：
  PYTHONPATH=/root/rknn_convert/libs python3 ab_test.py --mode ort  --model best_neu6.onnx --image xxx.jpg
  PYTHONPATH=/root/rknn_convert/libs python3 ab_test.py --mode sim  --model best_neu6.onnx --image xxx.jpg
  python3 ab_test.py --mode lite --model best_neu6.rknn --image xxx.jpg
"""

import argparse
import os
import sys

import cv2
import numpy as np


def imread_unicode(path):
    """cv2.imread 在中文路径下会失败，用 fromfile+imdecode 绕过。"""
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def letterbox(img, new_size=640, color=(114, 114, 114)):
    h, w = img.shape[:2]
    scale = min(new_size / w, new_size / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dw, dh = (new_size - nw) // 2, (new_size - nh) // 2
    padded = cv2.copyMakeBorder(resized, dh, new_size - nh - dh,
                                dw, new_size - nw - dw,
                                cv2.BORDER_CONSTANT, value=color)
    return padded, scale, (dw, dh)


def preprocess(img_bgr, imgsz):
    """与 board_infer.preprocess 一致：BGR->RGB->/255->NCHW float32。"""
    padded, scale, (dw, dh) = letterbox(img_bgr, imgsz)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    blob = rgb.astype(np.float32) / 255.0
    blob = np.transpose(blob, (2, 0, 1))[None, ...]
    return blob, scale, (dw, dh)


def preprocess_u8(img_bgr, imgsz):
    """与 board_server.read_sample 一致：BGR->RGB，保持 uint8 0-255，NHWC。

    这条路径把归一化交给 RKNN 内部(mean=0/std=255)完成，是 RKNN 的惯用做法，
    也是 INT8 量化校准能对得上的唯一形式。
    """
    padded, scale, (dw, dh) = letterbox(img_bgr, imgsz)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    return rgb[np.newaxis, ...], scale, (dw, dh)   # (1,H,W,3) uint8


def summarize(tag, out):
    """打印输出的 box/cls 数值范围，判定差异位置。"""
    o = np.asarray(out)
    if o.ndim == 3 and o.shape[1] in (4, 6, 8, 10):
        v = o[0]
    elif o.ndim == 3 and o.shape[2] in (4, 6, 8, 10):
        v = o[0].T
    else:
        v = o.reshape(-1, o.shape[-1]).T
    box, cls = v[:4], v[4:]
    print("  [%s] shape=%s dtype=%s" % (tag, o.shape, o.dtype))
    print("        box min=%.3f max=%.3f mean=%.3f" % (box.min(), box.max(), box.mean()))
    print("        cls min=%.4f max=%.4f mean=%.5f n>=0.25: %d" %
          (cls.min(), cls.max(), cls.mean(), int((cls >= 0.25).sum())))
    print("        per-class max: %s" % np.round(cls.max(axis=1), 4).tolist())
    # 若输出是 logits，这一行能直接看出 sigmoid 之后应该是多少
    sig = 1.0 / (1.0 + np.exp(-np.clip(cls, -50, 50)))
    print("        sigmoid(cls) max=%.4f  n>=0.25: %d  per-class: %s" %
          (sig.max(), int((sig >= 0.25).sum()), np.round(sig.max(axis=1), 4).tolist()))
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["ort", "sim", "lite"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--image", default="", help="图片路径；给了 --load-blob 时可省略")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--save-blob", default="", help="把 blob 存成 npy，供跨进程对比输入是否一致")
    ap.add_argument("--load-blob", default="", help="直接读入已存好的 blob，替代图片预处理")
    ap.add_argument("--no-norm", action="store_true",
                    help="config 里不传 mean_values/std_values，用于验证归一化是否被重复施加")
    ap.add_argument("--opt-level", type=int, default=3, help="sim 模式的 optimization_level")
    ap.add_argument("--std1", action="store_true",
                    help="sim 模式使用 mean=0/std=1/RGB2BGR（与 export_rknn.py 一致），"
                         "用于区分「std=1」和「完全不传」的差异")
    ap.add_argument("--swap-rb", action="store_true",
                    help="把 blob 的 R/B 通道对调，用于验证模型是否期望 BGR 输入")
    ap.add_argument("--u8", action="store_true",
                    help="sim/lite 模式改用 uint8(0-255) NHWC 输入（配 std=255 的模型），"
                         "对应 board_server.py 的生产输入形式")
    args = ap.parse_args()

    if args.load_blob:
        blob = np.load(args.load_blob)
        if blob.ndim == 3:
            blob = blob[None, ...]
        print("使用外部 blob: %s shape=%s dtype=%s" %
              (args.load_blob, blob.shape, blob.dtype))
    else:
        img = imread_unicode(args.image)
        if img is None:
            raise SystemExit("读图失败: %s" % args.image)
        if args.u8 and args.mode in ("sim", "lite"):
            blob, _, _ = preprocess_u8(img, args.imgsz)
        else:
            blob, _, _ = preprocess(img, args.imgsz)
        if args.save_blob:
            np.save(args.save_blob, blob[0] if blob.ndim == 4 and blob.shape[0] == 1 else blob)
            print("blob 已存: %s" % args.save_blob)

    print("输入统计: min=%.4f max=%.4f mean=%.4f" %
          (blob.min(), blob.max(), blob.mean()))
    if args.swap_rb:
        blob = blob[:, ::-1, :, :]
        print("已对调 R/B 通道")

    if args.mode == "ort":
        import onnxruntime as ort
        sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
        iname = sess.get_inputs()[0].name
        outs = sess.run(None, {iname: blob})
        summarize("ort", outs[0])

    elif args.mode == "sim":
        from rknn.api import RKNN
        rk = RKNN(verbose=False)
        cfg = dict(target_platform="rk3588")
        if args.std1:
            cfg.update(mean_values=[[0, 0, 0]], std_values=[[1, 1, 1]],
                       quant_img_RGB2BGR=True)
        elif not args.no_norm:
            cfg.update(mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]],
                       quant_img_RGB2BGR=True)
        cfg["optimization_level"] = args.opt_level
        print("sim config: %s" % cfg)
        rk.config(**cfg)
        if rk.load_onnx(model=args.model,
                        input_size_list=[[1, 3, args.imgsz, args.imgsz]]) != 0:
            raise SystemExit("load_onnx 失败")
        if rk.build(do_quantization=False) != 0:
            raise SystemExit("build 失败")
        # 模拟器：PC 侧软件跑 RKNN 编译产物(无 NPU)。结果对了 -> 编译器没问题，
        # 错 -> RKNN 编译本身就有问题。
        if rk.init_runtime() != 0:
            raise SystemExit("init_runtime(模拟器) 失败 —— 该版本模拟器可能不支持非量化模型")
        outs = rk.inference(inputs=[blob], data_format="nchw")
        summarize("sim", outs[0])
        rk.release()

    elif args.mode == "lite":
        from rknnlite.api import RKNNLite
        rk = RKNNLite()
        if rk.load_rknn(args.model) != 0:
            raise SystemExit("load_rknn 失败")
        if rk.init_runtime() != 0:
            raise SystemExit("init_runtime 失败")
        outs = rk.inference(inputs=[blob])
        summarize("lite", outs[0])
        rk.release()


if __name__ == "__main__":
    main()
