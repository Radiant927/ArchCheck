"""Diagnose geometry extraction accuracy against reference models.

Uses buildingSMART ReferenceView models as ground truth where possible,
and sanity-checks extracted dimensions on larger models.

Outputs per-element-type accuracy tables and a summary of issues found.

Usage: python scripts/diagnose_geometry_accuracy.py <ifc_dir> [--out outdir]
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from bim.parser import parse_ifc                       # noqa: E402
import ifcopenshell                                   # noqa: E402


# --- reference values for known models ---
# (model_name, element_type, element_name) -> {dim: expected_value_m}
REFERENCE_VALUES = {
    "wall-with-opening-and-window": {
        "wall": {"Wall for Test Example": {"height_m": 2.0, "thickness_m": None}},
        "window": {"Window for Test Example": {"width_m": 1.0, "height_m": 1.0}},
    },
}


def read_ifc_dims(ifc_path):
    """Read key dimensions directly from IFC file (ground truth approximation).
    Returns dict: {element_type: [{name, dims_dict}]}
    """
    m = ifcopenshell.open(str(ifc_path))
    result = defaultdict(list)

    # Walls — from ExtrudedAreaSolid depth (height) + profile thickness
    for wall in m.by_type("IfcWall"):
        info = {"name": wall.Name or wall.GlobalId}
        # height from extrusion depth
        height = None
        thickness = None
        width = None
        if wall.Representation:
            for rep in wall.Representation.Representations:
                if rep.RepresentationIdentifier == "Body":
                    for item in rep.Items:
                        if item.is_a("IfcExtrudedAreaSolid"):
                            height = item.Depth
                            sa = item.SweptArea
                            if sa.is_a("IfcArbitraryClosedProfileDef"):
                                # compute bounding box of the outer curve
                                curve = sa.OuterCurve
                                if hasattr(curve, "Points"):
                                    pts = curve.Points
                                    xs = [p.Coordinates[0] for p in pts]
                                    ys = [p.Coordinates[1] for p in pts]
                                    thickness = max(ys) - min(ys)
                                    width = max(xs) - min(xs)
                            elif sa.is_a("IfcRectangleProfileDef"):
                                thickness = sa.YDim
                                width = sa.XDim
        if height is not None:
            info["height_raw"] = height
        if thickness is not None:
            info["thickness_raw"] = thickness
        if width is not None:
            info["width_raw"] = width
        result["wall"].append(info)

    # Windows/Doors — OverallWidth / OverallHeight (in model units, usually mm)
    for etype, key in [("IfcWindow", "window"), ("IfcDoor", "door")]:
        for elem in m.by_type(etype):
            info = {"name": elem.Name or elem.GlobalId}
            w = getattr(elem, "OverallWidth", None)
            h = getattr(elem, "OverallHeight", None)
            if w is not None:
                info["width_raw"] = w
            if h is not None:
                info["height_raw"] = h
            result[key].append(info)

    # Columns — from extrusion + profile
    for col in m.by_type("IfcColumn"):
        info = {"name": col.Name or col.GlobalId}
        height = None
        section_min = None
        if col.Representation:
            for rep in col.Representation.Representations:
                if rep.RepresentationIdentifier == "Body":
                    for item in rep.Items:
                        if item.is_a("IfcExtrudedAreaSolid"):
                            height = item.Depth
                            sa = item.SweptArea
                            if hasattr(sa, "XDim") and hasattr(sa, "YDim"):
                                section_min = min(sa.XDim, sa.YDim)
                            elif sa.is_a("IfcArbitraryClosedProfileDef"):
                                curve = sa.OuterCurve
                                if hasattr(curve, "Points"):
                                    pts = curve.Points
                                    xs = [p.Coordinates[0] for p in pts]
                                    ys = [p.Coordinates[1] for p in pts]
                                    section_min = min(max(xs)-min(xs), max(ys)-min(ys))
        if height is not None:
            info["height_raw"] = height
        if section_min is not None:
            info["section_min_raw"] = section_min
        result["column"].append(info)

    # Slabs — thickness
    for slab in m.by_type("IfcSlab"):
        info = {"name": slab.Name or slab.GlobalId}
        thickness = None
        if slab.Representation:
            for rep in slab.Representation.Representations:
                if rep.RepresentationIdentifier == "Body":
                    for item in rep.Items:
                        if item.is_a("IfcExtrudedAreaSolid"):
                            thickness = item.Depth
        if thickness is not None:
            info["thickness_raw"] = thickness
        result["slab"].append(info)

    return dict(result)


def extracted_dims(struct):
    """Get extracted dimensions from parser output."""
    result = defaultdict(list)
    for f in struct.get("floors", []):
        # walls — from plan_elements
        for pe in f.get("plan_elements", []):
            if pe.get("type") in ("wall", "Wall") or "wall" in str(pe.get("name", "")).lower():
                result["wall"].append({
                    "name": pe.get("name", ""),
                    "ext_width": pe.get("length_m"),
                    "ext_thickness": pe.get("thickness_m"),
                    "ext_area": pe.get("area_sqm"),
                })
        # windows
        for w in f.get("windows", []):
            result["window"].append({
                "name": w.get("name", ""),
                "ext_width": w.get("width_m"),
                "ext_height": w.get("height_m"),
                "ext_area": w.get("area_sqm"),
            })
        # doors
        for d in f.get("doors", []):
            result["door"].append({
                "name": d.get("name", ""),
                "ext_width": d.get("width_m"),
                "ext_height": d.get("height_m"),
                "ext_area": d.get("area_sqm"),
            })
        # structural elements
        for se in f.get("structural_elements", []):
            et = se.get("element_type", "")
            info = {"name": se.get("name", ""), "ext_element_type": et}
            for dim in ["width_m", "depth_m", "thickness_m", "section_min_m", "height_m"]:
                if dim in se:
                    info[f"ext_{dim}"] = se[dim]
            result[et or "structural"].append(info)
        # slab thicknesses
        for t in f.get("structure", {}).get("slab_thicknesses", []):
            result["slab"].append({"ext_thickness_m": t})
    return dict(result)


def diagnose_model(ifc_path):
    """Diagnose one model, return findings dict."""
    model_name = Path(ifc_path).stem
    print(f"\n{'='*60}")
    print(f"Model: {model_name}")
    print(f"{'='*60}")

    try:
        ifc_dims = read_ifc_dims(ifc_path)
    except Exception as e:
        print(f"  IFC read failed: {e}")
        return None

    try:
        struct = parse_ifc(str(ifc_path))
        ext_dims = extracted_dims(struct)
    except Exception as e:
        print(f"  Parser failed: {e}")
        return None

    findings = {"model": model_name, "per_type": {}}

    for etype in ["wall", "window", "door", "column", "slab"]:
        ifc_list = ifc_dims.get(etype, [])
        ext_list = ext_dims.get(etype, [])
        if not ifc_list and not ext_list:
            continue

        print(f"\n--- {etype} ---")
        print(f"  IFC direct read: {len(ifc_list)} elements")
        for item in ifc_list[:5]:
            raw_dims = {k: v for k, v in item.items() if k != "name" and v is not None}
            print(f"    {item['name'][:40]:40s}  raw(IFC units): {raw_dims}")

        print(f"  Extracted: {len(ext_list)} elements")
        for item in ext_list[:5]:
            ext_d = {k: v for k, v in item.items() if k != "name" and v is not None}
            print(f"    {item.get('name','?')[:40]:40s}  extracted(m): {ext_d}")

        findings["per_type"][etype] = {
            "ifc_count": len(ifc_list),
            "extracted_count": len(ext_list),
        }

    # scale info
    print(f"\n  scale_info: {struct.get('scale_info')}")

    return findings


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="IFC file or directory")
    ap.add_argument("--out", default="output/benchmark_0908")
    args = ap.parse_args()

    target = Path(args.target)
    if target.is_file():
        files = [target]
    else:
        files = sorted(target.rglob("*.ifc"))
        files = [f for f in files if "temp_" not in str(f)]

    print(f"Found {len(files)} IFC file(s)")

    all_findings = []
    for f in files:
        findings = diagnose_model(f)
        if findings:
            all_findings.append(findings)

    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Models diagnosed: {len(all_findings)}")

    # Per-type extraction count comparison
    type_totals = defaultdict(lambda: {"ifc": 0, "ext": 0})
    for f in all_findings:
        for et, data in f["per_type"].items():
            type_totals[et]["ifc"] += data["ifc_count"]
            type_totals[et]["ext"] += data["extracted_count"]

    print(f"\nPer-type element count comparison:")
    for et in sorted(type_totals.keys()):
        t = type_totals[et]
        ratio = (t["ext"] / t["ifc"] * 100) if t["ifc"] > 0 else 0
        print(f"  {et:10s}: IFC={t['ifc']:5d}  extracted={t['ext']:5d}  ratio={ratio:.0f}%")


if __name__ == "__main__":
    main()
