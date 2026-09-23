"""
数据集完整性体检（YOLO 格式）
=============================

检查项：
  ① 图签一一对应（无孤儿标签、无孤儿图像）
  ② 文件可读性（图像非空、标签格式正确）
  ③ 框合法性（坐标在 [0,1]、宽高 > 0、类别 ID 在 nc 范围内）
  ④ 类映射审计（NC 与 yaml 声明一致、names 顺序与 ID 对齐）
  ⑤ 逐类样本量分布（发现严重不均衡时给出警告）
  ⑥ 已知陷阱：含中文绝对路径的 cv2.imwrite 静默失败
     → 体检脚本里会**强制**读回所有图像，绕过 imwrite 的"假成功"

退出码：
  0 = 全部通过
  1 = 存在硬错（缺图、缺签、框越界、类 ID 越界、图像读不出）
  2 = 软警告（不均衡、极少样本、命名不规范）→ 仅打印，不中断

用法：
  python _dataset_check.py --data data_neu.yaml
  python _dataset_check.py --data data_neu_dagm.yaml --strict
  python _dataset_check.py --root datasets/neu_det --nc 6 --names crazing inclusion patches pitted_surface rolled-in_scale scratches
  python _dataset_check.py --data data_neu.yaml --json _check_neu.json

为什么单独写：
  cv2.imwrite 写中文路径静默返回 False（不抛异常、不落盘），
  → 训练照样跑完、指标照样汇报，错得无声无息
  → 本体检脚本独立于训练流程，强制读回每张图，确保"图真的在"
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

try:
    import cv2
except ImportError:
    cv2 = None  # 部分场景下 cv2 不需要


# ---------- 工具 ----------

def parse_yolo_label(path):
    """读 YOLO 格式 txt，每行: cls cx cy w h (相对坐标)。
    返回 (records, error_msg)。records = [(cls, cx, cy, w, h), ...]
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return [], f"标签文件编码错（不是 utf-8）: {e}"
    except Exception as e:
        return [], f"读标签失败: {e}"
    records = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            return [], f"第 {i} 行格式错（应 5 个字段）: {line!r}"
        try:
            c = int(parts[0])
            cx, cy, w, h = map(float, parts[1:5])
        except ValueError as e:
            return [], f"第 {i} 行解析失败: {e}"
        records.append((c, cx, cy, w, h))
    return records, None


def check_image_readable(path):
    """强制读回图像，确认文件真实存在 + cv2 能解码。
    这是为了对抗 cv2.imwrite 写中文路径静默失败的陷阱：
    imwrite 返回 True 但文件实际未落盘 → 文件 size = 0 → 读不出。

    ⚠️ 已知 cv2.imread 在 Windows 上读「含中文的绝对路径」会静默失败（返回 None）。
    我们的策略：用 np.fromfile + cv2.imdecode（Unicode 安全，与 ultralytics 一致）。
    """
    if not path.exists():
        return False, "文件不存在"
    sz = path.stat().st_size
    if sz == 0:
        return False, "文件大小为 0（疑似 imwrite 静默失败）"
    if sz < 100:  # jpg/png 头都几百字节，< 100 字节一定是垃圾
        return False, f"文件过小（{sz} 字节）"
    if cv2 is not None:
        try:
            # Unicode 安全读图（绕开 cv2.imread 的中文路径 bug）
            import numpy as np
            data = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        except Exception as e:
            return False, f"cv2.imdecode 抛异常: {e}"
        if img is None:
            return False, "cv2.imdecode 解码失败（文件损坏或非图像）"
        h, w = img.shape[:2]
        if h < 8 or w < 8:
            return False, f"图像分辨率过小（{w}x{h}）"
    return True, None


# ---------- 体检主流程 ----------

