# -*- coding: utf-8 -*-
"""39 类（任意 nc）通用评估入口
================================

为什么需要它：
  `_eval_unified.py` 第 30 行把类别硬编码成 NEU 6 类：
      CLASSES = ['crazing', 'inclusion', ...]
  而混淆矩阵、逐类 GT/TP/FP/FN 全部由 `len(CLASSES)` 派生，
  所以拿 39 类模型去跑会整体错位（或直接索引越界）。

本脚本**不复制**评估逻辑，只做一件事：
  读 `--data` 指定的 yaml 里的 names，覆盖 `_eval_unified.CLASSES`，再调用它的 main()。
  原文件一行不改；未来原脚本改进（NMS、匹配策略等）自动生效。

用法（与原脚本完全一致，只是把 python 换成这个入口）：
  python _eval_steel39.py --model runs/steel39_yolo11n_640/weights/best.pt --data data_steel39.yaml
  python _eval_steel39.py --model ... --data data_steel39.yaml --json _eval_steel39.json
"""
import sys
from pathlib import Path

import yaml

import _eval_unified as U


def _names_from_argv():
    """从命令行里找 --data，读出它的 names。找不到就返回 None。"""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--data" and i + 1 < len(argv):
            p = Path(argv[i + 1])
        elif a.startswith("--data="):
            p = Path(a.split("=", 1)[1])
        else:
            continue
        if not p.exists():
            return None
        cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
        return cfg.get("names")
    return None


def main():
    names = _names_from_argv()
    if not names:
        print("[eval] 无法从 --data 读出 names，回退到 _eval_unified 内置 6 类")
    else:
        U.CLASSES = list(names)
        print("[eval] 类别数 = %d（来自 --data 的 names）" % len(U.CLASSES))
    U.main()


if __name__ == "__main__":
    main()
