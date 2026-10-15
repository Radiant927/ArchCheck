# -*- coding: utf-8 -*-
"""A1 交互 viewer demo — 单文件 HTML：底图 + 可 hover/点击的构件热区。

读一个 IFC + 它的 crosscheck CSV，输出一个自包含的 HTML（底图 base64 内嵌）：
  - hover：光标变手型 + 浮出 tooltip（名称/IFC 类型/楼层/尺寸/互检状态）；
  - 点击：右侧面板显示完整详情（GlobalId、三轴尺寸、原始材质、互检字段表）；
  - 问题清单（互检分歧 + 本层规则问题）点条目，图上高亮定位（双向联动）；
  - 楼层切换。

用法:
  python scripts/build_viewer_demo.py <ifc> --crosscheck <csv> [--out <html>]
"""
import argparse
import base64
import csv
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ifcopenshell
from ifcopenshell.util import element as ifcutil

from bim.parser import parse_ifc, build_review_data
from core import drawing, engine
from core.i18n import _floor_label

KIND_ZH = {"wall": "墙体", "door": "门", "window": "窗", "column": "柱",
           "beam": "梁", "slab": "板", "railing": "栏杆", "pipe": "管道",
           "duct": "风管"}

VERDICT_COLOR = {"✓": "#2e8b57", "✗": "#d32f2f",
                 "漏": "#f08c00", "多": "#8e6bbf", "?": "#9aa3af"}

FIELD_ZH = {
    "厚度_m": "厚度 (m)", "长度_m": "长度 (m)", "宽度_m": "宽度 (m)",
    "高度_m": "高度 (m)", "直径_m": "直径 (m)", "间距_m": "间距 (m)",
    "面积_m2": "面积 (m²)", "Qto面积_m2": "面积-Qto (m²)", "房间类型": "房间类型",
    "计数_类整体": "计数（类整体）",
}

WORST = {"✗": 4, "漏": 3, "多": 3, "✓": 1, "?": 0}


def load_verdict_map(csv_path):
    """GlobalId -> {verdict, fields:[{field,truth,extracted,verdict}]}"""
    vmap = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            gid = row.get("global_id", "")
            if not gid or gid.startswith("__"):
                continue
            e = vmap.setdefault(gid, {"fields": []})
            e["fields"].append({
                "field": row.get("field", ""),
                "truth": row.get("truth_value", ""),
                "extracted": row.get("extracted_value", ""),
                "verdict": row.get("verdict", "?"),
            })
    for e in vmap.values():
        e["verdict"] = max((fld["verdict"] for fld in e["fields"]),
                           key=lambda v: WORST.get(v, 0))
    return vmap


def gather_ifc_meta(ifc_path, gids):
    """{gid: {ifc_type, material}}，按需要直接开模型取。"""
    m = ifcopenshell.open(str(ifc_path))
    meta = {}
    for gid in gids:
        try:
            e = m.by_guid(gid)
        except Exception:
            continue
        if e is None:
            continue
        mat_names = []
        try:
            for mm in (ifcutil.get_materials(e) or []):
                nm = getattr(mm, "Name", None)
                if nm:
                    mat_names.append(nm)
        except Exception:
            pass
        meta[gid] = {"ifc_type": e.is_a(),
                     "material": " / ".join(dict.fromkeys(mat_names)) or ""}
    return meta


def dims_text(kind, b):
    dx = abs(b[3] - b[0])
    dy = abs(b[4] - b[1])
    dz = abs(b[5] - b[2])
    if kind == "wall":
        t, ln = sorted((dx, dy))
        return f"厚 {t:.2f} × 长 {ln:.2f} m，高 {dz:.2f} m"
    if kind in ("door", "window"):
        t, w = sorted((dx, dy))
        return f"宽 {w:.2f} × 厚 {t:.2f} m，高 {dz:.2f} m"
    if kind == "column":
        return f"截面 {dx:.2f} × {dy:.2f} m，高 {dz:.2f} m"
    return f"{dx:.2f} × {dy:.2f} × {dz:.2f} m"


