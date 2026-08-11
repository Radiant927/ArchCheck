"""BIM data extraction — turn an opened IFC model into a structural report + review-ready data.

Pure extraction: no model-quality checks here (see bim/qa_validator.py). Real-world
IFC files vary a lot; this extracts structural facts (storeys, footprint, door
widths, element counts) and, when the model contains them, real spaces/rooms with
geometry-derived areas. Electrical / fire-zone parameters are usually not in
architectural IFCs, so those are defaulted and left for the app's parameter editor.

Units: the model's length unit is read from the IFC (many exports use mm, others
use m) and every conversion is scaled accordingly.
"""
import re
from pathlib import Path

import networkx as nx

try:
    import ifcopenshell
    import ifcopenshell.geom as ifcgeom
    IFC_AVAILABLE = True
except ImportError:
    ifcopenshell = None
    ifcgeom = None
    IFC_AVAILABLE = False

DOOR_WIDTH_RE = re.compile(r"(\d{3,4})\s*[xX×]\s*(\d{3,4})mm")
DOOR_WIDTH_IN_RE = re.compile(r'(\d{1,3}(?:\.\d+)?)\s*["″]\s*[xX×]\s*(\d{1,3}(?:\.\d+)?)\s*["″]')
# Meters per IFC SI length-unit prefix.
_PREFIX_SCALE = {"MILLI": 0.001, "CENTI": 0.01, "DECI": 0.1,
                 "DECA": 10.0, "HECTO": 100.0, "KILO": 1000.0}
# Door centroid-to-room-polygon distance (m) used to associate a door with the
# rooms it serves when the model has no IfcRelSpaceBoundary data.
DOOR_ASSOC_DIST_M = 0.5


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


def _elem_bbox_dims(elem, scale, settings):
    """(x, y, z) extents in metres of an element's tessellated geometry bbox."""
    try:
        shape = ifcgeom.create_shape(settings, elem)
        v = shape.geometry.verts
        if len(v) < 6:
            return None
        xs = v[0::3]
        ys = v[1::3]
        zs = v[2::3]
        return ((max(xs) - min(xs)) * scale,
                (max(ys) - min(ys)) * scale,
                (max(zs) - min(zs)) * scale)
    except Exception:
        return None


def _structural_sections(els, settings, scale, col_cap=200, other_cap=30):
    """Sample structural element data from storey elements.

    Returns (elements, column_sections, beam_sections, slab_thicknesses).
    ``elements`` is a per-element list (id/name/element_type + section fields)
    that the review engine can judge; columns are sampled up to col_cap (they
    drive the structural rule) while beams/slabs stay at other_cap to bound
    tessellation cost on real buildings.
    """
    elements, col_sec, beam_sec, slab_th = [], [], [], []
    ncol = nbeam = nslab = 0
    for e in els:
        if e.is_a("IfcColumn"):
            if ncol >= col_cap:
                continue
            ncol += 1
            d = _elem_bbox_dims(e, scale, settings)
            if d and 0.05 < min(d[:2]) and max(d[:2]) < 2.0:
                w, dep = sorted((round(d[0], 3), round(d[1], 3)))
                col_sec.append((w, dep))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "column", "section_min_m": w,
                                 "section_max_m": dep})
        elif e.is_a("IfcBeam"):
            if nbeam >= other_cap:
                continue
            nbeam += 1
            d = _elem_bbox_dims(e, scale, settings)
            if d and 0.05 < d[2] < 2.0:
                beam_sec.append((round(d[2], 3), round(min(d[:2]), 3)))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "beam", "depth_m": round(d[2], 3),
                                 "width_m": round(min(d[:2]), 3),
                                 "span_m": round(max(d[0], d[1]), 3)})
        elif e.is_a("IfcSlab"):
            if nslab >= other_cap:
                continue
            nslab += 1
            d = _elem_bbox_dims(e, scale, settings)
            if d and 0.02 < d[2] < 1.0:
                slab_th.append(round(d[2], 3))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "slab", "thickness_m": round(d[2], 3),
                                 "span_m": round(max(d[0], d[1]), 3)})
    return elements, sorted(set(col_sec)), sorted(set(beam_sec)), sorted(set(slab_th))


