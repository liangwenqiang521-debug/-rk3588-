# -*- coding: utf-8 -*-
"""轮询板端 42 张样本，统计 39 类覆盖情况。

step 模式：一次 cmd=next 对应一帧；节拍放慢 + 丢帧重试，跑满一整轮。
用法：  C:/Users/21191/.workbuddy/binaries/python/envs/default/Scripts/python.exe tools/_probe_samples39.py [帧数]
"""
import json
import os
import socket
import sys
import time
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import board_env  # noqa: E402

try:
    from infer import CLASSES_39
except Exception:
    CLASSES_39 = []

HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 55

s = socket.create_connection((HOST, 9000), timeout=5)
s.settimeout(0.2)
print("已连接 %s:9000，目标 %d 帧..." % (HOST, N))

buf = b""


def drain(seconds):
    """读空缓冲，返回解析出的帧列表。"""
    global buf
    out = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            d = s.recv(262144)
        except socket.timeout:
            d = b""
        if d:
            buf += d
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line.decode("utf-8", "ignore")))
            except Exception:
                pass
    return out


drain(1.5)   # 排掉接入补推

cls_counter = Counter()
ok = ng = fail = 0
lat = []
for i in range(N):
    got = None
    for attempt in range(3):
        s.sendall(b'{"cmd":"next"}\n')
        for f in drain(3.0):
            if "defects" in f:
                got = f
                break
        if got:
            break
        time.sleep(0.4)
    if not got:
        fail += 1
        continue
    dets = got.get("defects", [])
    lat.append(got.get("ms") or got.get("total_ms") or 0)
    if dets:
        ng += 1
        for d in dets:
            cls_counter[d.get("cls")] += 1
    else:
        ok += 1
    time.sleep(0.3)

s.close()

print("=" * 66)
print("收到检测帧 %d / 目标 %d（重试后仍失败 %d）" % (ok + ng, N, fail))
print("  有缺陷 NG : %d 帧" % ng)
print("  无缺陷 OK : %d 帧" % ok)
ls = sorted(x for x in lat if x)
if ls:
    print("  推理耗时   : min %.0f / 中位 %.0f / max %.0f ms"
          % (ls[0], ls[len(ls) // 2], ls[-1]))
print("-" * 66)
print("出现过的缺陷类别（%d / %d）:" % (len(cls_counter), len(CLASSES_39) or '?'))
for name, cnt in cls_counter.most_common():
    flag = '' if name in CLASSES_39 else '  <-- 不在 CLASSES_39!'
    print("  %-26s %d%s" % (name, cnt, flag))
if CLASSES_39:
    unknown = [n for n in cls_counter if n not in CLASSES_39]
    print("-" * 66)
    print("未登记类别:", unknown or "无（全部命中上位机 CLASSES_39）")
    miss = [c for c in CLASSES_39 if c not in cls_counter]
    print("本轮未出现的类别（%d）: %s" % (len(miss), ', '.join(miss) or '无'))
