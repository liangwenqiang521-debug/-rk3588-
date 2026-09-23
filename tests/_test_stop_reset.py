# -*- coding: utf-8 -*-
"""停止检测后画面复原 回归测试（offscreen）"""
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

# 屏蔽开机自动连接：板端实时流会覆盖测试注入的结果，干扰断言
import page_detect as PD
PD.DetectPage._auto_connect = lambda self: None
PD.DetectPage._auto_retry = lambda self: None

import main as M
win = M.MainWindow()
dp = win.pages[0]

fails = []
def check(name, ok, detail=""):
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    if not ok:
        fails.append(name)

# ---- 1) 模拟一次 NG 边缘结果（等同板端回传 crazing 0.58）----
dp._edge_detect_enabled = True   # 连板后默认仅预览，测试需打开检测开关
obj = {"frame": 1, "ok": False, "w": 640, "h": 480,
       "defects": [{"cls": "crazing", "conf": 0.58,
                    "x1": 100, "y1": 80, "x2": 300, "y2": 220}],
       "infer_ms": 8.0}
dp._on_edge_result(obj)
app.processEvents()
check("停止前-画布有NG结果",
      dp.canvas.result == "NG" and len(dp.canvas._real_defects) == 1,
      "result=%r defects=%d" % (dp.canvas.result, len(dp.canvas._real_defects)))
check("停止前-右侧面板显示NG", dp.big_result.text() == "NG")

# ---- 2) 停止检测 → 应全部复原 ----
dp._stop()
app.processEvents()
check("停止后-画布角标清空", dp.canvas.result is None,
      "result=%r" % (dp.canvas.result,))
check("停止后-检测框清空", len(dp.canvas._real_defects) == 0)
check("停止后-右侧面板回待机",
      dp.big_result.text() == "--" and dp.big_conf.text() == "置信度: --",
      "big=%r conf=%r" % (dp.big_result.text(), dp.big_conf.text()))
check("停止后-闪烁边框复位", dp.canvas._flash is False)
check("停止后-按钮状态复位",
      dp.btn_start.isEnabled() and not dp.btn_stop.isEnabled())

# ---- 3) OK 结果 → 停止，同样复原 ----
obj2 = {"frame": 2, "ok": True, "w": 640, "h": 480,
        "defects": [], "infer_ms": 7.0}
dp._on_edge_result(obj2)
app.processEvents()
check("OK结果-画布OK", dp.canvas.result == "OK")
dp._stop()
app.processEvents()
check("OK后停止-复原",
      dp.canvas.result is None and dp.big_result.text() == "--")

# ---- 4) 待机态离屏渲染不崩溃（paintEvent result=None 分支）----
pix = dp.canvas.grab()
check("待机态渲染", not pix.isNull(), "%dx%d" % (pix.width(), pix.height()))

# ---- 5) 复原后再次检测仍正常（角标/框能重新出现）----
dp._on_edge_result(obj)
app.processEvents()
check("复原后可重新出结果",
      dp.canvas.result == "NG" and len(dp.canvas._real_defects) == 1)
dp._stop()
app.processEvents()

print("")
if fails:
    print("失败 %d 项: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("全部通过（停止检测画面复原）")
sys.exit(0)
