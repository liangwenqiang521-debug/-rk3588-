# _hardpool/2026-09-20/ 难例核对报告

> 编制时间：2026-09-20 17:10
> 状态：**两张"难例"图都是 0 字节空文件，无法核对。**

## 1. 数据轨迹

按 `_weekly_feedback.py` 的逻辑，从 `records.db` 挑了 2 条低置信 crazing 记录：

| id | time | defect | conf | image_path |
|----|------|--------|------|-----------|
| 33810 | 2026-09-17 18:40 | crazing | **0.37** | D:/Inspect/Images/sample_5959.jpg |
| 33728 | 2026-09-17 16:23 | crazing | **0.38** | D:/Inspect/Images/sample_6610.jpg |

`_weekly_feedback.py` 的 `link_or_copy()` 把它们复制到了 `_hardpool/2026-09-20/images/`：

- sample_5959_crazing_0.37.jpg
- sample_6610_crazing_0.38.jpg

## 2. **发现 bug：image_path 共享导致覆盖**

查 DB 发现 `D:/Inspect/Images/sample_6610.jpg` 路径下有**多条记录**：

| id | time | defect | conf |
|----|------|--------|------|
| 33366 | 2026-09-15 11:31 | dent | 0.97 |
| 33728 | 2026-09-17 16:23 | crazing | 0.38 ← 难例 |
| 33810 | 2026-09-17 18:40 | crazing | 0.37（但路径是 sample_5959）|

**根因**：上位机 `_save_evidence()` 的命名是 `存证_{stamp}.jpg`（基于时间戳，不重复），但边缘模式下的 sample 是按序号 `sample_{N}.jpg`（N 复用），**同一 N 被多次写入会覆盖**。

所以"难例"读到的不一定是当时低置信的版本（可能是 0.97 dent 覆盖了 0.38 crazing）。

## 3. 当前状态：0 字节空文件

进一步检查：

- `_hardpool/2026-09-20/images/sample_5959_crazing_0.37.jpg` → **0 bytes**
- `_hardpool/2026-09-20/images/sample_6610_crazing_0.38.jpg` → **0 bytes**

原始图（`D:/Inspect/Images/sample_5959.jpg` 等）也已不存在或被清空。

可能原因：
1. 上位机的 `D:/Inspect/Images/` 目录被 `utils.disk_guard()` 删掉了
2. sample_*.jpg 命名重复，DB 记录有但实际文件已被覆盖 + 后续清理

## 4. 修复方案

### 立即修（下次难例回流生效）

`_weekly_feedback.py` 的 `link_or_copy` 要加"按 db id 生成唯一文件名"：

```python
# 旧：直接用 src 的文件名 → 重复覆盖
dst = img_dir / f"{stem}_{cls}_{conf:.2f}.jpg"

# 新：加 db id 防止冲突
dst = img_dir / f"{rid:06d}_{cls}_{conf:.2f}_{stem}.jpg"
```

这样：同一 source 文件被多次写时，DB id 不同 → 难例目录里有多个版本，可追溯。

### 中期修（更彻底）

上位机存图逻辑：边缘模式 sample_*.jpg 改为带时间戳的 `sample_{N}_{stamp}.jpg`，永远不覆盖。

## 5. 09-20 这两张图的处置

- 当前：**无法核对**（0 字节）
- 处置：保留这两条记录在 hardpool.md，标注"文件已不可用"
- 下次 `_weekly_feedback.py` 跑（明晚）会按新规则生成唯一文件名

## 6. 结论

难例回流机制**逻辑正确但数据流有 bug**：
- 选源 ✓（从 DB 挑低置信 NG）
- 分类 ✓（按类均匀）
- 复制 ✗（image_path 共享导致覆盖 + 0 字节）

修复后难例机制才真正能跑通。本周内不需重跑旧难例（模型稳定，难例本来就少）。
