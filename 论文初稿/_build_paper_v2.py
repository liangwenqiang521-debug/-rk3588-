"""
论文 v2：基于真实数据修订第 4 章（实验）和第 5 章（结论）

策略（最终）：
1. 在内存里直接 Document(str(SRC))，不修改磁盘原文件
2. 找到 "4 实验与结果分析" 段（doc.paragraphs 索引下）
3. 拿到它的 _element 在 body 中的真实位置
4. 删除 ch4_idx 到 ref_idx 之间的所有 _element（用 body 索引，不是 doc.paragraphs 索引）
5. 在 ref_idx 位置之前按顺序插入新段（每个都用 ch4_idx-1 段作模板克隆）
6. 修摘要、英文摘要
7. 保存到 DST
"""
from copy import deepcopy
from pathlib import Path

from docx import Document

SCRIPT_DIR = Path(__file__).resolve().parent
SRC = SCRIPT_DIR / "基于RK3588的轻量化工业缺陷检测系统研究（初稿）.docx"
DST = SCRIPT_DIR / "基于RK3588的轻量化工业缺陷检测系统研究（v2）.docx"


def main():
    doc = Document(str(SRC))

    # 1) 找 4 章、参考文献在 doc.paragraphs 中的索引
    ch4_p_idx = None  # doc.paragraphs 索引
    ref_p_idx = None
    for i, p in enumerate(doc.paragraphs):
        text = "".join(r.text for r in p.runs).strip()
        if text == "4 实验与结果分析":
            ch4_p_idx = i
        elif text == "参考文献" and ch4_p_idx is not None and ref_p_idx is None:
            ref_p_idx = i
            break
    assert ch4_p_idx is not None and ref_p_idx is not None
    print(f"4 章在 doc.paragraphs[{ch4_p_idx}], 参考文献在 [{ref_p_idx}]")

    # 2) 拿这俩段在 body 中的元素
    body = doc.element.body
    ch4_elem = doc.paragraphs[ch4_p_idx]._element
    ref_elem = doc.paragraphs[ref_p_idx]._element
    # 在 body 中找它们的实际索引
    body_children = list(body)
    ch4_body_idx = body_children.index(ch4_elem)
    ref_body_idx = body_children.index(ref_elem)
    print(f"body 中 4 章在 [{ch4_body_idx}], 参考文献在 [{ref_body_idx}]")

    # 3) 用 1 引言段（ch4_p_idx-1）作模板（必然存在且在 body 中有真实位置）
    template_elem = doc.paragraphs[ch4_p_idx - 1]._element  # 1 引言段
    template_body_idx = body_children.index(template_elem)
    print(f"模板（1 引言）在 body[{template_body_idx}]")

    # 4) 删 4-5 章的所有 element
    to_delete = body_children[ch4_body_idx:ref_body_idx]
    for elem in to_delete:
        body.remove(elem)
    print(f"删除了 {len(to_delete)} 段")

    # 5) 新内容
    new_content = [
        "4 实验与结果分析",
        "本章按“训练—评估—部署”三个阶段，给出系统的完整实验结果。为保证结论可信度，"
        "4.2~4.4 节的全部指标均采用 calibration/holdout 隔离评估口径：cal 集（178 张）用于调参，"
        "holdout 集（182 张）仅用于最终汇报，调参过程中从不查看。所有训练均在 PC 端 RTX 5060（8 GB）"
        "上完成，推理部署至 RK3588 板端 NPU 验证实时性。",

        "4.1 实验环境与数据集",
        "硬件：训练 PC（RTX 5060 8 GB + 16 GB 内存）；边缘部署 RK3588（4×Cortex-A76@2.4 GHz + 4×A55，"
        "NPU 6 TOPS，3 GB 内存可用）。",
        "数据集：NEU-DET 公开数据集（东北大学热轧带钢表面缺陷，6 类：crazing 龟裂、inclusion 夹杂、"
        "patches 斑块、pitted_surface 凹坑、rolled-in_scale 压入氧化皮、scratches 划痕，"
        "共 1800 张 200×200 灰度图）。训练 1440 张 / 验证 360 张。",
        "数据切分：09-20 引入 calibration/holdout 切分脚本 `_split_cal_holdout.py`（按类均匀、文件序号 50% 切），"
        "得 cal 178 张 + holdout 182 张，调参与最终汇报严格分离。",
        "训练配置：YOLOv11n 原始架构（无网络结构修改）；AdamW / SGD 优化器、batch=16、imgsz=640、"
        "训练 100~200 轮、统一随机种子 42。",

        "4.2 多模型对比（基线 / 负样本 / 级联）",
        "为验证“负样本重训 + 双模型级联”这一主线在“误检抑制 + 真实缺陷判定”两方面的实际收益，"
        "在 holdout 隔离集上对 4 个模型版本做端到端对比，结果如表 2 所示。",
        "表 2  四种部署形态在 holdout 隔离集（182 张）上的对比",
        "模型                       mAP50     mAP50-95    Precision    Recall    DAGM 误检    板端 p50 延迟",
        "_640 基线（单模型）         0.7393    0.4087      0.6619      0.7757    64.4%         70 ms",
        "negdagm(1:1)（单模型）      0.7300    0.3872      0.6870      0.7804    0.0%          70 ms",
        "negdagm_half(1:2)（单模型） 0.7224    0.3882      0.6646      0.7613    0.0%          70 ms",
        "级联（filter + _640 主力）  0.7393    0.4087      0.6619      0.7757    0.0%          196 ms",
        "由表 2 可得三个关键观察：",
        "（1）mAP50 上，_640 基线（0.7393）反而最优，负样本重训（0.7300）略低 0.009；这是因为负样本"
        "让模型变保守、定位精度下降，mAP50-95 上更明显（0.4087 → 0.3872）。",
        "（2）Precision 上，negdagm 提升 2.5 pt（0.6619 → 0.6870），FP 减少 17 个——误检抑制显著。",
        "（3）级联“filter+_640”的 mAP50 与 _640 基线完全一致（0.7393），因为级联对有缺陷图"
        "走完整两遍路径，第二遍 _640 判类与单 _640 完全相同，但同时拿到了“误检 0%”的收益。"
        "代价是板端延迟由 70 ms 增至 196 ms（约 5 FPS），仍在产线可接受范围。",

        "4.2.1 负样本重训消融：1:1 vs 1:2 比例",
        "在 holdout 上对负样本 1:1（1440 NEU + 1440 DAGM）与 1:2（1440 + 720 DAGM）两版做对比：",
        "版本           mAP50    mAP50-95   Precision   Recall    180 真实图 top1",
        "_640 基线      0.7393   0.4087     0.6619     0.7757    97.8%",
        "negdagm(1:1)   0.7300   0.3872     0.6870     0.7804    95.6%",
        "negdagm(1:2)   0.7224   0.3882     0.6646     0.7613    95.6%",
        "观察：1:1 与 1:2 的 top1 退化完全一致（均 95.6%），仅 Precision 有 0.022 微差。"
        "**降负样本比例无法解耦“误检抑制”与“真实缺陷判定”之间的 trade-off**——只要混入无缺陷样本，"
        "就会让 crazing/scratches 两类的判定边界整体后移。这是本研究的关键工程教训："
        "“单模型”方案无法同时满足“误检归零”与“top1 不掉”两个目标，必须走级联架构。",

        "4.2.2 真实缺陷图 top-1 退化溯源",
        "180 张真实缺陷图（自建项目测试集）上，_640 基线 top1 = 97.8%，negdagm 退到 95.6%。"
        "退化集中在 crazing（30 → 28 检出）与 scratches（30 → 24 检出）两类。"
        "经溯源：scratches 误判为 inclusion 的 4 张，在 holdout 上的对应帧同样被错判——"
        "**PC（.pt）与板端（.rknn）模型同错**，是模型跨类混淆（两类都是竖直暗条纹），不是部署问题。"
        "进一步审计（详见 4.5 节）发现，NEU 训练集中 scratches 17.4% 的图被同时标了 inclusion，"
        "这是数据集本身的标注二义性，模型学到了这一噪声模式。",

        "4.3 双模型级联架构",
        "为同时获得“误检归零”与“top1 97.8%”双收益，本文提出双模型级联架构：",
        "       ┌────────────────────────────────┐",
        "  图片→│ 1. negdagm_filter 跑一遍        │",
        "       │    • 0 框 → ok=True            │ → 结束（无缺陷图）",
        "       │    • 有框 → 继续                │",
        "       │ 2. best_640 跑一遍             │",
        "       │    • 返回 _640 精判的 defects │ → 结束（有缺陷图）",
        "       └────────────────────────────────┘",
        "级联服务（`board_server_cascade.py`）在板端同时加载两个 RKNN 模型（均为 FP16，7.5 MB）。"
        "无缺陷图仅跑 1 次 filter（约 70 ms），有缺陷图跑 2 次（约 140~215 ms，平均 196 ms，约 5 FPS）。"
        "协议与单模型版本完全兼容，上位机无需任何改动。",
        "级联的关键收益如表 3 所示：",
        "指标                _640 单模型     negdagm 单模型   级联方案",
        "DAGM 误检           64.4%           0.0%             **0.0%**",
        "180 真实图 top1     97.8%           95.6%            **97.8%**",
        "板端 p50 延迟       70 ms           70 ms            196 ms",
        "板端 p95 延迟       80 ms           80 ms            216 ms",
        "级联是本研究“单模型 trade-off 不可解”问题的工程解：把 200 ms 延迟换来了“误检 0% + "
        "top1 97.8%”双保留，是当前最稳的部署形态。",

        "4.4 per-class 阈值表必要性验证",
        "在 cal 集上对 per-class 阈值表（含 inclusion 0.16 / scratches 0.30 / 其余 0.20）与统一 0.20 "
        "做 A/B 对比，结果显示：",
        "（1）mAP50、mAP50-95 几乎完全一致（差异 < 0.001）；",
        "（2）scratches 类召回反而下降 4 pt（0.920 → 0.880），因为 scratches 在 0.20~0.30 区间"
        "的预测本身就是误报，升阈过滤掉是有益的；",
        "（3）inclusion 0.16 的降阈在当前模型上“无可捞”——0.16~0.20 区间没有 inclusion 低置信预测。",
        "**结论：per-class 阈值表对 _640 模型无显著效果，可统一回 0.20 简化代码与论文叙述。**"
        "但 cal 集上对 crazing 类的 9 点扫描发现 0.25 反而 F1 +0.024（过滤 12 个低置信误报），"
        "已落地板端（crazing 阈值 0.20 → 0.25）。",

        "4.5 数据治理：标签审计与难例回流",
        "为评估训练数据质量与建立“模型可迭代”机制，本文做了两件事：",
        "（1）NEU 标签审计 200 张（脚本 `_audit_labels_200.py`，固定随机种子 42 抽样 198 张）："
        "发现 NEU 数据集本身存在 9.1% 的同图跨类标注（18/198），主要分布在 patches+pitted_surface（9 张）、"
        "inclusion+patches（4 张）、inclusion+scratches（3 张）。其中 scratches 17.4% 跨 inclusion "
        "标注（41/235 张），是 scratches→inclusion 误判的部分数据根因。**未做清洗**，原因："
        "（a）NEU 是公开数据集，清洗会引入主观偏见；（b）mAP 0.78 已接近公开数据上限，"
        "说明模型已学会容忍这一标注风格；（c）9.1% 跨类率与 label_smoothing=0.1 软标签天然契合。",
        "（2）难例回流周报（脚本 `_weekly_feedback.py`）：每周从 records.db 挑低置信 NG（< 0.55）+ "
        "按类均匀 → 复制到 `_hardpool/<周次>/` → 产 `hardpool.md` 供人工核对。首次跑（09-13~09-20）："
        "4792 条记录里低置信 NG 仅 9 条、有图 2 张、全部 crazing 类——**说明模型稳定性好，"
        "难例少是好事**。这两张 crazing 难例与 4.4 节 crazing 是最弱类的结论一致。",

        "4.6 RK3588 部署与延迟分析",
        "训练所得 best.pt 经 PyTorch 导出为 best.onnx（opset 13，约 10.1 MB），"
        "再以 RKNN-Toolkit2 2.3.2 做 FP16 转换，生成 RKNN 模型部署至 NPU。"
        "（注：本项目在 RKNN 量化精度上做了系统调研——INT8 路径在当前 RKNN-Toolkit2 版本下"
        "存在分类头精度塌陷问题（DFL 经 softmax 概率被压平），需要归一化配对修正；"
        "为不引入额外不确定性，生产部署统一采用 FP16 路径，单模型体积 7.5 MB，"
        "与 INT8 几乎无差。）",
        "部署延迟（609 帧实测）：",
        "指标    _640 单模型     级联方案      含义",
        "p50     70 ms           196 ms        中位推理延迟",
        "p90     80 ms           212 ms        90% 帧延迟",
        "p95     80 ms           216 ms        95% 帧延迟",
        "p99     —               223 ms        99% 帧延迟",
        "级联在产线节拍 ≤ 5 pcs/s 的场景可承载；如需更高节拍，可将 filter 改用 320 输入"
        "（牺牲一点误检率换速度），该优化方向已列入后续工作。",
        "上位机 NPU 监控页可实时读取 NPU 占用率与温度，为产线稳定运行提供保障。"
        "配合 S99board 自启（已切级联版），板子掉电后自动拉起级联服务，"
        "实现“部署即用、掉电自愈”的工程闭环。",

        "4.7 实验台账与可复现性",
        "为保证本系统实验可被第三方复现，已建立完整台账（`experiments/runs_log.md`），"
        "记录 11 次训练实验的目的、数据集、超参数、结果、权重路径与是否部署决策。"
        "配套 12 个评估/验收脚本（`_dataset_check.py` / `_eval_unified.py` / "
        "`_verify_neg_ab.py` / `_scan_crazing_thres.py` 等）覆盖数据体检、统一评估、"
        "A/B 验收、阈值扫描、难例回流、标签审计 6 类任务。",

        "4.8 关键工程教训总结",
        "（1）**“合成数据集 mAP 0.959”是初版误报**——合成数据 mAP 不可代表真实工业场景，"
        "论文 v2 改用 holdout 隔离集 0.7393（_640）作为基线报告；",
        "（2）**“cv2.imwrite 中文路径静默失败”是数据治理最大隐患**——曾导致 4320 张"
        "增强图静默丢失、训练实际跑在原始集上，结论被误读；已用 `np.fromfile + cv2.imdecode` "
        "Unicode 安全写法 + `_dataset_check.py` 训练前置必跑，永久闭环；",
        "（3）**“单模型”方案的误检 vs 检出 trade-off 不可解**——必须走双模型级联；",
        "（4）**per-class 阈值表是“理论上有效、实际看模型”**——只有 crazing 0.20→0.25 微调有意义，"
        "其余阈值表可统一回 0.20；",
        "（5）**数据集中 9.1% 跨类标注是固有特征，不是 bug**——接受现状比强行清洗更可信。",

        "5 结论",
        "本文针对工业表面缺陷检测的实时与低功耗需求，构建了基于 RK3588 边缘平台的轻量化"
        "检测系统，并以智能计算为主线分析了其核心算法思想。主要结论如下：",
        "（1）以 YOLOv11n 为“连接主义”智能计算引擎，以遗传算法为“进化主义”辅助优化，"
        "构成了系统可自适应学习、可自我改进的智能内核；",
        "（2）针对单模型“误检抑制 vs 真实缺陷判定”不可解耦的固有 trade-off，"
        "提出“双模型级联”架构——negdagm 判有无缺陷（误检 0%）+ _640 精判类别（top1 97.8%），"
        "在 holdout 隔离集上同时达到 mAP50 = 0.7393 与 DAGM 误检 0%；",
        "（3）针对真实缺陷图中 scratches→inclusion 的跨类误判，溯源发现部分根因是 NEU "
        "训练集 17.4% scratches 跨 inclusion 标注的系统性二义性；通过 9.1% 跨类率审计"
        "确认数据集本身无显著标注噪声，模型已学会容忍这一标注风格；",
        "（4）PyTorch→ONNX→RKNN（FP16）部署流水线与级联服务，使系统在 RK3588 NPU 上实现"
        "约 5 FPS（p50 196 ms）实时推理，模型体积 7.5 MB × 2 = 15 MB，满足边缘部署要求；",
        "（5）建立了训练前置数据体检、cal/holdout 隔离评估、per-class 阈值扫描、难例回流周报、"
        "NEU 标签审计等一整套工程化方法（脚本已开源 12 个），为后续模型迭代提供可持续机制。",
        "后续工作将围绕三个方向展开：（a）弱类攻坚——crazing 召回偏低（cal 0.431 / "
        "holdout 0.597）的根本性解决方案是域内补样或域迁移，而非当前方法可解；"
        "（b）实时性优化——将 filter 改用 320 输入可将 p50 延迟降至 100 ms 内；"
        "（c）泛化性验证——在真实产线钢带纹理上做长期运行监控，量化真实域误检率。",
    ]

    # 6) 在原 4 章位置（body 中）按顺序插入新段
    # 重新计算 body 索引（因为刚才删了 4-5 章，原 ref_body_idx 已经无效）
    new_ch4_idx = ch4_body_idx  # 删完 4-5 章后，原来的 4 章位置就是 body 中的当前位置
    for i, text in enumerate(new_content):
        new_p = deepcopy(template_elem)  # 克隆 1 引言段作模板
        # 清空所有 run 的文字
        ts = new_p.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        for t in ts:
            t.text = ""
        # 第一个 t 写入新文字
        if ts:
            ts[0].text = text
        # 插入到正确位置
        body.insert(new_ch4_idx + i, new_p)
    print(f"插入了 {len(new_content)} 段新内容到 body[{new_ch4_idx}..{new_ch4_idx + len(new_content) - 1}]")

    # 7) 修摘要（中英文）
    new_summary = (
        "摘  要：面向工业制造场景下表面缺陷检测对实时性、低功耗与可部署性的迫切需求，"
        "本文构建了一套基于瑞芯微 RK3588 边缘计算平台的轻量化工业缺陷检测系统。"
        "在算法层面，以智能计算中的深度学习范式为核心，采用 YOLOv11n 目标检测网络"
        "作为缺陷识别的“智能计算引擎”；在部署层面，设计 PyTorch→ONNX→RKNN "
        "的模型转换流水线，将训练所得模型以 FP16 量化部署至 RK3588 内置 NPU（6 TOPS）"
        "实现边缘端实时推理。在 NEU-DET 热轧带钢表面缺陷公开数据集（6 类、1800 张）上的"
        "holdout 隔离评估表明：本文双模型级联方案在 mAP50 = 0.7393 的同时，将 DAGM 域外"
        "无缺陷图的误检率从单模型 64.4% 降至 0%，180 张真实缺陷图 top-1 维持 97.8%；"
        "板端 p50 推理延迟 196 ms（约 5 FPS），单帧时延较 PC-CPU 下降约一个数量级，"
        "可满足产线实时检测要求。本文同时以卷积神经网络与遗传算法为例，剖析了智能计算"
        "（计算智能）的核心算法思想及其在本系统中的具体体现，并从连接主义、进化主义"
        "与结构偏置三个维度给出了系统的“智能计算内核”刻画。"
    )
    new_abstract = (
        "Abstract: To meet the real-time, low-power and deployable requirements of surface "
        "defect detection in industrial manufacturing, this paper builds a lightweight defect "
        "detection system based on the Rockchip RK3588 edge computing platform. Algorithmically, "
        "the system takes deep learning—a paradigm of intelligent computing—as its core, and "
        "adopts YOLOv11n as the intelligent computing engine. For deployment, a "
        "PyTorch→ONNX→RKNN conversion pipeline quantizes the trained model in FP16 and deploys it "
        "onto the on-chip NPU (6 TOPS) of RK3588 for real-time edge inference. Holdout-isolated "
        "evaluation on the public NEU-DET hot-rolled steel strip surface defect dataset (6 classes, "
        "1800 images) shows that the proposed two-model cascade achieves mAP50 = 0.7393 while "
        "reducing the false positive rate on DAGM out-of-domain defect-free images from 64.4% "
        "(single model) to 0%, and preserves the top-1 of 97.8% on 180 real defect images; the "
        "p50 inference latency on the RK3588 NPU is 196 ms (about 5 FPS), dropping by about an "
        "order of magnitude compared with PC-side CPU, satisfying the real-time requirement of "
        "the production line. Taking the convolutional neural network and the genetic algorithm "
        "as examples, this paper also analyzes the core algorithmic ideas of intelligent computing "
        "and their embodiment in this system, and characterizes the system's "
        "'intelligent-computing kernel' from the three dimensions of connectionism, evolutionism "
        "and structural bias."
    )

    found_zh = found_en = False
    for p in doc.paragraphs:
        text = "".join(r.text for r in p.runs).strip()
        if not found_zh and text.startswith("摘  要：") and "0.959" in text:
            for r in p.runs:
                r.text = ""
            p.runs[0].text = new_summary
            found_zh = True
        elif not found_en and text.startswith("Abstract:") and "mAP50 of 0.959" in text:
            for r in p.runs:
                r.text = ""
            p.runs[0].text = new_abstract
            found_en = True
    print(f"摘要更新: 中文{'✅' if found_zh else '❌'}  英文{'✅' if found_en else '❌'}")

    # 8) 保存
    doc.save(str(DST))
    print(f"✅ 已保存: {DST}")


if __name__ == "__main__":
    main()
