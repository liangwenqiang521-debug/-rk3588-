# STORY：工业缺陷检测项目 · 本周进展汇报（2026-10-12 ~ 10-15）

## ① 用户意图对齐

- **目标受众**：导师 / 项目评审 —— 关心"这一周做出了什么、发现了什么、有没有走偏"。
- **核心目标**：讲完后让听众清楚三件事 ——
  ① **这周不是堆功能，是在定方向**：板端完成配置选型实测，用数据定下"哪个组合最优"，而不是凭感觉上；
  ② **发现并修正了一个方向性误判**：原以为瓶颈是"背景误报 / 负样本不足"，实测推翻了它，
     真因是**评估集自身的标注缺失**；
  ③ **做了两件有长期价值的事**：重建评估集（全池分层重划分）+ 按新评估集重训（进行中）。
- **PPT 长度**：14 页（Hero 配额 20–30% → 3 页：封面 / 真因页 / 结束页）。
- **视觉调性**：沿用上一份的「工业科技蓝」，保证系列汇报的连续性。
- **内容边界**：
  - **必讲**：线 A 实测设计与 2×2 结论、三个假设的排除、真因证据（81.7% vs 7.2%）、oracle 上界、
    评估集重建结果、重训进度与风险、下周计划。
  - **不讲**：代码级实现细节、逐个缺陷类训练曲线、RKNN 转换踩坑全过程、SSH / 板端运维细节。
  - **禁碰**：不编造未实测数据；重训未完成必须标"进行中"并注明轮次；
    **不把"评估口径改善"说成"模型精度提升"**。

---

## ② 页面布局骨架

- **页面总数与分章**：共 14 页。目录声明 **3 个章节**，全篇有且仅有 **3 个 `type: section` 扉页**，编号 01–03。

| 章 | 目录条目 | 页码区间 | 扉页所在页 |
| :- | :--- | :--- | :--- |
| 01 | 板端落地与选型验证 | P3–P6 | P3 |
| 02 | 质量瓶颈归因 | P7–P10 | P7 |
| 03 | 评估集重建与重训 | P11–P13 | P11 |

> ⚠️ 3 个扉页编号 01/02/03，标题与目录逐字一致。
> P14 为结束页（非 section）。

- **Hero 页定位**（3 页 ≈ 21%，落在 20–30%）：P1 封面、P9 真因（81.7% 巨型锚点）、P14 结束页。互不相邻 ✅
- **rhythm**：P1 peak → P2 transition → P3 transition → P4 valley → P5 valley → P6 peak →
  P7 transition → P8 valley → P9 peak → P10 valley → P11 transition → P12 valley → P13 peak → P14 peak
  （连续 valley 用 peak/transition 打断 ✅）
- **非对称版式**：14 页中 10 页非对称（71%）✅
- **对称版式**：≤ 2 页 → 用在 P5（图表+洞察）与 P14（居中金句）✅
- **N 卡片横排**：全篇仅 P8 用 1 次（三假设排除卡）✅
- **版式重复**：相邻页版式均不同 ✅

---

## ③ 页面大纲

### P1 封面
| 字段 | 值 |
| :--- | :--- |
| title | 工业表面缺陷检测系统 · 本周进展汇报 |
| type | cover |
| role | hero |
| rhythm | peak |
| layout | 全幅图+骑线文字 |
| visual | L1: hero_factory_line.png（全幅底图 + 左侧骑线） |
| visual_role | atmosphere |
| density | 字数约 55 / 图片 1 / 留白 35% |
| anti_pattern | 禁止三卡指标横排堆封面；禁止把底图缩成小贴片 |
| description | 主标 + 副标「10-12 ~ 10-15 进展汇报」+ 一行范围（板端选型 / 瓶颈归因 / 评估集重建）+ 三指标（2×2 实测 / 81.7% 漏标率 / 100 轮重训中）+ 落款 2026-10-15。 |

### P2 目录
| 字段 | 值 |
| :--- | :--- |
| title | 目录 |
| type | catalog |
| role | supporting |
| rhythm | transition |
| layout | 左标题+右内容 |
| visual | L3: 章节大序号（SVG） |
| visual_role | evidence |
| density | 字数约 130 / 图片 0 / 留白 28% |
| anti_pattern | 禁止等宽卡片横排；禁止只列标题不写导语 |
| description | 三章导语式目录：01 板端落地与选型验证 · 02 质量瓶颈归因 · 03 评估集重建与重训。每条带一句判断。 |

### P3 【章 01 扉页】板端落地与选型验证
| 字段 | 值 |
| :--- | :--- |
| title | 01 板端落地与选型验证 |
| type | section |
| role | supporting |
| rhythm | transition |
| layout | 全屏视觉+大标题 |
| visual | L1: SVG 深蓝渐变底 + 巨型章号 |
| visual_role | atmosphere |
| density | 字数约 45 / 图片 0 / 留白 45% |
| anti_pattern | 禁止四卡预览；禁止铺满正文 |
| description | 章题 + 小标："新模型、新阈值，到底该上哪一个？用实测数据说话。" |

