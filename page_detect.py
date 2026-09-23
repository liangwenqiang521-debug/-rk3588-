# -*- coding: utf-8 -*-
"""实时检测页：检测结果写入数据库 + 日志 + 状态栏联动"""
import os
import time
from pathlib import Path
from PyQt5.QtCore import Qt, QTimer, QDateTime, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QToolButton, QFileDialog, QMessageBox,
    QScrollArea, QSizePolicy, QFrame,
)
from widgets import (
    GroupPanel, FormRow, MiniStat, DotIndicator, PreviewCanvas,
    ToggleSwitch, YieldTrendChart, DefectDistChart,
    C_GREEN, C_RED, C_BLUE, C_DIM, C_TEXT,
)
from utils import play_beep, disk_guard
import random
import base64

try:
    import numpy as np
except Exception:
    np = None

try:
    from infer import (DefectDetector, load_image, NAME_ZH as _NAME_ZH,
                       CLASS_COLORS as _CLASS_COLORS)
    _HAS_INFER = True
except Exception:
    _HAS_INFER = False
    DefectDetector = None
    load_image = None
    _NAME_ZH = {}
    _CLASS_COLORS = {}

# 边缘端默认地址：来自 board_env（环境变量 / board_env.local.py），
# 源码中不硬编码真实内网 IP。
try:
    import board_env
    _DEFAULT_EDGE_HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
except Exception:
    _DEFAULT_EDGE_HOST = "169.254.100.100"

# 演示模式可随机命中的缺陷类别（中文名）。
# 优先取 infer.NAME_ZH 里已登记的正式类别（含 09-21 扩展的工业常见类/表面处理类），
# 排除仅用于兼容旧合成数据的别名（scratch/dent/missing/crack），避免分布图里
# 出现"划痕"与"划痕"两个同义条目。infer 不可用时回落到内置 6 类。
_DEMO_DEFECTS = [
    v for k, v in _NAME_ZH.items()
    if k not in ("scratch", "dent", "missing", "crack")
] or ["龟裂", "夹杂物", "斑块", "麻面", "轧入氧化皮", "划痕"]

try:
    from serial_bridge import BoardSerialBridge
    _HAS_BRIDGE = True
except Exception:
    _HAS_BRIDGE = False
    BoardSerialBridge = None

try:
    from tcp_bridge import BoardTcpBridge
    _HAS_TCP = True
except Exception:
    _HAS_TCP = False
    BoardTcpBridge = None

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False
    cv2 = None


class CameraWorker(QThread):
    """后台相机采集线程：用 OpenCV 连续抓帧，向主线程发 QImage + JPEG 字节。

    本线程只负责『拿帧』；真实推理在 DetectPage 主线程同步执行（predict_cv2），
    避免把 torch 放进子线程与 Qt 事件循环冲突导致 C 层段错误（进程直接消失）。
    latest_bgr 保存最新一帧供推理读取。
    """

    frame_ready = pyqtSignal(object, object)   # (QImage, jpg_bytes)
    error = pyqtSignal(str)

    def __init__(self, device=0, interval_ms=33, parent=None):
        super().__init__(parent)
        self.device = device
        self.interval_ms = max(1, int(interval_ms))
        self._running = True
        self.latest_bgr = None

    def run(self):
        import cv2
        try:
            cap = cv2.VideoCapture(int(self.device))
        except Exception as e:
            self.error.emit("相机打开失败: %s" % e)
            return
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            self.error.emit("无法打开相机（设备 %s），可能被占用或无此设备" % self.device)
            return
        while self._running:
            ret, frame = cap.read()
            if not ret:
                self.msleep(30)
                continue
            self.latest_bgr = frame
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
            ok, buf = cv2.imencode(".jpg", frame)
            jpg = buf.tobytes() if ok else b""
            self.frame_ready.emit(qimg, jpg)
            self.msleep(self.interval_ms)
        try:
            cap.release()
        except Exception:
            pass

    def stop(self):
        self._running = False
        self.wait(2000)


