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
    are in the thousands+. If the declared unit is mm but the element geometry
    is clearly metre-scale (mixed exports, e.g. Schependomlaan), use metres for
    geometry measurements (storey elevations are normalised separately).
    """
    declared = None
    for ua in m.by_type("IfcUnitAssignment"):
        for u in ua.Units:
            if u.is_a("IfcSIUnit") and u.UnitType == "LENGTHUNIT":
                declared = _PREFIX_SCALE.get(u.Prefix, 1.0)
                break
    if declared is not None and declared < 1.0:
        # cross-check geometry magnitude: are sampled elements plausibly sized at
        # the declared scale, or are they metre-scale despite a mm declaration?
        s = ifcgeom.settings()
        small, checked = 0, 0
        for t in ("IfcSlab", "IfcColumn", "IfcBeam"):
            for e in m.by_type(t)[:3]:
                try:
                    sh = ifcgeom.create_shape(s, e)
                    v = sh.geometry.verts
                    if len(v) < 6:
                        continue
                    dims = [max(v[i::3]) - min(v[i::3]) for i in range(3)]
                    if min(dims) * declared < 0.02:  # implausibly tiny at declared scale
                        small += 1
                    checked += 1
                except Exception:
                    pass
        if checked >= 3 and small >= checked * 0.5:
            return 1.0  # geometry is metre-scale despite the mm declaration
        return declared
    if declared is not None:
        return declared
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


def _plan_element_kind(e):
    t = e.is_a()
    if t in ("IfcWall", "IfcWallStandardCase"):
        return "wall"
    if t == "IfcColumn":
        return "column"
    if t == "IfcBeam":
        return "beam"
    if t in ("IfcSlab", "IfcSlabStandardCase"):
        return "slab"
    if t == "IfcWindow":
        return "window"
    if t == "IfcDoor":
        return "door"
    if t in ("IfcFlowSegment", "IfcPipeSegment"):
        return "pipe"
    if t == "IfcDuctSegment":
        return "duct"
    return None


def _pset_value(e, pset_name, prop_name):
    """Value of a named property inside a named IfcPropertySet (None if absent)."""
    for rel in (e.IsDefinedBy or []):
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pd = rel.RelatingPropertyDefinition
        if pd.is_a("IfcPropertySet") and pd.Name == pset_name:
            for p in pd.HasProperties:
                if p.Name == prop_name and p.NominalValue:
                    try:
                        return p.NominalValue.wrappedValue
                    except Exception:
                        pass
    return None


def _pipe_slope_from_geom(e, settings):
    """Slope (rise/horiz) from a sloped pipe's tessellated geometry — the
    fallback when the model doesn't carry the slope in a property (real IFCs)."""
    try:
        sh = ifcgeom.create_shape(settings, e)
        v = sh.geometry.verts
        pts = [(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 3)]
        if len(pts) < 6:
            return None
        ranges = [max(p[a] for p in pts) - min(p[a] for p in pts) for a in (0, 1, 2)]
        axis = ranges.index(max(ranges))          # dominant axis = pipe length
        lo, hi = min(p[axis] for p in pts), max(p[axis] for p in pts)
        span = max(hi - lo, 1e-9)
        low = [p for p in pts if p[axis] <= lo + span * 0.2]
        high = [p for p in pts if p[axis] >= hi - span * 0.2]
        if not low or not high:
            return None

        def mean(g):
            return (sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g),
                    sum(p[2] for p in g) / len(g))

        lx, ly, lz = mean(low)
        hx, hy, hz = mean(high)
        horiz = ((hx - lx) ** 2 + (hy - ly) ** 2) ** 0.5
        if horiz < 1e-6:
            return None
        return round((hz - lz) / horiz, 4)
    except Exception:
        return None


_PIPE_TYPE_RULES = [
    ("fire", ("fire", "sprinkler", "hydrant", "brand", "消防")),
    ("drainage", ("sanitary", "soil", "waste", "storm", "drain", "afvoer", "riool",
                  "hemelwater", "hwa", "regenwater", "排水", "废水", "污")),
    ("supply", ("domestic", "cold water", "water supply", "waterleiding", "drinkwater",
                "给水", "供水")),
    ("hydronic", ("hydronic", "chilled", "heating", "cooling", "cv", "verwarming",
                  "暖通", "冷冻")),
    ("gas", ("gas", "燃气")),
    ("vent", ("exhaust", "vent", "air", "lucht")),
]


