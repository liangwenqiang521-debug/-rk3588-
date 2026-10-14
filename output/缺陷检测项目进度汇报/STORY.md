# STORY：工业缺陷检测项目 · 开发进度汇报（含应用场景）

## ① 用户意图对齐

- **目标受众**：答辩老师 / 项目评审 / 项目组 —— 关心"这个项目做到哪一步了、拿到什么成果、还剩什么、能用在哪"。
- **核心目标**：讲完后让听众清楚三件事 ——
  ① **进度可量化**：按开发阶段（数据 → 模型 → 边缘部署 → 上位机 → 论文）逐项交代完成度与实测数据；
  ② **成果可信**：所有关键指标（39 类、mAP50 0.724、128–157ms、3.0s 自愈）来自实测记录；
  ③ **应用场景清晰**：六大领域地图 + 落地路径，说明"这套系统往下能走多远"。
- **PPT 长度**：14 页（Hero 配额 20–30% → 3 页：封面 / 阶段总览 / 结束页）。
- **视觉调性**：工业科技蓝 · 精密冷峻 · 数据可信 · 报告严谨。
- **内容边界**：
  - **必讲**：五阶段进度与完成度、关键实测指标、里程碑时间线、遗留问题与下一步、应用场景。
  - **不讲**：代码级实现细节、逐个缺陷类的训练曲线、RKNN 量化踩坑全过程。
  - **禁碰**：不编造未实测数据；"技术就绪"≠"已成单"；行业侧数字标注为公开区间。

---

## ② 页面布局骨架

- **页面总数与分章**：共 14 页。目录声明 **3 个章节**，全篇必须有且仅有 **3 个 `type: section` 扉页**，编号 01–03。

| 章 | 目录条目 | 页码区间 | 扉页所在页 |
| :- | :--- | :--- | :--- |
| 01 | 开发进度：五个阶段 | P2–P6 | P3 |
| 02 | 成果指标：实测数据 | P7 | P7 |
| 03 | 应用场景：六大领域 | P9–P11 | P10 |

> ⚠️ 需 3 个扉页，编号 01/02/03，标题与目录逐字一致。
> P8 为进度章与场景章之间的过渡页（transition，非 section）。

- **Hero 页定位**（3 页 ≈ 21%，落在 20–30%）：P1 封面、P7 成果指标、P14 结束页。互不相邻 ✅
- **rhythm**：P1 peak → P2 transition → P3 transition → P4 valley → P5 valley → P6 peak(里程碑) →
  P7 peak → P8 transition → P9 valley → P10 transition → P11 valley → P12 valley → P13 peak → P14 peak
  （连续 valley 已用 peak/transition 打断 ✅）
- **非对称版式**：14 页中 ≥ 40% → 本稿 **10 页非对称（71%）** ✅
- **对称版式**：≤ 2 页 → 用在 P4（图表+洞察）与 P14（居中金句）；P6 用「全屏视觉+大标题」算对称 → 共 3 处超限 ⚠️
  → **修正：P6 改「左标题+右内容」非对称**，对称版式收在 P4 / P14 两页 ✅
- **N卡片横排** 全篇仅 P9 用 1 次 ✅
- **版式重复**：相邻页版式不同 ✅

---

## ③ 页面大纲

### P1 封面
| 字段 | 值 |
| :--- | :--- |
| title | 工业表面缺陷检测系统 · 开发进度汇报 |
| type | cover |
| role | hero |
| rhythm | peak |
| layout | 全幅图+骑线文字 |
| visual | L1: hero_factory_line.png（全幅底图 + 左侧骑线） |
| visual_role | atmosphere |
| density | 字数约 55 / 图片 1 / 留白 35% |
| anti_pattern | 禁止三卡指标横排堆封面；禁止把底图缩成小贴片 |
| description | 主标 + 副标「开发进度与应用场景汇报」+ 一行范围 + 三指标（39 类 / mAP50 0.724 / 128ms）+ 落款 2026-10。 |

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
| density | 字数约 120 / 图片 0 / 留白 28% |
| anti_pattern | 禁止等宽卡片横排；禁止只列标题不写导语 |
| description | 三章导语式目录：01 开发进度 · 02 成果指标 · 03 应用场景。每条带一句话判断。 |

