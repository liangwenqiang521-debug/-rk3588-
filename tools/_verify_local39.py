# -*- coding: utf-8 -*-
"""临时验证：本地推理切 39 类后，config 能否被 _scan_models 选中并用真实图跑出中文类名。

用法（项目根）：
    .venv/Scripts/python.exe tools/_verify_local39.py
"""
import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from infer import DefectDetector, load_image  # noqa: E402

cfg = json.load(open(os.path.join(_ROOT, "config.json"), encoding="utf-8"))
mpath = cfg["model"]["path"]
conf = float(cfg["model"]["conf"])
iou = float(cfg["model"]["iou"])
print("config model.path :", mpath)
print("config conf / iou :", conf, "/", iou)

# 模拟 page_detect._scan_models 的 rel 计算（决定下拉框能否选中本模型）
rel = os.path.relpath(os.path.join(_ROOT, mpath), _ROOT).replace("\\", "/")
print("scan 得到的 rel    :", rel, "| 与 config 一致:", rel == mpath)

det = DefectDetector(mpath, conf=conf, imgsz=640, device="cpu", iou=iou)
print("引擎就绪 :", det.ready, "| 错误:", det.load_error, "| 类数:", len(det.names))

labels = os.path.join(_ROOT, "缺陷检测扩展", "labels", "val")
picked = []
for im in sorted(glob.glob(os.path.join(_ROOT, "缺陷检测扩展", "images", "val", "*.jpg"))):
    lp = os.path.join(labels, os.path.splitext(os.path.basename(im))[0] + ".txt")
    if os.path.exists(lp) and os.path.getsize(lp) > 0:
        picked.append(im)
    if len(picked) >= 4:
        break

print("测试图:", [os.path.basename(p) for p in picked])
for im in picked:
    img = load_image(im)
    if img is None:
        print("  读图失败:", im)
        continue
    defs = det.predict_cv2(img)
    top = sorted(defs, key=lambda d: -d["conf"])[:3]
    print("  %-28s 框数=%-3d top=%s" % (
        os.path.basename(im), len(defs),
        [(d["name"], d["name_en"], round(d["conf"], 2)) for d in top]))
