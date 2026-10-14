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
import queue
import socket
import threading

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
        # 发送改后台队列：GUI 主线程只入队，由 _sender_loop 串行 sendall。
        # 原先主线程直接 sendall——"打开照片+检测"会把整张图（可能数 MB）一次性
        # 写入 socket，板端读得慢时发送缓冲写满，主线程阻塞在 syscall 上 → 界面冻结。
        self._out_q = queue.Queue(maxsize=64)
        self._sender_thread = None

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
        # 发送线程：socket 的所有写入都在此线程串行完成（读写分线程，互不阻塞）
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._sender_thread.start()
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
        # 收尾：先停发送线程（放哨兵唤醒它），再关 socket
        self._running = False
        try:
            self._out_q.put_nowait(None)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
        self.connected.emit(False, "已断开 %s:%d" % (self.host, self.port))

    def _sender_loop(self):
        """后台发送：从队列取数据串行 sendall。写失败只记一次错误，
        链路是否已断由接收循环判定（避免两个线程争抢 socket 生命周期）。"""
        while self._running:
            try:
                data = self._out_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if data is None:
                break
            try:
                sock = self.sock
                if sock is not None:
                    sock.sendall(data)
            except Exception as e:
                self.error.emit("发送异常: %s" % e)

    def _enqueue(self, obj):
        """把一条指令放入发送队列（非阻塞）。返回 False 表示未入队。"""
        if not self._running or self.sock is None:
            return False
        try:
            data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        except Exception:
            return False
        try:
            self._out_q.put_nowait(data)
            return True
        except queue.Full:
            return False

    def stop(self):
        self._running = False
        try:
            self._out_q.put_nowait(None)   # 唤醒并结束发送线程
        except Exception:
            pass
        self.wait(2000)

    def send_cmd(self, cmd):
        """向上位机→板端发送控制指令（step 模式用），如 {"cmd":"next"} / {"cmd":"reset"}。
        非阻塞：只入发送队列，真正的 sendall 在后台线程完成。
        返回 True 表示已入队（不代表已送达板端），失败静默返回 False。"""
        return self._enqueue({"cmd": cmd})

    def send_detect_image(self, jpeg_bytes, name="photo.jpg"):
        """把上位机打开的照片发给板端 NPU 检测（cmd=detect_img）。

        jpeg_bytes: 图片文件的原始字节（JPEG/PNG 均可，板端用 cv2.imdecode 解）。
        板端推理后广播常规结果帧：w/h 为原图尺寸，框坐标已还原到原图空间，
        img_b64 回传原图 —— 画布继续显示这张照片，叠加检测框。
        非阻塞：base64 编码后只入队，背景线程负责发送（大图不再冻结界面）。
        """
        try:
            obj = {"cmd": "detect_img", "name": str(name)[:80],
                   "img": base64.b64encode(bytes(jpeg_bytes)).decode("ascii")}
        except Exception:
            return False
        return self._enqueue(obj)
