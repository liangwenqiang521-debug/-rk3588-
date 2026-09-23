# -*- coding: utf-8 -*-
"""界面截图工具：用真实平台渲染全部页面到 _shots/（中文正常显示）。

用法:
    python _ui_smoke.py           # 截全部 6 页
    python _ui_smoke.py --page 0  # 只截第 0 页

注意：不要设 QT_QPA_PLATFORM=offscreen —— offscreen 下中文字体不渲染，
QScrollArea 子控件也会渲染不全，截图会失真。
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
from PyQt5.QtCore import QTimer

import main as m

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shots")
NAMES = ["detect", "settings", "history", "comm", "log", "npu"]


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", type=int, default=-1)
    ap.add_argument("--w", type=int, default=1600)
    ap.add_argument("--h", type=int, default=950)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(m.QSS)

    win = m.MainWindow()
    win.resize(args.w, args.h)
    win.show()

    todo = [args.page] if args.page >= 0 else list(range(len(NAMES)))

    def step(i=[0]):
        if i[0] >= len(todo):
            app.quit()
            return
        k = todo[i[0]]
        win.nav_group.button(k).setChecked(True)
        win._on_nav_changed(k)
        app.processEvents()
        path = os.path.join(OUT, "%d_%s.png" % (k, NAMES[k]))
        win.grab().save(path)
        print("saved", path)
        i[0] += 1
        QTimer.singleShot(250, step)

    QTimer.singleShot(900, step)
    app.exec_()
    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
