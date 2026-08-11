from PIL import Image, ImageDraw, ImageFont
from core.config import C
from core.i18n import LANG, T, _floor_label

FP_X1, FP_Y1 = 30, 80

FP_X1, FP_Y1 = 30, 80

FP_X2, FP_Y2 = 1230, 1130

FP_X2, FP_Y2 = 1230, 1130

FP_W = FP_X2 - FP_X1

FP_H = FP_Y2 - FP_Y1

ROOM_COLORS = {
    "office": (240, 245, 250),
    "corridor": (228, 238, 248),
    "stairs": (255, 248, 235),
    "elec": (252, 238, 238),
}

_FONT_CANDIDATES = ["msyh.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf"]

VIOLATION_POSITIONS = [
    (FP_X1+900, FP_Y1+800),
    (FP_X1+1140, FP_Y1+120),
    (FP_X1+550, FP_Y1+80),
    (FP_X1+90,  FP_Y1+800),
    (FP_X1+650, FP_Y1+490),
    (FP_X1+1140, FP_Y1+490),
    (FP_X1+950, FP_Y1+650),
    (FP_X1+270, FP_Y1+800),
]

MARKER_COLORS = {
    "civil":    (91, 163, 217),
    "eee":      (240, 146, 53),
    "building": (142, 107, 191),
    "conflict": (211, 47, 47),
}

def _load_fonts(sizes=(36, 28, 22)):
    for font_name in _FONT_CANDIDATES:
        try:
            return tuple(ImageFont.truetype(font_name, s) for s in sizes)
        except Exception:
            continue
    return (ImageFont.load_default(),) * len(sizes)

