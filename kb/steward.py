"""KB Steward agent — resolve dynamic rule thresholds from context.

Priority: deterministic formula -> RAG/LLM query -> static fallback. Results are
cached per (rule_id, context) so per-element rule evaluation stays fast even when
the LLM is slow or unreachable.
"""
import re

from llm import client

_cache = {}


def resolve_threshold(rule, item):
    """Effective threshold for `rule` given the evaluated `item`'s context."""
    dyn = rule.get("dynamic_threshold")
    if not dyn:
        return rule["threshold"]
    ctx = {f: item.get(f) for f in dyn.get("context_fields", [])}
    cache_key = (rule["id"], tuple(sorted((k, ctx[k]) for k in ctx)))
    if cache_key in _cache:
        return _cache[cache_key]

    val = None
    formula = dyn.get("formula")
    if formula:
        try:
            # Substitute context values into the expression, then evaluate with a
            # restricted namespace (no builtins, only math helpers).
            expr = formula
            for k, v in ctx.items():
                expr = expr.replace("{" + k + "}", str(v))
            ns = {"max": max, "min": min, "abs": abs, "round": round}
            val = float(eval(expr, {"__builtins__": {}}, ns))
        except Exception:
            val = None

    if val is None and client.available():
        q = dyn.get("query", "")
        for k, v in ctx.items():
            q = q.replace("{" + k + "}", str(v))
        val = _llm_extract(q, rule.get("code_ref", ""))

    if val is None:
        val = dyn.get("fallback", rule["threshold"])
    _cache[cache_key] = val
    return val


def _llm_extract(query, code_ref):
    try:
        system = "你是建筑规范数值提取器。"
        user = f"{query}，最小数值（米），只输出数字"
        out = client.chat(system, user)
        m = re.search(r"[-+]?\d*\.?\d+", out)
        if m:
            v = float(m.group(0))
            if 0 < v < 10:
                return v
    except Exception:
        pass
    return None
