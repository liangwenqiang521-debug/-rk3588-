# -*- coding: utf-8 -*-
"""RK3588 板端 NPU 推理服务（TCP 9000）

启动: python3 /root/rknn/board_server.py [best.rknn|best_int8.rknn] [port]

协议（逐行 JSON，UTF-8 + \n）：
  检测结果: {"frame":12,"ok":false,
             "defects":[{"cls":"dent","conf":0.93,"x1":120,"y1":80,"x2":210,"y2":175}],
             "infer_ms":8.2,"w":640,"h":640}
  NPU状态 : {"type":"stats","core0":42,"core1":7,"core2":8,
             "npu":"42%/7%/8%","temp":45.2,
             "mem_used":512,"mem_total":2048,"mem_available":1536,
             "fps":15.3,"infer_ms":65.4}
"""
import os, sys, json, time, socket, threading, glob, base64

import numpy as np

WORK = '/root/rknn'
SAMPLES = os.path.join(WORK, 'samples')
# 缺陷类别表。
# 前 6 项顺序必须与模型导出时的 names 严格一致（NEU-DET），勿动；
# 09-21 扩展类见 NAMES_EXT，供扩类模型复用本服务（协议与上位机零改动）。
NAMES = ['crazing', 'inclusion', 'patches', 'pitted_surface', 'rolled-in_scale', 'scratches']

# 扩展类别表（工业常见扩展类 + 表面处理类）
NAMES_EXT = [
    'edge_crack', 'scab', 'pitting', 'roll_mark', 'wavy_edge', 'oxide_scale',
    'stain', 'oil_spot', 'water_spot', 'rust',
]

# ---------- per-class 阈值表（方案 B，借鉴 Orin Nano 39 类报告）----------
# 背景：NEU-DET 里 inclusion 与 scratches 都是「竖直暗条纹」，模型在这两类的
# 置信度长期拉不开（实测 scratches_108 上 scratches 0.86 vs inclusion 0.82，差
# 0.04 的平票，谁排第一会抖）。用单一全局阈值无法区分这种易混对。
# 策略：
#   - inclusion 降阈到 0.16：夹杂是「漏检更不可接受」的类（有真实夹杂没抓=漏检），
#     降阈保住召回，宁可多框。
#   - scratches 提阈到 0.30：划伤是竖直条纹里最容易「假阳性」的类（纹理干扰多），
#     提阈压制误报，让 inclusion 判定在低置信区间占优，把易混对往「夹杂」方向收。
#   - crazing 提阈到 0.25：09-20 cal 阈值扫描发现，0.20 以下 crazing TP 增量为 0
#     （模型自身在 crazing 类几乎没有低置信预测可捞），升阈反而过滤 12 个低置信误报，F1 +0.024。
#   - 其余 3 类维持 0.20 基线。
# 说明：per-class 阈值**只改变「哪些框被保留」，不改变框内 argmax 的类别**；
#       想要真正分离易混对，还需配合上位机按 top-2 分差重排（见 page_detect.py）。
PER_CLASS_THRES = {
    'crazing': 0.25,            # 09-20 阈值扫描：F1 +0.024（vs 0.20）
    'inclusion': 0.16,
    'patches': 0.20,
    'pitted_surface': 0.20,
    'rolled-in_scale': 0.20,
    'scratches': 0.30,
}
# 兼容旧代码的默认阈值（无 per-class 配置时回退用）
CONF_THRES = 0.20
IOU_THRES = 0.45

# 默认模型：best_neu6.rknn = NEU 6 类 FP16。
# ⚠️ 该模型的 .rknn 是在「host 送 uint8[0,255] 原图、RKNN 内部 mean=0/std=255
#    归一化」的前提下转换的，read_sample() 因此**故意不做 /255**。
#    若在这里加 /255，会与 RKNN 内部归一化叠加，输入被压缩 255 倍，分类头直接
#    被压塌（crazing 0.40 -> 0.14 且 argmax 跑偏）。详见 export_rknn.py 的注释。
MODEL = sys.argv[1] if len(sys.argv) > 1 else 'best_neu6.rknn'
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9000
if not MODEL.startswith('/'):
    MODEL = os.path.join(WORK, MODEL)

# 运行模式：默认 'stream'（连续循环回放样本）；'step'（一张一张，收到 cmd=next 才检测下一张）
MODE = 'step' if '--step' in sys.argv else 'stream'

