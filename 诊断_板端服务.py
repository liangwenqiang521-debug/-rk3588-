# -*- coding: utf-8 -*-
"""探测板端 9000 端口：连上后读取若干行 JSON，验证推理服务真实可用。"""
import json
import socket
import sys
import time

import board_env
HOST = sys.argv[1] if len(sys.argv) > 1 else (board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0])
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9000

print("连接 %s:%d ..." % (HOST, PORT))
try:
    s = socket.create_connection((HOST, PORT), timeout=5)
except Exception as e:
    print("[FAIL] 连接失败:", e)
    sys.exit(1)
print("[OK] 已连接\n")

s.settimeout(10)
buf = b""
got = 0
t0 = time.time()
try:
    while got < 5 and time.time() - t0 < 15:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            print("(等待超时)")
            break
        if not chunk:
            print("(对端关闭)")
            break
        buf += chunk
        while b"\n" in buf and got < 5:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8", "ignore"))
            except Exception:
                print("[非JSON]", line[:120])
                continue
            got += 1
            if obj.get("type") == "stats":
                print("--- 帧 #%d  [NPU 状态] ---" % got)
                for k, v in obj.items():
                    if k != "type":
                        print("   %-14s = %s" % (k, str(v)[:90]))
            else:
                print("--- 帧 #%d  [检测结果] ---" % got)
                print("   frame      = %s" % obj.get("frame"))
                print("   ok         = %s" % obj.get("ok"))
                print("   infer_ms   = %s" % obj.get("infer_ms"))
                print("   w x h      = %s x %s" % (obj.get("w"), obj.get("h")))
                d = obj.get("defects") or []
                print("   defects(%d) :" % len(d))
                for it in d[:6]:
                    print("      %-10s conf=%.3f  box=(%s,%s,%s,%s)" % (
                        it.get("cls"), float(it.get("conf", 0)),
                        it.get("x1"), it.get("y1"), it.get("x2"), it.get("y2")))
                for k in ("img", "image", "frame_b64", "b64", "jpg", "jpeg"):
                    if k in obj:
                        print("   %s: %d bytes (base64)" % (k, len(str(obj[k]))))
                print("   其他字段: %s" % [k for k in obj.keys()])
            print()
except KeyboardInterrupt:
    pass
finally:
    try:
        s.close()
    except Exception:
        pass

if got == 0:
    print("[结论] TCP 通, 但 15 秒内未收到任何数据 -> 板端服务可能在跑但未产出帧")
else:
    print("[结论] 推理服务工作正常, 共收到 %d 帧" % got)
