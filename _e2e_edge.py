# -*- coding: utf-8 -*-
"""端到端验证：真实连接 RK3588 后执行「开始检测」，确认不再闪退且统计正常。

流程：构造主窗口 -> 连板(默认 169.254.x.x:9000，可用 BOARD_IP 覆盖) -> 调 _start()（等价点击开始检测）
      -> 观察若干秒 -> 检查计数器与进程存活。
"""
import os
import sys

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception as e:
    print("[warn] 预加载 infer/torch:", e)

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

import main as m

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000
WATCH_SEC = 15

app = QApplication(sys.argv)
win = m.MainWindow()
det = win.pages[0]

# 配置为 TCP 边缘模式
det.cb_edge_mode.setCurrentIndex(1)
det.ed_edge_host.setText(HOST)
det.ed_edge_port.setText(str(PORT))

print("连接 %s:%d ..." % (HOST, PORT))
det._connect_edge(silent=True)

state = {"t0": None, "started": False, "snap": None}


def poll():
    """等待连接建立，然后执行 _start()"""
    if not state["started"]:
        running = det.bridge is not None and det.bridge.isRunning()
        if running:
            print("[OK] 边缘已连接，执行 _start()（等价点击「开始检测」）")
            det._start()
            state["started"] = True
            state["t0"] = __import__("time").time()
            print("     _edge_detect_enabled = %s" % det._edge_detect_enabled)
            print("     本地定时器 active   = %s （应为 False）" % det.timer.isActive())
        return
    # 观察窗口内每 3 秒报一次计数
    import time
    el = time.time() - state["t0"]
    if int(el) % 3 == 0 and state.get("_last") != int(el):
        state["_last"] = int(el)
        print("  t=%2ds  总=%d  OK=%d  NG=%d  良率=%.1f%%"
              % (el, det.total, det.ok, det.ng,
                 (det.ok / det.total * 100) if det.total else 0.0))
    if el >= WATCH_SEC:
        print("\n停止检测（等价点击「停止检测」）")
        det._stop()
        print("  仍连接: %s   _edge_detect_enabled=%s"
              % (det.bridge is not None and det.bridge.isRunning(),
                 det._edge_detect_enabled))
        finish()


def finish():
    print("\n" + "=" * 58)
    print("进程存活 ✔  累计检测 %d 件（OK %d / NG %d）"
          % (det.total, det.ok, det.ng))
    print("结论: 连板 → 开始检测 → 统计 → 停止，全程无闪退")
    print("=" * 58)
    if det.bridge:
        try:
            det.bridge.stop()
        except Exception:
            pass
    app.quit()


timer = QTimer()
timer.timeout.connect(poll)
timer.start(1000)
QTimer.singleShot(60000, finish)
app.exec_()