from rknnlite.api import RKNNLite

# ---------------- 预处理 ----------------

def letterbox(img, size=640, pad=114):
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return np.full((size, size, 3), pad, dtype=np.uint8)
    scale = min(size / w, size / h)
    nw, nh = int(w * scale), int(h * scale)
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), pad, dtype=np.uint8)
    canvas[:nh, :nw] = r
    return canvas


try:
    import cv2
except ImportError:
    cv2 = None
    print('警告: 无 cv2，仅支持 .npy 样本')


def nms(boxes, scores, thres=IOU_THRES):
    if len(boxes) == 0:
        return []
    x1 = boxes[:, 0] - boxes[:, 2] / 2
    y1 = boxes[:, 1] - boxes[:, 3] / 2
    x2 = boxes[:, 0] + boxes[:, 2] / 2
    y2 = boxes[:, 1] + boxes[:, 3] / 2
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-8)
        order = rest[iou <= thres]
    return keep


def postprocess(out, conf_thres=CONF_THRES):
    """out: (1, 4+nc, 8400) -> defects list

    ⚠️ 模型的类别通道输出**已经是概率**（YOLOv11 导出的 ONNX 内部含 Sigmoid），
    这里直接取最大值即可。**不要再套一次 sigmoid**——sigmoid(0)=0.5 会让所有
    anchor 都超过阈值，表现为"每帧上千个框、置信度清一色 0.5"。
    """
    pred = np.array(out)[0].T          # (8400, 4+nc)
    boxes = pred[:, :4]
    cls_sc = pred[:, 4:]
    conf = cls_sc.max(axis=1)
    cls_id = cls_sc.argmax(axis=1)
    # per-class 阈值：按每个 anchor 的 argmax 类别查表，取该类专属阈值；
    # 未在表内的类别回退到全局 conf_thres。
    thresh = np.array([
        PER_CLASS_THRES.get(NAMES[c] if c < len(NAMES) else str(c), conf_thres)
        for c in cls_id
    ])
    m = conf > thresh
    if m.sum() == 0:
        return []
    bi = np.where(m)[0]
    keep = nms(boxes[bi], conf[bi])
    res = []
    for k in keep:
        j = bi[k]
        cx, cy, bw, bh = boxes[j]
        res.append({
            'cls': NAMES[cls_id[j]] if cls_id[j] < len(NAMES) else str(cls_id[j]),
            'conf': round(float(conf[j]), 4),
            'x1': round(float(cx - bw / 2), 1),
            'y1': round(float(cy - bh / 2), 1),
            'x2': round(float(cx + bw / 2), 1),
            'y2': round(float(cy + bh / 2), 1),
        })
    return res


# ---------------- NPU 服务 ----------------

