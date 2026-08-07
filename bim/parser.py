"""BIM ingestion — parse an IFC file into a structural report + review-ready data.

Real-world IFC files vary a lot. This parser extracts structural facts
(storeys, footprint, door widths, element counts) and, when the model contains
them, real spaces/rooms with geometry-derived areas. Electrical / fire-zone
parameters are usually not in architectural IFCs, so those are defaulted and
left for the app's parameter editor to supplement.

Units: the model's length unit is read from the IFC (many exports use mm,
others use m) and every conversion is scaled accordingly.
"""
import re
from pathlib import Path

try:
    import ifcopenshell
    import ifcopenshell.geom as ifcgeom
    IFC_AVAILABLE = True
except ImportError:
    ifcopenshell = None
    ifcgeom = None
    IFC_AVAILABLE = False

DOOR_WIDTH_RE = re.compile(r"(\d{3,4})\s*[xX×]\s*(\d{3,4})mm")

# Meters per IFC SI length-unit prefix.
_PREFIX_SCALE = {"MILLI": 0.001, "CENTI": 0.01, "DECI": 0.1,
                 "DECA": 10.0, "HECTO": 100.0, "KILO": 1000.0}


def available():
    return IFC_AVAILABLE


def _length_scale(m):
    """Meters per model length unit (1.0 for m, 0.001 for mm).

    If the model declares no length unit, infer it from the storey elevations:
    a real building's storey elevations land in ~0.5-500 m, whereas mm models
    are in the thousands+.
    """
    for ua in m.by_type("IfcUnitAssignment"):
        for u in ua.Units:
            if u.is_a("IfcSIUnit") and u.UnitType == "LENGTHUNIT":
                return _PREFIX_SCALE.get(u.Prefix, 1.0)
    elevations = [abs(s.Elevation or 0.0) for s in m.by_type("IfcBuildingStorey")]
    if elevations:
        peak = max(elevations)
        if 0.5 <= peak <= 500:
            return 1.0  # metres
    return 0.001  # fallback: mm


def _extrude_profile(item):
    if item.is_a("IfcExtrudedAreaSolid") and item.SweptArea.is_a("IfcRectangleProfileDef"):
        return item.SweptArea
    return None


def _door_width_m(door, scale):
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
                    return prof.XDim * scale
    return None


def _storey_footprint(m, storey, scale):
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
                            a = (prof.XDim * scale) * (prof.YDim * scale)
                            best = max(best, a)
    return round(best, 1)


def _space_area_m2(space, scale, settings=None):
    """Room area (m²) from the tessellated geometry's XY projection (convex hull).

    Works for both extruded and Brep space geometry; units follow the model.
    """
    try:
        if settings is None:
            settings = ifcgeom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifcgeom.create_shape(settings, space)
        v = shape.geometry.verts
        pts = sorted(set((v[i], v[i + 1]) for i in range(0, len(v), 3)))
        if len(pts) < 3:
            return 0.0
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lo = []
        for p in pts:
            while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
                lo.pop()
            lo.append(p)
        up = []
        for p in reversed(pts):
            while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
                up.pop()
            up.append(p)
        hull = lo[:-1] + up[:-1]
        area = 0.0
        for i in range(len(hull)):
            x1, y1 = hull[i]
            x2, y2 = hull[(i + 1) % len(hull)]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0 * (scale * scale)
    except Exception:
        return 0.0


def _classify_room_type(name):
    """Map a space name/reference to a review-room type."""
    n = (name or "").lower()
    if any(k in n for k in ("stair", "楼梯", "梯")):
        return "Stairwell"
    if any(k in n for k in ("corr", "走廊", "廊", "lobby", "foyer", "vestib", "hall", "前室")):
        return "Corridor"
    if any(k in n for k in ("meet", "会议", "training", "培训", "class", "教室", "auditor", "多功能")):
        return "Meeting Room"
    if any(k in n for k in ("electr", "mep", "配电", "设备", "mech", "plant", "机房", "lift", "elev")):
        return "Equipment Room"
    if any(k in n for k in ("wc", "toilet", "洗手", "厕所")):
        return "Vestibule"
    return "Office"


def _space_to_room(space, area, ref=""):
    """Build a review-engine room dict; non-BIM params get sensible defaults."""
    name = space.Name or "?"
    rtype = _classify_room_type(f"{ref} {name}")
    return {
        "id": space.GlobalId or name,
        "name": name,
        "type": rtype,
        "room_area_sqm": round(area, 1),
        "exit_count": 2 if area > 50 else 1,
        "door_width_m": 0.9,
        "has_emergency_light": rtype not in ("Stairwell", "Corridor", "Vestibule"),
        "dist_to_water_m": 5.0,
        "circuit_load_a": 10,
        "outlet_spacing_m": 5.0,
        "corridor_length_m": 0,
    }


