# -*- coding: utf-8 -*-
"""RK3588 板端模拟器（协议级替身）

作用
--------------------------------------------------------------------
在没有真实 RK3588 板子时，用本机的一个 TCP 服务**完整顶替板端 board_infer.py**，
让上位机走**完全真实的收发链路**（socket 连接 → 逐行 JSON → 桥接线程 → 分流渲染）。

与"上位机内部模拟数据"的本质区别：
  · 内部模拟：数据直接在 UI 里造，桥接/解析/分流全被绕过 —— 验证不了链路
  · 本模拟器：数据从真实的 TCP socket 出去，上位机用真桥接线程接收解析
    → 链路 100% 真实，真板子到位时**只需把 IP 换掉，上位机零改动**

协议与 模型训练/board_infer.py 逐字段一致：
  状态（每 1s）：
    {"type":"stats","core0":45,"core1":30,"core2":12,"temp":48.5,
     "mem_used":1520.0,"mem_total":8192.0,"fps":62.3,"infer_ms":8.1}
  检测（按 fps）：
    {"frame":12,"ok":false,"infer_ms":8.2,"w":640,"h":640,
     "defects":[{"cls":"scratches","conf":0.93,
                 "x1":120,"y1":80,"x2":210,"y2":175}]}

用法
--------------------------------------------------------------------
    python 板端模拟器.py                    # 监听 0.0.0.0:9000
    python 板端模拟器.py --port 9001        # 换端口
    python 板端模拟器.py --fps 15           # 调推理帧率
    python 板端模拟器.py --ng-rate 0.4      # 40% 的帧有缺陷

启动后在上位机：
  · NPU 监控页 → 数据来源「板端TCP」→ 地址填下面打印的 IP → 端口 9000 → 连接
  · 检测页     → 边缘模式「网络(TCP)」→ 同上地址端口 → 启动
"""

import argparse
import json
import math
import random
import socket
import sys
import threading
import time

# 缺陷类别表（与 infer.py 的 NAME_ZH / 部署/rk3588 的 NAMES 保持一致）。
# 前 6 项为 NEU 真实 6 类；之后是 09-21 扩展的演示类别——
# 模拟器会在全部类里随机取，方便上位机演示时看到更丰富的缺陷分布。
CLASSES = [
    # ---- NEU-DET 六类真实缺陷 ----
    "crazing",          # 龟裂
    "inclusion",        # 夹杂物
    "patches",          # 斑块
    "pitted_surface",   # 麻面（点蚀）
    "rolled-in_scale",  # 轧入氧化皮
    "scratches",        # 划痕
    # ---- 工业常见扩展类 ----
    "edge_crack",       # 边裂
    "scab",             # 结疤
    "pitting",          # 点蚀
    "roll_mark",        # 辊印
    "wavy_edge",        # 边浪
    "oxide_scale",      # 氧化铁皮压入
    # ---- 表面处理类缺陷 ----
    "stain",            # 污渍
    "oil_spot",         # 油污
    "water_spot",       # 水渍
    "rust",             # 锈蚀
    # ---- 09-28 扩展：39 类体系新增类（来源 缺陷检测扩展/data.yaml）----
    "bright_scratch",           # 亮划痕
    "crease",                   # 折痕
    "crescent_gap",             # 月牙缺口
    "dark_scratches",           # 暗划痕
    "finishing_roll_printing",  # 精轧辊印
    "iron_scale_compression",   # 氧化铁皮压入
    "iron_sheet_ash",           # 铁皮灰
    "oxide_scale_plate",        # 板系氧化铁皮
    "oxide_scale_temp",         # 温系氧化铁皮
    "punching",                 # 冲孔
    "red_iron_sheet",           # 红斑铁皮
    "rolled_pit",               # 轧制凹坑
    "secondary_rust_skin",      # 二次锈皮
    "silk_spot",                # 丝斑
    "slag_inclusion",           # 夹渣
    "waist_folding",            # 腰部折痕
    "welding_line",             # 焊缝线
    "white_rust",               # 白锈
    "cutting_opening",          # 切边开口
    "water_slag_mark",          # 水渣痕
    "slag_skin",                # 渣皮
    "longitudinal_crack",       # 纵向裂纹
    "warp",                     # 翘曲
    "external_fold",            # 外折
    "wrinkle",                  # 褶皱
    "blocky_scale",             # 块状氧化铁皮
    "striated_scale",           # 条纹氧化铁皮
    "foreign_obj",              # 异物
    "blowhole",                 # 气孔
    "break",                    # 断裂
    "fray",                     # 散边毛刺
    "uneven",                   # 厚薄不均
]

