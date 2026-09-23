# -*- coding: utf-8 -*-
"""验证板端 step 模式：连接 → 发 next → 逐张收结果。"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import socket, json

s = socket.create_connection((__import__('board_env').get('BOARD_IP', '') or __import__('board_env').fallback_ips()[0], 9000), timeout=5)
s.settimeout(3)
buf = b""


def read_one():
    """按行读取一个完整 JSON 对象（累积缓冲，处理跨 recv 的 base64 长行）。"""
    global buf
    while True:
        if b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line.startswith(b"{"):
                return json.loads(line.decode("utf-8", "ignore"))
            continue
        chunk = s.recv(65536)
        if not chunk:
            return None
        buf += chunk


# 首屏 stats
first = read_one()
print("首屏 type=%s" % first.get("type"))

for i in range(3):
    s.sendall(b'{"cmd":"next"}\n')
    # step 模式：next 后会先来一张结果，可能夹带 stats，跳过 stats 取结果
    obj = read_one()
    while obj and obj.get("type") == "stats":
        obj = read_one()
    if obj is None:
        print("第%d张: 无结果" % (i + 1))
        continue
    defects = obj.get("defects", [])
    top = max((d["conf"] for d in defects), default=0.0)
    print("第%d张: frame=%s src=%-22s ok=%s 缺陷=%d top_conf=%.3f" % (
        i + 1, obj.get("frame"), obj.get("src"), obj.get("ok"),
        len(defects), top))

# 验证 reset
s.sendall(b'{"cmd":"reset"}\n')
import time
time.sleep(0.5)
s.sendall(b'{"cmd":"next"}\n')
obj = read_one()
while obj and obj.get("type") == "stats":
    obj = read_one()
print("reset后第1张: frame=%s src=%s" % (obj.get("frame"), obj.get("src")))

s.close()
print("done")