### P3 【章 01 扉页】开发进度：五个阶段
| 字段 | 值 |
| :--- | :--- |
| title | 01 开发进度：五个阶段 |
| type | section |
| role | supporting |
| rhythm | transition |
| layout | 全屏视觉+大标题 |
| visual | L1: SVG 深蓝渐变底 + 巨型章号 |
| visual_role | atmosphere |
| density | 字数约 45 / 图片 0 / 留白 45% |
| anti_pattern | 禁止四卡预览；禁止铺满正文 |
| description | 章题 + 小标："数据、模型、部署、上位机、论文 —— 一条主线走到底。" |

### P4 五阶段完成度
| 字段 | 值 |
| :--- | :--- |
| title | 五个阶段，完成度一览 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 图表+洞察 |
| visual | Chart(五阶段横向条形图) + 洞察卡 |
| visual_role | evidence |
| density | 字数约 240 / 图表 1 / 留白 25% |
| anti_pattern | 禁止把阶段装进等宽卡片；禁止只给百分比不给判断 |
| description | 数据+判断：数据准备 100%（25689 图）、模型训练 100%（39 类，mAP50 0.724）、边缘部署 100%（128–157ms 上板实测）、上位机集成 100%（六页闭环 + 断流自愈）、论文撰写 60%（v2 初稿完成，待补消融与场景章节）。→ 判断：技术主线全部贯通，剩余在"论文收口 + 场景验证"。 |

### P5 里程碑时间线
| 字段 | 值 |
| :--- | :--- |
| title | 关键里程碑时间线 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 左标题+右内容 |
| visual | L1: SVG 竖向/斜向时间轴（6 节点） |
| visual_role | anchor |
| density | 字数约 260 / 图 1 / 留白 24% |
| anti_pattern | 禁止用四卡代替时间轴；禁止节点无日期无判断 |
| description | 六节点：08-21 路线图锁定 RK3588 → 09-14~09-17 数据与基线（_640 全 val 0.783）→ 09-18 负样本闭环（误检 64.4%→0%）→ 09-19 双模型级联上板 → 09-20 评估口径冻结（cal/holdout）→ 10-08~10-09 扩 39 类单模型 + 断流自愈 + 重 IO 后台化。 |

### P6 当前状态
| 字段 | 值 |
| :--- | :--- |
| title | 今天，系统已经跑到这一步 |
| type | content |
| role | supporting |
| rhythm | peak |
| layout | 左标题+右内容 |
| visual | 巨型数字 39 + 四项状态条 |
| visual_role | anchor |
| density | 字数约 230 / 图 0 / 留白 30% |
| anti_pattern | 禁止 N 卡横排；禁止无锚点数字 |
| description | 锚点「39 类 · 单模型 · 板端在线」；四条：板端服务已切 39 类单模型（step 按需推帧）／上位机本地+边缘双路均 39 类／断流自愈实测 3.0s 重连／重 IO 后台化主线程 0.373s→0.009s。判断：已从"能跑通"进入"能稳定跑"。 |

### P7 【章 02 扉页 + 成果指标】实测数据
| 字段 | 值 |
| :--- | :--- |
| title | 02 成果指标：实测数据 |
| type | section |
| role | hero |
| rhythm | peak |
| layout | 巨型数字+洞察 |
| visual | 4 个巨型指标（SVG 大数字） |
| visual_role | anchor |
| density | 字数约 180 / 图 0 / 留白 32% |
| anti_pattern | 禁止把指标塞进等宽卡片角落；禁止无 ≥48px 锚点 |
| description | 四项实测：mAP50 0.724（39 类，conf=0.2 统一口径）／单帧 128–157ms（板端 NKPU）／3.0s 断流自愈（实测掐线）／6 页上位机闭环。判断：指标达到可上产线的水平（≥5 FPS）。 |

### P8 阶段性结论（过渡）
| 字段 | 值 |
| :--- | :--- |
| title | 技术主线已经贯通 |
| type | content |
| role | supporting |
| rhythm | transition |
| layout | 非对称双栏（60:40） |
| visual | SVG 三节点链路图 + 右侧结论 |
| visual_role | anchor |
| density | 字数约 200 / 图 1 / 留白 30% |
| anti_pattern | 禁止左右等分；禁止线性单栏罗列 |
| description | 左：数据→模型→边缘→上位机 链路已闭环；右：一句话判断 —— "该讲的不是能不能做，而是还能做多深"，自然过渡到应用场景章。 |

### P9 【章 03 扉页】应用场景：六大领域
| 字段 | 值 |
| :--- | :--- |
| title | 03 应用场景：六大领域 |
| type | section |
| role | supporting |
| rhythm | transition |
| layout | 左大图+右侧文字 |
| visual | L1: SVG 左侧铺底（同心圆/辊道抽象） |
| visual_role | atmosphere |
| density | 字数约 50 / 图 1 / 留白 40% |
| anti_pattern | 禁止四卡预览；禁止左右 50:50 等分 |
| description | 章题 + 小标："同一个视觉内核，换一套数据就是一条新产线。" |