def pad_rect(px0, py0, px1, py1):
    w, h = abs(px1 - px0), abs(py1 - py0)
    pad = min(max(2.0, min(w, h) * 0.6), 14.0)
    if w < pad * 2:
        cx = (px0 + px1) / 2
        px0, px1 = cx - pad, cx + pad
    if h < pad * 2:
        cy = (py0 + py1) / 2
        py0, py1 = cy - pad, cy + pad
    return px0, py0, px1, py1


def _point_in_poly(px, py, poly):
    """射线法判断点是否在多边形内。poly 是 [x,y,x,y,...] 扁平列表。"""
    inside = False
    n = len(poly) // 2
    j = n - 1
    for i in range(n):
        xi, yi = poly[i * 2], poly[i * 2 + 1]
        xj, yj = poly[j * 2], poly[j * 2 + 1]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _poly_area(poly):
    """多边形面积（Shoelace 公式），poly = [x,y,x,y,...]。"""
    n = len(poly) // 2
    a = 0.0
    for i in range(n):
        x1, y1 = poly[i * 2], poly[i * 2 + 1]
        x2, y2 = poly[(i + 1) % n * 2], poly[(i + 1) % n * 2 + 1]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _poly_perimeter(poly):
    n = len(poly) // 2
    p = 0.0
    for i in range(n):
        x1, y1 = poly[i * 2], poly[i * 2 + 1]
        x2, y2 = poly[(i + 1) % n * 2], poly[(i + 1) % n * 2 + 1]
        p += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    return p


def build_floors(bdata, vmap, meta, world_scale):
    floors = []
    gids_for_issues = {}  # (floor_idx, gid) -> kind/name for rule-issue linking
    for fi, fl in enumerate(bdata.get("floors", [])):
        rooms = fl.get("rooms", []) or []
        pes = fl.get("plan_elements", []) or []
        if not rooms and not pes:
            continue
        fname = fl.get("floor_name") or fl.get("floor_id") or f"F{fi+1}"

        if rooms and all(r.get("hull") for r in rooms):
            base_img, _ = drawing.render_room_plan(rooms, fname, pes)
            t = drawing._compute_plan_transform(rooms, pes)
        else:
            base_img, t = drawing._render_elements_only_plan(pes, fname)
        if t is None:
            continue

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        room_json, element_json = [], []
        # 先收集房间的像素坐标多边形（用于点在多边形内判断）
        room_polys = []
        for r in rooms:
            hull = r.get("hull") or []
            if not hull:
                continue
            poly = []
            for x, y in hull:
                px, py = drawing._to_px(float(x), float(y), t)
                poly.extend([round(px, 1), round(py, 1)])
            room_polys.append((r, poly))

        for r, poly in room_polys:
            rid = r.get("id") or r.get("room_id") or r.get("name")
            perimeter_m = _poly_perimeter([p * (1.0 / t["scale"]) for p in poly]) \
                if t.get("scale") else None
            v = vmap.get(rid)
            room_json.append({
                "kind": "room", "id": rid,
                "name": r.get("name", ""), "rtype": r.get("type", "Unknown"),
                "area": round(float(r["room_area_sqm"]), 1) if r.get("room_area_sqm") else None,
                "perimeter": round(perimeter_m, 1) if perimeter_m else None,
                "poly": poly,
                "verdict": v["verdict"] if v else "",
                "fields": v["fields"] if v else [],
                "element_count": 0,
            })
            gids_for_issues[(fi, rid)] = ("room", r.get("name", ""))

        def _find_room(cx, cy):
            for i, (r, poly) in enumerate(room_polys):
                if _point_in_poly(cx, cy, poly):
                    return i, r
            return None, None

        for el in pes:
            gid = el.get("id") or el.get("global_id") or ""
            if not gid:
                continue
            b = [v * world_scale for v in el["bbox"]]
            bbox_px = drawing._bbox_to_px(b[:4] if world_scale != 1.0
                                          else el["bbox"][:4], t)
            px0, py0, px1, py1 = pad_rect(*bbox_px)
            cx, cy = (bbox_px[0] + bbox_px[2]) / 2, (bbox_px[1] + bbox_px[3]) / 2
            ri, rroom = _find_room(cx, cy)
            room_id = ""
            room_name = ""
            if rroom is not None:
                room_id = rroom.get("id") or rroom.get("room_id") or rroom.get("name")
                room_name = rroom.get("name", "")
                if ri is not None and ri < len(room_json):
                    room_json[ri]["element_count"] += 1
            v = vmap.get(gid)
            mm = meta.get(gid, {})
            element_json.append({
                "kind": el.get("kind", "unknown"), "id": gid,
                "name": el.get("name", "") or el.get("kind", ""),
                "ifc_type": mm.get("ifc_type", ""),
                "material": mm.get("material", ""),
                "dims": dims_text(el.get("kind", ""), b),
                "dims3": [round(abs(b[3] - b[0]), 3), round(abs(b[4] - b[1]), 3),
                          round(abs(b[5] - b[2]), 3)],
                "rect": [round(px0, 1), round(py0, 1),
                         round(px1, 1), round(py1, 1)],
                "verdict": v["verdict"] if v else "",
                "fields": v["fields"] if v else [],
                "room_id": room_id,
                "room_name": room_name,
            })
            gids_for_issues[(fi, gid)] = (el.get("kind", ""), el.get("name", ""))

        counters = defaultdict(int)
        for it in room_json + element_json:
            if it["verdict"]:
                counters[it["verdict"]] += 1
            else:
                counters["未比对"] += 1

        floors.append({
            "name": _floor_label(fname), "raw_name": fname,
            "W": t["W"], "H": t["H"], "img": img_b64,
            "rooms": room_json, "elements": element_json,
            "counters": dict(counters),
        })
    return floors, gids_for_issues


