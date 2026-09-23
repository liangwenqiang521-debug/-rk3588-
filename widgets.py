# -*- coding: utf-8 -*-
"""通用自定义组件：状态点、分组面板、统计卡、预览画布等"""
from PyQt5.QtCore import Qt, QRectF, QPoint, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import (QColor, QPainter, QPen, QBrush, QFont, QLinearGradient,
                         QRadialGradient, QPixmap)
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QSizePolicy, QGridLayout,
)
from collections import deque


# ---------------- 颜色常量（现代深蓝工业风） ----------------
C_BG = "#0e1116"        # 主背景（更深、微蓝）
C_PANEL = "#1a1f28"     # 面板
C_PANEL2 = "#212732"    # 面板内控件底
C_BORDER = "#2a3140"    # 边框
C_TEXT = "#e2e8f0"      # 主文字（更亮）
C_DIM = "#8b95a5"       # 次要文字
C_BLUE = "#3b9eff"      # 主色（更亮）
C_GREEN = "#2ea043"
C_RED = "#f85149"
C_YELLOW = "#d29922"


class DotIndicator(QWidget):
    """发光状态点 + 文字，如 '● 相机已连接'（自绘光晕效果）"""
    def __init__(self, text, color=C_GREEN, parent=None):
        super().__init__(parent)
        self._text = text
        self._color = QColor(color)
        self.setMinimumHeight(20)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(30 + fm.width(self._text), 20)

    def set_text(self, text):
        self._text = text
        self.update()

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = 8.0, self.height() / 2.0
        r = 4.5
        # 外圈光晕（径向渐变）
        glow = QRadialGradient(cx, cy, r * 3.2)
        c = self._color
        glow.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 120))
        glow.setColorAt(0.5, QColor(c.red(), c.green(), c.blue(), 40))
        glow.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QRectF(cx - r * 3.2, cy - r * 3.2, r * 6.4, r * 6.4))
        # 实心核心点
        p.setBrush(c)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        # 高光小点（立体感）
        p.setBrush(QColor(255, 255, 255, 170))
        p.drawEllipse(QRectF(cx - r * 0.45, cy - r * 0.65, r * 0.5, r * 0.5))
        # 文字
        p.setPen(QColor(C_TEXT))
        p.drawText(QRectF(20, 0, self.width() - 20, self.height()),
                   Qt.AlignVCenter, self._text)


class GroupPanel(QFrame):
    """带标题的分组面板"""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("groupPanel")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(10, 8, 10, 10)
        self._lay.setSpacing(6)
        if title:
            t = QLabel(title)
            t.setObjectName("groupTitle")
            self._lay.addWidget(t)

    def body(self):
        return self._lay


