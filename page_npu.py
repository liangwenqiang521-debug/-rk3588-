# -*- coding: utf-8 -*-
"""NPU 监控页：三核负载 + 历史曲线 + 温度/内存"""
import time
from PyQt5.QtCore import Qt, QRectF, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QProgressBar, QSizePolicy, QFrame, QMessageBox,
)
from widgets import GroupPanel, DotIndicator, C_GREEN, C_RED, C_BLUE, C_YELLOW, C_DIM, C_TEXT, C_BORDER, C_PANEL2
from npu_monitor import SerialBackend, DemoBackend, NpuWorker, LoadHistory, normalize_stats
from utils import refresh_port_combo

# 板端默认地址统一来自 board_env（不硬编码真实 IP）
try:
    import board_env
    DEFAULT_BOARD_ADDR = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
except Exception:
    DEFAULT_BOARD_ADDR = "169.254.100.100"

# 板端 NPU 状态接收（串口/TCP），与 serial_bridge/tcp_bridge 同接口
try:
    from serial_bridge import BoardSerialBridge
    _HAS_SERIAL_BRIDGE = True
except Exception:
    _HAS_SERIAL_BRIDGE = False
try:
    from tcp_bridge import BoardTcpBridge
    _HAS_TCP_BRIDGE = True
except Exception:
    _HAS_TCP_BRIDGE = False

CORE_COLORS = [C_BLUE, C_GREEN, C_YELLOW]
CORE_NAMES = ["Core 0", "Core 1", "Core 2"]


class CoreBar(QWidget):
    """单核负载条：名称 + 进度条 + 百分比"""
    def __init__(self, name, color, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lab = QLabel(name)
        lab.setFixedWidth(60)
        lab.setStyleSheet("color:%s; font-size:13px;" % C_TEXT)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(16)
        self.bar.setStyleSheet(
            "QProgressBar{background:%s; border:1px solid %s; border-radius:8px;}"
            "QProgressBar::chunk{background:%s; border-radius:7px;}"
            % (C_PANEL2, C_BORDER, color))
        self.val = QLabel("-- %")
        self.val.setFixedWidth(56)
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val.setStyleSheet("color:%s; font-size:14px; font-weight:bold;" % color)
        lay.addWidget(lab)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.val)

    def set_value(self, v):
        self.bar.setValue(v)
        self.val.setText("%d %%" % v)


class LoadChart(QWidget):
    """三核负载历史曲线"""
    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.history = history
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#101318"))

        left, right, top, bottom = 40, 14, 14, 24
        cw, ch = w - left - right, h - top - bottom

        # 网格与刻度（0/25/50/75/100%）
        f = QFont("Microsoft YaHei", 9)
        p.setFont(f)
        for i in range(5):
            y = top + ch * i / 4.0
            pen = QPen(QColor(C_BORDER))
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawLine(int(left), int(y), int(left + cw), int(y))
            p.setPen(QColor(C_DIM))
            p.drawText(QRectF(0, y - 8, left - 6, 16),
                       Qt.AlignRight | Qt.AlignVCenter, "%d" % (100 - i * 25))

        series = [self.history.core0, self.history.core1, self.history.core2]
        n_max = 90
        for si, data in enumerate(series):
            if len(data) < 2:
                continue
            pen = QPen(QColor(CORE_COLORS[si]))
            pen.setWidth(2)
            p.setPen(pen)
            n = len(data)
            prev = None
            for i, v in enumerate(data):
                x = left + cw * (n_max - n + i) / float(n_max - 1)
                y = top + ch * (1 - v / 100.0)
                if prev is not None:
                    p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
                prev = (x, y)

        # 图例
        lx = left + 10
        for si, name in enumerate(CORE_NAMES):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(CORE_COLORS[si]))
            p.drawRect(int(lx), int(h - 17), 12, 4)
            p.setPen(QColor(C_DIM))
            p.drawText(QRectF(lx + 16, h - 22, 60, 16), Qt.AlignVCenter, name)
            lx += 80
        p.end()


