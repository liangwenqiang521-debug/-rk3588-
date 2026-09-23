# -*- coding: utf-8 -*-
"""RK3588 网络(TCP)桥接：连接板端 board_infer.py 的 TCP 结果服务，接收逐行 JSON。

板端 board_infer.py 通过 --tcp-port 启动一个 TCP 服务，每帧检测结果以一行 JSON
(UTF-8, 换行结尾) 推送给所有已连接客户端：
  {"frame":12,"ok":false,
   "defects":[{"cls":"dent","conf":0.93,"x1":120,"y1":80,"x2":210,"y2":175}],
   "infer_ms":8.2,"w":640,"h":480}

本线程职责：连接到板子 IP:端口、按行解析 JSON、向上位机 UI 发信号。
接口（信号名）与 serial_bridge.BoardSerialBridge 完全一致，便于页面层互换。
"""
import base64
import json
import socket

from PyQt5.QtCore import QThread, pyqtSignal, QMutex

# 板端默认地址/端口统一来自 board_env，不在源码中硬编码内网 IP
try:
    import board_env
    _DEFAULT_HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
    _DEFAULT_PORT = board_env.get_int("BOARD_STREAM_PORT", 9000)
except Exception:
    _DEFAULT_HOST, _DEFAULT_PORT = "169.254.100.100", 9000


class BoardTcpBridge(QThread):
    result_received = pyqtSignal(dict)   # 解析后的整条检测结果 dict
    stats_received = pyqtSignal(dict)    # NPU 状态(dict)，type==stats
    connected = pyqtSignal(bool, str)     # (成功?, 消息)
    error = pyqtSignal(str)

    # 背压：允许同时在途(已投递但未处理完)的结果帧上限。
    # 板端 10fps 连续推送，若 GUI 绘制跟不上，Qt 事件队列会无限积压，
    # 每帧都攥着一份含 base64 图像的完整 JSON(约 150KB)，内存线性上涨直至卡死。
    # 超过上限的帧直接丢弃——实时预览场景下旧帧没有价值，最新帧才有。
    MAX_INFLIGHT = 2

    def __init__(self, host=None, port=None, parent=None):
        super().__init__(parent)
        self.host = host or _DEFAULT_HOST
        self.port = int(port) if str(port).isdigit() else _DEFAULT_PORT
        self._running = False
        self.sock = None
        self._buf = b""
        self._inflight = 0
        self._mutex = QMutex()
        self._dropped = 0      # 因 GUI 繁忙被丢弃的帧计数（诊断用）

    def ack(self):
        """GUI 处理完一帧后调用，释放一个在途槽位（背压）。"""
        self._mutex.lock()
        try:
            if self._inflight > 0:
                self._inflight -= 1
        finally:
            self._mutex.unlock()

    def _can_emit(self):
        """占用一个在途槽位；队列已满则返回 False（该帧应被丢弃）。"""
        self._mutex.lock()
        try:
            if self._inflight >= self.MAX_INFLIGHT:
                return False
            self._inflight += 1
            return True
        finally:
            self._mutex.unlock()

    def run(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=5)
        except Exception as e:
            self.connected.emit(False, "连接 %s:%d 失败: %s" % (self.host, self.port, e))
            self.error.emit(str(e))
            return
        self._running = True
        self.connected.emit(True, "已连接 %s:%d" % (self.host, self.port))
        self.sock.settimeout(0.5)
        while self._running:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                continue
            except Exception as e:
                self.error.emit("读取异常: %s" % e)
                break
            if not chunk:
                break
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8", "ignore"))
                except Exception:
                    # 非 JSON（如调试文本）忽略
                    continue
                if isinstance(obj, dict) and obj.get("type") == "stats":
                    self.stats_received.emit(obj)
                else:
                    # 结果帧：受背压限制，GUI 忙时丢弃旧帧（保留实时性）
                    if not self._can_emit():
                        self._dropped += 1
                    else:
                        self.result_received.emit(obj)
        try:
            self.sock.close()
        except Exception:
            pass
        self.connected.emit(False, "已断开 %s:%d" % (self.host, self.port))

    def stop(self):
        self._running = False
        self.wait(2000)

    def send_cmd(self, cmd):
        """向上位机→板端发送控制指令（step 模式用），如 {"cmd":"next"} / {"cmd":"reset"}。
        失败静默返回 False，不打断现有连接。"""
        try:
            if self.sock is None:
                return False
            self.sock.sendall((json.dumps({"cmd": cmd}, ensure_ascii=False) + "\n").encode("utf-8"))
            return True
        except Exception:
            return False

    def send_detect_image(self, jpeg_bytes, name="photo.jpg"):
        """把上位机打开的照片发给板端 NPU 检测（cmd=detect_img）。

        jpeg_bytes: 图片文件的原始字节（JPEG/PNG 均可，板端用 cv2.imdecode 解）。
        板端推理后广播常规结果帧：w/h 为原图尺寸，框坐标已还原到原图空间，
        img_b64 回传原图 —— 画布继续显示这张照片，叠加检测框。
        """
        try:
            if self.sock is None:
                return False
            obj = {"cmd": "detect_img", "name": str(name)[:80],
                   "img": base64.b64encode(bytes(jpeg_bytes)).decode("ascii")}
            self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
            return True
        except Exception:
            return False
