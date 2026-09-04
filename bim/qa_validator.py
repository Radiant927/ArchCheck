"""Model usability QA — health score + per-check report for a parsed IFC.

Consumed by the BIM Reader agent. A model that fails a fatal check (empty shell,
no geometry on key elements) should not proceed to compliance review; everything
else is reported as a score + warnings so the reviewer knows the data's limits
(e.g. no space boundaries -> door association falls back to geometry).

Messages are stored in both languages (`message` zh / `message_en`) because QA
runs once at parse time while the UI language can be switched afterwards.
"""
from .extractor import _length_scale, _PREFIX_SCALE

# score deductions per check level
_ERROR_PENALTY = 40
_WARN_PENALTY = 10


def _declared_length_prefix(m):
    """Return the declared SI length-unit prefix (e.g. 'MILLI') or None."""
    for ua in m.by_type("IfcUnitAssignment"):
        for u in ua.Units:
            if u.is_a("IfcSIUnit") and u.UnitType == "LENGTHUNIT":
                return u.Prefix or "METER"
    return None


def _check_units(m, checks):
    declared = _declared_length_prefix(m)
    inferred = _length_scale(m)
    if declared is None:
        checks.append(("unit", "warn",
                       f"模型未声明长度单位，已从标高推断为 {'米' if inferred == 1 else '毫米'}。"
                       "真实 IFC 的声明单位常与实际坐标不一致，建议在建模软件中显式声明。",
                       f"No length unit declared; inferred from storey elevations as "
                       f"{'metres' if inferred == 1 else 'millimetres'}. Real-world IFCs often "
                       "declare a unit that contradicts the coordinates — declare it explicitly "
                       "in the authoring tool."))
    elif declared == "METER":
        checks.append(("unit", "ok", "已声明 SI 长度单位：米（1 单位 = 1m）。",
                       "Declared SI length unit: metre (1 unit = 1 m)."))
    else:
        mult = _PREFIX_SCALE.get(declared, 1.0)
        checks.append(("unit", "ok",
                       f"已声明 SI 长度单位：{declared}（1 单位 = {mult}m）。",
                       f"Declared SI length unit: {declared} (1 unit = {mult} m)."))


def _check_spaces(m, struct, checks):
    n_spaces = len(m.by_type("IfcSpace"))
    floors = struct.get("floors", [])
    if not floors:
        checks.append(("spaces", "error", "未能解析出任何楼层，模型结构不可用。",
                       "No storeys could be parsed — the model structure is unusable."))
        return
    with_rooms = sum(1 for f in floors if f.get("rooms"))
    if n_spaces == 0:
        checks.append(("spaces", "warn",
                       "模型没有 IfcSpace 房间数据，房间级审查将跳过，仅执行整楼聚合校核。",
                       "The model has no IfcSpace rooms — room-level checks are skipped; "
                       "only whole-building aggregate checks run."))
    elif with_rooms == 0:
        checks.append(("spaces", "warn", "有 IfcSpace 但未归属到楼层，房间无法进入逐层审查。",
                       "IfcSpaces exist but are not assigned to storeys, so rooms cannot "
                       "enter the per-floor review."))
    elif with_rooms / len(floors) < 0.7:
        checks.append(("spaces", "warn",
                       f"{len(floors) - with_rooms}/{len(floors)} 层无房间数据"
                       f"（覆盖率 {with_rooms / len(floors):.0%}），部分楼层仅做整楼聚合。",
                       f"{len(floors) - with_rooms}/{len(floors)} storeys have no room data "
                       f"(coverage {with_rooms / len(floors):.0%}); those floors are covered by "
                       "building-level aggregates only."))
    else:
        checks.append(("spaces", "ok",
                       f"{n_spaces} 个空间，{with_rooms}/{len(floors)} 层有房间数据。",
                       f"{n_spaces} spaces; {with_rooms}/{len(floors)} storeys carry room data."))


def _check_geometry(m, checks):
    key = [e for cls in ("IfcDoor", "IfcWindow", "IfcWall", "IfcWallStandardCase")
           for e in m.by_type(cls)]
    if not key:
        checks.append(("geometry", "error", "模型不含门/窗/墙构件，无法审查。",
                       "The model contains no door/window/wall elements — review not possible."))
        return
    with_rep = sum(1 for e in key if e.Representation)
    ratio = with_rep / len(key)
    if ratio < 0.5:
        checks.append(("geometry", "error",
                       f"关键构件仅 {with_rep}/{len(key)}（{ratio:.0%}）有几何表示，"
                       "存在空壳/纯分类引用风险，尺寸类判定将不可信。",
                       f"Only {with_rep}/{len(key)} key elements ({ratio:.0%}) carry geometry — "
                       "risk of an empty shell / classification-only references, so "
                       "dimension-based checks cannot be trusted."))
    elif ratio < 0.9:
        checks.append(("geometry", "warn",
                       f"关键构件 {with_rep}/{len(key)} 有几何表示。",
                       f"{with_rep}/{len(key)} key elements carry geometry."))
    else:
        checks.append(("geometry", "ok",
                       f"关键构件 {with_rep}/{len(key)} 均带几何表示。",
                       f"All {with_rep}/{len(key)} key elements carry geometry."))


