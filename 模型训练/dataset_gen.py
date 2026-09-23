"""合成工业表面缺陷数据集生成器。

为「缺陷检测」项目生成可训练的 YOLO 格式数据集（无需外部下载）：
  - 背景：金属/铝型材表面（灰底 + 拉丝纹理 + 噪声 + 渐变）
  - 缺陷类别（4 类）：scratch 划痕 / dent 凹陷 / missing 缺料 / crack 裂纹
  - 输出：images/ + labels/（YOLO 归一化标注）+ data.yaml
  - 划分：train / val（默认 8:2），并混入少量无缺陷样本

用法：
  python dataset_gen.py                 # 默认 200 张
  python dataset_gen.py --num 400 --split 0.8
"""
import argparse
import math
import os
import random
from pathlib import Path

import cv2
import numpy as np

# 缺陷类别（顺序即 YOLO class id）
CLASSES = ["scratch", "dent", "missing", "crack"]


def save_img(path: str, img_bgr: np.ndarray):
    """用 imencode 写出，规避 OpenCV 中文路径 imwrite 失败问题。"""
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        raise RuntimeError(f"imencode failed: {path}")
    with open(path, "wb") as f:
        f.write(buf.tobytes())


def make_background(size: int, rng: random.Random) -> np.ndarray:
    base = rng.randint(120, 175)
    img = np.empty((size, size, 3), np.uint8)
    # 拉丝纹理（水平条纹）
    for y in range(size):
        v = base + rng.randint(-10, 10)
        img[y, :, :] = v
    # 整体渐变
    grad = np.linspace(0, rng.randint(-22, 22), size).astype(np.int16)
    img = img.astype(np.int16) + grad[None, :, None]
    # 高斯噪声
    noise = np.random.normal(0, 5, (size, size, 3)).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return img


def draw_scratch(img: np.ndarray, rng: random.Random):
    x = rng.randint(70, img.shape[1] - 70)
    y = rng.randint(70, img.shape[0] - 70)
    length = rng.randint(90, 200)
    angle = rng.uniform(0, 2 * math.pi)
    pts = []
    cx, cy = x, y
    n = rng.randint(8, 16)
    for _ in range(n):
        pts.append((cx, cy))
        ang = angle + rng.uniform(-0.45, 0.45)
        step = length / n
        cx += int(round(math.cos(ang) * step))
        cy += int(round(math.sin(ang) * step))
    pts = np.array(pts, np.int32)
    color = rng.randint(35, 85)
    cv2.polylines(img, [pts], False, (color, color, color), rng.randint(1, 2))
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


def draw_dent(img: np.ndarray, rng: random.Random):
    cx, cy = rng.randint(90, img.shape[1] - 90), rng.randint(90, img.shape[0] - 90)
    r = rng.randint(28, 58)
    Y, X = np.ogrid[: img.shape[0], : img.shape[1]]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    falloff = np.clip(1 - dist / r, 0, 1) ** 1.5
    dark = (rng.randint(35, 75) * falloff).astype(np.int16)
    for c in range(3):
        ch = img[:, :, c].astype(np.int16) - dark
        img[:, :, c] = np.clip(ch, 0, 255).astype(np.uint8)
    return (cx - r, cy - r, cx + r, cy + r)


def draw_missing(img: np.ndarray, rng: random.Random):
    cx, cy = rng.randint(85, img.shape[1] - 85), rng.randint(85, img.shape[0] - 85)
    r = rng.randint(22, 48)
    pts = []
    n = rng.randint(7, 12)
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * rng.uniform(0.6, 1.2)
        pts.append((int(cx + rr * math.cos(a)), int(cy + rr * math.sin(a))))
    pts = np.array(pts, np.int32)
    cv2.fillPoly(img, [pts], (12, 12, 12))
    # 边缘加一点阴影
    cv2.polylines(img, [pts], True, (60, 60, 60), 1)
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


def draw_crack(img: np.ndarray, rng: random.Random):
    x = rng.randint(70, img.shape[1] - 70)
    y = rng.randint(70, img.shape[0] - 70)
    pts = [(x, y)]
    ang = rng.uniform(0, 2 * math.pi)
    for _ in range(rng.randint(12, 22)):
        ang += rng.uniform(-0.7, 0.7)
        step = rng.randint(4, 13)
        x += int(round(math.cos(ang) * step))
        y += int(round(math.sin(ang) * step))
        pts.append((x, y))
    pts = np.array(pts, np.int32)
    cv2.polylines(img, [pts], False, (8, 8, 8), 1)
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


DRAWERS = [draw_scratch, draw_dent, draw_missing, draw_crack]


def clip_box(box, size):
    x1, y1, x2, y2 = box
    x1 = max(0, min(x1, size - 1))
    y1 = max(0, min(y1, size - 1))
    x2 = max(0, min(x2, size - 1))
    y2 = max(0, min(y2, size - 1))
    return x1, y1, x2, y2


def make_image(size, rng, allow_clean=True):
    img = make_background(size, rng)
    boxes = []
    if allow_clean and rng.random() < 0.12:
        return img, boxes  # 无缺陷样本
    n_def = rng.randint(1, 3)
    used_classes = set()
    for _ in range(n_def):
        cid = rng.randrange(len(CLASSES))
        # 避免同图重复同类
        if cid in used_classes:
            cid = (cid + 1) % len(CLASSES)
        used_classes.add(cid)
        box = clip_box(DRAWERS[cid](img, rng), size)
        # 过滤过小框
        if (box[2] - box[0]) < 6 or (box[3] - box[1]) < 6:
            continue
        boxes.append((cid, *box))
    return img, boxes


def to_yolo(box, size):
    cid, x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2) / size
    cy = ((y1 + y2) / 2) / size
    w = (x2 - x1) / size
    h = (y2 - y1) / size
    return f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num", type=int, default=200, help="总图片数")
    ap.add_argument("--size", type=int, default=640, help="图片边长(px)")
    ap.add_argument("--split", type=float, default=0.8, help="train 比例")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=None, help="输出根目录(默认脚本同级)")
    args = ap.parse_args()

    out = Path(args.out) if args.out else Path(__file__).resolve().parent
    ds_dir = out / "datasets" / "defect_synthetic"
    for sp in ("train", "val"):
        (ds_dir / "images" / sp).mkdir(parents=True, exist_ok=True)
        (ds_dir / "labels" / sp).mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    names = [f"img_{i:05d}" for i in range(args.num)]
    rng.shuffle(names)
    n_train = int(round(args.num * args.split))

    for i, name in enumerate(names):
        sp = "train" if i < n_train else "val"
        img, boxes = make_image(args.size, rng)
        save_img(str(ds_dir / "images" / sp / f"{name}.png"), img)
        if boxes:
            with open(ds_dir / "labels" / sp / f"{name}.txt", "w", encoding="utf-8") as f:
                for b in boxes:
                    f.write(to_yolo(b, args.size) + "\n")

    # data.yaml
    yaml_path = out / "data.yaml"
    nc = len(CLASSES)
    yaml_text = (
        f"# 自动生成 - 工业表面缺陷合成数据集\n"
        f"path: {ds_dir.as_posix()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {nc}\n"
        f"names: {CLASSES}\n"
    )
    yaml_path.write_text(yaml_text, encoding="utf-8")

    print(f"[dataset_gen] 完成: {args.num} 张 -> {ds_dir}")
    print(f"  train={n_train} val={args.num - n_train} 类别={CLASSES}")
    print(f"  data.yaml -> {yaml_path}")


if __name__ == "__main__":
    main()
