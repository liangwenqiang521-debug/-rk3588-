# -*- coding: utf-8 -*-
"""39 类数据集 · 划分清单生成（零破坏）
==========================================

为什么需要它
------------
现有 train/val 是多个来源数据集合并时**各自带的划分**，比例从未统一：
全库 val 框占比 20.4%，但逐类从 6.1%(warp) 到 33.4%(iron_sheet_ash)，差 5.5 倍。
39 类里有 16 类的 val 框 < 100（oxide_scale_plate 仅 18 个）。
在这些类上算出来的 F1/P/R 是**统计噪声**，拿去做「哪类弱、阈值调多少」的判断
等于在噪声上做决策。

本脚本**不改动** 缺陷检测扩展/images|labels 里的任何文件，只**新增清单**：

① calholdout（默认，立即可用）
     把现有 val 5296 张按类**分层随机**一分为二：
       splits/val_cal.txt       调阈值用（cal）
       splits/val_holdout.txt   报数用（holdout）
     产出 data_steel39_calholdout.yaml（val=cal / test=holdout）
     用途：per-class 阈值标定 —— 在 cal 上扫阈值选阈值，**只在 holdout 上报数**。
     局限：不解决「每类 val 框太少」，cal/holdout 各只有原来一半。
           要解决那个必须走 ②。

② stratified（全池分层重划分，可选）
     把 train+val 全池按类分层，重划成统一比例的新 train/val。
     产出 splits/train_strat.txt / val_strat.txt（并把新 val 再切 cal/holdout）
         + data_steel39_strat.yaml
     代价：必须**重训**才有效 —— 新 val 里含旧 train 的图，
           当前模型已经在上面训过，不能拿来评当前模型。

分层算法
--------
迭代分层（Sechidis 2011 多标签分层法的简化实现）：
  每轮挑「未满足目标 / 剩余实例」比值最大的类，从其未分配实例里随机取一张，
  计入第一组，直到所有类的目标数达成；剩下的整批归第二组。
多标签图按其「所在类集合」同时计入所有类；无标签的负样本按伪类 __bg__ 处理。
（注：目标是**每类框数**大致达标，不保证到个位。）

用法
----
  python _make_split.py                          # recon：只统计现状，不写文件
  python _make_split.py --mode calholdout --write
  python _make_split.py --mode stratified --write
  python _make_split.py --mode calholdout --write --seed 2026
"""
import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 幂等 sys.path 回退块（项目约定：脚本被直接执行 / 被 import 都能跑）
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXT_DIR = ROOT / "缺陷检测扩展"
SPLITS_DIR = SCRIPT_DIR / "splits"
IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp"}
BG = "__bg__"            # 无标签负样本的伪类
SEED = 20261012          # 固定随机种子（写进报告，保证可复现）

# ② stratified 模式的逐类 val 取用比例：
#   类越大越接近统一比例（保证类间可比），类越小越高（保证有足够框可统计）。
#   n<150  → 50%   （全库就几十个框的类，尽量都留给评估）
#   n<500  → 35%
#   其余   → ratio（默认 0.2）
RARE_T1, RARE_T2 = 150, 500


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def parse_names(yaml_path: Path):
    """从 data_steel39.yaml 取 names 列表（顺序 = 类别索引）"""
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
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


def load_split(split: str):
    """扫一个 split，返回 [(stem, img_path_posix, frozenset(classes), Counter(类->框数))]"""
    img_dir = EXT_DIR / "images" / split
    lbl_dir = EXT_DIR / "labels" / split
    if not img_dir.is_dir():
        raise SystemExit("目录不存在: %s" % img_dir)
    recs = []
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() not in IMG_EXT:
            continue
        boxes = Counter()
        lbl = lbl_dir / (p.stem + ".txt")
        if lbl.exists():
            for line in lbl.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    boxes[int(line.split()[0])] += 1
                except ValueError:
                    pass
        recs.append((p.stem, p.as_posix(), frozenset(boxes), boxes))
    return recs


