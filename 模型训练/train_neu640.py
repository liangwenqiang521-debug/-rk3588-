# -*- coding: utf-8 -*-
"""NEU-DET 真实钢材缺陷模型 · 在部署分辨率 640 下重新训练

背景（2026-09-15 诊断）：
  原 neu_yolo11n_aug(best.pt, mAP50=0.750) 是在 **imgsz=320** 下训练的，
  而 RK3588 板端与上位机均按 640 推理。实测同一权重：
      imgsz=320 -> mAP50 0.7496
      imgsz=640 -> mAP50 0.4243      <- 掉 32 个点
  之前那次续训(aug2)正是"320 权重 + 640 训练"，起点只有 0.424，故首轮崩到 0.115。

  本脚本改为：从官方 COCO 预训练权重 yolo11n.pt 出发，直接在 **640** 下
  fine-tune NEU-DET 增强集，使训练分辨率 == 部署分辨率。

用法：
  venv_cuda\Scripts\python.exe train_neu640.py                 # 默认 300 轮
  venv_cuda\Scripts\python.exe train_neu640.py --epochs 3      # 冒烟测试
  venv_cuda\Scripts\python.exe train_neu640.py --cpu           # 强制 CPU
"""
import argparse
import shutil
import sys
from pathlib import Path

import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
PRETRAIN = SCRIPT_DIR.parent / "yolo11n.pt"          # 官方 COCO 预训练
DATA = SCRIPT_DIR / "data_neu_aug.yaml"
RUN_NAME = "neu_yolo11n_640"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true", help="强制 CPU")
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--name", type=str, default=RUN_NAME)
    ap.add_argument("--patience", type=int, default=60)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--resume", action="store_true",
                    help="从 runs/<name>/weights/last.pt 断点续训")
    args = ap.parse_args()

    device = "cpu" if (args.cpu or not torch.cuda.is_available()) else "0"
    if device != "cpu":
        print("[train_neu640] GPU: %s (显存 %d MB)" % (
            torch.cuda.get_device_name(0),
            torch.cuda.get_device_properties(0).total_memory // 1024 ** 2))
    else:
        print("[train_neu640] 使用 CPU")

    if not PRETRAIN.exists():
        raise SystemExit("[train_neu640] 找不到预训练权重: %s" % PRETRAIN)
    if not DATA.exists():
        raise SystemExit("[train_neu640] 找不到数据集配置: %s" % DATA)

    print("[train_neu640] 数据集:     %s" % DATA)
    print("[train_neu640] imgsz=%d epochs=%d batch=%d -> runs/%s"
          % (args.imgsz, args.epochs, args.batch, args.name))
    sys.stdout.flush()

    if args.resume:
        last = SCRIPT_DIR / "runs" / args.name / "weights" / "last.pt"
        if not last.exists():
            raise SystemExit("[train_neu640] --resume 但找不到 last.pt: %s" % last)
        model = YOLO(str(last))
        print("[train_neu640] 断点续训: %s" % last)
    else:
        model = YOLO(str(PRETRAIN))
        print("[train_neu640] 预训练权重: %s" % PRETRAIN)

    results = model.train(
        data=str(DATA),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=device,
        name=args.name,
        project=str(SCRIPT_DIR / "runs"),
        resume=args.resume,
        # —— 调度：长训练 + 余弦退火 ——
        cos_lr=True,
        warmup_epochs=3,
        patience=args.patience,       # 长时间无提升才早停
        # —— 增强：NEU 为灰度钢材图，保留几何增强，弱化色相扰动 ——
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.2,
        fliplr=0.5,
        flipud=0.2,
        degrees=5.0,
        translate=0.1,
        scale=0.5,
        mosaic=1.0,
        mixup=0.05,
        close_mosaic=15,              # 最后 15 轮关 mosaic 稳定收敛
        # —— 其他 ——
        workers=args.workers,
        seed=42,
        verbose=True,
        exist_ok=True,
    )

    best_src = SCRIPT_DIR / "runs" / args.name / "weights" / "best.pt"
    if best_src.exists():
        dst = SCRIPT_DIR / ("best_%s.pt" % args.name)
        shutil.copy(str(best_src), str(dst))
        print("[train_neu640] best.pt -> %s" % dst)

        try:
            m = YOLO(str(best_src))
            # simplify=False：环境未装 onnxslim（镜像 403），且 RKNN 转换不需要 slim
            out = m.export(format="onnx", imgsz=args.imgsz, dynamic=False,
                           opset=12, simplify=False)
            print("[train_neu640] ONNX 导出 -> %s" % out)
        except Exception as e:
            print("[train_neu640] ONNX 导出失败(不影响 .pt): %s" % e)
    else:
        print("[train_neu640] 未找到 best.pt")

    print("[train_neu640] 训练完成。")


if __name__ == "__main__":
    main()
