# -*- coding: utf-8 -*-
"""为板端挑选覆盖 39 类的代表性样本图。

背景：板端 /root/rknn/samples/ 原本只有 24 张 NEU 6 类图，连板轮播自然只出 6 类。
本脚本从 缺陷检测扩展/ 中，按标签为每个类别挑 1 张「最干净、框最大」的图，
再补几张负样本（无缺陷），输出到 tools/_stage39/，供上传替换板端样本。

用法：  .venv/Scripts/python.exe tools/_pick_samples39.py
"""
import os
import sys
import glob
import shutil

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(_ROOT, '缺陷检测扩展')
STAGE = os.path.join(_ROOT, 'tools', '_stage39')

CLASSES = [
    'bright_scratch', 'crazing', 'crease', 'crescent_gap', 'dark_scratches',
    'finishing_roll_printing', 'inclusion', 'iron_scale_compression',
    'iron_sheet_ash', 'oil_spot', 'oxide_scale_plate', 'oxide_scale_temp',
    'patches', 'pitted_surface', 'punching', 'red_iron_sheet',
    'rolled-in_scale', 'rolled_pit', 'secondary_rust_skin', 'silk_spot',
    'slag_inclusion', 'waist_folding', 'water_spot', 'welding_line',
    'white_rust', 'cutting_opening', 'water_slag_mark', 'slag_skin',
    'longitudinal_crack', 'warp', 'external_fold', 'wrinkle',
    'blocky_scale', 'striated_scale', 'foreign_obj', 'blowhole',
    'break', 'fray', 'uneven',
]


def read_label(txt):
    """返回 [(cls, area), ...]；area = w*h（归一化）。"""
    out = []
    try:
        for ln in open(txt, encoding='utf-8'):
            p = ln.split()
            if len(p) >= 5:
                try:
                    out.append((int(float(p[0])), float(p[3]) * float(p[4])))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def main():
    img_dir = os.path.join(DS, 'images', 'val')
    lab_dir = os.path.join(DS, 'labels', 'val')

    imgs = {}
    for f in glob.glob(os.path.join(img_dir, '*')):
        stem = os.path.splitext(os.path.basename(f))[0]
        imgs[stem] = f
    print('val 图 %d 张' % len(imgs))

    # 逐个标签文件解析
    per_class = {}   # cls -> list[(n_labels, -max_area, stem)]
    has_label = set()
    for txt in glob.glob(os.path.join(lab_dir, '*.txt')):
        stem = os.path.splitext(os.path.basename(txt))[0]
        if stem not in imgs:
            continue
        rows = read_label(txt)
        if not rows:
            continue
        has_label.add(stem)
        n = len(rows)
        area_of = {}
        for c, a in rows:
            area_of[c] = max(area_of.get(c, 0.0), a)
        for c, a in area_of.items():
            per_class.setdefault(c, []).append((n, -a, stem))

    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)

    picked = set()
    lines = []
    for cid, key in enumerate(CLASSES):
        cand = per_class.get(cid, [])
        if not cand:
            lines.append('  [%2d] %-26s 无候选样本！' % (cid, key))
            continue
        # 先按标签数少、再按框大多排序
        cand.sort()
        n, nega, stem = cand[0]
        picked.add(stem)
        dst = os.path.join(STAGE, '%02d_%s.jpg' % (cid, key))
        shutil.copyfile(imgs[stem], dst)
        lines.append('  [%2d] %-26s <- %s（标签 %d 个，最大框 %.3f）'
                     % (cid, key, stem, n, -nega))

    # 补 3 张负样本（val 中无标签文件的图）
    negs = sorted(set(imgs) - has_label)
    n_neg = 0
    for stem in negs:
        if n_neg >= 3:
            break
        dst = os.path.join(STAGE, 'neg_%02d_%s.jpg' % (n_neg, 'no_defect'))
        shutil.copyfile(imgs[stem], dst)
        n_neg += 1
        lines.append('  [--] %-26s <- %s（负样本/无缺陷）' % ('neg_no_defect', stem))

    print('\n=== 挑选结果 ===')
    for l in lines:
        print(l)
    files = sorted(glob.glob(os.path.join(STAGE, '*.jpg')))
    print('\n落盘 %d 张 -> %s' % (len(files), STAGE))


if __name__ == '__main__':
    main()
