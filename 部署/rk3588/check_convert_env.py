# -*- coding: utf-8 -*-
"""板端 RKNN 转换环境自检（在 RK3588 上运行）。

用法：
    PYTHONPATH=/root/rknn_convert/libs python3 check_convert_env.py

逐项检查转换所需依赖能否 import。任何一个 FAIL 都会打印完整栈，
便于判断是缺包、ABI 不匹配（numpy/libstdc++）还是别的原因。
"""
import os
import sys
import traceback

print("=" * 60)
print("Python      :", sys.version.split()[0], "|", sys.platform)
print("executable  :", sys.executable)
print("PYTHONPATH  :", os.environ.get("PYTHONPATH", "(空)"))
print("=" * 60)

OK, FAIL = [], []


def check(name, fn):
    try:
        info = fn()
        print("[OK]   %-22s %s" % (name, info if info else ""))
        OK.append(name)
        return True
    except Exception as e:
        print("[FAIL] %-22s %s: %s" % (name, type(e).__name__, e))
        tb = traceback.format_exc().strip().splitlines()
        for line in tb[-4:]:
            print("         | " + line)
        FAIL.append(name)
        return False


def _numpy():
    import numpy
    return "%s  (%s)" % (numpy.__version__, os.path.dirname(numpy.__file__))


def _protobuf():
    import google.protobuf
    return google.protobuf.__version__


def _onnx():
    import onnx
    return "%s  (%s)" % (onnx.__version__, os.path.dirname(onnx.__file__))


def _scipy():
    import scipy
    return scipy.__version__


def _tqdm():
    import tqdm
    return getattr(tqdm, "__version__", "?")


def _psutil():
    import psutil
    return psutil.__version__


def _fast_histogram():
    import fast_histogram
    return "loaded"


def _rknn_api():
    from rknn.api import RKNN
    return "RKNN 类已加载"


def _rknn_new():
    from rknn.api import RKNN
    r = RKNN(verbose=False)
    r.release()
    return "RKNN 实例化成功"


print("--- 依赖 import ---")
check("numpy", _numpy)
check("protobuf", _protobuf)
check("onnx", _onnx)
check("scipy", _scipy)
check("tqdm", _tqdm)
check("psutil", _psutil)
check("fast_histogram", _fast_histogram)
check("rknn.api", _rknn_api)
check("RKNN() 实例化", _rknn_new)

print("")
print("=" * 60)
print("通过 %d 项，失败 %d 项" % (len(OK), len(FAIL)))
if FAIL:
    print("失败项: %s" % ", ".join(FAIL))
print("=" * 60)
sys.exit(1 if FAIL else 0)
