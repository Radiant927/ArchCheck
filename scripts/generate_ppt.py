"""
ArchCheck 答辩 PPT 生成器 v3 — 10页 · 10分钟 · 含3分钟平台实操演示
"""
import os
from datetime import datetime
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Cm
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

# ═══════════════════════════════════
# AICHER 色板
# ═══════════════════════════════════
C = {
    "blue":   RGBColor(0x5B, 0xA3, 0xD9),
    "orange": RGBColor(0xF0, 0x92, 0x35),
    "red":    RGBColor(0xD3, 0x2F, 0x2F),
    "green":  RGBColor(0x7C, 0xB3, 0x42),
    "silver": RGBColor(0x9B, 0xA3, 0xAB),
    "text":   RGBColor(0x1F, 0x24, 0x29),
    "muted":  RGBColor(0x6B, 0x74, 0x80),
    "border": RGBColor(0xED, 0xF0, 0xF3),
    "bg":     RGBColor(0xFA, 0xFB, 0xFC),
    "white":  RGBColor(0xFF, 0xFF, 0xFF),
    "dark":   RGBColor(0x1A, 0x1E, 0x23),
    "card":   RGBColor(0x25, 0x2A, 0x30),
}
FONT = "Microsoft YaHei"
FONT_EN = "Arial"

W = Inches(13.333)
H = Inches(7.5)
M = Inches(0.7)

# ═══════════════════════════════════
# 基础组件
# ═══════════════════════════════════

def bg(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color

def band(slide, top=0):
    parts = [(0.40, C["blue"]), (0.20, C["orange"]), (0.20, C["red"]), (0.20, C["green"])]
    x = 0
    for r, clr in parts:
        bw = int(W * r)
        s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, top, bw, Pt(6))
        s.fill.solid(); s.fill.fore_color.rgb = clr; s.line.fill.background()
        x += bw

def label(slide, text, left=M, top=Inches(0.35)):
    tb = slide.shapes.add_textbox(left, top, Inches(5), Pt(16))
    p = tb.text_frame.paragraphs[0]
    p.text = text; p.font.size = Pt(8); p.font.color.rgb = C["silver"]
    p.font.bold = True; p.font.name = FONT

def big_title(slide, text, sub=None, dark=False):
    tb = slide.shapes.add_textbox(M, Inches(0.5), Inches(11.5), Inches(1.3))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text; p.font.size = Pt(32); p.font.bold = True
    p.font.color.rgb = C["white"] if dark else C["text"]; p.font.name = FONT
    if sub:
        p2 = tf.add_paragraph()
        p2.text = sub; p2.font.size = Pt(13); p2.font.color.rgb = C["silver"] if dark else C["muted"]
        p2.font.name = FONT; p2.space_before = Pt(4)

def divider(slide, left=M, top=Inches(1.65), width=Inches(2.8)):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, Pt(2))
    s.fill.solid(); s.fill.fore_color.rgb = C["border"]; s.line.fill.background()

def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text

def rect(slide, x, y, w, h, fill=C["white"], line=C["border"], lw=Pt(0.5), radius=False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    s = slide.shapes.add_shape(shape_type, x, y, w, h)
    s.fill.solid(); s.fill.fore_color.rgb = fill
    s.line.color.rgb = line; s.line.width = lw
    return s

def textbox(slide, x, y, w, h, txt, size=Pt(10), color=None, bold=False, align=PP_ALIGN.LEFT, font=None, spacing=None):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = txt; p.font.size = size; p.font.color.rgb = color or C["text"]
    p.font.bold = bold; p.font.name = font or FONT; p.alignment = align
    if spacing: p.line_spacing = spacing
    return tf

def multiline(slide, x, y, w, h, lines, size=Pt(10), color=None, lead=Pt(18)):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line; p.font.size = size; p.font.color.rgb = color or C["muted"]
        p.font.name = FONT; p.space_before = Pt(4); p.line_spacing = lead
    return tf

def stat_card(slide, value, label_text, x, y, w=Inches(2.3), h=Inches(1.15), accent=None):
    r = rect(slide, x, y, w, h, fill=C["white"], radius=True)
    textbox(slide, x + Inches(0.15), y + Inches(0.08), w - Inches(0.3), Inches(0.55),
            str(value), size=Pt(30), color=accent or C["text"], bold=True, align=PP_ALIGN.CENTER, font=FONT_EN)
    textbox(slide, x + Inches(0.15), y + Inches(0.68), w - Inches(0.3), Inches(0.3),
            label_text, size=Pt(8), color=C["silver"], bold=True, align=PP_ALIGN.CENTER)

def accent_card(slide, title_text, body_lines, x, y, w=Inches(3.8), h=Inches(2.1), accent=C["blue"]):
    r = rect(slide, x, y, w, h)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, Pt(4), h)
    bar.fill.solid(); bar.fill.fore_color.rgb = accent; bar.line.fill.background()
    textbox(slide, x + Inches(0.18), y + Inches(0.1), w - Inches(0.3), Inches(0.32),
            title_text, size=Pt(13), color=accent, bold=True)
    if body_lines:
        multiline(slide, x + Inches(0.18), y + Inches(0.5), w - Inches(0.3), h - Inches(0.6),
                  body_lines, size=Pt(10), lead=Pt(17))

def numbered_circle(slide, num, x, y, d=Inches(0.5), color=C["blue"]):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    c.fill.solid(); c.fill.fore_color.rgb = color; c.line.fill.background()
    p = c.text_frame.paragraphs[0]
    p.text = str(num); p.font.size = Pt(14); p.font.bold = True
    p.font.color.rgb = C["white"]; p.font.name = FONT_EN; p.alignment = PP_ALIGN.CENTER

