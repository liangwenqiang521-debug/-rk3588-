# 板端同集对比（定论版）：1221 张双干净集 · e50 vs strat100

**日期**：2026-10-21
**目的**：给"100 轮分层重训（strat）是否值得替换生产模型（e50）"这个悬案下**统计定论**。
**前情**：`docs/board_eval_20261020.md` 在 300 张上得到 +1.31pp，但 95% CI 跨 0（p=0.14），且事后发现那 300 张里 **77% 曾进入 strat 的训练集**，结论不可用。

---

## 一、为什么必须重做

| 问题 | 具体情况 | 后果 |
|---|---|---|
| 样本量不足 | 300 张 / 约 605 个 GT 框，F1 抽样标准差 ≈ 0.012，与 Δ 同量级 | CI 宽达 4.8pp，跨 0 |
| **测试集污染** | 旧 `val_holdout.txt` 实际 2682 行，其中 **2065 张（77%）** 被新 train 占用 | strat 见过这些图，+1.31pp 可能是记忆效应 |

**解决方式**：构造双干净集 —— 两个模型都**从未见过**的图。

```
images/val 全集            5296 张   （e50 训练时 val 侧，但未参与梯度更新）
−  新 train 占用           4075 张   （strat 训练时见过）
=  val_clean_1221.txt      1221 张   （双干净）
```

`模型训练/splits/val_clean_1221.txt`，1221 张，2424 个 GT 框，覆盖全部有样本的类。

---

## 二、实验设计

| 项 | 设定 |
|---|---|
| 测试集 | `模型训练/splits/val_clean_1221.txt`（1221 张，双干净） |
| seed / limit | 20261013 / 0（全量） |
| 链路 | 真实板端 socket（ATK-DLRK3588 :9000，`cmd=detect_img` 端到端） |
| 后处理 | `CONF_THRES = 0.20`，`PER_CLASS_THRES = {}`，NMS IoU 0.45 |
| 匹配 | IoU 0.5，贪心匹配，TP 记真值类（与 `_calib_thres39.py` 默认口径一致） |
| 变量 | **仅模型**：A = `best_steel39_640.rknn`（50 轮） / B = `best_steel39_strat_640.rknn`（100 轮分层） |

两次评估同一批图、同一顺序，脚本逐条校验 `path` 对齐，严格配对。
单模型跑完约 28.5 分钟（1221 张 × ~1.4 s/张，含落盘与建连开销）。

---

## 三、结果

### 3.1 整体指标（1221 张，micro 汇总）

| 指标 | A e50 | B strat100 | Δ (B−A) |
|---|---|---|---|
| TP | 1650 | 1649 | **−1** |
| FP | 595 | 515 | **−80** |
| FN | 774 | 775 | **+1** |
| Precision | 0.7350 | 0.7620 | **+0.0270** |
| Recall | 0.6807 | 0.6803 | **−0.0004** |
| **F1** | **0.7068** | **0.7188** | **+0.0120** |

**这条结论比数字本身更重要**：TP 和 FN 都没动（±1），**全部提升来自误报减少 80 个（−13.4%）**。

也就是说 100 轮重训学到的是"**别乱报**"，不是"**多检出**"。召回率 0.6803 对 0.6807 —— 完全相同。
如果项目下一步的痛点是漏检（Recall 只有 68%），**这个模型不是解药**。

### 3.2 逐类胜负

- 变好（Δ > +0.01）：**17 类**
- 变差（Δ < −0.01）：**11 类**
- 基本持平：**11 类**

变化最大的几类（小 GT 类单框波动即 ±0.1，需谨慎）：

