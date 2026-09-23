# -*- coding: utf-8 -*-
"""端到端验收：连板子 TCP 9000，读若干帧 JSON，检查类别/置信度是否合理。

用法: python _e2e_check.py [ip] [port] [n_frames]
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import json
import socket
import sys
import time
from collections import Counter

import board_env
IP = sys.argv[1] if len(sys.argv) > 1 else (board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0])
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9000
N = int(sys.argv[3]) if len(sys.argv) > 3 else 30


def main():
    s = socket.create_connection((IP, PORT), timeout=8)
    print("已连接 %s:%d" % (IP, PORT))
    s.settimeout(10)
    buf = b""
    frames, stats_seen = 0, 0
    cls_counter = Counter()
    confs = []
    t0 = time.time()
    try:
        while frames < N and time.time() - t0 < 40:
            data = s.recv(65536)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line.decode("utf-8", errors="replace"))
                except Exception:
                    continue
                if obj.get("type") == "stats":
                    stats_seen += 1
                    continue
                frames += 1
                for d in obj.get("defects", []):
                    cls_counter[d["cls"]] += 1
                    confs.append(d["conf"])
                if frames <= 8:
                    print("  frame=%-4s ok=%-5s defects=%s infer_ms=%s src=%s" % (
                        obj.get("frame"), obj.get("ok"),
                        [(d["cls"], d["conf"]) for d in obj.get("defects", [])],
                        obj.get("infer_ms"), obj.get("src")))
                if frames >= N:
                    break
    finally:
        s.close()

    dt = time.time() - t0
    print("-" * 60)
    print("收到 %d 帧检测结果 + %d 条状态，用时 %.1fs (%.1f fps)" %
          (frames, stats_seen, dt, frames / max(dt, 1e-6)))
    print("类别分布:", dict(cls_counter))
    if confs:
        print("置信度 min=%.3f max=%.3f 均值=%.3f  (共 %d 个框)" %
              (min(confs), max(confs), sum(confs) / len(confs), len(confs)))


if __name__ == "__main__":
    main()
