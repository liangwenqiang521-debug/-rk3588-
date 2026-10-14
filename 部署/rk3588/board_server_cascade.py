# -*- coding: utf-8 -*-
"""RK3588 板端 NPU 推理服务（TCP 9000）

09-10-09 现状：**默认单模型**，主力 = 39 类钢材表面缺陷模型 best_steel39_640.rknn。
  单模型模式（默认）：只跑主模型，直接输出 39 类缺陷框。
  ⚠️ 旧的双模型级联（negdagm 过滤器 + 6 类主力）已不用于 39 类，原因：
     negdagm 过滤器只认 NEU 6 类，做 39 类的「有无缺陷」闸门会漏判其余 33 类。
  需要回到 NEU 6 类级联时，启动加 `--filter`：
     python3 board_server_cascade.py 9000 --filter
     （此时 NAMES/PER_CLASS_THRES 也要一并改回 6 类口径）

级联模式（--filter）原本的策略，供参考：
  - 过滤器模型 = negdagm（负样本重训）：对无缺陷图 0% 误检，但真实缺陷 top1 95.6%
  - 判类主力模型 = _640（基线）：真实缺陷 top1 97.8%，但无缺陷图 64.4% 误检

启动: python3 /root/rknn/board_server_cascade.py [port] [--filter]

协议（逐行 JSON，UTF-8 + \n，与 board_server.py 完全一致）：
  检测结果: {"frame":12,"ok":false,
             "defects":[{"cls":"dent","conf":0.93,"x1":120,"y1":80,"x2":210,"y2":175}],
             "infer_ms":8.2,"w":640,"h":640}
  NPU状态 : {"type":"stats", ...}
"""
import os, sys, json, time, socket, threading, glob, base64

import numpy as np

WORK = '/root/rknn'
SAMPLES = os.path.join(WORK, 'samples')
# 缺陷类别表。
# 前 6 项顺序必须与 best_neu6_640.rknn 导出时的 names 严格一致（NEU-DET），勿动；
# 09-21 扩展了工业常见类与表面处理类，供「扩类模型」直接复用本服务：
#   若加载的是扩类 rknn，把 NAMES 整体换成扩类 names（顺序同导出时）即可，
#   协议与上位机零改动（上位机按索引取中文名，未登记的名字原样显示）。
# 39 类工业钢材表面缺陷全集，来源 缺陷检测扩展/data.yaml（production v2.1）。
# 顺序 = data.yaml 的 ids = 模型输出索引，与上位机 infer.CLASSES_39 严格一致，勿改顺序。
NAMES_EXT = [
    'bright_scratch', 'crazing', 'crease', 'crescent_gap', 'dark_scratches',
    'finishing_roll_printing', 'inclusion', 'iron_scale_compression', 'iron_sheet_ash',
    'oil_spot', 'oxide_scale_plate', 'oxide_scale_temp', 'patches', 'pitted_surface',
    'punching', 'red_iron_sheet', 'rolled-in_scale', 'rolled_pit', 'secondary_rust_skin',
    'silk_spot', 'slag_inclusion', 'waist_folding', 'water_spot', 'welding_line',
    'white_rust', 'cutting_opening', 'water_slag_mark', 'slag_skin', 'longitudinal_crack',
    'warp', 'external_fold', 'wrinkle', 'blocky_scale', 'striated_scale', 'foreign_obj',
    'blowhole', 'break', 'fray', 'uneven',
]

# 09-10-09：板端主力已切换为 39 类模型，NAMES 即模型输出索引顺序（勿动）。
NAMES = list(NAMES_EXT)

# 模型文件（都在 /root/rknn/ 下，绝对路径）
# negdagm 过滤器只认 NEU 6 类，拿它给 39 类做「有无缺陷」闸门会漏判其余 33 类，
# 故 39 类部署默认关闭过滤器（单模型）。需回到 NEU 6 类级联时启动加 --filter。
FILTER_MODEL = '/root/rknn/negdagm_filter.rknn'
MAIN_MODEL    = '/root/rknn/best_steel39_640.rknn'
if '--filter' not in sys.argv:
    FILTER_MODEL = None

PORT = next((int(a) for a in sys.argv[1:] if a.isdigit()), 9000)

# per-class 阈值表。空 = 全部回落到 CONF_THRES。
# 09-10-09：旧值是 NEU 6 类 cal 集扫出来的，对 39 类未标定，故清空；
# 待 39 类 cal 集标定后再填（键名用 NAMES_EXT 里的 snake_case）。
PER_CLASS_THRES = {}
CONF_THRES = 0.20
IOU_THRES = 0.45

# 运行模式（09-21 改默认值）：
#   'step'   ：按需检测（默认）——只在上位机发 cmd=next 时才推一帧，不主动循环
#   'stream' ：自循环（旧行为）——24 张 sample 无限轮播，5 FPS 不停推帧
# 默认改为 step 的原因：stream 模式会让上位机画面永远在动、且持续写库，
# 真实产线场景应当是"相机来一帧 → 推一帧"的按需模式。
MODE = 'stream' if '--stream' in sys.argv else 'step'

