"""
Generate two floor plan images for ArchCheck demo:
  1. Architect's CAD-style submission — clean architectural drawing
  2. ArchCheck AI review annotated — violation markers + Aicher color overlay

Output: output/demo_architect_plan.png + output/demo_review_annotated.png
"""

import json
import math
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# CONSTANTS
# ============================================================
SCALE = 48          # pixels per meter (1:21 scale, fits A4-ish layout)
MARGIN = 90
CANVAS_W = 1600
CANVAS_H = 1080

# Aicher design tokens
C = {
    "blue":   ( 91,163,217), "orange": (240,146, 53),
    "red":    (211, 47, 47), "green":  (124,179, 66),
    "silver": (155,163,171), "text":   ( 31, 36, 41),
    "muted":  (107,116,128), "border": (237,240,243),
    "bg":     (250,251,252),
}

# Architectural palette
WALL_CUT    = ( 25, 30, 40)   # walls in section (dark)
WALL_LINE   = ( 60, 65, 75)   # wall outlines
ROOM_FILL   = (248,249,250)   # room interior fill
GRID_LINE   = (238,241,244)   # background grid
DIM_LINE    = (170,175,185)   # dimension lines
TITLE_BG    = ( 25, 30, 40)   # title bar background
WHITE       = (255,255,255)
BLACK       = ( 20, 25, 35)

# Room type → fill colour (for annotated plan)
TYPE_FILL = {
    "办公室":  (238,244,250),
    "会议室":  (240,245,250),
    "走廊":    (230,238,248),
    "楼梯间":  (252,246,232),
    "设备间":  (252,238,238),
}

# ============================================================
# FONTS
# ============================================================
def _load_font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "arial.ttf",
    ]
    for fp in candidates:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()

FONT_TITLE   = _load_font(22, True)
FONT_HEADER  = _load_font(16, True)
FONT_ROOM    = _load_font(15, True)
FONT_LABEL   = _load_font(12)
FONT_SMALL   = _load_font(10)
FONT_TINY    = _load_font(9)
FONT_MONO    = _load_font(11)
FONT_DIM     = _load_font(13)
FONT_CALLOUT = _load_font(11, True)

# ============================================================
# BUILDING GEOMETRY (in metres, origin at building interior top-left)
# ============================================================
EXT_WALL = 0.30   # exterior wall thickness (m)
INT_WALL = 0.20   # interior wall thickness (m)

ROOMS = [
    {
        "id":"R001","name":"办公室A","type":"办公室",
        "x":0.0, "y":0.0, "w":9.6, "h":8.0,
        "area_sqm":85, "exit_count":1, "door_width_m":1.0,
        "doors": [{"wall":"bottom","offset":4.5,"width":1.0,"swing":"right"}],
    },
    {
        "id":"R004","name":"会议室","type":"会议室",
        "x":9.6, "y":0.0, "w":8.2, "h":5.4,
        "area_sqm":120, "exit_count":2, "door_width_m":1.5,
        "doors": [
            {"wall":"bottom","offset":3.8,"width":1.5,"swing":"left"},
            {"wall":"left","offset":2.5,"width":1.5,"swing":"right"},
        ],
    },
    {
        "id":"R005","name":"楼梯间","type":"楼梯间",
        "x":9.6, "y":5.4, "w":4.5, "h":2.6,
        "area_sqm":20, "exit_count":1, "door_width_m":1.1,
        "doors": [{"wall":"bottom","offset":2.0,"width":1.1,"swing":"right"}],
    },
    {
        "id":"R003","name":"配电间","type":"设备间",
        "x":14.1, "y":5.4, "w":3.7, "h":2.6,
        "area_sqm":12, "exit_count":1, "door_width_m":0.9,
        "doors": [{"wall":"bottom","offset":1.6,"width":0.9,"swing":"left"}],
    },
    {
        "id":"R002","name":"走廊","type":"走廊",
        "x":0.0, "y":8.0, "w":17.8, "h":2.2,
        "area_sqm":42, "exit_count":2, "door_width_m":1.2,
        "corridor_length_m":42,
        "doors": [],
    },
]

