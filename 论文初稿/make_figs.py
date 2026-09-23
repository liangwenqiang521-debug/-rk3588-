# -*- coding: utf-8 -*-
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm
import numpy as np

# 注册中文字体
for fp in [r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"]:
    try:
        fm.fontManager.addfont(fp)
    except Exception as e:
        print("font add err", e)
plt.rcParams["font.sans-serif"] = ["SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT = r"D:\workbuddy\缺陷检测项目\论文初稿"

def box(ax, x, y, w, h, text, fc, ec="#2b3a55"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.04",
                                fc=fc, ec=ec, lw=1.4))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center",
            fontsize=10.5, color="#111", weight="bold")

def arrow(ax, x1, y1, x2, y2, color="#2b3a55"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=14, lw=1.6, color=color))

# ---------- 图1：系统总体结构 ----------
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
ax.text(5, 9.5, "图1  基于RK3588的工业缺陷检测系统总体结构", ha="center", fontsize=12, weight="bold")
box(ax, 0.6, 7.4, 2.2, 1.2, "工业相机\n(海康威视 GigE)", "#cfe3ff")
box(ax, 0.6, 5.2, 2.2, 1.2, "LED光源\n+数字控制器", "#d9f2e6")
box(ax, 0.6, 3.0, 2.2, 1.2, "光电传感器\n(触发信号)", "#fff0c2")
box(ax, 4.0, 4.2, 2.4, 2.4, "RK3588 边缘计算平台\n(四核A76/A55 + 6TOPS NPU)\n图像预处理 + YOLO推理", "#ffe0e0")
box(ax, 7.0, 7.4, 2.4, 1.4, "上位机软件\n(PyQt5 人机界面)", "#e7d9ff")
box(ax, 7.0, 4.8, 2.4, 1.4, "IO信号控制卡\n(STM32 剔除控制)", "#d6e4ff")
box(ax, 7.0, 2.4, 2.4, 1.2, "声光报警\n/良率统计", "#ffeec2")
arrow(ax, 2.8, 8.0, 4.0, 6.6)
arrow(ax, 2.8, 5.8, 4.0, 5.4)
arrow(ax, 2.8, 3.6, 4.0, 4.8)
arrow(ax, 6.4, 5.8, 7.0, 8.1)
arrow(ax, 6.4, 5.0, 7.0, 5.5)
arrow(ax, 6.4, 4.4, 7.0, 3.0)
ax.text(3.4, 9.0, "图像", fontsize=9, color="#444")
plt.tight_layout()
plt.savefig(f"{OUT}/fig1_system.png", dpi=150, bbox_inches="tight")
plt.close()

# ---------- 图2：模型部署流水线 ----------
fig, ax = plt.subplots(figsize=(7.2, 3.0))
ax.set_xlim(0, 12); ax.set_ylim(0, 4); ax.axis("off")
ax.text(6, 3.6, "图2  PyTorch→ONNX→RKNN 模型部署流水线", ha="center", fontsize=12, weight="bold")
steps = [("PyTorch\n训练", 0.4), ("导出 ONNX", 3.0), ("RKNN-Toolkit2\n量化/转换", 5.6),
         ("INT8 校准", 8.2), ("RK3588 NPU\n推理部署", 10.0)]
for i, (t, x) in enumerate(steps):
    box(ax, x, 1.4, 1.6, 1.0, t, "#cfe3ff")
    if i < len(steps)-1:
        arrow(ax, x+1.6, 1.9, steps[i+1][1], 1.9)
ax.text(2.0, 0.7, "PC 训练端", fontsize=9, color="#666")
ax.text(9.0, 0.7, "边缘部署端", fontsize=9, color="#666")
plt.tight_layout()
plt.savefig(f"{OUT}/fig2_pipeline.png", dpi=150, bbox_inches="tight")
plt.close()

# ---------- 图3：遗传算法流程（原图4，前移） ----------
fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
ax.text(5, 9.5, "图3  遗传算法（进化计算）流程", ha="center", fontsize=12, weight="bold")
box(ax, 3.6, 8.0, 2.8, 1.0, "初始化种群", "#cfe3ff")
box(ax, 3.6, 6.2, 2.8, 1.0, "适应度评估", "#d9f2e6")
box(ax, 3.6, 4.4, 2.8, 1.0, "选择 / 交叉 / 变异", "#fff0c2")
box(ax, 3.6, 2.6, 2.8, 1.0, "生成新一代种群", "#ffe0e0")
arrow(ax, 5.0, 8.0, 5.0, 7.2)
arrow(ax, 5.0, 6.2, 5.0, 5.4)
arrow(ax, 5.0, 4.4, 5.0, 3.6)
arrow(ax, 3.6, 3.1, 1.8, 3.1)
arrow(ax, 1.8, 3.1, 1.8, 6.7)
arrow(ax, 1.8, 6.7, 3.6, 6.7)
ax.text(1.2, 5.0, "未达\n终止条件", fontsize=8.5, color="#a33")
ax.text(7.0, 4.9, "满足精度/\n最大代数", fontsize=8.5, color="#2b3a55")
arrow(ax, 6.4, 4.9, 8.4, 4.9)
box(ax, 8.4, 4.3, 1.6, 1.2, "最优解\n(超参数)", "#e7d9ff")
plt.tight_layout()
plt.savefig(f"{OUT}/fig3_ga.png", dpi=150, bbox_inches="tight")
plt.close()

