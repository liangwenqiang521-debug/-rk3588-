# -*- coding: utf-8 -*-
"""运行日志页：显示真实日志，级别/模块/关键字筛选，导出 CSV"""
import os
import time
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QButtonGroup, QMessageBox,
)
from widgets import GroupPanel, LabeledProgress, C_DIM, C_GREEN, C_RED, C_YELLOW

LEVEL_COLOR = {"信息": C_GREEN, "警告": C_YELLOW, "错误": C_RED}
BASE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE, "exports")


class LogPage(QWidget):
    def __init__(self, log=None, sys_mon=None, start_ts=None, parent=None):
        super().__init__(parent)
        self.log = log
        self.sys_mon = sys_mon
        self.start_ts = start_ts
        self.level = "全部"

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---------------- 筛选条 ----------------
        g = GroupPanel("日志筛选")
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.level_group = QButtonGroup(self)
        for i, t in enumerate(["全部", "信息", "警告", "错误"]):
            b = QPushButton(t)
            b.setCheckable(True)
            b.setObjectName("filterBtn")
            if i == 0:
                b.setChecked(True)
            self.level_group.addButton(b, i)
            bar.addWidget(b)
        self.level_group.buttonClicked.connect(self._on_level)
        bar.addSpacing(12)
        lab = QLabel("模块")
        lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        bar.addWidget(lab)
        self.cb_module = QComboBox()
        self.cb_module.addItems(["全部", "系统", "相机", "模型", "PLC", "检测"])
        self.cb_module.setFixedWidth(90)
        self.cb_module.currentTextChanged.connect(lambda _: self._refresh())
        bar.addWidget(self.cb_module)
        self.ed_kw = QLineEdit(); self.ed_kw.setPlaceholderText("请输入关键字")
        self.ed_kw.returnPressed.connect(self._refresh)
        bar.addWidget(self.ed_kw, 1)
        b1 = QPushButton("查询"); b1.setObjectName("primaryBtn")
        b1.clicked.connect(self._refresh)
        self.btn_live = QPushButton("实时刷新")
        self.btn_live.setObjectName("ghostBtn")
        self.btn_live.setCheckable(True)
        self.btn_live.setChecked(True)
        b3 = QPushButton("导出日志"); b3.setObjectName("ghostBtn")
        b3.clicked.connect(self._export)
        bar.addWidget(self.btn_live)
        bar.addWidget(b3)
        holder = QWidget(); holder.setLayout(bar)
        g.body().addWidget(holder)
        root.addWidget(g)

        # ---------------- 日志表 + 详情 ----------------
        split = QSplitter(Qt.Horizontal)

        g2 = GroupPanel("实时日志")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["时间", "级别", "模块", "内容"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellClicked.connect(self._show_detail)
        g2.body().addWidget(self.table)
        split.addWidget(g2)

        right = QWidget()
        right.setFixedWidth(300)
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(8)

        g3 = GroupPanel("日志详情")
        self.detail = QTableWidget(6, 2)
        self.detail.setHorizontalHeaderLabels(["项目", "值"])
        self.detail.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.detail.verticalHeader().setVisible(False)
        self.detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, k in enumerate(["时间", "级别", "模块", "线程", "代码", "内容"]):
            self.detail.setItem(r, 0, QTableWidgetItem(k))
            self.detail.setItem(r, 1, QTableWidgetItem("--"))
        g3.body().addWidget(self.detail)
        rlay.addWidget(g3)

        g4 = GroupPanel("系统状态")
        self._sys_widgets = {}
        w_up = self._kv("运行时间", "--:--:--"); g4.body().addWidget(w_up)
        self._sys_widgets["uptime"] = w_up
        w_fps = self._kv("检测帧率", "-- FPS"); g4.body().addWidget(w_fps)
        self._sys_widgets["fps"] = w_fps
        self._cpu_prog = LabeledProgress("CPU", 0)
        g4.body().addWidget(self._cpu_prog)
        self._mem_prog = LabeledProgress("内存", 0)
        g4.body().addWidget(self._mem_prog)
        self._npu_prog = LabeledProgress("NPU", 0)
        g4.body().addWidget(self._npu_prog)
        self._disk_prog = LabeledProgress("磁盘剩余", 100)
        g4.body().addWidget(self._disk_prog)
        rlay.addWidget(g4)
        rlay.addStretch(1)
        split.addWidget(right)
        root.addWidget(split, 1)

        self.foot = QLabel("日志总数: 0    信息: 0    警告: 0    错误: 0")
        self.foot.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        root.addWidget(self.foot)

        # 订阅日志
        if self.log:
            self.log.bridge.record.connect(self._on_record)
            self._refresh()

        # 系统资源定时刷新
        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._update_sys)
        self._sys_timer.start(3000)
        self._update_sys()

    def _kv(self, k, v):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        a = QLabel(k); a.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        b = QLabel(v); b.setStyleSheet("color:#d5dbe1; font-size:11px;")
        lay.addWidget(a); lay.addStretch(1); lay.addWidget(b)
        w._value_label = b
        return w

    def _update_sys(self):
        """定时刷新系统资源状态"""
        if not self.sys_mon:
            return
        import time as _time
        if self.start_ts:
            uptime = self.sys_mon.uptime_string(self.start_ts)
            self._sys_widgets["uptime"]._value_label.setText(uptime)
        if self.sys_mon.available():
            cpu = self.sys_mon.cpu_percent()
            mem = self.sys_mon.memory_percent()
            disk_used = self.sys_mon.disk_percent("D:\\")
            disk_free = 100 - disk_used
            self._cpu_prog.set_value(cpu)
            self._mem_prog.set_value(mem)
            self._disk_prog.set_value(disk_free)
        else:
            self._sys_widgets["uptime"]._value_label.setText("（需安装 psutil）")

    def _on_level(self, btn):
        self.level = btn.text()
        self._refresh()

    def _match(self, it):
        if self.level != "全部" and it["level"] != self.level:
            return False
        mod = self.cb_module.currentText()
        if mod != "全部" and it["module"] != mod:
            return False
        kw = self.ed_kw.text().strip()
        if kw and kw not in it["content"]:
            return False
        return True

    def _refresh(self):
        if not self.log:
            return
        self.table.setRowCount(0)
        for it in reversed(list(self.log.buffer)):
            if self._match(it):
                self._append_row(it)
        self._update_foot()

    def _on_record(self, it):
        if self.btn_live.isChecked() and self._match(it):
            self._append_row(it, top=True)
        self._update_foot()

    def _append_row(self, it, top=False):
        r = 0 if top else self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(it["time"]))
        lv = QTableWidgetItem(it["level"])
        lv.setForeground(QColor(LEVEL_COLOR.get(it["level"], C_GREEN)))
        self.table.setItem(r, 1, lv)
        self.table.setItem(r, 2, QTableWidgetItem(it["module"]))
        self.table.setItem(r, 3, QTableWidgetItem(it["content"]))
        if self.table.rowCount() > 500:
            self.table.removeRow(self.table.rowCount() - 1)

    def _update_foot(self):
        if not self.log:
            return
        buf = list(self.log.buffer)
        n = len(buf)
        info = sum(1 for i in buf if i["level"] == "信息")
        warn = sum(1 for i in buf if i["level"] == "警告")
        err = sum(1 for i in buf if i["level"] == "错误")
        self.foot.setText("日志总数: %d    信息: %d    警告: %d    错误: %d"
                          % (n, info, warn, err))

    def _show_detail(self, row, col):
        vals = [self.table.item(row, 0).text(), self.table.item(row, 1).text(),
                self.table.item(row, 2).text(), "MainThread", "--",
                self.table.item(row, 3).text()]
        for r, v in enumerate(vals):
            self.detail.setItem(r, 1, QTableWidgetItem(v))

    def _export(self):
        if not self.log:
            return
        os.makedirs(EXPORT_DIR, exist_ok=True)
        path = os.path.join(EXPORT_DIR, "logs_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
        n = self.log.export_csv(path, self.level,
                                self.cb_module.currentText(),
                                self.ed_kw.text().strip())
        QMessageBox.information(self, "导出日志", "已导出 %d 条日志：\n%s" % (n, path))