def _classify_pipe_type(e):
    """Classify a real pipe's purpose from its IFC properties.

    Real exports carry the system role in PSet_Revit_Mechanical (System Type /
    System Name) or Pset_PipeSegmentCommon; falls back to the element name.
    Returns one of: fire / drainage / supply / hydronic / gas / vent / unknown.
    """
    text = " ".join(filter(None, [
        _pset_value(e, "PSet_Revit_Mechanical", "System Type"),
        _pset_value(e, "PSet_Revit_Mechanical", "System Name"),
        _pset_value(e, "Pset_PipeSegmentCommon", "FlowDirection"),
        e.Name or "",
    ])).lower()
    for pipe_type, kws in _PIPE_TYPE_RULES:
        if any(k in text for k in kws):
            return pipe_type
    return "unknown"


def _any_prop_value(e, prop_name):
    """Value of a property searched by name across all the element's Psets."""
    for rel in (e.IsDefinedBy or []):
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pd = rel.RelatingPropertyDefinition
        if pd.is_a("IfcPropertySet"):
            for p in pd.HasProperties:
                if p.Name == prop_name and p.NominalValue:
                    try:
                        return p.NominalValue.wrappedValue
                    except Exception:
                        pass
    return None


def _pipe_data(e, scale, settings):
    """Real pipe data for a contained IfcFlowSegment: type/diameter/slope from
    ArchCheckPipeParams (Pset), geometry bbox as fallback for diameter/length,
    geometry rise/horiz as fallback for slope."""
    pipe_type = _pset_value(e, "ArchCheckPipeParams", "pipe_type") or _classify_pipe_type(e)
    diameter = _pset_value(e, "ArchCheckPipeParams", "diameter_m")
    slope = _pset_value(e, "ArchCheckPipeParams", "slope")
    length = None
    d = _elem_bbox_dims(e, scale, settings)
    if d:
        dims = sorted(d)
        length = round(dims[2], 3)
        if diameter is None:
            diameter = round(dims[0], 3)
    if diameter is not None:
        diameter = round(float(diameter), 3)
    if slope is None:
        # real IFCs often carry slope in a property (e.g. PSet_Revit_Constraints.Slope)
        _real = _any_prop_value(e, "Slope")
        try:
            _real = float(_real)
            if not (0.0 <= _real <= 1.0):   # reject corrupt/unit-mismatched values
                _real = None
        except (TypeError, ValueError):
            _real = None
        slope = _real if _real is not None else _pipe_slope_from_geom(e, settings)
    if slope is not None:
        slope = round(float(slope), 3)
    return {"name": e.Name or e.GlobalId, "pipe_type": pipe_type,
            "diameter_m": diameter, "slope": slope, "length_m": length}


def _duct_data(e, scale, settings):
    """Real HVAC duct data: cross-section + clear net height from
    ArchCheckDuctParams (Pset), length from geometry bbox."""
    width = _pset_value(e, "ArchCheckDuctParams", "duct_width_m")
    height = _pset_value(e, "ArchCheckDuctParams", "duct_height_m")
    net = _pset_value(e, "ArchCheckDuctParams", "net_height_m")
    length = None
    d = _elem_bbox_dims(e, scale, settings)
    if d:
        length = round(max(d), 3)
    return {"name": e.Name or e.GlobalId,
            "duct_width_m": round(float(width), 3) if width is not None else None,
            "duct_height_m": round(float(height), 3) if height is not None else None,
            "net_height_m": round(float(net), 3) if net is not None else None,
            "length_m": length}


