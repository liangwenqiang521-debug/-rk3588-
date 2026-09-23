# -*- coding: utf-8 -*-
"""
RK3588 RKNN 模型转换脚本
====================================================================
将 YOLOv11 权重(.pt 或 .onnx) 转换为 RK3588 NPU 可运行的 .rknn 模型。

默认导出 **FP16（不量化）**——因为板端 NPU 驱动 v0.9.2 + RKNN 2.3.2 跑 INT8
时分类头输出全 0（box 正常），属驱动 bug，需升级到 0.9.6+ 才能用 INT8（有变砖风险，
暂不做）。如需 INT8 可加 --dtype int8（仍可用，但板端推理会出错，仅做导出验证）。

--------------------------------------------------------------------
⚠️ 运行环境要求(非常重要)
--------------------------------------------------------------------
RKNN-Toolkit2 仅支持以下环境，**本机 Windows + Python 3.13 无法运行**：
  * x86_64 Linux (Ubuntu 18.04 / 20.04 / 22.04) + Python 3.8 或 3.10
  * 或直接在 RK3588 板子(aarch64 Linux)上运行

在本机只负责"写好脚本"，转到上面任一环境再执行。
安装示例(在目标 Linux 环境)：
    pip install rknn-toolkit2   # 参见下方说明，官方通常提供 .whl 本地安装

--------------------------------------------------------------------
用法
--------------------------------------------------------------------
# 1) 已有 ONNX(如 NEU 6类 best.onnx)直接转 RKNN(FP16，板端可用)：
python export_rknn.py --src best.onnx --dst best_neu_yolo11n_640.rknn --imgsz 640 \
    --names crazing inclusion patches pitted_surface rolled-in_scale scratches

# 2) 从 .pt 出发(脚本先导出 ONNX，再转 RKNN，如 NEU 6类模型)：
python export_rknn.py --src best_neu_yolo11n_640.pt --dst best_neu_yolo11n_640.rknn \
    --imgsz 640 --names crazing inclusion patches pitted_surface rolled-in_scale scratches

# 3) 合成 4 类模型(FP16)：
python export_rknn.py --src best.onnx --dst best.rknn --imgsz 640 \
    --names scratch dent missing crack

参数说明：
  --src        输入权重，.pt 或 .onnx
  --dst        输出 .rknn 路径
  --calib      校准图目录(仅 --dtype int8 量化用)；会随机抽取 --ncalib 张
  --ncalib     校准图数量(默认 50，越多越准越慢)
  --imgsz      模型输入尺寸(默认 640)
  --names      类别名(仅用于日志提示，不影响模型结构)
  --target     目标平台(默认 rk3588)
  --opset      ONNX opset(导出用，默认 13)
  --dtype      量化类型: fp16(默认, 不量化, 板端生产可用) / int8(需校准集, 板端驱动有bug)
"""

import argparse
import os
import glob
import random


def build_calib_list(calib_dir, ncalib, seed=42):
    """从校准目录随机抽 ncalib 张图，返回绝对路径列表。"""
    exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
    imgs = []
    for ext in exts:
        imgs.extend(glob.glob(os.path.join(calib_dir, "**", ext), recursive=True))
        imgs.extend(glob.glob(os.path.join(calib_dir, ext)))
    if not imgs:
        raise SystemExit("❌ 校准目录未找到任何图片: %s" % calib_dir)
    imgs = sorted(set(imgs))
    random.seed(seed)
    if len(imgs) > ncalib:
        imgs = random.sample(imgs, ncalib)
    print("   校准图数量: %d (来自 %s)" % (len(imgs), calib_dir))
    return imgs


def write_calib_txt(img_list, txt_path):
    """RKNN 校准需要一个 txt，每行一张图的绝对路径。"""
    with open(txt_path, "w", encoding="utf-8") as f:
        for p in img_list:
            f.write(os.path.abspath(p).replace("\\", "/") + "\n")
    return txt_path


