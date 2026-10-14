# -*- coding: utf-8 -*-
"""漏标候选核对表生成：按 conf 分级裁图拼图，红框=候选漏标框，绿框=已有 GT 框。"""
import argparse
import csv
import io
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(r"D:\workbuddy\缺陷检测项目")
EXT = ROOT / "缺陷检测扩展"
TMP = Path(r"C:\Users\21191\AppData\Local\Temp\_wb_neg")
OUT = ROOT / "docs" / "fp_audit" / "review_sheets"

# 每个 cell 拼图目标尺寸
CELL = 320
COLS = 5
ROWS = 4  # 每张拼图 20 个 cell

NAMES = [
    "crazing", "inclusion", "patches", "pitted_surface", "rolled-in_scale", "scratches",
    "welding_line", "silver_blister", "silk_spot", "water_spot", "oxide_scale_temp",
    "oxide_scale_plate", "finishing_roll_printing", "iron_scale_compression", "iron_sheet_ash",
    "fold", "dark_scratches", "bright_scratch", "oil_spot", "crease", "warp",
    "waist_folding", "edge_crack", "crescent_gap", "punching", "roll_marks", "pockmark",
    "scuffing", "pitting", "striated_scale", "laminar_oxide", "scale_pitting",
    "silver_surface", "saw_tooth", "fish_scale", "seam", "shell", "spot_crack", "hairline",
]


def load_cache(split):
    pkl = TMP / f"{split}_preds.pkl"
    with open(pkl, "rb") as f:
        return pickle.load(f)


def build_index(cache):
    # name -> record
    return {c["name"]: c for c in cache}


def draw_box(img, x1, y1, x2, y2, color, width=2, label=None):
    cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, width)
    if label:
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img, (int(x1), int(y1) - th - 6), (int(x1) + tw + 4, int(y1)), color, -1)
        cv2.putText(img, label, (int(x1) + 2, int(y1) - 4), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)


def render_cell(rec, cand, split, expand=1.6):
    """cand: dict 含 image/cls/conf/x1/y1/x2/y2；rec: 缓存记录。返回裁剪图。"""
    img_path = EXT / "images" / split / rec["name"]
    img = cv2.imdecode(np.fromfile(str(img_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None, "IMG_FAIL"

    h, w = img.shape[:2]
    x1, y1, x2, y2 = cand["x1"], cand["y1"], cand["x2"], cand["y2"]
    # 以候选框为中心，扩大 expand 倍裁剪（限制在图内）
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    bw, bh = (x2 - x1) * expand, (y2 - y1) * expand
    half_w, half_h = bw / 2, bh / 2
    # 保证至少能看到周边
    half_w = max(half_w, (x2 - x1) * 0.8)
    half_h = max(half_h, (y2 - y1) * 0.8)
    ox1 = max(0, int(cx - half_w)); oy1 = max(0, int(cy - half_h))
    ox2 = min(w, int(cx + half_w)); oy2 = min(h, int(cy + half_h))
    crop = img[oy1:oy2, ox1:ox2].copy()

    # 画已有 GT 框（绿）
    for gb in rec["gt_b"]:
        gx1, gy1, gx2, gy2 = gb
        draw_box(crop, gx1 - ox1, gy1 - oy1, gx2 - ox1, gy2 - oy1, (0, 200, 0), 1)
    # 画候选漏标框（红）
    draw_box(crop, x1 - ox1, y1 - oy1, x2 - ox1, y2 - oy1, (0, 0, 255), 3,
             label=f"{cand['cls']} {cand['conf']:.2f}")

    # 缩放填到 cell
    return crop, "OK"


def make_sheet(cells_data, title):
    """cells_data: list of (crop, caption) 或 (None, err)。拼成一张图返回。"""
    n = len(cells_data)
    rows = (n + COLS - 1) // COLS
    sheet = np.full((rows * (CELL + 24), COLS * CELL, 3), 40, np.uint8)
    for k, (crop, cap) in enumerate(cells_data):
        r, c = k // COLS, k % COLS
        ox, oy = c * CELL, r * (CELL + 24)
        # 标题区
        cv2.putText(sheet, cap, (ox + 4, oy + 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.42, (220, 220, 220), 1, cv2.LINE_AA)
        if crop is None:
            cv2.putText(sheet, "FAIL:" + cap, (ox + 4, oy + 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            continue
        # 缩放到 cell 内
        ch, cw = crop.shape[:2]
        sc = min(CELL / cw, CELL / ch)
        nw, nh = int(cw * sc), int(ch * sc)
        resized = cv2.resize(crop, (nw, nh))
        px = ox + (CELL - nw) // 2
        py = oy + 24 + (CELL - nh) // 2
        sheet[py:py + nh, px:px + nw] = resized
    return sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["val", "train"], required=True)
    ap.add_argument("--conf-lo", type=float, default=0.45)
    ap.add_argument("--conf-hi", type=float, default=0.60)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    split = args.split
    csv_path = ROOT / "模型训练" / f"_miss_candidates_{split}.csv"
    cache = load_cache(split)
    idx = build_index(cache)

    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        for r in rd:
            conf = float(r["conf"])
            if args.conf_lo <= conf < args.conf_hi:
                rows.append(r)

    # 按 conf 降序，确保高置信优先
    rows.sort(key=lambda r: -float(r["conf"]))
    if args.limit:
        rows = rows[:args.limit]

    print(f"[{split}] conf∈[{args.conf_lo},{args.conf_hi}) 候选数 = {len(rows)}", flush=True)

    cells = []
    fails = 0
    for r in rows:
        name = r["image"]
        rec = idx.get(name)
        if rec is None:
            cells.append((None, f"{name} NO_CACHE"))
            fails += 1
            continue
        cand = {
            "cls": r["cls"], "conf": float(r["conf"]),
            "x1": float(r["x1"]), "y1": float(r["y1"]),
            "x2": float(r["x2"]), "y2": float(r["y2"]),
        }
        crop, status = render_cell(rec, cand, split)
        cap = f"{name[:18]} {r['cls'][:12]} {r['conf']}"
        if status != "OK":
            cells.append((None, cap + " " + status))
            fails += 1
        else:
            cells.append((crop, cap))

    # 分页拼图
    OUT.mkdir(parents=True, exist_ok=True)
    page = 0
    for i in range(0, len(cells), COLS * ROWS):
        chunk = cells[i:i + COLS * ROWS]
        sheet = make_sheet(chunk, f"")
        page += 1
        out_path = OUT / f"review_{split}_conf{args.conf_lo:.2f}-{args.conf_hi:.2f}_p{page:02d}.png"
        cv2.imencode(".png", sheet)[1].tofile(str(out_path))
        print(f"  写出 {out_path.name}  ({len(chunk)} cell)", flush=True)

    print(f"完成：{len(rows)} 候选，{fails} 失败，{page} 页", flush=True)


if __name__ == "__main__":
    main()