FIRE_ZONES = [
    {"id":"FZ001","name":"防火分区一","x":-0.15,"y":-0.15,"w":18.1,"h":8.45,
     "rooms":["R001","R002","R003"],"area_sqm":2800},
    {"id":"FZ002","name":"防火分区二","x":9.45,"y":-0.15,"w":8.5,"h":8.3,
     "rooms":["R004","R005"],"area_sqm":140},
]

# Origin of building exterior on canvas (top-left of ext wall outer face)
BUILD_X = 110
BUILD_Y = 185

def m2px(m):
    return int(round(m * SCALE))

def room_rect(room):
    """Pixel rect of room interior (inside walls)."""
    bx = BUILD_X + m2px(EXT_WALL)
    by = BUILD_Y + m2px(EXT_WALL)
    x1 = bx + m2px(room["x"])
    y1 = by + m2px(room["y"])
    x2 = x1 + m2px(room["w"])
    y2 = y1 + m2px(room["h"])
    return (x1, y1, x2, y2)

def room_center(room):
    r = room_rect(room)
    return ((r[0]+r[2])//2, (r[1]+r[3])//2)

def building_outer_rect():
    """Pixel rect of entire building (exterior wall outer face)."""
    total_w = 0
    for r in ROOMS:
        total_w = max(total_w, r["x"] + r["w"])
    total_h = 0
    for r in ROOMS:
        total_h = max(total_h, r["y"] + r["h"])
    bw = m2px(total_w + 2 * EXT_WALL)
    bh = m2px(total_h + 2 * EXT_WALL)
    return (BUILD_X, BUILD_Y, BUILD_X + bw, BUILD_Y + bh)

# ============================================================
# VIOLATION DATA (coordinates on plan for marker placement)
# ============================================================
VIOLATIONS = [
    {
        "id":1, "type":"civil", "severity":"高",
        "title":"疏散走廊过长",
        "detail":"走廊长度 42m > 规范 30m，需增设避难走道或重新规划疏散路线",
        "code":"GB 50016 §5.5.17",
        "at":(660, 598),   # pixel position on canvas (centre of corridor)
    },
    {
        "id":2, "type":"civil", "severity":"高",
        "title":"防火分区面积超限",
        "detail":"防火分区一面积 2800m² > 规范 2500m²，需增加防火分隔",
        "code":"GB 50016 §5.3.1",
        "at":(850, 230),
    },
    {
        "id":3, "type":"civil", "severity":"中",
        "title":"安全出口不足",
        "detail":"办公室A 面积 85m² > 50m²，仅有 1 个出口，规范要求 ≥ 2 个",
        "code":"GB 50016 §5.5.8",
        "at":(340, 380),
    },
    {
        "id":4, "type":"eee", "severity":"高",
        "title":"未配置应急照明",
        "detail":"走廊（疏散通道）未安装应急照明设备",
        "code":"GB 51309 §3.2.1",
        "at":(1100, 598),
    },
    {
        "id":5, "type":"eee", "severity":"中",
        "title":"配电箱距水源过近",
        "detail":"配电箱距水源仅 0.8m，规范要求 ≥ 1.5m",
        "code":"GB 50054 §4.2.3",
        "at":(870, 590),
    },
    {
        "id":6, "type":"eee", "severity":"中",
        "title":"回路负荷超限",
        "detail":"配电间回路负荷 20A > 规范 16A，需增设回路",
        "code":"GB 50054 §3.4",
        "at":(840, 538),
    },
    {
        "id":7, "type":"civil", "severity":"低",
        "title":"疏散门宽度不足",
        "detail":"配电间门宽 0.9m = 规范下限，建议加宽至 1.0m",
        "code":"GB 50016 §5.5.18",
        "at":(780, 555),
    },
    {
        "id":8, "type":"eee", "severity":"高",
        "title":"未配置应急照明",
        "detail":"楼梯间未安装应急照明设备",
        "code":"GB 51309 §3.2.1",
        "at":(690, 460),
    },
]

# ============================================================
# HELPER: draw functions shared by both plans
# ============================================================
def draw_grid(draw, w, h):
    for x in range(0, w, 48):
        draw.line([(x, 0), (x, h)], fill=GRID_LINE, width=1)
    for y in range(0, h, 48):
        draw.line([(0, y), (w, y)], fill=GRID_LINE, width=1)

def draw_north_arrow(draw, cx, cy):
    r = 20
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=BLACK, width=2)
    # arrow head
    pts = [(cx, cy-28), (cx-7, cy+6), (cx, cy-4), (cx+7, cy+6)]
    draw.polygon(pts, fill=BLACK)
    draw.text((cx-8, cy-48), "N", fill=BLACK, font=FONT_LABEL)

