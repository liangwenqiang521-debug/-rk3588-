# -*- coding: utf-8 -*-
"""工业缺陷检测上位机 - 主窗口入口"""
import os, sys
# 兜底：强制 Qt 从当前解释器对应的 PyQt5 插件目录加载平台插件，
# 覆盖环境里可能错误的 QT_QPA_PLATFORM_PLUGIN_PATH / PATH 干扰，
# 解决 PyQt5 报 "no Qt platform plugin could be initialized" 的问题
# （常见于 PyCharm / conda / torch 注入的 Qt 路径互相打架）。
_pyqt_plugins = os.path.normpath(os.path.join(
    os.path.dirname(sys.executable), "..", "Lib", "site-packages", "PyQt5", "Qt5", "plugins"))
if os.path.isdir(_pyqt_plugins):
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _pyqt_plugins
# 必须在 PyQt5 之前导入 infer（从而预加载 torch/c10.dll）。
# 原因：若 PyQt5 先加载，其 Qt DLL 会与 torch 的 c10.dll 初始化冲突，
# 导致后续 import ultralytics 报 WinError 1114（DLL 初始化失败），
# 真实推理引擎在 HMI 内静默失效。先 import infer 可让 torch DLL 优先初始化。
try:
    import infer  # noqa: F401
    # 强制 torch(c10.dll) 在当前进程完全初始化，避免随后 import PyQt5
    # 时 Qt 与 torch 的 DLL 初始化顺序冲突导致 WinError 1114。
    import torch
    torch.zeros(1)  # 触发 c10.dll 真正加载并稳定
except Exception:
    pass
from PyQt5.QtCore import Qt, QTimer, QDateTime, QTime
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QStatusBar, QButtonGroup,
    QFrame, QShortcut, QMessageBox,
)


def _install_crash_guard():
    """兜底：拦截未捕获异常，杜绝“无提示闪退”。

    PyQt5 在 QTimer / 按钮等槽函数里抛出未捕获异常时，会调用 qFatal() 直接终止
    进程：界面瞬间消失，app.log 里连 traceback 都没有，极难排查（本项目
    “一点开始检测就卡退”正是这一类）。安装自定义 sys.excepthook 可阻止 qFatal，
    把完整调用栈写入 logs/crash.log，进程继续运行。
    """
    import traceback
    import datetime

    def _hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        block = "[%s] 未捕获异常（已拦截，进程继续运行）:\n%s%s\n" % (
            stamp, text, "-" * 70)
        try:
            os.makedirs("logs", exist_ok=True)
            with open(os.path.join("logs", "crash.log"), "a", encoding="utf-8") as f:
                f.write(block + "\n")
        except Exception:
            pass
        try:
            sys.stderr.write(block)
            sys.stderr.flush()
        except Exception:
            pass

    sys.excepthook = _hook


_install_crash_guard()
from widgets import DotIndicator, C_GREEN, C_BG, C_PANEL, C_BORDER, C_TEXT, C_DIM, C_BLUE, C_RED, C_YELLOW
from page_detect import DetectPage
from page_settings import SettingsPage
from page_history import HistoryPage
from page_comm import CommPage
from page_log import LogPage
from page_npu import NpuPage
from utils import SysMonitor
import time


