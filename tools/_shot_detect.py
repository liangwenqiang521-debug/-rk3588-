# -*- coding: utf-8 -*-
"""截取上位机检测页实图（真实平台，中文可渲染）。输出 tools/_shot_detect.png"""
import os as _os
import sys as _sys

_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import sys

# 复刻 main.py 导入顺序
try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception:
    pass

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import main as M  # noqa: E402

app.setStyleSheet(M.QSS)
win = M.MainWindow()
win.resize(1500, 940)
win.show()
win.stack.setCurrentIndex(0)          # 检测页
app.processEvents()

# 灌一点演示分布数据，让分布图有内容
try:
    ch = win.pages[0].defect_chart
    ch.set_data({"夹杂物": 12, "亮划痕": 9, "龟裂": 7, "斑块": 5,
                 "麻面": 3, "轧入氧化皮": 2, "月牙缺口": 1})
    app.processEvents()
except Exception as e:
    print("chart skip:", e)

win.grab().save(_os.path.join(_ROOT, "tools", "_shot_detect.png"))
print("saved tools/_shot_detect.png")
win.close()
