from PIL import Image, ImageDraw, ImageFont
from core.config import C
from core import i18n
from core.i18n import _floor_label

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

    is_zh = i18n.LANG == "zh"
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
    legend_title = "图例" if i18n.LANG == "zh" else "LEGEND"
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
        draw.text((px+56, yy), lb[1] if i18n.LANG=="zh" else lb[0], fill=(40,45,55), font=fs)
    fz_y = ly + 220
    if floor_label:
        draw.text((px+16, fz_y), floor_label, fill=C["blue"], font=fm)
    fz1_label = "防火分区1" if i18n.LANG=="zh" else "Fire Zone 1"
    fz2_label = "防火分区2" if i18n.LANG=="zh" else "Fire Zone 2"
    draw.text((px+16, fz_y+34), fz1_label, fill=C["blue"], font=fs)
    draw.text((px+16, fz_y+58), i18n.T["sprinklered"], fill=C["silver"], font=fs)
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
    plan_label = "楼层平面图" if i18n.LANG == "zh" else "FLOOR PLAN"
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
        "CIVIL-001": i18n.T["fix_civ001"], "CIVIL-002": i18n.T["fix_civ002"],
        "CIVIL-003": i18n.T["fix_civ003"], "CIVIL-004": i18n.T["fix_civ004"],
        "EEE-001": i18n.T["fix_eee001"], "EEE-002": i18n.T["fix_eee002"],
        "EEE-003": i18n.T["fix_eee003"], "EEE-004": i18n.T["fix_eee004"],
        "BLD-001": i18n.T["fix_bld001"], "BLD-002": i18n.T["fix_bld002"],
        "BLD-003": i18n.T["fix_bld003"], "BLD-004": i18n.T["fix_bld004"],
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
    "Unknown": (235, 235, 238),
}


def _draw_plan_elements(draw, elements, minx, miny, scale, ox, oy):
    """Overlay physical-element footprints (walls/columns/windows) on a plan."""
    for el in elements:
        x0, y0, x1, y1 = el["bbox"][:4]
        kind = el["kind"]
        sx0 = ox + (x0 - minx) * scale; sy0 = oy + (y0 - miny) * scale
        sx1 = ox + (x1 - minx) * scale; sy1 = oy + (y1 - miny) * scale
        if kind == "wall":
            draw.rectangle([sx0, sy0, sx1, sy1], fill=(56, 62, 74),
                           outline=(34, 38, 46), width=2)
        elif kind == "column":
            cx = (sx0 + sx1) / 2; cy = (sy0 + sy1) / 2
            r = max(2.0, min(abs(sx1 - sx0), abs(sy1 - sy0)) / 2)
            draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=(98, 106, 120),
                           outline=(34, 38, 46), width=2)
        elif kind == "window":
            if abs(sx1 - sx0) >= abs(sy1 - sy0):
                draw.line([sx0 + 4, (sy0 + sy1) / 2, sx1 - 4, (sy0 + sy1) / 2],
                          fill=(74, 138, 200), width=4)
            else:
                draw.line([(sx0 + sx1) / 2, sy0 + 4, (sx0 + sx1) / 2, sy1 - 4],
                          fill=(74, 138, 200), width=4)
        elif kind == "pipe":
            draw.line([sx0, sy0, sx1, sy1], fill=(52, 120, 168), width=3)
        elif kind == "duct":
            draw.line([sx0, sy0, sx1, sy1], fill=(124, 92, 168), width=3)


