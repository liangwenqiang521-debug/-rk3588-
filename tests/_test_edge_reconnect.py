# -*- coding: utf-8 -*-
"""断流自愈端到端验证（需真实板端在线）：模拟链路中断 → 自动重连 → 检测续跑。

流程：连板 → 开始检测 → 等到有 3 件结果 → **强行掐断当前 socket**（模拟断线）
      → 断言 HMI 在若干秒内自动建起新连接，且计数继续增长。

这是"检测中断后卡住、然后停止检测"这个 bug 的直接验收用例。
运行：python tests/_test_edge_reconnect.py   （可用 BOARD_IP 环境变量覆盖板端地址）
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import socket
import sys
import time

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
HOST = os.environ.get("BOARD_IP") or board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000

app = QApplication(sys.argv)
win = m.MainWindow()
det = win.pages[0]

det.cb_edge_mode.setCurrentIndex(1)
det.ed_edge_host.setText(HOST)
det.ed_edge_port.setText(str(PORT))
print("连接 %s:%d ..." % (HOST, PORT))
det._connect_edge(silent=True)

st = {
    "phase": "wait_conn",
    "t0": time.time(),
    "old_br": None,
    "c1": 0,
    "t_cut": 0.0,
    "t_recover": 0.0,
    "c2": 0,
}
FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("[FAIL] %s" % msg, flush=True)


def tick():
    el = time.time() - st["t0"]

    if st["phase"] == "wait_conn":
        if det.bridge is not None and det.bridge.isRunning():
            print("[OK] 已连接，开始检测")
            det._start()
            st["phase"] = "warmup"
            st["t0"] = time.time()
        elif el > 20:
            fail("20s 内未能连上板端 %s:%d" % (HOST, PORT))
            finish()
        return

    if st["phase"] == "warmup":
        if det.total >= 3:
            st["c1"] = det.total
            st["old_br"] = det.bridge
            br = det.bridge
            # 强行掐断 socket，模拟链路静默中断（等价网线松脱 / 板端进程重启）
            try:
                br.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                br.sock.close()
            except Exception:
                pass
            print("[模拟断线] 已掐断链路（此时累计 %d 件），等待自动重连..." % det.total, flush=True)
            st["phase"] = "wait_recover"
            st["t_cut"] = time.time()
        elif el > 30:
            fail("30s 内未产出 3 件结果（累计 %d）" % det.total)
            finish()
        return

    if st["phase"] == "wait_recover":
        gap = time.time() - st["t_cut"]
        br = det.bridge
        if br is not None and br is not st["old_br"] and br.isRunning():
            st["t_recover"] = time.time()
            print("[OK] 断线后 %.1fs 自动重连成功（新 bridge）" % gap, flush=True)
            st["phase"] = "wait_resume"
            st["t0"] = time.time()
        elif gap > 45:
            fail("断线后 45s 未自动重连（bridge=%r）" % (type(br).__name__,))
            finish()
        return

    if st["phase"] == "wait_resume":
        if det.total > st["c1"]:
            st["c2"] = det.total
            print("[OK] 重连后检测已续跑：断线前 %d 件 → 现在 %d 件" % (st["c1"], st["c2"]), flush=True)
            finish()
        elif time.time() - st["t0"] > 30:
            fail("重连后 30s 计数未恢复（断线前 %d，现 %d）" % (st["c1"], det.total))
            finish()


def finish():
    global _done
    if getattr(finish, "done", False):
        return
    finish.done = True
    try:
        det._stop()
    except Exception:
        pass
    print("\n" + "=" * 58)
    if FAILS:
        print("结果: %d 项失败" % len(FAILS))
        for f in FAILS:
            print("  -", f)
    else:
        print("结果: 全过 —— 断流后自动重连、检测续跑")
        print("      断线前累计 %d 件；重连耗时 %.1fs；重连后累计 %d 件"
              % (st["c1"], st["t_recover"] - st["t_cut"], st["c2"]))
    print("=" * 58)
    try:
        if det.bridge:
            det.bridge.stop()
    except Exception:
        pass
    app.exit(1 if FAILS else 0)


_g_timer = QTimer()
_g_timer.timeout.connect(tick)
_g_timer.start(500)
QTimer.singleShot(150000, finish)

rc = app.exec_()
sys.exit(rc)
