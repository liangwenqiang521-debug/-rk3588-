# 工业缺陷检测上位机（PyQt5 6 页）+ RK3588 边缘级联服务

> **项目目标**：基于国产化 RK3588 边缘计算平台，构建一套可工程化部署的工业钢材表面缺陷检测系统。
> 训练在 PC（RTX 5060），推理在板端（RK3588 NPU），最终形态为**双模型级联**（negdagm 判有无缺陷 + _640 精判类别）。

> **当前状态**（2026-09-20）：上位机 + 板端全链路打通，级联方案生产部署，论文 v2 已生成。
> **关键数字**：holdout mAP50 = **0.7393** / DAGM 域外误检 **0%** / 180 张真实图 top1 **97.8%** / 板端 p50 延迟 **196 ms（约 5 FPS）**。

## 1. 目录结构

```
缺陷检测项目/
├── main.py                       # ★ 上位机入口（PyQt5，6 页面）
├── config.py / db.py / logger.py # 上位机核心模块
├── widgets.py / utils.py         # 上位机公共组件
├── npu_monitor.py                # NPU 监控采样
├── page_*.py                     # 6 个页面：实时检测/参数/历史/通信/日志/NPU
├── infer.py / tcp_bridge.py      # 推理引擎 + 上位机↔板端 TCP 桥
├── serial_bridge.py              # 上位机 ↔ 串口（PLC/相机触发）
├── model_manager.py              # 模型清单与热切换
│
├── board_env.py                  # ★ 板端连接参数统一入口（环境变量 > 本地私有文件 > 占位默认）
├── board_env.example.py          # 本地配置模板（复制为 board_env.local.py 后填真实值）
├── board_ssh.py                  # ★ 板端 SSH 通用工具（paramiko，支持 --net/--put/--get/--script）
├── board_health.py               # 板端健康监控（5 分钟一轮）
├── npu_watchdog.py               # NPU 异常自动重启（连续 3 次异常触发）
├── disk_guard.py                 # 板端 /root 磁盘守卫（>80% 清理）
├── dagm_monitor.py               # 域外误检长期监控（每小时）
│
├── tests/                        # ★ 回归测试与端到端验证
│   ├── _func_test.py             #   上位机全功能测试（28 项）
│   ├── _regress_crash.py         #   闪退回归（PyQt5 槽内异常防护）
│   ├── _ui_smoke.py              #   界面冒烟 + 截图落 _shots/
│   ├── _e2e_edge.py              #   边缘链路端到端
│   ├── _e2e_check.py             #   边缘连接检查
│   └── _test_*.py                #   停止/清除复位、step 模式、双模型等专项用例
│
├── tools/                        # ★ 诊断、验证与转换工具
│   ├── _diag_*.py                #   分层诊断（无帧、ONNX、step 模式）
│   ├── _pc_sock_test.py          #   纯 socket 对照（排除上位机干扰）
│   ├── _step_soak.py             #   step 模式浸泡测试 + 断流检测
│   ├── _shot*.py                 #   截图工具
│   ├── _verify_*.py              #   转换/新类别/边缘渲染验证
│   ├── _upload_convert.py        #   ONNX 上传板端转换
│   └── maintenance/              #   长期常驻维护脚本
│       ├── _weekly_feedback.py   #     难例回流（7 天）
│       └── _chk_boot.sh          #     板端起机状态检查
│
├── 模型训练/                      # 训练侧（独立目录，不依赖上位机）
│   ├── README.md                 #   训练脚本 + 工具索引
│   ├── train_*.py                #   训练入口（neu_yolo11n_640 / negdagm_filter 等）
│   ├── _eval_unified.py          #   ★ 统一评估口径（mAP + 混淆矩阵 + per-class 阈值）
│   ├── _dataset_check.py         #   训练前置体检（防空数据集 / 中文路径坑）
│   ├── _split_cal_holdout.py     #   cal/holdout 切分（调参在 cal，汇报在 holdout）
│   └── datasets/                 #   数据集（不入库）
│
├── 部署/rk3588/                  # 板端服务与自启配置
│   ├── README.md                 #   板端目录索引
│   ├── board_server_cascade.py   #   ★ 级联服务（生产用，部署到 /root/rknn/）
│   ├── board_server.py           #   旧版单模型服务
│   ├── S98boardip / S99board     #   自启脚本模板（双 IP + 服务拉起）
│   └── backup/                   #   权重带日期备份（防掉电）
│
├── docs/                          # 项目文档
│   ├── 项目纪要.md                #   硬约定 / 血泪坑 / 防膨胀机制（★ 新人先读）
│   ├── 开发路线图.md              #   6 阶段路线图（P0-P6）
│   ├── cascade_vs_single.md      #   级联 vs 单模型决策记录
│   └── rknn_int8_bug.md          #   RKNN INT8 分类头塌陷问题
│
├── experiments/runs_log.md        # 训练实验台账（每次训练的超参与结果）
├── output/rk3588_followup_plan/  # 后续工作计划与验收报告
├── 论文初稿/                      # 论文 v2 + 图件生成脚本 + fig[1-6].png
├── _hardpool/                     # 难例回流周报（每周日自动生成）
├── 图片/                          # 180 张真实测试图（6 类各 30 张）
├── 部署指南.md / 本周工作汇总_*.md / 模型对比与结论_*.md   # 阶段性工作笔记
└── LICENSE / requirements.txt / config.example.json
```

> **目录约定**：`tests/` 只放回归与端到端验证；`tools/` 放一次性诊断与转换辅助；
> `tools/maintenance/` 放长期常驻的维护脚本。
> 所有脚本均可**从任意目录直接运行**（内置 `sys.path` 回退到项目根）。


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
| `tests/_func_test.py` | 上位机全功能回归（28 项）|
| `tests/_e2e_edge.py` | 边缘链路端到端验证 |
| `tools/_pc_sock_test.py` | 纯 socket 对照测试（排除上位机干扰）|
| `tools/_step_soak.py` | step 模式浸泡测试 + 断流检测 |
| `模型训练/_dataset_check.py` | 数据集完整性体检（训练前置）|
| `模型训练/_eval_unified.py` | 统一评估（mAP50 + confusion matrix）|
| `tools/maintenance/_weekly_feedback.py` | 难例回流周报 |
| `模型训练/_audit_labels_200.py` | NEU 标签审计 |

> 所有脚本均支持**从任意目录运行**（内置 `sys.path` 回退到项目根），
> 例如 `python tests/_func_test.py` 与 `cd tests && python _func_test.py` 等价。


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