| cls | 类名 | GT | F1(A) | F1(B) | Δ |
|---|---|---|---|---|---|
| 23 | welding_line 焊缝线 | 38 | 0.759 | 0.897 | **+0.138** |
| 29 | warp 翘曲 | 7 | 0.300 | 0.400 | +0.100 |
| 17 | rolled_pit 轧制凹坑 | 27 | 0.435 | 0.533 | +0.099 |
| 24 | white_rust 白锈 | 60 | 0.635 | 0.694 | +0.059 |
| 15 | red_iron_sheet 红斑铁皮 | 44 | 0.913 | 0.966 | +0.052 |
| 21 | waist_folding 腰部折痕 | 68 | 0.385 | 0.430 | +0.045 |
| 30 | external_fold 外折 | 12 | 0.815 | 0.750 | −0.065 |
| 10 | oxide_scale_plate 板系氧化铁皮 | 8 | 1.000 | 0.933 | −0.067 |
| 33 | striated_scale 条纹氧化铁皮 | 10 | 1.000 | 0.889 | −0.111 |
| 2 | crease 折痕 | 27 | 0.512 | 0.390 | **−0.121** |
| 28 | longitudinal_crack 纵向裂纹 | 8 | 0.857 | 0.667 | −0.190 |

`welding_line` 是最大赢家（+0.138），它也是历史记录里唯一已知的**系统性跨类混淆类**（与 `crescent_gap` 互串，gc_* 源）。

### 3.3 统计显著性（配对 bootstrap，n=1221，重采样 10000 次）

| 项 | 300 张（污染集） | **1221 张（双干净集）** |
|---|---|---|
| ΔF1 均值 | +0.0131 | **+0.0120** |
| ΔF1 标准差 | 0.0123 | **0.0054** |
| 95% 置信区间 | [−0.0104, +0.0376] | **[+0.0014, +0.0227]** |
| P(Δ ≤ 0) | 0.1406 | **0.0133** |
| 结论 | 不显著 | **显著（p < 0.025）** |

**两个关键观察**：

1. **Δ 几乎没变（1.31pp → 1.20pp）**，说明 300 张上的提升**不是记忆效应**——去掉污染后提升依然存在。之前的怀疑被排除。
2. **CI 宽度从 4.8pp 压到 2.1pp**（缩 56%），样本量 4 倍带来的正是这个。P 值从 0.14 掉到 0.013。

### 3.4 跨类混淆（定位对 IoU≥0.5 但类别错）

两个模型在 1221 张上的混淆总数：**A=71 次 / B=62 次**，占各自 FN（774/775）的 9.2% / 8.0%。

| 混淆对 | A 次数 | B 次数 |
|---|---|---|
| 亮划痕(0) → 麻面(13) | 24 | **25** |
| 麻面(13) → 亮划痕(0) | 10 | **5** |
| 油污(9) → 夹杂物(6) | 10 | **7** |
| 块状氧化铁皮(32) → 条纹氧化铁皮(34) | 2 | **5** |

**归因结论（这条比 F1 更重要）**：

- **91% 的漏检不是类别判错，是根本没检出**。跨类混淆只有 71 次，FN 有 774 个——剩下 703 个是框都没出来。所以"修混淆"能拿到的上限只有约 0.9pp F1，**主要矛盾在召回**（小目标、低对比度、背景干扰）。
- **亮划痕→麻面 是唯一没被改善的顽固对（24→25）**，其他三对都降了。这两类在灰度图上都是"细碎亮/暗纹理"，仅靠 640 单尺度难分。

### 3.5 两套口径对照（供论文引用）

| 口径 | holdout micro F1 | 说明 |
|---|---|---|
| ultralytics 官方 | 0.775 | mAP50，不可与 F1 直接比 |
| 项目默认（class-agnostic + TP 记真值类） | 0.7159 | `_eval_steel39_strat.json` |
| **strict（预测类须等于真值类）** | **0.6915** | `_eval_steel39_strat_strict.json` |
| 板端双干净集（默认口径） | 0.7188 | 本报告 B 组 |

默认口径与 strict 差 **2.44pp**，这 132 个框就是"定位对、类别错"的跨类混淆代价。详见 `docs/metric_caliber_note.md`。

---

## 四、结论与决策建议

### 4.1 事实

1. strat 在双干净集上 **F1 +1.20pp，统计显著**（CI 完全 > 0，p=0.013）。
2. 提升**全部是精度**（FP −80），召回**零变化**。
3. 逐类 17 好 / 11 差，`welding_line` 单独贡献 +0.138。
4. 跨类混淆小改善（71→62），但**不是**瓶颈；瓶颈在召回。

### 4.2 建议

