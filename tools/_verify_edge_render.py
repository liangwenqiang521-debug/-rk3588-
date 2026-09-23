# -*- coding: utf-8 -*-
"""验证 09-21 修复：
  (A) 边缘结果的中文名映射 + 分类配色（原先硬编码英文 + C_RED）
  (B) _start() 重置统计时同步清空检测记录表（原先口径不一致）

用法: python _verify_edge_render.py
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys
import json

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception as e:
    print("[warn] 预加载失败:", e)

from PyQt5.QtWidgets import QApplication

import main as m
from infer import NAME_ZH, CLASS_COLORS


def edge_result(cls_en, conf, w=640, h=640):
    return {
        "type": "result", "ok": False, "w": w, "h": h, "infer_ms": 83.0,
        "defects": [{"x1": 300, "y1": 300, "x2": 360, "y2": 420,
                     "cls": cls_en, "conf": conf}],
    }


def main():
    app = QApplication(sys.argv)
    win = m.MainWindow(); win.resize(1600, 950); win.show()
    app.processEvents()
    page = win.pages[0]
    page._edge_detect_enabled = True

    fails = []

    # ---------- (A) 中文名 + 分类色 ----------
    print("=== (A) 边缘结果的类别名与配色 ===")
    cases = ["inclusion", "crazing", "rust", "edge_crack"]   # 含新增扩展类
    for en in cases:
        page._on_edge_result(edge_result(en, 0.7))
        app.processEvents()
        rd = page.canvas._real_defects or []
        if not rd:
            fails.append("%s: 画布无框" % en); print("  FAIL %s 无框" % en); continue
        d = rd[0]
        exp_zh = NAME_ZH.get(en, en)
        exp_col = CLASS_COLORS.get(en, "#f85149")
        # name 必须是英文原名（入库/历史筛选口径），name_zh 才是中文（显示用）
        ok_raw = d.get("name") == en
        ok_name = d.get("name_zh") == exp_zh
        ok_col = str(d.get("color", "")).lower() == exp_col.lower()
        print("  %-12s name=%-14s(%s)  中文名=%-8s(%s)  颜色=%s(%s)"
              % (en, d.get("name"), "OK" if ok_raw else "FAIL",
                 d.get("name_zh"), "OK" if ok_name else "FAIL",
                 d.get("color"), "OK" if ok_col else "FAIL"))
        if not ok_raw:  fails.append("%s: name 应保持英文原名，实为 %r" % (en, d.get("name")))
        if not ok_name: fails.append("%s: 中文名 %r != %r" % (en, d.get("name_zh"), exp_zh))
        if not ok_col:  fails.append("%s: 颜色 %r != %r" % (en, d.get("color"), exp_col))

    # 不同类别是否真的不同色
    cols = set()
    for en in cases:
        page._on_edge_result(edge_result(en, 0.7)); app.processEvents()
        rd = page.canvas._real_defects or []
        if rd: cols.add(str(rd[0].get("color", "")).lower())
    print("  4 个类别产生的不同颜色数: %d（应 = 4）" % len(cols))
    if len(cols) < 4:
        fails.append("类别配色未生效（只有 %d 种颜色）" % len(cols))

    # ---------- (B) 统计与记录表同步 ----------
    print("\n=== (B) 开始检测时统计与记录表同步归零 ===")
    before_rows = page.table.rowCount()
    before_total = page.total
    page._start()
    app.processEvents()
    after_rows = page.table.rowCount()
    after_total = page.total
    print("  _start 前: 记录表 %d 行 / total=%d" % (before_rows, before_total))
    print("  _start 后: 记录表 %d 行 / total=%d" % (after_rows, after_total))
    if after_rows != 0 or after_total != 0:
        fails.append("_start 未同步清零（表=%d total=%d）" % (after_rows, after_total))
    else:
        print("  OK  两者同步归零")

    print("\n" + "=" * 50)
    if fails:
        print("失败项:")
        for f in fails:
            print("  -", f)
    else:
        print("全部通过")
    print("=" * 50)


if __name__ == "__main__":
    main()
