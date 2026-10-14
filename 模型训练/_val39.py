# -*- coding: utf-8 -*-
"""提取日志中的验证结果表（每轮 all 行）+ 关键参数。只读。"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
raw = open(os.path.join(ROOT, "_train39.log"), "rb").read().decode("utf-8", "ignore")
chunks = [c.strip() for c in re.split(r"[\r\n]+", raw) if c.strip()]

print("== 验证结果行 (含 mAP50) ==")
for c in chunks:
    if "mAP50" in c and ("all" in c or "Class" in c):
        print(re.sub(r"\s+", " ", c)[:200])

print()
print("== 轮次进度行 (含 100%) ==")
for c in chunks:
    m = re.match(r"^\s*(\d+)/50\s", c)
    if m and "100%" in c:
        print(re.sub(r"\s+", " ", c)[:160])

print()
print("== 最近的 all 行 ==")
alls = [c for c in chunks if re.search(r"\ball\b", c) and re.search(r"0\.\d", c)]
for c in alls[-4:]:
    print(re.sub(r"\s+", " ", c)[:200])
