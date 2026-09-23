# rk3588 项目实验台账 v1

> 编制时间：2026-09-20
> 范围：rkn3588 项目从合成数据到最终级联部署的 11 次训练实验
> 目的：完整记录每次实验的目的 / 配置 / 数据 / 结果 / 结论 / 权重路径，给论文"可复现性"节提供素材

---

## 0. 总览表

| # | 实验名 | 时间 | 目的 | 状态 | 部署？ |
|---|--------|------|------|------|--------|
| 1 | defect_yolo11n | 09-14 之前 | 合成 4 类缺陷 baseline | 完成 | ❌（合成数据）|
| 2 | neu_yolo11n | 09-15 | NEU 6 类首次训练 | 完成 | ❌（基线）|
| 3 | **neu_yolo11n_640** | 09-16 | NEU 增强 200 轮，**最终基线** | 完成 | ✅ **采用** |
| 4 | neu_yolo11n_aug | 09-16 | 增强 + 320 分辨率（分辨率失配实验）| 完成 | ❌（320 vs 640 不一致）|
| 5 | neu_yolo11n_aug2 | 09-17 | 修复假增强集后重训 | 完成 | ❌（mAP 0.776 < 0.783）|
| 6 | neu_yolo11n_aug2_interrupted_1ep | 09-17 | batch=64 显存爆训练 | 中断 | ❌（batch 过大）|
| 7 | neu_yolo11n_aug2_partial_2ep | 09-17 | 续训，batch 仍 64 | 部分 | ❌（已废弃）|
| 8 | **neu_yolo11n_negdagm** | 09-18 | 负样本 1:1 微调 | 完成 | ✅ **filter 模型** |
| 9 | neu_yolo11n_negdagm_half | 09-19 | 负样本 1:2 轻量回炉 | 完成 | ❌（与 1:1 退化相同）|
| 10 | neu_yolo11n_crazing_focus | 09-20 | crazing 专项攻坚 | 完成 | ❌（**灾难性遗忘**，仅作反面教材）|
| 11 | **级联（board_server_cascade.py）** | 09-19 上线 | negdagm filter + _640 主力 | 完成 | ✅ **生产部署** |

---

## 1. 实验 1：defect_yolo11n（合成 baseline）

| 维度 | 取值 |
|------|------|
| 目的 | 合成数据快速跑通 YOLO 训练 pipeline |
| 数据集 | `data.yaml`（4 类合成缺陷）|
| 训练集大小 | 合成约 1000 张 |
| 验证集大小 | 合成约 200 张 |
| 模型 | yolo11n.pt 预训练 |
| 优化器 | auto（SGD）|
| epochs | 50 |
| batch | 16 |
| imgsz | 640 |
| lr0 | 0.01（默认）|
| 数据增强 | ultralytics 默认 |
| 硬件 | GPU（RTX 5060 8GB）|
| 训练时间 | 约 20 分钟 |
| **best epoch** | 40 |
| **mAP50** | **0.9802** |
| **mAP50-95** | **0.8469** |
| 权重 | `runs/defect_yolo11n/weights/best.pt` |
| 结论 | 合成数据 mAP 0.98（明显**虚高**），不能当 NEU 真实数据用 |
| 是否部署 | ❌（合成数据不能当真实工业指标）|

---

## 2. 实验 2：neu_yolo11n（NEU 首次训练）

| 维度 | 取值 |
|------|------|
| 目的 | 验证 NEU 数据集 + ultralytics 训练 pipeline |
| 数据集 | `data_neu.yaml`（NEU 原始 6 类，1440 train + 360 val）|
| 训练集大小 | 1440 |
| 验证集大小 | 360 |
| 模型 | yolo11n.pt 预训练 |
| 优化器 | auto（SGD）|
| epochs | 80 |
| batch | 16 |
| imgsz | 640 |
| lr0 | 0.01 |
| 增强 | 默认 |
| 训练时间 | 约 40 分钟 |
| **best epoch** | 15（早停，mAP 上升慢）|
| **mAP50** | **0.6511** |
| **mAP50-95** | **0.3252** |
| 权重 | `runs/neu_yolo11n/weights/best.pt` |
| 结论 | NEU 原始数据 mAP 仅 0.65，远低于公开研究 0.78~0.80，**说明需要数据增强** |
| 是否部署 | ❌（基线太低）|

