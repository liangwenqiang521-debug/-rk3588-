# 板端默认 step 模式 —— 落地验收报告

> 日期：2026-09-21
> 范围：板端级联服务默认运行模式由 stream 改为 step，及全链路打通验收
> 结论：**已完成并验收通过**（过程中发现并修复 2 个阻断性 bug）

---

## 1. 为什么要改

stream 模式下板端自循环 24 张 sample 无限轮播、持续推帧写库，上位机画面永远在动。
真实产线语义应当是**「相机来一帧 → 推一帧」的按需模式**，因此把默认值改为 step：
只有收到上位机 `cmd=next` 才推下一帧。

---

## 2. 改动清单

### 板端 `board_server_cascade.py`（已上板，PID 2354）

| 项 | 内容 |
|---|---|
| 默认值 | `MODE = 'stream' if '--stream' in sys.argv else 'step'` |
| 防黑屏 | step 模式下客户端接入瞬间补推一帧，之后等 `cmd=next` |
| **发送超时修复** | `settimeout(0.3)` → `5.0`；超时不再判死客户端（详见 §3 Bug 2）|
| 推理循环加固 | `_infer_loop_step` 包异常保护，异常不再静默终止整个循环 |
| 诊断日志 | 收到指令时打印 `[cmd] ...` |

### 上位机 `page_detect.py`

| 项 | 内容 |
|---|---|
| 心跳定时器 | 抽出 `_ensure_step_timer(on)`，按 1 秒节拍发 `cmd=next`（0.5/1/2 秒三档随速度下拉）|
| 驱动点 | `_start()` / `_stop()` / `_on_auto_detect_toggled()` / `_on_edge_connected()` 四处同步；`_stop_edge()` 断开前停表 |

### `dagm_monitor.py`（占位 → 真实实现）

此前卡在两个前置条件（step 模式 + 外部图片送检），现已满足，实现为真正的域外误检监控：
抽样 DAGM val → 走 `detect_img` 协议逐张送检 → 统计误检率。

- 用法：`python dagm_monitor.py --n 20`（默认 30，`--all` 全量 1200）
- 日志双写：本地 `output/dagm_monitor/dagm_monitor.log` + 板端 `/root/rknn/dagm_monitor.log`
- 告警线 5%；参考基线：_640 64.4%，级联目标 0%

---

## 3. 排查出的两个阻断性 bug

### Bug 1（上位机）：心跳定时器从未启动

`_start()` 直接给 `_edge_detect_enabled = True` 并赋值 `sw.on = True`，
但**自定义开关赋值不触发 Qt 信号** → `_on_auto_detect_toggled()` 未被调用 → 定时器没建。
表现为：点「开始检测」后没人发 `cmd=next`，板端等到天荒地老，统计恒为 0。

**修复**：抽成 `_ensure_step_timer()`，在 4 处显式驱动。

### Bug 2（板端，根因）：0.3 秒发送超时把上位机踢下线

`_sender_loop` 原逻辑 `c.settimeout(0.3)` + `sendall`，**超时即判定客户端死亡并 `close()`**。
每帧 `img_b64` 几百 KB，上位机只要读慢一点，板端 0.3 秒内没发完就踢掉连接；
之后上位机发的 `cmd=next` 全部落空，而**`sendall` 仍然返回成功**——现象是「推一两帧后再也不动」，极难排查。

**修复**：超时放宽到 5 秒；仅 `BrokenPipeError / ConnectionResetError / OSError` 判死，
`TimeoutError` 只丢弃本轮、保留连接（注意 `TimeoutError` 是 `OSError` 子类，except 顺序必须先它）。

> 直接证据：板端日志 13 次发送只收到 1 次 `[cmd] 'next'`；
> 纯 socket 对照实验第 2 次发送即 `WinError 10053`（连接被主机中止）。

---

## 4. 验收数据

| 项目 | 修复前 | 修复后 |
|---|---|---|
| 端到端 15 秒 | **1 件** | **15 件** |
| 60 秒浸泡 | — | **59 件，零断流**（稳定 1 件/秒）|
| 纯 socket 连发 5 次 next | 第 2 次即被踢（10053） | **5/5 全部响应** |
| DAGM 域外误检 | 只能间接看日志 | **20 张 0 误检，平均 83 ms** |

浸泡测试明细（60 秒）：t=10s→9 件，t=20s→19，t=30s→29，t=40s→39，t=50s→49，t=60s→59，无断流告警。

**自启一致性**：`S99board` → `start_cascade.sh`（不带 `--stream`）→ 掉电重启同样是 step 模式。

---

## 5. 可复跑的诊断脚本

| 脚本 | 用途 |
|---|---|
| `_pc_sock_test.py` | 纯 socket 连发 next，隔离「板端/网络问题」与「上位机框架问题」 |
| `_diag_step.py` | 分步诊断：定时器状态 → `send_cmd` 返回值 → 板端帧数增量 |
| `_step_soak.py` | 60 秒浸泡 + 断流检测（连续 8 秒无新增即告警） |

排查顺序建议：先看定时器是否 active（Bug 1 类），再看 `send_cmd` 返回值，
最后用纯 socket 对照确认板端是否踢客户端（Bug 2 类）。

---

## 6. 遗留建议

- step 节拍目前固定 1 秒（模拟 5 FPS）。真实相机接入后应改为**由相机帧驱动**而非定时器。
- 每帧都回传 `img_b64` 是带宽大头，若后续延迟吃紧，可考虑只在 NG 帧回传图像。