class NpuPage(QWidget):
    def __init__(self, log=None, parent=None):
        super().__init__(parent)
        self.log = log
        self.worker = None
        self.bridge = None
        self._dead_bridges = []  # 已失败/待回收的 bridge 线程，统一在 _disconnect 里 stop
        self.history = LoadHistory(90)
        self._sample_count = 0
        self._user_disconnecting = False  # 主动断开时静默后续 connected(False) 回调
        self._conn_since = 0.0  # 物理层打开的时间；超过 N 秒还没收到首条 JSON 提示用户

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---------------- 连接条 ----------------
        g = GroupPanel("设备连接")
        bar = QHBoxLayout()
        bar.setSpacing(10)
        lab = QLabel("数据来源")
        lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        bar.addWidget(lab)
        self.mode = QComboBox()
        self.mode.addItems(["模拟数据", "板端串口", "板端TCP"])
        self.mode.setFixedWidth(150)
        self.mode.currentIndexChanged.connect(self._apply_mode_ui)
        bar.addWidget(self.mode)

        # 板端串口：端口 + 波特率
        self.lab_port = QLabel("串口")
        self.lab_port.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        bar.addWidget(self.lab_port)
        self.port = QComboBox()
        refresh_port_combo(self.port, "COM3")
        self.port.setEditable(True)
        self.port.setFixedWidth(100)
        bar.addWidget(self.port)
        self.lab_baud = QLabel("波特率")
        self.lab_baud.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        bar.addWidget(self.lab_baud)
        self.baud = QLineEdit("1500000")
        self.baud.setFixedWidth(80)
        bar.addWidget(self.baud)

        # 板端TCP：地址 + 端口
        self.lab_addr = QLabel("地址")
        self.lab_addr.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        bar.addWidget(self.lab_addr)
        self.addr = QLineEdit(board_env.get("BOARD_IP", ""))
        self.addr.setFixedWidth(130)
        bar.addWidget(self.addr)
        self.lab_port_tcp = QLabel("端口")
        self.lab_port_tcp.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        bar.addWidget(self.lab_port_tcp)
        self.port_tcp = QLineEdit("9000")
        self.port_tcp.setFixedWidth(70)
        bar.addWidget(self.port_tcp)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setObjectName("toolBtn")
        self.btn_refresh.setFixedWidth(32)
        self.btn_refresh.setToolTip("刷新串口列表")
        self.btn_refresh.clicked.connect(lambda: refresh_port_combo(self.port, self.port.currentText()))
        bar.addWidget(self.btn_refresh)
        self.btn_conn = QPushButton("连接")
        self.btn_conn.setObjectName("primaryBtn")
        self.btn_conn.clicked.connect(self._toggle)
        bar.addWidget(self.btn_conn)
        self.status = DotIndicator("未连接", C_RED)
        bar.addWidget(self.status)
        bar.addStretch(1)
        self.hint = QLabel("")
        self.hint.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        bar.addWidget(self.hint)
        holder = QWidget(); holder.setLayout(bar)
        g.body().addWidget(holder)
        root.addWidget(g)
        self._apply_mode_ui(0)

        # ---------------- 三核负载 + 信息卡 ----------------
        mid = QHBoxLayout()
        mid.setSpacing(8)

        g2 = GroupPanel("NPU 核心负载 (RK3588 · 6 TOPS)")
        vb = QVBoxLayout()
        vb.setSpacing(14)
        self.bars = []
        for name, color in zip(CORE_NAMES, CORE_COLORS):
            b = CoreBar(name, color)
            self.bars.append(b)
            vb.addWidget(b)
        vb.addStretch(1)
        hw = QWidget(); hw.setLayout(vb)
        g2.body().addWidget(hw)
        mid.addWidget(g2, 1)

        right = QWidget()
        right.setFixedWidth(300)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        g3 = GroupPanel("板端状态")
        self.lb_temp = self._kv(g3, "芯片温度", "-- ℃")
        self.lb_mem = self._kv(g3, "内存占用", "-- / -- MB")
        self.mem_bar = QProgressBar()
        self.mem_bar.setRange(0, 100)
        self.mem_bar.setTextVisible(False)
        self.mem_bar.setFixedHeight(8)
        self.mem_bar.setStyleSheet(
            "QProgressBar{background:%s; border:none; border-radius:4px;}"
            "QProgressBar::chunk{background:%s; border-radius:4px;}"
            % (C_PANEL2, C_GREEN))
        g3.body().addWidget(self.mem_bar)
        self.lb_avg = self._kv(g3, "NPU 平均负载", "-- %")
        self.lb_peak = self._kv(g3, "NPU 峰值负载", "-- %")
        self.lb_fps = self._kv(g3, "推理帧率", "-- FPS")
        self.lb_infer = self._kv(g3, "单帧耗时", "-- ms")
        rl.addWidget(g3)

        g4 = GroupPanel("板端启动步骤（无板子请用『模拟数据』）")
        info = QLabel(
            "· <b>模拟数据</b>：本地随机值，无板子时调试 UI 用\n"
            "· <b>板端串口</b>：USB-TTL(3.3V) 连 RK3588 debug 串口（板端是 /dev/ttyS3）\n"
            "  板端命令：<code>python3 /root/rknn/board_infer.py --serial /dev/ttyS3</code>\n"
            "· <b>板端 TCP</b>：PC 与板子同网段（例 169.254.x.x，或网线直连）\n"
            "  板端命令：<code>python3 /root/rknn/board_infer.py --tcp-port 9000</code>\n"
            "· <b>板子需先转好 .rknn 模型</b>（FP16，INT8 分类头有驱动 bug）\n"
            "· 串口模式下请关闭其他串口工具，否则占用 COM")
        info.setStyleSheet("color:%s; font-size:11px; line-height:1.6;" % C_DIM)
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        g4.body().addWidget(info)
        rl.addWidget(g4)
        rl.addStretch(1)
        mid.addWidget(right)
        root.addLayout(mid, 0)

        # ---------------- 历史曲线 ----------------
        g5 = GroupPanel("负载历史 (最近 90 秒)")
        self.chart = LoadChart(self.history)
        g5.body().addWidget(self.chart)
        root.addWidget(g5, 1)

    def _kv(self, group, k, v):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        a = QLabel(k); a.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        b = QLabel(v); b.setStyleSheet("color:%s; font-size:13px; font-weight:bold;" % C_TEXT)
        lay.addWidget(a); lay.addStretch(1); lay.addWidget(b)
        group.body().addWidget(w)
        return b

    # ---------------- UI 联动：按数据来源显隐输入 ----------------
    def _apply_mode_ui(self, idx):
        is_serial = (idx == 1)
        is_tcp = (idx == 2)
        for w in (self.lab_port, self.port, self.lab_baud, self.baud, self.btn_refresh):
            w.setVisible(is_serial)
        for w in (self.lab_addr, self.addr, self.lab_port_tcp, self.port_tcp):
            w.setVisible(is_tcp)
        # hint 按数据来源给具体引导
        if idx == 0:
            self.hint.setText("💡 模拟数据：本地随机值，无板子时调试 UI 用")
        elif idx == 1:
            port = self.port.currentText().strip() or "COM3"
            self.hint.setText(
                "📋 板端：RK3588 跑 <code>board_infer.py --serial /dev/ttyS3</code>，"
                "USB-TTL 连 PC 的 <b>%s</b>" % port)
        else:
            addr = self.addr.text().strip() or DEFAULT_BOARD_ADDR
            port = self.port_tcp.text().strip() or "9000"
            self.hint.setText(
                "📋 板端：RK3588 跑 <code>board_infer.py --tcp-port %s</code>，"
                "PC 与板子接入同一网段，填 <b>%s:%s</b>" % (port, addr, port))
        # 关键：切换数据来源时必须停掉旧连接。
        # 否则旧 bridge 线程一直占着 COM 口（串口）或 socket（TCP），
        # 导致之后再连报 "拒绝访问" / 端口占用 —— 这是之前 COM3 被永久占死的根因。
        if self.worker or self.bridge:
            self._disconnect()

    # ---------------- 连接控制 ----------------
    def _toggle(self):
        if self.worker or self.bridge:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        # 兜底：无论当前什么状态，先彻底释放旧连接再建新的
        if self.worker or self.bridge:
            self._disconnect()
        idx = self.mode.currentIndex()
        try:
            if idx == 0:
                backend = DemoBackend()
                # 模拟模式采更快 (0.5 秒) + 波动更明显，便于肉眼确认"在跑"
                self.worker = NpuWorker(backend, interval=0.5)
                self.worker.sample_ready.connect(self._on_sample)
                self.worker.error.connect(self._on_error)
                self.worker.start()
                self.status.set_text("已连接 · 模拟采样中")
                self.status.set_color(C_GREEN)
                src = "模拟"
            elif idx == 1:  # 板端串口
                if not _HAS_SERIAL_BRIDGE:
                    raise RuntimeError("serial_bridge 模块不可用")
                self._conn_since = time.time()  # 用于"已开 COM3 但迟迟无 JSON"的超时提示
                self.bridge = BoardSerialBridge(
                    self.port.currentText().strip() or "COM3",
                    self.baud.text().strip() or "1500000")
                self.bridge.stats_received.connect(self._on_sample)
                self.bridge.connected.connect(self._on_bridge_conn)
                self.bridge.error.connect(self._on_error)
                self.bridge.start()
                src = "板端串口"
            else:  # idx == 2 板端TCP
                if not _HAS_TCP_BRIDGE:
                    raise RuntimeError("tcp_bridge 模块不可用")
                self._conn_since = time.time()  # 用于"已建 TCP 但迟迟无 JSON"的超时提示
                self.bridge = BoardTcpBridge(
                    self.addr.text().strip() or DEFAULT_BOARD_ADDR,
                    self.port_tcp.text().strip() or "9000")
                self.bridge.stats_received.connect(self._on_sample)
                self.bridge.connected.connect(self._on_bridge_conn)
                self.bridge.error.connect(self._on_error)
                self.bridge.start()
                src = "板端TCP"
        except Exception as e:
            self.status.set_text("连接失败: %s" % e)
            self.status.set_color(C_RED)
            return
        self.btn_conn.setText("断开")
        self.btn_conn.setObjectName("dangerBtn")
        self.btn_conn.style().unpolish(self.btn_conn)
        self.btn_conn.style().polish(self.btn_conn)
        if idx != 0:
            # 真实连接状态由 _on_bridge_conn 异步更新
            self.status.set_text("连接中…")
            self.status.set_color(C_YELLOW)
        if self.log:
            self.log.info("NPU", "NPU 监控已连接（%s）" % src)

    def _on_bridge_conn(self, ok, msg):
        if ok:
            # 串口/TCP 物理层通了，但板子是否真在发 JSON 还要等第一条数据
            self.status.set_text((msg or "已连接") + " · 等待板端数据…")
            self.status.set_color(C_GREEN)
        else:
            # 失败时把完整原因弹出来（状态灯文字只够 30 字，不够）
            self.status.set_text("连接失败")
            self.status.set_color(C_RED)
            self.btn_conn.setText("连接")
            self.btn_conn.setObjectName("primaryBtn")
            self.btn_conn.style().unpolish(self.btn_conn)
            self.btn_conn.style().polish(self.btn_conn)
            # 注意：不能在这里直接 stop()（信号来自 bridge 线程，wait 有风险）。
            # 把引用挪到 _dead_bridges，交给 _disconnect 统一清理，
            # 否则线程可能仍占着 COM 口/socket 而引用已丢，永久泄漏。
            if self.bridge is not None:
                self._dead_bridges.append(self.bridge)
            self.bridge = None
            # 主动断开时（用户点断开）会 emit connected(False, "已断开 COM3"），
            # 这种不算错误，不要弹对话框
            if not self._user_disconnecting and msg and not msg.startswith("已断开"):
                self._show_error_dialog(msg)

    def _show_error_dialog(self, detail):
        """弹一个非阻塞的失败原因对话框，给出可执行的下一步"""
        mode_idx = self.mode.currentIndex()
        if mode_idx == 1:
            port = self.port.currentText().strip() or "COM3"
            baud = self.baud.text().strip() or "1500000"
            title = "串口 %s 打开失败" % port
            text = (
                "未能在 <b>%s @ %s</b> 上读到板端数据。\n\n"
                "可能原因：\n"
                "  ① RK3588 没接 USB-TTL，或接到别的 COM 口\n"
                "  ② 板子上没运行 board_infer.py（要先 SSH 进板子跑起来）\n"
                "  ③ 波特率不匹配（RK3588 调试串口默认 1500000）\n"
                "  ④ 串口被其他程序占用（Arduino IDE / 串口助手 / 上位机其它页）\n\n"
                "下一步建议：\n"
                "  · 在板端 SSH 跑：<code>python3 board_infer.py --serial /dev/ttyS3 --baud %s</code>\n"
                "  · 没板子时切到『模拟数据』看 UI" % (port, baud, baud))
        else:
            addr = self.addr.text().strip() or DEFAULT_BOARD_ADDR
            port = self.port_tcp.text().strip() or "9000"
            title = "连接 %s:%s 失败" % (addr, port)
            text = (
                "未能连上 <b>%s:%s</b> 接收板端数据。\n\n"
                "可能原因：\n"
                "  ① PC 与 RK3588 不在同一网段（先 <code>ping %s</code>）\n"
                "  ② 板子上没运行 board_infer.py --tcp-port %s\n"
                "  ③ 防火墙挡住了 %s 端口\n"
                "  ④ IP / 端口填错了\n\n"
                "下一步建议：\n"
                "  · 在板端 SSH 跑：<code>python3 board_infer.py --tcp-port %s</code>\n"
                "  · 没板子时切到『模拟数据』看 UI" % (addr, port, addr, port, port, port))
        QMessageBox.warning(self, title, text + "\n\n技术细节：%s" % detail)

    def _disconnect(self):
        # 主动断开：让 bridge.run 末尾的 connected(False, "已断开...") 静默掉
        self._user_disconnecting = True
        if self.worker:
            self.worker.stop()
            self.worker = None
        if self.bridge:
            self.bridge.stop()
            self.bridge = None
        # 回收之前失败但线程可能仍活着的 bridge（防止 COM 口/socket 永久被占）
        for dead in self._dead_bridges:
            try:
                dead.stop()
            except Exception:
                pass
        self._dead_bridges = []
        # 关键：断开后清空所有显示，避免"旧数据残留 + 红点未连接"的歧义
        self._reset_ui()
        self.btn_conn.setText("连接")
        self.btn_conn.setObjectName("primaryBtn")
        self.btn_conn.style().unpolish(self.btn_conn)
        self.btn_conn.style().polish(self.btn_conn)
        self.status.set_text("未连接")
        self.status.set_color(C_RED)
        self._user_disconnecting = False
        self._conn_since = 0.0  # 重置 watchdog 计时
        if self.log:
            self.log.info("NPU", "NPU 监控已断开")

    def _reset_ui(self):
        """断开/初始化时把所有显示清回 '未连接' 状态"""
        self._sample_count = 0
        # 三核负载条
        for b in self.bars:
            b.set_value(0)
            b.val.setText("-- %")
        # 历史曲线
        self.history.core0.clear()
        self.history.core1.clear()
        self.history.core2.clear()
        # 板端状态文字
        self.lb_temp.setText("-- ℃")
        self.lb_mem.setText("-- / -- MB")
        self.mem_bar.setValue(0)
        self.lb_avg.setText("-- %")
        self.lb_peak.setText("-- %")
        self.lb_fps.setText("-- FPS")
        self.lb_infer.setText("-- ms")
        self.chart.update()

    def _on_error(self, msg):
        self.status.set_text(msg[:30])
        if self.log:
            self.log.error("NPU", msg)

    def _on_sample(self, d):
        # 协议归一化：兼容板端两套 stats 帧（串口 core0/1/2 与 TCP npu="%/...%"）
        d = normalize_stats(d)
        self._sample_count += 1
        vals = [d["core0"], d["core1"], d["core2"]]
        for b, v in zip(self.bars, vals):
            b.set_value(v)
        self.history.push(d)
        self.chart.update()
        # 状态指示灯实时显示已采点数 + 模式，让"在跑"一眼可见
        if self.bridge is None and self.worker is not None:
            self.status.set_text("已连接 · 模拟采样中 · %d 点" % self._sample_count)
        else:
            # 收到第一条数据后，'等待板端数据…' 升级为'实时·N 点'
            self.status.set_text("已连接 · 实时 · %d 点" % self._sample_count)
        if d.get("temp") is not None:
            self.lb_temp.setText("%.1f ℃" % d["temp"])
        if d.get("mem_used") is not None and d.get("mem_total"):
            self.lb_mem.setText("%.0f / %.0f MB" % (d["mem_used"], d["mem_total"]))
            self.mem_bar.setValue(int(d["mem_used"] * 100 / d["mem_total"]))
        elif d.get("mem_available") is not None:
            # 板端只发 mem_available（无 total）的兜底显示
            self.lb_mem.setText("可用 %d MB" % d["mem_available"])
        avg = sum(vals) / 3.0
        self.lb_avg.setText("%.0f %%" % avg)
        self.lb_peak.setText("%d %%" % max(vals))
        if d.get("fps") is not None:
            self.lb_fps.setText("%.1f FPS" % d["fps"])
        if d.get("infer_ms") is not None:
            self.lb_infer.setText("%.1f ms" % d["infer_ms"])

    def showEvent(self, e):
        """页签每次可见时，启动一个 1s 周期的「连接但无数据」巡检，避免长时间卡在『等待板端数据…』看不出问题"""
        super().showEvent(e)
        if not hasattr(self, "_watchdog") or self._watchdog is None:
            self._watchdog = QTimer(self)
            self._watchdog.setInterval(1000)
            self._watchdog.timeout.connect(self._watch_no_data)
            self._watchdog.start()

    def _watch_no_data(self):
        # 仅在『板端真实连接』模式下巡检（模拟模式自己会出数据，无需提醒）
        if self.bridge is None or self._sample_count > 0 or not self._conn_since:
            return
        elapsed = time.time() - self._conn_since
        if 5 < elapsed <= 10:
            self.status.set_text("⚠ 已开 COM3 · 等板端数据 %ds" % int(elapsed))
        elif elapsed > 10:
            self.status.set_text("⚠ 等板端数据 %ds · 检查 board_infer.py" % int(elapsed))

    def closeEvent(self, e):
        self._disconnect()
        super().closeEvent(e)
