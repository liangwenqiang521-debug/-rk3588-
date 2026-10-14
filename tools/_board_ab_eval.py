# -*- coding: utf-8 -*-
"""板端 39 类服务「生产链路」实测：走 cmd=detect_img，按 _calib_thres39.py 同口径算 FP/FN。

- 直接连板端 9000 端口，发送 holdout 随机子集的图片（base64）
- 板端用自己的 rknn + postprocess（含 PER_CLASS_THRES）返回 defects（原图坐标）
- 与本地 GT 标签按 NMS IoU 0.45 / 匹配 IoU 0.50 / TP 记真值类 的口径比对
- 板端已按阈值过滤，故返回即保留（等价 thres=0）；因此本脚本测的是「当前板端配置」的端到端表现。
  换板端配置：`python3 /root/_wb_set_board.py <old|new> <thres|nothres>` + `sh /root/rknn/start_cascade.sh`

结果增量写盘到 --out，便于中断后查看。
用法（需带 numpy/cv2 的解释器，如本仓 .venv）:
  python tools/_board_ab_eval.py --limit 300 --seed 20261013 --out board_eval.json
"""
import argparse
import base64
import json
import os
import socket
import sys
import time
from pathlib import Path

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import board_env

HOST_DEFAULT = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000
MATCH_IOU = 0.50
N_CLS = 39
MANIFEST = os.path.join(_ROOT, "模型训练", "splits", "val_holdout.txt")

NAMES = [
    "bright_scratch", "crazing", "crease", "crescent_gap", "dark_scratches",
    "finishing_roll_printing", "inclusion", "iron_scale_compression", "iron_sheet_ash",
    "oil_spot", "oxide_scale_plate", "oxide_scale_temp", "patches", "pitted_surface",
    "punching", "red_iron_sheet", "rolled-in_scale", "rolled_pit", "secondary_rust_skin",
    "silk_spot", "slag_inclusion", "waist_folding", "water_spot", "welding_line",
    "white_rust", "cutting_opening", "water_slag_mark", "slag_skin", "longitudinal_crack",
    "warp", "external_fold", "wrinkle", "blocky_scale", "striated_scale", "foreign_obj",
    "blowhole", "break", "fray", "uneven",
]
NAME2IDX = {n: i for i, n in enumerate(NAMES)}


def iou_xyxy(a, b):
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    ax1, ay1, ax2, ay2 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    bx1, by1, bx2, by2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    ix1 = np.maximum(ax1[:, None], bx1[None, :])
    iy1 = np.maximum(ay1[:, None], by1[None, :])
    ix2 = np.minimum(ax2[:, None], bx2[None, :])
    iy2 = np.minimum(ay2[:, None], by2[None, :])
    iw = np.clip(ix2 - ix1, 0, None)
    ih = np.clip(iy2 - iy1, 0, None)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1)
    ub = (bx2 - bx1) * (by2 - by1)
    return inter / np.clip(ua[:, None] + ub[None, :] - inter, 1e-9, None)


def label_path_for(img_path):
    parts = list(Path(img_path).parts)
    idx = [i for i, s in enumerate(parts) if s.lower() == "images"]
    if not idx:
        return None
    parts[idx[-1]] = "labels"
    return Path(*parts).with_suffix(".txt")