def draw_scale_bar(draw, x, y):
    """Draw a 0——5——10m scale bar."""
    L = m2px(5)  # 5 metres
    draw.line([(x, y), (x + 2*L, y)], fill=BLACK, width=2)
    draw.line([(x, y-6), (x, y+6)], fill=BLACK, width=2)
    draw.line([(x+L, y-4), (x+L, y+4)], fill=BLACK, width=2)
    draw.line([(x+2*L, y-6), (x+2*L, y+6)], fill=BLACK, width=2)
    draw.text((x-4, y+8), "0", fill=BLACK, font=FONT_SMALL, anchor="ma")
    draw.text((x+L-4, y+8), "5m", fill=BLACK, font=FONT_SMALL, anchor="ma")
    draw.text((x+2*L-4, y+8), "10m", fill=BLACK, font=FONT_SMALL, anchor="ma")

def draw_room_label(draw, room, color=BLACK, font=None):
    if font is None:
        font = FONT_ROOM
    cx, cy = room_center(room)
    # Room name
    draw.text((cx, cy-14), room["name"], fill=color, font=font, anchor="mm")
    # Area below
    area_str = f'{room["area_sqm"]} m²'
    draw.text((cx, cy+8), area_str, fill=C["muted"] if color==BLACK else color, font=FONT_SMALL, anchor="mm")
    # Room type below area
    draw.text((cx, cy+26), room["type"], fill=C["silver"], font=FONT_TINY, anchor="mm")

def draw_door(draw, room, door, wall_thickness=INT_WALL):
    """Draw door opening (gap) + door leaf + swing arc."""
    rr = room_rect(room)
    x1, y1, x2, y2 = rr

    wall = door["wall"]
    offset = m2px(door["offset"])
    half_w = m2px(door["width"]) // 2
    swing = door.get("swing", "right")

    if wall == "bottom":
        cx = x1 + offset
        cy = y2
        gap = [(cx - half_w, cy), (cx + half_w, cy)]
        # door leaf
        if swing == "right":
            leaf_end = (cx + m2px(door["width"]), cy - m2px(door["width"]))
        else:
            leaf_end = (cx - m2px(door["width"]), cy - m2px(door["width"]))
        arc_bbox = [cx - m2px(door["width"]), cy - m2px(door["width"]),
                     cx + m2px(door["width"]), cy + m2px(door["width"])]
        arc_start = 0 if swing == "right" else 90
        arc_end = 90 if swing == "right" else 0
    elif wall == "top":
        cx = x1 + offset
        cy = y1
        gap = [(cx - half_w, cy), (cx + half_w, cy)]
        if swing == "right":
            leaf_end = (cx + m2px(door["width"]), cy + m2px(door["width"]))
        else:
            leaf_end = (cx - m2px(door["width"]), cy + m2px(door["width"]))
        arc_bbox = [cx - m2px(door["width"]), cy - m2px(door["width"]),
                     cx + m2px(door["width"]), cy + m2px(door["width"])]
        arc_start = 270 if swing == "right" else 180
        arc_end = 180 if swing == "right" else 270
    elif wall == "left":
        cx = x1
        cy = y1 + offset
        gap = [(cx, cy - half_w), (cx, cy + half_w)]
        if swing == "right":
            leaf_end = (cx + m2px(door["width"]), cy - m2px(door["width"]))
        else:
            leaf_end = (cx + m2px(door["width"]), cy + m2px(door["width"]))
        arc_bbox = [cx - m2px(door["width"]), cy - m2px(door["width"]),
                     cx + m2px(door["width"]), cy + m2px(door["width"])]
        arc_start = 180 if swing == "right" else 90
        arc_end = 90 if swing == "right" else 180
    elif wall == "right":
        cx = x2
        cy = y1 + offset
        gap = [(cx, cy - half_w), (cx, cy + half_w)]
        if swing == "right":
            leaf_end = (cx - m2px(door["width"]), cy + m2px(door["width"]))
        else:
            leaf_end = (cx - m2px(door["width"]), cy - m2px(door["width"]))
        arc_bbox = [cx - m2px(door["width"]), cy - m2px(door["width"]),
                     cx + m2px(door["width"]), cy + m2px(door["width"])]
        arc_start = 0 if swing == "right" else 270
        arc_end = 270 if swing == "right" else 0

    return (gap, (cx, cy), leaf_end, arc_bbox, arc_start, arc_end)

