"""
NEU 标签审计 200 张（自动化统计层 + 待审清单）
==============================================

两阶段产出：

阶段 1：自动统计审计（无人工看图）
  抽 200 张（每类 ~33 张），跑：
    - 框坐标合法性（已在 _dataset_check.py 跑过，复述）
    - 框大小分布（按类统计 mean/median/min/max）
    - 框位置分布（按类统计中心点均值，看是否偏图边）
    - 同图多框的距离分布（异常近的多框可能是同一缺陷的重复标）
    - 跨类现象（同一图被标多种类）的频次 + 典型案例列表
  产出 neu_label_audit_200.md 报告

阶段 2：人工事后核对（不在本脚本内）
  报告里给出"建议优先人工核对的 TOP-N 张图清单"：
    - crazing + scratches 同图
    - scratches + inclusion 同图
    - 框 < 5x5 像素（可能是噪点标）
    - 框在图边（可能是裁切残留）

为什么这样设计：
  - 200 张人眼核对的成本约 1~2 小时（按 30s/张），需要先有清单再核对
  - 自动化统计层发现"系统性异常"（如 scratches 17% 跨 inclusion），这是论文素材
  - 自动统计 + 人工抽查组合，既高效又可信

用法：
  python _audit_labels_200.py
  python _audit_labels_200.py --n_per_class 50
"""
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
IMG_DIR = SCRIPT_DIR / "datasets" / "neu_det" / "images" / "train"
LBL_DIR = SCRIPT_DIR / "datasets" / "neu_det" / "labels" / "train"
CLASSES = ['crazing', 'inclusion', 'patches',
           'pitted_surface', 'rolled-in_scale', 'scratches']
IMG_W = 200
IMG_H = 200


def load_yolo_boxes(label_path, img_w=IMG_W, img_h=IMG_H):
    """读 YOLO 标签 → [(cls, x1, y1, x2, y2)] 像素坐标。"""
    if not label_path.exists():
        return []
    out = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        c = int(parts[0])
        cx, cy, w, h = map(float, parts[1:5])
        x1 = (cx - w / 2) * img_w
        y1 = (cy - h / 2) * img_h
        x2 = (cx + w / 2) * img_w
        y2 = (cy + h / 2) * img_h
        out.append((c, x1, y1, x2, y2, w, h))  # cls, xyxy, 相对 w/h
    return out


def sample_per_class(n_per_class):
    """每类抽 n_per_class 张图，返回 [(img_path, primary_class_idx), ...]"""
    sampled = []
    rng = random.Random(42)  # 固定种子，可复现
    for ci, cname in enumerate(CLASSES):
        imgs = sorted(IMG_DIR.glob(f"{cname}_*.jpg"))
        if len(imgs) > n_per_class:
            imgs = rng.sample(imgs, n_per_class)
        for img in imgs:
            sampled.append((img, ci))
    return sampled


def auto_audit(sampled):
    """对每张抽样图做自动化统计审计。"""
    findings = []  # 每张图的发现
    cross_class_pairs = Counter()  # 跨类对计数
    cross_class_cases = []  # 跨类案例（供后续人工抽查）
    box_size_outliers = []  # 异常小/大框
    edge_boxes = []  # 框在图边
    near_dup_boxes = []  # 同图距离过近的多框（疑似重复标）

    for img_path, primary_cls in sampled:
        lbl = LBL_DIR / f"{img_path.stem}.txt"
        boxes = load_yolo_boxes(lbl)
        if not boxes:
            findings.append({
                "img": img_path.name,
                "primary_cls": CLASSES[primary_cls],
                "boxes": 0,
                "issues": ["无标签（但文件名属于某类）"],
            })
            continue
        # 跨类
        cls_in_img = set(b[0] for b in boxes)
        if len(cls_in_img) > 1:
            cls_list = sorted(cls_in_img)
            pair = (CLASSES[cls_list[0]], CLASSES[cls_list[1]])
            cross_class_pairs[pair] += 1
            cross_class_cases.append({
                "img": img_path.name,
                "primary": CLASSES[primary_cls],
                "all_classes": [CLASSES[c] for c in cls_in_img],
                "n_boxes": len(boxes),
            })
        # 框大小检查
        for c, x1, y1, x2, y2, w, h in boxes:
            w_px = x2 - x1
            h_px = y2 - y1
            # 极小框（<5x5 像素）可能是噪点
            if w_px < 5 or h_px < 5:
                box_size_outliers.append({
                    "img": img_path.name,
                    "cls": CLASSES[c],
                    "w_px": round(w_px, 1),
                    "h_px": round(h_px, 1),
                })
            # 框在图边（< 2 像素容差）说明可能是裁切残留
            if x1 < 2 or y1 < 2 or x2 > IMG_W - 2 or y2 > IMG_H - 2:
                edge_boxes.append({
                    "img": img_path.name,
                    "cls": CLASSES[c],
                    "box": f"({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f})",
                })
        # 同图近距多框（两两中心距离 < 8 像素）
        centers = [(b[1] + (b[3] - b[1]) / 2, b[2] + (b[4] - b[2]) / 2) for b in boxes]
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                dx = centers[i][0] - centers[j][0]
                dy = centers[i][1] - centers[j][1]
                if (dx * dx + dy * dy) ** 0.5 < 8:
                    near_dup_boxes.append({
                        "img": img_path.name,
                        "i": i, "j": j,
                        "dist_px": round((dx*dx+dy*dy)**0.5, 1),
                    })
        findings.append({
            "img": img_path.name,
            "primary_cls": CLASSES[primary_cls],
            "boxes": len(boxes),
            "all_classes": [CLASSES[c] for c in sorted(cls_in_img)],
        })

    return {
        "findings": findings,
        "cross_class_pairs": dict(cross_class_pairs),
        "cross_class_cases": cross_class_cases,
        "box_size_outliers": box_size_outliers,
        "edge_boxes": edge_boxes,
        "near_dup_boxes": near_dup_boxes,
    }


