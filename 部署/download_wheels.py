# -*- coding: utf-8 -*-
"""下载板端部署所需的 aarch64 轮子到 部署/wheels_aarch64（直接按 PyPI URL 拉取，绕过 pip 平台过滤）。"""
import json
import os
import sys
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wheels_aarch64")
os.makedirs(OUT, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pick_file(pkg, ver, predicate):
    d = get_json("https://pypi.org/pypi/%s/%s/json" % (pkg, ver))
    for f in d["urls"]:
        if predicate(f["filename"]):
            return f["url"], f["filename"]
    print("[WARN] 未命中 %s==%s，可选文件:" % (pkg, ver))
    for f in d["urls"]:
        print("   ", f["filename"])
    return None, None


def dl(url, fn, retries=5):
    dest = os.path.join(OUT, fn)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print("已存在，跳过:", fn)
        return
    for attempt in range(1, retries + 1):
        try:
            print("下载(%d/%d):" % (attempt, retries), fn)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as fh:
                import shutil
                shutil.copyfileobj(r, fh, length=1 << 20)
            print("   -> %d 字节" % os.path.getsize(dest))
            return
        except Exception as e:
            print("   失败:", e)
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except Exception:
                    pass
    print("!! 放弃:", fn)


# 1) PySide6 全家桶（cp39-abi3 manylinux_2_31 aarch64，兼容板子 glibc 2.37 / py3.10）
for pkg in ["PySide6-Essentials", "shiboken6", "PySide6"]:
    url, fn = pick_file(
        pkg, "6.8.0.2",
        lambda n: "manylinux_2_31_aarch64" in n and "cp39-abi3" in n)
    if url:
        dl(url, fn)

# 2) psutil：选最新的、含 aarch64 manylinux 的轮子（优先 abi3）
d = get_json("https://pypi.org/pypi/psutil/json")
chosen = None
for v in sorted(d["releases"].keys(), reverse=True):
    for f in d["releases"][v]:
        if "aarch64" in f["filename"] and "manylinux" in f["filename"]:
            chosen = f
            break
    if chosen:
        break
if chosen:
    dl(chosen["url"], chosen["filename"])
else:
    print("[WARN] psutil 无 aarch64 manylinux 轮子")

# 3) pyserial：纯 py（none-any）
d = get_json("https://pypi.org/pypi/pyserial/json")
for v in sorted(d["releases"].keys(), reverse=True):
    for f in d["releases"][v]:
        if f["filename"].endswith("-none-any.whl") or f["filename"].endswith("-py2.py3-none-any.whl"):
            dl(f["url"], f["filename"])
            break
    else:
        continue
    break

print("\n完成。目录:", OUT)