# ---------------------------------------------------------------------------
# 迭代分层
# ---------------------------------------------------------------------------
def stratify(recs, ratio, seed, goal_fn=None):
    """按类分层把 recs 切成两组，返回 (第一组 stems, 第二组 stems)

    goal_fn(n) -> 第一组里该类应有约多少个**实例**（默认 n*ratio）
    """
    rng = random.Random(seed)
    key = {r[0]: (r[2] or frozenset([BG])) for r in recs}
    if goal_fn is None:
        goal_fn = lambda n: max(1, min(n, int(n * ratio + 0.5)))
    total = Counter()
    for labs in key.values():
        for x in labs:
            total[x] += 1
    goal = {x: goal_fn(n) for x, n in total.items()}

    # 每个类一张**打乱过的**候选列表 + 游标，避免反复全量扫描
    by_label = defaultdict(list)
    for s, labs in key.items():
        for x in labs:
            by_label[x].append(s)
    for x in by_label:
        rng.shuffle(by_label[x])
    ptr = Counter()

    rc = Counter(total)                 # 仍未被分配的、含该类 的实例数
    remaining = set(key)
    sel, cur = [], Counter()

    while remaining:
        best, bestv = None, -1.0
        for x, n in rc.items():
            if n <= 0:
                continue
            need = goal[x] - cur[x]
            if need <= 0:
                continue
            v = need / n                # 缺口比例最大者优先（小类优先被满足）
            if v > bestv:
                bestv, best = v, x
        if best is None:
            break                        # 所有类的目标都已达成

        lst = by_label[best]
        i = ptr[best]
        while i < len(lst) and lst[i] not in remaining:
            i += 1
        if i >= len(lst):                # 该类已无可用实例 → 目标收敛到现状
            goal[best] = cur[best]
            ptr[best] = i
            continue
        s = lst[i]
        ptr[best] = i + 1

        remaining.discard(s)
        sel.append(s)
        for x in key[s]:
            cur[x] += 1
            rc[x] -= 1

    return sel, sorted(remaining)


# ---------------------------------------------------------------------------
# 报表
# ---------------------------------------------------------------------------
def class_boxes(recs, stems: set, names):
    cb = Counter()
    for r in recs:
        if r[0] in stems:
            for k, v in r[3].items():
                cb[k] += v
    return cb


def print_table(title, recs, g1, g2, names):
    s1, s2 = set(g1), set(g2)
    b_all = class_boxes(recs, {r[0] for r in recs}, names)
    b1 = class_boxes(recs, s1, names)
    b2 = class_boxes(recs, s2, names)
    print("  %-4s %-26s %8s %8s %8s %7s" % ("idx", "key", "total", "G1", "G2", "G1%"))
    print("  " + "-" * 68)
    for i, n in enumerate(names):
        t, a, b = b_all.get(i, 0), b1.get(i, 0), b2.get(i, 0)
        pct = (100.0 * a / t) if t else 0.0
        print("  %-4d %-26s %8d %8d %8d %6.1f%%" % (i, n, t, a, b, pct))
    print("  " + "-" * 68)
    print("  %-4s %-26s %8d %8d %8d %6.1f%%" % (
        "", "合计", sum(b_all.values()), sum(b1.values()), sum(b2.values()),
        100.0 * sum(b1.values()) / max(1, sum(b_all.values()))))
    print("  图片数：G1=%d  G2=%d  合计=%d" % (len(s1), len(s2), len(s1) + len(s2)))


def stat_lines(recs, g1, g2, names, pad=""):
    """给 yaml 头部塞的逐类对照注释"""
    s1, s2 = set(g1), set(g2)
    b_all = class_boxes(recs, {r[0] for r in recs}, names)
    b1 = class_boxes(recs, s1, names)
    b2 = class_boxes(recs, s2, names)
    out = ["%s#  idx  key                        框数(G1)  框数(G2)   G1占比" % pad]
    for i, n in enumerate(names):
        t, a, b = b_all.get(i, 0), b1.get(i, 0), b2.get(i, 0)
        pct = (100.0 * a / t) if t else 0.0
        out.append("%s#  %3d  %-26s %8d %9d %7.1f%%" % (pad, i, n, a, b, pct))
    out.append("%s#  ---  合计                        %8d %9d %7.1f%%" % (
        pad, sum(b1.values()), sum(b2.values()),
        100.0 * sum(b1.values()) / max(1, sum(b_all.values()))))
    return out