def _electrical_equip_kind(e):
    """Classify a real electrical element (any schema) as lighting / socket /
    distribution, from ArchCheckEEEEquip or from type + name keywords. IfcFlowController
    is NOT enough for "distribution" (it covers valves/dampers) — require a name hint."""
    et = _pset_value(e, "ArchCheckEEEEquip", "equipment_type")
    if et:
        return et
    nm = (e.Name or "").lower()
    t = e.is_a()
    if any(k in nm for k in ("light", "lamp", "pendant", "sconce", "downlight", "应急", "筒灯", "灯具")):
        return "lighting"
    if any(k in nm for k in ("receptacle", "outlet", "socket", "插座")):
        return "socket"
    if t == "IfcElectricDistributionBoard" or \
       any(k in nm for k in ("panel", "breaker", "配电", "电箱", "alarm control")):
        return "distribution"
    return None


def _electrical_equipment(els, room_type_map):
    """Real electrical equipment elements (lighting / socket / distribution)
    with only the params relevant to their type (so rules skip non-matching
    elements instead of reporting data-missing). Works on IFC2X3 too — real
    exports carry lights/panels as IfcFlowTerminal / IfcFlowController and the
    info lives in the element name (e.g. "M_Sconce Light - 100W - 120V")."""
    out = []
    for e in els:
        if not (e.is_a("IfcElectricAppliance") or e.is_a("IfcLightFixture")
                or e.is_a("IfcElectricDistributionBoard") or e.is_a("IfcFlowTerminal")
                or e.is_a("IfcFlowController")):
            continue
        et = _electrical_equip_kind(e)
        if not et:
            continue
        room = _pset_value(e, "ArchCheckEEEEquip", "room_ref") or ""
        d = {"name": e.Name or e.GlobalId, "equipment_type": et,
             "room": room, "room_type": room_type_map.get(room, "")}
        nm = (e.Name or "").lower()
        if et == "lighting":
            d["has_emergency"] = _pset_value(e, "ArchCheckEEEEquip", "has_emergency")
            if d["has_emergency"] is None:
                d["has_emergency"] = True if ("emergency" in nm or "应急" in nm) else None
            d["power_w"] = _pset_value(e, "ArchCheckEEEEquip", "power_w")
            if d["power_w"] is None:
                m = re.search(r"(\d+(?:\.\d+)?)\s*w\b", nm)
                if m:
                    d["power_w"] = float(m.group(1))
        elif et == "socket":
            d["outlet_spacing_m"] = _pset_value(e, "ArchCheckEEEEquip", "outlet_spacing_m")
        elif et == "distribution":
            d["circuit_load_a"] = _pset_value(e, "ArchCheckEEEEquip", "circuit_load_a")
            d["dist_to_water_m"] = _pset_value(e, "ArchCheckEEEEquip", "dist_to_water_m")
        out.append(d)
    return out


def _pipe_segment(e, settings):
    """((x0, y0), (x1, y1)) horizontal endpoints of a pipe, from geometry."""
    try:
        sh = ifcgeom.create_shape(settings, e)
        v = sh.geometry.verts
        pts = [(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 3)]
        if len(pts) < 6:
            return None
        ranges = [max(p[a] for p in pts) - min(p[a] for p in pts) for a in (0, 1, 2)]
        ax = ranges.index(max(ranges))
        lo, hi = min(p[ax] for p in pts), max(p[ax] for p in pts)
        span = max(hi - lo, 1e-9)
        low = [p for p in pts if p[ax] <= lo + span * 0.2]
        high = [p for p in pts if p[ax] >= hi - span * 0.2]
        if not low or not high:
            return None
        return ((sum(p[0] for p in low) / len(low), sum(p[1] for p in low) / len(low)),
                (sum(p[0] for p in high) / len(high), sum(p[1] for p in high) / len(high)))
    except Exception:
        return None


def _equip_centroid(e, settings):
    """(name, x, y, z, r) centroid + effective horizontal half-extent of an
    electrical equipment element (world coords, r ≈ min horizontal half-size)."""
    try:
        sh = ifcgeom.create_shape(settings, e)
        v = sh.geometry.verts
        xs = v[0::3]; ys = v[1::3]; zs = v[2::3]
        r = min(max(xs) - min(xs), max(ys) - min(ys)) / 2
        return {"name": e.Name or "equip",
                "x": (min(xs) + max(xs)) / 2, "y": (min(ys) + max(ys)) / 2,
                "z": (min(zs) + max(zs)) / 2, "r": r}
    except Exception:
        return None


