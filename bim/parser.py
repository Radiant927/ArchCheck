"""BIM ingestion — parse an IFC file into a structural report + review-ready data.

Real-world IFC files vary a lot. This parser extracts what is reliably present
(structural facts) and leaves rooms / fire zones / electrical parameters to be
supplemented (via the app's parameter editor or an LLM), per the hybrid design.
"""
import re
from pathlib import Path

try:
    import ifcopenshell
    IFC_AVAILABLE = True
except ImportError:
    ifcopenshell = None
    IFC_AVAILABLE = False

DOOR_WIDTH_RE = re.compile(r"(\d{3,4})\s*[xX×]\s*(\d{3,4})mm")

# IFC default length unit: milli-metre in many exports. We convert to metres.
MM_TO_M = 0.001


def available():
    return IFC_AVAILABLE


def _extrude_profile(item):
    if item.is_a("IfcExtrudedAreaSolid") and item.SweptArea.is_a("IfcRectangleProfileDef"):
        return item.SweptArea
    return None


def _door_width_m(door):
    """Door width in metres: parse from type name, fall back to geometry."""
    nm = door.Name or ""
    mm = DOOR_WIDTH_RE.search(nm)
    if mm:
        return int(mm.group(1)) / 1000.0
    if door.Representation:
        for rep in door.Representation.Representations:
            for it in (rep.Items or []):
                prof = _extrude_profile(it)
                if prof:
                    return prof.XDim * MM_TO_M
    return None


def _storey_footprint(m, storey):
    """Approximate footprint area (m²) from the largest floor-slab rectangle."""
    best = 0.0
    sid = storey.GlobalId
    for rel in m.by_type("IfcRelContainedInSpatialStructure"):
        if rel.RelatingStructure.GlobalId != sid:
            continue
        for e in rel.RelatedElements:
            if not (e.is_a("IfcSlab") or e.is_a("IfcSlabStandardCase")):
                continue
            if e.Representation:
                for rep in e.Representation.Representations:
                    for it in (rep.Items or []):
                        prof = _extrude_profile(it)
                        if prof:
                            a = (prof.XDim * MM_TO_M) * (prof.YDim * MM_TO_M)
                            best = max(best, a)
    return round(best, 1)


def parse_ifc(path):
    """Parse an IFC file into a structural report dict.

    Returns
    -------
    dict with keys: source, file_name, project_name, storey_count,
    building_footprint_area_sqm, floors[] (name/elevation/footprint/structure).
    """
    if not IFC_AVAILABLE:
        raise RuntimeError("ifcopenshell is not installed.")
    path = str(path)
    m = ifcopenshell.open(path)
    mm = MM_TO_M

    project = m.by_type("IfcProject")
    project_name = project[0].Name if project else None

    # group elements by storey via containment (keyed by GlobalId — ifcopenshell
    # does not guarantee object identity across queries)
    by_storey = {}
    for rel in m.by_type("IfcRelContainedInSpatialStructure"):
        gid = rel.RelatingStructure.GlobalId
        by_storey.setdefault(gid, []).extend(rel.RelatedElements)

    floors = []
    for storey in m.by_type("IfcBuildingStorey"):
        els = by_storey.get(storey.GlobalId, [])
        types = {}
        door_widths = []
        for e in els:
            types[e.is_a()] = types.get(e.is_a(), 0) + 1
            if e.is_a("IfcDoor"):
                w = _door_width_m(e)
                if w:
                    door_widths.append(round(w, 3))
        floors.append({
            "name": storey.Name or "?",
            "elevation_m": round((storey.Elevation or 0.0) * mm, 2),
            "footprint_area_sqm": _storey_footprint(m, storey),
            "structure": {
                "walls": types.get("IfcWallStandardCase", 0) + types.get("IfcWall", 0),
                "doors": types.get("IfcDoor", 0),
                "windows": types.get("IfcWindow", 0),
                "columns": types.get("IfcColumn", 0) + types.get("IfcColumnStandardCase", 0),
                "beams": types.get("IfcBeam", 0),
                "slabs": types.get("IfcSlab", 0) + types.get("IfcSlabStandardCase", 0),
                "stairs": types.get("IfcStair", 0),
                "door_widths_m": sorted(set(door_widths)),
                "door_count": len(door_widths),
            },
        })

    footprint = max((f["footprint_area_sqm"] for f in floors), default=0.0)

    return {
        "source": "ifc",
        "file_name": Path(path).name,
        "project_name": project_name,
        "storey_count": len(floors),
        "building_footprint_area_sqm": footprint,
        "floors": floors,
    }


def build_review_data(struct, rooms_template, floor_room_map=None):
    """Merge a parsed IFC structure with a room template into review-ready data.

    Parameters
    ----------
    struct : dict from parse_ifc()
    rooms_template : list of rooms (demo template) OR None to leave rooms empty
    floor_room_map : optional dict mapping storey name -> room list override

    Returns a dict shaped like demo_building_data.json (building_params + floors).
    """
    floors = []
    for i, f in enumerate(struct["floors"]):
        rooms = rooms_template or []
        if floor_room_map and f["name"] in floor_room_map:
            rooms = floor_room_map[f["name"]]
        floors.append({
            "floor_id": f"F{i+1}",
            "floor_name": f["name"],
            "rooms": [dict(r) for r in rooms],
            "fire_zones": [],
            "structure": f["structure"],
        })
    return {
        "project_name": struct.get("project_name") or "BIM Building",
        "source": "ifc",
        "building_params": {
            "total_floors": struct.get("storey_count", len(floors)),
            "occupancy_type": "office",
            "ground_floor_exit_width_m": 2.4,
            "fire_pool_volume_m3": 160.0,
            "transformer_capacity_kw": 650.0,
            "emergency_power_duration_min": 60.0,
        },
        "floors": floors,
    }
