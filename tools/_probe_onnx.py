# -*- coding: utf-8 -*-
"""板端探针：查现有 ONNX 的 opset / IO 形状 + rknn-toolkit2 版本。只读。"""
import os
import sys

os.environ.setdefault("PYTHONPATH", "/root/rknn_convert/libs")

try:
    import onnx
    for name in ("best_neu6.onnx", "best_negdagm.onnx"):
        p = os.path.join("/root/rknn_convert", name)
        if not os.path.exists(p):
            print("%-22s (缺失)" % name)
            continue
        m = onnx.load(p)
        opset = [oi.version for oi in m.opset_import]
        ins = [(i.name, [d.dim_value for d in i.type.tensor_type.shape.dim]) for i in m.graph.input]
        outs = [(o.name, [d.dim_value for d in o.type.tensor_type.shape.dim]) for o in m.graph.output]
        print("%-22s opset=%s" % (name, opset))
        print("   in : %s" % ins)
        print("   out: %s" % outs)
except Exception as e:
    print("onnx 探测失败: %r" % e)

try:
    import rknn
    v = getattr(rknn, "__version__", None)
    print("rknn-toolkit2:", v if v else "(无 __version__ 属性)")
    from rknn.api import RKNN  # noqa
    print("rknn.api.RKNN 可导入 OK")
except Exception as e:
    print("rknn 探测失败: %r" % e)

try:
    import onnxruntime as ort
    print("onnxruntime:", ort.__version__)
except Exception as e:
    print("onnxruntime 探测失败: %r" % e)

print("python:", sys.version.split()[0])
