# -*- coding: utf-8 -*-
"""从 NEU 缺陷图裁「不含标注框」的干净块，生成近似 OK 负样本（B 档）

原理：NEU 每张图缺陷只占一块，其余大面积是正常钢材表面。把框外区域裁成
小块，即可得到近似良品图，用于「良品会不会误检」的离线快速验证。

⚠️ Windows + 中文路径：用 cv2.imencode().tofile() 写图（cv2.imwrite 会静默失败）。
"""
import os, glob, random
import numpy as np
import cv2

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, 'datasets', 'neu_det', 'images', 'train')
LBL_DIR = os.path.join(BASE, 'datasets', 'neu_det', 'labels', 'train')
OUT_DIR = os.path.join(BASE, 'datasets', 'neu_neg')   # 输出近似 OK 图

PATCH = 64          # 裁剪块边长（NEU 原图 200×200）
PER_IMG = 6         # 每张图裁几块
MAX_IMGS = 400      # 最多处理多少张原图（控制总量）
SEED = 42

random.seed(SEED)


def load_boxes(txt_path):
    """读 YOLO 标签 -> [(cx, cy, w, h)] 归一化坐标"""
    boxes = []
    with open(txt_path, encoding='utf-8') as f:
        for line in f:
            p = line.split()
            if len(p) < 5:
                continue
            _, cx, cy, w, h = map(float, p[:5])
            boxes.append((cx, cy, w, h))
    return boxes


def patch_overlaps(boxes, x0, y0, x1, y1, H, W):
    """判断裁剪块是否与任一缺陷框重叠（用归一化框反算像素）"""
    for (cx, cy, w, h) in boxes:
        bx0 = (cx - w / 2) * W
        by0 = (cy - h / 2) * H
        bx1 = (cx + w / 2) * W
        by1 = (cy + h / 2) * H
        # 块与框的交集面积
        ix0, iy0 = max(x0, bx0), max(y0, by0)
        ix1, iy1 = min(x1, bx1), min(y1, by1)
        if ix1 > ix0 and iy1 > iy0:
            return True
    return False


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    imgs = sorted(glob.glob(os.path.join(IMG_DIR, '*.jpg')))
    random.shuffle(imgs)
    imgs = imgs[:MAX_IMGS]

    total = 0
    for imp in imgs:
        name = os.path.splitext(os.path.basename(imp))[0]
        lbp = os.path.join(LBL_DIR, name + '.txt')
        if not os.path.exists(lbp):
            continue
        img = cv2.imdecode(np.fromfile(imp, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        H, W = img.shape[:2]
        boxes = load_boxes(lbp)
        if not boxes:
            continue

        got = 0
        tries = 0
        while got < PER_IMG and tries < 200:
            tries += 1
            # 随机左上角，保证块不越界
            x0 = random.randint(0, W - PATCH)
            y0 = random.randint(0, H - PATCH)
            if patch_overlaps(boxes, x0, y0, x0 + PATCH, y0 + PATCH, H, W):
                continue
            patch = img[y0:y0 + PATCH, x0:x0 + PATCH]
            out_name = '%s_n%d.jpg' % (name, got)
            ok, buf = cv2.imencode('.jpg', patch)
            if not ok:
                continue
            buf.tofile(os.path.join(OUT_DIR, out_name))
            got += 1
            total += 1
    print('生成近似 OK 负样本：%d 张 -> %s' % (total, OUT_DIR))


if __name__ == '__main__':
    main()
