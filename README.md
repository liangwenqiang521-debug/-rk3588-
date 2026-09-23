# 工业缺陷检测上位机（PyQt5 6 页）+ RK3588 边缘级联服务

> **项目目标**：基于国产化 RK3588 边缘计算平台，构建一套可工程化部署的工业钢材表面缺陷检测系统。
> 训练在 PC（RTX 5060），推理在板端（RK3588 NPU），最终形态为**双模型级联**（negdagm 判有无缺陷 + _640 精判类别）。

> **当前状态**（2026-09-20）：上位机 + 板端全链路打通，级联方案生产部署，论文 v2 已生成。
> **关键数字**：holdout mAP50 = **0.7393** / DAGM 域外误检 **0%** / 180 张真实图 top1 **97.8%** / 板端 p50 延迟 **196 ms（约 5 FPS）**。

## 1. 目录结构

```
缺陷检测项目/
├── main.py                       # 上位机入口（PyQt5）
├── config.py / db.py / logger.py # 上位机核心模块
├── widgets.py / utils.py         # 上位机公共组件
├── npu_monitor.py                # 上位机 NPU 监控页
├── page_*.py                     # 上位机 6 个页面
│   ├── page_main.py              # 主页（导航）
│   ├── page_detect.py            # 实时检测（核心）
│   ├── page_history.py           # 历史记录
│   ├── page_comm.py              # 通信设置
│   ├── page_param.py             # 参数设置
│   ├── page_log.py               # 运行日志
│   └── page_npu.py               # NPU 监控
├── infer.py / tcp_bridge.py      # 上位机 ↔ 板端 TCP 9000
├── serial_bridge.py              # 上位机 ↔ 串口/PLC
├── board_ssh.py                  # ★ 板端 SSH 通用工具（推荐）
├── board_health.py               # ★ 板端健康检查（5 分钟一次）
├── 模型训练/                      # 训练侧（独立目录）
│   ├── README.md                 # 训练脚本 + 工具索引
│   ├── train_*.py / _eval_unified.py / _dataset_check.py
│   └── datasets/                 # neu_det / neu_det_cal / dagm_neg / mixed / crazing_focus
├── 部署/rk3588/                  # 板端工具与配置
│   ├── README.md                 # 板端目录索引
│   ├── board_server_cascade.py   # ★ 级联服务（生产用，部署到 /root/rknn/）
│   ├── board_server.py           # 旧版单模型
│   ├── S99board.cascade          # 自启脚本模板
│   └── backup/                   # 权重带日期版本（防掉电）
├── docs/                          # 文档
│   ├── 开发路线图.md              # 项目总路线图（6 个阶段 P0-P6）
│   └── rknn_int8_bug.md          # RKNN INT8 量化分类头塌陷问题
├── experiments/                   # 实验台账
│   └── runs_log.md               # 11 次训练实验的完整台账
├── output/rk3588_followup_plan/  # 后续工作计划与验收报告
│   ├── rk3588_后续工作计划.md
│   ├── 统一多模型对比表.md
│   ├── 级联端到端三维验收.md
│   ├── crazing专项微调实验报告.md
│   ├── crazing攻坚_阈值vs微调_决策报告.md
│   └── neu_label_audit_summary.md
├── 论文初稿/
│   ├── 基于RK3588的轻量化工业缺陷检测系统研究（v2）.docx  # ★ 当前论文版本
│   ├── _build_paper_v2.py        # 论文 v2 重建脚本
│   ├── make_figs.py              # 图件生成
│   └── fig[1-6]_*.png            # 论文配图
├── _hardpool/                    # 难例回流周报（每周日自动生成）
│   └── 2026-09-20/               # 第一期：2 张 crazing 难例
├── board_env.py                  # ★ 板端连接参数统一入口（环境变量 / 本地私有文件）
├── board_env.example.py          # 本地配置模板
├── 部署指南.md                    # 旧版部署文档（已被 部署/rk3588/README.md 取代）
└── 本周工作汇总_0914-0917.md / 模型对比与结论_0917.md  # 旧版工作笔记
```

> **不随仓库分发**：训练数据集、模型权重、板端 wheel 包、Python 虚拟环境、
> 以及含真实 IP/凭据的本地配置（`board_env.local.py`、`config.json`）。
> 详见 `.gitignore`。

## 2. 快速开始

### 2.0 环境与配置

```bash
# 1) 安装依赖（建议 Python 3.10+）
pip install -r requirements.txt

# 2) 配置板端连接参数（可选，仅连板子时需要）
cp board_env.example.py board_env.local.py   # 填入你的板子 IP / 账号
# 或改用环境变量（优先级更高）：set BOARD_IP=192.168.1.20
```

> **凭据不入库**：所有板端 IP / 密码 / 密钥路径统一由 `board_env.py` 读取
> （环境变量 > `board_env.local.py` > 占位默认值）。`board_env.local.py`
> 已在 `.gitignore` 中，不会被提交。

### 2.1 上位机

```bash
python main.py
```

### 2.2 板端服务

```bash
# PC 端通过 SSH 工具
python board_ssh.py "/etc/init.d/S99board status"
python board_ssh.py "/etc/init.d/S99board restart"

# 健康检查（5 分钟一次，建议放任务计划）
python board_health.py
```

### 2.3 训练（在 `模型训练/`）

