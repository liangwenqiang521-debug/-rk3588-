# -*- coding: utf-8 -*-
"""板端全量批量验证：NEU 6 类 × 30 张 = 180 张。

按文件名前缀（crazing_001.jpg 等）推断真实类别，逐图跑 best_neu6.rknn（uint8 输入，
RKNN 内部 std=255 归一化，与生产路径完全一致），统计每类检出率 / 平均置信度 / 漏检明细。

用法：
    python3 batch_verify.py <model.rknn> <图片目录> [conf] [--json 输出路径]
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import board_infer as bi
from rknnlite.api import RKNNLite

NAMES = ["crazing", "inclusion", "patches", "pitted_surface",
         "rolled-in_scale", "scratches"]


def gt_cls(fname):
    """从文件名推断真实类别标签。"""
    stem = os.path.basename(fname)
    for c in NAMES:
        if stem.startswith(c):
            return c
    return None


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "/root/rknn/best_neu6.rknn"
    imgdir = sys.argv[2] if len(sys.argv) > 2 else "/root/rknn/testset"
    conf = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25
    json_out = None
    if "--json" in sys.argv:
        json_out = sys.argv[sys.argv.index("--json") + 1]

    rknn = RKNNLite()
    if rknn.load_rknn(model) != 0:
        raise SystemExit("load_rknn 失败: %s" % model)
    if rknn.init_runtime() != 0:
        raise SystemExit("init_runtime 失败")

    imgs = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        imgs += glob.glob(os.path.join(imgdir, ext))
    imgs.sort()

    # 每类统计：总张数 / 检出张数 / 置信度列表 / 漏检明细
    per_cls = {c: {"total": 0, "hit": 0, "confs": [], "miss": []} for c in NAMES}
    t0 = time.time()

    for p in imgs:
        label = gt_cls(p)
        frame = cv2.imread(p)
        if frame is None or label is None:
            continue
        blob, scale, pad = bi.preprocess(frame, 640)   # uint8 NHWC
        outputs = rknn.inference(inputs=[blob])
        defects = bi.postprocess(outputs[0], scale, pad, frame.shape,
                                 conf_thres=conf, iou_thres=0.45, names=NAMES)

        st = per_cls[label]
        st["total"] += 1
        # 正确检出 = 该类别的框里存在 ≥conf 的目标
        matched = [d for d in defects if d["cls"] == label]
        if matched:
            st["hit"] += 1
            st["confs"].append(max(d["conf"] for d in matched))
        else:
            # 记录漏检时模型实际预测了哪些类（用于分析混淆）
            pred = {d["cls"]: round(d["conf"], 3) for d in defects}
            st["miss"].append({"file": os.path.basename(p), "pred": pred})

    rknn.release()
    elapsed = time.time() - t0

    # 汇总输出
    print("=" * 68)
    print("NEU 6 类板端全量验证  conf=%.2f  model=%s" % (conf, os.path.basename(model)))
    print("=" * 68)
    grand_total = grand_hit = 0
    for c in NAMES:
        st = per_cls[c]
        n = st["total"]
        h = st["hit"]
        grand_total += n
        grand_hit += h
        rate = (h / n * 100) if n else 0.0
        avg = (sum(st["confs"]) / len(st["confs"])) if st["confs"] else 0.0
        print("%-16s 检出 %2d/%2d  (%.1f%%)  平均置信度 %.3f  %s" %
              (c, h, n, rate, avg, "漏检 %d" % len(st["miss"]) if st["miss"] else ""))

    overall = grand_hit / grand_total * 100 if grand_total else 0.0
    print("-" * 68)
    print("总体检出率: %d/%d (%.1f%%)  耗时 %.1fs (%.0f 张/秒)" %
          (grand_hit, grand_total, overall, elapsed, grand_total / elapsed if elapsed else 0))

    # 漏检明细
    miss_total = sum(len(per_cls[c]["miss"]) for c in NAMES)
    if miss_total:
        print("-" * 68)
        print("漏检明细（真实类别 → 模型实际预测）:")
        for c in NAMES:
            for m in per_cls[c]["miss"]:
                print("  [%s] %s  →  %s" % (c, m["file"], m["pred"] or "无预测"))

    if json_out:
        out = {
            "conf": conf, "model": os.path.basename(model),
            "total": grand_total, "hit": grand_hit,
            "rate": round(overall, 2), "elapsed_s": round(elapsed, 2),
            "per_class": {
                c: {
                    "total": per_cls[c]["total"], "hit": per_cls[c]["hit"],
                    "rate": round(per_cls[c]["hit"] / per_cls[c]["total"] * 100, 2)
                    if per_cls[c]["total"] else 0.0,
                    "avg_conf": round(sum(per_cls[c]["confs"]) / len(per_cls[c]["confs"]), 3)
                    if per_cls[c]["confs"] else 0.0,
                    "miss": per_cls[c]["miss"],
                } for c in NAMES
            },
        }
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("结果已写入: %s" % json_out)


if __name__ == "__main__":
    main()