def _draw_floor_plan(draw, W, H, variant=0):
    ft, fm, fs = _load_fonts((36, 28, 22))
    draw.rectangle([FP_X1-2, FP_Y1-2, FP_X2+2, FP_Y2+2], outline=(40, 45, 55), width=4)
    # Three variants: F1=original, F2=shifted rooms, F3=multifunction hall
    if variant == 0:
        rooms = [
            (FP_X1+20, FP_Y1+20, FP_X1+600, FP_Y1+430, ("Office A\n(85 m²)", "办公室A\n(85 m²)"), "office"),
            (FP_X1+620, FP_Y1+20, FP_X2-20, FP_Y1+430, ("Meeting Room\n(120 m²)", "会议室\n(120 m²)"), "office"),
            (FP_X1+620, FP_Y1+455, FP_X1+890, FP_Y1+680, ("Stairwell\n(20 m²)", "楼梯间\n(20 m²)"), "stairs"),
            (FP_X1+910, FP_Y1+455, FP_X2-20, FP_Y1+680, ("Electrical\nRoom (12 m²)", "配电间\n(12 m²)"), "elec"),
            (FP_X1+20, FP_Y1+710, FP_X2-20, FP_Y2-20, ("Corridor", "走廊"), "corridor"),
        ]
    elif variant == 1:
        rooms = [
            (FP_X1+20, FP_Y1+20, FP_X1+500, FP_Y1+430, ("Office B\n(90 m²)", "办公室B\n(90 m²)"), "office"),
            (FP_X1+520, FP_Y1+20, FP_X1+900, FP_Y1+430, ("Training Room\n(110 m²)", "培训室\n(110 m²)"), "office"),
            (FP_X1+920, FP_Y1+20, FP_X2-20, FP_Y1+300, ("Washroom", "洗手间"), "office"),
            (FP_X1+920, FP_Y1+320, FP_X2-20, FP_Y1+530, ("Stairwell\n(20 m²)", "楼梯间\n(20 m²)"), "stairs"),
            (FP_X1+520, FP_Y1+455, FP_X2-20, FP_Y1+680, ("Equip. Room\n(15 m²)", "设备间\n(15 m²)"), "elec"),
            (FP_X1+20, FP_Y1+710, FP_X2-20, FP_Y2-20, ("Corridor", "走廊"), "corridor"),
        ]
    else:  # variant 2
        rooms = [
            (FP_X1+20, FP_Y1+20, FP_X1+480, FP_Y1+500, ("Office C\n(88 m²)", "办公室C\n(88 m²)"), "office"),
            (FP_X1+500, FP_Y1+20, FP_X2-20, FP_Y1+500, ("Multi-Purpose\nHall (130 m²)", "多功能厅\n(130 m²)"), "office"),
            (FP_X1+20, FP_Y1+520, FP_X1+300, FP_Y1+680, ("LV Room\n(10 m²)", "弱电间\n(10 m²)"), "elec"),
            (FP_X1+320, FP_Y1+520, FP_X1+580, FP_Y1+680, ("Stairwell\n(20 m²)", "楼梯间\n(20 m²)"), "stairs"),
            (FP_X1+600, FP_Y1+520, FP_X2-20, FP_Y1+680, ("Lounge (40 m²)", "休息室 (40 m²)"), "office"),
            (FP_X1+20, FP_Y1+710, FP_X2-20, FP_Y2-20, ("Corridor", "走廊"), "corridor"),
        ]

    is_zh = LANG == "zh"
    room_rects = {}
    for rx1, ry1, rx2, ry2, label, rtype in rooms:
        fc = ROOM_COLORS[rtype]
        draw.rectangle([rx1, ry1, rx2, ry2], fill=fc, outline=(130, 140, 150), width=3)
        label_text = label[1] if is_zh else label[0]
        lines = label_text.split("\n")
        cx = (rx1 + rx2) // 2
        cy_start = (ry1 + ry2) // 2 - (len(lines) - 1) * 18
        for li, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=fm)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw//2, cy_start + li * 36), line, fill=(30, 35, 45), font=fm)
        key = rtype if rtype == "corridor" else (label[1] if is_zh else label[0]).split("\n")[0]
        room_rects[key] = (rx1, ry1, rx2, ry2)

    # Fire zone boundary
    if variant == 0:
        fz_x1, fz_y1, fz_x2, fz_y2 = FP_X1+8, FP_Y1+8, FP_X2-8, FP_Y1+695
    elif variant == 1:
        fz_x1, fz_y1, fz_x2, fz_y2 = FP_X1+8, FP_Y1+8, FP_X1+900+8, FP_Y1+430+8
    else:
        fz_x1, fz_y1, fz_x2, fz_y2 = FP_X1+8, FP_Y1+8, FP_X1+480+8, FP_Y1+500+8
    dash = 20
    for x in range(fz_x1, fz_x2, dash*2):
        draw.line([(x, fz_y1), (min(x+dash, fz_x2), fz_y1)], fill=C["blue"], width=3)
        draw.line([(x, fz_y2), (min(x+dash, fz_x2), fz_y2)], fill=C["blue"], width=3)
    for y in range(fz_y1, fz_y2, dash*2):
        draw.line([(fz_x1, y), (fz_x1, min(y+dash, fz_y2))], fill=C["blue"], width=3)
        draw.line([(fz_x2, y), (fz_x2, min(y+dash, fz_y2))], fill=C["blue"], width=3)
    return room_rects

