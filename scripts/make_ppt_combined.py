# -*- coding: utf-8 -*-
"""Combined 8-25 deck: semantic search + 6-tier roadmap, one consolidated Next Steps.

Usage:  python scripts/make_ppt_combined.py
Output: presentation/2026-08-25/ArchCheck_Progress_2026-08-25.pptx
"""
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "presentation" / "2026-08-25" / "ArchCheck_Progress_2026-08-25.pptx"

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
DARK = RGBColor(0x22, 0x22, 0x22)
GRAY = RGBColor(0x55, 0x55, 0x55)
RED = RGBColor(0xB0, 0x30, 0x30)
GREEN = RGBColor(0x1E, 0x6B, 0x3C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF2, 0xF4, 0xF7)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(BLANK)


def _set_bg(slide):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = WHITE


def tx(slide, left, top, width, height, lines, size=20, color=DARK,
       bold=False, align=PP_ALIGN.LEFT, font="Calibri"):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for text, level in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.text = text
        p.level = level
        p.alignment = align
        p.space_after = Pt(6)
        run = p.runs[0]
        run.font.size = Pt(size if level == 0 else max(size - 3, 12))
        run.font.bold = bold or (level == 0)
        run.font.color.rgb = color
        run.font.name = font
    return box


def title_bar(slide, text, size=30):
    box = slide.shapes.add_textbox(Inches(0.7), Inches(0.35), Inches(11.9), Inches(0.95))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.runs[0].font.size = Pt(size)
    p.runs[0].font.bold = True
    p.runs[0].font.color.rgb = NAVY
    p.runs[0].font.name = "Calibri"
    ln = slide.shapes.add_shape(1, Inches(0.7), Inches(1.28), Inches(11.9), Pt(2.2))
    ln.fill.solid()
    ln.fill.fore_color.rgb = NAVY
    ln.line.fill.background()
    ln.shadow.inherit = False
    return box


def make_table(slide, left, top, width, rows, col_widths, size=16,
               header_fill=NAVY, header_color=WHITE):
    n_rows, n_cols = len(rows), len(rows[0])
    shape = slide.shapes.add_table(n_rows, n_cols, Inches(left), Inches(top),
                                   Inches(width), Inches(0.42 * n_rows))
    tbl = shape.table
    for j, w in enumerate(col_widths):
        tbl.columns[j].width = Inches(w)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = Inches(0.06)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = 1
            cell.fill.solid()
            if i == 0:
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.fore_color.rgb = WHITE if i % 2 else LIGHT
            p = cell.text_frame.paragraphs[0]
            p.text = val
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            if not p.runs:
                continue
            run = p.runs[0]
            run.font.size = Pt(size if i else size)
            run.font.bold = (i == 0)
            run.font.color.rgb = header_color if i == 0 else DARK
            run.font.name = "Calibri"
    return shape


# ============================================================================
# PART 1 — Semantic search
# ============================================================================
# S1 · title
s = add_slide()
_set_bg(s)
tx(s, 1.4, 2.0, 10.5, 1.4,
   [("Semantic Knowledge Base Search", 0)], size=44, color=NAVY, bold=True)
tx(s, 1.4, 3.2, 10.5, 0.9,
   [("From keyword matching to meaning-based retrieval", 0)], size=26, color=GRAY)
tx(s, 1.4, 5.7, 10.5, 0.6, [("ArchCheck · 2026-08-25", 0)], size=18, color=GRAY)

# S2 · before
s = add_slide()
_set_bg(s)
title_bar(s, "Before: Keyword Search Had Three Hard Limits")
lims = [
    ("Synonym blind", "searching “escape” misses clauses written as “evacuation”"),
    ("No cross-lingual", "querying “exit” never matches the Chinese “出口”"),
    ("No natural language", "you can only type keywords, not ask a real question"),
]
y = 1.7
for head, body in lims:
    tx(s, 0.9, y, 11.5, 1.0, [(head, 0), ("• " + body, 1)], size=24, color=DARK)
    y += 1.35
tx(s, 0.9, y + 0.35, 11.5, 1.0,
   [("The knowledge base held the answers — users just couldn't reach them.", 0)],
   size=22, color=RED, bold=True)

# S3 · launch
s = add_slide()
_set_bg(s)
title_bar(s, "This Week ① — Semantic Search Launched")
tx(s, 0.9, 1.5, 11.6, 0.95,
   [("Every code clause → a 1024-dim vector; a question finds the semantically nearest clause — meaning, not wording.", 0)],
   size=20, color=DARK)
make_table(
    s, 0.9, 2.55, 11.6,
    [["", "Choice", "Why"],
     ["Model", "BAAI / bge-m3", "free, multilingual, zh–en aligned"],
     ["Runtime", "ONNX CPU", "runs on any laptop, no GPU"],
     ["Corpus", "1,590 chunks / 6 codes", "1 CN + 5 SG, all free documents"]],
    [1.4, 3.4, 6.8], size=16)
tx(s, 0.9, 4.35, 11.6, 0.5, [("Real results (run live, not illustrative)", 0)],
   size=18, color=NAVY, bold=True)
