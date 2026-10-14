"""
难例回流周报脚本
================

目的：
  把上位机连续检测一周里"最容易翻车"的图挑出来 → 等人工复核 → 标注 → 入下轮训练。
  这是 P2 数据治理的"模型迭代闭环"环节。

数据源（按优先级）：
  ① records.db 里 confidence < 0.40 的 NG 记录 + image_path 真实存在的图
  ② 各 defect_type 均匀抽样（确保每类都有难例，不偏科）
  ③ 不去重只挑：同一张图多个 NG 框都计入（这是多个缺陷的难例）

输出：
  _hardpool/<周次>/
      images/        复制 50~100 张难例图（symlink 优先，文件不存在时回退复制）
      hardpool.md    难例清单（id/类/置信/路径），方便人工打开图核对
      weekly_summary.md  本周统计：每类数量、低置信 TOP-10 等

人工流程：
  1. 打开 hardpool.md
  2. 对每张图核对：模型判得对不对？框位置准不准？类别有没有搞错？
  3. 把"模型判错/判漏"的图重新标注成 YOLO 格式
  4. 入 datasets/hardpool/images+labels/，等下轮 train_*.py 加载

用法：
  # 周日晚上跑一次
  python _weekly_feedback.py
  # 或者带周次指定
  python _weekly_feedback.py --week 2026-09-14
  # 或者带目标数量
  python _weekly_feedback.py --target 80

为什么独立于训练脚本：
  - 训练脚本用绝对路径体检（_dataset_check.py）是为了防静默事故
  - 难例回流是"线下"流程，不需要 GPU
  - 用纯 Python + sqlite3，不依赖 ultralytics/torch
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '../..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "records.db"
HARDPOOL = BASE / "_hardpool"
DEFAULT_TARGET = 60          # 默认每周挑 60 张
LOW_CONF_THRES = 0.55        # 低置信阈值（NEU 模型稳定，0.40 候选太少；0.55 略宽）
PER_CLASS_MIN = 5            # 每类至少挑几张
# 缺陷类别表（与 infer.NAME_ZH / 板端 NAMES 同步）。
# 前 6 项为 NEU 真实类；扩展类用于难例回流时按类均匀抽样，
# 若某扩展类在库中无记录，抽样函数会自动跳过（不影响原有 6 类回流）。
CLASSES = ['crazing', 'inclusion', 'patches', 'pitted_surface', 'rolled-in_scale', 'scratches',
           'edge_crack', 'scab', 'pitting', 'roll_mark', 'wavy_edge', 'oxide_scale',
           'stain', 'oil_spot', 'water_spot', 'rust',
           # 09-28 扩展：39 类体系新增类（来源 缺陷检测扩展/data.yaml）
           'bright_scratch', 'crease', 'crescent_gap', 'dark_scratches',
           'finishing_roll_printing', 'iron_scale_compression', 'iron_sheet_ash',
           'oxide_scale_plate', 'oxide_scale_temp', 'punching', 'red_iron_sheet',
           'rolled_pit', 'secondary_rust_skin', 'silk_spot', 'slag_inclusion',
           'waist_folding', 'welding_line', 'white_rust', 'cutting_opening',
           'water_slag_mark', 'slag_skin', 'longitudinal_crack', 'warp',
           'external_fold', 'wrinkle', 'blocky_scale', 'striated_scale',
           'foreign_obj', 'blowhole', 'break', 'fray', 'uneven']


def query_low_confidence_records(conn, since_iso, target):
    """主源：低置信 NG 记录，按置信升序、类均匀。"""
    sql = """
    SELECT id, time, defect_type, area, confidence, image_path
    FROM records
    WHERE time >= ?
      AND result = 'NG'
      AND confidence IS NOT NULL
      AND confidence < ?
      AND image_path IS NOT NULL
      AND image_path != ''
    ORDER BY confidence ASC
    """
    rows = conn.execute(sql, (since_iso, LOW_CONF_THRES)).fetchall()
    return rows


def per_class_balance(rows, per_class_min=5, total_target=60):
    """按类均匀抽样：先每类取 per_class_min 张，再补到 total_target。"""
    by_class = defaultdict(list)
    for r in rows:
        cls = r[2] or "(空)"
        by_class[cls].append(r)

    selected = []
    # 第一轮：每类 per_class_min
    for cls, lst in by_class.items():
        for r in lst[:per_class_min]:
            selected.append(r)

    # 第二轮：补到 total_target
    if len(selected) < total_target:
        seen_ids = {r[0] for r in selected}
        for cls, lst in by_class.items():
            for r in lst:
                if len(selected) >= total_target:
                    break
                if r[0] not in seen_ids:
                    selected.append(r)
                    seen_ids.add(r[0])

    return selected


def link_or_copy(src, dst):
    """优先 symlink，失败时复制。"""
    try:
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(str(src), str(dst))
        return "symlink"
    except (OSError, NotImplementedError):
        shutil.copy2(src, dst)
        return "copy"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", help="周次标识（默认=今天）YYYY-MM-DD")
    ap.add_argument("--target", type=int, default=DEFAULT_TARGET,
                    help=f"目标难例数量（默认 {DEFAULT_TARGET}）")
    ap.add_argument("--days", type=int, default=7,
                    help="回看 N 天（默认 7）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只看统计，不实际复制")
    args = ap.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"DB 不存在: {DB_PATH}\n请先运行上位机产生数据。")

    week_id = args.week or datetime.now().strftime("%Y-%m-%d")
    week_dir = HARDPOOL / week_id
    img_dir = week_dir / "images"

    since = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== 难例回流周报 ===")
    print(f"周次: {week_id}")
    print(f"回看: {args.days} 天 (从 {since} 起)")
    print(f"DB:   {DB_PATH}")
    print(f"输出: {week_dir}")
    print()

    conn = sqlite3.connect(str(DB_PATH))

    # 1) 总览统计
    n_total = conn.execute("SELECT count(*) FROM records WHERE time >= ?", (since,)).fetchone()[0]
    n_ng = conn.execute("SELECT count(*) FROM records WHERE time >= ? AND result='NG'", (since,)).fetchone()[0]
    n_low = conn.execute(
        "SELECT count(*) FROM records WHERE time >= ? AND result='NG' AND confidence < ?",
        (since, LOW_CONF_THRES)
    ).fetchone()[0]
    n_with_img = conn.execute(
        "SELECT count(*) FROM records WHERE time >= ? AND result='NG' AND confidence < ? "
        "AND image_path IS NOT NULL AND image_path != ''",
        (since, LOW_CONF_THRES)
    ).fetchone()[0]
    print(f"--- {args.days} 天总览 ---")
    print(f"  总记录: {n_total}    NG: {n_ng}    低置信(<{LOW_CONF_THRES}): {n_low}    其中有图: {n_with_img}")
    print()

    # 2) 各类分布
    print(f"--- 低置信 NG 按类分布 ---")
    by_cls = conn.execute(
        "SELECT defect_type, count(*) FROM records WHERE time >= ? AND result='NG' "
        "AND confidence < ? AND image_path != '' GROUP BY defect_type ORDER BY 2 DESC",
        (since, LOW_CONF_THRES)
    ).fetchall()
    for cls, n in by_cls:
        print(f"  {cls:20s}  {n:>3d}")
    print()

    # 3) 选难例
    rows = query_low_confidence_records(conn, since, args.target)
    if not rows:
        print("⚠️ 没有低置信 NG 记录，跳过。")
        return

    selected = per_class_balance(rows, per_class_min=PER_CLASS_MIN,
                                  total_target=args.target)
    print(f"--- 本周难例候选: {len(selected)} 张 ---")
    if args.dry_run:
        print("[dry-run 模式，不实际复制]")
        return

    # 4) 复制 / 链接
    img_dir.mkdir(parents=True, exist_ok=True)
    hardpool_md = week_dir / "hardpool.md"
    summary_md = week_dir / "weekly_summary.md"
    n_symlink = n_copy = 0
    n_missing = 0
    missing_list = []
    with open(hardpool_md, "w", encoding="utf-8") as f:
        f.write(f"# 难例周报 {week_id}\n\n")
        f.write(f"回看 {args.days} 天（{since} 起），挑 {len(selected)} 张低置信 NG 候选。\n")
        f.write(f"低置信阈值: < {LOW_CONF_THRES}\n\n")
        f.write("| id | 时间 | 类 | 置信 | 面积 | 原图 | 难例图 | 备注 |\n")
        f.write("|---:|------|---|-----:|-----:|------|--------|------|\n")
        for r in selected:
            rid, ts, cls, area, conf, src = r
            src_p = Path(src)
            if not src_p.exists() or src_p.stat().st_size == 0:
                # 09-20 修：源文件不存在或 0 字节都标记 MISSING（避免复制到难例目录）
                n_missing += 1
                missing_list.append(src)
                f.write(f"| {rid} | {ts} | {cls} | {conf:.2f} | {area:.1f} | `{src}` | ❌ MISSING | - |\n")
                continue
            # 目标文件名：DB id + 类别 + 置信 + 原 stem
            # 09-20 修：必须带 db id，否则同一 src 文件被多次写入时，目标会被覆盖
            # （原因：上位机 sample_*.jpg 命名复用，低置信版本被后续高置信版本覆盖）
            stem = src_p.stem
            dst_name = f"{rid:06d}_{cls}_{conf:.2f}_{stem}.jpg"
            dst = img_dir / dst_name
            mode = link_or_copy(src_p, dst)
            if mode == "symlink":
                n_symlink += 1
            else:
                n_copy += 1
            f.write(f"| {rid} | {ts} | {cls} | {conf:.2f} | {area:.1f} | `{src}` | `{dst.name}` | - |\n")

    # 09-20 修：若全部 missing，提醒用户去补 / D:/Inspect/Images/ 已清
    if n_missing == len(selected) and len(selected) > 0:
        print()
        print(f"⚠️  本周 {len(selected)} 张候选全部 MISSING，源文件可能已被清空。")
        print(f"   原因：上位机 D:/Inspect/Images/ 受 utils.disk_guard() 清理。")
        print(f"   处置：保留 DB 记录供追溯；下周新生成的样本会用新命名（带时间戳），不再被覆盖。")

    # 5) 每周 summary
    cls_count = Counter(r[2] for r in selected)
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write(f"# 难例周报 Summary — {week_id}\n\n")
        f.write(f"## 统计\n\n")
        f.write(f"- 总记录: {n_total}\n")
        f.write(f"- NG: {n_ng}\n")
        f.write(f"- 低置信 NG (< {LOW_CONF_THRES}): {n_low}\n")
        f.write(f"- 有图难例: {n_with_img}\n")
        f.write(f"- 本周挑出: {len(selected)}\n")
        f.write(f"  - symlink: {n_symlink}\n")
        f.write(f"  - 复制:    {n_copy}\n")
        f.write(f"  - 缺图:    {n_missing}\n\n")
        f.write(f"## 按类分布\n\n")
        f.write("| 类 | 数量 |\n|---|---:|\n")
        for cls, n in cls_count.most_common():
            f.write(f"| {cls} | {n} |\n")
        f.write("\n## 下一步\n\n")
        f.write("1. 打开 `hardpool.md`\n")
        f.write("2. 对每张图在 `images/` 目录核对：\n")
        f.write("   - 模型判的类别对吗？\n")
        f.write("   - 框位置准吗？\n")
        f.write("   - 有没有漏检的缺陷？\n")
        f.write("3. 把判错/漏的图用 YOLO 格式重新标注\n")
        f.write(f"4. 入 `datasets/hardpool/images+labels/`，等下轮 `train_*.py` 加载\n")

    print(f"--- 输出 ---")
    print(f"  难例清单:  {hardpool_md}")
    print(f"  周 summary: {summary_md}")
    print(f"  图目录:    {img_dir}/  ({len(selected) - n_missing} 张)")
    print(f"  缺图:      {n_missing} 张")
    if missing_list:
        print(f"    头 3 张: {missing_list[:3]}")
    print()
    print(f"✅ 难例周报生成完成。下一步：打开 {hardpool_md} 核对。")


if __name__ == "__main__":
    main()