def _draw_info_panel(draw, W, H, floor_label=""):
    ft, fm, fs = _load_fonts((36, 28, 22))
    px = 1270
    ly = FP_Y1
    draw.rectangle([px, ly, W-30, ly+200], fill=(255,255,255), outline=(200,205,210), width=2)
    legend_title = "图例" if LANG == "zh" else "LEGEND"
    draw.text((px+16, ly+10), legend_title, fill=(40,45,55), font=fm)
    items = [
        (("Office / Meeting", "办公/会议"), ROOM_COLORS["office"]),
        (("Corridor", "走廊"), ROOM_COLORS["corridor"]),
        (("Stairwell", "楼梯间"), ROOM_COLORS["stairs"]),
        (("Equip. Room", "设备间"), ROOM_COLORS["elec"]),
    ]
    for i, (lb, cl) in enumerate(items):
        yy = ly + 46 + i*30
        draw.rectangle([px+16, yy, px+46, yy+22], fill=cl, outline=(180,185,190))
        draw.text((px+56, yy), lb[1] if LANG=="zh" else lb[0], fill=(40,45,55), font=fs)
    fz_y = ly + 220
    if floor_label:
        draw.text((px+16, fz_y), floor_label, fill=C["blue"], font=fm)
    fz1_label = "防火分区1" if LANG=="zh" else "Fire Zone 1"
    fz2_label = "防火分区2" if LANG=="zh" else "Fire Zone 2"
    draw.text((px+16, fz_y+34), fz1_label, fill=C["blue"], font=fs)
    draw.text((px+16, fz_y+58), T["sprinklered"], fill=C["silver"], font=fs)
    draw.text((px+16, fz_y+80), fz2_label, fill=C["silver"], font=fs)
    sy = H - 50
    draw.line([(px, sy), (px+200, sy)], fill=(40,45,55), width=4)
    draw.line([(px, sy-10), (px, sy+10)], fill=(40,45,55), width=3)
    draw.line([(px+100, sy-10), (px+100, sy+10)], fill=(40,45,55), width=3)
    draw.line([(px+200, sy-10), (px+200, sy+10)], fill=(40,45,55), width=3)
    draw.text((px+10, sy-42), "0         5        10m", fill=C["dim"], font=fs)
    cx_n, cy_n = px+100, FP_Y1+420
    draw.ellipse([cx_n-22, cy_n-22, cx_n+22, cy_n+22], outline=(40,45,55), width=2)
    draw.polygon([(cx_n, cy_n-34), (cx_n-10, cy_n+6), (cx_n, cy_n-4), (cx_n+10, cy_n+6)], fill=(40,45,55))
    draw.text((cx_n-10, cy_n-62), "N", fill=(40,45,55), font=fm)

def generate_sample_image(floor_name="", variant=0):
    W, H = 1800, 1200
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((36, 28, 22))
    plan_label = "楼层平面图" if LANG == "zh" else "FLOOR PLAN"
    title = f"{plan_label}  —  {floor_name}" if floor_name else f"{plan_label}  —  Office Building"
    draw.rectangle([0, 0, W, 70], fill=(30, 35, 45))
    draw.text((40, 12), title, fill=(240, 245, 250), font=ft)
    _draw_floor_plan(draw, W, H, variant=variant)
    _draw_info_panel(draw, W, H, floor_name)
    return img

def annotate_image(image, issues):
    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_fonts((30,))[0]
    for i, issue in enumerate(issues):
        if i >= len(VIOLATION_POSITIONS):
            break
        x, y = VIOLATION_POSITIONS[i]
        color = MARKER_COLORS.get(issue.get("type", "civil"), MARKER_COLORS["civil"])
        r = 30
        rgba = color + (255,)
        draw.ellipse([x-r, y-r, x+r, y+r], fill=rgba, outline=(255,255,255,255), width=3)
        label = str(i+1)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x-tw//2, y-th//2-1), label, fill=(255,255,255,255), font=font)
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")

def _fix_map():
    return {
        "CIVIL-001": T["fix_civ001"], "CIVIL-002": T["fix_civ002"],
        "CIVIL-003": T["fix_civ003"], "CIVIL-004": T["fix_civ004"],
        "EEE-001": T["fix_eee001"], "EEE-002": T["fix_eee002"],
        "EEE-003": T["fix_eee003"], "EEE-004": T["fix_eee004"],
        "BLD-001": T["fix_bld001"], "BLD-002": T["fix_bld002"],
        "BLD-003": T["fix_bld003"], "BLD-004": T["fix_bld004"],
    }