def draw_exterior_wall_outline(draw):
    """Thick outline around the entire building perimeter."""
    outer = building_outer_rect()
    draw.rectangle(outer, outline=WALL_CUT, width=6)

def draw_interior_walls(draw, color=WALL_LINE, width=2):
    """Draw wall lines between rooms (interior partitions)."""
    drawn = set()
    for room in ROOMS:
        rr = room_rect(room)
        x1, y1, x2, y2 = rr
        # Each room's 4 edges
        edges = [
            ("top",    (x1, y1, x2, y1)),
            ("bottom", (x1, y2, x2, y2)),
            ("left",   (x1, y1, x1, y2)),
            ("right",  (x2, y1, x2, y2)),
        ]
        for wall_name, (sx, sy, ex, ey) in edges:
            # Skip if this edge is on the building perimeter
            outer = building_outer_rect()
            outer_x1, outer_y1, outer_x2, outer_y2 = outer
            wall_margin = m2px(EXT_WALL)
            on_perimeter = False
            if wall_name == "top" and sy <= outer_y1 + wall_margin + 2:
                on_perimeter = True
            if wall_name == "bottom" and sy >= outer_y2 - wall_margin - 2:
                on_perimeter = True
            if wall_name == "left" and sx <= outer_x1 + wall_margin + 2:
                on_perimeter = True
            if wall_name == "right" and sx >= outer_x2 - wall_margin - 2:
                on_perimeter = True

            if not on_perimeter:
                # Don't draw interior walls that are also exterior (avoid double-draw)
                # Check if this edge is adjacent to corridor (special case)
                draw.line([(sx, sy), (ex, ey)], fill=color, width=width)

