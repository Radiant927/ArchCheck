"""AI semantic enrichment layer — invisibly normalises ambiguous BIM semantics
BEFORE the deterministic rule engine judges.

Position in the pipeline (see presentation/2026-09-15/AI语义预处理层方案设计_2026-09-15.md):

    BIM Reader -> [enrich_review_data] -> Compliance Judge (deterministic)

The LLM never judges and never touches a single geometric number. It only fills
*semantic* fields from a controlled vocabulary, when the cheap deterministic
classifiers are unsure:

    * room    ``type``           for rooms the keyword tagger left ``Unknown``
    * element ``material_class`` for structural elements whose free-text
                                 material (or foreign-language name) is unclear
    * pipe    ``pipe_type``      for pipes whose system is ``unknown``

Engineering guarantees:
  * Only ambiguous items are sent (high-confidence keyword hits stay as-is).
  * Output is validated against enums — an out-of-vocabulary value is discarded.
  * All geometry / counts / distances are read-only to this layer.
  * Results carry provenance (keyword/ai) in ``bdata["_enrichment"]``.
  * One batched LLM call for the whole building; disk cache by content hash;
    graceful fallback to deterministic results when the LLM is unavailable.
"""

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO / "data" / ".enrich_cache.json"

# ---------------------------------------------------------------------------
# Controlled vocabularies (must stay in sync with the rule engine / UI labels)
# ---------------------------------------------------------------------------

ROOM_VOCAB = ["Office", "Corridor", "Stairwell", "Meeting Room",
              "Equipment Room", "Vestibule",
              # 住宅类（2026-09-20 扩充）：住宅模型（Jasmin/Duplex 等）需要
              "Living Room", "Bedroom", "Kitchen", "Dining Room",
              "Storage", "Reception",
              "Unknown"]

MATERIAL_VOCAB = ["concrete", "steel", "wood", "masonry", "composite", "unknown"]

# MUST stay in sync with bim/extractor._PIPE_TYPE_RULES and the MEP rules'
# pipe_type conditions (fire/drainage/supply/gas …). An AI value outside this
# enum is discarded, so a mismatch would make the whole pipe layer dead weight.
PIPE_VOCAB = ["fire", "drainage", "supply", "hydronic", "gas", "lab_gas",
              "vent", "unknown"]

CONFIDENCE = {"high", "medium", "low"}

# Free-text material name -> canonical class. Multi-lingual on purpose (real
# IFCs from Revit/FZK use German: Beton / Stahl / Holz / Ziegel).
_MATERIAL_KEYWORDS = [
    ("wood", ["wood", "holz", "timber", "lumber", "glulam", "clt", "木"]),
    ("steel", ["steel", "stahl", "s235", "s355", "s275", "型钢", "钢"]),
    ("masonry", ["brick", "ziegel", "mauer", "masonry", "clay", "block", "砖", "砌"]),
    ("concrete", ["concrete", "beton", "c20", "c25", "c30", "c35", "c40",
                  "rc ", "reinforced", "钢筋混凝土", "混凝土", "水泥"]),
    ("composite", ["composite", "verbund", "混合", "组合"]),
]


def classify_material(text):
    """Deterministic free-text material name -> controlled material_class."""
    if not text:
        return "unknown"
    n = str(text).lower()
    for cls, keys in _MATERIAL_KEYWORDS:
        if any(k in n for k in keys):
            return cls
    return "unknown"


# ---------------------------------------------------------------------------
# Candidate collection (only the items deterministic classifiers could not nail)
# ---------------------------------------------------------------------------

def _floor_rooms(floor):
    return floor.get("rooms") or []


def _struct_elements(floor):
    return floor.get("structural_elements") or []


