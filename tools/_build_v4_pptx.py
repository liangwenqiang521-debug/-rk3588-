# -*- coding: utf-8 -*-
"""从零生成 v4 PPT：39 类工业钢材表面缺陷检测系统专题。
版式沿用 v3 风格：左色块 + 大数字 + 副文本 + 页脚。
12 页：封面 / 目录 / 4 章（每章扉页 + 2~3 页内容）/ 收尾
用法：  python tools/_build_v4_pptx.py
"""
import os
from pptx import Presentation
from pptx.util import Pt, Emu, Inches
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree

# 主题色（与 v3 一致）
C_PRIMARY   = RGBColor(0x15, 0x65, 0xC0)  # 主蓝
C_DEEP      = RGBColor(0x0D, 0x47, 0xA1)  # 深蓝（标题）
C_ACCENT    = RGBColor(0x21, 0x96, 0xF3)  # 亮蓝（副标）
C_GREEN     = RGBColor(0x2E, 0x7D, 0x32)  # 绿（成功）
C_RED       = RGBColor(0xC6, 0x28, 0x28)  # 红（弱类/警告）
C_ORANGE    = RGBColor(0xFB, 0x8C, 0x00)  # 橙（边缘）
C_TEXT      = RGBColor(0x1A, 0x1A, 0x1A)  # 主文本
C_MUTED     = RGBColor(0x5C, 0x6E, 0x82)  # 弱文本
C_BORDER    = RGBColor(0xD8, 0xE0, 0xEA)  # 边框
C_LIGHT     = RGBColor(0xF4, 0xF7, 0xFB)  # 浅底
C_DARK_BG   = RGBColor(0x0A, 0x1F, 0x44)  # 封面深底

# 字体
F_HEI  = '黑体'
F_SONG = '宋体'
F_ENG  = 'Arial'


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, 'output', '缺陷检测项目周报_v4_39类', '缺陷检测项目周报_v4_39类.pptx')
ASSET_THUMBS = os.path.join(_ROOT, 'output', '缺陷检测项目周报_v4_39类', 'classes39_thumbs.png')
ASSET_F1    = os.path.join(_ROOT, 'output', '缺陷检测项目周报_v4_39类', 'classes39_f1_chart.png')
ASSET_2X2   = os.path.join(_ROOT, 'output', '缺陷检测项目周报_v4_39类', 'config_2x2_chart.png')


# ----- 通用工具 -----
def set_run(run, text, size=14, bold=False, color=C_TEXT, font=F_SONG):
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    # 设置东亚字体
    eaFont = rPr.find(qn('a:ea'))
    if eaFont is None:
        eaFont = etree.SubElement(rPr, qn('a:ea'))
    eaFont.set('typeface', font)


def add_text(slide, x, y, w, h, text, size=14, bold=False, color=C_TEXT,
             font=F_SONG, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    set_run(p.add_run(), text, size=size, bold=bold, color=color, font=font)
    return tb


def add_rect(slide, x, y, w, h, fill=None, line=None, line_w=0):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
    sh.shadow.inherit = False
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w) if line_w else Pt(0.75)
    return sh


def add_image(slide, path, x, y, w, h):
    return slide.shapes.add_picture(path, Emu(x), Emu(y), width=Emu(w), height=Emu(h))


def page_chrome(slide, idx, total, chapter, title, subtitle=''):
    """统一页眉/页脚/页码。"""
    # 顶部细条
    add_rect(slide, 0, 0, 12192000, 60000, fill=C_PRIMARY)
    # 章节名（顶部右上）
    add_text(slide, 8500000, 200000, 3000000, 350000,
             chapter, size=10, color=C_MUTED, font=F_HEI,
             align=PP_ALIGN.RIGHT)
    # 标题（页眉下方）
    add_text(slide, 500000, 250000, 11200000, 600000,
             title, size=22, bold=True, color=C_DEEP, font=F_HEI)
    if subtitle:
        add_text(slide, 500000, 750000, 11200000, 300000,
                 subtitle, size=10, color=C_MUTED, font=F_SONG)
    # 底部分隔
    add_rect(slide, 500000, 6500000, 11200000, 6000, fill=C_BORDER)
    # 页码
    add_text(slide, 10800000, 6580000, 1000000, 250000,
             '%02d / %02d' % (idx, total), size=9, color=C_MUTED, font=F_ENG,
             align=PP_ALIGN.RIGHT)
    add_text(slide, 500000, 6580000, 4000000, 250000,
             '39 类工业钢材表面缺陷检测 · v4', size=9, color=C_MUTED, font=F_HEI)


