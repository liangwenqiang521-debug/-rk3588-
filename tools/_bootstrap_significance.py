# -*- coding: utf-8 -*-
"""对两次板端同集评估做配对 bootstrap，给出 ΔF1 的置信区间与显著性。

同一批图、同 seed，逐图配对重采样（10000 次），统计 ΔF1 分布。
用途：判断 +1.3pp 是真实提升还是 300 张样本的统计噪声。

用法:
  python tools/_bootstrap_significance.py --a _board_eval_A.json --b _board_eval_strat.json
"""
import argparse
import json
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def f1_from_counts(tp, fp, fn):
    p = tp / np.maximum(tp + fp, 1e-12)
    r = tp / np.maximum(tp + fn, 1e-12)
    return 2 * p * r / np.maximum(p + r, 1e-12)


def per_image_counts(recs, match_iou=0.5):
    """逐图算 (tp, fp, fn)，口径与 _board_ab_eval 一致（贪心匹配、TP 记真值类）。"""
    out = []
    for r in recs:
        gb = np.asarray(r['gt_box'], np.float32).reshape(-1, 4)
        pb = np.asarray(r['pr_box'], np.float32).reshape(-1, 4)
        n_gt, n_pr = len(gb), len(pb)
        if n_gt == 0 and n_pr == 0:
            out.append((0, 0, 0))
            continue
        if n_gt == 0:
            out.append((0, n_pr, 0))
            continue
        if n_pr == 0:
            out.append((0, 0, n_gt))
            continue
        ax1, ay1, ax2, ay2 = gb[:, 0], gb[:, 1], gb[:, 2], gb[:, 3]
        bx1, by1, bx2, by2 = pb[:, 0], pb[:, 1], pb[:, 2], pb[:, 3]
        ix1 = np.maximum(ax1[:, None], bx1[None, :])
        iy1 = np.maximum(ay1[:, None], by1[None, :])
        ix2 = np.minimum(ax2[:, None], bx2[None, :])
        iy2 = np.minimum(ay2[:, None], by2[None, :])
        iw = np.clip(ix2 - ix1, 0, None)
        ih = np.clip(iy2 - iy1, 0, None)
        inter = iw * ih
        ua = (ax2 - ax1) * (ay2 - ay1)
        ub = (bx2 - bx1) * (by2 - by1)
        m = inter / np.clip(ua[:, None] + ub[None, :] - inter, 1e-9, None)
        used = set()
        tp = 0
        for gi in range(n_gt):
            j = int(np.argmax(m[gi]))
            if m[gi, j] >= match_iou and j not in used:
                used.add(j)
                tp += 1
        fn = n_gt - tp
        fp = n_pr - len(used)
        out.append((tp, fp, fn))
    return np.asarray(out, np.int64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True)
    ap.add_argument('--b', required=True)
    ap.add_argument('--n', type=int, default=10000)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    def load(p):
        path = p if os.path.isabs(p) else os.path.join(_ROOT, p)
        with open(path, encoding='utf-8') as f:
            return json.load(f)['recs']

    ra, rb = load(args.a), load(args.b)
    if len(ra) != len(rb):
        sys.exit('两次评估图数不同（%d vs %d），不是同集对比' % (len(ra), len(rb)))

    # 逐图对齐（顺序应一致；按 path 校验）
    for x, y in zip(ra, rb):
        if x['path'] != y['path']:
            sys.exit('图序不一致，无法配对：%s vs %s' % (x['path'], y['path']))

    ca = per_image_counts(ra)
    cb = per_image_counts(rb)

    def f1_of_counts(c):
        tp, fp, fn = c[:, 0].sum(), c[:, 1].sum(), c[:, 2].sum()
        return float(f1_from_counts(tp, fp, fn))

    f1a, f1b = f1_of_counts(ca), f1_of_counts(cb)
    delta = f1b - f1a
    print('点数法（全量）: F1(A) = %.4f  F1(B) = %.4f  Δ = %+.4f' % (f1a, f1b, delta))

    rng = np.random.RandomState(args.seed)
    n = len(ca)
    deltas = np.empty(args.n, np.float64)
    for i in range(args.n):
        idx = rng.randint(0, n, n)
        deltas[i] = f1_of_counts(cb[idx]) - f1_of_counts(ca[idx])

    lo, hi = np.percentile(deltas, [2.5, 97.5])
    p_b = float((deltas <= 0).mean())
    print()
    print('配对 bootstrap（n=%d, 重采样 %d 次）' % (n, args.n))
    print('  ΔF1 均值   = %+.4f' % deltas.mean())
    print('  ΔF1 标准差 = %.4f' % deltas.std())
    print('  95%% 置信区间 = [%+.4f, %+.4f]' % (lo, hi))
    print('  P(Δ <= 0)  = %.4f' % p_b)
    print()
    if lo > 0:
        print('结论: Δ 的 95% CI 完全在 0 以上 → 提升显著（p < 0.025）')
    elif hi < 0:
        print('结论: Δ 的 95% CI 完全在 0 以下 → 下降显著')
    else:
        print('结论: Δ 的 95% CI 跨 0 → 差异未达统计显著，不能断言谁更好')


if __name__ == '__main__':
    main()
