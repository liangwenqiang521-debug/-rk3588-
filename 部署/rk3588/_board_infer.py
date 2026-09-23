# -*- coding: utf-8 -*-
"""
RK3588 板端 NPU 推理脚本 (RKNNLite runtime)
====================================================================
在 RK3588 开发板上运行，用 NPU 对 YOLOv11 .rknn 模型做缺陷检测。
配套 `export_rknn.py` 产出的 .rknn 权重。

--------------------------------------------------------------------
⚠️ 运行环境
--------------------------------------------------------------------
  * 必须在 RK3588 板子的 Linux(aarch64) 上运行
  * 安装 rknn-toolkit-lite2 (板端 runtime):
        pip install rknn-toolkit-lite2
  * 需要 rknpu2 驱动(官方系统固件一般已带)

--------------------------------------------------------------------
用法
--------------------------------------------------------------------
# 单张图推理
python board_infer.py --model best.rknn --source test.jpg --imgsz 640 \
    --names crazing inclusion patches pitted_surface rolled-in_scale scratches

# 图片目录批量推理
python board_infer.py --model best.rknn --source ./images/ --imgsz 640 \
    --names crazing inclusion patches pitted_surface rolled-in_scale scratches

# 接 USB/CSI 相机实时推理(帧率统计)
python board_infer.py --model best.rknn --source 0 --imgsz 640 \
    --names crazing inclusion patches pitted_surface rolled-in_scale scratches

# 推理结果同时通过串口发给上位机(可选)
python board_infer.py --model best.rknn --source 0 --imgsz 640 \
    --names crazing inclusion patches pitted_surface rolled-in_scale scratches --serial /dev/ttyS0 --baud 1500000

# 推理结果通过 TCP 网络推送给上位机(推荐，走以太网)
python board_infer.py --model best.rknn --source 0 --imgsz 640 \
    --names crazing inclusion patches pitted_surface rolled-in_scale scratches --tcp-port 9000

--------------------------------------------------------------------
输出协议(供 PyQt5 上位机解析)
--------------------------------------------------------------------
板子->上位机的每一帧检测结果以一行 JSON(UTF-8, 换行结尾)发送：
  {"frame":12,"ok":false,"defects":[{"cls":"dent","conf":0.93,
     "x1":120,"y1":80,"x2":210,"y2":175}],"infer_ms":8.2}
其中 ok=false 表示存在至少一个缺陷(NG)，true 为 OK。

另有一条独立的「状态」JSON(同样一行，带 type 标记)周期推送(默认 1s)，
供上位机 NPU 监控页显示真实负载/温度/内存：
  {"type":"stats","core0":45,"core1":30,"core2":12,
   "temp":48.5,"mem_used":1520.0,"mem_total":8192.0,
   "fps":62.3,"infer_ms":8.1}
上位机桥接线程按 "type" 字段分流：检测结果->result_received，
状态->stats_received。
"""

import argparse
import os
import re
import json
import time
import glob
import socket
import threading

import cv2
import numpy as np


# ----------------------- TCP 结果服务(上位机网络接收) -----------------------
class TcpResultServer:
    """板端 TCP 服务：把每帧检测结果 JSON 推送给所有已连接的上位机客户端。

    用法：python board_infer.py ... --tcp-port 9000
    上位机在“边缘模式 → 网络(TCP)”中填板子 IP:9000 即可接收。
    """

    def __init__(self, port):
        self.port = int(port)
        self.sock = None
        self.clients = []
        self.lock = threading.Lock()
        self._running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.listen(5)
        self.thread.start()
        print("TCP 结果服务已启动: 0.0.0.0:%d" % self.port)

    def _serve(self):
        while self._running:
            try:
                conn, addr = self.sock.accept()
            except Exception:
                break
            print("客户端接入: %s" % str(addr))
            with self.lock:
                self.clients.append(conn)
            t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            t.start()

    def _handle(self, conn):
        try:
            while self._running:
                data = conn.recv(64)
                if not data:
                    break
        except Exception:
            pass
        finally:
            with self.lock:
                if conn in self.clients:
                    self.clients.remove(conn)
            try:
                conn.close()
            except Exception:
                pass

    def send(self, text):
        with self.lock:
            dead = []
            for c in self.clients:
                try:
                    c.sendall((text + "\n").encode("utf-8"))
                except Exception:
                    dead.append(c)
            for c in dead:
                self.clients.remove(c)

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass



