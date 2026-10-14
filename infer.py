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
    # ---- 09-28 扩展：39 类工业钢材表面缺陷（来源 缺陷检测扩展/data.yaml，production v2.1）----
    # 与 data.yaml 的 ids 顺序一一对应（见下方 CLASSES_39）；en 名统一小写 + 下划线。
    # 注意：crazing / inclusion / patches / pitted_surface / rolled-in_scale /
    # oil_spot / water_spot 已在上方登记，此处不重复；旧扩展类（edge_crack 等）
    # 与旧合成别名（scratch 等）全部保留，供历史数据与旧板端权重兼容。
    "bright_scratch": "亮划痕",
    "crease": "折痕",
    "crescent_gap": "月牙缺口",
    "dark_scratches": "暗划痕",
    "finishing_roll_printing": "精轧辊印",
    "iron_scale_compression": "氧化铁皮压入",
    "iron_sheet_ash": "铁皮灰",
    "oxide_scale_plate": "板系氧化铁皮",
    "oxide_scale_temp": "温系氧化铁皮",
    "punching": "冲孔",
    "red_iron_sheet": "红斑铁皮",
    "rolled_pit": "轧制凹坑",
    "secondary_rust_skin": "二次锈皮",
    "silk_spot": "丝斑",
    "slag_inclusion": "夹渣",
    "waist_folding": "腰部折痕",
    "welding_line": "焊缝线",
    "white_rust": "白锈",
    "cutting_opening": "切边开口",
    "water_slag_mark": "水渣痕",
    "slag_skin": "渣皮",
    "longitudinal_crack": "纵向裂纹",
    "warp": "翘曲",
    "external_fold": "外折",
    "wrinkle": "褶皱",
    "blocky_scale": "块状氧化铁皮",
    "striated_scale": "条纹氧化铁皮",
    "foreign_obj": "异物",
    "blowhole": "气孔",
    "break": "断裂",
    "fray": "散边毛刺",
    "uneven": "厚薄不均",
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
    # ---- 09-28 扩展：39 类工业钢材表面缺陷配色 ----
    # 与上方 20 色错开取色；同类在不同图上颜色恒定、彼此尽量可辨。
    "bright_scratch": "#ffd166",            # 亮黄
    "crease": "#f78c6b",                    # 鲑橙
    "crescent_gap": "#c792ea",              # 浅紫
    "dark_scratches": "#8d6e63",            # 深褐
    "finishing_roll_printing": "#64b5f6",   # 天蓝
    "iron_scale_compression": "#a1887f",    # 灰褐
    "iron_sheet_ash": "#78909c",            # 蓝灰
    "oxide_scale_plate": "#ff8a65",         # 珊瑚
    "oxide_scale_temp": "#d4a373",          # 沙黄
    "punching": "#4db6ac",                  # 青绿
    "red_iron_sheet": "#e57373",            # 浅红
    "rolled_pit": "#7986cb",                # 靛蓝
    "secondary_rust_skin": "#bf360c",       # 深锈红
    "silk_spot": "#f06292",                 # 粉
    "slag_inclusion": "#6d4c41",            # 深棕
    "waist_folding": "#9575cd",             # 紫罗兰
    "welding_line": "#26a69a",              # 蓝绿
    "white_rust": "#cfd8dc",                # 银白
    "cutting_opening": "#ffab91",           # 浅珊瑚
    "water_slag_mark": "#29b6f6",           # 亮蓝
    "slag_skin": "#8d9440",                 # 橄榄
    "longitudinal_crack": "#ef5350",        # 红
    "warp": "#5c6bc0",                      # 蓝紫
    "external_fold": "#ffb74d",             # 橙黄
    "wrinkle": "#ba68c8",                   # 紫红
    "blocky_scale": "#aed581",              # 浅绿
    "striated_scale": "#9ccc65",            # 黄绿
    "foreign_obj": "#00acc1",               # 青
    "blowhole": "#90a4ae",                  # 灰蓝
    "break": "#d32f2f",                     # 正红
    "fray": "#ffcc80",                      # 杏
    "uneven": "#7e57c2",                    # 深紫
}
DEFAULT_COLOR = "#f85149"

# 39 类工业钢材表面缺陷（顺序 = 缺陷检测扩展/data.yaml 的 ids，即模型 cls 索引）。
# 来源：datasets_master/production/v2.1（25689 图，train 20947 / val 5296）。
# 注意：rolled-in_scale 沿用 NEU 原有的连字符写法，与历史权重 names 保持一致。
CLASSES_39 = [
    "bright_scratch",           # 0  亮划痕
    "crazing",                  # 1  龟裂
    "crease",                   # 2  折痕
    "crescent_gap",             # 3  月牙缺口
    "dark_scratches",           # 4  暗划痕
    "finishing_roll_printing",  # 5  精轧辊印
    "inclusion",                # 6  夹杂物
    "iron_scale_compression",   # 7  氧化铁皮压入
    "iron_sheet_ash",           # 8  铁皮灰
    "oil_spot",                 # 9  油污
    "oxide_scale_plate",        # 10 板系氧化铁皮
    "oxide_scale_temp",         # 11 温系氧化铁皮
    "patches",                  # 12 斑块
    "pitted_surface",           # 13 麻面
    "punching",                 # 14 冲孔
    "red_iron_sheet",           # 15 红斑铁皮
    "rolled-in_scale",          # 16 轧入氧化皮
    "rolled_pit",               # 17 轧制凹坑
    "secondary_rust_skin",      # 18 二次锈皮
    "silk_spot",                # 19 丝斑
    "slag_inclusion",           # 20 夹渣
    "waist_folding",            # 21 腰部折痕
    "water_spot",               # 22 水渍
    "welding_line",             # 23 焊缝线
    "white_rust",               # 24 白锈
    "cutting_opening",          # 25 切边开口
    "water_slag_mark",          # 26 水渣痕
    "slag_skin",                # 27 渣皮
    "longitudinal_crack",       # 28 纵向裂纹
    "warp",                     # 29 翘曲
    "external_fold",            # 30 外折
    "wrinkle",                  # 31 褶皱
    "blocky_scale",             # 32 块状氧化铁皮
    "striated_scale",           # 33 条纹氧化铁皮
    "foreign_obj",              # 34 异物
    "blowhole",                 # 35 气孔
    "break",                    # 36 断裂
    "fray",                     # 37 散边毛刺
    "uneven",                   # 38 厚薄不均
]

# 类别枚举（供演示模式 / 分布图 / 下拉框按序展示）。
# 09-28：由早期 16 类扩为 39 类全量体系。旧的工业扩展类（edge_crack / scab /
# pitting / roll_mark / wavy_edge / oxide_scale / stain / rust）与旧合成别名
# （scratch / dent / missing / crack）仍保留在 NAME_ZH / CLASS_COLORS 中，
# 供历史记录与旧板端权重兼容，但不再出现在本枚举里。
DEFECT_CLASSES = list(CLASSES_39)


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
