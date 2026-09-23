# -*- coding: utf-8 -*-
"""per-class 阈值表单元测试（纯 CPU，不依赖 RKNNLite / NPU）

验证 board_server.py 的 postprocess 在改成 per-class 阈值后：
  1. inclusion 置信度 0.18（< 0.20 基线，但 >= 0.16）应被保留
  2. scratches 置信度 0.18（< 0.30）应被过滤
  3. crazing 0.25（>= 0.20 基线）应被保留
  4. 类别未在表内的回退到 conf_thres
"""
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 不真正 import RKNNLite（板端才有），直接 import 模块里纯 numpy 的部分。
# 方案：把 board_server.py 里 RKNNLite 的 import 用 stub 替换。
import types
stub_rknnlite = types.ModuleType('rknnlite')
stub_rknnlite.api = types.ModuleType('rknnlite.api')
stub_rknnlite.api.RKNNLite = type('RKNNLite', (), {
    'NPU_CORE_0_1_2': 0,
    '__init__': lambda self, verbose=False: None,
})
sys.modules['rknnlite'] = stub_rknnlite
sys.modules['rknnlite.api'] = stub_rknnlite.api

import board_server as B

NC = len(B.NAMES)          # 6
NA = 8400


def make_out(rows):
    """构造 (1, 4+nc, NA) 输出，rows = [(cls_id, conf, cx, cy, bw, bh)]"""
    pred = np.zeros((NA, 4 + NC), dtype=np.float32)
    # 默认所有 anchor 给一个极低分，避免误触发
    pred[:, 4:] = 0.01
    for i, (cid, cf, cx, cy, bw, bh) in enumerate(rows):
        pred[i, 0] = cx
        pred[i, 1] = cy
        pred[i, 2] = bw
        pred[i, 3] = bh
        # 让 argmax 落在目标类，且最大值 = cf
        pred[i, 4 + cid] = cf
    return pred[np.newaxis].transpose(0, 2, 1)  # (1, 4+nc, NA)


def get_cls_conf(res):
    return sorted([(d['cls'], d['conf']) for d in res])


passed = failed = 0


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('PASS  %s' % name)
    else:
        failed += 1
        print('FAIL  %s  %s' % (name, detail))


idx = {n: i for i, n in enumerate(B.NAMES)}

# 1) inclusion 0.18：< 0.20 但 >= 0.16，应保留
out = make_out([(idx['inclusion'], 0.18, 320, 320, 100, 100)])
res = B.postprocess(out)
check('inclusion 0.18 应保留', any(d['cls'] == 'inclusion' for d in res),
      get_cls_conf(res))

# 2) scratches 0.18：< 0.30，应过滤（丢弃）
out = make_out([(idx['scratches'], 0.18, 320, 320, 100, 100)])
res = B.postprocess(out)
check('scratches 0.18 应过滤', all(d['cls'] != 'scratches' for d in res),
      get_cls_conf(res))

# 3) crazing 0.25：>= 0.20 基线，应保留
out = make_out([(idx['crazing'], 0.25, 320, 320, 100, 100)])
res = B.postprocess(out)
check('crazing 0.25 应保留', any(d['cls'] == 'crazing' for d in res),
      get_cls_conf(res))

# 4) scratches 0.35：>= 0.30，应保留
out = make_out([(idx['scratches'], 0.35, 320, 320, 100, 100)])
res = B.postprocess(out)
check('scratches 0.35 应保留', any(d['cls'] == 'scratches' for d in res),
      get_cls_conf(res))

# 5) inclusion 0.15：< 0.16，应过滤
out = make_out([(idx['inclusion'], 0.15, 320, 320, 100, 100)])
res = B.postprocess(out)
check('inclusion 0.15 应过滤', all(d['cls'] != 'inclusion' for d in res),
      get_cls_conf(res))

# 6) 混合：inclusion 0.18 + scratches 0.18 同框 → 只留 inclusion
out = make_out([
    (idx['inclusion'], 0.18, 320, 320, 100, 100),
    (idx['scratches'], 0.18, 330, 330, 100, 100),
])
res = B.postprocess(out)
check('混合: 只留 inclusion，scratches 被滤',
      any(d['cls'] == 'inclusion' for d in res) and all(d['cls'] != 'scratches' for d in res),
      get_cls_conf(res))

print('\n%d passed, %d failed' % (passed, failed))
sys.exit(1 if failed else 0)