# ----------------------- 预处理: letterbox -----------------------
def letterbox(img, new_size=640, color=(114, 114, 114)):
    """保持纵横比缩放到 new_size×new_size，短边补灰边。返回 (padded, scale, (dw,dh))。"""
    h, w = img.shape[:2]
    scale = min(new_size / w, new_size / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dw, dh = (new_size - nw) // 2, (new_size - nh) // 2
    padded = cv2.copyMakeBorder(resized, dh, new_size - nh - dh,
                                dw, new_size - nw - dw,
                                cv2.BORDER_CONSTANT, value=color)
    return padded, scale, (dw, dh)


def preprocess(img_bgr, imgsz):
    """BGR->RGB，保持 uint8 0-255，输出 NHWC。

    ⚠️⚠️ **不要在这里做 /255 归一化！**
    本项目的 .rknn 是在「host 送 uint8[0,255]、RKNN 内部 mean=0/std=255 归一化」
    的前提下转换的（见 export_rknn.py 的说明）。若在这里再 /255，归一化会叠加两次，
    输入被压缩 255 倍，后果非常隐蔽：
      * 分类头被压塌（crazing 0.4021 -> 0.137，argmax 甚至跑到别的类）
      * box 却"看起来大致正常"（DFL 解码经 softmax，距离被限制在 [0,reg_max] 有界）
    实测（NEU 6 类、crazing 测试图）：uint8 输入 cls=0.4031（≈onnxruntime 0.4021），
    而 float32[0,1] 输入只有 0.2059。
    """
    padded, scale, (dw, dh) = letterbox(img_bgr, imgsz)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    return rgb[np.newaxis, ...], scale, (dw, dh)   # (1,H,W,3) uint8


# ----------------------- 后处理: 解码 YOLOv11 -----------------------
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def postprocess(output, scale, pad, orig_shape, conf_thres=0.25, iou_thres=0.45,
                names=None, cls_sigmoid="auto"):
    """
    output: np.ndarray, shape [1, 4+nc, 8400] (RKNN 输出)
    返回归一化前的原图坐标缺陷列表。

    cls_sigmoid: 类别通道是否**再**做一次 sigmoid
      - "auto"（默认）：按数值范围自动判定。YOLOv11 官方导出的 ONNX/RKNN
        内部已含 sigmoid，输出即概率（不会出现明显负值）；而部分导出方式
        /旧模型输出的是原始 logits（会出现明显负值）。
      - "on" / "off"：强制。

      ⚠️ 判定错会非常隐蔽：把"已经是概率"的输出再做一次 sigmoid，
        会让所有值被压到 ≈0.5（sigmoid(0)=0.5），于是所有 anchor 都超过
        阈值，表现为"每帧几百上千个框、置信度清一色 0.5"。
    """
    h0, w0 = orig_shape[:2]
    out = output[0].T  # -> [8400, 4+nc]
    boxes = out[:, :4]            # cx,cy,w,h (在 640 letterbox 空间)
    raw = out[:, 4:]
    if cls_sigmoid == "on":
        scores = sigmoid(raw)
    elif cls_sigmoid == "off":
        scores = raw
    else:
        # 概率输出不会出现明显负值；logits 则会出现。以此自动区分。
        scores = sigmoid(raw) if float(raw.min()) < -0.5 else raw
    scores = np.asarray(scores, dtype=np.float32)
    nc = scores.shape[1]

    # 反 letterbox 映射回原图
    dw, dh = pad
    cx, cy, bw, bh = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    x1 = (cx - bw / 2 - dw) / scale
    y1 = (cy - bh / 2 - dh) / scale
    x2 = (cx + bw / 2 - dw) / scale
    y2 = (cy + bh / 2 - dh) / scale
    x1 = np.clip(x1, 0, w0); y1 = np.clip(y1, 0, h0)
    x2 = np.clip(x2, 0, w0); y2 = np.clip(y2, 0, h0)

    detections = []
    for c in range(nc):
        cls_scores = scores[:, c]
        idx = np.where(cls_scores >= conf_thres)[0]
        for i in idx:
            detections.append([x1[i], y1[i], x2[i], y2[i], float(cls_scores[i]), c])
    if len(detections) == 0:
        return []
    detections = np.array(detections, dtype=np.float32)

    # 按类别做 NMS
    keep = []
    for c in range(nc):
        sub = detections[detections[:, 5] == c]
        if len(sub) == 0:
            continue
        boxes_n = sub[:, :4]
        sc = sub[:, 4]
        order = sc.argsort()[::-1]
        while len(order):
            i = order[0]
            keep.append(sub[i])
            if len(order) == 1:
                break
            xx1 = np.maximum(boxes_n[i, 0], boxes_n[order[1:], 0])
            yy1 = np.maximum(boxes_n[i, 1], boxes_n[order[1:], 1])
            xx2 = np.minimum(boxes_n[i, 2], boxes_n[order[1:], 2])
            yy2 = np.minimum(boxes_n[i, 3], boxes_n[order[1:], 3])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            area_i = (boxes_n[i, 2] - boxes_n[i, 0]) * (boxes_n[i, 3] - boxes_n[i, 1])
            area_j = (boxes_n[order[1:], 2] - boxes_n[order[1:], 0]) * (boxes_n[order[1:], 3] - boxes_n[order[1:], 1])
            iou = inter / (area_i + area_j - inter + 1e-9)
            order = order[1:][iou <= iou_thres]
    keep = np.array(keep) if keep else np.empty((0, 6))

    defects = []
    for d in keep:
        x1_, y1_, x2_, y2_, conf, c = d
        name = names[int(c)] if names and int(c) < len(names) else ("class_%d" % int(c))
        defects.append({
            "cls": name, "conf": round(float(conf), 3),
            "x1": int(round(x1_)), "y1": int(round(y1_)),
            "x2": int(round(x2_)), "y2": int(round(y2_)),
        })
    return defects


def draw(img, defects, names=None):
    color_map = {
        "scratch": (227, 179, 65), "dent": (47, 129, 247), "missing": (248, 81, 73),
        "crack": (163, 113, 247), "crazing": (63, 185, 80), "inclusion": (188, 63, 188),
        "patches": (240, 160, 40), "pitted_surface": (80, 200, 200),
        "rolled-in_scale": (200, 100, 100), "scratches": (227, 179, 65),
    }
    for d in defects:
        c = color_map.get(d["cls"], (0, 200, 255))
        x1, y1, x2, y2 = d["x1"], d["y1"], d["x2"], d["y2"]
        cv2.rectangle(img, (x1, y1), (x2, y2), c, 2)
        label = "%s %.2f" % (d["cls"], d["conf"])
        cv2.putText(img, label, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 2)
    return img


# ----------------------- NPU 状态上报 (供上位机 NPU 监控页) -----------------------
def read_npu_stats():
    """读取 RK3588 的 NPU 负载/温度/内存，返回 dict。

    负载来自 RKNPU 驱动 debugfs：/sys/kernel/debug/rknpu/load
    （需 root 且 debugfs 已挂载；读不到时返回 0，不影响推理）。
    温度来自 /sys/class/thermal/thermal_zone0/temp（毫摄氏度）。
    内存来自 /proc/meminfo。
    """
    stats = {"core0": 0, "core1": 0, "core2": 0,
             "temp": None, "mem_used": None, "mem_total": None}
    try:
        with open("/sys/kernel/debug/rknpu/load") as f:
            txt = f.read()
        m = re.search(r"Core0:\s*(\d+)%,\s*Core1:\s*(\d+)%,\s*Core2:\s*(\d+)%", txt)
        if m:
            stats["core0"] = int(m.group(1))
            stats["core1"] = int(m.group(2))
            stats["core2"] = int(m.group(3))
    except Exception:
        pass
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            stats["temp"] = int(f.read().strip()) / 1000.0
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            info = f.read()
        mt = re.search(r"MemTotal:\s+(\d+)", info)
        ma = re.search(r"MemAvailable:\s+(\d+)", info)
        if mt:
            total = int(mt.group(1)) / 1024.0
            stats["mem_total"] = total
            if ma:
                stats["mem_used"] = total - int(ma.group(1)) / 1024.0
    except Exception:
        pass
    return stats


class StatsReporter(threading.Thread):
    """后台线程：周期读 NPU 状态并以 JSON 推给上位机（串口/TCP 复用现有通道）。

    发送的 JSON 带 "type":"stats" 标记，上位机桥接线程据此区分检测结果与状态，
    转发给 NPU 监控页。每帧推理耗时由主循环 note_infer() 喂入，用于算平均与 FPS。
    """

    def __init__(self, ser=None, tcp_server=None, interval=1.0):
        super().__init__(daemon=True)
        self.ser = ser
        self.tcp_server = tcp_server
        self.interval = interval
        self._running = True
        self._lock = threading.Lock()
        self._last_infer_ms = 0.0
        self._frame_count = 0
        self._fps_t0 = time.time()

    def note_infer(self, ms):
        with self._lock:
            self._last_infer_ms = ms
            self._frame_count += 1

    def _send(self, line):
        if self.ser:
            try:
                self.ser.write((line + "\n").encode("utf-8"))
            except Exception:
                pass
        if self.tcp_server:
            self.tcp_server.send(line)

    def run(self):
        # 确保 debugfs 已挂载（失败忽略，load 会读不到）
        try:
            os.system("mount -t debugfs none /sys/kernel/debug 2>/dev/null")
        except Exception:
            pass
        while self._running:
            with self._lock:
                fps = self._frame_count / max(0.001, time.time() - self._fps_t0)
                self._frame_count = 0
                self._fps_t0 = time.time()
                ms = self._last_infer_ms
            payload = {"type": "stats"}
            payload.update(read_npu_stats())
            payload["fps"] = round(fps, 1)
            payload["infer_ms"] = round(ms, 2)
            self._send(json.dumps(payload, ensure_ascii=False))
            time.sleep(self.interval)

    def stop(self):
        self._running = False


def main():
    ap = argparse.ArgumentParser(description="RK3588 NPU 缺陷检测推理")
    ap.add_argument("--model", required=True, help=".rknn 权重路径")
    ap.add_argument("--source", required=True, help="图片/目录/摄像头索引(如 0)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--names", nargs="*", default=[], help="类别名")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--cls-sigmoid", default="auto", choices=["auto", "on", "off"],
                    help="类别通道是否再做 sigmoid：auto(默认,按数值范围判定) / on / off。"
                         "YOLOv11 官方导出的模型输出已是概率，无需再做 sigmoid。")
    ap.add_argument("--serial", default="", help="串口设备(如 /dev/ttyS0)，留空不发")
    ap.add_argument("--baud", type=int, default=1500000)
    ap.add_argument("--tcp-port", type=int, default=0, help="TCP 结果服务端口(如 9000)，>0 时启用网络推送")
    ap.add_argument("--save", default="", help="结果图保存目录(可选)")
    args = ap.parse_args()

    from rknnlite.api import RKNNLite
    rknn = RKNNLite()
    print("加载 RKNN 模型: %s" % args.model)
    if rknn.load_rknn(args.model) != 0:
        raise SystemExit("❌ 加载 .rknn 失败")
    if rknn.init_runtime() != 0:
        raise SystemExit("❌ init_runtime 失败(检查 rknpu2 驱动/NPU 占用)")
    print("✅ NPU runtime 就绪")

    ser = None
    if args.serial:
        import serial
        ser = serial.Serial(args.serial, args.baud, timeout=1)
        print("串口已打开: %s @ %d" % (args.serial, args.baud))

    # 网络结果推送服务(可选)
    tcp_server = None
    if args.tcp_port and args.tcp_port > 0:
        tcp_server = TcpResultServer(args.tcp_port)
        tcp_server.start()

    # NPU 状态后台上报(供上位机 NPU 监控页，串口/TCP 复用)
    reporter = StatsReporter(ser=ser, tcp_server=tcp_server, interval=1.0)
    reporter.start()

    # 数据源: 摄像头 / 图片目录 / 单图
    cap = None
    is_cam = args.source.isdigit()
    sources = []
    if is_cam:
        cap = cv2.VideoCapture(int(args.source))
    elif os.path.isdir(args.source):
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            sources += sorted(glob.glob(os.path.join(args.source, ext)))
        if not sources:
            raise SystemExit("❌ 目录无图片: %s" % args.source)
    else:
        sources = [args.source]

    if args.save:
        os.makedirs(args.save, exist_ok=True)

    frame_idx = 0
    try:
        while True:
            if is_cam:
                ok, frame = cap.read()
                if not ok:
                    break
            else:
                if not sources:
                    break
                frame = cv2.imread(sources.pop(0))
                if frame is None:
                    continue
            orig = frame.copy()
            blob, scale, pad = preprocess(frame, args.imgsz)
            t0 = time.time()
            outputs = rknn.inference(inputs=[blob])
            infer_ms = (time.time() - t0) * 1000.0
            reporter.note_infer(infer_ms)
            defects = postprocess(outputs[0], scale, pad, frame.shape,
                                  conf_thres=args.conf, iou_thres=args.iou, names=args.names,
                                  cls_sigmoid=args.cls_sigmoid)
            ok_flag = len(defects) == 0
            result = {"frame": frame_idx, "ok": ok_flag, "defects": defects,
                      "infer_ms": round(infer_ms, 2), "w": frame.shape[1], "h": frame.shape[0]}
            print(json.dumps(result, ensure_ascii=False))

            if ser:
                ser.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
            if tcp_server:
                tcp_server.send(json.dumps(result, ensure_ascii=False))

            vis = draw(orig, defects)
            if args.save:
                cv2.imwrite(os.path.join(args.save, "res_%05d.jpg" % frame_idx), vis)
            if is_cam:
                cv2.imshow("RK3588 NPU", vis)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            frame_idx += 1
            if not is_cam and not sources:
                break
    finally:
        reporter.stop()
        if cap:
            cap.release()
        if ser:
            ser.close()
        cv2.destroyAllWindows() if is_cam else None
        rknn.release()


if __name__ == "__main__":
    main()
