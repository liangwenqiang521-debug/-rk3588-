# -*- coding: utf-8 -*-
"""板端级联推理离线验证：加载双模型，对样本图跑级联，打印结果。

不占 9000 端口，直接 import board_server_cascade 的类做单图推理。
"""
import sys, os, time, glob
sys.path.insert(0, '/root/rknn')
from board_server_cascade import BoardServerCascade, NAMES

WORK = '/root/rknn'
SAMPLES = os.path.join(WORK, 'samples')

def main():
    srv = BoardServerCascade(9999)  # 端口随意，不真正 serve
    srv.load_samples()
    print('加载双模型...')
    srv.init_npu()
    print('双模型加载成功\n')

    # 取样本图：缺陷图（各类）+ 无缺陷图（如果有）
    files = srv.samples
    print('样本总数:', len(files))
    # 打印每类各一张做验证
    seen = {}
    for f in files:
        base = os.path.basename(f)
        cls = base.split('_')[0] if '_' in base else base[:6]
        if cls not in seen and cls in NAMES:
            seen[cls] = f

    for cls, f in sorted(seen.items()):
        x = srv.read_sample(f)
        if x is None:
            print('[%s] 读图失败: %s' % (cls, f))
            continue
        defects, fms, tms = srv._cascade_infer(x)
        print('[%s] %s' % (cls, os.path.basename(f)))
        if defects:
            for d in defects:
                print('    缺陷 %-16s conf=%.3f' % (d['cls'], d['conf']))
            print('    -> 有缺陷，跑了两遍（filter %.1fms + main）总 %.1fms' % (fms, tms))
        else:
            print('    -> 无缺陷（过滤器判 ok，只跑一遍 %.1fms）' % tms)
    print('\n级联验证完成')

if __name__ == '__main__':
    main()