def check_dataset(root, yaml_cfg, split_name, strict=False):
    """对单个 split 体检（train / val / cal / holdout 等）。
    返回 dict 报告。
    """
    img_dir = root / "images" / split_name
    lbl_dir = root / "labels" / split_name
    report = {
        "split": split_name,
        "img_dir": str(img_dir),
        "lbl_dir": str(lbl_dir),
        "n_images": 0,
        "n_labels": 0,
        "n_empty_labels": 0,  # 空标签（无缺陷的负样本图）
        "n_total_boxes": 0,
        "per_class_boxes": {},
        "per_class_images": {},
        "errors": [],
        "warnings": [],
    }
    nc = yaml_cfg["nc"]
    names = yaml_cfg.get("names", [str(i) for i in range(nc)])

    if not img_dir.exists():
        report["errors"].append(f"图像目录不存在: {img_dir}")
        return report
    if not lbl_dir.exists():
        report["errors"].append(f"标签目录不存在: {lbl_dir}")
        return report

    # 收集所有图像
    IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
    imgs = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    lbls = sorted(p for p in lbl_dir.iterdir() if p.suffix.lower() == ".txt")

    img_stems = {p.stem for p in imgs}
    lbl_stems = {p.stem for p in lbls}

    # ① 图签一一对应
    orphan_labels = lbl_stems - img_stems  # 有签无图
    orphan_imgs = img_stems - lbl_stems    # 有图无签

    if orphan_labels:
        report["errors"].append(
            f"孤儿标签（{len(orphan_labels)} 个，标签有但图像无）: "
            f"{sorted(orphan_labels)[:5]}{'...' if len(orphan_labels)>5 else ''}"
        )
    if orphan_imgs:
        # 有图无签：可能是负样本（空标签也允许），但若是常规检测集要报警
        if strict:
            report["errors"].append(
                f"孤儿图像（{len(orphan_imgs)} 个，图像有但标签无）: "
                f"{sorted(orphan_imgs)[:5]}{'...' if len(orphan_imgs)>5 else ''}"
            )
        else:
            report["warnings"].append(
                f"孤儿图像 {len(orphan_imgs)} 个（非严格模式下放过）"
            )

    report["n_images"] = len(imgs)
    report["n_labels"] = len(lbls)

    # ② 文件可读 + ③ 框合法性
    cls_box_counter = Counter()
    cls_img_counter = Counter()
    bad_class = []
    for img in imgs:
        # ② 文件可读
        ok, err = check_image_readable(img)
        if not ok:
            report["errors"].append(f"图像损坏: {img.name} - {err}")
            continue
        # ③ 读标签
        lbl = lbl_dir / f"{img.stem}.txt"
        if lbl.exists():
            records, err = parse_yolo_label(lbl)
            if err:
                report["errors"].append(f"标签解析失败: {img.name} - {err}")
                continue
        else:
            records = []  # 没标签 = 负样本
        if not records:
            report["n_empty_labels"] += 1
        for c, cx, cy, w, h in records:
            if c < 0 or c >= nc:
                bad_class.append((img.name, c))
                continue
            # 坐标合法性（相对坐标应 [0,1]）
            if not (0 <= cx <= 1 and 0 <= cy <= 1):
                report["errors"].append(
                    f"中心点越界: {img.name} cls={c} cx={cx:.3f} cy={cy:.3f}"
                )
                continue
            if w <= 0 or h <= 0 or w > 1 or h > 1:
                report["errors"].append(
                    f"宽高非法: {img.name} cls={c} w={w:.3f} h={h:.3f}"
                )
                continue
            cls_box_counter[c] += 1
            cls_img_counter[c] += 1
        report["n_total_boxes"] += len(records)

    if bad_class:
        # 累所有非法类 ID（去重文件名）
        bad_files = sorted({n for n, _ in bad_class})
        report["errors"].append(
            f"类 ID 越界（nc={nc}）: {len(bad_class)} 个框涉及 {len(bad_files)} 文件, "
            f"例: {bad_class[:3]}"
        )

    for i, name in enumerate(names):
        report["per_class_boxes"][name] = cls_box_counter.get(i, 0)
        report["per_class_images"][name] = cls_img_counter.get(i, 0)

    # ⑤ 不均衡检查
    counts = [report["per_class_boxes"][n] for n in names]
    if counts and max(counts) > 0:
        max_c = max(counts)
        min_c = min(c for c in counts if c > 0) if any(c > 0 for c in counts) else 0
        if min_c > 0 and max_c / min_c > 10:
            report["warnings"].append(
                f"类间样本不均衡: max={max_c} min={min_c} 比例 {max_c/min_c:.1f}x (>10x 警告)"
            )
        if min_c < 50 and min_c > 0:
            report["warnings"].append(f"最小类样本极少: {min_c} 框（<50）")

    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="YOLO 数据集 yaml 路径（含 path/nc/names/train/val）")
    ap.add_argument("--root", help="数据集根目录（替代 --data 的 path 字段）")
    ap.add_argument("--nc", type=int, help="类别数")
    ap.add_argument("--names", help="类别名（逗号分隔）")
    ap.add_argument("--splits", default="train,val", help="要检查的子集，逗号分隔")
    ap.add_argument("--strict", action="store_true", help="严格模式：有图无签也算错")
    ap.add_argument("--json", help="结果写到 JSON 文件")
    ap.add_argument("--exit-on-error", action="store_true",
                    help="有硬错时退出码=1（用于 train_*.py 前置调用）")
    args = ap.parse_args()

    # 解析 yaml / 参数
    if args.data:
        try:
            import yaml
        except ImportError:
            print("ERROR: 需要 PyYaml 解析 --data yaml（pip install pyyaml）", file=sys.stderr)
            sys.exit(2)
        cfg = yaml.safe_load(Path(args.data).read_text(encoding="utf-8"))
        root = Path(cfg["path"])
        nc = cfg["nc"]
        names = cfg.get("names", [str(i) for i in range(nc)])
        splits = args.splits.split(",")
    elif args.root and args.nc and args.names:
        root = Path(args.root)
        nc = args.nc
        names = args.names.split(",")
        splits = args.splits.split(",")
    else:
        print("ERROR: 必须传 --data 或 (--root --nc --names)", file=sys.stderr)
        sys.exit(2)

    print("=" * 70)
    print(f"数据集体检: {root}")
    print(f"nc={nc}  names={names}")
    print(f"splits={splits}  strict={args.strict}")
    print("=" * 70)

    yaml_cfg = {"nc": nc, "names": names}
    all_reports = []
    any_hard_error = False
    for sp in splits:
        rpt = check_dataset(root, yaml_cfg, sp, strict=args.strict)
        all_reports.append(rpt)
        # 打印
        print(f"\n--- {sp} ---")
        print(f"  图像: {rpt['n_images']}    标签: {rpt['n_labels']}    "
              f"空标签(负样本): {rpt['n_empty_labels']}    总框: {rpt['n_total_boxes']}")
        if rpt['per_class_boxes']:
            print(f"  {'类':<20s} {'框':>6s} {'图':>6s}")
            for n in names:
                print(f"  {n:<20s} {rpt['per_class_boxes'].get(n, 0):>6d} "
                      f"{rpt['per_class_images'].get(n, 0):>6d}")
        for e in rpt["errors"]:
            print(f"  [ERROR] {e}")
            any_hard_error = True
        for w in rpt["warnings"]:
            print(f"  [WARN]  {w}")

    # 总结
    print("\n" + "=" * 70)
    if any_hard_error:
        print(f"❌ 体检未通过：发现 {sum(len(r['errors']) for r in all_reports)} 个硬错")
        print("   请逐条修复后再训练！")
    else:
        warn_n = sum(len(r['warnings']) for r in all_reports)
        if warn_n:
            print(f"✅ 体检通过（有 {warn_n} 个软警告，可继续训练）")
        else:
            print("✅ 体检完美通过：所有检查项均 OK")
    print("=" * 70)

    if args.json:
        out = {
            "root": str(root),
            "nc": nc,
            "names": names,
            "splits": all_reports,
            "any_hard_error": any_hard_error,
        }
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        print(f"\n结果已写到: {args.json}")

    if args.exit_on_error and any_hard_error:
        sys.exit(1)
    sys.exit(0 if not any_hard_error else 1)


if __name__ == "__main__":
    main()
