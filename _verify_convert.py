# -*- coding: utf-8 -*-
"""验证板端 RKNN 模型与 PC 端 ONNX/ultralytics 是否一致。

用途：本次 6 类模型是在板子上用 torch 替身（stub）转换出来的，
      stub 会把 torch 的计算类 API 变成 no-op，因此必须用同一批
      真实图片比对两端输出，确认转换产物没有被带偏。

流程：
  1) 本脚本在 PC 上跑 ultralytics(best.pt) 得到基准结果 -> _verify_pc.json
  2) 板端用 board_infer.py 对同样图片推理 -> _verify_board.json
  3) 比对脚本读取两份 json 输出差异

用法：
    python _verify_convert.py            # PC 端推理 + 导出图片清单
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_ROOT = os.path.join(ROOT, "图片")
OUT_DIR = os.path.join(ROOT, "_verify_imgs")

NAMES6 = ["crazing", "inclusion", "patches", "pitted_surface",
          "rolled-in_scale", "scratches"]


def collect(samples_per_class=1):
    """每类挑若干张图，复制到英文路径目录，返回 [(本地路径, 英文名, 真值类别)]。"""
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)

    picked = []
    for cls in NAMES6:
        d = os.path.join(IMG_ROOT, cls)
        if not os.path.isdir(d):
            print("  [跳过] 目录不存在:", d)
            continue
        files = sorted(f for f in os.listdir(d)
                       if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")))
        for i, f in enumerate(files[:samples_per_class]):
            flat = "%s_%d%s" % (cls.replace("-", "_"), i, os.path.splitext(f)[1])
            dst = os.path.join(OUT_DIR, flat)
            shutil.copy2(os.path.join(d, f), dst)
            picked.append((dst, flat, cls))
    return picked


def main():
    picked = collect(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
    if not picked:
        raise SystemExit("没找到测试图片，请检查 图片/ 目录")

    print("选中 %d 张测试图：" % len(picked))
    for _, flat, cls in picked:
        print("   %-28s 真值=%s" % (flat, cls))
    print()

    # PC 端推理
    from ultralytics import YOLO
    model_path = os.path.join(ROOT, "模型训练", "runs", "neu_yolo11n_640",
                              "weights", "best.pt")
    print("PC 端模型:", model_path)
    model = YOLO(model_path)

    results = []
    for path, flat, truth in picked:
        r = model.predict(path, imgsz=640, conf=0.25, iou=0.45, verbose=False)[0]
        dets = []
        for b in r.boxes:
            dets.append({
                "cls": model.names[int(b.cls)],
                "conf": round(float(b.conf), 4),
                "box": [round(float(v), 1) for v in b.xyxy[0].tolist()],
            })
        results.append({"file": flat, "truth": truth, "n": len(dets), "dets": dets})
        print("  %-28s PC 检出 %2d 个: %s"
              % (flat, len(dets), ", ".join(d["cls"] for d in dets) or "(无)"))

    out = os.path.join(ROOT, "_verify_pc.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print()
    print("PC 基准结果已写入:", out)
    print("图片已复制到:", OUT_DIR, "（板子可通过 HTTP 拉取）")


if __name__ == "__main__":
    main()
