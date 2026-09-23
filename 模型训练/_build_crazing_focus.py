"""
crazing 专项数据集构造
======================

设计：
- 训练集 = NEU crazing 全量 239 张 + DAGM 无缺陷 239 张（1:1）
- 验证集 = cal 集（30 张 crazing + 148 张其它类）—— 隔离 holdout 不动
- 输出到 datasets/crazing_focus/

为什么这样设计：
- crazing 召回低（0.53~0.60）→ 需要让模型反复看 crazing 形态
- 但纯 crazing 训会让模型「过拟合 crazing、漏其它类」
- 加 DAGM 负样本约束：让模型也学「这不是 crazing」的形态
- 类内 1:1 平衡：crazing 239 张 vs DAGM 239 张，正负样本不偏

为什么只用 crazing 类（不全 NEU 6 类）：
- 专项微调的关键是「让模型对 crazing 的特征权重变高」
- 引入其它 5 类会稀释 crazing 的训练信号
- 其它 5 类召回由级联路径里的 _640 主力模型负责（不参与本次微调）

用法：
    python _build_crazing_focus.py
"""
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SRC_NEU = SCRIPT_DIR / "datasets" / "neu_det"
SRC_NEU_CAL = SCRIPT_DIR / "datasets" / "neu_det_cal"
SRC_DAGM = SCRIPT_DIR / "datasets" / "dagm_neg"
DST = SCRIPT_DIR / "datasets" / "crazing_focus"

NEG_RATIO = 1.0          # 负样本:正样本 = 1:1


def main():
    if DST.exists():
        print(f"删除旧目录: {DST}")
        shutil.rmtree(DST)
    for sub in ["images/train", "images/val", "labels/train", "labels/val"]:
        (DST / sub).mkdir(parents=True, exist_ok=True)

    # 1) NEU crazing 全量 → train
    src_img = SRC_NEU / "images" / "train"
    src_lbl = SRC_NEU / "labels" / "train"
    crazing_imgs = sorted(src_img.glob("crazing_*.jpg"))
    print(f"NEU crazing: {len(crazing_imgs)} 张")
    for img in crazing_imgs:
        stem = img.stem
        shutil.copy2(img, DST / "images" / "train" / img.name)
        lbl = src_lbl / f"{stem}.txt"
        if lbl.exists():
            shutil.copy2(lbl, DST / "labels" / "train" / f"{stem}.txt")
    n_crazing = len(crazing_imgs)

    # 2) DAGM 无缺陷 → train（按 1:1 数量取前 N 张）
    dagm_train = SRC_DAGM / "images" / "train"
    dagm_train_lbl = SRC_DAGM / "labels" / "train"
    dagm_imgs = sorted(dagm_train.glob("*.png"))[:int(n_crazing * NEG_RATIO)]
    print(f"DAGM 无缺陷: {len(dagm_imgs)} 张")
    for img in dagm_imgs:
        stem = img.stem
        shutil.copy2(img, DST / "images" / "train" / img.name)
        lbl = dagm_train_lbl / f"{stem}.txt"
        if lbl.exists():
            shutil.copy2(lbl, DST / "labels" / "train" / f"{stem}.txt")
        else:
            # DAGM 无缺陷图：理论上无标签，但保险起见写空
            (DST / "labels" / "train" / f"{stem}.txt").write_text("")

    # 3) 验证集 = cal 集（不重新切，cal 是调参用，holdout 留给最终汇报）
    val_img = SRC_NEU_CAL / "images" / "cal"
    val_lbl = SRC_NEU_CAL / "labels" / "cal"
    val_imgs = sorted(val_img.glob("*.jpg"))
    print(f"val 集: {len(val_imgs)} 张 (复用 cal)")
    for img in val_imgs:
        stem = img.stem
        shutil.copy2(img, DST / "images" / "val" / img.name)
        lbl = val_lbl / f"{stem}.txt"
        if lbl.exists():
            shutil.copy2(lbl, DST / "labels" / "val" / f"{stem}.txt")

    # 4) yaml 配置
    yaml_text = f"""# crazing 专项数据集（NEU crazing 239 + DAGM 无缺陷 239）
# 用于从 _640 热启动做 crazing 专项微调（lr=1e-5, 30 轮）
# val = cal 集（178 张 NEU，隔离 holdout 不动）
path: {DST.as_posix()}
train: images/train
val: images/val
nc: 6
names: ['crazing', 'inclusion', 'patches', 'pitted_surface', 'rolled-in_scale', 'scratches']
"""
    (SCRIPT_DIR / "data_crazing_focus.yaml").write_text(yaml_text, encoding="utf-8")
    print(f"\nyaml: data_crazing_focus.yaml")
    print(f"输出目录: {DST.as_posix()}")
    print(f"train: 239 crazing + 239 DAGM 负样本 = {n_crazing + len(dagm_imgs)} 张")
    print(f"val:   {len(val_imgs)} 张 (复用 cal)")


if __name__ == "__main__":
    main()
