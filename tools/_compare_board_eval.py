# -*- coding: utf-8 -*-
"""对比两次板端同集评估（配置 A vs 新模型），输出差异结论。

两次评估必须用同一 manifest + 同 seed + 同 limit，才是可比同集对比。
用法:
  python tools/_compare_board_eval.py --a _board_eval_A.json --b _board_eval_strat.json \
      --label-a "A 旧50轮+uniform0.20" --label-b "B strat100轮+uniform0.20"
"""
import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    path = p if os.path.isabs(p) else os.path.join(_ROOT, p)
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    return d['summary'], d.get('recs', [])


def per_class(recs, n_cls=39):
    """按真值类统计 TP/FP/FN（与 _board_ab_eval 同口径：TP 记真值类）。"""
    import numpy as np

    def iou_mat(a, b):
        if len(a) == 0 or len(b) == 0:
            return np.zeros((len(a), len(b)), np.float32)
        ax1, ay1, ax2, ay2 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
        bx1, by1, bx2, by2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
        ix1 = np.maximum(ax1[:, None], bx1[None, :])
        iy1 = np.maximum(ay1[:, None], by1[None, :])
        ix2 = np.minimum(ax2[:, None], bx2[None, :])
        iy2 = np.minimum(ay2[:, None], by2[None, :])
        iw = np.clip(ix2 - ix1, 0, None)
        ih = np.clip(iy2 - iy1, 0, None)
        inter = iw * ih
        ua = (ax2 - ax1) * (ay2 - ay1)
        ub = (bx2 - bx1) * (by2 - by1)
        return inter / np.clip(ua[:, None] + ub[None, :] - inter, 1e-9, None)

    tp = np.zeros(n_cls, np.int64)
    fp = np.zeros(n_cls, np.int64)
    fn = np.zeros(n_cls, np.int64)
    gt = np.zeros(n_cls, np.int64)
    for r in recs:
        gb = np.asarray(r['gt_box'], np.float32).reshape(-1, 4)
        gc = np.asarray(r['gt_cls'], np.int64)
        pb = np.asarray(r['pr_box'], np.float32).reshape(-1, 4)
        pc = np.asarray(r['pr_cls'], np.int64)
        for c in gc:
            if 0 <= c < n_cls:
                gt[c] += 1
        if len(gb) == 0 or len(pb) == 0:
            for c in gc:
                if 0 <= c < n_cls:
                    fn[c] += 1
            for c in pc:
                if 0 <= c < n_cls:
                    fp[c] += 1
            continue
        m = iou_mat(gb, pb)
        used_p = set()
        for gi in range(len(gb)):
            if len(pc) == 0:
                break
            j = int(np.argmax(m[gi]))
            if m[gi, j] >= 0.5 and j not in used_p:
                used_p.add(j)
                c = gc[gi]
                if 0 <= c < n_cls:
                    tp[c] += 1
            else:
                c = gc[gi]
                if 0 <= c < n_cls:
                    fn[c] += 1
        for j in range(len(pb)):
            if j in used_p:
                continue
            c = pc[j]
            if 0 <= c < n_cls:
                fp[c] += 1
    return tp, fp, fn, gt


def f1_of(tp, fp, fn):
    import numpy as np
    p = tp / np.maximum(tp + fp, 1)
    r = tp / np.maximum(tp + fn, 1)
    return 2 * p * r / np.maximum(p + r, 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True)
    ap.add_argument('--b', required=True)
    ap.add_argument('--label-a', default='A')
    ap.add_argument('--label-b', default='B')
    args = ap.parse_args()

    sa, ra = load(args.a)
    sb, rb = load(args.b)

    print('=' * 74)
    print('板端同集对比（同 manifest / seed / limit）')
    print('=' * 74)
    hdr = '%-28s %10s %10s %10s' % ('', args.label_a[:10], args.label_b[:10], 'Δ(B-A)')
    print(hdr)
    print('-' * 74)
    for k, fmt in [('n_img', '%d'), ('tp', '%d'), ('fp', '%d'), ('fn', '%d'),
                   ('precision', '%.4f'), ('recall', '%.4f'), ('f1', '%.4f')]:
        va, vb = sa[k], sb[k]
        d = vb - va
        print('%-28s %10s %10s %+10s' % (k, fmt % va, fmt % vb, (fmt % d) if k in ('precision', 'recall', 'f1') else ('%+d' % d)))
    print('-' * 74)
    print('seed=%s limit=%s  (A) / seed=%s limit=%s  (B)'
          % (sa.get('seed'), sa.get('limit'), sb.get('seed'), sb.get('limit')))

    # 逐类对比：只看有 GT 的类
    tpa, fpa, fna, gta = per_class(ra)
    tpb, fpb, fnb, gtb = per_class(rb)
    f1a = f1_of(tpa, fpa, fna)
    f1b = f1_of(tpb, fpb, fnb)

    rows = []
    for c in range(39):
        if gta[c] == 0 and gtb[c] == 0:
            continue
        rows.append((f1b[c] - f1a[c], c, gta[c], f1a[c], f1b[c], tpa[c], tpb[c]))
    rows.sort()

    print()
    print('=' * 74)
    print('逐类 F1 变化（按 Δ 升序，仅列变化幅度最大的 12 类）')
    print('=' * 74)
    print('%-4s %8s %8s %8s %9s %9s' % ('cls', 'GT', 'F1(A)', 'F1(B)', 'TP(A)', 'TP(B)'))
    print('-' * 74)
    show = rows[:6] + rows[-6:] if len(rows) > 12 else rows
    for d, c, g, fa, fb, ta, tb in show:
        print('%-4d %8d %8.3f %8.3f %9d %9d   %+.3f' % (c, g, fa, fb, ta, tb, d))

    better = sum(1 for r in rows if r[0] > 0.01)
    worse = sum(1 for r in rows if r[0] < -0.01)
    print()
    print('类级胜负: 变好 %d 类 / 变差 %d 类 / 基本持平 %d 类'
          % (better, worse, len(rows) - better - worse))

    # 结论
    d_f1 = sb['f1'] - sa['f1']
    print()
    if d_f1 > 0.005:
        verdict = '新模型胜出（+%.4f），建议切配置' % d_f1
    elif d_f1 < -0.005:
        verdict = '新模型落后（%.4f），建议维持现有配置' % d_f1
    else:
        verdict = '差异在噪声范围内（%.4f），无充分理由切换' % d_f1
    print('结论: %s' % verdict)
    print('判据: |ΔF1| > 0.005 才视为有实质差异（300 张样本的统计波动量级）')


if __name__ == '__main__':
    main()
