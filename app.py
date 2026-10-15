"""
ArchCheck — Building Plan Automated Review Platform
Multi-floor support · Standard switching (CN GB / SG FC23)
"""
import io
import json
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from PIL import Image

# 3D viewer 点击事件桥接组件（接收 iframe postMessage → 传给 Python）
_bridge_path = Path(__file__).resolve().parent / "web" / "viewer_bridge"
_click_bridge = components.declare_component("viewer_click_bridge", path=str(_bridge_path))

from core import engine
import core.i18n as i18n
from core.config import C, OUTPUT
from core.drawing import (generate_sample_image, annotate_image,
                          generate_correction_image, generate_building_section,
                          generate_building_3d, render_room_plan, annotate_room_plan,
                          _fix_map, build_image_overlay_plan)
from core.report import generate_report
from core.i18n import _room_type_label, _floor_label
from core.engine import DEMO_DATA, run_full_review
from bim.parser import parse_ifc, build_review_data
from agents.enricher import enrich_review_data
import llm.client as llm
from web.serve import get_server
from risk import csv_io as risk_csv

# 预启动 3D viewer 的静态文件服务（app 启动时就起好，避免懒加载导致 404）
VIEWER_SERVER = get_server(port=8765)
VIEWER_BASE = VIEWER_SERVER.base_url + "/viewer"