def _door_shape_info(door, scale):
    """(width_m, centroid_xy) of a door from its tessellated geometry bbox.

    The larger horizontal extent of the world-space bounding box is the door
    width; the centroid is used for door->room association. Returns (None, None)
    on failure so callers can fall back to attribute/name sources.
    """
    try:
        st = ifcgeom.settings()
        st.set(st.USE_WORLD_COORDS, True)
        shape = ifcgeom.create_shape(st, door)
        v = shape.geometry.verts
        if len(v) < 6:
            return None, None
        xs = v[0::3]
        ys = v[1::3]
        w = max(max(xs) - min(xs), max(ys) - min(ys)) * scale
        if not (0.1 <= w <= 5.0):
            w = None
        return w, (sum(xs) / len(xs), sum(ys) / len(ys))
    except Exception:
        return None, None


def _ramp_slope(ramp, scale):
    """Slope (rise/run) of an IfcRamp/IfcRampFlight from its geometry bbox.

    Returns None for non-ramps / degenerate shapes (run ≈ 0 or vertical like a
    stair). Rise is the z-extent; run is the longer horizontal extent.
    """
    try:
        st = ifcgeom.settings()
        st.set(st.USE_WORLD_COORDS, True)
        shape = ifcgeom.create_shape(st, ramp)
        v = shape.geometry.verts
        if len(v) < 6:
            return None
        xs = v[0::3]
        ys = v[1::3]
        zs = v[2::3]
        rise = (max(zs) - min(zs)) * scale
        run = max(max(xs) - min(xs), max(ys) - min(ys)) * scale
        if run <= 0.01:
            return None
        slope = rise / run
        return round(slope, 4) if 0.0 < slope <= 1.0 else None
    except Exception:
        return None


def _door_width_m(door, scale, geom_width=None):
    """Door width in metres, attribute-first.

    Priority: Pset_DoorCommon.OverallWidth -> type-name dimensions (mm, then
    inches) -> geometry bbox. Returns None when unresolvable so the review can
    report "data missing" instead of inventing a value.
    """
    w = None
    for rel in door.IsDefinedBy or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            ps = rel.RelatingPropertyDefinition
            if ps.is_a("IfcPropertySet") and ps.Name == "Pset_DoorCommon":
                for p in ps.HasProperties:
                    if p.Name == "OverallWidth" and p.NominalValue:
                        try:
                            w = float(p.NominalValue.wrappedValue) * scale
                        except (TypeError, ValueError):
                            pass
    if w is None:
        nm = door.Name or ""
        mm = DOOR_WIDTH_RE.search(nm)
        if mm:
            w = int(mm.group(1)) / 1000.0
        else:
            mi = DOOR_WIDTH_IN_RE.search(nm)
            if mi:
                w = float(mi.group(1)) * 0.0254
    if w is None:
        w = geom_width
    return round(w, 3) if w is not None else None


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