make_table(
    s, 0.9, 4.85, 11.6,
    [["Capability", "Question", "Hit"],
     ["Synonym", "“escape stair width”", "CN evacuation stairs + SG “1.5m in width”"],
     ["Cross-lingual", "“how wide should escape stairs be”", "SG Fire Code clause"],
     ["Natural language", "“Can gas pipes run in a residential stairwell?”", "CN gas-pipe clause"],
     ["Concrete scene", "“Exits needed for an underground car park?”", "CN car park + exit clauses"],
     ["Indirect / alias", "“room at a corridor dead-end”", "CN dead-end-room clause"]],
    [2.2, 4.6, 4.8], size=13)

# S4 · results
s = add_slide()
_set_bg(s)
title_bar(s, "This Week ② — How Well Does It Work? (Measured honestly)")
tx(s, 0.9, 1.40, 11.6, 0.62,
   [("How we tested: 63 questions — 55 that the knowledge base should answer, plus 8 on topics it does NOT cover (to verify it won't fabricate answers). “Clause” means the exact regulation sentence.", 0)],
   size=15, color=GRAY)
make_table(
    s, 0.9, 2.08, 11.6,
    [["Metric", "What it means", "Result (55 questions)"],
     ["P@1", "The very first result is the correct clause", "67%"],
     ["P@3", "The correct clause appears somewhere in the first 3 results", "84%"],
     ["Recall@3", "Share of the clauses that should be found that actually were", "84%"],
     ["F1", "One combined score of accuracy and completeness", "75%"],
     ["Document-level (looser test)", "Only the right document was found — the exact clause may be wrong", "91%"]],
    [3.1, 6.2, 2.3], size=14)
fx = [
    ("Finding the document ≠ finding the clause",
     "91% only means the right code book was found (e.g. GB 55037); 67% means the exact sentence. 67% is the honest number."),
    ("Not a replacement for keyword search",
     "A standard keyword method (BM25) scored 71%, close to ours. Semantic search wins on synonyms, cross-language and natural wording — so we keep both."),
    ("Anti-fabrication guard",
     "On the 8 questions outside the knowledge base, confident-but-wrong answers fell from 8/8 to 4/8, and no correct answer was ever blocked (0/55)."),
]
y = 4.85
for head, body in fx:
    tx(s, 0.9, y, 11.6, 0.72, [(head, 0), ("• " + body, 1)], size=15, color=DARK)
    y += 0.72
tx(s, 0.9, 6.95, 11.6, 0.5,
   [("Bottom line: 67% / 84% / 84% — accurate and honest, nothing inflated.", 0)],
   size=18, color=GREEN, bold=True)

# ============================================================================
# PART 2 — Roadmap
# ============================================================================
# S5 · title
s = add_slide()
_set_bg(s)
tx(s, 1.4, 2.0, 10.5, 1.4,
   [("The Road to Production-Ready Compliance Checking", 0)], size=40, color=NAVY, bold=True)
tx(s, 1.4, 3.3, 10.5, 0.9,
   [("A 6-tier industry-standard roadmap · progress & next steps", 0)], size=24, color=GRAY)
tx(s, 1.4, 5.7, 10.5, 0.6, [("ArchCheck · 2026-08-25", 0)], size=18, color=GRAY)

# S6 · overview
s = add_slide()
_set_bg(s)
title_bar(s, "The Roadmap at a Glance — 6 Tiers")
make_table(
    s, 0.9, 1.6, 11.6,
    [["Tier", "Done (this week)", "Plan (next)", "Progress"],
     ["1 · IFC reading", "spaces · doors · structure · MEP · electrical read; exact area / volume / material; mixed-unit fix",
      "connections · distribution systems · openings · quantity sets · profile shapes", "~70%"],
     ["2 · Quality validation", "QA 4 checks (units / spaces / geometry / boundaries); honest “not checked / area unknown”",
      "IDS parser + semantic validation (missing attributes, wrong classification)", "~40%"],
     ["3 · Geometry & quantities", "exact area (triangle projection) · exact volume · material take-off · basic clash pre-check",
      "boolean operations (CSG kernel) · swept solids · exact sections", "~85%"],
     ["4 · Clash & coordination", "MEP vs structure bbox + point-in-mesh confirmation (real vs bbox noise)",
      "full-discipline clash · clear-height checks · grading (hard / soft / clearance)", "early"],
     ["5 · Rules", "5 disciplines · 16 rules (CN + SG) · clause → rule tool",
      "16 → 50+ (fire / egress / MEP) · context & exceptions · cross-rule linkage", "~15%"],
     ["6 · Delivery & trust", "BCF 2.1 · COBie CSV · HTML/Excel/PNG · 4 samples run",
      "BCF viewpoints · fuller COBie · IFC with annotations · 10+ real projects · benchmark", "~35%"]],
    [2.6, 4.0, 3.7, 1.3], size=11)
tx(s, 0.9, 6.0, 11.6, 0.9,
   [("Foundation built: precise geometry + real samples + multi-discipline rules + delivery formats — now we build up.", 0)],
   size=20, color=NAVY, bold=True)