IMG_W, IMG_H = 640, 640


def local_ips():
    """列出本机可被板子/上位机访问到的 IPv4 地址。"""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips


class NpuSim(object):
    """模拟 RK3588 三核 NPU 的负载节奏。

    真实 NPU 在推理时三核会被同时拉高，任务间有短暂回落；
    这里用「正弦呼吸基线 + 随机推理脉冲」逼近这个形态：
      · 空闲：三核 5~25%，温度缓慢下降到 ~42℃
      · 推理脉冲：三核 85~97%（三核错峰，core2 略低），温度随负载爬升
      · 内存：随推理小幅上涨，回落缓慢
    """

    def __init__(self):
        self.t = 0.0
        self.temp = 42.0
        self.mem = 1450.0
        self.mem_total = 8192.0
        self.pulse_left = 0          # 剩余推理脉冲次数
        self.infer_ms = 0.6
        self.frame_count = 0
        self._fps_t0 = time.time()

    def note_frame(self, infer_ms):
        self.frame_count += 1
        self.infer_ms = infer_ms

    def step(self, dt):
        self.t += dt
        # 推理脉冲：约 18% 概率触发，持续 4~8 步
        if self.pulse_left > 0:
            self.pulse_left -= 1
        elif random.random() < 0.18:
            self.pulse_left = random.randint(4, 8)

        busy = self.pulse_left > 0
        # 呼吸基线：即使空闲也有轻微起伏，避免看着像死线
        breath = 8 + 6 * math.sin(self.t * 0.7)

        if busy:
            base = random.uniform(85, 97)
        else:
            base = breath + random.uniform(-3, 6)

        # 三核错峰：core0 最忙，core2 最闲（真实 NPU 层间流水不均）
        core0 = max(0, min(100, base + random.uniform(-4, 4)))
        core1 = max(0, min(100, base * 0.88 + random.uniform(-5, 5)))
        core2 = max(0, min(100, base * 0.72 + random.uniform(-6, 6)))

        avg = (core0 + core1 + core2) / 3.0
        # 温度向「42 + 负载贡献」缓慢逼近（热惯性）
        target = 42.0 + avg * 0.16
        self.temp += (target - self.temp) * 0.08 + random.uniform(-0.2, 0.2)
        self.temp = max(38.0, min(88.0, self.temp))

        # 内存：推理时涨，空闲缓慢回收
        self.mem += (1620 - self.mem) * 0.05 + (random.uniform(-12, 20) if busy else -6)
        self.mem = max(1100.0, min(self.mem_total * 0.75, self.mem))

        # FPS：从真实帧计数算
        now = time.time()
        el = now - self._fps_t0
        fps = self.frame_count / el if el > 0.2 else 0.0
        if el >= 1.0:
            self.frame_count = 0
            self._fps_t0 = now

        return {
            "type": "stats",
            "core0": int(round(core0)),
            "core1": int(round(core1)),
            "core2": int(round(core2)),
            "temp": round(self.temp, 1),
            "mem_used": round(self.mem, 1),
            "mem_total": self.mem_total,
            "fps": round(fps, 1),
            "infer_ms": round(self.infer_ms, 2),
        }


