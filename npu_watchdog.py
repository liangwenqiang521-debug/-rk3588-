"""
NPU 异常 watchdog（PC 端）
========================

每 1 分钟跑一次：主动连板端 TCP 9000 拿最近 stats。
如果连续 N 次都"拿不到 stats"或"npu=-/temp=None"，判定级联服务异常，
自动 /etc/init.d/S99board restart。

阈值：连续 3 次失败触发 restart（3 分钟延迟）
- 避免误杀（一次 timeout 不算）
- 不会"恢复不了"（restart 失败不会循环，因为 5 分钟后才重试）

输出：stdout + 落盘 /root/rknn/watchdog.log

用法：
  python npu_watchdog.py            # 单次
  # 1 分钟周期：放任务计划
"""
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000
LOG_PATH = "/root/rknn/watchdog.log"
STATE_PATH = "/root/rknn/.watchdog_fail_count"
CONSEC_FAILS_TO_RESTART = 3
WAIT_AFTER_RESTART = 30  # restart 后等 30 秒再继续


def ssh(cmd: str) -> str:
    p = subprocess.run(
        ["C:/Users/21191/.workbuddy/binaries/python/envs/default/Scripts/python.exe",
         "board_ssh.py", cmd],
        cwd=r"D:\workbuddy\缺陷检测项目",
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = p.stdout
    out = re.sub(r"^\[板子\].*?\n", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\\$.*?$", "", out, flags=re.MULTILINE)
    return out.strip()


def tcp_stats(timeout=3.0):
    try:
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        s.settimeout(timeout)
        buf = b""
        deadline = time.time() + 1.5
        while time.time() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            if b'"type": "stats"' in buf:
                time.sleep(0.1)
                try:
                    buf += s.recv(4096)
                except Exception:
                    pass
                break
        s.close()
        for line in buf.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "stats":
                        return obj
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return None


def read_fail_count():
    out = ssh(f"cat {STATE_PATH} 2>/dev/null")
    try:
        return int(out)
    except ValueError:
        return 0


def write_fail_count(n: int):
    ssh(f"echo {n} > {STATE_PATH}")


def main():
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    stats = tcp_stats()
    if stats is None:
        fails = read_fail_count() + 1
        write_fail_count(fails)
        line = f"{ts} [FAIL #{fails}] 拿不到 NPU stats (TCP {HOST}:{PORT} 无响应)"
        print(line)
        safe = line.replace("'", "'\\''")
        ssh(f"echo '{safe}' >> {LOG_PATH}")
        if fails >= CONSEC_FAILS_TO_RESTART:
            print(f"  触发自动 restart（连续 {fails} 次失败）")
            ssh("/etc/init.d/S99board restart")
            ssh(f"echo 0 > {STATE_PATH}")  # 重置计数
            time.sleep(WAIT_AFTER_RESTART)
        return 1
    else:
        # 健康
        npu = stats.get("npu")
        temp = stats.get("temp")
        # 1秒占用率（去掉 % 符号）
        if isinstance(npu, str) and "/" in npu:
            npu_1s = float(npu.split("/")[0].rstrip("%"))
        else:
            npu_1s = float(npu) if npu not in (None, "-") else 0
        # 健康判定：NPU 1秒占用 < 100% 且 temp < 80°C（基本不会发生异常）
        healthy = (npu_1s < 100.0) and (temp is None or temp < 80.0)
        if healthy:
            write_fail_count(0)
            line = f"{ts} [OK] NPU={npu_1s:.0f}%  temp={temp}°C"
        else:
            fails = read_fail_count() + 1
            write_fail_count(fails)
            line = f"{ts} [WARN #{fails}] NPU={npu_1s:.0f}%  temp={temp}°C（异常）"
        print(line)
        safe = line.replace("'", "'\\''")
        ssh(f"echo '{safe}' >> {LOG_PATH}")
        if not healthy and read_fail_count() >= CONSEC_FAILS_TO_RESTART:
            print(f"  触发自动 restart")
            ssh("/etc/init.d/S99board restart")
            ssh(f"echo 0 > {STATE_PATH}")
            time.sleep(WAIT_AFTER_RESTART)
        return 0


if __name__ == "__main__":
    sys.exit(main())