# ============================================================
# PAGE CONFIG — must be first Streamlit call
# ============================================================
st.set_page_config(
    page_title="ArchCheck — Building Plan Review",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
.aicher-band .band-bld   {{ flex:1; background:{C["purple"]}; }}
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
.aicher-stat.blue   .value {{ color:{C["blue"]}; }}
.aicher-stat.orange .value {{ color:{C["orange"]}; }}
.aicher-stat.purple .value {{ color:{C["purple"]}; }}
.aicher-stat.red    .value {{ color:{C["red"]}; }}
.aicher-stat.green  .value {{ color:{C["green"]}; }}
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
.issue-card.civil    {{ border-left:4px solid {C["blue"]}; }}
.issue-card.eee      {{ border-left:4px solid {C["orange"]}; }}
.issue-card.building {{ border-left:4px solid {C["purple"]}; background:#F8F5FC; }}
.issue-card.conflict {{ border-left:4px solid {C["red"]}; background:#FEF2F2; }}
.card-title {{ font-weight:700; font-size:15px; }}
.card-desc {{ font-size:14px; color:#6B7480; margin-top:4px; }}
.card-meta {{ font-size:13px; color:#9BA3AB; margin-top:4px; font-family:monospace; }}
.tag {{ display:inline-block; margin-left:8px; padding:1px 8px; border-radius:2px; font-size:12px; font-weight:600; }}
.tag-disc-civil {{ background:{C["blue"]}18; color:{C["blue"]}; }}
.tag-disc-eee {{ background:{C["orange"]}18; color:{C["orange"]}; }}
.tag-disc-building {{ background:{C["purple"]}18; color:{C["purple"]}; }}
.tag-disc-structural {{ background:{C["green"]}18; color:{C["green"]}; }}
.tag-disc-mep {{ background:{C["blue"]}22; color:#1f6f8b; }}
.tag-disc-accessibility {{ background:#B0804018; color:#8a6d00; }}
.tag-disc-conflict {{ background:{C["red"]}18; color:{C["red"]}; }}
.tag-sev-high {{ background:{C["red"]}18; color:{C["red"]}; }}
.tag-sev-medium {{ background:{C["orange"]}18; color:{C["orange"]}; }}
.tag-sev-low {{ background:{C["silver"]}18; color:{C["silver"]}; }}
.tag-sev-missing {{ background:{C["silver"]}18; color:{C["silver"]}; }}
.tag-sev-predictive {{ background:{C["purple"]}18; color:{C["purple"]}; }}
.sev-badge {{
    display:inline-block; margin-left:8px; padding:1px 8px; border-radius:2px;
    font-size:12px; font-weight:600;
}}
.floor-tag {{
    display:inline-block; padding:2px 8px; border-radius:2px; font-size:11px;
    font-weight:600; background:{C["text"]}0a; color:{C["muted"]};
    letter-spacing:0.06em; margin-left:8px;
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
.std-pill {{
    display:inline-flex; align-items:center; gap:6px; padding:6px 14px;
    border-radius:4px; font-weight:700; font-size:14px; cursor:pointer;
    border:2px solid transparent; transition: all 0.15s;
}}
.std-pill.active {{
    border-color:{C["text"]}; background:{C["text"]}; color:#FFFFFF;
}}
.std-pill.inactive {{
    border-color:{C["border"]}; background:#FFFFFF; color:{C["text"]};
}}
</style>""", unsafe_allow_html=True)

# INIT SESSION STATE
# ============================================================
defaults = {
    "page": "upload",
    "uploaded_image": None,
    "civil_results": [],
    "eee_results": [],
    "building_results": [],
    "structural_results": [],
    "mep_results": [],
    "predictive_results": [],
    "predictive_ranking": [],
    "predictive_monitor": {},
    "discipline_checked": {},
    "conflicts": [],
    "all_issues": [],
    "building_data": None,
    "review_loading": False,
    "standard": "cn",
    "active_floor": 0,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


def goto(page):
    """Programmatic navigation. `pending_page` is consumed at the top of the
    next run — before the sidebar nav radio is instantiated — so the radio's
    stored value is set in time and it won't bounce the page back."""
    st.session_state.page = page
    st.session_state.pending_page = page


def _point_in_poly(px, py, hull):
    """射线法：点 (px,py) 是否在 hull（[(x,y),...]，模型坐标）内。"""
    inside = False
    n = len(hull)
    j = n - 1
    for i in range(n):
        xi, yi = hull[i][0], hull[i][1]
        xj, yj = hull[j][0], hull[j][1]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _room_element_gids(data_version, bdata):
    """{房间名: {"gids": [...], "cam": (vx, vy, vz, radius)}}

    构件中心点落在房间轮廓内即归属该房间。
    用于「定位到 3D」：web-ifc 无法构建部分 Archicad 导出的 IfcSpace 几何，
    因此改为高亮房间内的真实构件（墙/门/窗），并由 Python 侧算好相机目标
    —— viewer 的 scene 是 Y-up，IFC 是 Z-up，换算：vx=x, vy=z, vz=-y。
    """
    out = {}
    for fl in bdata.get("floors", []):
        rooms = [r for r in fl.get("rooms", []) if r.get("hull")]
        if not rooms:
            continue
        # 墙/门天生坐在房间 hull 之间的缝隙里 → 把 hull 从质心向外放大，
        # 使边界构件也能归入相邻房间。
        scaled = []
        for r in rooms:
            h = r["hull"]
            cx = sum(p[0] for p in h) / len(h)
            cy = sum(p[1] for p in h) / len(h)
            f = 1.25
            scaled.append((str(r.get("name", "")),
                           [(cx + (p[0] - cx) * f, cy + (p[1] - cy) * f) for p in h]))
        for el in fl.get("plan_elements", []):
            bbox = el.get("bbox")
            gid = el.get("id") or el.get("global_id")
            if not bbox or not gid:
                continue
            # bbox = (x0,y0,x1,y1,z0,z1)
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            for nm, hull in scaled:
                if _point_in_poly(cx, cy, hull):
                    rec = out.setdefault(nm, {"gids": [], "bb": [], "kinds": {}})
                    if gid not in rec["gids"]:
                        rec["gids"].append(gid)
                        rec["bb"].append(bbox)
                        rec["kinds"][gid] = el.get("kind", "")

    # 算相机目标 + 标记框（模型坐标 → viewer 坐标：vx=x, vy=z, vz=-y）
    # 注意 bbox 顺序是 (x0, y0, x1, y1, z0, z1)
    result = {}
    for nm, rec in out.items():
        bb = rec["bb"]
        if bb:
            xs = [b[0] for b in bb] + [b[2] for b in bb]
            ys = [b[1] for b in bb] + [b[3] for b in bb]
            zs = [b[4] for b in bb] + [b[5] for b in bb]
            # 模型坐标 bbox
            mx0, mx1 = min(xs), max(xs)
            my0, my1 = min(ys), max(ys)
            mz0, mz1 = min(zs), max(zs)
            # viewer 坐标（Y-up）
            vx0, vx1 = mx0, mx1
            vy0, vy1 = mz0, mz1
            vz0, vz1 = -my1, -my0
            span = max(vx1 - vx0, vy1 - vy0, vz1 - vz0)
            radius = span * 1.2 + 4.0
            cam = ((vx0 + vx1) / 2, (vy0 + vy1) / 2, (vz0 + vz1) / 2, radius)
            box = (vx0, vy0, vz0, vx1, vy1, vz1)
        else:
            cam = None
            box = None
        # 每个构件单独转 viewer 坐标，便于按类型收敛后重算 cam/box
        vboxes = {}
        for gid, b in zip(rec["gids"], rec["bb"]):
            vboxes[gid] = (b[0], b[4], -b[3], b[2], b[5], -b[1])
        result[nm] = {"gids": rec["gids"], "cam": cam, "box": box,
                      "kinds": rec["kinds"], "vboxes": vboxes}
    return result


def _build_gid_bbox_map(bdata):
    """全局 gid → viewer 坐标 bbox 映射。
    viewer 是 Y-up，IFC 是 Z-up：vx=x, vy=z, vz=-y。
    用于 3D viewer 批量绘制违规构件标记。
    """
    m = {}
    for fl in bdata.get("floors", []):
        for el in fl.get("plan_elements", []):
            gid = el.get("global_id") or el.get("id")
            bbox = el.get("bbox")
            if not gid or not bbox or len(bbox) < 6:
                continue
            # bbox 顺序 (x0, y0, x1, y1, z0, z1) → viewer 的 (vx0, vy0, vz0, vx1, vy1, vz1)
            x0, y0, x1, y1, z0, z1 = bbox[:6]
            m[gid] = (x0, z0, -y1, x1, z1, -y0)
    return m


def _build_gid_room_map(bdata):
    """gid → 房间名 的反向映射。"""
    room_gids = _room_element_gids(0, bdata)
    m = {}
    for room_name, rec in room_gids.items():
        for gid in rec.get("gids", []):
            m[gid] = room_name
    return m


def _collect_violation_markers(bdata, all_issues):
    """收集 3D viewer 用的违规构件标记列表。

    每条：{gid, severity, rule_id, title}；若 Python 侧有 bbox 则附带 bbox
    （viewer 有 bbox 时直接画，没有就按构件网格自己算——大模型没有 plan_elements
     也能着色）。
    """
    room_gids = _room_element_gids(0, bdata)
    gid_bbox = _build_gid_bbox_map(bdata)
    seen = set()
    markers = []

    def _add(gid, iss):
        if not gid or gid in seen:
            return
        seen.add(gid)
        _sev = iss.get("severity", "Medium")
        # the built viewer bundle only maps High/Medium/Low; render predictive
        # findings in the same orange as Medium (the app UI keeps its own label).
        _sev = {"Predictive": "Medium"}.get(_sev, _sev)
        m = {
            "gid": gid,
            "severity": _sev,
            "rule_id": iss.get("rule_id", ""),
            "title": iss.get("title", ""),
        }
        if gid in gid_bbox:
            m["bbox"] = list(gid_bbox[gid])
        markers.append(m)

    for iss in all_issues:
        eids = iss.get("element_global_ids") or []
        if eids:
            for gid in eids:
                _add(gid, iss)
            continue
        loc = (iss.get("location", "") or "").strip()
        rec = room_gids.get(loc)
        if not rec:
            continue
        rule = engine.find_rule(iss.get("rule_id", ""))
        want_kind = _RULE_FIELD_KIND.get((rule or {}).get("field", ""))
        for gid in rec.get("gids", []):
            if want_kind and rec.get("kinds", {}).get(gid) != want_kind:
                continue
            _add(gid, iss)
    return markers


# 房间级规则字段 → 对应物理构件类型：用于把定位从"整个房间"收敛到"该类型的构件"
# （如门宽不足 → 只高亮房间里的门，而不是整个房间的所有构件）。
_RULE_FIELD_KIND = {
    "door_width_m": "door",
    "window_width_m": "window",
    "window_height_m": "window",
    "wall_thickness_m": "wall",
    "railing_height_m": "railing",
}


def _collect_element_info(bdata, all_issues):
    """gid → {name, kind, floor, material, material_ai, issues:[...]}

    供 3D viewer 点击构件时展示完整信息（尺寸由前端从几何算，这里给材料/楼层/触发规则）。
    房间级规则按"字段→构件类型"收敛后挂到房间内对应构件上。
    """
    info = {}
    enrich_el = (bdata.get("_enrichment") or {}).get("elements", {}) or {}
    room_gids = _room_element_gids(0, bdata)

    for fl in bdata.get("floors", []):
        fname = _floor_label(fl.get("floor_name", ""))
        for pe in fl.get("plan_elements", []):
            gid = pe.get("id")
            if not gid:
                continue
            rec = info.setdefault(gid, {})
            rec["name"] = pe.get("name", "")
            rec["kind"] = pe.get("kind", "")
            rec["floor"] = fname
            bb = pe.get("bbox")
            if bb and len(bb) >= 6:
                # bbox = (x0,y0,x1,y1,z0,z1)
                rec["dims"] = [round(abs(bb[2] - bb[0]), 2),
                               round(abs(bb[3] - bb[1]), 2),
                               round(abs(bb[5] - bb[4]), 2)]
        for se in fl.get("structural_elements", []):
            gid = se.get("id")
            if not gid:
                continue
            rec = info.setdefault(gid, {})
            rec.setdefault("name", se.get("name", ""))
            rec.setdefault("kind", se.get("element_type", ""))
            rec.setdefault("floor", fname)
            mc = se.get("material_class")
            if mc and mc != "unknown":
                rec["material"] = mc
                tr = enrich_el.get(gid) or {}
                rec["material_ai"] = (tr.get("source") == "ai")

    def _add_issue(gid, iss):
        rec = info.setdefault(gid, {})
        rec.setdefault("issues", []).append({
            "rule_id": iss.get("rule_id", ""), "title": iss.get("title", ""),
            "severity": iss.get("severity", ""), "code_ref": iss.get("code_ref", ""),
        })

    for iss in all_issues:
        eids = iss.get("element_global_ids") or []
        if eids:
            for gid in eids:
                _add_issue(gid, iss)
            continue
        # 房间级规则：收敛到房间内对应类型的构件
        loc = (iss.get("location", "") or "").strip()
        rec = room_gids.get(loc)
        if not rec:
            continue
        rule = engine.find_rule(iss.get("rule_id", ""))
        want_kind = _RULE_FIELD_KIND.get((rule or {}).get("field", ""))
        for gid in rec.get("gids", []):
            if want_kind and rec.get("kinds", {}).get(gid) != want_kind:
                continue
            _add_issue(gid, iss)
    return info


def _viewer_cam_box(vboxes):
    """从一组 viewer 坐标 bbox 算相机目标与标记框。

    返回 (cam=(cx,cy,cz,radius), box=(x0,y0,z0,x1,y1,z1)) 或 (None, None)。
    """
    vboxes = [b for b in (vboxes or []) if b and len(b) >= 6]
    if not vboxes:
        return None, None
    xs = [b[0] for b in vboxes] + [b[3] for b in vboxes]
    ys = [b[1] for b in vboxes] + [b[4] for b in vboxes]
    zs = [b[2] for b in vboxes] + [b[5] for b in vboxes]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    z0, z1 = min(zs), max(zs)
    span = max(x1 - x0, y1 - y0, z1 - z0)
    radius = span * 1.2 + 4.0
    cam = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, radius)
    box = (x0, y0, z0, x1, y1, z1)
    return cam, box


def _room_hull_meta(bdata):
    """房间名 → {gid, cam, box}（viewer 坐标），由房间 hull 轮廓 + 该层 z 范围算出。

    用于房间内没有可高亮构件时的兜底定位（画房间框 + 相机聚焦到房间）。
    """
    out = {}
    for fl in bdata.get("floors", []):
        zs = []
        for pe in fl.get("plan_elements", []):
            b = pe.get("bbox")
            if b and len(b) >= 6:
                zs += [b[4], b[5]]  # bbox = (x0,y0,x1,y1,z0,z1)
        z0, z1 = (min(zs), max(zs)) if zs else (0.0, 3.0)
        for r in fl.get("rooms", []):
            hull = r.get("hull")
            if not hull:
                continue
            xs = [p[0] for p in hull]
            ys = [p[1] for p in hull]
            mx0, mx1 = min(xs), max(xs)
            my0, my1 = min(ys), max(ys)
            # 模型坐标 → viewer 坐标（Y-up）：vx=x, vy=z, vz=-y
            vbox = (mx0, z0, -my1, mx1, z1, -my0)
            cam, box = _viewer_cam_box([vbox])
            out[str(r.get("name", ""))] = {
                "gid": r.get("id") or r.get("global_id") or "",
                "cam": cam, "box": box,
            }
    return out


def _collect_room_manifest(bdata):
    """导出给 3D viewer 导航用的房间清单（viewer 坐标）。

    {floors: [{floor, elevation, rooms: [{gid, name, type, area, vbox}]}]}
    有 hull/plan_elements 的小模型附 viewer 坐标 vbox；大模型或 Archicad 无
    几何的空间只给名字，viewer 侧靠 IFC 空间树兜底取包围盒。
    """
    floors_out = []
    for fl in bdata.get("floors", []):
        fname = fl.get("floor_name", "")
        zs = []
        for pe in fl.get("plan_elements", []):
            b = pe.get("bbox")
            if b and len(b) >= 6:
                zs += [b[4], b[5]]  # bbox = (x0,y0,x1,y1,z0,z1)
        z0, z1 = (min(zs), max(zs)) if zs else (0.0, 3.0)
        rooms_out = []
        for r in fl.get("rooms", []):
            gid = r.get("id") or r.get("global_id") or ""
            rec = {
                "gid": gid,
                "name": str(r.get("name", "")),
                "type": r.get("type", ""),
                "area": r.get("room_area_sqm"),
            }
            hull = r.get("hull")
            if hull:
                xs = [p[0] for p in hull]
                ys = [p[1] for p in hull]
                mx0, mx1 = min(xs), max(xs)
                my0, my1 = min(ys), max(ys)
                # 模型坐标 → viewer 坐标（Y-up）：vx=x, vy=z, vz=-y
                rec["vbox"] = [round(mx0, 3), round(z0, 3), round(-my1, 3),
                               round(mx1, 3), round(z1, 3), round(-my0, 3)]
            rooms_out.append(rec)
        floors_out.append({"floor": fname, "elevation": fl.get("elevation"),
                           "rooms": rooms_out})
    return {"floors": floors_out}


def _goto_target_for_issue(iss, room_gids, gid_bbox, room_hull=None):
    """为一条审查问题计算 3D 定位目标。

    返回 (hash_str, cmd_dict)；两者都为空时返回 (None, None)。
    hash 用于 iframe 初始加载，cmd 用于 postMessage 实时推送。
    """
    import urllib.parse as _up
    room_hull = room_hull or {}
    room_name = (iss.get("location", "") or "").strip()
    floor_name = (iss.get("floor_name", "") or "").strip()
    is_building = (iss.get("type") == "building")
    ts = int(time.time() * 1000)

    def _mk_highlight(gids, cam, box):
        gids = list(gids or [])[:80]
        cmd = {"type": "highlight", "globalIds": gids, "_reqId": ts}
        h = f"cmd=highlight&ids={_up.quote(';'.join(gids))}" if gids else "cmd=highlight&ids="
        if cam:
            cmd["cam"] = f"{cam[0]:.2f},{cam[1]:.2f},{cam[2]:.2f},{cam[3]:.2f}"
            h += f"&cam={cmd['cam']}"
        if box:
            cmd["box"] = (f"{box[0]:.2f},{box[1]:.2f},{box[2]:.2f},"
                          f"{box[3]:.2f},{box[4]:.2f},{box[5]:.2f}")
            h += f"&box={cmd['box']}"
        return h + f"&ts={ts}", cmd

    # 全楼级问题：无具体位置 → 显示全楼 + 相机拉到全局
    if is_building:
        return "", {"type": "fitAll", "_reqId": ts}

    # ① 构件级精确：规则引擎给出的物理构件 GlobalId
    # （不要求 Python 侧有 bbox —— viewer 会按实际选中网格自己算相机）
    eids = [g for g in (iss.get("element_global_ids") or []) if g]
    if eids:
        cam, box = None, None
        if eids[0] in gid_bbox:  # 有 bbox 时顺带给出（更稳）
            bb = [gid_bbox[g] for g in eids if g in gid_bbox]
            cam, box = _viewer_cam_box(bb)
        return _mk_highlight(eids, cam, box)

    # ② 房间级：优先房间内构件（按规则字段收敛到对应类型）
    rec = room_gids.get(room_name, {}) if room_name else {}
    gids = list(rec.get("gids", []))
    cam = rec.get("cam")
    box = rec.get("box")
    rule = engine.find_rule(iss.get("rule_id", ""))
    want_kind = _RULE_FIELD_KIND.get((rule or {}).get("field", ""))
    if want_kind and gids:
        kinds = rec.get("kinds", {})
        vbm = rec.get("vboxes", {})
        sub = [g for g in gids if kinds.get(g) == want_kind]
        if sub:
            gids = sub
            cam, box = _viewer_cam_box([vbm[g] for g in sub if g in vbm])
    if gids:
        return _mk_highlight(gids, cam, box)

    # ③ 房间内无构件 → 用房间自身 GlobalId + hull 轮廓框兜底
    hull_rec = room_hull.get(room_name) if room_name else None
    if hull_rec:
        return _mk_highlight([hull_rec.get("gid", "")], hull_rec.get("cam"), hull_rec.get("box"))

    # ④ 楼层级
    if floor_name and floor_name != "?":
        cmd = {"type": "gotoFloor", "floorName": floor_name, "_reqId": ts}
        h = f"cmd=gotoFloor&floor={_up.quote(floor_name)}&ts={ts}"
        return h, cmd

    # ⑤ 实在没有位置 → 全楼
    return "", {"type": "fitAll", "_reqId": ts}


def _clash_target_cmd(c):
    """冲突条目 → 双构件高亮指令（MEP 红 / 结构蓝），无 GID 时返回 None。"""
    mep_gid = c.get("mep_gid", "")
    vs_gid = c.get("vs_gid", "")
    if not mep_gid or not vs_gid:
        return None
    ts = int(time.time() * 1000)
    cmd = {"type": "highlight", "globalIds": [mep_gid, vs_gid],
           "colors": ["mep", "struct"], "_reqId": ts}
    ov = c.get("overlap")
    if ov and len(ov) >= 6:
        # overlap 是模型坐标 (x0,y0,x1,y1,z0,z1)
        x0, y0, x1, y1, z0, z1 = ov[:6]
        cam, box = _viewer_cam_box([(x0, z0, -y1, x1, z1, -y0)])
        if cam:
            cmd["cam"] = f"{cam[0]:.2f},{cam[1]:.2f},{cam[2]:.2f},{cam[3]:.2f}"
        if box:
            cmd["box"] = (f"{box[0]:.2f},{box[1]:.2f},{box[2]:.2f},"
                          f"{box[3]:.2f},{box[4]:.2f},{box[5]:.2f}")
    return cmd


_NL_SYS = (
    "你是建筑合规审查平台的查询解析器。把用户的自然语言问题解析成 JSON 过滤条件。\n"
    "可用字段（无则填 null）：\n"
    '- discipline: "civil"|"eee"|"structural"|"mep"|"building"|"accessibility"\n'
    '- keyword: 匹配规则标题/描述的关键词（如 "门宽"、"疏散"、"面积"、"墙厚"、"管道"）\n'
    '- severity: "High"|"Medium"|"Low"|"Missing"|"Predictive"\n'
    '- floor: 楼层名关键词\n'
    "只输出 JSON，不要任何解释。无法理解时输出 {\"error\": \"原因\"}。\n"
    "示例：\n"
    '问题：找出所有宽度不足的疏散门 → {"discipline": null, "keyword": "门宽", "severity": null, "floor": null}\n'
    '问题：二层有哪些结构问题 → {"discipline": "structural", "keyword": null, "severity": null, "floor": "二层"}'
)


def _nl_parse_query(q):
    """自然语言 → 结构化过滤条件。返回 (spec, err)。"""
    if not llm.available():
        return None, "AI 未配置，无法解析自然语言"
    txt = llm.chat(_NL_SYS, f"问题：{q}")
    if not txt:
        return None, "AI 无响应"
    import re as _re
    m = _re.search(r"\{.*\}", txt, _re.S)
    if not m:
        return None, "无法解析为查询条件"
    try:
        spec = json.loads(m.group(0))
    except Exception:
        return None, "无法解析为查询条件"
    if isinstance(spec, dict) and spec.get("error"):
        return None, str(spec["error"])
    return (spec if isinstance(spec, dict) else None), None


def _nl_filter_issues(all_issues, spec):
    """按解析出的过滤条件筛选问题。"""
    kw = (spec.get("keyword") or "").strip()
    disc = spec.get("discipline")
    sev = spec.get("severity")
    floor = (spec.get("floor") or "").strip()
    out = []
    for iss in all_issues:
        if disc and iss.get("type") != disc:
            continue
        if sev and iss.get("severity") != sev:
            continue
        if floor and floor not in str(iss.get("floor_name", "")):
            continue
        if kw:
            hay = " ".join(str(iss.get(k, "")) for k in
                           ("title", "description", "code_ref", "rule_id"))
            if kw not in hay:
                continue
        out.append(iss)
    return out


def _nl_highlight_cmd(issues, room_gids, gid_bbox):
    """把一批问题对应的构件汇总成一条高亮指令（无构件则返回 None）。"""
    gids, seen = [], set()

    def _push(g):
        if g and g not in seen:
            seen.add(g)
            gids.append(g)

    for iss in issues:
        eids = iss.get("element_global_ids") or []
        if eids:
            for g in eids:
                _push(g)
        else:
            loc = (iss.get("location", "") or "").strip()
            for g in (room_gids.get(loc, {}).get("gids") or []):
                _push(g)
    if not gids:
        return None
    ts = int(time.time() * 1000)
    cmd = {"type": "highlight", "globalIds": gids[:200], "_reqId": ts}
    bb = [gid_bbox[g] for g in gids if g in gid_bbox]
    if bb:
        cam, box = _viewer_cam_box(bb)
        if cam:
            cmd["cam"] = f"{cam[0]:.2f},{cam[1]:.2f},{cam[2]:.2f},{cam[3]:.2f}"
        if box:
            cmd["box"] = (f"{box[0]:.2f},{box[1]:.2f},{box[2]:.2f},"
                          f"{box[3]:.2f},{box[4]:.2f},{box[5]:.2f}")
    return cmd


@st.cache_data(show_spinner=False)
def _parse_uploaded(data_bytes):
    """Parse an uploaded IFC, cached by file content.

    Streamlit reruns the whole script on every widget interaction; without
    caching, a large model (HITOS 61MB) is re-parsed (~35s) on each rerun,
    which starves the post-parse render. Keyed on the file bytes so a new
    upload re-parses but any rerun in between is instant."""
    tmp = OUTPUT / "uploaded_building.ifc"
    tmp.write_bytes(data_bytes)
    return parse_ifc(tmp)


def _render_params_editor(bdata):
    """Editable building + room parameters for the loaded building data."""
    bp = bdata.get("building_params", {})
    with st.expander(T["bld_params_t"], expanded=True):
        st.caption(T["bld_params_caption"])
        st.markdown(
            f'<div style="font-size:12px;margin-bottom:8px;">'
            f'<span style="color:{C["green"]};">🟢 {T["src_model"]}</span> &nbsp;·&nbsp; '
            f'<span style="color:{C["orange"]};">🟠 {T["src_default"]}</span></div>',
            unsafe_allow_html=True)
        _dv = st.session_state.get("data_version", 0)
        bp1, bp2 = st.columns(2)
        bw = bp1.number_input(f"🟠 {T['p_ground_exit']}", value=float(bp.get("ground_floor_exit_width_m", 2.4)), step=0.1, key=f"bp_bw_{_dv}")
        fp = bp2.number_input(f"🟠 {T['p_fire_pool']}", value=float(bp.get("fire_pool_volume_m3", 160)), step=10.0, key=f"bp_fp_{_dv}")
        tc = bp1.number_input(f"🟠 {T['p_transformer']}", value=float(bp.get("transformer_capacity_kw", 650)), step=50.0, key=f"bp_tc_{_dv}")
        ep = bp2.number_input(f"🟠 {T['p_emergency']}", value=float(bp.get("emergency_power_duration_min", 60)), step=10.0, key=f"bp_ep_{_dv}")
        fl = bp1.number_input(f"🟢 {T['p_floors']}", value=int(bp.get("total_floors", 3)), min_value=1, max_value=20, step=1, key=f"bp_fl_{_dv}")
        # start from the model-derived params so fields we don't expose here
        # (accessibility counts, sprinkler/alarm flags, ramp slope …) survive
        # an editor save instead of being silently dropped.
        bp_updated = dict(bp)
        bp_updated.update({
            "total_floors": int(fl), "ground_floor_exit_width_m": bw,
            "fire_pool_volume_m3": fp, "transformer_capacity_kw": tc,
            "emergency_power_duration_min": ep,
            "occupancy_type": bp.get("occupancy_type", "office"),
            "fire_elevator_count": bp.get("fire_elevator_count", 1),
        })
    floors = bdata.get("floors", [])
    floor_tabs = st.tabs([_floor_label(f.get("floor_name", f.get("floor_id", f"F{i}"))) for i, f in enumerate(floors)])
    updated_floors = []
    for ti, (tab, floor) in enumerate(zip(floor_tabs, floors)):
        with tab:
            updated_rooms = []
            for room in floor.get("rooms", []):
                rid = room["id"]
                _esrc = "🟢" if room.get("eee_src") == "model" else "🟠"
                st.markdown(
                    f'<span style="font-weight:700;font-size:14px;">{room["name"]}</span> '
                    f'<span style="color:{C["silver"]};font-size:12px;">({_room_type_label(room["type"])})</span>',
                    unsafe_allow_html=True,
                )
                a1, a2, a3, a4 = st.columns(4)
                area = a1.number_input(f"🟢 {T['p_area']}", value=float(room.get("room_area_sqm") or 0), key=f"{rid}_a", step=5.0)
                exits = a2.number_input(f"🟢 {T['p_exits']}", value=int(room.get("exit_count") or 1), key=f"{rid}_x", min_value=0, max_value=500)
                corr = a3.number_input(f"🟢 {T['p_corridor']}", value=float(room.get("corridor_length_m", 0)), key=f"{rid}_c", step=1.0)
                light = a4.checkbox(f"{_esrc} {T['p_light']}", value=bool(room.get("has_emergency_light", False)), key=f"{rid}_l")
                b1, b2, b3, b4 = st.columns(4)
                water = b1.number_input(f"{_esrc} {T['p_water']}", value=float(room.get("dist_to_water_m", 5.0)), key=f"{rid}_w", step=0.1)
                circuit = b2.number_input(f"{_esrc} {T['p_load']}", value=float(room.get("circuit_load_a", 10)), key=f"{rid}_ld", step=1.0)
                outlet = b3.number_input(f"{_esrc} {T['p_outlet']}", value=float(room.get("outlet_spacing_m", 5.0)), key=f"{rid}_o", step=0.5)
                door = b4.number_input(f"🟢 {T['p_door']}", value=float(room.get("door_width_m") or 1.0), key=f"{rid}_d", step=0.1)
                # carry the room's other extracted fields (accessible corridor
                # width, sprinkler/exit-sign flags …) through the edit so they
                # aren't dropped on save.
                _nr = dict(room)
                _nr.update({
                    "id": rid, "name": room["name"], "type": room["type"],
                    "room_area_sqm": area, "exit_count": exits, "corridor_length_m": corr,
                    "door_width_m": door, "has_emergency_light": light,
                    "dist_to_water_m": water, "circuit_load_a": circuit, "outlet_spacing_m": outlet,
                    "hull": room.get("hull"),
                    "eee_src": room.get("eee_src", "default"),
                })
                updated_rooms.append(_nr)
                st.markdown(f'<div style="height:8px;"></div>', unsafe_allow_html=True)
            updated_zones = []
            for zone in floor.get("fire_zones", []):
                za = st.number_input(
                    f"{zone['name']} {T['p_fz_area']}",
                    value=float(zone.get("fire_zone_area_sqm", 0)),
                    key=f"{zone['id']}_z",
                    step=50.0,
                )
                updated_zones.append({
                    "id": zone["id"], "name": zone["name"],
                    "fire_zone_area_sqm": za, "rooms": zone["rooms"],
                })
            updated_floors.append({
                "floor_id": floor.get("floor_id", f"F{ti+1}"),
                "floor_name": floor.get("floor_name", f"Floor {ti+1}"),
                "rooms": updated_rooms,
                "fire_zones": updated_zones,
                "structure": floor.get("structure"),
                "structural_elements": floor.get("structural_elements", []),
                "plan_elements": floor.get("plan_elements", []),
                "pipes": floor.get("pipes", []),
                "electrical_equipment": floor.get("electrical_equipment", []),
            })
    if st.button(T["save_btn"], width="stretch"):
        saved = dict(bdata)
        saved.update({
            "project_name": bdata.get("project_name", "Building"),
            "building_params": bp_updated,
            "floors": updated_floors,
        })
        st.session_state.building_data = saved
        st.success(T["save_ok"])
def _render_maint_uploaders(bdata):
    """Optional maintenance/monitoring CSV upload. Parsed records land in
    session_state; the start-review block merges them into bdata."""
    with st.expander(T["maint_csv_title"], expanded=False):
        st.caption(T["maint_csv_hint"])

        # 每个 uploader 的 key 带一个世代号：移除后 +1，令 file_uploader 换用
        # 全新 key（否则被移除的文件仍留在控件里，rerun 时又被重新读入）。
        _gen = st.session_state.setdefault("maint_upcsv_gen", {})
        specs = [
            ("service", T["maint_service_t"], T["maint_service_hint"],
             risk_csv.service_template()),
            ("log", T["maint_log_t"], T["maint_log_hint"],
             risk_csv.log_template()),
            ("monitoring", T["maint_monitor_t"], T["maint_monitor_hint"],
             risk_csv.monitoring_template()),
        ]
        for kind, title, hint, template in specs:
            state_key = f"uploaded_{kind}"
            st.markdown(
                f'<div style="font-weight:700;font-size:14px;margin-top:10px;">{title}</div>',
                unsafe_allow_html=True)
            st.caption(hint)
            tc1, tc2 = st.columns([3, 2])
            with tc2:
                st.download_button(
                    T["maint_download_template"], data=template,
                    file_name=f"{kind}_template.csv", mime="text/csv",
                    key=f"tpl_{kind}", width="stretch")
            with tc1:
                up = st.file_uploader(T["maint_upload"], type=["csv"],
                                      key=f"upcsv_{kind}_{_gen.get(kind, 0)}",
                                      label_visibility="collapsed")
                if up is not None:
                    try:
                        df = risk_csv.read_csv_bytes(up.getvalue())
                        if kind == "service":
                            records, problems = risk_csv.parse_service_csv(df)
                            bad_regime = False
                        elif kind == "log":
                            records, problems = risk_csv.parse_log_csv(df)
                            bad_regime = False
                        else:
                            records, problems, status = risk_csv.parse_monitoring_csv(df)
                            bad_regime = status == "invalid"
                    except Exception as e:
                        st.error(T["maint_parse_failed"].format(detail=str(e)[:120]))
                    else:
                        if not records or bad_regime:
                            detail = "；".join(problems[:3])
                            if bad_regime:
                                detail = T["maint_bad_regime"]
                            st.error(T["maint_parse_failed"].format(detail=detail))
                        else:
                            v = risk_csv.validate_ids(records, bdata)
                            st.session_state[state_key] = records
                            summary = T["maint_parse_summary"].format(
                                n=len(records),
                                matched=len(v["matched"]),
                                unmatched=len(v["unmatched"]),
                                dupes=len(v["dupes"]))
                            st.success(summary)
                            if problems:
                                st.caption(T["maint_parse_problems"].format(
                                    problems="；".join(problems[:3])))
                elif st.session_state.get(state_key):
                    st.caption(T["maint_loaded"].format(
                        n=len(st.session_state[state_key])))
                else:
                    st.caption(T["maint_none"])
            with tc2:
                # 读取置于上传块之后：上传当次运行已写入 session_state，
                # 移除按钮才会立即出现（此前要等下一次 rerun）。
                if st.session_state.get(state_key) and st.button(
                        T["maint_remove"], key=f"rm_{kind}", width="stretch"):
                    st.session_state[state_key] = None
                    _gen[kind] = _gen.get(kind, 0) + 1
                    st.rerun()


# ============================================================
# ENGINE SETUP — load the current standard's rules + language
# ============================================================
engine.set_standard(st.session_state.standard)
T = i18n.T
LANG = i18n.LANG
STD_META = engine.STD_META

# CONSUME PENDING NAVIGATION (before any sidebar widget exists)
# ============================================================
if st.session_state.get("pending_page"):
    _pending = st.session_state.pop("pending_page")
    st.session_state.page = _pending
    st.session_state["nav_radio"] = _pending

# ============================================================
# SIDEBAR BRANDING + NAVIGATION + STANDARD SELECTOR
# ============================================================
with st.sidebar:
    st.markdown("## ArchCheck")
    st.markdown(
        f'<div class="aicher-band">'
        f'<div class="band-civil"></div><div class="band-eee"></div><div class="band-bld"></div>'
        f'<div class="band-risk"></div><div class="band-pass"></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="font-size:14px;color:{C["muted"]};line-height:1.5;">'
        f'{T["platform_desc"]}</p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Standard selector
    st.markdown(
        f'<div class="aicher-label" style="margin-bottom:8px;">{T["std_label"]}</div>',
        unsafe_allow_html=True,
    )
    std_list = engine.list_standards()
    std_ids = [s[0] for s in std_list]
    std_metas = {s[0]: s[1] for s in std_list}
    std_idx = std_ids.index(st.session_state.standard) if st.session_state.standard in std_ids else 0
    new_std = st.radio(
        "Standard",
        options=std_ids,
        format_func=lambda x: f'{std_metas.get(x, {}).get("flag","")} {std_metas.get(x, {}).get("category", x)}',
        index=std_idx,
        label_visibility="collapsed",
        key="std_radio",
    )
    if new_std != st.session_state.standard:
        st.session_state.standard = new_std
        # Re-run the review under the newly selected standard so the report
        # always reflects the current standard instead of stale results.
        if st.session_state.get("all_issues") and st.session_state.get("uploaded_image") is not None:
            st.session_state.review_loading = True
        st.rerun()
    st.caption(f'{T["active_std"]}: {STD_META.get("flag","")} {STD_META.get("civil_codes","")}')

    st.markdown("---")
    page_labels = {"upload": T["nav_upload"], "results": T["nav_results"], "architecture": T["nav_arch"], "kb": T["nav_kb"]}
    nav = st.radio(
        "Navigation",
        options=["upload", "results", "architecture", "kb"],
        format_func=lambda x: page_labels[x],
        key="nav_radio",
        label_visibility="collapsed",
    )
    if nav != st.session_state.page:
        st.session_state.page = nav
        st.rerun()
    st.markdown("---")
    st.markdown(
        f'<span class="aicher-label">{T["version"]}</span>',
        unsafe_allow_html=True,
    )

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
        st.warning(T["no_results"])
        st.session_state.review_loading = False
        if st.button(T["back_upload"], width="stretch"):
            st.rerun()
        st.stop()

    n_floors = len(bdata.get("floors", []))
    total_rooms = sum(len(f.get("rooms", [])) for f in bdata.get("floors", []))
    total_zones = sum(len(f.get("fire_zones", [])) for f in bdata.get("floors", []))

    st.markdown(f'<div class="aicher-label" style="margin-bottom:8px;">{T["sec_analysis"]}</div>', unsafe_allow_html=True)

    ca, cb = st.columns([1, 2])
    with ca:
        with st.container(border=True):
            st.image(uimg)
    with cb:
        st.markdown(
            f'<div style="font-size:36px;font-weight:800;color:{C["text"]};margin-bottom:20px;">'
            f'{T["reviewing_title"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:14px;color:{C["muted"]};margin-bottom:16px;">'
            f'{T["std_label_running"]}: {STD_META.get("flag","")} <b>{STD_META.get("civil_codes","")}</b> + {STD_META.get("eee_codes","")}<br>'
            f'{T["floors_label"]}: {n_floors} · {T["rooms_label"]}: {total_rooms} · {T["zones_label"]}: {total_zones}</div>',
            unsafe_allow_html=True,
        )

        with st.status(T["status_init"], expanded=True) as status:
            time.sleep(0.4)
            floors_label = T["floors_label"]
            rooms_label = T["rooms_label"]
            zones_label = T["zones_label"]
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["silver"]};">'
                f'{T["sys_prefix"]}{T["status_parsing"]} ({n_floors} {floors_label})</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.4)
            status.update(label=f'{T["status_loaded"]} — {n_floors} {floors_label}, {total_rooms} {rooms_label}, {total_zones} {zones_label}')

            results = run_full_review(bdata)

            # Per-floor agent logs
            for floor in bdata.get("floors", []):
                fname = _floor_label(floor.get("floor_name", floor.get("floor_id", "")))
                n_rooms = len(floor.get("rooms", []))
                time.sleep(0.4)
                status.update(label=f'{T["status_floor"]} {fname}...')
                st.markdown(
                    f'<span style="font-family:monospace;font-size:13px;color:{C["blue"]};">'
                    f'CIVIL [{fname}] | {T["log_civil"].format(n=n_rooms)} → {STD_META.get("civil_codes","")}</span>',
                    unsafe_allow_html=True,
                )
                time.sleep(0.3)
                st.markdown(
                    f'<span style="font-family:monospace;font-size:13px;color:{C["orange"]};">'
                    f'EEE   [{fname}] | {T["log_eee"]} → {STD_META.get("eee_codes","")}</span>',
                    unsafe_allow_html=True,
                )

            # Building-level check
            time.sleep(0.5)
            status.update(label=T["status_bld"])
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["purple"]};">'
                f'BLD   | {T["log_bld"].format(n=n_floors)}</span>',
                unsafe_allow_html=True,
            )

            # Coordinator
            time.sleep(0.5)
            status.update(label=T["status_coord"])
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["green"]};">'
                f'COORD | {T["log_coord"]}</span>',
                unsafe_allow_html=True,
            )
            time.sleep(0.6)

            total = len(results["all_issues"])
            n_conflicts = len(results["conflicts"])
            n_bld = len(results["building_results"])
            civ_n = len(results["civil_results"])
            eee_n = len(results["eee_results"])
            detail = T["status_done_detail"].format(total=total, civ_n=civ_n, eee_n=eee_n, n_bld=n_bld, n_conflicts=n_conflicts)
            status.update(
                label=f'{T["status_done"]} — {detail}',
                state="complete",
            )
            st.markdown(
                f'<span style="font-family:monospace;font-size:13px;color:{C["green"]};">'
                f'COORD | {T["log_done"].format(total=total, n_conflicts=n_conflicts, n_bld=n_bld)}</span>',
                unsafe_allow_html=True,
            )

        time.sleep(0.6)

    st.session_state.civil_results = results["civil_results"]
    st.session_state.eee_results = results["eee_results"]
    st.session_state.building_results = results["building_results"]
    st.session_state.structural_results = results["structural_results"]
    st.session_state.mep_results = results["mep_results"]
    st.session_state.accessibility_results = results.get("accessibility_results", [])
    st.session_state.predictive_results = results.get("predictive_results", [])
    st.session_state.predictive_ranking = results.get("predictive_ranking", [])
    st.session_state.predictive_monitor = results.get("predictive_monitor", {})
    st.session_state.coverage_findings = results.get("coverage_findings", [])
    st.session_state.discipline_checked = results.get("discipline_checked", {})
    st.session_state.discipline_notes = results.get("discipline_notes", {})
    st.session_state.clash_candidates = results.get("clash_candidates", [])
    st.session_state.conflicts = results["conflicts"]
    st.session_state.all_issues = results["all_issues"]
    st.session_state.ai_report = None
    st.session_state.ai_coord = None
    st.session_state.ai_error = None
    st.session_state.review_loading = False
    goto("results")
    st.rerun()

# ---- UPLOAD PAGE ----
elif st.session_state.page == "upload":
    st.markdown(
        f'<div class="aicher-label" style="margin-bottom:8px;">{T["sec_platform"]}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="aicher-band">'
        f'<div class="band-civil"></div><div class="band-eee"></div><div class="band-bld"></div>'
        f'<div class="band-risk"></div><div class="band-pass"></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"""<div style="max-width:860px;margin-bottom:8px;">
    <div style="font-size:56px;font-weight:800;line-height:1.15;color:{C["text"]};">
    {T["hero_1"]}<br>{T["hero_2"]}<span style="color:{C["blue"]};">{T["hero_3"]}</span>{T["hero_4"]}
    </div>
    <div style="margin-top:16px;font-size:18px;color:{C["muted"]};font-weight:300;line-height:1.5;">
    {T["hero_sub"]}
    </div>
    </div>""", unsafe_allow_html=True)

    st.markdown(f"""<div style="display:flex;gap:28px;margin:24px 0 8px 0;flex-wrap:wrap;">
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["blue"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_reader"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["orange"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_judge"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["purple"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_kb"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["red"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_reviewer"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["green"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_reasoner"]}</span>
    </div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    f1, f2, f3, f4 = st.columns(4)
    features = [
        ("🏗️", C["blue"], T["feat1_t"], T["feat1_d"]),
        ("⚖️", C["orange"], T["feat2_t"], T["feat2_d"]),
        ("🔍", C["red"], T["feat3_t"], T["feat3_d"]),
        ("🌐", C["purple"], T["feat4_t"], T["feat4_d"]),
    ]
    for col, (icon, color, title, desc) in zip([f1, f2, f3, f4], features):
        with col:
            st.markdown(f"""<div class="aicher-card">
            <div class="aicher-feature-icon" style="background:{color}15;">{icon}</div>
            <div style="font-weight:700;font-size:16px;color:{C["text"]};margin-bottom:6px;">{title}</div>
            <div style="font-size:13px;color:{C["muted"]};line-height:1.6;white-space:pre-line;">{desc}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown(
            f'<div style="font-weight:700;font-size:17px;color:{C["text"]};margin-bottom:8px;">'
            f'{T["ifc_upload_t"]}</div>',
            unsafe_allow_html=True,
        )
        ifc_file = st.file_uploader(T["ifc_upload_hint"], type=["ifc"], key="ifc_up")
        if ifc_file is not None:
            try:
                # 全楼层 / 全房间：解析耗时与楼层上限无关（瓶颈在几何提取），
                # 之前 max_floors=3 只保留"房间最多的 3 层"，会让多层建筑漏审。
                # 按内容缓存：rerun 不再重复解析大模型。
                struct = _parse_uploaded(ifc_file.getvalue())
            except Exception as ex:
                st.error(f'{T["ifc_parse_fail"]}: {ex}')
            else:
                # Model usability QA: health dashboard + fatal gate (BIM Reader agent)
                qa = struct.get("qa") or {}
                if qa:
                    st.markdown(f"### {T['model_health']}")
                    hm1, hm2 = st.columns([1, 3])
                    hm1.metric(T["qa_score"], f"{qa.get('score', 0)}/100")
                    hm2.progress(max(0, min(100, qa.get('score', 0))) / 100)
                    for ch in qa.get("checks", []):
                        lvl = ch["level"]
                        msg = ch["message_en"] if LANG == "en" and ch.get("message_en") else ch["message"]
                        if lvl == "error":
                            st.error(msg)
                        elif lvl == "warn":
                            st.warning(msg)
                        else:
                            st.info(msg)
                    if qa.get("fatal"):
                        st.error(T["qa_blocked"])
                        st.stop()
                # rooms come from the IFC when present; otherwise empty (no fabrication)
                bdata = build_review_data(struct)
                # Invisible AI pre-judgment: normalise ambiguous room type /
                # material / pipe-system semantics before the engine judges.
                if bdata.get("source") == "ifc":
                    enrich_review_data(bdata)
                st.session_state.building_data = bdata
                st.session_state.data_version = st.session_state.get("data_version", 0) + 1
                st.session_state.model_qa = struct.get("qa") or {}
                if struct["total_rooms"] == 0:
                    st.warning(T["ifc_no_rooms"])
                first_rooms = bdata["floors"][0]["rooms"] if bdata.get("floors") else []
                if first_rooms:
                    st.session_state.uploaded_image, _ = render_room_plan(
                        first_rooms, bdata["floors"][0]["floor_name"],
                        bdata["floors"][0].get("plan_elements"))
                else:
                    st.session_state.uploaded_image = generate_sample_image(struct.get("file_name", "BIM"), variant=0)
                st.session_state.civil_results = []
                st.session_state.eee_results = []
                st.session_state.building_results = []
                st.session_state.structural_results = []
                st.session_state.mep_results = []
                st.session_state.predictive_results = []
                st.session_state.predictive_ranking = []
                st.session_state.predictive_monitor = {}
                st.session_state.uploaded_service = None
                st.session_state.uploaded_log = None
                st.session_state.uploaded_monitoring = None
                st.session_state.conflicts = []
                st.session_state.all_issues = []
                total_doors = sum(f["structure"]["doors"] for f in struct["floors"])
                st.success(
                    f'{T["ifc_parsed"]} {struct["storey_count"]} {T["ifc_storey_lbl"]} · '
                    f'{T["ifc_footprint_lbl"]} {struct["building_footprint_area_sqm"]} m² · '
                    f'{T["ifc_rooms_lbl"]} {struct["total_rooms"]} · '
                    f'{T["ifc_doors_lbl"]} {total_doors}')
                for f in struct["floors"]:
                    s = f["structure"]
                    line = (f'<b>{_floor_label(f["name"])}</b> — {T["ifc_footprint_lbl"]} {f["footprint_area_sqm"]}m² · '
                            f'{T["ifc_rooms_lbl"]} {len(f["rooms"])} · {T["ifc_walls_lbl"]} {s["walls"]} · '
                            f'{T["ifc_doors_lbl"]} {s["doors"]} · {T["ifc_windows_lbl"]} {s["windows"]} · '
                            f'{T["ifc_door_w_lbl"]} {s["door_widths_m"]}m')
                    st.markdown(f'<div style="font-size:13px;color:{C["muted"]};padding:2px 0;">{line}</div>',
                                unsafe_allow_html=True)

    with c2:
        st.markdown(
            f'<div style="font-size:17px;font-weight:700;color:{C["text"]};margin-bottom:10px;">'
            f'{T["data_t"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="font-size:14px;color:{C["muted"]};margin-bottom:8px;">'
            f'{T["data_hint"]}</p>',
            unsafe_allow_html=True,
        )

        bdata = st.session_state.get("building_data")
        if bdata is None:
            st.info(T["need_upload"])
        else:
            _render_params_editor(bdata)
            _render_maint_uploaders(bdata)

    # 审查按钮（解析成功后显示）
    _bdata = st.session_state.get("building_data")
    st.write("DBG::", _bdata is not None, len((_bdata or {}).get("floors", [])))
    if _bdata and _bdata.get("floors"):
        st.markdown("---")
        sc1, sc2, sc3 = st.columns([1, 2, 1])
        with sc2:
            if st.button(T["start_btn"], type="primary", width="stretch"):
                for state_key, bdata_key in (
                        ("uploaded_service", "pipe_service"),
                        ("uploaded_log", "maintenance_log"),
                        ("uploaded_monitoring", "pipe_monitoring")):
                    recs = st.session_state.get(state_key)
                    if recs:
                        _bdata[bdata_key] = recs
                    else:
                        _bdata.pop(bdata_key, None)
                st.session_state.review_loading = True
                st.rerun()

    if _bdata is None:
        st.markdown(
            f'<div style="text-align:center;margin-top:32px;padding:24px;color:{C["silver"]};font-size:14px;">'
            f'{T["need_upload"]}</div>',
            unsafe_allow_html=True,
        )

# ---- RESULTS PAGE ----
elif st.session_state.page == "results":
    uimg = st.session_state.get("uploaded_image")
    civil_r = st.session_state.get("civil_results", [])
    eee_r = st.session_state.get("eee_results", [])
    building_r = st.session_state.get("building_results", [])
    structural_r = st.session_state.get("structural_results", [])
    mep_r = st.session_state.get("mep_results", [])
    acc_r = st.session_state.get("accessibility_results", [])
    predictive_r = st.session_state.get("predictive_results", [])
    predictive_ranking = st.session_state.get("predictive_ranking", [])
    predictive_monitor = st.session_state.get("predictive_monitor", {})
    conflicts = st.session_state.get("conflicts", [])
    all_issues = st.session_state.get("all_issues", [])
    bdata = st.session_state.get("building_data") or DEMO_DATA

    # Compute diff against another standard for the standard-switching summary
    _others = [s for s in std_ids if s != st.session_state.standard]
    other_std_id = _others[0] if _others else st.session_state.standard
    other_std = engine.load_standard(other_std_id)
    other_results = engine.run_review_with_standard(other_std_id, bdata)

    def _issue_key(iss):
        return (iss.get("rule_id", ""), iss.get("location", ""), iss.get("floor_id", ""))
    cur_keys = {_issue_key(i) for i in all_issues}
    other_keys = {_issue_key(i) for i in other_results["all_issues"]}
    added_in_other = [i for i in other_results["all_issues"] if _issue_key(i) not in cur_keys]
    removed_in_other = [i for i in all_issues if _issue_key(i) not in other_keys]
    other_meta = other_std["meta"]

    if uimg is None:
        st.warning(T["no_results"])
        if st.button(T["back_upload"], width="stretch"):
            goto("upload")
            st.rerun()
        st.stop()

    # Generate per-floor annotated and correction images
    floors = bdata.get("floors", [])
    annotated_by_floor = {}
    correction_by_floor = {}
    floor_by_name = {}  # floor_label -> floor dict (for interactive viewer)
    for fi, floor in enumerate(floors):
        fid = floor.get("floor_id", "")
        fname = _floor_label(floor.get("floor_name", fid))
        floor_by_name[fname] = floor  # 存起来给交互查看用
        floor_civ = [i for i in civil_r if i.get("floor_id") == fid]
        floor_eee = [i for i in eee_r if i.get("floor_id") == fid]
        floor_issues = floor_civ + floor_eee
        rooms = floor.get("rooms", [])

        if rooms:
            # data-driven plan — real rooms packed by area, markers on room centroids
            base_img, room_map = render_room_plan(rooms, fname, floor.get("plan_elements"))
            annotated_by_floor[fname] = annotate_room_plan(base_img, floor_issues, room_map)
            correction_by_floor[fname] = generate_correction_image(
                base_img, floor_civ, floor_eee, conflicts, bdata, fname,
                variant=fi, base_plan=base_img, room_map=room_map)
        else:
            base_img = generate_sample_image(fname, variant=fi)
            annotated_by_floor[fname] = annotate_image(base_img, floor_issues)
            correction_by_floor[fname] = generate_correction_image(
                base_img, floor_civ, floor_eee, conflicts, bdata, fname, variant=fi
            )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for fname, img in annotated_by_floor.items():
        safe = fname.replace(" ", "_")
        img.save(OUTPUT / f"review_{safe}.png")
    for fname, img in correction_by_floor.items():
        safe = fname.replace(" ", "_")
        img.save(OUTPUT / f"correction_{safe}.png")

    st.markdown(f'<div class="aicher-label" style="margin-bottom:8px;">{T["sec_results"]}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:40px;font-weight:800;color:{C["text"]};display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
        f'{T["results_title"]} <span style="font-size:18px;font-weight:600;background:{C["purple"]}18;color:{C["purple"]};padding:4px 14px;border-radius:4px;">{STD_META.get("flag","")} {STD_META.get("short_name","")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div style="font-size:16px;color:{C["muted"]};margin-bottom:20px;">{T["results_sub"]}</div>', unsafe_allow_html=True)

    if bdata.get("source") == "ifc" and sum(len(f.get("rooms", [])) for f in floors) == 0:
        st.warning(T["ifc_no_rooms"])

    # ① BIM Reader — model usability QA
    _qa = st.session_state.get("model_qa") or {}
    if _qa:
        st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["blue"]};margin:22px 0 10px;">① {T["agent_reader"]} · {T["model_health"]}</div>', unsafe_allow_html=True)
        _q1, _q2 = st.columns([1, 3])
        _q1.metric(T["qa_score"], f"{_qa.get('score', 0)}/100")
        _q2.progress(max(0, min(100, _qa.get('score', 0))) / 100)
        for _ch in _qa.get("checks", []):
            _lv = _ch["level"]
            _msg = _ch["message_en"] if LANG == "en" and _ch.get("message_en") else _ch["message"]
            if _lv == "error":
                st.error(_msg)
            elif _lv == "warn":
                st.warning(_msg)
            else:
                st.info(_msg)

    # ② Compliance Judge — deterministic review
    st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["orange"]};margin:22px 0 10px;">② {T["agent_judge"]}</div>', unsafe_allow_html=True)

    high = sum(1 for i in all_issues if i.get("severity") == "High")

    _n_disc = sum(1 for r in (civil_r, eee_r, building_r, structural_r, mep_r) if r)

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{len(all_issues)}</div><div class="label">{T["s_total"]}</div></div>', unsafe_allow_html=True)
    with s2:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{high}</div><div class="label">{T["s_high"]}</div></div>', unsafe_allow_html=True)
    with s3:
        st.markdown(f'<div class="aicher-stat red"><div class="value">{len(conflicts)}</div><div class="label">{T["s_conf"]}</div></div>', unsafe_allow_html=True)
    with s4:
        st.markdown(f'<div class="aicher-stat purple"><div class="value">{_n_disc}</div><div class="label">{T["s_disc"]}</div></div>', unsafe_allow_html=True)

    # Honest per-discipline check status: 0 findings could mean "checked, clean"
    # or "not checked (no elements to judge)" — make the difference visible.
    _chk = st.session_state.get("discipline_checked", {})
    _notes = st.session_state.get("discipline_notes", {})
    _discs = [("civil", civil_r, T["disc_civil"]), ("eee", eee_r, T["disc_eee"]),
              ("structural", structural_r, T["disc_str"]), ("mep", mep_r, T["disc_mep"]),
              ("building", building_r, T["disc_bld"])]
    _cells = []
    for _k, _r, _lbl in _discs:
        _n = len(_r)
        _c = _chk.get(_k, 0)
        if _n > 0:
            _st = f'<b style="color:{C["orange"]};">{T["disc_n_found"].format(n=_n)}</b>'
        elif _c > 0:
            _st = T["disc_clean"]
        elif _k == "structural" and _notes.get("structural_unit_suspicious", 0) > 0:
            _st = T["disc_unit_susp"].format(n=_notes["structural_unit_suspicious"])
        else:
            _st = T["disc_unchecked"]
        _cells.append(f'<span>{_lbl}: {_st}</span>')
    st.markdown(f'<div style="font-size:13px;color:{C["muted"]};margin:10px 0 4px;">'
                f'{T["s_disc_check"]}：{"　".join(_cells)}</div>', unsafe_allow_html=True)

    # Structural quantities by material (台阶3 · 工程量)
    _has_qty = any((f.get("structure") or {}).get("qty_by_type") for f in bdata.get("floors", []))
    if _has_qty:
        with st.expander(f"🏗️ {T['qty_title']}", expanded=False):
            _vol_total = 0.0
            for _f in bdata.get("floors", []):
                _st = _f.get("structure") or {}
                _qt = _st.get("qty_by_type") or {}
                _mv = _st.get("material_volumes") or {}
                if not _qt:
                    continue
                _by_type = "　·　".join(
                    f'{_t} {v["count"]}{T["qty_pcs"]}/{v["volume_m3"]}m³' for _t, v in _qt.items())
                _by_mat = "　·　".join(
                    f'{T["mat_unknown"] if k == "unknown" else k}: {v} m³' for k, v in _mv.items()) or "—"
                _vol_total += _st.get("structural_volume_m3", 0) or 0
                st.markdown(f'<div style="font-size:13px;color:{C["muted"]};margin:6px 0;">'
                            f'<b>{_floor_label(_f.get("floor_name", _f.get("floor_id", "")))}</b> '
                            f'（{T["qty_vol"]} {_st.get("structural_volume_m3", 0)} m³）<br>'
                            f'　{T["qty_by_type"]}：{_by_type}<br>　{T["qty_by_mat"]}：{_by_mat}</div>',
                            unsafe_allow_html=True)
            st.markdown(f'<div style="font-size:13px;font-weight:600;color:{C["text"]};margin-top:6px;">'
                        f'{T["qty_total"]}：{round(_vol_total, 1)} m³</div>', unsafe_allow_html=True)

    # Coarse MEP-vs-structure clash candidates (bbox pre-check, 台阶③)
    _clashes = st.session_state.get("clash_candidates", [])
    if _clashes:
        with st.expander(f"🧱 {T['clash_title']}（{len(_clashes)}）", expanded=False):
            st.markdown(f'<div style="font-size:12px;color:{C["muted"]};margin-bottom:6px;">{T["clash_h"]}</div>',
                        unsafe_allow_html=True)
            for _ci, _c in enumerate(_clashes):
                _fl = _floor_label(_c.get("floor_name", ""))
                _mark = T["clash_confirmed"] if _c.get("confirmed") else T["clash_candidate"]
                _col = C["red"] if _c.get("confirmed") else C["muted"]
                st.markdown(f'<div style="font-size:13px;color:{_col};margin:3px 0;">'
                            f'{_mark} <b>{_c["mep"]}</b> {T["clash_penetrates"]} <b>{_c["vs"]}</b>'
                            f'（{_c["type"]} · {T["clash_depth"]} {_c["depth"]}m · {_fl}）</div>',
                            unsafe_allow_html=True)
                _ccmd = _clash_target_cmd(_c)
                if _ccmd:
                    def _gc(_c2=_ccmd):
                        st.session_state["3d_cmd"] = json.dumps(_c2, ensure_ascii=False)
                    st.button("🌐 定位到 3D（🔴管道 / 🔵结构）",
                              key=f"clash3d_{_ci}", on_click=_gc)

    # Rules that exist but could not run because the model lacks their field
    _cov = st.session_state.get("coverage_findings", [])
    if _cov:
        with st.expander(f"📋 {T['coverage_title']}（{len(_cov)}）", expanded=False):
            st.markdown(f'<div style="font-size:12px;color:{C["muted"]};margin-bottom:8px;">{T["coverage_hint"]}</div>',
                        unsafe_allow_html=True)
            _cov_tl = {"civil": T["disc_civil"], "eee": T["disc_eee"], "building": T["disc_bld"],
                       "structural": T["disc_str"], "mep": T["disc_mep"], "accessibility": T["disc_acc"]}
            for _c in _cov:
                _d = _cov_tl.get(_c.get("type", ""), _c.get("type", ""))
                st.markdown(
                    f'<div style="font-size:12.5px;color:{C["muted"]};padding:3px 0;border-bottom:1px dashed #eee;">'
                    f'<span style="color:{C["text"]};font-weight:600;">{_c["title"]}</span>'
                    f' <span class="tag tag-disc-civil">{_d}</span>'
                    f' <span style="font-family:monospace;font-size:11px;color:{C["silver"]};">{_c.get("code_ref","")}</span><br>'
                    f'{_c["description"]}</div>',
                    unsafe_allow_html=True,
                )

    # Standard-switching diff summary
    if added_in_other or removed_in_other:
        cur_flag = STD_META.get("flag", "")
        oth_flag = other_meta.get("flag", "")
        oth_name = other_meta.get("short_name", "")
        with st.expander(f"🔄 {T['diff_title']} → {oth_flag} {oth_name}", expanded=False):
            st.markdown(f'<div style="font-size:13px;color:{C["muted"]};margin-bottom:10px;">{T["diff_h"]}</div>', unsafe_allow_html=True)
            cur_name = STD_META.get("short_name", "")
            if removed_in_other:
                st.markdown(
                    f'<div style="font-size:14px;font-weight:600;color:{C["green"]};margin:8px 0;">'
                    f'✅ {T["diff_n_remove"].format(n=len(removed_in_other), oth=oth_name)}</div>',
                    unsafe_allow_html=True,
                )
                for iss in removed_in_other:
                    floor_s = f' [{iss.get("floor_name","")}]' if iss.get("floor_name") else ""
                    st.markdown(
                        f'<div style="font-size:13px;color:{C["muted"]};padding:3px 0 3px 16px;">'
                        f'• <b>{iss["title"]}</b>{floor_s} — <span style="font-family:monospace;font-size:12px;">{iss.get("code_ref","")}</span></div>',
                        unsafe_allow_html=True,
                    )
            if added_in_other:
                st.markdown(
                    f'<div style="font-size:14px;font-weight:600;color:{C["red"]};margin:8px 0;">'
                    f'⚠️ {T["diff_n_add"].format(n=len(added_in_other), oth=oth_name)}</div>',
                    unsafe_allow_html=True,
                )
                for iss in added_in_other:
                    floor_s = f' [{iss.get("floor_name","")}]' if iss.get("floor_name") else ""
                    st.markdown(
                        f'<div style="font-size:13px;color:{C["muted"]};padding:3px 0 3px 16px;">'
                        f'• <b>{iss["title"]}</b>{floor_s} — <span style="font-family:monospace;font-size:12px;">{iss.get("code_ref","")}</span></div>',
                        unsafe_allow_html=True,
                    )
            if not added_in_other and not removed_in_other:
                st.success(T["diff_identical"].format(cur=cur_name, oth=oth_name))

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    # ---- ③ 三维模型 + ④⑤ 审查结果（左右分栏；右栏固定高度可滚动）----
    _col_l, _col_r = st.columns([3, 2], gap="medium")

    with _col_l:
        # ---- ③ 3D Viewer ----
        st.markdown(
            f'<div style="font-size:18px;font-weight:700;color:{C["blue"]};'
            f'margin:22px 0 10px;">③ 三维模型'
            f'<span style="font-size:11px;font-weight:400;color:{C["muted"]};'
            f'margin-left:10px;">左键旋转 · 右键平移 · 滚轮缩放 · 点击构件看信息</span></div>',
            unsafe_allow_html=True)
        # ---- 🔎 自然语言定位（AI 只做语义→规则映射，判定仍由确定性规则给出）----
        _nl_q = st.text_input(
            "🔎 用自然语言定位问题（AI 解析 → 3D 高亮）",
            placeholder="例如：找出所有宽度不足的门 / 二层有哪些结构问题",
            key="nl_query_input", label_visibility="visible")
        if st.button("定位到 3D", key="nl_query_go") and _nl_q.strip():
            _spec, _err = _nl_parse_query(_nl_q.strip())
            if _err:
                st.warning(f"⚠️ {_err}")
            else:
                _matched = _nl_filter_issues(all_issues, _spec)
                if not _matched:
                    st.info("没有匹配的问题（试试换种说法）")
                else:
                    _ncmd = _nl_highlight_cmd(
                        _matched, _room_element_gids(0, bdata), _build_gid_bbox_map(bdata))
                    if _ncmd:
                        st.session_state["3d_cmd"] = json.dumps(_ncmd, ensure_ascii=False)
                        st.success(f"✅ 匹配 {len(_matched)} 条问题，已在 3D 定位高亮")
                    else:
                        st.info(f"匹配 {len(_matched)} 条问题，但都没有可定位的构件")
        try:
            _ifc_path = OUTPUT / "uploaded_building.ifc"
            if _ifc_path.exists():
                _ifc_url = VIEWER_SERVER.serve_ifc("default", _ifc_path.read_bytes(),
                                                   _ifc_path.name)
                # 写入违规构件标记（3D viewer fetch 读取）
                _vmarkers = _collect_violation_markers(bdata, all_issues)
                _vdir = OUTPUT / "viewer_tmp" / "default"
                _vdir.mkdir(parents=True, exist_ok=True)
                (_vdir / "violations.json").write_text(
                    json.dumps(_vmarkers, ensure_ascii=False), encoding="utf-8")
                # 写入构件信息（材料/楼层/触发规则），供 3D 点击详情面板展示
                _einfo = _collect_element_info(bdata, all_issues)
                (_vdir / "elements.json").write_text(
                    json.dumps(_einfo, ensure_ascii=False), encoding="utf-8")
                # 写入房间清单，供 3D viewer 楼层/房间导航
                (_vdir / "rooms.json").write_text(
                    json.dumps(_collect_room_manifest(bdata), ensure_ascii=False),
                    encoding="utf-8")
                _viewer_base = f"{VIEWER_BASE}/?ifc={_ifc_url}&session=default&lang={LANG}"
                # 附加 hash 指令（点问题卡片的定位按钮会更新这个）
                _hash = st.session_state.get("3d_target_hash", "")
                _viewer_full = f"{_viewer_base}#{_hash}" if _hash else _viewer_base
                st.iframe(_viewer_full, height=800)
                # 违规统计
                _n_hi = sum(1 for m in _vmarkers if m["severity"] == "High")
                _n_med = sum(1 for m in _vmarkers if m["severity"] == "Medium")
                _n_low = sum(1 for m in _vmarkers if m["severity"] == "Low")
                st.caption(
                    f"🔴 严重 {_n_hi} · 🟠 中等 {_n_med} · 🟡 轻微 {_n_low} 个构件标记 "
                    f"（共 {len(_vmarkers)} 个涉及违规的构件）")
            else:
                st.info("请上传 IFC 文件以查看三维模型。")
        except Exception as _e3:
            st.error(f"三维查看器加载失败：{_e3}")


    def render_issue_cards(issues, css_class, show_floor=True):
        if not issues:
            st.success(T["no_issue"])
            return
        for i, iss in enumerate(issues, 1):
            sev = iss.get("severity", "Medium")
            floor_tag = ""
            if show_floor and iss.get("floor_name"):
                floor_tag = f'<span class="floor-tag">{_floor_label(iss["floor_name"])}</span>'
            loc_label = T["loc"]
            ref_label = T["ref"]
            _tl = {"civil": T["disc_civil"], "eee": T["disc_eee"], "building": T["disc_bld"],
                   "structural": T["disc_str"], "mep": T["disc_mep"], "accessibility": T["disc_acc"],
                   "conflict": T["disc_conf"]}
            _itype = iss.get("type", "")
            _sev_cls = {"High": "high", "Medium": "medium", "Low": "low", "Missing": "missing",
                        "Predictive": "predictive"}.get(sev, "low")
            _disc_cls = {"civil": "civil", "eee": "eee", "building": "building",
                         "structural": "structural", "mep": "mep", "accessibility": "accessibility",
                         "conflict": "conflict"}.get(_itype, "low")
            evid = ""
            if iss.get("review_status") == "verified" and iss.get("review_evidence"):
                evid = (f'<div class="card-meta" style="color:{C["green"]};">'
                        f'🔍 {T["review_evid"]}: {iss["review_evidence"][:150]}</div>')
            st.markdown(f'''<div class="issue-card {css_class}">
            <div class="card-title">{i}. {iss["title"]}
            <span class="tag tag-disc-{_disc_cls}">{_tl.get(_itype, _itype)}</span>
            <span class="tag tag-sev-{_sev_cls}">{sev}</span>
            {floor_tag}</div>
            <div class="card-desc">{iss.get("description","")}</div>
            <div class="card-meta">{loc_label}: {iss.get("location","-")} | {ref_label}: {iss.get("code_ref","-")}</div>
            {evid}
            </div>''', unsafe_allow_html=True)

    def _render_folded_issue_cards(issues, room_gids=None, highlight_room=None,
                                   gid_bbox=None, room_hull=None):
        """可折叠问题卡片（Streamlit 原生 expander），支持 3D 定位按钮。

        highlight_room: 3D 中点击构件所在的房间名，对应问题自动展开高亮。
        gid_bbox: 全局 GlobalId → viewer 坐标 bbox，用于构件级精确定位。
        room_hull: 房间名 → hull 轮廓框，用于房间内无构件时的兜底定位。
        """
        room_gids = room_gids or {}
        gid_bbox = gid_bbox or {}
        room_hull = room_hull or {}
        if not issues:
            return
        _tl = {"civil": T["disc_civil"], "eee": T["disc_eee"],
               "building": T["disc_bld"], "structural": T["disc_str"],
               "mep": T["disc_mep"], "accessibility": T["disc_acc"],
               "conflict": T["disc_conf"]}
        _tc = {"civil": C["blue"], "eee": C["orange"], "building": C["purple"],
               "structural": C["green"], "mep": "#1f6f8b",
               "accessibility": "#8a6d00", "conflict": C["red"]}
        _sc = {"High": C["red"], "Medium": C["orange"], "Low": C["silver"],
               "Missing": C["silver"], "Predictive": C["purple"]}
        for i, iss in enumerate(issues, 1):
            sev = iss.get("severity", "Medium")
            itype = iss.get("type", "")
            dot_color = _tc.get(itype, C["muted"])
            sev_color = _sc.get(sev, C["silver"])
            disc_label = _tl.get(itype, itype)
            floor_s = _floor_label(iss["floor_name"]) if iss.get("floor_name") else ""
            loc = iss.get("location", "-")
            ref = iss.get("code_ref", "-")
            desc = iss.get("description", "")
            bg = "#ffffff"
            if sev == "High":
                bg = "#FEF2F2"
            elif sev == "Medium" and itype == "building":
                bg = "#F8F5FC"

            # 3D 中点击的构件所在房间 → 该问题高亮展开
            is_highlight = bool(highlight_room) and str(iss.get("location", "")).strip() == str(highlight_room).strip()
            sev_dot = {"High": "🔴", "Medium": "🟠", "Predictive": "🟣"}.get(sev, "⚪")
            _prefix = "🎯 " if is_highlight else ""
            with st.expander(f"{_prefix}{sev_dot} {i}. {iss['title']}", expanded=is_highlight):
                # 标签行：严重度 + 学科
                st.markdown(
                    f'<span style="display:inline-block;font-size:11px;padding:2px 9px;'
                    f'border-radius:10px;background:{sev_color}20;color:{sev_color};'
                    f'font-weight:700;">{sev}</span>'
                    f'<span style="display:inline-block;font-size:11px;padding:2px 9px;'
                    f'border-radius:10px;background:{dot_color}15;color:{dot_color};'
                    f'font-weight:600;margin-left:6px;">{disc_label}</span>',
                    unsafe_allow_html=True)
                # 描述
                if desc:
                    st.markdown(
                        f'<div style="font-size:13px;color:#4B5563;line-height:1.75;'
                        f'margin-top:8px;">{desc}</div>',
                        unsafe_allow_html=True)
                # 位置 / 规范
                _meta = []
                if floor_s or loc and loc != "-":
                    _meta.append(f"📍 {floor_s}{'｜' if floor_s and loc else ''}{loc if loc != '-' else ''}")
                if ref and ref != "-":
                    _meta.append(f"📜 {ref}")
                if _meta:
                    st.caption("　　".join(_meta))

                # 定位到 3D 按钮（回调形式：在 rerun 前设好状态，避免"点两次"）
                btn_key = f"goto3d_{iss.get('rule_id','')}_{i}_{iss.get('location','')}"
                _h_pre, _cmd_pre = _goto_target_for_issue(iss, room_gids, gid_bbox, room_hull)

                def _go(_h=_h_pre, _c=_cmd_pre):
                    st.session_state["3d_target_hash"] = _h or ""
                    st.session_state["3d_cmd"] = json.dumps(_c, ensure_ascii=False) if _c else ""

                st.button("🌐 定位到 3D 模型", key=btn_key, on_click=_go,
                          use_container_width=True)

    def _render_aggregated_cards(cards, room_gids=None, gid_bbox=None, room_hull=None,
                                 key_prefix="agg"):
        """渲染聚合后的问题卡片：每张卡片 = 一条规则 × N 个实例，展开看明细。

        key_prefix 用于隔离不同分区（真实违规 / 数据缺失）的 widget key ——
        同一 rule_id 可能同时出现在两区（部分构件违规、部分构件缺字段），
        若共用命名空间会触发 StreamlitDuplicateElementKey。
        """
        room_gids = room_gids or {}
        gid_bbox = gid_bbox or {}
        room_hull = room_hull or {}
        _tl = {"civil": T["disc_civil"], "eee": T["disc_eee"],
               "building": T["disc_bld"], "structural": T["disc_str"],
               "mep": T["disc_mep"], "accessibility": T["disc_acc"],
               "conflict": T["disc_conf"]}
        _tc = {"civil": C["blue"], "eee": C["orange"], "building": C["purple"],
               "structural": C["green"], "mep": "#1f6f8b",
               "accessibility": "#8a6d00", "conflict": C["red"]}
        _sc = {"High": C["red"], "Medium": C["orange"], "Low": C["silver"],
               "Missing": C["silver"], "Predictive": C["purple"], "NotChecked": C["silver"]}
        _sev_dot = {"High": "🔴", "Medium": "🟠", "Low": "🟢",
                    "Missing": "⚪", "Predictive": "🟣", "NotChecked": "⚪"}

        for idx, card in enumerate(cards):
            sev = card.get("severity", "Low")
            itype = card.get("type", "")
            sev_color = _sc.get(sev, C["silver"])
            dot_color = _tc.get(itype, C["muted"])
            disc_label = _tl.get(itype, itype)
            sev_dot = _sev_dot.get(sev, "⚪")
            count = card.get("count", 0)
            title = card.get("title", "")
            rule_id = card.get("rule_id", "")
            by_floor = card.get("by_floor", {})
            items = card.get("items", [])

            floor_summary = ""
            if by_floor and len(by_floor) <= 4:
                parts = [f"{fl}:{cnt}" for fl, cnt in list(by_floor.items())[:4]]
                floor_summary = " · " + "  ".join(parts)
            elif by_floor:
                total_fl = len(by_floor)
                top3 = list(by_floor.items())[:3]
                parts = [f"{fl}:{cnt}" for fl, cnt in top3]
                floor_summary = f" · {total_fl} 层（{' '.join(parts)} …）"

            label = f"{sev_dot} {idx+1}. {title}"
            sub_info = f"[{rule_id}] {count} 处 · {disc_label}{floor_summary}"

            with st.expander(label, expanded=False):
                st.markdown(
                    f'<span style="display:inline-block;font-size:11px;padding:2px 9px;'
                    f'border-radius:10px;background:{sev_color}20;color:{sev_color};'
                    f'font-weight:700;">{sev}</span>'
                    f'<span style="display:inline-block;font-size:11px;padding:2px 9px;'
                    f'border-radius:10px;background:{dot_color}15;color:{dot_color};'
                    f'font-weight:600;margin-left:6px;">{disc_label}</span>'
                    f'<span style="display:inline-block;font-size:11px;padding:2px 9px;'
                    f'border-radius:10px;background:#f3f4f6;color:#6b7280;'
                    f'margin-left:6px;">{count} 处</span>',
                    unsafe_allow_html=True)

                if by_floor:
                    st.caption(f"📊 楼层分布：{', '.join(f'{fl} {cnt}处' for fl, cnt in by_floor.items())}")

                st.markdown(f"---\n**{T.get('detail_list', '明细')}（{count} 条）**")
                for j, iss in enumerate(items, 1):
                    floor_s = _floor_label(iss["floor_name"]) if iss.get("floor_name") else ""
                    loc = iss.get("location", "-")
                    ref = iss.get("code_ref", "-")
                    desc = iss.get("description", "")
                    _bg = "#f9fafb"
                    if sev == "High":
                        _bg = "#fef2f2"
                    st.markdown(
                        f'<div style="background:{_bg};border-radius:6px;padding:8px 12px;'
                        f'margin-bottom:6px;font-size:13px;line-height:1.6;">'
                        f'<div style="font-weight:600;">{j}. {loc}</div>'
                        f'<div style="color:#4b5563;margin-top:2px;">{desc}</div>'
                        f'<div style="font-size:11px;color:#9ca3af;margin-top:4px;">'
                        f'{floor_s}{"｜" if floor_s and ref and ref != "-" else ""}'
                        f'{"📜 " + ref if ref and ref != "-" else ""}</div>'
                        f'</div>',
                        unsafe_allow_html=True)

                    gids = iss.get("element_global_ids", [])
                    if gids:
                        def _go_issue(_i=iss, _rg=room_gids, _gb=gid_bbox, _rh=room_hull):
                            _h, _c = _goto_target_for_issue(_i, _rg, _gb, _rh)
                            st.session_state["3d_target_hash"] = _h or ""
                            st.session_state["3d_cmd"] = json.dumps(_c, ensure_ascii=False) if _c else ""
                        st.button("🌐 定位到 3D", key=f"{key_prefix}3d_{rule_id}_{idx}_{j}",
                                  on_click=_go_issue)

    def _render_summary_bar(summary):
        """渲染顶部审查总览条。"""
        high = summary["high_count"]
        med = summary["medium_count"]
        low = summary["low_count"]
        missing_rules = summary["missing_rule_count"]
        nc_rules = summary["not_checked_rule_count"]
        real_rules = summary["real_rule_count"]
        real_count = summary["real_violations"]

        st.markdown(
            f'<div style="background:linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);'
            f'border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px;'
            f'margin-bottom:14px;">'
            f'<div style="font-size:14px;font-weight:700;color:#1e293b;margin-bottom:8px;">'
            f'📋 {T.get("review_overview", "审查总览")}</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:10px 18px;font-size:13px;align-items:center;">'
            f'<span style="color:{C["red"]};font-weight:600;">🔴 高 {high}</span>'
            f'<span style="color:{C["orange"]};font-weight:500;">🟠 中 {med}</span>'
            f'<span style="color:#65a30d;font-weight:500;">🟢 低 {low}</span>'
            f'<span style="color:#64748b;margin-left:8px;">共 {real_rules} 类 · {real_count} 处</span>'
            f'</div>'
            f'<div style="margin-top:8px;font-size:12px;color:#94a3b8;">'
            f'⚪ 数据缺失：{missing_rules} 类规则缺少字段 · 未检查：{nc_rules} 类规则</div>'
            f'</div>',
            unsafe_allow_html=True)

    def _render_conflict_section(conflicts, compact=False):
        """冲突问题区块：⚠️ 红色标题条 + 可折叠卡片，与普通问题卡片视觉一致。"""
        if not conflicts:
            return
        st.markdown(
            f'<div style="background:#FEF2F2;border:1px solid #FECACA;'
            f'border-radius:8px;padding:10px 16px;margin:14px 0 10px;">'
            f'<span style="font-weight:700;font-size:15px;color:{C["red"]};">'
            f'⚠️ {T["tab_conf"]}（{len(conflicts)}）</span>'
            f'<span style="font-size:11.5px;color:{C["red"]};opacity:.75;'
            f'margin-left:10px;">构件之间存在冲突，需人工复核</span></div>',
            unsafe_allow_html=True)
        for i, iss in enumerate(conflicts, 1):
            sev = iss.get("severity", "High")
            floor_s = _floor_label(iss["floor_name"]) if iss.get("floor_name") else ""
            loc = iss.get("location", "") or ""
            ref = iss.get("code_ref", "") or ""
            with st.expander(f"🔴 {i}. {iss['title']}", expanded=False):
                st.markdown(
                    f'<span style="display:inline-block;font-size:11px;'
                    f'padding:2px 9px;border-radius:10px;background:{C["red"]}20;'
                    f'color:{C["red"]};font-weight:700;">{sev}</span>'
                    f'<span style="display:inline-block;font-size:11px;'
                    f'padding:2px 9px;border-radius:10px;background:{C["red"]}12;'
                    f'color:{C["red"]};font-weight:600;margin-left:6px;">{T["disc_conf"]}</span>',
                    unsafe_allow_html=True)
                _d = iss.get("description", "")
                if _d:
                    st.markdown(
                        f'<div style="font-size:13px;color:#4B5563;line-height:1.75;'
                        f'margin-top:8px;">{_d}</div>', unsafe_allow_html=True)
                _m = []
                if floor_s or loc:
                    _m.append(f"📍 {floor_s}{'｜' if floor_s and loc else ''}{loc}")
                if ref:
                    _m.append(f"📜 {ref}")
                if _m:
                    st.caption("　　".join(_m))


    def _render_element_detail(el_id, floor_data, all_issues, bdata):
        """Render detail panel for a clicked plan element."""
        if not floor_data:
            return
        # 找这个构件（从 plan_elements 里）
        el = None
        for pe in floor_data.get("plan_elements", []):
            if pe.get("id") == el_id or pe.get("global_id") == el_id:
                el = pe
                break
        if not el:
            # 可能是房间
            for r in floor_data.get("rooms", []):
                if r.get("room_id") == el_id or r.get("id") == el_id or str(r.get("name", "")) == str(el_id):
                    el = {"kind": "room", **r}
                    break
        if not el:
            st.caption(f"构件 ID: {el_id[:30]}...")
            return

        kind = el.get("kind", "unknown")
        name = el.get("name", "—")
        with st.container(border=True):
            st.markdown(f'<div style="font-weight:700;font-size:14px;color:{C["orange"]};margin-bottom:4px;">'
                        f'📌 {name}</div>', unsafe_allow_html=True)
            st.caption(f"类型: {kind} · 楼层: {_floor_label(floor_data.get('floor_name', ''))}")

            # 几何字段
            bbox = el.get("bbox")
            if bbox and len(bbox) >= 6:
                dx = round(bbox[2] - bbox[0], 3)
                dy = round(bbox[3] - bbox[1], 3)
                dz = round(bbox[5] - bbox[4], 3)
                cols = st.columns(3)
                cols[0].metric("X (m)", dx)
                cols[1].metric("Y (m)", dy)
                cols[2].metric("Z (m)", dz)

            # 房间面积
            if kind == "room" and el.get("room_area_sqm"):
                st.metric("面积 (m²)", el["room_area_sqm"])

            # 关联的审查问题
            el_issues = []
            for iss in all_issues:
                loc = iss.get("location", "") or ""
                # 房间名匹配
                if kind == "room" and name and str(name) in str(loc):
                    el_issues.append(iss)
                # 构件级匹配（按 element_id，如果问题里带的话）
                elif iss.get("element_id") == el_id:
                    el_issues.append(iss)
            if el_issues:
                st.markdown(f'<div style="font-weight:600;font-size:12px;color:{C["red"]};margin:8px 0 4px;">'
                            f'⚠️ 关联问题 ({len(el_issues)})</div>', unsafe_allow_html=True)
                for iss in el_issues[:3]:
                    sev = iss.get("severity", "Low")
                    st.markdown(f'<div style="font-size:12px;padding:4px 6px;background:{C["red"]}10;'
                                f'border-radius:3px;margin-bottom:3px;">'
                                f'<span style="font-weight:600;">{iss.get("rule_id","")}</span> '
                                f'{iss.get("title","")} '
                                f'<span style="color:{C["red"]};float:right;">{sev}</span></div>',
                                unsafe_allow_html=True)
                if len(el_issues) > 3:
                    st.caption(f"……还有 {len(el_issues) - 3} 条")
            else:
                st.markdown(f'<div style="font-size:12px;color:{C["green"]};padding:4px;'
                            f'background:{C["green"]}10;border-radius:3px;text-align:center;">'
                            f'✅ 该构件无关联违规</div>', unsafe_allow_html=True)

            # ID
            if el_id:
                with st.expander("ID / 技术信息"):
                    st.code(f"GlobalId: {el_id}\nType: {el.get('ifc_type', kind)}", language=None)


    # 桥接组件：双向通道
    #   viewer → Python：点击构件回传 globalId
    #   Python → viewer：把定位指令 postMessage 推给 viewer（不依赖 iframe 重载，实时生效）
    _cmd = st.session_state.get("3d_cmd", "")
    _clicked = _click_bridge(command=_cmd, key="viewer_click_bridge")
    if _clicked and isinstance(_clicked, dict):
        if _clicked.get("type") == "elementClicked":
            st.session_state["3d_clicked_gid"] = _clicked.get("globalId", "")
            st.session_state["3d_clicked_name"] = _clicked.get("name", "")
            st.session_state["3d_clicked_ifcType"] = _clicked.get("ifcType", "")
        elif _clicked.get("type") == "elementUnclicked":
            st.session_state["3d_clicked_gid"] = ""


    with _col_r:
        _rtab_iss, _rtab_plan = st.tabs(["⑤ 审查问题", "④ 楼层平面图"])
        with _rtab_iss:
            with st.container(height=816, border=False):
                    _all_issues = civil_r + eee_r + building_r + structural_r + mep_r + acc_r + predictive_r
                    _cov_findings = st.session_state.get("coverage_findings", [])
                    _full_result = {"all_issues": _all_issues,
                                    "coverage_findings": _cov_findings,
                                    "conflicts": conflicts}
                    _summary = engine.build_review_summary(_full_result)

                    # 总览条
                    _render_summary_bar(_summary)

                    _filter_all_label = T["filter_all"] + "（不含冲突）"
                    _fopt = {_filter_all_label: "all",
                             T["disc_civil"]: "civil",
                             T["disc_eee"]: "eee",
                             T["disc_bld"]: "building",
                             T["disc_str"]: "structural",
                             T["disc_mep"]: "mep",
                             T["disc_acc"]: "accessibility",
                             T["disc_conf"]: "conflict"}
                    _flt_label = st.radio(
                        "filter", options=list(_fopt.keys()),
                        horizontal=True, label_visibility="collapsed", key="find_flt")
                    _fid = _fopt[_flt_label]

                    _is_conflict_tab = (_fid == "conflict")
                    _findings = []
                    _missing_findings = []
                    if not _is_conflict_tab:
                        if _fid == "all":
                            _raw_findings = _all_issues
                        else:
                            _raw_findings = [i for i in _all_issues if i.get("type") == _fid]
                        # 拆分真实违规和 Missing
                        _findings = [i for i in _raw_findings
                                     if i.get("severity") in ("High", "Medium", "Low", "Critical", "Predictive")]
                        _missing_findings = [i for i in _raw_findings if i.get("severity") == "Missing"]

                    # 视角切换（仅非冲突 tab）
                    _view_mode = "rule"
                    if not _is_conflict_tab and _findings:
                        _vopt = {
                            T.get("view_by_rule", "按规则聚合"): "rule",
                            T.get("view_by_floor", "按楼层聚合"): "floor",
                            T.get("view_by_location", "按位置聚合"): "location",
                            T.get("view_list", "原始逐条"): "list",
                        }
                        _vlabel = st.radio(
                            "view", options=list(_vopt.keys()),
                            horizontal=True, label_visibility="collapsed", key="iss_view")
                        _view_mode = _vopt[_vlabel]

                    # 3D 反向联动：点击构件 → 高亮对应房间的问题
                    _room_gids = _room_element_gids(st.session_state.get("data_version", 0), bdata)
                    _clicked_gid = st.session_state.get("3d_clicked_gid", "")
                    _highlight_room = None
                    if _clicked_gid:
                        _gid_room = _build_gid_room_map(bdata)
                        _highlight_room = _gid_room.get(_clicked_gid)
                        if _highlight_room:
                            st.caption(f"🎯 3D 选中：{_highlight_room}（点击空白处取消）")

                    # 问题列表
                    if not _is_conflict_tab:
                        if _findings:
                            if _view_mode == "list":
                                _render_folded_issue_cards(
                                    _findings, _room_gids, _highlight_room,
                                    _build_gid_bbox_map(bdata), _room_hull_meta(bdata))
                            else:
                                _gb = "room" if _view_mode == "location" else _view_mode
                                _cards = engine.aggregate_issues(_findings, group_by=_gb)
                                _render_aggregated_cards(
                                    _cards, _room_gids,
                                    _build_gid_bbox_map(bdata), _room_hull_meta(bdata),
                                    key_prefix="real")
                        else:
                            st.info("当前筛选条件下无审查问题")

                        # 数据缺失（Missing）独立区域
                        if _missing_findings:
                            _m_cards = engine.aggregate_issues(_missing_findings, group_by="rule")
                            st.markdown(
                                f'<div style="margin:18px 0 6px;font-weight:700;font-size:13.5px;'
                                f'color:#64748b;">⚪ {T.get("missing_section", "数据缺失（无法判定）")}'
                                f' · {len(_m_cards)} 类规则 · 影响 {len(_missing_findings)} 处</div>',
                                unsafe_allow_html=True)
                            st.caption(T.get("missing_hint",
                                             "这些规则因模型缺少对应字段无法判定，不是违规。补齐字段后将自动启用。"))
                            _render_aggregated_cards(
                                _m_cards, _room_gids,
                                _build_gid_bbox_map(bdata), _room_hull_meta(bdata),
                                key_prefix="miss")

                    # 风险排序检修清单（预测层产物；仅 all/mep 筛选下展示）
                    if (not _is_conflict_tab and predictive_ranking
                            and _fid in ("all", "mep")):
                        st.markdown(
                            f'<div style="margin:14px 0 4px;font-weight:700;font-size:13.5px;'
                            f'color:{C["purple"]};">🟣 {T["predictive_ranking_title"]}</div>',
                            unsafe_allow_html=True)
                        st.caption(T["predictive_hint"])
                        _regime = (predictive_monitor or {}).get("regime")
                        if _regime == "inspection":
                            st.caption(f'🟣 {T["predictive_regime_inspection"]}')
                        elif _regime == "sensor":
                            st.caption(f'🟣 {T["predictive_regime_sensor"]}')
                        _top = predictive_ranking[:20]
                        st.dataframe(
                            pd.DataFrame({
                                T["predictive_col_rank"]: [r["rank"] for r in _top],
                                T["predictive_col_location"]: [r["location"] for r in _top],
                                T["predictive_col_floor"]: [r.get("floor_name") for r in _top],
                                T["predictive_col_prob"]: [r["p_fail_cycle"] for r in _top],
                                T["predictive_col_median"]: [r.get("median_failure_year") for r in _top],
                            }), hide_index=True, height=260, use_container_width=True)

                    # 冲突子区（非冲突 tab 下显示在底部；冲突 tab 下作为主内容）
                    if conflicts and _is_conflict_tab:
                        _render_conflict_section(conflicts)
                    elif conflicts and not _is_conflict_tab:
                        _render_conflict_section(conflicts, compact=True)
                    elif not conflicts and _is_conflict_tab:
                        st.info("当前无冲突问题")


        with _rtab_plan:
            with st.container(height=816, border=False):
                    floor_names = list(annotated_by_floor.keys())
                    if floor_names:
                        _sidx = st.radio(
                            T["floor_sel"], options=range(len(floor_names)),
                            format_func=lambda i: floor_names[i], index=0, horizontal=True,
                            label_visibility="collapsed", key="rs_floor")
                        _fn = floor_names[_sidx]
                        _floor_data = floors[_sidx] if _sidx < len(floors) else None

                        _vtab1, _vtab2 = st.tabs([
                            T.get("view_tab_static", "📐 标注图"),
                            T.get("view_tab_interactive", "🖱️ 交互查看"),
                        ])
                        with _vtab1:
                            st.markdown(f'<div style="font-weight:700;font-size:13px;color:{C["blue"]};margin-bottom:6px;">{_fn} — {T["view_top_t"]}</div>', unsafe_allow_html=True)
                            with st.container(border=True):
                                st.image(annotated_by_floor[_fn], width="stretch")
                            st.caption(T["before_cap"])

                        with _vtab2:
                            _floor_data = floor_by_name.get(_fn)
                            _rooms = _floor_data.get("rooms", []) if _floor_data else []
                            _plan_els = _floor_data.get("plan_elements", []) if _floor_data else []
                            if _rooms or _plan_els:
                                _floor_issues = [i for i in (civil_r + eee_r + mep_r + structural_r + acc_r)
                                                 if i.get("floor_id") == (_floor_data.get("floor_id") if _floor_data else "")
                                                 or i.get("floor_name") == _fn]
                                try:
                                    _fig = build_image_overlay_plan(_rooms, _plan_els, _fn, issues=_floor_issues)
                                    _sel = st.plotly_chart(
                                        _fig, width="stretch",
                                        on_select="rerun", key=f"plan_{_sidx}",
                                        selection_mode=["points"],
                                    )
                                    _sel_id = None
                                    if _sel and hasattr(_sel, "selection"):
                                        for _pt in getattr(_sel.selection, "points", []) or []:
                                            _cd = getattr(_pt, "customdata", None)
                                            if _cd:
                                                _sel_id = _cd if isinstance(_cd, str) else str(_cd)
                                                break
                                    if _sel_id:
                                        _render_element_detail(_sel_id, _floor_data, all_issues, bdata)
                                    else:
                                        st.caption(T.get("viewer_hint", "💡 悬停查看信息，点击构件查看详情"))
                                except Exception as _e:
                                    st.error(f"交互图加载失败：{_e}")
                                    st.image(annotated_by_floor[_fn], width="stretch", caption="(已降级为静态图)")
                            else:
                                st.info(T.get("viewer_no_data", "无平面图数据"))

    # ---- ⑥ Reasoner — LLM narrative / coordination ----
    st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["green"]};margin:22px 0 10px;">⑥ {T["agent_reasoner"]}</div>', unsafe_allow_html=True)
    ai_exp = st.expander(f"🤖 {T['ai_report_t']}")
    with ai_exp:
        if not llm.available():
            st.info(T["ai_unavailable"])
        else:
            if st.button(T["ai_generate_btn"], key="ai_gen"):
                with st.spinner("DeepSeek..."):
                    try:
                        st.session_state.ai_report = llm.generate_review_narrative(
                            civil_r, eee_r, building_r, conflicts, STD_META, LANG)
                        st.session_state.ai_coord = llm.coordinate_conflicts(
                            conflicts, STD_META, LANG)
                        st.session_state.ai_error = None
                    except Exception as ex:
                        st.session_state.ai_report = None
                        st.session_state.ai_coord = None
                        st.session_state.ai_error = str(ex)
            if st.session_state.get("ai_report"):
                st.markdown(st.session_state["ai_report"])
                if st.session_state.get("ai_coord"):
                    st.markdown("---")
                    st.markdown(
                        f'<div style="font-size:15px;font-weight:700;color:{C["purple"]};margin-bottom:6px;">'
                        f'{T["ai_coord_t"]}</div>', unsafe_allow_html=True)
                    st.markdown(st.session_state["ai_coord"])
            elif st.session_state.get("ai_error"):
                st.warning(f'{T["ai_fail_t"]}: {st.session_state["ai_error"]}')
            else:
                st.caption(T["ai_report_hint"])

    # Building-level correction suggestions
    if building_r:
        st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["purple"]};margin:20px 0 8px;">{T["bld_fix_t"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:13px;color:{C["muted"]};margin-bottom:12px;">{T["bld_fix_h"]}</div>', unsafe_allow_html=True)
        for iss in building_r:
            rid = iss.get("rule_id", "")
            fix = _fix_map().get(rid, iss.get("title", ""))
            st.markdown(f'''<div class="issue-card building">
            <div style="font-weight:700;font-size:14px;color:{C["purple"]};">{iss["title"]}</div>
            <div style="font-size:14px;color:{C["text"]};margin-top:6px;line-height:1.6;">{fix}</div>
            <div style="font-size:13px;color:{C["silver"]};margin-top:4px;font-family:monospace;">{T["ref"]}: {iss.get("code_ref","-")}</div>
            </div>''', unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["text"]};margin-bottom:12px;">{T["export_t"]}</div>', unsafe_allow_html=True)

    dc1, dc2, dc3, dc4 = st.columns(4)
    with dc1:
        if floor_names:
            first_floor = floor_names[0]
            buf_a = io.BytesIO()
            annotated_by_floor[first_floor].save(buf_a, format="PNG")
            st.download_button(T["dl_annotated"], data=buf_a.getvalue(), file_name=f"review_{first_floor}.png", mime="image/png", width="stretch")
    with dc2:
        if floor_names:
            first_floor = floor_names[0]
            buf_c = io.BytesIO()
            correction_by_floor[first_floor].save(buf_c, format="PNG")
            st.download_button(T["dl_correction"], data=buf_c.getvalue(), file_name=f"correction_{first_floor}.png", mime="image/png", width="stretch")
    with dc3:
        report_html = generate_report(annotated_by_floor, all_issues, civil_r, eee_r, building_r, structural_r, mep_r, conflicts, STD_META,
                                      predictive_r=predictive_r, predictive_ranking=predictive_ranking,
                                      predictive_monitor=predictive_monitor)
        st.download_button(T["dl_report"], data=report_html, file_name="archcheck_report.html", mime="text/html", width="stretch")
        import openpyxl
        _tlm = {"civil": T["disc_civil"], "eee": T["disc_eee"], "building": T["disc_bld"],
                "structural": T["disc_str"], "mep": T["disc_mep"], "conflict": T["disc_conf"]}
        _wb = openpyxl.Workbook()
        _ws = _wb.active
        _ws.title = "Review"
        _ws.append([T["col_rule"], T["col_title"], T["s_disc"], T["col_sev"],
                    T["col_floor"], T["loc"], T["ref"], T["col_status"], T["review_evid"]])
        for _iss in all_issues:
            _ws.append([_iss.get("rule_id", ""), _iss.get("title", ""),
                        _tlm.get(_iss.get("type", ""), _iss.get("type", "")),
                        _iss.get("severity", ""), _iss.get("floor_name", ""),
                        _iss.get("location", ""), _iss.get("code_ref", ""),
                        _iss.get("review_status", ""), (_iss.get("review_evidence", "") or "")[:120]])
        _ssheet = _wb.create_sheet(T["excel_summary_sheet"], 0)
        _ssheet.append([T["col_rule"], T["col_title"], T["col_sev"],
                        T["col_count"], T["report_distribution"]])
        for _c in engine.aggregate_issues(all_issues, group_by="rule"):
            _ssheet.append([_c["rule_id"], _c["title"], _c["severity"], _c["count"],
                            " · ".join(f"{fl}×{n}" for fl, n in _c["by_floor"].items())])
        _xb = io.BytesIO()
        _wb.save(_xb)
        st.download_button(T["dl_excel"], data=_xb.getvalue(), file_name="archcheck_results.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    with dc4:
        if st.button(T["new_review"], width="stretch"):
            goto("upload")
            st.session_state.uploaded_image = None
            st.session_state.civil_results = []
            st.session_state.eee_results = []
            st.session_state.building_results = []
            st.session_state.structural_results = []
            st.session_state.mep_results = []
            st.session_state.conflicts = []
            st.session_state.all_issues = []
            st.rerun()

# ---- ARCHITECTURE PAGE ----
# ---- REGULATION KNOWLEDGE BASE ----
elif st.session_state.page == "kb":
    st.markdown(f'<div class="aicher-label" style="margin-bottom:8px;">{T["kb_title"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:15px;color:{C["muted"]};margin-bottom:20px;max-width:860px;">{T["kb_sub"]}</div>', unsafe_allow_html=True)
    _manifest = json.loads((Path(__file__).resolve().parent / "scripts" / "rag_kb" / "kb_manifest.json").read_text(encoding="utf-8"))
    _kb_root = Path(__file__).resolve().parent / _manifest["kb_root"]
    _cats = _manifest["categories"]
    for _ck in ("SG_Free", "SG_Paid_Index", "CN_Mandatory", "CN_Reference"):
        _cat = _cats.get(_ck)
        if not _cat:
            continue
        st.markdown(f'<div style="font-size:21px;font-weight:700;color:{C["text"]};margin:26px 0 6px;">{_cat["label"]}</div>', unsafe_allow_html=True)
        for _sk, _sub in _cat["subdirs"].items():
            st.markdown(f'<div style="font-size:15px;font-weight:600;color:{C["muted"]};margin:14px 0 4px;">{_sub["label"]}</div>', unsafe_allow_html=True)
            for _doc in _sub["documents"]:
                _acc = _doc.get("access", "")
                _badge = T["kb_free"] if _acc == "free" else T["kb_paid"]
                _bcol = C["green"] if _acc == "free" else C["orange"]
                _fn = _doc.get("file", "")
                _full = _kb_root / _ck / _sk / _fn if _fn else None
                if LANG == "en":
                    _title = _doc.get("name_en") or _doc.get("name", "")
                    _std = _doc.get("standard_no_en") or _doc.get("standard_no", "")
                    _auth = _doc.get("authority_en") or _doc.get("authority")
                    _notes = _doc.get("notes_en") or _doc.get("notes")
                else:
                    _title = _doc.get("name_zh") or _doc.get("name", "")
                    _std = _doc.get("standard_no", "")
                    _auth = _doc.get("authority")
                    _notes = _doc.get("notes")
                with st.expander(f"{_title} — {_std}"):
                    st.markdown(f'<span style="font-size:12px;color:{_bcol};font-weight:600;padding:2px 8px;border-radius:2px;background:{_bcol}18;">{_badge}</span>', unsafe_allow_html=True)
                    for _k, _v in (("Authority", _auth), ("Year", _doc.get("year")),
                                   ("Status", _doc.get("status")), ("Scope", _doc.get("scope")),
                                   ("Source", _doc.get("source")), ("Notes", _notes)):
                        if _v:
                            st.caption(f"**{_k}:** {_v}")
                    if _full and _full.exists():
                        _txt = None
                        if _full.suffix.lower() == ".txt":
                            _txt = _full.read_text(encoding="utf-8", errors="ignore")
                        elif _full.suffix.lower() == ".pdf":
                            _sib = _full.with_suffix(".txt")
                            if _sib.exists():
                                _txt = _sib.read_text(encoding="utf-8", errors="ignore")
                            else:
                                try:
                                    from pypdf import PdfReader
                                    _rd = PdfReader(str(_full))
                                    _txt = "\n".join((p.extract_text() or "") for p in _rd.pages[:3])
                                except Exception:
                                    _txt = None
                        if _txt:
                            st.markdown(f"**{T['kb_content']}**")
                            st.code(_txt[:2000], language="")
                        else:
                            st.caption(f"{_full.name} — PDF")
                    else:
                        st.caption(T["kb_no_file"])

# ---- ARCHITECTURE PAGE ----
elif st.session_state.page == "architecture":
    arch_header = "ARCHCHECK · 架构" if LANG == "zh" else "ARCHCHECK · ARCHITECTURE"
    st.markdown(f'<div class="aicher-label" style="margin-bottom:8px;">{arch_header}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:40px;font-weight:800;color:{C["text"]};">{T["arch_title"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:16px;color:{C["muted"]};margin-bottom:24px;">{T["arch_sub"]}</div>', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin-bottom:12px;">{T["agents_t"]}</div>', unsafe_allow_html=True)

    ag1, ag2, ag3, ag4, ag5 = st.columns(5)
    with ag1:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["blue"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F3D7;</div>
        <div style="font-weight:700;font-size:16px;color:{C["blue"]};">{T["agent_reader"]}</div>
        <div style="font-size:12px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_reader_d"]}</div>
        <div style="font-size:12px;color:{C["silver"]};margin-top:12px;line-height:1.6;white-space:pre-line;">{T["arch_agent_reader_c"]}</div>
        <div style="margin-top:12px;padding:4px 8px;display:inline-block;background:{C["blue"]}12;border-radius:2px;font-size:11px;color:{C["blue"]};font-family:monospace;">{T["arch_agent_reader_tag"]}</div>
        </div>''', unsafe_allow_html=True)
    with ag2:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["orange"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x2696;</div>
        <div style="font-weight:700;font-size:16px;color:{C["orange"]};">{T["agent_judge"]}</div>
        <div style="font-size:12px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_judge_d"]}</div>
        <div style="font-size:12px;color:{C["silver"]};margin-top:12px;line-height:1.6;white-space:pre-line;">{T["arch_agent_judge_c"]}</div>
        <div style="margin-top:12px;padding:4px 8px;display:inline-block;background:{C["orange"]}12;border-radius:2px;font-size:11px;color:{C["orange"]};font-family:monospace;">{T["arch_agent_judge_tag"]}</div>
        </div>''', unsafe_allow_html=True)
    with ag3:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["purple"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F4DA;</div>
        <div style="font-weight:700;font-size:16px;color:{C["purple"]};">{T["agent_kb"]}</div>
        <div style="font-size:12px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_kb_d"]}</div>
        <div style="font-size:12px;color:{C["silver"]};margin-top:12px;line-height:1.6;white-space:pre-line;">{T["arch_agent_kb_c"]}</div>
        <div style="margin-top:12px;padding:4px 8px;display:inline-block;background:{C["purple"]}12;border-radius:2px;font-size:11px;color:{C["purple"]};font-family:monospace;">{T["arch_agent_kb_tag"]}</div>
        </div>''', unsafe_allow_html=True)
    with ag4:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["red"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F50D;</div>
        <div style="font-weight:700;font-size:16px;color:{C["red"]};">{T["agent_reviewer"]}</div>
        <div style="font-size:12px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_reviewer_d"]}</div>
        <div style="font-size:12px;color:{C["silver"]};margin-top:12px;line-height:1.6;white-space:pre-line;">{T["arch_agent_reviewer_c"]}</div>
        <div style="margin-top:12px;padding:4px 8px;display:inline-block;background:{C["red"]}12;border-radius:2px;font-size:11px;color:{C["red"]};font-family:monospace;">{T["arch_agent_reviewer_tag"]}</div>
        </div>''', unsafe_allow_html=True)
    with ag5:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["green"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F9E0;</div>
        <div style="font-weight:700;font-size:16px;color:{C["green"]};">{T["agent_reasoner"]}</div>
        <div style="font-size:12px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_reasoner_d"]}</div>
        <div style="font-size:12px;color:{C["silver"]};margin-top:12px;line-height:1.6;white-space:pre-line;">{T["arch_agent_reasoner_c"]}</div>
        <div style="margin-top:12px;padding:4px 8px;display:inline-block;background:{C["green"]}12;border-radius:2px;font-size:11px;color:{C["green"]};font-family:monospace;">{T["arch_agent_reasoner_tag"]}</div>
        </div>''', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin:32px 0 12px;">{T["pipeline_t"]}</div>', unsafe_allow_html=True)
    f1, f2, f3, f4, f5 = st.columns([2, 0.3, 2, 0.3, 2])
    with f1:
        st.markdown(f'<div class="flow-node" style="background:{C["blue"]}12;color:{C["blue"]};border:1px solid {C["blue"]}30;">{T["arch_p1"]}<br><span style="font-weight:400;font-size:12px;">{T["arch_p1s"]}</span></div>', unsafe_allow_html=True)
    with f2:
        st.markdown(f'<div style="font-size:28px;color:{C["silver"]};text-align:center;padding-top:8px;">→</div>', unsafe_allow_html=True)
    with f3:
        st.markdown(f'<div class="flow-node" style="background:{C["text"]}08;color:{C["text"]};border:1px solid {C["text"]}20;">{T["arch_p2"]}<br><span style="font-weight:400;font-size:12px;">{T["arch_p2s"]}</span></div>', unsafe_allow_html=True)
    with f4:
        st.markdown(f'<div style="font-size:28px;color:{C["silver"]};text-align:center;padding-top:8px;">→</div>', unsafe_allow_html=True)
    with f5:
        st.markdown(f'<div class="flow-node" style="background:{C["green"]}12;color:{C["green"]};border:1px solid {C["green"]}30;">{T["arch_p3"]}<br><span style="font-weight:400;font-size:12px;">{T["arch_p3s"]}</span></div>', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin:32px 0 12px;">{T["std_t"]}</div>', unsafe_allow_html=True)
    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown(f'''<div class="aicher-card">
        <div style="font-size:32px;margin-bottom:8px;">🇨🇳</div>
        <div style="font-weight:700;font-size:16px;">{T["arch_std_cn_t"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;white-space:pre-line;">{T["arch_std_cn_d"]}</div>
        </div>''', unsafe_allow_html=True)
    with sc2:
        st.markdown(f'''<div class="aicher-card">
        <div style="font-size:32px;margin-bottom:8px;">🇸🇬</div>
        <div style="font-weight:700;font-size:16px;">{T["arch_std_sg_t"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;white-space:pre-line;">{T["arch_std_sg_d"]}</div>
        </div>''', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin:32px 0 12px;">{T["tech_t"]}</div>', unsafe_allow_html=True)
    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    with tc1:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F40D;</div><div style="font-weight:700;font-size:15px;">Python 3</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">{T["arch_tech_py"]}</div></div>', unsafe_allow_html=True)
    with tc2:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F4CA;</div><div style="font-weight:700;font-size:15px;">Streamlit</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">{T["arch_tech_st"]}</div></div>', unsafe_allow_html=True)
    with tc3:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F5BC;</div><div style="font-weight:700;font-size:15px;">Pillow (PIL)</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">{T["arch_tech_pil"]}</div></div>', unsafe_allow_html=True)
    with tc4:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F4CB;</div><div style="font-weight:700;font-size:15px;">JSON Rules</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">{T["arch_tech_json"]}</div></div>', unsafe_allow_html=True)
    with tc5:
        st.markdown(f'<div class="tech-card"><div style="font-size:36px;margin-bottom:8px;">&#x1F3E2;</div><div style="font-weight:700;font-size:15px;">Multi-Floor</div><div style="font-size:12px;color:{C["silver"]};margin-top:2px;">{T["arch_tech_mf"]}</div></div>', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin:32px 0 12px;">{T["roadmap_t"]}</div>', unsafe_allow_html=True)
    rm1, rm2, rm3 = st.columns(3)
    with rm1:
        st.markdown(f'''<div class="roadmap-card">
        <div style="font-size:12px;letter-spacing:0.12em;font-weight:700;color:{C["blue"]};margin-bottom:6px;">{T["arch_p1_label"]}</div>
        <div style="font-weight:700;font-size:16px;color:{C["text"]};">{T["arch_p1_t"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;">{T["arch_p1_d"]}</div>
        </div>''', unsafe_allow_html=True)
    with rm2:
        st.markdown(f'''<div class="roadmap-card">
        <div style="font-size:12px;letter-spacing:0.12em;font-weight:700;color:{C["orange"]};margin-bottom:6px;">{T["arch_p2_label"]}</div>
        <div style="font-weight:700;font-size:16px;color:{C["text"]};">{T["arch_p2_t"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;">{T["arch_p2_d"]}</div>
        </div>''', unsafe_allow_html=True)
    with rm3:
        st.markdown(f'''<div class="roadmap-card">
        <div style="font-size:12px;letter-spacing:0.12em;font-weight:700;color:{C["silver"]};margin-bottom:6px;">{T["arch_p3_label"]}</div>
        <div style="font-weight:700;font-size:16px;color:{C["text"]};">{T["arch_p3_t"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:6px;line-height:1.6;">{T["arch_p3_d"]}</div>
        </div>''', unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)
    if st.button(T["back_upload_arch"], width="stretch"):
        goto("upload")
        st.rerun()

