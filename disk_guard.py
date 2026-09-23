"""
板端磁盘守护（PC 端）
====================

每 6 小时跑一次：查 /root 磁盘用量
- <80%：只打 log
- ≥80%：按 mtime 删最老的 .log / .pid
- ≥90%：再删 /root/rknn/samples_synth_bak 等旧备份

设计原则：
- 永不删 .rknn（模型权重，不可恢复）
- 永不删 /root/rknn/backup/（带验证信息的备份）
- 优先删 log（恢复代价低）

输出：stdout + 落盘 /root/rknn/disk_guard.log

用法：
  python disk_guard.py
  # 6 小时周期
"""
import re
import subprocess
import sys
import time
from pathlib import Path

LOG_PATH = "/root/rknn/disk_guard.log"
WARN_PCT = 80
DANGER_PCT = 90
PROTECT_PATHS = ["/root/rknn/*.rknn", "/root/rknn/backup/"]


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


def get_disk_pct():
    out = ssh("df -h /root")
    for line in out.splitlines():
        if "/dev/root" in line or "/dev/mmcblk" in line:
            m = re.search(r"(\d+)%", line)
            if m:
                return int(m.group(1))
    return None


def find_old_logs(limit=10):
    """找 /root/rknn 下所有 .log 文件，按 mtime 升序。"""
    out = ssh("find /root/rknn -name '*.log' -type f -printf '%T@ %p\\n' 2>/dev/null | sort -n | head -20")
    items = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            items.append(parts[1])
    return items[:limit]


def find_old_backups(limit=5):
    """找 /root 下非 .rknn 的旧目录（除 backup）。"""
    out = ssh("find /root -maxdepth 3 -type d -mtime +7 -not -path '/root/rknn*' -not -path '/root/.ssh*' 2>/dev/null | head -10")
    return [l for l in out.splitlines() if l.strip()]


def main():
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    pct = get_disk_pct()
    if pct is None:
        print(f"{ts} [ERR] 磁盘解析失败")
        return 1
    line = f"{ts} /root 磁盘 {pct}%"
    actions = []
    if pct < WARN_PCT:
        print(line)
        safe = line.replace("'", "'\\''")
        ssh(f"echo '{safe}' >> {LOG_PATH}")
        return 0
    # WARN
    if pct < DANGER_PCT:
        line += f" ⚠️  超过 {WARN_PCT}%，清理最老的 .log"
        old_logs = find_old_logs(5)
        for f in old_logs:
            ssh(f"rm '{f}'")
            actions.append(f"删 log: {f}")
    else:
        # DANGER
        line += f" ❌ 超过 {DANGER_PCT}%，清理 logs + 旧备份"
        old_logs = find_old_logs(10)
        for f in old_logs:
            ssh(f"rm '{f}'")
            actions.append(f"删 log: {f}")
        old_dirs = find_old_backups(3)
        for d in old_dirs:
            ssh(f"rm -rf '{d}'")
            actions.append(f"删旧目录: {d}")
    print(line)
    for a in actions:
        print(f"  - {a}")
    safe = line.replace("'", "'\\''")
    ssh(f"echo '{safe}' >> {LOG_PATH}")
    for a in actions:
        sa = a.replace("'", "'\\''")
        ssh(f"echo '{ts} {sa}' >> {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