# ============================================================
# DATA-DRIVEN ROOM PLAN (replaces the generic template for real input)
# ============================================================
def _treemap(areas):
    """Squarified treemap. areas: list of floats. Returns rects (x,y,w,h) in [0,1]²."""
    total = sum(areas) or 1.0
    norm = [max(a, 1e-6) / total for a in areas]
    rects = []

    def worst(row, length):
        s = sum(row)
        if s <= 0:
            return float("inf")
        mx, mn = max(row), min(row)
        return max(length * length * mx / (s * s), s * s / (length * length * mn))

    def layout(row, rx, ry, rw, rh):
        s = sum(row)
        if rw >= rh:
            for a in row:
                hh = rh * a / s
                rects.append((rx, ry, rw, hh))
                ry += hh
        else:
            for a in row:
                ww = rw * a / s
                rects.append((rx, ry, ww, rh))
                rx += ww

    row = []
    rx, ry, rw, rh = 0.0, 0.0, 1.0, 1.0
    i = 0
    n = len(norm)
    while i < n:
        a = norm[i]
        if not row:
            row.append(a)
            i += 1
            continue
        if worst(row + [a], min(rw, rh)) <= worst(row, min(rw, rh)):
            row.append(a)
            i += 1
            continue
        s = sum(row)
        if rw >= rh:
            hh = s / rw          # strip area == row area fraction
            layout(row, rx, ry, rw, hh)
            ry += hh
            rh -= hh
        else:
            ww = s / rh
            layout(row, rx, ry, ww, rh)
            rx += ww
            rw -= ww
        row = []
    if row:
        # last row fills the entire remaining region
        if rw >= rh:
            layout(row, rx, ry, rw, rh)
        else:
            layout(row, rx, ry, rw, rh)
    return rects


ROOM_TYPE_FILL = {
    "Office": (233, 240, 248), "Corridor": (224, 236, 247),
    "Stairwell": (255, 246, 230), "Meeting Room": (238, 240, 252),
    "Equipment Room": (252, 234, 234), "Vestibule": (240, 244, 238),
}