class DetectPage(QWidget):
    MAX_TABLE_ROWS = 200  # 检测记录表最大保留行数，防止长时间运行 UI 卡顿

    def __init__(self, cfg=None, db=None, log=None, status_cb=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.db = db
        self.log = log
        self.status_cb = status_cb
        self.running = False
        self.total, self.ok, self.ng = 0, 0, 0
        # 状态指示回调（C：由 MainWindow 注入，用于顶栏真实状态灯）
        self.ind_cb = None

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._build_left(), 0)
        root.addWidget(self._build_center(), 1)
        root.addWidget(self._build_right(), 0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._fake_frame)

        # 自动连接剩余重试次数（开机自动连接 RK3588 用）
        self._auto_left = 0

        # 真实推理（P4）：懒加载引擎，避免拖慢启动
        self.engine = None
        self._infer_busy = False          # 已废弃（推理改为同步主线程，见 _real_tick / _run_real_detect）
        self.infer_worker = None

        # 边缘模式（RK3588 串口）：通过串口接收板端 NPU 推理结果
        self.bridge = None

        # 实时相机（PC 摄像头 / 工业相机）：连续采集 + 真实推理
        self._camera_live = False
        self.cam_worker = None
        self._cur_frame_bytes = None
        self.cam_sel = None
        # 视频录制（连续存证）
        self._recording = False
        self.video_writer = None
        self._record_path = ""
        # 用户通过「打开照片」加载的照片路径：边缘连接时把它送板端 NPU 检测
        # （与 canvas.image_path() 分开跟踪——板端回传帧会把画布图换成字节流，
        #  但"当前要送检的照片"这个语义应该保留，直到点「清除图片」）
        self._photo_path = ""
        # 09-21 修：自动节拍下同一张照片只送检一次。
        # 原先 _edge_step_tick 每 tick 都调 _send_photo_for_detect，只要照片还在
        # 就永远返回 True 并 return，cmd=next 一次都发不出去 → 板端样本序列
        # 永远停在第一张（表现为"打开照片后节拍一直在跑但计数不涨/内容不变"）。
        self._photo_sent = False

        # 边缘帧落盘/入库节流（板端 10fps，若每帧都写 JPEG + 插库会撑爆磁盘并卡死界面）：
        #   存图 = 仅 NG，且距上次 ≥2s（持续 NG 不会每帧刷盘）
        #   入库 = NG 最快 0.5s/条，OK 最快 1s/条
        self._persist_gate = True          # 入库门控
        self._last_db_ts = 0.0
        self._edge_persist_interval = 1.0
        self._save_img_gate = True         # 存图门控
        self._last_img_ts = 0.0
        self._edge_img_interval = 2.0

        # 连板后是否自动执行检测（默认否）：保持连接仅预览，手动开启后再统计/入库
        self._edge_detect_enabled = False

        # NG 声音报警（开关已从前端表单移除，默认开启；如需关闭改此初值）
        self._alarm_enabled = True

        # 开机自动连接 RK3588：等界面稳定后再连，避免阻塞启动
        QTimer.singleShot(1800, self._auto_connect)

        # 落盘文件名自增序号（配合时间戳保证唯一，见 _uniq_path）
        self._save_seq = 0

    # ---------------- 左侧 ----------------
    def _build_left(self):
        # 左栏内容较多，用滚动容器兜底：窗口再小也不会把「连接 RK3588」挤出屏幕
        inner = QWidget()
        inner.setMinimumWidth(226)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        c = self.cfg

        # ============ ① 模型与边缘连接（合并原「模型选择 + 模型推理 + 边缘部署」）============
        g_edge = GroupPanel("模型与边缘连接")

        # --- 模型选择 ---
        self.cb_model = QComboBox()
        self.cb_model.setToolTip("选择要加载的推理模型（根目录或各训练产物）")
        self._refresh_model_list()
        self.cb_model.currentIndexChanged.connect(self._on_model_selected)
        g_edge.body().addWidget(FormRow("当前模型", self.cb_model))

        btn_refresh = QPushButton("刷新模型列表")
        btn_refresh.setObjectName("toolBtn")
        btn_refresh.clicked.connect(self._refresh_model_list)
        g_edge.body().addWidget(btn_refresh)

        # --- 本机推理 ---
        if _HAS_INFER:
            self.btn_real = QPushButton(" 本机真实检测")
            self.btn_real.setObjectName("primaryBtn")
            self.btn_real.setToolTip("对当前打开的照片做真实 YOLO 推理")
            self.btn_real.clicked.connect(self._run_real_detect)
            g_edge.body().addWidget(self.btn_real)
            rm_row = QWidget()
            rml = QHBoxLayout(rm_row); rml.setContentsMargins(0, 0, 0, 0)
            rm_lab = QLabel("连续真实检测")
            rm_lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
            rm_lab.setFixedWidth(90)
            rml.addWidget(rm_lab)
            self.real_toggle = ToggleSwitch(False)
            rml.addWidget(self.real_toggle)
            rml.addStretch(1)
            g_edge.body().addWidget(rm_row)

        # --- 边缘部署 RK3588 ---
        if _HAS_BRIDGE or _HAS_TCP:
            edge_sep = QLabel("RK3588 边缘推理")
            edge_sep.setStyleSheet("color:%s; font-size:12px; font-weight:bold;"
                                   "border-top: 1px solid #2a3140; padding-top: 6px;" % C_BLUE)
            g_edge.body().addWidget(edge_sep)

            mode_row = QWidget()
            ml = QHBoxLayout(mode_row); ml.setContentsMargins(0, 0, 0, 0)
            ml_lab = QLabel("连接方式")
            ml_lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
            ml_lab.setFixedWidth(90)
            ml.addWidget(ml_lab)
            self.cb_edge_mode = QComboBox()
            self.cb_edge_mode.addItems(["串口", "网络 (TCP)"])
            emode = self.cfg.get("edge", "mode", "serial") if self.cfg else "serial"
            self.cb_edge_mode.setCurrentIndex(1 if emode == "tcp" else 0)
            ml.addWidget(self.cb_edge_mode)
            ml.addStretch(1)
            g_edge.body().addWidget(mode_row)

            self.ed_edge_host = QLineEdit(
                (self.cfg.get("edge", "host", "") if self.cfg else "") or _DEFAULT_EDGE_HOST)
            self.ed_edge_host.setPlaceholderText("串口: COM3  |  网络: 板子 IP（如 169.254.x.x）")
            g_edge.body().addWidget(FormRow("地址", self.ed_edge_host))
            self.ed_edge_port = QLineEdit(
                self.cfg.get("edge", "port", "9000") if self.cfg else "9000")
            self.ed_edge_port.setPlaceholderText("串口: 1500000  |  网络: 9000")
            g_edge.body().addWidget(FormRow("端口/波特", self.ed_edge_port))

            self.btn_edge = QPushButton(" 连接 RK3588")
            self.btn_edge.setObjectName("ghostBtn")
            self.btn_edge.clicked.connect(self._toggle_edge)
            g_edge.body().addWidget(self.btn_edge)

            self.dot_edge = DotIndicator("RK3588 未连接", C_RED)
            g_edge.body().addWidget(self.dot_edge)

            auto_row = QWidget()
            al = QHBoxLayout(auto_row); al.setContentsMargins(0, 0, 0, 0)
            al.setSpacing(6)
            al_lab = QLabel("开机自动连接")
            al_lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
            al.addWidget(al_lab)
            self.sw_auto_edge = ToggleSwitch(
                bool(self.cfg.get("edge", "auto_connect", False)) if self.cfg else False)
            self.sw_auto_edge.setToolTip(
                "启动软件后自动连接 RK3588（网络 TCP 模式；失败会重试 3 次）")
            self.sw_auto_edge.toggled.connect(self._on_auto_edge_toggled)
            al.addWidget(self.sw_auto_edge)
            al.addSpacing(14)

            dl_lab = QLabel("连板自动检测")
            dl_lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
            al.addWidget(dl_lab)
            self.sw_auto_edge_detect = ToggleSwitch(
                bool(self.cfg.get("edge", "auto_detect", False)) if self.cfg else False)
            self.sw_auto_edge_detect.setToolTip(
                "RK3588 连接成功后立即开始检测、统计、入库；关闭则只显示画面")
            self.sw_auto_edge_detect.toggled.connect(self._on_auto_detect_toggled)
            al.addWidget(self.sw_auto_edge_detect)
            al.addStretch(1)
            g_edge.body().addWidget(auto_row)
        elif not _HAS_INFER:
            hint = QLabel("推理引擎未加载（缺少 ultralytics）")
            hint.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
            g_edge.body().addWidget(hint)
        lay.addWidget(g_edge)

        # ============ ② 检测参数 ============
        g2 = GroupPanel("检测参数")
        self.ed_conf = QLineEdit(c.get("model", "conf", "0.85") if c else "0.85")
        self.ed_area = QLineEdit(c.get("model", "min_area", "50") if c else "50")
        self.ed_iou = QLineEdit(c.get("model", "iou", "0.35") if c else "0.35")
        g2.body().addWidget(FormRow("置信度阈值", self.ed_conf))
        g2.body().addWidget(FormRow("最小面积(px)", self.ed_area))
        g2.body().addWidget(FormRow("NMS IoU", self.ed_iou))
        speed = QComboBox(); speed.addItems(["快速 (500ms)", "正常 (1000ms)", "慢速 (2000ms)"])
        speed.setCurrentIndex(1)
        self.cb_speed = speed
        g2.body().addWidget(FormRow("检测间隔", speed))
        lay.addWidget(g2)

        # ============ ③ ROI 设置 ============
        g3 = GroupPanel("ROI 设置")
        roi_row = QHBoxLayout()
        roi_row.setSpacing(10)
        for name in ("ROI 1", "ROI 2"):
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(6)
            lab = QLabel(name)
            lab.setStyleSheet("color:%s; font-size:12px;" % C_TEXT)
            hl.addWidget(lab)
            hl.addWidget(ToggleSwitch(True))
            roi_row.addWidget(holder)
        roi_row.addStretch(1)
        roi_holder = QWidget(); roi_holder.setLayout(roi_row)
        g3.body().addWidget(roi_holder)
        add = QPushButton("+ 添加 ROI")
        add.setObjectName("ghostBtn")
        add.clicked.connect(lambda: self._log("信息", "检测", "添加 ROI（示例操作）"))
        g3.body().addWidget(add)
        lay.addWidget(g3)

        lay.addStretch(1)

        # --- 操作按钮固定在底部（不随内容滚动，始终可点）---
        ops = QWidget()
        opl = QVBoxLayout(ops)
        opl.setContentsMargins(0, 0, 0, 0)
        opl.setSpacing(8)
        self.btn_start = QPushButton("  开始检测")
        self.btn_start.setObjectName("primaryBtn")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = QPushButton("■  停止检测")
        self.btn_stop.setObjectName("dangerBtn")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_next = QPushButton("▸  检测下一张")
        self.btn_next.setObjectName("ghostBtn")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self._next_one)
        opl.addWidget(self.btn_start)
        opl.addWidget(self.btn_stop)
        opl.addWidget(self.btn_next)

        row_ops = QHBoxLayout()
        row_ops.setSpacing(8)
        save = QPushButton("保存图像")
        save.setObjectName("ghostBtn")
        save.clicked.connect(self._save_image)
        evid = QPushButton("存证")
        evid.setObjectName("ghostBtn")
        evid.setToolTip("一键把当前画面存入存储目录（不弹对话框）")
        evid.clicked.connect(self._save_evidence)
        row_ops.addWidget(save)
        row_ops.addWidget(evid)
        holder_ops = QWidget(); holder_ops.setLayout(row_ops)
        opl.addWidget(holder_ops)

        # --- 外层容器：滚动区 + 底部操作栏 ---
        outer = QWidget()
        outer.setFixedWidth(252)
        olay = QVBoxLayout(outer)
        olay.setContentsMargins(0, 0, 0, 0)
        olay.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        # 让滚动内容宽度跟随视口，避免横向溢出把滚动条盖到内容上
        inner.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        scroll.setWidget(inner)
        scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        olay.addWidget(scroll, 1)
        olay.addWidget(ops, 0)
        return outer

    # ---------------- 中间 ----------------
    def _build_center(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        g = GroupPanel("实时预览")
        bar = QHBoxLayout()
        bar.setSpacing(6)
        # 工具栏：全部用文字按钮，避免 emoji 在 Windows 下渲染成方块
        self.tb_play = QToolButton()
        self.tb_play.setText("开始")
        self.tb_play.setToolTip("开始检测（F5）")
        self.tb_play.clicked.connect(self._start)
        bar.addWidget(self.tb_play)
        self.tb_pause = QToolButton()
        self.tb_pause.setText("停止")
        self.tb_pause.setToolTip("停止检测（F5）")
        self.tb_pause.setEnabled(False)
        self.tb_pause.clicked.connect(self._stop)
        bar.addWidget(self.tb_pause)
        self.tb_live = QToolButton()
        self.tb_live.setText("实时相机")
        self.tb_live.setToolTip("实时相机采集（连接 PC/工业相机，连续推理）")
        self.tb_live.clicked.connect(self._toggle_camera)
        bar.addWidget(self.tb_live)
        self.tb_rec = QToolButton()
        self.tb_rec.setText("录制")
        self.tb_rec.setToolTip("录制实时相机画面（再次点击停止并保存录像）")
        self.tb_rec.clicked.connect(self._toggle_record)
        bar.addWidget(self.tb_rec)
        self.tb_zoomin = QToolButton()
        self.tb_zoomin.setText("放大")
        self.tb_zoomin.setToolTip("放大图片")
        self.tb_zoomin.clicked.connect(lambda: self.canvas.zoom_in())
        bar.addWidget(self.tb_zoomin)
        self.tb_zoomout = QToolButton()
        self.tb_zoomout.setText("缩小")
        self.tb_zoomout.setToolTip("缩小图片")
        self.tb_zoomout.clicked.connect(lambda: self.canvas.zoom_out())
        bar.addWidget(self.tb_zoomout)
        for b in (self.tb_play, self.tb_pause, self.tb_live,
                  self.tb_rec, self.tb_zoomin, self.tb_zoomout):
            b.setObjectName("toolBtn")
        bar.addSpacing(10)
        # 打开照片按钮
        btn_open = QPushButton("打开照片")
        btn_open.setObjectName("toolBtn")
        btn_open.clicked.connect(self._open_image)
        bar.addWidget(btn_open)
        # 清除图片按钮
        btn_clear = QPushButton("清除图片")
        btn_clear.setObjectName("toolBtn")
        btn_clear.clicked.connect(self._clear_image)
        bar.addWidget(btn_clear)
        bar.addSpacing(10)
        zoom = QComboBox(); zoom.addItems(["100%", "75%", "50%", "200%"])
        zoom.setFixedWidth(80)
        zoom.setToolTip("缩放比例（也可用滚轮/🔍±按钮）")
        self.cb_zoom = zoom
        bar.addWidget(zoom)
        bar.addStretch(1)
        self.dot_cam = DotIndicator("相机未连接", C_RED)
        self.dot_cam.setToolTip("未接入相机 SDK；打开照片后显示“图像源:照片”")
        bar.addWidget(self.dot_cam)
        holder = QWidget(); holder.setLayout(bar)
        g.body().addWidget(holder)

        self.canvas = PreviewCanvas()
        # 缩放下拉框 ↔ 画布双向同步（A）
        self.cb_zoom.currentTextChanged.connect(
            lambda t: self.canvas.set_zoom(int(t.rstrip("%")) / 100.0))
        self.canvas.zoom_changed.connect(self._sync_zoom_combo)
        g.body().addWidget(self.canvas, 1)
        lay.addWidget(g, 1)

        g2 = GroupPanel("检测记录")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["结果", "缺陷类型", "图像路径", "时间"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        g2.body().addWidget(self.table)
        lay.addWidget(g2, 0)
        return w

    def _fill_row(self, r, res, typ, path, time=None):
        time = time or QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        it = QTableWidgetItem(res)
        it.setForeground(Qt.red if res == "NG" else Qt.green)
        self.table.setItem(r, 0, it)
        self.table.setItem(r, 1, QTableWidgetItem(typ))
        self.table.setItem(r, 2, QTableWidgetItem(path))
        self.table.setItem(r, 3, QTableWidgetItem(time))

    def _sync_zoom_combo(self, z):
        """画布缩放变化时同步下拉框显示（取最近档位，避免信号回路）"""
        cb = getattr(self, "cb_zoom", None)
        if cb is None:
            return
        pct = [int(cb.itemText(i).rstrip("%")) for i in range(cb.count())]
        nearest = min(pct, key=lambda v: abs(v - z * 100))
        txt = "%d%%" % nearest
        if cb.currentText() != txt:
            cb.blockSignals(True)
            cb.setCurrentText(txt)
            cb.blockSignals(False)

    # ---------------- 右侧 ----------------
    def _build_right(self):
        w = QWidget()
        w.setFixedWidth(300)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        g = GroupPanel("检测结果")
        self.big_result = QLabel("--")
        self.big_result.setAlignment(Qt.AlignCenter)
        self.big_result.setStyleSheet(
            "color:%s; font-size:44px; font-weight:bold;" % C_DIM)
        self.big_conf = QLabel("置信度: --")
        self.big_conf.setAlignment(Qt.AlignCenter)
        self.big_conf.setStyleSheet("color:%s; font-size:13px;" % C_DIM)
        g.body().addWidget(self.big_result)
        g.body().addWidget(self.big_conf)
        lay.addWidget(g)

        g2 = GroupPanel("统计")
        grid = QGridLayout()
        grid.setSpacing(6)
        self.st_total = MiniStat("总数", 0)
        self.st_ok = MiniStat("OK", 0, C_GREEN)
        self.st_ng = MiniStat("NG", 0, C_RED)
        self.st_rate = MiniStat("良率", "--", C_BLUE)
        grid.addWidget(self.st_total, 0, 0)
        grid.addWidget(self.st_ok, 0, 1)
        grid.addWidget(self.st_ng, 1, 0)
        grid.addWidget(self.st_rate, 1, 1)
        holder = QWidget(); holder.setLayout(grid)
        g2.body().addWidget(holder)
        lay.addWidget(g2)

        g3 = GroupPanel("当前结果详情")
        self.detail = QTableWidget(7, 2)
        self.detail.setHorizontalHeaderLabels(["项目", "值"])
        self.detail.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.detail.verticalHeader().setVisible(False)
        self.detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        keys = ["产品", "结果", "缺陷类型", "面积 (px)", "置信度", "时间", "图像路径"]
        for r, k in enumerate(keys):
            self.detail.setItem(r, 0, QTableWidgetItem(k))
            self.detail.setItem(r, 1, QTableWidgetItem("--"))
        self.detail.setFixedHeight(220)
        g3.body().addWidget(self.detail)
        lay.addWidget(g3, 1)

        g4 = GroupPanel("良率趋势")
        self.yield_chart = YieldTrendChart(60)
        g4.body().addWidget(self.yield_chart)
        lay.addWidget(g4)

        # E：缺陷类型分布（本次运行期各缺陷类型出现次数）
        # 09-21：类别扩充到 16 类后，分布图最多显示 10 行，需要更高的可视区域；
        # 它自身有 MinimumHeight(190) 撑住高度，这里不再 stretch，
        # 把右侧栏的剩余空间留给上方"当前结果详情"表（否则详情表被压到看不见）。
        g5 = GroupPanel("缺陷类型分布")
        self.defect_chart = DefectDistChart()
        g5.body().addWidget(self.defect_chart)
        lay.addWidget(g5)
        return w

    def _log(self, level, module, msg):
        if self.log:
            getattr(self.log, {"信息": "info", "警告": "warning", "错误": "error"}[level])(module, msg)

    def _log_ng(self, defect, conf_val, suffix=""):
        """NG 检测结果记'警告'级（不是程序错误）；对同类缺陷 3 秒内重复只记一次，避免刷屏。

        - 模型检出缺陷 = 正常的质检业务结果，应显为黄色'警告'而非红色'错误'
        - 连续检测模式对同一张图反复推理时，同类型缺陷会被反复记录，这里做去重
        """
        last_type = getattr(self, "_last_ng_type", None)
        last_t = getattr(self, "_last_ng_time", 0.0)
        now = time.time()
        if defect == last_type and (now - last_t) < 3.0:
            return
        self._last_ng_type = defect
        self._last_ng_time = now
        self._log("警告", "检测",
                  "检测到缺陷（%s），置信度 %.2f%s" % (defect, conf_val, suffix))

    # ---------------- 状态指示回调（C：顶栏真实状态灯） ----------------
    def _ind(self, kind, ok, text=None):
        """向 MainWindow 回报状态。kind: 'cam'/'model'/'plc'；ok: True/False；text 可选覆盖文案"""
        if self.ind_cb:
            try:
                self.ind_cb(kind, ok, text)
            except Exception:
                pass

    def _update_cam_ind(self):
        """相机状态 = 边缘(RK3588)已连接 / 实时相机采集中 / 已打开照片"""
        edge_ok = bool(self.bridge and self.bridge.isRunning())
        if edge_ok:
            self._ind("cam", True, "RK3588 已连接")
        elif self._camera_live:
            self._ind("cam", True, "相机实时采集")
        elif self.canvas.has_image():
            self._ind("cam", True, "图像源:照片")
        else:
            self._ind("cam", False, "相机未就绪")

    def _update_model_ind(self, ok, text=None):
        self._ind("model", ok, text)

    # ---------------- 模型选择（运行时切换）----------------
    def _scan_models(self):
        """扫描 模型训练/ 下所有可用 .pt 模型，返回 [(label, rel_path), ...]。

        包含：根目录的 *.pt（标记为“生产模型”）以及 runs/<name>/weights/*.pt
        每个训练产物。标签里附上该 run 的最佳 mAP50（取自 results.csv）。
        """
        here = os.path.dirname(os.path.abspath(__file__))
        mt = os.path.join(here, "模型训练")
        found = []
        if os.path.isdir(mt):
            # 1) 根目录下的 pt（如 best.pt）
            for p in sorted(Path(mt).glob("*.pt")):
                rel = os.path.relpath(str(p), here).replace("\\", "/")
                found.append(("%s (生产模型)" % p.stem, rel))
            # 2) runs/<name>/weights/best.pt（仅 best，避免 last.pt 干扰）
            for w in sorted(Path(mt).glob("runs/*/weights/best.pt")):
                run_dir = w.parent.parent  # runs/<name>
                name = run_dir.name
                mAP = self._best_map50(run_dir)
                tag = name
                if mAP is not None:
                    tag += " (mAP50=%.3f)" % mAP
                else:
                    tag += " (训练中…)"
                if w.stem != "best":
                    tag += " [%s]" % w.stem
                rel = os.path.relpath(str(w), here).replace("\\", "/")
                found.append((tag, rel))
        if not found:
            found.append(("（未找到任何模型）", ""))
        return found

    def _best_map50(self, run_dir):
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

    def _refresh_model_list(self):
        self.cb_model.blockSignals(True)
        self.cb_model.clear()
        cur = self.cfg.get("model", "path", "模型训练/best.pt") if self.cfg else "模型训练/best.pt"
        sel_idx = 0
        for i, (label, rel) in enumerate(self._scan_models()):
            self.cb_model.addItem(label, rel)
            if rel and rel == cur:
                sel_idx = i
        self.cb_model.setCurrentIndex(sel_idx)
        self.cb_model.blockSignals(False)
        self._log("信息", "检测", "已刷新模型列表（共 %d 个）" % self.cb_model.count())

    def _on_model_selected(self, idx):
        if idx < 0:
            return
        rel = self.cb_model.currentData()
        if not rel:
            return
        # 更新配置并卸载旧引擎：下次推理时 _ensure_engine 会懒加载新模型
        if self.cfg:
            self.cfg.set("model", "path", rel)
            self.cfg.save()
        self.engine = None
        self._update_model_ind(None, "模型待加载")   # C：切模型后回待加载态
        self._log("信息", "检测", "已切换模型: %s（下次推理生效）" % rel)


    def _resolve_mode(self):
        """决策“开始检测”的运行模式（纯逻辑，无 Qt 副作用，便于测试）。
        返回 'real'（真实推理）/ 'mock'（模拟演示）/ 'blocked'（需照片，已拦截）。

        注意：本地真实推理只能针对**从文件打开的照片**。边缘推流把画面塞进画布时
        走的是 set_image_bytes()，此时 has_image() 为 True 但 image_path() 是空串；
        若据此误判成 'real'，定时器会去 load_image("") 抛异常并闪退。
        """
        has_img = self.canvas.has_image()
        has_file_img = bool(has_img and self.canvas.image_path())
        # 已打开照片时，一律走真实推理（“开始检测”= 检测这张图）
        if _HAS_INFER and has_file_img:
            return "real"
        use_real = _HAS_INFER and getattr(self, "real_toggle", None) and self.real_toggle.on
        # 真实模式但没图：拦截（避免悄无声息跑模拟造成误导）
        if use_real and not has_file_img:
            return "blocked"
        return "mock"

    def _edge_running(self):
        """边缘通道（串口桥接 / TCP 桥接）当前是否已连接。"""
        try:
            return self.bridge is not None and self.bridge.isRunning()
        except Exception:
            return False

    def _start(self):
        # 相机实时采集与定时器检测互斥：开始检测前先停相机
        if self._camera_live:
            self._stop_camera()
            if hasattr(self, "tb_live"):
                self.tb_live.setText("实时相机")
        self.running = True
        # 重置计数器（同时清空检测记录表）。
        # 09-21 修：原先只清 self.total/ok/ng 与两张图表，却不清底部「检测记录」表，
        # 于是新开一轮后「右侧统计 = 本轮」而「底表 = 累计」，两个口径长期对不上，
        # 用户看到"底表一堆 NG、右侧却显示总数 1、画面还没框"会以为检测失效。
        # 现在统一为「开始检测 = 新的一轮」，底表与统计同步归零。
        self.total, self.ok, self.ng = 0, 0, 0
        self.yield_chart.clear()
        self.defect_chart.clear()
        try:
            self.table.setRowCount(0)
        except Exception:
            pass

        # ① 边缘已连接：点“开始检测”的语义 = 开始统计/入库板端 NPU 结果，
        #    而不是拿本地 CPU 去推理一张推流内存图（那样既无意义，也会闪退）。
        if self._edge_running():
            self._edge_detect_enabled = True
            sw = getattr(self, "sw_auto_edge_detect", None)
            if sw is not None:
                sw.on = True
                try:
                    sw.update()
                except Exception:
                    pass
            if self.cfg:
                self.cfg.set("edge", "auto_detect", True)
                self.cfg.save()
            # 09-21 修：step 模式下必须在这里显式启动心跳定时器，
            # 否则板端等 cmd=next 等到天荒地老，统计恒为 0。
            self._ensure_step_timer(True)
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            if hasattr(self, "tb_play"):
                self.tb_play.setEnabled(False)
                self.tb_pause.setEnabled(True)
            self._log("信息", "检测",
                      "开始检测（RK3588 边缘模式：接收板端 NPU 结果并统计入库）")
            # 已打开照片：直接把它送板端 NPU 检测，用户立刻能看到这张图的结果
            # （否则 step 模式下板端不推帧，闸门开了也永远 0 件——修复"用不了"）
            self._send_photo_for_detect(reason="（开始检测）")
            if self.status_cb:
                self.status_cb(True)
            return

        # 同步检测参数到配置
        if self.cfg:
            self.cfg.set("model", "conf", self.ed_conf.text())
            self.cfg.set("model", "min_area", self.ed_area.text())
            self.cfg.set("model", "iou", self.ed_iou.text())
        # 根据速度选择设置定时器间隔
        speed_map = {0: 500, 1: 1000, 2: 2000}
        interval = speed_map.get(self.cb_speed.currentIndex(), 1000)

        mode = self._resolve_mode()
        # 真实模式但没图：提示并中止
        if mode == "blocked":
            self.running = False
            QMessageBox.information(
                self, "开始检测",
                "真实检测需要先打开一张照片（点击“打开照片”）。\n"
                "或关闭左侧“连续真实检测”开关，使用模拟演示数据。")
            return

        use_real = (mode == "real")
        try:
            self.timer.timeout.disconnect()
        except Exception:
            pass
        if use_real:
            # 确保开关视觉状态与逻辑一致
            if getattr(self, "real_toggle", None):
                self.real_toggle.on = True
                self.real_toggle.update()
            # 关键：在点击事件的同步上下文里预加载模型（此时 Qt 事件循环空闲）。
            # 切勿把 ultralytics/YOLO 的模型加载放到 QTimer 回调里——模型加载发生在
            # 事件循环运行中时会与 torch 的线程池冲突导致 C 层段错误（进程直接消失）。
            engine = self._ensure_engine()
            if engine is None:
                self.running = False
                self.btn_start.setEnabled(True)
                QMessageBox.warning(self, "开始检测",
                                    "真实推理引擎加载失败，无法开始检测（检查训练产物与依赖）。")
                return
            self.timer.timeout.connect(self._real_tick)
            label = "真实推理"
        else:
            self.timer.timeout.connect(self._fake_frame)
            label = "模拟演示"
        self.timer.start(interval)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        if hasattr(self, "tb_play"):
            self.tb_play.setEnabled(False)
            self.tb_pause.setEnabled(True)
        self._log("信息", "检测", "开始检测（%s；置信度阈值 %s，最小面积 %s px，间隔 %dms）"
                  % (label, self.ed_conf.text(), self.ed_area.text(), interval))
        if self.status_cb:
            self.status_cb(True)

    def _stop(self):
        self.running = False
        self.timer.stop()
        # 复原显示：清掉画面上残留的检测框 / NG 角标 / 闪烁边框，
        # 右侧结果面板回待机（统计数字与记录表保留，仅复位"当前帧"的展示）
        self.canvas.clear_defects()
        self.canvas.clear_result()
        self.big_result.setText("--")
        self.big_result.setStyleSheet(
            "color:%s; font-size:44px; font-weight:bold;" % C_DIM)
        self.big_conf.setText("置信度: --")
        if self._edge_running():
            # 边缘模式下“停止检测”只关闭统计/入库、回到仅预览，**保留连接**，
            # 免得用户以为板子掉线还要重连一次。
            self._edge_detect_enabled = False
            sw = getattr(self, "sw_auto_edge_detect", None)
            if sw is not None:
                sw.on = False
                try:
                    sw.update()
                except Exception:
                    pass
            if self.cfg:
                self.cfg.set("edge", "auto_detect", False)
                self.cfg.save()
            # 09-21 修：停止检测要一并停掉心跳，否则"暂停"了还在给板端发 next
            self._ensure_step_timer(False)
            self._log("信息", "边缘", "已暂停边缘检测（连接保留，继续仅预览）")
        else:
            self._stop_edge()  # 非边缘模式：保持旧行为，顺带释放串口
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if hasattr(self, "tb_play"):
            self.tb_play.setEnabled(True)
            self.tb_pause.setEnabled(False)
        self._log("信息", "检测", "停止检测，共检测 %d 件（OK %d / NG %d）"
                  % (self.total, self.ok, self.ng))
        if self.status_cb:
            self.status_cb(False)

    def _uniq_path(self, save_dir, prefix, ext):
        """生成唯一落盘路径：秒级时间戳 + 进程内自增序号。

        09-21 修：原用 random.randint(0, 9999)，按生日悖论约 118 个文件后就有
        50% 概率撞名；命中后是**静默覆盖**——数据库记录里的路径会指向一张被
        后来的图覆盖掉的旧文件，出现"看图对不上号"且无从追溯。
        """
        self._save_seq = getattr(self, "_save_seq", 0) + 1
        ts = time.strftime("%Y%m%d_%H%M%S")
        return "%s/%s_%s_%04d.%s" % (save_dir, prefix, ts, self._save_seq % 10000, ext)

    def _open_image(self):
        """打开照片文件并显示在预览画布中"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff);;所有文件 (*.*)")
        if not path:
            return
        if self.canvas.set_image(path):
            self._photo_path = path
            self._photo_sent = False   # 新照片重置送检标记，允许再送一次
            self._log("信息", "检测", "已加载图片: %s" % path)
            # 新照片无检测结果：清掉上一张残留的框/角标，右侧面板回待机
            self.canvas.clear_defects()
            self.canvas.clear_result()
            self.big_result.setText("--")
            self.big_result.setStyleSheet(
                "color:%s; font-size:44px; font-weight:bold;" % C_DIM)
            self.big_conf.setText("置信度: --")
            # 图像源就绪：状态点变绿
            self.dot_cam.set_text("图像源:照片")
            self.dot_cam.set_color(C_GREEN)
            self._update_cam_ind()   # C：同步顶栏状态
            # 如果正在检测，先停止
            if self.running:
                self._stop()
        else:
            QMessageBox.warning(self, "打开照片",
                                "无法加载图片文件，可能格式不支持：\n%s" % path)
            self._log("错误", "检测", "图片加载失败: %s" % path)

    def _clear_image(self):
        """清除已加载的图片，恢复模拟显示（连同残留的检测框/结果角标一起清场）"""
        had = self.canvas.has_image() or bool(self._photo_path)
        self._photo_path = ""
        self._photo_sent = False
        self.canvas.clear_image()
        # 无论之前有没有图，都清掉残留结果：边缘框/角标可能在无图状态下残留
        # （如用户截图：模拟画面上挂着 inclusion 框 + NG 角标）
        self.canvas.clear_defects()
        self.canvas.clear_result()
        self.big_result.setText("--")
        self.big_result.setStyleSheet(
            "color:%s; font-size:44px; font-weight:bold;" % C_DIM)
        self.big_conf.setText("置信度: --")
        if had:
            self._log("信息", "检测", "已清除图片，恢复模拟显示")
            # 图像源断开：状态点恢复红色
            self.dot_cam.set_text("相机未连接")
            self.dot_cam.set_color(C_RED)
            self._update_cam_ind()   # C：同步顶栏状态

    # ---------------- 实时相机（PC/工业相机） ----------------
    def _refresh_cameras(self):
        """枚举本机可用相机设备，填充『相机选择』下拉（带设备序号）。"""
        combo = self.cam_sel
        if combo is None:
            return
        combo.blockSignals(True)
        combo.clear()
        cands = []
        if _HAS_CV2:
            import cv2 as _cv
            for i in range(4):
                try:
                    cap = _cv.VideoCapture(i)
                    ok = bool(cap.isOpened())
                    cap.release()
                    if ok:
                        cands.append(i)
                except Exception:
                    pass
        if not cands:
            cands = [0, 1]   # 没有可用相机时仍给出可选序号，便于手动指定
        for i in cands:
            combo.addItem("相机 %d" % i, i)
        combo.blockSignals(False)

    def _selected_camera_device(self):
        if self.cam_sel is not None:
            d = self.cam_sel.currentData()
            if isinstance(d, int):
                return d
        return 0

    def _toggle_camera(self):
        """开始 / 停止实时相机采集。"""
        if self._camera_live:
            self._stop_camera()
            if hasattr(self, "tb_live"):
                self.tb_live.setText("实时相机")
            return
        if not _HAS_CV2:
            QMessageBox.warning(
                self, "实时相机",
                "缺少 opencv-python 依赖，无法使用实时相机。\n"
                "请安装：pip install opencv-python")
            return
        # 先停掉照片/模拟检测定时器，避免两套采集打架
        if self.running:
            self._stop()
        self._refresh_cameras()
        dev = self._selected_camera_device()
        self.cam_worker = CameraWorker(dev)
        self.cam_worker.frame_ready.connect(self._on_camera_frame)
        self.cam_worker.error.connect(self._on_camera_err)
        self.cam_worker.start()
        self._camera_live = True
        if hasattr(self, "tb_live"):
            self.tb_live.setText("停止相机")
        self.dot_cam.set_text("相机实时采集")
        self.dot_cam.set_color(C_GREEN)
        # 默认开启连续真实推理，让相机画面直接出检测框
        if _HAS_INFER and getattr(self, "real_toggle", None):
            self.real_toggle.on = True
            self.real_toggle.update()
        self._update_cam_ind()
        self._log("信息", "检测", "已开始实时相机采集（设备 %s）" % dev)

    def _stop_camera(self):
        """停止相机采集并清场。"""
        self._stop_record(silent=True)   # 相机停了先静默收尾录像
        if self.cam_worker:
            try:
                self.cam_worker.stop()
            except Exception:
                pass
            self.cam_worker = None
        self._camera_live = False
        self._cur_frame_bytes = None
        self.canvas.clear_result()   # 含检测框+NG角标，避免停相机后残留结果
        self.canvas.clear_image()
        self.dot_cam.set_text("相机未连接")
        self.dot_cam.set_color(C_RED)
        self._update_cam_ind()
        self._log("信息", "检测", "已停止实时相机采集")

    def _on_camera_frame(self, qimg, jpg):
        """每帧回调：显示画面；开启真实推理时跑 YOLO（推理忙则跳过本帧）。"""
        self.canvas.set_live_frame(qimg)
        self._cur_frame_bytes = jpg if jpg else None
        # 录制中：把当前帧写入视频文件
        if self._recording and self.video_writer is not None and self.cam_worker:
            b = self.cam_worker.latest_bgr
            if b is not None:
                try:
                    self.video_writer.write(b)
                except Exception:
                    pass
        if (getattr(self, "real_toggle", None) and self.real_toggle.on
                and _HAS_INFER and self.cam_worker):
            bgr = self.cam_worker.latest_bgr
            if bgr is None:
                return
            # 相机实时推理改为主线程同步 + 节流，避免 torch 子线程与 Qt 冲突崩溃
            now = time.time()
            if now - getattr(self, "_last_cam_infer", 0.0) < 0.5:
                return
            self._last_cam_infer = now
            engine = self._ensure_engine()
            if engine is None:
                return
            try:
                conf = float(self.ed_conf.text())
            except Exception:
                conf = 0.25
            try:
                iou = float(self.ed_iou.text())
            except Exception:
                iou = 0.45
            try:
                min_area = float(self.ed_area.text())
            except Exception:
                min_area = 0
            try:
                defects = engine.predict_cv2(bgr, conf=conf, iou=iou, min_area=min_area)
                is_ng = len(defects) > 0
                top_conf = max((d["conf"] for d in defects), default=0.0)
                self._apply_real_result(defects, is_ng, top_conf, 0.0, False)
            except Exception as e:
                self._log("错误", "检测", "相机实时推理异常: %s" % e)

    def _on_camera_err(self, msg):
        self._stop_camera()
        if hasattr(self, "tb_live"):
            self.tb_live.setText("实时相机")
        self._log("错误", "检测", "实时相机错误: %s" % msg)
        QMessageBox.warning(self, "实时相机", "相机采集出错：%s" % msg)

    # ---------------- 视频录制 / 抽帧存证 ----------------
    def _save_dir(self):
        if self.cfg:
            return self.cfg.get("storage", "save_path", "D:/Inspect/Images")
        return "D:/Inspect/Images"

    def _toggle_record(self):
        """开始 / 停止录制。

        两种可录的源：① 实时相机画面（原有）；② RK3588 边缘检测画面——
        板端回传的 JPEG 帧落 VideoWriter（此前边缘模式点录制只会弹
        "请先开始实时相机"，表现为"录制用不了"）。
        """
        if self._recording:
            self._stop_record()
            return
        if not _HAS_CV2:
            QMessageBox.warning(self, "视频录制",
                                "缺少 opencv-python 依赖，无法录制。")
            return
        if self._camera_live and self.cam_worker is not None:
            bgr = self.cam_worker.latest_bgr
            if bgr is None:
                QMessageBox.information(self, "视频录制",
                                        "尚未获取到相机画面，请稍候再试。")
                return
            h, w = bgr.shape[:2]
            save_dir = self._save_dir()
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "视频录制",
                                    "无法创建存储目录：\n%s" % e)
                return
            path = "%s/录制_%s.avi" % (save_dir, time.strftime("%Y%m%d_%H%M%S"))
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"),
                                     10.0, (w, h))
            if not writer.isOpened():
                # 部分环境没有 MJPG 解码器，回退 XVID
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"XVID"),
                                         10.0, (w, h))
            if not writer.isOpened():
                QMessageBox.warning(
                    self, "视频录制",
                    "无法创建视频文件：\n%s\n\n可能是编码库缺失或路径不可写。" % path)
                return
            self.video_writer = writer
            self._record_path = path
            self._recording = True
            if hasattr(self, "tb_rec"):
                self.tb_rec.setText("停止录制")
            self._log("信息", "录制", "开始录制: %s（%dx%d）" % (path, w, h))
            return
        if self._edge_running():
            # 边缘录制：视频文件懒创建——等第一帧回传到达时按其尺寸建 writer
            self._recording = True
            self._record_path = ""
            self.video_writer = None
            if hasattr(self, "tb_rec"):
                self.tb_rec.setText("停止录制")
            self._log("信息", "录制",
                      "开始录制 RK3588 检测画面（收到第一帧后生成视频文件）")
            return
        QMessageBox.information(
            self, "视频录制",
            "请先「连接 RK3588」或「开始实时相机采集」，再点 录制。")

    def _record_edge_frame(self, arr):
        """把板端回传的一帧 (BGR ndarray) 写入录制文件；首个到达帧决定视频尺寸。"""
        if not self._recording:
            return
        try:
            if self.video_writer is None:
                save_dir = self._save_dir()
                os.makedirs(save_dir, exist_ok=True)
                path = "%s/录制_%s.avi" % (save_dir, time.strftime("%Y%m%d_%H%M%S"))
                h, w = arr.shape[:2]
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"),
                                         10.0, (w, h))
                if not writer.isOpened():
                    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"XVID"),
                                             10.0, (w, h))
                if not writer.isOpened():
                    self._log("警告", "录制", "无法创建视频文件（编码器不可用），录制已停止")
                    self._recording = False
                    if hasattr(self, "tb_rec"):
                        self.tb_rec.setText("录制")
                    return
                self.video_writer = writer
                self._record_path = path
                self._log("信息", "录制", "录制文件已创建: %s（%dx%d）" % (path, w, h))
            self.video_writer.write(arr)
        except Exception as e:
            self._log("警告", "录制", "写帧异常: %s" % e)

    def _stop_record(self, silent=False):
        """停止录制。silent=True 用于停相机时静默收尾，不弹提示。"""
        if self.video_writer is not None:
            try:
                self.video_writer.release()
            except Exception:
                pass
            self.video_writer = None
        was = self._recording
        self._recording = False
        if hasattr(self, "tb_rec"):
            self.tb_rec.setText("录制")
        if was:
            path = self._record_path
            self._record_path = ""
            if not path and self.video_writer is None:
                self._log("信息", "录制", "录制结束：期间未收到画面帧，未生成视频文件")
            else:
                self._log("信息", "录制", "录制结束，已保存: %s" % path)
                if not silent and path:
                    QMessageBox.information(self, "视频录制",
                                            "录像已保存：\n%s" % path)

    def _save_evidence(self):
        """一键存证：把当前相机帧（无则截图画布）直接存入存储目录，不弹文件对话框。"""
        save_dir = self._save_dir()
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "存证", "无法创建存储目录：\n%s" % e)
            return
        data = getattr(self, "_cur_frame_bytes", None)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        if data:
            path = "%s/存证_%s.jpg" % (save_dir, stamp)
            try:
                with open(path, "wb") as fh:
                    fh.write(data)
            except Exception as e:
                QMessageBox.warning(self, "存证", "保存失败：\n%s" % e)
                return
        else:
            # 无相机帧时退化为截图当前画布
            path = "%s/存证_%s.png" % (save_dir, stamp)
            if not self.canvas.grab().save(path):
                QMessageBox.warning(self, "存证", "保存失败，请检查路径权限。")
                return
        self._log("信息", "存储", "已存证: %s" % path)
        QMessageBox.information(self, "存证", "已保存到：\n%s" % path)

    def _save_image(self):
        """保存当前画布为图片文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图像", "",
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg)")
        if not path:
            return
        # 自动补全扩展名
        if not path.lower().endswith((".png", ".jpg", ".jpeg")):
            path += ".png"
        pix = self.canvas.grab()
        if pix.save(path):
            self._log("信息", "检测", "图像已保存: %s" % path)
            QMessageBox.information(self, "保存图像", "图像已保存：\n%s" % path)
        else:
            self._log("错误", "检测", "图像保存失败: %s" % path)
            QMessageBox.warning(self, "保存图像", "图像保存失败，请检查路径权限。")

    def _fake_frame(self):
        self.total += 1
        is_ng = random.random() < 0.02
        conf = random.randint(90, 99) if is_ng else random.randint(95, 100)
        product = self.cfg.get("model", "name", "Product_A_v1") if self.cfg else "Product_A_v1"
        save_dir = self.cfg.get("storage", "save_path", "D:/Inspect/Images") if self.cfg else "D:/Inspect/Images"
        path = self._uniq_path(save_dir, "sample", "png")
        # 模拟模式从「全部已登记类别」里随机取（含 09-21 扩展的工业常见类/表面处理类），
        # 让演示时的缺陷分布图能覆盖全部类别，而不是只有 3 种。
        defect = random.choice(_DEMO_DEFECTS) if is_ng else "--"
        area = random.randint(120, 180) if is_ng else 0

        if is_ng:
            self.ng += 1
            self.canvas.set_result("NG", conf)
            self.canvas.trigger_flash()
            self.big_result.setText("NG")
            self.big_result.setStyleSheet(
                "color:%s; font-size:44px; font-weight:bold;" % C_RED)
            self._log_ng(defect, conf / 100.0)
            self.defect_chart.push(defect)   # E：缺陷分布累加
            # NG 声音报警
            if self._alarm_enabled:
                play_beep()
        else:
            self.ok += 1
            self.canvas.set_result("OK", conf)
            self.big_result.setText("OK")
            self.big_result.setStyleSheet(
                "color:%s; font-size:44px; font-weight:bold;" % C_GREEN)
        self.big_conf.setText("置信度: %d%%" % conf)

        rate = self.ok * 100.0 / self.total
        self.st_total.value.setText(str(self.total))
        self.st_ok.value.setText(str(self.ok))
        self.st_ng.value.setText(str(self.ng))
        self.st_rate.value.setText("%.1f%%" % rate)
        self.yield_chart.push(rate)

        # 09-21 修：mock 演示模式不写真实数据库——否则模拟数据会污染统计/历史，
        # 用户没法区分"演示造的假记录"和"真实检测记录"。
        t = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")

        # 详情面板
        vals = [product, "NG" if is_ng else "OK", defect,
                str(area) if is_ng else "--", "%.2f" % (conf / 100.0), t, path]
        for r, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if r == 1:
                it.setForeground(Qt.red if is_ng else Qt.green)
            self.detail.setItem(r, 1, it)

        # 记录表
        self.table.insertRow(0)
        self._fill_row(0, "NG" if is_ng else "OK", defect, path, t)
        if self.table.rowCount() > self.MAX_TABLE_ROWS:
            self.table.removeRow(self.table.rowCount() - 1)

    # ---------------- 真实推理（P4）----------------
    def _ensure_engine(self):
        """懒加载推理引擎；首次会加载模型（约数秒）。返回引擎或 None。"""
        if not _HAS_INFER:
            return None
        if self.engine is None:
            weights = self.cfg.get("model", "path", "模型训练/best.pt") if self.cfg else "模型训练/best.pt"
            try:
                conf = float(self.ed_conf.text())
            except Exception:
                conf = 0.25
            try:
                iou = float(self.ed_iou.text())
            except Exception:
                iou = 0.45
            self.engine = DefectDetector(weights, conf=conf, imgsz=640, device="cpu", iou=iou)
            if not self.engine.ready:
                self._log("错误", "检测", "模型加载失败: %s" % (self.engine.load_error or "未知"))
                self._update_model_ind(False, "模型加载失败")
                return None
            self._log("信息", "检测", "真实推理引擎已加载: %s" % weights)
            self._update_model_ind(True, "模型已加载")   # C：顶栏点亮
        return self.engine

    def _run_real_detect(self):
        """对当前打开的照片做一次真实推理（一次性，主线程同步执行）。"""
        if not self.canvas.has_image():
            QMessageBox.information(self, "真实模型检测",
                                    "请先点击“打开照片”加载一张图片，再做真实推理。")
            return
        # 边缘推流的内存图没有文件路径：必须显式拦住，否则 load_image("") 会让
        # np.fromfile 抛 FileNotFoundError，而该行不在 try 内 -> PyQt5 直接杀进程。
        path = self.canvas.image_path()
        if not path or not os.path.exists(path):
            QMessageBox.information(
                self, "真实模型检测",
                "当前画面来自 RK3588 实时推流，没有本地文件路径。\n"
                "请先用“打开照片”加载一张本地图片再做真实模型检测。")
            return
        engine = self._ensure_engine()
        if engine is None:
            QMessageBox.warning(self, "真实模型检测",
                                "推理引擎不可用，请检查训练产物 模型训练/best.pt 与依赖。")
            return
        img = load_image(path)
        if img is None:
            QMessageBox.warning(self, "真实模型检测", "图片读取失败：%s" % path)
            return
        self.btn_real.setEnabled(False)
        self.btn_real.setText("推理中…")
        try:
            conf = float(self.ed_conf.text())
        except Exception:
            conf = 0.25
        try:
            iou = float(self.ed_iou.text())
        except Exception:
            iou = 0.45
        try:
            min_area = float(self.ed_area.text())
        except Exception:
            min_area = 0
        try:
            defects = engine.predict_cv2(img, conf=conf, iou=iou, min_area=min_area)
            is_ng = len(defects) > 0
            top_conf = max((d["conf"] for d in defects), default=0.0)
            self._apply_real_result(defects, is_ng, top_conf, 0.0, False)
        except Exception as e:
            QMessageBox.warning(self, "真实模型检测", "推理出错：%s" % e)
        finally:
            self.btn_real.setEnabled(True)
            self.btn_real.setText("真实模型检测")

    def _real_tick(self):
        """连续真实检测：对当前图片定时推理（主线程同步，避免 torch 在子线程与 Qt 冲突崩溃）。

        ⚠️ 整段必须包在 try 里：本函数由 QTimer 槽触发，而 PyQt5 对槽函数内未捕获的
        异常会直接调用 qFatal() 终止进程——现象是界面毫无提示地闪退、日志无 traceback。
        """
        try:
            if not self.canvas.has_image():
                return
            # 只有“从文件打开的照片”才有路径。边缘推流的内存图 image_path() 返回空串，
            # 直接传给 load_image 会让 np.fromfile("") 抛 FileNotFoundError（曾整段未保护
            # 导致点“开始检测”立即闪退）。
            path = self.canvas.image_path()
            if not path or not os.path.exists(path):
                return
            engine = self._ensure_engine()
            if engine is None:
                return
            img = load_image(path)
            if img is None:
                return
            try:
                conf = float(self.ed_conf.text())
            except Exception:
                conf = 0.25
            try:
                iou = float(self.ed_iou.text())
            except Exception:
                iou = 0.45
            try:
                min_area = float(self.ed_area.text())
            except Exception:
                min_area = 0
            defects = engine.predict_cv2(img, conf=conf, iou=iou, min_area=min_area)
            is_ng = len(defects) > 0
            top_conf = max((d["conf"] for d in defects), default=0.0)
            self._apply_real_result(defects, is_ng, top_conf, 0.0, True)
        except Exception as e:
            self._log("错误", "检测", "真实推理异常: %s" % e)

    # ---------------- 边缘模式：连接 RK3588（串口 / 网络 TCP） ----------------
    def _toggle_edge(self):
        """连接 / 断开 RK3588（串口或网络 TCP，取决于下拉选择）。"""
        if self.bridge and self.bridge.isRunning():
            self._stop_edge()
            return
        self._auto_left = 0          # 手动操作即取消自动重试
        self._connect_edge()

    def _connect_edge(self, silent=False):
        """实际发起连接。silent=True 时不弹窗，仅记日志（用于开机自动连接）。"""
        if not (hasattr(self, "cb_edge_mode") and hasattr(self, "ed_edge_host")):
            return

        mode = "tcp" if self.cb_edge_mode.currentIndex() == 1 else "serial"
        addr = self.ed_edge_host.text().strip()
        port_txt = self.ed_edge_port.text().strip()
        try:
            port = int(port_txt)
        except Exception:
            port = 9000 if mode == "tcp" else 1500000

        # 持久化当前选择，便于下次启动沿用
        if self.cfg:
            self.cfg.set("edge", "mode", mode)
            if mode == "tcp":
                self.cfg.set("edge", "host", addr)
                self.cfg.set("edge", "port", port_txt)
            else:
                self.cfg.set("serial", "port", addr)
                self.cfg.set("serial", "baud", port_txt)
            self.cfg.save()

        self.dot_edge.set_text("连接中 %s ..." % addr)
        self.dot_edge.set_color(C_BLUE)

        if mode == "tcp":
            if not _HAS_TCP:
                if not silent:
                    QMessageBox.warning(self, "边缘模式", "TCP 桥接模块未加载（缺少依赖）。")
                self._log("错误", "边缘", "TCP 桥接模块未加载（缺少依赖）")
                self.dot_edge.set_text("RK3588 未连接")
                self.dot_edge.set_color(C_RED)
                return
            self.bridge = BoardTcpBridge(addr, port)
        else:
            if not _HAS_BRIDGE:
                if not silent:
                    QMessageBox.warning(self, "边缘模式", "串口桥接模块未加载（缺少 pyserial）。")
                self._log("错误", "边缘", "串口桥接模块未加载（缺少 pyserial）")
                self.dot_edge.set_text("RK3588 未连接")
                self.dot_edge.set_color(C_RED)
                return
            self.bridge = BoardSerialBridge(addr, port)

        self.bridge.connected.connect(self._on_edge_connected)
        self.bridge.result_received.connect(self._on_edge_result)
        self.bridge.error.connect(lambda m: self._log("错误", "边缘", m))
        self.bridge.start()

    # ---------------- 开机自动连接 RK3588 ----------------
    def _on_auto_edge_toggled(self, on):
        if self.cfg:
            self.cfg.set("edge", "auto_connect", bool(on))
            self.cfg.save()
        self._log("信息", "边缘", "开机自动连接已%s" % ("开启" if on else "关闭"))

    # ---------------- 连板后自动检测开关 ----------------
    def _on_auto_detect_toggled(self, on):
        self._edge_detect_enabled = bool(on)
        if self.cfg:
            self.cfg.set("edge", "auto_detect", bool(on))
            self.cfg.save()
        # 连接中/已连接时实时生效
        state = "运行" if on else "暂停"
        self._log("信息", "边缘", "连板自动检测已%s（当前状态：%s）" % ("开启" if on else "关闭", state))
        self._ensure_step_timer(bool(on))

    def _ensure_step_timer(self, on):
        """step 模式下板端不主动推帧，靠上位机按节拍发 cmd=next 驱动。

        定时器必须在「开始检测 / 停止检测 / 自动检测开关」三处都同步启停——
        09-21 修：原先只在开关回调里启停，而 _start()/_stop() 是直接改
        _edge_detect_enabled 属性（自定义开关赋值不触发 Qt 信号），
        导致点「开始检测」后定时器从未启动 → 板端收不到 cmd=next → 统计恒为 0。
        注意：stream 模式下这个定时器多余但无害（板端自循环，多发 next 无副作用）。
        """
        if on:
            if getattr(self, "_edge_step_timer", None):
                return  # 已在跑，不重复建
            if not self._edge_running():
                return  # 没连板，等连上再建（连板回调会再调一次）
            speed_map = {0: 500, 1: 1000, 2: 2000}
            interval = speed_map.get(self.cb_speed.currentIndex(), 1000)
            t = QTimer(self)
            t.setInterval(interval)
            t.timeout.connect(self._edge_step_tick)
            self._edge_step_timer = t
            t.start()
        else:
            t = getattr(self, "_edge_step_timer", None)
            if t is not None:
                t.stop()
                self._edge_step_timer = None

    def _edge_step_tick(self):
        """定时器心跳：边缘模式 + step 模式 + auto_detect 开 → 自动发 cmd=next
        收到一帧结果后会通过 _on_edge_result 入库；空回（无图时）不影响。
        """
        br = getattr(self, "bridge", None)
        if br is None or not getattr(br, "isRunning", lambda: False)():
            return
        # 仅当已经 "开始检测"（_edge_detect_enabled）时推帧
        if not getattr(self, "_edge_detect_enabled", False):
            return
        # 已打开的照片只需送检一次（不抢占 cmd=next 节拍）；
        # 送过之后把节拍让给样本序列。09-21 修：原先每 tick 都重发同一张照片，
        # cmd=next 永远发不出去。
        if not getattr(self, "_photo_sent", False):
            try:
                if self._send_photo_for_detect(reason="（自动节拍）"):
                    return
            except Exception:
                pass
        # 否则请求板端 sample 下一张
        if hasattr(br, "send_cmd"):
            br.send_cmd("next")

    # ---------------- 一张一张检测（step 模式） ----------------
    def _send_photo_for_detect(self, reason=""):
        """把「打开照片」加载的照片发给板端 NPU 检测。

        返回 True 表示已发出（照片存在 + 边缘已连接 + 发送成功）。
        这是边缘模式下「开始检测 / 检测下一张」对已打开照片的正确语义：
        之前这两个按钮在边缘模式下只会开统计闸门干等板端推帧（step 模式下
        板端不主动推），导致打开照片后点开始检测永远是 0 件。
        """
        p = getattr(self, "_photo_path", "")
        if not p:
            return False
        br = getattr(self, "bridge", None)
        if br is None or not br.isRunning() or not hasattr(br, "send_detect_image"):
            return False
        try:
            with open(p, "rb") as f:
                data = f.read()
        except Exception as e:
            self._log("错误", "边缘", "读取照片失败: %s" % e)
            return False
        ok = br.send_detect_image(data, os.path.basename(p))
        if ok:
            self._photo_sent = True   # 送检成功标记，避免自动节拍无限重发同一张
            self._log("信息", "边缘", "已送检照片: %s %s" % (os.path.basename(p), reason))
        else:
            self._log("错误", "边缘", "照片送检失败（发送异常）")
        return ok

    def _next_one(self):
        """检测一张：若用户已打开照片 → 送板端 NPU 检测该照片；
        否则请求板端检测样本目录的下一张（cmd=next）。"""
        br = getattr(self, "bridge", None)
        if br is None or not br.isRunning():
            QMessageBox.information(self, "检测下一张", "尚未连接 RK3588。")
            return
        if self._send_photo_for_detect(reason="（检测下一张）"):
            return
        if not hasattr(br, "send_cmd"):
            self._log("警告", "边缘", "当前桥接不支持逐张指令（需 TCP 模式）。")
            return
        ok = br.send_cmd("next")
        if ok:
            self._log("信息", "边缘", "已请求检测下一张")
        else:
            self._log("错误", "边缘", "发送下一张指令失败")

    def _auto_connect(self):
        """启动后自动连接边缘设备（仅网络 TCP 模式，串口保持手动避免误占 COM）。"""
        try:
            if self.bridge and self.bridge.isRunning():
                return
            if not (hasattr(self, "cb_edge_mode") and hasattr(self, "ed_edge_host")):
                return
            if not self.cfg or not self.cfg.get("edge", "auto_connect", False):
                return
            if self.cb_edge_mode.currentIndex() != 1:      # 仅 TCP
                return
            addr = self.ed_edge_host.text().strip()
            if not addr:
                return
            self._auto_left = 3                            # 失败后再重试 3 次
            self._log("信息", "边缘", "开机自动连接 %s ..." % addr)
            self._connect_edge(silent=True)
        except Exception as e:
            self._log("错误", "边缘", "自动连接异常: %s" % e)

    def _auto_retry(self):
        """自动连接失败后的退避重试（间隔 6 秒，最多 3 次）。"""
        if self.bridge and self.bridge.isRunning():
            return
        if getattr(self, "_auto_left", 0) <= 0:
            return
        self._auto_left -= 1
        self._log("信息", "边缘", "自动连接重试（剩余 %d 次）..." % self._auto_left)
        self._connect_edge(silent=True)

    def _stop_edge(self):
        # 09-21 修：断开前先停心跳，避免定时器在 bridge=None 后还在 tick
        self._ensure_step_timer(False)
        if self.bridge:
            try:
                self.bridge.stop()
            except Exception:
                pass
            self.bridge = None
        if hasattr(self, "dot_edge"):
            self.dot_edge.set_text("RK3588 未连接")
            self.dot_edge.set_color(C_RED)
        if hasattr(self, "btn_edge"):
            self.btn_edge.setText("连接 RK3588")
        if hasattr(self, "btn_next"):
            self.btn_next.setEnabled(False)
        self._update_cam_ind()   # C：断开后相机状态回退

    def _on_edge_connected(self, ok, msg):
        if hasattr(self, "dot_edge"):
            if ok:
                self.dot_edge.set_text("RK3588 已连接")
                self.dot_edge.set_color(C_GREEN)
                self.btn_edge.setText("断开 RK3588")
                if hasattr(self, "btn_next"):
                    self.btn_next.setEnabled(True)
            else:
                self.dot_edge.set_text("连接失败")
                self.dot_edge.set_color(C_RED)
                self.btn_edge.setText("连接 RK3588")
        self._update_cam_ind()   # C：边缘连接影响相机状态灯
        if self.log:
            self.log.info("边缘", msg)
        else:
            self._log("信息", "边缘", msg)

        # 开机自动连接：成功即停止重试；失败则退避重试（6s × 最多3次）
        if ok:
            self._auto_left = 0
            # 连板成功后根据“自动检测”开关决定是否开始检测，默认只预览
            if hasattr(self, "sw_auto_edge_detect"):
                self._edge_detect_enabled = bool(self.sw_auto_edge_detect.on)
            else:
                self._edge_detect_enabled = bool(self.cfg.get("edge", "auto_detect", False)) if self.cfg else False
            mode_text = "检测+统计已启动" if self._edge_detect_enabled else "仅预览（检测已暂停）"
            self._log("信息", "边缘", "RK3588 已连接：%s" % mode_text)
            # 09-21 修：连板后若自动检测开着（上次退出前存的配置），
            # 要立刻起心跳，否则 step 模式下画面停在补推的那一帧。
            self._ensure_step_timer(bool(self._edge_detect_enabled))
        elif getattr(self, "_auto_left", 0) > 0:
            QTimer.singleShot(6000, self._auto_retry)

    def _on_edge_result(self, obj):
        """解析板端 JSON 检测结果，转换为画布格式并复用真实结果渲染流程。"""
        try:
            # 板端随结果下发 base64 JPEG 帧（增强版 board_server），先渲染图像
            img_b64 = obj.get("img_b64")
            if img_b64:
                try:
                    raw = base64.b64decode(img_b64)
                    # 送检照片的回传：同一张照片，保持用户当前缩放，别重置
                    keep_zoom = (obj.get("mode") == "img"
                                 and bool(getattr(self, "_photo_path", "")))
                    z = self.canvas.zoom if keep_zoom else None
                    self.canvas.set_image_bytes(raw)
                    if z is not None and abs(z - 1.0) > 1e-6:
                        self.canvas.set_zoom(z)
                except Exception as e:
                    self._log("警告", "边缘", "图像帧解码失败: %s" % e)
                # 边缘流录制：无相机时把板端回传帧写入视频（存证）
                if (self._recording and not self._camera_live
                        and _HAS_CV2 and np is not None):
                    try:
                        arr = cv2.imdecode(np.frombuffer(raw, np.uint8),
                                           cv2.IMREAD_COLOR)
                        if arr is not None:
                            self._record_edge_frame(arr)
                    except Exception:
                        pass

            # 连板自动检测关闭时：只显示实时画面，不画框、不统计、不入库
            if not self._edge_detect_enabled:
                return

            w = int(obj.get("w", 0))
            h = int(obj.get("h", 0))
            defects = []
            for d in obj.get("defects", []):
                x1, y1, x2, y2 = d["x1"], d["y1"], d["x2"], d["y2"]
                xyxy = [x1 / w, y1 / h, x2 / w, y2 / h] if (w and h) else [0, 0, 0, 0]
                # 板端下发英文类名（NAMES 里的项）。
                # 09-21 修：原先把 "color" 硬编码成 C_RED，所有类别框同色，丢掉分类配色。
                # 注意 "name" 必须保留**英文原名**——它同时是入库/统计/历史筛选的口径，
                # 改成中文会让 DB 历史数据格式前后不一致（见 _func_test T16/T17 契约断言）；
                # 中文名另存 "name_zh" 供界面显示，画布优先用它。
                en = d.get("cls", "defect")
                defects.append({
                    "xyxy": xyxy,
                    "xyxy_px": [x1, y1, x2, y2],
                    "name": en,
                    "name_en": en,
                    "name_zh": _NAME_ZH.get(en, en),
                    "conf": float(d.get("conf", 0)),
                    "color": _CLASS_COLORS.get(en, C_RED),
                })
            is_ng = not bool(obj.get("ok", True))
            infer_ms = float(obj.get("infer_ms", 0))
            top_conf = max((d["conf"] for d in defects), default=0.0)
            # 落盘/入库节流：画面与统计仍逐帧更新，只有重 IO（写文件/插库）被限流。
            now = time.time()
            # 存图：仅 NG 且距上次 ≥2s
            self._save_img_gate = bool(is_ng) and (now - self._last_img_ts) >= self._edge_img_interval
            if self._save_img_gate:
                self._last_img_ts = now
            # 入库：NG 0.5s / OK 1s
            iv = self._edge_persist_interval * (0.5 if is_ng else 1.0)
            if (now - self._last_db_ts) >= iv:
                self._persist_gate = True
                self._last_db_ts = now
            else:
                self._persist_gate = False
            # 复用真实结果渲染（含 ROI 过滤、统计、数据库、NG 闪烁）
            self._apply_real_result(defects, is_ng, top_conf, infer_ms / 1000.0, False)
        except Exception as e:
            self._log("错误", "边缘", "结果解析失败: %s | %s" % (e, obj))
        finally:
            # 释放背压槽位，允许 bridge 继续投递下一帧（丢帧保实时，避免事件队列无限积压）
            try:
                br = getattr(self, "bridge", None)
                if br is not None and hasattr(br, "ack"):
                    br.ack()
            except Exception:
                pass

    @staticmethod
    def _defect_in_roi(d, rois):
        """框中心是否落在任一 ROI 内（rois: 归一化 (x,y,w,h) 列表）。"""
        if not rois:
            return True
        x1, y1, x2, y2 = d["xyxy"]
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        for (rx, ry, rw, rh) in rois:
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                return True
        return False

    def _apply_real_result(self, defects, is_ng, top_conf, elapsed, stream):
        # A3: ROI 边界过滤（框中心不在任一 ROI 内则丢弃）
        rois = getattr(self.canvas, "rois", []) or []
        if rois:
            defects = [d for d in defects if self._defect_in_roi(d, rois)]
        # 过滤后重算 NG 判定与最高置信度
        is_ng = len(defects) > 0
        top_conf = max((d["conf"] for d in defects), default=0.0)
        # 画真实框（多类别颜色 + 标签）
        self.canvas.set_defects(defects)
        self.canvas.set_result("NG" if is_ng else "OK", int(top_conf * 100) if defects else 0)
        # 主缺陷类型（置信度最高）；对 top1/top2 接近的易混对（如 scratches↔inclusion）
        # 做双候选显示，避免武断报单一类别（见 MEMORY 排坑：跨类混淆真分差无法靠阈值治）
        # 09-21：拆成两个口径 —— main_type 走英文（入库/统计/历史筛选的契约），
        #         main_type_zh 走中文（详情面板与记录表显示）。本地推理的 defects
        #         本身带中文 name，此时两者取值一致，不冲突。
        if defects:
            top = max(defects, key=lambda d: d["conf"])
            main_type = top["name"]
            main_type_zh = top.get("name_zh") or _NAME_ZH.get(top["name"], top["name"])
            main_area = int((top["xyxy_px"][2] - top["xyxy_px"][0]) *
                            (top["xyxy_px"][3] - top["xyxy_px"][1]))
            # top-2 双候选：按「不同类别」取第二高置信框，分差 < 0.15 时并列显示
            second = None
            for d in sorted(defects, key=lambda x: -x["conf"]):
                if d is not top and d["name"] != top["name"]:
                    second = d
                    break
            if second is not None and (top["conf"] - second["conf"]) < 0.15:
                main_type = "%s / %s" % (top["name"], second["name"])
                s2 = second.get("name_zh") or _NAME_ZH.get(second["name"], second["name"])
                main_type_zh = "%s / %s" % (main_type_zh, s2)
        else:
            main_type = "--"
            main_type_zh = "--"
            main_area = 0

        product = self.cfg.get("model", "name", "Product_A_v1") if self.cfg else "Product_A_v1"
        save_dir = self.cfg.get("storage", "save_path", "D:/Inspect/Images") if self.cfg else "D:/Inspect/Images"
        # 图像落盘：实时相机帧仅 NG 时落盘（避免每秒数十张刷爆磁盘）；
        # 边缘部署帧沿用原逻辑落盘；普通照片检测只记占位路径不写文件。
        cam_bytes = getattr(self, "_cur_frame_bytes", None)
        edge_bytes = getattr(self.canvas, "_last_bytes", None)
        # 落盘/入库节流仅对边缘模式生效；照片、实时相机模式行为不变
        gate = True
        if self.bridge and self.bridge.isRunning():
            gate = self._persist_gate
        if cam_bytes:
            if is_ng:
                import os as _os
                path = self._uniq_path(save_dir, "cam", "jpg")
                try:
                    _os.makedirs(save_dir, exist_ok=True)
                    with open(path, "wb") as fh:
                        fh.write(cam_bytes)
                except Exception as e:
                    self._log("警告", "存储", "相机图像落盘失败: %s" % e)
                    path = ""
            else:
                path = ""
            self._cur_frame_bytes = None
        elif edge_bytes:
            # 边缘帧：仅 NG 存图，且受 2s 节流门控（持续 NG 不会每帧刷盘）
            if self._save_img_gate:
                import os as _os
                path = self._uniq_path(save_dir, "sample", "jpg")
                try:
                    _os.makedirs(save_dir, exist_ok=True)
                    with open(path, "wb") as fh:
                        fh.write(edge_bytes)
                except Exception as e:
                    self._log("警告", "存储", "图像落盘失败: %s" % e)
                    path = ""
            else:
                path = ""
        else:
            path = self._uniq_path(save_dir, "sample", "png")

        # 磁盘守护：剩余空间低于 storage.disk_warn(%) 时自动清理最老的连拍帧
        # （内部 60s 节流；人工存证/录制文件受保护，不会被删）
        if path:
            try:
                thr = 10.0
                if self.cfg:
                    thr = float(self.cfg.get("storage", "disk_warn", 10) or 10)
                disk_guard(save_dir, min_free_pct=thr, log=self.log)
            except Exception:
                pass

        if is_ng:
            self.canvas.trigger_flash()
            self.big_result.setText("NG")
            self.big_result.setStyleSheet("color:%s; font-size:44px; font-weight:bold;" % C_RED)
            self._log_ng(main_type, top_conf, "，耗时 %.0fms" % (elapsed * 1000))
            for d in defects:                     # E：缺陷分布累加（多类别分别计）
                self.defect_chart.push(d.get("name", "defect"))
            if self._alarm_enabled:
                play_beep()
        else:
            self.big_result.setText("OK")
            self.big_result.setStyleSheet("color:%s; font-size:44px; font-weight:bold;" % C_GREEN)
        self.big_conf.setText("置信度: %.0f%%  耗时 %.0fms" % (top_conf * 100, elapsed * 1000))

        # 统计（一次性与连续模式都累加）
        self.total += 1
        if is_ng:
            self.ng += 1
        else:
            self.ok += 1
        rate = self.ok * 100.0 / self.total
        self.st_total.value.setText(str(self.total))
        self.st_ok.value.setText(str(self.ok))
        self.st_ng.value.setText(str(self.ng))
        self.st_rate.value.setText("%.1f%%" % rate)
        self.yield_chart.push(rate)

        # 写数据库（实时相机模式下仅记录 NG；边缘模式下 OK 记录受节流门控）
        t = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        if self.db and gate and (not self._camera_live or is_ng):
            try:
                t = self.db.insert(product, "NG" if is_ng else "OK", main_type,
                                   main_area, round(top_conf, 2), path)
            except Exception:
                pass

        # 详情面板（缺陷类型显示中文；入库仍用英文 main_type）
        vals = [product, "NG" if is_ng else "OK", main_type_zh,
                str(main_area) if is_ng else "--", "%.2f" % top_conf, t, path]
        for r, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if r == 1:
                it.setForeground(Qt.red if is_ng else Qt.green)
            self.detail.setItem(r, 1, it)

        # 记录表（同样显示中文；入库口径保持英文不变）
        self.table.insertRow(0)
        self._fill_row(0, "NG" if is_ng else "OK", main_type_zh, path, t)
        if self.table.rowCount() > self.MAX_TABLE_ROWS:
            self.table.removeRow(self.table.rowCount() - 1)
