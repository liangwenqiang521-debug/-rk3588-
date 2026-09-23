# -*- coding: utf-8 -*-
"""通用工具函数：串口枚举、声音报警、系统资源监控"""
import os
import sys
import subprocess


def list_serial_ports():
    """枚举当前可用的串口，返回 [(device, description), ...]"""
    try:
        import serial.tools.list_ports as lp
        ports = list(lp.comports())
        return [(p.device, "%s %s" % (p.description, p.hwid))
                for p in ports if p.device]
    except Exception:
        return []


def refresh_port_combo(combo, current_text=""):
    """刷新串口下拉框，保留当前选中项"""
    ports = list_serial_ports()
    combo.clear()
    for dev, desc in ports:
        combo.addItem(dev)
    if not ports:
        combo.addItem("（无可用串口）")
    # 尝试恢复之前的选择
    idx = combo.findText(current_text)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    elif ports:
        combo.setCurrentIndex(0)
    return ports


_BEEP_LOCK = {"ts": 0.0}


def play_beep():
    """播放系统提示音（NG 报警用）。

    09-21 优化：winsound.Beep(1000, 300) 是**同步阻塞**调用，在检测主循环里
    每出一个 NG 就冻结 UI 主线程 300ms（表现为界面卡顿、动画掉帧、点击迟滞）。
    改为后台 daemon 线程播放；并做 400ms 内的重复抑制，避免连续 NG 时线程堆积。
    """
    import time
    import threading
    now = time.time()
    if now - _BEEP_LOCK["ts"] < 0.4:
        return
    _BEEP_LOCK["ts"] = now

    def _beep():
        try:
            if sys.platform == "win32":
                import winsound
                winsound.Beep(1000, 300)
            else:
                # Linux/Mac: 使用 print bell
                sys.stdout.write("\a")
                sys.stdout.flush()
        except Exception:
            pass

    try:
        threading.Thread(target=_beep, daemon=True).start()
    except Exception:
        pass


def open_file(path):
    """用系统默认程序打开文件（查看原图）"""
    if not path or not os.path.exists(path):
        return False
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def open_directory(path):
    """在文件管理器中打开包含指定文件的目录，并选中该文件"""
    if not path:
        return False
    directory = os.path.dirname(path) if os.path.isfile(path) else path
    if not directory or not os.path.exists(directory):
        return False
    try:
        if sys.platform == "win32":
            if os.path.isfile(path):
                # 选中文件
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(directory)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", directory])
        else:
            subprocess.Popen(["xdg-open", directory])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 磁盘守护：连续检测会持续落盘，磁盘写满前自动删除最老的自动生成图片。
# 人工存证（存证_*/录制_*）默认受保护，不会被自动删除。
# ---------------------------------------------------------------------------
_LAST_DISK_CHECK = {"ts": 0.0}


def disk_guard(directory, min_free_pct=10.0, protect=("存证_", "录制_"),
               max_delete=300, interval=60.0, log=None):
    """磁盘剩余空间低于 min_free_pct% 时，删除 directory 下最老的自动存图。

    - directory      : 需要守护的落盘目录
    - min_free_pct   : 触发阈值（剩余百分比低于此值开始清理）
    - protect        : 这些前缀的文件永不自动删除（人工存证/录像）
    - max_delete     : 单次最多删除数量，避免一次删太多
    - interval       : 检查节流间隔（秒），避免每次保存都 stat 磁盘
    返回 (是否触发, 实际删除数)
    """
    import time
    now = time.time()
    if now - _LAST_DISK_CHECK["ts"] < interval:
        return (False, 0)
    _LAST_DISK_CHECK["ts"] = now

    try:
        import shutil
        total, used, free = shutil.disk_usage(directory)
    except Exception:
        return (False, 0)

    free_pct = free * 100.0 / total if total else 100.0
    if free_pct >= min_free_pct:
        return (False, 0)

    if log:
        try:
            log.warning("存储", "磁盘剩余 %.1f%% 低于阈值 %.0f%%，开始清理最老的存图"
                        % (free_pct, min_free_pct))
        except Exception:
            pass

    try:
        entries = []
        for name in os.listdir(directory):
            p = os.path.join(directory, name)
            if not os.path.isfile(p):
                continue
            if any(name.startswith(x) for x in protect):
                continue
            try:
                entries.append((os.path.getmtime(p), p))
            except Exception:
                continue
        entries.sort()                      # 最老的排前面
        n = 0
        for _ts, p in entries:
            if n >= max_delete:
                break
            try:
                os.remove(p)
                n += 1
            except Exception:
                continue
        if log and n:
            try:
                log.info("存储", "已清理 %d 个历史存图，当前剩余 %.1f%%" % (n, free_pct))
            except Exception:
                pass
        return (True, n)
    except Exception:
        return (True, 0)


class SysMonitor:
    """系统资源监控（基于 psutil），不可用时降级为占位值"""
    def __init__(self):
        self._psutil = None
        try:
            import psutil
            self._psutil = psutil
            # 预热采样基准：这一次建立 CPU 时间快照，之后所有采样都走
            # interval=None（与上次调用做差），全程非阻塞。
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    def available(self):
        return self._psutil is not None

    def cpu_percent(self):
        """CPU 使用率（非阻塞）。

        09-21 优化：原用 interval=0.1，psutil 会真的 sleep 100ms 采样两次，
        而调用方是 3s 周期的 GUI 定时器 → 每 3 秒冻结主线程 100ms。
        interval=None 直接用「上次调用以来」的累积差值，开销仅几十微秒。
        """
        if not self._psutil:
            return 0
        try:
            return int(self._psutil.cpu_percent(interval=None))
        except Exception:
            return 0

    def memory_percent(self):
        if not self._psutil:
            return 0
        return int(self._psutil.virtual_memory().percent)

    def disk_percent(self, path="D:\\"):
        if not self._psutil:
            return 0
        try:
            return int(self._psutil.disk_usage(path).percent)
        except Exception:
            return 0

    def disk_free_gb(self, path="D:\\"):
        if not self._psutil:
            return 0
        try:
            return round(self._psutil.disk_usage(path).free / (1024**3), 1)
        except Exception:
            return 0

    def uptime_string(self, start_ts):
        """从启动时间戳计算运行时长字符串"""
        if not self._psutil:
            return "--:--:--"
        import time
        elapsed = int(time.time() - start_ts)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        return "%02d:%02d:%02d" % (h, m, s)
