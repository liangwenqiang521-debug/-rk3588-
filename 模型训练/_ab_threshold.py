# -*- coding: utf-8 -*-
"""A/B：全局阈值 0.20 vs per-class 阈值表，在 180 张真实缺陷图上对比。

目的：验证 board_server.py 改成 per-class 阈值后，检出率(top1/覆盖率)不倒退。
用法: venv_cuda/Scripts/python.exe _ab_threshold.py
"""
import sys
from pathlib import Path
from collections import Counter

from ultralytics import YOLO

BASE = Path(__file__).resolve().parent
IMG_ROOT = BASE.parent / "图片"
CLASSES = ["crazing", "inclusion", "patches", "pitted_surface",
           "rolled-in_scale", "scratches"]

MODEL = BASE / "runs" / "neu_yolo11n_640" / "weights" / "best.pt"

# 旧口径：全局 0.20
GLOBAL_CONF = 0.20
# 新口径：per-class（与 board_server.py 一致）
PER_CLASS = {
    'crazing': 0.20, 'inclusion': 0.16, 'patches': 0.20,
    'pitted_surface': 0.20, 'rolled-in_scale': 0.20, 'scratches': 0.30,
}


def filter_boxes(boxes, names, mode):
    """按 mode 过滤框，返回 [(conf, cls)] 排序列表。
    mode='global' 用 GLOBAL_CONF；mode='perclass' 用 PER_CLASS 查表。"""
    out = []
    for b in boxes:
        cname = names[int(b.cls)]
        conf = float(b.conf)
        th = GLOBAL_CONF if mode == 'global' else PER_CLASS.get(cname, GLOBAL_CONF)
        if conf > th:
            out.append((conf, cname))
    out.sort(reverse=True)
    return out


def evaluate(mode):
    model = YOLO(str(MODEL))
    names = model.names
    stat = {c: {"n": 0, "top1": 0, "cover": 0} for c in CLASSES}
    scratch_wrong = Counter()

    for cls in CLASSES:
        files = sorted((IMG_ROOT / cls).glob("*.jpg"))
        for f in files:
            rs = model.predict(str(f), conf=0.001, iou=0.45, imgsz=640, verbose=False)
            dets = filter_boxes(rs[0].boxes, names, mode)
            stat[cls]["n"] += 1
            if dets:
                if dets[0][1] == cls:
                    stat[cls]["top1"] += 1
                elif cls == "scratches":
                    scratch_wrong[dets[0][1]] += 1
                if any(d[1] == cls for d in dets):
                    stat[cls]["cover"] += 1
        print(f"    {cls:<16} 完成 {len(files)} 张", flush=True)
    return stat, scratch_wrong


def report(tag, stat, scratch_wrong):
    print(f"\n===== {tag} =====")
    print(f"{'类别':<16}{'张数':>5}{'top1':>6}{'top1%':>8}{'含真值':>7}{'覆盖率':>8}")
    tot = {"n": 0, "top1": 0, "cover": 0}
    for c in CLASSES:
        s = stat[c]
        for k in tot:
            tot[k] += s[k]
        print(f"{c:<16}{s['n']:>5}{s['top1']:>6}"
              f"{s['top1']/s['n']*100:>7.1f}%{s['cover']:>7}"
              f"{s['cover']/s['n']*100:>7.1f}%")
    print(f"{'总计':<16}{tot['n']:>5}{tot['top1']:>6}"
          f"{tot['top1']/tot['n']*100:>7.1f}%{tot['cover']:>7}"
          f"{tot['cover']/tot['n']*100:>7.1f}%")
    if scratch_wrong:
        print(f"  scratches 被误判为: {dict(scratch_wrong)}")
    return tot


def main():
    results = {}
    for mode, tag in [("global", "旧: 全局阈值 0.20"),
                      ("perclass", "新: per-class 阈值表")]:
        print(f"\n>>> 评测 {tag}")
        stat, sw = evaluate(mode)
        results[mode] = report(tag, stat, sw)

    g, p = results["global"], results["perclass"]
    print("\n===== 结论 =====")
    print(f"  全局 0.20 : top1={g['top1']/g['n']*100:.1f}%  cover={g['cover']/g['n']*100:.1f}%")
    print(f"  per-class : top1={p['top1']/p['n']*100:.1f}%  cover={p['cover']/p['n']*100:.1f}%")
    dt = (p['top1'] - g['top1']), (p['cover'] - g['cover'])
    print(f"  差值: top1 {dt[0]:+.1f}%  cover {dt[1]:+.1f}%")
    if dt[1] < 0:
        print("  ⚠️ 覆盖率下降，per-class 阈值有漏检风险，需复核 scratches 提阈是否过狠")
    else:
        print("  ✅ 覆盖率未降，per-class 阈值安全（不伤检出）")


if __name__ == "__main__":
    main()