class FormRow(QWidget):
    """标签 + 控件的表单行"""
    def __init__(self, label, widget, label_w=90, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lab = QLabel(label)
        lab.setFixedWidth(label_w)
        lab.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        lay.addWidget(lab)
        lay.addWidget(widget, 1)


class StatCard(QFrame):
    """大数字统计卡：顶部彩色强调条 + 悬停高亮"""
    def __init__(self, title, value, color=C_TEXT, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self._accent = color
        self.setStyleSheet(
            "#statCard { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 #1c222c, stop:1 #171c24);"
            " border: 1px solid %s; border-top: 2px solid %s;"
            " border-radius: 8px; }"
            " #statCard:hover { border: 1px solid #3d4655; border-top: 2px solid %s; }"
            % (C_BORDER, color, color))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(2)
        self.title = QLabel(title)
        self.title.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        self.value = QLabel(str(value))
        self.value.setStyleSheet(
            "color:%s; font-size:28px; font-weight:bold;" % color)
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set_value(self, v):
        self.value.setText(str(v))


class MiniStat(QFrame):
    """实时检测页右侧的窄统计格：顶部强调条"""
    def __init__(self, title, value, color=C_TEXT, parent=None):
        super().__init__(parent)
        self.setObjectName("miniStat")
        self.setStyleSheet(
            "#miniStat { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 #1c222c, stop:1 #171c24);"
            " border: 1px solid %s; border-top: 2px solid %s;"
            " border-radius: 8px; }"
            % (C_BORDER, color))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(4)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:%s; font-size:12px;" % C_DIM)
        self.value = QLabel(str(value))
        self.value.setAlignment(Qt.AlignCenter)
        self.value.setStyleSheet(
            "color:%s; font-size:20px; font-weight:bold;" % color)
        lay.addWidget(t)
        lay.addWidget(self.value)

    def set_value(self, v):
        self.value.setText(str(v))


class LabeledProgress(QWidget):
    """带标签与百分比的进度条（系统状态用）"""
    def __init__(self, label, percent, color=C_GREEN, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lab = QLabel(label)
        lab.setFixedWidth(56)
        lab.setStyleSheet("color:%s; font-size:11px;" % C_DIM)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(percent)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            "QProgressBar{background:%s; border:none; border-radius:4px;}"
            "QProgressBar::chunk{background:%s; border-radius:4px;}"
            % (C_PANEL2, color))
        self.val = QLabel("%d%%" % percent)
        self.val.setFixedWidth(36)
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val.setStyleSheet("color:%s; font-size:11px;" % C_TEXT)
        lay.addWidget(lab)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.val)

    def set_value(self, v):
        self.bar.setValue(int(v))
        self.val.setText("%d%%" % int(v))


class YieldTrendChart(QWidget):
    """良率趋势迷你曲线图：最近 N 次检测的良率变化"""
    def __init__(self, maxlen=60, parent=None):
        super().__init__(parent)
        self.data = deque(maxlen=maxlen)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def push(self, rate):
        self.data.append(rate)
        self.update()

    def clear(self):
        self.data.clear()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#101318"))

        if len(self.data) < 2:
            f = QFont("Microsoft YaHei", 9)
            p.setFont(f)
            p.setPen(QColor(C_DIM))
            p.drawText(self.rect(), Qt.AlignCenter, "等待检测数据...")
            p.end()
            return

        left, right, top, bottom = 2, 2, 4, 14
        cw, ch = w - left - right, h - top - bottom

        # 网格线 50% / 100%
        pen = QPen(QColor(C_BORDER))
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        for ratio in (0.5, 1.0):
            y = top + ch * (1 - ratio)
            p.drawLine(int(left), int(y), int(left + cw), int(y))
        f = QFont("Microsoft YaHei", 7)
        p.setFont(f)
        p.setPen(QColor(C_DIM))
        p.drawText(QRectF(0, top + ch * (1 - 1.0) - 8, left + cw, 12),
                   Qt.AlignLeft | Qt.AlignVCenter, "100%")
        p.drawText(QRectF(0, top + ch * (1 - 0.5) - 8, left + cw, 12),
                   Qt.AlignLeft | Qt.AlignVCenter, "50%")

        # 良率曲线
        n = len(self.data)
        pen = QPen(QColor(C_BLUE))
        pen.setWidth(2)
        p.setPen(pen)
        prev = None
        for i, rate in enumerate(self.data):
            x = left + cw * i / float(n - 1)
            y = top + ch * (1 - rate / 100.0)
            if prev is not None:
                p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
            prev = (x, y)

        # 最后一点高亮
        if prev:
            p.setBrush(QColor(C_BLUE))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(int(prev[0]) - 3, int(prev[1]) - 3), 6, 6)
            # 显示最新良率
            p.setPen(QColor(C_TEXT))
            p.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            p.drawText(QRectF(int(prev[0]) - 40, int(prev[1]) - 22, 40, 16),
                       Qt.AlignRight | Qt.AlignVCenter, "%.1f%%" % self.data[-1])

        p.end()


# 缺陷分布图调色板（未登记类别的回落色，按行号循环取色）
_DIST_PALETTE = ["#f85149", "#3b9eff", "#d29922", "#2ea043", "#b478f5",
                 "#e8724c", "#38c8d8", "#f256a5", "#8fb339", "#5d7bf5"]

# 中文类别名 → 颜色（从 infer 的登记表派生，保证分布图配色与画布缺陷框一致）。
# infer 不可用时留空，分布图自动回落到 _DIST_PALETTE。
_NAME_COLORS = {}
try:
    from infer import NAME_ZH as _INZ, CLASS_COLORS as _ICC
    _NAME_COLORS = {_INZ[k]: v for k, v in _ICC.items() if k in _INZ}
except Exception:
    pass


