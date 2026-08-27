"""DeepSeek (via local Anthropic-compatible proxy) client.

Division of labour: the LLM does *reasoning / generation* only — review
narratives, conflict coordination, rule authoring. Numeric compliance judgment
stays in core/engine.py's deterministic rule engine.

Transport: plain `requests` to the local proxy's /v1/messages endpoint. The
anthropic SDK (httpx transport) returns 502 against this proxy in this
environment, so we avoid it. Endpoint defaults to the local proxy; override with
env vars:
    LLM_BASE_URL   (default http://127.0.0.1:15721)
    LLM_API_KEY    (default PROXY_MANAGED)
    LLM_MODEL      (default deepseek-v4-flash)
    LLM_MAX_TOKENS (default 1200)
"""
import json
import os

import requests

BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:15721")
API_KEY = os.environ.get("LLM_API_KEY", "PROXY_MANAGED")
MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1600"))


def available():
    """Whether the HTTP transport is importable."""
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def chat(system, user, model=None, max_tokens=None, retries=3):
    """Single chat completion. Returns the assistant text (thinking skipped).

    Reasoning models may spend the whole token budget on thinking and return no
    text — so on an empty response (or a transient 502) we retry with a larger
    budget.
    """
    body = {"model": model or MODEL, "max_tokens": max_tokens or MAX_TOKENS,
            "messages": [{"role": "user", "content": user}]}
    if system:
        body["system"] = system
    headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01"}
    budget = body["max_tokens"]
    for attempt in range(retries):
        try:
            resp = requests.post(f"{BASE_URL}/v1/messages", json=body,
                                 headers=headers, timeout=120)
            if resp.status_code != 200:
                if resp.status_code == 502 and attempt < retries - 1:
                    budget = min(budget * 2, 6000)
                    body["max_tokens"] = budget
                    continue
                return ""
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text").strip()
            if text:
                return text
            budget = min(budget * 2, 6000)  # thinking ate the budget
            body["max_tokens"] = budget
        except Exception:
            if attempt == retries - 1:
                return ""
    return ""


# --------------------------------------------------------------------------
# Feature 1: review narrative
# --------------------------------------------------------------------------
def _compact_issues(issues, lang="zh"):
    sev_lbl, code_lbl, empty = ("严重度", "规范", "（无）") if lang == "zh" \
        else ("severity", "code", "(none)")
    lines = []
    for i, iss in enumerate(issues, 1):
        floor = iss.get("floor_name", "-")
        sev = iss.get("severity", "-")
        lines.append(
            f'{i}. [{floor}] {iss.get("location", "-")} | {iss.get("title", "-")} '
            f'| {sev_lbl}:{sev} | {code_lbl}:{iss.get("code_ref", "-")} | {iss.get("description", "")}'
        )
    return "\n".join(lines) if lines else empty


def generate_review_narrative(civil, eee, building, conflicts, std_meta, lang="zh"):
    """Turn structured review findings into a professional review report."""
    std_label = f'{std_meta.get("flag", "")} {std_meta.get("name", "")}'
    if lang == "zh":
        system = "你是资深的建筑与电气规范审查总工。你根据自动审查结果撰写专业、客观、可执行的审查意见报告，语气严谨，突出重点与整改优先级。"
        user = (
            f"请根据以下建筑合规自动审查结果，撰写一份专业审查意见报告。审查标准：{std_label}。\n\n"
            f"【建筑消防问题】\n{_compact_issues(civil, lang)}\n\n"
            f"【电气安全问题】\n{_compact_issues(eee, lang)}\n\n"
            f"【全楼累积问题（跨楼层）】\n{_compact_issues(building, lang)}\n\n"
            f"【跨专业冲突】\n{_compact_issues(conflicts, lang)}\n\n"
            "请按以下结构输出（不要复述全部条目，抓重点）：\n"
            "1. 总体评价：一句话概括整楼合规状况\n"
            "2. 重点问题：挑 2-3 个最严重/最典型的问题，说明其影响\n"
            "3. 整改优先级：按紧急程度给出处置顺序建议"
        )
    else:
        system = ("You are a senior building & electrical code review engineer. "
                  "Write a professional, objective, actionable review report.")
        user = (
            f"Write a professional compliance review report based on these automated findings. "
            f"Standard: {std_label}.\n\n"
            f"[Civil / Fire safety]\n{_compact_issues(civil, lang)}\n\n"
            f"[Electrical]\n{_compact_issues(eee, lang)}\n\n"
            f"[Building-level aggregates]\n{_compact_issues(building, lang)}\n\n"
            f"[Cross-discipline conflicts]\n{_compact_issues(conflicts, lang)}\n\n"
            "Structure: 1) Overall assessment in one sentence. 2) Top 2-3 critical issues "
            "and their impact. 3) Remediation priority order."
        )
    return chat(system, user)