# S7 · breakthrough
s = add_slide()
_set_bg(s)
title_bar(s, "This Week's Breakthrough — Precise Geometry & Quantities (Tier ③)", size=27)
pts = [
    ("Exact area", "triangle projection replaces convex hull — L-shaped room 36 → 27 m², no over-estimate"),
    ("Exact volume", "signed-tetrahedron — office_3f slab 96.9 m³ · Schependomlaan structural total 287.4 m³"),
    ("Material & quantity take-off", "per-material volume + per-type counts → “structural quantities by material”"),
    ("Mixed-unit repair", "models declared in mm but modelled in metres auto-corrected (Schependomlaan)"),
    ("Basic clash pre-check", "MEP vs structure bbox + point-in-mesh confirmation — real penetration, not bbox noise"),
]
y = 1.6
for head, body in pts:
    tx(s, 0.9, y, 11.6, 0.95, [(head, 0), ("• " + body, 1)], size=19, color=DARK)
    y += 1.02
tx(s, 0.9, y + 0.12, 11.6, 0.7,
   [("Unlocks what's downstream: quantities, clash detection, clear-height checks — all depend on real geometry.", 0)],
   size=18, color=GREEN, bold=True)

# S8 · done vs open
s = add_slide()
_set_bg(s)
title_bar(s, "Where We Stand — Done vs Still Open (honest)")
tx(s, 0.9, 1.55, 5.7, 0.55, [("Already in place", 0)], size=21, color=GREEN, bold=True)
done = [
    "5-discipline rule engine (CN + SG)",
    "BCF 2.1 / COBie export",
    "Clause → machine-rule tooling",
    "Semantic knowledge-base search",
    "Precise geometry, volumes, materials",
    "Real samples: Duplex_MEP, Schependomlaan",
]
y = 2.25
for d in done:
    tx(s, 0.9, y, 5.7, 0.6, [("• " + d, 0)], size=17, color=DARK)
    y += 0.62
tx(s, 6.9, 1.55, 5.7, 0.55, [("Still open (flagged, not hidden)", 0)], size=21, color=RED, bold=True)
opn = [
    "Boolean operations (openings) — needs CSG kernel",
    "IDS-based quality validation",
    "Rule volume: 16 → hundreds",
    "Full-discipline clash + clear-height checks",
    "BCF viewpoints · full COBie",
    "Scale benchmark vs commercial tools",
]
y = 2.25
for d in opn:
    tx(s, 6.9, y, 5.7, 0.6, [("• " + d, 0)], size=17, color=DARK)
    y += 0.62
tx(s, 0.9, 6.35, 11.6, 0.7,
   [("Everything we can't do yet is stated explicitly — no silent omissions.", 0)],
   size=18, color=GRAY, bold=True)

# ============================================================================
# PART 3 — Consolidated Next Steps (merged from both parts)
# ============================================================================
s = add_slide()
_set_bg(s)
title_bar(s, "Next Steps — Consolidated")
# left column: knowledge-base search
tx(s, 0.9, 1.5, 5.7, 0.55, [("Knowledge-base search", 0)], size=21, color=GREEN, bold=True)
kb = [
    ("Attack hard queries", "query rewriting / domain aliases — hard-query hit rate is now 45%"),
    ("Cross-code retrieval", "route by CN / SG, or split the query — cross-code recovery is 33%"),
    ("Stronger guard", "top1−top2 score margin — no false rejects so far (0/55)"),
    ("Grow the gold standard", "keep adding test queries as the knowledge base grows"),
]
y = 2.2
for i, (head, body) in enumerate(kb, 1):
    tx(s, 0.9, y, 5.7, 1.05, [(f"{i}.  {head}", 0), ("• " + body, 1)], size=15, color=DARK)
    y += 1.12
# right column: platform roadmap
tx(s, 6.9, 1.5, 5.7, 0.55, [("Platform — 6-tier roadmap", 0)], size=21, color=NAVY, bold=True)
pl = [
    ("Rule expansion", "16 → 50+ rules, fire / egress / MEP first (2–3 wks)"),
    ("IDS quality checking", "subset parser + semantic validation (1–2 wks)"),
    ("Clash deepening", "full-discipline clash + clear-height + grading (2 wks)"),
    ("Delivery", "BCF viewpoints · fuller COBie · 10+ real projects (1–2 wks)"),
]
y = 2.2
for i, (head, body) in enumerate(pl, 1):
    tx(s, 6.9, y, 5.7, 1.05, [(f"{i}.  {head}", 0), ("• " + body, 1)], size=15, color=DARK)
    y += 1.12
tx(s, 6.9, y, 5.7, 0.6,
   [("Long-term: boolean ops (CSG) · full rule coverage · benchmark vs tools", 0)],
   size=14, color=GRAY, bold=True)
tx(s, 0.9, 6.55, 11.6, 0.6,
   [("Two tracks, one goal: more rules, better retrieval, verified at real scale.", 0)],
   size=19, color=GREEN, bold=True)

prs.save(OUT)
print("saved:", OUT)