---

## 3. 实验 3：neu_yolo11n_640 ⭐（**最终基线**）

| 维度 | 取值 |
|------|------|
| 目的 | 跑更长 + 数据增强（augment_neu.py 输出 5760 张）→ 逼近公开数据上限 |
| 数据集 | `data_neu_aug.yaml`（NEU 1440 + 增强 4320 = 5760）|
| 训练集大小 | 5760 |
| 验证集大小 | 360（纯 NEU 原图，**增强集未污染 val**）|
| 模型 | yolo11n.pt 预训练 |
| 优化器 | auto（SGD）|
| epochs | 200 |
| batch | 16 |
| imgsz | 640 |
| lr0 | 0.01 |
| 增强 | 默认（mosaic=1.0, mixup=0.15, copy_paste=0.1）|
| 训练时间 | 约 1.5 小时 |
| **best epoch** | 181 |
| **mAP50** | **0.8013**（在 val 360 上）|
| **mAP50-95** | **0.4389** |
| 权重 | `runs/neu_yolo11n_640/weights/best.pt`（**主模型**）|
| 板端 | `best_neu6_640.rknn`（FP16，7.5MB）→ `best_neu6.rknn`（替换前）|
| 结论 | **mAP 0.8013 接近公开数据上限**，定为本项目基线。后续所有微调都从此权重热启动 |
| 是否部署 | ✅ **主部署模型（双模型级联的判类主力）**|

---

## 4. 实验 4：neu_yolo11n_aug（增强 + 320 分辨率）

| 维度 | 取值 |
|------|------|
| 目的 | 测试小分辨率（320）的训练效果 |
| 数据集 | `data_neu_aug.yaml`（同实验 3）|
| 训练集大小 | 5760 |
| imgsz | **320** |
| 训练 epoch | 60（续训 from _640 失败，回退到 320 重训）|
| **best epoch** | 59 |
| **mAP50** | **0.7516** |
| 结论 | 320 < 640 训练，mAP 0.7516 < 0.8013，**且推理时 320 训练的权重用 640 输入会失配** |
| 是否部署 | ❌（分辨率失配问题）|

---

## 5. 实验 5：neu_yolo11n_aug2（修复假增强集后重训）

| 维度 | 取值 |
|------|------|
| 目的 | 修复 `augment_neu.py` 的 `cv2.imwrite` 中文路径静默失败 bug 后，重跑增强 + 重训 |
| 数据集 | `data_neu_aug.yaml`（**真增强集** 5760 + 5760 标签，0 孤儿）|
| 模型 | **热启动 `_640/best.pt`** |
| 优化器 | AdamW |
| epochs | 150 |
| batch | 16（首次跑 batch=64 显存爆，回退 16）|
| imgsz | 640 |
| lr0 | 0.001（热启动小学习率）|
| lrf | 0.01 |
| 增强 | mosaic=0.9, mixup=0.15, copy_paste=0.1 |
| 训练时间 | 约 1 小时 |
| **best epoch** | 77 |
| **mAP50** | **0.7767** |
| 结论 | mAP 0.7767 **< 基线 _640 0.8013**。**热启动后增强没带来收益**——模型已饱和。**不部署** |
| 是否部署 | ❌（mAP 退化）|

---

## 6. 实验 6：neu_yolo11n_aug2_interrupted_1ep（batch=64 显存爆）

| 维度 | 取值 |
|------|------|
| 目的 | 试 batch=64 加速训练 |
| batch | 64 |
| 显存占用 | 7808/8151 MiB（贴顶）|
| 训练时间 | 165s/it（vs 16 batch 的 0.36s/it，慢了 460 倍）|
| 状态 | 1 epoch 后中断 |
| 结论 | 8GB 卡 batch 64 不可用，**永远跑不下去**。已永久回退 batch=16 |
| 是否部署 | ❌（中断）|

---

## 7. 实验 7：neu_yolo11n_aug2_partial_2ep

