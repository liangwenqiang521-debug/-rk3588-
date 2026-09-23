# -*- coding: utf-8 -*-
"""诊断：板端检测结果为什么画不出框。

复现路径：构造一个与板端返回结构完全一致的 result 对象 →
喂给 DetectPage._on_edge_result → 检查画布 defects / result 角标 / 统计。

用法:
    python _diag_noframe.py
"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os
import sys
import json
import base64

try:
    import infer  # noqa: F401
    import torch
    torch.zeros(1)
except Exception as e:
    print("[warn] 预加载失败:", e)

from PyQt5.QtWidgets import QApplication

import main as m


def make_edge_result(w=640, h=640, defects=None, ok=False):
    """模拟 board_server_cascade 下发的 result 帧结构。"""
    return {
        "type": "result",
        "ok": ok,
        "w": w, "h": h,
        "infer_ms": 83.0,
        "defects": defects or [],
    }


def main():
    app = QApplication(sys.argv)
    win = m.MainWindow()
    win.resize(1600, 950)
    win.show()
    app.processEvents()

    page = win.pages[0]
    canvas = page.canvas

    print("=" * 60)
    print("画布 ROI 默认值:", canvas.rois)
    print("=" * 60)

    # 打开自动检测（否则 _on_edge_result 会在 _edge_detect_enabled 处直接 return）
    page._edge_detect_enabled = True

    # 构造板端典型返回：两个缺陷，坐标落在画面中部（模拟真实缺陷位置）
    # 板端 NAMES 顺序: crazing inclusion patches pitted_surface rolled-in_scale scratches
    defects = [
        {"x1": 300, "y1": 300, "x2": 360, "y2": 420, "cls": "inclusion", "conf": 0.72},
        {"x1": 420, "y1": 250, "x2": 480, "y2": 330, "cls": "crazing",   "conf": 0.55},
    ]
    obj = make_edge_result(640, 640, defects, ok=False)

    print("\n--- 喂入板端结果 ---")
    print("defects:", json.dumps(defects, ensure_ascii=False))

    # 直接调渲染（绕过 bridge 信号，聚焦渲染链路）
    page._on_edge_result(obj)
    app.processEvents()

    print("\n--- 渲染后状态 ---")
    rd = getattr(canvas, "_real_defects", None)
    print("canvas._real_defects 条数:", len(rd) if rd else 0)
    if rd:
        for d in rd:
            print("   ", d.get("name"), "conf=%.2f" % d.get("conf", 0),
                  "xyxy=", [round(v, 3) for v in d.get("xyxy", [])])
    else:
        print("   （空 → 画不出任何框）")

    print("canvas.result:", getattr(canvas, "result", None))
    print("canvas.confidence:", getattr(canvas, "confidence", None))
    print("右侧 big_result:", page.big_result.text())
    print("统计: total=%s ok=%s ng=%s" % (page.total, page.ok, page.ng))

    # 逐帧验证 ROI 过滤到底吃了多少
    print("\n--- ROI 过滤逐框判定 ---")
    for d in page._dframe_to_defects(obj) if hasattr(page, "_dframe_to_defects") else []:
        pass
    for d in defects:
        x1, y1, x2, y2 = d["x1"] / 640.0, d["y1"] / 640.0, d["x2"] / 640.0, d["y2"] / 640.0
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        inside = page._defect_in_roi({"xyxy": [x1, y1, x2, y2]}, canvas.rois)
        print("  %-14s 中心(%.2f, %.2f) → ROI内=%s" % (d["cls"], cx, cy, inside))

    print("=" * 60)


if __name__ == "__main__":
    main()
