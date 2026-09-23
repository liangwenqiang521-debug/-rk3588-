# -*- coding: utf-8 -*-
"""RK3588 NPU 监控后端：
- SerialBackend：通过串口控制台直连板端 root shell，正则解析输出
- DemoBackend：模拟数据（无板子时调试用）
- NpuWorker：QThread 周期采样，向 UI 发信号
"""
import re
import time
import random
import threading
from collections import deque

from PyQt5.QtCore import QThread, pyqtSignal

LOAD_RE = re.compile(r"Core0:\s*(\d+)%,\s*Core1:\s*(\d+)%,\s*Core2:\s*(\d+)%")
TEMP_RE = re.compile(r"^\s*(\d{4,6})\s*$", re.M)
MEM_RE = re.compile(r"Mem:\s+(\d+)\s+(\d+)\s+(\d+)")


class SerialBackend(object):
    """串口直连板端 shell（要求对端已是 root 提示符，且独占 COM 口）"""

    def __init__(self, port="COM3", baud=1500000):
        import serial
        self.ser = serial.Serial(port, baud, bytesize=8, parity="N",
                                 stopbits=1, timeout=0.1)
        self.lock = threading.Lock()
        # 确保 debugfs 已挂载
        self._raw("mount -t debugfs none /sys/kernel/debug 2>/dev/null")
        time.sleep(0.3)
        self._drain()

    def _raw(self, cmd):
        self.ser.write(cmd.encode() + b"\r\n")

    def _drain(self):
        try:
            self.ser.read(65535)
        except Exception:
            pass

    def _query(self, cmd, pattern, timeout=2.0):
        """发命令，收输出，返回 pattern 的最后一组匹配"""
        with self.lock:
            self._drain()
            self._raw(cmd)
            buf = b""
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    chunk = self.ser.read(4096)
                except Exception:
                    break
                if chunk:
                    buf += chunk
                    m = pattern.findall(buf.decode("utf-8", "ignore"))
                    if m:
                        return m[-1]
                time.sleep(0.05)
            m = pattern.findall(buf.decode("utf-8", "ignore"))
            return m[-1] if m else None

    def sample(self):
        """返回 dict: core0/1/2(%), temp(℃), mem_used/total(MB) ；失败返回 None"""
        load = self._query("cat /sys/kernel/debug/rknpu/load", LOAD_RE)
        if not load:
            return None
        temp_m = self._query("cat /sys/class/thermal/thermal_zone0/temp", TEMP_RE)
        mem_m = self._query("free", MEM_RE)
        # 单分组 findall 返回字符串，多分组返回元组，统一处理
        temp_raw = temp_m if isinstance(temp_m, str) else (temp_m[0] if temp_m else None)
        return {
            "core0": int(load[0]), "core1": int(load[1]), "core2": int(load[2]),
            "temp": (int(temp_raw) / 1000.0) if temp_raw else None,
            "mem_used": (int(mem_m[1]) / 1024.0) if mem_m else None,
            "mem_total": (int(mem_m[0]) / 1024.0) if mem_m else None,
        }

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


class DemoBackend(object):
    """模拟数据后端
    - 用一个慢正弦驱动基线，避免肉眼看不到变化
    - 周期性地做一次"推理脉冲"，让三核瞬间冲到 85~95%，效果像真在跑模型
    - 同时输出 fps / infer_ms，让 UI 不再有 '--'
    """
    def __init__(self):
        self._t = 0
        self._pulse_left = 0  # >0 表示脉冲进行中（再持续 N 次采样）
        self._pulse_target = 0  # 脉冲期间三核均值

    def sample(self):
        self._t += 1
        # ---- 决定三核基线 + 是否进入脉冲 ----
        # 触发脉冲：每 ~15 次随机来一次，模拟"接到一帧图"
        if self._pulse_left <= 0 and random.random() < 0.15 and self._t > 5:
            self._pulse_left = 4 + random.randint(0, 3)      # 持续 4~7 次采样 (~2-3.5 秒)
            self._pulse_target = 88 + random.randint(0, 8)   # 脉冲峰值 88~96%
        in_pulse = self._pulse_left > 0
        if in_pulse:
            self._pulse_left -= 1

        # 正弦基线（中心 45、幅度 ±20 → 25~65 区间慢呼吸）
        import math
        base_mid = 45 + 20 * math.sin(self._t * 0.35)

        if in_pulse:
            base_mid = (base_mid + self._pulse_target) / 2.0

        # 三核略不齐（小抖动 + 互相错相位）
        phase = [0.0, 0.7, 1.4]
        per_core = []
        for i in range(3):
            jitter = random.uniform(-6, 6)
            v = base_mid + 4 * math.sin(self._t * 0.35 + phase[i]) + jitter
            per_core.append(max(0, min(99, int(v))))

        # ---- 派生字段 ----
        if in_pulse:
            # 脉冲期：fps 较低（推理慢），单帧较高
            fps = random.uniform(8.0, 12.0)
            infer_ms = random.uniform(85.0, 125.0)
        else:
            fps = random.uniform(0.0, 1.5)        # 空闲期近乎 0
            infer_ms = random.uniform(0.0, 1.2)

        return {
            "core0": per_core[0], "core1": per_core[1], "core2": per_core[2],
            "temp": 44.0 + 4.0 * math.sin(self._t * 0.12) + random.uniform(-0.6, 0.6),
            "mem_used": 1420.0 + 80.0 * math.sin(self._t * 0.2) + random.uniform(-15, 15),
            "mem_total": 8192.0,
            "fps": fps, "infer_ms": infer_ms,
        }

    def close(self):
        pass