# ---------- 图4：ECA 注意力结构（原图3，后移） ----------
fig, ax = plt.subplots(figsize=(7.2, 2.6))
ax.set_xlim(0, 12); ax.set_ylim(0, 4); ax.axis("off")
ax.text(6, 3.6, "图4  ECA 通道注意力机制结构", ha="center", fontsize=12, weight="bold")
box(ax, 0.4, 1.2, 1.8, 1.0, "输入特征图\nH×W×C", "#cfe3ff")
box(ax, 2.6, 1.2, 1.8, 1.0, "全局平均池化\nGAP", "#d9f2e6")
box(ax, 4.8, 1.2, 1.9, 1.0, "1D 卷积\n(核K自适应)", "#fff0c2")
box(ax, 7.0, 1.2, 1.5, 1.0, "Sigmoid", "#ffe0e0")
box(ax, 8.8, 1.2, 2.4, 1.0, "通道权重×输入\n(不降维交互)", "#e7d9ff")
for x1, x2 in [(2.2,2.6),(4.4,4.8),(6.7,7.0),(8.3,8.8)]:
    arrow(ax, x1, 1.7, x2, 1.7)
plt.tight_layout()
plt.savefig(f"{OUT}/fig4_eca.png", dpi=150, bbox_inches="tight")
plt.close()

# ---------- 图5：智能计算三大范式—系统映射 ----------
fig, ax = plt.subplots(figsize=(7.6, 4.4))
ax.set_xlim(0, 12); ax.set_ylim(0, 10); ax.axis("off")
ax.text(6, 9.6, "图5  智能计算三大范式与系统角色的映射", ha="center", fontsize=12, weight="bold")
# 左：三大范式
box(ax, 0.4, 7.2, 3.0, 1.4, "连接主义\nCNN / YOLO", "#cfe3ff")
box(ax, 0.4, 5.0, 3.0, 1.4, "进化主义\n遗传算法 GA", "#d9f2e6")
box(ax, 0.4, 2.8, 3.0, 1.4, "结构偏置\nECA 注意力", "#fff0c2")
# 中：内核
box(ax, 4.6, 4.2, 2.8, 2.2, "RK3588\n智能计算内核", "#ffe0e0")
# 右：角色
box(ax, 8.4, 7.2, 3.2, 1.4, "缺陷识别主引擎\n(端到端回归)", "#e7d9ff")
box(ax, 8.4, 5.0, 3.2, 1.4, "超参数/锚框\n自动寻优", "#d6e4ff")
box(ax, 8.4, 2.8, 3.2, 1.4, "轻量化\n精度增强", "#ffeec2")
arrow(ax, 3.4, 7.9, 4.6, 5.6)
arrow(ax, 3.4, 5.7, 4.6, 5.3)
arrow(ax, 3.4, 3.5, 4.6, 4.8)
arrow(ax, 7.4, 5.6, 8.4, 7.9)
arrow(ax, 7.4, 5.3, 8.4, 5.7)
arrow(ax, 7.4, 4.8, 8.4, 3.5)
ax.text(2.0, 0.6, "思想内核：从数据中学习 / 种群演化 / 结构先验", fontsize=8.5, color="#666")
plt.tight_layout()
plt.savefig(f"{OUT}/fig5_mapping.png", dpi=150, bbox_inches="tight")
plt.close()

# ---------- 图6：实验结果可视化 ----------
fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.4))
models = ["YOLOv8n", "YOLOv11n", "本文(+\nECA)"]
map50 = [0.931, 0.942, 0.959]
npu_lat = [11.4, 10.8, 9.6]
# 左：mAP50
ax = axes[0]
bars = ax.bar(models, map50, color=["#9ec5ff", "#6fa8ff", "#2b6cff"])
ax.set_ylim(0.85, 1.0); ax.set_ylabel("mAP50", fontsize=10)
ax.set_title("检测精度 (mAP50)", fontsize=11)
for b, v in zip(bars, map50):
    ax.text(b.get_x()+b.get_width()/2, v+0.002, f"{v:.3f}", ha="center", fontsize=9)
# 右：RK3588 NPU 时延
ax = axes[1]
bars2 = ax.bar(models, npu_lat, color=["#ffcf9e", "#ffb36f", "#ff7a2b"])
ax.set_ylabel("时延 / ms", fontsize=10); ax.set_title("RK3588 NPU 单帧时延", fontsize=11)
for b, v in zip(bars2, npu_lat):
    ax.text(b.get_x()+b.get_width()/2, v+0.1, f"{v:.1f}", ha="center", fontsize=9)
fig.suptitle("图6  主流模型与本文方法在 RK3588 NPU 上的性能对比", fontsize=12, weight="bold", y=1.02)
plt.tight_layout()
plt.savefig(f"{OUT}/fig6_results.png", dpi=150, bbox_inches="tight")
plt.close()
print("figs done")
