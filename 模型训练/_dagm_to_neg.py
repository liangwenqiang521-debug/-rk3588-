# -*- coding: utf-8 -*-
"""
DAGM 2007（ModelScope 镜像）无缺陷图 -> YOLO 负样本集转换

ModelScope 结构（datasets/dagm_ms/raw/）：
    ClassX.zip     = 1000 张无缺陷图（解压后 ClassX/1.png ~ 1000.png）
    ClassX_def.zip = 有缺陷图（本脚本不用）

本脚本：解压前 6 类的 ClassX.zip，取全部 1000 张无缺陷图，
按 8:2 切分 train/val（与 NEU 一致的口径），生成 YOLO 空标签负样本。

产出目录：datasets/dagm_neg/
    images/train/ClassX_xxx.png  +  labels/train/ClassX_xxx.txt（空）
    images/val/  ...

用法：
    venv_cuda/Scripts/python.exe _dagm_to_neg.py
"""
import os, shutil, zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RAW = SCRIPT_DIR / "datasets" / "dagm_ms" / "raw"
OUT = SCRIPT_DIR / "datasets" / "dagm_neg"
CLASSES = [1, 2, 3, 4, 5, 6]
VAL_RATIO = 0.2  # 每类 1000 张，200 张进 val

def main():
    # 清空旧输出
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "images" / "train").mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (OUT / "images" / "val").mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / "val").mkdir(parents=True, exist_ok=True)

    total = 0
    for c in CLASSES:
        zp = RAW / f"Class{c}.zip"
        if not zp.exists():
            print(f"[跳过] 未找到 {zp}")
            continue
        with zipfile.ZipFile(zp) as z:
            # 只取 ClassX/*.png（无缺陷图）
            pngs = sorted([n for n in z.namelist()
                           if n.startswith(f"Class{c}/") and n.endswith(".png")])
            print(f"Class{c}: zip 内无缺陷图 {len(pngs)} 张")
            n_val = int(len(pngs) * VAL_RATIO)
            for i, n in enumerate(pngs):
                idx = n.split("/")[-1].split(".")[0]  # 纯数字名
                out_name = f"Class{c}_{idx}.png"
                split = "val" if i < n_val else "train"
                # 解压图片（用二进制读，避免 cv2 中文路径坑）
                data = z.read(n)
                (OUT / "images" / split / out_name).write_bytes(data)
                # 空标签
                (OUT / "labels" / split / (Path(out_name).stem + ".txt")).write_text("", encoding="utf-8")
                total += 1

    # 汇总
    for sp in ("train", "val"):
        im = len(list((OUT / "images" / sp).glob("*.png")))
        lb = len(list((OUT / "labels" / sp).glob("*.txt")))
        print(f"[{sp}] 图片 {im} / 标签 {lb}")
    print(f"\n总计无缺陷负样本: {total} 张")
    print(f"输出目录: {OUT}")


if __name__ == "__main__":
    main()