def write_list(path: Path, stems, recs):
    path_map = {r[0]: r[1] for r in recs}
    lines = [path_map[s] for s in sorted(stems)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["recon", "calholdout", "stratified"],
                    default="recon")
    ap.add_argument("--ratio", type=float, default=0.2,
                    help="stratified 模式的大类 val 比例（默认 0.2）")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--write", action="store_true", help="真正写文件（否则只打印）")
    args = ap.parse_args()

    names = parse_names(SCRIPT_DIR / "data_steel39.yaml")
    print("=" * 72)
    print("类别数 %d   数据集根 %s" % (len(names), EXT_DIR))
    print("=" * 72)

    if args.mode == "recon":
        tr = load_split("train")
        va = load_split("val")
        print("\n[现状] 现有 train / val 逐类框数")
        print_table("现有划分", tr + va, {r[0] for r in tr}, {r[0] for r in va}, names)
        print("\ntrain 图 %d / val 图 %d" % (len(tr), len(va)))
        return

    if args.mode == "calholdout":
        va = load_split("val")
        print("\n[calholdout] 对现有 val %d 张做分层 50/50 随机切分，seed=%d"
              % (len(va), args.seed))
        cal, hold = stratify(va, 0.5, args.seed)
        print_table("val -> cal / holdout", va, cal, hold, names)
        if not args.write:
            print("\n(未加 --write，不写文件)")
            return
        SPLITS_DIR.mkdir(parents=True, exist_ok=True)
        n1 = write_list(SPLITS_DIR / "val_cal.txt", cal, va)
        n2 = write_list(SPLITS_DIR / "val_holdout.txt", hold, va)
        print("\n已写 splits/val_cal.txt (%d) / splits/val_holdout.txt (%d)" % (n1, n2))

        ext = str(EXT_DIR).replace("\\", "/")
        lines = [
            "# 39 类钢板表面缺陷 · cal/holdout 评测配置",
            "# 由 模型训练/_make_split.py --mode calholdout 生成，请勿手改",
            "# seed=%d   生成日期：2026-10-12" % args.seed,
            "#",
            "# 用途：per-class 阈值标定（**只用于评测，不要拿去训练**）",
            "#   val  = cal      → 在它上面扫阈值、挑阈值",
            "#   test = holdout  → 只用来报最终数字（一旦用它调过参就不再是 holdout）",
            "#",
            "# 注意：cal/holdout 各只有原 val 的一半，所以逐类框数少的类仍不可标定。",
            "#",
        ]
        lines += stat_lines(va, cal, hold, names)
        lines += [
            "",
            "path: %s" % ext,
            "train: %s/images/train" % ext,
            "val: %s/splits/val_cal.txt" % str(SCRIPT_DIR).replace("\\", "/"),
            "test: %s/splits/val_holdout.txt" % str(SCRIPT_DIR).replace("\\", "/"),
            "nc: %d" % len(names),
            "names:",
        ]
        for n in names:
            lines.append("  - %s" % n)
        lines.append("")
        out = SCRIPT_DIR / "data_steel39_calholdout.yaml"
        out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        print("已写 %s" % out)
        return

    # ---- stratified ----
    tr = load_split("train")
    va = load_split("val")
    pool = tr + va
    print("\n[stratified] 全池 %d 张（train %d + val %d）按类分层重划，seed=%d"
          % (len(pool), len(tr), len(va), args.seed))

    def goal_fn(n):
        if n < RARE_T1:
            r = 0.50
        elif n < RARE_T2:
            r = 0.35
        else:
            r = args.ratio
        return max(1, min(n, int(n * r + 0.5)))

    new_val, new_train = stratify(pool, args.ratio, args.seed, goal_fn=goal_fn)
    print("\n[新 train / val]")
    print_table("全池 -> train / val", pool, new_train, new_val, names)
    nv_cal, nv_hold = stratify([r for r in pool if r[0] in set(new_val)],
                               0.5, args.seed)
    print("\n[新 val 再切 cal / holdout]")
    print_table("新 val -> cal / holdout", pool, nv_cal, nv_hold, names)

    if not args.write:
        print("\n(未加 --write，不写文件)")
        return
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    write_list(SPLITS_DIR / "train_strat.txt", new_train, pool)
    write_list(SPLITS_DIR / "val_strat.txt", new_val, pool)
    write_list(SPLITS_DIR / "val_strat_cal.txt", nv_cal, pool)
    write_list(SPLITS_DIR / "val_strat_holdout.txt", nv_hold, pool)
    print("\n已写 splits/{train_strat,val_strat,val_strat_cal,val_strat_holdout}.txt")

    sd = str(SCRIPT_DIR).replace("\\", "/")
    ext = str(EXT_DIR).replace("\\", "/")
    lines = [
        "# 39 类钢板表面缺陷 · 全池分层重划分（stratified）",
        "# 由 模型训练/_make_split.py --mode stratified 生成，请勿手改",
        "# seed=%d   生成日期：2026-10-12" % args.seed,
        "#",
        "# 与 data_steel39.yaml 的区别：train/val 不再用目录，而是用清单文件；",
        "#   划分按类分层、比例统一（小类 50%% / 中类 35%% / 大类 %d%%）。" % int(args.ratio * 100),
        "#",
        "# ★ 本划分**必须重训**才有效：新 val 含旧 train 的图，",
        "#   当前已训模型在上面是「见过」的，不能用它评当前模型。",
        "#",
        "# 阈值标定仍走 cal/holdout：val=val_strat_cal.txt / test=val_strat_holdout.txt",
        "#",
    ]
    lines += stat_lines(pool, new_val, new_train, names)
    lines += [
        "",
        "path: %s" % ext,
        "train: %s/splits/train_strat.txt" % sd,
        "val: %s/splits/val_strat.txt" % sd,
        "test: %s/splits/val_strat_holdout.txt" % sd,
        "nc: %d" % len(names),
        "names:",
    ]
    for n in names:
        lines.append("  - %s" % n)
    lines.append("")
    out = SCRIPT_DIR / "data_steel39_strat.yaml"
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("已写 %s" % out)


if __name__ == "__main__":
    main()