class SimBoard(object):
    """模拟 board_infer.py 的 TCP 服务端行为。"""

    def __init__(self, port, fps, ng_rate):
        self.port = port
        self.fps = fps
        self.ng_rate = ng_rate
        self.sock = None
        self.clients = []
        self.lock = threading.Lock()
        self.npu = NpuSim()
        self._running = True
        self.frame_id = 0

    # ---------------- 网络 ----------------
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.listen(8)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._frame_loop, daemon=True).start()
        threading.Thread(target=self._stats_loop, daemon=True).start()

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self.sock.accept()
            except Exception:
                break
            print("  ✅ 上位机接入: %s" % str(addr))
            with self.lock:
                self.clients.append(conn)

    def _broadcast(self, obj):
        line = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        dead = []
        with self.lock:
            for c in self.clients:
                try:
                    c.sendall(line)
                except Exception:
                    dead.append(c)
            for c in dead:
                self.clients.remove(c)
                print("  ⚠ 客户端断开: %s" % str(c.getpeername() if c.fileno() >= 0 else ""))

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass
        with self.lock:
            for c in self.clients:
                try:
                    c.close()
                except Exception:
                    pass

    # ---------------- 检测帧生成 ----------------
    def _make_frame(self):
        """生成一帧检测结果，形态逼近真实 YOLO 输出。"""
        self.frame_id += 1
        # 推理耗时：脉冲期 ~9ms（NPU 真跑），空闲期几乎为 0
        busy = self.npu.pulse_left > 0
        infer_ms = random.uniform(7.5, 12.0) if busy else random.uniform(0.4, 1.2)
        self.npu.note_frame(infer_ms)

        defects = []
        if random.random() < self.ng_rate:
            # 一次出 1~3 个缺陷，类别随机，框不超出画面
            for _ in range(random.randint(1, 3)):
                cls = random.choice(CLASSES)
                w = random.randint(40, 150)
                h = random.randint(35, 130)
                x1 = random.randint(10, IMG_W - w - 10)
                y1 = random.randint(10, IMG_H - h - 10)
                # 置信度集中在 0.55~0.97，贴近真实分布
                conf = round(random.uniform(0.55, 0.97), 3)
                defects.append({
                    "cls": cls, "conf": conf,
                    "x1": x1, "y1": y1,
                    "x2": x1 + w, "y2": y1 + h,
                })

        return {
            "frame": self.frame_id,
            "ok": len(defects) == 0,
            "infer_ms": round(infer_ms, 2),
            "w": IMG_W,
            "h": IMG_H,
            "defects": defects,
        }

    def _frame_loop(self):
        interval = 1.0 / max(1, self.fps)
        while self._running:
            t0 = time.time()
            obj = self._make_frame()
            if self.clients:
                self._broadcast(obj)
            dt = interval - (time.time() - t0)
            if dt > 0:
                time.sleep(dt)

    def _stats_loop(self):
        while self._running:
            time.sleep(1.0)
            st = self.npu.step(1.0)
            if self.clients:
                self._broadcast(st)


def main():
    ap = argparse.ArgumentParser(description="RK3588 板端模拟器（协议级替身）")
    ap.add_argument("--port", type=int, default=9000, help="监听端口，默认 9000")
    ap.add_argument("--fps", type=float, default=10.0, help="推理帧率，默认 10")
    ap.add_argument("--ng-rate", type=float, default=0.35, help="出缺陷帧比例，默认 0.35")
    args = ap.parse_args()

    print("=" * 66)
    print("  RK3588 板端模拟器 —— 协议级替身（非上位机内部模拟）")
    print("=" * 66)
    ips = local_ips()
    print("监听端口      : 0.0.0.0:%d" % args.port)
    print("推理帧率      : %.1f FPS      NG 比例: %.0f%%" % (args.fps, args.ng_rate * 100))
    print()
    print("在上位机里填这些地址之一：")
    print("   · 本机回环   127.0.0.1:%d   （同一台电脑测试用）" % args.port)
    for ip in ips:
        print("   · 局域网     %s:%d" % (ip, args.port))
    print()
    print("  · NPU 监控页 → 数据来源「板端TCP」→ 填上面地址 → 连接")
    print("  · 检测页     → 边缘模式「网络(TCP)」→ 同上 → 启动")
    print()
    print("按 Ctrl+C 停止")
    print("=" * 66)

    board = SimBoard(args.port, args.fps, args.ng_rate)
    board.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止中...")
        board.stop()
        print("已停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
