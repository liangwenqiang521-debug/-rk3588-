# -*- coding: utf-8 -*-
"""画 39 类 F1 横向柱图（按 F1 升序），高亮 holdout 上 F1 < 0.6 的弱类。
权威数据 = _eval_steel39_strat.json holdout_base.per_class。
用法：  .venv/Scripts/python.exe tools/_render_f1_classes39.py
"""
import os
import sys
import json
import numpy as np

# 用无 matplotlib 兜底（系统 py 不一定有），优先用 cv2 画
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False
import cv2

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON = os.path.join(_ROOT, '模型训练', '_eval_steel39_strat.json')
OUT = os.path.join(_ROOT, 'output', '缺陷检测项目周报_v4_39类', 'classes39_f1_chart.png')

# cls id -> 中文名（与 _render_classes39_thumbs.py 一致）
NAME_ZH = {
    0:'亮划痕',1:'龟裂',2:'折痕',3:'月牙缺口',4:'暗划痕',
    5:'精轧辊印',6:'夹杂物',7:'氧化铁皮压入',8:'铁皮灰',9:'油污',
    10:'板系氧化铁皮',11:'温系氧化铁皮',12:'斑块',13:'麻面',14:'冲孔',
    15:'红斑铁皮',16:'轧入氧化皮',17:'轧制凹坑',18:'二次锈皮',19:'丝斑',
    20:'夹渣',21:'腰部折痕',22:'水渍',23:'焊缝线',24:'白锈',
    25:'切边开口',26:'水渣痕',27:'渣皮',28:'纵向裂纹',29:'翘曲',
    30:'外折',31:'褶皱',32:'块状氧化铁皮',33:'条纹氧化铁皮',34:'异物',
    35:'气孔',36:'断裂',37:'散边毛刺',38:'厚薄不均',
}
KEYS = [
    'bright_scratch','crazing','crease','crescent_gap','dark_scratches',
    'finishing_roll_printing','inclusion','iron_scale_compression','iron_sheet_ash','oil_spot',
    'oxide_scale_plate','oxide_scale_temp','patches','pitted_surface','punching',
    'red_iron_sheet','rolled-in_scale','rolled_pit','secondary_rust_skin','silk_spot',
    'slag_inclusion','waist_folding','water_spot','welding_line','white_rust',
    'cutting_opening','water_slag_mark','slag_skin','longitudinal_crack','warp',
    'external_fold','wrinkle','blocky_scale','striated_scale','foreign_obj',
    'blowhole','break','fray','uneven',
]


def main():
    with open(JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    pc = data['holdout_base']['per_class']
    micro = data['holdout_base']['micro']
    print('holdout F1 = %.4f (uniform 0.20)' % micro['f1'])

    rows = []
    for i, k in enumerate(KEYS):
        v = pc.get(k)
        if v is None:
            continue
        rows.append((v['f1'], i, k, NAME_ZH[i], v.get('gt', 0), v.get('tp', 0), v.get('fp', 0), v.get('fn', 0)))
    rows.sort(key=lambda r: r[0])

    if HAS_MPL:
        # matplotlib 路径
        matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
        matplotlib.rcParams['axes.unicode_minus'] = False
        names_zh = [r[3] for r in rows]
        f1s = [r[0] for r in rows]
        f1s_capped = [min(x, 1.05) for x in f1s]  # 截断
        colors = []
        for r in rows:
            if r[0] < 0.55:
                colors.append('#C62828')   # 红：弱类
            elif r[0] < 0.7:
                colors.append('#FB8C00')   # 橙：边缘
            else:
                colors.append('#1565C0')   # 蓝：合格

        fig, ax = plt.subplots(figsize=(11, 13))
        y = np.arange(len(rows))
        ax.barh(y, f1s_capped, color=colors, edgecolor='white', height=0.78)
        ax.set_yticks(y)
        ax.set_yticklabels([r[3] for r in rows], fontsize=9, fontfamily='SimHei')
        for i, r in enumerate(rows):
            x = min(r[0], 1.05) + 0.01
            ax.text(x, i, '%.3f  (gt=%d)' % (r[0], r[4]), va='center', fontsize=8, color='#333')
        ax.axvline(micro['f1'], color='#0D47A1', linestyle='--', linewidth=1.2, alpha=0.7)
        ax.text(micro['f1'], len(rows) - 0.6, ' 整体 F1=%.4f' % micro['f1'],
                color='#0D47A1', fontsize=10, va='center')
        ax.set_xlim(0, 1.15)
        ax.set_xlabel('F1 (holdout, conf 0.20, IoU 0.5)', fontsize=10)
        ax.set_title('39 类 holdout F1 分布（按 F1 升序）', fontsize=13, fontfamily='SimHei', color='#0D47A1', pad=14)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='x', linestyle=':', alpha=0.4)
        # 弱类图例
        from matplotlib.patches import Patch
        legend = [
            Patch(facecolor='#C62828', label='弱类 F1<0.55'),
            Patch(facecolor='#FB8C00', label='边缘 0.55≤F1<0.7'),
            Patch(facecolor='#1565C0', label='合格 F1≥0.7'),
        ]
        ax.legend(handles=legend, loc='lower right', fontsize=9, framealpha=0.92)
        plt.tight_layout()
        plt.savefig(OUT, dpi=150, bbox_inches='tight', facecolor='white')
        print('已生成 %s' % OUT)
        return

    # 兜底 cv2 路径（不期望走到这里）
    print('matplotlib 不可用，跳过')


if __name__ == '__main__':
    main()