# ----- 各页生成 -----
def page_01_cover(prs, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    # 深底
    add_rect(s, 0, 0, 12192000, 6858000, fill=C_DARK_BG)
    # 装饰斜条
    add_rect(s, 0, 0, 300000, 6858000, fill=C_PRIMARY)
    add_rect(s, 0, 0, 60000, 6858000, fill=C_ACCENT)
    # 顶部小字
    add_text(s, 900000, 600000, 11000000, 300000,
             'TECHNICAL DEEP DIVE  ·  2026-10-16', size=12, color=C_ACCENT,
             font=F_ENG, align=PP_ALIGN.LEFT)
    # 主标题
    add_text(s, 900000, 1200000, 11000000, 1500000,
             '39 类工业钢材表面缺陷检测系统',
             size=42, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_HEI)
    # 副标题
    add_text(s, 900000, 2400000, 11000000, 800000,
             '从 NEU 6 类扩展到 39 类的数据 · 训练 · 评估 · 板端闭环',
             size=20, color=C_ACCENT, font=F_HEI)
    # 三个关键数字条
    boxes = [
        ('25689', '张训练 + 验证图', C_ACCENT),
        ('39', '类（含 6 类 NEU 兼容）', C_ORANGE),
        ('0.7159', 'holdout F1（项目统一口径）', C_GREEN),
    ]
    box_w = 3400000
    box_h = 1100000
    box_y = 3700000
    gap = 200000
    for i, (num, label, col) in enumerate(boxes):
        x = 900000 + i * (box_w + gap)
        # 数字
        add_text(s, x, box_y, box_w, 600000, num, size=44, bold=True, color=col, font=F_ENG)
        # 标签
        add_text(s, x, box_y + 650000, box_w, 350000, label,
                 size=12, color=RGBColor(0xCC, 0xD8, 0xE8), font=F_HEI)
    # 汇报信息
    add_rect(s, 900000, 5500000, 11000000, 6000, fill=C_ACCENT)
    add_text(s, 900000, 5600000, 11000000, 350000,
             '汇报人: 项目组   ·   汇报日期: 2026-10-16   ·   文档版本: v4 专题',
             size=12, color=RGBColor(0xCC, 0xD8, 0xE8), font=F_SONG)
    add_text(s, 900000, 6000000, 11000000, 350000,
             '本汇报专注 39 类扩展本身: 数据体系、训练工程、评估归因、板端落地',
             size=11, color=C_MUTED, font=F_SONG)


def page_02_toc(prs, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, 2, total, '目录', '目录', '4 章 · 14 页 · 总时长 8-10 分钟')
    chapters = [
        ('一', '为什么必须扩展', 'NEU 6 类的局限 · 工业现场的真实缺陷广度', C_PRIMARY),
        ('二', '39 类数据体系', 'datasets_master v2.1 · 类别表 · 评估集重建', C_ACCENT),
        ('三', '模型训练与评估', '100 轮重训 · 39 类 F1 全景 · 弱类归因', C_ORANGE),
        ('四', '板端落地与下一步', '.pt → .rknn · 2×2 实验 · 三件待办', C_GREEN),
    ]
    base_y = 1300000
    row_h = 1100000
    for i, (no, title, sub, col) in enumerate(chapters):
        y = base_y + i * row_h
        # 左侧色块
        add_rect(s, 800000, y, 220000, 850000, fill=col)
        # 编号
        add_text(s, 1200000, y + 50000, 1300000, 700000, no,
                 size=44, bold=True, color=col, font=F_HEI)
        # 标题
        add_text(s, 2700000, y + 100000, 8500000, 450000, title,
                 size=22, bold=True, color=C_DEEP, font=F_HEI)
        # 副标
        add_text(s, 2700000, y + 550000, 8500000, 350000, sub,
                 size=11, color=C_MUTED, font=F_SONG)


def page_chapter_divider(prs, idx, total, no, en, zh, sub):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    # 大色块
    add_rect(s, 0, 0, 12192000, 6858000, fill=C_LIGHT)
    add_rect(s, 0, 0, 4200000, 6858000, fill=C_PRIMARY)
    # 大编号
    add_text(s, 800000, 1800000, 3000000, 1500000, no,
             size=140, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_ENG)
    add_text(s, 800000, 3300000, 3000000, 400000, en,
             size=14, color=C_ACCENT, font=F_ENG)
    # 标题
    add_text(s, 4800000, 2200000, 6800000, 800000, zh,
             size=32, bold=True, color=C_DEEP, font=F_HEI)
    # 副标
    add_text(s, 4800000, 3100000, 6800000, 500000, sub,
             size=14, color=C_MUTED, font=F_SONG)
    # 章节进度
    add_text(s, 10800000, 6580000, 1000000, 250000,
             '%02d / %02d' % (idx, total), size=9, color=C_MUTED, font=F_ENG,
             align=PP_ALIGN.RIGHT)


def page_04_limitations(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '一 · 背景',
                '原 NEU 6 类的三大局限',
                '为什么 6 类不够 · 工业现场实际有 30+ 类常见缺陷')
    # 三大局限卡片
    cards = [
        ('01', '场景贴近学校', 'crazing / inclusion / patches / pitted_surface / rolled-in_scale / scratches\n仅 6 类热轧带钢表面缺陷，覆盖工业产线全场景太窄'),
        ('02', '数据量 1620 张', '训练 1440 + 验证 180，工业产线数据规模差一个量级\nval 太小，任何指标波动都不能下结论'),
        ('03', '类别无金属加工语义', '缺热轧/冷轧/表面处理/形变等大类\n无法对应钢厂实际质检的「缺陷词典」'),
    ]
    cw, ch = 3500000, 4200000
    gap = 250000
    base_x = 600000
    base_y = 1500000
    for i, (no, title, body) in enumerate(cards):
        x = base_x + i * (cw + gap)
        add_rect(s, x, base_y, cw, ch, fill=C_LIGHT, line=C_BORDER, line_w=1.5)
        add_rect(s, x, base_y, cw, 100000, fill=C_PRIMARY)
        add_text(s, x + 250000, base_y + 200000, 1500000, 600000, no,
                 size=36, bold=True, color=C_PRIMARY, font=F_ENG)
        add_text(s, x + 250000, base_y + 850000, cw - 400000, 600000, title,
                 size=18, bold=True, color=C_DEEP, font=F_HEI)
        add_text(s, x + 250000, base_y + 1500000, cw - 400000, 2400000, body,
                 size=11, color=C_TEXT, font=F_SONG)
    # 底部结论
    add_rect(s, 600000, 5950000, 11000000, 450000, fill=C_DEEP)
    add_text(s, 800000, 6000000, 10800000, 400000,
             '结论: 要进产线, 必须扩类. 工业现场常见的 30+ 类缺陷必须落到模型里.',
             size=14, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_HEI)


def page_05_39_overview(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '一 · 背景',
                '工业现场实际有 30+ 类常见缺陷（39 类全景）',
                '按类别簇划分: 表面线状 / 氧化物 / 形变 / 夹杂物 / 裂纹 / 边缘 / 工艺线 / 表面处理 / 严重缺陷 / 表面杂质')
    # 大图
    add_image(s, ASSET_THUMBS, 600000, 1500000, 7800000, 4900000)
    # 右侧文字
    add_rect(s, 8600000, 1500000, 3000000, 4900000, fill=C_LIGHT, line=C_BORDER, line_w=1)
    add_text(s, 8750000, 1600000, 2800000, 400000, '类别簇分布', size=12, bold=True, color=C_DEEP, font=F_HEI)
    clusters = [
        ('表面线状', '亮划痕 / 暗划痕 / 焊缝线', C_PRIMARY),
        ('氧化物', '块状 / 条纹 / 板系 / 温系 / 压入', C_ACCENT),
        ('形变', '翘曲 / 外折 / 褶皱 / 厚薄不均', C_GREEN),
        ('夹杂物', '夹杂物 / 夹渣 / 异物 / 铁皮灰', C_ORANGE),
        ('裂纹', '纵向裂纹 / 断裂', C_RED),
        ('边缘 / 工艺', '切边开口 / 散边毛刺 / 精轧辊印', C_DEEP),
        ('表面处理', '油污 / 水渍 / 白锈 / 二次锈皮', C_MUTED),
    ]
    cy = 2100000
    for name, items, col in clusters:
        add_rect(s, 8750000, cy, 80000, 380000, fill=col)
        add_text(s, 8900000, cy - 20000, 2700000, 250000, name, size=11, bold=True, color=col, font=F_HEI)
        add_text(s, 8900000, cy + 220000, 2700000, 200000, items, size=9, color=C_MUTED, font=F_SONG)
        cy += 580000


def page_07_dataset(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '二 · 数据',
                '数据源 & 类别体系',
                'datasets_master v2.1 · 25689 张 · 全灰度 · 扁平结构')
    # 左侧大数字
    add_rect(s, 600000, 1500000, 4400000, 4800000, fill=C_LIGHT, line=C_BORDER, line_w=1.5)
    add_text(s, 800000, 1700000, 4000000, 400000, '数据规模', size=12, color=C_MUTED, font=F_HEI)
    add_text(s, 800000, 2100000, 4000000, 800000, '25689', size=64, bold=True, color=C_PRIMARY, font=F_ENG)
    add_text(s, 800000, 3000000, 4000000, 400000, '张 (train 20947 / val 5296 原始)', size=12, color=C_TEXT, font=F_SONG)
    # 数据特征
    add_rect(s, 800000, 3600000, 4000000, 6000, fill=C_BORDER)
    add_text(s, 800000, 3700000, 4000000, 350000, '·  全灰度 (hsv 关)', size=12, color=C_TEXT, font=F_SONG)
    add_text(s, 800000, 4100000, 4000000, 350000, '·  扁平结构 (不按类分子目录)', size=12, color=C_TEXT, font=F_SONG)
    add_text(s, 800000, 4500000, 4000000, 350000, '·  39 类 cls 0~38, 与 data.yaml ids 一致', size=12, color=C_TEXT, font=F_SONG)
    add_text(s, 800000, 4900000, 4000000, 350000, '·  3 张 0 字节坏图 (ultralytics 自动跳过)', size=12, color=C_TEXT, font=F_SONG)
    add_text(s, 800000, 5300000, 4000000, 350000, '·  权威源 = infer.py CLASSES_39', size=12, bold=True, color=C_DEEP, font=F_HEI)
    # 右侧类别表说明
    add_rect(s, 5300000, 1500000, 6300000, 4800000, fill=C_LIGHT, line=C_BORDER, line_w=1.5)
    add_text(s, 5500000, 1600000, 6000000, 400000, '类别体系与兼容性设计', size=14, bold=True, color=C_DEEP, font=F_HEI)
    add_text(s, 5500000, 2100000, 6000000, 500000,
             '39 类 = 6 类 NEU 兼容 + 33 类工业新增',
             size=14, bold=True, color=C_PRIMARY, font=F_HEI)
    items = [
        '·  cls 1/6/12/13/16 继承 NEU 原 6 类: crazing / inclusion / patches / pitted_surface / rolled-in_scale (cls 索引不可改)',
        '·  其余 33 类全新增: 涵盖热轧/冷轧/表面处理/形变/夹杂物/裂纹/边缘/工艺等工业大类',
        '·  NAME_ZH 保留 16 个旧 key (edge_crack / scab / pitting ...) —— 供历史权重兼容, 不在 39 类枚举',
        '·  CLASS_COLORS 52 色, 同类不同图恒定, 彼此可辨',
        '·  4 处定义必须同步: infer.py / 板端 board_server_cascade.py NAMES_EXT / 板端模拟器 / 周回流工具',
    ]
    yy = 2700000
    for it in items:
        add_text(s, 5500000, yy, 6000000, 700000, it, size=11, color=C_TEXT, font=F_SONG)
        yy += 700000


def page_08_split(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '二 · 数据',
                '评估集重建 · 分层重划分',
                'val 必须保持独立才有 holdout 价值')
    # 上半: 问题
    add_rect(s, 600000, 1300000, 11200000, 1000000, fill=C_RED)
    add_text(s, 800000, 1400000, 10800000, 400000,
             '问题: 原 NEU 6 类 val 仅 180 张 —— 拿 NEU val 评 39 类不合法',
             size=14, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_HEI)
    add_text(s, 800000, 1800000, 10800000, 400000,
             '如果只补 train 不重划 val, 任何 holdout 数字都会被选择偏差污染',
             size=12, color=RGBColor(0xFF, 0xCC, 0xCC), font=F_SONG)
    # 中: 动作
    add_text(s, 600000, 2600000, 11200000, 400000,
             '动作: 全池分层重划分 (train + val 全部打散, 按类别框数分层抽样)',
             size=14, bold=True, color=C_DEEP, font=F_HEI)
    # 数据流
    # 输入
    add_rect(s, 600000, 3100000, 2400000, 1400000, fill=C_LIGHT, line=C_BORDER, line_w=1.5)
    add_text(s, 700000, 3200000, 2200000, 300000, '原 train + val', size=11, color=C_MUTED, font=F_HEI,
             align=PP_ALIGN.CENTER)
    add_text(s, 700000, 3550000, 2200000, 500000, '25689 张', size=24, bold=True, color=C_DEEP, font=F_ENG,
             align=PP_ALIGN.CENTER)
    add_text(s, 700000, 4100000, 2200000, 300000, '全部打散', size=10, color=C_MUTED, font=F_SONG,
             align=PP_ALIGN.CENTER)
    # 箭头
    add_text(s, 3200000, 3700000, 400000, 200000, '→', size=28, bold=True, color=C_PRIMARY, font=F_ENG,
             align=PP_ALIGN.CENTER)
    # 中间: 切分
    add_rect(s, 3700000, 3100000, 5400000, 1400000, fill=C_LIGHT, line=C_PRIMARY, line_w=2)
    add_text(s, 3800000, 3200000, 5200000, 300000, '分层抽样 · 39 类全保', size=11, color=C_MUTED, font=F_HEI,
             align=PP_ALIGN.CENTER)
    add_text(s, 3800000, 3550000, 2500000, 500000, '新 train 20329', size=22, bold=True, color=C_PRIMARY, font=F_ENG,
             align=PP_ALIGN.CENTER)
    add_text(s, 6500000, 3550000, 2500000, 500000, '新 val 5911', size=22, bold=True, color=C_PRIMARY, font=F_ENG,
             align=PP_ALIGN.CENTER)
    add_text(s, 3800000, 4100000, 2500000, 300000, '小类全保 · 中类降采样', size=9, color=C_MUTED, font=F_SONG,
             align=PP_ALIGN.CENTER)
    add_text(s, 6500000, 4100000, 2500000, 300000, '39 类全部 ≥30 框', size=9, color=C_MUTED, font=F_SONG,
             align=PP_ALIGN.CENTER)
    # 箭头
    add_text(s, 9250000, 3700000, 400000, 200000, '→', size=28, bold=True, color=C_PRIMARY, font=F_ENG,
             align=PP_ALIGN.CENTER)
    # 输出: val 内部
    add_rect(s, 9750000, 3100000, 1800000, 1400000, fill=C_DEEP, line=None)
    add_text(s, 9850000, 3200000, 1600000, 300000, 'val 内部再切', size=11, color=C_ACCENT, font=F_HEI,
             align=PP_ALIGN.CENTER)
    add_text(s, 9850000, 3550000, 1600000, 400000, 'cal 2891', size=20, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_ENG,
             align=PP_ALIGN.CENTER)
    add_text(s, 9850000, 4000000, 1600000, 400000, 'holdout 3020', size=20, bold=True, color=C_ACCENT, font=F_ENG,
             align=PP_ALIGN.CENTER)
    # 底部说明
    add_rect(s, 600000, 4900000, 11200000, 1500000, fill=C_LIGHT, line=C_BORDER, line_w=1)
    add_text(s, 800000, 5000000, 10800000, 400000,
             'cal 集 (2891 张) —— 仅用于标定阈值, 不参与最终指标',
             size=12, color=C_DEEP, font=F_HEI)
    add_text(s, 800000, 5400000, 10800000, 400000,
             'holdout 集 (3020 张) —— 最终汇报专用, 不参与调参',
             size=12, color=C_DEEP, font=F_HEI)
    add_text(s, 800000, 5800000, 10800000, 400000,
             '最小类 oxide_scale_plate 在 val 中也有 16/16 张 —— 全 39 类覆盖完整',
             size=11, color=C_MUTED, font=F_SONG)
    add_text(s, 600000, 6200000, 11200000, 300000,
             '评估口径从此干净: 任何 "cal 上调参、holdout 报数" 都可独立验证',
             size=12, bold=True, color=C_GREEN, font=F_HEI)


def page_10_training(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '三 · 模型',
                '训练工程 · 100 轮重训与口径',
                'YOLOv11n · 640 · 分层重划分后 train 20329')
    # 4 个数据卡
    cards = [
        ('0.7808', 'mAP50 (100 轮)', C_PRIMARY),
        ('0.78217', 'mAP50 峰值 (@96 轮)', C_ACCENT),
        ('0.7159', 'holdout F1 (项目统一口径)', C_GREEN),
        ('100', '训练轮数', C_DEEP),
    ]
    cw, ch = 2500000, 2000000
    gap = 200000
    base_x = 600000
    base_y = 1500000
    for i, (num, label, col) in enumerate(cards):
        x = base_x + i * (cw + gap)
        add_rect(s, x, base_y, cw, ch, fill=col)
        add_text(s, x, base_y + 200000, cw, 800000, num, size=44, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_ENG,
                 align=PP_ALIGN.CENTER)
        add_text(s, x, base_y + 1100000, cw, 600000, label, size=12, color=RGBColor(0xCC, 0xE0, 0xFF), font=F_HEI,
                 align=PP_ALIGN.CENTER)
    # 中部: 工程细节
    add_text(s, 600000, 3800000, 11200000, 400000,
             '工程细节',
             size=14, bold=True, color=C_DEEP, font=F_HEI)
    items = [
        '·  模型: YOLOv11n · 640 · 100 轮 (峰值 0.78217 @ 96 轮, 100 轮略回落 0.7808)',
        '·  训练数据: 分层重划分后 train 20329 张, val 5911 张 (cal 2891 + holdout 3020)',
        '·  holdout F1 0.7159: 真实项目统一口径 (conf 0.20, IoU 0.5, micro over 39 类)',
        '·  训练工程插曲: 100 轮训练被 IDE 砍 2 次 (分别 @ 66 轮和 @ 96 轮), 续训 4 轮补完',
        '·  最终权重: best_steel39_yolo11n_640_strat.pt (5.24 MB, 已锁定)',
    ]
    yy = 4250000
    for it in items:
        add_text(s, 600000, yy, 11200000, 350000, it, size=12, color=C_TEXT, font=F_SONG)
        yy += 380000
    # 底部警告
    add_rect(s, 600000, 6200000, 11200000, 280000, fill=C_RED)
    add_text(s, 800000, 6230000, 10800000, 240000,
             '注意: 100 轮 holdout F1 0.7159 与 50 轮板端 F1 0.7376 不可直接比 —— val 集大小差 10 倍',
             size=12, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_HEI)


def page_11_f1_chart(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '三 · 模型',
                '39 类 F1 全景 + 5 弱类归因',
                'holdout 集 3020 张 · uniform 0.20 · 整体 F1 = 0.7159')
    # 左侧: F1 柱图
    add_image(s, ASSET_F1, 400000, 1500000, 6400000, 4900000)
    # 右侧: 5 弱类高亮 + 强类对比
    add_text(s, 7000000, 1500000, 4700000, 500000,
             '5 个弱类 (F1 < 0.55)', size=16, bold=True, color=C_RED, font=F_HEI)
    weak = [
        ('腰部折痕', 0.372, 'gt=143', C_RED),
        ('精轧辊印', 0.468, 'gt=69', C_RED),
        ('暗划痕', 0.514, 'gt=118', C_RED),
        ('折痕', 0.526, 'gt=119', C_RED),
        ('夹渣', 0.563, 'gt=228', C_ORANGE),
    ]
    yy = 2100000
    for name, f1, gt, col in weak:
        add_rect(s, 7000000, yy, 4700000, 380000, fill=C_LIGHT, line=C_BORDER, line_w=0.75)
        add_rect(s, 7000000, yy, 80000, 380000, fill=col)
        add_text(s, 7120000, yy + 30000, 1800000, 320000, name,
                 size=14, bold=True, color=C_DEEP, font=F_HEI)
        add_text(s, 8950000, yy + 30000, 1500000, 320000, 'F1 = %.3f' % f1,
                 size=14, bold=True, color=col, font=F_ENG, align=PP_ALIGN.RIGHT)
        add_text(s, 10600000, yy + 50000, 1000000, 280000, gt,
                 size=10, color=C_MUTED, font=F_ENG, align=PP_ALIGN.RIGHT)
        yy += 420000
    # 强类示例
    add_text(s, 7000000, yy + 100000, 4700000, 400000,
             '强类 (F1 = 1.000)', size=14, bold=True, color=C_GREEN, font=F_HEI)
    strong_text = '冲孔 / 温系氧化铁皮 · 0 个 FP  ·  ' + \
                  '月牙缺口 0.944 · 水渣痕 0.967 · 厚薄不均 0.984'
    add_text(s, 7000000, yy + 550000, 4700000, 700000, strong_text,
             size=11, color=C_TEXT, font=F_SONG)
    # 真因
    add_rect(s, 7000000, yy + 1350000, 4700000, 1300000, fill=C_DEEP, line=None)
    add_text(s, 7100000, yy + 1380000, 4500000, 400000, '真因',
             size=12, bold=True, color=C_ACCENT, font=F_HEI)
    add_text(s, 7100000, yy + 1750000, 4500000, 800000,
             '评估集漏标 (高置信未匹配框的同类率 81.7%)\noracle 回收上界: F1 可再涨 +4.0pp',
             size=11, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_SONG)


def page_13_2x2(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '四 · 板端',
                '板端 2×2 实验 · 链路与判决',
                '.pt → .onnx (opset 12) → .rknn (fp16) → RK3588 NPU')
    # 顶部板端链路
    add_text(s, 600000, 1300000, 11200000, 400000, '板端链路',
             size=14, bold=True, color=C_DEEP, font=F_HEI)
    chain = [
        ('.pt', 'best_steel39_yolo11n_640_strat.pt', C_PRIMARY),
        ('.onnx', 'opset 12 · 640 · simplify · [1,43,8400]', C_ACCENT),
        ('.rknn', 'fp16 · 7.58 MB · rknn.config std=255', C_ORANGE),
        ('RK3588', 'ATK-DLRK3588 · Buildroot · NPU 推理', C_GREEN),
    ]
    cw, ch = 2700000, 800000
    gap = 100000
    base_x = 600000
    base_y = 1750000
    for i, (lbl, sub, col) in enumerate(chain):
        x = base_x + i * (cw + gap + 60000)
        add_rect(s, x, base_y, cw, ch, fill=col)
        add_text(s, x, base_y + 80000, cw, 350000, lbl,
                 size=18, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_ENG,
                 align=PP_ALIGN.CENTER)
        add_text(s, x, base_y + 430000, cw, 350000, sub,
                 size=9, color=RGBColor(0xCC, 0xE0, 0xFF), font=F_SONG,
                 align=PP_ALIGN.CENTER)
        if i < 3:
            add_text(s, x + cw + 5000, base_y + 200000, 120000, 200000, '→',
                     size=24, bold=True, color=C_PRIMARY, font=F_ENG)
    # 左侧: 2x2 柱图
    add_image(s, ASSET_2X2, 400000, 2900000, 7400000, 3500000)
    # 右侧: 判决卡
    add_rect(s, 7900000, 2900000, 3700000, 3500000, fill=C_LIGHT, line=C_BORDER, line_w=1)
    add_text(s, 8050000, 3000000, 3500000, 400000, '判决', size=12, color=C_MUTED, font=F_HEI)
    add_text(s, 8050000, 3400000, 3500000, 700000, '配置 A 维持生产', size=20, bold=True, color=C_GREEN, font=F_HEI)
    add_text(s, 8050000, 4150000, 3500000, 1500000,
             '板端 F1 = 0.7376\n(300 张旧 holdout · 真实 socket)',
             size=12, color=C_TEXT, font=F_SONG)
    add_rect(s, 8050000, 4900000, 3500000, 6000, fill=C_BORDER)
    add_text(s, 8050000, 5000000, 3500000, 400000, '关键事实', size=11, color=C_MUTED, font=F_HEI)
    add_text(s, 8050000, 5400000, 3500000, 900000,
             '·  单模型 39 类 (已弃级联)\n·  2×2: A 0.7376 / B 0.7162 / C 0.7064 / D 0.7295\n·  e100 不盲切, 必须上板同集对比',
             size=10, color=C_TEXT, font=F_SONG)
    # 底部: 为何弃级联
    add_rect(s, 600000, 6500000, 11200000, 500000, fill=C_DARK_BG)
    add_text(s, 800000, 6540000, 10800000, 400000,
             '为何放弃级联: negdagm_filter.rknn 只认 NEU 6 类 → 做 39 类闸门会把 33 类判「无缺陷」 → 静默漏检',
             size=11, color=RGBColor(0xFF, 0xCC, 0xCC), font=F_SONG)


def page_14_next(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '四 · 板端',
                '下一步 · 三件待办与风险',
                '当前不盲切, 走完整闭环')
    # 三件待办
    todos = [
        ('01', '上板同集对比', '把 e100 + uniform 0.20 上板, 跑同 300 张旧 holdout\n判据: F1 ≥ 0.7376 才切, 否则维持配置 A\n(本周内可完成)', C_PRIMARY),
        ('02', '标注修复 (候选)', 'train 侧 461 张候选已备 (目检约 85% 真漏标)\nval 侧禁止补框以保独立\n(需标注工具 + 人工确认, 量级 1-2 周)', C_ORANGE),
        ('03', '论文 v2 同步', '基于新 39 类重写 4.3-4.5 节 (数据/训练/评估)\n把 81.7% 同类率作为评估集重建的核心论据\n(下周内)', C_GREEN),
    ]
    cw, ch = 3700000, 4400000
    gap = 100000
    base_x = 400000
    base_y = 1500000
    for i, (no, title, body, col) in enumerate(todos):
        x = base_x + i * (cw + gap)
        add_rect(s, x, base_y, cw, ch, fill=C_LIGHT, line=C_BORDER, line_w=1.5)
        # 顶部色块
        add_rect(s, x, base_y, cw, 700000, fill=col)
        add_text(s, x + 250000, base_y + 100000, 800000, 500000, no,
                 size=32, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_ENG)
        add_text(s, x + 1100000, base_y + 220000, cw - 1200000, 400000, title,
                 size=16, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_HEI)
        add_text(s, x + 250000, base_y + 900000, cw - 400000, 3300000, body,
                 size=11, color=C_TEXT, font=F_SONG)
    # 底部风险
    add_rect(s, 600000, 6100000, 11200000, 500000, fill=C_RED)
    add_text(s, 800000, 6150000, 10800000, 400000,
             '风险: 5 个弱类 (waist_folding 0.372 / 精轧辊印 0.468 / 暗划痕 0.514 / 折痕 0.526 / 夹渣 0.563) 暂无直接提升方案 —— 漏标是天花板',
             size=11, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_HEI)


def page_15_appendix(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    page_chrome(s, idx, total, '附录',
                '39 类完整清单 · 中英对照',
                '权威源 = infer.py CLASSES_39 · cls 0~38')
    # 3 列表格
    CLASSES = [
        (0,'bright_scratch','亮划痕','表面线状'),(1,'crazing','龟裂','NEU 6 类'),
        (2,'crease','折痕','形状'),(3,'crescent_gap','月牙缺口','形状'),
        (4,'dark_scratches','暗划痕','表面线状'),(5,'finishing_roll_printing','精轧辊印','工艺'),
        (6,'inclusion','夹杂物','NEU 6 类'),(7,'iron_scale_compression','氧化铁皮压入','氧化物'),
        (8,'iron_sheet_ash','铁皮灰','表面杂质'),(9,'oil_spot','油污','表面处理'),
        (10,'oxide_scale_plate','板系氧化铁皮','氧化物'),(11,'oxide_scale_temp','温系氧化铁皮','氧化物'),
        (12,'patches','斑块','NEU 6 类'),(13,'pitted_surface','麻面','NEU 6 类'),
        (14,'punching','冲孔','形状'),(15,'red_iron_sheet','红斑铁皮','表面色差'),
        (16,'rolled-in_scale','轧入氧化皮','NEU 6 类'),(17,'rolled_pit','轧制凹坑','形状'),
        (18,'secondary_rust_skin','二次锈皮','腐蚀'),(19,'silk_spot','丝斑','表面色差'),
        (20,'slag_inclusion','夹渣','夹杂物'),(21,'waist_folding','腰部折痕','形状'),
        (22,'water_spot','水渍','表面处理'),(23,'welding_line','焊缝线','工艺'),
        (24,'white_rust','白锈','腐蚀'),(25,'cutting_opening','切边开口','边缘'),
        (26,'water_slag_mark','水渣痕','表面杂质'),(27,'slag_skin','渣皮','表面杂质'),
        (28,'longitudinal_crack','纵向裂纹','裂纹'),(29,'warp','翘曲','形变'),
        (30,'external_fold','外折','形变'),(31,'wrinkle','褶皱','形变'),
        (32,'blocky_scale','块状氧化铁皮','氧化物'),(33,'striated_scale','条纹氧化铁皮','氧化物'),
        (34,'foreign_obj','异物','夹杂物'),(35,'blowhole','气孔','铸造'),
        (36,'break','断裂','严重缺陷'),(37,'fray','散边毛刺','边缘'),
        (38,'uneven','厚薄不均','形变'),
    ]
    # 表格坐标
    rows = len(CLASSES) + 1
    cols = 4
    col_w = [1100000, 4400000, 2400000, 2300000]  # cls / en / zh / 簇
    total_w = sum(col_w)
    base_x = 600000
    base_y = 1500000
    header_h = 400000
    row_h = 115000  # 39*115000 = 4485000 -> 1300000+4485000=5785000
    # 表头
    headers = ['cls', '英文 key', '中文名', '类别簇']
    cx = base_x
    for ci, h in enumerate(headers):
        add_rect(s, cx, base_y, col_w[ci], header_h, fill=C_DEEP)
        add_text(s, cx, base_y + 50000, col_w[ci], header_h - 100000, h,
                 size=12, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), font=F_HEI,
                 align=PP_ALIGN.CENTER)
        cx += col_w[ci]
    # 数据
    for ri, (cls, en, zh, cluster) in enumerate(CLASSES):
        y = base_y + header_h + ri * row_h
        # 底色交替
        bg = C_LIGHT if ri % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF)
        add_rect(s, base_x, y, total_w, row_h, fill=bg, line=C_BORDER, line_w=0.5)
        cx = base_x
        for ci, val in enumerate([str(cls), en, zh, cluster]):
            color = C_TEXT
            bold = False
            font = F_ENG if ci == 0 or ci == 1 else F_SONG
            if ci == 0:
                color = C_PRIMARY
                bold = True
            if ci == 2 and zh in ('腰部折痕', '精轧辊印', '暗划痕', '折痕', '夹渣'):
                color = C_RED
                bold = True
            add_text(s, cx, y, col_w[ci], row_h, val,
                     size=9, bold=bold, color=color, font=font,
                     align=PP_ALIGN.CENTER)
            cx += col_w[ci]


