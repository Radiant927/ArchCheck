# -*- coding: utf-8 -*-
"""English weekly-progress PPT for 2026-09-01 (white bg · serif · 14pt body).

Concise CET-4 English, professional terms kept (B-Rep / CSG / IFC / MEP / KB…).
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

FONT = "宋体"
DARK = (0x1F, 0x3A, 0x5F)     # title blue
BODY = (0x33, 0x33, 0x33)     # body dark grey
ACC  = (0x2E, 0x5E, 0x8C)     # accent bar blue
GRN  = (0x2E, 0x6E, 0x3A)     # green

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

# ============ S1 Title ============
s = new_slide()
add_bar(s, 0, 0, 13.333, 0.22, DARK)
tf = add_text(s, 1.0, 2.35, 11.3, 1.3)
add_para(tf, "ArchCheck · AI Building-Code Compliance Review", size=38, bold=True,
         color=DARK, align=PP_ALIGN.CENTER)
tf = add_text(s, 1.0, 3.6, 11.3, 0.6)
add_para(tf, "Weekly Progress Report · 2026-09-01", size=22, color=BODY,
         align=PP_ALIGN.CENTER)
tf = add_text(s, 1.0, 6.3, 11.3, 0.5)
add_para(tf, "Huang Yunlin · NTU Pre", size=16, color=(0x88, 0x88, 0x88),
         align=PP_ALIGN.CENTER)

# ============ S2 Answering last week's questions ============
s = new_slide()
add_title(s, "Answering Last Week's Questions")
data = [
    ["Last week's question", "This week's answer"],
    ["Does IFC carry B-Rep? (affects Step 3: CSG or not)",
     "Yes. Main models have B-Rep → exact geometry, no CSG kernel needed"],
    ["Can the KB move from 'find articles' to 'real judging'?",
     "Yes. Extractor upgrade → door–room link 6/100 → 98/100"],
    ["Search style?", "Keywords first, semantic as fallback"],
]
tbl = add_table(s, 4, 2, 0.9, 1.6, 11.5, 4.4, col_widths=[5.2, 6.3])
fill_table(tbl, data, size=15)

# ============ S3 Line 1: model reading & processing ============
s = new_slide()
add_title(s, "Line 1 · Model Reading & Processing")
# Card A
add_bar(s, 0.9, 1.55, 0.12, 0.5, ACC)
tf = add_text(s, 1.15, 1.5, 5.6, 4.6)
add_para(tf, "Door–Room Link  6/100 → 98/100", size=19, bold=True, color=DARK, space_after=10)
add_para(tf, "Method", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "bbox footprint → every room gets a floor area", size=14, space_after=2)
add_para(tf, "placement matrix includes rotation", size=14, space_after=2)
add_para(tf, "boundary data first, geometry fills gaps", size=14, space_after=10)
add_para(tf, "Result", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "escape distance: 6 → 98 rooms judged", size=14, space_after=2)
add_para(tf, "door width & exits: 98/100 judged", size=14, space_after=2)
add_para(tf, "found 2 real violations (rooms 3.04 / 6.04)", size=14, space_after=2)
# Card B
add_bar(s, 6.85, 1.55, 0.12, 0.5, ACC)
tf = add_text(s, 7.1, 1.5, 5.6, 4.6)
add_para(tf, "Fire Hydrant Spacing (MEP-009)", size=19, bold=True, color=DARK, space_after=10)
add_para(tf, "Method", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "fire-pipe centroid → nearest-neighbor spacing", size=14, space_after=10)
add_para(tf, "Meaning", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "reading upgraded: attributes → geometry + distance", size=14, space_after=10)
add_para(tf, "Result", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "office_3f: 6 pipes, spacing 13.0m ≤ 30m", size=14, space_after=2)

# ============ S4 Line 2: rules vs code (rule scaling) ============
s = new_slide()
add_title(s, "Line 2 · Rules vs Code: 21 → 47 per Region")
tf = add_text(s, 0.9, 1.5, 11.5, 0.7)
add_para(tf, "Rules now hold real thresholds from GB 55037 / GB 50016 / GB 50974 / FC23 / PUB / SS",
         size=15, bold=True, color=DARK)
tf = add_text(s, 0.9, 2.2, 11.5, 3.2)
add_para(tf, "Principle — every rule can be judged, precise, traceable", size=15, bold=True,
         color=ACC, space_after=8)
add_para(tf, "① real fields only — match extractor output, no dead rules", size=14, space_after=6)
add_para(tf, "② scope by condition — judge only matching elements (e.g. pipe_type==fire)", size=14, space_after=6)
add_para(tf, "③ cite the code — code_ref → exact clause; thresholds verified (door 0.9m / spacing 30m)",
         size=14, space_after=10)
add_para(tf, "Effect", size=15, bold=True, color=ACC, space_after=8)
add_para(tf, "question → clause → rule → real judgement on the model", size=14, space_after=6)
add_para(tf, "KB: from 'search' to 'basis for judgement'", size=14, space_after=6)

# ============ S5 Line 3: B-Rep survey ============
s = new_slide()
add_title(s, "Line 3 · B-Rep Survey: Built-In, Ready for Exact Geometry")
tf = add_text(s, 0.9, 1.45, 11.5, 0.6)
add_para(tf, "Survey · IfcFacetedBrep count in 4 samples", size=15, bold=True, color=ACC)
data = [
    ["Sample", "Schependomlaan", "office_3f", "FZK_Haus", "Duplex_MEP"],
    ["B-Rep count", "4202", "362 (whole)", "140", "0"],
]
tbl = add_table(s, 2, 5, 0.9, 2.0, 11.5, 0.9, col_widths=[2.0, 2.7, 2.3, 2.2, 2.3])
fill_table(tbl, data, size=14)
# Left: original plan + CSG vs B-Rep
add_bar(s, 0.9, 3.15, 0.12, 0.55, ACC)
tf = add_text(s, 1.15, 3.12, 5.5, 3.1)
add_para(tf, "Original plan: CSG + Boolean", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "keeps modelling history, but needs a self-built solid kernel — high cost", size=14, space_after=10)
add_para(tf, "CSG vs B-Rep (both common in IFC)", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "CSG: parametric build, keeps history (Boolean tree)", size=14, space_after=2)
add_para(tf, "B-Rep: explicit shells — surfaces close into a solid", size=14, space_after=2)
# Right: what we do
add_bar(s, 6.85, 3.15, 0.12, 0.55, ACC)
tf = add_text(s, 7.1, 3.12, 5.6, 3.1)
add_para(tf, "What we do", size=15, bold=True, color=ACC, space_after=3)
add_para(tf, "B-Rep is built-in → use it directly, no kernel", size=14, space_after=2)
add_para(tf, "divergence theorem (signed tetrahedra) → exact volume", size=14, space_after=2)
add_para(tf, "verified on column / beam / slab", size=14, space_after=10)
add_para(tf, "Boolean cut → tessellation + precision note", size=14, space_after=2)
add_bar(s, 0.9, 6.35, 0.12, 0.55, DARK)
tf = add_text(s, 1.15, 6.38, 11.0, 0.7)
add_para(tf, "Step 3 = B-Rep / mesh mix + precision note (no CSG kernel)", size=17, bold=True,
         color=DARK)

# ============ S6 One engine, four datasets ============
s = new_slide()
add_title(s, "One Engine · Four Datasets → Adaptive Judgement")
data = [
    ["Sample", "Data covered", "Demo rules judged"],
    ["office_3f", "rooms + MEP + electrical + fire pipes",
     "all 5 rules judged · 3 emergency-light issues"],
    ["Schependomlaan", "housing: 100 rooms + doors + structure",
     "100 rooms judged · 11 narrow-door issues"],
    ["Duplex", "MEP only: 427 pipes + electrical",
     "MEP rules: diameter / slope / spacing"],
    ["FZK", "building + structure",
     "building rules: escape / structure"],
]
tbl = add_table(s, 5, 3, 0.9, 1.7, 11.5, 4.2, col_widths=[2.4, 4.2, 4.9])
fill_table(tbl, data, size=14)

# ============ S7 Effect of this week's upgrade ============
s = new_slide()
add_title(s, "This Week's Extractor Upgrade in Action")
data = [
    ["Scenario", "8-27 (last week)", "Now"],
    ["Door width", "data missing", "11 violations found"],
    ["Escape distance", "only 6 rooms", "100 rooms judged"],
    ["Exit count", "2 false alarms", "clean (false positives fixed)"],
]
tbl = add_table(s, 4, 3, 0.9, 1.7, 11.5, 3.2, col_widths=[3.0, 4.0, 4.5])
fill_table(tbl, data, size=15)
add_bar(s, 0.9, 5.3, 0.12, 0.55, DARK)
tf = add_text(s, 1.15, 5.33, 11.0, 0.7)
add_para(tf, "From 'cannot judge' to 'real judgement'", size=18, bold=True, color=DARK)

# ============ S8 Next steps ============
s = new_slide()
add_title(s, "Next Steps")
tf = add_text(s, 0.9, 1.8, 11.5, 4.0)
add_para(tf, "· exact geometry: B-Rep / mesh mix + precision note (foundation ready)", size=16, space_after=14)
add_para(tf, "· new fields: IfcZone (fire zones) · IfcRamp (ramps) · pipe topology", size=16, space_after=14)
add_para(tf, "· IDS-driven extraction (read what the code needs)", size=16, space_after=14)
tf = add_text(s, 0.9, 6.4, 11.5, 0.6)
add_para(tf, "Please guide us", size=20, bold=True, color=DARK, align=PP_ALIGN.CENTER)

out = "presentation/2026-08-26/本周进展汇报_2026-09-01_EN.pptx"
prs.save(out)
print("saved:", out)
print("slides:", len(prs.slides._sldIdLst))
