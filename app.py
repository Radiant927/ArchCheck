"""
ArchCheck — Building Plan Automated Review Platform
Multi-floor support · Standard switching (CN GB / SG FC23)
"""
import io
import time

import streamlit as st
from PIL import Image

from core import engine
import core.i18n as i18n
from core.config import C, OUTPUT
from core.drawing import (generate_sample_image, annotate_image,
                          generate_correction_image, generate_building_section,
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
    std_idx = 0 if st.session_state.standard == "cn" else 1
    new_std = st.radio(
        "Standard",
        options=["cn", "sg"],
        format_func=lambda x: T["std_cn"] if x == "cn" else T["std_sg"],
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
    page_labels = {"upload": T["nav_upload"], "results": T["nav_results"], "architecture": T["nav_arch"]}
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
        st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
        st.image(uimg)
        st.markdown('</div>', unsafe_allow_html=True)
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
    <span style="font-size:15px;font-weight:600;">{T["agent_civil"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["orange"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_eee"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["purple"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_bld"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:14px;height:14px;background:{C["red"]};border-radius:2px;"></div>
    <span style="font-size:15px;font-weight:600;">{T["agent_coord"]}</span>
    </div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    f1, f2, f3, f4 = st.columns(4)
    features = [
        ("📐", C["blue"], T["feat1_t"],
         f"Evacuation distance · Fire zones\nEmergency exits · Door width\n{STD_META.get('civil_codes','')}" if LANG == "en" else
         f"疏散距离 · 防火分区\n安全出口 · 疏散门宽\n{STD_META.get('civil_codes','')}"),
        ("⚡", C["orange"], T["feat2_t"],
         f"Emergency lighting · Water clearance\nCircuit load · Outlet spacing\n{STD_META.get('eee_codes','')}" if LANG == "en" else
         f"应急照明 · 水源间距\n回路负荷 · 插座间距\n{STD_META.get('eee_codes','')}"),
        ("🏢", C["purple"], T["feat3_t"], T["feat3_d"]),
        ("🔗", C["red"], T["feat4_t"], T["feat4_d"]),
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
            f'<div style="font-size:17px;font-weight:700;color:{C["text"]};margin-bottom:10px;">'
            f'{T["upload_t"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="font-size:14px;color:{C["muted"]};margin-bottom:8px;">'
            f'{T["upload_hint"]}</p>',
            unsafe_allow_html=True,
        )
        uf = st.file_uploader(
            T["upload_drag"],
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

        st.markdown("---")
        st.markdown(
            f'<div style="font-weight:700;font-size:15px;color:{C["text"]};margin-bottom:8px;">'
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
                if struct["total_rooms"] > 0:
                    # real rooms parsed from the IFC
                    bdata = build_review_data(struct)
                else:
                    # no spaces in the model — fall back to demo rooms per storey
                    demo_floors = DEMO_DATA.get("floors", [])
                    room_map = {f["name"]: demo_floors[i]["rooms"]
                                for i, f in enumerate(struct["floors"]) if i < len(demo_floors)}
                    bdata = build_review_data(struct, rooms_template=None, floor_room_map=room_map)
                st.session_state.building_data = bdata
                st.session_state.uploaded_image = generate_sample_image(struct.get("file_name", "BIM"), variant=0)
                st.session_state.civil_results = []
                st.session_state.eee_results = []
                st.session_state.building_results = []
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

        st.markdown(
            f'<div style="font-size:13px;color:{C["silver"]};margin:12px 0;text-align:center;">'
            f'{T["demo_or"]}</div>',
            unsafe_allow_html=True,
        )
        if st.button(T["demo_btn"], width="stretch"):
            demo_path = OUTPUT / "demo_architect_plan.png"
            first_fname = _floor_label(DEMO_DATA["floors"][0].get("floor_name", "1F"))
            if demo_path.exists():
                st.session_state.uploaded_image = Image.open(demo_path)
            else:
                st.session_state.uploaded_image = generate_sample_image(first_fname, variant=0)
            st.session_state.building_data = DEMO_DATA
            st.session_state.review_loading = True
            st.rerun()

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

        # Building-level params
        bdata = st.session_state.get("building_data") or DEMO_DATA
        bp = bdata.get("building_params", {})

        with st.expander(T["bld_params_t"], expanded=True):
            st.caption(T["bld_params_caption"])
            bp1, bp2 = st.columns(2)
            bw = bp1.number_input(T["p_ground_exit"], value=float(bp.get("ground_floor_exit_width_m", 2.4)), step=0.1, key="bp_bw")
            fp = bp2.number_input(T["p_fire_pool"], value=float(bp.get("fire_pool_volume_m3", 160)), step=10.0, key="bp_fp")
            tc = bp1.number_input(T["p_transformer"], value=float(bp.get("transformer_capacity_kw", 650)), step=50.0, key="bp_tc")
            ep = bp2.number_input(T["p_emergency"], value=float(bp.get("emergency_power_duration_min", 60)), step=10.0, key="bp_ep")
            fl = bp1.number_input(T["p_floors"], value=int(bp.get("total_floors", 3)), min_value=1, max_value=20, step=1, key="bp_fl")
            bp_updated = {
                "total_floors": int(fl), "ground_floor_exit_width_m": bw,
                "fire_pool_volume_m3": fp, "transformer_capacity_kw": tc,
                "emergency_power_duration_min": ep,
                "occupancy_type": bp.get("occupancy_type", "office"),
                "fire_elevator_count": bp.get("fire_elevator_count", 1),
            }

        # Per-floor room editing in tabs
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
                    area = a1.number_input(T["p_area"], value=float(room.get("room_area_sqm", 0)), key=f"{rid}_a", step=5.0)
                    exits = a2.number_input(T["p_exits"], value=int(room.get("exit_count", 1)), key=f"{rid}_x", min_value=0, max_value=4)
                    corr = a3.number_input(T["p_corridor"], value=float(room.get("corridor_length_m", 0)), key=f"{rid}_c", step=1.0)
                    light = a4.checkbox(T["p_light"], value=bool(room.get("has_emergency_light", False)), key=f"{rid}_l")
                    b1, b2, b3, b4 = st.columns(4)
                    water = b1.number_input(T["p_water"], value=float(room.get("dist_to_water_m", 5.0)), key=f"{rid}_w", step=0.1)
                    circuit = b2.number_input(T["p_load"], value=float(room.get("circuit_load_a", 10)), key=f"{rid}_ld", step=1.0)
                    outlet = b3.number_input(T["p_outlet"], value=float(room.get("outlet_spacing_m", 5.0)), key=f"{rid}_o", step=0.5)
                    door = b4.number_input(T["p_door"], value=float(room.get("door_width_m", 1.0)), key=f"{rid}_d", step=0.1)
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

    if st.session_state.uploaded_image is not None:
        st.markdown("---")
        sc1, sc2, sc3 = st.columns([1, 2, 1])
        with sc2:
            if st.button(T["start_btn"], type="primary", width="stretch"):
                if st.session_state.building_data is None:
                    st.session_state.building_data = DEMO_DATA
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
    conflicts = st.session_state.get("conflicts", [])
    all_issues = st.session_state.get("all_issues", [])
    bdata = st.session_state.get("building_data") or DEMO_DATA

    # Compute diff against the other standard for the standard-switching summary
    other_std_id = "sg" if st.session_state.standard == "cn" else "cn"
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

    high = sum(1 for i in all_issues if i.get("severity") == "High")

    s1, s2, s3, s4, s5, s6 = st.columns(6)
    with s1:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{len(all_issues)}</div><div class="label">{T["s_total"]}</div></div>', unsafe_allow_html=True)
    with s2:
        st.markdown(f'<div class="aicher-stat blue"><div class="value">{len(civil_r)}</div><div class="label">{T["s_civil"]}</div></div>', unsafe_allow_html=True)
    with s3:
        st.markdown(f'<div class="aicher-stat orange"><div class="value">{len(eee_r)}</div><div class="label">{T["s_eee"]}</div></div>', unsafe_allow_html=True)
    with s4:
        st.markdown(f'<div class="aicher-stat purple"><div class="value">{len(building_r)}</div><div class="label">{T["s_bld"]}</div></div>', unsafe_allow_html=True)
    with s5:
        st.markdown(f'<div class="aicher-stat red"><div class="value">{len(conflicts)}</div><div class="label">{T["s_conf"]}</div></div>', unsafe_allow_html=True)
    with s6:
        st.markdown(f'<div class="aicher-stat green"><div class="value">{high}</div><div class="label">{T["s_high"]}</div></div>', unsafe_allow_html=True)

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

    # ---- AI review report (LLM-generated) ----
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

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    # Building cross-section: visual floor connection
    sec_img = generate_building_section(floors, civil_r, eee_r, building_r, conflicts)
    sec_col1, sec_col2 = st.columns([3, 2])
    with sec_col1:
        st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
        st.image(sec_img, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
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

    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin-bottom:4px;">{T["before_after_t"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:14px;color:{C["muted"]};margin-bottom:16px;">{T["before_after_h"]}</div>', unsafe_allow_html=True)

    floor_names = list(annotated_by_floor.keys())
    if floor_names:
        selected_floor = st.radio(
            T["floor_sel"],
            options=range(len(floor_names)),
            format_func=lambda i: floor_names[i],
            index=0,
            horizontal=True,
            label_visibility="collapsed",
        )
        fname = floor_names[selected_floor]

        bc1, bc2 = st.columns(2)
        with bc1:
            st.markdown(f'<div style="font-weight:700;font-size:16px;color:{C["red"]};margin-bottom:6px;">{T["before_l"]} — {fname}</div>', unsafe_allow_html=True)
            st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
            st.image(annotated_by_floor[fname], use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption(T["before_cap"])
        with bc2:
            st.markdown(f'<div style="font-weight:700;font-size:16px;color:{C["green"]};margin-bottom:6px;">{T["after_l"]} — {fname}</div>', unsafe_allow_html=True)
            st.markdown('<div class="aicher-img-frame">', unsafe_allow_html=True)
            st.image(correction_by_floor[fname], use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption(T["after_cap"])

    st.markdown('<hr class="aicher-divider">', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs([
        f'{T["tab_civil"]} ({len(civil_r)})',
        f'{T["tab_eee"]} ({len(eee_r)})',
        f'{T["tab_bld"]} ({len(building_r)})',
        f'{T["tab_conf"]} ({len(conflicts)})',
    ])

    def render_issue_cards(issues, css_class, show_floor=True):
        if not issues:
            st.success(T["no_issue"])
            return
        for i, iss in enumerate(issues, 1):
            sev = iss.get("severity", "Medium")
            sev_color = {"High": C["red"], "Medium": C["orange"], "Low": C["silver"]}.get(sev, C["silver"])
            floor_tag = ""
            if show_floor and iss.get("floor_name"):
                floor_tag = f'<span class="floor-tag">{_floor_label(iss["floor_name"])}</span>'
            loc_label = T["loc"]
            ref_label = T["ref"]
            st.markdown(f'''<div class="issue-card {css_class}">
            <div style="font-weight:700;font-size:15px;">{i}. {iss["title"]}
            <span style="display:inline-block;margin-left:8px;padding:1px 8px;border-radius:2px;font-size:12px;font-weight:600;background:{sev_color}18;color:{sev_color};">{sev}</span>
            {floor_tag}</div>
            <div style="font-size:14px;color:{C["muted"]};margin-top:4px;">{iss.get("description","")}</div>
            <div style="font-size:13px;color:{C["silver"]};margin-top:4px;font-family:monospace;">{loc_label}: {iss.get("location","-")} | {ref_label}: {iss.get("code_ref","-")}</div>
            </div>''', unsafe_allow_html=True)

    with t1:
        render_issue_cards(civil_r, "civil")
    with t2:
        render_issue_cards(eee_r, "eee")
    with t3:
        st.markdown(
            f'<div style="font-size:13px;color:{C["muted"]};margin-bottom:12px;padding:10px;background:{C["purple"]}0a;border-radius:4px;">'
            f'{T["bld_blurb"]}</div>',
            unsafe_allow_html=True,
        )
        render_issue_cards(building_r, "building", show_floor=True)
    with t4:
        if conflicts:
            render_issue_cards(conflicts, "conflict")
        else:
            st.success(T["no_conflict"])

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
        report_html = generate_report(annotated_by_floor, all_issues, civil_r, eee_r, building_r, conflicts, STD_META)
        st.download_button(T["dl_report"], data=report_html, file_name="archcheck_report.html", mime="text/html", width="stretch")
    with dc4:
        if st.button(T["new_review"], width="stretch"):
            goto("upload")
            st.session_state.uploaded_image = None
            st.session_state.civil_results = []
            st.session_state.eee_results = []
            st.session_state.building_results = []
            st.session_state.conflicts = []
            st.session_state.all_issues = []
            st.rerun()

# ---- ARCHITECTURE PAGE ----
elif st.session_state.page == "architecture":
    arch_header = "ARCHCHECK · 架构" if LANG == "zh" else "ARCHCHECK · ARCHITECTURE"
    st.markdown(f'<div class="aicher-label" style="margin-bottom:8px;">{arch_header}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:40px;font-weight:800;color:{C["text"]};">{T["arch_title"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:16px;color:{C["muted"]};margin-bottom:24px;">{T["arch_sub"]}</div>', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:24px;font-weight:700;color:{C["text"]};margin-bottom:12px;">{T["agents_t"]}</div>', unsafe_allow_html=True)

    ag1, ag2, ag3, ag4 = st.columns(4)
    with ag1:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["blue"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F3D7;</div>
        <div style="font-weight:700;font-size:18px;color:{C["blue"]};">{T["agent_civil"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_civ_d"]}</div>
        <div style="font-size:13px;color:{C["silver"]};margin-top:14px;line-height:1.7;white-space:pre-line;">{T["arch_agent_civ_c"]}</div>
        <div style="margin-top:14px;padding:4px 10px;display:inline-block;background:{C["blue"]}12;border-radius:2px;font-size:12px;color:{C["blue"]};font-family:monospace;">{STD_META.get("civil_codes","")}</div>
        </div>''', unsafe_allow_html=True)
    with ag2:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["orange"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">⚡</div>
        <div style="font-weight:700;font-size:18px;color:{C["orange"]};">{T["agent_eee"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_eee_d"]}</div>
        <div style="font-size:13px;color:{C["silver"]};margin-top:14px;line-height:1.7;white-space:pre-line;">{T["arch_agent_eee_c"]}</div>
        <div style="margin-top:14px;padding:4px 10px;display:inline-block;background:{C["orange"]}12;border-radius:2px;font-size:12px;color:{C["orange"]};font-family:monospace;">{STD_META.get("eee_codes","")}</div>
        </div>''', unsafe_allow_html=True)
    with ag3:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["purple"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">🏢</div>
        <div style="font-weight:700;font-size:18px;color:{C["purple"]};">{T["agent_bld"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_bld_d"]}</div>
        <div style="font-size:13px;color:{C["silver"]};margin-top:14px;line-height:1.7;white-space:pre-line;">{T["arch_agent_bld_c"]}</div>
        <div style="margin-top:14px;padding:4px 10px;display:inline-block;background:{C["purple"]}12;border-radius:2px;font-size:12px;color:{C["purple"]};font-family:monospace;">{T["arch_agent_bld_tag"]}</div>
        </div>''', unsafe_allow_html=True)
    with ag4:
        st.markdown(f'''<div class="agent-card">
        <div style="width:48px;height:48px;border-radius:4px;background:{C["red"]}18;display:flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:14px;">&#x1F517;</div>
        <div style="font-weight:700;font-size:18px;color:{C["red"]};">{T["agent_coord"]}</div>
        <div style="font-size:13px;color:{C["muted"]};margin-top:4px;">{T["arch_agent_coord_d"]}</div>
        <div style="font-size:13px;color:{C["silver"]};margin-top:14px;line-height:1.7;white-space:pre-line;">{T["arch_agent_coord_c"]}</div>
        <div style="margin-top:14px;padding:4px 10px;display:inline-block;background:{C["red"]}12;border-radius:2px;font-size:12px;color:{C["red"]};font-family:monospace;">{T["arch_agent_coord_tag"]}</div>
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

