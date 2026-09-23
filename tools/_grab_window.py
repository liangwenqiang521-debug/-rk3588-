# -*- coding: utf-8 -*-
"""抓取正在运行的上位机主窗口截图（纯 ctypes + PIL，无需 pywin32）。"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import ctypes
from ctypes import wintypes
import sys
import time

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()

TITLE_KEY = sys.argv[1] if len(sys.argv) > 1 else "缺陷检测"
OUT = sys.argv[2] if len(sys.argv) > 2 else "_win_shot.png"

found = []


def cb(hwnd, _):
    if not u32.IsWindowVisible(hwnd):
        return True
    n = u32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return True
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    if TITLE_KEY in buf.value:
        found.append((hwnd, buf.value))
    return True


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
u32.EnumWindows(WNDENUMPROC(cb), 0)

if not found:
    print("未找到标题含 %r 的可见窗口" % TITLE_KEY)
    sys.exit(1)

hwnd, title = found[0]
print("命中窗口: %r  hwnd=%s" % (title, hwnd))

try:
    u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    u32.SetForegroundWindow(hwnd)
except Exception:
    pass
time.sleep(1.0)

rect = wintypes.RECT()
u32.GetWindowRect(hwnd, ctypes.byref(rect))
x1, y1, x2, y2 = rect.left, rect.top, rect.right, rect.bottom
print("窗口区域: (%d,%d)-(%d,%d)  %dx%d" % (x1, y1, x2, y2, x2 - x1, y2 - y1))

from PIL import ImageGrab
img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
img.save(OUT)
print("已保存: %s  %s" % (OUT, img.size))