QSS = """
* { font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; }
QMainWindow, QWidget { background: %(BG)s; color: %(TEXT)s; font-size: 12px; }

#topBar { background: #151a22;
          border-bottom: 1px solid #232a36; }
#appTitle { color: #ffffff; font-size: 16px; font-weight: bold; }
#topInfo { background: #1a2029; border: 1px solid #2a3140;
           border-radius: 11px; padding: 3px 12px; color: #9fb0c8; font-size: 12px; }

QPushButton#navBtn { background: transparent; border: 1px solid transparent;
    border-radius: 8px; color: %(DIM)s; font-size: 13px; padding: 6px 20px; }
QPushButton#navBtn:hover { color: %(TEXT)s; background: #1c222c; }
QPushButton#navBtn:checked { color: #ffffff; background: rgba(59, 158, 255, 0.16);
    border: 1px solid rgba(59, 158, 255, 0.45); }

#groupPanel { background: #161b23;
              border: 1px solid #242b37; border-radius: 10px; }
#groupTitle { color: #dce6f2; font-size: 13px; font-weight: bold;
              border-left: 3px solid %(BLUE)s; padding: 1px 0 3px 8px; }

QLineEdit, QComboBox, QDateTimeEdit, QSpinBox, QDoubleSpinBox {
    background: #131720; border: 1px solid #2a3140; border-radius: 6px;
    padding: 6px 10px; color: %(TEXT)s; min-height: 16px;
    selection-background-color: %(BLUE)s; selection-color: #ffffff; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: #39424f; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid %(BLUE)s; background: #141b26; }
QLineEdit:disabled, QComboBox:disabled { color: #5a6472; background: #10141a; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #1a202a; border: 1px solid #2f3644;
    color: %(TEXT)s; selection-background-color: #24406b;
    selection-color: #ffffff; border-radius: 6px; padding: 2px; }

QPushButton#primaryBtn {
    background: #2f8bea;
    border: none; border-radius: 6px; color: #ffffff;
    padding: 8px 18px; font-size: 12px; font-weight: bold; }
QPushButton#primaryBtn:hover { background: #3f9bfa; }
QPushButton#primaryBtn:pressed { background: #2470d6; }
QPushButton#primaryBtn:disabled { background: #2a3140; color: #6b7686; }
QPushButton#dangerBtn {
    background: #d3362f;
    border: none; border-radius: 6px; color: #ffffff;
    padding: 8px 18px; font-size: 12px; font-weight: bold; }
QPushButton#dangerBtn:hover { background: #e8453d; }
QPushButton#dangerBtn:pressed { background: #c72f28; }
QPushButton#dangerBtn:disabled { background: #2a3140; color: #6b7686; }
QPushButton#ghostBtn { background: #212732; border: 1px solid #2f3644;
    border-radius: 6px; color: #cbd5e1; padding: 8px 18px; font-size: 12px; }
QPushButton#ghostBtn:hover { background: #283040; border-color: %(BLUE)s; color: #ffffff; }
QPushButton#ghostBtn:pressed { background: #1d2530; }
QPushButton#filterBtn { background: #212732; border: 1px solid #2f3644;
    border-radius: 6px; color: %(DIM)s; padding: 5px 14px; font-size: 12px; }
QPushButton#filterBtn:hover { color: %(TEXT)s; border-color: #39424f; }
QPushButton#filterBtn:checked { background: %(BLUE)s; color: #ffffff; border: none; }
QToolButton#toolBtn, QPushButton#toolBtn { background: #212732;
    border: 1px solid #2f3644; border-radius: 6px; color: %(TEXT)s;
    padding: 5px 10px; font-size: 12px; }
QToolButton#toolBtn:hover, QPushButton#toolBtn:hover {
    background: #283040; border-color: #39424f; }
QToolButton#toolBtn:checked, QPushButton#toolBtn:checked {
    background: rgba(59, 158, 255, 0.18); border-color: %(BLUE)s; color: #ffffff; }

QTableWidget { background: #131720; border: 1px solid #272d38; border-radius: 8px;
    gridline-color: #1e242e; color: %(TEXT)s; font-size: 12px;
    alternate-background-color: #161b24; }
QTableWidget::item { padding: 5px; border: none; }
QTableWidget::item:hover { background: #1c2430; }
QTableWidget::item:selected { background: #24406b; color: #ffffff; }
QHeaderView::section { background: #1a202a; color: #9fb0c8; border: none;
    border-bottom: 2px solid #2a3140; padding: 7px 6px; font-size: 12px;
    font-weight: bold; }
QTableCornerButton::section { background: #1a202a; border: none; }

QTabWidget::pane { border: 1px solid #272d38; border-radius: 6px; top: -1px; }
QTabBar::tab { background: #131720; color: %(DIM)s; padding: 6px 18px;
    border: 1px solid #272d38; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:hover { color: %(TEXT)s; }
QTabBar::tab:selected { background: #1a1f28; color: %(BLUE)s; }

#statCard, #miniStat { background: #1a2029; border: 1px solid #272d38; border-radius: 8px; }

QStatusBar { background: #10141b; color: %(DIM)s; border-top: 1px solid #232a36; }
QStatusBar QLabel { color: %(DIM)s; font-size: 11px; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #333b48; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #434d5e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: #333b48; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #434d5e; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QSplitter::handle { background: #232a36; }
QSplitter::handle:hover { background: %(BLUE)s; }
QToolTip { background: #1a202a; color: %(TEXT)s; border: 1px solid #2f3644;
           border-radius: 4px; padding: 4px 8px; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QCheckBox { color: %(TEXT)s; font-size: 12px; spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid #3a4350; background: #131720; }
QCheckBox::indicator:checked { background: %(BLUE)s; border-color: %(BLUE)s; }
QRadioButton { color: %(TEXT)s; font-size: 12px; spacing: 6px; }
QMessageBox { background: #161b23; }
QMessageBox QLabel { color: %(TEXT)s; }
QMenu { background: #1a202a; color: %(TEXT)s; border: 1px solid #2f3644;
        border-radius: 6px; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: #24406b; color: #ffffff; }
"""% {"BG": C_BG, "PANEL": C_PANEL, "BORDER": C_BORDER, "TEXT": C_TEXT,
       "DIM": C_DIM, "BLUE": C_BLUE}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("工业缺陷检测上位机")
        self.resize(1600, 950)

        # ---- 共享服务 ----
        from config import Config
        from db import RecordDB
        from logger import AppLogger
        self.cfg = Config()
        self.db = RecordDB()
        self.log = AppLogger()
        self.sys_mon = SysMonitor()
        self._start_ts = time.time()
        self._config_dirty = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())
        root.addWidget(self._build_nav())

        self.stack = QStackedWidget()
        self.pages = [
            DetectPage(cfg=self.cfg, db=self.db, log=self.log,
                       status_cb=self._on_detect_state),
            SettingsPage(cfg=self.cfg, log=self.log, dirty_cb=self._mark_dirty),
            HistoryPage(db=self.db, log=self.log),
            CommPage(cfg=self.cfg, log=self.log, dirty_cb=self._mark_dirty),
            LogPage(log=self.log, sys_mon=self.sys_mon, start_ts=self._start_ts),
            NpuPage(log=self.log),
        ]
        for p in self.pages:
            self.stack.addWidget(p)
        root.addWidget(self.stack, 1)

        self._build_statusbar()

        self.nav_group.buttonClicked[int].connect(self._on_nav_changed)
        self.stack.setCurrentIndex(0)

        # C：检测页状态事件 → 顶栏真实状态灯
        self.pages[0].ind_cb = self._on_page_indicator
        import page_detect as _pd
        if not getattr(_pd, "_HAS_INFER", False):
            self.set_top_indicator("model", False, "推理不可用")

        self.log.info("系统", "软件启动，配置与数据库加载完成")
        self.log.info("模型", "模型 %s 加载完成（模拟）" % self.cfg.get("model", "name"))

        self._setup_shortcuts()
        self._setup_sys_timer()

    def _mark_dirty(self, dirty=True):
        self._config_dirty = dirty

    def _setup_shortcuts(self):
        # F5: 开始/停止检测
        sc_f5 = QShortcut(QKeySequence("F5"), self)
        sc_f5.activated.connect(self._toggle_detect)
        # Ctrl+S: 保存配置
        sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
        sc_save.activated.connect(self._save_config)
        # Ctrl+1~6: 切换页面
        for i in range(6):
            sc = QShortcut(QKeySequence("Ctrl+%d" % (i + 1)), self)
            sc.activated.connect(lambda idx=i: self._goto_page(idx))

    def _setup_sys_timer(self):
        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._update_sys_status)
        self._sys_timer.start(3000)
        self._update_sys_status()

    def _update_sys_status(self):
        if self.sys_mon.available():
            cpu = self.sys_mon.cpu_percent()
            mem = self.sys_mon.memory_percent()
            disk = self.sys_mon.disk_percent("D:\\")
            self.sb_sys.setText("CPU %d%%  ·  内存 %d%%  ·  磁盘 %d%%" % (cpu, mem, disk))
            # 磁盘空间不足时警告
            if disk > 90:
                self.sb_sys.setStyleSheet("color:%s; font-size:11px;" % C_RED)
            else:
                self.sb_sys.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        uptime = self.sys_mon.uptime_string(self._start_ts)
        self.sb_uptime.setText("运行 " + uptime)

    def _toggle_detect(self):
        page = self.pages[0]
        if page.running:
            page._stop()
        else:
            page._start()

    def _save_config(self):
        if self.cfg:
            self.cfg.save()
            self._config_dirty = False
            self.log.info("系统", "配置已保存到 config.json (Ctrl+S)")

    def _goto_page(self, idx):
        self.nav_group.button(idx).setChecked(True)
        self.stack.setCurrentIndex(idx)
        self._on_nav_changed(idx)

    def _on_nav_changed(self, idx):
        self.stack.setCurrentIndex(idx)

    # ---------------- 顶栏状态灯（C） ----------------
    def _on_page_indicator(self, kind, ok, text=None):
        self.set_top_indicator(kind, ok, text)

    def set_top_indicator(self, kind, ok, text=None):
        """设置顶栏状态灯。kind: 'cam'/'model'；
        ok: True=绿(正常) / False=红(异常) / None=黄(待定)。"""
        dots = {"cam": self.dot_cam_top,
                "model": self.dot_model_top}
        dot = dots.get(kind)
        if dot is None:
            return
        color = C_GREEN if ok is True else (C_RED if ok is False else C_YELLOW)
        if text:
            dot.set_text(text)
        dot.set_color(color)

    def closeEvent(self, event):
        """退出前提示保存配置"""
        if self._config_dirty:
            reply = QMessageBox.question(
                self, "退出确认",
                "配置已修改但尚未保存，是否保存？\n\n是 - 保存并退出\n否 - 不保存退出\n取消 - 返回程序",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self._save_config()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        # 停止检测、相机采集（含录像收尾）、NPU监控
        if self.pages[0].running:
            self.pages[0]._stop()
        if getattr(self.pages[0], "_camera_live", False):
            self.pages[0]._stop_camera()
        if self.pages[5].worker:
            self.pages[5]._disconnect()
        self.log.info("系统", "软件正常退出")
        event.accept()

    def _on_detect_state(self, running):
        if running:
            self.sb_state.setText("● 运行中")
            self.sb_state.setStyleSheet("color:#3fb950; font-size:11px;")
            self.sb_fps.setText("帧率 %s" % self.cfg.get("camera", "fps", "30 FPS"))
        else:
            self.sb_state.setText("● 已停止")
            self.sb_state.setStyleSheet("color:#d29922; font-size:11px;")
            self.sb_fps.setText("帧率 -- FPS")

    # ---------------- 顶部栏 ----------------
    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(14)

        title = QLabel("工业缺陷检测上位机")
        title.setObjectName("appTitle")
        # 标题左侧品牌色竖条
        accent = QFrame()
        accent.setFixedSize(4, 22)
        accent.setStyleSheet("background: %s; border-radius: 2px;" % C_BLUE)
        lay.addWidget(accent)
        lay.addWidget(title)
        lay.addStretch(1)

        # 状态灯（由各页面事件驱动，不再恒绿）
        self.dot_cam_top = DotIndicator("相机未就绪", C_RED)
        self.dot_cam_top.setToolTip("打开照片或连接 RK3588 后点亮")
        self.dot_model_top = DotIndicator("模型待加载", C_YELLOW)
        self.dot_model_top.setToolTip("首次真实推理时加载模型并点亮")
        for d in (self.dot_cam_top, self.dot_model_top):
            lay.addWidget(d)
            lay.addSpacing(8)

        # 分隔线
        sep = QFrame()
        sep.setFixedSize(1, 22)
        sep.setStyleSheet("background: #2a3140;")
        lay.addWidget(sep)
        lay.addSpacing(4)

        model = QLabel("模型  %s" % self.cfg.get("model", "name", "Product_A_v1"))
        model.setObjectName("topInfo")
        cam = QLabel("相机  %s" % self.cfg.get("camera", "name", "相机 01").replace(" ", "_"))
        cam.setObjectName("topInfo")
        lay.addWidget(model)
        lay.addWidget(cam)
        return bar

    # ---------------- 导航 ----------------
    def _build_nav(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(44)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(4)

        self.nav_group = QButtonGroup(self)
        names = ["实时检测", "参数设置", "历史记录", "通信设置", "运行日志", "NPU 监控"]
        for i, n in enumerate(names):
            b = QPushButton(n)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip("%s  (Ctrl+%d)" % (n, i + 1))
            self.nav_group.addButton(b, i)
            lay.addWidget(b)
            if i == 0:
                b.setChecked(True)
        lay.addStretch(1)
        return bar

    # ---------------- 状态栏 ----------------
    def _build_statusbar(self):
        sb = QStatusBar()
        sb.setFixedHeight(26)
        self.setStatusBar(sb)
        self.sb_state = QLabel("● 已停止")
        self.sb_state.setStyleSheet("color:#d29922; font-size:11px;")
        self.sb_fps = QLabel("帧率 -- FPS")
        self.sb_fps.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        self.sb_uptime = QLabel("运行 --:--:--")
        self.sb_uptime.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        self.sb_sys = QLabel("")
        self.sb_sys.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        self.sb_time = QLabel()
        self.sb_time.setStyleSheet("color:%s; font-size:11px;" % C_DIM)

        def _sep():
            s = QLabel("·")
            s.setStyleSheet("color:#3a4350; font-size:11px;")
            return s

        sb.addWidget(self.sb_state)
        sb.addWidget(_sep())
        sb.addWidget(self.sb_fps)
        sb.addWidget(_sep())
        sb.addWidget(self.sb_uptime)
        sb.addPermanentWidget(self.sb_sys)
        sb.addPermanentWidget(_sep())
        sb.addPermanentWidget(self.sb_time)
        timer = QTimer(self)
        timer.timeout.connect(lambda: self.sb_time.setText(
            QDateTime.currentDateTime().toString("yyyy-MM-dd  hh:mm:ss")))
        timer.start(1000)
        self.sb_time.setText(
            QDateTime.currentDateTime().toString("yyyy-MM-dd  hh:mm:ss"))


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
