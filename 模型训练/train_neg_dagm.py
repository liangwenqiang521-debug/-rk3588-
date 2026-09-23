# -*- coding: utf-8 -*-
"""NEU 缺陷 + DAGM 无缺陷 负样本重训实验

目标：验证混入 DAGM 无缺陷负样本后，能否把误检率压下去、同时不伤缺陷召回。

方式：从 neu_yolo11n_640/best.pt 热启动，在「NEU 缺陷 1440 + DAGM 无缺陷 1440」
      混合集上微调，输出 runs/neu_yolo11n_negdagm。

对照口径：
  - 验证集 = 纯 NEU 360 张（mAP 与基线 _640 的 0.783 直接可比）
  - 训完后用 _verify_dagm_fp.py 跑 DAGM val 1200 张看误检率是否下降

用法：
  venv_cuda\Scripts\python.exe train_neg_dagm.py
"""
import argparse
import shutil
from pathlib import Path

import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
CKPT = SCRIPT_DIR / "runs" / "neu_yolo11n_640" / "weights" / "best.pt"
DATA = SCRIPT_DIR / "data_neu_dagm.yaml"
RUN_NAME = "neu_yolo11n_negdagm"


def _precheck_dataset():
    """训练前置：调用 _dataset_check.py 体检，体检不通过则拒绝训练。
    这是为了永久防止 cv2.imwrite / cv2.imread 中文路径静默失败类数据事故。
    """
    import subprocess
    import sys
    cmd = [
        sys.executable, str(SCRIPT_DIR / "_dataset_check.py"),
        "--data", str(DATA),
        "--splits", "train,val",
        "--exit-on-error",
    ]
    r = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    if r.returncode != 0:
        raise SystemExit(
            f"\n[neg_dagm] ❌ 数据体检未通过，已拒绝训练！\n"
            f"   请先解决 _dataset_check.py 报的硬错（多半是数据/路径问题），\n"
            f"   再重新运行训练脚本。\n"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--epochs", type=int, default=100)   # 微调，100 轮足够
    ap.add_argument("--batch", type=int, default=16)      # 与 _640 一致，防爆显存
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    device = "cpu" if (args.cpu or not torch.cuda.is_available()) else "0"
    if device != "cpu":
        print(f"[neg_dagm] GPU: {torch.cuda.get_device_name(0)} "
              f"({torch.cuda.get_device_properties(0).total_memory // 1024**2} MB)")
    else:
        print("[neg_dagm] CPU")

    if not CKPT.exists():
        raise SystemExit(f"[neg_dagm] 找不到热启动权重: {CKPT}")

    _precheck_dataset()  # ← 训练前置体检

    print(f"[neg_dagm] 热启动: {CKPT}")
    print(f"[neg_dagm] 数据:   {DATA}")
    model = YOLO(str(CKPT))

    model.train(
        data=str(DATA),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=device,
        name=RUN_NAME,
        project=str(SCRIPT_DIR / "runs"),
        optimizer="AdamW",
        lr0=0.0005,           # 微调用小学习率，避免灾难性遗忘
        lrf=0.01,
        warmup_epochs=3,
        cos_lr=True,
        momentum=0.937,
        weight_decay=0.0005,
        mosaic=0.9,
        mixup=0.15,
        copy_paste=0.1,
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
        fliplr=0.5, flipud=0.2,
        degrees=5.0, translate=0.1, scale=0.5, shear=2.0, perspective=0.0005,
        close_mosaic=10,
        label_smoothing=0.1,
        box=7.5, cls=0.5, dfl=1.5,
        patience=30,
        workers=4,
        seed=42,
        verbose=True,
    )

    try:
        run_dir = Path(model.trainer.save_dir)
    except Exception:
        run_dir = SCRIPT_DIR / "runs" / RUN_NAME
    print(f"[neg_dagm] 输出目录: {run_dir}")

    best_src = run_dir / "weights" / "best.pt"
    if best_src.exists():
        dst = SCRIPT_DIR / f"best_{run_dir.name}.pt"
        shutil.copy(str(best_src), str(dst))
        print(f"[neg_dagm] 已复制 best.pt -> {dst}")
    else:
        print(f"[neg_dagm] 未找到 best.pt: {best_src}")

    print("[neg_dagm] 负样本重训完成。")


if __name__ == "__main__":
    main()