def export_onnx_from_pt(pt_path, imgsz, opset):
    """用 ultralytics 把 .pt 导出为简化版 ONNX，返回 onnx 路径。"""
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("❌ 当前环境缺少 ultralytics，无法从 .pt 导出 ONNX。请先 pip install ultralytics。")
    print("   从 .pt 导出 ONNX: %s  (imgsz=%d, opset=%d)" % (pt_path, imgsz, opset))
    model = YOLO(pt_path)
    out = model.export(format="onnx", imgsz=imgsz, simplify=True, opset=opset, dynamic=False)
    # ultralytics 返回导出路径字符串
    onnx_path = out if isinstance(out, str) else os.path.splitext(pt_path)[0] + ".onnx"
    if not os.path.exists(onnx_path):
        raise SystemExit("❌ ONNX 导出失败: %s" % onnx_path)
    print("   ONNX 已生成: %s" % onnx_path)
    return onnx_path


def main():
    ap = argparse.ArgumentParser(description="YOLOv11 -> RK3588 RKNN (INT8) 转换")
    ap.add_argument("--src", required=True, help="输入 .pt 或 .onnx")
    ap.add_argument("--dst", required=True, help="输出 .rknn 路径")
    ap.add_argument("--calib", default="", help="校准图目录(仅 --dtype int8 量化时必填)")
    ap.add_argument("--ncalib", type=int, default=50, help="校准图数量(默认50)")
    ap.add_argument("--imgsz", type=int, default=640, help="输入尺寸(默认640)")
    ap.add_argument("--names", nargs="*", default=[], help="类别名(仅日志提示)")
    ap.add_argument("--target", default="rk3588", help="目标平台(默认rk3588)")
    ap.add_argument("--opset", type=int, default=13, help="ONNX opset(默认13)")
    ap.add_argument("--host-norm", action="store_true",
                    help="改为「host 端已归一化」模式：mean=0/std=1，配合 host 送 float32 [0,1]。"
                         "默认模式是 RKNN 惯用法 mean=0/std=255，配合 host 送 uint8[0,255]，"
                         "（正是 board_server.py 的做法）。两者只能选一个，配对错了会静默失效。")
    ap.add_argument("--opt-level", type=int, default=3,
                    help="RKNN optimization_level(默认3)。实测 0/3 对分类头问题无差别，"
                         "但遇到数值异常时可对比排除图优化因素。")
    ap.add_argument("--dtype", default="fp16", choices=["fp16", "int8"],
                    help="量化类型: fp16(默认,不量化,板端生产可用) / int8(需校准集,板端驱动v0.9.2有bug)")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit("❌ 输入文件不存在: %s" % args.src)
    do_quant = (args.dtype == "int8")
    if do_quant and not os.path.isdir(args.calib):
        raise SystemExit("❌ INT8 量化需要校准目录: %s" % args.calib)

    try:
        from rknn.api import RKNN
    except ImportError:
        raise SystemExit(
            "❌ 未找到 rknn-toolkit2。\n"
            "   本脚本必须在 x86_64 Linux(Ubuntu) 或 RK3588 板子上运行，"
            "并先安装 rknn-toolkit2。\n"
            "   参考: https://github.com/airockchip/rknn-toolkit2"
        )

    # 1) 准备 ONNX
    src = args.src
    if src.lower().endswith(".pt"):
        onnx_path = export_onnx_from_pt(src, args.imgsz, args.opset)
    elif src.lower().endswith(".onnx"):
        onnx_path = src
        print("   使用现有 ONNX: %s" % onnx_path)
    else:
        raise SystemExit("❌ --src 仅支持 .pt 或 .onnx")

    # 2) 准备校准集（仅 INT8 需要）
    if do_quant:
        calib_imgs = build_calib_list(args.calib, args.ncalib)
        calib_txt = os.path.splitext(args.dst)[0] + "_calib.txt"
        write_calib_txt(calib_imgs, calib_txt)
        print("   校准列表: %s" % calib_txt)
    else:
        calib_txt = None
        print("   跳过校准集(FP16 不量化)")

    # 3) 配置 + 转换
    do_quant = (args.dtype == "int8")
    rknn = RKNN(verbose=True)
    print("[1/4] rknn.config ...")
    # ⚠️⚠️ mean_values / std_values 是 RKNN **在模型内部**对输入做的归一化
    #      (x - mean) / std，与 host 端预处理**会叠加**！两者必须严格配对：
    #
    #   ① 默认（推荐，本函数默认值）：host 送 **uint8 原图 [0,255]**，
    #      配置 mean=0 / std=255 -> RKNN 内部归一化到 [0,1]。
    #      board_server.py 就是这么喂的（cvtColor 后直接 uint8 NHWC）。
    #      INT8 量化校准时 RKNN 也按同一套 mean/std 处理校准图，因此保持一致。
    #
    #   ② --host-norm：host 端**自己**归一化到 float32 [0,1]（board_infer.py 的
    #      老做法），此时配置必须是恒等 mean=0 / std=1，否则输入被再除一次 255。
    #
    #   踩过的坑（2026-09-15）：配置用 std=255 却送 float32[0,1]（①的配置 + ②的
    #   输入），输入被压缩 255 倍，后果极隐蔽：
    #     * 分类头 logits 被压塌：crazing 0.4021 -> 0.137，argmax 甚至跑到别的类
    #     * box 看起来"大致正常"——DFL 解码经 softmax，距离值被限制在 [0, reg_max]
    #       有界，对输入尺度不敏感，所以只看 box 会误判成"模型没问题"
    #     * RKNN 自带的 accuracy_analysis **发现不了**：它的 golden 与 simulator
    #       用的是同一份（错误的）预处理，两边一起错，cosine 依然 0.99999
    cfg = dict(
        target_platform=args.target,
        optimization_level=args.opt_level,
    )
    if args.host_norm:
        print("   (--host-norm：host 端已归一化，使用恒等 mean/std)")
        cfg["mean_values"] = [[0, 0, 0]]
        cfg["std_values"] = [[1, 1, 1]]
    else:
        print("   (默认：host 送 uint8[0,255]，RKNN 内部 /255)")
        cfg["mean_values"] = [[0, 0, 0]]
        cfg["std_values"] = [[255, 255, 255]]
    cfg["quant_img_RGB2BGR"] = True   # 仅影响量化校准图的读取顺序，不影响图结构
    if do_quant:
        cfg["quantized_dtype"] = "int8"
    rknn.config(**cfg)

    print("[2/4] rknn.load_onnx ...")
    ret = rknn.load_onnx(model=onnx_path, input_size_list=[[1, 3, args.imgsz, args.imgsz]])
    if ret != 0:
        raise SystemExit("❌ load_onnx 失败, ret=%s" % ret)

    if do_quant:
        print("[3/4] rknn.build (INT8 量化, 使用校准集) ...")
        ret = rknn.build(do_quantization=True, dataset=calib_txt)
    else:
        print("[3/4] rknn.build (FP16, 不量化) ...")
        ret = rknn.build(do_quantization=False)
    if ret != 0:
        raise SystemExit("❌ build 失败, ret=%s" % ret)

    print("[4/4] rknn.export_rknn -> %s" % args.dst)
    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
    ret = rknn.export_rknn(args.dst)
    if ret != 0:
        raise SystemExit("❌ export_rknn 失败, ret=%s" % ret)

    rknn.release()
    print("")
    print("✅ 转换完成: %s" % args.dst)
    print("   类别: %s" % (args.names if args.names else "(未指定)"))
    print("   输入尺寸: %d x %d" % (args.imgsz, args.imgsz))
    print("   下一步: 把 .rknn 拷到 RK3588 板子，用 board_infer.py 或 C++ demo 推理。")


if __name__ == "__main__":
    main()
