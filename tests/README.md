# tests/ — 回归测试与端到端验证

本目录存放**可重复执行**的回归测试。改动上位机代码后，建议按下面顺序过一遍。

## 快速回归（改完 UI / 桥接层必跑）

```bash
python tests/_func_test.py        # 上位机全功能测试（28 项，基线 23/28）
python tests/_regress_crash.py    # 闪退回归（PyQt5 槽内异常防护）
python tests/_ui_smoke.py         # 界面冒烟，截图落 _shots/
```

## 边缘链路（改完板端协议必跑）

```bash
python tests/_e2e_check.py        # 边缘连接可用性检查
python tests/_e2e_edge.py         # 端到端：连板 → 开始检测 → 收帧 → 统计
python tests/_test_step.py        # step 模式节拍验证（15s 应出 15 件）
python tests/_test_detect_img.py  # cmd=detect_img 外部图送检
```

## 状态复位（改完页面语义必跑）

```bash
python tests/_test_stop_reset.py    # 停止检测 → 统计归零、连接保留
python tests/_test_clear_reset.py   # 清除 → 画布/缺陷列表/右侧面板全复位
```

## 模型相关

```bash
python tests/_test_top2_dual.py   # 双模型 top2 输出
```

## 说明

- **`_func_test.py` 固定用 offscreen 跑**（不弹窗口）；`_ui_smoke.py` 必须用真实平台
  截图，因为 offscreen 下中文不渲染。
- 所有脚本内置 `sys.path` 回退，**在项目根直接 `python tests/xxx.py` 或
  `cd tests && python xxx.py` 均可**。
- 运行前请用项目虚拟环境：
  `.venv/Scripts/python.exe tests/_func_test.py`（Windows）。
