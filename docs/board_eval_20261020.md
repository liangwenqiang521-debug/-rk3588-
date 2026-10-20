# 板端同集对比报告：旧 50 轮 vs 100 轮分层重训

**日期**：2026-10-20
**目的**：回答项目里最后一个悬案——100 轮新模型（strat）在板端真实链路上到底比旧 50 轮强还是弱。
**背景**：此前两个数字（板端 0.7376 / holdout 0.7159）因 val 集不同、大小差 10 倍，**不可直接比较**。

---

## 一、实验设计

| 项 | 设定 |
|---|---|
| 测试集 | `模型训练/splits/val_holdout.txt`（**旧** 300 张 holdout，全量） |
| seed | 20261013（与 10-13 的 2×2 实验完全一致，图集可逐张对齐） |
| 链路 | 真实板端 socket（ATK-DLRRK3588 :9000，`cmd=detect_img` 端到端） |
| 后处理 | 板端 `CONF_THRES = 0.20`，`PER_CLASS_THRES = {}`（统一阈值），NMS IoU 0.45 |
| 评估匹配 | IoU 0.5，贪心匹配，TP 记真值类（与 `_calib_thres39.py` 同口径） |
| 变量 | **仅模型**（A = 旧 50 轮，B = 100 轮分层重训 strat） |

两次评估使用**同一批图、同一顺序**，脚本会校验 `path` 逐条对齐，确保是严格配对对比。

---

## 二、模型转换与部署

| 步骤 | 结果 |
|---|---|
| `.pt` → `.onnx` | `best_steel39_strat_640.onnx`，10.63 MB，opset 12，`out = [1, 43, 8400]` PASS |
| 板端 `.onnx` → `.rknn` | `best_steel39_strat_640.rknn`，7,582,710 B，fp16（INT8 不可用，见 `docs/rknn_int8_bug.md`） |
| md5 | `2c5cc2164726f92ebb1dae5f84976651`（与 e50 `84daf622…`、e100 `510d69af…` 均不同，确认是新权重） |
| 板端配置 | `MAIN_MODEL = /root/rknn/best_steel39_strat_640.rknn`，`FILTER_MODEL = None`（单模型 39 类） |
| 备份 | `board_server_cascade.py.bak_configA_20261020`（回滚用） |

> 注：rknn 文件大小与旧 e50 rknn 完全相同（7,582,710 B）是**同架构 fp16 的正常现象**，md5 不同已确认不是复制。

---

## 三、结果

### 3.1 整体指标（300 张，micro 汇总）

| 指标 | A 旧 50 轮 | B strat 100 轮 | Δ (B−A) |
|---|---|---|---|
| TP | 430 | 435 | **+5** |
| FP | 124 | 112 | **−12** |
| FN | 182 | 177 | **−5** |
| Precision | 0.7762 | 0.7952 | **+0.0191** |
| Recall | 0.7026 | 0.7108 | **+0.0082** |
| **F1** | **0.7376** | **0.7506** | **+0.0131** |

**三重同向改善**：假阳性少 12 个、假阴性少 5 个、真阳性多 5 个。不是"用召回换精度"的零和权衡。

### 3.2 逐类变化

- 变好（Δ > +0.01）：**14 类**
- 变差（Δ < −0.01）：**10 类**
- 基本持平：**13 类**

变化最大的几类（GT 极少，单框波动即满分/零分，需谨慎解读）：

| cls | 类名 | GT | F1(A) | F1(B) | Δ |
|---|---|---|---|---|---|
| 2 | crease 折痕 | 2 | 0.667 | 1.000 | +0.333 |
| 5 | finishing_roll_printing 精轧辊印 | 4 | 0.600 | 0.889 | +0.289 |
| 27 | slag_skin 渣皮 | 2 | 0.800 | 1.000 | +0.200 |
| 8 | iron_sheet_ash 铁皮灰 | 13 | 0.621 | 0.750 | +0.129 |
| 23 | welding_line 焊缝线 | 16 | 0.750 | 0.875 | +0.125 |
| 18 | secondary_rust_skin 二次锈皮 | 11 | 0.583 | 0.462 | −0.122 |
| 4 | dark_scratches 暗划痕 | 8 | 1.000 | 0.875 | −0.125 |
| 33 | striated_scale 条纹氧化铁皮 | 1 | 1.000 | 0.000 | −1.000 |

### 3.3 统计显著性（配对 bootstrap，n=300，重采样 10000 次）

