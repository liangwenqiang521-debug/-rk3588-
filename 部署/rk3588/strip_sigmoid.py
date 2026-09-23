# -*- coding: utf-8 -*-
"""
YOLOv11 ONNX 图手术：去掉分类头末尾的 Sigmoid，让模型输出原始 logits。
====================================================================
背景
----
RK3588 + RKNN 2.3.2 把 `Conv -> Sigmoid` 融合成 `ConvExSigmoid`（NPU 用 LUT
实现 sigmoid）。实测该融合在**分类头**上结果错误：box 分支完全正常，但 6 个类别
的分数被抹平（最大仅 0.137，且 argmax 跑到错误的类），软/硬件模拟器结果一致，
说明是**编译器**问题而非 NPU 驱动问题。
（本板此前 INT8 也出现过"分类头输出全 0、box 正常"，同一病症。）

做法
----
把最终 Concat 的第二个输入从 `Sigmoid_output_0` 改成 `Sigmoid` 的输入张量，
即让模型直接输出 **logits**。这样图里就没有会触发 `ConvExSigmoid` 融合的尾部
Sigmoid，类别分数改由 host 端 numpy 做 sigmoid（board_infer.py 已支持
`--cls-sigmoid on` / auto 自动判定）。

用法
----
    python strip_sigmoid.py best_neu6.onnx best_neu6_logits.onnx
"""

import sys
import onnx


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "best_neu6.onnx"
    dst = sys.argv[2] if len(sys.argv) > 2 else "best_neu6_logits.onnx"

    m = onnx.load(src)
    g = m.graph

    # 1) 定位末尾那个把 [box, cls] 拼起来的 Concat（它的输出就是 output0）
    out_names = {o.name for o in g.output}
    tail = None
    for n in g.node:
        if n.op_type == "Concat" and any(o in out_names for o in n.output):
            tail = n
            break
    if tail is None:
        raise SystemExit("没找到输出 output0 的 Concat 节点，模型结构不是预期形态")

    print("末尾 Concat: out=%s  输入=%s" % (list(tail.output), list(tail.input)))

    # 2) 找出哪个输入来自 Sigmoid，把它换成 Sigmoid 的输入（即 logits）
    sig_out = {}
    for n in g.node:
        if n.op_type == "Sigmoid":
            for o in n.output:
                sig_out[o] = n.input[0]

    replaced = False
    for i, inp in enumerate(tail.input):
        if inp in sig_out:
            print("  输入[%d] %s 来自 Sigmoid -> 替换为 %s" % (i, inp, sig_out[inp]))
            tail.input[i] = sig_out[inp]
            replaced = True
    if not replaced:
        raise SystemExit("末尾 Concat 的输入里没有 Sigmoid 输出，模型可能已经不含尾部 sigmoid")

    # 3) 清理：删除不再被任何节点引用的 Sigmoid（以及可能的死节点）
    used = set()
    for n in g.node:
        used.update(n.input)
    used.update(out_names)

    keep = []
    removed = []
    for n in g.node:
        if n.op_type == "Sigmoid" and all(o not in used for o in n.output):
            removed.append(list(n.output))
            continue
        keep.append(n)
    print("  删除无用 Sigmoid: %s" % removed)
    del g.node[:]
    g.node.extend(keep)

    # 4) 校验并保存
    onnx.checker.check_model(m)
    onnx.save(m, dst)
    print("✅ 已保存: %s" % dst)
    print("   模型现在输出 [box(4), cls_logits(6)]，host 端需自行 sigmoid 类别通道。")


if __name__ == "__main__":
    main()