def _collect_candidates(bdata):
    """Tag every structural element with material_class (deterministic), then
    gather the low-confidence items a single LLM call may resolve.

    Returns (rooms, elements, pipes, trace) where each candidate is a dict
    carrying its floor index and a stable local key.
    """
    trace = {"rooms": {}, "elements": {}, "pipes": {}}
    room_cands, elem_cands, pipe_cands = [], [], []

    for fi, floor in enumerate(bdata.get("floors", [])):
        # --- rooms: only those the extractor's keyword tagger left Unknown ---
        for r in _floor_rooms(floor):
            if (r.get("type") or "Unknown") == "Unknown":
                key = r.get("id") or f"r{fi}:{r.get('name')}"
                # Name only: no area/floor, so the model must classify from the
                # functional text itself and abstain on bare numeric codes.
                room_cands.append({"key": key, "name": r.get("name", "?")})
            # NOTE: high-confidence room types are untouched.

        # --- structural elements: deterministic material_class for all ------
        for el in _struct_elements(floor):
            raw = el.get("material")
            cls = classify_material(raw)
            el["material_class"] = cls
            key = el.get("id") or f"e{fi}:{el.get('name')}"
            if cls != "unknown":
                trace["elements"][key] = {
                    "field": "material_class", "value": cls,
                    "source": "keyword", "confidence": "high",
                    "raw_material": raw,
                }
            else:
                elem_cands.append({
                    "key": key, "name": el.get("name", "?"),
                    "element_type": el.get("element_type", "?"),
                    "material": raw,
                })

        # --- pipes: only unknown systems ------------------------------------
        for pi, p in enumerate(floor.get("pipes") or []):
            if (p.get("pipe_type") or "unknown") == "unknown":
                key = p.get("id") or f"p{fi}:{pi}:{p.get('name')}"
                # Name/material only — diameter carries no system semantics.
                pipe_cands.append({
                    "key": key, "name": p.get("name", "?"),
                    "material": p.get("material"),
                })

    return room_cands, elem_cands, pipe_cands, trace


# ---------------------------------------------------------------------------
# LLM batched semantic labelling
# ---------------------------------------------------------------------------

ENRICHER_PROMPT_VERSION = "v4_residential_vocab"

_SYSTEM = (
    "You are a BIM classification assistant. Given short descriptions of building "
    "objects from an IFC model (names may be English, German, Chinese, abbreviated "
    "or client-authored), map each to the SINGLE most appropriate controlled category.\n"
    "Hard rules:\n"
    "- Classify ONLY from textual evidence: the object name and (for materials) the "
    "given material text. Area, floor, diameter and size are CONTEXT, never evidence "
    "of a room's function or a member's material.\n"
    "- A room whose name is only a number or project code (e.g. '101', 'A102', '70.001', "
    "'2.03') with no functional word MUST be 'Unknown' — do NOT guess office/meeting/"
    "toilet from its size. Abstain unless a word in the text indicates the function.\n"
    "- Do NOT force a real function into the nearest enum value. Only assign an enum "
    "value when the room truly IS that category, not merely similar to it. If the room's "
    "function is clear but is NOT in the enum list, output 'Unknown'.\n"
    "- Residential rooms ARE in the enum: living room / Wohnzimmer -> 'Living Room'; "
    "bedroom / Schlafzimmer / Kinderzimmer -> 'Bedroom'; kitchen / Kueche / Küche -> "
    "'Kitchen'; dining / Esszimmer -> 'Dining Room'. Storage / Lager / Archiv / "
    "Abstellraum -> 'Storage'; reception / Empfang -> 'Reception'.\n"
    "- Material: use explicit material words or conventional construction terms in the "
    "name/material (timber, wood, holz, steel, stahl, concrete, beton, brick, masonry; "
    "also a clearly named timber/steel SYSTEM type). A GENERIC member with no material "
    "indicator ('generic slab', 'solid', 'unnamed', a bare code) MUST be 'unknown' — do "
    "NOT default generic concrete slabs/beams/columns to concrete. (A named cast-in-place "
    "foundation/pad type may be concrete, at low confidence.)\n"
    "- Only output a category from the given enum lists; when undecidable use the "
    "unknown/Unknown value. Never infer dimensions, counts or any numeric fact.\n"
    "Output strictly one JSON object, no prose, no code fences."
)