```bash
# 训练（带数据体检前置）
cd 模型训练
python train_neg_dagm.py

# 评估（holdout 隔离集）
python _eval_unified.py --model runs/neu_yolo11n_negdagm/weights/best.pt --data data_neu_holdout.yaml
```

> 训练数据集（NEU-DET / DAGM）与模型权重未随仓库分发，请按 `模型训练/README.md`
> 自行下载准备。评估前请先跑 `_dataset_check.py` 做数据集体检。

## 3. 关键决策与里程碑

| 日期 | 决策 | 结果 |
|------|------|------|
| 2026-09-14 | 切到 NEU 真实数据集（替换合成）| mAP 0.65 |
| 2026-09-16 | NEU 增强 200 轮 → `_640` 基线 | mAP 0.783（**生产基线**）|
| 2026-09-17 | 修复假增强集 bug（cv2.imwrite 中文路径）| mAP 0.776（不部署，反面教材）|
| 2026-09-18 | 负样本重训 1:1 → `negdagm` | DAGM 误检 0%（**filter**）|
| 2026-09-19 | 双模型级联上线 | 误检 0% + top1 97.8%（**生产部署**）|
| 2026-09-20 | crazing 阈值 0.20→0.25 | cal F1 +0.024 |
| 2026-09-20 | cal/holdout 切分 + 数据体检前置 | 评估口径可信 |
| 2026-09-20 | 论文 v2 生成 | 修正 mAP 0.959 误报、NEU 类别等错误 |
| 2026-09-21 | 上位机工程化优化（非阻塞采样 / 文件名唯一化 / step 心跳去重）| 主线程零阻塞 |
| 2026-09-22 | 缺陷类别体系 6 类 → 16 类全链路打通 | 体系就绪，扩展类待重训 |

## 4. 已知工程坑（避免重蹈覆辙）

- ⚠️ `cv2.imwrite/imread` 在 Windows 中文路径会静默失败 → 用 `np.fromfile + cv2.imdecode`
- ⚠️ 合成数据集 mAP 0.959 不可代表真实工业场景（已修正）
- ⚠️ 负样本重训 trade-off 不可解（误检 vs 检出）→ 必须双模型级联
- ⚠️ NEU 9.1% 跨类标注是数据集固有特征，不需清洗
- ⚠️ RKNN INT8 分类头会被压塌（已知 bug，本项目用 FP16）
- ⚠️ 级联服务必须用 S99board 启动，否则掉电后失效

详见 `docs/rknn_int8_bug.md` 和 `.workbuddy/memory/MEMORY.md`。

## 5. 文档地图

| 想了解什么 | 看哪里 |
|------------|-------|
| 项目总览和阶段划分 | `docs/开发路线图.md` |
| 训练流程 | `模型训练/README.md` |
| 板端部署 | `部署/rk3588/README.md` |
| 论文当前状态 | `论文初稿/基于RK3588的...（v2）.docx` |
| 实验台账（11 次训练）| `experiments/runs_log.md` |
| 后续工作计划 | `output/rk3588_followup_plan/rk3588_后续工作计划.md` |
| 任意一项的细节 | `output/rk3588_followup_plan/*.md` |
| 项目工程约定 | `docs/项目纪要.md` |
| 板端 INT8 量化 bug | `docs/rknn_int8_bug.md` |

## 6. 工具脚本速查

### 上位机（项目根）

| 脚本 | 用途 |
|------|------|
| `board_ssh.py "cmd"` | SSH 到板端跑命令（最常用）|
| `board_ssh.py --put local remote` | 大块 SFTP 上传（78MB/s）|
| `board_ssh.py --get remote local` | 大块 SFTP 下载 |
| `board_ssh.py --script local.sh --timeout N` | 上传并跑多行 shell |
| `board_health.py` | 板端健康检查（服务/磁盘/内存/NPU/温度/延迟）|
| `模型训练/_dataset_check.py` | 数据集完整性体检（训练前置）|
| `模型训练/_eval_unified.py` | 统一评估（mAP50 + confusion matrix）|
| `模型训练/_weekly_feedback.py` | 难例回流周报 |
| `模型训练/_audit_labels_200.py` | NEU 标签审计 |

## 7. 关键事实

- 板子 SSH：`root@<板子IP>`（推荐免密密钥认证；IP/账号经环境变量或 `board_env.local.py` 配置）
- 板端服务端口：TCP 9000
- 板端数据目录：`/root/rknn/`（含 2 个 RKNN 模型 + 启动脚本 + 日志）
- 自启链：`/etc/init.d/S99board`（已切级联版）
- 板端 8GB 内存已用 ~700MB（级联占约 200MB，余量充足）
- 模型体积：级联 2 × 7.5MB = 15MB（FP16，INT8 已知 bug 故未用）
- 训练环境：PC + 独立 CUDA venv（RTX 5060 8GB 实测）

## 8. 数据集与模型声明

- **NEU-DET**（东北大学热轧带钢表面缺陷数据集）与 **DAGM 2007** 版权归各自
  发布方所有，本仓库**不分发**这些数据集的原始数据与训练权重。
- 仓库内的 `图片/` 仅含少量演示用样本，用于上位机功能自测。
- 如用于论文或商业场景，请自行获取数据集授权并遵守其许可条款。

## 9. 许可

代码采用 [MIT License](LICENSE)。数据集与论文内容不适用该许可。
