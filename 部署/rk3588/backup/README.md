# /root/rknn/backup/ 目录

存放关键权重的**带日期版本**，用于掉电/误操作后快速恢复。

## 备份规则

每次有重要权重变更（训练完成、阈值调整后重新转换），拷一份到 `backup/YYYYMMDD/`：
- 文件名用 `{训练标识}_{分辨率}_{精度}.rknn` 格式
- 同一权重只在**第一次上线**时备份（不每次轮训都拷）

## 文件清单

| 日期 | 文件名 | 来源 | 验证 |
|------|--------|------|------|
| 20260920 | `640_640x640_FP16.rknn` | `runs/neu_yolo11n_640/weights/best.pt` → `best_neu6_640.rknn`（级联判类主力）| holdout mAP50=0.7393，180 图 top1=97.8% |
| 20260920 | `negdagm_1to1_640x640_FP16.rknn` | `runs/neu_yolo11n_negdagm/weights/best.pt` → `negdagm_filter.rknn`（级联 filter）| DAGM val 误检 0% |
| 20260920 | `../../backup_best_neu6_negdagm_20260918.rknn` | 09-18 老 negdagm（被级联替代前的单模型版本）| 仅供参考，已不部署 |
| 20260920 | `../../S99board.bak_20260920` | 旧版自启脚本（单模型）| 应急回滚用 |

## 部署权重当前路径

`/root/rknn/best_neu6_640.rknn` 和 `/root/rknn/negdagm_filter.rknn` 是线上权重。
`/root/rknn/backup/20260920/` 是**带验证信息的版本**。

## 恢复流程

如果线上权重被误改 / 损坏：

```bash
# 确认是最新版本
md5sum /root/rknn/best_neu6_640.rknn
md5sum /root/rknn/backup/20260920/640_640x640_FP16.rknn

# 不一致则恢复
cp /root/rknn/backup/20260920/640_640x640_FP16.rknn /root/rknn/best_neu6_640.rknn
cp /root/rknn/backup/20260920/negdagm_1to1_640x640_FP16.rknn /root/rknn/negdagm_filter.rknn

# 重启级联
/etc/init.d/S99board restart
```