def draw_dimension_line(draw, x1, y1, x2, y2, label, offset=24):
    """External dimension line with tick marks."""
    # Main line
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx*dx + dy*dy)

    # Ticks at ends
    tick_len = 10
    # perpendicular direction (simplified — assume horizontal or vertical)
    if abs(dx) > abs(dy):  # horizontal
        draw.line([(x1, y1), (x2, y2)], fill=DIM_LINE, width=1)
        draw.line([(x1, y1-tick_len), (x1, y1+tick_len)], fill=DIM_LINE, width=1)
        draw.line([(x2, y2-tick_len), (x2, y2+tick_len)], fill=DIM_LINE, width=1)
        # label at centre
        cx = (x1+x2)//2
        draw.text((cx, y1 + offset), label, fill=C["muted"], font=FONT_SMALL, anchor="mt")
    else:  # vertical
        draw.line([(x1, y1), (x2, y2)], fill=DIM_LINE, width=1)
        draw.line([(x1-tick_len, y1), (x1+tick_len, y1)], fill=DIM_LINE, width=1)
        draw.line([(x2-tick_len, y2), (x2+tick_len, y2)], fill=DIM_LINE, width=1)
        cx = (x1+x2)//2
        draw.text((x1 - offset, (y1+y2)//2), label, fill=C["muted"], font=FONT_SMALL, anchor="mm")

def draw_title_block(draw, x, y, w, h, title_text, subtitle, extra_lines=None):
    """Professional title block (bottom-right corner)."""
    draw.rectangle([x, y, x+w, y+h], fill=TITLE_BG)
    draw.text((x+16, y+14), title_text, fill=WHITE, font=FONT_HEADER)
    draw.text((x+16, y+40), subtitle, fill=C["silver"], font=FONT_SMALL)
    yy = y + 58
    if extra_lines:
        for line in extra_lines:
            draw.text((x+16, yy), line, fill=C["silver"], font=FONT_TINY)
            yy += 16
    # Separator line near top
    draw.line([(x+16, y+36), (x+w-16, y+36)], fill=C["muted"], width=1)

def draw_violation_marker(draw, v, number):
    """Red circle + number + leader line + callout box."""
    ax, ay = v["at"]
    sev_color = C["red"] if v["severity"] == "高" else (C["orange"] if v["severity"] == "中" else C["silver"])
    r = 14

    # Outer glow
    draw.ellipse([ax-r-3, ay-r-3, ax+r+3, ay+r+3], outline=sev_color, width=1)
    # Circle
    draw.ellipse([ax-r, ay-r, ax+r, ay+r], outline=sev_color, width=3)
    draw.ellipse([ax-r+3, ay-r+3, ax+r-3, ay+r-3], fill=(255,255,255))
    # Number
    draw.text((ax, ay-1), str(number), fill=sev_color, font=FONT_CALLOUT, anchor="mm")

    # Callout text to the side
    tx = ax + 22
    ty = ay - 10
    text = v["title"]
    bbox = draw.textbbox((0,0), text, font=FONT_SMALL)
    tw = bbox[2] - bbox[0]
    # background pill
    pad = 4
    draw.rectangle([tx-pad, ty-pad, tx+tw+pad, ty+14+pad], fill=WHITE, outline=sev_color, width=1)
    draw.text((tx, ty), text, fill=sev_color, font=FONT_SMALL)
    # connecting line
    draw.line([(ax+r, ay), (tx-2, ty+7)], fill=sev_color, width=1)

# ============================================================
# IMAGE 1: ARCHITECT'S CLEAN CAD PLAN
# ============================================================
def render_architect_plan():
    W, H = CANVAS_W, CANVAS_H
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img, "RGBA")

    # --- Grid ---
    draw_grid(draw, W, H)

    # --- Room fills ---
    for room in ROOMS:
        rr = room_rect(room)
        draw.rectangle(rr, fill=ROOM_FILL, outline=None)

    # --- Exterior wall ---
    outer = building_outer_rect()
    # outer thick line
    draw.rectangle(outer, outline=WALL_CUT, width=6)
    # inner thin line (wall inner face)
    inner_margin = m2px(EXT_WALL)
    inner = (outer[0]+inner_margin, outer[1]+inner_margin,
             outer[2]-inner_margin, outer[3]-inner_margin)
    draw.rectangle(inner, outline=WALL_LINE, width=1)

    # --- Interior walls ---
    # Draw lines between rooms that share a boundary
    for room in ROOMS:
        rr = room_rect(room)
        x1, y1, x2, y2 = rr
        # Draw all 4 edges for each room (creates interior wall lines)
        # But only where the room doesn't align with exterior
        outer_m = m2px(EXT_WALL)
        o_adj = (outer[0]+outer_m, outer[1]+outer_m, outer[2]-outer_m, outer[3]-outer_m)

        # Top edge — if not aligned with building top
        if y1 > o_adj[1] + 2:
            draw.line([(x1, y1), (x2, y1)], fill=WALL_LINE, width=2)
        # Bottom edge — if not aligned with building bottom
        if y2 < o_adj[3] - 2:
            draw.line([(x1, y2), (x2, y2)], fill=WALL_LINE, width=2)
        # Left edge
        if x1 > o_adj[0] + 2:
            draw.line([(x1, y1), (x1, y2)], fill=WALL_LINE, width=2)
        # Right edge
        if x2 < o_adj[2] - 2:
            draw.line([(x2, y1), (x2, y2)], fill=WALL_LINE, width=2)

    # --- Doors (white-out wall + draw door symbol) ---
    for room in ROOMS:
        for door in room.get("doors", []):
            gap, hinge, leaf_end, arc_bbox, arc_start, arc_end = draw_door(draw, room, door)
            # White-out the wall gap
            draw.line(gap, fill=WHITE, width=m2px(door["width"])+4)
            # Door leaf (thick line from hinge to leaf_end)
            draw.line([hinge, leaf_end], fill=WALL_LINE, width=2)
            # Swing arc
            draw.arc(arc_bbox, arc_start, arc_end, fill=WALL_LINE, width=2)

    # --- Room labels ---
    for room in ROOMS:
        draw_room_label(draw, room, color=BLACK)

    # --- Fire zone (thin dashed, architectural style) ---
    for fz in FIRE_ZONES:
        bx = BUILD_X + m2px(EXT_WALL)
        by = BUILD_Y + m2px(EXT_WALL)
        fx1 = bx + m2px(fz["x"])
        fy1 = by + m2px(fz["y"])
        fx2 = fx1 + m2px(fz["w"])
        fy2 = fy1 + m2px(fz["h"])
        dash_len = 12
        # top
        for px in range(int(fx1), int(fx2), dash_len*2):
            draw.line([(px, fy1), (min(px+dash_len, fx2), fy1)], fill=C["muted"], width=1)
        # bottom
        for px in range(int(fx1), int(fx2), dash_len*2):
            draw.line([(px, fy2), (min(px+dash_len, fx2), fy2)], fill=C["muted"], width=1)
        # left
        for py in range(int(fy1), int(fy2), dash_len*2):
            draw.line([(fx1, py), (fx1, min(py+dash_len, fy2))], fill=C["muted"], width=1)
        # right
        for py in range(int(fy1), int(fy2), dash_len*2):
            draw.line([(fx2, py), (fx2, min(py+dash_len, fy2))], fill=C["muted"], width=1)
        # label
        fz_cx = (fx1+fx2)//2
        draw.text((fz_cx, fy1-16), f'{fz["name"]}  ({fz["area_sqm"]}m²)', fill=C["muted"], font=FONT_TINY, anchor="mb")

    # --- Dimension lines ---
    # Horizontal: total width
    outer = building_outer_rect()
    dim_y_bottom = outer[3] + 28
    draw_dimension_line(draw, outer[0], dim_y_bottom, outer[2], dim_y_bottom, "17.8m", offset=20)

    # Vertical: total height
    dim_x_left = outer[0] - 40
    draw_dimension_line(draw, dim_x_left, outer[1], dim_x_left, outer[3], "10.2m", offset=-28)

    # --- North arrow ---
    draw_north_arrow(draw, CANVAS_W - 110, BUILD_Y - 20)

    # --- Scale bar ---
    draw_scale_bar(draw, BUILD_X, CANVAS_H - 65)

    # --- Title block ---
    today = datetime.now().strftime("%Y-%m-%d")
    tb_w, tb_h = 340, 100
    draw_title_block(draw, CANVAS_W - MARGIN - tb_w, CANVAS_H - MARGIN - tb_h,
                     tb_w, tb_h,
                     "办公楼 一层平面图",
                     "Office Building — 1st Floor Plan",
                     [f"Scale  1:{round(100/(SCALE/0.48))}  |  Date  {today}",
                      "Drawing No.  A-101  |  Rev.  A"])

    # --- Legend ---
    lx, ly = BUILD_X, CANVAS_H - 120
    draw.rectangle([lx, ly, lx+180, ly+88], fill=WHITE, outline=DIM_LINE, width=1)
    draw.text((lx+8, ly+4), "LEGEND", fill=BLACK, font=FONT_SMALL)
    legend_items = [
        ("办公室", ROOM_FILL), ("走廊", ROOM_FILL),
        ("楼梯间", ROOM_FILL), ("设备间", ROOM_FILL),
    ]
    for i, (lb, fc) in enumerate(legend_items):
        yy = ly + 20 + i * 15
        draw.rectangle([lx+8, yy, lx+22, yy+10], fill=fc, outline=DIM_LINE, width=1)
        draw.text((lx+28, yy-1), lb, fill=C["muted"], font=FONT_TINY)

    # --- Top title bar ---
    draw.rectangle([0, 0, W, 52], fill=TITLE_BG)
    draw.text((MARGIN, 14), "ARCHITECT'S SUBMISSION  —  FLOOR PLAN", fill=WHITE, font=FONT_HEADER)
    draw.text((W-200, 16), f"Sheet: A-101  |  {today}", fill=C["silver"], font=FONT_SMALL)
    # Aicher band below title
    band_y = 52
    band_colors = [(91,163,217), (91,163,217), (240,146,53), (240,146,53), (124,179,66)]
    seg_w = W // len(band_colors)
    for i, bc in enumerate(band_colors):
        draw.rectangle([i*seg_w, band_y, (i+1)*seg_w, band_y+5], fill=bc)

    return img

# ============================================================
# IMAGE 2: ARCHCHECK AI REVIEW ANNOTATED PLAN
# ============================================================
def render_review_annotated():
    W, H = CANVAS_W, CANVAS_H
    img = Image.new("RGBA", (W, H), (*WHITE, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # --- Grid (faint) ---
    draw_grid(draw, W, H)

    # --- Room fills (type-coloured) ---
    for room in ROOMS:
        rr = room_rect(room)
        fc = TYPE_FILL.get(room["type"], ROOM_FILL)
        draw.rectangle(rr, fill=fc, outline=None)

    # --- Exterior wall (lighter for review) ---
    outer = building_outer_rect()
    draw.rectangle(outer, outline=(120,128,140), width=4)
    inner_margin = m2px(EXT_WALL)
    inner = (outer[0]+inner_margin, outer[1]+inner_margin,
             outer[2]-inner_margin, outer[3]-inner_margin)
    draw.rectangle(inner, outline=(180,188,200), width=1)

    # --- Interior walls (light) ---
    for room in ROOMS:
        rr = room_rect(room)
        x1, y1, x2, y2 = rr
        outer_m = m2px(EXT_WALL)
        o_adj = (outer[0]+outer_m, outer[1]+outer_m, outer[2]-outer_m, outer[3]-outer_m)
        if y1 > o_adj[1] + 2:
            draw.line([(x1, y1), (x2, y1)], fill=(180,188,200), width=2)
        if y2 < o_adj[3] - 2:
            draw.line([(x1, y2), (x2, y2)], fill=(180,188,200), width=2)
        if x1 > o_adj[0] + 2:
            draw.line([(x1, y1), (x1, y2)], fill=(180,188,200), width=2)
        if x2 < o_adj[2] - 2:
            draw.line([(x2, y1), (x2, y2)], fill=(180,188,200), width=2)

    # --- Doors ---
    for room in ROOMS:
        for door in room.get("doors", []):
            gap, hinge, leaf_end, arc_bbox, arc_start, arc_end = draw_door(draw, room, door)
            draw.line(gap, fill=WHITE, width=m2px(door["width"])+4)
            draw.line([hinge, leaf_end], fill=(140,148,160), width=2)
            draw.arc(arc_bbox, arc_start, arc_end, fill=(140,148,160), width=2)

    # --- Room labels (muted) ---
    for room in ROOMS:
        draw_room_label(draw, room, color=C["muted"])

    # --- Fire zones (coloured dashed + semi-transparent fill) ---
    fz_colors = {"FZ001": (91,163,217), "FZ002": (240,146,53)}
    for fz in FIRE_ZONES:
        bx = BUILD_X + m2px(EXT_WALL)
        by = BUILD_Y + m2px(EXT_WALL)
        fx1 = bx + m2px(fz["x"])
        fy1 = by + m2px(fz["y"])
        fx2 = fx1 + m2px(fz["w"])
        fy2 = fy1 + m2px(fz["h"])
        fc = fz_colors.get(fz["id"], C["muted"])

        # Semi-transparent fill
        overlay = Image.new("RGBA", img.size, (0,0,0,0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([fx1, fy1, fx2, fy2], fill=(*fc, 18))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img, "RGBA")

        # Dashed border
        dash_len = 14
        for px in range(int(fx1), int(fx2), dash_len*2):
            draw.line([(px, fy1), (min(px+dash_len, fx2), fy1)], fill=fc, width=2)
            draw.line([(px, fy2), (min(px+dash_len, fx2), fy2)], fill=fc, width=2)
        for py in range(int(fy1), int(fy2), dash_len*2):
            draw.line([(fx1, py), (fx1, min(py+dash_len, fy2))], fill=fc, width=2)
            draw.line([(fx2, py), (fx2, min(py+dash_len, fy2))], fill=fc, width=2)

        # Label
        fz_cx = (fx1+fx2)//2
        draw.text((fz_cx, fy1-16), f'{fz["name"]}  ({fz["area_sqm"]}m²)', fill=fc, font=FONT_TINY, anchor="mb")

    # --- Violation markers ---
    for v in VIOLATIONS:
        draw_violation_marker(draw, v, v["id"])

    # --- Legend (violations) ---
    lx, ly = BUILD_X - 10, CANVAS_H - 170
    legend_w, legend_h = 260, 144
    draw.rectangle([lx, ly, lx+legend_w, ly+legend_h], fill=WHITE, outline=C["border"], width=1)
    draw.text((lx+10, ly+6), "VIOLATION LEGEND", fill=C["text"], font=FONT_SMALL)
    legend_data = [
        (C["red"], "高", "严重违规 — 须立即整改"),
        (C["orange"], "中", "中度违规 — 建议修改"),
        (C["silver"], "低", "轻微偏离 — 优化建议"),
        (C["blue"], "—", "Civil 建筑规范"),
        (C["orange"], "—", "EEE  电气规范"),
    ]
    for i, (clr, sev, desc) in enumerate(legend_data):
        yy = ly + 24 + i * 22
        r = 7
        draw.ellipse([lx+14-r, yy+2-r, lx+14+r, yy+2+r], fill=clr)
        draw.text((lx+28, yy-1), sev, fill=clr, font=FONT_TINY)
        draw.text((lx+60, yy-1), desc, fill=C["muted"], font=FONT_TINY)

    # --- Top review header ---
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    draw.rectangle([0, 0, W, 58], fill=TITLE_BG)
    draw.text((MARGIN, 10), "ArchCheck  AI Review  —  Annotated Floor Plan", fill=WHITE, font=FONT_HEADER)
    draw.text((MARGIN, 34), f"Automated Building Code Compliance Review  |  {today}", fill=C["silver"], font=FONT_SMALL)
    # Stats pills in header
    total_issues = len(VIOLATIONS)
    civil_count = sum(1 for v in VIOLATIONS if v["type"]=="civil")
    eee_count = sum(1 for v in VIOLATIONS if v["type"]=="eee")
    high_count = sum(1 for v in VIOLATIONS if v["severity"]=="高")
    stats_str = f"Issues: {total_issues}  |  Civil: {civil_count}  |  EEE: {eee_count}  |  High: {high_count}"
    draw.text((W-MARGIN-10, 14), stats_str, fill=C["silver"], font=FONT_SMALL, anchor="ra")

    # Aicher band
    band_y = 58
    band_colors = [C["blue"], C["blue"], C["orange"], C["orange"], C["red"], C["red"], C["green"]]
    seg_w = W // len(band_colors)
    for i, bc in enumerate(band_colors):
        draw.rectangle([i*seg_w, band_y, (i+1)*seg_w, band_y+6], fill=bc)

    # --- North arrow ---
    draw_north_arrow(draw, CANVAS_W - 110, BUILD_Y - 20)

    # --- Scale bar ---
    draw_scale_bar(draw, BUILD_X, CANVAS_H - 65)

    # --- Watermark ---
    wm_text = "ARCHCHECK"
    wm_font = _load_font(72, True)
    wm_bbox = draw.textbbox((0,0), wm_text, font=wm_font)
    wm_w = wm_bbox[2] - wm_bbox[0]
    wm_x = (W - wm_w) // 2
    wm_y = (H) // 2 - 30
    # Very faint
    overlay2 = Image.new("RGBA", img.size, (0,0,0,0))
    overlay2_draw = ImageDraw.Draw(overlay2)
    overlay2_draw.text((wm_x, wm_y), wm_text, fill=(200,208,218,25), font=wm_font)
    img = Image.alpha_composite(img, overlay2)

    return img.convert("RGB")

# ============================================================
# MAIN
# ============================================================
def main():
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    print("Generating Image 1: Architect's CAD plan...")
    img1 = render_architect_plan()
    path1 = output_dir / "demo_architect_plan.png"
    img1.save(path1, "PNG", dpi=(150, 150))
    print(f"  -> {path1}  ({path1.stat().st_size//1024} KB)")

    print("Generating Image 2: ArchCheck AI review annotated plan...")
    img2 = render_review_annotated()
    path2 = output_dir / "demo_review_annotated.png"
    img2.save(path2, "PNG", dpi=(150, 150))
    print(f"  -> {path2}  ({path2.stat().st_size//1024} KB)")

    print("\nDone. Two demo images ready.")

if __name__ == "__main__":
    main()