def _dist_pt_seg(p, a, b):
    """Horizontal distance from point p to segment a-b."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _elem_world_bbox(elem, settings):
    """(x0, y0, x1, y1, z0, z1) world-space bbox in model units (None on failure)."""
    try:
        sh = ifcgeom.create_shape(settings, elem)
        v = sh.geometry.verts
        if len(v) < 6:
            return None
        xs = v[0::3]; ys = v[1::3]; zs = v[2::3]
        return (min(xs), min(ys), max(xs), max(ys), min(zs), max(zs))
    except Exception:
        return None


def _point_in_mesh(px, py, pz, verts, faces):
    """Ray-cast point-in-polyhedron (ray along +z, Möller-Trumbore). True if the
    point is strictly inside a closed triangle mesh."""
    inside = False
    n = len(faces)
    for i in range(0, n, 3):
        a, b, c = faces[i], faces[i + 1], faces[i + 2]
        v0x, v0y, v0z = verts[a * 3], verts[a * 3 + 1], verts[a * 3 + 2]
        v1x, v1y, v1z = verts[b * 3], verts[b * 3 + 1], verts[b * 3 + 2]
        v2x, v2y, v2z = verts[c * 3], verts[c * 3 + 1], verts[c * 3 + 2]
        e1x, e1y, e1z = v1x - v0x, v1y - v0y, v1z - v0z
        e2x, e2y, e2z = v2x - v0x, v2y - v0y, v2z - v0z
        # h = cross(dir=(0,0,1), e2)
        hx, hy = -e2y, e2x
        det = e1x * hx + e1y * hy                      # dot(e1, h)
        if abs(det) < 1e-12:
            continue
        inv = 1.0 / det
        sx, sy, sz = px - v0x, py - v0y, pz - v0z
        u = inv * (sx * hx + sy * hy)
        if u < 0.0 or u > 1.0:
            continue
        # q = cross(s, e1)
        qx, qy, qz = sy * e1z - sz * e1y, sz * e1x - sx * e1z, sx * e1y - sy * e1x
        v = inv * qz                                  # dot(q, dir=(0,0,1))
        if v < 0.0 or u + v > 1.0:
            continue
        t = inv * (qx * e2x + qy * e2y + qz * e2z)
        if t > 0.0:
            inside = not inside
    return inside


def _detect_clashes(els, settings, margin=0.05):
    """Cross-discipline clash pre-check between MEP (pipe/duct) and structure
    (beam/slab/wall). bbox overlap (depth > margin) produces candidates; each is
    then CONFIRMED by point-in-mesh (any MEP vertex strictly inside the solid).
    Columns are excluded (pipes commonly run alongside them). Returns
    [{mep, vs, type, depth, confirmed}]."""
    mep = [e for e in els if e.is_a("IfcFlowSegment") or e.is_a("IfcDuctSegment")]
    solid = [e for e in els
             if e.is_a("IfcBeam") or e.is_a("IfcSlab") or e.is_a("IfcWall") or e.is_a("IfcWallStandardCase")]
    out = []
    for a in mep:
        ba = _elem_world_bbox(a, settings)
        if not ba:
            continue
        for b in solid:
            bb = _elem_world_bbox(b, settings)
            if not bb:
                continue
            ox = min(ba[2], bb[2]) - max(ba[0], bb[0])
            oy = min(ba[3], bb[3]) - max(ba[1], bb[1])
            oz = min(ba[5], bb[5]) - max(ba[4], bb[4])
            if ox > margin and oy > margin and oz > margin:
                out.append({"mep": a.Name or "?", "vs": b.Name or "?",
                            "type": b.is_a(), "depth": round(min(ox, oy, oz), 2),
                            "confirmed": _confirm_clash(a, b, settings)})
    return out


def _confirm_clash(a, b, settings):
    """True if any of MEP element a's mesh vertices is strictly inside solid b."""
    try:
        sha = ifcgeom.create_shape(settings, a)
        v = sha.geometry.verts
        shb = ifcgeom.create_shape(settings, b)
        vb = shb.geometry.verts
        fb = shb.geometry.faces
        if len(fb) < 3:
            return False
        for i in range(0, len(v), 3):
            if _point_in_mesh(v[i], v[i + 1], v[i + 2], vb, fb):
                return True
    except Exception:
        return False
    return False


