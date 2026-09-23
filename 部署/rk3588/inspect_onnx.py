# -*- coding: utf-8 -*-
"""查看板端 ONNX 的 opset / 输入输出 / 尾部算子，用于排查 RKNN 兼容性。

用法: PYTHONPATH=/root/rknn_convert/libs python3 inspect_onnx.py best_neu6.onnx
"""
import sys
import onnx


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "best_neu6.onnx"
    m = onnx.load(path)
    print("文件:", path)
    print("opset_import:", [(o.domain or "ai.onnx", o.version) for o in m.opset_import])
    print("ir_version:", m.ir_version)
    print("producer:", m.producer_name, m.producer_version)

    def shape_of(vi):
        t = vi.type.tensor_type
        dims = []
        for d in t.shape.dim:
            dims.append(d.dim_value if d.HasField("dim_value") else (d.dim_param or "?"))
        return dims

    print("inputs:", [(i.name, shape_of(i)) for i in m.graph.input])
    print("outputs:", [(o.name, shape_of(o)) for o in m.graph.output])
    print("n_nodes:", len(m.graph.node))

    ops = [n.op_type for n in m.graph.node]
    from collections import Counter
    print("算子统计:", dict(Counter(ops)))

    # 打印尾部 12 个算子及其输入输出，看 Detect 头结构
    print("\n--- 尾部算子 ---")
    for n in m.graph.node[-12:]:
        print("  %-12s in=%s out=%s" % (n.op_type, list(n.input)[:4], list(n.output)[:3]))

    # 找 Sigmoid，确认分类头是否已含 sigmoid
    sigs = [n for n in m.graph.node if n.op_type == "Sigmoid"]
    print("\nSigmoid 数量:", len(sigs))
    for n in sigs[:4]:
        print("  Sigmoid out:", list(n.output))

    # 检查是否有 dynamic shape / 非常规算子
    unusual = sorted({o for o in ops if o not in {
        "Conv", "Add", "Mul", "Sub", "Div", "Concat", "Reshape", "Transpose",
        "Sigmoid", "Softmax", "MaxPool", "Slice", "Split", "Constant", "Shape",
        "Gather", "Unsqueeze", "Squeeze", "Cast", "Relu", "Pad", "Resize",
        "Clip", "Exp", "ReduceSum", "Range", "Where", "Expand", "Equal",
        "Greater", "Less", "Neg", "Sqrt", "Pow", "Identity", "Flatten",
    }})
    print("\n非 YOLO 常见算子(可能触发兼容性问题):", unusual)


if __name__ == "__main__":
    main()
