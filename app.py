"""
ArchCheck — Building Plan Automated Review Platform
Main Entry Point · Upload & Initiate Review
"""
import json
import time
import io
import base64
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
OUTPUT = HERE / "output"

# ============================================================
# PAGE CONFIG — must be first Streamlit call
# ============================================================
st.set_page_config(
    page_title="ArchCheck — Building Plan Review",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# AICHER DESIGN TOKENS
# ============================================================
C = {
    "blue": "#5BA3D9", "orange": "#F09235", "red": "#D32F2F",
    "green": "#7CB342", "silver": "#9BA3AB", "text": "#1F2429",
    "muted": "#6B7480", "dim": "#6B7480", "border": "#EDF0F3", "bg": "#FAFBFC",
}

# ============================================================
# GLOBAL CSS
# ============================================================
st.markdown(f"""<style>
.stApp {{
    background-color: {C["bg"]};
    background-image:
        linear-gradient({C["border"]} 1px, transparent 1px),
        linear-gradient(90deg, {C["border"]} 1px, transparent 1px);
    background-size: 32px 32px;
}}
.aicher-band {{
    display:flex; height:6px; border-radius:3px; margin-bottom:20px; overflow:hidden;
}}
.aicher-band div {{ height:100%; }}
.aicher-band .band-civil {{ flex:2; background:{C["blue"]}; }}
.aicher-band .band-eee   {{ flex:1; background:{C["orange"]}; }}
.aicher-band .band-risk  {{ flex:1; background:{C["red"]}; }}
.aicher-band .band-pass  {{ flex:.6; background:{C["green"]}; }}
.aicher-stat {{
    text-align:center; padding:20px 12px; background:#FFFFFF;
    border:1px solid {C["border"]}; border-radius:4px;
}}
.aicher-stat .value {{
    font-size:42px; font-weight:800; color:{C["text"]}; line-height:1.1;
}}
.aicher-stat .label {{
    font-size:12px; color:{C["silver"]}; letter-spacing:0.08em;
    text-transform:uppercase; margin-top:4px;
}}
.aicher-stat.blue  .value {{ color:{C["blue"]}; }}
.aicher-stat.orange .value {{ color:{C["orange"]}; }}
.aicher-stat.red   .value {{ color:{C["red"]}; }}
.aicher-stat.green .value {{ color:{C["green"]}; }}
.aicher-label {{
    font-size:12px; letter-spacing:0.34em; color:{C["silver"]};
    font-weight:600; text-transform:uppercase;
}}
.aicher-divider {{
    border:none; border-top:2px solid {C["text"]};
    margin:28px 0; opacity:0.08;
}}
.aicher-img-frame {{
    border:1px solid {C["border"]}; border-radius:4px;
    padding:8px; background:#FFFFFF;
}}
.aicher-card {{
    background:#FFFFFF; border:1px solid {C["border"]}; border-radius:4px;
    padding:20px; transition: box-shadow 0.15s;
}}
.aicher-card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,0.06); }}
.aicher-feature-icon {{
    width:40px; height:40px; border-radius:4px; display:flex;
    align-items:center; justify-content:center; font-size:24px;
    margin-bottom:12px;
}}
[data-testid="stSidebar"] {{
    background:#FFFFFF; border-right:1px solid {C["border"]};
}}
.stButton > button {{
    border-radius:4px; font-weight:600; letter-spacing:0.02em;
    border:1px solid {C["border"]}; transition: all 0.15s;
}}
.stButton > button[kind="primary"] {{
    background:{C["text"]}; color:#FFFFFF; border-color:{C["text"]};
}}
.stButton > button[kind="primary"]:hover {{
    background:{C["blue"]}; border-color:{C["blue"]};
}}
[data-testid="stFileUploader"] {{
    border:2px dashed {C["border"]}; border-radius:4px;
    background:#FFFFFF;
}}
[data-testid="stExpander"] {{
    border:1px solid {C["border"]}; border-radius:4px; background:#FFFFFF;
}}
.stProgress > div > div > div {{
    background:{C["blue"]} !important;
}}
div[data-testid="stStatus"] {{
    border:1px solid {C["border"]}; border-radius:4px;
}}
.issue-card {{
    background:#FFFFFF; border:1px solid {C["border"]};
    border-radius:2px; padding:14px 18px; margin-bottom:8px;
}}
.issue-card.civil {{ border-left:4px solid {C["blue"]}; }}
.issue-card.eee   {{ border-left:4px solid {C["orange"]}; }}
.issue-card.conflict {{ border-left:4px solid {C["red"]}; background:#FEF2F2; }}
.sev-badge {{
    display:inline-block; margin-left:8px; padding:1px 8px; border-radius:2px;
    font-size:12px; font-weight:600;
}}
.metric-bar {{
    height:6px; border-radius:3px; background:{C["border"]}; overflow:hidden;
}}
.metric-bar .fill {{ height:100%; border-radius:3px; }}
div[data-testid="stTabs"] button {{
    font-weight:600;
}}
.agent-card {{
    background:#FFFFFF; border:1px solid {C["border"]}; border-radius:4px;
    padding:24px; transition: box-shadow 0.15s;
}}
.flow-node {{
    padding:12px 18px; border-radius:4px; text-align:center;
    font-weight:600; font-size:14px; white-space:nowrap;
}}
.flow-arrow {{
    color:{C["silver"]}; font-size:21px; display:flex; align-items:center;
}}
.tech-card {{
    background:#FFFFFF; border:1px solid {C["border"]}; border-radius:4px;
    padding:20px; text-align:center;
}}
.roadmap-card {{
    background:#FFFFFF; border:1px solid {C["border"]}; border-radius:4px;
    padding:16px;
}}
</style>""", unsafe_allow_html=True)

# ============================================================
# INIT SESSION STATE
# ============================================================
defaults = {
    "page": "upload",
    "uploaded_image": None,
    "civil_results": [],
    "eee_results": [],
    "conflicts": [],
    "all_issues": [],
    "building_data": None,
    "review_loading": False,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ============================================================
# SIDEBAR BRANDING + NAVIGATION
# ============================================================
with st.sidebar:
    st.markdown("## ArchCheck")
    st.markdown(
        f'<div class="aicher-band">'
        f'<div class="band-civil"></div><div class="band-eee"></div>'
        f'<div class="band-risk"></div><div class="band-pass"></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-size:14px;color:{C["muted"]};line-height:1.5;">'
        f'AI-powered building code compliance review platform.<br>'
        f'Multi-Agent: Civil + EEE + Coordinator</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    page_labels = {"upload": "Upload & Review", "results": "Review Results", "architecture": "Platform Architecture"}
    current_idx = ["upload", "results", "architecture"].index(st.session_state.page)
    nav = st.radio(
        "Navigation",
        options=["upload", "results", "architecture"],
        format_func=lambda x: page_labels[x],
        index=current_idx,
        key="nav_radio",
        label_visibility="collapsed",
    )
    if nav != st.session_state.page:
        st.session_state.page = nav
        st.rerun()
    st.markdown("---")
    st.markdown(
        f'<span class="aicher-label">Aicher System · v2.0</span>',
        unsafe_allow_html=True,
    )

# ============================================================
# RULES DATA (hot-reload from JSON if available)
# ============================================================
def load_rules():
    """Load rules from JSON files with fallback to built-in defaults."""
    civil_path = Path("data/civil_rules.json")
    eee_path = Path("data/eee_rules.json")

    default_civil = [
        {"id":"CIVIL-001","name":"Evacuation Distance Check","field":"corridor_length_m","operator":"<=","threshold":30,"severity":"High","code_ref":"GB 50016 5.5.17","message":"Corridor too long (actual {value}m > limit {threshold}m). Add refuge passage or redesign evacuation route."},
        {"id":"CIVIL-002","name":"Fire Zone Area Check","field":"fire_zone_area_sqm","operator":"<=","threshold":2500,"severity":"High","code_ref":"GB 50016 5.3.1","message":"Fire zone area exceeds limit (actual {value}m² > limit {threshold}m²). Add fire separation."},
        {"id":"CIVIL-003","name":"Emergency Exit Count Check","field":"exit_count","operator":">=","threshold":2,"condition_field":"room_area_sqm","condition_operator":">","condition_threshold":50,"severity":"Medium","code_ref":"GB 50016 5.5.8","message":"Room area {condition_value}m² > {condition_threshold}m², only {value} exit(s), at least {threshold} required."},
        {"id":"CIVIL-004","name":"Evacuation Door Width Check","field":"door_width_m","operator":">=","threshold":0.9,"severity":"Low","code_ref":"GB 50016 5.5.18","message":"Door width insufficient (actual {value}m < required {threshold}m). Widen the door."},
    ]
    default_eee = [
        {"id":"EEE-001","name":"Emergency Lighting Check","field":"has_emergency_light","operator":"==","threshold":True,"condition_field":"type","condition_operator":"in","condition_threshold":["Corridor","Stairwell","Vestibule"],"severity":"High","code_ref":"GB 51309 3.2.1","message":"{room_name} (type: {condition_value}) lacks emergency lighting. Install fixture."},
        {"id":"EEE-002","name":"Panel Water Clearance Check","field":"dist_to_water_m","operator":">=","threshold":1.5,"severity":"Medium","code_ref":"GB 50054 4.2.3","message":"Panel is only {value}m from water source, {threshold}m minimum required. Relocate panel."},
        {"id":"EEE-003","name":"Circuit Load Check","field":"circuit_load_a","operator":"<=","threshold":16,"severity":"Medium","code_ref":"GB 50054 3.4","message":"Circuit overload (actual {value}A > limit {threshold}A). Split circuit or reduce load."},
        {"id":"EEE-004","name":"Outlet Spacing Check","field":"outlet_spacing_m","operator":"<=","threshold":6,"severity":"Low","code_ref":"GB 50055 6.0.3","message":"Outlet spacing too large (actual {value}m > limit {threshold}m). Add receptacle."},
    ]

    civil = default_civil
    eee = default_eee
    if civil_path.exists():
        try:
            civil = json.loads(civil_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if eee_path.exists():
        try:
            eee = json.loads(eee_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return civil, eee

CIVIL_RULES, EEE_RULES = load_rules()

# ============================================================
# DEMO BUILDING DATA
# ============================================================
DEMO_DATA = {
    "project_name": "Sample Office Building — 1F Floor Plan",
    "rooms": [
        {"id":"R001","name":"Office A","type":"Office","room_area_sqm":85,"exit_count":1,"door_width_m":1.0,"has_emergency_light":True,"dist_to_water_m":3.0,"circuit_load_a":12,"outlet_spacing_m":5.0,"corridor_length_m":0},
        {"id":"R002","name":"Corridor","type":"Corridor","room_area_sqm":42,"exit_count":2,"door_width_m":1.2,"has_emergency_light":False,"dist_to_water_m":5.0,"circuit_load_a":8,"outlet_spacing_m":8.0,"corridor_length_m":42},
        {"id":"R003","name":"Electrical Room","type":"Equipment Room","room_area_sqm":12,"exit_count":1,"door_width_m":0.9,"has_emergency_light":True,"dist_to_water_m":0.8,"circuit_load_a":20,"outlet_spacing_m":3.0,"corridor_length_m":0},
        {"id":"R004","name":"Meeting Room","type":"Meeting Room","room_area_sqm":120,"exit_count":2,"door_width_m":1.5,"has_emergency_light":True,"dist_to_water_m":10.0,"circuit_load_a":10,"outlet_spacing_m":4.0,"corridor_length_m":0},
        {"id":"R005","name":"Stairwell","type":"Stairwell","room_area_sqm":20,"exit_count":1,"door_width_m":1.1,"has_emergency_light":False,"dist_to_water_m":8.0,"circuit_load_a":6,"outlet_spacing_m":0,"corridor_length_m":0},
    ],
    "fire_zones": [
        {"id":"FZ001","name":"Fire Zone 1","fire_zone_area_sqm":2800,"rooms":["R001","R002","R003"]},
        {"id":"FZ002","name":"Fire Zone 2","fire_zone_area_sqm":140,"rooms":["R004","R005"]},
    ],
}

# ============================================================
# RULES ENGINE
# ============================================================
OPERATORS = {
    "<=": lambda a,b: a<=b, ">=": lambda a,b: a>=b, ">": lambda a,b: a>b,
    "<": lambda a,b: a<b, "==": lambda a,b: a==b, "!=": lambda a,b: a!=b,
    "in": lambda a,b: a in b, "not_in": lambda a,b: a not in b,
}

def run_rules(rules, item, prefix):
    violations = []
    for rule in rules:
        field = rule["field"]
        if field not in item:
            continue
        value = item[field]
        threshold = rule["threshold"]
        cond_value = None
        cond_threshold = None
        if "condition_field" in rule:
            cond_value = item.get(rule["condition_field"])
            if cond_value is None:
                continue
            cond_threshold = rule["condition_threshold"]
            if not OPERATORS[rule["condition_operator"]](cond_value, cond_threshold):
                continue
        op_func = OPERATORS[rule["operator"]]
        if op_func(value, threshold):
            continue
        room_name = item.get("name", item.get("id", "?"))
        msg = rule["message"].replace("{value}", str(value)).replace("{threshold}", str(threshold)).replace("{room_name}", str(room_name))
        if cond_value is not None:
            msg = msg.replace("{condition_value}", str(cond_value)).replace("{condition_threshold}", str(cond_threshold))
        violations.append({
            "title": rule["name"], "description": msg,
            "location": room_name, "severity": rule["severity"],
            "code_ref": rule["code_ref"], "type": prefix,
            "rule_id": rule["id"],
        })
    return violations

# ============================================================
# SHARED FLOOR PLAN DRAWING
# ============================================================
# Layout: 1800×1200 canvas. Floor plan occupies left ~2/3 (x:30→1230, y:80→1130).
# Right panel (x:1260→1770) holds legend, scale bar, north arrow, fire zone info.

FP_X1, FP_Y1 = 30, 80    # floor plan top-left
FP_X2, FP_Y2 = 1230, 1130  # floor plan bottom-right
FP_W = FP_X2 - FP_X1      # 1200
FP_H = FP_Y2 - FP_Y1      # 1050

ROOM_COLORS = {
    "office": (240, 245, 250),
    "corridor": (228, 238, 248),
    "stairs": (255, 248, 235),
    "elec": (252, 238, 238),
}

def _load_fonts(sizes=(36, 28, 22)):
    try:
        return tuple(ImageFont.truetype("arial.ttf", s) for s in sizes)
    except Exception:
        return (ImageFont.load_default(),) * len(sizes)

def _draw_floor_plan(draw, W, H):
    """Draw the shared floor plan base onto an image. Returns room rects dict."""
    ft, fm, fs = _load_fonts((36, 28, 22))

    # Outer border
    draw.rectangle([FP_X1-2, FP_Y1-2, FP_X2+2, FP_Y2+2], outline=(40, 45, 55), width=4)

    # Room definitions (x1, y1, x2, y2, label, type_key)
    rooms = [
        (FP_X1+20, FP_Y1+20, FP_X1+600, FP_Y1+430, "Office A\n(85 m²)", "office"),
        (FP_X1+620, FP_Y1+20, FP_X2-20, FP_Y1+430, "Meeting Room\n(120 m²)", "office"),
        (FP_X1+620, FP_Y1+455, FP_X1+890, FP_Y1+680, "Stairwell\n(20 m²)", "stairs"),
        (FP_X1+910, FP_Y1+455, FP_X2-20, FP_Y1+680, "Electrical\nRoom (12 m²)", "elec"),
        (FP_X1+20, FP_Y1+710, FP_X2-20, FP_Y2-20, "Corridor  (42 m)", "corridor"),
    ]

    room_rects = {}
    for rx1, ry1, rx2, ry2, label, rtype in rooms:
        fc = ROOM_COLORS[rtype]
        draw.rectangle([rx1, ry1, rx2, ry2], fill=fc, outline=(130, 140, 150), width=3)

        # Room name centered
        lines = label.split("\n")
        cx = (rx1 + rx2) // 2
        cy_start = (ry1 + ry2) // 2 - (len(lines) - 1) * 18
        for li, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=fm)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw//2, cy_start + li * 36), line, fill=(30, 35, 45), font=fm)

        # Store for later use
        key = rtype if rtype == "corridor" else label.split("\n")[0]
        room_rects[key] = (rx1, ry1, rx2, ry2)

    # Fire zone boundary (dashed blue line around Fire Zone 1)
    fz_x1, fz_y1 = FP_X1+8, FP_Y1+8
    fz_x2, fz_y2 = FP_X2-8, FP_Y1+695
    dash = 20
    for x in range(fz_x1, fz_x2, dash*2):
        draw.line([(x, fz_y1), (min(x+dash, fz_x2), fz_y1)], fill=C["blue"], width=3)
        draw.line([(x, fz_y2), (min(x+dash, fz_x2), fz_y2)], fill=C["blue"], width=3)
    for y in range(fz_y1, fz_y2, dash*2):
        draw.line([(fz_x1, y), (fz_x1, min(y+dash, fz_y2))], fill=C["blue"], width=3)
        draw.line([(fz_x2, y), (fz_x2, min(y+dash, fz_y2))], fill=C["blue"], width=3)

    return room_rects

def _draw_info_panel(draw, W, H):
    """Draw right-side info panel: legend, scale bar, north arrow, fire zone label."""
    ft, fm, fs = _load_fonts((36, 28, 22))
    px = 1270  # panel x start

    # Legend box
    ly = FP_Y1
    draw.rectangle([px, ly, W-30, ly+200], fill=(255,255,255), outline=(200,205,210), width=2)
    draw.text((px+16, ly+10), "LEGEND", fill=(40,45,55), font=fm)
    items = [
        ("Office / Meeting", ROOM_COLORS["office"]),
        ("Corridor", ROOM_COLORS["corridor"]),
        ("Stairwell", ROOM_COLORS["stairs"]),
        ("Electrical Room", ROOM_COLORS["elec"]),
    ]
    for i, (lb, cl) in enumerate(items):
        yy = ly + 46 + i*30
        draw.rectangle([px+16, yy, px+46, yy+22], fill=cl, outline=(180,185,190))
        draw.text((px+56, yy), lb, fill=(40,45,55), font=fs)

    # Fire zone info
    fz_y = ly + 220
    draw.text((px+16, fz_y), "FIRE ZONE 1", fill=C["blue"], font=fm)
    draw.text((px+16, fz_y+34), "(2800 m²)", fill=C["blue"], font=fs)
    draw.text((px+16, fz_y+56), "Fire Zone 2", fill=C["silver"], font=fs)
    draw.text((px+16, fz_y+78), "(140 m²)", fill=C["silver"], font=fs)

    # Scale bar
    sy = H - 50
    draw.line([(px, sy), (px+200, sy)], fill=(40,45,55), width=4)
    draw.line([(px, sy-10), (px, sy+10)], fill=(40,45,55), width=3)
    draw.line([(px+100, sy-10), (px+100, sy+10)], fill=(40,45,55), width=3)
    draw.line([(px+200, sy-10), (px+200, sy+10)], fill=(40,45,55), width=3)
    draw.text((px+10, sy-42), "0         5        10m", fill=C["dim"], font=fs)

    # North arrow
    cx_n, cy_n = px+100, FP_Y1+420
    draw.ellipse([cx_n-22, cy_n-22, cx_n+22, cy_n+22], outline=(40,45,55), width=2)
    draw.polygon([(cx_n, cy_n-34), (cx_n-10, cy_n+6), (cx_n, cy_n-4), (cx_n+10, cy_n+6)], fill=(40,45,55))
    draw.text((cx_n-10, cy_n-62), "N", fill=(40,45,55), font=fm)


def generate_sample_image():
    """Generate a clean architectural floor plan (no violation markers)."""
    W, H = 1800, 1200
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((36, 28, 22))

    # Title bar
    draw.rectangle([0, 0, W, 70], fill=(30, 35, 45))
    draw.text((40, 12), "FLOOR PLAN  —  Office Building  1F", fill=(240, 245, 250), font=ft)

    # Floor plan body
    _draw_floor_plan(draw, W, H)

    # Info panel (right side)
    _draw_info_panel(draw, W, H)

    return img

# ============================================================
# IMAGE ANNOTATION — VIOLATION MARKERS
# ============================================================

# Per-issue positions inside the floor plan area (x, y)
# Spread across rooms so markers don't overlap
VIOLATION_POSITIONS = [
    (FP_X1+900, FP_Y1+800),   # 1  CIVIL-001  Corridor evacuation (right side)
    (FP_X1+1140, FP_Y1+120),  # 2  CIVIL-002  Fire Zone 1 area (Meeting Room top-right)
    (FP_X1+550, FP_Y1+80),    # 3  CIVIL-003  Office A exit count (top-right corner)
    (FP_X1+90,  FP_Y1+800),   # 4  EEE-001    Corridor emerg. light (far left)
    (FP_X1+650, FP_Y1+490),   # 5  EEE-001    Stairwell emerg. light (top-left)
    (FP_X1+1140, FP_Y1+490),  # 6  EEE-002    Elec Room water clearance (top-right)
    (FP_X1+950, FP_Y1+650),   # 7  EEE-003    Elec Room circuit load (bottom-left)
    (FP_X1+270, FP_Y1+800),   # 8  EEE-004    Corridor outlet spacing (left side)
]

MARKER_COLORS = {
    "civil":    (91, 163, 217),
    "eee":      (240, 146, 53),
    "conflict": (211, 47, 47),
}

def annotate_image(image, issues):
    """Overlay numbered violation markers on the floor plan."""
    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        font = ImageFont.load_default()

    for i, issue in enumerate(issues):
        if i >= len(VIOLATION_POSITIONS):
            break
        x, y = VIOLATION_POSITIONS[i]
        color = MARKER_COLORS.get(issue.get("type", "civil"), MARKER_COLORS["civil"])
        r = 30
        rgba = color + (255,)
        # Filled circle
        draw.ellipse([x-r, y-r, x+r, y+r], fill=rgba, outline=(255,255,255,255), width=3)
        # Number
        label = str(i+1)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x-tw//2, y-th//2-1), label, fill=(255,255,255,255), font=font)

    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


# ============================================================
# CORRECTION IMAGE — GREEN FIX CALLOUTS
# ============================================================

FIX_INSTRUCTIONS = {
    "CIVIL-001": "Add refuge passage to\nshorten evacuation path\nto <= 30m",
    "CIVIL-002": "Split fire zone: add fire\nwall here to keep each\n<= 2500 m²",
    "CIVIL-003": "Add second exit door\n(rooms > 50 m² require\nmin 2 exits)",
    "CIVIL-004": "Widen door to >= 0.9m\nclear width",
    "EEE-001":  "Install emergency light\nfixture (required for\nthis space type)",
    "EEE-002":  "Relocate panel: min 1.5m\nclearance from water\nsource required",
    "EEE-003":  "Split circuit or add\nseparate feeder\n(load 20A > 16A limit)",
    "EEE-004":  "Add wall outlet here\n(max 6m spacing\nbetween receptacles)",
}

def generate_correction_image(image, civ, eee, conflicts, bdata):
    """Generate correction plan with green callout boxes in right panel."""
    W, H = 1800, 1200
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((34, 24, 20))

    # Green title bar
    draw.rectangle([0, 0, W, 70], fill=(100, 160, 50))
    draw.text((40, 12), "CORRECTION PLAN  —  Suggested Fixes", fill=(255, 255, 255), font=ft)

    # Same floor plan as base image
    _draw_floor_plan(draw, W, H)

    # Draw small numbered green circle markers on the floor plan
    all_items = list(civ) + list(eee)
    for i, iss in enumerate(all_items):
        if i >= len(VIOLATION_POSITIONS):
            break
        x, y = VIOLATION_POSITIONS[i]
        r = 18
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(100,160,50), outline=(255,255,255), width=2)
        label = str(i+1)
        bbox = draw.textbbox((0, 0), label, font=fs)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x-tw//2, y-th//2-1), label, fill=(255,255,255), font=fs)

    # Callout boxes in the right panel area
    px = 1270  # panel x start
    cy = FP_Y1   # current y in the right panel

    for i, iss in enumerate(all_items):
        rid = iss.get("rule_id", "")
        fix_text = FIX_INSTRUCTIONS.get(rid, iss.get("title", "Fix issue"))
        lines = fix_text.split("\n")
        line_h = 26
        box_w = 480
        box_h = len(lines) * line_h + 24

        # Check if we need to wrap to bottom area (avoid overflow)
        if cy + box_h > H - 20:
            break

        # Green left border + white box
        draw.rectangle([px, cy, px+box_w, cy+box_h], fill=(255,255,255), outline=(100,160,50), width=3)
        draw.rectangle([px, cy, px+6, cy+box_h], fill=(100,160,50))

        # Number badge
        draw.text((px+16, cy+8), str(i+1), fill=(100,160,50), font=fm)

        # Fix text
        for j, line in enumerate(lines):
            draw.text((px+50, cy+10 + j*line_h), line, fill=(30,35,45), font=fs)

        cy += box_h + 6

    return img

# ============================================================
# REPORT GENERATOR
# ============================================================
def generate_report(image, all_issues, civil_r, eee_r, conflicts):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    img64 = base64.b64encode(buf.getvalue()).decode()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def rows(items, cls):
        out = ""
        for i, iss in enumerate(items, 1):
            sv = iss.get("severity", "Medium")
            sc = {"High":"high", "Medium":"mid", "Low":"low"}.get(sv, "mid")
            out += (
                f'<div class="card {cls}">'
                f'<div class="title">{i}. {iss["title"]}'
                f'<span class="sev sev-{sc}">{sv}</span></div>'
                f'<div class="desc">{iss.get("description","")}</div>'
                f'<div class="meta">LOC: {iss.get("location","-")} | REF: {iss.get("code_ref","-")}</div>'
                f'</div>'
            )
        return out

    def crow(conflicts):
        out = ""
        for i, c in enumerate(conflicts, 1):
            out += (
                f'<div class="card cnf">'
                f'<div class="title">{i}. {c["title"]}'
                f'<span class="sev sev-high">PRIORITY</span></div>'
                f'<div class="desc">{c.get("description","")}</div>'
                f'<div class="meta">LOC: {c.get("location","-")} | {c.get("related_issues","")}</div>'
                f'</div>'
            )
        return out

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>ArchCheck Report</title><style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Segoe UI','PingFang SC',sans-serif;max-width:960px;margin:0 auto;padding:40px 32px;color:{C["text"]};background:{C["bg"]};background-image:linear-gradient({C["border"]} 1px,transparent 1px),linear-gradient(90deg,{C["border"]} 1px,transparent 1px);background-size:32px 32px;}}
.band{{display:flex;height:6px;border-radius:3px;margin-bottom:32px;overflow:hidden;}}
.band-c{{flex:2;background:{C["blue"]};}}.band-e{{flex:1;background:{C["orange"]};}}.band-r{{flex:1;background:{C["red"]};}}.band-p{{flex:.6;background:{C["green"]};}}
.label{{font-size:12px;letter-spacing:.34em;color:{C["silver"]};font-weight:600;text-transform:uppercase;margin-bottom:8px;}}
h1{{font-size:52px;font-weight:800;line-height:1.15;margin-bottom:4px;}}h1 span{{color:{C["blue"]};}}
.subtitle{{font-size:17px;color:{C["muted"]};font-weight:300;margin-bottom:32px;}}
.stats{{display:flex;gap:16px;margin-bottom:32px;}}
.stat{{flex:1;background:#FFF;border:1px solid {C["border"]};border-radius:4px;padding:20px;text-align:center;}}
.stat .val{{font-size:40px;font-weight:800;}}.stat .lbl{{font-size:12px;color:{C["silver"]};letter-spacing:.08em;text-transform:uppercase;margin-top:4px;}}
.stat.c .val{{color:{C["blue"]};}}.stat.e .val{{color:{C["orange"]};}}.stat.r .val{{color:{C["red"]};}}
h2{{font-size:24px;font-weight:700;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid {C["text"]};}}
.img-box{{text-align:center;margin:24px 0;}}.img-box img{{max-width:100%;border-radius:4px;border:1px solid {C["border"]};}}
.card{{background:#FFF;border:1px solid {C["border"]};border-radius:2px;padding:14px 18px;margin-bottom:8px;}}
.card.civ{{border-left:4px solid {C["blue"]};}}.card.eee{{border-left:4px solid {C["orange"]};}}.card.cnf{{border-left:4px solid {C["red"]};background:#FEF2F2;}}
.card .title{{font-weight:700;font-size:15px;}}.card.civ .title{{color:{C["blue"]};}}.card.eee .title{{color:{C["orange"]};}}.card.cnf .title{{color:{C["red"]};}}
.card .desc{{font-size:14px;color:{C["muted"]};margin-top:4px;}}.card .meta{{font-size:13px;color:{C["silver"]};margin-top:4px;font-family:monospace;}}
.sev{{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:2px;font-size:12px;font-weight:600;}}
.sev-high{{background:#FEF2F2;color:{C["red"]};}}.sev-mid{{background:#FFF7ED;color:{C["orange"]};}}.sev-low{{background:#F9FAFB;color:{C["silver"]};}}
.footer{{text-align:center;font-size:13px;color:{C["silver"]};margin-top:40px;border-top:1px solid {C["border"]};padding-top:16px;}}
</style></head><body>
<div class="label">ARCHCHECK · REPORT</div>
<div class="band"><div class="band-c"></div><div class="band-e"></div><div class="band-r"></div><div class="band-p"></div></div>
<h1>Review <span>Report</span></h1><div class="subtitle">Automated Building Plan Review · {now}</div>
<div class="stats">
<div class="stat"><div class="val">{len(civil_r)+len(eee_r)}</div><div class="lbl">Total Issues</div></div>
<div class="stat c"><div class="val">{len(civil_r)}</div><div class="lbl">Civil Issues</div></div>
<div class="stat e"><div class="val">{len(eee_r)}</div><div class="lbl">EEE Issues</div></div>
<div class="stat r"><div class="val">{len(conflicts)}</div><div class="lbl">Conflicts</div></div>
</div>
<div class="img-box"><h2>Annotated Floor Plan</h2><img src="data:image/png;base64,{img64}" alt="Floor Plan"></div>
<h2>Civil Code Violations</h2>
{rows(civil_r,'civ') if civil_r else '<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">No civil code violations found.</span></div>'}
<h2>EEE Code Violations</h2>
{rows(eee_r,'eee') if eee_r else '<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">No electrical code violations found.</span></div>'}
<h2>Conflict Zones</h2>
{crow(conflicts) if conflicts else '<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">No conflict zones detected.</span></div>'}
<div class="footer">ArchCheck · Aicher System · AI-Powered Building Code Review · This report is for reference only</div>
</body></html>"""

# ============================================================
# REVIEW ENGINE (runs all checks)
# ============================================================
def run_full_review(bdata):
    """Execute full review: Civil + EEE + Coordinator. Returns results dict."""
    civil_results = []
    for room in bdata.get("rooms", []):
        civil_results.extend(run_rules(CIVIL_RULES, room, "civil"))
    for zone in bdata.get("fire_zones", []):
        civil_results.extend(run_rules(CIVIL_RULES, zone, "civil"))

    eee_results = []
    for room in bdata.get("rooms", []):
        eee_results.extend(run_rules(EEE_RULES, room, "eee"))

    all_issues = []
    loc_map = defaultdict(list)
    for iss in civil_results:
        iss["type"] = "civil"
        loc_map[iss.get("location", "?")].append(iss)
        all_issues.append(iss)
    for iss in eee_results:
        iss["type"] = "eee"
        loc_map[iss.get("location", "?")].append(iss)
        all_issues.append(iss)

    conflicts = []
    for loc, issues in loc_map.items():
        types = set(i["type"] for i in issues)
        if len(types) >= 2:
            ct = [i["title"] for i in issues if i["type"] == "civil"]
            et = [i["title"] for i in issues if i["type"] == "eee"]
            conflicts.append({
                "title": f"Conflict Zone: {loc}",
                "description": f"This zone has {len(ct)}  civil issue(s) and  {len(et)}  electrical issue(s). Coordinate resolution required. Prioritize by severity.",
                "location": loc,
                "related_issues": f"Civil: {', '.join(ct)} | EEE: {', '.join(et)}",
                "type": "conflict",
                "severity": "High",
            })

    return {
        "civil_results": civil_results,
        "eee_results": eee_results,
        "conflicts": conflicts,
        "all_issues": all_issues,
    }

# ============================================================
# MAIN PAGE RENDERING
# ============================================================

# ---- LOADING STATE ----
if st.session_state.review_loading:
    uimg = st.session_state.get("uploaded_image")
    bdata = st.session_state.get("building_data", DEMO_DATA)
    if bdata is None:
        bdata = DEMO_DATA

    if uimg is None:
        st.warning("Please upload a floor plan first.")
        st.session_state.review_loading = False
        if st.button("Back to Upload", width="stretch"):
            st.rerun()
        st.stop()

    rc = len(bdata.get("rooms", []))
    zc = len(bdata.get("fire_zones", []))

    st.markdown('<div class="aicher-label" style="margin-bottom:8px;">ARCHCHECK · ANALYSIS</div>', unsafe_allow_html=True)

    ca, cb = st.columns([1, 2])
    with ca:
        st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
        st.image(uimg)
        st.markdown('</div>', unsafe_allow_html=True)
    with cb:
        st.markdown(
            f'<div style="font-size:36px;font-weight:800;color:{C["text"]};margin-bottom:20px;">'
            f'Agent Review in Progress...</div>',
            unsafe_allow_html=True,
        )

        with st.status("Initializing review engine...", expanded=True) as status:
            time.sleep(0.5)
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["silver"]};">'
                f'SYS | Parsing floor plan, detecting rooms, corridors, exits...</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.4)
            status.update(label=f"Image analysis complete — {rc} rooms, {zc} fire zones detected")

            # Civil Agent
            time.sleep(0.6)
            status.update(label="Civil Agent: Checking building code compliance...")
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["blue"]};">'
                f'CIVIL | Checking evacuation distance → GB 50016 5.5.17</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.3)
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["blue"]};">'
                f'CIVIL | Checking fire zone area → GB 50016 5.3.1</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.3)
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["blue"]};">'
                f'CIVIL | Checking emergency exits → GB 50016 5.5.8</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.3)
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["blue"]};">'
                f'CIVIL | Checking door width → GB 50016 5.5.18</span>',
                unsafe_allow_html=True,
            )

            # EEE Agent
            time.sleep(0.5)
            status.update(label="EEE Agent: Checking electrical code compliance...")
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["orange"]};">'
                f'EEE  | Checking emergency lighting → GB 51309 3.2.1</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.3)
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["orange"]};">'
                f'EEE  | Checking distribution box clearance → GB 50054 4.2.3</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.3)
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["orange"]};">'
                f'EEE  | Checking circuit load → GB 50054 3.4</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.3)
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["orange"]};">'
                f'EEE  | Checking outlet spacing → GB 50055 6.0.3</span>',
                unsafe_allow_html=True,
            )

            # Run actual rules
            results = run_full_review(bdata)

            # Coordinator
            time.sleep(0.5)
            status.update(label="Coordinator: Merging results & detecting conflicts...")
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["green"]};">'
                f'COORD | Merging Civil + EEE results, detecting cross-domain conflicts</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.6)

            total = len(results["all_issues"])
            n_conflicts = len(results["conflicts"])
            status.update(
                label=f"Review complete — {total} issues, {n_conflicts} conflicts",
                state="complete",
            )
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["green"]};">'
                f'COORD | Report generated: {total} issues ({len(results["civil_results"])} civil, '
                f'{len(results["eee_results"])} electrical), {n_conflicts} conflicts</span>',
                unsafe_allow_html=True,
            )

        time.sleep(0.6)

    # Store results — then navigate to results page
    st.session_state.civil_results = results["civil_results"]
    st.session_state.eee_results = results["eee_results"]
    st.session_state.conflicts = results["conflicts"]
    st.session_state.all_issues = results["all_issues"]
    st.session_state.review_loading = False
    st.session_state.demo_mode = True if st.session_state.get("demo_mode") else False
    st.session_state.page = "results"
    st.rerun()

# ---- UPLOAD PAGE (default) ----
elif st.session_state.page == "upload":
    # Hero section
    st.markdown(
        '<div class="aicher-label" style="margin-bottom:8px;">ARCHCHECK · PLATFORM</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="aicher-band">'
        f'<div class="band-civil"></div><div class="band-eee"></div>'
        f'<div class="band-risk"></div><div class="band-pass"></div></div>',
        unsafe_allow_html=True,
    )

    # Title
    st.markdown(f"""<div style="max-width:860px;margin-bottom:8px;">
    <div style="font-size:56px;font-weight:800;line-height:1.15;color:{C["text"]};">
    Upload floor plans,<br>AI <span style="color:{C["blue"]};">automated review</span> for compliance.
    </div>
    <div style="margin-top:16px;font-size:18px;color:{C["muted"]};font-weight:300;line-height:1.5;">
    Multi-agent collaborative platform for automated building code review — covering fire safety and electrical compliance
    </div>
    </div>""", unsafe_allow_html=True)

    # Agent badges
    st.markdown(f"""<div style="display:flex;gap:28px;margin:24px 0 8px 0;">
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["blue"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">Civil Agent · Fire Safety</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["orange"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">EEE Agent · Electrical Safety</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["red"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">Coordinator · Conflict Resolution</span>
    </div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    # Feature highlights
    f1, f2, f3, f4 = st.columns(4)
    features = [
        ("📐", C["blue"], "Fire Safety Review", "Evacuation distance · Fire zones\nEmergency exits · Door width\nBased on GB 50016 series"),
        ("⚡", C["orange"], "Electrical Safety Review", "Emergency lighting · Water clearance\nCircuit load · Outlet spacing\nBased on GB 51309 / 50054"),
        ("🔗", C["red"], "Conflict Detection", "Cross-discipline issue merging\nConflict zone identification\nCoordinated resolution suggestions"),
        ("📄", C["green"], "One-Click Export", "Annotated floor plan\nHTML format report\nReady for review archiving"),
    ]
    for col, (icon, color, title, desc) in zip([f1, f2, f3, f4], features):
        with col:
            st.markdown(f"""<div class="aicher-card">
            <div class="aicher-feature-icon" style="background:{color}15;">{icon}</div>
            <div style="font-weight:700;font-size:16px;color:{C["text"]};margin-bottom:6px;">{title}</div>
            <div style="font-size:13px;color:{C["muted"]};line-height:1.6;white-space:pre-line;">{desc}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    # Upload + Data columns
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown(
            f'<div style="font-size:17px;font-weight:700;color:{C["text"]};margin-bottom:10px;">'
            f'Upload Floor Plan</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="font-size:14px;color:{C["muted"]};margin-bottom:8px;">'
            f'Supported formats: PNG, JPG, JPEG, PDF. Max size: 20MB.</p>',
            unsafe_allow_html=True,
        )
        uf = st.file_uploader(
            "Drag and drop your floor plan here",
            type=["png", "jpg", "jpeg", "pdf"],
            key="fu",
            label_visibility="collapsed",
        )
        if uf is not None:
            img = Image.open(uf)
            st.session_state.uploaded_image = img
            st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
            st.image(img)
            st.markdown('</div>', unsafe_allow_html=True)

        # Demo button
        st.markdown(
            f'<div style="font-size:13px;color:{C["silver"]};margin:12px 0;text-align:center;">'
            f'— or —</div>',
            unsafe_allow_html=True,
        )
        if st.button("Quick Demo (Load Sample Building)", width="stretch"):
            demo_path = OUTPUT / "demo_architect_plan.png"
            if demo_path.exists():
                st.session_state.uploaded_image = Image.open(demo_path)
            else:
                st.session_state.uploaded_image = generate_sample_image()
            st.session_state.building_data = DEMO_DATA
            st.session_state.review_loading = True
            st.rerun()

    with c2:
        st.markdown(
            f'<div style="font-size:17px;font-weight:700;color:{C["text"]};margin-bottom:10px;">'
            f'Building Data Parameters</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="font-size:14px;color:{C["muted"]};margin-bottom:8px;">'
            f'Edit room and fire zone parameters. These values are used during code compliance checking.</p>',
            unsafe_allow_html=True,
        )
        with st.expander("Edit Room Parameters", expanded=False):
            st.caption("Modify parameters below, then click Save. The review engine will use the updated values.")
            bd = st.session_state.get("building_data") or DEMO_DATA
            updated_rooms = []
            for room in bd.get("rooms", []):
                rid = room["id"]
                st.markdown(
                    f'<span style="font-weight:700;font-size:15px;">{room["name"]}</span> '
                    f'<span style="color:{C["silver"]};font-size:13px;">({room["type"]})</span>',
                    unsafe_allow_html=True,
                )
                a1, a2, a3, a4 = st.columns(4)
                area = a1.number_input("Area (m²)", value=float(room.get("room_area_sqm", 0)), key=f"{rid}_a", step=5.0)
                exits = a2.number_input("Exits", value=int(room.get("exit_count", 1)), key=f"{rid}_x", min_value=0, max_value=4)
                corr = a3.number_input("Corridor (m)", value=float(room.get("corridor_length_m", 0)), key=f"{rid}_c", step=1.0)
                light = a4.checkbox("Emerg. Light", value=bool(room.get("has_emergency_light", False)), key=f"{rid}_l")
                b1, b2, b3, b4 = st.columns(4)
                water = b1.number_input("Dist-Water (m)", value=float(room.get("dist_to_water_m", 5.0)), key=f"{rid}_w", step=0.1)
                circuit = b2.number_input("Load (A)", value=float(room.get("circuit_load_a", 10)), key=f"{rid}_ld", step=1.0)
                outlet = b3.number_input("Outlet Spacing (m)", value=float(room.get("outlet_spacing_m", 5.0)), key=f"{rid}_o", step=0.5)
                door = b4.number_input("Door Width (m)", value=float(room.get("door_width_m", 1.0)), key=f"{rid}_d", step=0.1)
                updated_rooms.append({
                    "id": rid, "name": room["name"], "type": room["type"],
                    "room_area_sqm": area, "exit_count": exits, "corridor_length_m": corr,
                    "door_width_m": door, "has_emergency_light": light,
                    "dist_to_water_m": water, "circuit_load_a": circuit, "outlet_spacing_m": outlet,
                })
                st.markdown("---")

            st.markdown('<span style="font-weight:700;font-size:15px;">Fire Zones</span>', unsafe_allow_html=True)
            updated_zones = []
            for zone in bd.get("fire_zones", []):
                za = st.number_input(
                    f"{zone['name']} Area (m²)",
                    value=float(zone.get("fire_zone_area_sqm", 0)),
                    key=f"{zone['id']}_z",
                    step=50.0,
                )
                updated_zones.append({
                    "id": zone["id"], "name": zone["name"],
                    "fire_zone_area_sqm": za, "rooms": zone["rooms"],
                })

            if st.button("Save Parameters", width="stretch"):
                st.session_state.building_data = {"rooms": updated_rooms, "fire_zones": updated_zones}
                st.success("Parameters saved successfully!")

    # Start Review button
    if st.session_state.uploaded_image is not None:
        st.markdown("---")
        sc1, sc2, sc3 = st.columns([1, 2, 1])
        with sc2:
            if st.button("Start Review", type="primary", width="stretch"):
                if st.session_state.building_data is None:
                    st.session_state.building_data = DEMO_DATA
                st.session_state.review_loading = True
                st.rerun()

    # Footer hint
    if st.session_state.uploaded_image is None:
        st.markdown(
            f'<div style="text-align:center;margin-top:32px;padding:24px;color:{C["silver"]};font-size:14px;">'
            f'Upload a floor plan or click "Quick Demo" to get started</div>',
            unsafe_allow_html=True,
        )

# ---- RESULTS PAGE ----
elif st.session_state.page == "results":
    uimg = st.session_state.get("uploaded_image")
    civil_r = st.session_state.get("civil_results", [])
    eee_r = st.session_state.get("eee_results", [])
    conflicts = st.session_state.get("conflicts", [])
    all_issues = st.session_state.get("all_issues", [])
    bdata = st.session_state.get("building_data") or DEMO_DATA

    if uimg is None:
        st.warning("No review results found. Please upload a floor plan and start a review first.")
        if st.button("Back to Upload", width="stretch"):
            st.session_state.page = "upload"
            st.rerun()
        st.stop()

    annotated = annotate_image(uimg, all_issues)
    correction = generate_correction_image(uimg, civil_r, eee_r, conflicts, bdata)

    # Save output images
    OUTPUT.mkdir(parents=True, exist_ok=True)
    annotated.save(OUTPUT / "review_annotated.png")
    correction.save(OUTPUT / "correction_plan.png")

    st.markdown('<div class="aicher-label" style="margin-bottom:8px;">ARCHCHECK · REVIEW RESULTS</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:40px;font-weight:800;color:{C["text"]};">Review Results Report</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:16px;color:{C["muted"]};margin-bottom:20px;">Automated building code compliance review — Civil + EEE + Coordinator</div>', unsafe_allow_html=True)

    # Severity counts
    high = sum(1 for i in all_issues if i.get("severity") == "High")
    mid = sum(1 for i in all_issues if i.get("severity") == "Medium")
    low = sum(1 for i in all_issues if i.get("severity") == "Low")

    s1, s2, s3, s4, s5 = st.columns(5)
    with s1:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{len(all_issues)}</div><div class="label">Total Issues</div></div>', unsafe_allow_html=True)
    with s2:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{len(civil_r)}</div><div class="label">Civil Issues</div></div>', unsafe_allow_html=True)
    with s3:
        st.markdown(f'<div class="aicher-stat orange"><div class="value">{len(eee_r)}</div><div class="label">EEE Issues</div></div>', unsafe_allow_html=True)
    with s4:
        st.markdown(f'<div class="aicher-stat red"><div class="value">{len(conflicts)}</div><div class="label">Conflicts</div></div>', unsafe_allow_html=True)
    with s5:
        st.markdown(f'<div class="aicher-stat green"><div class="value">{high}</div><div class="label">High Severity</div></div>', unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    # Before / After comparison
    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin-bottom:4px;">Before / After — Violation Detection & Correction Suggestions</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:14px;color:{C["muted"]};margin-bottom:16px;">Left: original plan with violations marked in red/orange. Right: correction plan with suggested fixes in green.</div>', unsafe_allow_html=True)

    bc1, bc2 = st.columns(2)
    with bc1:
        st.markdown(f'<div style="font-weight:700;font-size:16px;color:{C["red"]};margin-bottom:6px;">BEFORE — Detected Violations</div>', unsafe_allow_html=True)
        st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
        st.image(annotated, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption(f"Red/orange/blue markers indicate code violations found during automated review")
    with bc2:
        st.markdown(f'<div style="font-weight:700;font-size:16px;color:{C["green"]};margin-bottom:6px;">AFTER — Suggested Corrections</div>', unsafe_allow_html=True)
        st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
        st.image(correction, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption(f"Green markers show recommended fixes — new exits, relocated panels, added fixtures")

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    # Detailed issues in tabs
    t1, t2, t3 = st.tabs([
        f"Civil Issues ({len(civil_r)})",
        f"EEE Issues ({len(eee_r)})",
        f"Conflicts ({len(conflicts)})",
    ])

    def render_issue_cards(issues, css_class):
        if not issues:
            st.success("No issues found in this category.")
            return
        for i, iss in enumerate(issues, 1):
            sev = iss.get("severity", "Medium")
            sev_color = {"High": C["red"], "Medium": C["orange"], "Low": C["silver"]}.get(sev, C["silver"])
            st.markdown(f'''<div class="issue-card {css_class}">
            <div style="font-weight:700;font-size:15px;">{i}. {iss["title"]}<span style="display:inline-block;margin-left:8px;padding:1px 8px;border-radius:2px;font-size:12px;font-weight:600;background:{sev_color}18;color:{sev_color};">{sev}</span></div>
            <div style="font-size:14px;color:{C["muted"]};margin-top:4px;">{iss.get("description","")}</div>
            <div style="font-size:13px;color:{C["silver"]};margin-top:4px;font-family:monospace;">LOC: {iss.get("location","-")} | REF: {iss.get("code_ref","-")}</div>
            </div>''', unsafe_allow_html=True)

    with t1:
        render_issue_cards(civil_r, "civil")
    with t2:
        render_issue_cards(eee_r, "eee")
    with t3:
        if conflicts:
            for i, c in enumerate(conflicts, 1):
                st.markdown(f'''<div class="issue-card conflict">
                <div style="font-weight:700;font-size:15px;">{i}. {c["title"]}<span style="display:inline-block;margin-left:8px;padding:1px 8px;border-radius:2px;font-size:12px;font-weight:600;background:{C["red"]}18;color:{C["red"]};">PRIORITY</span></div>
                <div style="font-size:14px;color:{C["muted"]};margin-top:4px;">{c.get("description","")}</div>
                <div style="font-size:13px;color:{C["silver"]};margin-top:4px;font-family:monospace;">LOC: {c.get("location","-")} | {c.get("related_issues","")}</div>
                </div>''', unsafe_allow_html=True)
        else:
            st.success("No conflict zones detected between civil and electrical domains.")

    # Downloads section
    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["text"]};margin-bottom:12px;">Export Results</div>', unsafe_allow_html=True)

    dc1, dc2, dc3, dc4 = st.columns(4)
    with dc1:
        buf_a = io.BytesIO()
        annotated.save(buf_a, format="PNG")
        st.download_button("Download Annotated Plan", data=buf_a.getvalue(), file_name="review_annotated.png", mime="image/png", width="stretch")
    with dc2:
        buf_c = io.BytesIO()
        correction.save(buf_c, format="PNG")
        st.download_button("Download Correction Plan", data=buf_c.getvalue(), file_name="correction_plan.png", mime="image/png", width="stretch")
    with dc3:
        report_html = generate_report(uimg, all_issues, civil_r, eee_r, conflicts)
        st.download_button("Download HTML Report", data=report_html, file_name="archcheck_report.html", mime="text/html", width="stretch")
    with dc4:
        if st.button("New Review", width="stretch"):
            st.session_state.page = "upload"
            st.session_state.uploaded_image = None
            st.session_state.civil_results = []
            st.session_state.eee_results = []
            st.session_state.conflicts = []
            st.session_state.all_issues = []
            st.rerun()

# ---- ARCHITECTURE PAGE ----
elif st.session_state.page == "architecture":
    st.markdown('<div class="aicher-label" style="margin-bottom:8px;">ARCHCHECK · ARCHITECTURE</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:40px;font-weight:800;color:{C["text"]};">Platform Architecture</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:16px;color:{C["muted"]};margin-bottom:24px;">Multi-Agent collaborative architecture for automated building code compliance review</div>', unsafe_allow_html=True)

    # Agent cards
    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin-bottom:12px;">Multi-Agent System</div>', unsafe_allow_html=True)

    ag1, ag2, ag3 = st.columns(3)
    with ag1:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["blue"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F3D7;</div>
        <div style="font-weight:700;font-size:18px;color:{C["blue"]};">Civil Agent</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:4px;">Building Code Review</div>
        <div style="font-size:13px;color:{C["silver"]};margin-top:14px;line-height:1.7;">Evacuation distance check<br>Fire zone area verification<br>Emergency exit count<br>Door width compliance</div>
        <div style="margin-top:14px;padding:4px 10px;display:inline-block;background:{C["blue"]}12;border-radius:2px;font-size:12px;color:{C["blue"]};font-family:monospace;">GB 50016 Series</div>
        </div>''', unsafe_allow_html=True)
    with ag2:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["orange"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">⚡</div>
        <div style="font-weight:700;font-size:18px;color:{C["orange"]};">EEE Agent</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:4px;">Electrical Safety Review</div>
        <div style="font-size:13px;color:{C["silver"]};margin-top:14px;line-height:1.7;">Emergency lighting check<br>Water clearance distance<br>Circuit load verification<br>Outlet spacing compliance</div>
        <div style="margin-top:14px;padding:4px 10px;display:inline-block;background:{C["orange"]}12;border-radius:2px;font-size:12px;color:{C["orange"]};font-family:monospace;">GB 51309 / 50054 / 50055</div>
        </div>''', unsafe_allow_html=True)
    with ag3:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["red"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F517;</div>
        <div style="font-weight:700;font-size:18px;color:{C["red"]};">Coordinator</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:4px;">Conflict Detection & Merge</div>
        <div style="font-size:13px;color:{C["silver"]};margin-top:14px;line-height:1.7;">Cross-domain issue merge<br>Conflict zone identification<br>Priority-based resolution<br>Unified report generation</div>
        <div style="margin-top:14px;padding:4px 10px;display:inline-block;background:{C["red"]}12;border-radius:2px;font-size:12px;color:{C["red"]};font-family:monospace;">Rule Engine Core</div>
        </div>''', unsafe_allow_html=True)

    # Review pipeline
    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin:32px 0 12px;">Review Pipeline</div>', unsafe_allow_html=True)

    f1, f2, f3, f4, f5 = st.columns([2, 0.3, 2, 0.3, 2])
    with f1:
        st.markdown(f'<div class="flow-node" style="background:{C["blue"]}12;color:{C["blue"]};border:1px solid {C["blue"]}30;">1. Upload Floor Plan<br><span style="font-weight:400;font-size:12px;">PNG / JPG / PDF</span></div>', unsafe_allow_html=True)
    with f2:
        st.markdown(f'<div style="font-size:28px;color:{C["silver"]};text-align:center;padding-top:8px;">→</div>', unsafe_allow_html=True)
    with f3:
        st.markdown(f'<div class="flow-node" style="background:{C["text"]}08;color:{C["text"]};border:1px solid {C["text"]}20;">2. Multi-Agent Review<br><span style="font-weight:400;font-size:12px;">Civil + EEE + Coordinator</span></div>', unsafe_allow_html=True)
    with f4:
        st.markdown(f'<div style="font-size:28px;color:{C["silver"]};text-align:center;padding-top:8px;">→</div>', unsafe_allow_html=True)
    with f5:
        st.markdown(f'<div class="flow-node" style="background:{C["green"]}12;color:{C["green"]};border:1px solid {C["green"]}30;">3. Report & Correction<br><span style="font-weight:400;font-size:12px;">Annotated Images + HTML Report</span></div>', unsafe_allow_html=True)

    # Technology stack
    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin:32px 0 12px;">Technology Stack</div>', unsafe_allow_html=True)

    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    with tc1:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F40D;</div><div style="font-weight:700;font-size:15px;">Python 3</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">Core Engine</div></div>', unsafe_allow_html=True)
    with tc2:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F4CA;</div><div style="font-weight:700;font-size:15px;">Streamlit</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">Web Interface</div></div>', unsafe_allow_html=True)
    with tc3:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F5BC;</div><div style="font-weight:700;font-size:15px;">Pillow (PIL)</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">Image Processing</div></div>', unsafe_allow_html=True)
    with tc4:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F4CB;</div><div style="font-weight:700;font-size:15px;">JSON Rules</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">Rule Engine</div></div>', unsafe_allow_html=True)
    with tc5:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F4C4;</div><div style="font-weight:700;font-size:15px;">python-pptx</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">PPT Export</div></div>', unsafe_allow_html=True)

    # Development roadmap
    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin:32px 0 12px;">Development Roadmap</div>', unsafe_allow_html=True)

    rm1, rm2, rm3 = st.columns(3)
    with rm1:
        st.markdown(f'''<div class="roadmap-card">
        <div style="font-size:12px;letter-spacing:0.12em;font-weight:700;color:{C["blue"]};margin-bottom:6px;">PHASE 1 · COMPLETE</div>
        <div style="font-weight:700;font-size:16px;color:{C["text"]};">Core Review Engine</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;">JSON-driven rules engine with 8 operators, multi-agent framework with Civil + EEE + Coordinator, image annotation with violation markers, HTML report export with inline CSS</div>
        </div>''', unsafe_allow_html=True)
    with rm2:
        st.markdown(f'''<div class="roadmap-card">
        <div style="font-size:12px;letter-spacing:0.12em;font-weight:700;color:{C["orange"]};margin-bottom:6px;">PHASE 2 · PLANNED</div>
        <div style="font-weight:700;font-size:16px;color:{C["text"]};">AI-Powered Analysis</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;">Computer vision for automated room/zone detection from floor plans, ML-based violation severity prediction, natural language rule authoring, intelligent correction suggestion generation</div>
        </div>''', unsafe_allow_html=True)
    with rm3:
        st.markdown(f'''<div class="roadmap-card">
        <div style="font-size:12px;letter-spacing:0.12em;font-weight:700;color:{C["silver"]};margin-bottom:6px;">PHASE 3 · FUTURE</div>
        <div style="font-weight:700;font-size:16px;color:{C["text"]};">Enterprise Platform</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;">Multi-user collaboration with role-based access, BIM/IFC file format support, real-time regulatory updates, cloud deployment with project management dashboard, API integration for third-party tools</div>
        </div>''', unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)
    if st.button("Back to Upload", width="stretch"):
        st.session_state.page = "upload"
        st.rerun()
