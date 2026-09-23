# -*- coding: utf-8 -*-
"""端到端验证「照片送检」协议：PC 读本地 NEU 图片 → detect_img 发板端 → 收结果。

校验点：
  1. 收到 mode=img 的结果帧
  2. w/h = 原图尺寸（非 640 letterbox）
  3. 框坐标在原图范围内
  4. img_b64 可解码且与原图尺寸一致
  5. cmd=next 样本路径仍正常
"""
import socket, json, base64, sys, time

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = board_env.get_int("BOARD_STREAM_PORT", 9000)
IMG_PATH = sys.argv[1] if len(sys.argv) > 1 else "图片/scratches/scratches_112.jpg"

s = socket.create_connection((HOST, PORT), timeout=5)
s.settimeout(10)
buf = b""

def read_msg(timeout=10):
    global buf
    t0 = time.time()
    while b"\n" not in buf:
        if time.time() - t0 > timeout:
            return None
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            return None
        if not chunk:
            return None
        buf += chunk
    line, buf = buf.split(b"\n", 1)
    line = line.strip()
    if not line:
        return read_msg(timeout=max(0.1, timeout - (time.time() - t0)))
    try:
        return json.loads(line.decode("utf-8", "ignore"))
    except Exception:
        return read_msg(timeout=max(0.1, timeout - (time.time() - t0)))

# 1) 读首屏 stats
m = read_msg(6)
print("首屏:", "stats OK" if m and m.get("type") == "stats" else m)

# 2) 送检照片
data = open(IMG_PATH, "rb").read()
import struct
# 用 Pillow 不一定有，直接用 cv2 读尺寸做对照
import cv2
import numpy as np
img = cv2.imdecode(np.fromfile(IMG_PATH, dtype=np.uint8), cv2.IMREAD_COLOR)
oh, ow = img.shape[:2]
t0 = time.time()
obj = {"cmd": "detect_img", "name": IMG_PATH.replace("\\", "/").split("/")[-1],
       "img": base64.b64encode(data).decode("ascii")}
s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
print("已发送送检请求: %s (%dx%d, %.1fKB)" % (obj["name"], ow, oh, len(data) / 1024))

# 3) 等结果（跳过 stats）
result = None
deadline = time.time() + 20
while time.time() < deadline:
    m = read_msg(20)
    if m is None:
        break
    if m.get("type") == "stats":
        continue
    result = m
    break
dt = time.time() - t0
assert result is not None, "20s 内未收到送检结果"
assert result.get("mode") == "img", "结果不是送检回传: %s" % {k: result.get(k) for k in ("frame", "src")}
print("收到送检结果 (往返 %.2fs, 推理 %.1fms):" % (dt, result.get("infer_ms", 0)))
print("  src=%s  w=%d h=%d (期望 %dx%d)  ok=%s" %
      (result.get("src"), result.get("w"), result.get("h"), ow, oh, result.get("ok")))
assert result.get("w") == ow and result.get("h") == oh, "尺寸不是原图"
defs = result.get("defects", [])
print("  缺陷 %d 个:" % len(defs))
for d in defs[:5]:
    print("    %s %.4f  (%.0f,%.0f)-(%.0f,%.0f)" % (d["cls"], d["conf"], d["x1"], d["y1"], d["x2"], d["y2"]))
    assert 0 <= d["x1"] <= ow and 0 <= d["x2"] <= ow, "x 坐标越界"
    assert 0 <= d["y1"] <= oh and 0 <= d["y2"] <= oh, "y 坐标越界"
raw = base64.b64decode(result.get("img_b64") or b"")
back = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
assert back is not None and back.shape[1] == ow and back.shape[0] == oh, "回传图与原图尺寸不符"
print("  回传图解码 OK (%dx%d, %.1fKB)" % (back.shape[1], back.shape[0], len(raw) / 1024))

# 4) cmd=next 样本路径仍正常
s.sendall(b'{"cmd":"next"}\n')
m2 = None
deadline = time.time() + 15
while time.time() < deadline:
    m = read_msg(15)
    if m is None:
        break
    if m.get("type") == "stats":
        continue
    m2 = m
    break
assert m2 is not None and m2.get("mode") != "img", "next 未返回样本帧"
print("next 样本帧 OK: %s 缺陷 %d 个 %dx%d" %
      (m2.get("src"), len(m2.get("defects", [])), m2.get("w"), m2.get("h")))
s.close()
print("ALL PASS")