def _check_boundaries(m, checks):
    spaces = m.by_type("IfcSpace")
    if not spaces:
        return
    bounded = sum(1 for s in spaces if (s.BoundedBy or []))
    if bounded == 0:
        checks.append(("boundaries", "warn",
                       "模型没有 IfcRelSpaceBoundary，门-房间关联与疏散距离依赖几何兜底"
                       "（结果可能不如显式边界精确）。",
                       "No IfcRelSpaceBoundary in the model — door-to-room association and "
                       "egress distances fall back to geometry (less precise than explicit "
                       "boundaries)."))
    elif bounded / len(spaces) < 0.5:
        checks.append(("boundaries", "warn",
                       f"仅 {bounded}/{len(spaces)} 空间有空间边界，门关联部分依赖几何兜底。",
                       f"Only {bounded}/{len(spaces)} spaces have space boundaries; door "
                       "association partly falls back to geometry."))
    else:
        checks.append(("boundaries", "ok",
                       f"{bounded}/{len(spaces)} 空间有空间边界，门关联采用精确边界路径。",
                       f"{bounded}/{len(spaces)} spaces have space boundaries; door association "
                       "uses the exact-boundary path."))


def _safe_count(m, type_name):
    """by_type count that tolerates entity types absent from the schema
    (e.g. IfcPipeSegment doesn't exist in IFC2X3)."""
    try:
        return len(m.by_type(type_name))
    except Exception:
        return 0


# Entity base types the extractor (bim/extractor.parse_model) consumes, matched
# by subtype (a StandardCase or IFC2X3 generic element is_a its IFC4 base).
_HANDLED_BASE_TYPES = [
    # building / structure — counted into structure{} + structural_elements
    "IfcWall", "IfcDoor", "IfcWindow", "IfcSlab", "IfcColumn", "IfcBeam",
    "IfcStair", "IfcRamp", "IfcRampFlight",
    # pipes / ducts / fittings — consumed as pipes[] / ducts[] / pipe_fittings[]
    # (IfcFlowSegment covers pipes + ducts in both schemas; IfcFlowFitting
    #  covers pipe/duct fittings in both schemas)
    "IfcFlowSegment", "IfcFlowFitting",
    # electrical — consumed as electrical_elements[]
    "IfcElectricAppliance", "IfcLightFixture", "IfcElectricDistributionBoard",
    "IfcFlowTerminal", "IfcFlowController",
]


def _is_handled(e):
    """True if the extractor consumes this element in some form."""
    return any(e.is_a(t) for t in _HANDLED_BASE_TYPES)


def _check_entity_coverage(m, checks):
    """Report physical element types present in the model that the extractor
    does NOT consume — the gap between "what the file has" and "what we parse".

    Reported as ``info`` (never lowers the health score — extra element types
    are normal model content, not a defect); the machine-readable breakdown
    lives in stats['entity_coverage'].
    """
    handled = {}
    unhandled = {}
    for e in m.by_type("IfcElement"):
        t = e.is_a()
        if _is_handled(e):
            handled[t] = handled.get(t, 0) + 1
        else:
            unhandled[t] = unhandled.get(t, 0) + 1
    if unhandled:
        items = sorted(unhandled.items(), key=lambda kv: -kv[1])
        total = sum(c for _, c in items)
        names = "、".join(f"{t}×{c}" for t, c in items[:5])
        more = f" 等 {len(items)} 类" if len(items) > 5 else ""
        msg = (f"模型含 {total} 个未识别构件（{names}{more}）。提取器未消费这些类型，"
               "相关规则可能无法判定；如需支持请扩展 bim/extractor。")
        msg_en = (f"Model has {total} unrecognised elements ({names}{more}). The "
                  "extractor does not consume these types, so related checks may not run.")
        checks.append(("coverage", "info", msg, msg_en))
    return {"handled": handled, "unhandled": unhandled}


def validate_model(m, struct):
    """Return a usability report: {score, fatal, checks, stats}.

    score: 0-100 health score. fatal: True means the model should be blocked
    from review (empty shell / no geometry / no floors).
    """
    checks = []
    _check_units(m, checks)
    _check_spaces(m, struct, checks)
    _check_geometry(m, checks)
    _check_boundaries(m, checks)
    entity_coverage = _check_entity_coverage(m, checks)

    # Only error / warn deduct from the health score; info notes never do.
    score = 100 - sum(_ERROR_PENALTY if lvl == "error" else _WARN_PENALTY
                      for _, lvl, _, _ in checks if lvl in ("error", "warn"))
    score = max(0, min(100, score))
    report = {
        "score": score,
        "fatal": any(lvl == "error" for _, lvl, _, _ in checks),
        "checks": [{"id": cid, "level": lvl, "message": msg, "message_en": msg_en}
                   for cid, lvl, msg, msg_en in checks],
        "stats": {
            "storeys": _safe_count(m, "IfcBuildingStorey"),
            "spaces": _safe_count(m, "IfcSpace"),
            "doors": _safe_count(m, "IfcDoor"),
            "windows": _safe_count(m, "IfcWindow"),
            "walls": _safe_count(m, "IfcWall") + _safe_count(m, "IfcWallStandardCase"),
            "pipes": _safe_count(m, "IfcPipeSegment") or _safe_count(m, "IfcFlowSegment"),
            "pipe_fittings": _safe_count(m, "IfcPipeFitting"),
            "ducts": _safe_count(m, "IfcDuctSegment"),
            "elements": sum(1 for e in m.by_type("IfcElement")),
        },
        "entity_coverage": entity_coverage,
    }
    return report
