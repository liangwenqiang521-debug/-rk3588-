# 部署 / RK3588 板端

本目录包含 rk3588 工业缺陷检测项目的 **板端推理服务** + **转换工具** + **验收脚本**。
上位机（PC）通过 TCP 9000 连接板端，自动加载双模型级联服务（filter + 判类主力）。

> 对应开发路线图（docs/开发路线图.md）阶段 **P3 边缘端部署**。

## 1. 板端文件布局（/root/rknn/）

```
/root/rknn/
├── 启动与配置
│   ├── start_srv.sh              # 旧版单模型启动（已不推荐）
│   ├── start_cascade.sh         # **级联版启动（生产用）**
│   └── S99board                  # 开机自启 init 脚本（级联版）
├── 模型权重
│   ├── best_neu6_640.rknn        # 判类主力（_640，7.5MB FP16）
│   ├── negdagm_filter.rknn      # 过滤器（negdagm，7.5MB FP16）
│   ├── backup_best_neu6_negdagm_20260918.rknn  # 09-18 老 negdagm 备份
│   └── S99board.bak_20260920    # 旧版自启备份
├── 推理服务源码
│   ├── board_server.py           # 旧版单模型
│   └── board_server_cascade.py  # **新版级联（生产用）**
├── 诊断工具
│   ├── board_infer.py            # 单图推理（手动调试）
│   ├── diag_cls.py               # 分类头诊断
│   ├── diag_conf.py              # 置信度分布
│   ├── deep_diag2.py             # 深度诊断
│   ├── bench_cores.py            # CPU 性能测试
│   └── library (lib/)            # RKNN-Toolkit2 工具链
├── 样本与日志
│   ├── samples/                  # 24 张 NEU 样本（6 类 × 4 张）
│   ├── samples_synth_bak/        # 合成样本备份
│   ├── testset/                  # 旧测试集
│   ├── server.log                 # 旧单模型运行日志
│   ├── server_cascade.log        # **级联运行日志（生产用）**
│   ├── boot.log / boot_cascade.log  # 自启启动日志
│   └── boardip.log                # 双 IP 固化日志
└── ref_output_opset12.npy / test_input_uint8.npy  # INT8 调试用（已弃用）
```

## 2. 通信协议

TCP 9000，JSON 文本行。

**服务推送（板端 → 上位机）：**

```json
{
  "frame": 1234,
  "ok": true,                 // 无缺陷 = true；有缺陷 = false
  "defects": [                // 有缺陷时填充
    {
      "cls": "inclusion",
      "cls_id": 1,
      "conf": 0.82,
      "x1": 12.3, "y1": 45.6,
      "x2": 78.9, "y2": 110.1
    }
  ],
  "infer_ms": 196.3,         // 级联两遍总耗时
  "w": 640, "h": 640,
  "src": "crazing_01.jpg",
  "img_b64": "..."           // 板端回传图（base64）
}
```

**健康推送**（每 N 帧一次）：

```json
{
  "type": "stats",
  "core0": 35.2, "core1": 28.7, "core2": 30.1, "core3": 31.5,
  "npu": 45.0,               // NPU 占用率
  "temp": 52.3,              // NPU 温度（°C）
  "mem_used": 1820, "mem_total": 7780, "mem_available": 5960,
  "fps": 5.0,                // 实际推理帧率
  "infer_ms": 196.3,         // 当前帧耗时
  "model": "cascade(negdagm+_640)"
}
```

**上位机控制**（通过 `board_ssh.py` 直接 shell，不经 TCP 9000）。

## 3. 启动与维护

### 启动

```bash
# 手动启动级联
sh /root/rknn/start_cascade.sh

# 重启
/etc/init.d/S99board restart

# 查状态
ps aux | grep board_server
tail -n 20 /root/rknn/server_cascade.log
```

### S99board 自启（已切级联版）

板子掉电重启后会自动：
1. 固化双 IP（静态地址 + 链路本地地址，具体值见 `S98boardip`）
2. 启动级联服务（级联版 `board_server_cascade.py`）

旧版备份：`/root/rknn/S99board.bak_20260920`

## 4. 工具脚本

| 脚本 | 目的 | 用法 |
|------|------|------|
| `board_ssh.py` | 板端 SSH 工具（paramiko）| `python board_ssh.py "ps aux"` |
| `_sftp_fast_put.py` | 大块 SFTP 上传（78MB/s）| 已被 `board_ssh.py --put` 取代 |
| `_verify_cascade_board.py` | 级联板端验证（24 sample）| 上传后跑 |
| `_test_perclass_thresh.py` | per-class 阈值单图测试 | 上传后跑 |
| `_board_infer.py` | 手动单图推理 | 调试用 |
| `_board_export_rknn.py` | 板端 ONNX → RKNN 转换 | 板端环境内运行 |
| `S99board.cascade` | 升级版自启脚本模板 | 已部署到 /etc/init.d/ |

PC 端工具在项目根目录：

| 脚本 | 目的 |
|------|------|
| `board_ssh.py` | SSH 通用工具（推荐）|
| `_diag_onnx.py` | ONNX 推理（外部基线）|
| `_e2e_check.py` | 端到端检查 |
| `_func_test.py` / `_regress_crash.py` | 上位机功能测试 |

## 5. 关键性能数据（609 帧实测）

| 指标 | _640 单模型 | 级联（filter+_640） |
|------|------------|--------------------|
| p50 延迟 | 70 ms | **196 ms**（5 FPS）|
| p95 延迟 | 80 ms | 216 ms |
| p99 延迟 | — | 223 ms |
| NPU 占用 | ~25% | ~45% |
| NPU 温度 | ~50°C | ~55°C |

## 6. per-class 阈值表（已落地）

```python
PER_CLASS_THRES = {
    'crazing':         0.25,   # 09-20 cal 阈值扫描：F1 +0.024
    'inclusion':       0.16,   # 降阈保召回
    'patches':         0.20,
    'pitted_surface':  0.20,
    'rolled_in_scale': 0.20,
    'scratches':       0.30,   # 升阈压误报
}
```

## 7. 关键经验

1. **FP16 而非 INT8** — 见 `../docs/rknn_int8_bug.md`，INT8 分类头会被压塌
2. **双模型级联** — 误检 0% + top1 97.8% 双保留，单模型无法同时满足
3. **掉电自启** — S99board 已切级联版，板子掉电自动拉起
4. **APIPA 直连** — 板子 eth0 配「静态 IP + 链路本地(169.254.x.x)」双地址，PC 端零配置即可直连
5. **ssh 密钥** — `~/.ssh/id_ed25519` 免密认证（路径可用 `BOARD_KEY` 覆盖）

## 8. 详细文档

- `../docs/rknn_int8_bug.md` — INT8 分类头塌陷根因 + 规避
- `../experiments/runs_log.md` — 11 次实验台账
- `../output/rk3588_followup_plan/级联端到端三维验收.md` — 误检 0% + top1 97.8% + 延迟分布验收
- `../docs/项目纪要.md` — 板端硬约定与工程约定
