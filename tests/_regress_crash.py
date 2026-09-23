# -*- coding: utf-8 -*-
"""回归测试：验证「连板后点开始检测即闪退」已修复。

原崩溃链条：
  板端推流 set_image_bytes() -> image_path() 变空串
  -> _resolve_mode() 误判为本地推理 -> _real_tick() 调 load_image("")
  -> np.fromfile("") 抛 FileNotFoundError（该行原本不在 try 内）
  -> PyQt5 槽函数未捕获异常 -> qFatal() 杀进程（界面无提示消失）
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys
import traceback

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception as e:
    print("[warn] 预加载 infer/torch:", e)

import cv2
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

import main as m

RESULTS = []


def check(name, ok, extra=""):
    RESULTS.append((name, ok, extra))
    print("  [%s] %s %s" % ("PASS" if ok else "FAIL", name, extra))


def find_img():
    for root, _d, files in os.walk("图片"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                return os.path.join(root, f)
    return None


app = QApplication(sys.argv)
win = m.MainWindow()
det = win.pages[0]
cv = det.canvas
img_path = find_img()
print("测试图:", img_path)


def stage_a():
    """A. 模拟板端推流（内存图）—— 原崩溃路径"""
    print("\n=== A. 板端推流内存图（原崩溃路径）===")
    raw_img = cv2.imread(img_path)
    ok, buf = cv2.imencode(".jpg", raw_img)
    cv.set_image_bytes(buf.tobytes())
    check("has_image() 为 True", cv.has_image() is True)
    check("image_path() 为空串", cv.image_path() == "", "实际=%r" % cv.image_path())
    mode = det._resolve_mode()
    check("_resolve_mode() 不再误判为 real", mode != "real", "实际=%r" % mode)
    try:
        det._real_tick()
        check("_real_tick() 未抛异常（进程存活）", True)
    except Exception as e:
        check("_real_tick() 未抛异常（进程存活）", False, repr(e))
    QTimer.singleShot(50, stage_b)


def stage_b():
    """B. 从文件打开照片 —— 本地推理路径仍应正常工作"""
    print("\n=== B. 文件照片（本地推理仍可用）===")
    cv.set_image(img_path)
    check("image_path() 有值", bool(cv.image_path()))
    mode = det._resolve_mode()
    check("_resolve_mode() == 'real'", mode == "real", "实际=%r" % mode)
    try:
        det._real_tick()
        check("_real_tick() 正常执行", True)
    except Exception as e:
        traceback.print_exc()
        check("_real_tick() 正常执行", False, repr(e))
    QTimer.singleShot(50, stage_c)


class FakeBridge:
    """模拟已连接的 TCP 桥接"""
    def isRunning(self):
        return True


def stage_c():
    """C. 边缘已连接时点开始检测 —— 应走边缘模式，而非本地推理"""
    print("\n=== C. 边缘已连接 → 开始检测应走边缘模式 ===")
    det.bridge = FakeBridge()
    det._edge_detect_enabled = False
    try:
        det._start()
        check("_edge_detect_enabled 置为 True", det._edge_detect_enabled is True)
        check("未启动本地推理定时器", not det.timer.isActive())
        check("开始按钮被禁用", not det.btn_start.isEnabled())
        det._stop()
        check("停止后回到仅预览且保留连接",
              det._edge_detect_enabled is False and det.bridge is not None)
    except Exception as e:
        traceback.print_exc()
        check("边缘 _start / _stop 无异常", False, repr(e))
    finally:
        det.bridge = None
        QTimer.singleShot(50, finish)


def finish():
    print("\n" + "=" * 58)
    bad = [r for r in RESULTS if not r[1]]
    if bad:
        print("结果: %d 项失败 / 共 %d 项" % (len(bad), len(RESULTS)))
        for n, _o, e in bad:
            print("   FAIL:", n, e)
    else:
        print("结果: 全部 %d 项通过 —— 闪退已修复" % len(RESULTS))
    print("=" * 58)
    app.quit()


QTimer.singleShot(300, stage_a)
QTimer.singleShot(90000, app.quit)
app.exec_()
sys.exit(1 if [r for r in RESULTS if not r[1]] else 0)
