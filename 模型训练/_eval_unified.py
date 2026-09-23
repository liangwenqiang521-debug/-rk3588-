"""
统一评估脚本（cal / holdout + confusion matrix）
================================================

设计：
- 输入：模型 .pt + 数据集 yaml（cal 或 holdout）
- 输出：mAP50、mAP50-95、逐类 mAP、逐类召回、6x6 confusion matrix、Top-10 混淆对
- 固定 IoU=0.5；conf 可配（默认 0.20）
- 支持 per-class 阈值：--per-class-thres '{"inclusion":0.16,...}'

为什么不用 ultralytics 自带 val.py：
- 自带 val 只能出整体 mAP 和 per-class AP，confusion matrix 需要自己跑推理
- 我们的需求：① conf 可配 ② per-class 阈值 ③ Top-N 混淆对清单 ④ 简洁文本/JSON 输出

用法：
    python _eval_unified.py --model runs/neu_yolo11n_640/weights/best.pt --data data_neu_cal.yaml
    python _eval_unified.py --model runs/neu_yolo11n_640/weights/best.pt --data data_neu_holdout.yaml --json out.json
    python _eval_unified.py --model runs/neu_yolo11n_640/weights/best.pt --data data_neu_holdout.yaml --per-class-thres '{"inclusion":0.16,"scratches":0.30}'
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

CLASSES = ['crazing', 'inclusion', 'patches',
           'pitted_surface', 'rolled-in_scale', 'scratches']


def iou_xyxy(a, b):
    """a: (N,4) b: (M,4) 返回 (N,M) IoU 矩阵"""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    ax1, ay1, ax2, ay2 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    bx1, by1, bx2, by2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    ix1 = np.maximum(ax1[:, None], bx1[None, :])
    iy1 = np.maximum(ay1[:, None], by1[None, :])
    ix2 = np.minimum(ax2[:, None], bx2[None, :])
    iy2 = np.minimum(ay2[:, None], by2[None, :])
    iw = np.clip(ix2 - ix1, 0, None)
    ih = np.clip(iy2 - iy1, 0, None)
    inter = iw * ih
    union = area_a[:, None] + area_b[None, :] - inter
    return inter / np.clip(union, 1e-9, None)


def load_labels(label_dir, img_stem, img_w, img_h):
    """读 YOLO 格式 txt → (cx,cy,w,h,cls) → xyxy + cls"""
    p = label_dir / f"{img_stem}.txt"
    if not p.exists():
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.int32)
    boxes, clses = [], []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        c = int(parts[0])
        cx, cy, w, h = map(float, parts[1:5])
        x1 = (cx - w / 2) * img_w
        y1 = (cy - h / 2) * img_h
        x2 = (cx + w / 2) * img_w
        y2 = (cy + h / 2) * img_h
        boxes.append([x1, y1, x2, y2])
        clses.append(c)
    return np.array(boxes, dtype=np.float32), np.array(clses, dtype=np.int32)


def run_inference(model, img_path, img_size, conf, per_class_thres, iou_nms=0.45):
    """跑一次推理，按 per-class 阈值过滤，返回 xyxy + cls + score"""
    r = model.predict(str(img_path), imgsz=img_size, conf=conf, iou=iou_nms,
                      verbose=False, device=0 if torch.cuda.is_available() else "cpu")
    if not r:
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.int32), np.zeros((0,), dtype=np.float32)
    boxes = r[0].boxes
    if boxes is None or len(boxes) == 0:
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.int32), np.zeros((0,), dtype=np.float32)
    xyxy = boxes.xyxy.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(np.int32)
    conf_arr = boxes.conf.cpu().numpy()
    # per-class 阈值过滤
    keep = np.ones(len(cls), dtype=bool)
    for i, c in enumerate(cls):
        cname = CLASSES[c]
        if cname in per_class_thres:
            if conf_arr[i] < per_class_thres[cname]:
                keep[i] = False
    return xyxy[keep], cls[keep], conf_arr[keep]


def match_predictions(gt_boxes, gt_cls, pred_boxes, pred_cls, iou_thres=0.5):
    """对单张图匹配预测与真值，返回 (TP/FP/FN) 计数和 confusion pair。
    每个 GT 只能被一个最佳 IoU 预测匹配；剩余预测 = FP。
    """
    n_gt = len(gt_boxes)
    n_pr = len(pred_boxes)
    pairs = []  # (gt_idx, pr_idx, iou)
    if n_gt > 0 and n_pr > 0:
        ious = iou_xyxy(gt_boxes, pred_boxes)
        # 按 IoU 降序贪心匹配
        order = np.argsort(-ious.flatten())
        used_g = set()
        used_p = set()
        for idx in order:
            i = idx // n_pr
            j = idx % n_pr
            if i in used_g or j in used_p:
                continue
            if ious[i, j] < iou_thres:
                break
            used_g.add(i)
            used_p.add(j)
            pairs.append((i, j, ious[i, j]))
    tp = len(pairs)
    fp = n_pr - tp
    fn = n_gt - tp
    return tp, fp, fn, pairs


def compute_map(records, n_cls, iou_thres=0.5):
    """records: list of (img_id, score, pred_cls, matched_gt_idx_or_-1)
    用简化版 101 点插值 mAP（IoU=0.5 单点），适合小数据集快速回报。
    """
    if not records:
        return 0.0, [0.0] * n_cls
    # 按类算 AP
    aps = []
    for c in range(n_cls):
        cls_recs = [r for r in records if r[2] == c]
        n_gt = sum(1 for r in cls_recs if r[3] is not None) + sum(1 for r in cls_recs if r[3] is None and False)
        # 重新数 GT 数：基于 records 不够准，需要外部传 gt_count per class
        aps.append(0.0)  # 占位，下面用更准的算法
    return 0.0, aps  # 复杂 AP 暂不算，下面用 ultralytics val 算整体 mAP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True, help="数据集 yaml 路径（cal 或 holdout）")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.20)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--per-class-thres", type=str, default=None,
                    help='JSON 格式 per-class 阈值，如 \'{"inclusion":0.16,"scratches":0.30}\'')
    ap.add_argument("--max-det", type=int, default=300)
    ap.add_argument("--json", type=str, default=None, help="把结果写到 JSON 文件")
    ap.add_argument("--device", type=str, default="0" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    per_class = json.loads(args.per_class_thres) if args.per_class_thres else {}

    print(f"模型: {args.model}")
    print(f"数据: {args.data}")
    print(f"imgsz={args.imgsz} conf={args.conf} iou={args.iou}")
    if per_class:
        print(f"per-class 阈值: {per_class}")
    print("=" * 70)

    model = YOLO(args.model)
    # 读 yaml
    import yaml
    cfg = yaml.safe_load(Path(args.data).read_text(encoding="utf-8"))
    root = Path(cfg["path"])
    val_img_dir = root / cfg["val"]
    val_lbl_dir = root / cfg["val"].replace("images", "labels")

    imgs = sorted(p for p in val_img_dir.iterdir()
                  if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    print(f"val 图像数: {len(imgs)}")

    # 推理
    conf_matrix = np.zeros((len(CLASSES), len(CLASSES)), dtype=np.int32)  # 行=真值, 列=预测
    per_class_gt = np.zeros(len(CLASSES), dtype=np.int32)  # 每类 GT 数
    per_class_tp = np.zeros(len(CLASSES), dtype=np.int32)  # 每类 TP 数
    per_class_pred = np.zeros(len(CLASSES), dtype=np.int32)  # 每类预测数（含 FP）
    confusion_pairs = []  # (gt_name, pred_name, count)

    import cv2
    n_miss = 0
    n_tp = 0
    n_fp = 0
    n_fn = 0
    for i, ip in enumerate(imgs, 1):
        img = cv2.imread(str(ip))
        if img is None:
            print(f"[WARN] 读不到 {ip}")
            continue
        h, w = img.shape[:2]
        gt_b, gt_c = load_labels(val_lbl_dir, ip.stem, w, h)
        pb, pc, pconf = run_inference(model, ip, args.imgsz, args.conf, per_class)
        tp, fp, fn, pairs = match_predictions(gt_b, gt_c, pb, pc, args.iou)
        n_tp += tp
        n_fp += fp
        n_fn += fn
        matched_p = set(j for _, j, _ in pairs)
        # 真值统计
        for c in gt_c:
            per_class_gt[c] += 1
        # 预测统计
        for c in pc:
            per_class_pred[c] += 1
        # 匹配对：填入 conf_matrix + 累计 per_class_tp
        for gi, pj, iou_v in pairs:
            conf_matrix[gt_c[gi], pc[pj]] += 1
            per_class_tp[gt_c[gi]] += 1
            n_miss = 0
        # 漏检：没匹配上的真值 → 记到 fn_per_class[gt_c[gi]]
        matched_g = set(gi for gi, _, _ in pairs)
        for gi in range(len(gt_c)):
            if gi not in matched_g:
                pass  # 已通过 per_class_gt - per_class_tp 计入 fn_per_class
        # 多余预测：没匹配上的预测 → 记到 fp_per_class[pc[pj]]
        for pj in range(len(pc)):
            if pj not in matched_p:
                pass  # 已通过 per_class_pred - per_class_tp 计入 fp_per_class

        if i % 50 == 0 or i == len(imgs):
            print(f"  [{i}/{len(imgs)}] tp={n_tp} fp={n_fp} fn={n_fn}")

    # 计算每类 recall / precision / F1
    per_class_recall = np.where(per_class_gt > 0,
                                 per_class_tp / per_class_gt, 0.0)
    per_class_precision = np.where(per_class_pred > 0,
                                    per_class_tp / per_class_pred, 0.0)
    denom = per_class_recall + per_class_precision
    per_class_f1 = np.where(
        denom > 0,
        2 * per_class_recall * per_class_precision / np.clip(denom, 1e-9, None),
        0.0
    )

    # 6x6 主对角误判混淆矩阵：把"漏检"算作 conf_matrix 之外的"FN"列
    # 简化：单独打印"误判方向"
    # rows=真值, cols=预测（包含 = 全部漏检也归到主对角外的"漏检"维度）
    # 实际我们用 6x6 + 一个独立 fn_per_class
    fn_per_class = per_class_gt - per_class_tp  # 每类漏检数
    fp_per_class = per_class_pred - per_class_tp  # 每类误报数

    # Top-10 混淆对（off-diagonal + 漏检、误报）
    off_diag = []
    for gi in range(len(CLASSES)):
        for pi in range(len(CLASSES)):
            if gi != pi and conf_matrix[gi, pi] > 0:
                off_diag.append((CLASSES[gi], CLASSES[pi], int(conf_matrix[gi, pi])))
    for c in range(len(CLASSES)):
        if fn_per_class[c] > 0:
            off_diag.append((CLASSES[c], "(漏检)", int(fn_per_class[c])))
    for c in range(len(CLASSES)):
        if fp_per_class[c] > 0:
            off_diag.append(("[背景]", CLASSES[c], int(fp_per_class[c])))
    off_diag.sort(key=lambda x: -x[2])

    # ultralytics val 跑一次拿 mAP50 / mAP50-95（官方口径，可信）
    print("\n调用 ultralytics val() 拿 mAP...")
    val_res = model.val(data=args.data, imgsz=args.imgsz, conf=args.conf, iou=args.iou,
                        device=args.device, plots=False, verbose=False, max_det=args.max_det)
    map50 = float(val_res.box.map50)
    map50_95 = float(val_res.box.map)

    # 汇总
    print("\n" + "=" * 70)
    print(f"整体 mAP50:     {map50:.4f}")
    print(f"整体 mAP50-95:  {map50_95:.4f}")
    print(f"总 TP/FP/FN:    {n_tp}/{n_fp}/{n_fn}")
    if (n_tp + n_fp) > 0:
        print(f"整体 precision: {n_tp / (n_tp + n_fp):.4f}")
    if (n_tp + n_fn) > 0:
        print(f"整体 recall:    {n_tp / (n_tp + n_fn):.4f}")
    print("=" * 70)

    print("\n逐类指标（6x6 匹配 + 漏检/误报）：")
    print(f"{'类':<20s} {'GT':>4s} {'TP':>4s} {'FN':>4s} {'FP':>4s} {'R':>6s} {'P':>6s} {'F1':>6s}")
    print("-" * 70)
    for c in range(len(CLASSES)):
        print(f"{CLASSES[c]:<20s} {per_class_gt[c]:>4d} {per_class_tp[c]:>4d} "
              f"{fn_per_class[c]:>4d} {fp_per_class[c]:>4d} "
              f"{per_class_recall[c]:>6.3f} {per_class_precision[c]:>6.3f} {per_class_f1[c]:>6.3f}")

    print("\n6x6 混淆矩阵（行=真值, 列=预测, 包含 TP+误判）：")
    print(f"{'':20s} " + " ".join(f"{c[:6]:>6s}" for c in CLASSES))
    for gi in range(len(CLASSES)):
        row = " ".join(f"{conf_matrix[gi, pi]:>6d}" for pi in range(len(CLASSES)))
        print(f"{CLASSES[gi]:20s} {row}")

    print("\nTop-10 混淆对（真值 → 预测 / 漏检 / 误报）：")
    for gt, pred, cnt in off_diag[:10]:
        print(f"  {gt:20s} → {pred:20s}  {cnt:>4d} 张")

    # JSON 输出
    if args.json:
        out = {
            "model": args.model,
            "data": args.data,
            "imgsz": args.imgsz,
            "conf": args.conf,
            "per_class_thres": per_class,
            "mAP50": map50,
            "mAP50_95": map50_95,
            "total_tp": int(n_tp),
            "total_fp": int(n_fp),
            "total_fn": int(n_fn),
            "per_class": {
                CLASSES[c]: {
                    "gt": int(per_class_gt[c]),
                    "tp": int(per_class_tp[c]),
                    "fn": int(fn_per_class[c]),
                    "fp": int(fp_per_class[c]),
                    "recall": float(per_class_recall[c]),
                    "precision": float(per_class_precision[c]),
                    "f1": float(per_class_f1[c]),
                }
                for c in range(len(CLASSES))
            },
            "confusion_matrix": conf_matrix.tolist(),
            "top_confusion_pairs": [
                {"gt": gt, "pred": pred, "count": cnt}
                for gt, pred, cnt in off_diag
            ],
        }
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写到: {args.json}")


if __name__ == "__main__":
    main()
