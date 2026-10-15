"""Diagnose entity coverage gap — which IfcElement types exist in the model
but our extractor never reads.

For each model, list all IfcElement subclasses and compare against what the
extractor currently tracks. Output a ranked gap list and per-model CSV.

Usage: python scripts/diagnose_entity_coverage.py <ifc_dir> [--out outdir]
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ifcopenshell

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

# What the extractor currently handles (base types — by_type includes subclasses)
TRACKED_TYPES = {
    "IfcWall", "IfcDoor", "IfcWindow", "IfcColumn", "IfcBeam",
    "IfcSlab", "IfcStair", "IfcPipeSegment", "IfcPipeFitting",
    "IfcDuctSegment", "IfcDuctFitting", "IfcSpace",
    "IfcElectricAppliance", "IfcLightFixture",
    "IfcRamp", "IfcRoof", "IfcRailings",
    "IfcFurnishingElement",
}

ELEMENT_BASE = "IfcElement"


def all_element_types(model_path):
    """Return Counter of all IfcElement subclass instances in the model."""
    m = ifcopenshell.open(str(model_path))
    counter = Counter()
    # We have to enumerate all instances and check is_a() per instance because
    # by_type("IfcElement") would return subclasses but not break them down.
    for e in m.by_type(ELEMENT_BASE):
        counter[e.is_a()] += 1
    return counter


def is_tracked(ifc_type):
    """Check if an IFC type is covered by our extractor (via inheritance)."""
    # Quick path: exact match
    if ifc_type in TRACKED_TYPES:
        return True
    # We can't easily check inheritance without opening a model; approximate by
    # checking well-known subclasses against their base type prefix.
    known_subclass_map = {
        "IfcWallStandardCase": "IfcWall",
        "IfcCurtainWall": "IfcWall",
        "IfcWallElementedCase": "IfcWall",
        "IfcDoorStandardCase": "IfcDoor",
        "IfcDoorPanel": "IfcDoor",
        "IfcWindowStandardCase": "IfcWindow",
        "IfcColumnStandardCase": "IfcColumn",
        "IfcBeamStandardCase": "IfcBeam",
        "IfcSlabStandardCase": "IfcSlab",
        "IfcSlabElementedCase": "IfcSlab",
        "IfcStairFlight": "IfcStair",
        "IfcRampFlight": "IfcRamp",
        "IfcPipeSegment": "IfcPipeSegment",
        "IfcDuctSegment": "IfcDuctSegment",
    }
    if ifc_type in known_subclass_map:
        return True
    return False


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

    # aggregate across all models
    global_gap = Counter()  # type -> total count across all models
    models_with_type = Counter()  # type -> number of models that have it
    per_model_rows = []

    for f in files:
        try:
            types = all_element_types(f)
        except Exception as e:
            per_model_rows.append({"file": f.name, "error": str(e)})
            continue

        tracked_total = 0
        gap_total = 0
        gap_items = []
        for t, c in types.most_common():
            if is_tracked(t):
                tracked_total += c
            else:
                gap_total += c
                gap_items.append((t, c))
                global_gap[t] += c
                models_with_type[t] += 1

        total = tracked_total + gap_total
        coverage = tracked_total / total * 100 if total > 0 else 0
        per_model_rows.append({
            "file": f.name,
            "total_elements": total,
            "tracked": tracked_total,
            "gap": gap_total,
            "coverage_pct": round(coverage, 1),
            "gap_types": ", ".join(f"{t}({c})" for t, c in gap_items[:10]),
        })

    # --- output ---
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    # Per-model CSV
    csv_path = outdir / "entity_coverage_per_model.csv"
    cols = ["file", "total_elements", "tracked", "gap", "coverage_pct", "gap_types", "error"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in per_model_rows:
            w.writerow(r)

    # Global gap ranking
    gap_path = outdir / "entity_gap_ranking.csv"
    with open(gap_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["ifc_type", "total_count", "models_present", "category"])
        for t, c in global_gap.most_common():
            # rough category
            cat = "unknown"
            if any(k in t.lower() for k in ("stair", "ramp", "rail")):
                cat = "circulation"
            elif any(k in t.lower() for k in ("furnitur", "desk", "table", "chair")):
                cat = "furniture"
            elif any(k in t.lower() for k in ("door", "window")):
                cat = "opening"
            elif any(k in t.lower() for k in ("pipe", "duct", "flow", "fitting", "valve")):
                cat = "mep"
            elif any(k in t.lower() for k in ("column", "beam", "slab", "wall", "footing", "pile", "brace")):
                cat = "structural"
            elif any(k in t.lower() for k in ("roof", "ceiling", "floor")):
                cat = "envelope"
            elif any(k in t.lower() for k in ("electric", "lamp", "light", "switch", "outlet")):
                cat = "electrical"
            elif any(k in t.lower() for k in ("sanitary", "toilet", "sink", "wc", "tub", "shower")):
                cat = "sanitary"
            elif any(k in t.lower() for k in ("space", "zone")):
                cat = "space"
            w.writerow([t, c, models_with_type[t], cat])

    # Console summary
    print(f"\n{'='*60}")
    print("ENTITY COVERAGE GAP — TOP 20 UNTRACKED TYPES")
    print(f"{'='*60}")
    print(f"{'Type':35s} {'Count':>6s} {'Models':>6s}  Category")
    print("-" * 60)
    for t, c in global_gap.most_common(20):
        # re-calc cat for display
        cat = "unknown"
        if any(k in t.lower() for k in ("stair", "ramp", "rail")): cat = "circulation"
        elif any(k in t.lower() for k in ("furnitur", "desk", "table")): cat = "furniture"
        elif any(k in t.lower() for k in ("pipe", "duct", "flow", "fitting", "valve")): cat = "mep"
        elif any(k in t.lower() for k in ("column", "beam", "slab", "wall", "footing", "pile")): cat = "structural"
        elif any(k in t.lower() for k in ("roof", "ceiling")): cat = "envelope"
        elif any(k in t.lower() for k in ("electric", "lamp", "light")): cat = "electrical"
        elif any(k in t.lower() for k in ("sanitary", "toilet", "sink", "wc", "tub")): cat = "sanitary"
        elif any(k in t.lower() for k in ("space", "zone")): cat = "space"
        print(f"  {t:33s} {c:>6d} {models_with_type[t]:>6d}  {cat}")

    total_tracked = sum(1 for _ in TRACKED_TYPES)
    print(f"\nTracked types (base): {total_tracked}")
    print(f"Untracked types found: {len(global_gap)}")
    print(f"\nCSV: {csv_path}")
    print(f"Gap ranking: {gap_path}")


if __name__ == "__main__":
    main()
