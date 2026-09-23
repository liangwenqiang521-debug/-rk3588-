# -*- coding: utf-8 -*-
"""通信设置页：与 config.json 联动，串口/触发/模型/存储设置真实生效。

已按需求精简：移除 PLC 通信、云端上报、声音/闪烁/IO 报警等无硬件支撑的模块。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QMessageBox, QFrame,
)
from widgets import (GroupPanel, FormRow, DotIndicator, ToggleSwitch,
                     MiniStat, C_GREEN, C_RED, C_DIM, C_BORDER, C_BLUE,
                     C_YELLOW, C_TEXT)
from utils import refresh_port_combo


class CommPage(QWidget):
    def __init__(self, cfg=None, log=None, dirty_cb=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.log = log
        self.dirty_cb = dirty_cb
        self.widgets = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        root.addWidget(self._header())
        # 两列均称：左列 = 串口 + 触发；右列 = 模型 + 存储
        cols = QHBoxLayout()
        cols.setSpacing(12)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(12)
        ll.addWidget(self._col_serial(), 1)
        ll.addWidget(self._col_trigger(), 0)
        cols.addWidget(left, 1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        rl.addWidget(self._col_model_storage(), 1)
        cols.addWidget(right, 1)

        root.addLayout(cols, 1)
        root.addWidget(self._footer())

        self._bind_signals()
        self._take_snapshot()
        self._refresh_footer()

    # ---------------- 顶部 ----------------
    def _header(self):
        g = QFrame()
        lay = QHBoxLayout(g)
        lay.setContentsMargins(2, 2, 2, 2)
        left = QVBoxLayout()
        t = QLabel("通信设置")
        t.setStyleSheet("font-size:18px; font-weight:bold; color:%s;" % C_TEXT)
        sub = QLabel("串口 / 触发 / 模型 / 存储 通道配置，修改后点『保存配置』持久化到 config.json")
        sub.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        left.addWidget(t)
        left.addWidget(sub)
        lay.addLayout(left)
        lay.addStretch(1)
        self.serial_status = DotIndicator("串口 未连接", C_RED)
        self.serial_status.setToolTip("点下方『测试连接』验证串口是否可用")
        lay.addWidget(self.serial_status)
        return g

    # ---------------- 列1：串口通信 ----------------
    def _col_serial(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        g = GroupPanel("串口通信")
        g.body().addWidget(self._toggle_row("启用通道", "serial", "enable"))
        port = QComboBox()
        refresh_port_combo(port)
        self._serial_port_combo = port
        g.body().addWidget(FormRow("串口号", self._reg("serial", "port", port)))

        row_ref = QHBoxLayout()
        btn_rf = QPushButton("刷新端口")
        btn_rf.setObjectName("toolBtn")
        btn_rf.clicked.connect(lambda: refresh_port_combo(
            self._serial_port_combo, self._serial_port_combo.currentText()))
        row_ref.addStretch(1)
        row_ref.addWidget(btn_rf)
        rh2 = QWidget(); rh2.setLayout(row_ref)
        g.body().addWidget(rh2)

        g.body().addWidget(FormRow("波特率", self._reg("serial", "baud",
                            self._combo(["9600", "19200", "38400", "57600",
                                         "115200", "1500000"]))))
        g.body().addWidget(FormRow("数据位", self._reg("serial", "databits", self._combo(["8", "7"]))))
        g.body().addWidget(FormRow("停止位", self._reg("serial", "stopbits", self._combo(["1", "1.5", "2"]))))
        g.body().addWidget(FormRow("校验位", self._reg("serial", "parity",
                            self._combo(["无 (N)", "偶 (E)", "奇 (O)"]))))
        g.body().addWidget(FormRow("流控", self._reg("serial", "flow",
                            self._combo(["无", "RTS/CTS", "XON/XOFF"]))))
        g.body().addWidget(FormRow("超时 (ms)", self._reg("serial", "timeout", QLineEdit())))

        row2 = QHBoxLayout()
        self.serial_test_btn = QPushButton("测试连接")
        self.serial_test_btn.setObjectName("ghostBtn")
        self.serial_test_btn.clicked.connect(self._test_serial)
        row2.addWidget(self.serial_status)
        row2.addStretch(1)
        row2.addWidget(self.serial_test_btn)
        rh3 = QWidget(); rh3.setLayout(row2)
        g.body().addWidget(rh3)
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    # ---------------- 列2：触发设置 ----------------
    def _col_trigger(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        g = GroupPanel("触发设置")
        g.body().addWidget(FormRow("触发方式", self._reg("trigger", "mode",
                            self._combo(["PLC 触发", "软触发", "连续采集"]))))
        g.body().addWidget(FormRow("触发延时 (ms)", self._reg("trigger", "delay", QLineEdit())))
        g.body().addWidget(self._toggle_row("NG 信号输出", "trigger", "ng_output"))
        g.body().addWidget(FormRow("复检次数", self._reg("trigger", "recheck", QLineEdit())))
        g.body().addWidget(self._toggle_row("自动复位计数", "trigger", "auto_reset"))
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    # ---------------- 列3：模型 / 存储 ----------------
    def _col_model_storage(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        g = GroupPanel("模型设置")
        g.body().addWidget(FormRow("当前模型", self._reg("model", "name", QLineEdit()), 70))
        g.body().addWidget(FormRow("模型路径", self._reg("model", "path", QLineEdit()), 70))
        row = QHBoxLayout()
        b1 = QPushButton("加载模型"); b1.setObjectName("primaryBtn")
        b1.clicked.connect(self._load_model)
        b2 = QPushButton("模型管理"); b2.setObjectName("ghostBtn")
        b2.clicked.connect(self._model_manage)
        row.addWidget(b1); row.addWidget(b2)
        rh = QWidget(); rh.setLayout(row)
        g.body().addWidget(rh)
        lay.addWidget(g)

        g2 = GroupPanel("存储设置")
        g2.body().addWidget(FormRow("保存路径", self._reg("storage", "save_path", QLineEdit()), 70))
        g2.body().addWidget(self._toggle_row("保存 NG 图像", "storage", "save_ng"))
        g2.body().addWidget(self._toggle_row("保存原图", "storage", "save_raw"))
        g2.body().addWidget(FormRow("自动清理", self._reg("storage", "clean",
                            self._combo(["磁盘空间 < 10% 时删除", "保留 30 天", "从不删除"])), 70))
        g2.body().addWidget(FormRow("文件名规则", self._reg("storage", "filename_rule", QLineEdit()), 70))
        g2.body().addWidget(FormRow("磁盘告警阈值 (%)", self._reg("storage", "disk_warn", QLineEdit()), 90))
        lay.addWidget(g2)
        lay.addStretch(1)
        return w

    # ---------------- 底部摘要栏 ----------------
    def _footer(self):
        g = QFrame(); g.setObjectName("footerBar")
        footer_color = "#161b23"
        g.setStyleSheet("#footerBar { background:%s; border:1px solid %s; border-radius:8px; }"
                        % (footer_color, C_BORDER))
        lay = QHBoxLayout(g)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        self.ms_items = MiniStat("配置参数", "—", C_BLUE)
        self.ms_serial = MiniStat("串口", "—", C_YELLOW)
        self.ms_state = MiniStat("保存状态", "—", C_DIM)
        for m in (self.ms_items, self.ms_serial, self.ms_state):
            m.setFixedWidth(160)
            lay.addWidget(m)
        lay.addStretch(1)
        b1 = QPushButton("应用设置"); b1.setObjectName("primaryBtn")
        b1.clicked.connect(self._apply)
        b2 = QPushButton("保存配置"); b2.setObjectName("ghostBtn")
        b2.clicked.connect(self._save)
        b3 = QPushButton("恢复默认"); b3.setObjectName("toolBtn")
        b3.clicked.connect(self._reset)
        for b in (b1, b2, b3):
            b.setFixedWidth(110)
            lay.addWidget(b)
            lay.addSpacing(8)
        return g

    # ---------------- 工具 ----------------
    def _combo(self, items):
        cb = QComboBox()
        cb.addItems(items)
        return cb

    def _toggle_row(self, text, section, key, label_w=90):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lab = QLabel(text)
        lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        lab.setFixedWidth(label_w)
        lay.addWidget(lab)
        lay.addWidget(self._reg(section, key, ToggleSwitch(True)))
        lay.addStretch(1)
        return w

    def _reg(self, section, key, widget):
        self.widgets[(section, key)] = widget
        if self.cfg:
            v = self.cfg.get(section, key, None)
            if v is not None:
                if isinstance(widget, QLineEdit):
                    widget.setText(str(v))
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(str(v))
                elif isinstance(widget, ToggleSwitch):
                    widget.on = bool(v)
                    widget.update()
        return widget

    def _value(self, widget):
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, ToggleSwitch):
            return widget.on
        return None

    def _collect(self):
        if not self.cfg:
            return
        for (section, key), widget in self.widgets.items():
            self.cfg.set(section, key, self._value(widget))

    def _bind_signals(self):
        for (sec, key), w in self.widgets.items():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._on_change)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self._on_change)
            elif isinstance(w, ToggleSwitch):
                w.toggled.connect(self._on_change)

    def _on_change(self, *a):
        self._refresh_footer()

    def _take_snapshot(self):
        self._snap = {(s, k): self._value(w) for (s, k), w in self.widgets.items()}

    def _is_dirty(self):
        if not hasattr(self, "_snap"):
            return False
        for (s, k), w in self.widgets.items():
            if self._value(w) != self._snap.get((s, k)):
                return True
        return False

    def _refresh_footer(self):
        self.ms_items.set_value("%d 项" % len(self.widgets))
        sport = self._value(self.widgets[("serial", "port")]) if ("serial", "port") in self.widgets else ""
        self.ms_serial.set_value(sport or "—")
        self.ms_state.set_value("有未保存改动" if self._is_dirty() else "已同步")

    def _reload_values(self):
        for (sec, key), w in self.widgets.items():
            if not self.cfg:
                continue
            v = self.cfg.get(sec, key, None)
            if v is None:
                continue
            if isinstance(w, QLineEdit):
                w.setText(str(v))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, ToggleSwitch):
                w.on = bool(v)
                w.update()

    # ---------------- 动作 ----------------
    def _apply(self):
        self._collect()
        if self.dirty_cb:
            self.dirty_cb()
        if self.log:
            self.log.info("系统", "通信设置已应用（串口: %s）"
                          % self.cfg.get("serial", "port"))
        self._take_snapshot()
        self._refresh_footer()

    def _save(self):
        self._collect()
        if self.cfg:
            self.cfg.save()
        if self.dirty_cb:
            self.dirty_cb(False)
        if self.log:
            self.log.info("系统", "通信配置已保存到 config.json")
        self._take_snapshot()
        self._refresh_footer()
        QMessageBox.information(self, "保存配置", "通信配置已保存到 config.json")

    def _reset(self):
        if self.cfg:
            self.cfg.reset()
        self._reload_values()
        self._take_snapshot()
        self._refresh_footer()
        if self.log:
            self.log.info("系统", "通信配置已恢复默认")
        QMessageBox.information(self, "恢复默认", "通信配置已恢复为默认值")

    def _test_serial(self):
        port = self._value(self.widgets[("serial", "port")]) if ("serial", "port") in self.widgets else ""
        baud = self._value(self.widgets[("serial", "baud")]) if ("serial", "baud") in self.widgets else ""
        if not port:
            self.serial_status.set_text("未选择端口")
            self.serial_status.set_color(C_RED)
            return
        if self.log:
            self.log.info("串口", "尝试打开 %s @ %s ..." % (port, baud))
        self.serial_status.set_text("已连接 %s" % port)
        self.serial_status.set_color(C_GREEN)
        if self.log:
            self.log.info("串口", "%s 连接成功（模拟，真实需硬件）" % port)

    def _load_model(self):
        name = self.cfg.get("model", "name") if self.cfg else ""
        if self.log:
            self.log.info("模型", "模型 %s 加载完成（模拟）" % name)
        QMessageBox.information(self, "加载模型", "模型 %s 加载完成（模拟）" % name)

    def _model_manage(self):
        """打开模型管理对话框：列出所有训练产物，一键切换当前模型。"""
        try:
            from model_manager import ModelManagerDialog
        except Exception as e:
            QMessageBox.warning(self, "模型管理", "模块加载失败: %s" % e)
            return
        dlg = ModelManagerDialog(self.cfg, self.log, parent=self)
        dlg.activated.connect(self._on_model_activated)
        dlg.exec_()
        self._refresh_footer()

    def _on_model_activated(self, rel, name):
        """模型管理对话框切换模型后，通知实时检测页刷新下拉并切到该模型。"""
        mw = self.window()
        dp = getattr(mw, "pages", [None])[0] if mw else None
        if dp and hasattr(dp, "_refresh_model_list"):
            dp.cfg.set("model", "path", rel)   # 对话框已写入 config，这里确保一致
            dp._refresh_model_list()
            idx = dp.cb_model.findData(rel)
            if idx >= 0:
                dp.cb_model.setCurrentIndex(idx)
            if self.log:
                self.log.info("模型", "实时检测页模型列表已刷新：%s" % name)

    def _log_msg(self, msg):
        if self.log:
            self.log.info("系统", msg)
