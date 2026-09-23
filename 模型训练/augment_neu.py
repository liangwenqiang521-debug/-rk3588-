"""NEU-DET 离线数据增强脚本（路线圖 P1 补充：不引入外部数据集，扩充现有真实数据）。

做法：对 train 集做几何 + 光度增强，标注框零误差同步变换：
  - 水平翻转 (x_center -> 1 - x_center)
  - 垂直翻转 (y_center -> 1 - y_center)
  - 光度增强 (随机亮度/对比度/高斯噪声，不改变坐标)
val 集原样保留（避免数据泄露）。

用法：
  python augment_neu.py                 # 默认 3 种增强（H/V/photometric），train 扩到 4x
  python augment_neu.py --per 3        # 每个样本生成的增强数（不含原图）

输出：
  datasets/neu_aug/images/{train,val}/*.jpg
  datasets/neu_aug/labels/{train,val}/*.txt
  data_neu_aug.yaml  (nc=6，与 NEU 一致)
"""
import argparse
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

CLASSES = ["crazing", "inclusion", "patches", "pitted_surface",
           "rolled-in_scale", "scratches"]


def load_label(p: Path):
    boxes = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            c, x, y, w, h = line.split()
            boxes.append([int(c), float(x), float(y), float(w), float(h)])
    return boxes


def save_label(p: Path, boxes):
    with open(str(p), "w", encoding="utf-8") as f:
        for c, x, y, w, h in boxes:
            f.write(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")


def hflip(boxes):
    return [[c, 1 - x, y, w, h] for c, x, y, w, h in boxes]


def vflip(boxes):
    return [[c, x, 1 - y, w, h] for c, x, y, w, h in boxes]


def photometric(img: np.ndarray, rng: random.Random):
    """随机亮度/对比度/高斯噪声，不改变坐标。"""
    alpha = rng.uniform(0.7, 1.3)      # 对比度
    beta = rng.uniform(-25, 25)         # 亮度
    img = img.astype(np.float32) * alpha + beta
    if rng.random() < 0.5:
        sigma = rng.uniform(0, 8)
        noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
        img = img + noise
    return np.clip(img, 0, 255).astype(np.uint8)


def read_img(path: Path):
    """用 PIL 读取（对 NEU 的非常规 jpg 编码更鲁棒），返回 BGR numpy。"""
    from PIL import Image
    im = Image.open(str(path)).convert("RGB")
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def write_img(path: Path, img: np.ndarray):
    """BGR numpy -> jpg。

    ⚠️⚠️ cv2.imwrite 在 Windows 下有两重坑（2026-09-17 查明血案根因）：
      1. 写**含中文的绝对路径**时静默返回 False（OpenCV 走 ANSI 编码解析路径），
         不抛异常、不建文件；相对路径若全为 ASCII 则正常 → 极易误判为"写成功"。
      2. 失败时只返回 False，不会抛错。
    历史后果：本脚本 4320 张增强图全部写失败，neu_aug/train 只剩 1440 张原图 +
    4320 个孤儿标签 → 所谓「增强集」实际等同原始集，两轮训练白跑。
    故此处必须：① 用 imencode + ndarray.tofile（走 Python 文件层，Unicode 安全）
    兜底；② 显式校验文件确实落盘。
    """
    ok = cv2.imwrite(str(path), img)
    if not ok or not path.exists() or path.stat().st_size == 0:
        ext = path.suffix or ".jpg"
        enc_ok, buf = cv2.imencode(ext, img)
        if not enc_ok:
            raise RuntimeError(f"cv2.imencode 编码失败: {path}")
        buf.tofile(str(path))          # Unicode 安全写盘
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"写图失败（imwrite 与 tofile 均未落盘）: {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=str, default=str(Path(__file__).resolve().parent / "datasets" / "neu_det"))
    ap.add_argument("--out", type=str, default=str(Path(__file__).resolve().parent / "datasets" / "neu_aug"))
    ap.add_argument("--per", type=int, default=3, help="每个样本生成的增强数(不含原图)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    # 不使用 rmtree（会触发批量删除保护）。直接确保目录存在，
    # 所有输出文件名都是确定性的，重跑会原地覆盖，不会残留脏数据。
    for sp in ("train", "val"):
        (out / "images" / sp).mkdir(parents=True, exist_ok=True)
        (out / "labels" / sp).mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    yaml_path = Path(__file__).resolve().parent / "data_neu_aug.yaml"
    abs_out = out.resolve()
    abs_val = (out / "images" / "val").resolve()

    # val 原样复制
    n_val = 0
    for imgp in (src / "images" / "val").glob("*.jpg"):
        shutil.copyfile(str(imgp), str(out / "images" / "val" / imgp.name))
        lab = src / "labels" / "val" / (imgp.stem + ".txt")
        shutil.copyfile(str(lab), str(out / "labels" / "val" / (imgp.stem + ".txt")))
        n_val += 1

    # train：原图 + 增强
    train_imgs = sorted((src / "images" / "train").glob("*.jpg"))
    n_orig = 0
    n_aug = 0
    for imgp in train_imgs:
        labp = src / "labels" / "train" / (imgp.stem + ".txt")
        boxes = load_label(labp)
        # 复制原图
        shutil.copyfile(str(imgp), str(out / "images" / "train" / imgp.name))
        save_label(out / "labels" / "train" / (imgp.stem + ".txt"), boxes)
        n_orig += 1

        img = read_img(imgp)
        # 生成 per 个增强
        for k in range(args.per):
            mode = rng.choice(["h", "v", "p", "hv"])
            aimg = img.copy()
            aboxes = boxes
            if "h" in mode:
                aimg = cv2.flip(aimg, 1)
                aboxes = hflip(aboxes)
            if "v" in mode:
                aimg = cv2.flip(aimg, 0)
                aboxes = vflip(aboxes)
            if "p" in mode:
                aimg = photometric(aimg, rng)
            new_stem = f"{imgp.stem}_a{mode}{k}"
            write_img(out / "images" / "train" / (new_stem + ".jpg"), aimg)
            save_label(out / "labels" / "train" / (new_stem + ".txt"), aboxes)
            n_aug += 1

    with open(str(yaml_path), "w", encoding="utf-8") as f:
        f.write(f"# NEU-DET 增强版（离线增强 by augment_neu.py，nc 仍=6）\n")
        f.write(f"path: {abs_out}\n")
        f.write(f"train: images/train\n")
        f.write(f"val: images/val\n")
        f.write(f"nc: {len(CLASSES)}\n")
        f.write(f"names: {CLASSES}\n")

    print(f"[augment_neu] 完成")
    print(f"  train: 原始 {n_orig} + 增强 {n_aug} = {n_orig + n_aug}")
    print(f"  val:   {n_val} (原样)")
    print(f"  data_neu_aug.yaml -> {yaml_path}")


if __name__ == "__main__":
    main()
