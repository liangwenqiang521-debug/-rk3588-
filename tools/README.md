# tools/ — 诊断、验证与转换工具

本目录存放**排查问题用的一次性/低频工具**。与 `tests/` 的区别：
`tests/` 是可重复执行的回归套件，`tools/` 是出问题时的分步诊断与辅助脚本。

## 分步诊断（连不上 / 推帧不动时）

排查 step 模式「推一两帧后卡住」这类问题，按由外到内的顺序：

```bash
python tools/_pc_sock_test.py     # 1. 纯 socket 对照——若此步正常，问题在上位机框架
python tools/_diag_step.py        # 2. 分步诊断：定时器状态 → send_cmd 返回值 → 板端帧数增量
python tools/_diag_noframe.py     # 3. 无帧诊断
```

`_step_soak.py` 用于长时间浸泡测试（60 秒 / N 秒），带断流检测。

## 模型与转换验证

```bash
python tools/_diag_onnx.py           # ONNX 推理基线（外部对照，抓归一化配置错误）
python tools/_upload_convert.py      # 上传 ONNX 到板端并转换 RKNN
python tools/_verify_convert.py      # 转换结果验证
python tools/_verify_new_classes.py  # 新增类别验证
python tools/_verify_edge_render.py  # 边缘渲染结果验证
```

## 截图与辅助

```bash
python tools/_shot.py              # 截图（落 _shots/）
python tools/_shot_edge_fixed.py   # 边缘画面截图
python tools/_grab_window.py       # 抓取窗口
python tools/_fetch_libgomp.py     # 拉取 libgomp（板端缺失依赖）
```

## maintenance/ — 长期常驻维护

```bash
python tools/maintenance/_weekly_feedback.py   # 难例回流周报（7 天周期）
sh    tools/maintenance/_chk_boot.sh           # 板端起机状态检查
```

## 说明

- 所有脚本内置 `sys.path` 回退到项目根，**可在任意目录直接运行**。
- 涉及板端的脚本需要先配好 `board_env.local.py`（见项目根 `board_env.example.py`）。
