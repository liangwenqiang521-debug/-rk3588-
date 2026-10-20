# -*- coding: utf-8 -*-
"""从 缺陷检测扩展 数据集每类抽 1 张代表样本，拼成 9x5 矩阵缩略图。
权威 cls 定义 = infer.py CLASSES_39（cls 0~38），中文名 = NAME_ZH。
用法：  venv_cuda/Scripts/python.exe tools/_render_classes39_thumbs.py
"""
import os
import sys
import glob
import numpy as np
import cv2

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(_ROOT, '缺陷检测扩展', 'images', 'train')
LABELS = os.path.join(_ROOT, '缺陷检测扩展', 'labels', 'train')
OUT = os.path.join(_ROOT, 'output', '缺陷检测项目周报_v4_39类', 'classes39_thumbs.png')

# cls id -> (英文 key, 中文名)
CLASSES = [
    (0, 'bright_scratch', '亮划痕'),
    (1, 'crazing', '龟裂'),
    (2, 'crease', '折痕'),
    (3, 'crescent_gap', '月牙缺口'),
    (4, 'dark_scratches', '暗划痕'),
    (5, 'finishing_roll_printing', '精轧辊印'),
    (6, 'inclusion', '夹杂物'),
    (7, 'iron_scale_compression', '氧化铁皮压入'),
    (8, 'iron_sheet_ash', '铁皮灰'),
    (9, 'oil_spot', '油污'),
    (10, 'oxide_scale_plate', '板系氧化铁皮'),
    (11, 'oxide_scale_temp', '温系氧化铁皮'),
    (12, 'patches', '斑块'),
    (13, 'pitted_surface', '麻面'),
    (14, 'punching', '冲孔'),
    (15, 'red_iron_sheet', '红斑铁皮'),
    (16, 'rolled-in_scale', '轧入氧化皮'),
    (17, 'rolled_pit', '轧制凹坑'),
    (18, 'secondary_rust_skin', '二次锈皮'),
    (19, 'silk_spot', '丝斑'),
    (20, 'slag_inclusion', '夹渣'),
    (21, 'waist_folding', '腰部折痕'),
    (22, 'water_spot', '水渍'),
    (23, 'welding_line', '焊缝线'),
    (24, 'white_rust', '白锈'),
    (25, 'cutting_opening', '切边开口'),
    (26, 'water_slag_mark', '水渣痕'),
    (27, 'slag_skin', '渣皮'),
    (28, 'longitudinal_crack', '纵向裂纹'),
    (29, 'warp', '翘曲'),
    (30, 'external_fold', '外折'),
    (31, 'wrinkle', '褶皱'),
    (32, 'blocky_scale', '块状氧化铁皮'),
    (33, 'striated_scale', '条纹氧化铁皮'),
    (34, 'foreign_obj', '异物'),
    (35, 'blowhole', '气孔'),
    (36, 'break', '断裂'),
    (37, 'fray', '散边毛刺'),
    (38, 'uneven', '厚薄不均'),
]

THUMB = 220
PAD = 8
HEAD = 42
COLS = 8
ROWS = 5  # 5*8 = 40 >= 39


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ext = os.path.splitext(p)[1] or '.png'
    cv2.imencode(ext, img)[1].tofile(p)


def pick_per_class():
    """每个 cls 取第一张出现的图（图片本身的 label 中含该 cls 即算）。"""
    picked = {}  # cls -> (img_path, label_path)
    label_files = sorted(glob.glob(os.path.join(LABELS, '*.txt')))
    print('扫描 %d 个 label 文件...' % len(label_files))
    for lf in label_files:
        try:
            with open(lf, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            continue
        cls_in_file = set()
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                cls = int(ln.split()[0])
            except Exception:
                continue
            if 0 <= cls < 39:
                cls_in_file.add(cls)
        for cls in cls_in_file:
            if cls in picked:
                continue
            stem = os.path.splitext(os.path.basename(lf))[0]
            img_path = os.path.join(IMAGES, stem + '.jpg')
            if not os.path.exists(img_path):
                continue
            picked[cls] = (img_path, lf)
            if len(picked) == 39:
                return picked
    return picked


def main():
    picked = pick_per_class()
    print('已选 %d/39 类' % len(picked))
    if len(picked) < 39:
        miss = [c[0] for c in CLASSES if c[0] not in picked]
        print('缺失 cls:', miss)

    cw, ch = THUMB, THUMB + HEAD
    canvas_h = ROWS * ch + PAD * 2
    canvas_w = COLS * cw + PAD * 2
    canvas = np.full((canvas_h, canvas_w, 3), 248, np.uint8)

    for cls_id, en, zh in CLASSES:
        idx = cls_id
        r, c = divmod(idx, COLS)
        x0 = PAD + c * cw
        y0 = PAD + r * ch

        # 缩略图
        if cls_id in picked:
            img = imread_u(picked[cls_id][0])
            if img is not None:
                t = cv2.resize(img, (THUMB, THUMB), interpolation=cv2.INTER_AREA)
                canvas[y0 + HEAD:y0 + HEAD + THUMB, x0:x0 + THUMB] = t
        else:
            cv2.rectangle(canvas, (x0 + 4, y0 + HEAD + 4),
                          (x0 + THUMB - 4, y0 + HEAD + THUMB - 4),
                          (220, 220, 220), -1)
        cv2.rectangle(canvas, (x0, y0), (x0 + THUMB, y0 + ch - 1),
                      (200, 200, 200), 1)

        # 标签
        line1 = '%02d  %s' % (cls_id, en)
        line2 = zh
        cv2.putText(canvas, line1, (x0 + 4, y0 + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (20, 20, 20), 1, cv2.LINE_AA)
        cv2.putText(canvas, line2, (x0 + 4, y0 + 33),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (21, 101, 192), 1, cv2.LINE_AA)

    # 顶部标题
    title_h = 30
    title_canvas = np.full((title_h, canvas_w, 3), 255, np.uint8)
    cv2.putText(title_canvas, '39 industrial steel surface defect classes (cls 0-38)',
                (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (21, 101, 192), 2, cv2.LINE_AA)
    final = np.vstack([title_canvas, canvas])
    imwrite_u(OUT, final)
    print('已生成 %s  (%dx%d)' % (OUT, final.shape[1], final.shape[0]))


if __name__ == '__main__':
    main()