def _plan_elements(els, settings, cap=150):
    """Footprint geometry of physical elements (walls/columns/windows/...) for
    drawing a data-driven plan/3D view. Same coordinate frame as room hulls
    (model units, world coords). Bounded by ``cap`` per storey."""
    out = []
    for e in els:
        kind = _plan_element_kind(e)
        if not kind or len(out) >= cap:
            continue
        b = _elem_world_bbox(e, settings)
        if not b:
            continue
        x0, y0, x1, y1, z0, z1 = b
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6 or z1 - z0 < 1e-6:
            continue
        out.append({"kind": kind, "name": e.Name or "",
                    "bbox": [round(v, 2) for v in b]})
    return out


def _brep_xy_area(item, scale):
    """XY bounding-rectangle area (m²) of an IfcFacetedBrep box (None if not a box)."""
    try:
        shell = item.Outer.CfsFaces
        pts = []
        for face in shell:
            for bound in face.Bounds:
                for p in bound.Bound.Polygon:
                    c = p.Coordinates
                    pts.append((c[0], c[1]))
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (max(xs) - min(xs)) * (max(ys) - min(ys)) * scale * scale
    except Exception:
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


def _elem_material(e):
    """Material name of an element (None if absent). Handles IfcMaterial,
    IfcMaterialLayerSetUsage (first layer) and IfcMaterialList associations."""
    for rel in (e.HasAssociations or []):
        if not rel.is_a("IfcRelAssociatesMaterial"):
            continue
        mr = rel.RelatingMaterial
        if mr.is_a("IfcMaterial"):
            return mr.Name
        if mr.is_a("IfcMaterialLayerSetUsage"):
            mls = mr.ForLayerSet
            if mls and mls.MaterialLayers:
                for l in mls.MaterialLayers:
                    if l.Material and l.Material.Name:
                        return l.Material.Name
        if mr.is_a("IfcMaterialList") and mr.Materials:
            return mr.Materials[0].Name
    return None


def _material_volumes(elements):
    """{material: total volume m³} over structural elements, 'unknown' for None."""
    out = {}
    for e in elements:
        mt = e.get("material") or "unknown"
        out[mt] = out.get(mt, 0) + (e.get("volume_m3") or 0)
    return {k: round(v, 2) for k, v in out.items()}


def _qty_by_type(elements):
    """{element_type: {count, volume_m3}} over structural elements."""
    out = {}
    for e in elements:
        t = e.get("element_type", "?")
        out.setdefault(t, {"count": 0, "volume_m3": 0.0})
        out[t]["count"] += 1
        out[t]["volume_m3"] += (e.get("volume_m3") or 0)
    return {k: {"count": v["count"], "volume_m3": round(v["volume_m3"], 2)}
            for k, v in out.items()}


def _elem_volume(elem, settings, scale):
    """Volume (m³) of a closed solid element from its tessellated mesh, via the
    signed-tetrahedron (divergence-theorem) formula. None if not computable."""
    try:
        sh = ifcgeom.create_shape(settings, elem)
        v = sh.geometry.verts
        f = sh.geometry.faces
        if len(f) < 3:
            return None
        vol = 0.0
        for i in range(0, len(f), 3):
            a, b, c = f[i], f[i + 1], f[i + 2]
            ax, ay, az = v[a * 3], v[a * 3 + 1], v[a * 3 + 2]
            bx, by, bz = v[b * 3], v[b * 3 + 1], v[b * 3 + 2]
            cx, cy, cz = v[c * 3], v[c * 3 + 1], v[c * 3 + 2]
            vol += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
        vol = abs(vol) / 6.0 * (scale ** 3)
        return round(vol, 4)
    except Exception:
        return None


