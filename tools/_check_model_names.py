# -*- coding: utf-8 -*-
"""临时校验：确认 39 类 .pt 的内嵌 names 是 snake_case 且能被 infer.NAME_ZH / CLASS_COLORS 接住。

用法（项目根）：
    .venv/Scripts/python.exe tools/_check_model_names.py [模型路径]
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ultralytics import YOLO  # noqa: E402

from infer import NAME_ZH, CLASS_COLORS, CLASSES_39  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    _ROOT, "模型训练", "best_steel39_yolo11n_640.pt")

print("模型:", path)
print("存在:", os.path.exists(path))
m = YOLO(path)
names = m.names
vals = [names[i] for i in sorted(names)]
print("nc =", len(vals))
print("前 12 个 names:", vals[:12])

miss_zh = [v for v in vals if v not in NAME_ZH]
miss_col = [v for v in vals if v not in CLASS_COLORS]
print("模型 names == infer.CLASSES_39 :", vals == CLASSES_39)
print("缺中文名 :", miss_zh or "无")
print("缺配色   :", miss_col or "无")
print("NAME_ZH 条数:", len(NAME_ZH), " CLASS_COLORS 条数:", len(CLASS_COLORS))
