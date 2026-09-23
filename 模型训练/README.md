# 模型训练（NEU 钢材表面缺陷检测）

本目录包含 rk3588 工业缺陷检测项目的 **YOLO 模型训练** 完整流程。
与 PyQt5 上位机解耦，独立产出可用于转 RKNN / 接入级联服务的模型权重。

> 对应开发路线图（docs/开发路线图.md）阶段 **P1 数据** 与 **P2 模型训练与转换**。
> 当前实际数据：NEU-DET 6 类（crazing 龟裂 / inclusion 夹杂 / patches 斑块 / pitted_surface 凹坑 / rolled-in_scale 压入氧化皮 / scratches 划痕），共 1800 张 200×200 灰度图。
> 最终部署形态：**双模型级联**（negdagm 判有无缺陷 + _640 精判类别），跑在 RK3588 NPU。

## 1. 数据集布局

```
datasets/
├── neu_det/             # NEU 原始 6 类（train 1440 + val 360）
├── neu_det_aug/         # NEU 增强（5760 张，09-17 修复 cv2.imwrite 后）
├── neu_det_cal/         # 09-20 切分：cal 178 + holdout 182
│   ├── images/{cal,holdout}/
│   └── labels/{cal,holdout}/
├── dagm_neg/            # DAGM 2007 6000 张无缺陷（train 4800 + val 1200）
├── neu_det_dagm/        # 1:1 混合（2880 张，negdagm 训练用）
├── neu_det_dagm_half/   # 1:2 混合（2160 张，negdagm_half 训练用）
└── crazing_focus/       # crazing 专项微调（478 张，灾难性遗忘教训）
```

## 2. 训练脚本（11 个核心）

| 脚本 | 目的 | 输出 |
|------|------|------|
| `neu2yolo.py` | NEU 原图 → YOLO 格式转换 | `datasets/neu_det/` |
| `augment_neu.py` | 数据增强（5760 张）| `datasets/neu_det_aug/` |
| `_split_cal_holdout.py` | 09-20 切 NEU val → cal/holdout 双集 | `datasets/neu_det_cal/` |
| `_dagm_to_neg.py` | DAGM → YOLO 空标签负样本 | `datasets/dagm_neg/` |
| `_build_mixed_dataset.py` | 构造 NEU + DAGM 1:1 混合 | `datasets/neu_det_dagm/` |
| `train_neg_dagm.py` | **负样本 1:1 训练（filter 主力）**| `runs/neu_yolo11n_negdagm/` |
| `train_neg_dagm_half.py` | 负样本 1:2 训练（证明 trade-off 不可解）| `runs/neu_yolo11n_negdagm_half/` |
| `_build_crazing_focus.py` | crazing 专项集 | `datasets/crazing_focus/` |
| `train_crazing_focus.py` | crazing 专项微调（**不可部署，反面教材**）| `runs/neu_yolo11n_crazing_focus/` |
| `train.py` | 旧版 baseline 训练（已被 09-16 训练取代）| — |
| `export_rknn.py` | 训练完导出 RKNN 转换脚本 | `.rknn` |

**所有 train_*.py 已加 `_precheck_dataset()` 前置必跑**（永久防 cv2 中文路径静默事故）。

## 3. 评估脚本（5 个核心）

| 脚本 | 目的 |
|------|------|
| **`_dataset_check.py`** | 数据完整性体检（训练前置必跑）|
| **`_eval_unified.py`** | 统一评估：mAP50 + 6x6 confusion matrix + Top-10 混淆对 + per-class 阈值 |
| `_verify_neg_ab.py` | 负样本重训 A/B 验收（DAGM 误检）|
| `_verify_neg_half_ab.py` | 1:1 vs 1:2 三维对比 |
| `_ab_models.py` | 180 真实图 top-1 对比 |
| `_ab_pc_vs_board.py` | PC（.pt/.onnx）vs 板端（.rknn）一致性 |
| `_scan_crazing_thres.py` | crazing 9 点阈值扫描 |
| `_audit_labels_200.py` | NEU 标签审计 198 张 |

## 4. 关键数据

| 模型 | mAP50 (holdout) | DAGM 误检 | 部署？ |
|------|----------------|------------|------|
| `_640` 基线 | **0.7393** | 64.4% | ✅ 级联判类主力 |
| `negdagm(1:1)` | 0.7300 | **0%** | ✅ 级联 filter |
| `negdagm_half(1:2)` | 0.7224 | 0% | ❌ 与 1:1 退化相同 |
| `crazing_focus` | 0.6963 | — | ❌ 灾难性遗忘，反面教材 |
| **级联（filter+_640）** | **0.7393** | **0%** | ✅ **生产部署** |

## 5. 训练配置基线

- 模型：YOLOv11n 原始架构（无网络结构修改）
- 优化器：AdamW / SGD auto
- batch=16，imgsz=640
- lr0=0.0005~0.01（按热启动 vs 从零区分）
- 数据增强：mosaic / mixup / HSV / flip（ultralytics 默认）
- 训练环境：PC + RTX 5060 8GB
- 固定随机种子 42（保证可复现）

## 6. 复现实验

```bash
# 1) 训练主模型
venv_cuda/Scripts/python.exe train_neg_dagm.py
# → runs/neu_yolo11n_negdagm/weights/best.pt

# 2) 训练主力 _640
# 跑 augment_neu.py → continue_neu.py 或从头跑（参考 runs/neu_yolo11n_640/args.yaml）

# 3) 转 RKNN（在板端 /root/rknn_convert/）
# 上传 best.pt → best.onnx → 用 RKNN-Toolkit2 转 .rknn
# 详见 部署/rk3588/board_server_cascade.py 启动流程

# 4) 板端启动级联
# 板端: sh /root/rknn/start_cascade.sh
# PC: board_ssh.py "ps aux | grep board_server" 确认进程
```

## 7. 详细文档

- `experiments/runs_log.md` — 11 次实验台账（完整复现性）
- `output/rk3588_followup_plan/` — 后续工作计划 + 4 周节奏
- `docs/rknn_int8_bug.md` — RKNN INT8 量化分类头塌陷问题（**已规避，维持 FP16**）
- `docs/开发路线图.md` — 项目总路线图
- `.workbuddy/memory/MEMORY.md` — 长期事实

## 8. 教训（避免重蹈覆辙）

1. **cv2.imwrite 中文路径静默失败** → 用 imencode+tofile 或 np.fromfile+imdecode
2. **假增强集** → 增强前必须 `_dataset_check.py` 体检
3. **负样本重训 trade-off** → 单模型无法同时"误检 0% + top1 97.8%"，必须级联
4. **专项微调灾难性遗忘** → 不要在 6 类混训的数据集外单独微调
5. **per-class 阈值表只在 crazing 0.25 有效** → 其余统一回 0.20 简化代码
