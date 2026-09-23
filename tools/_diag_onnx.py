# -*- coding: utf-8 -*-
"""诊断：直接看 PC 端 ONNX 推理的原始输出张量。"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys

import cv2
import numpy as np
import onnxruntime as ort

ROOT = os.path.dirname(os.path.abspath(__file__))
ONNX = os.path.join(ROOT, "模型训练", "runs", "neu_yolo11n_640", "weights", "best.onnx")
IMG = os.path.join(ROOT, "_verify_imgs", "crazing_0.jpg")


def letterbox(img, size=640, color=(114, 114, 114)):
    h, w = img.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dw, dh = (size - nw) // 2, (size - nh) // 2
    return cv2.copyMakeBorder(r, dh, size - nh - dh, dw, size - nw - dw,
                              cv2.BORDER_CONSTANT, value=color)


def imread_unicode(path):
    """cv2.imread 在 Windows 下读不了中文路径，用 fromfile+imdecode 绕过。"""
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def main():
    if not os.path.exists(ONNX):
        raise SystemExit("找不到 onnx: %s" % ONNX)
    if not os.path.exists(IMG):
        raise SystemExit("找不到测试图: %s" % IMG)

    sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"])
    print("输入:", [(i.name, i.shape) for i in sess.get_inputs()])
    print("输出:", [(o.name, o.shape) for o in sess.get_outputs()])

    img = imread_unicode(IMG)
    padded = letterbox(img)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    blob = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None, ...]

    out = sess.run(None, {sess.get_inputs()[0].name: blob})[0]
    print()
    print("输出张量 shape:", out.shape, out.dtype)

    if out.ndim == 3:
        v = out[0]                      # [4+nc, 8400]
    else:
        v = out
    print("转成 [C, N]:", v.shape)

    nc_guess = v.shape[0] - 4
    print("推断类别数:", nc_guess)
    print()
    box = v[:4]
    cls = v[4:]
    print("--- box 通道 (前4) ---")
    print("  min=%.3f max=%.3f mean=%.3f std=%.3f"
          % (box.min(), box.max(), box.mean(), box.std()))
    print("--- cls 通道 (后%d) ---" % nc_guess)
    print("  min=%.4f max=%.4f mean=%.4f std=%.4f"
          % (cls.min(), cls.max(), cls.mean(), cls.std()))

    print()
    print("--- 每类最大 logit / sigmoid 后 ---")
    names = ["crazing", "inclusion", "patches", "pitted_surface",
             "rolled-in_scale", "scratches"]
    for c in range(cls.shape[0]):
        col = cls[c]
        mx = float(col.max())
        sig = 1.0 / (1.0 + np.exp(-mx))
        nm = names[c] if c < len(names) else "class_%d" % c
        print("  %-16s max_logit=%8.3f  ->sigmoid=%.4f   (超0.25的: %d 个)"
              % (nm, mx, sig, int((col > 0.25).sum())))

    # 最高分位置
    i = int(np.argmax(cls.max(axis=0)))
    print()
    print("最佳候选列 index=%d  该列 box(cx,cy,w,h)=%s"
          % (i, np.round(box[:, i], 2).tolist()))
    print("  该列各类 logit:", np.round(cls[:, i], 3).tolist())


if __name__ == "__main__":
    main()
