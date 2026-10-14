# -*- coding: utf-8 -*-
"""batch / workers 吞吐对照实验
================================

背景：39 类数据集首轮冒烟实测 batch=16 → 0.38 s/it（约 42 img/s），
      但取数基准显示单进程解码+缩放就有 546 img/s，磁盘 102 MB/s，
      且显存只占 2.4G/8G —— 说明瓶颈是**小批量下的每步开销**，不是取数。

做法：固定 fraction，跑 1 轮，只比较 it/s 与显存占用。
      跑完即删（各 config 用独立 name，最后清理）。

用法：
  venv_cuda\\Scripts\\python.exe _bench_batch.py
  venv_cuda\\Scripts\\python.exe _bench_batch.py --configs 16,32,48 --workers 4
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
PRETRAIN = SCRIPT_DIR.parent / "yolo11n.pt"
DATA = SCRIPT_DIR / "data_steel39.yaml"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", type=str, default="16,32,48",
                    help="要对比的 batch 列表，逗号分隔")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--fraction", type=float, default=0.05,
                    help="只用前 N%% 数据（快跑对照用）")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    batches = [int(x) for x in args.configs.split(",") if x.strip()]
    print("=" * 70)
    print("吞吐对照: batches=%s workers=%d fraction=%.3f imgsz=%d"
          % (batches, args.workers, args.fraction, args.imgsz))
    print("GPU: %s" % torch.cuda.get_device_name(0))
    print("=" * 70)
    sys.stdout.flush()

    results = []
    for b in batches:
        name = "_bench_b%d" % b
        print("\n--- batch=%d ---" % b)
        sys.stdout.flush()
        try:
            model = YOLO(str(PRETRAIN))
            model.train(
                data=str(DATA), epochs=1, batch=b, imgsz=args.imgsz,
                device="0", name=name, project=str(SCRIPT_DIR / "runs"),
                fraction=args.fraction, workers=args.workers,
                cos_lr=True, warmup_epochs=0, patience=1, save_period=1,
                hsv_h=0.0, hsv_s=0.0, hsv_v=0.2,
                fliplr=0.5, flipud=0.5, degrees=10.0, translate=0.1,
                scale=0.5, mosaic=1.0, mixup=0.05, close_mosaic=0,
                seed=42, verbose=False, plots=False, exist_ok=True,
            )
            csv_p = SCRIPT_DIR / "runs" / name / "results.csv"
            if csv_p.exists():
                head = csv_p.read_text(encoding="utf-8").splitlines()[0]
                row = csv_p.read_text(encoding="utf-8").splitlines()[-1]
                keys = [k.strip() for k in head.split(",")]
                vals = row.split(",")
                d = dict(zip(keys, vals))
                t = float(d.get("train/box_loss", 0))  # 占位，真实时间看 log
                results.append((b, d.get("time", "?"), d.get("metrics/mAP50(B)", "?"),
                                d.get("epoch", "?")))
                print("  batch=%d 完成  mAP50=%s" %
                      (b, d.get("metrics/mAP50(B)", "?")))
        except Exception as e:
            print("  batch=%d 失败: %r" % (b, e))
        sys.stdout.flush()

    print()
    print("=" * 70)
    print("对照结果（时间取自 results.csv 的 time 列 = 该轮累计秒数）")
    print("=" * 70)
    for b, t, m, ep in results:
        try:
            sec = float(t)
            print("  batch=%-3d  单轮 %6.1f s   ~%5.2f s/it   mAP50=%s" %
                  (b, sec, sec / max(1, int(20944 * args.fraction) // b), m))
        except Exception:
            print("  batch=%-3d  time=%s mAP50=%s" % (b, t, m))

    # 清理 bench 产物
    for b in batches:
        p = SCRIPT_DIR / "runs" / ("_bench_b%d" % b)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    print("\n已清理 bench 产物")


if __name__ == "__main__":
    main()