def _build_user(rooms, elements, pipes):
    payload = {"rooms": rooms, "elements": elements, "pipes": pipes}
    return (
        "Classify every object below. Enum choices:\n"
        f"- rooms[].type one of {ROOM_VOCAB}\n"
        f"- elements[].material_class one of {MATERIAL_VOCAB} "
        "(primary structural material of that member)\n"
        f"- pipes[].pipe_type one of {PIPE_VOCAB}\n"
        "Respond with JSON keyed by the same object key, in this shape:\n"
        '{"rooms": {"<key>": {"type": ..., "confidence": "high|medium|low", '
        '"reason": "short (<=12 words)"}}, '
        '"elements": {"<key>": {"material_class": ..., "confidence": ..., "reason": ...}}, '
        '"pipes": {"<key>": {"pipe_type": ..., "confidence": ..., "reason": ...}}}\n\n'
        f"Objects:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_json(text):
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1] if len(t.split("```")) > 1 else t
        if t.startswith("json"):
            t = t[4:]
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(t[s:e + 1])
    except Exception:
        return None


def _load_cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# 一次问太多会让响应超出 LLM_MAX_TOKENS 被截断、JSON 解析失败 —— 分块调用。
# 每块同时给足 token 预算（分类答案含 reason，verbose 时会超默认 1600）。
CHUNK_SIZE = 30
CHUNK_MAX_TOKENS = 3500


def _llm_classify(rooms, elements, pipes):
    """分块批量调用。返回 (answer, n_cached)，LLM 不可用/全失败时返回 None。

    每个分块单独缓存（按内容哈希）；大模型（数百候选）也能全部覆盖，
    而不是整栋楼只跑第一个响应。
    """
    try:
        import llm.client as llm
        if not llm.available():
            return None
    except Exception:
        return None

    cache = _load_cache()
    out = {"rooms": {}, "elements": {}, "pipes": {}}
    n_cached = 0
    any_ok = False

    items = ([("r", c) for c in rooms] + [("e", c) for c in elements]
             + [("p", c) for c in pipes])
    for group in _chunks(items, CHUNK_SIZE):
        sub_r = [c for t, c in group if t == "r"]
        sub_e = [c for t, c in group if t == "e"]
        sub_p = [c for t, c in group if t == "p"]
        req = {"v": ENRICHER_PROMPT_VERSION, "r": sub_r, "e": sub_e, "p": sub_p}
        h = hashlib.sha1(json.dumps(req, ensure_ascii=False,
                                    sort_keys=True).encode("utf-8")).hexdigest()
        if h in cache:
            ans = cache[h]
            n_cached += len(group)
        else:
            reply = llm.chat(_SYSTEM, _build_user(sub_r, sub_e, sub_p),
                             max_tokens=CHUNK_MAX_TOKENS)
            ans = _parse_json(reply)
            if ans is None:
                continue  # 该块失败，保留其他块的成果
            cache[h] = ans
        any_ok = True
        out["rooms"].update(ans.get("rooms") or {})
        out["elements"].update(ans.get("elements") or {})
        out["pipes"].update(ans.get("pipes") or {})

    _save_cache(cache)
    if not any_ok:
        return None
    return out, n_cached


def _valid(value, vocab):
    return isinstance(value, str) and value in vocab


# ---------------------------------------------------------------------------
# Merge AI answers back into building data
# ---------------------------------------------------------------------------

