# -*- coding: utf-8 -*-
"""板端 RKNN vs ONNX 数值一致性校验（39 类）。

目的：确认 .rknn 的分类头没有被压塌（归一化配对错误的典型症状）。
做法：同一张图 -> 同一份 RGB uint8 NHWC 预处理
  * rknn.inference(inputs=[blob])            （RKNN 内部 /255）
  * onnxruntime: blob/255 转 NCHW float32     （ONNX 期望的归一化输入）
比较：整体余弦相似度、最大绝对差、类别分数块的最大差、top1 类别是否一致。

用法: PYTHONPATH=/root/rknn_convert/libs python3 _verify_rknn39.py
"""
import glob
import os
import sys

import cv2
import numpy as np

RKNN_MODEL = "/root/rknn_convert/best_steel39_640.rknn"
ONNX_MODEL = "/root/rknn_convert/best_steel39.onnx"
SAMPLE_DIRS = ["/root/rknn/samples", "/root/rknn/testset"]
N_IMG = 10
NC = 39


def letterbox(img, size=640, pad=114):
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return np.full((size, size, 3), pad, dtype=np.uint8)
    scale = min(size / w, size / h)
    nw, nh = int(w * scale), int(h * scale)
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), pad, dtype=np.uint8)
    canvas[:nh, :nw] = r
    return canvas


def collect_images():
    out = []
    for d in SAMPLE_DIRS:
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            out += sorted(glob.glob(os.path.join(d, ext)))
    return out[:N_IMG]


def main():
    imgs = collect_images()
    if not imgs:
        print("没有可用样本图")
        return 1
    print("样本数:", len(imgs))

    from rknnlite.api import RKNNLite
    import onnxruntime as ort

    rk = RKNNLite(verbose=False)
    if rk.load_rknn(RKNN_MODEL) != 0:
        print("load_rknn 失败")
        return 1
    if rk.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2) != 0:
        print("init_runtime 失败")
        return 1

    sess = ort.InferenceSession(ONNX_MODEL, providers=["CPUExecutionProvider"])
    iname = sess.get_inputs()[0].name

    print("%-28s %8s %9s %9s  %-22s %-22s" %
          ("image", "cos", "maxabs", "cls_maxd", "rknn_top1", "onnx_top1"))
    worst_cos = 1.0
    agree_top = 0
    for p in imgs:
        img = cv2.imread(p)
        if img is None:
            continue
        blob = cv2.cvtColor(letterbox(img), cv2.COLOR_BGR2RGB)[np.newaxis, ...]  # uint8 NHWC RGB

        y_rk = np.array(rk.inference(inputs=[blob])[0])              # (1,43,8400)
        x_on = blob.transpose(0, 3, 1, 2).astype(np.float32) / 255.0  # NCHW RGB [0,1]
        y_on = np.asarray(sess.run(None, {iname: x_on})[0])           # (1,43,8400)

        a = y_rk.reshape(-1).astype(np.float64)
        b = y_on.reshape(-1).astype(np.float64)
        cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        maxabs = float(np.max(np.abs(a - b)))

        # 类别分数块（前 4 通道是 box，4: 是类别概率）
        cs_rk = y_rk[0][4:4 + NC]     # (NC, 8400)
        cs_on = y_on[0][4:4 + NC]
        cls_maxd = float(np.max(np.abs(cs_rk - cs_on)))

        # 全图最高置信度锚点的类别
        i_rk = int(cs_rk.max(axis=0).argmax())
        c_rk = int(cs_rk[:, i_rk].argmax())
        v_rk = float(cs_rk[c_rk, i_rk])
        i_on = int(cs_on.max(axis=0).argmax())
        c_on = int(cs_on[:, i_on].argmax())
        v_on = float(cs_on[c_on, i_on])
        same = "=" if c_rk == c_on else "!"
        agree_top += int(c_rk == c_on)
        worst_cos = min(worst_cos, cos)

        print("%-28s %8.5f %9.4f %9.4f  cls%-3d(%.3f)%s    cls%-3d(%.3f)" %
              (os.path.basename(p)[:28], cos, maxabs, cls_maxd, c_rk, v_rk, same, c_on, v_on))

    rk.release()
    print("-" * 96)
    print("最差余弦相似度: %.5f   top1 一致: %d/%d" % (worst_cos, agree_top, len(imgs)))
    print("判定: %s" % ("PASS（分类头正常）" if worst_cos > 0.99 and agree_top == len(imgs) else "CHECK（需人工确认）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
