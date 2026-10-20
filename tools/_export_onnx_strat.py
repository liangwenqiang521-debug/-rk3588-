# -*- coding: utf-8 -*-
"""把 100 轮分层重训权重（strat）导出 ONNX，供板端转 rknn 做同集对比。

不改动 _export_onnx39.py（原脚本硬编码 50 轮权重），这里是独立包装。
输出: 模型训练/best_steel39_strat_640.onnx（期望 out=[1,43,8400]）

用法: venv_cuda/Scripts/python.exe tools/_export_onnx_strat.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PT = os.path.join(_ROOT, '模型训练', 'best_steel39_yolo11n_640_strat.pt')
OUT = os.path.join(_ROOT, '模型训练', 'best_steel39_strat_640.onnx')
IMGSZ = 640
OPSET = 12

if not os.path.exists(PT):
    sys.exit('找不到权重: %s' % PT)

from ultralytics import YOLO

print('[1/2] 导出 ONNX: %s' % os.path.basename(PT))
model = YOLO(PT)
res = model.export(format='onnx', imgsz=IMGSZ, simplify=True, opset=OPSET, dynamic=False)
src = res if isinstance(res, str) else os.path.splitext(PT)[0] + '.onnx'
if src != OUT:
    if os.path.exists(OUT):
        os.remove(OUT)
    os.replace(src, OUT)
print('   ONNX: %s (%.2f MB)' % (OUT, os.path.getsize(OUT) / 1e6))
print('   nc =', model.model.nc)

print('[2/2] 校验 IO 形状')
try:
    import onnx
    m = onnx.load(OUT)
    print('   opset =', [oi.version for oi in m.opset_import])
    outs = [(o.name, [d.dim_value for d in o.type.tensor_type.shape.dim]) for o in m.graph.output]
    print('   out =', outs)
    ok = outs and outs[0][1] == [1, 43, 8400]
    print('   期望 [1,43,8400] ->', 'PASS' if ok else 'MISMATCH')
except ImportError:
    print('   (无 onnx 包，跳过形状校验)')
