# -*- coding: utf-8 -*-
"""39 类分层重划分训练入口（不改 train_steel39.py）
==============================================================
把 train_steel39.py 的数据源换成 data_steel39_strat.yaml，
其余超参全部复用主脚本的 main()，避免两处超参漂移。

为什么需要它：
  全池分层重划分后，val 里含有旧 train 的图，已训模型在上面是「见过」的，
  不能用来评估当前模型；必须在**新 train 清单**上重训，新 val 才是干净 holdout。

用法：
  venv_cuda\\Scripts\\python.exe _train_steel39_strat.py            # 默认 100 轮
  venv_cuda\\Scripts\\python.exe _train_steel39_strat.py --epochs 2  # 冒烟
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import train_steel39 as T  # noqa: E402

# —— 只覆盖数据源与运行名，其余超参交回主脚本 ——
T.DATA = HERE / "data_steel39_strat.yaml"
T.RUN_NAME = "steel39_yolo11n_640_strat"

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # 无参数时的默认：100 轮 / batch 16 / workers 4（本机内存与 8GB 显存安全档）
        sys.argv = [sys.argv[0], "--epochs", "100", "--batch", "16", "--workers", "4"]
    print("[_train_steel39_strat] 数据源 = %s" % T.DATA)
    print("[_train_steel39_strat] 运行名 = %s" % T.RUN_NAME)
    sys.stdout.flush()
    raise SystemExit(T.main())
