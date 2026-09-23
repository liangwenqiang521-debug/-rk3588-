# -*- coding: utf-8 -*-
"""板端导入验证：确认 PySide6 + qt_shim(PyQt5) 垫片 + 全部上位机模块可导入，
并抽查关键 Qt 短枚举/信号别名，避免上板才发现 import 崩。

运行（板端）：
  cd /opt/hmi && QT_QPA_PLATFORM=minimal PYTHONPATH=/opt/hmi/qt_shim python3 verify_imports.py
"""
import os
import sys

FAILS = []
def check(name, fn):
    try:
        fn()
        print("  [OK]  %s" % name)
    except Exception as e:
        FAILS.append(name)
        print("  [FAIL] %s -> %s: %s" % (name, type(e).__name__, e))

print("=== 1. PySide6 本体 ===")
check("import PySide6", lambda: __import__("PySide6"))
check("PySide6.__version__", lambda: __import__("PySide6").__version__)
check("import shiboken6", lambda: __import__("shiboken6"))
check("import numpy", lambda: __import__("numpy"))
check("import psutil", lambda: __import__("psutil"))
check("import serial", lambda: __import__("serial"))

print("=== 2. Qt 平台插件 ===")
import PySide6
_pdir = os.path.join(os.path.dirname(PySide6.__file__), "Qt", "plugins", "platforms")
check("platforms dir exists", lambda: (os.path.isdir(_pdir) or (_ for _ in ()).throw(Exception("no dir %s" % _pdir))))
if os.path.isdir(_pdir):
    print("      platforms:", sorted(os.listdir(_pdir)))

print("=== 3. qt_shim -> PyQt5 垫片 ===")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "qt_shim"))
check("import PyQt5", lambda: __import__("PyQt5"))
from PyQt5 import QtCore, QtGui, QtWidgets
check("QtCore.Qt 存在", lambda: QtCore.Qt)
check("QtCore.pyqtSignal 存在", lambda: QtCore.pyqtSignal)
check("QtCore.QThread 存在", lambda: QtCore.QThread)

print("=== 4. Qt 短枚举抽查 ===")
for name in ["red", "green", "AlignCenter", "AlignLeft", "AlignRight", "AlignVCenter",
             "Horizontal", "NoPen", "NoBrush", "DashLine", "SmoothTransformation",
             "KeepAspectRatio", "ScrollBarAsNeeded", "PointingHandCursor"]:
    check("Qt.%s" % name, lambda n=name: getattr(QtCore.Qt, n))

print("=== 5. 各类枚举简写抽查 ===")
check("QPainter.Antialiasing", lambda: QtGui.QPainter.Antialiasing)
check("QHeaderView.Stretch", lambda: QtWidgets.QHeaderView.Stretch)
check("QSizePolicy.Expanding", lambda: QtWidgets.QSizePolicy.Expanding)
check("QMessageBox.Yes", lambda: QtWidgets.QMessageBox.Yes)
check("QAbstractItemView.SelectRows", lambda: QtWidgets.QAbstractItemView.SelectRows)
check("QFont.Bold", lambda: QtGui.QFont.Bold)

print("=== 6. QApplication 构造（minimal 平台）===")
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
def mk_app():
    global _app
    _app = QtWidgets.QApplication(sys.argv)
check("QApplication(...)", mk_app)

print("=== 7. 导入全部上位机模块 ===")
import importlib
for mod in ["main", "config", "db", "logger", "widgets", "utils", "npu_monitor",
            "page_detect", "page_settings", "page_history", "page_comm",
            "page_log", "page_npu", "tcp_bridge", "serial_bridge", "infer"]:
    check("import %s" % mod, lambda m=mod: importlib.import_module(m))

print("=== 8. 构造主窗口 ===")
import main
def mk_win():
    global _win
    _win = main.MainWindow()
    _win.show()
    _app.processEvents()
check("main.MainWindow()", mk_win)

print()
if FAILS:
    print("FAILED (%d): %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("ALL_OK")
