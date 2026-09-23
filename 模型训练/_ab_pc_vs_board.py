# -*- coding: utf-8 -*-
"""A/B 定位：PC 端 aug 模型直接推理，与板端 RKNN 结果对照。
用法: venv_cuda/Scripts/python.exe _ab_pc_vs_board.py
"""
import sys
from ultralytics import YOLO

W = "runs/neu_yolo11n_aug/weights/best.pt"
IMGS = [
    ("../图片/scratches/scratches_108.jpg", "scratches"),
    ("../图片/inclusion/inclusion_108.jpg", "inclusion"),
    ("../图片/rolled-in_scale/rolled-in_scale_108.jpg", "rolled-in_scale"),
]

model = YOLO(W)
names = model.names
print("模型:", W)
print("类别:", names)
print("conf=0.20（板端生产阈值）与 0.40 各跑一遍\n")

for path, true_cls in IMGS:
    for conf in (0.20, 0.40):
        rs = model.predict(path, conf=conf, iou=0.45, imgsz=640, verbose=False)
        dets = []
        for b in rs[0].boxes:
            dets.append("%s(%.2f)" % (names[int(b.cls)], float(b.conf)))
        print("%-28s true=%-15s conf=%.2f -> %s"
              % (path.split("/")[-1] + ("@%.2f" % conf), true_cls, conf,
                 dets if dets else "无检出"))
    print()
