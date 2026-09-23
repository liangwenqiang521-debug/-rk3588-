# -*- coding: utf-8 -*-
"""诊断：step 模式下上位机心跳 cmd=next 是否真的驱动板端推帧。

区分两种故障：
  A. 定时器没启动（_ensure_step_timer 没被调用 / 提前 return）
  B. 定时器在跑但板端收不到或没处理 cmd=next
"""
import sys
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

import main as m

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000

app = QApplication(sys.argv)
win = m.MainWindow()
det = win.pages[0]

det.cb_edge_mode.setCurrentIndex(1)
det.ed_edge_host.setText(HOST)
det.ed_edge_port.setText(str(PORT))

print("连接 %s:%d ..." % (HOST, PORT))
det._connect_edge(silent=True)

st = {"phase": 0, "t0": 0.0}
BOARD_LOG = []


def board_frames():
    """读板端日志里 step frame 的行数（作为板端是否推帧的独立证据）"""
    try:
        sys.path.insert(0, ".")
        import board_ssh
        c = board_ssh.connect(verbose=False)
        out, err, code = board_ssh.run(
            c, "grep -c 'step frame' /root/rknn/server_cascade.log")
        c.close()
        return int(str(out).strip().splitlines()[-1])
    except Exception:
        return -1


def phase0_connect():
    if det.bridge is not None and det.bridge.isRunning():
        print("[1] 已连接")
        print("    启动前 _edge_step_timer = %s" % getattr(det, "_edge_step_timer", None))
        det._start()
        t = getattr(det, "_edge_step_timer", None)
        print("[2] _start() 后 _edge_step_timer = %s  active=%s"
              % (t, (t.isActive() if t is not None else "N/A")))
        print("    interval = %s ms" % (t.interval() if t is not None else "N/A"))
        print("    _edge_detect_enabled = %s" % det._edge_detect_enabled)
        st["phase"] = 1
        st["t0"] = time.time()
        st["f0"] = board_frames()


def phase1_watch():
    """观察 10 秒：心跳是否自动驱动统计"""
    el = time.time() - st["t0"]
    if el >= 10:
        f1 = board_frames()
        print("[3] 10 秒自动观察结束: total=%d  板端 step frame %s -> %s（+%s）"
              % (det.total, st["f0"], f1, (f1 - st["f0"]) if f1 >= 0 else "?"))
        st["phase"] = 2
        st["t1"] = time.time()
        st["f1"] = f1
        st["base"] = det.total
        st["n"] = 0


def phase2_manual():
    """手动调 _edge_step_tick() 3 次（间隔 1.2s），验证单发 next 能否推帧"""
    el = time.time() - st["t1"]
    want = int(el / 1.2)
    if want > st["n"] and st["n"] < 3:
        st["n"] += 1
        br = det.bridge
        print("    手动 tick #%d" % st["n"])
        print("      bridge      = %s  isRunning=%s"
              % (br, (br.isRunning() if br is not None else None)))
        print("      bridge.sock = %s" % getattr(br, "sock", "N/A"))
        r = br.send_cmd("next") if br is not None else None
        print("      send_cmd('next') -> %r" % r)
    if el >= 5:
        f2 = board_frames()
        print("[4] 手动 tick %d 次后: total %d -> %d（+%d）  板端 frame %s -> %s（+%s）"
              % (st["n"], st["base"], det.total, det.total - st["base"],
                 st["f1"], f2, (f2 - st["f1"]) if f2 >= 0 else "?"))
        finish()


def finish():
    print("\n" + "=" * 60)
    print("结论提示：")
    print("  - [3] 板端 +0 且 total 不增  → 心跳没驱动（查定时器）")
    print("  - [4] 手动 tick 能 +1        → 定时器未启/未触发（A 类故障）")
    print("  - [4] 手动 tick 也 +0        → cmd=next 链路不通（B 类故障）")
    print("=" * 60)
    if det.bridge:
        try:
            det.bridge.stop()
        except Exception:
            pass
    app.quit()


def poll():
    try:
        if st["phase"] == 0:
            phase0_connect()
        elif st["phase"] == 1:
            phase1_watch()
        elif st["phase"] == 2:
            phase2_manual()
    except Exception as e:
        print("[poll 异常]", e)


timer = QTimer()
timer.timeout.connect(poll)
timer.start(500)
QTimer.singleShot(90000, finish)
app.exec_()