def screenshot_placeholder(slide, x, y, w, h, caption=""):
    """Placeholder frame for actual platform screenshots."""
    r = rect(slide, x, y, w, h, fill=RGBColor(0xF0, 0xF2, 0xF5), line=C["border"], lw=Pt(1.5))
    # Dashed inner border effect via lighter fill
    textbox(slide, x + Inches(0.1), y + h//2 - Inches(0.2), w - Inches(0.2), Inches(0.4),
            caption, size=Pt(9), color=C["silver"], align=PP_ALIGN.CENTER)
    return r

# ═══════════════════════════════════
# SLIDE 1 — 封面
# ═══════════════════════════════════
def s01_cover(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["dark"])
    # 网格点阵
    for x in range(0, 21):
        for y in range(0, 12):
            d = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x*0.64), Inches(y*0.64), Pt(1.2), Pt(1.2))
            d.fill.solid(); d.fill.fore_color.rgb = RGBColor(0x2A,0x2F,0x36); d.line.fill.background()
    band(s)

    textbox(s, Inches(1.6), Inches(1.6), Inches(10), Inches(1.6),
            "ArchCheck", size=Pt(84), color=C["white"], bold=True, font=FONT_EN)
    textbox(s, Inches(1.6), Inches(1.6), Inches(5), Inches(1.6),
            "Arch", size=Pt(84), color=C["blue"], bold=True, font=FONT_EN)
    textbox(s, Inches(1.6), Inches(3.5), Inches(10), Inches(0.6),
            "基于多智能体的建筑图纸合规性自动审查平台", size=Pt(20), color=C["silver"])
    textbox(s, Inches(1.6), Inches(4.5), Inches(10), Inches(0.5),
            "\"让建筑合规审查更快、更准、更智能\"", size=Pt(14), color=C["muted"], font=FONT)
    textbox(s, Inches(1.6), Inches(5.7), Inches(10), Inches(0.5),
            "建筑方向  ·  电气方向  ·  软件方向", size=Pt(13), color=C["silver"])
    textbox(s, Inches(1.6), Inches(6.2), Inches(10), Inches(0.4),
            datetime.now().strftime("%Y年%m月"), size=Pt(10), color=C["muted"])
    notes(s, "【封面 · 20秒】全体成员亮相，介绍项目名称和团队构成。")

