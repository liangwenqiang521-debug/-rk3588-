# -*- coding: utf-8 -*-
"""板端模型验证：用真实图片推理，只打印统计（不刷屏）。

复用 board_infer.py 的预处理/后处理，确保与生产脚本完全一致。

用法：
    python3 board_verify.py <model.rknn> <图片目录> [conf]
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import board_infer as bi
from rknnlite.api import RKNNLite

NAMES = ["crazing", "inclusion", "patches", "pitted_surface",
         "rolled-in_scale", "scratches"]


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "/root/rknn/best_neu6.rknn"
    imgdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/vimgs"
    conf = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25

    rknn = RKNNLite()
    if rknn.load_rknn(model) != 0:
        raise SystemExit("load_rknn 失败: %s" % model)
    if rknn.init_runtime() != 0:
        raise SystemExit("init_runtime 失败")
    print("模型: %s" % model)
    print("-" * 64)

    imgs = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        imgs += glob.glob(os.path.join(imgdir, ext))
    imgs.sort()
    if not imgs:
        raise SystemExit("目录无图片: %s" % imgdir)

    for p in imgs:
        frame = cv2.imread(p)
        if frame is None:
            continue
        blob, scale, pad = bi.preprocess(frame, 640)
        outputs = rknn.inference(inputs=[blob])

        # 诊断：看清 RKNN 原始输出的形状与数值范围
        o = np.asarray(outputs[0])
        flat = o.reshape(-1, o.shape[-1]) if o.ndim >= 2 else o.reshape(1, -1)
        if o.ndim == 3 and o.shape[1] in (4, 6, 8, 10):
            v = o[0]                       # [C, N]
        elif o.ndim == 3 and o.shape[2] in (4, 6, 8, 10):
            v = o[0].T                     # [N, C] -> [C, N]
        else:
            v = o.reshape(-1, o.shape[-1]).T
        print("     [diag] raw_shape=%s  dtype=%s  C=%d N=%d" %
              (o.shape, o.dtype, v.shape[0], v.shape[1]))
        print("     [diag] box  min=%.3f max=%.3f | cls min=%.4f max=%.4f mean=%.5f" %
              (v[:4].min(), v[:4].max(), v[4:].min(), v[4:].max(), v[4:].mean()))

        defects = bi.postprocess(outputs[0], scale, pad, frame.shape,
                                 conf_thres=conf, iou_thres=0.45, names=NAMES)
        counts = {}
        for d in defects:
            counts[d["cls"]] = counts.get(d["cls"], 0) + 1
        top = max((d["conf"] for d in defects), default=0.0)
        print(json.dumps({
            "file": os.path.basename(p),
            "n": len(defects),
            "counts": counts,
            "top_conf": round(top, 3),
        }, ensure_ascii=False))

    rknn.release()


if __name__ == "__main__":
    main()
