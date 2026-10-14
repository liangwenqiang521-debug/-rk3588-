# -*- coding: utf-8 -*-
"""断流自愈回归测试（10-09 加）：验证"检测中断后卡住、然后停止检测"的修复。

覆盖：
  A 自适应节拍：上一帧未回时不再重复发 cmd=next
  B 收到结果帧后恢复发帧，并刷新断流计时
  C 看门狗软踢：6s 无帧且请求未回 → 重发 next
  D 看门狗硬恢复：20s 无帧 → 断开并重连
  E 运行中掉线 → 置空 bridge + 退避重连；主动断开则取消重连
  F TCP 桥接发送非阻塞（GUI 主线程只入队）

运行：python tests/_test_edge_recovery.py   （须真实平台，勿用 offscreen）
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import sys
import time

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception as e:
    print("[warn] 预加载 infer/torch:", e)

from PyQt5.QtWidgets import QApplication

import main as M

_results = []


def report(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


class FakeBridge:
    """模拟 TCP 桥接：可控制"是否在运行"，并记录 next 次数。"""

    def __init__(self, running=True):
        self.running = running
        self.n = 0
        self._dropped = 0
        self.stopped = False

    def isRunning(self):
        return self.running

    def send_cmd(self, cmd):
        if cmd == "next":
            self.n += 1
        return True

    def send_detect_image(self, data, name="x"):
        self.n += 1
        return True

    def ack(self):
        pass

    def stop(self):
        self.stopped = True
        self.running = False


app = QApplication(sys.argv)
win = M.MainWindow()
det = win.pages[0]

# 隔离：不连板、不走"送检照片"分支（直接测 cmd=next 节拍）
det._edge_step_timer = None
det._photo_path = ""
det._photo_sent = True

# ---------------- A/B 自适应节拍 ----------------
try:
    fb = FakeBridge()
    det.bridge = fb
    det._edge_detect_enabled = True
    det._awaiting_frame = False
    det._last_frame_ts = time.time()

    det._edge_step_tick()
    n1 = fb.n
    det._edge_step_tick()          # 上一帧未回 → 不应再发
    det._edge_step_tick()
    ok_a = (n1 == 1 and fb.n == 1 and det._awaiting_frame is True)
    report("A 自适应节拍：未回帧不重复发", ok_a,
           "next=%d awaiting=%s" % (fb.n, det._awaiting_frame))

    # 模拟回帧（暂时关检测以跳过重 IO 路径，只验证标志刷新）
    det._edge_detect_enabled = False
    det._on_edge_result({"frame": 1, "ok": True, "defects": [],
                         "infer_ms": 5.0, "w": 640, "h": 640})
    det._edge_detect_enabled = True
    cleared = (det._awaiting_frame is False)
    fresh = (time.time() - det._last_frame_ts) < 1.0
    det._edge_step_tick()
    resent = (fb.n == 2)
    ok_b = cleared and fresh and resent
    report("B 回帧后恢复发帧 + 刷新计时", ok_b,
           "回帧清标志=%s 计时刷新=%s 再发成功=%s next总数=%d"
           % (cleared, fresh, resent, fb.n))
except Exception as e:
    report("A/B 自适应节拍", False, repr(e))

# ---------------- C 看门狗软踢 ----------------
try:
    fb2 = FakeBridge()
    det.bridge = fb2
    det._edge_detect_enabled = True
    det._awaiting_frame = True
    det._awaiting_since = time.time() - 7.0
    det._last_frame_ts = time.time() - 7.0
    det._edge_watchdog()
    report("C 看门狗软踢（6s 无帧重发 next）", fb2.n == 1, "重发次数=%d" % fb2.n)
except Exception as e:
    report("C 看门狗软踢", False, repr(e))

# ---------------- D 看门狗硬恢复 ----------------
try:
    calls = {"connect": 0}
    det.bridge = FakeBridge()
    det._edge_detect_enabled = True
    det._last_frame_ts = time.time() - 25.0
    _orig_connect = det._connect_edge
    det._connect_edge = lambda silent=False: calls.__setitem__("connect", calls["connect"] + 1)
    det._edge_watchdog()
    det._connect_edge = _orig_connect
    ok_d = (calls["connect"] == 1 and det.bridge is None)
    report("D 看门狗硬恢复（20s 无帧断开重连）", ok_d,
           "重连调用=%d bridge已置空=%s" % (calls["connect"], det.bridge is None))
except Exception as e:
    report("D 看门狗硬恢复", False, repr(e))

# ---------------- E 掉线自动重连 / 主动断开取消 ----------------
try:
    # E1 运行中掉线（线程已退出）→ 置空 bridge + 排重连
    fb3 = FakeBridge(running=True)
    det.bridge = fb3
    det._edge_detect_enabled = True
    det._edge_was_connected = True
    det._reconnect_left = 6
    det._reconnect_step = 0
    fb3.running = False                      # 模拟桥接线程已退出
    det._on_edge_connected(False, "已断开 169.254.x.x:9000")
    e1 = (det.bridge is None and det._reconnect_left == 5)

    # E2 主动断开 → 取消重连意图
    det._reconnect_left = 6
    det.bridge = FakeBridge()
    det._stop_edge()
    e2 = (det._reconnect_left == 0 and det._auto_left == 0)

    # E3 退避触发点：仍"想"保持链路时才真连
    cnt = {"c": 0}
    det._reconnect_left = 3
    det._edge_detect_enabled = True
    _oc = det._connect_edge
    det._connect_edge = lambda silent=False: cnt.__setitem__("c", cnt["c"] + 1)
    det._reconnect_tick()
    det._connect_edge = _oc
    e3 = (cnt["c"] == 1)

    ok_e = e1 and e2 and e3
    report("E 掉线自动重连 / 主动断开取消", ok_e,
           "掉线置空并排重连=%s 主动断开清零=%s 退避触发重连=%s" % (e1, e2, e3))
except Exception as e:
    report("E 掉线自动重连", False, repr(e))

# ---------------- F TCP 桥接发送非阻塞 ----------------
try:
    from tcp_bridge import BoardTcpBridge
    br = BoardTcpBridge("127.0.0.1", 1)
    f1 = (br.send_cmd("next") is False)         # 未连接 → False，且不抛异常
    br.sock = object()                          # 伪造已连接（不真发）
    br._running = True
    f2 = (br.send_cmd("next") is True and br._out_q.qsize() == 1)
    f3 = (br.send_detect_image(b"\xff\xd8\xff", "a.jpg") is True and br._out_q.qsize() == 2)
    ok_f = f1 and f2 and f3
    report("F TCP 桥接发送只入队（非阻塞）", ok_f,
           "未连接=%s 入队cmd=%s 入队图片=%s" % (f1, f2, f3))
except Exception as e:
    report("F TCP 桥接发送非阻塞", False, repr(e))

# ---------------- G 后台发送线程真实送达（真 socket） ----------------
try:
    import json as _json
    import socket as _sk
    import threading as _th

    from PyQt5.QtCore import QThread as _QT
    from tcp_bridge import BoardTcpBridge

    _port = 9411
    _got = []

    def _serve():
        srv = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
        srv.setsockopt(_sk.SOL_SOCKET, _sk.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", _port))
        srv.listen(1)
        c, _ = srv.accept()
        buf = b""
        deadline = time.time() + 8
        while time.time() < deadline and len(_got) < 2:
            try:
                chunk = c.recv(4096)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                ln, buf = buf.split(b"\n", 1)
                ln = ln.strip()
                if ln:
                    _got.append(_json.loads(ln.decode("utf-8", "ignore")))
        try:
            c.close()
            srv.close()
        except Exception:
            pass

    _th.Thread(target=_serve, daemon=True).start()
    time.sleep(0.3)
    import base64 as _b64
    _payload = b"\xff\xd8\xff\xe0fakejpg"
    _want_len = len(_b64.b64encode(_payload))   # 服务端收到的应为同一张图的 base64

    _br = BoardTcpBridge("127.0.0.1", _port)
    _br.start()
    _QT.msleep(600)
    g1 = _br.send_cmd("next")
    g2 = _br.send_detect_image(_payload, "t.jpg")
    _QT.msleep(1200)
    _br.stop()

    _kinds = [g.get("cmd") for g in _got]
    _img_len = len(_got[1].get("img", "")) if len(_got) > 1 else 0
    ok_g = (g1 and g2 and _kinds == ["next", "detect_img"] and _img_len == _want_len)
    report("G 后台发送线程真实送达（真 socket）", ok_g,
           "入队=%s/%s 服务端收到=%s 图片b64长度=%d(期望%d)"
           % (g1, g2, _kinds, _img_len, _want_len))
except Exception as e:
    report("G 后台发送线程真实送达", False, repr(e))

print("\n" + "=" * 58)
bad = [n for n, o in _results if not o]
print("结果: %d 项失败 / 共 %d 项" % (len(bad), len(_results)))
for n in bad:
    print("  失败:", n)
print("=" * 58)
sys.exit(1 if bad else 0)
