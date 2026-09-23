# -*- coding: utf-8 -*-
"""良品误检验证：用 PC 端 .pt 模型批量推理近似 OK 负样本，统计误检率

回答核心问题：NEU 6 类模型面对「正常钢材表面」会不会误检。
"""
import os, glob, sys
import numpy as np
import cv2
from ultralytics import YOLO

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(BASE, 'runs', 'neu_yolo11n_640', 'weights', 'best.pt')
NEG_DIR = os.path.join(BASE, 'datasets', 'neu_neg')

# 用与板端一致的 per-class 阈值口径（对齐刚改的 board_server.py）
PER_CLASS_THRES = {
    'crazing': 0.20, 'inclusion': 0.16, 'patches': 0.20,
    'pitted_surface': 0.20, 'rolled-in_scale': 0.20, 'scratches': 0.30,
}
DEFAULT_THRES = 0.20


def main():
    model = YOLO(MODEL)
    names = model.names
    imgs = sorted(glob.glob(os.path.join(NEG_DIR, '*.jpg')))
    print('负样本总数:', len(imgs))

    fp_imgs = 0          # 有误检的图数
    total_boxes = 0      # 总误检框数
    cls_counter = {}     # 各类误检框数
    conf_list = []       # 误检框置信度

    for imp in imgs:
        r = model.predict(imp, conf=0.001, iou=0.45, imgsz=640, verbose=False)[0]
        kept = 0
        for b in r.boxes:
            cid = int(b.cls)
            cname = names[cid]
            conf = float(b.conf)
            th = PER_CLASS_THRES.get(cname, DEFAULT_THRES)
            if conf > th:            # 严格大于，与 board_server 的 `>` 一致
                kept += 1
                cls_counter[cname] = cls_counter.get(cname, 0) + 1
                conf_list.append(conf)
        if kept > 0:
            fp_imgs += 1
            total_boxes += kept

    n = len(imgs)
    print('\n===== 良品误检报告 =====')
    print('总 OK 图数: %d' % n)
    print('有误检的图: %d  (%.1f%%)' % (fp_imgs, 100.0 * fp_imgs / n if n else 0))
    print('总误检框数: %d  (平均 %.2f 框/图)' % (total_boxes, total_boxes / n if n else 0))
    print('\n各类误检分布:')
    for c in sorted(cls_counter, key=lambda k: -cls_counter[k]):
        print('  %-16s %d' % (c, cls_counter[c]))
    if conf_list:
        conf_list.sort()
        print('\n误检框置信度: min=%.2f 中位=%.2f 最大=%.2f' % (
            conf_list[0], conf_list[len(conf_list)//2], conf_list[-1]))
        low = sum(1 for c in conf_list if c < 0.35)
        print('  <0.35 的低置信误检占 %d/%d (%.0f%%) —— 可用提阈压制'
              % (low, len(conf_list), 100.0*low/len(conf_list)))


if __name__ == '__main__':
    main()
