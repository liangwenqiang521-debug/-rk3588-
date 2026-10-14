# -*- coding: utf-8 -*-
"""39 类 per-class 置信度阈值标定（cal 扫阈值 / holdout 报数）
==============================================================

为什么需要它
------------
统一 conf=0.20 会在不同类上犯**方向相反**的错误：
  - `break`      P 0.995 / R 0.577  → 模型很自信，**降阈值直接换回召回**
  - `inclusion`  FP 全库第一         → 假框挤在低分段，**必须升阈值才清得掉**
错误构成里 FP + FN 占约 96%，类间混淆只有约 4% —— 阈值是唯一能直接压这 96%、
又**零训练成本**的手段（不动模型、不重训，纯后处理）。

方法
----
1. 只跑**一次**推理：conf 取极低（--conf-floor，默认 0.01），拿到全部候选框。
   因为 ultralytics 的 NMS 是按分数降序贪心的、且默认 class-aware
   （`non_max_suppression(agnostic=False)`），
   「低 conf 跑一次 NMS 再按阈值过滤」与「按该阈值跑 NMS」**结果等价**，
   所以后续所有阈值扫描都是纯 numpy，不重复推理。

2. 指标口径**完全对齐** `_eval_unified.py`（它产出了基线 `_eval_steel39.json`）：
     - NMS IoU 0.45 ；匹配 IoU 0.50
     - 匹配**与类别无关**（只看 IoU >= 0.5）
     - 默认（非 --strict）：TP 记在**真值类**上 —— 与基线 JSON 完全可比。
       代价是 `fp = 该类预测数 - 该类 TP` 可能为负、precision 可能 > 1：
       当某类的真值被**别的类**的框命中时，真值类的 TP 涨了、但预测数没涨。
       这正是基线 `_eval_steel39.json` 里 `striated_scale` 出现 fp=-2 / P=1.105
       的原因 —— 不是随机 bug，而是「TP 按真值类记、precision 分母按预测类数」
       这个口径本身的内部不一致。
     - `--strict`：只有 `预测类 == 真值类` 才记 TP（标准 per-class 口径），
       此时 fp/fn 恒 >= 0、P <= 1。论文口径建议用这个；
       与基线对照时用默认口径。

3. cal 上逐类**坐标下降**扫阈值（默认 0.05..0.95 步长 0.05），准则 = 该类 F1 最大。
   只有 cal 真值框数 >= --min-gt 的类参与标定；其余保持 --base-conf 不变。

4. holdout **只报数**：输出「统一阈值 vs 标定阈值」的对照，不参与选阈值。

用法
----
  # 冒烟测试（60 张、CPU，不与训练抢 GPU）
  python _calib_thres39.py --limit 60 --device cpu

  # 正式（训练结束后直接换权重）
  python _calib_thres39.py
  python _calib_thres39.py --model runs/xxx/weights/best.pt --min-gt 120

产出（均为新增文件，不改模型/数据）
  _calib_thres39.json   阈值表 + cal/holdout 指标 + 敏感性曲线（给论文）
  _calib_thres39.md     可读报告
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# 幂等 sys.path 回退块（项目约定：脚本被直接执行 / 被 import 都能跑）
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 与 _eval_unified.py 对齐的两个 IoU（改这里就要同步改那边，否则口径不可比）
NMS_IOU = 0.45
MATCH_IOU = 0.50

DEFAULT_CAL = SCRIPT_DIR / "splits" / "val_cal.txt"
DEFAULT_HOLD = SCRIPT_DIR / "splits" / "val_holdout.txt"
DEFAULT_NAMES = SCRIPT_DIR / "data_steel39.yaml"
DEFAULT_MODEL = SCRIPT_DIR / "runs" / "steel39_yolo11n_640_e100" / "weights" / "best.pt"


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def parse_names(yaml_path):
    """从 data_steel39.yaml 取 names 列表（顺序 = 类别索引）。

    刻意**不**在脚本里硬编码 39 个类名 —— 项目硬约定是「4 处定义必须同步」，
    这里直接读权威源，少一处需要同步的地方。
    """
    lines = Path(yaml_path).read_text(encoding="utf-8").splitlines()
    i = next((k for k, l in enumerate(lines) if l.strip().startswith("names:")), None)
    if i is None:
        raise SystemExit("找不到 names: %s" % yaml_path)
    out = []
    for l in lines[i + 1:]:
        s = l.strip()
        if s.startswith("- "):
            out.append(s[2:].strip())
        elif s and not s.startswith("#"):
            break
    return out


def iou_xyxy(a, b):
    """a:(N,4) b:(M,4) -> (N,M) IoU。镜像自 _eval_unified.py（保持口径一致）"""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    ax1, ay1, ax2, ay2 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    bx1, by1, bx2, by2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    ix1 = np.maximum(ax1[:, None], bx1[None, :])
    iy1 = np.maximum(ay1[:, None], by1[None, :])
    ix2 = np.minimum(ax2[:, None], bx2[None, :])
    iy2 = np.minimum(ay2[:, None], by2[None, :])
    iw = np.clip(ix2 - ix1, 0, None)
    ih = np.clip(iy2 - iy1, 0, None)
    inter = iw * ih
    union = area_a[:, None] + area_b[None, :] - inter
    return inter / np.clip(union, 1e-9, None)


def label_path_for(img_path):
    """图片路径 -> 标签路径（把最后一个 'images' 段换成 'labels'）。

    清单里存的是绝对 POSIX 路径，形如
      D:/.../缺陷检测扩展/images/val/gc_img_01_425000300_00520.jpg
    标签固定为
      D:/.../缺陷检测扩展/labels/val/gc_img_01_425000300_00520.txt
    无标签的负样本（neg_*.jpg）属于正常情况（GT 为空）。
    """
    p = Path(img_path)
    parts = list(p.parts)
    idx = [i for i, s in enumerate(parts) if s.lower() == "images"]
    if not idx:
        return None
    parts[idx[-1]] = "labels"
    return Path(*parts).with_suffix(".txt")


def load_gt(img_path, w, h):
    """读 YOLO 标签 -> xyxy(像素) + cls。缺失/空文件 = 负样本，返回空数组。"""
    lp = label_path_for(img_path)
    if lp is None or not lp.exists():
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.int32)
    boxes, clses = [], []
    for line in lp.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            c = int(parts[0])
            cx, cy, bw, bh = map(float, parts[1:5])
        except ValueError:
            continue
        boxes.append([(cx - bw / 2) * w, (cy - bh / 2) * h,
                      (cx + bw / 2) * w, (cy + bh / 2) * h])
        clses.append(c)
    return (np.asarray(boxes, dtype=np.float32) if boxes else np.zeros((0, 4), dtype=np.float32),
            np.asarray(clses, dtype=np.int32) if clses else np.zeros((0,), dtype=np.int32))


def build_rec(gt_b, gt_c, pr_b, pr_c, pr_f):
    """单张图预计算：把「只依赖框、不依赖分数」的部分全部前置。

    关键收益：匹配用的 IoU 降序序列只跟框有关，与阈值无关 → 扫阈值时不必重算 IoU。
    """
    n_gt, n_pr = len(gt_b), len(pr_b)
    if n_gt and n_pr:
        ious = iou_xyxy(gt_b, pr_b).reshape(-1)
        order = np.argsort(-ious)
        order = order[ious[order] >= MATCH_IOU]      # 低 IoU 对直接丢弃（等价于原脚本的 break）
        o_i = (order // n_pr).tolist()
        o_j = (order % n_pr).tolist()
    else:
        o_i, o_j = [], []
    return {
        "gt_cls": gt_c,
        "n_gt": n_gt,
        "pred_cls": pr_c,
        "pred_conf": pr_f,
        "o_i": o_i,
        "o_j": o_j,
        "n_pair": len(o_i),
    }


# ---------------------------------------------------------------------------
# 推理：每个 split 只跑一次
# ---------------------------------------------------------------------------
def collect(model, manifest, imgsz, conf_floor, device, limit, tag):
    paths = [l.strip() for l in Path(manifest).read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        paths = paths[:limit]
    total = len(paths)
    print("[%s] 清单 %d 张，conf_floor=%.3f，开始推理..." % (tag, total, conf_floor))
    recs, skipped = [], []
    t0 = time.time()
    for i, p in enumerate(paths, 1):
        try:
            r = model.predict(p, imgsz=imgsz, conf=conf_floor, iou=NMS_IOU,
                              max_det=1000, verbose=False, device=device)
        except Exception as e:                                # noqa: BLE001
            skipped.append((p, "%s: %s" % (type(e).__name__, e)))
            continue
        if not r:
            skipped.append((p, "no result"))
            continue
        res = r[0]
        h, w = res.orig_shape                              # 直接从结果拿原图尺寸，省一次读图
        gt_b, gt_c = load_gt(p, w, h)
        b = res.boxes
        if b is None or len(b) == 0:
            pr_b = np.zeros((0, 4), dtype=np.float32)
            pr_c = np.zeros((0,), dtype=np.int32)
            pr_f = np.zeros((0,), dtype=np.float32)
        else:
            pr_b = b.xyxy.cpu().numpy().astype(np.float32)
            pr_c = b.cls.cpu().numpy().astype(np.int32)
            pr_f = b.conf.cpu().numpy().astype(np.float32)
        recs.append(build_rec(gt_b, gt_c, pr_b, pr_c, pr_f))
        if i % 200 == 0 or i == total:
            el = time.time() - t0
            eta = el / i * (total - i)
            print("  [%s %d/%d] 已用 %.0fs  ETA %.0fs" % (tag, i, total, el, eta))
    print("[%s] 完成 %d 张（跳过 %d），用时 %.0fs" % (tag, len(recs), len(skipped), time.time() - t0))
    for p, why in skipped[:5]:
        print("   跳过: %s (%s)" % (Path(p).name, why))
    return recs


# ---------------------------------------------------------------------------
# 评估（口径 = _eval_unified.py）
# ---------------------------------------------------------------------------
def evaluate(recs, n_cls, thres_vec, strict=False):
    gt_c = np.zeros(n_cls, dtype=np.int64)
    pred_c = np.zeros(n_cls, dtype=np.int64)
    tp_c = np.zeros(n_cls, dtype=np.int64)          # 默认按真值类记 TP（对齐原脚本）
    cm = np.zeros((n_cls, n_cls), dtype=np.int64)   # 行=真值类, 列=预测类
    tot_tp = tot_fp = tot_fn = 0

    for r in recs:
        gcls, n_gt = r["gt_cls"], r["n_gt"]
        pcls, pconf = r["pred_cls"], r["pred_conf"]
        if n_gt:
            gt_c += np.bincount(gcls, minlength=n_cls)
        if len(pcls):
            keep = pconf >= thres_vec[pcls]
            pred_c += np.bincount(pcls[keep], minlength=n_cls)
            kept = set(np.nonzero(keep)[0].tolist())
        else:
            kept = set()

        mg, mp = set(), set()
        n_same = 0
        for k in range(r["n_pair"]):
            i = r["o_i"][k]
            if i in mg:
                continue
            j = r["o_j"][k]
            if j in kept and j not in mp:
                mg.add(i)
                mp.add(j)
                same = (pcls[j] == gcls[i])
                cm[gcls[i], pcls[j]] += 1
                if same:
                    n_same += 1
                if (not strict) or same:
                    tp_c[gcls[i]] += 1

        matched = n_same if strict else len(mg)
        tot_tp += matched
        tot_fn += n_gt - matched
        tot_fp += len(kept) - matched

    with np.errstate(divide="ignore", invalid="ignore"):
        recall = np.where(gt_c > 0, tp_c / np.maximum(gt_c, 1), 0.0)
        prec = np.where(pred_c > 0, tp_c / np.maximum(pred_c, 1), 0.0)
        denom = recall + prec
        f1 = np.where(denom > 0, 2 * recall * prec / np.maximum(denom, 1e-12), 0.0)
    fn_c = gt_c - tp_c
    fp_c = pred_c - tp_c

    micro = {
        "tp": int(tot_tp), "fp": int(tot_fp), "fn": int(tot_fn),
        "precision": float(tot_tp / max(1, tot_tp + tot_fp)),
        "recall": float(tot_tp / max(1, tot_tp + tot_fn)),
    }
    micro["f1"] = float(2 * micro["precision"] * micro["recall"]
                        / max(1e-12, micro["precision"] + micro["recall"]))
    return {
        "gt": gt_c, "pred": pred_c, "tp": tp_c, "fn": fn_c, "fp": fp_c,
        "recall": recall, "precision": prec, "f1": f1,
        "cm": cm, "micro": micro,
        "sum_fp": int(fp_c.sum()), "sum_fn": int(fn_c.sum()),
    }


# ---------------------------------------------------------------------------
# 坐标下降标定
# ---------------------------------------------------------------------------
def calibrate(recs, n_cls, gt_cal, grid, base_conf, calib_ids, rounds, names,
              strict=False, verbose=True):
    thres = np.full(n_cls, base_conf, dtype=np.float64)
    curves = {}
    for rd in range(1, rounds + 1):
        changed = 0
        for c in calib_ids:
            best_t, best_f = thres[c], -1.0
            curve = []
            for t in grid:
                old = thres[c]
                thres[c] = t
                m = evaluate(recs, n_cls, thres, strict)
                thres[c] = old
                curve.append([float(t), float(m["f1"][c]),
                              float(m["precision"][c]), float(m["recall"][c])])
                if m["f1"][c] > best_f + 1e-9:
                    best_f, best_t = float(m["f1"][c]), float(t)
            if abs(best_t - thres[c]) > 1e-9:
                changed += 1
            thres[c] = best_t
            curves[c] = curve
            if verbose:
                print("    轮%d  %-26s -> %.2f  (cal F1 %.3f, cal GT %d)"
                      % (rd, names[c], best_t, best_f, gt_cal[c]))
        if verbose:
            print("  [坐标下降] 第 %d 轮收敛，%d 个类阈值有变动" % (rd, changed))
        if changed == 0:
            break
    return thres, curves


# ---------------------------------------------------------------------------
# 报表
# ---------------------------------------------------------------------------
def md_table(names, thres, cal_m, base_m, calib_ids, base_conf):
    out = ["| idx | 类 | cal GT | F1@%.2f | 标定阈值 | cal F1 | 变化 |" % base_conf,
           "| ---: | :--- | ---: | ---: | ---: | ---: | ---: |"]
    for c, n in enumerate(names):
        if c in calib_ids:
            d = cal_m["f1"][c] - base_m["f1"][c]
            out.append("| %d | %s | %d | %.3f | **%.2f** | %.3f | %+.3f |"
                       % (c, n, cal_m["gt"][c], base_m["f1"][c], thres[c], cal_m["f1"][c], d))
        else:
            out.append("| %d | %s | %d | %.3f | %.2f (未标定) | %.3f | - |"
                       % (c, n, cal_m["gt"][c], base_m["f1"][c], base_conf, cal_m["f1"][c]))
    return out


def md_compare(names, before, after, topn=18):
    out = ["| 类 | GT | FP 前 | FP 后 | FN 前 | FN 后 | F1 前 | F1 后 | 变化 |",
           "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    order = np.argsort(-before["fp"])
    for c in order[:topn]:
        d = after["f1"][c] - before["f1"][c]
        out.append("| %s | %d | %d | %d | %d | %d | %.3f | %.3f | %+.3f |"
                   % (names[c], before["gt"][c], before["fp"][c], after["fp"][c],
                      before["fn"][c], after["fn"][c],
                      before["f1"][c], after["f1"][c], d))
    return out


def dump_metrics(m, names):
    return {
        "micro": m["micro"],
        "sum_fp": m["sum_fp"],
        "sum_fn": m["sum_fn"],
        "per_class": {
            names[c]: {
                "gt": int(m["gt"][c]), "tp": int(m["tp"][c]),
                "fn": int(m["fn"][c]), "fp": int(m["fp"][c]),
                "recall": float(m["recall"][c]),
                "precision": float(m["precision"][c]),
                "f1": float(m["f1"][c]),
            }
            for c in range(len(names))
        },
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(errors="replace")     # 控制台 GBK 时避免 UnicodeEncodeError
    except Exception:                                # noqa: BLE001
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(DEFAULT_MODEL), help="权重 .pt")
    ap.add_argument("--cal", default=str(DEFAULT_CAL), help="cal 图片清单（扫阈值用）")
    ap.add_argument("--holdout", default=str(DEFAULT_HOLD), help="holdout 图片清单（报数用）")
    ap.add_argument("--names-yaml", default=str(DEFAULT_NAMES), help="取 names 的 yaml（权威源）")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--base-conf", type=float, default=0.20, help="现有统一阈值")
    ap.add_argument("--conf-floor", type=float, default=0.01, help="首次推理的最低 conf（必须 < 网格最小值）")
    ap.add_argument("--grid-lo", type=float, default=0.05)
    ap.add_argument("--grid-hi", type=float, default=0.95)
    ap.add_argument("--grid-step", type=float, default=0.05)
    ap.add_argument("--min-gt", type=int, default=120, help="cal 真值框数达到该值才参与标定")
    ap.add_argument("--rounds", type=int, default=3, help="坐标下降轮数上限")
    ap.add_argument("--limit", type=int, default=0, help="只用清单前 N 张（冒烟测试）")
    ap.add_argument("--strict", action="store_true",
                    help="TP 只在 预测类==真值类 时记（标准 per-class 口径）；"
                         "默认关 = 与基线 _eval_steel39.json 可比")
    ap.add_argument("--device", default=None)
    ap.add_argument("--json", default=str(SCRIPT_DIR / "_calib_thres39.json"))
    ap.add_argument("--md", default=str(SCRIPT_DIR / "_calib_thres39.md"))
    args = ap.parse_args()

    import torch
    from ultralytics import YOLO

    device = args.device or ("0" if torch.cuda.is_available() else "cpu")
    names = parse_names(args.names_yaml)
    n_cls = len(names)
    grid = np.round(np.arange(args.grid_lo, args.grid_hi + 1e-9, args.grid_step), 2)

    print("=" * 78)
    print("39 类 per-class 阈值标定")
    print("  模型      : %s" % args.model)
    print("  类别数    : %d（来自 %s）" % (n_cls, Path(args.names_yaml).name))
    print("  设备      : %s" % device)
    print("  cal       : %s" % Path(args.cal).name)
    print("  holdout   : %s" % Path(args.holdout).name)
    print("  基准阈值  : %.2f   扫描网格: %.2f..%.2f 步长 %.2f（%d 点）"
          % (args.base_conf, grid[0], grid[-1], args.grid_step, len(grid)))
    print("=" * 78)

    if not Path(args.model).exists():
        raise SystemExit("权重不存在: %s" % args.model)

    model = YOLO(args.model)

    # ---- 1. 两侧各推理一次 ----
    cal_recs = collect(model, args.cal, args.imgsz, args.conf_floor, device, args.limit, "cal")
    hold_recs = collect(model, args.holdout, args.imgsz, args.conf_floor, device, args.limit, "holdout")
    if not cal_recs:
        raise SystemExit("cal 集合为空，无法标定")

    # ---- 2. 基准（统一阈值）----
    base_vec = np.full(n_cls, args.base_conf, dtype=np.float64)
    cal_base = evaluate(cal_recs, n_cls, base_vec, args.strict)
    hold_base = evaluate(hold_recs, n_cls, base_vec, args.strict) if hold_recs else None

    calib_ids = [c for c in range(n_cls) if cal_base["gt"][c] >= args.min_gt]
    not_calib = [c for c in range(n_cls) if c not in calib_ids]
    tot_fp = int(cal_base["fp"].sum())
    cov = 100.0 * float(cal_base["fp"][calib_ids].sum()) / max(1, tot_fp)
    print("\n参与标定的类 %d/%d（cal GT >= %d）；这些类覆盖 cal 误报的 %.1f%%"
          % (len(calib_ids), n_cls, args.min_gt, cov))
    print("未标定（样本不足，保持 %.2f）：%s"
          % (args.base_conf, ", ".join(names[c] for c in not_calib)))

    # ---- 3. 坐标下降 ----
    print("\n[cal 坐标下降扫阈值]")
    thres, curves = calibrate(cal_recs, n_cls, cal_base["gt"], grid,
                              args.base_conf, calib_ids, args.rounds, names, args.strict)
    cal_tuned = evaluate(cal_recs, n_cls, thres, args.strict)

    # ---- 4. holdout 报数 ----
    hold_tuned = evaluate(hold_recs, n_cls, thres, args.strict) if hold_recs else None

    def line(tag, m):
        if m is None:
            return
        u = m["micro"]
        print("  %-10s TP %6d  FP %6d  FN %6d | P %.4f  R %.4f  F1 %.4f"
              % (tag, u["tp"], u["fp"], u["fn"], u["precision"], u["recall"], u["f1"]))

    print("\n" + "=" * 78)
    print("[整体指标（micro）]")
    line("cal 基准", cal_base)
    line("cal 标定", cal_tuned)
    line("hold 基准", hold_base)
    line("hold 标定", hold_tuned)
    if hold_base and hold_tuned:
        print("\n  holdout 变化: FP %+d   FN %+d   F1 %+.4f"
              % (hold_tuned["micro"]["fp"] - hold_base["micro"]["fp"],
                 hold_tuned["micro"]["fn"] - hold_base["micro"]["fn"],
                 hold_tuned["micro"]["f1"] - hold_base["micro"]["f1"]))

    print("\n[逐类结果（cal GT 降序）]")
    print("  %-26s %6s %8s %8s %8s %8s" % ("类", "calGT", "基准F1", "标定阈值", "calF1", "holdF1"))
    print("  " + "-" * 74)
    for c in sorted(range(n_cls), key=lambda x: -cal_base["gt"][x]):
        hf = "%.3f" % hold_tuned["f1"][c] if hold_tuned else "  -  "
        mark = "" if c in calib_ids else "  (未标定)"
        print("  %-26s %6d %8.3f %8.2f %8.3f %8s%s"
              % (names[c], cal_base["gt"][c], cal_base["f1"][c], thres[c],
                 cal_tuned["f1"][c], hf, mark))

    # ---- 5. 落盘 ----
    out = {
        "model": args.model,
        "names_yaml": args.names_yaml,
        "cal_manifest": args.cal,
        "holdout_manifest": args.holdout,
        "imgsz": args.imgsz,
        "base_conf": args.base_conf,
        "conf_floor": args.conf_floor,
        "nms_iou": NMS_IOU,
        "match_iou": MATCH_IOU,
        "min_gt": args.min_gt,
        "strict_tp": bool(args.strict),
        "grid": grid.tolist(),
        "cal_images": len(cal_recs),
        "holdout_images": len(hold_recs),
        "calibrated_classes": [names[c] for c in calib_ids],
        "non_calibrated_classes": [names[c] for c in not_calib],
        "thresholds": {names[c]: float(thres[c]) for c in range(n_cls)},
        "thresholds_tuned_only": {names[c]: float(thres[c]) for c in calib_ids},
        "cal_base": dump_metrics(cal_base, names),
        "cal_tuned": dump_metrics(cal_tuned, names),
        "holdout_base": dump_metrics(hold_base, names) if hold_base else None,
        "holdout_tuned": dump_metrics(hold_tuned, names) if hold_tuned else None,
        "curves": {names[c]: curves[c] for c in curves},
    }
    Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n结果已写到: %s" % args.json)

    # ---- markdown ----
    md = []
    md.append("# 39 类 per-class 阈值标定报告")
    md.append("")
    md.append("- 模型：`%s`" % Path(args.model).as_posix())
    md.append("- cal：`%s`（%d 张）  holdout：`%s`（%d 张）"
              % (Path(args.cal).name, len(cal_recs), Path(args.holdout).name, len(hold_recs)))
    md.append("- 基准阈值 %.2f ；扫描网格 %s" % (args.base_conf, list(grid)))
    md.append("- NMS IoU %.2f ；匹配 IoU %.2f ；TP 记法：%s"
              % (NMS_IOU, MATCH_IOU,
                 "严格（预测类==真值类）" if args.strict
                 else "按真值类（与 _eval_steel39.json 可比）"))
    md.append("- 参与标定：cal GT >= %d 的 %d 个类（覆盖 cal 误报 %.1f%%）；其余保持 %.2f"
              % (args.min_gt, len(calib_ids), cov, args.base_conf))
    md.append("")
    md.append("## 一、整体指标（holdout 为准）")
    md.append("")
    if hold_base and hold_tuned:
        md.append("| 口径 | TP | FP | FN | P | R | F1 |")
        md.append("| :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for tag, m in (("holdout 基准", hold_base), ("holdout 标定", hold_tuned)):
            u = m["micro"]
            md.append("| %s | %d | %d | %d | %.4f | %.4f | %.4f |"
                      % (tag, u["tp"], u["fp"], u["fn"], u["precision"], u["recall"], u["f1"]))
        md.append("")
        md.append("**holdout 变化：FP %+d ，FN %+d ，F1 %+.4f**"
                  % (hold_tuned["micro"]["fp"] - hold_base["micro"]["fp"],
                     hold_tuned["micro"]["fn"] - hold_base["micro"]["fn"],
                     hold_tuned["micro"]["f1"] - hold_base["micro"]["f1"]))
    md.append("")
    md.append("## 二、阈值表（在 cal 上选出）")
    md.append("")
    md += md_table(names, thres, cal_tuned, cal_base, set(calib_ids), args.base_conf)
    md.append("")
    md.append("## 三、holdout 逐类对照（按基准 FP 降序，前 18 类）")
    md.append("")
    if hold_base and hold_tuned:
        md += md_compare(names, hold_base, hold_tuned)
    md.append("")
    md.append("## 四、落地")
    md.append("")
    md.append("板端 `board_server_cascade.py` 的 `PER_CLASS_THRES`（只放标定过的类）：")
    md.append("")
    md.append("```python")
    md.append("PER_CLASS_THRES = " + json.dumps(
        {names[c]: round(float(thres[c]), 2) for c in calib_ids}, ensure_ascii=False))
    md.append("```")
    md.append("")
    md.append("未标定的类**不要**写进板端字典 —— 样本不足的类扫出来的阈值是拟合噪声，上产线会失效。")
    md.append("")
    Path(args.md).write_text("\n".join(md), encoding="utf-8")
    print("报告已写到: %s" % args.md)


if __name__ == "__main__":
    main()