def render_room_plan(rooms, floor_name=""):
    """Draw a data-driven floor plan: rooms packed by area (treemap), labeled.

    Returns (PIL image, room_map) where room_map maps room name -> (cx, cy).
    """
    W, H = 1800, 1200
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((36, 28, 22))
    plan_label = "楼层平面图" if LANG == "zh" else "FLOOR PLAN"
    title = f"{plan_label}  —  {_floor_label(floor_name)}" if floor_name else plan_label
    draw.rectangle([0, 0, W, 70], fill=(30, 35, 45))
    draw.text((40, 12), title, fill=(240, 245, 250), font=ft)

    dx1, dy1, dx2, dy2 = 60, 110, 1130, H - 150
    aw, ah = dx2 - dx1, dy2 - dy1
    room_map = {}
    if not rooms:
        draw.text((dx1, dy1 + 40), "无房间数据" if LANG == "zh" else "No room data",
                  fill=(150, 155, 165), font=fm)
        return img, room_map

    if rooms and all(r.get("hull") for r in rooms):
        # Real IFC geometry — draw the actual room footprint polygons (hulls).
        _all = [p for r in rooms for p in r["hull"]]
        _minx = min(p[0] for p in _all); _maxx = max(p[0] for p in _all)
        _miny = min(p[1] for p in _all); _maxy = max(p[1] for p in _all)
        _spanx = max(_maxx - _minx, 1e-6); _spany = max(_maxy - _miny, 1e-6)
        _scale = min((aw - 40) / _spanx, (ah - 40) / _spany)
        _ox = dx1 + (aw - _spanx * _scale) / 2
        _oy = dy1 + (ah - _spany * _scale) / 2
        for r in rooms:
            _poly = [(int(_ox + (x - _minx) * _scale), int(_oy + (y - _miny) * _scale)) for x, y in r["hull"]]
            _fill = ROOM_TYPE_FILL.get(r.get("type", "Office"), ROOM_TYPE_FILL["Office"])
            draw.polygon(_poly, fill=_fill, outline=(120, 130, 142))
            _cx = int(sum(p[0] for p in _poly) / len(_poly))
            _cy = int(sum(p[1] for p in _poly) / len(_poly))
            _nm = str(r.get("name", "?"))
            _nb = draw.textbbox((0, 0), _nm, font=fm)
            draw.text((_cx - (_nb[2] - _nb[0]) // 2, _cy - 12), _nm, fill=(30, 35, 45), font=fm)
            room_map[_nm] = (_cx, _cy)
    else:
        areas = [max(float(r.get("room_area_sqm", 20)), 4.0) for r in rooms]
        rects = _treemap(areas)
        for r, (nx, ny, nw, nh) in zip(rooms, rects):
            x1 = int(dx1 + nx * aw)
            y1 = int(dy1 + ny * ah)
            x2 = int(dx1 + (nx + nw) * aw)
            y2 = int(dy1 + (ny + nh) * ah)
            fill = ROOM_TYPE_FILL.get(r.get("type", "Office"), ROOM_TYPE_FILL["Office"])
            draw.rectangle([x1, y1, x2, y2], fill=fill, outline=(120, 130, 142), width=2)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            name = str(r.get("name", "?"))
            area_txt = f'{float(r.get("room_area_sqm", 0)):.0f}m²'
            if (x2 - x1) > 120 and (y2 - y1) > 46:
                nb = draw.textbbox((0, 0), name, font=fm)
                draw.text((cx - (nb[2] - nb[0]) // 2, cy - 18), name, fill=(30, 35, 45), font=fm)
                ab = draw.textbbox((0, 0), area_txt, font=fs)
                draw.text((cx - (ab[2] - ab[0]) // 2, cy + 14), area_txt, fill=(90, 100, 112), font=fs)
            else:
                nb = draw.textbbox((0, 0), name, font=fs)
                draw.text((cx - (nb[2] - nb[0]) // 2, cy - 8), name, fill=(30, 35, 45), font=fs)
            room_map[name] = (cx, cy)

    # legend
    ly = H - 60
    lx = dx1
    for rtype, col in ROOM_TYPE_FILL.items():
        draw.rectangle([lx, ly, lx + 16, ly + 16], fill=col, outline=(140, 150, 160))
        lbl = rtype
        draw.text((lx + 22, ly), lbl, fill=(70, 75, 85), font=fs)
        lx += 170
    return img, room_map


def annotate_room_plan(img, issues, room_map):
    """Overlay numbered markers at each issue's room centroid (fallback: fixed)."""
    img = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_fonts((30,))[0]
    for i, issue in enumerate(issues):
        color = MARKER_COLORS.get(issue.get("type", "civil"), MARKER_COLORS["civil"])
        pos = room_map.get(issue.get("location", ""))
        if pos is None and i < len(VIOLATION_POSITIONS):
            pos = VIOLATION_POSITIONS[i]
        if pos is None:
            continue
        x, y = pos
        r = 30
        rgba = color + (255,)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=rgba, outline=(255, 255, 255, 255), width=3)
        label = str(i + 1)
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((x - tw // 2, y - th // 2 - 1), label, fill=(255, 255, 255, 255), font=font)
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def generate_correction_image(image, civ, eee, conflicts, bdata=None, floor_name="",
                              variant=0, base_plan=None, room_map=None):
    W, H = 1800, 1200
    if base_plan is not None:
        img = base_plan.convert("RGB").copy()
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, W, 6], fill=(100, 160, 50))
    else:
        img = Image.new("RGB", (W, H), (250, 251, 252))
        draw = ImageDraw.Draw(img)
        ft, fm, fs = _load_fonts((34, 24, 20))
        correction_title = "修正方案" if LANG == "zh" else "CORRECTION PLAN"
        title = f"{correction_title}  —  {floor_name}" if floor_name else f"{correction_title}"
        draw.rectangle([0, 0, W, 70], fill=(100, 160, 50))
        draw.text((40, 12), title, fill=(255, 255, 255), font=ft)
        _draw_floor_plan(draw, W, H, variant=variant)
    ft, fm, fs = _load_fonts((34, 24, 20))
    all_items = list(civ) + list(eee)
    for i, iss in enumerate(all_items):
        pos = room_map.get(iss.get("location", "")) if room_map else None
        if pos is None:
            if i >= len(VIOLATION_POSITIONS):
                break
            pos = VIOLATION_POSITIONS[i]
        x, y = pos
        r = 18
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(100,160,50), outline=(255,255,255), width=2)
        label = str(i+1)
        bbox = draw.textbbox((0, 0), label, font=fs)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x-tw//2, y-th//2-1), label, fill=(255,255,255), font=fs)
    px = 1270
    cy = FP_Y1
    for i, iss in enumerate(all_items):
        rid = iss.get("rule_id", "")
        fix_text = _fix_map().get(rid, iss.get("title", "Fix issue"))
        lines = fix_text.split("\n")
        line_h = 26
        box_w = 480
        box_h = len(lines) * line_h + 24
        if cy + box_h > H - 20:
            break
        draw.rectangle([px, cy, px+box_w, cy+box_h], fill=(255,255,255), outline=(100,160,50), width=3)
        draw.rectangle([px, cy, px+6, cy+box_h], fill=(100,160,50))
        draw.text((px+16, cy+8), str(i+1), fill=(100,160,50), font=fm)
        for j, line in enumerate(lines):
            draw.text((px+50, cy+10 + j*line_h), line, fill=(30,35,45), font=fs)
        cy += box_h + 6
    return img

def generate_building_section(floors, civil_r, eee_r, building_r, conflicts):
    n = len(floors)
    W, H = 900, 120 + n * 160 + 80
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((28, 20, 16))

    title = "建筑剖面 · 楼层关联" if LANG == "zh" else "BUILDING SECTION · FLOOR CONNECTIONS"
    draw.rectangle([0, 0, W, 50], fill=(30, 35, 45))
    draw.text((20, 10), title, fill=(240, 245, 250), font=ft)

    floor_h = 120
    gap = 20
    bx, by = 40, 70
    bw = 520

    # Build per-floor counts
    floor_stats = {}
    for f in floors:
        fid = f.get("floor_id", "")
        fname = _floor_label(f.get("floor_name", fid))
        fc = sum(1 for i in civil_r if i.get("floor_id") == fid)
        fe = sum(1 for i in eee_r if i.get("floor_id") == fid)
        fk = sum(1 for c in conflicts if c.get("floor_id") == fid)
        floor_stats[fid] = (fname, fc, fe, fk)

    # Draw floors top-to-bottom (F3 -> F1 or highest floor first)
    for idx, f in enumerate(reversed(floors)):
        fid = f.get("floor_id", "")
        fname, fc, fe, fk = floor_stats.get(fid, (fid, 0, 0, 0))
        y = by + idx * (floor_h + gap)

        # Floor slab
        draw.rectangle([bx, y, bx+bw, y+floor_h], fill=(245, 247, 250), outline=(180, 190, 200), width=2)
        draw.rectangle([bx, y+floor_h-8, bx+bw, y+floor_h], fill=(160, 170, 180))

        # Floor label
        draw.text((bx+14, y+12), fname, fill=(30, 35, 45), font=fm)

        # Issue badges
        bx2 = bx + 160
        if fc > 0:
            draw.rounded_rectangle([bx2, y+12, bx2+80, y+38], radius=4, fill=C["blue"])
            civ_lbl = f"建筑 {fc}" if LANG == "zh" else f"CIV {fc}"
            draw.text((bx2+8, y+15), civ_lbl, fill=(255,255,255), font=fs)
            bx2 += 90
        if fe > 0:
            draw.rounded_rectangle([bx2, y+12, bx2+80, y+38], radius=4, fill=C["orange"])
            eee_lbl = f"电气 {fe}" if LANG == "zh" else f"EEE {fe}"
            draw.text((bx2+8, y+15), eee_lbl, fill=(255,255,255), font=fs)
            bx2 += 90
        if fk > 0:
            draw.rounded_rectangle([bx2, y+12, bx2+90, y+38], radius=4, fill=C["red"])
            c_lbl = f"冲突 {fk}" if LANG == "zh" else f"CNFL {fk}"
            draw.text((bx2+8, y+15), c_lbl, fill=(255,255,255), font=fs)

        # Stairwell connecting block (left side, visual continuity)
        stair_x = bx + 20
        draw.rectangle([stair_x, y+48, stair_x+50, y+floor_h-8], fill=(255, 248, 235), outline=(200, 180, 140), width=1)
        stair_lbl = "楼梯" if LANG == "zh" else "STAIR"
        draw.text((stair_x+4, y+58), stair_lbl, fill=(140, 110, 60), font=fs)

        # Elevator/services shaft (right side, carries building-level risers)
        serv_x = bx + bw - 90
        draw.rectangle([serv_x, y+48, serv_x+70, y+floor_h-8], fill=(252, 238, 238), outline=(200, 160, 160), width=1)
        serv_lbl = "管井" if LANG == "zh" else "RISER"
        draw.text((serv_x+8, y+58), serv_lbl, fill=(160, 80, 80), font=fs)

    # Draw vertical connection lines (building-level issues run through all floors)
    n_bld = len(building_r)
    if n_bld > 0:
        serv_cx = bx + bw - 55
        top_y = by + 10
        bot_y = by + n * (floor_h + gap) - gap - 10
        # Vertical purple line spanning all floors through the riser
        draw.line([(serv_cx, top_y), (serv_cx, bot_y)], fill=C["purple"], width=6)
        for i in range(n+1):
            yy = by + i * (floor_h + gap) + floor_h - 8 if i < n else by + i * (floor_h + gap) - gap - 10
            draw.ellipse([serv_cx-6, yy-6, serv_cx+6, yy+6], fill=C["purple"])

        # Building-level issue badge
        draw.rounded_rectangle([bx+bw+20, by+20, W-20, by+20+40], radius=6, fill=C["purple"])
        bld_lbl = f"全楼 {n_bld}" if LANG == "zh" else f"BLD {n_bld}"
        draw.text((bx+bw+32, by+27), bld_lbl, fill=(255,255,255), font=fm)

        # Individual building-level issue labels
        bld_names = {
            "BLD-001": ("首层门宽", "Exit Width"),
            "BLD-002": ("消防水池", "Fire Pool"),
            "BLD-003": ("变压器", "Transformer"),
            "BLD-004": ("应急电源", "Emg. Power"),
        }
        label_y = by + 75
        for iss in building_r:
            rid = iss.get("rule_id", "")
            zh_name, en_name = bld_names.get(rid, (rid, rid))
            lbl = zh_name if LANG == "zh" else en_name
            draw.text((bx+bw+28, label_y), f"● {lbl}", fill=C["purple"], font=fs)
            label_y += 24

        # Arrow/label indicating these span all floors
        span_lbl = "↕ 跨楼层累积量" if LANG == "zh" else "↕ Cross-floor totals"
        draw.text((bx+bw+28, bot_y-20), span_lbl, fill=C["purple"], font=fs)

    # Legend at bottom
    leg_y = H - 40
    items = [
        (("建筑", "CIV"), C["blue"]),
        (("电气", "EEE"), C["orange"]),
        (("全楼", "BLD"), C["purple"]),
        (("冲突", "CNFL"), C["red"]),
    ]
    lx = bx
    for (lb_zh, lb_en), col in items:
        lb = lb_zh if LANG == "zh" else lb_en
        draw.rectangle([lx, leg_y, lx+16, leg_y+16], fill=col)
        draw.text((lx+22, leg_y), lb, fill=(60, 65, 75), font=fs)
        lx += 90

    return img

