# -*- coding: utf-8 -*-
"""负样本重训 A/B 验收：基线 _640 vs 负样本重训 negdagm，对比 DAGM 误检率 + NEU mAP

口径与 _verify_dagm_fp.py 一致（per-class 阈值）。
"""
import os, glob, csv
from ultralytics import YOLO

BASE = os.path.dirname(os.path.abspath(__file__))
NEG_DIR = os.path.join(BASE, 'datasets', 'dagm_neg', 'images')

MODELS = {
    'baseline_640': os.path.join(BASE, 'runs', 'neu_yolo11n_640', 'weights', 'best.pt'),
    'negdagm':      os.path.join(BASE, 'runs', 'neu_yolo11n_negdagm', 'weights', 'best.pt'),
}

PER_CLASS_THRES = {
    'crazing': 0.20, 'inclusion': 0.16, 'patches': 0.20,
    'pitted_surface': 0.20, 'rolled-in_scale': 0.20, 'scratches': 0.30,
}
DEFAULT_THRES = 0.20


def fp_report(model, names, imgs, tag):
    fp_imgs = 0
    total_boxes = 0
    cls_counter = {}
    for imp in imgs:
        r = model.predict(imp, conf=0.001, iou=0.45, imgsz=640, verbose=False)[0]
        kept = 0
        for b in r.boxes:
            cname = names[int(b.cls)]
            th = PER_CLASS_THRES.get(cname, DEFAULT_THRES)
            if float(b.conf) > th:
                kept += 1
                cls_counter[cname] = cls_counter.get(cname, 0) + 1
        if kept > 0:
            fp_imgs += 1
            total_boxes += kept
    n = len(imgs)
    print('  [%s] OK图=%d  误检图=%d (%.2f%%)  总框=%d' % (
        tag, n, fp_imgs, 100.0*fp_imgs/n, total_boxes))
    for c in sorted(cls_counter, key=lambda k: -cls_counter[k]):
        print('      %-16s %d' % (c, cls_counter[c]))
    return fp_imgs, n


def neu_map(model):
    """在 NEU val 集上跑 mAP50 / mAP50-95"""
    m = model.val(data=os.path.join(BASE, 'data_neu_dagm.yaml'), split='val',
                  imgsz=640, verbose=False)
    return float(m.box.map50), float(m.box.map)


def main():
    dagm_val = sorted(glob.glob(os.path.join(NEG_DIR, 'val', '*.png')))
    print('DAGM val 无缺陷图: %d 张\n' % len(dagm_val))

    summary = []
    for tag, mp in MODELS.items():
        print('==== 模型 %s ====' % tag)
        model = YOLO(mp)
        names = model.names
        fp, n = fp_report(model, names, dagm_val, 'DAGM-val')
        m50, m5095 = neu_map(model)
        print('  NEU val: mAP50=%.4f  mAP50-95=%.4f' % (m50, m5095))
        summary.append((tag, fp, n, m50, m5095))
        print()

    print('\n===== 汇总对比 =====')
    print('%-14s %-14s %-14s %-16s %s' % ('模型', 'DAGM误检率', 'NEU mAP50', 'NEU mAP50-95', '结论'))
    for tag, fp, n, m50, m5095 in summary:
        print('%-14s %-14s %-14s %-16s' % (
            tag, '%.1f%%(%d/%d)' % (100.0*fp/n, fp, n), '%.4f' % m50, '%.4f' % m5095))


if __name__ == '__main__':
    main()
