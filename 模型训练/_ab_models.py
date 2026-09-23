# -*- coding: utf-8 -*-
"""双模型对比：新增强集模型(aug2) vs 现役基线(_640)，在 180 张真实测试图上评测。

指标：
  top1  = 置信度最高的检出框所属类别是否 == 真值（对应"上位机大屏显示的判定"）
  cover = 真值类别是否出现在任一检出框中（召回视角，宽松）
用法: venv_cuda/Scripts/python.exe _ab_models.py
"""
import sys
from pathlib import Path
from collections import Counter

from ultralytics import YOLO

BASE = Path(__file__).resolve().parent
IMG_ROOT = BASE.parent / "图片"
CLASSES = ["crazing", "inclusion", "patches", "pitted_surface",
           "rolled-in_scale", "scratches"]

MODELS = [
    ("基线 _640 (0.783)", BASE / "runs" / "neu_yolo11n_640" / "weights" / "best.pt"),
    ("负样本 negdagm (0.785)", BASE / "runs" / "neu_yolo11n_negdagm" / "weights" / "best.pt"),
]

CONF = 0.20   # 板端生产阈值


def evaluate(tag, wpath):
    model = YOLO(str(wpath))
    names = model.names
    stat = {c: {"n": 0, "top1": 0, "cover": 0} for c in CLASSES}
    scratch_wrong = Counter()

    for cls in CLASSES:
        folder = IMG_ROOT / cls
        files = sorted(folder.glob("*.jpg"))
        for f in files:
            rs = model.predict(str(f), conf=CONF, iou=0.45, imgsz=640, verbose=False)
            boxes = rs[0].boxes
            dets = sorted(
                [(float(b.conf), names[int(b.cls)]) for b in boxes], reverse=True)
            stat[cls]["n"] += 1
            if dets:
                if dets[0][1] == cls:
                    stat[cls]["top1"] += 1
                else:
                    if cls == "scratches":
                        scratch_wrong[dets[0][1]] += 1
                if any(d[1] == cls for d in dets):
                    stat[cls]["cover"] += 1
        print(f"    {cls:<16} 完成 {len(files)} 张", flush=True)

    return stat, scratch_wrong


def report(tag, stat, scratch_wrong):
    print(f"\n===== {tag} =====")
    print(f"{'类别':<16}{'张数':>5}{'top1命中':>9}{'top1准确率':>11}{'含真值':>8}{'覆盖率':>9}")
    tot = {"n": 0, "top1": 0, "cover": 0}
    for c in CLASSES:
        s = stat[c]
        for k in tot:
            tot[k] += s[k]
        print(f"{c:<16}{s['n']:>5}{s['top1']:>9}"
              f"{s['top1']/s['n']*100:>10.1f}%{s['cover']:>8}"
              f"{s['cover']/s['n']*100:>8.1f}%")
    print(f"{'总计':<16}{tot['n']:>5}{tot['top1']:>9}"
          f"{tot['top1']/tot['n']*100:>10.1f}%{tot['cover']:>8}"
          f"{tot['cover']/tot['n']*100:>8.1f}%")
    if scratch_wrong:
        print(f"  scratches 被误判为: {dict(scratch_wrong)}")
    return tot


def main():
    results = []
    for tag, w in MODELS:
        if not w.exists():
            print(f"!! 权重不存在: {w}")
            continue
        print(f"\n>>> 评测 {tag}\n    权重: {w}")
        stat, sw = evaluate(tag, w)
        tot = report(tag, stat, sw)
        results.append((tag, tot))

    if len(results) == 2:
        print("\n===== 结论 =====")
        a, b = results
        print(f"  {a[0]:<22} top1={a[1]['top1']/a[1]['n']*100:.1f}%  "
              f"cover={a[1]['cover']/a[1]['n']*100:.1f}%")
        print(f"  {b[0]:<22} top1={b[1]['top1']/b[1]['n']*100:.1f}%  "
              f"cover={b[1]['cover']/b[1]['n']*100:.1f}%")


if __name__ == "__main__":
    main()