### P4 为什么做这组对照
| 字段 | 值 |
| :--- | :--- |
| title | 上线前先做一次四格对照 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 左标题+右内容 |
| visual | L1: SVG 2×2 矩阵（模型 × 阈值） |
| visual_role | anchor |
| density | 字数约 220 / 图 1 / 留白 26% |
| anti_pattern | 禁止只列变量不给判据；禁止用纯文字代替矩阵 |
| description | 两个变量：模型（旧 50 轮 / 新 100 轮 e100）× 阈值（统一 0.20 / 13 类标定）→ 四格 A/B/C/D。样本 300 张 holdout，走真实板端 socket。判断：不靠"新的一定好"，让数据选。 |

### P5 2×2 实测结果
| 字段 | 值 |
| :--- | :--- |
| title | 四格实测：最优是「旧模型 + 统一阈值」 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 图表+洞察 |
| visual | Chart（四格 F1 对比条形图）+ 洞察卡 |
| visual_role | evidence |
| density | 字数约 200 / 图表 1 / 留白 24% |
| anti_pattern | 禁止只给数字不给判断；禁止省略离线对照 |
| description | A 旧50轮/统一 0.20 → F1 0.7376（最优）；B 新 e100/统一 → 0.7162；C 新 e100/13类标定 → 0.7064；D 旧50轮/13类标定 → 0.7295。 |

### P6 两条结论
| 字段 | 值 |
| :--- | :--- |
| title | 换模型、换阈值，都在伤指标 |
| type | content |
| role | supporting |
| rhythm | peak |
| layout | 非对称双栏（60:40） |
| visual | 左侧两条负收益箭头（SVG）+ 右侧动作 |
| visual_role | anchor |
| density | 字数约 240 / 图 1 / 留白 26% |
| anti_pattern | 禁止只报结论不给证据；禁止把负收益写成中性 |
| description | 换模型 −0.0214 F1；换阈值 −0.008 ~ −0.010 F1 → 板端已回滚到配置 A（10-09 生产态）。附带校验：板端与离线同条件 F1 0.7064 vs 0.7062，差 0.5% → **板端后处理链路忠实**。 |

### P7 【章 02 扉页】质量瓶颈归因
| 字段 | 值 |
| :--- | :--- |
| title | 02 质量瓶颈归因 |
| type | section |
| role | supporting |
| rhythm | transition |
| layout | 全屏视觉+大标题 |
| visual | L1: SVG 深蓝渐变底 + 巨型章号 |
| visual_role | atmosphere |
| density | 字数约 45 / 图片 0 / 留白 45% |
| anti_pattern | 禁止四卡预览；禁止提前给出结论 |
| description | 章题 + 小标："mAP 卡在 0.72 —— 是模型不行，还是尺子不准？" |

### P8 三个假设，两个被排除
| 字段 | 值 |
| :--- | :--- |
| title | 先排除：不是背景误报，也不是 NMS 太松 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 三卡横排（每卡一假设） |
| visual | 三张排除卡（SVG 图标 + 数据） |
| visual_role | evidence |
| density | 每卡 ≥ 110 字 / 图 0 / 留白 25% |
| anti_pattern | 禁止只写"已排除"不给数字；禁止做成等宽装饰卡 |
| description | ① 背景误报 → 200 张纯背景图 FP = **0**，负样本治理无收益空间；② NMS 太松 → 调紧仅 +0.0039 F1，代价 FP −302 换 FN +109；③ 阈值 → 只能压半量低置信 FP，实测 −0.008 F1。→ 三个方向都不是主因。 |

### P9 【真因 · Hero】精度被系统低估
| 字段 | 值 |
| :--- | :--- |
| title | 真正的瓶颈：评估集自己漏标了 |
| type | content |
| role | hero |
| rhythm | peak |
| layout | 巨型数字+洞察 |
| visual | 巨型锚点 81.7% + 随机基线 7.2% 对比 |
| visual_role | anchor |
| density | 字数约 190 / 图 0 / 留白 30% |
| anti_pattern | 禁止无 ≥48px 锚点；禁止把自证偏置说成精确值 |
| description | 2647 个 FP **100% 出自有缺陷的图**；高置信未匹配框的"预测类 == 图内已有类"达 **81.7%**（196/240），随机基线仅 7.2% → 模型找到了没被标注的同类缺陷。oracle 上界 F1 0.7108 → **0.7507（+4.0pp）**，按 60–80% 确认率折算实际 +2.5~3.5pp。 |

