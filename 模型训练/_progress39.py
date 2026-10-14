# -*- coding: utf-8 -*-
"""极简训练进度快照：把 ultralytics 的 \r 进度噪声解析成每轮汇总行。
只读日志，不改任何东西。用完可删。
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "_train39.log")

if not os.path.exists(LOG):
    print("no log yet:", LOG)
    sys.exit(0)


def main():
    with open(LOG, "rb") as f:
        raw = f.read().decode("utf-8", "ignore")
    # ultralytics 用 \r 刷新同一行，统一切成段
    chunks = re.split(r"[\r\n]+", raw)
    chunks = [c.strip() for c in chunks if c.strip()]

    # 找形如 " 12/50 ... 640: 100% ..." 的整轮完成行
    epoch_line = re.compile(r"^\s*(\d+)/(\d+)\s")
    done = []
    for c in chunks:
        m = epoch_line.match(c)
        if m and "100%" in c:
            done.append(c)

    print("=" * 60)
    for line in done[-6:]:
        # 压缩多余空白
        print("  " + re.sub(r"\s+", " ", line)[:160])

    print("-" * 60)
    # 当前正在进行的最后一轮
    last = chunks[-1] if chunks else ""
    print("LATEST:", re.sub(r"\s+", " ", last)[:200])
    print("-" * 60)

    mt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(LOG)))
    age = time.time() - os.path.getmtime(LOG)
    print("log mtime:", mt, "  (%.0fs ago)" % age)
    print("epochs completed:", len(done))
    print("=" * 60)


if __name__ == "__main__":
    main()
