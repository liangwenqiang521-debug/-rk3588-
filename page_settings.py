# -*- coding: utf-8 -*-
"""参数设置页：与 config.json 联动，应用/保存/恢复默认真正生效"""
import os
from PyQt5.QtCore import Qt, QPoint, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox,
)
from widgets import (
    GroupPanel, FormRow, ToggleSwitch, PreviewCanvas, MiniStat,
    DotIndicator, C_DIM, C_TEXT, C_GREEN, C_RED, C_BLUE, C_YELLOW,
)

try:
    from infer import DefectDetector
    _HAS_INFER = True
except Exception:
    _HAS_INFER = False
    DefectDetector = None

BASE = os.path.dirname(os.path.abspath(__file__))


class ModelLoadWorker(QThread):
    """后台加载 YOLO 权重：避免大模型加载（数秒）把 PyQt5 主线程卡死。"""

    done = pyqtSignal(object)    # 加载成功的 DefectDetector
    failed = pyqtSignal(str)     # 失败原因

    def __init__(self, weights, conf=0.25, iou=0.45, parent=None):
        super().__init__(parent)
        self.weights = weights
        self.conf = conf
        self.iou = iou

    def run(self):
        try:
            det = DefectDetector(self.weights, conf=self.conf,
                                 imgsz=640, device="cpu", iou=self.iou)
            if det.ready:
                self.done.emit(det)
            else:
                self.failed.emit(det.load_error or "未知原因")
        except Exception as e:
            self.failed.emit(str(e))