from rknnlite.api import RKNNLite

try:
    import cv2
except ImportError:
    cv2 = None
    print('警告: 无 cv2，仅支持 .npy 样本')


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
    """out: (1, 4+nc, 8400) -> defects list。类别通道已是概率，勿再套 sigmoid。"""
    pred = np.array(out)[0].T
    boxes = pred[:, :4]
    cls_sc = pred[:, 4:]
    conf = cls_sc.max(axis=1)
    cls_id = cls_sc.argmax(axis=1)
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


class BoardServerCascade:
    def __init__(self, port):
        self.port = port
        self.clients = []
        self.lock = threading.Lock()
        self.frame_id = 0
        self.rknn_filter = None   # 过滤器：negdagm
        self.rknn_main = None     # 判类主力：_640
        self.samples = []
        self.last_ms = 0.0
        self._send_q = []
        self._wake = threading.Event()
        self._stop_sender = False
        self._next_evt = threading.Event()
        self._reset_evt = threading.Event()
        self._pending_img = None

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
            if a.ndim == 4 and a.shape[1] == 3:
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

    def _init_one(self, model_path, tag):
        """加载单个 RKNN 模型，返回 RKNNLite 实例。"""
        rk = RKNNLite(verbose=False)
        ret = rk.load_rknn(model_path)
        if ret != 0:
            raise RuntimeError('load_rknn(%s) failed, ret=%d' % (tag, ret))
        ret = rk.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
        if ret != 0:
            raise RuntimeError('init_runtime(%s) failed, ret=%d' % (tag, ret))
        print('NPU 就绪 [%s]: %s' % (tag, model_path))
        return rk

    def init_npu(self):
        """加载模型。FILTER_MODEL 为 None 时只加载主模型（单模型模式，39 类用）。"""
        if FILTER_MODEL:
            self.rknn_filter = self._init_one(FILTER_MODEL, 'filter/negdagm')
        else:
            self.rknn_filter = None
            print('单模型模式：跳过过滤器，只用主模型')
        self.rknn_main = self._init_one(MAIN_MODEL, 'main/steel39')

    def _cascade_infer(self, x):
        """推理入口。返回 (defects, filter_ms, total_ms)。
        单模型模式（39 类）：直接跑主模型；
        级联模式（--filter，NEU 6 类）：先 negdagm 判有无缺陷，有缺陷再精判。"""
        if self.rknn_filter is None:
            t0 = time.time()
            y = self.rknn_main.inference(inputs=[x])
            ms = (time.time() - t0) * 1000
            self.last_ms = ms
            return postprocess(y[0]), 0.0, ms
        # 第一步：过滤器（negdagm）判有无缺陷
        t0 = time.time()
        y = self.rknn_filter.inference(inputs=[x])
        filter_ms = (time.time() - t0) * 1000
        filter_defects = postprocess(y[0])
        if len(filter_defects) == 0:
            # 过滤器判「无缺陷」，直接返回，不跑主力
            self.last_ms = filter_ms
            return [], filter_ms, filter_ms
        # 第二步：有缺陷，用 _640 精判类别
        t1 = time.time()
        y2 = self.rknn_main.inference(inputs=[x])
        main_ms = (time.time() - t1) * 1000
        main_defects = postprocess(y2[0])
        total_ms = filter_ms + main_ms
        self.last_ms = total_ms
        return main_defects, filter_ms, total_ms

    def broadcast(self, obj):
        if self._stop_sender:
            return
        with self.lock:
            self._send_q.append(obj)
        self._wake.set()

    def _sender_loop(self):
        while not self._stop_sender:
            self._wake.wait(timeout=0.2)
            self._wake.clear()
            batch = []
            with self.lock:
                if self._send_q:
                    batch = self._send_q
                    self._send_q = []
            if not batch:
                continue
            payloads = []
            for obj in batch:
                try:
                    payloads.append((json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8'))
                except Exception:
                    payloads.append(b'')
            dead = []
            with self.lock:
                clients = list(self.clients)
            for c in clients:
                # 09-21 修：原来 settimeout(0.3) + 超时即判死，是 step 模式"推
                # 一两帧就再也不动"的根因——每帧 img_b64 几百 KB，上位机只要
                # 稍微读慢一点，板端 0.3s 没发完就把客户端当死连接 close 掉；
                # 之后上位机发的 cmd=next 全部落空（sendall 仍返回成功，极难排查）。
                # 现在：只有真正的连接级错误才判死，超时只丢弃本轮、保留连接。
                try:
                    c.settimeout(5.0)
                    for data in payloads:
                        if not data:
                            continue
                        c.sendall(data)
                except TimeoutError:
                    print('[发送超时] 本轮丢弃，保留客户端', flush=True)
                except (BrokenPipeError, ConnectionResetError):
                    dead.append(c)
                except OSError:
                    dead.append(c)
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
        # 09-20 修：优先找 NPU/GPU/SoC 温度（按 type 名匹配），没有再回退到 zone0
        # 这块 ATK-DLRK3588 板子的 thermal zone 实际是 soc-thermal（SoC 包含 CPU+NPU），
        # 没有独立的 npu-thermal，所以 soc-thermal 是 NPU 工作温度的合理代理
        temp = None
        npu_zone = None
        cpu_zone = None
        for p in glob.glob('/sys/class/thermal/thermal_zone*/type'):
            try:
                tname = open(p).read().strip().lower()
                if 'npu' in tname or 'gpu' in tname or 'soc' in tname:
                    npu_zone = p.replace('/type', '/temp')
                elif 'cpu' in tname and cpu_zone is None:
                    cpu_zone = p.replace('/type', '/temp')
            except Exception:
                pass
        target = npu_zone or cpu_zone
        if target:
            try:
                t = int(open(target).read().strip())
                temp = t / 1000.0 if t > 1000 else float(t)
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
            'core0': cores[0], 'core1': cores[1], 'core2': cores[2],
            'npu': load,
            'temp': temp,
            'mem_used': mem_used,
            'mem_total': mem_total,
            'mem_available': mem_avail,
            'fps': round(1000.0 / self.last_ms, 1) if self.last_ms > 0 else 0,
            'infer_ms': round(self.last_ms, 1),
            'model': 'cascade(negdagm+steel39)' if self.rknn_filter else 'single(steel39)',
        }

    def infer_loop(self):
        print('推理线程启动（模式: %s）' % MODE)
        if MODE == 'stream':
            self._infer_loop_stream()
        else:
            self._infer_loop_step()

    def _infer_one(self):
        if not self.samples:
            self.load_samples()
        if not self.samples:
            return None, None
        path = self.samples[self.frame_id % len(self.samples)]
        x = self.read_sample(path)
        if x is None:
            self.frame_id += 1
            return None, None
        defects, fms, tms = self._cascade_infer(x)
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
            'infer_ms': round(tms, 1),
            'w': 640, 'h': 640,
            'src': os.path.basename(path),
            'img_b64': img_b64,
        }
        return msg, path

    def _infer_pending(self):
        item = self._pending_img
        if item is None:
            return None
        self._pending_img = None
        name, img_bgr = item
        h0, w0 = img_bgr.shape[:2]
        scale = min(640.0 / w0, 640.0 / h0) if (w0 and h0) else 1.0
        lb = letterbox(img_bgr)
        x = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB)[np.newaxis, ...].astype(np.uint8)
        defects, fms, tms = self._cascade_infer(x)
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
            'infer_ms': round(tms, 1),
            'w': w0, 'h': h0,
            'src': name,
            'mode': 'img',
            'img_b64': img_b64,
        }

    def _infer_loop_step(self):
        # 09-21 加：推理主循环包一层保护。此前任何一次异常（读图/NPU/编码）
        # 都会让整个 while True 静默退出 —— 表现为"推几帧后再也不动"，
        # 客户端还连着、端口还 LISTEN，极难排查。
        while True:
            try:
                self._infer_loop_step_once()
            except Exception as e:
                print('[推理循环异常] %s: %s' % (type(e).__name__, e), flush=True)
                import time as _t
                _t.sleep(0.5)

    def _infer_loop_step_once(self):
        while True:
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
            self.broadcast(self.npu_stats())
            self.frame_id += 1

    def _infer_loop_stream(self):
        print('推理线程启动（级联）')
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
            defects, fms, tms = self._cascade_infer(x)
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
                'infer_ms': round(tms, 1),
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
                    # 09-21 调试：打印收到的指令，确认上位机 cmd=next 是否到达板端
                    print('[cmd] %r' % (cmd,), flush=True)
                    if cmd == "next":
                        if MODE == 'step':
                            self._next_evt.set()
                    elif cmd == "reset":
                        if MODE == 'step':
                            self._reset_evt.set()
                    elif cmd == "detect_img":
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
        print('监听 0.0.0.0:%d (模式: %s, 级联)' % (self.port, MODE), flush=True)

        threading.Thread(target=self._sender_loop, daemon=True).start()
        threading.Thread(target=self.infer_loop, daemon=True).start()

        while True:
            c, addr = srv.accept()
            print('客户端接入:', addr, flush=True)
            c.settimeout(None)
            with self.lock:
                self.clients.append(c)
            threading.Thread(target=self._client_reader, args=(c,), daemon=True).start()
            self.broadcast(self.npu_stats())
            # 09-21 加：step 模式下客户端接入后不主动推帧会黑屏，
            # 因此接入瞬间补推一帧（让上位机立刻有画面），之后等 cmd=next 才推下一张。
            if MODE == 'step':
                self._next_evt.set()


if __name__ == '__main__':
    print('=' * 60)
    print('RK3588 板端 NPU 推理服务（双模型级联）')
    print('过滤器: %s' % FILTER_MODEL)
    print('判类主力: %s' % MAIN_MODEL)
    print('端口:', PORT)
    print('模式: %s %s' % (MODE,
          '（按需：等 cmd=next 才推帧，默认）' if MODE == 'step'
          else '（自循环：24 张 sample 无限轮播）'))
    print('=' * 60)
    srv = BoardServerCascade(PORT)
    srv.load_samples()
    srv.init_npu()
    srv.serve()
