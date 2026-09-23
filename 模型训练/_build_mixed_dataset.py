# -*- coding: utf-8 -*-
"""
构造「NEU 缺陷 + DAGM 无缺陷」混合训练集（负样本重训实验）

策略：用干净的原生 NEU（neu_det，1440 张缺陷图）作为正样本，
混入 DAGM 无缺陷图作为负样本（空标签），验证负样本能否压误检且不伤召回。

比例：负样本 : 正样本 = 1:1（取 1440 张 DAGM 无缺陷图，与 1440 张 NEU 缺陷图等量）。
  - 过多负样本会让模型把什么都判背景、伤缺陷召回；
  - 1:1 是温和起点，能干净验证"负样本是否有效"这个因果。

产出目录：datasets/neu_det_dagm/
    images/train/  (1440 NEU 缺陷 + 1440 DAGM 无缺陷)
    labels/train/  (NEU 有标签，DAGM 空标签)
    images/val/    (纯 NEU 360 张，口径不变)
    labels/val/

用 symlink（Windows 下用 os.symlink，需管理员或开发模式；失败则回退 copy2）。

用法：
    venv_cuda/Scripts/python.exe _build_mixed_dataset.py
"""
import os, shutil, random
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
NEU_DET = SCRIPT_DIR / "datasets" / "neu_det"
DAGM = SCRIPT_DIR / "datasets" / "dagm_neg"
OUT = SCRIPT_DIR / "datasets" / "neu_det_dagm_half"

NEG_RATIO = 0.5          # 负样本 : 正样本 = 1:2（方案A：减轻负样本压制力）
SEED = 42


def link_or_copy(src: Path, dst: Path):
    """优先 symlink（省磁盘），失败回退复制。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    random.seed(SEED)
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)

    # 1) 正样本：NEU 全部缺陷图（train 1440）
    neu_train_imgs = sorted((NEU_DET / "images" / "train").glob("*.jpg"))
    print(f"NEU 缺陷正样本(train): {len(neu_train_imgs)} 张")

    # 2) 负样本：DAGM 无缺陷图，取与正样本等量
    dagm_imgs = sorted((DAGM / "images" / "train").glob("*.png"))
    n_neg = int(len(neu_train_imgs) * NEG_RATIO)
    neg_imgs = random.sample(dagm_imgs, n_neg)
    print(f"DAGM 无缺陷负样本: 取 {n_neg} / {len(dagm_imgs)} 张")

    # 3) 拼接 train
    for img in neu_train_imgs:
        link_or_copy(img, OUT / "images" / "train" / img.name)
        lbl = NEU_DET / "labels" / "train" / (img.stem + ".txt")
        link_or_copy(lbl, OUT / "labels" / "train" / (img.stem + ".txt"))
    for img in neg_imgs:
        link_or_copy(img, OUT / "images" / "train" / img.name)
        # DAGM 空标签直接写空文件
        (OUT / "labels" / "train" / (img.stem + ".txt")).write_text("", encoding="utf-8")

    # 4) val：纯 NEU（口径不变）
    for img in sorted((NEU_DET / "images" / "val").glob("*.jpg")):
        link_or_copy(img, OUT / "images" / "val" / img.name)
        lbl = NEU_DET / "labels" / "val" / (img.stem + ".txt")
        link_or_copy(lbl, OUT / "labels" / "val" / (img.stem + ".txt"))

    # 5) 汇总
    for sp in ("train", "val"):
        im = len(list((OUT / "images" / sp).glob("*.*")))
        lb = len(list((OUT / "labels" / sp).glob("*.txt")))
        print(f"[{sp}] 图片 {im} / 标签 {lb}")
    print(f"输出目录: {OUT}")


if __name__ == "__main__":
    main()
