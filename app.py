"""
ArchCheck — Building Plan Automated Review Platform
Multi-floor support · Standard switching (CN GB / SG FC23)
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
DATA = HERE / "data"

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
    "purple": "#8E6BBF",
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

# ============================================================
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

# ============================================================
# STANDARDS LOADING
# ============================================================
def load_standard(standard_id):
    """Load rules + meta for a given standard (cn / sg)."""
    base = DATA / "standards" / standard_id
    fallback = {"civil": [], "eee": [], "building": [], "meta": {}}
    result = dict(fallback)
    for key, fname in [("civil", "civil_rules.json"), ("eee", "eee_rules.json"),
                       ("building", "building_rules.json"), ("meta", "meta.json")]:
        p = base / fname
        if p.exists():
            try:
                result[key] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return result

STD = load_standard(st.session_state.standard)
CIVIL_RULES = STD["civil"]
EEE_RULES = STD["eee"]
BUILDING_RULES = STD["building"]
STD_META = STD["meta"]
LANG = STD_META.get("language", "en")

# ============================================================
# BILINGUAL TEXT DICTIONARY
# ============================================================
_I18N = {
    "zh": {
        "platform_desc": "AI 驱动的多层建筑合规审查平台<br>多智能体：建筑 + 电气 + 全楼聚合 + 协调器",
        "std_label": "审查标准",
        "std_cn": "🇨🇳  中国标准 GB",
        "std_sg": "🇸🇬  新加坡标准 FC23",
        "active_std": "当前标准",
        "nav_upload": "上传与审查",
        "nav_results": "审查结果",
        "nav_arch": "平台架构",
        "version": "Aicher 系统 · v3.0",
        "hero_1": "上传楼层图纸，",
        "hero_2": "AI ",
        "hero_3": "多层合规审查",
        "hero_4": "自动化。",
        "hero_sub": "多智能体建筑合规自动审查平台——覆盖消防、电气、跨楼层累积量校核。支持中国 GB 与新加坡 Fire Code 2023 一键切换。",
        "agent_civil": "建筑 Agent · 消防安全",
        "agent_eee": "电气 Agent · 电气安全",
        "agent_bld": "全楼 Agent · 跨楼层累积",
        "agent_coord": "协调器 · 冲突检测",
        "feat1_t": "消防安全审查",
        "feat2_t": "电气安全审查",
        "feat3_t": "跨楼层累积校核",
        "feat4_t": "冲突检测",
        "feat3_d": "首层疏散外门总净宽 · 消防水池容积\n变压器装机容量 · 应急电源持续时间\n单层合规 ≠ 整楼合规",
        "feat4_d": "跨专业问题汇总\n同层冲突区域识别\n协同处置建议",
        "upload_t": "上传楼层平面图",
        "upload_hint": "支持 PNG / JPG / JPEG / PDF，最大 20MB。",
        "upload_drag": "拖拽图纸至此处上传",
        "demo_or": "— 或者 —",
        "demo_btn": "快速演示（加载三层示例建筑）",
        "data_t": "建筑数据参数",
        "data_hint": "编辑整楼参数与各楼层房间参数。参数将直接用于合规审查。",
        "bld_params_t": "整楼参数（跨楼层累积）",
        "bld_params_caption": "整楼汇总参数，按全楼阈值校核。",
        "p_ground_exit": "首层疏散外门总净宽 (m)",
        "p_fire_pool": "消防水池容积 (m³)",
        "p_transformer": "变压器装机容量 (kW)",
        "p_emergency": "应急电源持续时间 (min)",
        "p_floors": "楼层总数",
        "p_area": "面积 (m²)",
        "p_exits": "出口数",
        "p_corridor": "走廊长度 (m)",
        "p_light": "应急照明",
        "p_water": "距水源 (m)",
        "p_load": "负荷 (A)",
        "p_outlet": "插座间距 (m)",
        "p_door": "门宽 (m)",
        "p_fz_area": "面积 (m²)",
        "save_btn": "保存所有参数",
        "save_ok": "参数保存成功，可以开始审查。",
        "start_btn": "开始审查",
        "need_upload": "请先上传图纸或点击「快速演示」",
        "reviewing_title": "多智能体审查进行中...",
        "std_label_running": "标准",
        "floors_label": "楼层",
        "rooms_label": "房间",
        "zones_label": "防火分区",
        "status_init": "初始化审查引擎...",
        "status_parsing": "解析全楼建筑数据",
        "status_loaded": "建筑数据加载完成",
        "status_floor": "审查中",
        "status_bld": "全楼聚合：跨楼层累积量校核...",
        "status_coord": "协调器：合并结果并检测冲突...",
        "status_done": "审查完成",
        "back_upload": "返回上传",
        "results_title": "审查结果报告",
        "results_sub": "多层建筑自动合规审查 — 建筑 + 电气 + 全楼 + 协调器",
        "s_total": "问题总数",
        "s_civil": "建筑问题",
        "s_eee": "电气问题",
        "s_bld": "全楼问题",
        "s_conf": "冲突",
        "s_high": "高危",
        "before_after_t": "各楼层平面图 — 违规检测 / 修正建议",
        "before_after_h": "左：各 Agent 颜色标记违规点。右：绿色标注给出具体修正建议。",
        "floor_sel": "选择楼层",
        "before_l": "审查前 — 违规标注",
        "after_l": "审查后 — 修正建议",
        "before_cap": "蓝=建筑 · 橙=电气 · 编号对应下方问题列表",
        "after_cap": "绿色编号标记与右侧修正说明一一对应",
        "tab_civil": "建筑问题",
        "tab_eee": "电气问题",
        "tab_bld": "全楼累积问题",
        "tab_conf": "冲突区域",
        "no_issue": "该类别未发现问题。",
        "bld_blurb": "全楼问题是跨楼层累积计算得出的。各楼层单独审查可能均合规，但整楼汇总后超过规范阈值——这是分层审查最容易遗漏的盲区。",
        "loc": "位置",
        "ref": "规范",
        "export_t": "导出结果",
        "dl_annotated": "下载标注图（当前楼层）",
        "dl_correction": "下载修正图（当前楼层）",
        "dl_report": "下载 HTML 报告",
        "new_review": "新审查",
        "no_results": "未找到审查结果，请先上传图纸并开始审查。",
        "arch_title": "平台架构",
        "arch_sub": "面向多层、多标准合规审查的多智能体协同架构",
        "agents_t": "多智能体系统",
        "pipeline_t": "审查流水线",
        "p1": "1. 上传与配置",
        "p1s": "楼层图纸 + 参数 + 标准",
        "p2": "2. 多智能体审查",
        "p2s": "建筑 + 电气（分层）+ 全楼聚合",
        "p3": "3. 报告与修正",
        "p3s": "分层标注图 + 统一 HTML 报告",
        "std_t": "标准切换",
        "tech_t": "技术栈",
        "roadmap_t": "开发路线图",
        "bld_fix_t": "全楼修正建议",
        "bld_fix_h": "全楼累积问题的修正措施（无法在单层平面图上标注，单独列出）。",
        "diff_title": "标准切换差异",
        "diff_h": "在当前数据下，切换标准会产生以下变化：",
        "log_civil": "检查 {n} 个房间与防火分区",
        "log_eee": "检查电气安全",
        "log_bld": "聚合 {n} 层：首层门宽、消防水池、变压器、应急电源",
        "log_coord": "交叉索引同层跨专业冲突",
        "log_done": "报告生成完成：共 {total} 个问题，{n_conflicts} 个跨专业冲突，{n_bld} 个跨楼层问题",
        "status_done_detail": "{total} 个问题（{civ_n} 建筑，{eee_n} 电气，{n_bld} 全楼），{n_conflicts} 个冲突",
        "issue_pass": "该类别未发现问题。",
        "no_conflict": "各层均未发现跨专业冲突区域。",
        "fix_civ001": "增设避难走道，将疏散\n距离缩短至 ≤ 30m",
        "fix_civ002": "增设防火墙分隔，使每个\n防火分区面积 ≤ 限值",
        "fix_civ003": "增设第二个安全出口\n（>50m² 房间需至少 2 个出口）",
        "fix_civ004": "加宽疏散门至 ≥ 0.9m\n净宽",
        "fix_eee001": "安装应急照明灯具\n（该空间类型强制要求）",
        "fix_eee002": "移位配电箱：与水源\n保持最小安全距离",
        "fix_eee003": "拆分回路或增设独立\n馈电（负荷超过限值）",
        "fix_eee004": "增设墙面插座以满足\n覆盖要求",
        "fix_bld001": "加宽首层疏散外门至\n满足总净宽要求",
        "fix_bld002": "扩大消防水池容积至\n满足总用水量要求",
        "fix_bld003": "增容或增设变压器以\n满足全楼计算负荷",
        "fix_bld004": "增大应急蓄电池容量至\n规范要求的持续供电时间",
        "sys_prefix": "系统 | ",
        "sprinklered": "(设自动喷水灭火系统)",
        "conflict_title": "冲突区域：{loc}",
        "conflict_desc": "{floor} 的 {loc} 存在 {n_civ} 个建筑问题和 {n_eee} 个电气问题，需协同处置。请按严重程度优先处理。",
        "whole_building": "全楼",
        "rt_office": "办公室",
        "rt_corridor": "走廊",
        "rt_stairwell": "楼梯间",
        "rt_meeting": "会议室",
        "rt_equipment": "设备间",
        "rt_vestibule": "前室",
        "report_title": "审查报告",
        "report_sub": "多层建筑自动合规审查",
        "report_loc": "位置",
        "report_ref": "规范",
        "report_no_civ": "未发现建筑消防合规问题。",
        "report_no_eee": "未发现电气安全合规问题。",
        "report_no_bld": "未发现全楼累积问题。",
        "report_no_conf": "未发现跨专业冲突区域。",
        "report_footer": "ArchCheck · Aicher 系统 · AI 多层建筑合规审查 · 本报告仅供参考",
        "report_annotated": "标注楼层平面图",
        "report_civ_h": "建筑消防问题",
        "report_eee_h": "电气安全问题",
        "report_bld_h": "全楼累积问题（跨楼层）",
        "report_conf_h": "冲突区域（同层 · 跨专业）",
        "report_total": "问题总数",
        "back_upload_arch": "返回上传页",
        "diff_identical": "当前建筑在 {cur} 与 {oth} 标准下结果一致。",
        "diff_n_remove": "✅ {n} 个问题在 {oth} 下不再违规：",
        "diff_n_add": "⚠️ {n} 个新问题在 {oth} 下会出现：",
        "arch_agent_civ_d": "建筑规范审查",
        "arch_agent_eee_d": "电气安全审查",
        "arch_agent_bld_d": "跨楼层聚合",
        "arch_agent_coord_d": "冲突检测",
        "arch_agent_civ_c": "疏散距离\n防火分区面积\n安全出口数量\n疏散门宽度合规",
        "arch_agent_eee_c": "应急照明\n水源安全距离\n回路负荷验证\n插座覆盖",
        "arch_agent_bld_c": "首层疏散总净宽\n消防水池容积\n变压器装机容量\n应急电源持续时间",
        "arch_agent_coord_c": "同层跨领域问题\n冲突区域识别\n按优先级处置\n统一报告生成",
        "arch_agent_bld_tag": "全楼汇总量",
        "arch_agent_coord_tag": "规则引擎核心",
        "arch_p1": "1. 上传与配置",
        "arch_p1s": "楼层图纸 + 参数 + 标准",
        "arch_p2": "2. 多智能体审查",
        "arch_p2s": "建筑 + 电气（分层）+ 全楼聚合",
        "arch_p3": "3. 报告与修正",
        "arch_p3s": "分层标注图 + HTML 报告",
        "arch_std_cn_t": "中国标准 (GB)",
        "arch_std_cn_d": "GB 50016 建筑设计防火规范\nGB 51309 消防应急照明\nGB 50054 低压配电设计\nGB 50055 通用用电设备\nGB 50974 消防给水及消火栓",
        "arch_std_sg_t": "新加坡标准 (FC23)",
        "arch_std_sg_d": "Singapore Fire Code 2023\nSS 551 应急照明\nCP 5 布线规范\nSS 531 电气装置\nSS 575 消防水源",
        "arch_tech_py": "核心引擎",
        "arch_tech_st": "Web 界面",
        "arch_tech_pil": "图像处理",
        "arch_tech_json": "规则引擎（按标准）",
        "arch_tech_mf": "数据模型",
        "arch_p1_label": "阶段 1 · 已完成",
        "arch_p1_t": "核心多层引擎",
        "arch_p1_d": "JSON 驱动的按标准规则引擎、多智能体框架（建筑 + 电气 + 全楼 + 协调器）、分层图像标注、全楼聚合校核、HTML 报告导出",
        "arch_p2_label": "阶段 2 · 规划中",
        "arch_p2_t": "AI 智能分析",
        "arch_p2_d": "楼层平面图房间/区域 CV 识别、ML 严重程度预测、自然语言规则编写、更多标准（东盟/欧盟/美国）、竖向连续性校核",
        "arch_p3_label": "阶段 3 · 未来",
        "arch_p3_t": "企业级平台",
        "arch_p3_d": "BIM/IFC 文件支持、多用户协作、跨司法管辖区法规实时更新、云端部署、设计工具 API 集成",
        "sec_platform": "ARCHCHECK · 平台",
        "sec_analysis": "ARCHCHECK · 分析",
        "sec_results": "ARCHCHECK · 审查结果",
    },
    "en": {
        "platform_desc": "AI-powered multi-floor building code compliance review.<br>Multi-Agent: Civil + EEE + Building + Coordinator",
        "std_label": "CODE STANDARD",
        "std_cn": "🇨🇳  China GB",
        "std_sg": "🇸🇬  Singapore FC23",
        "active_std": "Active",
        "nav_upload": "Upload & Review",
        "nav_results": "Review Results",
        "nav_arch": "Platform Architecture",
        "version": "Aicher System · v3.0",
        "hero_1": "Upload floor plans,",
        "hero_2": "AI ",
        "hero_3": "multi-floor review",
        "hero_4": " for compliance.",
        "hero_sub": "Multi-agent platform for automated building code review — fire safety, electrical, and cross-floor aggregated checks. Switch between Chinese (GB) and Singapore (Fire Code 2023) standards.",
        "agent_civil": "Civil Agent · Fire Safety",
        "agent_eee": "EEE Agent · Electrical",
        "agent_bld": "Building Agent · Cross-Floor",
        "agent_coord": "Coordinator · Conflicts",
        "feat1_t": "Fire Safety Review",
        "feat2_t": "Electrical Safety Review",
        "feat3_t": "Cross-Floor Checks",
        "feat4_t": "Conflict Detection",
        "feat3_d": "Aggregate exit width · Fire water tank\nTransformer capacity · Emergency power\nEach floor OK ≠ building OK",
        "feat4_d": "Cross-discipline issue merging\nPer-floor conflict identification\nCoordinated resolution",
        "upload_t": "Upload Floor Plan",
        "upload_hint": "Supported: PNG, JPG, JPEG, PDF. Max 20MB.",
        "upload_drag": "Drag and drop your floor plan here",
        "demo_or": "— or —",
        "demo_btn": "Quick Demo (Load Sample Multi-Floor Building)",
        "data_t": "Building Data Parameters",
        "data_hint": "Edit building-level and per-floor parameters. Values drive the compliance check.",
        "bld_params_t": "Building-Level Parameters (Cross-Floor)",
        "bld_params_caption": "Aggregate parameters checked against whole-building thresholds.",
        "p_ground_exit": "Ground Floor Exit Width (m)",
        "p_fire_pool": "Fire Pool Volume (m³)",
        "p_transformer": "Transformer Capacity (kW)",
        "p_emergency": "Emergency Power Duration (min)",
        "p_floors": "Total Floors",
        "p_area": "Area (m²)",
        "p_exits": "Exits",
        "p_corridor": "Corridor (m)",
        "p_light": "Emerg. Light",
        "p_water": "Dist-Water (m)",
        "p_load": "Load (A)",
        "p_outlet": "Outlet Spacing (m)",
        "p_door": "Door Width (m)",
        "p_fz_area": "Area (m²)",
        "save_btn": "Save All Parameters",
        "save_ok": "Parameters saved successfully! Ready for review.",
        "start_btn": "Start Review",
        "need_upload": 'Upload a floor plan or click "Quick Demo" to get started',
        "reviewing_title": "Multi-Agent Review in Progress...",
        "std_label_running": "Standard",
        "floors_label": "Floors",
        "rooms_label": "Rooms",
        "zones_label": "Fire Zones",
        "status_init": "Initializing review engine...",
        "status_parsing": "Parsing building data across floors...",
        "status_loaded": "Building data loaded",
        "status_floor": "Agents reviewing",
        "status_bld": "Building-level aggregation: checking cross-floor totals...",
        "status_coord": "Coordinator: Merging results & detecting conflicts...",
        "status_done": "Review complete",
        "back_upload": "Back to Upload",
        "results_title": "Review Results Report",
        "results_sub": "Automated multi-floor building code compliance review — Civil + EEE + Building + Coordinator",
        "s_total": "Total Issues",
        "s_civil": "Civil",
        "s_eee": "EEE",
        "s_bld": "Building",
        "s_conf": "Conflicts",
        "s_high": "High Severity",
        "before_after_t": "Floor Plans — Before / After",
        "before_after_h": "Left: violations marked by agent color. Right: green callouts show suggested fixes per floor.",
        "floor_sel": "Select Floor",
        "before_l": "BEFORE — Violations",
        "after_l": "AFTER — Suggested Corrections",
        "before_cap": "Blue = Civil · Orange = EEE · Numbered markers correspond to issue list below",
        "after_cap": "Green markers with numbered fix instructions in right panel",
        "tab_civil": "Civil Issues",
        "tab_eee": "EEE Issues",
        "tab_bld": "Building-Level",
        "tab_conf": "Conflicts",
        "no_issue": "No issues found in this category.",
        "bld_blurb": "Building-level issues are aggregated across all floors. Each floor may be compliant individually, but whole-building totals can exceed code thresholds — a gap that per-floor review misses.",
        "loc": "LOC",
        "ref": "REF",
        "export_t": "Export Results",
        "dl_annotated": "Download Annotated (Current Floor)",
        "dl_correction": "Download Correction (Current Floor)",
        "dl_report": "Download HTML Report",
        "new_review": "New Review",
        "no_results": "No review results found. Please upload a floor plan and start a review first.",
        "arch_title": "Platform Architecture",
        "arch_sub": "Multi-agent collaborative architecture for multi-floor, multi-standard building code compliance review",
        "agents_t": "Multi-Agent System",
        "pipeline_t": "Review Pipeline",
        "p1": "1. Upload + Configure",
        "p1s": "Floor plans + parameters + standard",
        "p2": "2. Multi-Agent Review",
        "p2s": "Civil + EEE (per floor) + Building (aggregate)",
        "p3": "3. Report & Correction",
        "p3s": "Annotated plans per floor + HTML report",
        "std_t": "Standard Switching",
        "tech_t": "Technology Stack",
        "roadmap_t": "Development Roadmap",
        "bld_fix_t": "Building-Level Correction Suggestions",
        "bld_fix_h": "Whole-building issues cannot be marked on a single floor plan — their fixes are listed here.",
        "diff_title": "Standard Switching Impact",
        "diff_h": "With the current data, switching standard produces these changes:",
        "log_civil": "Checking {n} rooms + fire zones",
        "log_eee": "Checking electrical safety",
        "log_bld": "Aggregating {n} floors: exit width, fire water, transformer, emergency power",
        "log_coord": "Cross-referencing same-floor cross-discipline conflicts",
        "log_done": "Report: {total} total, {n_conflicts} cross-discipline conflicts, {n_bld} cross-floor issues",
        "status_done_detail": "{total} issues ({civ_n} civil, {eee_n} eee, {n_bld} building), {n_conflicts} conflicts",
        "issue_pass": "No issues found in this category.",
        "no_conflict": "No conflict zones detected between civil and electrical domains on any floor.",
        "fix_civ001": "Add refuge passage to shorten\ntravel distance to <= 30m",
        "fix_civ002": "Add fire separation wall to keep\ncompartment within area limit",
        "fix_civ003": "Add second exit door\n(rooms > 50m² need 2 exits)",
        "fix_civ004": "Widen door to >= 0.9m\nclear width",
        "fix_eee001": "Install emergency light fixture\n(required for this space type)",
        "fix_eee002": "Relocate panel: maintain min\nclearance from water source",
        "fix_eee003": "Split circuit or add separate\nfeeder (load exceeds rating)",
        "fix_eee004": "Add wall outlet for\nadequate coverage",
        "fix_bld001": "Widen ground floor exit\ndischarge to meet total width",
        "fix_bld002": "Increase fire water tank\ncapacity to meet total demand",
        "fix_bld003": "Upgrade or add transformer\nto meet total building load",
        "fix_bld004": "Increase emergency battery\ncapacity to required duration",
        "sys_prefix": "SYS | ",
        "sprinklered": "(sprinklered)",
        "conflict_title": "Conflict Zone: {loc}",
        "conflict_desc": "{loc} on {floor} has {n_civ} civil issue(s) and {n_eee} electrical issue(s). Coordinate resolution required. Prioritize by severity.",
        "whole_building": "WHOLE BUILDING",
        "rt_office": "Office",
        "rt_corridor": "Corridor",
        "rt_stairwell": "Stairwell",
        "rt_meeting": "Meeting Room",
        "rt_equipment": "Equipment Room",
        "rt_vestibule": "Vestibule",
        "report_title": "Review Report",
        "report_sub": "Automated Multi-Floor Building Plan Review",
        "report_loc": "LOC",
        "report_ref": "REF",
        "report_no_civ": "No civil code violations found.",
        "report_no_eee": "No electrical code violations found.",
        "report_no_bld": "No building-level violations found.",
        "report_no_conf": "No conflict zones detected.",
        "report_footer": "ArchCheck · Aicher System · AI-Powered Multi-Floor Building Code Review · This report is for reference only",
        "report_annotated": "Annotated Floor Plans",
        "report_civ_h": "Civil Code Violations",
        "report_eee_h": "EEE Code Violations",
        "report_bld_h": "Building-Level Violations (Cross-Floor)",
        "report_conf_h": "Conflict Zones (Same Floor · Cross-Discipline)",
        "report_total": "Total Issues",
        "back_upload_arch": "Back to Upload",
        "diff_identical": "Results identical under {cur} and {oth} for this building.",
        "diff_n_remove": "✅ {n} issue(s) would no longer violate under {oth}:",
        "diff_n_add": "⚠️ {n} new issue(s) would appear under {oth}:",
        "arch_agent_civ_d": "Building Code Review",
        "arch_agent_eee_d": "Electrical Safety Review",
        "arch_agent_bld_d": "Cross-Floor Aggregation",
        "arch_agent_coord_d": "Conflict Detection",
        "arch_agent_civ_c": "Evacuation distance\nFire compartment area\nEmergency exit count\nDoor width compliance",
        "arch_agent_eee_c": "Emergency lighting\nWater clearance distance\nCircuit load verification\nOutlet coverage",
        "arch_agent_bld_c": "Aggregate exit width\nFire water tank volume\nTransformer capacity\nEmergency power duration",
        "arch_agent_coord_c": "Same-floor cross-domain\nConflict zone identification\nPriority-based resolution\nUnified report generation",
        "arch_agent_bld_tag": "Whole-Building Totals",
        "arch_agent_coord_tag": "Rule Engine Core",
        "arch_p1": "1. Upload + Configure",
        "arch_p1s": "Floor plans + parameters + standard",
        "arch_p2": "2. Multi-Agent Review",
        "arch_p2s": "Civil + EEE (per floor) + Building (aggregate)",
        "arch_p3": "3. Report & Correction",
        "arch_p3s": "Annotated plans per floor + HTML report",
        "arch_std_cn_t": "Chinese Standards (GB)",
        "arch_std_cn_d": "GB 50016 建筑设计防火规范\nGB 51309 消防应急照明\nGB 50054 低压配电设计\nGB 50055 通用用电设备\nGB 50974 消防给水及消火栓",
        "arch_std_sg_t": "Singapore Standards (FC23)",
        "arch_std_sg_d": "Singapore Fire Code 2023\nSS 551 Emergency Lighting\nCP 5 Code of Practice for Wiring\nSS 531 Electrical Installations\nSS 575 Fire Water Storage",
        "arch_tech_py": "Core Engine",
        "arch_tech_st": "Web Interface",
        "arch_tech_pil": "Image Processing",
        "arch_tech_json": "Rule Engine (per standard)",
        "arch_tech_mf": "Data Model",
        "arch_p1_label": "PHASE 1 · COMPLETE",
        "arch_p1_t": "Core Multi-Floor Engine",
        "arch_p1_d": "JSON-driven rules engine per standard, multi-agent framework (Civil + EEE + Building + Coordinator), per-floor image annotation, building-level aggregate checks, HTML report export",
        "arch_p2_label": "PHASE 2 · PLANNED",
        "arch_p2_t": "AI-Powered Analysis",
        "arch_p2_d": "Computer vision for room/zone detection from floor plans, ML-based severity prediction, natural language rule authoring, additional standards (ASEAN/EU/US), vertical continuity checks",
        "arch_p3_label": "PHASE 3 · FUTURE",
        "arch_p3_t": "Enterprise Platform",
        "arch_p3_d": "BIM/IFC file support, multi-user collaboration, real-time regulatory updates across jurisdictions, cloud deployment, API integration for design tools",
        "sec_platform": "ARCHCHECK · PLATFORM",
        "sec_analysis": "ARCHCHECK · ANALYSIS",
        "sec_results": "ARCHCHECK · REVIEW RESULTS",
    },
}
T = _I18N[LANG]

def _room_type_label(rtype):
    mapping = {
        "Office": T["rt_office"], "Corridor": T["rt_corridor"],
        "Stairwell": T["rt_stairwell"], "Meeting Room": T["rt_meeting"],
        "Equipment Room": T["rt_equipment"], "Vestibule": T["rt_vestibule"],
    }
    return mapping.get(rtype, rtype)

# ============================================================
# DEMO BUILDING DATA (multi-floor)
# ============================================================
def load_demo_data():
    p = DATA / "demo_building_data.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"project_name": "Demo", "building_params": {}, "floors": []}

DEMO_DATA = load_demo_data()

# ============================================================
# RULES ENGINE
# ============================================================
OPERATORS = {
    "<=": lambda a,b: a<=b, ">=": lambda a,b: a>=b, ">": lambda a,b: a>b,
    "<": lambda a,b: a<b, "==": lambda a,b: a==b, "!=": lambda a,b: a!=b,
    "in": lambda a,b: a in b, "not_in": lambda a,b: a not in b,
}

def run_rules(rules, item, prefix, floor_id=None, floor_name=None):
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
            "floor_id": floor_id,
            "floor_name": floor_name,
        })
    return violations

# ============================================================
# SHARED FLOOR PLAN DRAWING
# ============================================================
FP_X1, FP_Y1 = 30, 80
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

# ============================================================
# IMAGE ANNOTATION
# ============================================================
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

# ============================================================
# CORRECTION IMAGE
# ============================================================
def _fix_map():
    return {
        "CIVIL-001": T["fix_civ001"], "CIVIL-002": T["fix_civ002"],
        "CIVIL-003": T["fix_civ003"], "CIVIL-004": T["fix_civ004"],
        "EEE-001": T["fix_eee001"], "EEE-002": T["fix_eee002"],
        "EEE-003": T["fix_eee003"], "EEE-004": T["fix_eee004"],
        "BLD-001": T["fix_bld001"], "BLD-002": T["fix_bld002"],
        "BLD-003": T["fix_bld003"], "BLD-004": T["fix_bld004"],
    }

def generate_correction_image(image, civ, eee, conflicts, bdata=None, floor_name="", variant=0):
    W, H = 1800, 1200
    img = Image.new("RGB", (W, H), (250, 251, 252))
    draw = ImageDraw.Draw(img)
    ft, fm, fs = _load_fonts((34, 24, 20))
    correction_title = "修正方案" if LANG == "zh" else "CORRECTION PLAN"
    title = f"{correction_title}  —  {floor_name}" if floor_name else f"{correction_title}"
    draw.rectangle([0, 0, W, 70], fill=(100, 160, 50))
    draw.text((40, 12), title, fill=(255, 255, 255), font=ft)
    _draw_floor_plan(draw, W, H, variant=variant)
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

# ============================================================
# BUILDING CROSS-SECTION DIAGRAM (visual floor connection)
# ============================================================
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
        fname = f.get("floor_name", fid)
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

# ============================================================
# REPORT GENERATOR
# ============================================================
def generate_report(images_by_floor, all_issues, civil_r, eee_r, building_r, conflicts, std_meta):
    t = _I18N[LANG]
    sev_map = {"High": ("高", "high") if LANG == "zh" else ("High", "high"),
               "Medium": ("中", "mid") if LANG == "zh" else ("Medium", "mid"),
               "Low": ("低", "low") if LANG == "zh" else ("Low", "low")}
    priority_label = "优先处理" if LANG == "zh" else "PRIORITY"
    html_lang = "zh" if LANG == "zh" else "en"

    floors_html = ""
    for fname, img in images_by_floor.items():
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img64 = base64.b64encode(buf.getvalue()).decode()
        floors_html += f'<h3>{fname}</h3><div class="img-box"><img src="data:image/png;base64,{img64}" alt="{fname}"></div>'

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    std_label = f'{std_meta.get("flag","")} {std_meta.get("name","")}'
    report_header = "ARCHCHECK · 审查报告" if LANG == "zh" else "ARCHCHECK · REPORT"

    def rows(items, cls):
        out = ""
        for i, iss in enumerate(items, 1):
            sv = iss.get("severity", "Medium")
            sv_label, sc = sev_map.get(sv, ("?", "mid"))
            floor_info = ""
            if iss.get("floor_name"):
                floor_info = f' · <span style="color:{C["silver"]};font-size:12px;">{iss["floor_name"]}</span>'
            out += (
                f'<div class="card {cls}">'
                f'<div class="title">{i}. {iss["title"]}'
                f'<span class="sev sev-{sc}">{sv_label}</span>{floor_info}</div>'
                f'<div class="desc">{iss.get("description","")}</div>'
                f'<div class="meta">{t["report_loc"]}: {iss.get("location","-")} | {t["report_ref"]}: {iss.get("code_ref","-")}</div>'
                f'</div>'
            )
        return out

    def crow(conflicts):
        out = ""
        for i, c in enumerate(conflicts, 1):
            out += (
                f'<div class="card cnf">'
                f'<div class="title">{i}. {c["title"]}'
                f'<span class="sev sev-high">{priority_label}</span></div>'
                f'<div class="desc">{c.get("description","")}</div>'
                f'<div class="meta">{t["report_loc"]}: {c.get("location","-")} | {c.get("related_issues","")}</div>'
                f'</div>'
            )
        return out

    no_civ = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_civ"]}</span></div>'
    no_eee = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_eee"]}</span></div>'
    no_bld = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_bld"]}</span></div>'
    no_cnf = f'<div class="card" style="border-left:4px solid #7CB342;background:#EEF5E2;"><span class="title" style="color:#7CB342;">{t["report_no_conf"]}</span></div>'

    label_css = "" if LANG == "en" else "text-transform:none;letter-spacing:.12em;"

    return f"""<!DOCTYPE html><html lang="{html_lang}"><head><meta charset="UTF-8"><title>ArchCheck {t["report_title"]}</title><style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;max-width:960px;margin:0 auto;padding:40px 32px;color:{C["text"]};background:{C["bg"]};background-image:linear-gradient({C["border"]} 1px,transparent 1px),linear-gradient(90deg,{C["border"]} 1px,transparent 1px);background-size:32px 32px;}}
