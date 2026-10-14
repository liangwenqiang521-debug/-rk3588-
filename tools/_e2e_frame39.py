# -*- coding: utf-8 -*-
"""抓取板端 39 类服务的完整帧 JSON（去掉 img_b64），确认类别名/索引来自 39 类表。"""
import json
import os
import socket
import sys
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import board_env

HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000

# 顺便带出上位机的 39 类表做交叉核对
sys.path.insert(0, _ROOT)
try:
    from infer import CLASSES_39
except Exception:
    CLASSES_39 = []

s = socket.create_connection((HOST, PORT), timeout=5)
s.settimeout(1.0)
print("已连接 %s:%d" % (HOST, PORT))


def read_frames(seconds=3.0):
    buf = b""
    t0 = time.time()
    out = []
    while time.time() - t0 < seconds:
        try:
            d = s.recv(65536)
            if not d:
                break
            buf += d
        except socket.timeout:
            continue
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                out.append(json.loads(line.decode("utf-8", "ignore")))
            except Exception:
                pass
    return out


frames = read_frames(2.0)
for i in range(3):
    s.sendall(b'{"cmd":"next"}\n')
    time.sleep(1.2)
    frames += read_frames(1.0)

s.close()

det = [f for f in frames if "defects" in f]
print("总帧 %d，检测帧 %d" % (len(frames), len(det)))
print("=" * 70)
for f in det[:6]:
    f2 = dict(f)
    f2.pop("img_b64", None)
    print(json.dumps(f2, ensure_ascii=False)[:400])
print("=" * 70)
# 核对类别名是否能在上位机 39 类表里找到
names = set()
for f in det:
    for d in f.get("defects", []):
        names.add(d.get("cls"))
print("出现过的类别:", sorted(names))
if CLASSES_39:
    unknown = [n for n in names if n not in CLASSES_39]
    print("上位机 CLASSES_39 未登记的名: %s" % (unknown or "无（全部匹配）"))
