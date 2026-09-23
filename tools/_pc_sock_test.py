# -*- coding: utf-8 -*-
"""纯 socket 对照实验：绕开 PyQt/tcp_bridge，直接连板端 9000 连发 5 次 next。

用途：区分「板端/网络问题」与「上位机 bridge 或定时器问题」。
  板端能推 ~5 帧 → 板端与网络正常，问题在上位机侧
  板端只推 1~2 帧 → 板端或链路问题
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import socket
import sys
import time

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000
N = 5

s = socket.create_connection((HOST, PORT), timeout=5)
print("已连接 %s:%d" % (HOST, PORT), flush=True)

received = 0
t0 = time.time()


def drain():
    """非阻塞读数，统计收到的帧数"""
    global received
    s.settimeout(0.2)
    try:
        while True:
            data = s.recv(65536)
            if not data:
                return False
            if b'"defects"' in data or b'"src"' in data:
                received += data.count(b'"src"')
    except socket.timeout:
        return True
    except Exception as e:
        print("recv 异常:", e, flush=True)
        return False


drain()
print("接入后已收帧: %d（预期 1 帧补推）" % received, flush=True)

for i in range(N):
    n = s.sendall(b'{"cmd":"next"}\n')
    print("发送 next #%d  sendall=%r" % (i + 1, n), flush=True)
    time.sleep(1.0)
    drain()
    print("   累计收到帧: %d" % received, flush=True)

s.close()
print("\n合计收到帧: %d（接入补推 1 + 期望 %d）" % (received, N), flush=True)
print("判定: %s" % ("板端/网络正常" if received >= N else "板端或链路异常"), flush=True)
