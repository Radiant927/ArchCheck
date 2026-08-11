"""
ArchCheck — Building Plan Automated Review Platform
Multi-floor support · Standard switching (CN GB / SG FC23)
"""
import io
import json
import time
from pathlib import Path

import streamlit as st
from PIL import Image

from core import engine
import core.i18n as i18n
from core.config import C, OUTPUT
from core.drawing import (generate_sample_image, annotate_image,
                          generate_correction_image, generate_building_section,
                          generate_building_3d, render_room_plan, annotate_room_plan,
                          _fix_map)
from core.report import generate_report
from core.i18n import _room_type_label, _floor_label
from core.engine import DEMO_DATA, run_full_review
from bim.parser import parse_ifc, build_review_data
import llm.client as llm

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
.tag-disc-conflict {{ background:{C["red"]}18; color:{C["red"]}; }}
.tag-sev-high {{ background:{C["red"]}18; color:{C["red"]}; }}
.tag-sev-medium {{ background:{C["orange"]}18; color:{C["orange"]}; }}
.tag-sev-low {{ background:{C["silver"]}18; color:{C["silver"]}; }}
.tag-sev-missing {{ background:{C["silver"]}18; color:{C["silver"]}; }}
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
        bp_updated = {
            "total_floors": int(fl), "ground_floor_exit_width_m": bw,
            "fire_pool_volume_m3": fp, "transformer_capacity_kw": tc,
            "emergency_power_duration_min": ep,
            "occupancy_type": bp.get("occupancy_type", "office"),
            "fire_elevator_count": bp.get("fire_elevator_count", 1),
        }
    floors = bdata.get("floors", [])
    floor_tabs = st.tabs([_floor_label(f.get("floor_name", f.get("floor_id", f"F{i}"))) for i, f in enumerate(floors)])
    updated_floors = []
    for ti, (tab, floor) in enumerate(zip(floor_tabs, floors)):
        with tab:
            updated_rooms = []
            for room in floor.get("rooms", []):
                rid = room["id"]
                st.markdown(
                    f'<span style="font-weight:700;font-size:14px;">{room["name"]}</span> '
                    f'<span style="color:{C["silver"]};font-size:12px;">({_room_type_label(room["type"])})</span>',
                    unsafe_allow_html=True,
                )
                a1, a2, a3, a4 = st.columns(4)
                area = a1.number_input(f"🟢 {T['p_area']}", value=float(room.get("room_area_sqm", 0)), key=f"{rid}_a", step=5.0)
                exits = a2.number_input(f"🟢 {T['p_exits']}", value=int(room.get("exit_count") or 1), key=f"{rid}_x", min_value=0, max_value=50)
                corr = a3.number_input(f"🟢 {T['p_corridor']}", value=float(room.get("corridor_length_m", 0)), key=f"{rid}_c", step=1.0)
                light = a4.checkbox(f"🟠 {T['p_light']}", value=bool(room.get("has_emergency_light", False)), key=f"{rid}_l")
                b1, b2, b3, b4 = st.columns(4)
                water = b1.number_input(f"🟠 {T['p_water']}", value=float(room.get("dist_to_water_m", 5.0)), key=f"{rid}_w", step=0.1)
                circuit = b2.number_input(f"🟠 {T['p_load']}", value=float(room.get("circuit_load_a", 10)), key=f"{rid}_ld", step=1.0)
                outlet = b3.number_input(f"🟠 {T['p_outlet']}", value=float(room.get("outlet_spacing_m", 5.0)), key=f"{rid}_o", step=0.5)
                door = b4.number_input(f"🟢 {T['p_door']}", value=float(room.get("door_width_m") or 1.0), key=f"{rid}_d", step=0.1)
                updated_rooms.append({
                    "id": rid, "name": room["name"], "type": room["type"],
                    "room_area_sqm": area, "exit_count": exits, "corridor_length_m": corr,
                    "door_width_m": door, "has_emergency_light": light,
                    "dist_to_water_m": water, "circuit_load_a": circuit, "outlet_spacing_m": outlet,
                })
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
            })
    if st.button(T["save_btn"], width="stretch"):
        st.session_state.building_data = {
            "project_name": bdata.get("project_name", "Building"),
            "building_params": bp_updated,
            "floors": updated_floors,
        }
        st.success(T["save_ok"])
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
        ("🏗️", C["blue"], T["feat1_t"],
         f"IFC → 楼层/房间/构件\n模型健康度 QA\n门宽/疏散距离/截面" if LANG == "en" else
         f"IFC → 楼层/房间/构件\n模型健康度 QA\n门宽/疏散距离/截面"),
        ("⚖️", C["orange"], T["feat2_t"],
         f"消防/电气/结构/无障碍\n值 vs 阈值 · 动态阈值\n跨楼层聚合 · 冲突" if LANG == "en" else
         f"消防/电气/结构/无障碍\n值 vs 阈值 · 动态阈值\n跨楼层聚合 · 冲突"),
        ("🔍", C["red"], T["feat3_t"],
         f"RAG 检索规范原文复核\n已复核 ✅ / 待人工复核 ⚠️\n证据片段展示" if LANG == "en" else
         f"RAG 检索规范原文复核\n已复核 ✅ / 待人工复核 ⚠️\n证据片段展示"),
        ("🌐", C["purple"], T["feat4_t"],
         f"CN GB ↔ SG FC23 一键切换\n规则库配置化扩展\n双语界面" if LANG == "en" else
         f"CN GB ↔ SG FC23 一键切换\n规则库配置化扩展\n双语界面"),
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
            tmp = OUTPUT / "uploaded_building.ifc"
            tmp.write_bytes(ifc_file.getvalue())
            try:
                struct = parse_ifc(tmp, max_floors=3, max_rooms_per_floor=6)
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
                        lvl = ch["level"]; msg = ch["message"]
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
                st.session_state.building_data = bdata
                st.session_state.data_version = st.session_state.get("data_version", 0) + 1
                st.session_state.model_qa = struct.get("qa") or {}
                if struct["total_rooms"] == 0:
                    st.warning(T["ifc_no_rooms"])
                first_rooms = bdata["floors"][0]["rooms"] if bdata.get("floors") else []
                if first_rooms:
                    st.session_state.uploaded_image, _ = render_room_plan(
                        first_rooms, bdata["floors"][0]["floor_name"])
                else:
                    st.session_state.uploaded_image = generate_sample_image(struct.get("file_name", "BIM"), variant=0)
                st.session_state.civil_results = []
                st.session_state.eee_results = []
                st.session_state.building_results = []
                st.session_state.structural_results = []
                st.session_state.conflicts = []
                st.session_state.all_issues = []
                total_doors = sum(f["structure"]["doors"] for f in struct["floors"])
                st.success(
                    f'{T["ifc_parsed"]} {struct["storey_count"]} {T["ifc_storey_lbl"]} · '
                    f'{T["ifc_footprint_lbl"]} {struct["building_footprint_area_sqm"]} m² · '
                    f'房间 {struct["total_rooms"]} · 门 {total_doors} 扇')
                for f in struct["floors"]:
                    s = f["structure"]
                    if LANG == "zh":
                        line = (f'<b>{f["name"]}</b> — 占地 {f["footprint_area_sqm"]}m² · '
                                f'房间 {len(f["rooms"])} · 墙 {s["walls"]} · 门 {s["doors"]} · '
                                f'窗 {s["windows"]} · 门宽 {s["door_widths_m"]}m')
                    else:
                        line = (f'<b>{f["name"]}</b> — footprint {f["footprint_area_sqm"]}m² · '
                                f'rooms {len(f["rooms"])} · walls {s["walls"]} · doors {s["doors"]} · '
                                f'windows {s["windows"]} · door widths {s["door_widths_m"]}m')
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

    # Uploaded IFC → generated plan views (3D / per-floor / section)
    _bdata = st.session_state.get("building_data")
    if _bdata and _bdata.get("floors"):
        st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:22px;font-weight:700;color:{C["text"]};margin:8px 0 4px;">{T["plans_t"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:13px;color:{C["muted"]};margin-bottom:12px;">{T["plans_h"]}</div>', unsafe_allow_html=True)
        p1, p2 = st.columns([3, 2])
        with p1:
            with st.container(border=True):
                st.image(generate_building_3d(_bdata["floors"]), width="stretch")
        with p2:
            _fnn = [_floor_label(f.get("floor_name", f"F{i}")) for i, f in enumerate(_bdata["floors"])]
            _fli = st.radio(T["floor_sel"], options=range(len(_fnn)), format_func=lambda i: _fnn[i], index=0, horizontal=True, label_visibility="collapsed", key="up_floor")
            _plan, _rmap = render_room_plan(_bdata["floors"][_fli].get("rooms", []), _bdata["floors"][_fli].get("floor_name", ""))
            with st.container(border=True):
                st.image(_plan, width="stretch")
        st.markdown(f'<div style="font-weight:700;font-size:16px;color:{C["text"]};margin:16px 0 6px;">{T["section_t"]}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.image(generate_building_section(_bdata["floors"], [], [], [], []), width="stretch")

    if st.session_state.uploaded_image is not None:
        st.markdown("---")
        sc1, sc2, sc3 = st.columns([1, 2, 1])
        with sc2:
            if st.button(T["start_btn"], type="primary", width="stretch"):
                st.session_state.review_loading = True
                st.rerun()

    if st.session_state.uploaded_image is None:
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
    for fi, floor in enumerate(floors):
        fid = floor.get("floor_id", "")
        fname = _floor_label(floor.get("floor_name", fid))
        floor_civ = [i for i in civil_r if i.get("floor_id") == fid]
        floor_eee = [i for i in eee_r if i.get("floor_id") == fid]
        floor_issues = floor_civ + floor_eee
        rooms = floor.get("rooms", [])

        if rooms:
            # data-driven plan — real rooms packed by area, markers on room centroids
            base_img, room_map = render_room_plan(rooms, fname)
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
            _lv = _ch["level"]; _msg = _ch["message"]
            if _lv == "error":
                st.error(_msg)
            elif _lv == "warn":
                st.warning(_msg)
            else:
                st.info(_msg)

    # ② Compliance Judge — deterministic review
    st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["orange"]};margin:22px 0 10px;">② {T["agent_judge"]}</div>', unsafe_allow_html=True)

    high = sum(1 for i in all_issues if i.get("severity") == "High")

    _n_disc = sum(1 for r in (civil_r, eee_r, building_r, structural_r) if r)

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{len(all_issues)}</div><div class="label">{T["s_total"]}</div></div>', unsafe_allow_html=True)
    with s2:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{high}</div><div class="label">{T["s_high"]}</div></div>', unsafe_allow_html=True)
    with s3:
        st.markdown(f'<div class="aicher-stat red"><div class="value">{len(conflicts)}</div><div class="label">{T["s_conf"]}</div></div>', unsafe_allow_html=True)
    with s4:
        st.markdown(f'<div class="aicher-stat purple"><div class="value">{_n_disc}</div><div class="label">{T["s_disc"]}</div></div>', unsafe_allow_html=True)

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

    # ② whole-building section — vertical view of all floors
    sec_img = generate_building_section(floors, civil_r, eee_r, building_r, conflicts)
    st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["text"]};margin:24px 0 4px;">{T["section_t"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:13px;color:{C["muted"]};margin-bottom:12px;max-width:860px;">{T["section_h"]}</div>', unsafe_allow_html=True)
    sec_col1, sec_col2 = st.columns([3, 2])
    with sec_col1:
        with st.container(border=True):
            st.image(sec_img, width="stretch")
    with sec_col2:
        bld_n = len(building_r)
        if bld_n:
            st.markdown(
                f'<div style="font-size:18px;font-weight:700;color:{C["purple"]};margin-bottom:8px;">'
                f'{T["s_bld"]} ({bld_n})</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:13px;color:{C["muted"]};margin-bottom:12px;">{T["bld_blurb"]}</div>',
                unsafe_allow_html=True)
            for iss in building_r:
                st.markdown(
                    f'<div style="font-size:13px;padding:6px 0;border-bottom:1px solid {C["border"]};">'
                    f'<span style="color:{C["purple"]};font-weight:600;">●</span> {iss["title"]}<br>'
                    f'<span style="color:{C["silver"]};font-family:monospace;font-size:11px;">{iss.get("code_ref","")}</span></div>',
                    unsafe_allow_html=True)
        else:
            ok_msg = "所有全楼累积指标均符合规范要求。" if LANG == "zh" else "All building-level aggregates meet code requirements."
            st.markdown(
                f'<div style="font-size:16px;font-weight:700;color:{C["green"]};margin-bottom:8px;">'
                f'✓ {T["s_bld"]}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:13px;color:{C["muted"]};">{ok_msg}</div>',
                unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

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
                   "structural": T["disc_str"], "conflict": T["disc_conf"]}
            _itype = iss.get("type", "")
            _sev_cls = {"High": "high", "Medium": "medium", "Low": "low", "Missing": "missing"}.get(sev, "low")
            _disc_cls = {"civil": "civil", "eee": "eee", "building": "building",
                         "structural": "structural", "conflict": "conflict"}.get(_itype, "low")
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

    # ② Compliance Judge — unified findings (left) + floor plan (right)
    _fopt = {T["disc_civil"]: "civil", T["disc_eee"]: "eee", T["disc_bld"]: "building",
             T["disc_str"]: "structural", T["disc_conf"]: "conflict"}
    _flt = st.radio(
        "filter", options=[T["filter_all"]] + list(_fopt.keys()),
        horizontal=True, label_visibility="collapsed", key="find_flt")
    _findings = civil_r + eee_r + building_r + structural_r
    if _flt != T["filter_all"]:
        _fid = _fopt[_flt]
        _findings = [i for i in _findings if i.get("type") == _fid]

    _lcol, _rcol = st.columns([3, 2])
    with _lcol:
        if _findings:
            render_issue_cards(_findings, "all")
        else:
            st.success(T["no_issue"])
        if conflicts:
            st.markdown(
                f'<div style="font-size:15px;font-weight:700;color:{C["red"]};margin:18px 0 6px;">'
                f'{T["tab_conf"]} ({len(conflicts)})</div>',
                unsafe_allow_html=True,
            )
            render_issue_cards(conflicts, "conflict")
    with _rcol:
        st.markdown(f'<div style="font-weight:700;font-size:15px;color:{C["blue"]};margin-bottom:6px;">🏗️ {T["view3d_t"]}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.image(generate_building_3d(floors), width="stretch")
        floor_names = list(annotated_by_floor.keys())
        if floor_names:
            _sidx = st.radio(
                T["floor_sel"], options=range(len(floor_names)),
                format_func=lambda i: floor_names[i], index=0, horizontal=True,
                label_visibility="collapsed", key="rs_floor")
            _fn = floor_names[_sidx]
            st.markdown(f'<div style="font-weight:700;font-size:15px;color:{C["blue"]};margin-bottom:6px;">📐 {_fn} — {T["view_top_t"]}</div>', unsafe_allow_html=True)
            with st.container(border=True):
                st.image(annotated_by_floor[_fn], width="stretch")
            st.caption(T["before_cap"])

    # ---- ④ Reasoner — LLM narrative / coordination ----
    st.markdown(f'<div style="font-size:18px;font-weight:700;color:{C["green"]};margin:22px 0 10px;">④ {T["agent_reasoner"]}</div>', unsafe_allow_html=True)
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
        report_html = generate_report(annotated_by_floor, all_issues, civil_r, eee_r, building_r, structural_r, conflicts, STD_META)
        st.download_button(T["dl_report"], data=report_html, file_name="archcheck_report.html", mime="text/html", width="stretch")
        import openpyxl
        _tlm = {"civil": T["disc_civil"], "eee": T["disc_eee"], "building": T["disc_bld"],
                "structural": T["disc_str"], "conflict": T["disc_conf"]}
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
                _title = _doc.get("name_zh") or _doc.get("name", "")
                _std = _doc.get("standard_no", "")
                with st.expander(f"{_title} — {_std}"):
                    st.markdown(f'<span style="font-size:12px;color:{_bcol};font-weight:600;padding:2px 8px;border-radius:2px;background:{_bcol}18;">{_badge}</span>', unsafe_allow_html=True)
                    for _k, _v in (("Authority", _doc.get("authority")), ("Year", _doc.get("year")),
                                   ("Status", _doc.get("status")), ("Scope", _doc.get("scope")),
                                   ("Source", _doc.get("source")), ("Notes", _doc.get("notes"))):
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

