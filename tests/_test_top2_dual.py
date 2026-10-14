# -*- coding: utf-8 -*-
"""top-2 双候选显示 回归测试（offscreen）

验证 page_detect._apply_real_result 里：
  1. 易混对（分差<0.15）→ main_type 显示 "A / B"
  2. 分差>=0.15 → 只显示单一 top1 类别
  3. 单缺陷 → 只显示该类别
  4. 三框取不同类次高 → 双候选
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

import page_detect as PD
PD.DetectPage._auto_connect = lambda self: None
PD.DetectPage._auto_retry = lambda self: None

import main as M
win = M.MainWindow()
dp = win.pages[0]

passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('PASS  %s' % name)
    else:
        failed += 1
        print('FAIL  %s  %s' % (name, detail))


def mk(name, conf, xyxy_px=(200, 200, 300, 300)):
    return {"name": name, "conf": conf, "xyxy_px": xyxy_px,
            "xyxy": [0.3, 0.3, 0.5, 0.5], "color": "#ff0000"}


def get_main_type():
    return dp.detail.item(2, 1).text() if dp.detail.item(2, 1) else ""


# 1) 易混对：scratches 0.86 / inclusion 0.82（分差 0.04）→ 双候选
dp._apply_real_result([mk("scratches", 0.86), mk("inclusion", 0.82)], True, 0.86, 0.01, False)
app.processEvents()
mt = get_main_type()
check("易混对→双候选", mt == "scratches / inclusion", mt)

# 2) 分差大：inclusion 0.90 / scratches 0.60（分差 0.30）→ 单类 inclusion
dp._apply_real_result([mk("inclusion", 0.90), mk("scratches", 0.60)], True, 0.90, 0.01, False)
app.processEvents()
mt = get_main_type()
check("分差大→单类", mt == "inclusion", mt)

# 3) 单缺陷：crazing 0.55 → 单类
dp._apply_real_result([mk("crazing", 0.55)], True, 0.55, 0.01, False)
app.processEvents()
mt = get_main_type()
check("单缺陷→单类", mt == "crazing", mt)

# 4) 三框：inclusion 0.88 / inclusion 0.82 / scratches 0.78 → 不同类次高 scratches(0.78)，分差 0.10 → 双候选
dp._apply_real_result([mk("inclusion", 0.88), mk("inclusion", 0.82), mk("scratches", 0.78)],
                      True, 0.88, 0.01, False)
app.processEvents()
mt = get_main_type()
check("三框取不同类次高→双候选", mt == "inclusion / scratches", mt)

# 5) 无缺陷 → "--"
dp._apply_real_result([], False, 0.0, 0.01, False)
app.processEvents()
mt = get_main_type()
check("无缺陷→--", mt == "--", mt)

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
