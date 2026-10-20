"""
从 .pptx 读取每页文字,生成一张多页文字预览拼图(供 IDE 预览面板查看).
不依赖 WPS / LibreOffice,纯 python-pptx + PIL.
"""
from pptx import Presentation
from pptx.util import Emu
from PIL import Image, ImageDraw, ImageFont
import os, re

PPTX = r"D:\workbuddy\缺陷检测项目\output\缺陷检测项目周报\缺陷检测项目周报.pptx"
OUT  = r"D:\workbuddy\缺陷检测项目\output\缺陷检测项目周报\预览内容长图.png"

# 找字体
font_candidates = [
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 bold
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
    r"C:\Windows\Fonts\simsun.ttc",   # 宋体
]
FONT_PATH = None
for f in font_candidates:
    if os.path.exists(f):
        FONT_PATH = f; break

prs = Presentation(PPTX)
sw_pt = prs.slide_width / 12700.0   # 1pt = 12700 EMU
sh_pt = prs.slide_height / 12700.0
ratio_w, ratio_h = 960, int(960 * sh_pt / sw_pt)

print(f"PPT: {len(prs.slides)} 页, 单页预览 {ratio_w}x{ratio_h}px")

def collect_text(slide):
    """提取一页里所有文字+粗略位置(按 from-top 排序)."""
    items = []
    for shp in slide.shapes:
        if shp.has_text_frame:
            for p in shp.text_frame.paragraphs:
                for r in p.runs:
                    txt = r.text.strip()
                    if not txt: continue
                    bold = bool(r.font.bold)
                    try:
                        size = r.font.size.pt if r.font.size else 18
                    except Exception:
                        size = 18
                    color = "000000"
                    try:
                        if r.font.color and r.font.color.rgb:
                            color = str(r.font.color.rgb)
                    except Exception:
                        pass
                    top = Emu(shp.top or 0).pt
                    left = Emu(shp.left or 0).pt
                    items.append((top, left, size, bold, txt, color))
    items.sort(key=lambda x: (x[0], x[1]))
    return items

def find_box_fill(slide):
    """找到第一个大面积色块作为背景(优先非黑)."""
    best = None
    for shp in slide.shapes:
        if shp.has_text_frame: continue
        try:
            w = Emu(shp.width or 0).pt
            h = Emu(shp.height or 0).pt
        except Exception:
            continue
        if w < 400 or h < 200: continue
        try:
            if shp.fill.type == 1:  # solid
                col = str(shp.fill.fore_color.rgb)
            else:
                col = None
        except Exception:
            col = None
        if col and col != "000000":
            return col
    return None

# 字体大小自适应: 不同字号用不同 pts
def fnt(size, bold=False):
    if FONT_PATH and "msyh" in FONT_PATH and bold:
        return ImageFont.truetype(FONT_PATH, size, index=0)
    if FONT_PATH:
        return ImageFont.truetype(FONT_PATH, size)
    return ImageFont.load_default()

# 逐页渲染, 拼成 7x2 网格(14 页刚好)
cols, rows = 4, 4   # 14 页用 4x4(留 2 空),居中
margin = 24
total_w = cols * ratio_w + (cols+1) * margin
total_h = rows * ratio_h + (rows+1) * margin + 60   # +60 顶部留标题
canvas = Image.new("RGB", (total_w, total_h), "#F5F7FA")
draw = ImageDraw.Draw(canvas)
title_fnt = ImageFont.truetype(FONT_PATH, 32) if FONT_PATH else ImageFont.load_default()
draw.text((margin, 12), f"缺陷检测项目周报   |   14 页预览拼图   |   内容预览(非像素级)", fill="#1E3A5F", font=title_fnt)

for idx, slide in enumerate(prs.slides):
    r, c = idx // cols, idx % cols
    x0 = margin + c * (ratio_w + margin)
    y0 = margin + 60 + r * (ratio_h + margin)
    # 单页底色
    bg = find_box_fill(slide) or "#FFFFFF"
    page = Image.new("RGB", (ratio_w, ratio_h), bg)
    pd = ImageDraw.Draw(page)
    # 页边框
    pd.rectangle([0,0,ratio_w-1,ratio_h-1], outline="#9CB3C9", width=2)
    # 页码
    page_no_fnt = ImageFont.truetype(FONT_PATH, 18) if FONT_PATH else ImageFont.load_default()
    pd.text((10, 8), f"P{idx+1:02d}", fill="#FFFFFF", font=page_no_fnt)
    # 内容
    for top, left_pt, size, bold, text, color in collect_text(slide):
        # 缩放: 原 SLIDE 720pt -> 960px, 每 pt = 960/720 px = 1.333px
        scale = 960/720
        sz = max(10, int(size * scale))
        x = int(left_pt * scale)
        y = int(top * scale)
        # 颜色提亮: 深色背景用白字
        fcolor = "#" + color.upper() if color else "#000000"
        if bg != "#FFFFFF":
            fcolor = "#FFFFFF"
        # 找近似字号
        try:
            f = fnt(sz, bold)
        except Exception:
            f = page_no_fnt
        # 文本超框时换行
        max_chars = max(10, int((ratio_w - x - 10) / max(sz*0.6, 6)))
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        pd.text((x, y), text, fill=fcolor, font=f)
    canvas.paste(page, (x0, y0))

canvas.save(OUT, optimize=True)
print(f"OK: {OUT}, {os.path.getsize(OUT)/1024:.1f} KB, {canvas.size}")