def collect_issues(bdata, floors, vmap):
    """互检分歧（跨楼层）+ 规则引擎问题（挂到房间名）。返回每楼层 issue 列表。"""
    per_floor = [[] for _ in floors]

    # 1) 互检分歧：verdict 非 ✓ 的构件/房间
    for fi, fl in enumerate(floors):
        for it in fl["rooms"] + fl["elements"]:
            if it["verdict"] in ("✗", "漏", "多"):
                bad = [f for f in it["fields"] if f["verdict"] != "✓"]
                detail = "；".join(
                    f"{FIELD_ZH.get(f['field'], f['field'])}：真值 {f['truth'] or '—'} → "
                    f"提取 {f['extracted'] or '—'}" for f in bad)
                label = "房间" if it["kind"] == "room" else KIND_ZH.get(it["kind"], it["kind"])
                per_floor[fi].append({
                    "target": it["id"], "kind": it["kind"],
                    "title": f"【互检·{it['verdict']}】{label} {it['name']}",
                    "detail": detail, "severity": "crosscheck",
                })

    # 2) 规则引擎问题：按楼层 + 房间名挂到房间
    res = engine.run_full_review(bdata)
    raw_issues = res.get("all_issues", [])
    floor_names = [f["raw_name"] for f in floors]
    for iss in raw_issues:
        fi = None
        target = None
        fname = iss.get("floor_name", "")
        fid = iss.get("floor_id", "")
        for i, fl in enumerate(floors):
            if (fname and fl["raw_name"] == fname) or (fid and fid in fl["raw_name"]):
                fi = i
                break
        if fi is None:
            continue
        loc = iss.get("location") or iss.get("room_name") or ""
        if loc:
            for r in floors[fi]["rooms"]:
                if r["name"] == loc:
                    target = r["id"]
                    break
        per_floor[fi].append({
            "target": target or "", "kind": "rule",
            "title": f"【{iss.get('rule_id', '')}】{iss.get('title', '')}",
            "detail": iss.get("description", "") or iss.get("clause", ""),
            "severity": iss.get("severity", "medium"),
        })
    return per_floor


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>互检平面交互查看器 · __MODEL__</title>
<style>
  :root { --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb; --bg:#f4f6f8;
          --green:#2e8b57; --red:#d32f2f; --orange:#f08c00; --purple:#8e6bbf;
          --blue:#2563eb; --head:#1e232d; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Microsoft YaHei","PingFang SC",Inter,system-ui,sans-serif;
         background:var(--bg); color:var(--ink); font-size:14px; }
  header { background:var(--head); color:#f0f5fa; padding:14px 24px; }
  header h1 { margin:0; font-size:18px; font-weight:700; }
  header .sub { margin-top:4px; font-size:12px; color:#9fb0c3; }
  .wrap { display:grid; grid-template-columns:minmax(0,1fr) 360px; gap:16px;
          padding:16px 24px 24px; align-items:start; }
  .tabs { display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap; }
  .tab { padding:6px 16px; border:1px solid var(--line); background:#fff; border-radius:6px;
         cursor:pointer; font-size:13px; user-select:none; }
  .tab.active { background:var(--head); color:#fff; border-color:var(--head); font-weight:600; }
  .card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px; }
  .plan-stats { display:flex; gap:16px; align-items:center; font-size:12.5px;
                color:var(--muted); margin:8px 2px 0; flex-wrap:wrap; }
  .badge { display:inline-flex; align-items:center; gap:5px; }
  .dot { width:10px; height:10px; border-radius:2px; display:inline-block; }
  .plan-box { position:relative; width:100%; aspect-ratio:3/2; border-radius:6px;
              overflow:hidden; background:#fff; }
  .plan-box img { width:100%; display:block; }
  .plan-box svg { position:absolute; inset:0; width:100%; height:100%; }
  .hot { cursor:pointer; }
  .hot.poly-room { fill:#2563eb; fill-opacity:0; stroke:#2563eb;
                   stroke-width:0; vector-effect:non-scaling-stroke; }
  .hot.poly-el { fill-opacity:0; stroke-width:0; vector-effect:non-scaling-stroke; }
  .hot:hover, .hot.hov { stroke-width:2.5px; }
  .poly-room:hover, .poly-room.hov { fill-opacity:.10; stroke-width:2px; }
  .hot.selected { stroke:#f59e0b !important; stroke-width:3px !important;
                  fill-opacity:.18 !important; filter:drop-shadow(0 0 6px rgba(245,158,11,.8)); }
  .hot.flagged { stroke-width:3px; }
  @keyframes pulse { 0%,100%{stroke-opacity:1} 50%{stroke-opacity:.15} }
  .hot.pulse { animation:pulse .5s ease-in-out 4; }
  .side { display:flex; flex-direction:column; gap:14px; }
  .side h3 { margin:0 0 8px; font-size:13px; font-weight:700; }
  .issue { border:1px solid var(--line); border-left-width:4px; border-radius:6px;
           padding:8px 10px; margin-bottom:8px; cursor:pointer; background:#fff; }
  .issue:hover { background:#f8fafc; }
  .issue .t { font-size:12.5px; font-weight:600; line-height:1.4; }
  .issue .d { font-size:11.5px; color:var(--muted); margin-top:3px; line-height:1.5; }
  .issue.crosscheck { border-left-color:var(--red); }
  .issue.high { border-left-color:var(--red); }
  .issue.medium { border-left-color:var(--orange); }
  .issue.low { border-left-color:#9aa3af; }
  .empty { color:var(--muted); font-size:12.5px; padding:6px 2px; }
  .kv { display:grid; grid-template-columns:88px 1fr; gap:6px 10px; font-size:12.5px;
        margin:8px 0; }
  .kv .k { color:var(--muted); }
  .kv .v { word-break:break-all; }
  .gid { font-family:Consolas,monospace; font-size:11.5px; background:#f1f5f9;
         padding:2px 6px; border-radius:4px; }
  table.fields { width:100%; border-collapse:collapse; font-size:12px; margin-top:8px; }
  table.fields th, table.fields td { border:1px solid var(--line); padding:4px 7px;
         text-align:left; }
  table.fields th { background:#f8fafc; font-weight:600; }
  .vbadge { display:inline-block; padding:0 7px; border-radius:10px; color:#fff;
            font-size:11px; font-weight:700; }
  .section-note { font-size:11.5px; color:var(--muted); line-height:1.6; }
  #tooltip { position:fixed; z-index:50; pointer-events:none; background:rgba(30,35,45,.96);
             color:#eef2f7; border-radius:8px; padding:9px 12px; font-size:12px;
             max-width:300px; box-shadow:0 6px 22px rgba(0,0,0,.25); display:none;
             line-height:1.55; }
  #tooltip .nm { font-weight:700; font-size:13px; margin-bottom:2px; }
  #tooltip .row { color:#c6d0dc; }
  #tooltip .vb { margin-left:4px; }
  .hint { font-size:11.5px; color:var(--muted); margin-top:6px; }
</style>
</head>
<body>
<header>
  <h1>互检平面交互查看器（A1 demo）</h1>
  <div class="sub">__MODEL__ · 悬停构件看摘要，点击看详情；右侧问题清单点条目可在图上定位</div>
</header>
<div class="wrap">
  <div>
    <div class="tabs" id="tabs"></div>
    <div class="card">
      <div class="plan-box" id="planbox">
        <img id="planimg" alt="floor plan">
        <svg id="svg" preserveAspectRatio="none"></svg>
      </div>
      <div class="plan-stats" id="stats"></div>
      <div class="hint">提示：墙面等细构件的可点区域已自动加宽；红框 = 互检分歧。浏览器 Ctrl/⌘ + 滚轮可缩放页面。</div>
    </div>
  </div>
  <div class="side">
    <div class="card">
      <h3>问题清单 <span id="issue-count" style="color:var(--muted);font-weight:400;"></span></h3>
      <div id="issuelist"></div>
    </div>
    <div class="card" id="detailcard">
      <h3>构件详情</h3>
      <div id="detail" class="empty">点击图上任意房间 / 墙 / 门 / 窗 / 柱查看详情。</div>
    </div>
  </div>
</div>
<div id="tooltip"></div>
<script>
const DATA = __DATA__;
const KIND_ZH = __KINDZH__;
const VCOL = __VCOL__;
const FIELD_ZH = __FIELDZH__;

let curFloor = 0, selectedId = null;
const svg = document.getElementById('svg');
const tooltip = document.getElementById('tooltip');

function vbadge(v) {
  if (!v) return '';
  const c = VCOL[v] || '#9aa3af';
  return `<span class="vbadge vb" style="background:${c}">${v}</span>`;
}

function renderTabs() {
  const el = document.getElementById('tabs');
  el.innerHTML = '';
  DATA.floors.forEach((f, i) => {
    const d = document.createElement('div');
    d.className = 'tab' + (i === curFloor ? ' active' : '');
    d.textContent = f.name;
    d.onclick = () => { curFloor = i; selectedId = null; render(); };
    el.appendChild(d);
  });
}

function renderStats() {
  const c = DATA.floors[curFloor].counters;
  const order = [['✓','正确',VCOL['✓']], ['✗','读错',VCOL['✗']],
                 ['漏','漏读',VCOL['漏']], ['多','多读',VCOL['多']],
                 ['未比对','未比对','#9aa3af']];
  document.getElementById('stats').innerHTML = order
    .filter(([k]) => c[k] != null)
    .map(([k, t, col]) => `<span class="badge"><span class="dot" style="background:${col}"></span>${t} ${c[k]}</span>`)
    .join('');
}

function polyPoints(poly) {
  let s = '';
  for (let i = 0; i < poly.length; i += 2) s += poly[i] + ',' + poly[i+1] + ' ';
  return s;
}

function renderPlan() {
  const f = DATA.floors[curFloor];
  document.getElementById('planimg').src = 'data:image/png;base64,' + f.img;
  svg.setAttribute('viewBox', `0 0 ${f.W} ${f.H}`);
  svg.innerHTML = '';

  const addHot = (it, isRoom) => {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    p.classList.add('hot', isRoom ? 'poly-room' : 'poly-el');
    p.dataset.id = it.id;
    if (isRoom) {
      p.setAttribute('points', polyPoints(it.poly));
    } else {
      const [x0, y0, x1, y1] = it.rect;
      p.setAttribute('points', `${x0},${y0} ${x1},${y0} ${x1},${y1} ${x0},${y1}`);
    }
    if (it.verdict && it.verdict !== '✓') {
      p.style.stroke = VCOL[it.verdict] || '#9aa3af';
      p.classList.add('flagged');
      p.style.fill = VCOL[it.verdict];
      if (isRoom) p.style.fillOpacity = .07;
    }
    p.addEventListener('mouseenter', e => {
      p.classList.add('hov');
      showTooltip(it, isRoom, e);
    });
    p.addEventListener('mousemove', moveTooltip);
    p.addEventListener('mouseleave', () => {
      p.classList.remove('hov');
      tooltip.style.display = 'none';
    });
    p.addEventListener('click', () => select(it.id));
    if (selectedId === it.id) p.classList.add('selected');
    svg.appendChild(p);
  };
  f.rooms.forEach(r => addHot(r, true));
  f.elements.forEach(e => addHot(e, false));
}

function showTooltip(it, isRoom, e) {
  const f = DATA.floors[curFloor];
  let rows = '';
  if (isRoom) {
    rows += `<div class="row">类型：${it.rtype || 'Unknown'}</div>`;
    if (it.area != null) rows += `<div class="row">面积：${it.area} m²</div>`;
  } else {
    rows += `<div class="row">IFC：${it.ifc_type || '—'}</div>`;
    rows += `<div class="row">尺寸：${it.dims}</div>`;
    if (it.material) rows += `<div class="row">材质：${it.material}</div>`;
    if (it.room_name) rows += `<div class="row">房间：${it.room_name}</div>`;
  }
  const bad = it.fields.filter(x => x.verdict !== '✓');
  let miss = '';
  if (bad.length) {
    miss = bad.map(x => `${FIELD_ZH[x.field] || x.field}：${x.truth || '—'} → ${x.extracted || '—'}`)
              .join('；');
  }
  tooltip.innerHTML =
    `<div class="nm">${it.name || '(未命名)'} ${vbadge(it.verdict)}</div>` +
    `<div class="row">楼层：${f.name}</div>` + rows +
    (miss ? `<div style="color:#fca5a5;margin-top:3px;">✗ ${miss}</div>` : '');
  tooltip.style.display = 'block';
  moveTooltip(e);
}

function moveTooltip(e) {
  const pad = 14;
  let x = e.clientX + pad, y = e.clientY + pad;
  const r = tooltip.getBoundingClientRect();
  if (x + r.width > window.innerWidth) x = e.clientX - r.width - pad;
  if (y + r.height > window.innerHeight) y = e.clientY - r.height - pad;
  tooltip.style.left = x + 'px';
  tooltip.style.top = y + 'px';
}

function findItem(id) {
  const f = DATA.floors[curFloor];
  return f.rooms.find(r => r.id === id) || f.elements.find(e => e.id === id);
}

function select(id, pulse) {
  selectedId = id;
  svg.querySelectorAll('.hot').forEach(p => {
    p.classList.toggle('selected', p.dataset.id === id);
    p.classList.remove('pulse');
  });
  const it = findItem(id);
  if (it) {
    renderDetail(it);
    if (pulse) {
      const p = svg.querySelector(`.hot[data-id="${CSS.escape(id)}"]`);
      if (p) p.classList.add('pulse');
    }
  }
  document.getElementById('detailcard').scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

function renderDetail(it) {
  const f = DATA.floors[curFloor];
  const isRoom = it.kind === 'room';
  let html = `<div style="font-size:15px;font-weight:700;">${it.name || '(未命名)'} ${vbadge(it.verdict)}</div>`;
  html += '<div class="kv">';
  html += `<div class="k">楼层</div><div class="v">${f.name}</div>`;
  if (isRoom) {
    html += `<div class="k">房间类型</div><div class="v">${it.rtype || 'Unknown'}</div>`;
    if (it.area != null) html += `<div class="k">面积</div><div class="v">${it.area} m²</div>`;
    if (it.perimeter != null) html += `<div class="k">周长</div><div class="v">${it.perimeter} m</div>`;
    html += `<div class="k">所含构件</div><div class="v">${it.element_count || 0} 件（墙/门/窗等）</div>`;
  } else {
    html += `<div class="k">IFC 类型</div><div class="v">${it.ifc_type || '—'}</div>`;
    html += `<div class="k">三轴尺寸</div><div class="v">${it.dims3.join(' × ')} m<br><span style="color:var(--muted)">${it.dims}</span></div>`;
    html += `<div class="k">原始材质</div><div class="v">${it.material || '—（模型未提供）'}</div>`;
    html += `<div class="k">所属房间</div><div class="v">`;
    if (it.room_id) {
      html += `<a href="javascript:void(0)" style="color:var(--blue);text-decoration:none;" `
           + `onclick="select('${it.room_id}')">${it.room_name || '查看'}</a>`;
    } else {
      html += '—（在公共区域/外部）';
    }
    html += '</div>';
  }
  html += `<div class="k">GlobalId</div><div class="v"><span class="gid">${it.id}</span></div>`;
  html += '</div>';
  if (it.fields.length) {
    html += '<table class.fields><tr><th>互检字段</th><th>真值</th><th>提取值</th><th>判定</th></tr>';
    for (const x of it.fields) {
      html += `<tr><td>${FIELD_ZH[x.field] || x.field}</td><td>${x.truth || '—'}</td>`
           + `<td>${x.extracted || '—'}</td><td>${vbadge(x.verdict)}</td></tr>`;
    }
    html += '</table>';
    document.getElementById('detail').className = '';
  } else {
    html += '<div class="section-note">该构件未参与互检比对。</div>';
  }
  if (!isRoom) {
    html += '<div class="section-note" style="margin-top:8px;">正式版将在此展示 AI 归一化材质类别（标注"AI 识别"）与该构件触发的审查规则条文；本 demo 为离线数据。</div>';
  }
  document.getElementById('detail').innerHTML = html;
}

function renderIssues() {
  const list = DATA.issues[curFloor] || [];
  document.getElementById('issue-count').textContent = `(${list.length})`;
  const el = document.getElementById('issuelist');
  if (!list.length) { el.innerHTML = '<div class="empty">本层无互检分歧、无规则违规。</div>'; return; }
  el.innerHTML = '';
  list.forEach((iss, idx) => {
    const d = document.createElement('div');
    d.className = `issue ${iss.severity || 'medium'}`;
    d.innerHTML = `<div class="t">${iss.title}</div><div class="d">${iss.detail || ''}</div>`;
    d.onclick = () => {
      renderTabs(); renderPlan(); renderStats();
      if (iss.target) {
        const f = DATA.floors[curFloor];
        const exists = f.rooms.some(r => r.id === iss.target)
                    || f.elements.some(e => e.id === iss.target);
        if (exists) select(iss.target, true);
      }
    };
    el.appendChild(d);
  });
}

function render() {
  renderTabs(); renderPlan(); renderStats(); renderIssues();
  document.getElementById('detail').innerHTML =
    '点击图上任意房间 / 墙 / 门 / 窗 / 柱查看详情。';
  document.getElementById('detail').className = 'empty';
}
render();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc")
    ap.add_argument("--crosscheck", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    ifc_path = Path(args.ifc)
    csv_path = Path(args.crosscheck)
    model_name = ifc_path.stem
    out = Path(args.out) if args.out else \
        ROOT / "presentation" / "2026-09-22" / "demo" / f"{model_name}_viewer_demo.html"
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] parse {ifc_path.name} ...")
    struct = parse_ifc(str(ifc_path))
    world_scale = float((struct.get("scale_info") or {}).get("world_scale", 1.0))
    bdata = build_review_data(struct)

    print("[2/4] verdicts + IFC meta ...")
    vmap = load_verdict_map(csv_path)
    floors, _ = build_floors(bdata, vmap, {}, world_scale)

    gids = set()
    for fl in floors:
        for e in fl["elements"]:
            gids.add(e["id"])
    meta = gather_ifc_meta(ifc_path, gids)
    for fl in floors:
        for e in fl["elements"]:
            m = meta.get(e["id"], {})
            e["ifc_type"] = m.get("ifc_type", "")
            e["material"] = m.get("material", "")

    print("[3/4] issues ...")
    issues = collect_issues(bdata, floors, vmap)

    print("[4/4] html ...")
    data = {"floors": floors, "issues": issues}
    html = (HTML_TEMPLATE
            .replace("__MODEL__", model_name)
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)
                     .replace("</", "<\\/"))
            .replace("__KINDZH__", json.dumps(KIND_ZH, ensure_ascii=False))
            .replace("__VCOL__", json.dumps(VERDICT_COLOR, ensure_ascii=False))
            .replace("__FIELDZH__", json.dumps(FIELD_ZH, ensure_ascii=False)))
    out.write_text(html, encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    print(f"done -> {out}  ({size_kb} KB, {len(floors)} floors)")


if __name__ == "__main__":
    main()
