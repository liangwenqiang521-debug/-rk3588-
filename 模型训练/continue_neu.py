# -*- coding: utf-8 -*-
"""NEU-DET 真实钢材缺陷模型 · 续训脚本（热启动 + 延长 + 增强）

目标：在已有 neu_yolo11n_aug/best.pt (mAP50=0.750) 基础上继续提升，冲 0.80+。
方式：加载 best.pt 作为初始权重（warm-start，保留已学特征），在 NEU 增强集上
      再用更长调度 + 更强增强训练，输出到 runs/neu_yolo11n_aug2。

用法：
  venv_cuda\Scripts\python.exe continue_neu.py            # GPU 自动
  venv_cuda\Scripts\python.exe continue_neu.py --cpu     # 强制 CPU
"""
import argparse
import shutil
from pathlib import Path

import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
# 热启动权重：选历史最优的 neu_yolo11n_640（mAP50=0.783, imgsz=640，板端部署版）
# 而非 neu_yolo11n_aug（0.750, imgsz=320 训的，与 640 推理存在分辨率失配）
CKPT = SCRIPT_DIR / "runs" / "neu_yolo11n_640" / "weights" / "best.pt"
DATA = SCRIPT_DIR / "data_neu_aug.yaml"
RUN_NAME = "neu_yolo11n_aug2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true", help="强制用 CPU")
    ap.add_argument("--epochs", type=int, default=150)
    # batch=64 会把 8GB 笔记本显存打满（7808/8151 MiB）→ GPU 100% 但仅 35W，
    # 实测 165 s/it（一个 epoch 50 分钟）。与 neu_yolo11n_640（200 轮跑通）保持一致用 16。
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    device = "cpu" if (args.cpu or not torch.cuda.is_available()) else "0"
    if device != "cpu":
        print(f"[continue_neu] 使用 GPU: {torch.cuda.get_device_name(0)} "
              f"(显存 {torch.cuda.get_device_properties(0).total_memory // 1024**2} MB)")
    else:
        print("[continue_neu] 使用 CPU")

    if not CKPT.exists():
        raise SystemExit(f"[continue_neu] 找不到热启动权重: {CKPT}")

    print(f"[continue_neu] 热启动权重: {CKPT}")
    print(f"[continue_neu] 数据集:     {DATA}")
    model = YOLO(str(CKPT))

    results = model.train(
        data=str(DATA),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=device,
        name=RUN_NAME,
        project=str(SCRIPT_DIR / "runs"),
        # —— 训练策略：长调度 + 余弦退火 + 早停宽容 ——
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        warmup_epochs=3,
        warmup_momentum=0.8,
        cos_lr=True,
        momentum=0.937,
        weight_decay=0.0005,
        # —— 增强：针对小数据集防过拟合 ——
        mosaic=0.9,
        mixup=0.15,
        copy_paste=0.1,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        fliplr=0.5,
        flipud=0.2,
        degrees=5.0,
        translate=0.1,
        scale=0.5,
        shear=2.0,
        perspective=0.0005,
        close_mosaic=10,        # 最后 10 轮关闭 mosaic，常用涨点技巧
        label_smoothing=0.1,
        # —— 损失侧重 ——
        box=7.5,
        cls=0.5,
        dfl=1.5,
        # —— 其他 ——
        patience=40,            # 40 轮无提升才早停
        workers=4,
        seed=42,
        verbose=True,
    )

    # 复制 best.pt 到脚本同级（不覆盖原 neu 模型）
    # 注意：ultralytics 在同名目录已存在时会自动加后缀（aug2 -> aug2-2），
    # 必须用 trainer 的真实 save_dir，不能硬编码 RUN_NAME，否则会复制到旧的残留权重。
    try:
        run_dir = Path(model.trainer.save_dir)
    except Exception:
        run_dir = SCRIPT_DIR / "runs" / RUN_NAME
    print(f"[continue_neu] 训练输出目录: {run_dir}")

    best_src = run_dir / "weights" / "best.pt"
    if best_src.exists():
        dst = SCRIPT_DIR / f"best_{run_dir.name}.pt"
        shutil.copy(str(best_src), str(dst))
        print(f"[continue_neu] 已复制 best.pt -> {dst}")

        # 导出 ONNX（opset12，兼容 RKNN 转换）
        try:
            m = YOLO(str(best_src))
            out = m.export(format="onnx", imgsz=args.imgsz, dynamic=False, opset=12)
            print(f"[continue_neu] ONNX 导出成功 -> {out}")
        except Exception as e:
            print(f"[continue_neu] ONNX 导出失败(不影响 .pt): {e}")
    else:
        print(f"[continue_neu] 未找到 best.pt: {best_src}")

    print("[continue_neu] 续训完成。")


if __name__ == "__main__":
    main()
