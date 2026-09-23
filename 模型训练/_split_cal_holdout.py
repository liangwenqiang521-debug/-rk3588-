"""
把 NEU val 切成 calibration / holdout 双集
==========================================

设计：
- 每类按文件名序号排序，前 50% 入 cal、后 50% 入 holdout
- 用复制（不是 symlink）保证 Windows 兼容、训练脚本读取无差异
- 输出目录：datasets/neu_det_cal/
    images/cal/   labels/cal/      (调参用)
    images/holdout/ labels/holdout/ (汇报用，绝不在调参过程中看)
- 同时生成 data_neu_cal.yaml / data_neu_holdout.yaml
- 切分映射落到 _split_manifest.json（可复现、可审计）

为什么切而不合并：
- 当前所有"提升"（aug / neg / 1:1 / 1:2）都在同一 val 上调+评
- 存在"评估集过拟合"风险，per-class 阈值、模型选型结论都受影响
- 切开后，cal 用来调（阈值/超参），holdout 只汇报（不参与任何选择）

用法：
    python _split_cal_holdout.py
"""
import json
import shutil
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SRC = SCRIPT_DIR / "datasets" / "neu_det"
DST = SCRIPT_DIR / "datasets" / "neu_det_cal"

CLASSES = ['crazing', 'inclusion', 'patches',
           'pitted_surface', 'rolled-in_scale', 'scratches']


def main():
    src_img = SRC / "images" / "val"
    src_lbl = SRC / "labels" / "val"

    assert src_img.is_dir(), f"NEU val 目录不存在: {src_img}"
    assert src_lbl.is_dir(), f"NEU val 标签目录不存在: {src_lbl}"

    # 1) 按类收集所有 val 文件
    by_class = {c: [] for c in CLASSES}
    for img in sorted(src_img.iterdir()):
        stem = img.stem
        for c in CLASSES:
            if stem.startswith(c + "_"):
                by_class[c].append(img.name)
                break
        else:
            print(f"[WARN] 文件名不属于已知 6 类，跳过: {img.name}")

    # 2) 输出目录
    for sub in ["images/cal", "images/holdout", "labels/cal", "labels/holdout"]:
        (DST / sub).mkdir(parents=True, exist_ok=True)

    # 3) 每类 50% 切，序号排序后切片
    manifest = {"cal": [], "holdout": []}
    summary = {}
    for c, files in by_class.items():
        files_sorted = sorted(files)  # crazing_2 < crazing_17 < ... < crazing_298
        n = len(files_sorted)
        half = n // 2
        cal_files = files_sorted[:half]
        holdout_files = files_sorted[half:]
        summary[c] = {"total": n, "cal": len(cal_files), "holdout": len(holdout_files)}

        for fname in cal_files:
            stem = Path(fname).stem
            shutil.copy2(src_img / fname, DST / "images" / "cal" / fname)
            lbl = src_lbl / f"{stem}.txt"
            if lbl.exists():
                shutil.copy2(lbl, DST / "labels" / "cal" / f"{stem}.txt")
            else:
                (DST / "labels" / "cal" / f"{stem}.txt").write_text("")
            manifest["cal"].append(fname)

        for fname in holdout_files:
            stem = Path(fname).stem
            shutil.copy2(src_img / fname, DST / "images" / "holdout" / fname)
            lbl = src_lbl / f"{stem}.txt"
            if lbl.exists():
                shutil.copy2(lbl, DST / "labels" / "holdout" / f"{stem}.txt")
            else:
                (DST / "labels" / "holdout" / f"{stem}.txt").write_text("")
            manifest["holdout"].append(fname)

    # 4) 写 manifest（可复现审计）
    (DST / "_split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 5) 写两个 yaml
    base = SCRIPT_DIR
    cal_yaml = f"""# NEU-DET calibration 子集（用于调阈值/调超参，不汇报）
path: {DST.as_posix()}
train: images/cal
val: images/cal
nc: 6
names: ['crazing', 'inclusion', 'patches', 'pitted_surface', 'rolled-in_scale', 'scratches']
"""
    holdout_yaml = f"""# NEU-DET holdout 子集（仅用于最终汇报，调参过程中不要看）
path: {DST.as_posix()}
train: images/holdout
val: images/holdout
nc: 6
names: ['crazing', 'inclusion', 'patches', 'pitted_surface', 'rolled-in_scale', 'scratches']
"""
    (base / "data_neu_cal.yaml").write_text(cal_yaml, encoding="utf-8")
    (base / "data_neu_holdout.yaml").write_text(holdout_yaml, encoding="utf-8")

    # 6) 汇总
    print("=" * 60)
    print("cal / holdout 切分完成")
    print("=" * 60)
    print(f"{'类':<20s} {'总':>4s} {'cal':>4s} {'holdout':>8s}")
    print("-" * 60)
    for c, s in summary.items():
        print(f"{c:<20s} {s['total']:>4d} {s['cal']:>4d} {s['holdout']:>8d}")
    total_n = sum(s["total"] for s in summary.values())
    total_c = sum(s["cal"] for s in summary.values())
    total_h = sum(s["holdout"] for s in summary.values())
    print("-" * 60)
    print(f"{'合计':<20s} {total_n:>4d} {total_c:>4d} {total_h:>8d}")
    print()
    print(f"输出目录: {DST.as_posix()}")
    print(f"切分映射: {DST / '_split_manifest.json'}")
    print(f"cal yaml:     {base / 'data_neu_cal.yaml'}")
    print(f"holdout yaml: {base / 'data_neu_holdout.yaml'}")
    print()
    print("使用约定：")
    print("  ① 调阈值/选模型 → 在 data_neu_cal.yaml 上做")
    print("  ② 最终汇报指标 → 用 data_neu_holdout.yaml")


if __name__ == "__main__":
    main()
