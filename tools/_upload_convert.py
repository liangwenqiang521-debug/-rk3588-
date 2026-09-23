# -*- coding: utf-8 -*-
"""把 RKNN 转换所需的 wheel 与模型一次性传到板子（单次 SSH 连接，带进度）。

目标：
  /root/rknn_convert/wheels/   <- 全部 .whl
  /root/rknn_convert/          <- best_neu6.onnx + export_rknn.py
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys
import glob
import time

import board_ssh

LOCAL_WHEELS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_wheels_rknn")
LOCAL_ONNX = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "模型训练", "runs", "neu_yolo11n_640", "weights", "best.onnx",
)
LOCAL_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "模型训练", "export_rknn.py",
)

REMOTE_ROOT = "/root/rknn_convert"
REMOTE_WHEELS = REMOTE_ROOT + "/wheels"


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, u)
        n /= 1024.0
    return "%.1f TB" % n


def main():
    files = sorted(glob.glob(os.path.join(LOCAL_WHEELS, "*.whl")))
    if not files:
        raise SystemExit("本地没有 wheel 可用（_wheels_rknn/ 为空）")
    files.append(LOCAL_ONNX)
    files.append(LOCAL_SCRIPT)

    total = sum(os.path.getsize(f) for f in files)
    print("待传 %d 个文件，共 %s" % (len(files), human(total)))

    cli = board_ssh.connect()
    sftp = cli.open_sftp()

    for d in (REMOTE_ROOT, REMOTE_WHEELS):
        try:
            sftp.stat(d)
        except IOError:
            sftp.mkdir(d)
            print("  新建目录", d)

    t0 = time.time()
    sent = 0
    for f in files:
        base = os.path.basename(f)
        dst = (REMOTE_WHEELS + "/" + base) if f.endswith(".whl") else (REMOTE_ROOT + "/" + base)
        sz = os.path.getsize(f)
        sftp.put(f, dst)
        sent += sz
        print("  [%5.1f%%] %-70s %s" % (100.0 * sent / total, base, human(sz)))

    sftp.close()
    cli.close()
    print("")
    print("上传完成，耗时 %.1f 秒（%s/s）" % (time.time() - t0, human(total / max(time.time() - t0, 0.01))))
    print("板端目录: %s" % REMOTE_ROOT)


if __name__ == "__main__":
    sys.exit(main())