class BoardServer:
    def __init__(self, model, port):
        self.model_path = model
        self.port = port
        self.clients = []
        self.lock = threading.Lock()
        self.frame_id = 0
        self.rknn = None
        self.samples = []
        self.last_ms = 0.0
        self._send_q = []            # 待发送 obj 队列（加锁消费）
        self._wake = threading.Event()  # 通知发送线程有数据
        self._stop_sender = False    # 发送线程退出标志
        self._next_evt = threading.Event()  # step 模式：收到 cmd=next 时置位，驱动推理一张
        self._reset_evt = threading.Event() # step 模式：收到 cmd=reset 时置位，回到第一张
        self._pending_img = None     # HMI 送检的照片 (name, bgr)；非空时优先于样本检测

    def load_samples(self):
        pats = ['*.npy', '*.jpg', '*.png', '*.bmp']
        files = []
        for p in pats:
            files += sorted(glob.glob(os.path.join(SAMPLES, p)))
        self.samples = files
        print('样本数:', len(files))
        if files:
            print('示例:', [os.path.basename(f) for f in files[:3]])
        return files

    def read_sample(self, path):
        if path.endswith('.npy'):
            a = np.load(path)
            if a.ndim == 4 and a.shape[1] == 3:      # NCHW -> NHWC
                a = np.transpose(a[0], (1, 2, 0))
            elif a.ndim == 3 and a.shape[0] == 3:
                a = np.transpose(a, (1, 2, 0))
            if a.ndim == 3:
                a = a[np.newaxis, ...]
            return a.astype(np.uint8)
        if cv2 is None:
            return None
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        return cv2.cvtColor(letterbox(img), cv2.COLOR_BGR2RGB)[np.newaxis, ...]

    def init_npu(self):
        self.rknn = RKNNLite(verbose=False)
        ret = self.rknn.load_rknn(self.model_path)
        if ret != 0:
            raise RuntimeError('load_rknn failed, ret=%d' % ret)
        ret = self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
        if ret != 0:
            raise RuntimeError('init_runtime failed, ret=%d' % ret)
        print('NPU 就绪:', self.model_path)

    def broadcast(self, obj):
        """非阻塞广播：把 obj 丢进发送队列，立即返回，绝不阻塞推理循环。
        真实发送由 _sender_loop 独立线程完成（短超时 + 失败踢客户端）。"""
        if self._stop_sender:
            return
        with self.lock:
            self._send_q.append(obj)
        self._wake.set()

    def _sender_loop(self):
        """独立发送线程：从队列取 obj，逐个 client 短超时 sendall。
        任何客户端发送失败/超时立即踢出，避免慢客户端拖死整个服务。"""
        while not self._stop_sender:
            # 等待有数据
            self._wake.wait(timeout=0.2)
            self._wake.clear()
            # 取所有待发对象
            batch = []
            with self.lock:
                if self._send_q:
                    batch = self._send_q
                    self._send_q = []
            if not batch:
                continue
            # 编码每条
            payloads = []
            for obj in batch:
                try:
                    payloads.append((json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8'))
                except Exception:
                    payloads.append(b'')
            # 对每个客户端，按顺序发送这一批
            dead = []
            with self.lock:
                clients = list(self.clients)
            for c in clients:
                try:
                    c.settimeout(0.3)        # 短超时，宁可丢包也不能阻塞
                    for data in payloads:
                        if not data:
                            continue
                        c.sendall(data)
                except Exception:
                    dead.append(c)
            if dead:
                with self.lock:
                    for c in dead:
                        try:
                            c.close()
                        except Exception:
                            pass
                        if c in self.clients:
                            self.clients.remove(c)

    def npu_stats(self):
        load = '-'
        cores = [0, 0, 0]
        try:
            with open('/sys/kernel/debug/rknpu/load') as f:
                t = f.read()
            nums = [x for x in t.replace('%', ' ').split() if x.replace('.', '').isdigit()]
            load = '/'.join(nums[:3]) + '%' if len(nums) >= 3 else t.strip()
            if len(nums) >= 3:
                cores = [int(float(x)) for x in nums[:3]]
        except Exception:
            pass
        temp = None
        for p in glob.glob('/sys/class/thermal/thermal_zone*/temp'):
            try:
                temp = int(open(p).read().strip()) / 1000.0
                break
            except Exception:
                pass
        mem_total = None
        mem_avail = None
        try:
            for line in open('/proc/meminfo'):
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1]) // 1024
                elif line.startswith('MemAvailable:'):
                    mem_avail = int(line.split()[1]) // 1024
        except Exception:
            pass
        mem_used = (mem_total - mem_avail) if (mem_total and mem_avail) else None
        return {
            'type': 'stats',
            'core0': cores[0], 'core1': cores[1], 'core2': cores[2],  # 兼容串口版协议
            'npu': load,
            'temp': temp,
            'mem_used': mem_used,
            'mem_total': mem_total,
            'mem_available': mem_avail,
            'fps': round(1000.0 / self.last_ms, 1) if self.last_ms > 0 else 0,
            'infer_ms': round(self.last_ms, 1),
            'model': os.path.basename(self.model_path),
        }

    def infer_loop(self):
        print('推理线程启动（模式: %s）' % MODE)
        if MODE == 'stream':
            self._infer_loop_stream()
        else:
            self._infer_loop_step()

    def _infer_one(self):
        """检测当前 frame_id 对应的一张样本，返回 (msg_dict, path) 或 (None, None)。"""
        if not self.samples:
            self.load_samples()
        if not self.samples:
            return None, None
        path = self.samples[self.frame_id % len(self.samples)]
        x = self.read_sample(path)
        if x is None:
            self.frame_id += 1
            return None, None
        t0 = time.time()
        try:
            y = self.rknn.inference(inputs=[x])
        except Exception as e:
            print('推理异常:', e)
            return None, None
        self.last_ms = (time.time() - t0) * 1000
        defects = postprocess(y[0])
        img_b64 = ""
        try:
            if cv2 is not None:
                _frame = x[0]
                _jpg = cv2.imencode('.jpg', cv2.cvtColor(_frame, cv2.COLOR_RGB2BGR))[1]
                img_b64 = base64.b64encode(_jpg.tobytes()).decode('ascii')
        except Exception:
            img_b64 = ""
        msg = {
            'frame': self.frame_id,
            'ok': len(defects) == 0,
            'defects': defects,
            'infer_ms': round(self.last_ms, 1),
            'w': 640, 'h': 640,
            'src': os.path.basename(path),
            'img_b64': img_b64,
        }
        return msg, path

    def _infer_pending(self):
        """检测 HMI 送来的照片（cmd=detect_img），返回 msg 或 None。

        与样本路径的区别：结果框坐标从 640 letterbox 空间**还原到原图空间**，
        img_b64 回传原图本体 —— HMI 画布显示的仍是用户打开的那张照片。
        letterbox 是左上角对齐（canvas[:nh,:nw]），无 padding 偏移，
        因此 x_orig = x640 / scale，scale = min(640/w0, 640/h0)。
        """
        item = self._pending_img
        if item is None:
            return None
        self._pending_img = None
        name, img_bgr = item
        h0, w0 = img_bgr.shape[:2]
        scale = min(640.0 / w0, 640.0 / h0) if (w0 and h0) else 1.0
        lb = letterbox(img_bgr)
        x = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB)[np.newaxis, ...].astype(np.uint8)
        t0 = time.time()
        try:
            y = self.rknn.inference(inputs=[x])
        except Exception as e:
            print('送检推理异常:', e)
            return None
        self.last_ms = (time.time() - t0) * 1000
        defects = postprocess(y[0])
        for d in defects:
            d['x1'] = round(min(max(d['x1'] / scale, 0), w0), 1)
            d['y1'] = round(min(max(d['y1'] / scale, 0), h0), 1)
            d['x2'] = round(min(max(d['x2'] / scale, 0), w0), 1)
            d['y2'] = round(min(max(d['y2'] / scale, 0), h0), 1)
        img_b64 = ''
        try:
            ok_j, jpg = cv2.imencode('.jpg', img_bgr)
            if ok_j:
                img_b64 = base64.b64encode(jpg.tobytes()).decode('ascii')
        except Exception:
            img_b64 = ''
        return {
            'frame': self.frame_id,
            'ok': len(defects) == 0,
            'defects': defects,
            'infer_ms': round(self.last_ms, 1),
            'w': w0, 'h': h0,
            'src': name,
            'mode': 'img',           # 标记送检回传：HMI 据此保持画布缩放
            'img_b64': img_b64,
        }

    def _infer_loop_step(self):
        """step 模式：收到 cmd=next 才检测一张；cmd=reset 回到第一张。
        送检照片（cmd=detect_img）优先级最高，到货即测，无需等 next。"""
        while True:
            # 先处理 reset（优先级高于 next）
            if self._reset_evt.is_set():
                self._reset_evt.clear()
                self.frame_id = 0
                print('已重置到第一张')
            msg = self._infer_pending()
            if msg is not None:
                self.broadcast(msg)
                self.broadcast(self.npu_stats())
                print('送检 %s  缺陷 %d 个  %.1f ms'
                      % (msg['src'], len(msg['defects']), self.last_ms), flush=True)
                self.frame_id += 1
                continue
            if not self._next_evt.is_set():
                self._next_evt.wait(timeout=0.5)
                continue
            self._next_evt.clear()
            msg, path = self._infer_one()
            if msg is None:
                continue
            self.broadcast(msg)
            print('step frame %d  %s  缺陷 %d 个  %.1f ms'
                  % (self.frame_id, os.path.basename(path),
                     len(msg['defects']), self.last_ms), flush=True)
            # 每张都附带一次 NPU 状态，便于上位机刷新
            self.broadcast(self.npu_stats())
            self.frame_id += 1

    def _infer_loop_stream(self):
        print('推理线程启动')
        while True:
            msg = self._infer_pending()
            if msg is not None:
                self.broadcast(msg)
                self.broadcast(self.npu_stats())
                print('送检 %s  缺陷 %d 个  %.1f ms'
                      % (msg['src'], len(msg['defects']), self.last_ms), flush=True)
                self.frame_id += 1
                continue
            if not self.samples:
                time.sleep(2)
                self.load_samples()
                continue
            path = self.samples[self.frame_id % len(self.samples)]
            x = self.read_sample(path)
            if x is None:
                self.frame_id += 1
                continue
            t0 = time.time()
            try:
                y = self.rknn.inference(inputs=[x])
            except Exception as e:
                print('推理异常:', e)
                time.sleep(1)
                continue
            self.last_ms = (time.time() - t0) * 1000
            defects = postprocess(y[0])
            # 编码当前帧为 JPEG(base64) 随结果下发，供 HMI 显示真实图像
            img_b64 = ""
            try:
                if cv2 is not None:
                    _frame = x[0]
                    _jpg = cv2.imencode('.jpg', cv2.cvtColor(_frame, cv2.COLOR_RGB2BGR))[1]
                    img_b64 = base64.b64encode(_jpg.tobytes()).decode('ascii')
            except Exception:
                img_b64 = ""
            msg = {
                'frame': self.frame_id,
                'ok': len(defects) == 0,
                'defects': defects,
                'infer_ms': round(self.last_ms, 1),
                'w': 640, 'h': 640,
                'src': os.path.basename(path),
                'img_b64': img_b64,
            }
            self.broadcast(msg)
            if self.frame_id % 10 == 0:
                self.broadcast(self.npu_stats())
                print('frame %d  %s  缺陷 %d 个  %.1f ms'
                      % (self.frame_id, os.path.basename(path),
                         len(defects), self.last_ms), flush=True)
            self.frame_id += 1
            time.sleep(0.02)

    def _client_reader(self, c):
        """每个客户端的读线程：解析控制指令（cmd=next/reset）。
        stream 模式下指令被忽略（本来就是连续推）；step 模式下驱动逐张推理。"""
        buf = b""
        try:
            while True:
                chunk = c.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8", "ignore"))
                    except Exception:
                        continue
                    cmd = obj.get("cmd") if isinstance(obj, dict) else None
                    if cmd == "next":
                        if MODE == 'step':
                            self._next_evt.set()
                    elif cmd == "reset":
                        if MODE == 'step':
                            self._reset_evt.set()
                    elif cmd == "detect_img":
                        # HMI 送检照片：base64 图片 → 解码 → 交推理线程（任何模式都支持）
                        name = str(obj.get("name") or 'photo.jpg')[:80]
                        try:
                            raw = base64.b64decode(obj.get("img") or '')
                            img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8),
                                               cv2.IMREAD_COLOR)
                        except Exception:
                            img = None
                        if img is None:
                            print('送检图片解码失败:', name, flush=True)
                        else:
                            self._pending_img = (name, img)
                            self._next_evt.set()
                            print('收到送检图片: %s (%dx%d)'
                                  % (name, img.shape[1], img.shape[0]), flush=True)
        except Exception:
            pass

    def serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('0.0.0.0', self.port))
        srv.listen(8)
        print('监听 0.0.0.0:%d (模式: %s)' % (self.port, MODE), flush=True)

        # 启动独立发送线程（短超时，绝不阻塞）
        threading.Thread(target=self._sender_loop, daemon=True).start()
        # 启动推理循环
        threading.Thread(target=self.infer_loop, daemon=True).start()

        while True:
            c, addr = srv.accept()
            print('客户端接入:', addr, flush=True)
            c.settimeout(None)        # 接收用阻塞读，不超时；发送由发送线程短超时
            with self.lock:
                self.clients.append(c)
            # 每个客户端开一个读线程，接收控制指令
            threading.Thread(target=self._client_reader, args=(c,), daemon=True).start()
            # 首屏统计走队列，绝不在 accept 线程里 sendall
            self.broadcast(self.npu_stats())


if __name__ == '__main__':
    print('=' * 60)
    print('RK3588 板端 NPU 推理服务')
    print('模型:', MODEL, ' 端口:', PORT)
    print('=' * 60)
    srv = BoardServer(MODEL, PORT)
    srv.load_samples()
    srv.init_npu()
    srv.serve()