def parse_ifc(path, max_floors=None, max_rooms_per_floor=None):
    """Parse an IFC file into a structural report dict (with rooms when present).

    Parameters
    ----------
    max_floors : int | None — keep only the N storeys with the most spaces
    max_rooms_per_floor : int | None — keep only the N largest rooms per storey
    """
    if not IFC_AVAILABLE:
        raise RuntimeError("ifcopenshell is not installed.")
    path = str(path)
    m = ifcopenshell.open(path)
    scale = _length_scale(m)
    geom_settings = ifcgeom.settings()
    geom_settings.set(geom_settings.USE_WORLD_COORDS, True)

    project = m.by_type("IfcProject")
    project_name = project[0].Name if project else None

    # storey -> contained elements (walls/doors/...) and aggregated spaces
    by_storey = {}
    storey_spaces = {}
    space_ids = {s.GlobalId for s in m.by_type("IfcSpace")}
    for rel in m.by_type("IfcRelContainedInSpatialStructure"):
        gid = rel.RelatingStructure.GlobalId
        by_storey.setdefault(gid, []).extend(rel.RelatedElements)
    for rel in m.by_type("IfcRelAggregates"):
        if rel.RelatingObject.is_a("IfcBuildingStorey"):
            kids = [o for o in rel.RelatedObjects if o.GlobalId in space_ids]
            if kids:
                storey_spaces.setdefault(rel.RelatingObject.GlobalId, []).extend(kids)

    # Pset_SpaceCommon.Reference -> space (room types often live here, e.g. "Stair S1")
    ref_map = {}
    for rel in m.by_type("IfcRelDefinesByProperties"):
        pd = rel.RelatingPropertyDefinition
        if not (pd.is_a("IfcPropertySet") and pd.Name == "Pset_SpaceCommon"):
            continue
        ref = ""
        for p in pd.HasProperties:
            if p.Name == "Reference" and p.NominalValue:
                ref = str(p.NominalValue.wrappedValue)
                break
        if ref:
            for o in rel.RelatedObjects:
                if o.GlobalId in space_ids:
                    ref_map[o.GlobalId] = ref

    # storeys sorted by elevation; optionally keep the busiest N
    storeys = sorted(m.by_type("IfcBuildingStorey"),
                     key=lambda s: s.Elevation or 0.0)
    if max_floors:
        storeys = sorted(storeys,
                         key=lambda s: len(storey_spaces.get(s.GlobalId, [])),
                         reverse=True)[:max_floors]
        storeys.sort(key=lambda s: s.Elevation or 0.0)

    floors = []
    for storey in storeys:
        els = by_storey.get(storey.GlobalId, [])
        types = {}
        door_widths = []
        for e in els:
            types[e.is_a()] = types.get(e.is_a(), 0) + 1
            if e.is_a("IfcDoor"):
                w = _door_width_m(e, scale)
                if w:
                    door_widths.append(round(w, 3))

        spaces = storey_spaces.get(storey.GlobalId, [])
        sized = [(s, _space_area_m2(s, scale, geom_settings)) for s in spaces]
        sized.sort(key=lambda x: -x[1])
        if max_rooms_per_floor:
            sized = sized[:max_rooms_per_floor]
        rooms = [_space_to_room(s, a, ref_map.get(s.GlobalId, "")) for s, a in sized]

        floors.append({
            "name": storey.Name or "?",
            "elevation_m": round((storey.Elevation or 0.0) * scale, 2),
            "footprint_area_sqm": _storey_footprint(m, storey, scale),
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
            "rooms": rooms,
        })

    footprint = max((f["footprint_area_sqm"] for f in floors), default=0.0)
    return {
        "source": "ifc",
        "file_name": Path(path).name,
        "project_name": project_name,
        "storey_count": len(floors),
        "building_footprint_area_sqm": footprint,
        "total_rooms": sum(len(f["rooms"]) for f in floors),
        "floors": floors,
    }


def build_review_data(struct, rooms_template=None, floor_room_map=None):
    """Merge a parsed IFC structure into review-ready data.

    Rooms parsed from the IFC are kept; storeys without rooms fall back to the
    template / floor_room_map.
    """
    floors = []
    for i, f in enumerate(struct["floors"]):
        rooms = f.get("rooms") or []
        if not rooms:
            rooms = rooms_template or []
            if floor_room_map and f["name"] in floor_room_map:
                rooms = floor_room_map[f["name"]]
        floors.append({
            "floor_id": f"F{i + 1}",
            "floor_name": f["name"],
            "rooms": [dict(r) for r in rooms],
            "fire_zones": [],
            "structure": f.get("structure"),
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