class DefectDistChart(QWidget):
    """缺陷类型分布横向柱状图：各缺陷类型出现次数（降序）

    set_data(dict) 设置全量数据；push(name) 单次累加；clear() 清空。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}          # {缺陷类型: 次数}
        # 09-21：类别从 6 扩到 16 后，96px 只够 8 行，字会糊成一片；
        # 提到 190px 让行高 ≥11px，16 类里能直接看到 10 类（其余归"其他"）。
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def push(self, name):
        if not name or name == "--":
            return
        self.data[name] = self.data.get(name, 0) + 1
        self.update()

    def set_data(self, mapping):
        """全量设置 {类型: 次数}"""
        self.data = {k: int(v) for k, v in (mapping or {}).items() if v}
        self.update()

    def clear(self):
        self.data.clear()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#101318"))

        if not self.data:
            p.setFont(QFont("Microsoft YaHei", 9))
            p.setPen(QColor(C_DIM))
            p.drawText(self.rect(), Qt.AlignCenter, "暂无缺陷数据")
            p.end()
            return

        # 按次数降序。09-21：类别从 6 类扩到 16 类，原先"最多 6 行、其余并入其他"
        # 会让新增类别永远看不见 → 按可用高度动态定行数（每行至少 11px 才可读），
        # 上限 10 行，超出部分合并为"其他"。面板越高能显示的类别越多。
        max_rows = int(h / 11) if h else 10
        max_rows = max(3, min(10, max_rows))
        items = sorted(self.data.items(), key=lambda kv: kv[1], reverse=True)
        if len(items) > max_rows:
            other = sum(v for _, v in items[max_rows - 1:])
            items = items[:max_rows - 1] + [("其他", other)]

        rows = len(items)
        row_h = h / float(rows)
        bar_area_w = w - 8            # 边距
        label_w = min(64, int(w * 0.28))
        max_v = max(v for _, v in items) or 1
        f = QFont("Microsoft YaHei", 9)

        for i, (name, v) in enumerate(items):
            y = int(i * row_h)
            bar_h = max(6, int(row_h * 0.52))
            by = int(y + (row_h - bar_h) / 2)
            # 颜色：优先用该缺陷类型的登记色（与预览画布上的框色一致），
            # 未登记的（如"其他"）才按行号回落调色板。
            color = QColor(_NAME_COLORS.get(name) or
                           _DIST_PALETTE[i % len(_DIST_PALETTE)])
            # 类别名
            p.setFont(f)
            p.setPen(QColor(C_TEXT))
            txt = name if len(name) <= 6 else name[:6] + "…"
            p.drawText(QRectF(4, y, label_w, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, txt)
            # 柱
            bx = 4 + label_w
            bw = int((bar_area_w - label_w - 40) * v / float(max_v))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(bx, by, max(bw, 2), bar_h), 2, 2)
            # 次数
            p.setPen(QColor(C_DIM))
            p.drawText(QRectF(bx + max(bw, 2) + 6, y, 40, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, str(v))
        p.end()


class ToggleSwitch(QWidget):
    """简单 ON/OFF 开关（ROI 启用）"""
    toggled = pyqtSignal(bool)

    def __init__(self, on=True, parent=None):
        super().__init__(parent)
        self.on = on
        self.setFixedSize(34, 18)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        self.on = not self.on
        self.update()
        self.toggled.emit(self.on)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(C_GREEN) if self.on else QColor(C_BORDER)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(self.rect(), 9, 9)
        p.setBrush(QBrush(QColor("#ffffff")))
        d = 14
        x = self.width() - d - 2 if self.on else 2
        p.drawEllipse(x, 2, d, d)
        p.end()


class PreviewCanvas(QWidget):
    """实时预览画布：绘制占位工件图 + ROI 绿框 + 缺陷红框 + 角标结果

    支持加载真实图片：set_image(path) 后画布显示实际图片而非模拟工件图。
    支持缩放：set_zoom()/zoom_in()/zoom_out()/滚轮；zoom_changed 信号可同步外部控件。
    """
    zoom_changed = pyqtSignal(float)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result = "NG"          # NG / OK
        self.confidence = 99
        self.rois = [(0.18, 0.10, 0.64, 0.80), (0.30, 0.28, 0.40, 0.44)]
        self.defects = [(0.62, 0.52, 0.09, 0.16), (0.78, 0.62, 0.10, 0.14)]
        self._flash = False
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        self._image = None          # QPixmap, None 时绘制模拟工件
        self._image_path = ""       # 当前加载的图片路径
        self._real_defects = []     # 真实检测框: [{xyxy(归一化), name, conf, color}, ...]
        self._zoom = 1.0            # 图片缩放倍率（1.0 = 适配画布）
        self.setMouseTracking(True)

    # ---------------- 缩放 ----------------
    def set_zoom(self, z):
        """设置缩放倍率（0.25~4.0）。对图片与模拟画面均生效（以画布中心缩放）"""
        z = max(0.25, min(4.0, float(z)))
        if abs(z - self._zoom) < 1e-6:
            return
        self._zoom = z
        self.update()
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self):
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self._zoom / 1.25)

    def reset_zoom(self):
        self.set_zoom(1.0)

    @property
    def zoom(self):
        return self._zoom

    def wheelEvent(self, e):
        """滚轮缩放（图片/模拟画面均可）"""
        d = e.angleDelta().y()
        if d > 0:
            self.zoom_in()
        elif d < 0:
            self.zoom_out()

    def set_result(self, result, conf):
        self.result = result
        self.confidence = conf
        self.update()

    def set_image(self, path):
        """加载并显示真实图片（缩放重置为 1.0）"""
        if not path:
            return False
        pix = QPixmap(path)
        if pix.isNull():
            return False
        self._image = pix
        self._image_path = path
        self._last_bytes = None
        self._zoom = 1.0
        self.zoom_changed.emit(1.0)
        self.update()
        return True

    def set_image_bytes(self, data):
        """从图片字节(如 JPEG/PNG 二进制)加载并显示，缩放重置为 1.0。返回是否成功。

        用于边缘部署：板端把推理帧编码为 base64 JPEG 随结果下发，
        HMI 直接解码渲染，无需本地图像文件。原始字节会暂存于 _last_bytes，
        供结果落盘时写出为图片文件。
        """
        if not data:
            return False
        pix = QPixmap()
        if not pix.loadFromData(data):
            return False
        if pix.isNull():
            return False
        self._image = pix
        self._image_path = ""
        self._last_bytes = bytes(data)
        self._zoom = 1.0
        self.zoom_changed.emit(1.0)
        self.update()
        return True

    def clear_image(self):
        """清除图片，恢复模拟工件显示（缩放重置）"""
        self._image = None
        self._image_path = ""
        self._zoom = 1.0
        self.zoom_changed.emit(1.0)
        self.update()

    def set_live_frame(self, qimg):
        """设置实时相机帧（QImage）。与 set_image 不同：不重置缩放、
        不触发 zoom_changed（避免每帧扰动外部缩放控件），且清空图片字节标记。
        """
        if qimg is None or qimg.isNull():
            return False
        self._image = QPixmap.fromImage(qimg)
        self._image_path = ""
        self._last_bytes = None
        self.update()
        return True

    def has_image(self):
        return self._image is not None

    def image_path(self):
        return self._image_path

    def set_defects(self, defects):
        """设置真实检测框（归一化坐标 + 标签 + 颜色）。空列表=清除。"""
        self._real_defects = list(defects) if defects else []
        self.update()

    def clear_defects(self):
        """清除真实检测框（恢复模拟/无框状态）"""
        self._real_defects = []
        self.update()

    def clear_result(self):
        """清除结果与检测框，回到待机状态（保留已加载的图片/预览帧）。

        result 置 None：paintEvent 不再绘制 NG/OK 角标与置信度，
        也不再回退绘制模拟缺陷红框（该回退仅在 result == "NG" 时触发）。
        用于"停止检测"后画面复原，避免上一帧结果冻结在屏幕上。
        """
        self.result = None
        self.confidence = 0
        self._real_defects = []
        self._flash = False
        try:
            self._flash_timer.stop()
        except Exception:
            pass
        self.update()

    def trigger_flash(self):
        """触发红色闪烁报警"""
        self._flash = True
        self.update()
        self._flash_timer.start(600)

    def _end_flash(self):
        self._flash = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#101318"))

        p.save()
        # 统一缩放：以画布为中心对**全部内容**（图片/模拟工件/ROI/检测框）缩放。
        # 修复：此前缩放只改 _zoom 且仅在加载图片时生效，模拟画面下
        # 「放大/缩小/比例下拉/滚轮」全部无响应。
        if abs(self._zoom - 1.0) > 1e-6:
            p.translate(w / 2.0, h / 2.0)
            p.scale(self._zoom, self._zoom)
            p.translate(-w / 2.0, -h / 2.0)

        if self._image is not None:
            # --- 显示真实图片（等比缩放居中）---
            pix = self._image
            pw, ph = pix.width(), pix.height()
            scale = min(w / pw, h / ph)
            dw, dh = int(pw * scale), int(ph * scale)
            dx, dy = (w - dw) // 2, (h - dh) // 2
            p.drawPixmap(dx, dy, dw, dh, pix)
            # 用图片区域作为坐标系参考
            canvas_w, canvas_h = dw, dh
            canvas_x, canvas_y = dx, dy
        else:
            # --- 模拟工件（轴承端面）---
            cx, cy = w * 0.5, h * 0.52
            R = min(w, h) * 0.34
            grad = QLinearGradient(cx - R, cy, cx + R, cy)
            grad.setColorAt(0, QColor("#3a3f46"))
            grad.setColorAt(0.5, QColor("#9aa1a9"))
            grad.setColorAt(1, QColor("#33383e"))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRect(QRectF(cx - R * 1.5, cy - R * 0.62, R * 3.0, R * 1.24))
            for ratio, c1, c2 in [
                (1.0, "#b9bfc6", "#6b7077"),
                (0.80, "#e8eaec", "#9ea3aa"),
                (0.55, "#7c828a", "#4c5157"),
                (0.34, "#c9ced4", "#878d94"),
            ]:
                g = QLinearGradient(cx - R * ratio, cy - R * ratio,
                                    cx + R * ratio, cy + R * ratio)
                g.setColorAt(0, QColor(c1))
                g.setColorAt(1, QColor(c2))
                p.setBrush(QBrush(g))
                p.drawEllipse(QPoint(int(cx), int(cy)), int(R * ratio), int(R * ratio))
            p.setBrush(QBrush(QColor("#2a2e33")))
            p.drawEllipse(QPoint(int(cx), int(cy)), int(R * 0.16), int(R * 0.16))
            # 模拟模式用整个画布坐标
            canvas_w, canvas_h = w, h
            canvas_x, canvas_y = 0, 0

        # --- ROI 绿框 ---
        pen = QPen(QColor(C_GREEN))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for (rx, ry, rw, rh) in self.rois:
            p.drawRect(QRectF(canvas_x + rx * canvas_w, canvas_y + ry * canvas_h,
                              rw * canvas_w, rh * canvas_h))

        # --- 真实检测框（多类别颜色 + 标签）---
        if self._real_defects:
            f = QFont("Microsoft YaHei", 10, QFont.Bold)
            for d in self._real_defects:
                x1, y1, x2, y2 = d.get("xyxy", [0, 0, 0, 0])
                rx = x1 * canvas_w
                ry = y1 * canvas_h
                rw = (x2 - x1) * canvas_w
                rh = (y2 - y1) * canvas_h
                color = QColor(d.get("color", C_RED))
                pen = QPen(color)
                pen.setWidth(2)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(canvas_x + rx, canvas_y + ry, rw, rh))
                # 标签：类别名 + 置信度。
                # 09-21：优先用中文名 name_zh（边缘结果的 name 是英文原名，
                # 用于入库口径；本地推理两者一致，取谁都不会错）。
                label = "%s %.2f" % (d.get("name_zh") or d.get("name", ""),
                                     d.get("conf", 0))
                p.setFont(f)
                tb = p.fontMetrics().boundingRect(label)
                lx = canvas_x + rx
                ly = canvas_y + ry - tb.height() - 4
                if ly < 0:
                    ly = canvas_y + ry + 2
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(color))
                p.drawRect(QRectF(lx, ly, tb.width() + 8, tb.height() + 4))
                p.setPen(QColor("#ffffff"))
                p.drawText(QRectF(lx + 4, ly, tb.width() + 4, tb.height() + 4),
                           Qt.AlignLeft | Qt.AlignVCenter, label)
        # --- 缺陷红框（模拟，无真实框时回退）---
        elif self.result == "NG":
            pen = QPen(QColor(C_RED))
            pen.setWidth(2)
            p.setPen(pen)
            for (rx, ry, rw, rh) in self.defects:
                p.drawRect(QRectF(canvas_x + rx * canvas_w, canvas_y + ry * canvas_h,
                                  rw * canvas_w, rh * canvas_h))

        p.restore()   # 结束缩放变换：角标/闪烁边框保持屏幕尺寸，不随缩放

        # --- 右上角结果角标（待机时 result=None，不绘制）---
        if self.result:
            f = QFont("Microsoft YaHei", 26, QFont.Bold)
            p.setFont(f)
            color = QColor(C_RED) if self.result == "NG" else QColor(C_GREEN)
            p.setPen(color)
            p.drawText(QRectF(0, 6, w - 16, 44),
                       Qt.AlignRight | Qt.AlignVCenter, self.result)
            f2 = QFont("Microsoft YaHei", 11)
            p.setFont(f2)
            p.drawText(QRectF(0, 46, w - 16, 22),
                       Qt.AlignRight | Qt.AlignVCenter,
                       "置信度: %d%%" % self.confidence)

        # --- NG 闪烁报警边框 ---
        if self._flash:
            pen = QPen(QColor(255, 0, 0, 200))
            pen.setWidth(6)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(3, 3, w - 6, h - 6)

        p.end()