# ═══════════════════════════════════
# SLIDE 2 — 问题：事故警示 + 痛点量化
# ═══════════════════════════════════
def s02_problem(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 问题分析 / PROBLEM")
    big_title(s, "人工审查为什么跟不上时代？")
    divider(s)

    # 左侧：事故警示卡片
    accidents = [
        ("长沙自建房倒塌 · 2022", "53人遇难 — 违规加层无审批，全过程审查缺失", C["red"]),
        ("泉州酒店倒塌 · 2020", "29人遇难 — 违规改建承重结构，审查形同虚设", C["red"]),
        ("南昌\"2·25\"火灾 · 2017", "10人遇难 — 疏散通道堵塞未在审查阶段被发现", C["orange"]),
    ]
    for i, (title, desc, clr) in enumerate(accidents):
        y = Inches(2.1) + Inches(1.15) * i
        r = rect(s, M, y, Inches(5.8), Inches(0.95), fill=C["white"], line=clr, lw=Pt(1.5))
        bar = slide_shapes_list = [s.shapes.add_shape(MSO_SHAPE.RECTANGLE, M, y, Pt(4), Inches(0.95))]
        bar[0].fill.solid(); bar[0].fill.fore_color.rgb = clr; bar[0].line.fill.background()
        textbox(s, M + Inches(0.2), y + Inches(0.12), Inches(5.3), Inches(0.3),
                title, size=Pt(12), color=clr, bold=True)
        textbox(s, M + Inches(0.2), y + Inches(0.52), Inches(5.3), Inches(0.3),
                desc, size=Pt(10), color=C["muted"])

    # 右侧：四个量化痛点
    pains = [
        ("慢", "一栋 5 万 m² 综合体 ≈ 40 个工作日\n涉及 12 本规范、300+ 检查项", C["blue"]),
        ("漏", "人工审查跨专业交叉项\n遗漏率高达 41%", C["red"]),
        ("贵", "资深注册工程师年薪 30-50 万\n审查费占设计费 15-20%", C["orange"]),
        ("不一致", "同一图纸给 3 位审查员\n违规检出差异可达 35%", C["silver"]),
    ]
    for i, (t, desc, clr) in enumerate(pains):
        y = Inches(2.1) + Inches(1.18) * i
        numbered_circle(s, i+1, Inches(7.3), y + Inches(0.1), Inches(0.38), clr)
        textbox(s, Inches(7.85), y + Inches(0.08), Inches(2.0), Inches(0.3),
                t, size=Pt(14), color=clr, bold=True)
        multiline(s, Inches(7.85), y + Inches(0.38), Inches(4.8), Inches(0.55),
                  desc.split("\n"), size=Pt(9), color=C["muted"], lead=Pt(14))

    # 底部金句
    rect(s, M, Inches(5.95), Inches(11.8), Inches(0.8), fill=C["white"], line=C["red"], lw=Pt(1.5))
    textbox(s, M + Inches(0.3), Inches(6.05), Inches(11.2), Inches(0.55),
            "这些事故背后有一个共同点：该被发现的违规，在审查阶段被遗漏了。",
            size=Pt(18), color=C["red"], bold=True, align=PP_ALIGN.CENTER)

    notes(s, "【问题 · 1.5分钟】三起真实事故建立紧迫感 → 四个量化痛点说明这不是个别现象 → 金句收尾引出方案。")

# ═══════════════════════════════════
# SLIDE 3 — 方案：多 Agent 协同审查
# ═══════════════════════════════════
def s03_solution(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 解决方案 / APPROACH")
    big_title(s, "我们的方案：多智能体协同审查")
    divider(s)

    # 副标题解释"为什么必须是多Agent"
    textbox(s, M, Inches(1.85), Inches(11.5), Inches(0.4),
            "建筑规范和电气规范由不同专业的 Agent 独立执行，避免单模型知识过载和跨专业混淆——这正是 Multi-Agent 优于单一 AI 的关键原因。",
            size=Pt(11), color=C["muted"])

    # 对比表
    headers = ["", "传统方式", "ArchCheck"]
    rows = [
        ["审查主体", "一人看所有规范", "Civil + EEE 双 Agent 并行执行"],
        ["专业协作", "各专业分开审核、互不通信", "Coordinator 实时合并 + 冲突自动检测"],
        ["冲突发现", "依赖个人经验，极易遗漏", "基于房间位置索引自动交叉比对"],
        ["输出形式", "纸质报告，信息静态", "标注平面图 + 修正方案 + HTML 一键导出"],
        ["审查速度", "数天 ～ 数周", "初次筛选 < 1 分钟"],
    ]

    cw = [Inches(2.0), Inches(4.3), Inches(5.0)]
    tl, tt, rh = M, Inches(2.4), Inches(0.58)

    # 表头
    x = tl
    for hdr, w in zip(headers, cw):
        h = rect(s, x, tt, w, Inches(0.48), fill=C["text"], line=C["text"])
        p = h.text_frame.paragraphs[0]
        p.text = hdr; p.font.size = Pt(11); p.font.bold = True
        p.font.color.rgb = C["white"]; p.font.name = FONT; p.alignment = PP_ALIGN.CENTER
        x += w

    for i, row in enumerate(rows):
        y = tt + Inches(0.48) + rh * i
        bg_c = C["white"] if i % 2 == 0 else RGBColor(0xF5, 0xF7, 0xF9)
        x = tl
        for j, (txt, w) in enumerate(zip(row, cw)):
            cell = rect(s, x, y, w, rh, fill=bg_c)
            tf = cell.text_frame; tf.word_wrap = True
            tf.margin_left = Inches(0.12); tf.margin_top = Inches(0.08)
            p = tf.paragraphs[0]
            p.text = txt; p.font.size = Pt(10)
            if j == 0:
                p.font.color.rgb = C["text"]; p.font.bold = True
            elif j == 1:
                p.font.color.rgb = C["muted"]
            else:
                p.font.color.rgb = C["text"]; p.font.bold = True
            p.font.name = FONT
            x += w

    # 底部结论
    rect(s, M, Inches(5.65), Inches(11.8), Inches(1.05), fill=C["white"], line=C["border"], radius=True)
    textbox(s, M + Inches(0.2), Inches(5.75), Inches(11.4), Inches(0.35),
            "核心差异化优势", size=Pt(12), color=C["blue"], bold=True, align=PP_ALIGN.CENTER)
    textbox(s, M + Inches(0.2), Inches(6.1), Inches(11.4), Inches(0.45),
            "传统方式 = 串行 + 人工 + 单专业  →  ArchCheck = 并行 + 自动化 + 跨专业协同",
            size=Pt(14), color=C["text"], bold=True, align=PP_ALIGN.CENTER)

    notes(s, "【方案 · 1.5分钟】先解释为什么多Agent是这个问题的正确解法 → 5维对比 → 核心差异一句话收尾。")

# ═══════════════════════════════════
# SLIDE 4 — 为什么分专业？（承上启下）
# ═══════════════════════════════════
def s04_why_multi_agent(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 设计原理 / DESIGN RATIONALE")
    big_title(s, "为什么必须是 Civil + EEE 双 Agent？", "不是设计选择，是这个问题的本质决定的")
    divider(s)

    reasons = [
        ("现实世界就是分专业的",
         "注册建筑师审查 GB 50016 防火规范\n注册电气工程师审查 GB 51309 / 50054 电气规范\n两个专业各看各的、各签各的字\n人做不到\"一人精通所有规范\"，AI 同样不该假装能做到",
         C["blue"]),
        ("冲突检测的前提：先独立，再交叉",
         "只有两个 Agent 各自独立运行、互不干扰\nCoordinator 才能按位置做交叉索引\n才能发现\"同一位置、两个专业、同时违规\"\n单 Agent 输出只是问题列表，不是冲突检测",
         C["red"]),
        ("规范体系完全不同，混在一起会乱",
         "建筑规范判距离/面积/数量，电气规范判布尔/电流\n条件过滤逻辑不同（面积 > 50 vs 房间类型 in 列表）\n严重程度判定标准不同（距离超标 = 高 vs 插座 = 低）\n分开来，每条规则只对专业数据负责，逻辑清晰",
         C["orange"]),
        ("可扩展：不是\"加规则\"，是\"加 Agent\"",
         "结构 · 暖通 · 给排水 · 消防 —— 每加一个新专业\n= 新增一个独立 Agent 模块，不碰 Civil、不碰 EEE\nCoordinator 自动纳入冲突检测，即插即用",
         C["green"]),
    ]

    for i, (title, body, clr) in enumerate(reasons):
        col = i % 2  # 0 = left, 1 = right
        row = i // 2  # 0 or 1
        x = M if col == 0 else Inches(7.0)
        y = Inches(2.1) + Inches(2.3) * row

        r = rect(s, x, y, Inches(5.6), Inches(2.0), fill=C["white"], line=clr, lw=Pt(1.5), radius=True)
        # top accent
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, Inches(5.6), Pt(4))
        bar.fill.solid(); bar.fill.fore_color.rgb = clr; bar.line.fill.background()

        # number circle
        numbered_circle(s, i+1, x + Inches(0.18), y + Inches(0.2), Inches(0.42), clr)
        textbox(s, x + Inches(0.75), y + Inches(0.22), Inches(4.6), Inches(0.28),
                title, size=Pt(14), color=clr, bold=True)
        multiline(s, x + Inches(0.18), y + Inches(0.65), Inches(5.2), Inches(1.2),
                  body.split("\n"), size=Pt(9), lead=Pt(16))

    notes(s, "【为什么分专业 · 40秒】四宫格快速过：现实分专业 → 冲突前提 → 规范不同 → 可扩展。为接下来Civil和EEE的详细介绍做铺垫。")

# ═══════════════════════════════════
# SLIDE 5 — 建筑 Agent（以走廊为锚点）
# ═══════════════════════════════════
def s05_civil(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 建筑审查 / CIVIL AGENT")
    big_title(s, "建筑 Agent：把规范翻译成规则", "负责 GB 50016《建筑设计防火规范》自动化审查")
    divider(s)

    # 左侧：4条规则简洁卡片
    rules = [
        ("CIVIL-001", "疏散距离检查", "走廊长度 ≤ 30m", "高", "GB 50016 5.5.17"),
        ("CIVIL-002", "防火分区面积", "单区面积 ≤ 2500m²", "高", "GB 50016 5.3.1"),
        ("CIVIL-003", "安全出口数量", "≥ 2 个（面积 > 50m²）", "中", "GB 50016 5.5.8"),
        ("CIVIL-004", "疏散门宽度", "≥ 0.9m", "低", "GB 50016 5.5.18"),
    ]
    rl, rt = M, Inches(2.1)
    sev_color = {"高": C["red"], "中": C["orange"], "低": C["silver"]}

    for i, (rid, name, cond, sev, ref) in enumerate(rules):
        y = rt + Inches(0.58) * i
        r = rect(s, rl, y, Inches(5.8), Inches(0.48), fill=C["white"] if i%2==0 else RGBColor(0xF5,0xF7,0xF9))
        textbox(s, rl + Inches(0.12), y + Inches(0.1), Inches(1.2), Inches(0.28),
                rid, size=Pt(8), color=C["silver"], font=FONT_EN)
        textbox(s, rl + Inches(1.35), y + Inches(0.1), Inches(1.3), Inches(0.28),
                name, size=Pt(11), color=C["text"], bold=True)
        textbox(s, rl + Inches(2.7), y + Inches(0.1), Inches(1.6), Inches(0.28),
                cond, size=Pt(9), color=C["muted"])
        textbox(s, rl + Inches(4.3), y + Inches(0.1), Inches(0.5), Inches(0.28),
                sev, size=Pt(10), color=sev_color[sev], bold=True)
        textbox(s, rl + Inches(4.75), y + Inches(0.1), Inches(1.0), Inches(0.28),
                ref, size=Pt(7), color=C["silver"], font=FONT_EN)

    # 右侧：走廊案例
    rx, ry = Inches(7.2), Inches(2.1)
    rect(s, rx, ry, Inches(5.4), Inches(4.0), line=C["blue"], lw=Pt(2), radius=True)
    textbox(s, rx + Inches(0.2), ry + Inches(0.15), Inches(5.0), Inches(0.3),
            "以「走廊」为例", size=Pt(16), color=C["blue"], bold=True)

    # 走廊违规详述
    corridor_issues = [
        ("实测：疏散距离 42m", "规范要求 ≤ 30m → 违规！需增设避难走道", C["red"]),
        ("实测：防火分区 2800m²", "规范要求 ≤ 2500m² → 违规！需增加防火分隔", C["red"]),
        ("实测：办公室 85m² 仅 1 出口", "规范要求 ≥ 2 出口（面积 > 50m²）→ 违规！", C["orange"]),
    ]
    for i, (measured, verdict, clr) in enumerate(corridor_issues):
        yy = ry + Inches(0.65) + Inches(0.95) * i
        textbox(s, rx + Inches(0.2), yy, Inches(5.0), Inches(0.28),
                measured, size=Pt(10), color=C["text"], bold=True)
        textbox(s, rx + Inches(0.2), yy + Inches(0.35), Inches(5.0), Inches(0.28),
                verdict, size=Pt(10), color=clr)
        # mini divider
        if i < 2:
            ms = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, rx + Inches(0.2), yy + Inches(0.75),
                                    Inches(5.0), Pt(1))
            ms.fill.solid(); ms.fill.fore_color.rgb = C["border"]; ms.line.fill.background()

    # 底部统计
    stat_card(s, "4", "审查规则", M, Inches(5.6), Inches(1.6), Inches(1.0), C["blue"])
    stat_card(s, "3 项违规", "演示样例检出", Inches(2.7), Inches(5.6), Inches(1.6), Inches(1.0), C["red"])
    stat_card(s, "GB 50016", "核心规范依据", Inches(4.7), Inches(5.6), Inches(1.6), Inches(1.0), C["blue"])

    notes(s, "【Civil · 1分钟】4条规则概览 → 以走廊为例逐一说明违规 → 3项违规检出。强调：不是笼统的AI判断，是逐条对照规范的判定。")

# ═══════════════════════════════════
# SLIDE 5 — 电气 Agent（同一走廊 + 引出冲突）
# ═══════════════════════════════════
def s06_eee(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 电气审查 / EEE AGENT")
    big_title(s, "电气 Agent：同一位置，不同视角", "负责 GB 51309 / GB 50054 / GB 50055 自动化电气审查")
    divider(s)

    # 左侧：4条规则
    rules = [
        ("EEE-001", "应急照明检查", "走廊/楼梯间必须设置", "高", "GB 51309 3.2.1"),
        ("EEE-002", "配电箱防水距离", "距水源 ≥ 1.5m", "中", "GB 50054 4.2.3"),
        ("EEE-003", "回路负荷检查", "≤ 16A", "中", "GB 50054 3.4"),
        ("EEE-004", "插座间距检查", "≤ 6m", "低", "GB 50055 6.0.3"),
    ]
    rl, rt = M, Inches(2.1)
    sev_color = {"高": C["red"], "中": C["orange"], "低": C["silver"]}

    for i, (rid, name, cond, sev, ref) in enumerate(rules):
        y = rt + Inches(0.58) * i
        r = rect(s, rl, y, Inches(5.8), Inches(0.48), fill=C["white"] if i%2==0 else RGBColor(0xF5,0xF7,0xF9))
        textbox(s, rl + Inches(0.12), y + Inches(0.1), Inches(1.2), Inches(0.28),
                rid, size=Pt(8), color=C["silver"], font=FONT_EN)
        textbox(s, rl + Inches(1.35), y + Inches(0.1), Inches(1.5), Inches(0.28),
                name, size=Pt(11), color=C["text"], bold=True)
        textbox(s, rl + Inches(2.9), y + Inches(0.1), Inches(1.6), Inches(0.28),
                cond, size=Pt(9), color=C["muted"])
        textbox(s, rl + Inches(4.55), y + Inches(0.1), Inches(0.5), Inches(0.28),
                sev, size=Pt(10), color=sev_color[sev], bold=True)
        textbox(s, rl + Inches(4.95), y + Inches(0.1), Inches(0.8), Inches(0.28),
                ref, size=Pt(7), color=C["silver"], font=FONT_EN)

    # 右侧：电气违规 + 冲突
    rx, ry = Inches(7.2), Inches(2.1)
    rect(s, rx, ry, Inches(5.4), Inches(2.3), line=C["orange"], lw=Pt(2), radius=True)
    textbox(s, rx + Inches(0.2), ry + Inches(0.15), Inches(5.0), Inches(0.3),
            "电气 Agent 发现的问题", size=Pt(14), color=C["orange"], bold=True)

    eee_issues = [
        "走廊 — 缺应急照明（GB 51309 强制要求）",
        "配电间 — 距水源仅 0.8m（要求 ≥ 1.5m）",
        "配电间 — 回路负荷 20A 超限（要求 ≤ 16A）",
    ]
    for i, iss in enumerate(eee_issues):
        yy = ry + Inches(0.55) + Inches(0.5) * i
        textbox(s, rx + Inches(0.2), yy, Inches(5.0), Inches(0.35),
                f"●  {iss}", size=Pt(10), color=C["text"])

    # 冲突区域高亮
    conflict_y = ry + Inches(2.55)
    rect(s, rx, conflict_y, Inches(5.4), Inches(1.2), fill=RGBColor(0xFE,0xF2,0xF2), line=C["red"], lw=Pt(2), radius=True)
    textbox(s, rx + Inches(0.2), conflict_y + Inches(0.12), Inches(5.0), Inches(0.28),
            "⚡ 跨专业冲突：走廊", size=Pt(14), color=C["red"], bold=True)
    multiline(s, rx + Inches(0.2), conflict_y + Inches(0.5), Inches(5.0), Inches(0.6),
              ["建筑 Agent 发现：疏散距离 42m 超标（建筑问题）",
               "电气 Agent 发现：未配置应急照明（电气问题）",
               "→ 同一位置，两专业同时违规，需优先协调处理"],
              size=Pt(10), lead=Pt(16), color=C["red"])

    # 底部统计
    stat_card(s, "4", "审查规则", M, Inches(5.6), Inches(1.6), Inches(1.0), C["orange"])
    stat_card(s, "3 项违规", "演示样例检出", Inches(2.7), Inches(5.6), Inches(1.6), Inches(1.0), C["red"])
    stat_card(s, "1 处冲突", "走廊双重违规", Inches(4.7), Inches(5.6), Inches(1.8), Inches(1.0), C["red"])

    notes(s, "【EEE · 1分钟】4条电气规则 → 3项违规 → 引出关键：走廊同时被建筑和电气标记 = 跨专业冲突。这是人工审查最容易遗漏的场景，ArchCheck自动发现。")

# ═══════════════════════════════════
# SLIDE 6 — 实操：上传与数据配置
# ═══════════════════════════════════
def s07_demo_input(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 平台实操 1/4 / DEMO")
    big_title(s, "Step 1 — 上传图纸与数据配置", "一键加载示例方案，参数在线可调")
    divider(s)

    # 左侧：截图占位（主页面）
    screenshot_placeholder(s, M, Inches(2.0), Inches(6.5), Inches(4.5),
                           "[ 截图：平台主页面 — 上传区 + Quick Demo 按钮 + 数据编辑面板 ]")

    # 右侧：功能要点
    ry = Inches(2.2)
    features = [
        ("1", "Quick Demo 一键加载", "加载示例办公楼平面图\n5 个房间 + 2 个防火分区\n预设 6 项违规用于演示", C["blue"]),
        ("2", "在线数据编辑面板", "每房间 8 个可调参数\n面积 / 出口数 / 疏散距离\n电气负荷 / 插座间距……", C["orange"]),
        ("3", "数据驱动审查", "修改任意参数 → 重新审查\n审查结果实时响应数据变更\n同一架构适用不同项目", C["green"]),
    ]
    for i, (num, title, desc, clr) in enumerate(features):
        y = ry + Inches(1.35) * i
        numbered_circle(s, num, Inches(7.8), y, Inches(0.42), clr)
        textbox(s, Inches(8.4), y, Inches(4.2), Inches(0.28),
                title, size=Pt(13), color=clr, bold=True)
        textbox(s, Inches(8.4), y + Inches(0.35), Inches(4.2), Inches(0.8),
                desc, size=Pt(9), color=C["muted"], spacing=Pt(15))

    notes(s, "【实操1 · 40秒】展示主页面三个核心区域。强调数据可编辑、审查可复现。快速过渡到下一页。")

# ═══════════════════════════════════
# SLIDE 7 — 实操：审查过程
# ═══════════════════════════════════
def s08_demo_process(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 平台实操 2/4 / DEMO")
    big_title(s, "Step 2 — 多 Agent 协同审查过程", "不到 1 分钟完成三阶段审查流水线")
    divider(s)

    # 上部：3 阶段流程
    phases = [
        ("Phase 1\nSYS 解析", "识别房间类型\n映射防火分区\n提取审查参数", C["silver"], Inches(0.8)),
        ("Phase 2\n并行 Agent 审查", "Civil 4 步建筑检查\nEEE 4 步电气检查\n同时执行、互不阻塞", C["blue"], Inches(4.7)),
        ("Phase 3\nCoordinator 合并", "结果合并\n位置索引分组\n跨专业冲突检测", C["green"], Inches(8.6)),
    ]
    for title, desc, clr, x in phases:
        r = rect(s, x, Inches(2.15), Inches(3.5), Inches(1.7), line=clr, lw=Pt(1.5), radius=True)
        textbox(s, x + Inches(0.15), Inches(2.3), Inches(3.2), Inches(0.55),
                title, size=Pt(14), color=clr, bold=True, align=PP_ALIGN.CENTER, font=FONT_EN)
        # arrow between phases
        if x < Inches(8.0):
            pass  # arrow would go here, but keep it clean

    # 下部：Agent 日志模拟
    log_y = Inches(4.2)
    rect(s, M, log_y, Inches(11.8), Inches(2.6), fill=C["white"], line=C["border"], radius=True)
    textbox(s, M + Inches(0.2), log_y + Inches(0.1), Inches(5.0), Inches(0.25),
            "Agent 实时日志流（审查过程透明可追溯）", size=Pt(11), color=C["text"], bold=True)

    logs = [
        ("SYS", "Parsing floor plan, detecting rooms, corridors, exits...", C["silver"]),
        ("CIVIL", "Checking evacuation distance → GB 50016 5.5.17  [走廊 42m > 30m 违规]", C["blue"]),
        ("CIVIL", "Checking fire zone area → GB 50016 5.3.1  [防火分区1 2800m² > 2500m² 违规]", C["blue"]),
        ("EEE", "Checking emergency lighting → GB 51309 3.2.1  [走廊未配置应急照明]", C["orange"]),
        ("EEE", "Checking distribution box clearance → GB 50054 4.2.3  [配电间 0.8m < 1.5m]", C["orange"]),
        ("COORD", "Merging Civil + EEE results... 1 cross-domain conflict detected >> 走廊", C["green"]),
    ]
    for i, (agent, msg, clr) in enumerate(logs):
        yy = log_y + Inches(0.45) + Inches(0.32) * i
        textbox(s, M + Inches(0.3), yy, Inches(0.6), Inches(0.22),
                agent, size=Pt(8), color=clr, bold=True, font=FONT_EN)
        textbox(s, M + Inches(0.95), yy, Inches(10.5), Inches(0.22),
                msg, size=Pt(8), color=C["muted"], font=FONT_EN)

    notes(s, "【实操2 · 30秒】三阶段流程 + 日志流。强调：每步检查标注规范条款，黑箱变透明。快速过渡到结果页。")

# ═══════════════════════════════════
# SLIDE 8 — 实操：Before/After 检测与修正 ⭐ 重点页
# ═══════════════════════════════════
def s09_demo_before_after(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 平台实操 3/4 / DEMO")
    big_title(s, "Step 3 — Before / After：违规检测 + 修正建议", "不仅发现问题，还给出具体修正方案")
    divider(s)

    # 左侧：BEFORE
    lx, ly = M, Inches(2.1)
    rect(s, lx, ly, Inches(5.6), Inches(4.6), line=C["red"], lw=Pt(2), radius=True)
    # Red top accent bar
    rect(s, lx, ly, Inches(5.6), Pt(4), fill=C["red"], line=C["red"])
    textbox(s, lx + Inches(0.2), ly + Inches(0.15), Inches(5.2), Inches(0.3),
            "BEFORE — 审查发现 6 项违规", size=Pt(14), color=C["red"], bold=True)

    # Screenshot placeholder
    screenshot_placeholder(s, lx + Inches(0.15), ly + Inches(0.6), Inches(5.3), Inches(3.2),
                           "[ 截图：dem_review_annotated.png — 违规标注图 ]")

    # Key findings below screenshot
    findings = [
        "● 疏散距离 42m 超标（规范 ≤ 30m）",
        "● 防火分区 2800m² 超限（规范 ≤ 2500m²）",
        "● 走廊缺应急照明（GB 51309 强制要求）",
    ]
    multiline(s, lx + Inches(0.2), ly + Inches(3.95), Inches(5.2), Inches(0.6),
              findings, size=Pt(8), lead=Pt(15))

    # 右侧：AFTER
    rx, ry = Inches(7.1), Inches(2.1)
    rect(s, rx, ry, Inches(5.6), Inches(4.6), line=C["green"], lw=Pt(2), radius=True)
    rect(s, rx, ry, Inches(5.6), Pt(4), fill=C["green"], line=C["green"])
    textbox(s, rx + Inches(0.2), ry + Inches(0.15), Inches(5.2), Inches(0.3),
            "AFTER — 智能生成修正方案", size=Pt(14), color=C["green"], bold=True)

    screenshot_placeholder(s, rx + Inches(0.15), ry + Inches(0.6), Inches(5.3), Inches(3.2),
                           "[ 截图：correction_plan.png — 绿色修正建议图 ]")

    corrections = [
        "✓ 增设避难走道，缩短疏散路径至 ≤ 30m",
        "✓ 增加防火分隔墙，拆分防火分区",
        "✓ 安装应急照明灯具于走廊",
    ]
    multiline(s, rx + Inches(0.2), ry + Inches(3.95), Inches(5.2), Inches(0.6),
              corrections, size=Pt(8), lead=Pt(15), color=C["green"])

    # 底部 highlight
    rect(s, M, Inches(6.9), Inches(11.8), Inches(0.45), fill=C["red"], line=C["red"])
    textbox(s, M + Inches(0.2), Inches(6.93), Inches(11.4), Inches(0.38),
            "★  走廊同时被红色（建筑违规）和蓝色（电气违规）标记 → 跨专业冲突区，人工审查极易遗漏",
            size=Pt(14), color=C["white"], bold=True, align=PP_ALIGN.CENTER)

    notes(s, "【实操3 · 1分钟 — 全PPT最重要的一页。】左侧违规检测 → 右侧修正方案 → 底部冲突区高亮。强调：不是'有问题'三个字，而是'什么问题、在哪、怎么改'。走廊冲突区是人工审查最容易遗漏的场景。")

# ═══════════════════════════════════
# SLIDE 9 — 实操：详情与导出
# ═══════════════════════════════════
def s10_demo_export(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 平台实操 4/4 / DEMO")
    big_title(s, "Step 4 — 问题详情与成果导出", "分专业查看违规明细，一键导出可交付成果")
    divider(s)

    # 左侧：分页标签
    lx, ly = M, Inches(2.1)
    rect(s, lx, ly, Inches(6.0), Inches(4.5), fill=C["white"], line=C["border"], radius=True)
    textbox(s, lx + Inches(0.2), ly + Inches(0.12), Inches(5.5), Inches(0.28),
            "分专业问题详情（Civil / EEE / Conflicts 三标签页）", size=Pt(12), color=C["text"], bold=True)

    # 模拟 issue cards
    cards_data = [
        ("CIVIL-001  疏散距离检查", "疏散走廊过长（实际 42m > 规范 30m），需增设避难走道",
         "LOC: 走廊  |  REF: GB 50016 5.5.17", "高", C["red"], C["blue"]),
        ("EEE-001  应急照明检查", "走廊（类型: 走廊）未配置应急照明设备",
         "LOC: 走廊  |  REF: GB 51309 3.2.1", "高", C["red"], C["orange"]),
        ("CIVIL-002  防火分区面积检查", "防火分区面积超限（实际 2800m² > 规范 2500m²），需增加防火分隔",
         "LOC: 防火分区1  |  REF: GB 50016 5.3.1", "高", C["red"], C["blue"]),
        ("EEE-002  配电箱防水距离检查", "配电箱距水源仅 0.8m，规范要求 ≥ 1.5m",
         "LOC: 配电间  |  REF: GB 50054 4.2.3", "中", C["orange"], C["orange"]),
    ]
    for i, (title, desc, meta, sev, sev_c, border_c) in enumerate(cards_data):
        yy = ly + Inches(0.5) + Inches(0.85) * i
        r = rect(s, lx + Inches(0.15), yy, Inches(5.7), Inches(0.72),
                 fill=C["white"], line=border_c, lw=Pt(1.5))
        # Left border
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, lx + Inches(0.15), yy, Pt(3), Inches(0.72))
        bar.fill.solid(); bar.fill.fore_color.rgb = border_c; bar.line.fill.background()
        # Title + severity badge
        textbox(s, lx + Inches(0.3), yy + Inches(0.06), Inches(3.5), Inches(0.22),
                title, size=Pt(9), color=C["text"], bold=True)
        badge = rect(s, lx + Inches(4.0), yy + Inches(0.06), Inches(0.35), Inches(0.2),
                      fill=RGBColor(0xFE,0xF2,0xF2) if sev=="高" else RGBColor(0xFF,0xF7,0xED),
                      line=sev_c, lw=Pt(0.5))
        p = badge.text_frame.paragraphs[0]
        p.text = sev; p.font.size = Pt(7); p.font.bold = True
        p.font.color.rgb = sev_c; p.font.name = FONT; p.alignment = PP_ALIGN.CENTER
        # Description
        textbox(s, lx + Inches(0.3), yy + Inches(0.3), Inches(5.4), Inches(0.2),
                desc, size=Pt(8), color=C["muted"])
        # Meta
        textbox(s, lx + Inches(0.3), yy + Inches(0.52), Inches(5.4), Inches(0.16),
                meta, size=Pt(7), color=C["silver"], font=FONT_EN)

    # 右侧：导出选项
    rx, ry = Inches(7.5), Inches(2.1)
    rect(s, rx, ry, Inches(5.2), Inches(4.5), fill=C["white"], line=C["border"], radius=True)
    textbox(s, rx + Inches(0.2), ry + Inches(0.12), Inches(4.8), Inches(0.28),
            "一键导出审查成果", size=Pt(12), color=C["text"], bold=True)

    exports = [
        ("标注平面图", "红色编号标记违规位置\n直观定位问题区域", "PNG", C["red"]),
        ("修正方案图", "绿色虚线标注修正建议\n具体措施 + 位置指引", "PNG", C["green"]),
        ("HTML 审查报告", "嵌入式图片 + 分页问题列表\n可直接打印、归档、流转", "HTML", C["blue"]),
    ]
    for i, (name, desc, fmt, clr) in enumerate(exports):
        ey = ry + Inches(0.55) + Inches(1.2) * i
        r = rect(s, rx + Inches(0.2), ey, Inches(4.8), Inches(1.0), line=clr, lw=Pt(1), radius=True)
        textbox(s, rx + Inches(0.4), ey + Inches(0.08), Inches(3.5), Inches(0.22),
                name, size=Pt(11), color=clr, bold=True)
        textbox(s, rx + Inches(4.0), ey + Inches(0.08), Inches(0.8), Inches(0.2),
                fmt, size=Pt(8), color=C["silver"], font=FONT_EN, align=PP_ALIGN.RIGHT)
        textbox(s, rx + Inches(0.4), ey + Inches(0.38), Inches(4.4), Inches(0.5),
                desc, size=Pt(8), color=C["muted"], spacing=Pt(14))

    notes(s, "【实操4 · 50秒】左侧问题详情格式展示 → 右侧三种导出格式。强调：输出是可交付的正式审查成果，不是学术Demo。")

# ═══════════════════════════════════
# SLIDE 10 — 价值 + 路线图 + 致谢
# ═══════════════════════════════════
def s11_impact(p):
    s = p.slides.add_slide(p.slide_layouts[6]); bg(s, C["bg"]); band(s)
    label(s, "ARCHCHECK · 价值 & 展望 / IMPACT")
    big_title(s, "社会价值与未来规划")
    divider(s)

    # 五个价值卡片
    values = [
        ("效率提升", "审查时间\n数天 → 数分钟\n提速 10 倍+", C["blue"]),
        ("质量保障", "系统性覆盖规范\n减少人为遗漏\n跨专业冲突自动检出", C["red"]),
        ("成本降低", "降低对资深工程师\n的过度依赖\n减少人力投入", C["orange"]),
        ("标准统一", "统一执行判定标准\n消除审查主观差异\n结果可复现", C["green"]),
        ("可扩展", "新增 Agent 即插即用\n结构 · 暖通 · 消防\n同一架构无限扩展", C["blue"]),
    ]
    for i, (t, desc, clr) in enumerate(values):
        x = Inches(0.35) + Inches(2.5) * i
        y = Inches(2.15)
        numbered_circle(s, i+1, x + Inches(0.78), y, Inches(0.6), clr)
        textbox(s, x + Inches(0.1), y + Inches(0.72), Inches(2.3), Inches(0.32),
                t, size=Pt(14), color=clr, bold=True, align=PP_ALIGN.CENTER)
        textbox(s, x + Inches(0.1), y + Inches(1.1), Inches(2.3), Inches(1.0),
                desc, size=Pt(10), color=C["muted"], align=PP_ALIGN.CENTER, spacing=Pt(16))

    # 路线图
    rm_y = Inches(4.3)
    textbox(s, M, rm_y, Inches(11.5), Inches(0.3),
            "Development Roadmap", size=Pt(11), color=C["silver"], bold=True, font=FONT_EN)

    phases = [
        ("PHASE 1 · 已完成", "Civil + EEE 双 Agent\n8 条 JSON 规则引擎\n违规标注 + 修正方案\nHTML 报告一键导出", C["blue"]),
        ("PHASE 2 · 进行中", "OCR 图纸自动识别\n规范知识库扩充至 50+ 条\n智能修正建议优化\n审查流程性能提升", C["orange"]),
        ("PHASE 3 · 规划中", "BIM/IFC 格式接入\n结构 · 暖通 · 给排水 Agent\n云端 SaaS 多用户协作\nREST API 第三方集成", C["green"]),
    ]
    for i, (title, desc, clr) in enumerate(phases):
        x = Inches(0.6) + Inches(4.1) * i
        y = rm_y + Inches(0.45)
        rect(s, x, y, Inches(3.7), Inches(1.75), line=clr, lw=Pt(1.5), radius=True)
        textbox(s, x + Inches(0.15), y + Inches(0.12), Inches(3.4), Inches(0.28),
                title, size=Pt(11), color=clr, bold=True)
        multiline(s, x + Inches(0.15), y + Inches(0.5), Inches(3.4), Inches(1.1),
                  desc.split("\n"), size=Pt(10), lead=Pt(17))

    # 结束语
    rect(s, Inches(2), Inches(6.5), Inches(9.3), Inches(0.75), fill=C["white"], line=C["border"], radius=True)
    textbox(s, Inches(2.2), Inches(6.55), Inches(8.9), Inches(0.3),
            "多个 AI 专家协同工作 — 让建筑合规审查更快、更准、更智能",
            size=Pt(18), color=C["text"], bold=True, align=PP_ALIGN.CENTER)
    textbox(s, Inches(2.2), Inches(6.85), Inches(8.9), Inches(0.3),
            "感谢各位老师！欢迎提问与交流。", size=Pt(13), color=C["silver"], align=PP_ALIGN.CENTER)

    notes(s, "【总结 · 1分钟】五大价值点简要概括 → 三阶段路线图展示后续规划 → 致谢收尾。强调项目不是'答辩结束就完'，有成体系的后续规划。")

# ═══════════════════════════════════
# MAIN
# ═══════════════════════════════════
def main():
    p = Presentation()
    p.slide_width = W; p.slide_height = H

    slides = [
        ("封面",                               s01_cover),
        ("问题分析：事故警示 + 痛点量化",        s02_problem),
        ("解决方案：多Agent协同审查",            s03_solution),
        ("为什么分专业：设计原理",               s04_why_multi_agent),
        ("建筑Agent：规范翻译官",                s05_civil),
        ("电气Agent：同一位置不同视角 + 冲突",   s06_eee),
        ("实操 1/4：上传与数据配置",             s07_demo_input),
        ("实操 2/4：审查过程日志流",             s08_demo_process),
        ("实操 3/4：Before/After 检测与修正 ★", s09_demo_before_after),
        ("实操 4/4：详情与导出",                 s10_demo_export),
        ("价值 + 路线图 + 致谢",                 s11_impact),
    ]

    print("ArchCheck 答辩 PPT 生成中（v3 — 11页 · 10分钟）...")
    for name, fn in slides:
        print(f"  [{slides.index((name, fn))+1:2d}/10] {name}...")
        fn(p)

    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = str(out_dir / "ArchCheck_答辩PPT_v4.pptx")
    p.save(out)
    print(f"\n已保存: {out}")
    print(f"共 {len(p.slides)} 页 · 全中文 · 含 {4} 页平台实操演示 + 1 页设计原理")
    print()
    print("=== 截图准备清单 ===")
    print("S6  — 平台主页面完整截图（上传区 + 数据编辑面板）")
    print("S7  — Loading 状态截图（Agent 日志流全展开）")
    print("S8  — demo_review_annotated.png（违规标注图）")
    print("S8  — correction_plan.png（绿色修正建议图）")
    print("S9  — 问题详情卡片 + 导出面板截图")

if __name__ == "__main__":
    main()
