"""BIM data extraction — turn an opened IFC model into a structural report + review-ready data.

Pure extraction: no model-quality checks here (see bim/qa_validator.py). Real-world
IFC files vary a lot; this extracts structural facts (storeys, footprint, door
widths, element counts) and, when the model contains them, real spaces/rooms with
geometry-derived areas. Electrical / fire-zone parameters are usually not in
architectural IFCs, so those are defaulted and left for the app's parameter editor.

Units: the model's length unit is read from the IFC (many exports use mm, others
use m) and every conversion is scaled accordingly.
"""
import math
import re
from pathlib import Path

import networkx as nx
import numpy as np

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


def _by_type(m, type_name):
    """m.by_type() that returns [] when the entity doesn't exist in the file's
    schema (e.g. IfcPipeSegment / IfcDuctSegment are IFC4-only; IFC2X3 models
    carry them as generic IfcFlowSegment)."""
    try:
        return m.by_type(type_name)
    except Exception:
        return []


def _declared_length_scale(m):
    """Meters per unit declared by the model's length unit (0.001 mm / 1.0 m),
    or None if the model declares no length unit. Handles both SI units
    (mm/m) and conversion-based units (imperial FOOT/INCH, e.g. Revit models
    with 1.0 ft floor thickness)."""
    for ua in m.by_type("IfcUnitAssignment"):
        for u in ua.Units:
            if u.is_a("IfcSIUnit") and u.UnitType == "LENGTHUNIT":
                return _PREFIX_SCALE.get(u.Prefix, 1.0)
    # Non-SI length unit (FOOT / INCH / ...): let ifcopenshell resolve the factor.
    try:
        import ifcopenshell.util.unit as _uu
        return _uu.calculate_unit_scale(m)
    except Exception:
        return None


def _length_scale(m):
    """Meters per model length unit (1.0 for m, 0.001 for mm).

    If the model declares no length unit, infer it from the storey elevations:
    a real building's storey elevations land in ~0.5-500 m, whereas mm models
    are in the thousands+. If the declared unit is mm but the element geometry
    is clearly metre-scale (mixed exports, e.g. Schependomlaan), use metres for
    geometry measurements (storey elevations are normalised separately).
    """
    declared = _declared_length_scale(m)
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


# Plausible dimension ranges (metres) for common MEP / structural element sizes.
# Used as a sanity guard when inferring units — anything outside is treated as
# a unit-mismatch red flag.
_PLAUSIBLE_SIZES = {
    "pipe_diameter": (0.01, 2.0),      # 1 cm to 2 m
    "duct_side":     (0.05, 4.0),      # 5 cm to 4 m
    "wall_thickness":(0.05, 1.5),      # 5 cm to 1.5 m
    "slab_thickness":(0.08, 1.0),      # 8 cm to 1 m
    "column_width":  (0.1, 3.0),       # 10 cm to 3 m
}


def _is_plausible(value_m, size_key):
    """Whether a dimension in metres falls in a plausible real-world range."""
    if value_m is None or value_m <= 0:
        return False
    lo, hi = _PLAUSIBLE_SIZES.get(size_key, (0.001, 100.0))
    return lo <= value_m <= hi


def _is_duct_segment(e):
    """True if e is a duct segment. IFC4 has IfcDuctSegment; IFC2X3 carries
    ducts as generic IfcFlowSegment, so also check name hints."""
    if e.is_a("IfcDuctSegment"):
        return True
    if not e.is_a("IfcFlowSegment"):
        return False
    nm = (e.Name or "").lower()
    return any(k in nm for k in ("duct", "air", "风管", "送风", "回风", "排风", "送排"))


def _is_pipe_fitting(e):
    """True if e is a pipe fitting. IFC4 splits IfcPipeFitting / IfcDuctFitting;
    IFC2X3 has only generic IfcFlowFitting, so classify by name."""
    if e.is_a("IfcPipeFitting"):
        return True
    if e.is_a("IfcDuctFitting"):
        return False
    if e.is_a("IfcFlowFitting"):
        # IFC2X3: all flow fittings are pipe fittings unless clearly a duct part
        nm = (e.Name or "").lower()
        if any(k in nm for k in ("duct", "damper", "silencer", "风管", "阀")):
            return False
        return True
    return False


def _is_pipe_segment(e):
    """True if e is a pipe segment (as opposed to a duct)."""
    if e.is_a("IfcDuctSegment"):
        return False
    if not e.is_a("IfcFlowSegment"):
        return False
    return True


def _infer_profile_scale(m, world_scale, declared_scale, settings, n_samples=20):
    """Infer the unit scale of Qto / ProfileDef data by sampling and comparing
    against tessellated geometry bbox (which uses world_scale).

    Strategy
    --------
    1. Sample up to ``n_samples`` pipes and ducts that have both Qto/Profile
       data AND a tessellated geometry bbox.
    2. For each, try converting with declared_scale and with world_scale.
    3. Vote: which scale brings Qto/Profile closer to the bbox (within 30%)?
    4. Only commit to a global scale if the winning side leads by a clear
       margin (>= 2:1 ratio) AND there are enough samples (>= 5).
    5. Otherwise return ``declared_scale`` as the conservative default and a
       confidence flag of ``False`` so callers can fall back to per-element
       cross-checking.

    Returns
    -------
    (profile_scale, confidence, diagnostics_dict)
        profile_scale : float — metres per Qto/profile-definition unit
        confidence : bool — whether we trust the global scale
        diagnostics : dict — what we saw (n_A, n_B, n_tie, n_samples, reason)
    """
    if declared_scale == world_scale:
        return declared_scale, True, {"reason": "declared == world"}

    geom_s = ifcgeom.settings()
    geom_s.set(geom_s.USE_WORLD_COORDS, True)

    def _sample(elements, qto_set, qto_prop, size_key,
                profile_fn=None, profile_scale_arg=None):
        """Return (n_declared_hits, n_world_hits, n_ties, n_usable)."""
        a_hits = b_hits = ties = usable = 0
        for e in elements[:n_samples * 3]:  # over-sample, we filter below
            if usable >= n_samples:
                break
            # bbox reference (ground truth in world units)
            d = _elem_bbox_dims(e, world_scale, geom_s)
            if not d:
                continue
            bbox_ref = min(d) if size_key in ("pipe_diameter",) else sorted(d)[1]
            if bbox_ref is None or bbox_ref <= 0:
                continue
            # Try Qto first
            raw = _qto_value(e, qto_set, qto_prop)
            source = "qto"
            # Fall back to profile def for pipes
            if raw is None and profile_fn:
                raw = profile_fn(e, 1.0)  # raw units (not yet scaled)
                source = "profile"
            if raw is None or raw <= 0:
                continue
            v_decl = raw * declared_scale
            v_world = raw * world_scale
            # Plausibility filter — crazy values can't be right
            p_decl = _is_plausible(v_decl, size_key)
            p_world = _is_plausible(v_world, size_key)
            if not p_decl and not p_world:
                continue  # both implausible — skip
            err_decl = abs(v_decl - bbox_ref) / bbox_ref
            err_world = abs(v_world - bbox_ref) / bbox_ref
            TOL = 0.3
            if err_decl < TOL and err_world < TOL:
                ties += 1
            elif err_decl < TOL:
                a_hits += 1
            elif err_world < TOL:
                b_hits += 1
            else:
                # Neither matches bbox well — element geometry might be weird.
                # Use plausibility as a tiebreaker.
                if p_decl and not p_world:
                    a_hits += 1
                elif p_world and not p_decl:
                    b_hits += 1
                else:
                    continue
            usable += 1
        return a_hits, b_hits, ties, usable

    total_a = total_b = total_ties = total_usable = 0

    # Pipe samples: diameter (OuterDiameter from Qto, or Radius*2 from profile)
    pipes = list(_by_type(m, "IfcPipeSegment"))
    if not pipes:
        pipes = [e for e in _by_type(m, "IfcFlowSegment")
                 if not e.is_a("IfcDuctSegment")]
    a, b, t, u = _sample(pipes, "Qto_PipeSegmentBaseQuantities",
                         "OuterDiameter", "pipe_diameter",
                         profile_fn=lambda e, s: _pipe_profile_diameter(e, s))
    total_a += a; total_b += b; total_ties += t; total_usable += u

    # Duct samples: width from Qto
    ducts = list(_by_type(m, "IfcDuctSegment"))
    if ducts:
        a, b, t, u = _sample(ducts, "Qto_DuctSegmentBaseQuantities",
                             "Width", "duct_side")
        total_a += a; total_b += b; total_ties += t; total_usable += u

    diagnostics = {
        "n_declared_hits": total_a,
        "n_world_hits": total_b,
        "n_ties": total_ties,
        "n_usable": total_usable,
    }

    if total_usable < 5:
        diagnostics["reason"] = "too_few_samples"
        return declared_scale, False, diagnostics

    # Clear majority? need >= 2:1 ratio
    if total_a >= total_b * 2 and total_a >= 3:
        diagnostics["reason"] = "declared_wins_2to1"
        return declared_scale, True, diagnostics
    if total_b >= total_a * 2 and total_b >= 3:
        diagnostics["reason"] = "world_wins_2to1"
        return world_scale, True, diagnostics

    diagnostics["reason"] = "ambiguous"
    return declared_scale, False, diagnostics


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
    if t == "IfcRailing":
        return "railing"
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


