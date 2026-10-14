# -*- coding: utf-8 -*-
"""重 IO 后台化回归测试（10-09 加）。

验证：边缘结果帧的「存图 + 入库」已搬离 GUI 主线程，且行为与同步路径一致。

覆盖：
  A 异步开关默认开启，配置可回退（edge.async_io）
  B 异步提交后主线程立刻返回（不等磁盘），最终文件确实落盘
  C 异步提交后记录确实写入 DB
  D 回退到同步模式（async_io=False）时行为与旧版一致
  E 磁盘守护回调不炸（_on_io_done 容错）

运行：python tests/_test_async_io.py
"""
# --- 项目根目录加入 sys.path ---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys
import tempfile
import time

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception as e:
    print("[warn] 预加载 infer/torch:", e)

from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication

import main as M

_results = []


def report(name, ok, detail=""):
    _results.append((name, bool(ok)))
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def wait_events(ms=800):
    """跑一会儿事件循环，让线程池回调排入主线程。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


app = QApplication(sys.argv)
win = M.MainWindow()
det = win.pages[0]

# 用一个独立临时 DB，避免污染项目 records.db
import db as _dbm


class _TmpDB:
    def __init__(self, path):
        import sqlite3
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(_dbm._SCHEMA)
        self.conn.commit()
        self.rows = []

    def insert(self, product, result, defect_type, area, confidence, image_path):
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        # 故意慢一点，验证"主线程不被拖住"
        time.sleep(0.35)
        self.conn.execute(
            "INSERT INTO records(time,product,result,defect_type,area,confidence,image_path)"
            " VALUES(?,?,?,?,?,?,?)",
            (t, product, result, defect_type, area, confidence, image_path))
        self.conn.commit()
        self.rows.append((result, defect_type, image_path))
        return t

    def count(self):
        return len(self.rows)


tmpdir = tempfile.mkdtemp(prefix="asyncio_")
db_path = os.path.join(tmpdir, "t.db")
det.db = _TmpDB(db_path)
det._edge_detect_enabled = True
det._persist_gate = True
det._save_img_gate = True
det._camera_live = False

# 直接构造一条"边缘结果"（带真实可解码的 JPEG + 一个缺陷框）
import base64
try:
    import cv2
    import numpy as np
    _img = np.full((64, 64, 3), 128, np.uint8)
    _ok, _buf = cv2.imencode(".jpg", _img)
    jpg = base64.b64encode(_buf.tobytes()).decode("ascii")
except Exception:
    # 兜底：写一张真实小 PNG 再 base64
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import QBuffer, QByteArray
    _im = QImage(64, 64, QImage.Format_RGB888)
    _im.fill(0x808080)
    _ba = QByteArray()
    _b = QBuffer(_ba); _b.open(QBuffer.WriteOnly)
    _im.save(_b, "JPG"); _b.close()
    jpg = base64.b64encode(bytes(_ba)).decode("ascii")

obj = {"frame": 1, "ok": False, "infer_ms": 8.0, "w": 640, "h": 640,
       "img_b64": jpg,
       "defects": [{"cls": "inclusion", "conf": 0.9,
                    "x1": 10, "y1": 10, "x2": 60, "y2": 60}]}

save_dir = tmpdir
det.cfg.set("storage", "save_path", save_dir)

# ---------------- A 开关默认值 + 可回退 ----------------
ok_a = (det.cfg.get("edge", "async_io", None) is not None)
report("A 配置项 edge.async_io 存在", ok_a,
       "值=%r（默认应为 True）" % det.cfg.get("edge", "async_io", None))

# ---------------- B/C 异步提交：主线程不阻塞 + 最终落盘入库 ----------------
try:
    det.cfg.set("edge", "async_io", True)
    n_before = det._TmpDB__dict__ if False else len(det.db.rows)
    t0 = time.time()
    det._on_edge_result(obj)
    dt = time.time() - t0                     # 主线程耗时：应远小于 DB 的 0.35s
    d1 = (time.time() - det._last_frame_ts) < 3.0
    wait_events(1500)
    rows = det.db.rows
    n_after = len(rows)
    # 落盘文件
    files = [f for f in os.listdir(save_dir) if not f.endswith(".db")]
    ok_b = (dt < 0.30 and n_after == n_before + 1 and len(files) >= 1)
    report("B 异步提交：主线程快速返回 + 文件落盘", ok_b,
           "主线程耗时=%.3fs(<0.30) 入库=%d 落盘文件=%d" % (dt, n_after, len(files)))
    ok_c = (n_after >= 1 and rows[-1][0] == "NG" and rows[-1][1] == "inclusion")
    report("C 异步提交：记录正确入库", ok_c,
           "末条=%r" % (rows[-1] if rows else None,))
except Exception as e:
    report("B/C 异步提交", False, repr(e))

# ---------------- D 回退同步模式 ----------------
try:
    det.cfg.set("edge", "async_io", False)
    n_before = len(det.db.rows)
    t0 = time.time()
    det._on_edge_result(obj)
    dt = time.time() - t0
    n_after = len(det.db.rows)
    # 同步路径下，_on_edge_result 返回时 DB 已写完
    ok_d = (n_after == n_before + 1 and dt >= 0.30)
    report("D 回退同步模式行为一致", ok_d,
           "主线程耗时=%.3fs(应≥0.35) 入库=%d" % (dt, n_after - n_before))
    det.cfg.set("edge", "async_io", True)     # 复原
except Exception as e:
    report("D 回退同步模式", False, repr(e))

# ---------------- E _on_io_done 容错 ----------------
try:
    det._on_io_done("", False)                # 落盘失败路径
    det._on_io_done(os.path.join(tmpdir, "x.jpg"), True)
    report("E _on_io_done 容错", True, "空路径/正常路径均未抛异常")
except Exception as e:
    report("E _on_io_done 容错", False, repr(e))

print("\n" + "=" * 58)
bad = [n for n, o in _results if not o]
print("结果: %d 项失败 / 共 %d 项" % (len(bad), len(_results)))
for n in bad:
    print("  失败:", n)
print("=" * 58)
sys.exit(1 if bad else 0)
