"""
DAGM 域外误检长期监控（PC 端）
=============================

09-21 由「占位」升级为**真实实现**。此前卡在两个前置条件上，现在都满足了：
  1. 板端级联服务默认 step 模式（不再自循环刷屏）
  2. 板端支持 detect_img 协议（外部图片送检，TCP 推 base64）

原理：
  从 DAGM 2007 无缺陷图里抽样 N 张 → 逐张推给板端 NPU（级联 filter+判类）
  → 统计"检出缺陷框"的比例。DAGM 无缺陷图**本应 0 框**，
  所以这个比例就是**域外误检率**（基线模型 64.4%，负样本模型/级联应 ≈0%）。

为什么重要：
  这是"模型会不会把正常纹理判成缺陷"的长期哨兵。换模型/改阈值/重训后
  必须跑一遍，防止误检悄悄回退。

用法：
  python dagm_monitor.py                # 默认抽 30 张
  python dagm_monitor.py --n 100        # 抽 100 张（约 2 分钟）
  python dagm_monitor.py --all          # 全量 1200 张（约 20 分钟，慎跑）

输出：
  本地 output/dagm_monitor/dagm_monitor.log（追加，可画趋势）
  板端 /root/rknn/dagm_monitor.log（与板端其它日志同处，便于现场排查）
"""
import argparse
import base64
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
RECV_TIMEOUT = 20.0          # 单张最长等待

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "模型训练" / "datasets" / "dagm_neg" / "images" / "val"
LOCAL_LOG = ROOT / "output" / "dagm_monitor" / "dagm_monitor.log"
BOARD_LOG = "/root/rknn/dagm_monitor.log"

# 板端日志里"误检基线"参考：_640 基线 64.4%，级联目标 0%
BASELINE_PCT = 64.4
ALERT_PCT = 5.0              # 超过这个比例就告警


def ssh(cmd: str) -> str:
    """走 board_ssh.py 执行板端命令（沿用项目既有通道）。"""
    p = subprocess.run(
        ["C:/Users/21191/.workbuddy/binaries/python/envs/default/Scripts/python.exe",
         "board_ssh.py", cmd],
        cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = p.stdout or ""
    out = re.sub(r"^\[板子\].*?\n", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\$.*?$", "", out, flags=re.MULTILINE)
    return out.strip()


def infer_one(sock, img_path: Path):
    """推一张图到板端，返回 (defects 数, 推理毫秒)；失败返回 (None, None)。"""
    payload = {
        "cmd": "detect_img",
        "name": img_path.name,
        "img": base64.b64encode(img_path.read_bytes()).decode("ascii"),
    }
    sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

    buf = b""
    deadline = time.time() + RECV_TIMEOUT
    while time.time() < deadline:
        sock.settimeout(1.0)
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            continue
        except OSError:
            return None, None
        if not chunk:
            return None, None
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                obj = json.loads(line.decode("utf-8", "ignore"))
            except Exception:
                continue
            # 板端回的帧结果里带 src；stats 帧没有
            if isinstance(obj, dict) and obj.get("src") == img_path.name:
                return len(obj.get("defects") or []), obj.get("infer_ms")
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="抽样张数（默认 30）")
    ap.add_argument("--all", action="store_true", help="全量 1200 张")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    if not SRC.exists():
        print("找不到 DAGM 负样本目录: %s" % SRC)
        return 2

    imgs = sorted(SRC.glob("*.png"))
    if not imgs:
        print("目录无 PNG: %s" % SRC)
        return 2
    if not args.all:
        # 顺序抽样但错开起点，避免每次都测同一批
        start = int(time.time() // 3600) % max(1, len(imgs) - args.n)
        imgs = imgs[start:start + args.n]
    n_total = len(imgs)

    print("DAGM 域外误检监控：%d 张，目标板端 %s:%d" % (n_total, args.host, args.port))
    try:
        sock = socket.create_connection((args.host, args.port), timeout=5)
    except Exception as e:
        print("连板失败: %s" % e)
        return 3

    n_fp, n_done, ms_list = 0, 0, []
    t0 = time.time()
    try:
        for i, p in enumerate(imgs, 1):
            nd, ms = infer_one(sock, p)
            if nd is None:
                print("  [%d/%d] %s 超时/失败，跳过" % (i, n_total, p.name))
                continue
            n_done += 1
            ms_list.append(ms or 0)
            if nd > 0:
                n_fp += 1
                print("  [%d/%d] %s 误检 %d 框  %.0f ms"
                      % (i, n_total, p.name, nd, ms or 0))
            if i % 10 == 0:
                print("  进度 %d/%d  当前误检 %d/%d"
                      % (i, n_total, n_fp, n_done))
    finally:
        try:
            sock.close()
        except Exception:
            pass

    pct = (n_fp * 100.0 / n_done) if n_done else 0.0
    avg_ms = (sum(ms_list) / len(ms_list)) if ms_list else 0.0
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    # 注意：Windows 控制台是 GBK，emoji 会 UnicodeEncodeError（项目约定一律纯文字）
    verdict = "[正常]" if pct <= ALERT_PCT else "[告警] 误检回退？"

    line = ("%s  n=%d  误检 %d (%.1f%%)  平均 %.0f ms  耗时 %.0fs  %s"
            % (ts, n_done, n_fp, pct, avg_ms, time.time() - t0, verdict))
    print("\n" + "=" * 60)
    print(line)
    print("参考：_640 基线 %.1f%%，级联目标 0%%（告警线 %.1f%%）"
          % (BASELINE_PCT, ALERT_PCT))
    print("=" * 60)

    # 本地日志（可画趋势）
    LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # 板端日志（现场排查）
    safe = line.replace("'", "'\\''")
    ssh("echo '%s' >> %s" % (safe, BOARD_LOG))
    return 0 if pct <= ALERT_PCT else 1


if __name__ == "__main__":
    sys.exit(main())
