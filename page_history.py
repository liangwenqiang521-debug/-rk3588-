# -*- coding: utf-8 -*-
"""历史记录页：查询 SQLite 数据库，筛选/导出 CSV/缺陷分布/双击回看真实生效"""
import os
import time
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDateTimeEdit, QSplitter, QMessageBox,
    QButtonGroup, QDialog, QSizePolicy,
)
from widgets import (GroupPanel, StatCard, PreviewCanvas, DefectDistChart,
                     C_GREEN, C_RED, C_BLUE, C_DIM)
from utils import open_file, open_directory

BASE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE, "exports")

# 默认查询时间范围（天）——过短会导致"看起来没数据"
DEFAULT_RANGE_DAYS = 7


class HistoryPage(QWidget):
    def __init__(self, db=None, log=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.log = log
        self.rows = []
        self.result_filter = "全部"   # 结果快捷筛选：全部 / OK / NG

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---------------- 查询条件 ----------------
        g = GroupPanel("查询条件")
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.dt_start = QDateTimeEdit(QDateTime.currentDateTime().addDays(-DEFAULT_RANGE_DAYS))
        self.dt_start.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        self.dt_end = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_end.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        bar.addWidget(self._lab("开始时间")); bar.addWidget(self.dt_start)
        bar.addWidget(self._lab("结束时间")); bar.addWidget(self.dt_end)
        self.cb_product = QComboBox(); self.cb_product.addItem("全部")
        self.cb_defect = QComboBox(); self.cb_defect.addItem("全部")
        bar.addWidget(self._lab("产品型号")); bar.addWidget(self.cb_product)
        bar.addWidget(self._lab("缺陷类型")); bar.addWidget(self.cb_defect)
        self.ed_kw = QLineEdit(); self.ed_kw.setPlaceholderText("请输入关键字")
        bar.addWidget(self.ed_kw, 1)
        b1 = QPushButton("查询"); b1.setObjectName("primaryBtn")
        b1.clicked.connect(self._query)
        b2 = QPushButton("重置"); b2.setObjectName("ghostBtn")
        b2.clicked.connect(self._reset)
        b3 = QPushButton("导出记录"); b3.setObjectName("ghostBtn")
        b3.clicked.connect(self._export)
        for b in (b1, b2, b3):
            bar.addWidget(b)
        holder = QWidget(); holder.setLayout(bar)
        g.body().addWidget(holder)

        # 结果快捷筛选（B：全部 / OK / NG）
        fbar = QHBoxLayout()
        fbar.setSpacing(6)
        fbar.addWidget(self._lab("结果筛选"))
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for txt in ("全部", "OK", "NG"):
            fb = QPushButton(txt)
            fb.setObjectName("filterBtn")
            fb.setCheckable(True)
            fb.setChecked(txt == "全部")
            fb.clicked.connect(lambda _=False, t=txt: self._set_result_filter(t))
            self.filter_group.addButton(fb)
            fbar.addWidget(fb)
        fbar.addSpacing(12)
        self.lb_count = QLabel("命中 0 条")
        self.lb_count.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        fbar.addWidget(self.lb_count)
        fbar.addStretch(1)
        fholder = QWidget(); fholder.setLayout(fbar)
        g.body().addWidget(fholder)
        root.addWidget(g)

        # ---------------- 统计卡 ----------------
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self.card_total = StatCard("检测总数", "0")
        self.card_ok = StatCard("OK数量", "0", C_GREEN)
        self.card_ng = StatCard("NG数量", "0", C_RED)
        self.card_rate = StatCard("良率", "--", C_BLUE)
        for c in (self.card_total, self.card_ok, self.card_ng, self.card_rate):
            cards.addWidget(c)
        root.addLayout(cards)

        # ---------------- 表格 + 详情 ----------------
        split = QSplitter(Qt.Horizontal)

        g2 = GroupPanel("检测记录（双击行可回看图像）")
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["序号", "时间", "产品", "结果", "缺陷类型", "面积 (px)", "置信度", "图像路径"])
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.cellClicked.connect(self._show_detail)
        self.table.cellDoubleClicked.connect(self._preview_image)
        g2.body().addWidget(self.table)
        split.addWidget(g2)

        right = QWidget()
        right.setFixedWidth(320)
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(8)
        g3 = GroupPanel("记录详情")
        self.canvas = PreviewCanvas()
        self.canvas.setFixedHeight(180)
        g3.body().addWidget(self.canvas)
        self.detail = QTableWidget(6, 2)
        self.detail.setHorizontalHeaderLabels(["项目", "值"])
        self.detail.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.detail.verticalHeader().setVisible(False)
        self.detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, k in enumerate(["产品", "结果", "缺陷类型", "面积 (px)", "置信度", "检测时间"]):
            self.detail.setItem(r, 0, QTableWidgetItem(k))
            self.detail.setItem(r, 1, QTableWidgetItem("--"))
        g3.body().addWidget(self.detail)
        brow = QHBoxLayout()
        bp = QPushButton("查看原图"); bp.setObjectName("primaryBtn")
        bp.clicked.connect(self._view_image)
        bo = QPushButton("打开目录"); bo.setObjectName("ghostBtn")
        bo.clicked.connect(self._open_dir)
        brow.addWidget(bp); brow.addWidget(bo)
        bw = QWidget(); bw.setLayout(brow)
        g3.body().addWidget(bw)
        rlay.addWidget(g3)

        # B：缺陷类型分布（由查询结果驱动）
        g4 = GroupPanel("缺陷类型分布（当前查询范围）")
        self.dist_chart = DefectDistChart()
        g4.body().addWidget(self.dist_chart)
        rlay.addWidget(g4)
        split.addWidget(right)
        root.addWidget(split, 1)

        self._refresh_dicts()
        self._query()

    def _lab(self, text):
        l = QLabel(text)
        l.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        return l

    def _current_image_path(self):
        """获取当前选中行的图像路径"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            return None
        path = self.rows[row][7]
        return path if path else None

    def _view_image(self):
        """用系统默认图片查看器打开原图"""
        path = self._current_image_path()
        if not path:
            QMessageBox.information(self, "查看原图", "请先选中一条记录")
            return
        if not open_file(path):
            QMessageBox.warning(self, "查看原图",
                                "图像文件不存在或无法打开：\n%s" % path)
            if self.log:
                self.log.warning("系统", "图像文件不存在: %s" % path)

    def _open_dir(self):
        """在文件管理器中打开图像所在目录"""
        path = self._current_image_path()
        if not path:
            QMessageBox.information(self, "打开目录", "请先选中一条记录")
            return
        if not open_directory(path):
            QMessageBox.warning(self, "打开目录",
                                "目录不存在或无法打开：\n%s" % path)

    def _refresh_dicts(self):
        if not self.db:
            return
        for p in self.db.products():
            self.cb_product.addItem(p)
        for d in self.db.defect_types():
            self.cb_defect.addItem(d)

    # ---------------- 操作 ----------------
    def _set_result_filter(self, txt):
        self.result_filter = txt
        self._query()

    def _query(self):
        if not self.db:
            return
        self.rows = self.db.query(
            start=self.dt_start.dateTime().toString("yyyy-MM-dd hh:mm:ss"),
            end=self.dt_end.dateTime().toString("yyyy-MM-dd hh:mm:ss"),
            product=self.cb_product.currentText(),
            defect=self.cb_defect.currentText(),
            keyword=self.ed_kw.text().strip(),
            result=self.result_filter)
        self.table.setRowCount(0)
        for row in self.rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [str(row[0]), row[1], row[2], row[3],
                    row[4] or "--",
                    str(int(row[5])) if row[5] else "--",
                    "%.2f" % row[6] if row[6] else "--", row[7] or ""]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 3:
                    it.setForeground(Qt.red if v == "NG" else Qt.green)
                self.table.setItem(r, c, it)
        s = self.db.stats(self.rows)
        self.card_total.set_value(s["total"])
        self.card_ok.set_value(s["ok"])
        self.card_ng.set_value(s["ng"])
        self.card_rate.set_value("%.1f%%" % s["rate"] if s["total"] else "--")
        # 命中数提示（空结果时引导扩大时间范围）
        if self.rows:
            self.lb_count.setText("命中 %d 条" % len(self.rows))
        else:
            self.lb_count.setText(
                "命中 0 条 —— 无数据时试试「重置」或扩大时间范围（当前查近 %d 天）"
                % DEFAULT_RANGE_DAYS)
        # 缺陷类型分布（按 NG 记录的缺陷类型统计）
        dist = {}
        for row in self.rows:
            dt = row[4]
            if row[3] == "NG" and dt and dt != "--":
                dist[dt] = dist.get(dt, 0) + 1
        self.dist_chart.set_data(dist)
        if self.log:
            self.log.info("系统", "历史查询：命中 %d 条记录（筛选: %s）"
                          % (len(self.rows), self.result_filter))

    def _reset(self):
        self.dt_start.setDateTime(QDateTime.currentDateTime().addDays(-DEFAULT_RANGE_DAYS))
        self.dt_end.setDateTime(QDateTime.currentDateTime())
        self.cb_product.setCurrentIndex(0)
        self.cb_defect.setCurrentIndex(0)
        self.ed_kw.clear()
        self.result_filter = "全部"
        for b in self.filter_group.buttons():
            b.setChecked(b.text() == "全部")
        self._query()

    def _export(self):
        if not self.db:
            return
        if not self.rows:
            QMessageBox.information(self, "导出记录",
                                    "当前查询无记录，先查询到数据再导出。")
            return
        os.makedirs(EXPORT_DIR, exist_ok=True)
        path = os.path.join(EXPORT_DIR,
                            "records_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
        n = self.db.export_csv(path, self.rows)
        if self.log:
            self.log.info("系统", "导出检测记录 %d 条 → %s" % (n, path))
        QMessageBox.information(self, "导出记录",
                                "已导出 %d 条记录：\n%s" % (n, path))

    def _show_detail(self, row, col):
        if row >= len(self.rows):
            return
        rec = self.rows[row]
        vals = [rec[2], rec[3], rec[4] or "--",
                str(int(rec[5])) if rec[5] else "--",
                "%.2f" % rec[6] if rec[6] else "--", rec[1]]
        for r, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            if r == 1:
                it.setForeground(Qt.red if v == "NG" else Qt.green)
            self.detail.setItem(r, 1, it)
        self.canvas.set_result(rec[3], int((rec[6] or 1.0) * 100))
        # 尝试加载对应图片
        img_path = rec[7] if len(rec) > 7 and rec[7] else ""
        if img_path and os.path.exists(img_path):
            if self.canvas.set_image(img_path):
                if self.log:
                    self.log.info("系统", "已加载图片: %s" % img_path)
            else:
                self.canvas.clear_image()
        else:
            self.canvas.clear_image()

    def _preview_image(self, row, col):
        """B：双击行弹大图预览（图片存在时），否则提示路径"""
        if row >= len(self.rows):
            return
        rec = self.rows[row]
        path = rec[7] if len(rec) > 7 and rec[7] else ""
        if not path or not os.path.exists(path):
            QMessageBox.information(
                self, "回看图像",
                "该记录没有可回看的图像文件：\n%s" % (path or "（未记录路径）"))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("记录 #%s  %s  %s" % (rec[0], rec[1], rec[3]))
        lay = QVBoxLayout(dlg)
        pix = QPixmap(path)
        lab = QLabel()
        lab.setAlignment(Qt.AlignCenter)
        # 缩放到 900x640 以内，保持比例
        scaled = pix.scaled(900, 640, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lab.setPixmap(scaled)
        lay.addWidget(lab)
        info = QLabel("缺陷: %s    置信度: %s    路径: %s"
                      % (rec[4] or "--",
                         ("%.2f" % rec[6]) if rec[6] else "--", path))
        info.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        info.setWordWrap(True)
        lay.addWidget(info)
        dlg.setLayout(lay)
        dlg.resize(min(920, scaled.width() + 24), scaled.height() + 60)
        dlg.exec_()