def _space_hull(space, settings):
    """(convex_hull_xy, centroid_xy) of a space's tessellated XY projection.

    Coordinates are in model units. Used both for area (convex-hull approx,
    overestimates concave spaces) and for door->room association.
    """
    try:
        shape = ifcgeom.create_shape(settings, space)
        v = shape.geometry.verts
        pts = sorted(set((v[i], v[i + 1]) for i in range(0, len(v), 3)))
        if len(pts) < 3:
            return None, None
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
        return hull, (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    except Exception:
        return None, None


def _hull_area(hull, scale):
    """Area (m²) of a convex hull polygon, scaled from model units to metres."""
    area = 0.0
    for i in range(len(hull)):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % len(hull)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0 * (scale * scale)


def _space_area_m2(space, scale, settings=None):
    if settings is None:
        settings = ifcgeom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
    hull, _ = _space_hull(space, settings)
    return _hull_area(hull, scale) if hull else 0.0


def _point_in_poly(p, poly):
    """Ray-casting point-in-polygon test (XY)."""
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _dist_to_poly(p, poly):
    """0 if inside the polygon, else min distance (model units) to its edges."""
    if _point_in_poly(p, poly):
        return 0.0
    px, py = p
    best = float("inf")
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            d = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        else:
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
            d = ((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2) ** 0.5
        best = min(best, d)
    return best


def _associate_doors(space_geom, door_geom, scale, spaces, space_storey, door_storey):
    """Map each space to the doors that serve it.

    Uses IfcRelSpaceBoundary when the model has them (exact), then complements
    with a geometric proximity test (door centroid within DOOR_ASSOC_DIST_M of a
    room's footprint) for models without boundaries (e.g. Snowdon). Doors are
    only associated to rooms on the same storey. Returns {space_gid: set(door_gid)}.
    """
    assoc = {}
    for s in spaces:
        for b in s.BoundedBy or []:
            el = b.RelatedBuildingElement
            if el and el.is_a("IfcDoor"):
                assoc.setdefault(s.GlobalId, set()).add(el.GlobalId)
    threshold = DOOR_ASSOC_DIST_M / scale
    for gid, (hull, _, _) in space_geom.items():
        if not hull:
            continue
        sg = space_storey.get(gid)
        for dg, (_, centroid) in door_geom.items():
            if not centroid:
                continue
            ds = door_storey.get(dg)
            if ds is not None and sg is not None and ds != sg:
                continue
            if _dist_to_poly(centroid, hull) <= threshold:
                assoc.setdefault(gid, set()).add(dg)
    return assoc


def _compute_travel_distances(space_geom, door_room, door_geom, scale):
    """{space_gid: travel_distance_m} — shortest path from each room to the
    nearest exit room.

    Rooms are graph nodes; an edge connects two rooms that share a door, weighted
    by their centroid distance in metres. Exits come from single-room (exterior)
    doors; for boundary-less models where geometry associates every door with
    several rooms, a door on the building's bounding-box edge is treated as an
    exterior exit. Returns {} when no exit or adjacency is usable.
    """
    centroids = {}
    for gid, (_, _, centroid) in space_geom.items():
        if centroid:
            centroids[gid] = (centroid[0] * scale, centroid[1] * scale)
    if not centroids:
        return {}
    G = nx.Graph()
    G.add_nodes_from(centroids)
    door_rooms = {}
    for sgid, doors in door_room.items():
        for d in doors:
            door_rooms.setdefault(d, []).append(sgid)
    for rooms in door_rooms.values():
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                a, b = rooms[i], rooms[j]
                if a in centroids and b in centroids:
                    dx = centroids[a][0] - centroids[b][0]
                    dy = centroids[a][1] - centroids[b][1]
                    G.add_edge(a, b, weight=(dx * dx + dy * dy) ** 0.5)
    # primary exits: doors that serve exactly one room (exterior/openings)
    exits = {rooms[0] for rooms in door_rooms.values()
             if len(rooms) == 1 and rooms[0] in centroids}
    # fallback exits: doors on the building's bounding-box edge (models whose
    # geometry association binds every door to several rooms, e.g. no boundaries)
    if not exits:
        pts = [c for _, c in door_geom.values() if c]
        if pts:
            xs = [p[0] * scale for p in pts]
            ys = [p[1] * scale for p in pts]
            minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
            edge_tol = 0.5
            for d, (_, c) in door_geom.items():
                if not c:
                    continue
                px, py = c[0] * scale, c[1] * scale
                on_edge = (px - minx <= edge_tol or maxx - px <= edge_tol
                           or py - miny <= edge_tol or maxy - py <= edge_tol)
                if on_edge:
                    for r in door_rooms.get(d, []):
                        if r in centroids:
                            exits.add(r)
    if not exits:
        return {}
    result = {}
    for gid in centroids:
        try:
            lengths = nx.single_source_dijkstra_path_length(G, gid, weight="weight")
            reachable = [lengths[e] for e in exits if e in lengths]
            result[gid] = round(min(reachable), 1) if reachable else None
        except Exception:
            result[gid] = None
    return result


def _classify_room_type(name):
    """Map a space name/reference to a review-room type.

    Returns "Unknown" when nothing matches — we do not guess "Office" for rooms
    whose function is not indicated in the model (honest data policy).
    """
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
    if any(k in n for k in ("office", "办公")):
        return "Office"
    return "Unknown"


def _space_to_room(space, area, ref="", door_widths=None, travel_distance=None, hull=None):
    """Build a review-engine room dict from a real IfcSpace.

    exit_count and door_width_m come from the real doors associated with the
    space. door_widths=None means the model has no usable door data -> both are
    None so the engine reports "data missing"; door_widths=[] is a real room
    with no doors (exit_count 0). travel_distance is the computed egress path
    (m) to the nearest exit room, feeding corridor_length_m. hull (if any) is
    the room's footprint polygon in model units, used to draw a real floor plan.
    """
    name = space.Name or "?"
    rtype = _classify_room_type(f"{ref} {name}")
    if door_widths is None:
        exit_count = None
        door_width = None
    else:
        exit_count = len(door_widths)
        real = [w for w in door_widths if w is not None]
        door_width = max(real) if real else None
    return {
        "id": space.GlobalId or name,
        "name": name,
        "type": rtype,
        "room_area_sqm": round(area, 1),
        "exit_count": exit_count,
        "door_width_m": door_width,
        "has_emergency_light": rtype not in ("Stairwell", "Corridor", "Vestibule"),
        "dist_to_water_m": 5.0,
        "circuit_load_a": 10,
        "outlet_spacing_m": 5.0,
        "corridor_length_m": travel_distance or 0,
        "hull": hull,
    }


def parse_model(m, path, max_floors=None, max_rooms_per_floor=None):
    """Extract a structural report dict from an already-opened IFC model.

    Parameters
    ----------
    m : ifcopenshell model (open)
    path : str|Path — used only for file_name in the report
    max_floors : int | None — keep only the N storeys with the most spaces
    max_rooms_per_floor : int | None — keep only the N largest rooms per storey
    """
    if not IFC_AVAILABLE:
        raise RuntimeError("ifcopenshell is not installed.")
    path = str(path)
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

    # Only compute geometry/doors for storeys and spaces that appear in output.
    kept_storey_gids = {st.GlobalId for st in storeys}

    space_geom = {}
    space_storey = {}
    kept_spaces = []
    for sg, slist in storey_spaces.items():
        if sg not in kept_storey_gids:
            continue
        for sp in slist:
            hull, centroid = _space_hull(sp, geom_settings)
            space_geom[sp.GlobalId] = (hull, _hull_area(hull, scale) if hull else 0.0, centroid)
            space_storey[sp.GlobalId] = sg
            kept_spaces.append(sp)

    door_storey = {e.GlobalId: sg for sg, els in by_storey.items() for e in els if e.is_a("IfcDoor")}
    doors_kept = [d for d in m.by_type("IfcDoor")
                  if door_storey.get(d.GlobalId) in kept_storey_gids
                  or d.GlobalId not in door_storey]
    door_geom = {d.GlobalId: _door_shape_info(d, scale) for d in doors_kept}
    door_meta = {d.GlobalId: _door_width_m(d, scale, door_geom[d.GlobalId][0])
                 for d in doors_kept}

    door_room = _associate_doors(space_geom, door_geom, scale, kept_spaces,
                                 space_storey, door_storey)
    travel = _compute_travel_distances(space_geom, door_room, door_geom, scale)

    floors = []
    for storey in storeys:
        els = by_storey.get(storey.GlobalId, [])
        types = {}
        storey_door_widths = []
        ramp_slopes = []
        for e in els:
            types[e.is_a()] = types.get(e.is_a(), 0) + 1
            if e.is_a("IfcDoor"):
                w = door_meta.get(e.GlobalId)
                if w:
                    storey_door_widths.append(w)
            elif e.is_a("IfcRamp") or e.is_a("IfcRampFlight"):
                s = _ramp_slope(e, scale)
                if s is not None:
                    ramp_slopes.append(s)
        elements, col_sec, beam_sec, slab_th = _structural_sections(els, geom_settings, scale)

        spaces = storey_spaces.get(storey.GlobalId, [])
        sized = sorted(spaces, key=lambda s: -(space_geom.get(s.GlobalId, (None, 0.0))[1]))
        if max_rooms_per_floor:
            sized = sized[:max_rooms_per_floor]
        rooms = []
        for s in sized:
            _sg = space_geom.get(s.GlobalId, (None, 0.0, None))
            area = _sg[1]
            widths = None
            if door_meta:  # model has doors: report real per-room door data
                widths = [door_meta[g] for g in door_room.get(s.GlobalId, set()) if g in door_meta]
            rooms.append(_space_to_room(s, area, ref_map.get(s.GlobalId, ""), widths,
                                        travel.get(s.GlobalId), _sg[0]))

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
                "column_sections": col_sec,
                "beam_sections": beam_sec,
                "slab_thicknesses": slab_th,
                "stairs": types.get("IfcStair", 0),
                "ramps": types.get("IfcRamp", 0) + types.get("IfcRampFlight", 0),
                "ramp_slopes": sorted(ramp_slopes),
                "door_widths_m": sorted(set(storey_door_widths)),
                "door_count": len(storey_door_widths),
            },
            "rooms": rooms,
            "structural_elements": elements,
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
            "structural_elements": f.get("structural_elements", []),
        })
    all_ramp_slopes = [s for f in struct.get("floors", [])
                       for s in (f.get("structure") or {}).get("ramp_slopes", [])]
    bp = {
        "total_floors": struct.get("storey_count", len(floors)),
        "occupancy_type": "office",
        "ground_floor_exit_width_m": 2.4,
        "fire_pool_volume_m3": 160.0,
        "transformer_capacity_kw": 650.0,
        "emergency_power_duration_min": 60.0,
    }
    if all_ramp_slopes:
        bp["max_ramp_slope"] = max(all_ramp_slopes)
    return {
        "project_name": struct.get("project_name") or "BIM Building",
        "source": "ifc",
        "building_params": bp,
        "floors": floors,
    }
