# -*- coding: utf-8 -*-
"""画 2x2 实验 4 档 F1 对比柱图（A/B/C/D，4 色区分）。
权威数据：板端 2x2 300 张 holdout 真实结果。
用法：  .venv/Scripts/python.exe tools/_render_2x2_chart.py
"""
import os
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import matplotlib.pyplot as plt

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, 'output', '缺陷检测项目周报_v4_39类', 'config_2x2_chart.png')

# 4 档配置
configs = [
    ('A  旧 e50 + uniform 0.20', 0.7376, '#2E7D32'),   # 绿：最优
    ('B  新 e100 + uniform 0.20', 0.7162, '#1565C0'),
    ('C  新 e100 + per-class',    0.7064, '#FB8C00'),
    ('D  旧 e50 + per-class',     0.7295, '#0D47A1'),
]

fig, ax = plt.subplots(figsize=(10, 5.2))
names = [c[0] for c in configs]
f1s = [c[1] for c in configs]
colors = [c[2] for c in configs]
y = list(range(len(configs)))
bars = ax.barh(y, f1s, color=colors, edgecolor='white', height=0.62)
ax.set_yticks(y)
ax.set_yticklabels(names, fontsize=11)
ax.invert_yaxis()  # A 在最上
for i, v in enumerate(f1s):
    ax.text(v + 0.001, i, '  %.4f' % v, va='center', fontsize=10, color='#333', fontweight='bold')
# 整体参考线
mean_f1 = sum(f1s) / len(f1s)
ax.axvline(mean_f1, color='#888', linestyle=':', linewidth=0.9, alpha=0.6)
ax.set_xlim(0.69, 0.75)
ax.set_xlabel('F1 (板端真实 socket · 300 张旧 holdout)', fontsize=10)
ax.set_title('四格实测：最优是「旧模型 + 统一阈值」', fontsize=13, color='#0D47A1', pad=12)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(axis='x', linestyle=':', alpha=0.35)
# 标注
ax.text(0.694, 0.05, '绿色 = 当前生产配置 A (0.7376)',
        transform=ax.transAxes, fontsize=9, color='#2E7D32', alpha=0.9)
plt.tight_layout()
plt.savefig(OUT, dpi=150, bbox_inches='tight', facecolor='white')
print('已生成 %s' % OUT)
