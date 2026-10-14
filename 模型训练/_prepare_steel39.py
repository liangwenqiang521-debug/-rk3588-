# -*- coding: utf-8 -*-
"""39 类钢板缺陷数据集 · 本机训练前置准备
=========================================

做两件事：
  ① 校验类别**索引顺序**三方一致
       infer.CLASSES_39  /  缺陷检测扩展/data.yaml  /  板端 NAMES_EXT
  ② 生成**本机可用**的训练 yaml（原始 data.yaml 的 path 指向另一台机器）

为什么单独生成 yaml：
  原 `缺陷检测扩展/data.yaml` 的 `path:` 指向
      D:/RK3588&Orin Nano/ORIN NANO/.../datasets_master/production/v2.1
  本机不存在 → ultralytics 直接 Dataset not found。
  另：ultralytics 对**相对** path 是按 DATASETS_DIR 解析、不是按 yaml 所在目录，
  所以统一写**绝对路径**，最稳。

为什么 names 用 snake_case（而不是原 yaml 的可读英文名）：
  `infer.py:288` 是  `en = self.names.get(cls)` —— 上位机取的是**模型内嵌类名**，
  再拿它去查 NAME_ZH / CLASS_COLORS。
  若 names 写成 'Bright scratch'，查表落空 → 界面只显示英文、颜色回退默认色。
  写成 'bright_scratch' 才能命中中文名与配色。
  标签文件存的是**索引**，所以改 names 不影响训练本身，只影响模型元数据。

用法：
  python _prepare_steel39.py            # 校验 + 写 yaml
  python _prepare_steel39.py --check    # 只校验，不写文件
"""
import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
EXT_DIR = ROOT / "缺陷检测扩展"
SRC_YAML = EXT_DIR / "data.yaml"
OUT_YAML = SCRIPT_DIR / "data_steel39.yaml"
INFER_PY = ROOT / "infer.py"
BOARD_PY = ROOT / "部署" / "rk3588" / "board_server_cascade.py"

# ---------------------------------------------------------------------------
# 权威索引映射：数据集 yaml 的显示名  ->  项目内部 snake_case key
# 这张表是「索引对齐」的书面依据（来源：缺陷检测扩展/BALANCE_REPORT.md 的 id 列）。
# 前 25 项显示名与 key 拼写不同（含空格/大小写/of system 等），无法机械归一化，
# 必须显式登记；后 14 项两者本来就相同。
# ---------------------------------------------------------------------------
DISPLAY_TO_KEY = {
    "Bright scratch": "bright_scratch",
    "Crazing": "crazing",
    "Crease": "crease",
    "Crescent gap": "crescent_gap",
    "Dark scratches": "dark_scratches",
    "Finishing roll printing": "finishing_roll_printing",
    "Inclusion": "inclusion",
    "Iron scale compression": "iron_scale_compression",
    "Iron sheet ash": "iron_sheet_ash",
    "Oil spot": "oil_spot",
    "Oxide scale of plate system": "oxide_scale_plate",
    "Oxide scale of temperature system": "oxide_scale_temp",
    "Patches": "patches",
    "Pitted surface": "pitted_surface",
    "Punching": "punching",
    "Red iron sheet": "red_iron_sheet",
    "Rolled in scale": "rolled-in_scale",
    "Rolled pit": "rolled_pit",
    "Secondary rust skin": "secondary_rust_skin",
    "Silk spot": "silk_spot",
    "Slag inclusion": "slag_inclusion",
    "Waist folding": "waist_folding",
    "Water spot": "water_spot",
    "Welding line": "welding_line",
    "White rust": "white_rust",
    "cutting_opening": "cutting_opening",
    "water_slag_mark": "water_slag_mark",
    "slag_skin": "slag_skin",
    "longitudinal_crack": "longitudinal_crack",
    "warp": "warp",
    "external_fold": "external_fold",
    "wrinkle": "wrinkle",
    "blocky_scale": "blocky_scale",
    "striated_scale": "striated_scale",
    "foreign_obj": "foreign_obj",
    "blowhole": "blowhole",
    "break": "break",
    "fray": "fray",
    "uneven": "uneven",
}


def _parse_names(text: str):
    """从 yaml 文本里取 names 列表（跨行，python 字面量，单引号）"""
    i = text.index("names:")
    seg = text[i + len("names:"):]
    j = seg.index("]")
    return eval(seg[: j + 1].strip())