| 维度 | 取值 |
|------|------|
| 目的 | 续训实验 6 |
| batch | 64（仍太大）|
| 状态 | 2 epoch 跑不动，已废弃 |
| 结论 | 旧版本残留，无意义，**目录可删除** |
| 是否部署 | ❌（废弃）|

---

## 8. 实验 8：neu_yolo11n_negdagm ⭐（**负样本 1:1**）

| 维度 | 取值 |
|------|------|
| 目的 | 解决 _640 模型对"无缺陷纹理"严重误检（NEU 裁块 35.5%、DAGM 64.4%）|
| 数据集 | `data_neu_dagm.yaml`（NEU 1440 + DAGM 1440 1:1 混合 = 2880）|
| 模型 | **热启动 `_640/best.pt`** |
| 优化器 | AdamW |
| epochs | 100 |
| batch | 16 |
| imgsz | 640 |
| lr0 | 0.0005（**极低**，防灾难性遗忘）|
| lrf | 0.01 |
| 训练时间 | 约 1.8 小时 |
| **best epoch** | 87 |
| **mAP50** | **0.7849** |
| 板端 | `best_negdagm.rknn`（FP16，7.5MB）→ 重命名为 `negdagm_filter.rknn`（级联 filter）|
| A/B 验收 | DAGM 误检 64.4% → 0%；180 真实图 top1 97.8% → 95.6%（crazing/scratches 退化）|
| 结论 | **误检归零，但真实缺陷 top1 掉 2.2pt**。**单模型不可部署**（用于级联 filter 路径）|
| 是否部署 | ✅ **级联 filter 路径**（不是单独部署）|

---

## 9. 实验 9：neu_yolo11n_negdagm_half（负样本 1:2 轻量回炉）

| 维度 | 取值 |
|------|------|
| 目的 | 方案 A：把负样本比例从 1:1 降到 1:2，验证是否能在误检 vs top1 之间找平衡 |
| 数据集 | `data_neu_dagm_half.yaml`（NEU 1440 + DAGM 720 1:2 = 2160）|
| 模型 | 热启动 `_640/best.pt` |
| 优化器 | AdamW |
| epochs | 100 |
| batch | 16 |
| imgsz | 640 |
| lr0 | 0.0005 |
| **best epoch** | 88 |
| **mAP50** | **0.7865** |
| A/B 验收 | DAGM 误检仍 0%、180 图 top1 仍 95.6%（**与 1:1 完全一致**）|
| 结论 | **降负样本比例不能解耦 trade-off**——只要混负样本就会让 crazing/scratches 退化。**不部署**（已归档）|
| 是否部署 | ❌（与 1:1 退化相同）|

---

## 10. 实验 10：neu_yolo11n_crazing_focus（crazing 专项攻坚）

| 维度 | 取值 |
|------|------|
| 目的 | crazing 是统一最弱类（cal R=0.431, holdout R=0.597），专项微调提升召回 |
| 数据集 | `data_crazing_focus.yaml`（NEU crazing 239 + DAGM 239 1:1 = 478）|
| val | cal 178（隔离 holdout）|
| 模型 | 热启动 `_640/best.pt` |
| 优化器 | AdamW |
| epochs | **30（短微调）** |
| batch | 16 |
| imgsz | 640 |
| lr0 | **1e-5（极低）** |
| 增强 | 弱增强（mosaic=0.5, scale=0.3）|
| 训练时间 | **7 分钟**（数据量小）|
| **best epoch** | 29 |
| **mAP50**（专项 val）| **0.6963** |
| holdout A/B 验收 | crazing R: 0.597 → 0.611（+1.4pt，几乎无变化）<br>整体 mAP50: **0.7393 → 0.5020（-24pt，灾难性遗忘）**<br>其它 5 类 inclusion -32pt, pitted_surface -49pt, rolled-in_scale -52pt |
| 结论 | **crazing 召回本质是模型特征问题**，不是微调/数据能解决。**专项微调导致严重灾难性遗忘**——权重不可部署。详见 `output/rk3588_followup_plan/crazing专项微调实验报告.md` |
| 是否部署 | ❌（灾难性遗忘，仅作反面教材归档）|

---

## 11. 实验 11：级联服务（**最终生产部署**）

