# -*- coding: utf-8 -*-
"""方案A 三维验收：基线 _640 vs 1:1 negdagm vs 1:2 negdagm_half

维度：
  1) DAGM val 1200 无缺陷误检率（per-class 阈值口径）
  2) NEU val mAP50 / mAP50-95
  3) 180 张真实缺陷图 top1 / cover

用法: venv_cuda/Scripts/python.exe _verify_neg_half_ab.py
"""
import os, glob
from pathlib import Path
from collections import Counter

from ultralytics import YOLO

BASE = Path(__file__).resolve().parent
NEG_VAL = BASE / 'datasets' / 'dagm_neg' / 'images' / 'val'
IMG_ROOT = BASE.parent / "图片"
CLASSES = ["crazing", "inclusion", "patches", "pitted_surface",
           "rolled-in_scale", "scratches"]

MODELS = {
    'baseline_640':  BASE / 'runs' / 'neu_yolo11n_640' / 'weights' / 'best.pt',
    'negdagm_1to1':  BASE / 'runs' / 'neu_yolo11n_negdagm' / 'weights' / 'best.pt',
    'negdagm_1to2':  BASE / 'runs' / 'neu_yolo11n_negdagm_half' / 'weights' / 'best.pt',
}

PER_CLASS_THRES = {
    'crazing': 0.20, 'inclusion': 0.16, 'patches': 0.20,
    'pitted_surface': 0.20, 'rolled-in_scale': 0.20, 'scratches': 0.30,
}
DEFAULT_THRES = 0.20
CONF = 0.20   # 180 图 top1 用的板端生产阈值


def fp_dagm(model, names, imgs):
    fp_imgs = 0
    total_boxes = 0
    cls_counter = Counter()
    for imp in imgs:
        r = model.predict(imp, conf=0.001, iou=0.45, imgsz=640, verbose=False)[0]
        kept = 0
        for b in r.boxes:
            cname = names[int(b.cls)]
            th = PER_CLASS_THRES.get(cname, DEFAULT_THRES)
            if float(b.conf) > th:
                kept += 1
                cls_counter[cname] += 1
        if kept > 0:
            fp_imgs += 1
            total_boxes += kept
    return fp_imgs, len(imgs), total_boxes, cls_counter


def neu_map(model):
    m = model.val(data=str(BASE / 'data_neu_dagm_half.yaml'), split='val',
                  imgsz=640, verbose=False)
    return float(m.box.map50), float(m.box.map)


def top1_180(model, names):
    stat = {c: {"n": 0, "top1": 0, "cover": 0} for c in CLASSES}
    scratch_wrong = Counter()
    for cls in CLASSES:
        for f in sorted((IMG_ROOT / cls).glob("*.jpg")):
            rs = model.predict(str(f), conf=CONF, iou=0.45, imgsz=640, verbose=False)
            dets = sorted([(float(b.conf), names[int(b.cls)]) for b in rs[0].boxes],
                          reverse=True)
            stat[cls]["n"] += 1
            if dets:
                if dets[0][1] == cls:
                    stat[cls]["top1"] += 1
                elif cls == "scratches":
                    scratch_wrong[dets[0][1]] += 1
                if any(d[1] == cls for d in dets):
                    stat[cls]["cover"] += 1
    tot = {"n": 0, "top1": 0, "cover": 0}
    for c in CLASSES:
        for k in tot:
            tot[k] += stat[c][k]
    return tot, stat, scratch_wrong


def main():
    dagm_val = sorted(NEG_VAL.glob('*.png'))
    print('DAGM val 无缺陷: %d 张\n' % len(dagm_val))

    results = {}
    for tag, mp in MODELS.items():
        if not mp.exists():
            print('!! 权重不存在: %s\n' % mp)
            continue
        print('==== 模型 %s ====' % tag)
        model = YOLO(str(mp))
        names = model.names

        fp, n, nbox, cc = fp_dagm(model, names, dagm_val)
        print('  DAGM 误检: %d/%d (%.1f%%)  总框=%d' % (fp, n, 100.0*fp/n, nbox))
        if cc:
            print('    分布:', dict(cc.most_common(5)))

        m50, m5095 = neu_map(model)
        print('  NEU val:  mAP50=%.4f  mAP50-95=%.4f' % (m50, m5095))

        tot, stat, sw = top1_180(model, names)
        print('  180图 top1: %d/%d (%.1f%%)  cover=%.1f%%' % (
            tot['top1'], tot['n'], 100.0*tot['top1']/tot['n'],
            100.0*tot['cover']/tot['n']))
        if sw:
            print('    scratches 误判:', dict(sw))
        # 分类明细
        for c in CLASSES:
            s = stat[c]
            print('      %-16s top1 %2d/%-2d (%4.1f%%)  cover %2d' % (
                c, s['top1'], s['n'], 100.0*s['top1']/s['n'], s['cover']))

        results[tag] = (fp, n, m50, m5095, tot, stat, sw)
        print()

    print('\n===== 汇总对比 =====')
    print('%-14s %-12s %-10s %-12s %-12s' % (
        '模型', 'DAGM误检', 'NEUmAP50', 'NEUmAP50-95', '180图top1'))
    for tag, (fp, n, m50, m5095, tot, stat, sw) in results.items():
        print('%-14s %-12s %-10s %-12s %-12s' % (
            tag, '%.1f%%(%d/%d)' % (100.0*fp/n, fp, n), '%.4f' % m50,
            '%.4f' % m5095, '%.1f%%(%d/%d)' % (
                100.0*tot['top1']/tot['n'], tot['top1'], tot['n'])))


if __name__ == '__main__':
    main()
