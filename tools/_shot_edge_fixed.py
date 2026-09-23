# -*- coding: utf-8 -*-
"""渲染：边缘结果修复后的检测页（中文标签 + 分类配色）。

用法: python _shot_edge_fixed.py
产出: _shots/edge_fixed.png
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception as e:
    print("[warn] 预加载失败:", e)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter

import main as m

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shots")


def render(widget):
    img = QImage(widget.size(), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    widget.render(p)
    p.end()
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(m.QSS)
    win = m.MainWindow(); win.resize(1600, 950); win.show()
    app.processEvents()

    page = win.pages[0]
    page._edge_detect_enabled = True
    page._alarm_enabled = False          # 截图时别响

    # 模拟一批多类别板端结果，覆盖原有 6 类 + 新增扩展类
    batch = [
        ("crazing", 0.62, 200, 180, 280, 300),
        ("inclusion", 0.72, 300, 300, 360, 420),
        ("scratches", 0.81, 420, 120, 470, 300),
        ("rust", 0.66, 150, 380, 230, 460),
        ("edge_crack", 0.58, 480, 350, 560, 470),
        ("stain", 0.51, 350, 200, 420, 260),
    ]
    for en, conf, x1, y1, x2, y2 in batch:
        obj = {"type": "result", "ok": False, "w": 640, "h": 640, "infer_ms": 88.0,
               "defects": [{"cls": en, "conf": conf,
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2}]}
        page._on_edge_result(obj)
        for _ in range(3):
            app.processEvents()

    for _ in range(8):
        app.processEvents()

    path = os.path.join(OUT, "edge_fixed.png")
    render(win).save(path)
    print("saved", path)
    print("统计: total=%d ok=%d ng=%d" % (page.total, page.ok, page.ng))
    print("记录表行数:", page.table.rowCount())
    for i in range(min(6, page.table.rowCount())):
        print("   行%d: %s | %s" % (i,
              page.table.item(i, 1).text() if page.table.item(i, 1) else "",
              page.table.item(i, 2).text() if page.table.item(i, 2) else ""))


if __name__ == "__main__":
    main()