def _merge(bdata, answer, rooms, elements, pipes, trace, stats):
    """Write validated AI labels onto the real items; record provenance."""
    if not isinstance(answer, dict):
        return
    ans_rooms = answer.get("rooms") or {}
    ans_elems = answer.get("elements") or {}
    ans_pipes = answer.get("pipes") or {}

    room_keys = {c["key"] for c in rooms}
    elem_keys = {c["key"] for c in elements}
    pipe_keys = {c["key"] for c in pipes}

    for fi, floor in enumerate(bdata.get("floors", [])):
        for r in _floor_rooms(floor):
            key = r.get("id") or f"r{fi}:{r.get('name')}"
            if key not in room_keys:
                continue
            a = ans_rooms.get(key) or {}
            val = a.get("type")
            if _valid(val, ROOM_VOCAB) and val != "Unknown":
                r["type"] = val
                stats["ai_resolved"] += 1
                trace["rooms"][key] = {
                    "from": "Unknown", "to": val, "source": "ai",
                    "confidence": a.get("confidence") if a.get("confidence") in CONFIDENCE else "low",
                    "reason": str(a.get("reason", ""))[:80],
                }
            elif val == "Unknown":
                stats["ai_abstained"] += 1  # honest: text genuinely insufficient
            else:
                stats["rejected"] += 1      # out-of-vocab / malformed answer

        for el in _struct_elements(floor):
            key = el.get("id") or f"e{fi}:{el.get('name')}"
            if key not in elem_keys:
                continue
            a = ans_elems.get(key) or {}
            val = a.get("material_class")
            if _valid(val, MATERIAL_VOCAB) and val != "unknown":
                el["material_class"] = val
                stats["ai_resolved"] += 1
                trace["elements"][key] = {
                    "field": "material_class", "value": val, "source": "ai",
                    "confidence": a.get("confidence") if a.get("confidence") in CONFIDENCE else "low",
                    "raw_material": el.get("material"),
                    "reason": str(a.get("reason", ""))[:80],
                }
            elif val == "unknown":
                stats["ai_abstained"] += 1
            else:
                stats["rejected"] += 1

        for pi, p in enumerate(floor.get("pipes") or []):
            key = p.get("id") or f"p{fi}:{pi}:{p.get('name')}"
            if key not in pipe_keys:
                continue
            a = ans_pipes.get(key) or {}
            val = a.get("pipe_type")
            if _valid(val, PIPE_VOCAB) and val != "unknown":
                p["pipe_type"] = val
                stats["ai_resolved"] += 1
                trace["pipes"][key] = {
                    "from": "unknown", "to": val, "source": "ai",
                    "confidence": a.get("confidence") if a.get("confidence") in CONFIDENCE else "low",
                    "reason": str(a.get("reason", ""))[:80],
                }
            elif val == "unknown":
                stats["ai_abstained"] += 1
            else:
                stats["rejected"] += 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def enrich_review_data(bdata):
    """Invisibly normalise room type / material class / pipe system semantics.

    Mutates ``bdata`` in place and attaches a provenance ledger at
    ``bdata["_enrichment"]``. Safe on demo / hand-built data (no floors ->
    no-op) and when the LLM is down (deterministic results only).
    """
    if not isinstance(bdata, dict) or not bdata.get("floors"):
        return bdata

    rooms, elements, pipes, trace = _collect_candidates(bdata)
    stats = {"candidates": len(rooms) + len(elements) + len(pipes),
             "rooms": len(rooms), "elements": len(elements), "pipes": len(pipes),
             "ai_resolved": 0, "ai_abstained": 0, "rejected": 0, "cached": 0}

    llm_used = False
    if rooms or elements or pipes:
        result = _llm_classify(rooms, elements, pipes)
        if result is not None:
            answer, n_cached = result
            llm_used = True
            stats["cached"] = n_cached
            _merge(bdata, answer, rooms, elements, pipes, trace, stats)

    bdata["_enrichment"] = {
        "enabled": True,
        "llm_used": llm_used,
        "stats": stats,
        "rooms": trace["rooms"],
        "elements": trace["elements"],
        "pipes": trace["pipes"],
    }
    return bdata
