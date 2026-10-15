"""Arbitration Agent — resolve code-review grey areas that deterministic rules
cannot decide alone.

The deterministic rule engine handles the clear-cut findings. A minority of
rules carry an ``arbitration`` block in their JSON definition because the
correct threshold / applicability depends on interpretation: what type of
room is this, is this a "public building", which fire-compartment limit
applies. For those, the Judge defers to this agent instead of guessing.

Design contract:
  * The agent NEVER decides alone — every result is an "AI suggestion"
    (status ``pending``) that a human confirms.
  * Every suggestion must cite retrieved regulation text as evidence.
  * If the LLM or the RAG corpus is unavailable, the agent returns a
    graceful fallback so the review flow never breaks or blocks.
"""

import json
from pathlib import Path

from core import i18n

REPO = Path(__file__).resolve().parent.parent
KB = REPO / "data" / "rag_kb"

# ---------------------------------------------------------------------------
# RAG evidence retrieval (reuses the free-corpus semantic index)
# ---------------------------------------------------------------------------

_kb_txt_cache = None


def _kb_txts():
    """(filename, text) for every searchable KB document — mirrors reviewer.py."""
    global _kb_txt_cache
    if _kb_txt_cache is not None:
        return _kb_txt_cache
    _kb_txt_cache = []
    for p in sorted(KB.rglob("*.txt")):
        try:
            _kb_txt_cache.append((p.name, p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    return _kb_txt_cache


def _keyword_evidence(query, top_k):
    """Keyword fallback when the semantic index is unavailable: score each KB
    document by how many query tokens it contains, return the best snippets."""
    tokens = [t for t in (query or "").replace("，", " ").replace(",", " ").split() if len(t) >= 2]
    if not tokens:
        return []
    scored = []
    for fname, text in _kb_txts():
        hits = sum(text.count(t) for t in tokens)
        if hits > 0:
            # locate the densest region around the first token
            first = next((text.find(t) for t in tokens if text.find(t) != -1), 0)
            snippet = text[max(0, first - 120): first + 260].replace("\n", " ").strip()
            scored.append((hits, fname, snippet))
    scored.sort(reverse=True)
    return [{"doc": fname, "text": snip, "score": float(h)} for h, fname, snip in scored[:top_k]]


def _retrieve_evidence(query, top_k=3):
    """Return [{doc, text, score}] for a query.

    Tries the semantic index first (best quality); falls back to keyword
    matching over the free corpus so evidence still appears when the embedding
    model / index is unavailable. Returns [] if neither yields anything.
    """
    if not query:
        return []
    try:
        from kb.semantic import search as _sem_search
        results = _sem_search(query, top_k=top_k)
        if results:
            out = []
            for chunk, score in results:
                out.append({
                    "doc": chunk.get("doc", "?"),
                    "text": (chunk.get("text", "") or "")[:300].replace("\n", " ").strip(),
                    "score": round(float(score), 3),
                })
            return out
    except Exception:
        pass
    return _keyword_evidence(query, top_k)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_ZH = (
    "你是一名资深建筑规范审查专家，负责仲裁规则引擎无法自动判定的边界问题。\n"
    "你的判定必须有依据——优先引用提供的规范条文原文。\n"
    "如果证据不足以支撑明确结论，必须如实说明，不要编造条文。\n"
    "只输出 JSON，不要输出其他内容。"
)
_SYSTEM_EN = (
    "You are a senior building-code review expert arbitrating boundary cases "
    "that a deterministic rule engine cannot decide alone.\n"
    "Every judgement must be grounded in the provided regulation text.\n"
    "If the evidence is insufficient, say so honestly — never invent clauses.\n"
    "Output JSON only, nothing else."
)


def _build_prompt(rule, arbitration, context):
    """Build the (system, user) prompt pair for one arbitration case."""
    lang = context.get("lang", "zh")
    system = _SYSTEM_ZH if lang == "zh" else _SYSTEM_EN

    # --- project summary ---
    b = context.get("building", {})
    proj = (f"建筑类型: {b.get('type', '未标注')}\n"
            f"层数: {b.get('num_floors', '?')}\n"
            f"总建筑面积: {b.get('total_area_m2', '?')} m²\n"
            f"标准: {context.get('std_name', '?')}")

    # --- the element this finding is about ---
    el = context.get("element", {})
    el_lines = "\n".join(f"  - {k}: {v}" for k, v in el.items()) or "  （无具体构件信息）"

    # --- retrieved regulation evidence ---
    ev = context.get("evidence", [])
    ev_lines = "\n\n".join(
        f"[{i+1}] 《{e['doc']}》(相关度 {e['score']})\n{e['text']}"
        for i, e in enumerate(ev)
    ) or "（未检索到相关条文，请如实说明证据不足）"

    # --- candidate answers ---
    cands = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(arbitration.get("candidates", [])))

    if lang == "zh":
        user = f"""【项目概况】
{proj}

【待仲裁规则】
规则编号: {rule.get('id')}
规则名称: {rule.get('name')}
当前默认取值: {rule.get('threshold')} {rule.get('unit', '')}
仲裁点类型: {arbitration.get('point')}
仲裁说明: {arbitration.get('description')}

【本题涉及构件/空间】
{el_lines}

【规范条文证据】
{ev_lines}

【候选答案】
{cands or '（无预设候选，请自行分析）'}

请输出 JSON，格式：
{{
  "verdict": "你的判定结论（一句话）",
  "recommended_value": "建议采用的阈值或适用性取值",
  "confidence": "high / medium / low",
  "reasoning": "判定理由（2-3 句，说明为什么这样判）",
  "cited_clauses": ["引用的规范条文要点，如无可留空数组"],
  "needs_human": true/false   // 是否强烈建议人工复核
}}"""
    else:
        user = f"""【Project】
{proj}

【Rule under arbitration】
ID: {rule.get('id')}
Name: {rule.get('name')}
Current default: {rule.get('threshold')} {rule.get('unit', '')}
Arbitration point: {arbitration.get('point')}
Explanation: {arbitration.get('description')}

【Element / space in question】
{el_lines}

【Retrieved regulation evidence】
{ev_lines}

【Candidate answers】
{cands or '(none preset — analyse from scratch)'}

Output JSON:
{{
  "verdict": "one-sentence conclusion",
  "recommended_value": "the threshold / applicability you recommend",
  "confidence": "high / medium / low",
  "reasoning": "2-3 sentences justifying the decision",
  "cited_clauses": ["key clauses cited, [] if none"],
  "needs_human": true/false
}}"""
    return system, user


# ---------------------------------------------------------------------------
# LLM call + parse
# ---------------------------------------------------------------------------

def _parse_json_response(text):
    """Extract a JSON object from an LLM reply (tolerates code fences)."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1] if len(t.split("```")) > 1 else t
        if t.startswith("json"):
            t = t[4:]
    t = t.strip()
    # take the outermost {...}
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(t[start:end + 1])
    except Exception:
        return None


def _fallback(arbitration, reason):
    """Graceful degradation when the LLM is unavailable."""
    return {
        "verdict": "AI 仲裁不可用，保留默认判定",
        "recommended_value": None,
        "confidence": "low",
        "reasoning": reason,
        "cited_clauses": [],
        "needs_human": True,
        "status": "pending",
        "ai_arbitrated": False,
    }


def arbitrate(rule, context):
    """Arbitrate one boundary case.

    ``rule``    — the rule dict (with an ``arbitration`` block).
    ``context`` — {building, element, std_name, lang, ...}

    Returns a dict (see ``_fallback`` for the shape) with ``status`` always
    ``"pending"`` — an AI suggestion that awaits human confirmation.
    """
    arbitration = rule.get("arbitration") or {}
    if not arbitration.get("required"):
        return None

    # 1. Retrieve regulation evidence (deterministic RAG, free corpus only)
    evidence = _retrieve_evidence(arbitration.get("rag_query", rule.get("name", "")))
    ctx = dict(context)
    ctx["evidence"] = evidence

    # 2. Ask the LLM
    try:
        import llm.client as llm
        if not llm.available():
            res = _fallback(arbitration, "LLM 未配置，无法进行 AI 仲裁")
        else:
            system, user = _build_prompt(rule, arbitration, ctx)
            reply = llm.chat(system, user)
            parsed = _parse_json_response(reply)
            if not parsed:
                res = _fallback(arbitration, "AI 返回内容无法解析为结构化判定")
            else:
                parsed["status"] = "pending"
                parsed["ai_arbitrated"] = True
                parsed.setdefault("cited_clauses", [])
                res = parsed
    except Exception as ex:
        res = _fallback(arbitration, f"AI 仲裁调用失败: {ex}")

    # 3. Attach retrieval evidence + rule metadata for the UI
    res["rule_id"] = rule.get("id")
    res["rule_name"] = rule.get("name")
    res["arbitration_point"] = arbitration.get("point")
    res["evidence"] = evidence
    res["default_value"] = rule.get("threshold")
    return res


def arbitrate_batch(cases, context):
    """Arbitrate several cases. ``cases`` = [(rule, per-case context)].

    Returns a list parallel to ``cases`` (None where a rule has no
    arbitration block). Kept simple/sequential — the caller decides whether
    to background it.
    """
    out = []
    for rule, per_case in cases:
        merged = dict(context)
        merged.update(per_case or {})
        out.append(arbitrate(rule, merged))
    return out
