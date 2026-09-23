# -*- coding: utf-8 -*-
"""验证 09-21 扩展缺陷类别：跑模拟模式灌数据 + 渲染检测页截图。

用法:
    python _verify_new_classes.py            # 每个类别灌 1 条，共 16 类
    python _verify_new_classes.py --n 3      # 每类灌 3 条

产出: _shots/verify_new_classes.png
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys
import argparse

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)   # 预加载 c10.dll，避免 WinError 1114
except Exception as e:
    print("[warn] 预加载 infer/torch 失败:", e)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter

import main as m
from infer import DEFECT_CLASSES, NAME_ZH, CLASS_COLORS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shots")


def render(widget):
    img = QImage(widget.size(), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    widget.render(p)
    p.end()
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1, help="每个类别灌入条数")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(m.QSS)

    win = m.MainWindow()
    win.resize(1600, 950)
    win.show()
    app.processEvents()

    page = win.pages[0]           # 实时检测页
    chart = page.defect_chart

    # 直接向分布图灌入全部类别（等价于模拟模式随机命中的效果）
    total = 0
    for _ in range(args.n):
        for en in DEFECT_CLASSES:
            chart.push(NAME_ZH[en])
            total += 1

    print("灌入 %d 条，覆盖 %d 类" % (total, len(DEFECT_CLASSES)))

    for _ in range(6):
        app.processEvents()

    path = os.path.join(OUT, "verify_new_classes.png")
    render(win).save(path)
    print("saved %s" % path)

    # 逐类打印，确认 16 类都在图里
    counts = chart.data
    print("分布图内部类别数: %d" % len(counts))
    for en in DEFECT_CLASSES:
        zh = NAME_ZH[en]
        print("  %-16s %-10s %s  n=%s" % (en, zh, CLASS_COLORS[en], counts.get(zh, 0)))


if __name__ == "__main__":
    main()