| 决策 | 我的看法 |
|---|---|
| **板端保留 strat** | **建议采纳**。显著更好，且更保守（误报少 13%，现场误停线概率降低） |
| 论文里怎么写 | 写"F1 由 0.7068 提升至 0.7188（+1.20pp，配对 bootstrap 95% CI [+0.14, +2.27]pp，p=0.013）"，**并明确说明提升来自精度而非召回** —— 这是诚实且更有说服力的写法 |
| 是否继续追精度 | 收益上限低（混淆只占 9%），不值得 |
| **是否追召回** | **这才是主要矛盾**。Recall 68% 意味着每 3 个缺陷漏 1 个 |

### 4.3 追召回的三条路（按性价比排序）

1. **降 conf 到 0.15 + 逐类阈值标定**（配 `PER_CLASS_THRES`）—— 零训练成本，用 `模型训练/_calib_thres39.py` 的 cal 集标定，预期 Recall +3~5pp、P 掉 1~2pp
2. **提高输入分辨率到 960**（`imgsz=960`）—— 小目标收益最直接，板端推理耗时约 +1.6×，需重测 NPU 帧率
3. **补标漏标样本**（`docs/fp_audit/` 已量化：FP 大头来自有缺陷图的漏标，oracle 回收上界 F1 +4.0pp）

---

## 五、复现命令

```bash
# 0) 板端切到 strat 并重启（用 sed 精确改行，不要依赖 .bak 文件）
#    已踩过坑：.bak_configA_20261020 里存的其实是 strat 版本
export MSYS_NO_PATHCONV=1
python board_ssh.py --timeout 120 "sed -i \"s|MAIN_MODEL    = '/root/rknn/[a-z0-9_.]*'|MAIN_MODEL    = '/root/rknn/best_steel39_strat_640.rknn'|\" /root/rknn/board_server_cascade.py; grep -n MAIN_MODEL /root/rknn/board_server_cascade.py | head -1"
python board_ssh.py --timeout 120 "sh /root/rknn/start_cascade.sh; sleep 15; tail -20 /root/rknn/server_cascade.log"

# 1) 基线 A：e50（先切回 best_steel39_640.rknn，同样用 sed）
.venv/Scripts/python.exe -u tools/_board_ab_eval.py \
    --manifest "模型训练/splits/val_clean_1221.txt" --limit 0 \
    --out _board_clean_e50.json > _board_clean_e50.log 2>&1

# 2) 新模型 B：strat
.venv/Scripts/python.exe -u tools/_board_ab_eval.py \
    --manifest "模型训练/splits/val_clean_1221.txt" --limit 0 \
    --out _board_clean_strat.json > _board_clean_strat.log 2>&1

# 3) 对比 + 显著性
.venv/Scripts/python.exe tools/_compare_board_eval.py \
    --a _board_clean_e50.json --b _board_clean_strat.json \
    --label-a "A e50" --label-b "B strat100"
.venv/Scripts/python.exe tools/_bootstrap_significance.py \
    --a _board_clean_e50.json --b _board_clean_strat.json --n 10000
```

---

## 六、产物位置

| 文件 | 说明 |
|---|---|
| `模型训练/splits/val_clean_1221.txt` | 双干净集清单（1221 张） |
| `_board_clean_e50.json` | A 组逐图结果（F1 0.7068） |
| `_board_clean_strat.json` | B 组逐图结果（F1 0.7188） |
| `_board_clean_e50.log` / `_board_clean_strat.log` | 两次运行日志（零错帧） |
| `docs/board_eval_clean_1221.md` | 本报告 |
| `docs/board_eval_20261020.md` | 前序 300 张报告（结论已被本报告取代） |

---

## 七、回滚方法（修正版）

⚠️ **不要用 `cp .bak_configA_20261020`** —— 那个文件中实际存的是 strat 版本（备份时 sed 已先执行）。

```bash
# 回滚到 e50：直接改 MAIN_MODEL 行
export MSYS_NO_PATHCONV=1
python board_ssh.py --timeout 120 "sed -i \"s|MAIN_MODEL    = '/root/rknn/[a-z0-9_.]*'|MAIN_MODEL    = '/root/rknn/best_steel39_640.rknn'|\" /root/rknn/board_server_cascade.py; sh /root/rknn/start_cascade.sh; sleep 12; grep 'NPU 就绪' /root/rknn/server_cascade.log | tail -1"
```