def load_gt(img_path, w, h):
    lp = label_path_for(img_path)
    if lp is None or not lp.exists():
        return np.zeros((0, 4), np.float32), np.zeros((0,), np.int32)
    boxes, clses = [], []
    for line in lp.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.split()
        if len(t) < 5:
            continue
        try:
            c = int(t[0]); cx, cy, bw, bh = map(float, t[1:5])
        except ValueError:
            continue
        boxes.append([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
        clses.append(c)
    return (np.asarray(boxes, np.float32) if boxes else np.zeros((0, 4), np.float32),
            np.asarray(clses, np.int32) if clses else np.zeros((0,), np.int32))


def recv_lines(sock, buf, deadline):
    out = []
    while time.time() < deadline:
        try:
            d = sock.recv(1 << 20)
        except socket.timeout:
            continue
        except OSError:
            break
        if not d:
            break
        buf += d
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                out.append(json.loads(line.decode("utf-8", "ignore")))
            except Exception:
                pass
    return out, buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST_DEFAULT)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--out", default="board_eval.json")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    paths = [l.strip() for l in Path(MANIFEST).read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = np.random.RandomState(args.seed)
    if args.limit and args.limit < len(paths):
        sel = rng.choice(len(paths), size=args.limit, replace=False)
        paths = [paths[i] for i in sorted(sel)]
    print("待测 %d 张（holdout 全量 %d，seed=%d）" % (len(paths), args.limit, args.seed), flush=True)

    s = socket.create_connection((args.host, PORT), timeout=10)
    s.settimeout(1.0)
    print("已连接 %s:%d" % (args.host, PORT), flush=True)

    recs = []
    errors = []
    buf = b""
    t0 = time.time()
    for i, p in enumerate(paths, 1):
        raw = np.fromfile(p, dtype=np.uint8)
        if raw.size == 0:
            errors.append((p, "read fail"))
            continue
        w = h = None
        import cv2
        img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if img is None:
            errors.append((p, "decode fail"))
            continue
        h, w = img.shape[:2]
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            errors.append((p, "encode fail"))
            continue
        b64 = base64.b64encode(enc.tobytes()).decode("ascii")
        token = "EV%05d_%s" % (i, os.path.basename(p))[:78]

        frame = None
        for attempt in range(2):
            s.sendall((json.dumps({"cmd": "detect_img", "name": token, "img": b64}) + "\n").encode())
            deadline = time.time() + args.timeout
            while time.time() < deadline:
                got, buf = recv_lines(s, buf, time.time() + 1.0)
                for f in got:
                    if f.get("src") == token and "defects" in f:
                        frame = f
                        break
                if frame:
                    break
            if frame:
                break
        if frame is None:
            errors.append((p, "no frame"))
            continue

        gt_b, gt_c = load_gt(p, w, h)
        b = np.zeros((0, 4), np.float32); c = np.zeros((0,), np.int32); cf = np.zeros((0,), np.float32)
        if frame.get("defects"):
            b = np.asarray([[d["x1"], d["y1"], d["x2"], d["y2"]] for d in frame["defects"]], np.float32)
            c = np.asarray([NAME2IDX.get(d["cls"], -1) for d in frame["defects"]], np.int32)
            cf = np.asarray([float(d["conf"]) for d in frame["defects"]], np.float32)
            bad = c < 0
            if bad.any():
                b, c, cf = b[~bad], c[~bad], cf[~bad]
        recs.append({"path": p, "n_gt": len(gt_b), "gt_cls": gt_c.tolist(),
                     "gt_box": gt_b.tolist(), "pr_cls": c.tolist(), "pr_box": b.tolist(),
                     "pr_conf": cf.tolist(), "infer_ms": frame.get("infer_ms")})
        if i % 20 == 0 or i == len(paths):
            el = time.time() - t0
            print("  [%d/%d] %.0fs  ETA %.0fs  已收 %d 帧，错 %d"
                  % (i, len(paths), el, el / i * (len(paths) - i), len(recs), len(errors)), flush=True)
            json.dump({"recs": recs, "errors": errors, "meta": {"limit": args.limit, "seed": args.seed}},
                      open(args.out, "w", encoding="utf-8"))

    s.close()

    # ---- 评估（板端已按 PER_CLASS_THRES 过滤，故 thres 视为 0：返回即保留）----
    gt_c = np.zeros(N_CLS, np.int64); pred_c = np.zeros(N_CLS, np.int64); tp_c = np.zeros(N_CLS, np.int64)
    tot_tp = tot_fp = tot_fn = 0
    for r in recs:
        gcls = np.asarray(r["gt_cls"], np.int32); n_gt = r["n_gt"]
        pcls = np.asarray(r["pr_cls"], np.int32)
        if n_gt:
            gt_c += np.bincount(gcls, minlength=N_CLS)
        if len(pcls):
            pred_c += np.bincount(pcls, minlength=N_CLS)
        mg, mp = set(), set()
        if n_gt and len(pcls):
            ious = iou_xyxy(np.asarray(r["gt_box"], np.float32), np.asarray(r["pr_box"], np.float32)).reshape(-1)
            order = np.argsort(-ious)
            order = order[ious[order] >= MATCH_IOU]
            for k in order:
                gi = int(k // len(pcls)); pj = int(k % len(pcls))
                if gi in mg or pj in mp:
                    continue
                mg.add(gi); mp.add(pj)
                tp_c[int(gcls[gi])] += 1
        tot_tp += len(mg); tot_fn += n_gt - len(mg); tot_fp += len(pcls) - len(mg)

    P = tot_tp / max(1, tot_tp + tot_fp); R = tot_tp / max(1, tot_tp + tot_fn)
    F1 = 2 * P * R / max(1e-12, P + R)
    print("=" * 72, flush=True)
    print("板端实测（e100 + 13 类标定阈值）  样本 %d 张" % len(recs), flush=True)
    print("  TP %d  FP %d  FN %d   P %.4f  R %.4f  F1 %.4f" % (tot_tp, tot_fp, tot_fn, P, R, F1), flush=True)
    print("  GT 框合计 %d  预测框合计 %d" % (int(gt_c.sum()), int(pred_c.sum())), flush=True)
    print("-" * 72, flush=True)
    print("%-26s %6s %6s %6s %6s" % ("类", "GT", "FP", "FN", "F1"), flush=True)
    fp_c = pred_c - tp_c; fn_c = gt_c - tp_c
    for i in np.argsort(-fp_c)[:18]:
        rec = tp_c[i] / max(1, gt_c[i]); pre = tp_c[i] / max(1, pred_c[i])
        f1 = 2 * rec * pre / max(1e-12, rec + pre)
        print("%-26s %6d %6d %6d %6.3f" % (NAMES[i], gt_c[i], fp_c[i], fn_c[i], f1), flush=True)
    print("错误样本数 %d" % len(errors), flush=True)

    json.dump({"recs": recs, "errors": errors,
               "summary": {"n_img": len(recs), "tp": tot_tp, "fp": tot_fp, "fn": tot_fn,
                           "precision": P, "recall": R, "f1": F1,
                           "gt_total": int(gt_c.sum()), "pred_total": int(pred_c.sum()),
                           "seed": args.seed, "limit": args.limit}},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("已写 %s" % args.out, flush=True)


if __name__ == "__main__":
    sys.exit(main())
