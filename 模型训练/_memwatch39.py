# -*- coding: utf-8 -*-
"""采样：系统可用内存 + 训练日志进度，判断是否持续爬升。只读。"""
import ctypes
import os
import re
import subprocess
import time


class MS(ctypes.Structure):
    _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]


def mem():
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1e9, m.dwMemoryLoad


def nchild(pid):
    out = subprocess.run(['tasklist', '/FO', 'CSV'], capture_output=True, text=True,
                         errors='ignore').stdout
    n = 0
    for line in out.splitlines()[1:]:
        if '"python.exe"' in line:
            n += 1
    return n


ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "_train39.log")


def progress():
    try:
        raw = open(LOG, 'rb').read().decode('utf-8', 'ignore')
        last = [c.strip() for c in re.split(r'[\r\n]+', raw) if c.strip()][-1]
        return re.sub(r'\s+', ' ', last)[:120]
    except Exception as e:
        return 'err %s' % e


print('t     avail(GB) used%  pythons  progress')
for i in range(7):
    a, u = mem()
    print('%3ds   %6.2f   %3d%%   %3d      %s' % (i * 20, a, u, nchild(0), progress()))
    if i < 6:
        time.sleep(20)