def _structural_sections(els, settings, scale, col_cap=200, other_cap=30):
    """Sample structural element data from storey elements.

    Returns (elements, column_sections, beam_sections, slab_thicknesses,
    unit_suspicious). ``elements`` is a per-element list (id/name/element_type +
    section fields) that the review engine can judge; columns are sampled up to
    col_cap while beams/slabs stay at other_cap to bound tessellation cost.
    ``unit_suspicious`` counts column/beam/slab elements whose scaled dimensions
    are implausibly small (< 0.02 m) — a sign of a unit-magnitude mismatch in
    the source model — so they are not silently dropped.
    """
    elements, col_sec, beam_sec, slab_th = [], [], [], []
    ncol = nbeam = nslab = 0
    unit_suspicious = 0
    for e in els:
        if e.is_a("IfcColumn"):
            if ncol >= col_cap:
                continue
            ncol += 1
            d = _elem_bbox_dims(e, scale, settings)
            if d and min(d) < 0.02:
                unit_suspicious += 1
                continue
            if d and 0.05 < min(d[:2]) and max(d[:2]) < 2.0:
                w, dep = sorted((round(d[0], 3), round(d[1], 3)))
                col_sec.append((w, dep))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "column", "section_min_m": w,
                                 "section_max_m": dep,
                                 "volume_m3": _elem_volume(e, settings, scale),
                                 "material": _elem_material(e)})
        elif e.is_a("IfcBeam"):
            if nbeam >= other_cap:
                continue
            nbeam += 1
            d = _elem_bbox_dims(e, scale, settings)
            if d and min(d) < 0.02:
                unit_suspicious += 1
                continue
            if d and 0.05 < d[2] < 2.0:
                beam_sec.append((round(d[2], 3), round(min(d[:2]), 3)))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "beam", "depth_m": round(d[2], 3),
                                 "width_m": round(min(d[:2]), 3),
                                 "span_m": round(max(d[0], d[1]), 3),
                                 "volume_m3": _elem_volume(e, settings, scale),
                                 "material": _elem_material(e)})
        elif e.is_a("IfcSlab"):
            if nslab >= other_cap:
                continue
            nslab += 1
            d = _elem_bbox_dims(e, scale, settings)
            if d and min(d) < 0.02:
                unit_suspicious += 1
                continue
            if d and 0.02 < d[2] < 1.0:
                slab_th.append(round(d[2], 3))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "slab", "thickness_m": round(d[2], 3),
                                 "span_m": round(max(d[0], d[1]), 3),
                                 "volume_m3": _elem_volume(e, settings, scale),
                                 "material": _elem_material(e)})
    return elements, sorted(set(col_sec)), sorted(set(beam_sec)), sorted(set(slab_th)), unit_suspicious


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
                        else:
                            a = _brep_xy_area(it, scale)
                            if a:
                                best = max(best, a)
    return round(best, 1)


def _space_bounding_box(space):
    """(x_dim, y_dim) of a space's IfcBoundingBox in model units (None if absent)."""
    try:
        for rep in (space.Representation.Representations or []) if space.Representation else []:
            for it in (rep.Items or []):
                if it.is_a("IfcBoundingBox"):
                    return float(it.XDim), float(it.YDim)
    except Exception:
        pass
    return None


