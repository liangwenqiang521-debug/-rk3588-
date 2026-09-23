# -*- coding: utf-8 -*-
"""DAGM 无缺陷图误检验证：用 PC 端 .pt 模型批量推理 DAGM 负样本，统计误检率

这是「真实无缺陷负样本」的正式口径（区别于之前 neu_neg 的近似 OK 块）。
DAGM 是 512x512 灰度纹理图，域与钢材表面不同，但能回答：
  「模型对『非缺陷纹理』的抑制能力有多强」——正是负样本闭环的核心问题。

用法：
    venv_cuda/Scripts/python.exe _verify_dagm_fp.py
"""
import os, glob
import numpy as np
from ultralytics import YOLO

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(BASE, 'runs', 'neu_yolo11n_640', 'weights', 'best.pt')
NEG_DIR = os.path.join(BASE, 'datasets', 'dagm_neg', 'images')

# 与板端 board_server.py 一致的 per-class 阈值口径
PER_CLASS_THRES = {
    'crazing': 0.20, 'inclusion': 0.16, 'patches': 0.20,
    'pitted_surface': 0.20, 'rolled-in_scale': 0.20, 'scratches': 0.30,
}
DEFAULT_THRES = 0.20


def evaluate(model, names, imgs, tag):
    fp_imgs = 0
    total_boxes = 0
    cls_counter = {}
    conf_list = []
    for imp in imgs:
        r = model.predict(imp, conf=0.001, iou=0.45, imgsz=640, verbose=False)[0]
        kept = 0
        for b in r.boxes:
            cname = names[int(b.cls)]
            conf = float(b.conf)
            th = PER_CLASS_THRES.get(cname, DEFAULT_THRES)
            if conf > th:
                kept += 1
                cls_counter[cname] = cls_counter.get(cname, 0) + 1
                conf_list.append(conf)
        if kept > 0:
            fp_imgs += 1
            total_boxes += kept
    n = len(imgs)
    print('\n===== [%s] DAGM 无缺陷负样本误检报告 =====' % tag)
    print('OK 图数: %d' % n)
    if n == 0:
        print('  (无样本，跳过)')
        return
    print('有误检的图: %d  (%.2f%%)' % (fp_imgs, 100.0 * fp_imgs / n))
    print('总误检框数: %d  (平均 %.3f 框/图)' % (total_boxes, total_boxes / n))
    print('各类误检分布:')
    for c in sorted(cls_counter, key=lambda k: -cls_counter[k]):
        print('  %-16s %d' % (c, cls_counter[c]))
    if conf_list:
        conf_list.sort()
        print('误检框置信度: min=%.2f 中位=%.2f 最大=%.2f' % (
            conf_list[0], conf_list[len(conf_list)//2], conf_list[-1]))
        low = sum(1 for c in conf_list if c < 0.35)
        print('  <0.35 低置信误检占 %d/%d (%.0f%%)' % (low, len(conf_list), 100.0*low/len(conf_list)))
    return fp_imgs, n


def main():
    model = YOLO(MODEL)
    names = model.names

    # 分 train/val 两批统计（DAGM 的 Train/Test 划分，避免泄露口径混用）
    for split in ('train', 'val'):
        d = os.path.join(NEG_DIR, split)
        if not os.path.exists(d):
            print('[%s] 目录不存在: %s' % (split, d))
            continue
        imgs = sorted(glob.glob(os.path.join(d, '*.png')))
        print('\n[%s] 扫描到 %d 张无缺陷图' % (split, len(imgs)))
        evaluate(model, names, imgs, split)


if __name__ == '__main__':
    main()
