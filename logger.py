# -*- coding: utf-8 -*-
"""日志系统：写文件 logs/app.log（滚动），同时通过 Qt 信号推送到 GUI"""
import os
import csv
import logging
import time
from logging.handlers import RotatingFileHandler
from collections import deque

from PyQt5.QtCore import QObject, pyqtSignal

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

LEVEL_ZH = {"DEBUG": "信息", "INFO": "信息", "WARNING": "警告",
            "ERROR": "错误", "CRITICAL": "错误"}


class QtLogBridge(QObject):
    record = pyqtSignal(dict)


class _QtHandler(logging.Handler):
    def __init__(self, bridge, buffer):
        super().__init__()
        self.bridge = bridge
        self.buffer = buffer

    def emit(self, rec):
        item = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rec.created)),
            "level": LEVEL_ZH.get(rec.levelname, "信息"),
            "module": getattr(rec, "module_name", "系统"),
            "content": rec.getMessage(),
        }
        self.buffer.append(item)
        self.bridge.record.emit(item)


class AppLogger(object):
    """全局日志入口；usage: log.info('相机', '相机初始化完成')"""

    def __init__(self, maxlen=2000):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.buffer = deque(maxlen=maxlen)
        self.bridge = QtLogBridge()
        self.logger = logging.getLogger("hmi")
        self.logger.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(module_name)s] %(message)s")

        fh = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        self.logger.addHandler(fh)

        qh = _QtHandler(self.bridge, self.buffer)
        self.logger.addHandler(qh)

    def _log(self, level, module, msg):
        self.logger.log(level, msg, extra={"module_name": module})

    def info(self, module, msg):
        self._log(logging.INFO, module, msg)

    def warning(self, module, msg):
        self._log(logging.WARNING, module, msg)

    def error(self, module, msg):
        self._log(logging.ERROR, module, msg)

    def export_csv(self, path, level="全部", module="全部", keyword=""):
        n = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["时间", "级别", "模块", "内容"])
            for it in self.buffer:
                if level != "全部" and it["level"] != level:
                    continue
                if module != "全部" and it["module"] != module:
                    continue
                if keyword and keyword not in it["content"]:
                    continue
                w.writerow([it["time"], it["level"], it["module"], it["content"]])
                n += 1
        return n
