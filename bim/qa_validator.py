"""Model usability QA — health score + per-check report for a parsed IFC.

Consumed by the BIM Reader agent. A model that fails a fatal check (empty shell,
no geometry on key elements) should not proceed to compliance review; everything
else is reported as a score + warnings so the reviewer knows the data's limits
(e.g. no space boundaries -> door association falls back to geometry).
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
                       "真实 IFC 的声明单位常与实际坐标不一致，建议在建模软件中显式声明。"))
    elif declared == "METER":
        checks.append(("unit", "ok", "已声明 SI 长度单位：米（1 单位 = 1m）。"))
    else:
        mult = _PREFIX_SCALE.get(declared, 1.0)
        checks.append(("unit", "ok",
                       f"已声明 SI 长度单位：{declared}（1 单位 = {mult}m）。"))


def _check_spaces(m, struct, checks):
    n_spaces = len(m.by_type("IfcSpace"))
    floors = struct.get("floors", [])
    if not floors:
        checks.append(("spaces", "error", "未能解析出任何楼层，模型结构不可用。"))
        return
    with_rooms = sum(1 for f in floors if f.get("rooms"))
    if n_spaces == 0:
        checks.append(("spaces", "warn",
                       "模型没有 IfcSpace 房间数据，房间级审查将跳过，仅执行整楼聚合校核。"))
    elif with_rooms == 0:
        checks.append(("spaces", "warn", "有 IfcSpace 但未归属到楼层，房间无法进入逐层审查。"))
    elif with_rooms / len(floors) < 0.7:
        checks.append(("spaces", "warn",
                       f"{len(floors) - with_rooms}/{len(floors)} 层无房间数据"
                       f"（覆盖率 {with_rooms / len(floors):.0%}），部分楼层仅做整楼聚合。"))
    else:
        checks.append(("spaces", "ok",
                       f"{n_spaces} 个空间，{with_rooms}/{len(floors)} 层有房间数据。"))


def _check_geometry(m, checks):
    key = [e for cls in ("IfcDoor", "IfcWindow", "IfcWall", "IfcWallStandardCase")
           for e in m.by_type(cls)]
    if not key:
        checks.append(("geometry", "error", "模型不含门/窗/墙构件，无法审查。"))
        return
    with_rep = sum(1 for e in key if e.Representation)
    ratio = with_rep / len(key)
    if ratio < 0.5:
        checks.append(("geometry", "error",
                       f"关键构件仅 {with_rep}/{len(key)}（{ratio:.0%}）有几何表示，"
                       "存在空壳/纯分类引用风险，尺寸类判定将不可信。"))
    elif ratio < 0.9:
        checks.append(("geometry", "warn", f"关键构件 {with_rep}/{len(key)} 有几何表示。"))
    else:
        checks.append(("geometry", "ok", f"关键构件 {with_rep}/{len(key)} 均带几何表示。"))


def _check_boundaries(m, checks):
    spaces = m.by_type("IfcSpace")
    if not spaces:
        return
    bounded = sum(1 for s in spaces if (s.BoundedBy or []))
    if bounded == 0:
        checks.append(("boundaries", "warn",
                       "模型没有 IfcRelSpaceBoundary，门-房间关联与疏散距离依赖几何兜底"
                       "（结果可能不如显式边界精确）。"))
    elif bounded / len(spaces) < 0.5:
        checks.append(("boundaries", "warn",
                       f"仅 {bounded}/{len(spaces)} 空间有空间边界，门关联部分依赖几何兜底。"))
    else:
        checks.append(("boundaries", "ok",
                       f"{bounded}/{len(spaces)} 空间有空间边界，门关联采用精确边界路径。"))


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

    score = 100 - sum(_ERROR_PENALTY if lvl == "error" else _WARN_PENALTY
                      for _, lvl, _ in checks if lvl != "ok")
    score = max(0, min(100, score))
    report = {
        "score": score,
        "fatal": any(lvl == "error" for _, lvl, _ in checks),
        "checks": [{"id": cid, "level": lvl, "message": msg} for cid, lvl, msg in checks],
        "stats": {
            "storeys": len(m.by_type("IfcBuildingStorey")),
            "spaces": len(m.by_type("IfcSpace")),
            "doors": len(m.by_type("IfcDoor")),
            "windows": len(m.by_type("IfcWindow")),
            "walls": len(m.by_type("IfcWall")) + len(m.by_type("IfcWallStandardCase")),
        },
    }
    return report