def _any_pset_value(e, prop_name):
    """Search all property sets on an element for a property by name."""
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


def _qto_value(e, qset_name, quantity_name):
    """Value of a named quantity inside a named IfcElementQuantity, or None."""
    for rel in (e.IsDefinedBy or []):
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pd = rel.RelatingPropertyDefinition
        if not pd.is_a("IfcElementQuantity") or pd.Name != qset_name:
            continue
        for q in pd.Quantities:
            if q.Name != quantity_name:
                continue
            try:
                if q.is_a("IfcQuantityLength"):
                    return q.LengthValue
                if q.is_a("IfcQuantityArea"):
                    return q.AreaValue
                if q.is_a("IfcQuantityVolume"):
                    return q.VolumeValue
                if q.is_a("IfcQuantityCount"):
                    return q.CountValue
                if q.is_a("IfcQuantityWeight"):
                    return q.WeightValue
            except Exception:
                pass
    return None


def _elem_material(e):
    """Primary material name of an element (None if absent).

    Handles IfcMaterial, IfcMaterialLayerSet(Usage), IfcMaterialProfileSet,
    IfcMaterialConstituentSet, IfcMaterialList — returns the first usable name.
    """
    for rel in (e.HasAssociations or []):
        if not rel.is_a("IfcRelAssociatesMaterial"):
            continue
        mr = rel.RelatingMaterial
        if mr.is_a("IfcMaterial"):
            return mr.Name
        if mr.is_a("IfcMaterialLayerSet"):
            for l in mr.MaterialLayers:
                if l.Material and l.Material.Name:
                    return l.Material.Name
        if mr.is_a("IfcMaterialLayerSetUsage"):
            mls = mr.ForLayerSet
            if mls and mls.MaterialLayers:
                for l in mls.MaterialLayers:
                    if l.Material and l.Material.Name:
                        return l.Material.Name
        if mr.is_a("IfcMaterialProfileSet"):
            for mp in mr.MaterialProfiles:
                if mp.Material and mp.Material.Name:
                    return mp.Material.Name
        if mr.is_a("IfcMaterialConstituentSet"):
            for mc in mr.MaterialConstituents:
                if mc.Material and mc.Material.Name:
                    return mc.Material.Name
        if mr.is_a("IfcMaterialList") and mr.Materials:
            return mr.Materials[0].Name
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
    ("fire", ("fire", "sprinkler", "hydrant", "fire hydrant", "brand",
              "消防", "喷淋", "消火栓")),
    ("drainage", ("sanitary", "soil", "waste", "storm", "drain", "afvoer",
                  "riool", "hemelwater", "hwa", "regenwater", "lab waste",
                  "condensate", "sewer", "sewage", "asw",
                  "排水", "废水", "污", "雨水", "冷凝", "实验室废水", "污水")),
    ("supply", ("domestic", "cold water", "water supply", "waterleiding",
                "drinkwater", "domestic hot water", "hot water",
                "pwc", "pwh", "circulation",
                "给水", "供水", "生活热水", "热水", "循环")),
    ("hydronic", ("hydronic", "chilled", "heating", "cooling", "cv",
                  "verwarming", "chilled water",
                  "heat flow", "heat return", "hhf", "hhr", "kvk", "frk",
                  "暖通", "冷冻", "空调水", "采暖", "供热")),
    ("gas", ("gas", "燃气", "天然气")),
    ("lab_gas", ("compressed air", "vacuum", "nitrogen", "oxygen", "argon",
                 "lab gas", "cda", "n2", "o2", "co2",
                 "压缩空气", "真空", "氮气", "氧气", "氩气", "实验气", "工艺气体")),
    ("vent", ("exhaust", "vent", "air", "lucht", "fume hood", "general exhaust",
              "排风", "通风柜排风", "一般排风", "送排风")),
]


_DUCT_TYPE_RULES = [
    ("supply_air", ("supply air", "supply", "saf", "送风", "送風", "空调送风")),
    ("return_air", ("return air", "return", "raf", "回风", "回風")),
    ("exhaust_air", ("exhaust", "general exhaust", "gef", "vent", "排风", "排風",
                     "fume hood", "通风柜排风", "通风柜")),
    ("outside_air", ("outside air", "outside", "oaf", "fresh air", "新风", "室外风")),
    ("smoke_exhaust", ("smoke", "smoke exhaust", "排烟", "消防排烟")),
]


def _classify_pipe_type(e):
    """Classify a pipe/duct/fitting's purpose from multiple IFC data sources.

    Priority: ArchCheckPipeParams Pset → system Psets (Revit/Common) → type object
    name → material name → element name → unknown. Works on IFC2X3 and IFC4.

    Returns one of the keys in _PIPE_TYPE_RULES or 'unknown'.
    """
    # 1. ArchCheck override Pset (highest priority, used by manual editors)
    override = _pset_value(e, "ArchCheckPipeParams", "pipe_type")
    if override:
        return override
    # 2. Build a text blob from all system-indicating sources
    text_parts = []
    # Standard Psets
    for pset, prop in [("Pset_PipeSegmentCommon", "System"),
                        ("Pset_PipeSegmentTypeCommon", "SystemType"),
                        ("Pset_DuctSegmentCommon", "System"),
                        ("Pset_DuctSegmentTypeCommon", "SystemType")]:
        v = _pset_value(e, pset, prop)
        if v:
            text_parts.append(str(v))
    # Revit-specific
    for pset, prop in [("PSet_Revit_Mechanical", "System Type"),
                        ("PSet_Revit_Mechanical", "System Name"),
                        ("PSet_Revit_Mechanical", "System Classification"),
                        ("Pset_PipeSegmentCommon", "FlowDirection")]:
        v = _pset_value(e, pset, prop)
        if v:
            text_parts.append(str(v))
    # Element name
    text_parts.append(e.Name or "")
    # 3. Type object name (IfcPipeSegmentType / IfcDuctSegmentType / IfcPipeFittingType)
    type_name = _type_object_name(e)
    if type_name:
        text_parts.append(type_name)
    # 4. Material name (last resort: material hints at system, e.g. "Fire Sprinkler Pipe")
    mat = _elem_material(e)
    if mat:
        text_parts.append(mat)
    text = " ".join(filter(None, text_parts)).lower()
    for pipe_type, kws in _PIPE_TYPE_RULES:
        if any(k in text for k in kws):
            return pipe_type
    return "unknown"


def _classify_duct_type(e):
    """Classify a duct's purpose using the same multi-source strategy."""
    override = _pset_value(e, "ArchCheckDuctParams", "duct_type")
    if override:
        return override
    text_parts = []
    for pset, prop in [("Pset_DuctSegmentCommon", "System"),
                        ("Pset_DuctSegmentTypeCommon", "SystemType"),
                        ("PSet_Revit_Mechanical", "System Type"),
                        ("PSet_Revit_Mechanical", "System Name")]:
        v = _pset_value(e, pset, prop)
        if v:
            text_parts.append(str(v))
    text_parts.append(e.Name or "")
    type_name = _type_object_name(e)
    if type_name:
        text_parts.append(type_name)
    mat = _elem_material(e)
    if mat:
        text_parts.append(mat)
    text = " ".join(filter(None, text_parts)).lower()
    for duct_type, kws in _DUCT_TYPE_RULES:
        if any(k in text for k in kws):
            return duct_type
    return "unknown"


def _type_object_name(e):
    """Name of the element's type object (IfcTypeObject) via IfcRelDefinesByType,
    or None. Falls back to IFC4-style HasPredefinedType /ElementType attribute."""
    # via IfcRelDefinesByType (both IFC2X3 and IFC4)
    for rel in (e.HasAssociations or []):
        if rel.is_a("IfcRelDefinesByType"):
            rt = rel.RelatingType
            if rt and rt.Name:
                return rt.Name
    # IFC4: some types expose ElementType directly
    et = getattr(e, "ElementType", None)
    if et:
        return et
    return None