class NpuWorker(QThread):
    """周期采样线程"""
    sample_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, backend, interval=1.0, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.interval = max(0.05, float(interval))  # 防 0 / 负数
        self._running = True
        self._cancelled = False  # 立即退出信号

    def run(self):
        # 把 msleep 拆成 100ms 小段，stop() 能在 100ms 内生效，
        # 避免最后一帧 sample 写回已清空的 UI
        step_ms = 100
        elapsed = 0
        total_ms = int(self.interval * 1000)
        while self._running and not self._cancelled:
            if elapsed >= total_ms:
                try:
                    data = self.backend.sample()
                    if data:
                        self.sample_ready.emit(data)
                    else:
                        self.error.emit("读取失败：未解析到 NPU 负载数据")
                except Exception as e:
                    self.error.emit("采样异常: %s" % e)
                elapsed = 0
            self.msleep(step_ms)
            elapsed += step_ms

    def stop(self):
        self._cancelled = True
        self._running = False
        self.wait(2000)  # 等线程真死再让调用方清空 UI，杜绝竞态
        try:
            self.backend.close()
        except Exception:
            pass


class LoadHistory(object):
    """保存最近 N 次采样供曲线绘制"""
    def __init__(self, maxlen=90):
        self.core0 = deque(maxlen=maxlen)
        self.core1 = deque(maxlen=maxlen)
        self.core2 = deque(maxlen=maxlen)

    def push(self, d):
        d = normalize_stats(d)
        self.core0.append(d["core0"])
        self.core1.append(d["core1"])
        self.core2.append(d["core2"])


def normalize_stats(d):
    """把板端不同版本的 stats 帧归一化为统一字段（core0/1/2 + mem_used/total）。

    板端现在有两套协议在混用，上位机接入其中任一都不能崩：
      A) 串口 board_infer.py: {"core0":45,"core1":30,"core2":12,
                               "temp":48.5,"mem_used":1520.0,"mem_total":8192.0}
      B) TCP  board_server.py: {"npu":"42/7/8%","temp":45.2,
                               "mem_avail_mb":512,"fps":15.3,"infer_ms":65.4}
    归一化后输出 *新 dict*，缺失字段补 None/0。
    """
    out = dict(d)

    # NPU 三核负载：A 直接取；B 解析 "42/7/8%"
    if all(k in d for k in ("core0", "core1", "core2")):
        cores = [d["core0"], d["core1"], d["core2"]]
    else:
        v = d.get("npu")
        nums = []
        if isinstance(v, (list, tuple)):
            nums = list(v)
        elif isinstance(v, str):
            nums = re.findall(r"\d+(?:\.\d+)?", v)
        try:
            nums = [int(float(x)) for x in nums[:3]]
        except Exception:
            nums = []
        if not nums:
            nums = [0, 0, 0]
        while len(nums) < 3:
            nums.append(0)
        cores = nums[:3]
    out["core0"], out["core1"], out["core2"] = cores[0], cores[1], cores[2]

    # 内存：A 已有 used/total；B 只有 avail，没有 total → 留 None
    if "mem_used" not in out or out.get("mem_used") is None:
        if d.get("mem_used") is None and d.get("mem_avail_mb") is not None:
            out["mem_available"] = d["mem_avail_mb"]
    return out