| 项 | 值 |
|---|---|
| ΔF1 均值 | +0.0131 |
| ΔF1 标准差 | 0.0123 |
| **95% 置信区间** | **[−0.0104, +0.0376]** |
| P(Δ ≤ 0) | **0.1406** |

**结论：置信区间跨 0，ΔF1 未达统计显著。** 300 张样本量下，+1.31pp 与"没有差异"无法区分。

---

## 四、结论与建议

### 4.1 事实层面

1. **点估计上新模型更好**（+1.31pp），且是 P、R 双升，方向一致。
2. **但证据强度不足**：95% CI 从 −1.04pp 到 +3.76pp，跨过 0；p = 0.14。
3. 逐类层面 14 好 / 10 差，也不是压倒性优势。

### 4.2 为什么置信区间这么宽

F1 是**全局指标**，对单图结果的扰动高度敏感。300 张、约 600 个 GT 框的规模，F1 的抽样标准差本身就在 0.012 量级——恰好与观测到的 Δ 同量级。**这不是"实验做错了"，而是"样本量不够分辨这么小的差异"**。

### 4.3 决策建议

| 选项 | 说明 | 我的看法 |
|---|---|---|
| **① 维持板端 strat，观察** | 点估计更好，无证据表明更差 | 可接受，但需在文档中写明"未达显著" |
| ② 回滚到配置 A | 严格遵守"无显著证据不动生产" | 最保守，但放弃 1.3pp 的可能收益 |
| **③ 扩样本再判（推荐）** | 用新 3020 张 holdout 跑同集对比，把 σ 压下去 | **唯一能真正定论的路径** |

扩样本的一个**技术注意点**：新 holdout（`val_strat_holdout.txt`）是从旧 train+val 全池重划出来的，**旧 50 轮模型在训练时可能见过其中部分图**（旧 train 的图进入了新 holdout）。这会让 e50 被高估、对比结果**偏向 e50**——即对 strat 是保守估计。若 strat 在这种不利条件下仍显著更好，结论就很硬。

预估耗时：2 模型 × 3020 张 × ~0.13 s/张 ≈ **2.5 小时**（可分两次跑）。

---

## 五、复现命令

```bash
# 1) 基线（配置 A：旧 50 轮 + uniform 0.20）
.venv/Scripts/python.exe tools/_board_ab_eval.py --limit 300 --seed 20261013 --out _board_eval_A.json

# 2) 导出 strat ONNX（不改动 _export_onnx39.py）
模型训练/venv_cuda/Scripts/python.exe tools/_export_onnx_strat.py

# 3) 板端转 rknn（必须后台跑，转换耗时 > SSH 默认超时）
#    cd /root/rknn_convert && nohup sh -c 'PYTHONPATH=... python3 export_rknn.py --src ... --dst ... --imgsz 640 --dtype fp16' > strat_convert.log 2>&1 &

# 4) 切板端配置并重启
#    sed -i "s|best_steel39_640.rknn|best_steel39_strat_640.rknn|" /root/rknn/board_server_cascade.py
#    sh /root/rknn/start_cascade.sh

# 5) 新模型评估
.venv/Scripts/python.exe tools/_board_ab_eval.py --limit 300 --seed 20261013 --out _board_eval_strat.json

# 6) 对比 + 显著性
.venv/Scripts/python.exe tools/_compare_board_eval.py --a _board_eval_A.json --b _board_eval_strat.json
.venv/Scripts/python.exe tools/_bootstrap_significance.py --a _board_eval_A.json --b _board_eval_strat.json
```

---

## 六、产物位置

| 文件 | 说明 |
|---|---|
| `_board_eval_A.json` | 配置 A 逐图评估结果（基线，F1 0.7376） |
| `_board_eval_strat.json` | strat 逐图评估结果（F1 0.7506） |
| `_board_eval_strat.log` | 板端评估运行日志 |
| `模型训练/best_steel39_strat_640.onnx` | 导出 ONNX（不入 git） |
| `tools/_export_onnx_strat.py` | ONNX 导出脚本 |
| `tools/_compare_board_eval.py` | 同集对比（整体 + 逐类） |
| `tools/_bootstrap_significance.py` | 配对 bootstrap 显著性检验 |
| `docs/board_eval_20261020.md` | 本报告 |

---

## 七、板端回滚方法

```bash
# 回到配置 A（旧 50 轮 + uniform 0.20）
cp /root/rknn/board_server_cascade.py.bak_configA_20261020 /root/rknn/board_server_cascade.py
sh /root/rknn/start_cascade.sh
```
