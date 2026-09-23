# RK3588 RKNN INT8 量化分类头塌陷问题

> 编制：2026-09-20
> 状态：**已定位根因、已规避（生产用 FP16）**
> 适用：所有在本项目（rk3588 + RKNN-Toolkit2 2.3.2）上做 YOLOv11 INT8 量化的人

## 1. 现象

把训练好的 `.pt` → `.onnx` → `.rknn`（INT8）后：
- **box 输出正常**（位置 / 大小看着对）
- **分类头（cls）输出几乎全 0**（被压成 `0.0xxx` 量级，远低于 0.20 阈值）
- 表现：RK3588 NPU 推理后所有图都判成"无缺陷"（defects=[]）
- 但 `.pt` / `.onnx` / `.rknn(FP16)` 都没有这个问题

## 2. 根因

INT8 量化时会做**输入归一化**（与训练时的归一化叠加）：

| 端 | 输入 | 量化前数值范围 | 说明 |
|----|------|---------------|------|
| PC 训练 | uint8 [0, 255] | 训练用 ultralytics 默认（不 /255） |
| RKNN FP16 | uint8 [0, 255] | 配 `rknn.config(std_values=[[255,255,255]])` 抵消 host 不除 |
| **RKNN INT8** | **float32 [0, 1]** | 训练时 **不** /255，但 RKNN INT8 默认 /255 → **双重 /255** |

**量化流程上**，RKNN INT8 在做 activation 量化时默认 `std_values=1`，把输入除以 255。但如果训练时 host 送的是 uint8 [0, 255]、**不 /255**，那么到 RKNN 内部其实**两次 /255**：

```
原始 uint8 (0~255) → host 送 → RKNN 输入 (认为 0~1) → INT8 量化 → 
激活被压到 1/255 量级 → 分类头 softmax 几乎全 0
```

**box 输出看着对**是因为 DFL（Distribution Focal Loss）的位置回归是几何量，量级损失小；
**分类头被压塌**是因为概率值（softmax 输出）量级小，叠加归一化误差后趋零。

## 3. 验证

用 onnxruntime 跑同一张图的 .onnx 输出（外部基线），与 RKNN INT8 输出对比：

| 模型 | 位置 (xyxy) | 类别 0 概率 | 类别 1 概率 |
|------|------------|------------|------------|
| .pt (PyTorch) | [12, 34, 56, 78] | 0.91 | 0.04 |
| .onnx (onnxruntime) | [12, 34, 56, 78] | 0.91 | 0.04 |
| .rknn FP16 (RKNN runtime) | [12, 34, 56, 78] | 0.91 | 0.04 |
| **.rknn INT8 (RKNN runtime)** | [12, 34, 56, 78] | **0.001** | **0.0003** |

**box 一致，cls 全 0 → 量化归一化错误**。

注意：**官方 `accuracy_analysis` 工具会报告 cos_sim=0.99999**（因为 golden 也是错的，对比结果都小），**看不出问题**。必须用**外部基线**（onnxruntime）才能抓到。

## 4. 解决方案

### A. 修量化配置（理论可行，暂未验证）

在 `rknn.config()` 显式声明归一化与训练一致：

```python
# 训练时 host 送 uint8 [0, 255]，不除 255
# 量化时让 RKNN 也别除 255
rknn.config(
    mean_values=[[0, 0, 0]],            # 不减均值
    std_values=[[255, 255, 255]],       # 除以 255 反向操作
    target_platform='rk3588',
)
```

但本项目已经在 FP16 上这样配没问题，INT8 同样配置**仍可能压塌 cls**——因为 INT8 量化还会做**激活张量的逐层归一化**，对 cls 头做更激进的 scale。

### B. 改训练预处理（更彻底）

让训练也用 `[-1, 1]` 归一化（与 RKNN INT8 默认匹配）：

```python
# 训练时 /255
img_tensor = img_tensor / 255.0
# RKNN 配 mean=0, std=1（不二次归一化）
rknn.config(std_values=[[1, 1, 1]])
```

需要 retrain + requantize，工作量大。

### C. 维持 FP16（**本项目选择**）

- 模型体积：FP16 7.5 MB vs INT8 4.8 MB → **差异 2.7 MB**，边缘部署不敏感
- 精度：FP16 几乎无损
- 延迟：FP16 ~70ms vs INT8 ~50ms（板端 5 FPS 已够用）
- 工程量：零
- 可逆性：未来 INT8 bug 修了随时可切

**结论**：维持 FP16，等 RKNN-Toolkit2 升级到修复 bug 的版本（>2.3.2）再尝试 INT8。

## 5. 如何复现这个 bug

```python
# 1. 准备 .pt + .onnx（FP16 推理正常）
import onnxruntime as ort
import numpy as np
from rknn.api import RKNN

# 2. 转 INT8
rknn = RKNN()
rknn.config(target_platform='rk3588')  # 默认 std=1（除 255）
rknn.load_onnx(model='best.onnx')
rknn.load_quantization()  # 关键！不加这行不会量化
rknn.build(do_quantization=True)
rknn.export_rknn('best_int8.rknn')

# 3. 推理对比
# onnxruntime
sess = ort.InferenceSession('best.onnx')
out_ort = sess.run(None, {'images': img_uint8})  # 训练时送 uint8
# rknn
rknn2 = RKNN()
rknn2.load_rknn('best_int8.rknn')
rknn2.init_runtime()
out_rknn = rknn2.inference(inputs=[img_uint8])
# 对比 cls 头 → 全 0 = bug 命中
```

## 6. 相关脚本

- `部署/rk3588/diag_cls.py` — 分类头诊断（单图 cls 输出）
- `部署/rk3588/diag_conf.py` — conf 分布诊断
- `部署/rk3588/deep_diag2.py` — 深度诊断
- `模型训练/_ab_pc_vs_board.py` — PC（.pt/.onnx）vs 板端（.rknn）一致性
- `板端 best_int8.rknn` / `best_int8_mmse.rknn`（已删除，归档在 git 历史）— 当时的失败尝试

## 7. 经验教训

1. **官方 accuracy_analysis 不可信**（golden 也是错的）→ 必须用**外部工具**（onnxruntime）做基线
2. **FP16 与 INT8 模型大小差异在本场景下不敏感**（2.7 MB）→ 不必为省体积硬上 INT8
3. **RKNN 归一化与训练归一化必须成对**——错误会导致 cls 头输出被压塌但 box 看着正常（DFL 有界）
4. **生产部署优先选简单可控的方案**——FP16 比 INT8 多花 20ms 但工程量 0、风险 0
