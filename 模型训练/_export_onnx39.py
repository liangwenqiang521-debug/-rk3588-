# -*- coding: utf-8 -*-
"""把 39 类 .pt 导出为 ONNX（对齐板端已验证的 opset=12 / imgsz=640 / simplify）。

输出: best_steel39_yolo11n_640.onnx（与 .pt 同目录）
导出后打印 IO 形状，期望 out=[1, 43, 8400]（39 类 + 4 框）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PT = os.path.join(HERE, "best_steel39_yolo11n_640.pt")
IMGSZ = 640
OPSET = 12

if not os.path.exists(PT):
    sys.exit("找不到权重: %s" % PT)

from ultralytics import YOLO

print("[1/2] 从 .pt 导出 ONNX (imgsz=%d, opset=%d, simplify=True) ..." % (IMGSZ, OPSET))
model = YOLO(PT)
out = model.export(format="onnx", imgsz=IMGSZ, simplify=True, opset=OPSET, dynamic=False)
onnx_path = out if isinstance(out, str) else os.path.splitext(PT)[0] + ".onnx"
print("   ONNX:", onnx_path, "%.1f MB" % (os.path.getsize(onnx_path) / 1e6))
print("   模型类别数 nc =", model.model.nc)

print("[2/2] 校验 IO 形状 ...")
try:
    import onnx
    m = onnx.load(onnx_path)
    opset = [oi.version for oi in m.opset_import]
    ins = [(i.name, [d.dim_value for d in i.type.tensor_type.shape.dim]) for i in m.graph.input]
    outs = [(o.name, [d.dim_value for d in o.type.tensor_type.shape.dim]) for o in m.graph.output]
    print("   opset =", opset)
    print("   in    =", ins)
    print("   out   =", outs)
    ok = outs and outs[0][1] == [1, 43, 8400]
    print("   期望 out=[1,43,8400] ->", "PASS" if ok else "MISMATCH!")
except ImportError:
    print("   (本环境无 onnx 包，跳过形状校验)")

print("DONE")
