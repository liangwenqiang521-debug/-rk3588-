# -*- coding: utf-8 -*-
"""step 模式浸泡测试：连板后连续检测 60 秒，确认不会中途断流。

背景：09-21 修的根因是板端 0.3s 发送超时把上位机当死连接踢掉，
表现为"推一两帧后再也不动"。短测（15s）可能碰巧通过，
所以这里用 60 秒 + 断流检测（连续 8 秒无新增即判定断流）。
"""
import sys
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

import main as m

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000
SOAK_SEC = 60
STALL_SEC = 8          # 连续多久没新增算断流

app = QApplication(sys.argv)
win = m.MainWindow()
det = win.pages[0]

det.cb_edge_mode.setCurrentIndex(1)
det.ed_edge_host.setText(HOST)
det.ed_edge_port.setText(str(PORT))

print("连接 %s:%d ..." % (HOST, PORT))
det._connect_edge(silent=True)

st = {"started": False, "t0": 0.0, "prev": 0, "last_grow": 0.0,
      "stalls": [], "samples": []}


def poll():
    if not st["started"]:
        if det.bridge is not None and det.bridge.isRunning():
            det._start()
            st["started"] = True
            st["t0"] = time.time()
            st["last_grow"] = st["t0"]
            print("[启动] 开始检测，浸泡 %d 秒" % SOAK_SEC, flush=True)
        return

    el = time.time() - st["t0"]
    cur = det.total
    if cur > st["prev"]:
        st["prev"] = cur
        st["last_grow"] = time.time()
    else:
        gap = time.time() - st["last_grow"]
        if gap >= STALL_SEC and not st.get("stall_marked"):
            st["stall_marked"] = True
            st["stalls"].append(round(el, 1))
            print("  !! 断流 %.0f 秒无新增（t=%.0fs, total=%d）" % (gap, el, cur),
                  flush=True)
        if gap < STALL_SEC:
            st["stall_marked"] = False

    if int(el) % 10 == 0 and st.get("_last") != int(el):
        st["_last"] = int(el)
        st["samples"].append((int(el), cur))
        print("  t=%2ds  total=%d  OK=%d  NG=%d" % (el, cur, det.ok, det.ng),
              flush=True)

    if el >= SOAK_SEC:
        report()


def report():
    el = time.time() - st["t0"]
    total = det.total
    print("\n" + "=" * 62)
    print("浸泡 %.0f 秒：共检测 %d 件（OK %d / NG %d）" % (el, total, det.ok, det.ng))
    print("平均节拍: %.2f 件/秒" % (total / el if el else 0))
    print("断流次数: %d %s" % (len(st["stalls"]), st["stalls"] if st["stalls"] else ""))
    ok = (total >= SOAK_SEC * 0.8) and (not st["stalls"])
    print("结论: %s" % ("✅ step 模式长跑稳定，无断流" if ok else "❌ 仍有断流/掉线"))
    print("=" * 62)
    if det.bridge:
        try:
            det.bridge.stop()
        except Exception:
            pass
    app.quit()


timer = QTimer()
timer.timeout.connect(poll)
timer.start(500)
QTimer.singleShot(180000, report)
app.exec_()