| 维度 | 取值 |
|------|------|
| 目的 | 把"误检归零"和"top1 97.8%"组合起来——单模型无法同时满足 |
| 部署目录 | 板端 `/root/rknn/` |
| 模型 1（filter）| `negdagm_filter.rknn`（= 实验 8 权重，FP16，7.5MB）|
| 模型 2（判类）| `best_neu6_640.rknn`（= 实验 3 权重，FP16，7.5MB）|
| 服务脚本 | `部署/rk3588/board_server_cascade.py` |
| 启动脚本 | `/root/rknn/start_cascade.sh` |
| 自启 | `/etc/init.d/S99board`（已升级为级联版，旧版备份 `S99board.bak_20260918`）|
| 协议 | 与单模型 `board_server.py` 完全兼容，上位机零改动 |
| per-class 阈值 | crazing 0.25 / inclusion 0.16 / 其余 0.20 / scratches 0.30（09-20 改 crazing 0.20→0.25）|
| 端到端验收 | DAGM 误检 0% / 180 真实图 top1 97.8% / 延迟 p50=196ms p95=216ms（609 帧）|
| 论文引用 | `output/rk3588_followup_plan/级联端到端三维验收.md` |
| 是否部署 | ✅ **生产部署（2026-09-19 上线）**|

---

## 12. 评估与验收脚本清单

| 脚本 | 用途 | 数据 |
|------|------|------|
| `_dataset_check.py` | 数据完整性体检（训练前置必跑）| 4 个数据集 + cal/holdout |
| `_split_cal_holdout.py` | 切 cal/holdout 双集 | 178 cal + 182 holdout |
| `_eval_unified.py` | 统一评估（mAP50 + confusion matrix）| 4 模型 × 4 数据集 |
| `_verify_neg_ab.py` | 负样本重训 A/B 验收 | 4 模型 × DAGM |
| `_verify_neg_half_ab.py` | 1:1 vs 1:2 三维对比 | 3 模型 |
| `_ab_models.py` | 180 真实图 top1 | 4 模型 |
| `_ab_pc_vs_board.py` | PC vs 板端一致性 | 180 张 |
| `_scan_crazing_thres.py` | crazing 阈值扫描 | cal 集 9 点 |
| `_weekly_feedback.py` | 难例回流周报 | records.db |
| `_audit_labels_200.py` | NEU 标签审计 | 198 张 |
| `_verify_dagm_fp.py` | DAGM 误检验证 | DAGM 1200 张 |
| `_verify_cascade_board.py` | 级联板端验证 | 24 samples |

---

## 13. 论文写作素材映射

| 论文章节 | 引用本台账 | 引用报告 |
|---------|-----------|---------|
| 3.1 数据集 | 实验 3 | `neu_label_audit_summary.md` |
| 3.2 模型与训练 | 实验 3 / 8 / 9 | — |
| 4.1 基线 mAP | 实验 3 | 统一多模型对比表 |
| 4.2 数据增强消融 | 实验 4 / 5 | `本周工作汇总_0914-0917.md` |
| 4.3 负样本重训 | 实验 8 / 9 | `模型对比与结论_0917.md` |
| 4.4 双模型级联 | 实验 11 | `级联端到端三维验收.md` |
| 5.1 板端实测 | 实验 11 | `部署/rk3588/全量验证报告.md` |
| 5.2 per-class 阈值 | 实验 11 | `crazing攻坚_阈值vs微调_决策报告.md` |
| 6.1 弱类攻坚 | 实验 10 | `crazing专项微调实验报告.md` |
| 6.2 数据治理 | 实验 10 + 审计 | `neu_label_audit_summary.md` |
| 6.3 数据回流 | — | `_weekly_feedback.py` |
| 7.1 复现性 | 全部 11 实验 | **本台账** |

---

## 14. 后续可清理项

- 实验 6 / 7（aug2_interrupted / aug2_partial）目录可删除（已废弃）
- 实验 4（aug）目录保留作 320 vs 640 分辨率对比证据
- 实验 5（aug2）目录保留作"增强无效"反例证据
- 实验 9（negdagm_half）目录保留作"1:2 调比例无效"证据
- 实验 10（crazing_focus）目录保留作"专项微调灾难性遗忘"反面教材
