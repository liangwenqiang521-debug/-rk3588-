# -*- coding: utf-8 -*-
"""训练守护：等 39 类训练结束 -> 自动跑评估。只读日志 + 调评估脚本。
判活用日志 mtime（训练时日志每几秒刷新一次），比探进程稳。
完成标志：ultralytics 打印 "N epochs completed in" 或 "Stopping training early"。
异常退出：日志 15 分钟无更新且无完成标志。
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
TRAIN_LOG = os.path.join(ROOT, "_train39.log")
WATCH_LOG = os.path.join(ROOT, "_watch39.log")
EVAL_LOG = os.path.join(ROOT, "_eval39.log")
BEST = os.path.join(ROOT, "runs", "steel39_yolo11n_640", "weights", "best.pt")
PY = os.path.join(ROOT, "venv_cuda", "Scripts", "python.exe")

DONE_RE = re.compile(r"(\d+)\s+epochs completed in|Stopping training early")
STALE_SEC = 15 * 60
POLL = 120


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(WATCH_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_log():
    try:
        return open(TRAIN_LOG, "rb").read().decode("utf-8", "ignore")
    except Exception as e:
        return "ERR %s" % e


def run_eval():
    if not os.path.exists(BEST):
        log("best.pt 不存在，无法评估：%s" % BEST)
        return
    cmd = [PY, "_eval_steel39.py",
           "--model", BEST,
           "--data", "data_steel39.yaml",
           "--json", "_eval_steel39.json"]
    log("开始评估: %s" % " ".join(os.path.basename(c) if i else c for i, c in enumerate(cmd)))
    with open(EVAL_LOG, "w", encoding="utf-8", errors="ignore") as f:
        p = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    log("评估结束 exit=%d -> %s" % (p.returncode, EVAL_LOG))


def main():
    log("watch 启动，等待训练完成（log=%s）" % TRAIN_LOG)
    last_marker_seen = False
    while True:
        txt = read_log()
        if DONE_RE.search(txt):
            log("检测到训练完成标志")
            run_eval()
            return
        # 已完成轮数
        m = re.findall(r"^\s*(\d+)/50\s", txt, re.M)
        age = time.time() - os.path.getmtime(TRAIN_LOG) if os.path.exists(TRAIN_LOG) else 1e9
        last_epoch = m[-1] if m else "?"
        if age > STALE_SEC:
            log("日志已 %.0fs 无更新且无完成标志，疑似异常退出（最后轮次=%s）" % (age, last_epoch))
            log("跳过自动评估，请人工确认。")
            return
        time.sleep(POLL)


if __name__ == "__main__":
    main()
