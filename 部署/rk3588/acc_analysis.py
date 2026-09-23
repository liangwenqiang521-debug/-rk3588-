# -*- coding: utf-8 -*-
"""
用 RKNN 官方 accuracy_analysis 做逐层精度对比，定位数值崩坏的具体层。

原理：把 ONNX 的浮点仿真结果 与 RKNN 编译后（模拟器）的逐层结果做 cosine 相似度
/ 欧氏距离对比，输出一份报告。相似度突然掉下来的那一层就是元凶。

用法（板子上，需要 rknn-toolkit2 + torch）：
    PYTHONPATH=/root/rknn_convert/libs python3 acc_analysis.py \
        --src best_neu6.onnx --image /tmp/vimgs/crazing_0.jpg --out /root/rknn_convert/snap
"""

import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="best_neu6.onnx")
    ap.add_argument("--image", default="/tmp/vimgs/crazing_0.jpg")
    ap.add_argument("--out", default="/root/rknn_convert/snap")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--opt-level", type=int, default=3)
    ap.add_argument("--no-norm", action="store_true")
    args = ap.parse_args()

    from rknn.api import RKNN

    os.makedirs(args.out, exist_ok=True)

    rk = RKNN(verbose=False)
    cfg = dict(target_platform="rk3588")
    if not args.no_norm:
        cfg.update(mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]],
                   quant_img_RGB2BGR=True)
    cfg["optimization_level"] = args.opt_level
    print("config:", cfg)
    rk.config(**cfg)

    if rk.load_onnx(model=args.src,
                    input_size_list=[[1, 3, args.imgsz, args.imgsz]]) != 0:
        raise SystemExit("load_onnx 失败")
    if rk.build(do_quantization=False) != 0:
        raise SystemExit("build 失败")

    print("开始精度分析(需要几分钟)...")
    ret = rk.accuracy_analysis(inputs=[args.image], output_dir=args.out)
    print("accuracy_analysis ret =", ret)

    rk.release()

    # 打印报告里相似度最低的若干层
    txt = os.path.join(args.out, "error_analysis.txt")
    if not os.path.exists(txt):
        for root, _dirs, files in os.walk(args.out):
            for f in files:
                if f.endswith(".txt") or f.endswith(".csv"):
                    print("产出文件:", os.path.join(root, f))
        return

    print("\n===== error_analysis.txt (尾部) =====")
    with open(txt, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    print("".join(lines[-60:]))

    # 解析出 cosine 相似度最小的层
    print("\n===== cosine 相似度最低的 15 层 =====")
    rows = []
    for ln in lines:
        parts = ln.replace("\t", " ").split()
        if len(parts) < 3:
            continue
        for p in parts:
            try:
                v = float(p)
            except ValueError:
                continue
            if -1.0 <= v <= 1.0:
                rows.append((v, ln.strip()[:150]))
                break
    rows.sort()
    for v, ln in rows[:15]:
        print("  %.6f  %s" % (v, ln))


if __name__ == "__main__":
    main()