.band{{display:flex;height:6px;border-radius:3px;margin-bottom:32px;overflow:hidden;}}
.band-c{{flex:2;background:{C["blue"]};}}.band-e{{flex:1;background:{C["orange"]};}}.band-b{{flex:1;background:{C["purple"]};}}.band-r{{flex:1;background:{C["red"]};}}.band-p{{flex:.6;background:{C["green"]};}}
.label{{font-size:12px;letter-spacing:.34em;color:{C["silver"]};font-weight:600;text-transform:uppercase;margin-bottom:8px;{label_css}}}
.std-badge{{display:inline-block;padding:4px 12px;border-radius:2px;background:{C["purple"]}18;color:{C["purple"]};font-weight:600;font-size:13px;margin-bottom:12px;}}
h1{{font-size:52px;font-weight:800;line-height:1.15;margin-bottom:4px;}}h1 span{{color:{C["blue"]};}}
.subtitle{{font-size:17px;color:{C["muted"]};font-weight:300;margin-bottom:32px;}}
.stats{{display:flex;gap:12px;margin-bottom:32px;flex-wrap:wrap;}}
.stat{{flex:1;min-width:120px;background:#FFF;border:1px solid {C["border"]};border-radius:4px;padding:16px;text-align:center;}}
.stat .val{{font-size:36px;font-weight:800;}}.stat .lbl{{font-size:11px;color:{C["silver"]};letter-spacing:.08em;text-transform:uppercase;margin-top:4px;}}
.stat.c .val{{color:{C["blue"]};}}.stat.e .val{{color:{C["orange"]};}}.stat.b .val{{color:{C["purple"]};}}.stat.r .val{{color:{C["red"]};}}
h2{{font-size:24px;font-weight:700;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid {C["text"]};}}
h3{{font-size:18px;font-weight:600;margin:20px 0 8px;color:{C["muted"]};}}
.img-box{{text-align:center;margin:16px 0;}}.img-box img{{max-width:100%;border-radius:4px;border:1px solid {C["border"]};}}
.card{{background:#FFF;border:1px solid {C["border"]};border-radius:2px;padding:14px 18px;margin-bottom:8px;}}
.card.civ{{border-left:4px solid {C["blue"]};}}.card.eee{{border-left:4px solid {C["orange"]};}}
.card.bld{{border-left:4px solid {C["purple"]};background:#F8F5FC;}}.card.cnf{{border-left:4px solid {C["red"]};background:#FEF2F2;}}
.card .title{{font-weight:700;font-size:15px;}}.card.civ .title{{color:{C["blue"]};}}.card.eee .title{{color:{C["orange"]};}}
.card.bld .title{{color:{C["purple"]};}}.card.cnf .title{{color:{C["red"]};}}
.card .desc{{font-size:14px;color:{C["muted"]};margin-top:4px;}}.card .meta{{font-size:13px;color:{C["silver"]};margin-top:4px;font-family:monospace;}}
.sev{{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:2px;font-size:12px;font-weight:600;}}
.sev-high{{background:#FEF2F2;color:{C["red"]};}}.sev-mid{{background:#FFF7ED;color:{C["orange"]};}}.sev-low{{background:#F9FAFB;color:{C["silver"]};}}
.footer{{text-align:center;font-size:13px;color:{C["silver"]};margin-top:40px;border-top:1px solid {C["border"]};padding-top:16px;}}
</style></head><body>
<div class="label">{report_header}</div>
<div class="band"><div class="band-c"></div><div class="band-e"></div><div class="band-b"></div><div class="band-r"></div><div class="band-p"></div></div>
<div class="std-badge">{std_label}</div>
<h1>{t["report_title"]}</h1><div class="subtitle">{t["report_sub"]} · {now}</div>
<div class="stats">
<div class="stat"><div class="val">{len(civil_r)+len(eee_r)+len(building_r)}</div><div class="lbl">{t["report_total"]}</div></div>
<div class="stat c"><div class="val">{len(civil_r)}</div><div class="lbl">{t["s_civil"]}</div></div>
<div class="stat e"><div class="val">{len(eee_r)}</div><div class="lbl">{t["s_eee"]}</div></div>
<div class="stat b"><div class="val">{len(building_r)}</div><div class="lbl">{t["s_bld"]}</div></div>
<div class="stat r"><div class="val">{len(conflicts)}</div><div class="lbl">{t["s_conf"]}</div></div>
</div>
<h2>{t["report_annotated"]}</h2>
{floors_html}
<h2>{t["report_civ_h"]}</h2>
{rows(civil_r,'civ') if civil_r else no_civ}
<h2>{t["report_eee_h"]}</h2>
{rows(eee_r,'eee') if eee_r else no_eee}
<h2>{t["report_bld_h"]}</h2>
{rows(building_r,'bld') if building_r else no_bld}
<h2>{t["report_conf_h"]}</h2>
{crow(conflicts) if conflicts else no_cnf}
<div class="footer">{t["report_footer"]}</div>
</body></html>"""

# ============================================================
# REVIEW ENGINE (multi-floor)
# ============================================================
def run_full_review(bdata):
    civil_results = []
    eee_results = []
    building_results = []

    for floor in bdata.get("floors", []):
        fid = floor.get("floor_id", "")
        fname = floor.get("floor_name", fid)
        for room in floor.get("rooms", []):
            civil_results.extend(run_rules(CIVIL_RULES, room, "civil", fid, fname))
            eee_results.extend(run_rules(EEE_RULES, room, "eee", fid, fname))
        for zone in floor.get("fire_zones", []):
            civil_results.extend(run_rules(CIVIL_RULES, zone, "civil", fid, fname))

    bp = bdata.get("building_params", {})
    whole_label = _I18N[LANG]["whole_building"]
    building_results.extend(run_rules(BUILDING_RULES, bp, "building", None, whole_label))

    all_issues = civil_results + eee_results + building_results

    # Conflict detection: same floor AND same location has both civil + eee
    loc_map = defaultdict(list)
    for iss in civil_results + eee_results:
        key = f"{iss.get('floor_id','')}::{iss.get('location','?')}"
        loc_map[key].append(iss)

    conflicts = []
    for key, issues in loc_map.items():
        types = set(i["type"] for i in issues)
        if len(types) >= 2:
            ct = [i["title"] for i in issues if i["type"] == "civil"]
            et = [i["title"] for i in issues if i["type"] == "eee"]
            floor_name = issues[0].get("floor_name", "")
            loc_name = issues[0].get("location", "?")
            t = _I18N[LANG]
            conflicts.append({
                "title": t["conflict_title"].format(loc=loc_name),
                "description": t["conflict_desc"].format(floor=floor_name, loc=loc_name, n_civ=len(ct), n_eee=len(et)),
                "location": loc_name,
                "related_issues": f"{T['s_civil']}: {', '.join(ct)} | {T['s_eee']}: {', '.join(et)}",
                "type": "conflict",
                "severity": "High",
                "floor_id": issues[0].get("floor_id"),
                "floor_name": floor_name,
            })

    return {
        "civil_results": civil_results,
        "eee_results": eee_results,
        "building_results": building_results,
        "conflicts": conflicts,
        "all_issues": all_issues,
    }

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
                fname = floor.get("floor_name", floor.get("floor_id", ""))
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
    st.session_state.review_loading = False
    st.session_state.page = "results"
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

        st.markdown(
            f'<div style="font-size:13px;color:{C["silver"]};margin:12px 0;text-align:center;">'
            f'{T["demo_or"]}</div>',
            unsafe_allow_html=True,
        )
        if st.button(T["demo_btn"], width="stretch"):
            demo_path = OUTPUT / "demo_architect_plan.png"
            first_fname = DEMO_DATA["floors"][0].get("floor_name", "1F")
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
        floor_tabs = st.tabs([f.get("floor_name", f.get("floor_id", f"F{i}")) for i, f in enumerate(floors)])
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
    other_std = load_standard(other_std_id)
    _saved = (CIVIL_RULES, EEE_RULES, BUILDING_RULES)
    CIVIL_RULES, EEE_RULES, BUILDING_RULES = other_std["civil"], other_std["eee"], other_std["building"]
    other_results = run_full_review(bdata)
    CIVIL_RULES, EEE_RULES, BUILDING_RULES = _saved

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
            st.session_state.page = "upload"
            st.rerun()
        st.stop()

    # Generate per-floor annotated and correction images
    floors = bdata.get("floors", [])
    annotated_by_floor = {}
    correction_by_floor = {}
    for fi, floor in enumerate(floors):
        fid = floor.get("floor_id", "")
        fname = floor.get("floor_name", fid)
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
                floor_tag = f'<span class="floor-tag">{iss["floor_name"]}</span>'
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
            st.session_state.page = "upload"
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
        st.session_state.page = "upload"
        st.rerun()
