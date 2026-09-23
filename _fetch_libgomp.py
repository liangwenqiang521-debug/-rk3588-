# -*- coding: utf-8 -*-
"""从 Debian arm64 软件包中提取 libgomp.so.1（RK3588 板子缺 OpenMP 运行库）。

背景
----
aarch64 版 torch 动态链接了 ``libgomp.so.1``（GNU OpenMP 运行时），
而目标板是 Buildroot 精简系统，既没有编译器也没有该库。

做法
----
Debian 的 libgomp1 包是标准 ``.deb``（ar 归档，内含 data.tar.xz）。
本脚本纯 Python 解析 ar + tar，把 ``libgomp.so.1*`` 提取到本地目录，
再随其它文件一起传到板子（放到 ``LD_LIBRARY_PATH`` 可见的位置即可）。
"""
import io
import os
import re
import sys
import tarfile
import urllib.request

POOL = "http://deb.debian.org/debian/pool/main/g/gcc-12/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs_out")
UA = {"User-Agent": "Mozilla/5.0 (rknn-deploy)"}


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def find_deb_url():
    """在 Debian pool 目录里找最新的 libgomp1_*_arm64.deb。"""
    print("查询:", POOL)
    try:
        html = http_get(POOL).decode("utf-8", "replace")
    except Exception as e:
        print("  目录列表获取失败(%s)，改用备选 gcc-11 目录" % e)
        return find_deb_url_fallback()

    names = re.findall(r'href="(libgomp1_[^"]*_arm64\.deb)"', html)
    if not names:
        return find_deb_url_fallback()
    # 取版本号最大的一个
    def ver(n):
        m = re.search(r"libgomp1_([0-9][^_]*)_", n)
        return m.group(1) if m else "0"
    names.sort(key=ver)
    pick = names[-1]
    print("  选中:", pick)
    return POOL + pick


def find_deb_url_fallback():
    for sub in ("gcc-13", "gcc-11", "gcc-10"):
        url = "http://deb.debian.org/debian/pool/main/g/%s/" % sub
        try:
            html = http_get(url).decode("utf-8", "replace")
        except Exception:
            continue
        names = re.findall(r'href="(libgomp1_[^"]*_arm64\.deb)"', html)
        if names:
            names.sort()
            print("  从 %s 选中: %s" % (sub, names[-1]))
            return url + names[-1]
    raise SystemExit("未能在 Debian 源中找到 libgomp1 arm64 包")


def parse_ar(blob):
    """解析 ar 归档，返回 {成员名: 字节}。"""
    if not blob.startswith(b"!<arch>\n"):
        raise ValueError("不是 ar 归档（.deb 头不对）")
    pos = 8
    members = {}
    while pos + 60 <= len(blob):
        header = blob[pos:pos + 60]
        name = header[0:16].decode("ascii", "replace").strip()
        try:
            size = int(header[48:58].decode("ascii", "replace").strip())
        except ValueError:
            break
        data = blob[pos + 60: pos + 60 + size]
        members[name.rstrip("/")] = data
        pos += 60 + size
        if pos % 2:            # ar 成员 2 字节对齐
            pos += 1
    return members


def extract_libgomp(members, outdir):
    """从 data.tar.* 中提取 libgomp.so.1*。"""
    data_name = None
    for n in members:
        if n.startswith("data.tar"):
            data_name = n
            break
    if not data_name:
        raise SystemExit("deb 里没有 data.tar.*")

    raw = members[data_name]
    print("  解包:", data_name, "(%d 字节)" % len(raw))
    tf = tarfile.open(fileobj=io.BytesIO(raw))
    got = []
    for m in tf.getmembers():
        base = os.path.basename(m.name)
        if base.startswith("libgomp.so.1"):
            f = tf.extractfile(m)
            if f is None:
                continue
            dst = os.path.join(outdir, base)
            with open(dst, "wb") as fh:
                fh.write(f.read())
            os.chmod(dst, 0o755)
            got.append((base, m.size))
            print("    ->", base, m.size, "字节")
    tf.close()
    return got


def main():
    os.makedirs(OUT, exist_ok=True)
    url = find_deb_url()
    print("下载:", url)
    deb = http_get(url, timeout=180)
    print("  .deb 大小: %.1f MB" % (len(deb) / 1048576.0))

    members = parse_ar(deb)
    print("  ar 成员:", ", ".join(members.keys()))
    got = extract_libgomp(members, OUT)
    if not got:
        raise SystemExit("没有提取到 libgomp.so.1*")

    # 确保存在 soname 软链指向
    real = [g for g in got if g[0] != "libgomp.so.1"]
    link = os.path.join(OUT, "libgomp.so.1")
    if real and not os.path.exists(link):
        os.symlink(real[0][0], link)
        print("  建立软链: libgomp.so.1 ->", real[0][0])

    print()
    print("完成，输出目录:", OUT)
    for f in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, f)
        print("   %-24s %s" % (f, "link" if os.path.islink(p)
                              else "%.0f KB" % (os.path.getsize(p) / 1024.0)))


if __name__ == "__main__":
    sys.exit(main())