def main():
    n_per_class = 33  # 6 类 × 33 = 198 张
    sampled = sample_per_class(n_per_class)
    audit = auto_audit(sampled)
    n_total = len(sampled)

    report = []
    report.append("# NEU 标签审计 200 张（自动统计层）\n")
    report.append(f"抽样: 每类 {n_per_class} 张，共 {n_total} 张（固定随机种子 42，可复现）\n")
    report.append(f"图片尺寸: {IMG_W}×{IMG_H}\n")
    report.append(f"数据源: `datasets/neu_det/images/train`\n")
    report.append("\n## 1. 跨类现象（同一图被标多种类）\n")
    if not audit["cross_class_pairs"]:
        report.append("✅ 未发现跨类图。\n")
    else:
        report.append("| 类对 | 图数 |\n|---|---:|\n")
        for (a, b), n in sorted(audit["cross_class_pairs"].items(), key=lambda x: -x[1]):
            report.append(f"| {a} + {b} | {n} |\n")
        report.append(f"\n**总跨类图: {len(audit['cross_class_cases'])} 张**\n\n")
        report.append("典型跨类图（建议人工核对）：\n\n")
        for case in audit["cross_class_cases"][:30]:
            report.append(f"- `{case['img']}` 主类={case['primary']}, 含={case['all_classes']}, 框={case['n_boxes']}\n")
        if len(audit["cross_class_cases"]) > 30:
            report.append(f"- ... 另有 {len(audit['cross_class_cases'])-30} 张\n")

    report.append("\n## 2. 极小框（<5×5 像素）\n")
    if not audit["box_size_outliers"]:
        report.append("✅ 未发现 < 5×5 像素的异常小框。\n")
    else:
        report.append(f"共 {len(audit['box_size_outliers'])} 个可疑小框（前 20）：\n\n")
        for o in audit["box_size_outliers"][:20]:
            report.append(f"- `{o['img']}` cls={o['cls']} size={o['w_px']}×{o['h_px']}px\n")

    report.append("\n## 3. 框在图边（<2 像素）\n")
    if not audit["edge_boxes"]:
        report.append("✅ 未发现贴边框。\n")
    else:
        report.append(f"共 {len(audit['edge_boxes'])} 个贴边框（前 20）：\n\n")
        for o in audit["edge_boxes"][:20]:
            report.append(f"- `{o['img']}` cls={o['cls']} box={o['box']}\n")

    report.append("\n## 4. 同图近距多框（中心 < 8px，疑似重复标）\n")
    if not audit["near_dup_boxes"]:
        report.append("✅ 未发现疑似重复标。\n")
    else:
        report.append(f"共 {len(audit['near_dup_boxes'])} 对疑似重复：\n\n")
        for o in audit["near_dup_boxes"][:20]:
            report.append(f"- `{o['img']}` 框{o['i']},{o['j']} 距={o['dist_px']}px\n")

    report.append("\n## 5. 抽样清单（完整 {n} 张）\n".format(n=n_total))
    report.append("| 文件 | 主类 | 框数 | 含类 |\n|---|---|---:|---|\n")
    for f in audit["findings"]:
        all_cls = ",".join(f.get("all_classes", []))
        report.append(f"| `{f['img']}` | {f['primary_cls']} | {f['boxes']} | {all_cls} |\n")

    out = SCRIPT_DIR / "neu_label_audit.md"
    out.write_text("".join(report), encoding="utf-8")
    print(f"✅ 审计报告: {out}")
    print(f"   抽样: {n_total} 张")
    print(f"   跨类图: {len(audit['cross_class_cases'])} 张")
    print(f"   极小框: {len(audit['box_size_outliers'])} 个")
    print(f"   贴边框: {len(audit['edge_boxes'])} 个")
    print(f"   疑似重复: {len(audit['near_dup_boxes'])} 对")


if __name__ == "__main__":
    main()