### P10 人工核查佐证
| 字段 | 值 |
| :--- | :--- |
| title | 46 页核对表，逐张看过了 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 左大图+右侧文字 |
| visual | L1: 核对拼图示意（红框=预测 / 绿框=GT） |
| visual_role | evidence |
| density | 字数约 200 / 图 1 / 留白 28% |
| anti_pattern | 禁止只有结论没有样本；禁止左右 50:50 |
| description | 695 个漏标候选 → 按 conf 三档拼成 46 页核对表；已目检 high-conf 8 页 143 个候选，**约 85% 判为真漏标**（红框圈住 patches 暗斑 / inclusion 细长夹杂 / 横向压入氧化皮纹理，附近无绿框）；存疑集中在 water_spot / oil_spot 反光区。 |

### P11 【章 03 扉页】评估集重建与重训
| 字段 | 值 |
| :--- | :--- |
| title | 03 评估集重建与重训 |
| type | section |
| role | supporting |
| rhythm | transition |
| layout | 全屏视觉+大标题 |
| visual | L1: SVG 深蓝渐变底 + 巨型章号 |
| visual_role | atmosphere |
| density | 字数约 45 / 图片 0 / 留白 45% |
| anti_pattern | 禁止四卡预览；禁止铺满正文 |
| description | 章题 + 小标："尺子先校准，再量模型。" |

### P12 评估集重建：全池分层重划分
| 字段 | 值 |
| :--- | :--- |
| title | 让每个缺陷类都在验证集里有足够样本 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 左标题+右内容 |
| visual | L1: SVG 前后对比条形图（最弱类框数） |
| visual_role | evidence |
| density | 字数约 240 / 图 1 / 留白 26% |
| anti_pattern | 禁止只给总量不给小类；禁止把重划分说成提精度 |
| description | 全池 26243 张按类分层重划（小类 50% / 中类 35% / 大类 20%）→ 新 train 20329 / val 5911（cal 2891 / holdout 3020），**39 类框数全部 ≥30**（最小 oxide_scale_plate 16/16、striated_scale 30/30），修掉原 16 类 val 框数不足导致的统计失真。 |

### P13 重训进行中
| 字段 | 值 |
| :--- | :--- |
| title | 100 轮重训跑到哪了，下周做什么 |
| type | content |
| role | supporting |
| rhythm | peak |
| layout | 非对称双栏（65:35） |
| visual | 左：重训进度 + 中间指标；右：下周计划与风险 |
| visual_role | evidence |
| density | 字数约 290 / 图 0 / 留白 24% |
| anti_pattern | 禁止把"进行中"写成"已完成"；禁止隐瞒中断 |
| description | 左：100 轮已跑 65 轮，中间指标 mAP50 **0.7716** / mAP50-95 0.4990（注：口径与新 val 不同，仅作趋势参考）；10-15 02:2x 因机器关机中断，已从 last.pt 续训。右：下周 —— ① 跑完 100 轮 → 新 val 评估 + cal 标定 ② 论文补写「FP 归因 → 评估集漏标 → 精度被低估」章节 ③ 标注修复（可选，需人力）。风险：训练期间机器不可关机；补框需人工，且只补 train。 |

### P14 结束页
| 字段 | 值 |
| :--- | :--- |
| title | 尺子准了，数字才算数 |
| type | ending |
| role | hero |
| rhythm | peak |
| layout | 居中金句/巨型数字 |
| visual | L1: SVG 光带暗底 + 巨型数字 81.7% |
| visual_role | anchor |
| density | 字数约 45 / 图 1 / 留白 45% |
| anti_pattern | 禁止罗列信息；禁止目录式总结卡 |
| description | 收束金句 + 一行落点：2×2 实测 / 81.7% 漏标率 / 100 轮重训。落款：项目组 · 2026-10-15。 |

---

## ④ 数据口径纪律

- 线 A 实测（`docs/e100板端落地与AB实测.md`、`模型训练/board_ab_20261013.json`）：300 张 holdout、
  NMS IoU 0.45、匹配 IoU 0.50、TP 记真值类；四格 A/B/C/D + 离线对照 O 均取该口径。
- FP 归因（`docs/fp_audit/FP归因与漏标核查.md`）：val 5296 张（负样本 200 / 有缺陷 5096，GT 10226 框），
  50 轮基线 model，conf≥0.01 缓存后按 th=0.20 复算。**81.7% 与 +4.0pp 均含自证偏置，标注为"上界"**。
- 分层重划分（`模型训练/data_steel39_strat.yaml`）：框数为该 yaml 表头自带的 G1/G2 统计。
- 重训指标：`runs/steel39_yolo11n_640_strat/results.csv`，**属旧 val 口径的中间值**，
  与新 val 不可比，仅作收敛趋势参考，汇报时必须标注"进行中"。
- 遗留问题与风险如实列出，不淡化；中断事实如实交代。
