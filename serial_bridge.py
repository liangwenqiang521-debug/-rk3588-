# -*- coding: utf-8 -*-
"""RK3588 串口桥接：读取板端 board_infer.py 推送的逐行 JSON 检测结果。

板端 board_infer.py 每行发送一条 JSON（末尾换行）：
  {"frame":12,"ok":false,
   "defects":[{"cls":"dent","conf":0.93,"x1":120,"y1":80,"x2":210,"y2":175}],
   "infer_ms":8.2,"w":640,"h":480}

本线程职责：打开串口、按行解析 JSON、向上位机 UI 发信号。
遵循项目既有范式（QThread + pyqtSignal），与 npu_monitor.SerialBackend 风格一致。
"""
import json

from PyQt5.QtCore import QThread, pyqtSignal
import serial


class BoardSerialBridge(QThread):
    result_received = pyqtSignal(dict)   # 解析后的整条检测结果 dict
    stats_received = pyqtSignal(dict)    # NPU 状态(dict)，type==stats
    connected = pyqtSignal(bool, str)     # (成功?, 消息)
    error = pyqtSignal(str)

    def __init__(self, port="COM3", baud=1500000, parent=None):
        super().__init__(parent)
        self.port = port
        self.baud = int(baud) if str(baud).isdigit() else 1500000
        self._running = False
        self.ser = None
        self._buf = b""

    def run(self):
        try:
            # Windows 下 pyserial 只支持 exclusive=True；这里保留默认值。
            self.ser = serial.Serial(self.port, self.baud, timeout=0.2,
                                     bytesize=8, parity="N", stopbits=1)
        except Exception as e:
            self.connected.emit(False, "打开串口 %s 失败: %s" % (self.port, e))
            self.error.emit(str(e))
            return
        self._running = True
        self.connected.emit(True, "已连接 %s @ %d" % (self.port, self.baud))
        while self._running:
            try:
                chunk = self.ser.read(4096)
            except Exception as e:
                self.error.emit("读取异常: %s" % e)
                break
            if not chunk:
                continue
            self._buf += chunk
            # 逐行解析（板端每条 JSON 以 \n 结尾）
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8", "ignore"))
                except Exception:
                    # 非 JSON（如板端调试文本）忽略
                    continue
                if isinstance(obj, dict) and obj.get("type") == "stats":
                    self.stats_received.emit(obj)
                else:
                    self.result_received.emit(obj)
        try:
            self.ser.close()
        except Exception:
            pass
        self.connected.emit(False, "已断开 %s" % self.port)

    def stop(self):
        self._running = False
        self.wait(2000)
