# -*- coding: utf-8 -*-
"""真实缺陷检测推理引擎（YOLO）。

- 优先用 ultralytics 加载 PyTorch 权重（best.pt），也兼容 ONNX（ultralytics 自动走 onnxruntime）。
- 返回归一化坐标 + 中文类别名 + 颜色，便于 PyQt5 画布绘制。
- 推理在 CPU 上进行（RK3588 边缘部署为后续 P3 阶段，见 docs/开发路线图.md）。

设计原则：本模块被上位机 import，因此依赖缺失时降级提示，不阻断启动。
"""
import os
import time
import numpy as np

try:
    from ultralytics import YOLO
    _HAS_ULTRALYTICS = True
except Exception:
    _HAS_ULTRALYTICS = False
    YOLO = None

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False
    cv2 = None


# 类别中文映射。
# 前 6 项顺序与 模型训练/data_neu.yaml（NEU-DET）严格一致，勿动顺序；
# 之后是 09-21 扩展的类别表（工业常见扩展类 + 表面处理类），
# 供扩类模型 / 板端标签 / 演示模式共用。en 名务必用下划线小写，
# 与 YOLO names 写法和板端 NAMES 保持一致。
NAME_ZH = {
    # ---- NEU-DET 六类（顺序即模型 cls 索引，勿改）----
    "crazing": "龟裂",
    "inclusion": "夹杂物",
    "patches": "斑块",
    "pitted_surface": "麻面",
    "rolled-in_scale": "轧入氧化皮",
    "scratches": "划痕",
    # ---- 工业常见扩展类（热轧/冷轧板带高频缺陷）----
    "edge_crack": "边裂",
    "scab": "结疤",
    "pitting": "点蚀",
    "roll_mark": "辊印",
    "wavy_edge": "边浪",
    "oxide_scale": "氧化铁皮压入",
    # ---- 表面处理类缺陷 ----
    "stain": "污渍",
    "oil_spot": "油污",
    "water_spot": "水渍",
    "rust": "锈蚀",
    # ---- 兼容旧合成数据 4 类 ----
    "scratch": "划痕",
    "dent": "凹陷",
    "missing": "缺料",
    "crack": "裂纹",
}
# 类别颜色（十六进制，与 widgets.py 调色板一致）。
# 前 6 项为 NEU 原配色，勿改（历史图表/论文截图已引用）；
# 扩展类按色相环错开取色，保证同类在不同图上颜色恒定、彼此可辨。
CLASS_COLORS = {
    # ---- NEU-DET 六类（原配色，勿改）----
    "crazing": "#a371f7",          # 紫
    "inclusion": "#2f81f7",        # 蓝
    "patches": "#d29922",          # 黄
    "pitted_surface": "#3fb950",   # 绿
    "rolled-in_scale": "#f85149",  # 红
    "scratches": "#e3b341",        # 橙
    # ---- 工业常见扩展类 ----
    "edge_crack": "#ff6b9d",       # 玫红
    "scab": "#8b6f47",             # 棕
    "pitting": "#00b8d4",          # 青
    "roll_mark": "#9e7bff",        # 淡紫
    "wavy_edge": "#4dd0e1",        # 浅青
    "oxide_scale": "#b06a3b",      # 赭
    # ---- 表面处理类缺陷 ----
    "stain": "#7f8c8d",            # 灰
    "oil_spot": "#ffa726",         # 琥珀
    "water_spot": "#26c6da",       # 天青
    "rust": "#c1440e",             # 铁锈红
    # ---- 兼容旧合成数据 4 类 ----
    "scratch": "#d29922",
    "dent": "#2f81f7",
    "missing": "#f85149",
    "crack": "#a371f7",
}
DEFAULT_COLOR = "#f85149"

# 类别枚举（供演示模式 / 分布图 / 下拉框按序展示）
DEFECT_CLASSES = [
    "crazing", "inclusion", "patches", "pitted_surface",
    "rolled-in_scale", "scratches",
    "edge_crack", "scab", "pitting", "roll_mark", "wavy_edge", "oxide_scale",
    "stain", "oil_spot", "water_spot", "rust",
]


def load_image(path):
    """读取图片（支持中文路径），返回 cv2 BGR 数组；失败返回 None。"""
    if not _HAS_CV2:
        return None
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class DefectDetector:
    """封装 YOLO 推理，提供 predict_cv2(img) -> defects。"""

    def __init__(self, weights, conf=0.25, imgsz=640, device="cpu", iou=0.45):
        self.weights = weights
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.iou = iou
        self.model = None
        self.names = {}
        self.load_error = None
        self._load()

    def _resolve(self, weights):
        if os.path.isabs(weights) and os.path.exists(weights):
            return weights
        here = os.path.dirname(os.path.abspath(__file__))
        cand = os.path.join(here, weights)
        if os.path.exists(cand):
            return cand
        cand2 = os.path.join(here, "模型训练", os.path.basename(weights))
        if os.path.exists(cand2):
            return cand2
        return weights

    def _load(self):
        if not _HAS_ULTRALYTICS:
            self.load_error = "ultralytics 未安装，无法进行真实推理"
            return
        try:
            path = self._resolve(self.weights)
            self.model = YOLO(path)
            self.names = dict(self.model.names)
        except Exception as e:
            self.load_error = "模型加载失败: %s" % e
            self.model = None

    @property
    def ready(self):
        return self.model is not None

    def predict_cv2(self, img_bgr, conf=None, iou=None, min_area=0):
        """输入 cv2 BGR 图，返回缺陷列表。

        每个缺陷: {xyxy_px:[x1,y1,x2,y2], xyxy:[x1n,y1n,x2n,y2n](归一化),
                  conf, cls, name_en, name(中文), color}
        """
        if self.model is None:
            return []
        h, w = img_bgr.shape[:2]
        use_conf = conf if conf is not None else self.conf
        use_iou = iou if iou is not None else self.iou
        res = self.model.predict(
            img_bgr, conf=float(use_conf), iou=float(use_iou),
            imgsz=self.imgsz, device=self.device, verbose=False)[0]
        defects = []
        for b in res.boxes:
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
            if min_area and (x2 - x1) * (y2 - y1) < min_area:
                continue
            c = float(b.conf[0])
            cls = int(b.cls[0])
            en = self.names.get(cls, "defect_%d" % cls)
            zh = NAME_ZH.get(en, en)
            color = CLASS_COLORS.get(en, DEFAULT_COLOR)
            defects.append({
                "xyxy_px": [x1, y1, x2, y2],
                "xyxy": [x1 / w, y1 / h, x2 / w, y2 / h],
                "conf": c,
                "cls": cls,
                "name_en": en,
                "name": zh,
                "color": color,
            })
        return defects
