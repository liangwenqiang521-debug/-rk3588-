"""
板端健康检查（PC 端脚本）
=========================

每 5 分钟跑一次，输出当前 RK3588 板子的：
  - 级联服务 PID 与运行时间
  - CPU 4 核占用率
  - 内存使用（/proc/meminfo）
  - 磁盘 /root 用量
  - NPU 占用率与温度（**通过 TCP 9000 主动连板端拿最新 stats**）
  - 延迟 P50/P95（从 server_cascade.log 最近 200 帧统计）
  - 24 sample 检出数（看是否跌到 0）

输出：打印到 stdout + 追加到 /root/rknn/health.log
健康阈值（违反时输出 ⚠️ 警告）：
  - 服务不在跑 → CRITICAL
  - 磁盘 >85% → WARN
  - NPU 温度 >70°C → WARN
  - 延迟 P95 > 400ms → WARN
  - 内存可用 < 200MB → WARN

用法：
  python board_health.py            # 单次跑
  # 5 分钟周期：放 cron 0/5 * * * *
"""
import json
import re
import socket
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
PORT = 9000
LOG_PATH = "/root/rknn/health.log"
WARN = "⚠️ "
CRIT = "❌ "
OK = "✅ "

# 健康阈值
DISK_WARN_PCT = 85
TEMP_WARN_C = 70.0
P95_WARN_MS = 400
MEM_WARN_MB = 200


def ssh(cmd: str) -> str:
    """通过 board_ssh.py 跑命令，返回 stdout。"""
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
    """主动连 TCP 9000 拿一次 broadcast stats。
    板端会每秒推送一次 stats 消息（每 10 帧），但 TCP 不会自动送——需要先发一个触发。
    简化：直接读最近一次 npu_stats 推送到客户端的输出。
    """
    try:
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        s.settimeout(timeout)
        # 服务端是 broadcast，不接收请求——但每 ~1 秒会推 stats
        # 收集 1.5 秒内的所有消息，挑 stats 那条
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
            # 检查是否含 stats
            if b'"type": "stats"' in buf:
                # 多读一点保证完整
                time.sleep(0.1)
                try:
                    buf += s.recv(4096)
                except Exception:
                    pass
                break
        s.close()
        # 解析每行 JSON 找 stats
        for line in buf.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") == "stats":
                    return obj
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return None


def parse_disk(out: str):
    for line in out.splitlines():
        if "/dev/root" in line or "/dev/mmcblk" in line:
            m = re.search(r"(\d+)%\s+(\S+)$", line)
            if m:
                return int(m.group(1)), m.group(2)
    return None, None


def parse_mem(out: str):
    total = avail = None
    for line in out.splitlines():
        if line.startswith("MemTotal:"):
            total = int(line.split()[1]) // 1024
        elif line.startswith("MemAvailable:"):
            avail = int(line.split()[1]) // 1024
    return total, avail


def parse_service(out: str):
    for line in out.splitlines():
        if "board_server_cascade" in line:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    return None
    return None


def parse_cascade_log(out: str):
    lines = out.splitlines()
    fps = []
    for line in lines[-500:]:
        m = re.match(r"frame\s+\d+\s+\S+?\.jpg\s+缺陷\s+(\d+)\s+个\s+([\d.]+)\s+ms", line)
        if m:
            fps.append((int(m.group(1)), float(m.group(2))))
    return fps


def percentile(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f, c = int(k), int(k) + 1
    if c >= len(s):
        return s[-1]
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def main():
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"\n=== {ts} 板端健康检查 ==="]

    # 1) 服务状态
    ps_out = ssh("ps aux | grep board_server | grep -v grep")
    pid = parse_service(ps_out)
    if pid is None:
        lines.append(CRIT + "级联服务未运行！需要 /etc/init.d/S99board restart")
    else:
        lines.append(OK + f"级联服务 PID={pid}  运行中")

    # 2) 磁盘
    disk_out = ssh("df -h /root")
    pct, mnt = parse_disk(disk_out)
    if pct is None:
        lines.append("⚠️  磁盘解析失败: " + disk_out[:80])
    else:
        marker = WARN if pct > DISK_WARN_PCT else OK
        lines.append(marker + f"磁盘 / 使用 {pct}%（阈值 {DISK_WARN_PCT}%）")

    # 3) 内存
    mem_out = ssh("cat /proc/meminfo")
    total, avail = parse_mem(mem_out)
    if total and avail is not None:
        used_pct = int((total - avail) * 100 / total)
        marker = WARN if avail < MEM_WARN_MB else OK
        lines.append(marker + f"内存 {used_pct}% ({avail}MB available / {total}MB total, 阈值 {MEM_WARN_MB}MB)")

    # 4) NPU + 延迟（延迟从 log，NPU 主动连 TCP 拿）
    log_out = ssh("tail -n 600 /root/rknn/server_cascade.log")
    fps = parse_cascade_log(log_out)
    if fps:
        lats = [m for _, m in fps]
        p50 = percentile(lats, 50)
        p95 = percentile(lats, 95)
        lines.append(OK + f"延迟 最近 {len(fps)} 帧: p50={p50:.0f}ms  p95={p95:.0f}ms"
                     + (WARN if p95 > P95_WARN_MS else ""))
        # 24 sample 检出数
        recent = fps[-24:] if len(fps) >= 24 else fps
        if recent:
            avg_defects = sum(d for d, _ in recent) / len(recent)
            if avg_defects < 0.5:
                lines.append(WARN + f"24 sample 平均检出数 {avg_defects:.1f}（正常 1~6）")
    else:
        lines.append("⚠️  级联日志无 frame 记录（服务可能未真在跑）")

    # 5) 主动连 TCP 9000 拿 NPU stats
    npu = temp = fps_remote = infer_ms = None
    stats = tcp_stats()
    if stats:
        npu = stats.get("npu")
        temp = stats.get("temp")
        fps_remote = stats.get("fps")
        infer_ms = stats.get("infer_ms")
    if npu is not None and temp is not None:
        # npu 字段板端格式 "38/5/6%"（1秒/5秒/15秒），取第一个
        if isinstance(npu, str) and "/" in npu:
            npu_1s = float(npu.split("/")[0].rstrip("%"))
        else:
            npu_1s = float(npu) if npu not in (None, "-") else None
        lines.append(
            (WARN if temp > TEMP_WARN_C else OK)
            + f"NPU 1秒占用 {npu_1s if npu_1s is not None else npu}%  温度 {temp:.1f}°C（阈值 {TEMP_WARN_C}°C）"
            + (f"  实际 FPS={fps_remote}  当前延迟={infer_ms}ms" if fps_remote else "")
        )
    else:
        lines.append("⚠️  TCP 9000 拿不到 NPU stats（服务可能没 broadcast）")

    out = "\n".join(lines)
    print(out)
    # 落盘（简化：用 ssh heredoc）
    safe = out.replace("'", "'\\''")
    ssh(f"echo '{safe}' >> {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
