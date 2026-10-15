# -*- coding: utf-8 -*-
"""生成 2026-09-01 本周进展汇报 PPT（白底 · 宋体 · 四号 14pt）。"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

FONT = "宋体"
DARK = (0x1F, 0x3A, 0x5F)     # 标题蓝
BODY = (0x33, 0x33, 0x33)     # 正文深灰
ACC  = (0x2E, 0x5E, 0x8C)     # 强调条蓝
HL   = (0xB0, 0x30, 0x30)     # 高亮红
GRN  = (0x2E, 0x6E, 0x3A)     # 绿

def set_font(run, size=14, bold=False, color=BODY):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(*color)
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        ea = rPr.makeelement(qn('a:ea'), {})
        rPr.append(ea)
    ea.set('typeface', FONT)

def add_para(tf, text, size=14, bold=False, color=BODY, align=PP_ALIGN.LEFT,
             space_after=4, space_before=0, level=0):
    p = tf.paragraphs[0] if (len(tf.paragraphs) == 1 and not tf.paragraphs[0].runs) \
        else tf.add_paragraph()
    p.alignment = align
    p.space_after = Pt(space_after)
    p.space_before = Pt(space_before)
    p.level = level
    r = p.add_run()
    r.text = text
    set_font(r, size, bold, color)
    return p

def add_text(slide, left, top, width, height):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    return tf

def add_bar(slide, left, top, width, height, color=ACC):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top),
                                 Inches(width), Inches(height))
    shp.fill.solid()
    shp.fill.fore_color.rgb = RGBColor(*color)
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp

def add_title(slide, text, size=22):
    add_bar(slide, 0.55, 0.42, 0.16, 0.55, DARK)
    tf = add_text(slide, 0.9, 0.38, 11.5, 0.7)
    add_para(tf, text, size=size, bold=True, color=DARK)
    add_bar(slide, 0.55, 1.18, 12.23, 0.014, (0xD0, 0xD0, 0xD0))

def add_table(slide, rows, cols, left, top, width, height, col_widths=None):
    shp = slide.shapes.add_table(rows, cols, Inches(left), Inches(top),
                                 Inches(width), Inches(height))
    tbl = shp.table
    if col_widths:
        for i, w in enumerate(col_widths):
            tbl.columns[i].width = Inches(w)
    return tbl

def set_cell(cell, text, size=14, bold=False, color=BODY, fill=None, align=PP_ALIGN.LEFT):
    cell.margin_left = Inches(0.08)
    cell.margin_right = Inches(0.08)
    cell.margin_top = Inches(0.05)
    cell.margin_bottom = Inches(0.05)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    if fill:
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(*fill)
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    set_font(r, size, bold, color)

def fill_table(tbl, data, header_fill=(0x1F, 0x3A, 0x5F), header_color=(0xFF, 0xFF, 0xFF),
               size=14, first_col_bold=True):
    for ri, row in enumerate(data):
        for ci, txt in enumerate(row):
            if ri == 0:
                set_cell(tbl.cell(ri, ci), txt, size=size, bold=True,
                         color=header_color, fill=header_fill)
            else:
                fill = (0xEF, 0xF3, 0xF8) if ri % 2 == 0 else None
                bold = first_col_bold and ci == 0
                set_cell(tbl.cell(ri, ci), txt, size=size, bold=bold, fill=fill)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank = prs.slide_layouts[6]

def new_slide():
    return prs.slides.add_slide(blank)

# ============ S1 标题 ============
s = new_slide()
add_bar(s, 0, 0, 13.333, 0.22, DARK)
tf = add_text(s, 1.0, 2.35, 11.3, 1.3)
add_para(tf, "ArchCheck · 建筑合规自动审查平台", size=40, bold=True, color=DARK,
         align=PP_ALIGN.CENTER)
tf = add_text(s, 1.0, 3.6, 11.3, 0.6)
add_para(tf, "本周进展汇报 · 2026-09-01", size=22, color=BODY, align=PP_ALIGN.CENTER)
tf = add_text(s, 1.0, 6.3, 11.3, 0.5)
add_para(tf, "汇报人 黄韵霖 · NTU Pre", size=16, color=(0x88, 0x88, 0x88),
         align=PP_ALIGN.CENTER)

# ============ S2 回应上周老师 ============
s = new_slide()
add_title(s, "回应上周老师的方向")
data = [
    ["上周的方向", "本周回答"],
    ["验证 IFC 是否含 B-Rep（影响台阶③ CSG 与否）",
     "验证完成：主流模型自带 B-Rep，为精确几何铺路，无需 CSG 内核"],
    ["知识库从「搜到条文」走向「实际判定」",
     "判定链路跑通，提取器升级让规则判得动（6/100 → 98/100）"],
    ["混合检索口径", "关键词优先、语义兜底"],
]
tbl = add_table(s, 4, 2, 0.9, 1.6, 11.5, 4.4, col_widths=[5.2, 6.3])
fill_table(tbl, data, size=15)

# ============ S3 主线一：模型读取与信息处理 ============
s = new_slide()
add_title(s, "主线一 · 模型读取与信息处理 —— 从「读得到」到「算得出」")
# 卡 A
add_bar(s, 0.9, 1.55, 0.12, 0.5, ACC)
tf = add_text(s, 1.15, 1.5, 5.6, 4.6)
add_para(tf, "门-房间关联  6/100 → 98/100", size=19, bold=True, color=DARK, space_after=10)
add_para(tf, "方法", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "bbox 矩形占用面（无实体几何的房间也有足迹）", size=14, space_after=2)
add_para(tf, "放置矩阵含旋转（楼层框架转 90°）", size=14, space_after=2)
add_para(tf, "边界优先（真实边界数据优先，几何只补缺）", size=14, space_after=10)
add_para(tf, "效果", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "疏散距离 6→98 房可判定；门宽/出口数 98/100", size=14, space_after=2)
add_para(tf, "新查出 2 条真违规（3.04 / 6.04 无疏散门）", size=14, space_after=2)
# 卡 B
add_bar(s, 6.85, 1.55, 0.12, 0.5, ACC)
tf = add_text(s, 7.1, 1.5, 5.6, 4.6)
add_para(tf, "消火栓间距字段激活（MEP-009）", size=19, bold=True, color=DARK, space_after=10)
add_para(tf, "方法", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "提取器新增消防管几何质心 → 最近邻间距", size=14, space_after=10)
add_para(tf, "意义", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "读取从「读属性」升级到「读几何、算距离」", size=14, space_after=10)
add_para(tf, "效果", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "office_3f 6 根消防管，间距 13.0m ≤ 30m", size=14, space_after=2)

# ============ S4 主线二：文献对应（规则扩量） ============
s = new_slide()
add_title(s, "主线二 · 文献对应：规则扩量 21 → 47 条/地区")
tf = add_text(s, 0.9, 1.5, 11.5, 0.7)
add_para(tf, "为什么能对上文献：规则库已覆盖 GB 55037 / GB 50016 / GB 50974 / FC23 / PUB / SS 的具体阈值",
         size=15, bold=True, color=DARK)
tf = add_text(s, 0.9, 2.2, 11.5, 3.2)
add_para(tf, "规则扩量的原理 —— 每条规则「判得动、判得准、可追溯」", size=15, bold=True, color=ACC, space_after=8)
add_para(tf, "① 选取真实字段 —— 规则只对准提取器真实产出的字段，杜绝「读不到」的死规则", size=14, space_after=6)
add_para(tf, "② 条件限定范围 —— condition_field 只判匹配的元素（如 pipe_type==fire），不误伤其它", size=14, space_after=6)
add_para(tf, "③ 规范的出处 —— code_ref 对应原文条款，阈值按标准原文核实（净宽 0.9m / 间距 30m）", size=14, space_after=10)
add_para(tf, "扩量后的作用", size=15, bold=True, color=ACC, space_after=8)
add_para(tf, "提问 → 语义检索命中条文 → 条文对应规则 → 规则在模型上真判定", size=14, space_after=6)
add_para(tf, "文献从「搜到条文」落地为「判定依据」，21 → 47 条/地区可判定", size=14, space_after=6)

# ============ S5 主线三：B-Rep 调研 ============
s = new_slide()
add_title(s, "主线三 · B-Rep 调研：主流模型自带，为精确几何铺路")
tf = add_text(s, 0.9, 1.5, 11.5, 0.6)
add_para(tf, "调研情况 · 4 样例 IfcFacetedBrep 计数", size=15, bold=True, color=ACC)
data = [
    ["样例", "Schependomlaan", "office_3f", "FZK_Haus", "Duplex_MEP"],
    ["B-Rep 数", "4202", "362（整模）", "140", "0"],
]
tbl = add_table(s, 2, 5, 0.9, 2.0, 11.5, 0.9, col_widths=[2.0, 2.7, 2.3, 2.2, 2.3])
fill_table(tbl, data, size=14)
# 左栏：原本计划 CSG + IFC 中 CSG 与 B-Rep 的区别
add_bar(s, 0.9, 3.15, 0.12, 0.55, ACC)
tf = add_text(s, 1.15, 3.12, 5.5, 3.1)
add_para(tf, "原本计划：CSG + 布尔运算", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "参数化构造、保留建模历史，但布尔裁剪需自研实体内核，投入大", size=14, space_after=10)
add_para(tf, "IFC 中 CSG 与 B-Rep 的区别（二者都常见）", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "CSG：参数化构造，保留建模历史（布尔树）", size=14, space_after=2)
add_para(tf, "B-Rep：显式的外壳集合（表面拼出实体）", size=14, space_after=2)
# 右栏：我们的做法
add_bar(s, 6.85, 3.15, 0.12, 0.55, ACC)
tf = add_text(s, 7.1, 3.12, 5.6, 3.1)
add_para(tf, "我们的做法", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "B-Rep 主流自带 → 直接利用，无需自研内核", size=14, space_after=2)
add_para(tf, "散度定理（有符号四面体）→ 精确体积", size=14, space_after=2)
add_para(tf, "柱 / 梁 / 板已验证", size=14, space_after=10)
add_para(tf, "布尔裁剪结果 → tessellation + 精度标注", size=14, space_after=2)
add_bar(s, 0.9, 6.35, 0.12, 0.55, DARK)
tf = add_text(s, 1.15, 6.38, 11.0, 0.7)
add_para(tf, "台阶③ = B-Rep / 网格混合 + 精度标注，不引入 CSG 实体内核", size=17, bold=True, color=DARK)

# ============ S6 4 样例横向验证 ============
s = new_slide()
add_title(s, "同一引擎 · 四种数据 → 自适应判定")
data = [
    ["样例", "数据覆盖", "演示规则判定结果"],
    ["office_3f", "房 + 机电 + 电气 + 消防管", "5 条规则全部判定 · 应急照明违规 3 处"],
    ["Schependomlaan", "住宅（100 房 + 门 + 结构）", "疏散 100 房全判定 · 门宽违规 11 处"],
    ["Duplex", "纯机电（427 管 + 电气）", "机电规则判定（管径 / 坡度 / 间距）"],
    ["FZK", "建筑 + 结构", "建筑规则判定（疏散 / 结构构件）"],
]
tbl = add_table(s, 5, 3, 0.9, 1.7, 11.5, 4.2, col_widths=[2.4, 4.2, 4.9])
fill_table(tbl, data, size=14)

# ============ S7 升级效果 ============
s = new_slide()
add_title(s, "本周提取器升级的效果")
data = [
    ["场景", "8-27（上周）", "现在"],
    ["疏散门净宽", "数据缺失", "违规 11 处"],
    ["疏散距离", "只能判 6 房", "已判定 100 房"],
    ["出口数量", "误报 2 处", "通过（纠正假阳性）"],
]
tbl = add_table(s, 4, 3, 0.9, 1.7, 11.5, 3.2, col_widths=[3.0, 4.0, 4.5])
fill_table(tbl, data, size=15)
add_bar(s, 0.9, 5.3, 0.12, 0.55, DARK)
tf = add_text(s, 1.15, 5.33, 11.0, 0.7)
add_para(tf, "从「判不了」到「判得动」", size=18, bold=True, color=DARK)

# ============ S8 下一步 ============
s = new_slide()
add_title(s, "下一步")
tf = add_text(s, 0.9, 1.8, 11.5, 4.0)
add_para(tf, "· 台阶③ 精确几何：B-Rep / 网格混合 + 精度标注（基础已铺好）", size=16, space_after=14)
add_para(tf, "· 新提取字段：IfcZone（防火分区）· IfcRamp（坡道）· 管道拓扑", size=16, space_after=14)
add_para(tf, "· IDS 驱动提取（提取器按规范要求取数）", size=16, space_after=14)
tf = add_text(s, 0.9, 6.4, 11.5, 0.6)
add_para(tf, "请老师指导", size=20, bold=True, color=DARK, align=PP_ALIGN.CENTER)

out = "presentation/2026-08-26/本周进展汇报_2026-09-01_v2.pptx"
prs.save(out)
print("saved:", out)
print("slides:", len(prs.slides._sldIdLst))