# --------------------------------------------------------------------------
# Feature 2: conflict coordination
# --------------------------------------------------------------------------
def coordinate_conflicts(conflicts, std_meta, lang="zh"):
    """Explain conflict zones and propose a coordinated resolution order."""
    if not conflicts:
        return ""
    std_label = f'{std_meta.get("flag", "")} {std_meta.get("name", "")}'
    body = _compact_issues(conflicts, lang)
    if lang == "zh":
        system = ("你是建筑审查协调专家，负责协调不同专业（建筑/电气）在同一位置的冲突整改。")
        user = (
            f"以下是审查发现的跨专业冲突区域（同一楼层同一位置同时存在建筑问题和电气问题），"
            f"审查标准：{std_label}。\n\n{body}\n\n"
            "请对每个冲突区域给出：① 冲突成因分析（为什么两个专业会同时出问题）② 建议的协同处置顺序（先改什么、后改什么，理由）。"
        )
    else:
        system = "You are a building review coordinator resolving cross-discipline conflicts."
        user = (
            f"These are cross-discipline conflict zones (same floor/location flagged by both "
            f"civil and electrical). Standard: {std_label}.\n\n{body}\n\n"
            "For each conflict: 1) root-cause analysis of why both disciplines fail together; "
            "2) recommended remediation order (what first, what second, and why)."
        )
    return chat(system, user)


# --------------------------------------------------------------------------
# Feature 3: rule authoring from code text (bonus)
# --------------------------------------------------------------------------
def generate_rules_from_code(code_text, std_id="cn", category="civil"):
    """Turn a code clause into JSON rules for the rule engine.

    Returns a list of rule dicts matching the schema in data/standards/.
    """
    # real fields the rule engine can judge, so the LLM maps to them instead of
    # inventing a Chinese field name that never matches any item. Each category
    # lists the fields bim/extractor.py actually produces for that item type;
    # condition_field/condition_threshold must come from the same list (usually
    # the *_type discriminator, e.g. room "type" or pipe "pipe_type").
    fields = {
        "room": "type room_area_sqm exit_count door_width_m corridor_length_m "
                "has_emergency_light dist_to_water_m circuit_load_a outlet_spacing_m",
        "civil": "type room_area_sqm exit_count door_width_m corridor_length_m "
                 "has_emergency_light dist_to_water_m circuit_load_a outlet_spacing_m",
        "eee": "equipment_type room_type has_emergency power_w "
               "outlet_spacing_m circuit_load_a dist_to_water_m",
        "mep": "pipe_type duct_width_m duct_height_m net_height_m "
               "diameter_m slope min_clearance_m length_m",
        "structural": "element_type section_min_m section_max_m depth_m "
                      "width_m span_m thickness_m volume_m3",
        "building": "total_floors occupancy_type ground_floor_exit_width_m "
                    "fire_pool_volume_m3 transformer_capacity_kw "
                    "emergency_power_duration_min max_ramp_slope",
    }.get(category, "type room_area_sqm exit_count door_width_m corridor_length_m")
    system = (
        "你是建筑规范工程师，负责把规范条文转换成规则引擎的 JSON 规则。"
        f"规则字段：id, name, description, field, operator, threshold, unit, severity(High/Medium/Low), code_ref, message。"
        "可选条件字段（仅当条文限定在某类构件/房间时用）：condition_field, condition_operator, condition_threshold，三者成组出现。"
        f"field 必须从以下真实字段中选择（不要造新字段名）：{fields}。"
        "operator 只能是 <= >= > < == != in not_in 之一。condition_field 也用上述真实字段。"
        "message 里可用 {value} {threshold} {room_name} {condition_value} {condition_threshold} 占位符。"
        "code_ref 只写标准名（如 GB 55037 / Fire Code 2023 / GB 50016），不要写条款号——除非你确知原文。"
        "只输出 JSON 数组，不要额外文字。"
    )
    user = (
        f"请把以下规范条文转换成 {std_id} 标准、{category} 类别的 JSON 规则数组：\n\n{code_text}"
    )
    out = chat(system, user, max_tokens=max(MAX_TOKENS, 1500))
    try:
        start = out.find("[")
        end = out.rfind("]")
        return json.loads(out[start:end + 1])
    except Exception:
        return []
