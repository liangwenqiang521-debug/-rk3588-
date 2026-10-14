# -*- coding: utf-8 -*-
"""39 类钢板表面缺陷模型 · YOLOv11n @640 训练
=================================================

数据集：缺陷检测扩展/（production v2.1）
  train 20947 图（含 1800 张负样本，无标签）
  val    5296 图（含 200 张负样本）
  39 类，box 数 137 ~ 7824，最不平衡处差 124 倍

本机数据配置：data_steel39.yaml（由 _prepare_steel39.py 生成）
  ★ names 用 snake_case，与 infer.CLASSES_39 / 板端 NAMES_EXT 逐位一致；
    上位机取模型内嵌类名查 NAME_ZH / CLASS_COLORS，写显示名会查表落空。

与 NEU 6 类模型（train_neu640.py）的差异：
  · imgsz=640 不变（训练分辨率 == 部署分辨率，这条是硬约束）
  · hsv_h/hsv_s 仍为 0 —— 已实测本数据集 200/200 采样全为灰度图（通道差 0.00），
    无颜色信息可增强；hsv_v=0.2 保留亮度扰动
  · save_period=10，长训练定期存盘，防中途掉电全丢
  · 数据集规模约 6 倍，单轮更慢但总轮数可少

用法：
  venv_cuda\\Scripts\\python.exe train_steel39.py --smoke      # 2 轮冒烟，验证链路
  venv_cuda\\Scripts\\python.exe train_steel39.py              # 默认 100 轮
  venv_cuda\\Scripts\\python.exe train_steel39.py --resume     # 断点续训
"""
import argparse
import shutil
import sys
from pathlib import Path

import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
PRETRAIN = SCRIPT_DIR.parent / "yolo11n.pt"          # 官方 COCO 预训练
DATA = SCRIPT_DIR / "data_steel39.yaml"
RUN_NAME = "steel39_yolo11n_640"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true", help="强制 CPU")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--name", type=str, default=RUN_NAME)
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--close-mosaic", type=int, default=10,
                    help="最后 N 轮关闭 mosaic 以稳定收敛（默认 10）")
    ap.add_argument("--workers", type=int, default=4,
                    help="取数进程数。★ 本机仅 15.4GB 内存，验证时训练+验证 worker 同时存活，"
                         ">6 会因内存不足被系统杀掉（DataLoader worker exited unexpectedly）")
    ap.add_argument("--save-period", type=int, default=10,
                    help="每 N 轮存一次中间权重（长训练防掉电）")
    ap.add_argument("--smoke", action="store_true", help="冒烟测试：2 轮")
    ap.add_argument("--fraction", type=float, default=1.0,
                    help="仅用前 N%% 训练数据（快速计时/冒烟）")
    ap.add_argument("--resume", action="store_true",
                    help="从 runs/<name>/weights/last.pt 断点续训")
    args = ap.parse_args()

    if args.smoke:
        args.epochs = 2
        args.patience = 2
        args.save_period = 1
        if args.name == RUN_NAME:
            args.name = RUN_NAME + "_smoke"     # 与正式跑分开，避免互相覆盖
        print("[train_steel39] 冒烟模式：epochs=2 name=%s" % args.name)

    device = "cpu" if (args.cpu or not torch.cuda.is_available()) else "0"
    if device != "cpu":
        print("[train_steel39] GPU: %s (显存 %d MB)" % (
            torch.cuda.get_device_name(0),
            torch.cuda.get_device_properties(0).total_memory // 1024 ** 2))
    else:
        print("[train_steel39] 使用 CPU")

    if not PRETRAIN.exists():
        raise SystemExit("[train_steel39] 找不到预训练权重: %s" % PRETRAIN)
    if not DATA.exists():
        raise SystemExit(
            "[train_steel39] 找不到数据集配置: %s\n"
            "  先跑: python _prepare_steel39.py" % DATA)

    print("[train_steel39] 数据集配置: %s" % DATA)
    print("[train_steel39] imgsz=%d epochs=%d batch=%d -> runs/%s"
          % (args.imgsz, args.epochs, args.batch, args.name))
    sys.stdout.flush()

    if args.resume:
        last = SCRIPT_DIR / "runs" / args.name / "weights" / "last.pt"
        if not last.exists():
            raise SystemExit("[train_steel39] --resume 但找不到 last.pt: %s" % last)
        model = YOLO(str(last))
        print("[train_steel39] 断点续训: %s" % last)
    else:
        model = YOLO(str(PRETRAIN))
        print("[train_steel39] 预训练权重: %s" % PRETRAIN)

    results = model.train(
        data=str(DATA),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=device,
        name=args.name,
        project=str(SCRIPT_DIR / "runs"),
        resume=args.resume,
        # —— 调度 ——
        cos_lr=True,
        warmup_epochs=3,
        patience=args.patience,
        save_period=args.save_period,
        # —— 增强：本数据集已实测全为灰度，关闭色相/饱和度扰动 ——
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.2,
        fliplr=0.5,
        flipud=0.5,        # 钢板缺陷无固定上下方向，上下翻转可用（NEU 为 0.2）
        degrees=10.0,      # 实测分辨率/长宽比很杂，旋转增强略放大
        translate=0.1,
        scale=0.5,
        mosaic=1.0,
        mixup=0.05,
        close_mosaic=args.close_mosaic,   # 最后 N 轮关 mosaic 稳定收敛
        # —— 其他 ——
        workers=args.workers,
        fraction=args.fraction,
        seed=42,
        verbose=True,
        plots=True,
        exist_ok=True,
    )

    best_src = SCRIPT_DIR / "runs" / args.name / "weights" / "best.pt"
    if best_src.exists():
        dst = SCRIPT_DIR / ("best_%s.pt" % args.name)
        shutil.copy(str(best_src), str(dst))
        print("[train_steel39] best.pt -> %s" % dst)
    else:
        print("[train_steel39] 未找到 best.pt")

    print("[train_steel39] 训练完成。")
    print("[train_steel39] 下一步：python _eval_unified.py --model %s --data %s"
          % (SCRIPT_DIR / ("best_%s.pt" % args.name), DATA))


if __name__ == "__main__":
    main()