def _parse_nc(text: str):
    m = re.search(r"^nc:\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else None


def _classes_39_from_infer():
    src = INFER_PY.read_text(encoding="utf-8")
    m = re.search(r"^CLASSES_39 = \[(.*?)^\]", src, re.S | re.M)
    if not m:
        raise SystemExit("infer.py 里找不到 CLASSES_39")
    return eval("[" + m.group(1) + "]")


def _name_zh_from_infer():
    """解析 NAME_ZH 字典（仅取字面量，不 import infer —— 避免拉起 ultralytics）"""
    src = INFER_PY.read_text(encoding="utf-8")
    m = re.search(r"^NAME_ZH = \{(.*?)^\}", src, re.S | re.M)
    if not m:
        return {}
    body = re.sub(r"#[^\n]*", "", m.group(1))
    try:
        return eval("{" + body + "}")
    except Exception:
        return {}


def _names_ext_from_board():
    src = BOARD_PY.read_text(encoding="utf-8")
    m = re.search(r"NAMES_EXT\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        return None
    body = re.sub(r"#[^\n]*", "", m.group(1))
    return eval("[" + body + "]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写 yaml")
    args = ap.parse_args()

    names_disp = _parse_names(SRC_YAML.read_text(encoding="utf-8"))
    nc = _parse_nc(SRC_YAML.read_text(encoding="utf-8"))
    c39 = _classes_39_from_infer()
    nzh = _name_zh_from_infer()
    board = _names_ext_from_board()

    print("=" * 70)
    print("① 类别索引顺序校验")
    print("=" * 70)
    print("  infer.CLASSES_39            : %d" % len(c39))
    print("  缺陷检测扩展/data.yaml names : %d  (nc=%s)" % (len(names_disp), nc))
    print("  板端 NAMES_EXT              : %s" % (len(board) if board else "未找到"))
    print()

    fails = []
    if nc != len(names_disp):
        fails.append("data.yaml nc=%s 与 names 长度 %d 不符" % (nc, len(names_disp)))
    if len(c39) != nc:
        fails.append("infer.CLASSES_39 长度 %d 与 nc=%s 不符" % (len(c39), nc))

    # yaml 显示名 -> key，逐位比对 infer.CLASSES_39
    for k, disp in enumerate(names_disp):
        key = DISPLAY_TO_KEY.get(disp)
        if key is None:
            fails.append("  idx %2d  yaml 显示名未登记: %r" % (k, disp))
            continue
        if k >= len(c39):
            failures = True
            continue
        if key != c39[k]:
            fails.append("  idx %2d  %r -> key=%r  但 infer[%d]=%r"
                         % (k, disp, key, k, c39[k]))

    if board is not None and list(board) != list(c39):
        for k in range(max(len(board), len(c39))):
            a = board[k] if k < len(board) else "<缺>"
            b = c39[k] if k < len(c39) else "<缺>"
            if a != b:
                fails.append("  板端 idx %2d  NAMES_EXT=%r  infer=%r" % (k, a, b))

    if fails:
        print("[FAIL] 类别索引顺序校验未通过:")
        for f in fails:
            print("   ", f)
        print()
        print("索引错 = 模型输出整体错位，必须先对齐再训练。")
        sys.exit(1)

    print("[OK] 索引顺序三方一致（infer / 扩展 data.yaml / 板端 NAMES_EXT）")

    print()
    print("=" * 70)
    print("② 本机 data yaml")
    print("=" * 70)
    print("  数据集根: %s" % EXT_DIR)
    if not EXT_DIR.is_dir():
        sys.exit("[FAIL] 数据集目录不存在")
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        if not (EXT_DIR / sub).is_dir():
            sys.exit("[FAIL] 缺少目录: %s" % (EXT_DIR / sub))

    if args.check:
        print("  (--check 模式，不写文件)")
        return

    lines = [
        "# 39 类钢板表面缺陷 · 本机训练配置",
        "# 由 模型训练/_prepare_steel39.py 生成，请勿手改（改请改生成脚本）",
        "#",
        "# names 用 snake_case —— 必须与 infer.CLASSES_39 / 板端 NAMES_EXT 逐位一致。",
        "# 原因：上位机 infer.py 取「模型内嵌类名」去查 NAME_ZH / CLASS_COLORS，",
        "#       写成 'Bright scratch' 这类显示名会导致中文名与配色查表落空。",
        "# 标签文件存的是索引，故 names 只影响模型元数据，不影响训练本身。",
        "#",
        "#  idx  key                        显示名                          中文",
    ]
    for k, key in enumerate(c39):
        disp = names_disp[k] if k < len(names_disp) else ""
        zh = nzh.get(key, "")
        lines.append("#  %3d  %-26s %-30s %s" % (k, key, disp, zh))
    lines.append("")
    lines.append("path: %s" % str(EXT_DIR).replace("\\", "/"))
    lines.append("train: images/train")
    lines.append("val: images/val")
    lines.append("nc: %d" % nc)
    lines.append("names:")
    for key in c39:
        lines.append("  - %s" % key)
    lines.append("")

    OUT_YAML.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("  已写入: %s" % OUT_YAML)
    print("  nc=%d / names=%d" % (nc, len(c39)))

    back = OUT_YAML.read_text(encoding="utf-8")
    got = re.findall(r"^  - (\S+)$", back, re.M)
    assert got == list(c39), "回读 names 与 CLASSES_39 不一致"
    assert _parse_nc(back) == nc, "回读 nc 不一致"
    print("[OK] 回读校验通过（names 与 CLASSES_39 逐位一致）")


if __name__ == "__main__":
    main()
