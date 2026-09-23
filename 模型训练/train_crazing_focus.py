# -*- coding: utf-8 -*-
"""crazing 专项微调（NEU crazing 弱类攻坚）

目标：把 crazing 类召回从 holdout 上的 0.53~0.60 提升到 0.70+。
      同时不显著退化其它 5 类（≤3pt）。

设计：
  - 数据：crazing 239 + DAGM 负样本 239（构造脚本：_build_crazing_focus.py）
  - 热启动：_640/best.pt（纯 NEU 训练，crazing 召回基础 0.60）
  - 学习率：1e-5（极低，避免灾难性遗忘）
  - 轮数：30（短微调，不让模型偏到 crazing 单类）
  - 验证：cal 集（178 张 NEU 6 类，crazing 58 张）

为什么用 DAGM 负样本而不是其它 5 类 NEU：
  - DAGM 无标签 = 强制"这不是 crazing"
  - 其它 5 类 NEU 也会带 crazing 漏检的混淆
  - DAGM 已经在 negdagm 训练里验证过能抑制误检

用法：
  venv_cuda\\Scripts\\python.exe train_crazing_focus.py
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
CKPT = SCRIPT_DIR / "runs" / "neu_yolo11n_640" / "weights" / "best.pt"
DATA = SCRIPT_DIR / "data_crazing_focus.yaml"
RUN_NAME = "neu_yolo11n_crazing_focus"


def _precheck_dataset():
    """训练前置：调用 _dataset_check.py 体检，体检不通过则拒绝训练。"""
    cmd = [
        sys.executable, str(SCRIPT_DIR / "_dataset_check.py"),
        "--data", str(DATA),
        "--splits", "train,val",
        "--exit-on-error",
    ]
    r = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    if r.returncode != 0:
        raise SystemExit(
            f"\n[crazing] ❌ 数据体检未通过，已拒绝训练！\n"
            f"   请先解决 _dataset_check.py 报的硬错，\n"
            f"   再重新运行训练脚本。\n"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--epochs", type=int, default=30)    # 短微调
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--lr0", type=float, default=1e-5)   # 极低学习率
    args = ap.parse_args()

    device = "cpu" if (args.cpu or not torch.cuda.is_available()) else "0"
    if device != "cpu":
        print(f"[crazing] GPU: {torch.cuda.get_device_name(0)} "
              f"({torch.cuda.get_device_properties(0).total_memory // 1024**2} MB)")
    else:
        print("[crazing] CPU")

    if not CKPT.exists():
        raise SystemExit(f"[crazing] 找不到热启动权重: {CKPT}")

    _precheck_dataset()  # ← 训练前置体检

    print(f"[crazing] 热启动: {CKPT}")
    print(f"[crazing] 数据:   {DATA}")
    print(f"[crazing] epochs={args.epochs}  lr0={args.lr0}  batch={args.batch}  imgsz={args.imgsz}")
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
        lr0=args.lr0,
        lrf=0.01,
        warmup_epochs=1,
        cos_lr=True,
        momentum=0.937,
        weight_decay=0.0005,
        mosaic=0.5,         # 弱增强，保持 crazing 形态不被破坏
        mixup=0.0,
        copy_paste=0.0,
        hsv_h=0.01, hsv_s=0.3, hsv_v=0.2,  # 弱色彩抖动
        fliplr=0.5, flipud=0.2,
        degrees=3.0, translate=0.05, scale=0.3, shear=1.0, perspective=0.0003,
        close_mosaic=5,
        label_smoothing=0.05,
        box=7.5, cls=0.5, dfl=1.5,
        patience=20,        # 短微调下早点停
        workers=4,
        seed=42,
        verbose=True,
    )

    try:
        run_dir = Path(model.trainer.save_dir)
    except Exception:
        run_dir = SCRIPT_DIR / "runs" / RUN_NAME
    print(f"[crazing] 输出目录: {run_dir}")

    best_src = run_dir / "weights" / "best.pt"
    if best_src.exists():
        dst = SCRIPT_DIR / f"best_{run_dir.name}.pt"
        shutil.copy(str(best_src), str(dst))
        print(f"[crazing] 已复制 best.pt -> {dst}")
    else:
        print(f"[crazing] 未找到 best.pt: {best_src}")

    print("[crazing] crazing 专项微调完成。")


if __name__ == "__main__":
    main()
