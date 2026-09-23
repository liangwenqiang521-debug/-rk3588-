# models_cards/ — 模型元信息卡

每个 RKNN 权重配一个 JSON，记录：
- **来源**（哪个 .pt 转的）
- **训练**（epochs / batch / lr0 / 优化器 / 种子 / 日期）
- **数据**（训练集 / 验证集 / 增强策略）
- **指标**（holdout mAP50 / DAGM 误检 / 180 真实图 top1）
- **部署**（pairing / 路径 / 日期 / per-class 阈值）

## 文件清单

| 文件 | 模型 | 部署角色 |
|------|------|----------|
| `negdagm_filter.json` | `negdagm_filter.rknn` | 级联第一遍（判有无缺陷）|
| `best_neu6_640.json` | `best_neu6_640.rknn` | 级联第二遍（精判类别）|

## 用法

部署时把 cards 拷到板端对应目录：

```bash
# PC 端
python board_ssh.py --put models_cards/negdagm_filter.json /root/rknn/
python board_ssh.py --put models_cards/best_neu6_640.json /root/rknn/

# 板端查看（先 cat 再看 cat 模型 + 阈值是否一致）
cat /root/rknn/negdagm_filter.json | python -m json.tool | head -30
```

## 命名规范

`{训练标识}_{分辨率}_{精度}.rknn` 与 `cards/{训练标识}.json` 一一对应：
- `negdagm_filter.rknn` ↔ `negdagm_filter.json`
- `best_neu6_640.rknn` ↔ `best_neu6_640.json`

## 更新时机

- 重新训练 → 更新对应 json 的 training / metrics 字段
- 修改 per-class 阈值 → 更新对应 json 的 per_class_thresholds 字段
- 部署新模型 → 新建一个 .json + 同步到板端