def _classify_system_pipe_type(system_name):
    """Map an IFC system name onto a pipe_type keyword for the classification
    fallback when the pipe itself carries no type hint (system membership is a
    strong signal — e.g. a pipe in the CHILLEDWATER system is hydronic)."""
    text = (system_name or "").lower()
    # IFC PredefinedType enum tokens come as one word (CHILLEDWATER, RAINWATER…)
    tokens = text.replace("_", " ")
    for pipe_type, kws in _PIPE_TYPE_RULES:
        if any(k in tokens for k in kws):
            return pipe_type
    # IFC enum values without spaces (e.g. "chilledwater") need direct mapping
    if any(k in tokens for k in ("fireprotection", "fire")) or text == "fire":
        return "fire"
    if any(k in text for k in ("drainage", "wastewater", "sewage", "stormwater",
                                "rainwater", "disposal", "sewer")):
        return "drainage"
    if any(k in text for k in ("watersupply", "coldwater", "hotwater", "domestic",
                                "circulation")):
        return "supply"
    if any(k in text for k in ("chilledwater", "condenserwater", "heating",
                                "refrigeration", "heatflow", "heatreturn",
                                "coolingflow", "coolingreturn")):
        return "hydronic"
    if text == "gas" or "gas" in text:
        return "gas"
    if any(k in text for k in ("compressedair", "vacuum")):
        return "lab_gas"
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


def _pipe_profile_diameter(e, declared_scale):
    """Diameter (m) from IfcCircleProfileDef inside an IfcExtrudedAreaSolid.

    More precise than bbox for circular pipes — returns None if the geometry
    isn't a simple circular extrusion. ``declared_scale`` is the metres-per-unit
    of the model's *declared* length unit (profile dims use declared units,
    not world-coordinate units — they can differ in mixed-unit models).
    """
    info = _extrusion_profile_info(e, declared_scale)
    if info and info.get("is_circular"):
        return info["section_min_m"] * 2 if info.get("radius") else info["section_min_m"]
    return None


def _extrusion_profile_info(e, scale):
    """Best-effort section + length info from an element's extrusion geometry.

    Works for any element that has an IfcExtrudedAreaSolid body representation
    (beams, columns, slabs, footings, pipes, ducts, …). Slanted / rotated
    extrusions still give the correct cross-section dimensions because the
    SweptArea is defined in its own 2D plane. Mapped representations
    (IfcMappedItem) are dereferenced so repeated elements (e.g. rafters) also
    resolve correctly.

    Returns dict with keys:
      section_min_m / section_max_m — bounding dimensions of the 2D profile (m)
      length_m                     — extrusion depth, i.e. length along axis (m)
      is_circular                  — True if profile is a circle
      radius                       — circle radius (m), if circular
    Returns None if no extrusion found.
    """
    def _resolve_items(items):
        """Yield geometric representation items, descending into MappedItems."""
        for item in items or []:
            if item.is_a("IfcMappedItem"):
                # 解引用映射项：进到映射源的几何里找
                mrep = getattr(item, "MappingSource", None)
                if mrep and hasattr(mrep, "MappedRepresentation"):
                    mapped = mrep.MappedRepresentation
                    if mapped and hasattr(mapped, "Items"):
                        for sub in _resolve_items(mapped.Items):
                            yield sub
            else:
                yield item

    def _from_extrusion(item):
        """从一个 IfcExtrudedAreaSolid 提取截面 + 深度。"""
        if not item.is_a("IfcExtrudedAreaSolid"):
            return None
        sa = item.SweptArea
        depth = getattr(item, "Depth", None)
        if depth is None or depth <= 0:
            return None
        sec_min = sec_max = None
        is_circular = False
        radius = None
        if sa.is_a("IfcCircleProfileDef") or sa.is_a("IfcCircleHollowProfileDef"):
            r = getattr(sa, "Radius", 0)
            if r > 0:
                sec_min = sec_max = 2 * r
                is_circular = True
                radius = r
        elif sa.is_a("IfcRectangleProfileDef"):
            xd = getattr(sa, "XDim", 0)
            yd = getattr(sa, "YDim", 0)
            if xd > 0 and yd > 0:
                sec_min, sec_max = sorted((xd, yd))
        elif sa.is_a("IfcArbitraryClosedProfileDef"):
            curve = getattr(sa, "OuterCurve", None)
            if curve and hasattr(curve, "Points"):
                pts = curve.Points
                xs = [p.Coordinates[0] for p in pts]
                ys = [p.Coordinates[1] for p in pts]
                dx = max(xs) - min(xs)
                dy = max(ys) - min(ys)
                if dx > 0 and dy > 0:
                    sec_min, sec_max = sorted((dx, dy))
        if sec_min is None or sec_max is None:
            return None
        return {
            "section_min_m": sec_min * scale,
            "section_max_m": sec_max * scale,
            "length_m": depth * scale,
            "is_circular": is_circular,
            "radius_m": radius * scale if radius else None,
        }

    if not e.Representation:
        return None
    for rep in e.Representation.Representations or []:
        if rep.RepresentationIdentifier and rep.RepresentationIdentifier != "Body":
            continue
        for geom in _resolve_items(rep.Items):
            result = _from_extrusion(geom)
            if result:
                return result
    return None