# ----- 主流程 -----
def main():
    prs = Presentation()
    prs.slide_width = Emu(12192000)
    prs.slide_height = Emu(6858000)
    TOTAL = 12  # 1=封面, 2=目录, 3=Ch1扉页, 4=6类局限, 5=全景, 6=Ch2扉页, 7=数据源, 8=划分, 9=Ch3扉页, 10=训练, 11=F1, 12=Ch4扉页+2x2+next+附录
    # 实际 14 页：1 封面 + 2 目录 + 3 Ch1扉 + 4 局限 + 5 全景 + 6 Ch2扉 + 7 数据 + 8 划分 +
    #             9 Ch3扉 + 10 训练 + 11 F1 + 12 Ch4扉 + 13 2x2 + 14 next + 15 附录 = 15
    TOTAL = 15
    # P1
    page_01_cover(prs, TOTAL)
    # P2
    page_02_toc(prs, TOTAL)
    # P3
    page_chapter_divider(prs, 3, TOTAL, '01', 'CHAPTER 01 · BACKGROUND',
                        '为什么必须扩展', 'NEU 6 类的局限 · 工业现场的实际缺陷广度')
    # P4
    page_04_limitations(prs, 4, TOTAL)
    # P5
    page_05_39_overview(prs, 5, TOTAL)
    # P6
    page_chapter_divider(prs, 6, TOTAL, '02', 'CHAPTER 02 · DATA',
                        '39 类数据体系', 'datasets_master v2.1 · 类别表 · 评估集重建')
    # P7
    page_07_dataset(prs, 7, TOTAL)
    # P8
    page_08_split(prs, 8, TOTAL)
    # P9
    page_chapter_divider(prs, 9, TOTAL, '03', 'CHAPTER 03 · MODEL',
                        '模型训练与评估', '100 轮重训 · 39 类 F1 全景 · 5 弱类归因')
    # P10
    page_10_training(prs, 10, TOTAL)
    # P11
    page_11_f1_chart(prs, 11, TOTAL)
    # P12
    page_chapter_divider(prs, 12, TOTAL, '04', 'CHAPTER 04 · EDGE',
                        '板端落地与下一步', '.pt → .rknn · 2×2 实验 · 三件待办')
    # P13
    page_13_2x2(prs, 13, TOTAL)
    # P14
    page_14_next(prs, 14, TOTAL)
    # P15
    page_15_appendix(prs, 15, TOTAL)

    prs.save(OUT)
    print('已生成 %s  (%d 页)' % (OUT, len(prs.slides)))


if __name__ == '__main__':
    main()
