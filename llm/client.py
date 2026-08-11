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
def _compact_issues(issues):
    lines = []
    for i, iss in enumerate(issues, 1):
        floor = iss.get("floor_name", "-")
        sev = iss.get("severity", "-")
        lines.append(
            f'{i}. [{floor}] {iss.get("location", "-")} | {iss.get("title", "-")} '
            f'| 严重度:{sev} | 规范:{iss.get("code_ref", "-")} | {iss.get("description", "")}'
        )
    return "\n".join(lines) if lines else "（无）"


def generate_review_narrative(civil, eee, building, conflicts, std_meta, lang="zh"):
    """Turn structured review findings into a professional review report."""
    std_label = f'{std_meta.get("flag", "")} {std_meta.get("name", "")}'
    if lang == "zh":
        system = "你是资深的建筑与电气规范审查总工。你根据自动审查结果撰写专业、客观、可执行的审查意见报告，语气严谨，突出重点与整改优先级。"
        user = (
            f"请根据以下建筑合规自动审查结果，撰写一份专业审查意见报告。审查标准：{std_label}。\n\n"
            f"【建筑消防问题】\n{_compact_issues(civil)}\n\n"
            f"【电气安全问题】\n{_compact_issues(eee)}\n\n"
            f"【全楼累积问题（跨楼层）】\n{_compact_issues(building)}\n\n"
            f"【跨专业冲突】\n{_compact_issues(conflicts)}\n\n"
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
            f"[Civil / Fire safety]\n{_compact_issues(civil)}\n\n"
            f"[Electrical]\n{_compact_issues(eee)}\n\n"
            f"[Building-level aggregates]\n{_compact_issues(building)}\n\n"
            f"[Cross-discipline conflicts]\n{_compact_issues(conflicts)}\n\n"
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
    body = _compact_issues(conflicts)
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
    system = (
        "你是建筑规范工程师，负责把规范条文转换成规则引擎的 JSON 规则。"
        "规则字段：id, name, description, field, operator, threshold, unit, "
        "severity(High/Medium/Low), code_ref, message。"
        "operator 只能是 <= >= > < == != in not_in 之一。message 里可用 {value} {threshold} {room_name} 占位符。"
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