def _pca_dims(elem, settings, scale):
    """Long/short dimensions (m) of a prismatic element via PCA on its mesh.

    For sloped or rotated elements (rafters, sloped beams, tilted columns)
    whose geometry is a FacetedBrep / tessellation rather than an extrusion,
    the axis-aligned bbox is wrong: its long axis is the *horizontal* extent,
    not the element axis. PCA on the vertices finds the true element axis
    (1st principal component) and the cross-section plane (2nd/3rd), so the
    three projected ranges give a correct (length, height, width) estimate
    regardless of orientation.

    Returns (small, mid, big) in metres, or None.
    """
    try:
        shape = ifcgeom.create_shape(settings, elem)
        v = shape.geometry.verts
        if len(v) < 6:
            return None
        pts = np.asarray(v, dtype=np.float64).reshape(-1, 3)
        if len(pts) < 3:
            return None
        # 降采样控制成本：超过 10k 顶点时均匀抽取
        if len(pts) > 10000:
            step = max(1, len(pts) // 10000)
            pts = pts[::step]
        c = pts.mean(axis=0)
        centered = pts - c
        # 协方差矩阵的三个特征向量 = 三个主方向；特征值开根 ≈ 该方向标准差
        cov = np.cov(centered.T)
        eigvals, eigvecs = np.linalg.eigh(cov)
        # 按主方向从小到大排
        order = np.argsort(eigvals)
        ranges = []
        for i in order:
            axis = eigvecs[:, i]
            proj = centered @ axis
            ranges.append((proj.max() - proj.min()))
        small, mid, big = sorted(ranges)
        # 归一性保护：粗结果必须接近"细长杆件"才有意义，否则退回 None
        if small > 1e-6 and mid > 1e-6:
            return (small * scale, mid * scale, big * scale)
        return None
    except Exception:
        return None


def _try_best_scale(raw_value, ref_value, scale_a, scale_b, size_key, tol=0.3):
    """Try two scales on a raw value; return (best_value, best_scale) that is
    closer to ``ref_value`` within tolerance, or (None, None)."""
    if raw_value is None or ref_value is None or ref_value <= 0:
        return None, None
    candidates = []
    for s in (scale_a, scale_b):
        v = raw_value * s
        if v <= 0:
            continue
        err = abs(v - ref_value) / ref_value
        if err < tol and _is_plausible(v, size_key):
            candidates.append((err, v, s))
    if not candidates:
        return None, None
    candidates.sort()
    return candidates[0][1], candidates[0][2]


def _pipe_data(e, scale, settings, profile_scale=None):
    """Real pipe data for an IfcFlowSegment / IfcPipeSegment.

    Extraction priority:
      1. ArchCheckPipeParams Pset (manual override) — in metres
      2. IfcElementQuantity / Qto — scale from ``profile_scale``
      3. IfcCircleProfileDef (extrusion cross-section) — scale from ``profile_scale``
      4. Tessellated geometry bbox — in ``scale`` (world units)

    ``profile_scale`` is the unit scale for Qto and ProfileDef data. If None
    (confidence low), falls back to per-element cross-checking against bbox.
    """
    pipe_type = _classify_pipe_type(e)
    d = _elem_bbox_dims(e, scale, settings)
    bbox_dia = min(d) if d else None

    diameter = None
    _override = _pset_value(e, "ArchCheckPipeParams", "diameter_m")
    if _override is not None:
        diameter = float(_override)

    if diameter is None and profile_scale is not None:
        _qto = _qto_value(e, "Qto_PipeSegmentBaseQuantities", "OuterDiameter")
        if _qto is not None:
            diameter = _qto * profile_scale
            if not _is_plausible(diameter, "pipe_diameter"):
                diameter = None
        if diameter is None:
            p_dia = _pipe_profile_diameter(e, profile_scale)
            if p_dia is not None and _is_plausible(p_dia, "pipe_diameter"):
                diameter = p_dia

    if diameter is None:
        # Low confidence: cross-check both declared vs world scale against bbox
        # We need declared_scale but don't have it here — try both extreme scales.
        # Use scale and 1000*scale as two candidates (covers mm↔m flip).
        scale_b = scale * 1000.0 if scale < 0.01 else scale / 1000.0
        _qto = _qto_value(e, "Qto_PipeSegmentBaseQuantities", "OuterDiameter")
        if _qto is not None and bbox_dia is not None:
            diameter, _ = _try_best_scale(_qto, bbox_dia, scale, scale_b, "pipe_diameter")
        if diameter is None:
            # Try profile def
            p_raw = _pipe_profile_diameter(e, 1.0)  # raw (one model unit = 1m)
            if p_raw and bbox_dia is not None:
                diameter, _ = _try_best_scale(p_raw, bbox_dia, scale, scale_b, "pipe_diameter")

    if diameter is None and bbox_dia is not None:
        diameter = bbox_dia
    if diameter is not None:
        diameter = round(float(diameter), 4)

    # length: Qto → bbox
    length = None
    _qto_len = _qto_value(e, "Qto_PipeSegmentBaseQuantities", "Length")
    if _qto_len is not None:
        length = _qto_len * scale
    elif d:
        length = round(max(d), 3)

    # slope: Pset override → any Pset "Slope" → geometry rise/run
    slope = _pset_value(e, "ArchCheckPipeParams", "slope")
    if slope is None:
        _real = _any_prop_value(e, "Slope")
        try:
            _real = float(_real)
            if not (0.0 <= _real <= 1.0):
                _real = None
        except (TypeError, ValueError):
            _real = None
        slope = _real if _real is not None else _pipe_slope_from_geom(e, settings)
    if slope is not None:
        slope = round(float(slope), 4)

    material = _elem_material(e)

    out = {"name": e.Name or e.GlobalId, "pipe_type": pipe_type,
           "diameter_m": diameter, "slope": slope, "length_m": length,
           "material": material}
    # fire hydrant spacing centroid
    if pipe_type == "fire":
        _c = _elem_bbox_centroid(e, scale, settings)
        if _c:
            out["_centroid"] = _c
    # drainage stack detection
    if pipe_type == "drainage" and d and d[2] > max(d[0], d[1]) * 1.5:
        out["vertical_drain_diameter_m"] = round(min(d[0], d[1]), 4)
    return out


def _duct_cross_section(e, scale, settings):
    """(width_m, height_m) of a duct's cross-section, perpendicular to its length.

    For rectangular ducts this is the two shorter bbox dimensions; for flat oval /
    round ducts we approximate from the bbox. Returns (None, None) if geometry
    cannot be tessellated.
    """
    d = _elem_bbox_dims(e, scale, settings)
    if not d:
        return None, None
    dims = sorted(d)  # smallest, middle, largest (= length)
    return round(dims[0], 4), round(dims[1], 4)


def _duct_data(e, scale, settings, profile_scale=None):
    """Real HVAC duct data with multi-source extraction priority.

    Priority: ArchCheckDuctParams Pset → Qto (profile_scale) → bbox geometry.
    When ``profile_scale`` is None (low confidence), Qto values are
    cross-checked against bbox per-element.
    """
    duct_type = _classify_duct_type(e)
    d = _elem_bbox_dims(e, scale, settings)
    gw, gh = _duct_cross_section(e, scale, settings)

    def _resolve_qto(qty_name, bbox_ref, size_key):
        qv = _qto_value(e, "Qto_DuctSegmentBaseQuantities", qty_name)
        if qv is None or bbox_ref is None or bbox_ref <= 0:
            return None
        if profile_scale is not None:
            v = qv * profile_scale
            if _is_plausible(v, size_key):
                return v
            return None
        # Per-element fallback: try both scale and scale*1000 (mm↔m flip)
        scale_b = scale * 1000.0 if scale < 0.01 else scale / 1000.0
        best, _ = _try_best_scale(qv, bbox_ref, scale, scale_b, size_key)
        return best

    width = _pset_value(e, "ArchCheckDuctParams", "duct_width_m")
    height = _pset_value(e, "ArchCheckDuctParams", "duct_height_m")
    if width is not None:
        width = round(float(width), 4)
    if height is not None:
        height = round(float(height), 4)
    if width is None:
        w = _resolve_qto("Width", gw, "duct_side")
        width = round(w, 4) if w is not None else gw
    if height is None:
        h = _resolve_qto("Height", gh, "duct_side")
        height = round(h, 4) if h is not None else gh

    net = _pset_value(e, "ArchCheckDuctParams", "net_height_m")
    if net is not None:
        net = round(float(net), 4)

    length = None
    bbox_len = max(d) if d else None
    if bbox_len and bbox_len > 0:
        _ql = _qto_value(e, "Qto_DuctSegmentBaseQuantities", "Length")
        if _ql is not None:
            if profile_scale is not None:
                v = _ql * profile_scale
                if abs(v - bbox_len) / bbox_len < 0.3:
                    length = round(v, 3)
            else:
                scale_b = scale * 1000.0 if scale < 0.01 else scale / 1000.0
                v, _ = _try_best_scale(_ql, bbox_len, scale, scale_b, "duct_side", tol=0.5)
                if v is not None:
                    length = round(v, 3)
    if length is None and d:
        length = round(max(d), 3)

    material = _elem_material(e)
    return {"name": e.Name or e.GlobalId, "duct_type": duct_type,
            "duct_width_m": width, "duct_height_m": height,
            "net_height_m": net, "length_m": length, "material": material}


_FITTING_TYPE_RULES = [
    ("elbow", ("elbow", "ellbow", "bend", "弯头", "弯管")),
    ("tee", ("tee", "t-piece", "t branch", "三通", "丁字")),
    ("transition", ("transition", "reducer", "expander", "变径", "异径", "大小头")),
    ("cross", ("cross", "four-way", "四通")),
    ("cap", ("cap", "plug", "end cap", "堵头", "管帽")),
    ("trap", ("trap", "存水弯", "s弯", "p弯", "s trap", "p trap")),
    ("flange", ("flange", "法兰")),
    ("union", ("union", "活接", "接头")),
    ("valve", ("valve", "gate", "butterfly", "check", "球阀", "闸阀", "蝶阀", "止回阀", "阀门")),
]


def _classify_fitting_type(e):
    """Classify an IfcPipeFitting / IfcDuctFitting by PredefinedType + name keywords.

    Returns one of: elbow / tee / transition / cross / cap / trap / flange / union /
    valve / unknown.
    """
    predef = getattr(e, "PredefinedType", None)
    if predef and predef not in ("USERDEFINED", "NOTDEFINED", None):
        mapping = {"ELBOW": "elbow", "TEE": "tee", "TRANSITION": "transition",
                   "JUNCTION": "tee", "CROSS": "cross", "CAP": "cap",
                   "TRAP": "trap", "UNION": "union", "FLANGE": "flange"}
        if predef in mapping:
            return mapping[predef]
    name = (e.Name or "").lower()
    for ftype, kws in _FITTING_TYPE_RULES:
        if any(k in name for k in kws):
            return ftype
    return "unknown"


def _pipe_fitting_data(e, scale, settings):
    """Extract data for an IfcPipeFitting: type, size, material, bbox centroid."""
    ftype = _classify_fitting_type(e)
    pipe_type = _classify_pipe_type(e)
    d = _elem_bbox_dims(e, scale, settings)
    size_m = None
    if d:
        size_m = round(min(d[0], d[1]), 4)  # smaller cross-section dim = nominal size
    material = _elem_material(e)
    centroid = _elem_bbox_centroid(e, scale, settings)
    out = {"name": e.Name or e.GlobalId, "fitting_type": ftype,
           "pipe_type": pipe_type, "size_m": size_m, "material": material,
           "length_m": round(max(d), 4) if d else None}
    if centroid:
        out["_centroid"] = centroid
    return out


def _pipe_network_topology(m):
    """Graph connectivity of MEP flow elements via IfcRelConnectsPorts.

    Two elements are neighbours when a port on one is connected (by
    IfcRelConnectsPorts) to a port on the other. Returns a dict for downstream
    consumers (per-pipe neighbour names) plus a connectivity report.

    Returns
    -------
    {"networks": [{members, count}], "member_count": int,
     "element_neighbours": {gid: [neighbour_gid]}}
    If the model has no port data, returns {"member_count": 0, ...} so callers
    can report "无端口连接数据" honestly.
    """
    # port gid -> element gid (which element owns which port)
    port_owner = {}
    for rel in m.by_type("IfcRelConnectsPortToElement"):
        el = rel.RelatedElement
        if el is None:
            continue
        port_owner[rel.RelatingPort.GlobalId] = el.GlobalId

    neighbours = {}
    connections = m.by_type("IfcRelConnectsPorts")
    if not connections:
        return {"networks": [], "member_count": 0, "element_neighbours": {}}
    for rel in connections:
        a = port_owner.get(rel.RelatingPort.GlobalId)
        b = port_owner.get(rel.RelatedPort.GlobalId)
        if not a or not b or a == b:
            continue
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)

    # Connected components (networks) via BFS over the neighbour graph
    networks = []
    seen = set()
    for gid in neighbours:
        if gid in seen:
            continue
        comp = []
        stack = [gid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(neighbours.get(cur, set()) - seen)
        networks.append({"members": comp, "count": len(comp)})
    networks.sort(key=lambda n: -n["count"])

    return {
        "networks": networks,
        "member_count": sum(n["count"] for n in networks),
        "element_neighbours": {k: sorted(v) for k, v in neighbours.items()},
    }


def _distribution_system_map(m):
    """{system_name: [element GlobalIds]} from IfcDistributionSystem members."""
    out = {}
    for rel in m.by_type("IfcRelAssignsToGroup"):
        grp = rel.RelatingGroup
        if not (grp.is_a("IfcDistributionSystem") or grp.is_a("IfcSystem")):
            continue
        out[grp.Name or grp.GlobalId] = [o.GlobalId for o in rel.RelatedObjects]
    return out


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
            # rare fields: only set when a value actually exists, so a model that
            # lacks them reports a clean "未检查（缺字段）" instead of a Missing
            # flood on every element.
            if _pset_value(e, "ArchCheckEEEEquip", "has_exit_sign") or \
               any(k in nm for k in ("exit sign", "exit", "疏散指示", "出口指示")):
                d["has_exit_sign"] = True
            _illum = _pset_value(e, "ArchCheckEEEEquip", "illuminance_lx")
            if _illum is not None:
                d["illuminance_lx"] = _illum
        elif et == "socket":
            d["outlet_spacing_m"] = _pset_value(e, "ArchCheckEEEEquip", "outlet_spacing_m")
        elif et == "distribution":
            d["circuit_load_a"] = _pset_value(e, "ArchCheckEEEEquip", "circuit_load_a")
            d["dist_to_water_m"] = _pset_value(e, "ArchCheckEEEEquip", "dist_to_water_m")
            if _pset_value(e, "ArchCheckEEEEquip", "fire_rated") or \
               any(k in nm for k in ("fire rated", "耐火")):
                d["fire_rated"] = True
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


def _detect_clashes_list(mep_els, solid_els, settings, margin=0.05):
    """Cross-discipline clash pre-check between two element lists.

    bbox overlap (depth > margin) produces candidates; each is then CONFIRMED
    by point-in-mesh (any MEP vertex strictly inside the solid). Each element's
    world bbox is tessellated once and cached, so runtime is O(n_mep + n_solid)
    geometry calls rather than O(n_mep × n_solid).
    Returns [{mep, vs, type, depth, confirmed}]."""
    solids = []
    for b in solid_els:
        bb = _elem_world_bbox(b, settings)
        if bb:
            solids.append((b, bb))
    if not solids or not mep_els:
        return []
    out = []
    for a in mep_els:
        ba = _elem_world_bbox(a, settings)
        if not ba:
            continue
        for b, bb in solids:
            ox = min(ba[2], bb[2]) - max(ba[0], bb[0])
            oy = min(ba[3], bb[3]) - max(ba[1], bb[1])
            oz = min(ba[5], bb[5]) - max(ba[4], bb[4])
            if ox > margin and oy > margin and oz > margin:
                out.append({"mep": a.Name or "?", "vs": b.Name or "?",
                            "type": b.is_a(), "depth": round(min(ox, oy, oz), 2),
                            "confirmed": _confirm_clash(a, b, settings)})
    return out


def _detect_clashes(els, settings, margin=0.05):
    """Cross-discipline clash pre-check between MEP (pipe/duct) and structure
    (beam/slab/wall). Convenience wrapper that splits one list into MEP vs solid.
    """
    mep = [e for e in els if e.is_a("IfcFlowSegment") or e.is_a("IfcDuctSegment")
           or e.is_a("IfcPipeFitting") or e.is_a("IfcDuctFitting")]
    solid = [e for e in els
             if e.is_a("IfcBeam") or e.is_a("IfcSlab") or e.is_a("IfcWall") or e.is_a("IfcWallStandardCase")]
    return _detect_clashes_list(mep, solid, settings, margin)


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


def _elem_bbox_centroid(elem, scale, settings):
    """(cx, cy, cz) centroid in metres of an element's tessellated geometry bbox."""
    try:
        shape = ifcgeom.create_shape(settings, elem)
        v = shape.geometry.verts
        if len(v) < 6:
            return None
        xs = v[0::3]
        ys = v[1::3]
        zs = v[2::3]
        return ((min(xs) + max(xs)) / 2 * scale,
                (min(ys) + max(ys)) / 2 * scale,
                (min(zs) + max(zs)) / 2 * scale)
    except Exception:
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


def _slab_thickness_m(e, scale, settings, profile_scale=None):
    """Slab thickness in metres, best-effort by priority.

    1. Qto_SlabBaseQuantities.GrossThickness  (if profile_scale known)
    2. IfcExtrudedAreaSolid.Depth              (if profile_scale known)
    3. PCA smallest principal axis              (world units — reliable even for
       mixed-unit mm-declared models and sloped tessellated slabs)
    4. bbox Z-axis difference                   (last-resort; wrong for sloped)

    Qto / extrusion Depth use the model's declared length unit (e.g. mm when the
    file declares MILLI but its geometry is metre-scaled), so they are only read
    when ``profile_scale`` is known and multiplied by it. When unit inference is
    not confident (``profile_scale is None``) they are skipped — multiplying by
    the world scale would make mm-declared Revit slabs read ~1000x too thick.
    Returns None if nothing works.
    """
    if profile_scale is not None:
        # 1. Qto
        qto = _qto_value(e, "Qto_SlabBaseQuantities", "GrossThickness")
        if qto is not None and qto > 0:
            return qto * profile_scale

        # 2. Extrusion depth (Body representation)
        if e.Representation:
            for rep in e.Representation.Representations:
                if rep.RepresentationIdentifier != "Body":
                    continue
                for item in rep.Items:
                    if item.is_a("IfcExtrudedAreaSolid"):
                        depth = getattr(item, "Depth", None)
                        if depth and depth > 0:
                            return depth * profile_scale

    # 3. PCA smallest axis — slab is a flat panel, its thinnest direction is
    #    the thickness regardless of how the slab is tilted in world space.
    pca = _pca_dims(e, settings, scale)
    if pca and pca[0] > 0.005:
        return pca[0]

    # 4. bbox fallback
    d = _elem_bbox_dims(e, scale, settings)
    if d and d[2] > 0.01:
        return d[2]

    return None


def _structural_sections(els, settings, scale, profile_scale=None,
                         col_cap=500, other_cap=500):
    """Structural element data from storey elements.

    Returns (elements, column_sections, beam_sections, slab_thicknesses,
    unit_suspicious). ``elements`` is a per-element list (id/name/element_type +
    section fields) for the review engine. Section dimensions are taken from
    extrusion cross-section (IfcExtrudedAreaSolid.SweptArea) when available —
    this stays correct for sloped/rotated beams, columns, etc. Bounding-box
    dimensions are used as fallback. ``profile_scale`` is the unit scale for
    SweptArea / Qto data (may differ from world scale in mixed-unit models).
    ``unit_suspicious`` counts elements whose scaled dimensions are implausibly
    small (< 0.02 m) — sign of a unit-magnitude mismatch.
    """
    elements, col_sec, beam_sec, slab_th = [], [], [], []
    ncol = nbeam = nslab = nfooting = 0
    unit_suspicious = 0
    for e in els:
        if e.is_a("IfcColumn"):
            if ncol >= col_cap:
                continue
            ncol += 1
            info = _extrusion_profile_info(e, profile_scale) if profile_scale else None
            d = _elem_bbox_dims(e, scale, settings)
            sec_min = sec_max = height = None
            if info:
                sec_min = info["section_min_m"]
                sec_max = info["section_max_m"]
                height = info["length_m"]
            else:
                pca = _pca_dims(e, settings, scale)  # (small, mid, big)
                if pca and 0.03 < pca[0] and pca[1] < 2.0:
                    sec_min, sec_max, height = pca[0], pca[1], pca[2]
                elif d and min(d) > 0.02:
                    sec_min, sec_max = sorted((d[0], d[1]))
                    height = d[2]
                else:
                    unit_suspicious += 1
                    continue
            if sec_min and sec_max and 0.05 < sec_min and sec_max < 2.0:
                col_sec.append((round(sec_min, 3), round(sec_max, 3)))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "column",
                                 "section_min_m": round(sec_min, 3),
                                 "section_max_m": round(sec_max, 3),
                                 "height_m": round(height, 3) if height else None,
                                 "volume_m3": _elem_volume(e, settings, scale),
                                 "material": _elem_material(e)})
        elif e.is_a("IfcBeam"):
            if nbeam >= other_cap:
                continue
            nbeam += 1
            info = _extrusion_profile_info(e, profile_scale) if profile_scale else None
            d = _elem_bbox_dims(e, scale, settings)
            sec_min = sec_max = span = None
            if info:
                sec_min = info["section_min_m"]
                sec_max = info["section_max_m"]
                span = info["length_m"]  # 拉伸深度 = 梁的真实长度（斜梁也对）
            else:
                pca = _pca_dims(e, settings, scale)  # (small, mid, big)，斜梁也对
                if pca and 0.03 < pca[0] and pca[1] < 2.0:
                    sec_min, sec_max, span = pca[0], pca[1], pca[2]
                elif d and min(d) > 0.02:
                    # bbox 兜底：假设梁是水平的
                    sec_min = min(d[0], d[1])
                    sec_max = d[2]
                    span = max(d[0], d[1])
                else:
                    unit_suspicious += 1
                    continue
            if sec_min and sec_max and 0.03 < sec_min and sec_max < 2.0:
                beam_sec.append((round(sec_max, 3), round(sec_min, 3)))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "beam",
                                 "depth_m": round(sec_max, 3),
                                 "width_m": round(sec_min, 3),
                                 "span_m": round(span, 3) if span else None,
                                 "volume_m3": _elem_volume(e, settings, scale),
                                 "material": _elem_material(e)})
        elif e.is_a("IfcSlab"):
            if nslab >= other_cap:
                continue
            nslab += 1
            d = _elem_bbox_dims(e, scale, settings)
            thickness = _slab_thickness_m(e, scale, settings, profile_scale)
            if thickness is None or thickness < 0.01:
                unit_suspicious += 1
                continue
            if 0.02 < thickness < 1.0:
                slab_th.append(round(thickness, 3))
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "slab",
                                 "thickness_m": round(thickness, 3),
                                 "span_m": round(max(d[0], d[1]), 3) if d else None,
                                 "volume_m3": _elem_volume(e, settings, scale),
                                 "material": _elem_material(e)})
        elif e.is_a("IfcFooting"):
            if nfooting >= other_cap:
                continue
            nfooting += 1
            info = _extrusion_profile_info(e, profile_scale) if profile_scale else None
            d = _elem_bbox_dims(e, scale, settings)
            thickness = span = None
            if info:
                # 基础通常是短粗的拉伸体，厚度 = 拉伸方向长度
                thickness = info["section_min_m"]
                span = info["section_max_m"]
            else:
                # 用 PCA 截面：承台(0.84×0.84×0.3)与桩(0.3×0.3×6m)都取
                # 截面短边为"厚度"，长边为跨度 —— 避免把 6m 长的桩按 bbox z
                # 当厚度而超过过滤范围被丢弃。
                pca = _pca_dims(e, settings, scale)
                if pca and 0.02 < pca[0] < 3.0:
                    thickness, span = pca[0], pca[2]
                elif d and d[2] > 0.02:
                    thickness = d[2]
                    span = max(d[0], d[1])
                else:
                    unit_suspicious += 1
                    continue
            if thickness and 0.05 < thickness < 3.0:
                elements.append({"id": e.GlobalId, "name": e.Name or e.GlobalId,
                                 "element_type": "footing",
                                 "thickness_m": round(thickness, 3),
                                 "span_m": round(span, 3) if span else None,
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


def _space_bbox_rect(space):
    """(x0, y0, x1, y1) world-XY rectangle (raw authored units) of a space's
    IfcBoundingBox: its four corners transformed through the ObjectPlacement
    chain. Rotation/mirror in the placement (not just the origin) matters —
    Schependomlaan's storey frames are rotated 90°, which swaps the bbox's X/Y
    extents in world space. None if there is no bbox or no resolvable placement."""
    bb = _space_bounding_box(space)
    if not bb:
        return None
    try:
        import ifcopenshell.util.placement as _place_util
        if space.ObjectPlacement is None:
            return None
        mat = _place_util.get_local_placement(space.ObjectPlacement)
    except Exception:
        return None
    w, d = bb
    xs = []
    ys = []
    for lx, ly in ((0.0, 0.0), (w, 0.0), (0.0, d), (w, d)):
        xs.append(mat[0][0] * lx + mat[0][1] * ly + mat[0][3])
        ys.append(mat[1][0] * lx + mat[1][1] * ly + mat[1][3])
    return min(xs), min(ys), max(xs), max(ys)


def _space_hull(space, settings, bbox_scale=1.0):
    """(convex_hull_xy, centroid_xy, precise_area_units) of a space's tessellated
    XY projection. Coordinates in model units. precise_area_units is the exact
    2D outline area (positive-signed projected triangles — handles concave rooms,
    which the convex hull overestimates), or None when the mesh has no faces.
    Spaces without tessellatable geometry fall back to a placement-aligned
    rectangle built from their IfcBoundingBox (bbox_scale converts the bbox's
    authored unit into model units); if there is no geometry and no bbox at all,
    area_units is None (area unknown)."""
    try:
        shape = ifcgeom.create_shape(settings, space)
        v = shape.geometry.verts
        f = shape.geometry.faces
        pts = sorted(set((v[i], v[i + 1]) for i in range(0, len(v), 3)))
        if len(pts) < 3:
            return _bbox_hull(space, bbox_scale)
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
        return _bbox_hull(space, bbox_scale)


def _bbox_hull(space, bbox_scale=1.0):
    """Rectangle hull for a space that only has an IfcBoundingBox (no solid mesh):
    returns (rect_polygon, rect_centroid, None, True) when a placement resolves,
    else the legacy (None, None, bbox_area_units, True) so the caller can still
    get an area from the raw bbox product."""
    rect = _space_bbox_rect(space)
    if rect:
        x0, y0, x1, y1 = [c * bbox_scale for c in rect]
        return ([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                ((x0 + x1) / 2, (y0 + y1) / 2), None, True)
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
    # Geometry only fills in rooms with no boundary data — trust IfcRelSpaceBoundary
    # where the model provides it (the bbox-rect footprint is an approximation and
    # would over-count doors for boundary-backed rooms, e.g. Schependomlaan's lobby).
    for gid, (hull, _, _) in space_geom.items():
        if not hull or gid in assoc:
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
    if any(k in n for k in (
        "stair", "楼梯", "梯",
        "treppe", "trepp", "stg",  # 德语/北欧
    )):
        return "Stairwell"
    if any(k in n for k in (
        "corr", "走廊", "廊", "lobby", "foyer", "vestib", "hall", "前室",
        "korridor", "gang", "flur", "durchgang",  # 德语
    )):
        return "Corridor"
    if any(k in n for k in (
        "meet", "会议", "training", "培训", "class", "教室", "auditor", "多功能",
        "besprech", "sitzung", "konferenz", "meeting",  # 德语
    )):
        return "Meeting Room"
    if any(k in n for k in (
        "electr", "mep", "配电", "设备", "mech", "plant", "机房", "lift", "elev",
        "techn", "gerät", "maschinen", "hausanschluss", "schacht",  # 德语
        "el.", "lift", "aufzug",  # 德语电梯/电气
    )):
        return "Equipment Room"
    if any(k in n for k in (
        "wc", "toilet", "洗手", "厕所",
        "bad", "dusche", "sanitär", "klos", "toilette",  # 德语
        "rwc",  # 北欧 restroom with closet
    )):
        return "Vestibule"
    if any(k in n for k in (
        "office", "办公",
        "büro", "buro", "kontor", "kont.", "arbeitsplatz",  # 德语/北欧
    )):
        return "Office"
    return "Unknown"


def _max_room_travel(room_door_centroids, hull, scale):
    """Farthest-point egress distance (m): max over points in the room of the
    min distance to its exit doors. Approximated by sampling the hull vertices
    plus a coarse interior grid — exact farthest-point-in-polygon is a Voronoi
    computation we don't need at this precision."""
    if not hull or not room_door_centroids:
        return None
    xs = [p[0] for p in hull]
    ys = [p[1] for p in hull]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    cand = list(hull)
    step = max(maxx - minx, maxy - miny) / 8
    if step < 0.1:
        step = 0.1
    y = miny
    while y <= maxy + 1e-9:
        x = minx
        while x <= maxx + 1e-9:
            if _point_in_poly((x, y), hull):
                cand.append((x, y))
            x += step
        y += step
    best = 0.0
    for px, py in cand:
        dmin = min(((px - qx) ** 2 + (py - qy) ** 2) ** 0.5 for qx, qy in room_door_centroids)
        if dmin > best:
            best = dmin
    return round(best * scale, 2)


def _building_fire_stats(m):
    """(fire_elevator_count, fire_extinguisher_count) counted from raw elements."""
    elev = 0
    for e in m.by_type("IfcTransportElement"):
        pt = getattr(e, "PredefinedType", None)
        nm = (e.Name or "").lower()
        if pt == "ELEVATOR" or any(k in nm for k in ("lift", "elevator", "电梯")):
            elev += 1
    ext = 0
    for e in m.by_type("IfcFurnishingElement"):
        nm = (e.Name or "").lower()
        if "exting" in nm or "灭火" in (e.Name or ""):
            ext += 1
    return elev, ext


def _space_to_room(space, area, ref="", door_widths=None, travel_distance=None, hull=None,
                   max_room_travel=None, has_sprinkler=None):
    """Build a review-engine room dict from a real IfcSpace.

    exit_count and door_width_m come from the real doors associated with the
    space. door_widths=None means the model has no usable door data -> both are
    None so the engine reports "data missing"; door_widths=[] is a real room
    with no doors (exit_count 0). travel_distance is the computed egress path
    (m) to the nearest exit room, feeding corridor_length_m. hull (if any) is
    the room's footprint polygon in model units, used to draw a real floor plan.
    max_room_travel / has_sprinkler are honest supplements: the former is the
    computed farthest-point egress distance, the latter a fire-pipe proximity
    proxy (None when the floor has no fire pipe to assess against).
    """
    name = space.Name or "?"
    long_name = getattr(space, "LongName", None) or ""
    rtype = _classify_room_type(f"{ref} {name} {long_name}")
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
    # corridor clear width: bbox short side for Corridor-type rooms
    # (approximation — good enough for accessibility code-of-thumb checks)
    corridor_width = None
    if rtype == "Corridor" and hull and len(hull) >= 3:
        xs = [p[0] for p in hull]
        ys = [p[1] for p in hull]
        corridor_width = round(min(max(xs) - min(xs), max(ys) - min(ys)), 3)

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
        "accessible_corridor_width_m": corridor_width,
        "max_room_travel_dist_m": max_room_travel,
        "has_sprinkler": has_sprinkler,
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
    # Declared length unit — profile definitions / Qto / bounding-box dims use
    # this, which can differ from the world-coordinate scale in mixed-unit
    # models (e.g. declared mm but geometry in m).
    declared_scale = _declared_length_scale(m) or scale
    # IfcBoundingBox is authored in the declared unit (often mm), which can
    # differ from the solid-geometry scale (Schependomlaan: mm bbox, m solids).
    # bbox_scale converts bbox units into model units for rectangle hulls.
    bbox_scale = declared_scale / scale
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

    # Infer the unit scale of Qto / ProfileDef data by sampling and voting.
    # profile_scale_confident = True → use globally; False → per-element fallback.
    profile_scale, profile_scale_confident, profile_scale_diag = _infer_profile_scale(
        m, scale, declared_scale, geom_settings)
    if not profile_scale_confident:
        # Not confident? Pass None to per-element functions so they fall back
        # to their own cross-check against bbox.
        profile_scale_for_extract = None
    else:
        profile_scale_for_extract = profile_scale

    # Port-based pipe network topology (real IFCs from Revit/Tekla carry ports;
    # many exports do not — then this honestly reports 0 networks).
    topology = _pipe_network_topology(m)
    system_map = _distribution_system_map(m)
    # element gid -> network index, for per-pipe network attribution below
    gid_network = {}
    for i, net in enumerate(topology.get("networks", [])):
        for gid in net["members"]:
            gid_network[gid] = i
    # element gid -> first system name it belongs to
    gid_system = {}
    for sys_name, members in system_map.items():
        for gid in members:
            gid_system.setdefault(gid, sys_name)

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

    # Wall/Door/Window/Railing/Stair fallback: same containment reality — some
    # exporters put these under the building/site (or none) instead of a storey.
    # Assign uncontained ones to a storey by world z-centre. NOTE: by_type
    # ("IfcWall") already includes IfcWallStandardCase, so de-dup by GlobalId.
    wall_door_window_fallback = {}
    if storeys:
        _wdw_seen = set()
        for e in (list(m.by_type("IfcWall")) + list(m.by_type("IfcWallStandardCase"))
                  + list(m.by_type("IfcDoor")) + list(m.by_type("IfcWindow"))
                  + list(m.by_type("IfcRailing")) + list(m.by_type("IfcStair"))):
            if e.GlobalId in kept_els_gids or e.GlobalId in _wdw_seen:
                continue
            _wdw_seen.add(e.GlobalId)
            b = _elem_world_bbox(e, geom_settings)
            if not b:
                continue
            zc = (b[4] + b[5]) / 2
            idx = 0
            for i, ev in enumerate(elevs):
                if zc >= ev:
                    idx = i
            wall_door_window_fallback.setdefault(storeys[idx].GlobalId, []).append(e)

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

    # MEP fallback: pipes / ducts / fittings are often under building/site, not
    # a storey (especially MEP-only models). Assign uncontained elements to the
    # nearest storey by their world z-centroid so they enter the per-floor review.
    mep_pipe_fallback = {}
    mep_duct_fallback = {}
    mep_fitting_fallback = {}
    if storeys:
        kept_els_gids3 = {e.GlobalId for st in storeys for e in by_storey.get(st.GlobalId, [])}

        def _assign_to_storey(elem, storeys_list, elevs_list, settings):
            b = _elem_world_bbox(elem, settings)
            if not b:
                return None
            zc = (b[4] + b[5]) / 2
            idx = 0
            for i, ev in enumerate(elevs_list):
                if zc >= ev:
                    idx = i
            return storeys_list[idx].GlobalId

        # MEP fallback: pipes / ducts / fittings are often under building/site, not
        # a storey (especially MEP-only models). Assign uncontained elements to the
        # nearest storey by their world z-centroid so they enter the per-floor review.
        # IfcFlowSegment covers pipes+ducts and IfcFlowFitting covers fittings in
        # BOTH schemas (IFC4-only IfcPipeSegment/IfcDuctSegment/IfcPipeFitting can't
        # be used with by_type on IFC2X3), then split by subtype/name.
        for e in m.by_type("IfcFlowSegment"):
            if e.GlobalId in kept_els_gids3:
                continue
            sg = _assign_to_storey(e, storeys, elevs, geom_settings)
            if not sg:
                continue
            if _is_duct_segment(e):
                mep_duct_fallback.setdefault(sg, []).append(e)
            else:
                mep_pipe_fallback.setdefault(sg, []).append(e)
        for e in m.by_type("IfcFlowFitting"):
            if e.GlobalId in kept_els_gids3:
                continue
            sg = _assign_to_storey(e, storeys, elevs, geom_settings)
            if sg and _is_pipe_fitting(e):
                mep_fitting_fallback.setdefault(sg, []).append(e)

    space_geom = {}
    space_storey = {}
    kept_spaces = []
    for sg, slist in storey_spaces.items():
        if sg not in kept_storey_gids:
            continue
        for sp in slist:
            hull, centroid, area_units, is_bbox = _space_hull(sp, geom_settings, bbox_scale)
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
    # plan/3D detail render); huge models skip it to keep parsing fast. Count
    # only elements the plan actually draws (_plan_element_kind) — otherwise
    # heavy Annotation / Furnishing / Space containers wrongly trip the gate
    # (e.g. Institute-Building: 809 total but only 442 plan-worthy).
    total_phys = sum(1 for els in by_storey.values()
                     for e in els if _plan_element_kind(e))
    extract_plan = total_phys <= 600

    floors = []
    for storey in storeys:
        els = by_storey.get(storey.GlobalId, [])
        wdw_fb = wall_door_window_fallback.get(storey.GlobalId, [])
        types = {}
        storey_door_widths = []
        ramp_slopes = []
        for e in els + wdw_fb:
            types[e.is_a()] = types.get(e.is_a(), 0) + 1
            if e.is_a("IfcDoor"):
                w = door_meta.get(e.GlobalId)
                if w:
                    storey_door_widths.append(w)
            elif e.is_a("IfcRamp") or e.is_a("IfcRampFlight"):
                s = _ramp_slope(e, scale)
                if s is not None:
                    ramp_slopes.append(s)
        # Structural elements (with z-fallback for uncontained columns/beams/slabs)
        all_struct_els = els + structural_fallback.get(storey.GlobalId, [])
        elements, col_sec, beam_sec, slab_th, unit_suspicious = _structural_sections(
            all_struct_els, geom_settings, scale, profile_scale_for_extract)

        plan_elems = _plan_elements(els + wdw_fb, geom_settings) if extract_plan else []

        # Pipes (storey-contained + z-fallback)
        pipe_elems = [e for e in els if _is_pipe_segment(e) and not _is_duct_segment(e)]
        pipe_elems += mep_pipe_fallback.get(storey.GlobalId, [])
        pipes = [_pipe_data(e, scale, geom_settings, profile_scale_for_extract) for e in pipe_elems]
        # fire hydrant spacing: distance to nearest other fire pipe centroid
        fire_centroids = [(i, p["_centroid"]) for i, p in enumerate(pipes)
                          if p.get("_centroid")]
        if fire_centroids:
            for i, (cx, cy, cz) in fire_centroids:
                dists = sorted(math.hypot(cx - fx, cy - fy, cz - fz)
                               for j, (fx, fy, fz) in fire_centroids if j != i)
                if dists:
                    pipes[i]["hydrant_spacing_m"] = round(dists[0], 3)
                else:
                    pipes[i]["hydrant_spacing_m"] = pipes[i].get("length_m") or 0.0
        for p in pipes:
            p.pop("_centroid", None)

        # Pipe fittings (storey-contained + z-fallback)
        fitting_elems = [e for e in els if _is_pipe_fitting(e)]
        fitting_elems += mep_fitting_fallback.get(storey.GlobalId, [])
        pipe_fittings = [_pipe_fitting_data(e, scale, geom_settings) for e in fitting_elems]
        for pf in pipe_fittings:
            pf.pop("_centroid", None)

        # Port topology attribution: which network each pipe/fitting belongs to,
        # and which IFC system names it (real exports group pipes by system).
        for e, pd in zip(pipe_elems, pipes):
            gid = e.GlobalId
            if gid in gid_network:
                pd["network_id"] = gid_network[gid]
            if gid in gid_system:
                pd["system"] = gid_system[gid]
                # system membership is a strong pipe_type signal (only when
                # classification found nothing — don't override a named type)
                if pd.get("pipe_type") in (None, "unknown"):
                    pd["pipe_type"] = _classify_system_pipe_type(gid_system[gid])
        for e, pf in zip(fitting_elems, pipe_fittings):
            gid = e.GlobalId
            if gid in gid_network:
                pf["network_id"] = gid_network[gid]
            if gid in gid_system:
                pf["system"] = gid_system[gid]

        # Ducts (storey-contained + z-fallback)
        duct_elems = [e for e in els if _is_duct_segment(e)]
        duct_elems += mep_duct_fallback.get(storey.GlobalId, [])
        ducts = [_duct_data(e, scale, geom_settings, profile_scale_for_extract) for e in duct_elems]

        # Railings — count + approximate height from bbox
        railing_elems = [e for e in els if e.is_a("IfcRailing")]
        railing_heights = []
        for re in railing_elems:
            b = _elem_world_bbox(re, geom_settings)
            if b:
                h = b[5] - b[4]  # z1 - z0
                if h > 0.01:
                    railing_heights.append(round(h, 3))
        railings = [{"name": e.Name or "",
                     "railing_type": getattr(e, "PredefinedType", None) or "",
                     "height_m": h}
                    for e, h in zip(railing_elems, railing_heights)]

        # Clash detection: include all MEP + structural elements on this floor
        all_mep_els = pipe_elems + duct_elems + fitting_elems
        if extract_plan:
            clash_els = [e for e in all_struct_els if e.is_a("IfcBeam")
                         or e.is_a("IfcSlab") or e.is_a("IfcWall")
                         or e.is_a("IfcWallStandardCase")]
            clashes = _detect_clashes_list(all_mep_els, clash_els, geom_settings)
        else:
            clashes = []
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
        # exit-sign fixtures: a room "has an exit sign" if a fixture named as one
        # is associated with it (matching by room ref).
        exit_sign_rooms = {el.get("room") for el in electrical if el.get("has_exit_sign")}
        # fire-pipe segments for the sprinkler-coverage proximity proxy
        fire_segs = []
        for e, pipe in zip(pipe_elems, pipes):
            if pipe.get("pipe_type") == "fire":
                seg = _pipe_segment(e, geom_settings)
                if seg:
                    fire_segs.append(seg)
        rooms = []
        for s in sized:
            _sg = space_geom.get(s.GlobalId, (None, 0.0, None))
            area = _sg[1]
            widths = None
            if door_meta:  # model has doors: report real per-room door data
                widths = [door_meta[g] for g in door_room.get(s.GlobalId, set()) if g in door_meta]
            _hull = _sg[0]
            _doors = [door_geom[g][1] for g in door_room.get(s.GlobalId, set())
                      if g in door_geom and door_geom[g][1]]
            _mrt = _max_room_travel(_doors, _hull, scale)
            _cent = _sg[2]
            _spr = None
            if fire_segs and _cent:
                _near = min(_dist_pt_seg((_cent[0], _cent[1]), a, b) for a, b in fire_segs)
                _spr = bool(_near <= 2.0)
            room = _space_to_room(s, area, ref_map.get(s.GlobalId, ""), widths,
                                  travel.get(s.GlobalId), _hull, _mrt, _spr)
            # unknown values are left absent (-> clean "未检查（缺字段）" coverage)
            # rather than a None that floods "数据缺失" per room.
            if _mrt is None:
                room.pop("max_room_travel_dist_m", None)
            if _spr is None:
                room.pop("has_sprinkler", None)
            if exit_sign_rooms:
                room["has_exit_sign"] = (s.Name or "?") in exit_sign_rooms
            rooms.append(room)

        n_pipe_fit = len(pipe_fittings)
        n_pipes = len(pipes)
        n_ducts = len(ducts)
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
                "footings": types.get("IfcFooting", 0),
                "pipe_fittings": n_pipe_fit,
                "pipes": n_pipes,
                "ducts": n_ducts,
                "column_sections": col_sec,
                "beam_sections": beam_sec,
                "slab_thicknesses": slab_th,
                "stairs": types.get("IfcStair", 0),
                "ramps": types.get("IfcRamp", 0) + types.get("IfcRampFlight", 0),
                "ramp_slopes": sorted(ramp_slopes),
                "railings": len(railing_elems),
                "railing_heights": sorted(railing_heights),
                "sanitary_fixtures": types.get("IfcSanitaryTerminal", 0),
                "air_terminals": types.get("IfcAirTerminal", 0),
                "outlets": types.get("IfcOutlet", 0),
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
            "pipe_fittings": pipe_fittings,
            "ducts": ducts,
            "railings": railings,
            "electrical_equipment": equip,
            "electrical_elements": electrical,
        })

    footprint = max((f["footprint_area_sqm"] for f in floors), default=0.0)
    fire_elevators, fire_extinguishers = _building_fire_stats(m)
    return {
        "source": "ifc",
        "file_name": Path(path).name,
        "project_name": project_name,
        "storey_count": len(floors),
        "building_footprint_area_sqm": footprint,
        "total_rooms": sum(len(f["rooms"]) for f in floors),
        "building_fire_stats": {"fire_elevators": fire_elevators,
                                "fire_extinguishers": fire_extinguishers},
        "scale_info": {
            "world_scale": scale,
            "declared_scale": declared_scale,
            "elev_scale": elev_scale,
            "bbox_scale": bbox_scale,
            "profile_scale": profile_scale,
            "profile_scale_confident": profile_scale_confident,
            "profile_scale_diag": profile_scale_diag,
        },
        "pipe_topology": {
            "networks": topology.get("networks", []),
            "member_count": topology.get("member_count", 0),
            "systems": sorted(system_map.keys()),
        },
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
    stats = struct.get("building_fire_stats") or {}
    any_fire_pipe = any(p.get("pipe_type") == "fire"
                        for f in struct.get("floors", []) for p in f.get("pipes", []))
    any_fire_alarm = any(
        any(k in (el.get("name") or "").lower() for k in ("alarm", "smoke", "感烟", "报警"))
        for f in struct.get("floors", []) for el in f.get("electrical_elements", []))
    bp = {
        "total_floors": struct.get("storey_count", len(floors)),
        "occupancy_type": "office",
        "ground_floor_exit_width_m": 2.4,
        "fire_pool_volume_m3": 160.0,
        "transformer_capacity_kw": 650.0,
        "emergency_power_duration_min": 60.0,
        "fire_elevator_count": stats.get("fire_elevators", 0),
        "fire_extinguisher_count": stats.get("fire_extinguishers", 0),
        "has_sprinkler_system": any_fire_pipe,
        "has_fire_alarm": any_fire_alarm,
    }
    if all_ramp_slopes:
        bp["max_ramp_slope"] = max(all_ramp_slopes)
    return {
        "project_name": struct.get("project_name") or "BIM Building",
        "source": "ifc",
        "building_params": bp,
        "floors": floors,
    }