### P10 六大场景地图
| 字段 | 值 |
| :--- | :--- |
| title | 一张地图看清六个应用领域 |
| type | content |
| role | hero |
| rhythm | peak |
| layout | 上大图+下方卡片 |
| visual | L1: SVG 六宫格场景矩阵 + 锚点「6 领域 / 39 类」 |
| visual_role | anchor |
| density | 字数约 220 / 图 1 / 留白 30% |
| anti_pattern | 禁止等宽六小卡横排；禁止把主视觉缩到 1/3 |
| description | 钢铁/3C/纺织/新能源/食品/玻璃；锚点「6 大领域 / 39 类」；判断：39 类为钢铁/金属实测成果，其余为迁移目标（换数据重训）。 |

### P11 落地路径
| 字段 | 值 |
| :--- | :--- |
| title | 从试跑到规模化的三步路 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 非对称双栏（60:40） |
| visual | L1: SVG 三步路径箭头图 |
| visual_role | evidence |
| density | 字数约 260 / 图 1 / 留白 25% |
| anti_pattern | 禁止左右等分；禁止只给步骤不给成本判断 |
| description | 第一步 PoC 试跑（2–4 周，出检出率基线）→ 第二步 小规模部署（1 月，标定阈值 + 接 PLC + 难例回流）→ 第三步 规模复制（换数据即迁移，边际成本主要是标注）。 |

### P12 迁移成本
| 字段 | 值 |
| :--- | :--- |
| title | 换一个行业，要动的只有三样 |
| type | content |
| role | supporting |
| rhythm | valley |
| layout | 左大图+右侧文字 |
| visual | L1: SVG 迁移矩阵（左 58%）+ 右侧三条清单 |
| visual_role | evidence |
| density | 字数约 240 / 图 1 / 留白 28% |
| anti_pattern | 禁止等宽三卡；禁止左右 50:50；禁止泛泛说"很容易" |
| description | ① 换数据集 ② 调阈值 ③ 接现场；不动的：模型结构、边缘服务、上位机 —— 平台化红利。 |

### P13 遗留问题与下一步
| 字段 | 值 |
| :--- | :--- |
| title | 还差什么，下一步做什么 |
| type | content |
| role | supporting |
| rhythm | peak |
| layout | 非对称双栏（65:35） |
| visual | 左：遗留问题清单；右：下一步行动（SVG 图标卡） |
| visual_role | evidence |
| density | 字数约 300 / 图 0 / 留白 24% |
| anti_pattern | 禁止只报喜不报忧；禁止把遗留问题写成"小问题" |
| description | 遗留：① inclusion/bright_scratch 背景误报（FP 623/328），阈值未对 39 类标定 ② 弱类 waist_folding/crease/warp F1 <0.5 ③ 板端未做 39 类负样本误检实测 ④ README 仍写旧级联口径。下一步：39 类 cal 阈值标定 → 负样本补测 → 论文补消融/场景章 → 真实产线实拍。 |

### P14 结束页
| 字段 | 值 |
| :--- | :--- |
| title | 让每一条产线都看得见缺陷 |
| type | ending |
| role | hero |
| rhythm | peak |
| layout | 居中金句/巨型数字 |
| visual | L1: SVG 光带暗底 + 巨型数字 39 |
| visual_role | anchor |
| density | 字数约 50 / 图 1 / 留白 45% |
| anti_pattern | 禁止罗列信息；禁止目录式总结卡 |
| description | 收束金句 + 一行落点：39 类 / 128ms / 3.0s 自愈。落款：项目组 · 2026-10。 |

---

## ④ 数据口径纪律

- 进度百分比为本项目自评：数据/模型/边缘/上位机 = 已实测贯通 → 100%；论文 = v2 初稿完成、待补章节 → 60%。
- 关键指标一律取实测：mAP50 0.724（`模型训练/_eval_steel39.json`，conf=0.2）、
  单帧 128–157ms（`.workbuddy/memory/2026-10-09.md`）、3.0s 自愈（`tests/_test_edge_reconnect.py`）、
  主线程 0.373→0.009s（`tests/_test_async_io.py`）。
- 行业侧数字（漏检率、人力占比）标注"行业普遍区间"。
- 遗留问题如实列出，不淡化。
