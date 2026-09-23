# -*- coding: utf-8 -*-
"""模型管理对话框：列出 模型训练/ 下所有可用模型，对比 mAP50 / 体积，一键设为当前模型。

与 page_detect.DetectPage._scan_models 同源逻辑（扫描 .pt + runs/<name>/weights/best.pt），
但独立成模块，避免与检测页形成循环依赖。设置当前模型后通过 activated 信号通知外界刷新。
"""
import os
import pathlib
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
)
from widgets import GroupPanel, C_DIM, C_TEXT, C_GREEN, C_YELLOW

BASE = os.path.dirname(os.path.abspath(__file__))
MT_DIR = os.path.join(BASE, "模型训练")


def _best_map50(run_dir):
    """从 run 目录的 results.csv 读最佳 mAP50(B)；无/解析失败返回 None。"""
    csvp = os.path.join(str(run_dir), "results.csv")
    if not os.path.exists(csvp):
        return None
    try:
        best = 0.0
        with open(csvp, encoding="utf-8") as f:
            header = f.readline().strip().split(",")
            key = "metrics/mAP50(B)"
            if key not in header:
                return None
            idx = header.index(key)
            for line in f:
                parts = line.strip().split(",")
                if len(parts) > idx:
                    try:
                        best = max(best, float(parts[idx]))
                    except ValueError:
                        pass
        return best if best > 0 else None
    except Exception:
        return None


def scan_models():
    """返回 [(tag, rel_path, mAP50_or_None), ...]"""
    found = []
    if os.path.isdir(MT_DIR):
        # 1) 根目录下的 pt（生产模型）
        for p in sorted(pathlib.Path(MT_DIR).glob("*.pt")):
            rel = os.path.relpath(str(p), BASE).replace("\\", "/")
            found.append(("%s (生产模型)" % p.stem, rel, None))
        # 2) runs/<name>/weights/best.pt
        for w in sorted(pathlib.Path(MT_DIR).glob("runs/*/weights/best.pt")):
            run_dir = w.parent.parent
            name = run_dir.name
            mAP = _best_map50(run_dir)
            tag = name
            if mAP is not None:
                tag += " (mAP50=%.3f)" % mAP
            else:
                tag += " (训练中…)"
            rel = os.path.relpath(str(w), BASE).replace("\\", "/")
            found.append((tag, rel, mAP))
    if not found:
        found.append(("（未找到任何模型）", "", None))
    return found


def _clean_name(tag):
    """从下拉标签里剥离 mAP / 训练中 后缀，得到干净显示名。"""
    return tag.split(" (mAP")[0].split(" (训练中")[0]


class ModelManagerDialog(QDialog):
    activated = pyqtSignal(str, str)   # (rel_path, name)

    def __init__(self, cfg=None, log=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.log = log
        self.setWindowTitle("模型管理")
        self.resize(720, 460)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        tip = QLabel("选择训练产物并『设为当前模型』，实时检测页下次推理即加载该权重（含 mAP50 与体积对比）。")
        tip.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        tip.setWordWrap(True)
        root.addWidget(tip)

        g = GroupPanel("可用模型")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["模型", "mAP50", "体积", "当前", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        g.body().addWidget(self.table)
        root.addWidget(g, 1)

        brow = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setObjectName("ghostBtn")
        self.btn_refresh.clicked.connect(self._fill)
        brow.addWidget(self.btn_refresh)
        brow.addStretch(1)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setObjectName("ghostBtn")
        self.btn_close.clicked.connect(self.accept)
        brow.addWidget(self.btn_close)
        root.addLayout(brow)

        self._fill()

    def _model_size_str(self, rel):
        if not rel:
            return "—"
        p = rel if os.path.isabs(rel) else os.path.join(BASE, rel)
        if os.path.exists(p):
            return "%.1f MB" % (os.path.getsize(p) / 1024.0 / 1024.0)
        return "未找到"

    def _fill(self):
        self.table.setRowCount(0)
        cur = self.cfg.get("model", "path", "") if self.cfg else ""
        for (tag, rel, mAP) in scan_models():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(tag))
            self.table.setItem(r, 1, QTableWidgetItem("%.3f" % mAP if mAP is not None else "—"))
            self.table.setItem(r, 2, QTableWidgetItem(self._model_size_str(rel)))
            is_cur = (rel != ""and rel == cur)
            citem = QTableWidgetItem("● 当前" if is_cur else "")
            if is_cur:
                citem.setForeground(Qt.green)
            self.table.setItem(r, 3, citem)
            btn = QPushButton("设为当前")
            btn.setObjectName("primaryBtn")
            btn.setEnabled(rel != "")
            btn.clicked.connect(lambda _=False, rr=rel, tt=tag: self._set_active(rr, tt))
            self.table.setCellWidget(r, 4, btn)

    def _set_active(self, rel, tag):
        if not rel or not self.cfg:
            return
        name = _clean_name(tag)
        self.cfg.set("model", "path", rel)
        self.cfg.set("model", "name", name)
        self.cfg.save()
        self.activated.emit(rel, name)
        if self.log:
            self.log.info("模型", "已将当前模型切换为: %s (%s)" % (name, rel))
        QMessageBox.information(self, "模型管理", "已设为当前模型：\n%s" % name)
        self._fill()