def render_room_plan(rooms, floor_name="", plan_elements=None):
    """Draw a data-driven floor plan: rooms packed by area (treemap), labeled.

    Returns (PIL image, room_map) where room_map maps room name -> (cx, cy).
    """
    W, H = 1800, 1200
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((36, 28, 22))
    plan_label = "楼层平面图" if i18n.LANG == "zh" else "FLOOR PLAN"
    title = f"{plan_label}  —  {_floor_label(floor_name)}" if floor_name else plan_label
    draw.rectangle([0, 0, W, 70], fill=(30, 35, 45))
    draw.text((40, 12), title, fill=(240, 245, 250), font=ft)

    dx1, dy1, dx2, dy2 = 60, 110, 1130, H - 150
    aw, ah = dx2 - dx1, dy2 - dy1
    room_map = {}
    if not rooms:
        draw.text((dx1, dy1 + 40), "无房间数据" if i18n.LANG == "zh" else "No room data",
                  fill=(150, 155, 165), font=fm)
        return img, room_map

    if rooms and all(r.get("hull") for r in rooms):
        # Real IFC geometry — draw the actual room footprint polygons (hulls),
        # then overlay physical elements (walls/columns/windows) from the model.
        _all = [p for r in rooms for p in r["hull"]]
        for el in (plan_elements or []):
            _x0, _y0, _x1, _y1 = el["bbox"][:4]
            _all += [(_x0, _y0), (_x1, _y0), (_x0, _y1), (_x1, _y1)]
        _minx = min(p[0] for p in _all); _maxx = max(p[0] for p in _all)
        _miny = min(p[1] for p in _all); _maxy = max(p[1] for p in _all)
        _spanx = max(_maxx - _minx, 1e-6); _spany = max(_maxy - _miny, 1e-6)
        _scale = min((aw - 40) / _spanx, (ah - 40) / _spany)
        _ox = dx1 + (aw - _spanx * _scale) / 2
        _oy = dy1 + (ah - _spany * _scale) / 2
        _polys = []
        for r in rooms:
            _poly = [(int(_ox + (x - _minx) * _scale), int(_oy + (y - _miny) * _scale)) for x, y in r["hull"]]
            _fill = ROOM_TYPE_FILL.get(r.get("type", "Office"), ROOM_TYPE_FILL["Office"])
            draw.polygon(_poly, fill=_fill, outline=(120, 130, 142))
            _polys.append((_poly, r))
        _draw_plan_elements(draw, plan_elements or [], _minx, _miny, _scale, _ox, _oy)
        for _poly, r in _polys:
            _cx = int(sum(p[0] for p in _poly) / len(_poly))
            _cy = int(sum(p[1] for p in _poly) / len(_poly))
            _nm = str(r.get("name", "?"))
            _nb = draw.textbbox((0, 0), _nm, font=fm)
            draw.text((_cx - (_nb[2] - _nb[0]) // 2, _cy - 12), _nm, fill=(30, 35, 45), font=fm)
            room_map[_nm] = (_cx, _cy)
    else:
        areas = [max(float(r.get("room_area_sqm") or 20), 4.0) for r in rooms]
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
            _a = r.get("room_area_sqm")
            area_txt = (f'{float(_a):.0f}m²' if _a is not None
                        else ("面积未知" if i18n.LANG == "zh" else "area n/a"))
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


def _darken(color, f=0.7):
    """Darker shade of an RGB color (tuple or #RRGGBB) for 3D side faces."""
    if isinstance(color, str):
        r = int(color[1:3], 16); g = int(color[3:5], 16); b = int(color[5:7], 16)
    else:
        r, g, b = color
    return (int(r * f), int(g * f), int(b * f))


def generate_building_3d(floors):
    """Isometric 3D view of the building — every floor's real room footprint
    extruded vertically, so the whole multi-storey 3D structure is visible at
    once (top floor overlaps lower ones). Falls back to a note if no room
    geometry is available."""
    W, H = 1800, 1400
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((36, 28, 22))
    title = "建筑 3D 立体视图" if i18n.LANG == "zh" else "BUILDING 3D ISOMETRIC VIEW"
    draw.rectangle([0, 0, W, 70], fill=(30, 35, 45))
    draw.text((40, 12), title, fill=(240, 245, 250), font=ft)

    pts = [p for f in floors for r in f.get("rooms", []) for p in (r.get("hull") or [])]
    for f in floors:
        for el in f.get("plan_elements") or []:
            _x0, _y0, _x1, _y1 = el["bbox"][:4]
            pts += [(_x0, _y0), (_x1, _y0), (_x0, _y1), (_x1, _y1)]
    if not pts:
        draw.text((60, 130), "无房间几何数据" if i18n.LANG == "zh" else "No room geometry data",
                  fill=(150, 155, 165), font=fm)
        return img
    minx = min(p[0] for p in pts); maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts); maxy = max(p[1] for p in pts)
    spanx = max(maxx - minx, 1e-6); spany = max(maxy - miny, 1e-6)

    n = len(floors)
    floor_h = 170
    wall_h = 34
    s = min((W - 320) / (spanx + spany), (H - 250 - (n - 1) * floor_h) / (spanx + spany))
    s = max(s, 1e-6)
    cx = W // 2
    base_cy = H - 100

    def iso(x, y, z):
        u = x - minx - spanx / 2
        v = y - miny - spany / 2
        sx = cx + (u - v) * 0.866 * s
        sy = base_cy + (u + v) * 0.5 * s - z
        return int(sx), int(sy)

    for idx in range(n - 1, -1, -1):  # bottom -> top so upper floors overlap
        f = floors[idx]
        z = (n - 1 - idx) * floor_h
        polys = [(poly, r) for r in f.get("rooms", []) if r.get("hull")
                 for poly in [[iso(p[0], p[1], z) for p in r["hull"]]]]
        for poly, r in polys:
            base = ROOM_TYPE_FILL.get(r.get("type", "Office"), ROOM_TYPE_FILL["Office"])
            dark = _darken(base)
            for i in range(len(poly)):
                x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
                draw.polygon([(x1, y1), (x2, y2), (x2, y2 + wall_h), (x1, y1 + wall_h)], fill=dark)
        for poly, r in polys:
            fill = ROOM_TYPE_FILL.get(r.get("type", "Office"), ROOM_TYPE_FILL["Office"])
            draw.polygon(poly, fill=fill, outline=(110, 120, 130))
            cr = sum(p[0] for p in poly) // len(poly)
            cc = sum(p[1] for p in poly) // len(poly)
            nb = draw.textbbox((0, 0), r.get("name", "?"), font=fs)
            draw.text((cr - (nb[2] - nb[0]) // 2, cc - 9), r.get("name", "?"), fill=(30, 35, 45), font=fs)
        # overlay physical-element boxes (walls / columns) so the building
        # envelope and structure are visible, not just room footprints
        for el in f.get("plan_elements") or []:
            kind = el["kind"]
            if kind not in ("wall", "column", "pipe", "duct"):
                continue
            x0, y0, x1, y1 = el["bbox"][:4]
            if kind == "pipe":
                base = (52, 120, 168)
            elif kind == "duct":
                base = (124, 92, 168)
            else:
                base = (146, 154, 166) if kind == "wall" else (118, 126, 140)
            dark = _darken(base)
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            pb = [iso(x, y, z) for x, y in corners]
            pt = [iso(x, y, z + wall_h) for x, y in corners]
            for i in range(4):
                draw.polygon([pb[i], pb[(i + 1) % 4], pt[(i + 1) % 4], pt[i]], fill=dark)
            draw.polygon(pt, fill=base, outline=(100, 110, 122))
        lbl = _floor_label(f.get("floor_name", f"F{idx}"))
        lb = draw.textbbox((0, 0), lbl, font=fm)
        draw.text((cx - (lb[2] - lb[0]) // 2, base_cy - z + 6), lbl, fill=(60, 65, 75), font=fm)
    return img


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
        correction_title = "修正方案" if i18n.LANG == "zh" else "CORRECTION PLAN"
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

    title = "建筑剖面 · 楼层关联" if i18n.LANG == "zh" else "BUILDING SECTION · FLOOR CONNECTIONS"
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
            civ_lbl = f"建筑 {fc}" if i18n.LANG == "zh" else f"CIV {fc}"
            draw.text((bx2+8, y+15), civ_lbl, fill=(255,255,255), font=fs)
            bx2 += 90
        if fe > 0:
            draw.rounded_rectangle([bx2, y+12, bx2+80, y+38], radius=4, fill=C["orange"])
            eee_lbl = f"电气 {fe}" if i18n.LANG == "zh" else f"EEE {fe}"
            draw.text((bx2+8, y+15), eee_lbl, fill=(255,255,255), font=fs)
            bx2 += 90
        if fk > 0:
            draw.rounded_rectangle([bx2, y+12, bx2+90, y+38], radius=4, fill=C["red"])
            c_lbl = f"冲突 {fk}" if i18n.LANG == "zh" else f"CNFL {fk}"
            draw.text((bx2+8, y+15), c_lbl, fill=(255,255,255), font=fs)

        # Stairwell connecting block (left side, visual continuity)
        stair_x = bx + 20
        draw.rectangle([stair_x, y+48, stair_x+50, y+floor_h-8], fill=(255, 248, 235), outline=(200, 180, 140), width=1)
        stair_lbl = "楼梯" if i18n.LANG == "zh" else "STAIR"
        draw.text((stair_x+4, y+58), stair_lbl, fill=(140, 110, 60), font=fs)

        # Elevator/services shaft (right side, carries building-level risers)
        serv_x = bx + bw - 90
        draw.rectangle([serv_x, y+48, serv_x+70, y+floor_h-8], fill=(252, 238, 238), outline=(200, 160, 160), width=1)
        serv_lbl = "管井" if i18n.LANG == "zh" else "RISER"
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
        bld_lbl = f"全楼 {n_bld}" if i18n.LANG == "zh" else f"BLD {n_bld}"
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
            lbl = zh_name if i18n.LANG == "zh" else en_name
            draw.text((bx+bw+28, label_y), f"● {lbl}", fill=C["purple"], font=fs)
            label_y += 24

        # Arrow/label indicating these span all floors
        span_lbl = "↕ 跨楼层累积量" if i18n.LANG == "zh" else "↕ Cross-floor totals"
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
        lb = lb_zh if i18n.LANG == "zh" else lb_en
        draw.rectangle([lx, leg_y, lx+16, leg_y+16], fill=col)
        draw.text((lx+22, leg_y), lb, fill=(60, 65, 75), font=fs)
        lx += 90

    return img


# ---------------------------------------------------------------- crosscheck ----

CROSSCHECK_COLORS = {
    "pass":    (46, 139, 87),     # ✓ 绿
    "fail":    (211, 47, 47),     # ✗ 红
    "missing": (255, 140, 0),     # 漏 橙
    "extra":   (142, 107, 191),   # 多 紫
    "default": (176, 182, 190),   # 未参与比对 灰
}

_VERDICT_RANK = {"✗": 3, "漏": 2, "多": 2, "✓": 1}


def _aggregate_verdict(field_rows):
    """Worst verdict across a component's fields (✗ beats 漏 beats ✓)."""
    if not field_rows:
        return None
    return max(field_rows, key=lambda v: _VERDICT_RANK.get(v, 0))


def _dashed_rect(draw, box, color, width=3, dash=10):
    x0, y0, x1, y1 = box
    for x in range(int(x0), int(x1), dash * 2):
        draw.line([x, y0, min(x + dash, x1), y0], fill=color, width=width)
        draw.line([x, y1, min(x + dash, x1), y1], fill=color, width=width)
    for y in range(int(y0), int(y1), dash * 2):
        draw.line([x0, y, x0, min(y + dash, y1)], fill=color, width=width)
        draw.line([x1, y, x1, min(y + dash, y1)], fill=color, width=width)


def _compute_plan_transform(rooms, plan_elements, W=1800, H=1200,
                                dx1=60, dy1=110, dx2=None, dy2=None):
    """Compute (minx, miny, scale, ox, oy) so model coords map to pixel coords.

    Pixel formula: px = ox + (mx - minx) * scale
    Matches the layout used by ``render_room_plan`` for real-geometry plans.
    Falls back to plan_elements bbox if no room hulls available.
    Returns None if neither rooms nor plan_elements have real geometry.
    """
    if dx2 is None:
        dx2 = W - 670
    if dy2 is None:
        dy2 = H - 150
    aw, ah = dx2 - dx1, dy2 - dy1

    has_rooms = bool(rooms and all(r.get("hull") for r in rooms))
    has_plan = bool(plan_elements)

    if not has_rooms and not has_plan:
        return None

    pts = []
    if has_rooms:
        for r in rooms:
            for x, y in r["hull"]:
                pts.append((x, y))
    if has_plan:
        for el in plan_elements:
            x0, y0, x1, y1 = el["bbox"][:4]
            pts += [(x0, y0), (x1, y1)]
    if not pts:
        return None

    pts = [p for r in rooms for p in r["hull"]]
    for el in (plan_elements or []):
        x0, y0, x1, y1 = el["bbox"][:4]
        pts += [(x0, y0), (x1, y1)]
    if not pts:
        return None
    minx = min(p[0] for p in pts)
    maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    maxy = max(p[1] for p in pts)
    spanx = max(maxx - minx, 1e-6)
    spany = max(maxy - miny, 1e-6)
    scale = min((aw - 40) / spanx, (ah - 40) / spany)
    ox = dx1 + (aw - spanx * scale) / 2
    oy = dy1 + (ah - spany * scale) / 2
    return {"minx": minx, "miny": miny, "scale": scale,
            "ox": ox, "oy": oy, "W": W, "H": H,
            "dx1": dx1, "dy1": dy1, "dx2": dx2, "dy2": dy2}


def _to_px(mx, my, t):
    """Model coords -> pixel coords using transform t."""
    return (t["ox"] + (mx - t["minx"]) * t["scale"],
            t["oy"] + (my - t["miny"]) * t["scale"])


def _bbox_to_px(bbox, t):
    """Model bbox (x0,y0,x1,y1) -> pixel bbox (px0,py0,px1,py1)."""
    x0, y0, x1, y1 = bbox[:4]
    px0, py0 = _to_px(x0, y0, t)
    px1, py1 = _to_px(x1, y1, t)
    return (px0, py0, px1, py1)


def _render_elements_only_plan(plan_elements, floor_name="", W=1800, H=1200):
    """Render a plan image with only physical elements (no rooms).

    Used when the model has no room spaces (e.g. pure MEP / structural
    models). Returns (PIL image, transform_dict).
    """
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((36, 28, 22))

    title = f"楼层平面图  —  {_floor_label(floor_name)}" if floor_name else "楼层平面图"
    draw.rectangle([0, 0, W, 70], fill=(30, 35, 45))
    draw.text((40, 12), title, fill=(240, 245, 250), font=ft)

    t = _compute_plan_transform([], plan_elements, W=W, H=H,
                                dx1=60, dy1=110, dx2=W-60, dy2=H-150)
    if t and plan_elements:
        _draw_plan_elements(draw, plan_elements,
                            t["minx"], t["miny"], t["scale"], t["ox"], t["oy"])
    return img, t


def build_image_overlay_plan(rooms, plan_elements=None, floor_name="",
                             issues=None, verdict_map=None):
    """Interactive floor plan: Pillow-rendered base image + plotly hotspots.

    The visual quality is the same as the static plan (professional
    architectural style), and clicking/hovering hits transparent plotly
    shapes laid on top at matching pixel positions.

    Returns a plotly.graph_objects.Figure.
    """
    import plotly.graph_objects as go
    import base64
    import io

    has_rooms = bool(rooms and all(r.get("hull") for r in rooms))

    # 1. Render the high-quality base image
    if has_rooms:
        base_img, room_map = render_room_plan(rooms, floor_name, plan_elements)
    else:
        base_img, _ = _render_elements_only_plan(plan_elements, floor_name)

    # 2. Compute pixel transform (same as render_room_plan uses internally)
    t = _compute_plan_transform(rooms, plan_elements)
    if t is None:
        # No geometry at all — just show the placeholder image
        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()
        fig = go.Figure()
        fig.add_layout_image(
            dict(source=f"data:image/png;base64,{img_b64}",
                 x=0, y=base_img.height,
                 xref="x", yref="y",
                 sizex=base_img.width, sizey=base_img.height,
                 sizing="stretch", layer="below")
        )
        fig.update_layout(
            xaxis=dict(scaleanchor="y", scaleratio=1,
                       range=[0, base_img.width], showgrid=False,
                       zeroline=False, showticklabels=False),
            yaxis=dict(range=[0, base_img.height], showgrid=False,
                       zeroline=False, showticklabels=False),
            margin=dict(l=0, r=0, t=0, b=0),
            height=500, plot_bgcolor="white", paper_bgcolor="white",
        )
        return fig

    W, H = t["W"], t["H"]

    # 3. Build pixel-coord hotspots
    room_issue_map = {}
    if issues:
        for iss in issues:
            loc = iss.get("location") or iss.get("room_name") or ""
            sev = iss.get("severity", "info")
            if loc and (not room_issue_map.get(loc) or sev == "high"):
                room_issue_map[loc] = sev

    all_xs = []
    all_ys = []
    all_text = []
    all_custom = []

    # Room hotspots (polygon fill, transparent, clickable)
    for r in rooms:
        hull = r.get("hull") or []
        if not hull:
            continue
        name = r.get("name", "")
        rtype = r.get("type", "Unknown")
        rid = r.get("room_id") or r.get("id") or name
        area = r.get("room_area_sqm")
        sev = room_issue_map.get(name)

        px_poly = [_to_px(x, y, t) for x, y in hull]
        xs = [p[0] for p in px_poly] + [px_poly[0][0], None]
        ys = [p[1] for p in px_poly] + [px_poly[0][1], None]

        hover = f"<b>{name}</b><br>类型: {rtype}"
        if area:
            hover += f"<br>面积: {area:.1f} m²"
        if sev:
            hover += f"<br><span style='color:#d32f2f'><b>⚠️ {sev} 级问题</b></span>"

        n = len(xs)
        all_xs.extend(xs)
        all_ys.extend(ys)
        all_text.extend([hover] * n)
        all_custom.extend([rid] * n)

    # Plan element hotspots (rectangular bboxes)
    for el in (plan_elements or []):
        kind = el.get("kind", "unknown")
        eid = el.get("id") or el.get("global_id") or ""
        ename = el.get("name") or kind
        verdict = verdict_map.get(eid) if verdict_map else None

        px0, py0, px1, py1 = _bbox_to_px(el["bbox"], t)
        # Expand thin elements so they're easier to click
        dx = abs(px1 - px0)
        dy = abs(py1 - py0)
        pad = max(2.0, min(dx, dy) * 0.3)
        if dx < pad * 2:
            cx = (px0 + px1) / 2
            px0, px1 = cx - pad, cx + pad
        if dy < pad * 2:
            cy = (py0 + py1) / 2
            py0, py1 = cy - pad, cy + pad

        xs = [px0, px1, px1, px0, px0, None]
        ys = [py0, py0, py1, py1, py0, None]

        h = f"<b>{ename}</b><br>类型: {kind}"
        if verdict:
            vcol = {"✓": "#2e8b57", "✗": "#d32f2f",
                    "漏": "#ff8c00", "多": "#8e6bbf"}.get(verdict, "#888")
            h += f"<br>互检: <span style='color:{vcol}'><b>{verdict}</b></span>"
        if eid:
            h += f"<br><span style='color:#888;font-size:11px;'>ID: {eid[:24]}…</span>"

        n = len(xs)
        all_xs.extend(xs)
        all_ys.extend(ys)
        all_text.extend([h] * n)
        all_custom.extend([eid or f"{kind}_i"] * n)

    # 4. Encode base image
    buf = io.BytesIO()
    base_img.save(buf, format="PNG")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()

    # 5. Build figure
    fig = go.Figure()

    # Transparent hotspot layer
    fig.add_trace(go.Scatter(
        x=all_xs, y=all_ys,
        fill="toself",
        fillcolor="rgba(0,0,0,0.001)",  # nearly transparent, but clickable
        line=dict(width=0, color="rgba(0,0,0,0)"),
        mode="lines",
        name="hotspots",
        text=all_text,
        hoverinfo="text",
        customdata=all_custom,
        showlegend=False,
        hoveron="fills",
    ))

    # Base image as layout background
    fig.add_layout_image(
        dict(
            source=f"data:image/png;base64,{img_b64}",
            x=0, y=H,
            xref="x", yref="y",
            sizex=W, sizey=H,
            sizing="stretch",
            layer="below",
        )
    )

    fig.update_layout(
        xaxis=dict(
            scaleanchor="y", scaleratio=1,
            range=[0, W],
            showgrid=False, zeroline=False, showticklabels=False,
            showline=False, fixedrange=False,
        ),
        yaxis=dict(
            range=[0, H],
            showgrid=False, zeroline=False, showticklabels=False,
            showline=False, fixedrange=False,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=520,
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, system-ui, sans-serif",
            bordercolor="#e2e8f0",
        ),
        clickmode="event+select",
        dragmode="zoom",
    )

    return fig


def render_crosscheck_plan(rooms, plan_elements, verdict_map, floor_name="",
                           subtitle=""):
    """Floor plan with each physical element coloured by its crosscheck verdict.

    ``verdict_map`` maps GlobalId -> {"verdict": "✓"/"✗"/"漏"/"多",
    "fields": [(field, truth, extracted, verdict), ...]}. Elements with no
    crosscheck row stay grey (not compared). Returns a PIL image.
    """
    W, H = 1800, 1200
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((36, 28, 22))
    head = "互检平面标注图" if i18n.LANG == "zh" else "CROSSCHECK PLAN"
    title = f"{head}  —  {_floor_label(floor_name)}" if floor_name else head
    if subtitle:
        title += f"   ({subtitle})"
    draw.rectangle([0, 0, W, 70], fill=(30, 35, 45))
    draw.text((40, 12), title, fill=(240, 245, 250), font=ft)

    dx1, dy1, dx2, dy2 = 60, 110, W - 60, H - 150
    aw, ah = dx2 - dx1, dy2 - dy1

    pts = [p for r in rooms for p in (r.get("hull") or [])]
    for el in plan_elements:
        x0, y0, x1, y1 = el["bbox"][:4]
        pts += [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    if not pts:
        draw.text((dx1, dy1 + 40),
                  "无几何数据" if i18n.LANG == "zh" else "No geometry data",
                  fill=(150, 155, 165), font=fm)
        return img

    minx = min(p[0] for p in pts); maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts); maxy = max(p[1] for p in pts)
    spanx = max(maxx - minx, 1e-6); spany = max(maxy - miny, 1e-6)
    scale = min((aw - 40) / spanx, (ah - 40) / spany)
    ox = dx1 + (aw - spanx * scale) / 2
    oy = dy1 + (ah - spany * scale) / 2

    def tf(x, y):
        return (ox + (x - minx) * scale, oy + (y - miny) * scale)

    # 1) room footprints as light context
    for r in rooms:
        if not r.get("hull"):
            continue
        poly = [tf(x, y) for x, y in r["hull"]]
        fill = ROOM_TYPE_FILL.get(r.get("type", "Unknown"), ROOM_TYPE_FILL["Unknown"])
        draw.polygon(poly, fill=fill, outline=(205, 210, 218))
        cx = int(sum(p[0] for p in poly) / len(poly))
        cy = int(sum(p[1] for p in poly) / len(poly))
        nm = str(r.get("name", ""))
        nb = draw.textbbox((0, 0), nm, font=fs)
        draw.text((cx - (nb[2] - nb[0]) // 2, cy - 8), nm, fill=(120, 128, 138), font=fs)

    # 2) physical elements coloured by verdict (worst-first so ✗ draws on top)
    counts = {"✓": 0, "✗": 0, "漏": 0, "多": 0, "—": 0}
    label_queue = []
    ordered = sorted(plan_elements,
                     key=lambda el: _VERDICT_RANK.get(
                         _aggregate_verdict([f[3] for f in
                                             verdict_map.get(el.get("id"), {}).get("fields", [])]) or "", 0))
    for el in ordered:
        x0, y0, x1, y1 = el["bbox"][:4]
        sx0, sy0 = tf(x0, y0); sx1, sy1 = tf(x1, y1)
        info = verdict_map.get(el.get("id"))
        v = _aggregate_verdict([f[3] for f in info["fields"]]) if info else None
        if info is None or v is None:
            col, width = CROSSCHECK_COLORS["default"], 2
            counts["—"] += 1
        elif v == "✓":
            col, width = CROSSCHECK_COLORS["pass"], 3
            counts["✓"] += 1
        elif v == "✗":
            col, width = CROSSCHECK_COLORS["fail"], 6
            counts["✗"] += 1
            label_queue.append((sx0, sy0, sx1, sy1, info))
        elif v == "漏":
            col, width = CROSSCHECK_COLORS["missing"], 5
            counts["漏"] += 1
            label_queue.append((sx0, sy0, sx1, sy1, info))
        else:
            col, width = CROSSCHECK_COLORS["extra"], 4
            counts["多"] += 1
        kind = el["kind"]
        if kind == "window":
            if abs(sx1 - sx0) >= abs(sy1 - sy0):
                draw.line([sx0, (sy0 + sy1) / 2, sx1, (sy0 + sy1) / 2], fill=col, width=width)
            else:
                draw.line([(sx0 + sx1) / 2, sy0, (sx0 + sx1) / 2, sy1], fill=col, width=width)
        elif kind == "column":
            draw.ellipse([sx0, sy0, sx1, sy1], outline=col, width=width)
        elif v == "漏":
            _dashed_rect(draw, (sx0, sy0, sx1, sy1), col, width=3)
        else:
            draw.rectangle([sx0, sy0, sx1, sy1], outline=col, width=width)

    # 3) text labels for ✗ / 漏 (greedy vertical stagger to avoid overlap)
    used_y = []
    for sx0, sy0, sx1, sy1, info in label_queue:
        name = str(info.get("name", ""))[:18]
        bad = [f for f in info["fields"] if f[3] != "✓"]
        detail = " / ".join(f"{f[0]} {f[1]}→{f[2]}" for f in bad[:2])
        txt = f"{name}: {detail}"
        ty = int((sy0 + sy1) / 2)
        while any(abs(ty - u) < 26 for u in used_y):
            ty += 28
        used_y.append(ty)
        ex = int(sx1) + 6
        draw.line([int(sx1), int((sy0 + sy1) / 2), ex, ty], fill=(180, 60, 60), width=2)
        draw.text((ex + 4, ty - 10), txt, fill=(150, 30, 30), font=fs)

    # 4) legend + counts
    ly = H - 60
    lx = dx1
    legend = [("✓ 正确", "pass"), ("✗ 读错", "fail"),
              ("漏 漏读", "missing"), ("多 多读", "extra"), ("— 未比对", "default")]
    for lbl, key in legend:
        draw.rectangle([lx, ly, lx + 16, ly + 16], fill=CROSSCHECK_COLORS[key],
                       outline=(140, 150, 160))
        draw.text((lx + 22, ly), lbl, fill=(70, 75, 85), font=fs)
        lx += 150
    stat = (f"✓ {counts['✓']}   ✗ {counts['✗']}   漏 {counts['漏']}   "
            f"多 {counts['多']}   未比对 {counts['—']}")
    draw.text((dx1, H - 100), stat, fill=(60, 65, 75), font=fm)
    return img


# ---------------------------------------------------------------------------
# Plotly interactive floor plan (for results-page viewer)
# ---------------------------------------------------------------------------

def _rgb(c, alpha=1.0):
    """Convert (r,g,b) tuple to 'rgba(...)' string."""
    return f"rgba({c[0]},{c[1]},{c[2]},{alpha})"


def _plan_bounds(rooms, plan_elements):
    """Compute (minx, miny, maxx, maxy) from rooms + plan elements."""
    pts = []
    for r in rooms:
        for x, y in (r.get("hull") or []):
            pts.append((x, y))
    for el in (plan_elements or []):
        x0, y0, x1, y1 = el["bbox"][:4]
        pts += [(x0, y0), (x1, y1)]
    if not pts:
        return (0, 0, 10, 10)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def build_interactive_plan(rooms, plan_elements=None, floor_name="",
                          issues=None, verdict_map=None):
    """Build a plotly figure for an interactive floor plan.

    Style mirrors the existing Pillow-rendered plans: light warm room fills,
    dark walls, blue windows/doors. Clicking an element carries its id in
    customdata for the results-page detail panel.
    """
    import plotly.graph_objects as go

    fig = go.Figure()

    # ---- rooms: one trace per room type (shared legend) ----
    room_issue_map = {}
    if issues:
        for iss in issues:
            loc = iss.get("location") or iss.get("room_name") or ""
            sev = iss.get("severity", "info")
            if loc and (not room_issue_map.get(loc) or sev == "high"):
                room_issue_map[loc] = sev

    # Group rooms by type so each type is one trace (cleaner legend)
    rooms_by_type = {}
    for r in rooms:
        rtype = r.get("type", "Unknown")
        rooms_by_type.setdefault(rtype, []).append(r)

    for rtype, rlist in rooms_by_type.items():
        all_xs = []
        all_ys = []
        all_text = []
        all_custom = []
        base = ROOM_TYPE_FILL.get(rtype, ROOM_TYPE_FILL["Unknown"])

        for r in rlist:
            hull = r.get("hull") or []
            if not hull:
                continue
            name = r.get("name", "")
            rid = r.get("room_id") or r.get("id") or name
            area = r.get("room_area_sqm")
            sev = room_issue_map.get(name)

            xs = [p[0] for p in hull] + [hull[0][0], None]
            ys = [p[1] for p in hull] + [hull[0][1], None]
            all_xs.extend(xs)
            all_ys.extend(ys)

            h = f"<b>{name}</b><br>类型: {rtype}"
            if area:
                h += f"<br>面积: {area:.1f} m²"
            if sev:
                h += f"<br><span style='color:#d32f2f'><b>⚠️ {sev} 级问题</b></span>"
            all_text.extend([h] * len(xs))
            all_custom.extend([rid] * len(xs))

        if not all_xs:
            continue

        fig.add_trace(go.Scatter(
            x=all_xs, y=all_ys,
            fill="toself",
            fillcolor=_rgb(base, 0.9),
            line=dict(color="rgba(140,148,160,0.7)", width=1.2),
            mode="lines",
            name=rtype,
            text=all_text,
            hoverinfo="text",
            customdata=all_custom,
            legendgroup=f"room_{rtype}",
            showlegend=True,
            hoveron="fills",
        ))

    # ---- physical elements: per-kind traces, line-style (not filled rects) ----
    # Wall: dark grey thick line. Column: dark filled square.
    # Window: blue thin line. Door: blue dashed / half.
    # Railing: thin grey dash.

    els_by_kind = {}
    for el in (plan_elements or []):
        kind = el.get("kind", "unknown")
        els_by_kind.setdefault(kind, []).append(el)

    # Visual specs per kind
    kind_style = {
        "wall":    dict(color="#2d323d", width=5,  dash="solid",    showlegend=True,  filled=False),
        "column":  dict(color="#4a5060", width=1,  dash="solid",    showlegend=True,  filled=True),
        "window":  dict(color="#3b82c4", width=3,  dash="solid",    showlegend=True,  filled=False),
        "door":    dict(color="#2563eb", width=2.5, dash="dash",    showlegend=True,  filled=False),
        "railing": dict(color="#9aa3b2", width=1.5, dash="dot",     showlegend=True,  filled=False),
        "beam":    dict(color="#b8860b", width=2,  dash="solid",    showlegend=False, filled=False),
        "slab":    dict(color="#d4c4a8", width=1,  dash="solid",    showlegend=False, filled=True, fill_alpha=0.2),
        "pipe":    dict(color="#2980b9", width=3,  dash="solid",    showlegend=True,  filled=False),
        "duct":    dict(color="#8e6bb8", width=4,  dash="solid",    showlegend=True,  filled=False),
    }

    verdict_colors = {
        "✓": "#2e8b57",
        "✗": "#d32f2f",
        "漏": "#ff8c00",
        "多": "#8e6bbf",
    }

    draw_order = ["slab", "beam", "column", "railing", "wall", "window", "door", "duct", "pipe"]
    for kind in draw_order:
        els = els_by_kind.get(kind, [])
        if not els:
            continue
        style = kind_style.get(kind, kind_style["wall"])

        all_xs = []
        all_ys = []
        all_text = []
        all_custom = []

        for el in els:
            x0, y0, x1, y1 = el["bbox"][:4]
            eid = el.get("id") or el.get("global_id") or ""
            ename = el.get("name") or kind
            verdict = verdict_map.get(eid) if verdict_map else None

            # Use outline of the bbox for walls / windows / doors etc.
            # For thin elements (wall/window), we draw the full rectangle
            # so click target is bigger; but with thin line it still looks right.
            if style.get("filled"):
                # filled shape (column / slab)
                xs = [x0, x1, x1, x0, x0, None]
                ys = [y0, y0, y1, y1, y0, None]
            else:
                # just the 4 sides
                xs = [x0, x1, None, x1, x1, None, x1, x0, None, x0, x0, None]
                ys = [y0, y0, None, y0, y1, None, y1, y1, None, y1, y0, None]

            all_xs.extend(xs)
            all_ys.extend(ys)

            color = verdict_colors[verdict] if verdict and verdict in verdict_colors else style["color"]
            h = f"<b>{ename}</b><br>类型: {kind}"
            if verdict:
                h += f"<br>互检: <span style='color:{color}'><b>{verdict}</b></span>"
            if eid:
                h += f"<br><span style='color:#888;font-size:11px;'>ID: {eid[:24]}…</span>"
            all_text.extend([h] * len(xs))
            all_custom.extend([eid or f"{kind}_i"] * len(xs))

        fill_color = None
        if style.get("filled"):
            fill_color = style["color"]

        fig.add_trace(go.Scatter(
            x=all_xs, y=all_ys,
            fill="toself" if style.get("filled") else "none",
            fillcolor=_rgb(_hex_to_rgb(style["color"]), style.get("fill_alpha", 0.4)) if style.get("filled") else None,
            line=dict(
                color=style["color"],
                width=style["width"],
                dash=style.get("dash", "solid"),
            ),
            mode="lines",
            name=kind,
            text=all_text,
            hoverinfo="text",
            customdata=all_custom,
            legendgroup=kind,
            showlegend=style.get("showlegend", True),
            visible="legendonly" if kind in ("pipe", "duct", "slab", "beam") else True,
        ))

    # ---- layout ----
    minx, miny, maxx, maxy = _plan_bounds(rooms, plan_elements)
    span = max(maxx - minx, maxy - miny, 1e-6)
    pad = span * 0.06

    title = f"{_floor_label(floor_name)}" if floor_name else ""

    fig.update_layout(
        title=dict(
            text=f"<span style='font-size:15px;font-weight:700;color:#2a3140;'>{title}</span>"
                 f"<span style='font-size:12px;color:#8892a0;margin-left:10px;'>💡 点击构件查看详情</span>",
            x=0, xanchor="left",
        ),
        plot_bgcolor="#f5f7fa",
        paper_bgcolor="white",
        xaxis=dict(
            scaleanchor="y", scaleratio=1,
            range=[minx - pad, maxx + pad],
            showgrid=False, zeroline=False, showticklabels=False,
            showline=False,
        ),
        yaxis=dict(
            range=[miny - pad, maxy + pad],
            showgrid=False, zeroline=False, showticklabels=False,
            showline=False,
        ),
        margin=dict(l=4, r=4, t=32, b=4),
        height=500,
        legend=dict(
            orientation="v",
            yanchor="top", y=1,
            xanchor="right", x=1.0,
            font=dict(size=11, color="#4a5568"),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e2e8f0",
            borderwidth=1,
        ),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="white",
            font_size=12,
            font_family="Inter, system-ui, sans-serif",
            bordercolor="#e2e8f0",
        ),
        clickmode="event+select",
    )

    return fig


def _hex_to_rgb(hex_color):
    """Convert '#rrggbb' to (r,g,b) tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