class SettingsPage(QWidget):
    def __init__(self, cfg=None, log=None, dirty_cb=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.log = log
        self.dirty_cb = dirty_cb
        self.widgets = {}   # (section, key) -> widget

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        root.addWidget(self._header())

        cols = QHBoxLayout()
        cols.setSpacing(10)
        cols.addWidget(self._col_camera(), 1)
        cols.addWidget(self._col_model(), 1)
        cols.addWidget(self._col_roi_storage(), 1)
        root.addLayout(cols, 1)

        root.addWidget(self._footer())

        # 构造完成后延迟刷新摘要栏（避免构造期重复重绘/信号开销）
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_footer)

    # ---------------- 顶部标题 + 状态点 ----------------
    def _header(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        t = QLabel("检测参数配置")
        t.setStyleSheet("color:%s; font-size:18px; font-weight:bold;" % C_TEXT)
        sub = QLabel("修改即时生效，点击『保存配置』写入 config.json")
        sub.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        lay.addWidget(t)
        lay.addWidget(sub)
        lay.addStretch(1)
        self.dot_cam = DotIndicator("相机 未连接", C_RED)
        self.dot_model = DotIndicator("模型 就绪", C_GREEN)
        self.dot_storage = DotIndicator("存储 已配置", C_GREEN)
        for d in (self.dot_cam, self.dot_model, self.dot_storage):
            lay.addWidget(d)
        return w

    # ---------------- 工具 ----------------
    def _reg(self, section, key, widget, live=True):
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
        if live:
            try:
                if isinstance(widget, QLineEdit):
                    widget.textChanged.connect(lambda *_: self._refresh_footer())
                elif isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(lambda *_: self._refresh_footer())
            except Exception:
                pass
        return widget

    def _value(self, widget):
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, ToggleSwitch):
            return widget.on
        return None

    def _log(self, msg):
        if self.log:
            self.log.info("系统", msg)

    def _toggle_row(self, text, section, key):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lab = QLabel(text)
        lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        lab.setFixedWidth(70)
        lay.addWidget(lab)
        lay.addWidget(self._reg(section, key, ToggleSwitch(True)))
        lay.addStretch(1)
        return w

    # ---------------- 列 1：相机 ----------------
    def _col_camera(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        g = GroupPanel("相机参数")
        cam = QComboBox(); cam.addItems(["相机 01", "相机 02", "相机 03"])
        g.body().addWidget(FormRow("相机选择", self._reg("camera", "name", cam)))
        res = QComboBox(); res.addItems(["1920×1080", "1280×720", "640×480", "2592×1944"])
        g.body().addWidget(FormRow("分辨率", self._reg("camera", "resolution", res)))
        fps = QComboBox(); fps.addItems(["30 FPS", "60 FPS", "120 FPS", "240 FPS"])
        g.body().addWidget(FormRow("采集帧率", self._reg("camera", "fps", fps)))
        trig = QComboBox(); trig.addItems(["连续触发", "软触发", "硬触发"])
        g.body().addWidget(FormRow("触发模式", self._reg("camera", "trigger", trig)))
        g.body().addWidget(FormRow("触发延时 (ms)", self._reg("camera", "trigger_delay", QLineEdit())))
        lay.addWidget(g)

        g3 = GroupPanel("使用提示")
        tip = QLabel("· 修改后点『应用设置』即时下发到检测页\n"
                     "· 点『保存配置』才会写入 config.json\n"
                     "· 点『恢复默认』还原全部参数")
        tip.setStyleSheet("color:%s; font-size:12px; line-height:1.8;" % C_DIM)
        tip.setWordWrap(True)
        g3.body().addWidget(tip)
        lay.addWidget(g3)

        lay.addStretch(1)
        return w

    # ---------------- 列 2：模型 ----------------
    def _col_model(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        g = GroupPanel("检测模型")
        g.body().addWidget(FormRow("当前模型", self._reg("model", "name", QLineEdit())))
        g.body().addWidget(FormRow("模型文件", self._reg("model", "path", QLineEdit())))
        size = QComboBox(); size.addItems(["640×640", "320×320", "1280×1280"])
        g.body().addWidget(FormRow("输入尺寸", self._reg("model", "input_size", size)))
        dev = QComboBox(); dev.addItems(["CPU", "Auto", "GPU", "NPU (RK3588)"])
        g.body().addWidget(FormRow("推理设备", self._reg("model", "device", dev)))
        g.body().addWidget(FormRow("置信度阈值", self._reg("model", "conf", QLineEdit())))
        g.body().addWidget(FormRow("最小缺陷面积 (px)", self._reg("model", "min_area", QLineEdit())))
        g.body().addWidget(FormRow("IOU 阈值", self._reg("model", "iou", QLineEdit())))
        self.btn_load = QPushButton("加载模型")
        self.btn_load.setObjectName("primaryBtn")
        self.btn_load.setToolTip("真实加载当前模型权重（后台线程），加载完成后实时检测页可直接复用")
        self.btn_load.clicked.connect(self._load_model)
        g.body().addWidget(self.btn_load)
        lay.addWidget(g)

        info = QHBoxLayout()
        info.setSpacing(8)
        self.ms_in = MiniStat("输入尺寸", "—", C_GREEN)
        self.ms_dev = MiniStat("推理设备", "—", C_YELLOW)
        self.ms_conf = MiniStat("置信度", "—", C_BLUE)
        for m in (self.ms_in, self.ms_dev, self.ms_conf):
            info.addWidget(m)
        info.addStretch(1)
        lay.addLayout(info)

        lay.addStretch(1)
        return w

    # ---------------- 列 3：ROI + 预览 + 存储 ----------------
    def _col_roi_storage(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        g = GroupPanel("ROI 设置")
        self.roi_table = QTableWidget(2, 4)
        self.roi_table.setHorizontalHeaderLabels(["ROI", "启用", "坐标 (x,y,w,h)", "操作"])
        self.roi_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.roi_table.verticalHeader().setVisible(False)
        self.roi_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.roi_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.roi_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.roi_table.setFixedHeight(140)
        data = [("ROI 1", "120, 120, 420, 420"), ("ROI 2", "380, 120, 150, 420")]
        for r, (name, coord) in enumerate(data):
            self._set_roi_row(r, name, coord, True)
        g.body().addWidget(self.roi_table)
        add = QPushButton("+ 添加 ROI")
        add.setObjectName("ghostBtn")
        add.clicked.connect(self._add_roi)
        g.body().addWidget(add)
        lay.addWidget(g)

        g2 = GroupPanel("ROI 预览")
        canvas = PreviewCanvas()
        canvas.setMinimumHeight(170)
        g2.body().addWidget(canvas)
        lay.addWidget(g2)

        g3 = GroupPanel("存储设置")
        g3.body().addWidget(FormRow("保存路径", self._reg("storage", "save_path", QLineEdit()), 70))
        g3.body().addWidget(self._toggle_row("保存 NG 图像", "storage", "save_ng"))
        g3.body().addWidget(self._toggle_row("保存原图", "storage", "save_raw"))
        clean = QComboBox(); clean.addItems(["磁盘空间 < 10% 时删除", "保留 30 天", "从不删除"])
        g3.body().addWidget(FormRow("自动清理", self._reg("storage", "clean", clean), 70))
        g3.body().addWidget(FormRow("文件名规则", self._reg("storage", "filename_rule", QLineEdit()), 70))
        g3.body().addWidget(FormRow("磁盘告警阈值 (%)", self._reg("storage", "disk_warn", QLineEdit()), 70))
        lay.addWidget(g3)

        lay.addStretch(1)
        return w

    def _set_roi_row(self, r, name, coord, enabled):
        self.roi_table.setItem(r, 0, QTableWidgetItem(name))
        self.roi_table.setCellWidget(r, 1, ToggleSwitch(enabled))
        self.roi_table.setItem(r, 2, QTableWidgetItem(coord))
        delbtn = QPushButton("🗑")
        delbtn.setObjectName("toolBtn")
        delbtn.setToolTip("删除该 ROI")
        delbtn.clicked.connect(lambda _, b=delbtn: self._del_roi(b))
        self.roi_table.setCellWidget(r, 3, delbtn)

    def _add_roi(self):
        r = self.roi_table.rowCount()
        self.roi_table.insertRow(r)
        self._set_roi_row(r, "ROI %d" % (r + 1), "0, 0, 200, 200", True)
        self._log("已添加 ROI %d" % (r + 1))

    def _del_roi(self, btn):
        # 遍历匹配按钮所属行（不依赖几何布局，offscreen 下更稳健）
        row = -1
        for r in range(self.roi_table.rowCount()):
            if self.roi_table.cellWidget(r, 3) is btn:
                row = r
                break
        if row >= 0:
            self.roi_table.removeRow(row)
            self._log("已删除 ROI 行 %d" % (row + 1))

    # ---------------- 底部：配置摘要 + 操作 ----------------
    def _footer(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.ms_items = MiniStat("配置参数", "—", C_BLUE)
        self.ms_size = MiniStat("模型体积", "—", C_GREEN)
        self.ms_fmt = MiniStat("模型格式", "—", C_YELLOW)
        self.ms_state = MiniStat("保存状态", "—", C_DIM)
        for m in (self.ms_items, self.ms_size, self.ms_fmt, self.ms_state):
            lay.addWidget(m)
        lay.addStretch(1)
        b1 = QPushButton("应用设置"); b1.setObjectName("primaryBtn")
        b1.clicked.connect(self._apply)
        b2 = QPushButton("保存配置"); b2.setObjectName("ghostBtn")
        b2.clicked.connect(self._save)
        b3 = QPushButton("恢复默认"); b3.setObjectName("ghostBtn")
        b3.clicked.connect(self._reset)
        for b in (b1, b2, b3):
            b.setFixedWidth(110)
            lay.addWidget(b)
            lay.addSpacing(8)
        return w

    def _model_size_str(self):
        p = self.cfg.get("model", "path") if self.cfg else ""
        if not p:
            return "—"
        if not os.path.isabs(p):
            p = os.path.join(BASE, p)
        if os.path.exists(p):
            return "%.1f MB" % (os.path.getsize(p) / 1024.0 / 1024.0)
        return "未找到"

    def _is_dirty(self):
        if not self.cfg:
            return False
        for (s, k), w in self.widgets.items():
            if self.cfg.get(s, k) != self._value(w):
                return True
        return False

    def _refresh_footer(self):
        self.ms_items.set_value("%d 项" % len(self.widgets))
        self.ms_size.set_value(self._model_size_str())
        p = self.cfg.get("model", "path") if self.cfg else ""
        self.ms_fmt.set_value(p.split(".")[-1].upper() if p else "—")
        self.ms_state.set_value("有未保存改动" if self._is_dirty() else "已同步")
        if self.cfg:
            self.ms_in.set_value(self.cfg.get("model", "input_size", "—"))
            self.ms_dev.set_value(self.cfg.get("model", "device", "—"))
            self.ms_conf.set_value(self.cfg.get("model", "conf", "—"))

    # ---------------- 操作 ----------------
    def _collect(self):
        if not self.cfg:
            return
        for (section, key), widget in self.widgets.items():
            self.cfg.set(section, key, self._value(widget))

    def _apply(self):
        self._collect()
        if self.dirty_cb:
            self.dirty_cb(True)
        self._refresh_footer()
        self._log("参数已应用（置信度阈值 %s，最小面积 %s px）"
                  % (self.cfg.get("model", "conf"), self.cfg.get("model", "min_area"))
                  if self.cfg else "")

    def _save(self):
        self._collect()
        if self.cfg:
            self.cfg.save()
        if self.dirty_cb:
            self.dirty_cb(False)
        self._refresh_footer()
        self._log("配置已保存到 config.json")
        QMessageBox.information(self, "保存配置", "配置已保存到 config.json")

    def _reset(self):
        if self.cfg:
            self.cfg.reset()
            for (section, key), widget in self.widgets.items():
                v = self.cfg.get(section, key, None)
                if v is None:
                    continue
                if isinstance(widget, QLineEdit):
                    widget.setText(str(v))
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(str(v))
                elif isinstance(widget, ToggleSwitch):
                    widget.on = bool(v)
                    widget.update()
        self._refresh_footer()
        self._log("配置已恢复默认值")

    def _detect_page(self):
        """取实时检测页实例（用于把已加载引擎注入进去）。"""
        mw = self.window()
        dp = getattr(mw, "pages", [None])[0] if mw else None
        return dp

    def _load_model(self):
        """真实加载当前模型权重（后台线程，不卡界面）。"""
        if not _HAS_INFER:
            QMessageBox.warning(
                self, "加载模型",
                "推理引擎不可用（缺少 ultralytics / OpenCV）。\n"
                "请安装：pip install ultralytics opencv-python")
            return
        weights = self.cfg.get("model", "path", "") if self.cfg else ""
        if not weights:
            QMessageBox.warning(self, "加载模型",
                                "未配置模型路径，请先在上方『模型文件』填入 .pt 路径。")
            return
        try:
            conf = float(self.cfg.get("model", "conf", "0.25"))
        except Exception:
            conf = 0.25
        try:
            iou = float(self.cfg.get("model", "iou", "0.45"))
        except Exception:
            iou = 0.45

        self.btn_load.setEnabled(False)
        self.btn_load.setText("加载中…")
        self.dot_model.set_text("模型 加载中")
        self.dot_model.set_color(C_YELLOW)
        self._log("开始加载模型: %s" % weights)
        self._worker = ModelLoadWorker(weights, conf, iou, self)
        self._worker.done.connect(self._on_model_loaded)
        self._worker.failed.connect(self._on_model_failed)
        self._worker.start()

    def _on_model_loaded(self, det):
        self.btn_load.setEnabled(True)
        self.btn_load.setText("加载模型")
        name = self.cfg.get("model", "name") if self.cfg else ""
        path = self.cfg.get("model", "path", "") if self.cfg else ""
        self.dot_model.set_text("模型 就绪")
        self.dot_model.set_color(C_GREEN)
        cls_n = len(getattr(det, "names", {}) or {})
        self._log("模型 %s 真实加载完成（%s，%d 类）" % (name, path, cls_n))
        # 注入实时检测页：已加载引擎直接复用，下次推理无需再等加载
        dp = self._detect_page()
        if dp is not None:
            dp.engine = det
            if hasattr(dp, "_update_model_ind"):
                dp._update_model_ind(True, "模型已加载")
        QMessageBox.information(
            self, "加载模型",
            "模型加载完成：\n%s\n\n共 %d 个类别，已注入实时检测页，可直接开始检测。"
            % (name, cls_n))

    def _on_model_failed(self, msg):
        self.btn_load.setEnabled(True)
        self.btn_load.setText("加载模型")
        self.dot_model.set_text("模型 加载失败")
        self.dot_model.set_color(C_RED)
        self._log("模型加载失败: %s" % msg)
        QMessageBox.warning(self, "加载模型", "模型加载失败：\n%s" % msg)