def _space_hull(space, settings):
    """(convex_hull_xy, centroid_xy, precise_area_units) of a space's tessellated
    XY projection. Coordinates in model units. precise_area_units is the exact
    2D outline area (positive-signed projected triangles — handles concave rooms,
    which the convex hull overestimates), or None when the mesh has no faces.
    Spaces without any tessellatable geometry fall back to their IfcBoundingBox
    area; if there is no geometry at all, area_units is None (area unknown)."""
    try:
        shape = ifcgeom.create_shape(settings, space)
        v = shape.geometry.verts
        f = shape.geometry.faces
        pts = sorted(set((v[i], v[i + 1]) for i in range(0, len(v), 3)))
        if len(pts) < 3:
            bb = _space_bounding_box(space)
            return None, None, (bb[0] * bb[1]) if bb else None, bool(bb)
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
        centroid = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        area_units = None
        if len(f) >= 3:
            pos = 0.0
            for i in range(0, len(f), 3):
                a, b, c = f[i], f[i + 1], f[i + 2]
                ax, ay = v[a * 3], v[a * 3 + 1]
                bx, by = v[b * 3], v[b * 3 + 1]
                cx, cy = v[c * 3], v[c * 3 + 1]
                ar = ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2.0
                if ar > 0:
                    pos += ar
            if pos > 0:
                area_units = pos
        return hull, centroid, area_units, False
    except Exception:
        bb = _space_bounding_box(space)
        return None, None, (bb[0] * bb[1]) if bb else None, bool(bb)


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
    hull, _, _, _ = _space_hull(space, settings)
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
    # electrical params: real values when the model declares them
    # (ArchCheckEEEParams), otherwise honest defaults the user can fill in
    # (the editor marks these 🟠 默认·待填写 vs 🟢 来自模型).
    light = _pset_value(space, "ArchCheckEEEParams", "has_emergency_light")
    water = _pset_value(space, "ArchCheckEEEParams", "dist_to_water_m")
    circuit = _pset_value(space, "ArchCheckEEEParams", "circuit_load_a")
    outlet = _pset_value(space, "ArchCheckEEEParams", "outlet_spacing_m")
    eee_src = "model" if (light is not None or water is not None) else "default"
    return {
        "id": space.GlobalId or name,
        "name": name,
        "type": rtype,
        "room_area_sqm": round(area, 1) if area is not None else None,
        "exit_count": exit_count,
        "door_width_m": door_width,
        "has_emergency_light": bool(light) if light is not None
            else (rtype not in ("Stairwell", "Corridor", "Vestibule")),
        "dist_to_water_m": float(water) if water is not None else 5.0,
        "circuit_load_a": float(circuit) if circuit is not None else 10,
        "outlet_spacing_m": float(outlet) if outlet is not None else 5.0,
        "eee_src": eee_src,
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
    # mixed-unit models (e.g. Schependomlaan): geometry is metre-scale but storey
    # elevations are in mm — normalise elevations separately for display / z-assignment.
    elev_scale = scale
    try:
        raw_elevs = [st.Elevation or 0.0 for st in m.by_type("IfcBuildingStorey")]
        if scale == 1.0 and raw_elevs and max(abs(e) for e in raw_elevs) > 500:
            elev_scale = 0.001
    except Exception:
        pass
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

    # Structural fallback: real models often don't contain columns/beams/slabs
    # in the storey's IfcRelContainedInSpatialStructure. Assign uncontained
    # structural elements to a storey by their world z-centre so STR rules have
    # something to judge (e.g. Schependomlaan: 174 beams + 279 slabs uncontained).
    structural_fallback = {}
    if storeys:
        elevs = [(st.Elevation or 0.0) * elev_scale for st in storeys]
        # only skip elements already attached to a kept storey; real models
        # (e.g. Schependomlaan) contain structural elements under the building
        # or site instead of the storey, so those still need z-assignment.
        kept_els_gids = {e.GlobalId for st in storeys for e in by_storey.get(st.GlobalId, [])}
        for e in list(m.by_type("IfcColumn")) + list(m.by_type("IfcBeam")) + list(m.by_type("IfcSlab")):
            if e.GlobalId in kept_els_gids:
                continue
            b = _elem_world_bbox(e, geom_settings)
            if not b:
                continue
            zc = (b[4] + b[5]) / 2
            idx = 0
            for i, ev in enumerate(elevs):
                if zc >= ev:
                    idx = i
            structural_fallback.setdefault(storeys[idx].GlobalId, []).append(e)

    # Electrical fallback: same containment reality — lights/panels/terminals are
    # often under the building/site, not a storey. Assign uncontained electrical
    # elements to a storey by their world z-centre.
    electrical_fallback = {}
    if storeys:
        kept_els_gids2 = {e.GlobalId for st in storeys for e in by_storey.get(st.GlobalId, [])}
        # IfcDistributionFlowElement covers terminals/controllers/appliances in
        # both schemas (IFC4-only type names can't be used with by_type).
        for e in m.by_type("IfcDistributionFlowElement"):
            if e.GlobalId in kept_els_gids2 or not _electrical_equip_kind(e):
                continue
            b = _elem_world_bbox(e, geom_settings)
            if not b:
                continue
            zc = (b[4] + b[5]) / 2
            idx = 0
            for i, ev in enumerate(elevs):
                if zc >= ev:
                    idx = i
            electrical_fallback.setdefault(storeys[idx].GlobalId, []).append(e)

    space_geom = {}
    space_storey = {}
    kept_spaces = []
    for sg, slist in storey_spaces.items():
        if sg not in kept_storey_gids:
            continue
        for sp in slist:
            hull, centroid, area_units, is_bbox = _space_hull(sp, geom_settings)
            if area_units:
                # bounding-box spaces are mm-scale in mixed models (like storey
                # elevations) while solid geometry is metre-scale
                _ascale = elev_scale if is_bbox else scale
                area = round(area_units * _ascale * _ascale, 1)
            elif hull:
                area = _hull_area(hull, scale)
            else:
                area = None  # no geometry -> area unknown (don't fake 0)
            space_geom[sp.GlobalId] = (hull, area, centroid)
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

    # Only extract per-element footprint geometry for affordable models (the
    # plan/3D detail render); huge models skip it to keep parsing fast.
    total_phys = sum(len(v) for v in by_storey.values())
    extract_plan = total_phys <= 600

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
        elements, col_sec, beam_sec, slab_th, unit_suspicious = _structural_sections(
            els + structural_fallback.get(storey.GlobalId, []), geom_settings, scale)
        plan_elems = _plan_elements(els, geom_settings) if extract_plan else []
        clashes = _detect_clashes(els, geom_settings) if extract_plan else []
        pipe_elems = [e for e in els if e.is_a("IfcFlowSegment") and not e.is_a("IfcDuctSegment")]
        pipes = [_pipe_data(e, scale, geom_settings) for e in pipe_elems]
        ducts = [_duct_data(e, scale, geom_settings) for e in els if e.is_a("IfcDuctSegment")]
        equip = [q for q in (_equip_centroid(e, geom_settings) for e in els
                             if e.is_a("IfcElectricAppliance") or e.is_a("IfcLightFixture")) if q]
        room_type_map = {}
        for _sp in storey_spaces.get(storey.GlobalId, []):
            _ref = ref_map.get(_sp.GlobalId) or _sp.Name or ""
            room_type_map[_ref] = _classify_room_type(f"{_ref} {_sp.Name or ''}")
        electrical = _electrical_equipment(els + electrical_fallback.get(storey.GlobalId, []),
                                           room_type_map)
        if equip:
            for e, pipe in zip(pipe_elems, pipes):
                seg = _pipe_segment(e, geom_settings)
                if seg:
                    pr = (pipe.get("diameter_m") or 0.0) / 2
                    clear = min(_dist_pt_seg((q["x"], q["y"]), seg[0], seg[1]) - pr - q.get("r", 0.0)
                                for q in equip)
                    pipe["min_clearance_m"] = round(max(clear, 0.0), 3)

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
            "elevation_m": round((storey.Elevation or 0.0) * elev_scale, 2),
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
                "unit_suspicious_struct": unit_suspicious,
                "structural_volume_m3": round(sum((e.get("volume_m3") or 0) for e in elements), 3),
                "material_volumes": _material_volumes(elements),
                "qty_by_type": _qty_by_type(elements),
            },
            "rooms": rooms,
            "structural_elements": elements,
            "plan_elements": plan_elems,
            "clashes": clashes,
            "pipes": pipes,
            "ducts": ducts,
            "electrical_equipment": equip,
            "electrical_elements": electrical,
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
            "plan_elements": f.get("plan_elements", []),
            "clashes": f.get("clashes", []),
            "pipes": f.get("pipes", []),
            "ducts": f.get("ducts", []),
            "electrical_equipment": f.get("electrical_equipment", []),
            "electrical_elements": f.get("electrical_elements", []),
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
