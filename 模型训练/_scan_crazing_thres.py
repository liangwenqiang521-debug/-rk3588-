"""
crazing 单类阈值扫描（cal 集）
==============================

对 crazing 类的 conf 阈值做 0.05~0.30 扫描（其它类保持 0.20），
找「召回最大化、整体 mAP 不掉」的最优阈值。

输出：阈值 × (crazing 召回, crazing precision, 整体 mAP) 三维表。
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from _eval_unified import (load_labels, match_predictions, iou_xyxy,
                            CLASSES, run_inference)
import cv2

CAL_IMG = SCRIPT_DIR / "datasets" / "neu_det_cal" / "images" / "cal"
CAL_LBL = SCRIPT_DIR / "datasets" / "neu_det_cal" / "labels" / "cal"
MODEL = SCRIPT_DIR / "runs" / "neu_yolo11n_640" / "weights" / "best.pt"
IMG_SZ = 640
OTHER_THRES = 0.20
CRAZING_IDX = CLASSES.index("crazing")


def main():
    model = YOLO(str(MODEL))
    imgs = sorted(p for p in CAL_IMG.iterdir()
                  if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})

    # 一次性把所有图跑完缓存 (xyxy, cls, score, gt_box, gt_cls)
    print(f"加载 {len(imgs)} 张 cal 图 + 跑一次推理...")
    cache = []
    for ip in imgs:
        img = cv2.imdecode(np.fromfile(str(ip), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        h, w = img.shape[:2]
        gt_b, gt_c = load_labels(CAL_LBL, ip.stem, w, h)
        pb, pc, pconf = run_inference(model, ip, IMG_SZ, OTHER_THRES, {})
        cache.append((ip.name, gt_b, gt_c, pb, pc, pconf))
    print(f"已缓存 {len(cache)} 张图的预测。\n")

    # 扫描 crazing 阈值
    print(f"{'crazing_thres':>14s}  {'R_cz':>6s}  {'P_cz':>6s}  {'R_total':>8s}  {'P_total':>8s}  {'F1_total':>8s}")
    print("-" * 70)
    results = []
    for cz_thres in [0.30, 0.25, 0.20, 0.18, 0.15, 0.12, 0.10, 0.08, 0.05]:
        n_tp = n_fp = n_fn = 0
        cz_tp = cz_fp = cz_fn = 0
        for name, gt_b, gt_c, pb, pc, pconf in cache:
            # 只过滤 crazing 类的预测
            keep = np.ones(len(pc), dtype=bool)
            for i, c in enumerate(pc):
                if c == CRAZING_IDX and pconf[i] < cz_thres:
                    keep[i] = False
            pb_f = pb[keep]
            pc_f = pc[keep]
            tp, fp, fn, _ = match_predictions(gt_b, gt_c, pb_f, pc_f, 0.5)
            n_tp += tp
            n_fp += fp
            n_fn += fn
            # 单独统计 crazing 类（用 match_predictions 算 IoU 匹配）
            cz_gt_mask = (gt_c == CRAZING_IDX)
            cz_pr_mask = (pc_f == CRAZING_IDX)
            cz_gt_b = gt_b[cz_gt_mask]
            cz_pr_b = pb_f[cz_pr_mask]
            cz_tp_m, cz_fp_m, cz_fn_m, _ = match_predictions(
                cz_gt_b if len(cz_gt_b) else np.zeros((0, 4)),
                np.zeros(len(cz_gt_b), dtype=np.int32),
                cz_pr_b if len(cz_pr_b) else np.zeros((0, 4)),
                np.zeros(len(cz_pr_b), dtype=np.int32),
                0.5,
            )
            cz_tp += cz_tp_m
            cz_fp += cz_fp_m
            cz_fn += cz_fn_m
        # 整体 R/P
        r_tot = n_tp / max(n_tp + n_fn, 1)
        p_tot = n_tp / max(n_tp + n_fp, 1)
        f1_tot = 2 * r_tot * p_tot / max(r_tot + p_tot, 1e-9)
        results.append((cz_thres, r_tot, p_tot, f1_tot))
        print(f"{cz_thres:>14.2f}  {r_tot:>6.3f}  {p_tot:>6.3f}  {n_tp:>4d}/{n_tp+n_fn:<3d}  {n_tp:>4d}/{n_tp+n_fp:<3d}  {f1_tot:>8.3f}")

    # 单独算 crazing 类召回
    print(f"\n--- crazing 类单独召回（用 match_predictions）---")
    print(f"{'crazing_thres':>14s}  {'TP':>4s} {'FN':>4s} {'R':>6s} {'FP':>4s} {'P':>6s}")
    for cz_thres in [0.30, 0.25, 0.20, 0.18, 0.15, 0.12, 0.10, 0.08, 0.05]:
        cz_tp = cz_fp = cz_fn = 0
        for name, gt_b, gt_c, pb, pc, pconf in cache:
            keep = np.ones(len(pc), dtype=bool)
            for i, c in enumerate(pc):
                if c == CRAZING_IDX and pconf[i] < cz_thres:
                    keep[i] = False
            pb_f = pb[keep]
            pc_f = pc[keep]
            # crazing gt vs pred
            cz_gt_mask = (gt_c == CRAZING_IDX)
            cz_pr_mask = (pc_f == CRAZING_IDX)
            cz_gt_b = gt_b[cz_gt_mask]
            cz_pr_b = pb_f[cz_pr_mask]
            tp, fp, fn, _ = match_predictions(cz_gt_b, np.zeros(len(cz_gt_b), dtype=np.int32),
                                                cz_pr_b, np.zeros(len(cz_pr_b), dtype=np.int32),
                                                0.5)
            cz_tp += tp
            cz_fp += fp
            cz_fn += fn
        r = cz_tp / max(cz_tp + cz_fn, 1)
        p = cz_tp / max(cz_tp + cz_fp, 1)
        print(f"{cz_thres:>14.2f}  {cz_tp:>4d} {cz_fn:>4d} {r:>6.3f} {cz_fp:>4d} {p:>6.3f}")


if __name__ == "__main__":
    main()
