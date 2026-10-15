"""IFC batch benchmark — measure how completely ArchCheck reads a set of IFC models.

For every .ifc in a directory, run the full pipeline and score it on 6 axes:

  A. Robustness       (20%)  — opens + parses + reviews without crashing
  B. Extraction       (25%)  — of the elements physically in the model, how many
                               the extractor emits (per class, min(1, got/have))
  C. Field coverage   (20%)  — for rules that judged anything, share of elements
                               that actually carried a value (judged/(judged+null))
  D. Accuracy proxy   (15%)  — extracted dimensions fall in plausible real-world
                               ranges (diameter/duct/door/area). Honest label: this
                               is a sanity proxy, not a ground-truth comparison —
                               true accuracy needs reference models with Qto.
  E. Rule activation  (15%)  — share of the standard's rules that judged >=1 element
  F. Performance      ( 5%)  — parse seconds per megabyte, mapped to 0-100

Output per model: JSON under --out; console table; plus one summary CSV row
per model. A model that cannot open is scored 0 on A-E with the exception noted.

Usage:
    python scripts/benchmark_ifc.py <ifc|dir> [--standard cn] [--out outdir]
"""
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import ifcopenshell

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from bim.parser import parse_ifc                       # noqa: E402
from bim.extractor import build_review_data            # noqa: E402
from core import engine                                # noqa: E402

WEIGHTS = {"A": 0.20, "B": 0.25, "C": 0.20, "D": 0.15, "E": 0.15, "F": 0.05}

# --- entity buckets: how the extractor's floor counters map to model counts ---
# extracted_field: which structure{} counter the extractor fills
# Note: by_type() already includes subclasses, so list only the base type
# (IfcWall covers IfcWallStandardCase; IfcSlab covers IfcSlabStandardCase…).
BUCKETS = [
    ("wall",   ["IfcWall"], "walls"),
    ("door",   ["IfcDoor"], "doors"),
    ("window", ["IfcWindow"], "windows"),
    ("column", ["IfcColumn"], "columns"),
    ("beam",   ["IfcBeam"], "beams"),
    ("slab",    ["IfcSlab"], "slabs"),
    ("footing", ["IfcFooting"], "footings"),
    ("stair",   ["IfcStair"], "stairs"),
    ("railing", ["IfcRailing"], "railings"),
    ("pipe",    ["IfcPipeSegment"], "pipes"),
    ("pipe_fitting", ["IfcPipeFitting"], "pipe_fittings"),
    ("duct",   ["IfcDuctSegment"], "ducts"),
    ("sanitary", ["IfcSanitaryTerminal"], "sanitary_fixtures"),
    ("air_terminal", ["IfcAirTerminal"], "air_terminals"),
    ("outlet", ["IfcOutlet"], "outlets"),
]


def _count_types(m, type_names):
    total = 0
    for t in type_names:
        try:
            total += len(m.by_type(t))
        except Exception:
            pass
    if not total and type_names[0] == "IfcPipeSegment":
        # IFC2X3 / early IFC4 files use generic IfcFlowSegment for pipes
        try:
            flow = len(m.by_type("IfcFlowSegment"))
            duct = 0
            try:
                duct = len(m.by_type("IfcDuctSegment"))
            except Exception:
                pass
            total = flow - duct
        except Exception:
            pass
    if not total and type_names[0] == "IfcPipeFitting":
        try:
            total = len(m.by_type("IfcFlowFitting"))
        except Exception:
            pass
    return total


def _plausible_share(values, lo, hi):
    if not values:
        return None
    return sum(1 for v in values if v is not None and lo <= v <= hi) / len(values)


def _plausible_many(checks):
    """Aggregate a list of (plausible_share_or_None) across measurement kinds.
    Only kinds that actually produced samples count toward the mean — a model
    with no pipes is not punished for its lack of pipes, but its real
    measurements (room area, door widths…) still are."""
    shares = [c for c in checks if c is not None]
    if not shares:
        return None
    return sum(shares) / len(shares)


# ===================================================================== axes ==


def axis_robustness(exc, floors, qa_fatal):
    """A. 100 = full pipeline OK; content gaps (fatal QA) cap at 70."""
    if exc:
        return 0.0, f"parse exception: {type(exc).__name__}"
    if not floors:
        return 60.0, "parsed but no floors extracted"
    if qa_fatal:
        return 70.0, "parsed; QA fatal (content missing, review blocked)"
    return 100.0, "opened / parsed / reviewed OK"


def axis_extraction(m, struct):
    """B. Per entity class, share of model elements the extractor emitted."""
    per_floor_structure = [f.get("structure") or {} for f in struct.get("floors", [])]
    ratios = []
    details = []
    for label, type_names, field in BUCKETS:
        have_model = _count_types(m, type_names)
        if have_model <= 0:
            continue  # model has none of these — not a failure to miss them
        got = sum((s.get(field) or 0) for s in per_floor_structure)
        ratio = min(1.0, got / have_model)
        ratios.append(ratio)
        details.append(f"{label} {got}/{have_model}")
    if not ratios:
        return 0.0, "no known element classes present", details
    return sum(ratios) / len(ratios) * 100.0, "; ".join(details), details


def axis_field_coverage(tally):
    """C. Share of judged elements that actually carried a value."""
    judged = sum(t["judged"] for t in tally.values())
    null = sum(t["null"] for t in tally.values())
    if judged + null == 0:
        return 0.0, "no rule judged any element (no data to assess)", None
    return judged / (judged + null) * 100.0, f"judged={judged} null={null}", None


def axis_accuracy(struct):
    """D. Sanity proxy: extracted dimensions fall in real-world ranges.

    Scored per *measurement kind present in the model*, across disciplines —
    building (room area / door width / corridor length), structural (column
    section / slab thickness), MEP (pipe diameter / duct section). A model is
    only judged on the kinds it actually carries, so a residential file with no
    pipes is not docked for missing them while its real measurements still count.
    """
    # collect samples per measurement kind
    kinds = {}  # kind -> list of 0/1 plausibility flags

    def add(kind, flags):
        kinds.setdefault(kind, []).extend(flags)

    for f in struct.get("floors", []):
        # --- building ---
        for r in f.get("rooms", []):
            a = r.get("room_area_sqm")
            if a is not None:
                add("room_area", [1.0 if 1.0 <= a <= 5000 else 0.0])
        door_ws = f.get("structure", {}).get("door_widths_m", [])
        for w in door_ws:
            add("door_width", [1.0 if 0.5 <= w <= 3.0 else 0.0])
        # --- structural ---
        for (mn, mx) in f.get("structure", {}).get("column_sections", []):
            add("column_section", [1.0 if 0.05 <= min(mn, mx) <= 3.0 else 0.0])
        for th in f.get("structure", {}).get("slab_thicknesses", []):
            add("slab_thickness", [1.0 if 0.05 <= th <= 1.0 else 0.0])
        for rh in f.get("structure", {}).get("railing_heights", []):
            add("railing_height", [1.0 if 0.3 <= rh <= 2.0 else 0.0])
        # --- MEP ---
        for p in f.get("pipes", []):
            d = p.get("diameter_m")
            if d is not None:
                add("pipe_diameter", [1.0 if 0.005 <= d <= 2.0 else 0.0])
        for d in f.get("ducts", []):
            if d.get("duct_width_m"):
                add("duct_width", [1.0 if 0.03 <= d["duct_width_m"] <= 4.0 else 0.0])
            if d.get("duct_height_m"):
                add("duct_height", [1.0 if 0.02 <= d["duct_height_m"] <= 4.0 else 0.0])

    if not kinds:
        return 50.0, "no measurable dimensions in model", None
    per_kind = {k: sum(v) / len(v) for k, v in kinds.items()}
    score = sum(per_kind.values()) / len(per_kind) * 100.0
    n_measured = sum(len(v) for v in kinds.values())
    detail = "; ".join(f"{k}={s:.0%}" for k, s in sorted(per_kind.items()))
    return score, f"{detail} ({n_measured} measured)", per_kind


def axis_rule_activation(tally, rules, struct):
    """E. Of the standard's rules that the MODEL can possibly exercise (the
    model carries that discipline's data), how many judged at least one element.

    Using only rules whose scope the model actually contains avoids punishing a
    specialist model (e.g. MEP-only, no rooms) for the 20 room-based civil rules
    that can never fire — that is a model-content fact, not an extraction defect.
    Both the adjusted and the raw share are reported.
    """
    applicable, judged_ids = [], set()
    for rule in rules:
        pref = rule.get("_prefix")
        if not _discipline_present(struct, pref):
            continue
        applicable.append(rule)
        if tally.get(rule["id"], {}).get("judged", 0) > 0:
            judged_ids.add(rule["id"])
    raw_applicable = len(rules)
    raw_judged = sum(1 for r in rules
                     if tally.get(r["id"], {}).get("judged", 0) > 0)
    if not applicable:
        return 0.0, "no applicable rules (model lacks every discipline's data)", None
    adjusted = len(judged_ids) / len(applicable) * 100.0
    detail = (f"{len(judged_ids)}/{len(applicable)} judged "
              f"(raw {raw_judged}/{raw_applicable})")
    return adjusted, detail, None


def _discipline_present(struct, prefix):
    """Whether the parsed model carries enough data for a discipline's rules."""
    floors = struct.get("floors", [])
    if prefix in ("civil", "accessibility"):
        return any(f.get("rooms") for f in floors)
    if prefix == "eee":
        return any(f.get("electrical_elements") or f.get("electrical_equipment")
                   for f in floors)
    if prefix == "structural":
        return any(f.get("structural_elements") for f in floors)
    if prefix == "mep":
        return any(f.get("pipes") or f.get("ducts") or f.get("pipe_fittings")
                   for f in floors)
    if prefix == "building":
        return bool(struct.get("floors")) or bool(struct.get("building_params"))
    return True  # scope/zone unknown — assume applicable


def axis_performance(secs, mb):
    """F. parse seconds per megabyte → 0-100 (<=2 s/MB full marks, >20 s/MB → 0)."""
    if mb <= 0:
        return 100.0, "empty file"
    s_per_mb = secs / mb
    score = 100.0 * max(0.0, min(1.0, (20.0 - s_per_mb) / 18.0))
    return score, f"{s_per_mb:.2f} s/MB"


def _grade(total):
    if total >= 90:
        return "S"
    if total >= 80:
        return "A"
    if total >= 65:
        return "B"
    if total >= 50:
        return "C"
    return "D"


# ===================================================================== runner ==


def benchmark_file(path, standard_id="cn"):
    """Run the full pipeline on one file, return a report dict."""
    path = str(path)
    mb = Path(path).stat().st_size / (1024 * 1024)
    start = time.time()
    report = {"file": Path(path).name, "schema": None, "size_mb": round(mb, 2)}
    try:
        m = ifcopenshell.open(path)
        report["schema"] = m.schema
        struct = parse_ifc(path)
        parse_secs = time.time() - start
    except Exception as exc:                      # noqa: BLE001
        report["score"] = 0.0
        report["grade"] = "D"
        report["axes"] = {
            "A": {"score": 0.0, "detail": f"open/parse failed: {exc}"}}
        for ax in "BCDEF":
            report["axes"][ax] = {"score": 0.0, "detail": "not reached"}
        report["error"] = str(exc)
        return report

    floors = struct.get("floors", [])
    qa = struct.get("qa") or {}
    bdata = build_review_data(struct)
    rev = engine.run_review_with_standard(standard_id, bdata)
    tally = rev.get("rule_tally", {})
    rules = _load_all_rules(standard_id)

    axes = {}
    axes["A"] = {"score": axis_robustness(None, floors, qa.get("fatal"))[0],
                 "detail": axis_robustness(None, floors, qa.get("fatal"))[1]}
    ax_b = axis_extraction(m, struct)
    axes["B"] = {"score": ax_b[0], "detail": ax_b[1]}
    ax_c = axis_field_coverage(tally)
    axes["C"] = {"score": ax_c[0], "detail": ax_c[1]}
    axes["D"] = {"score": axis_accuracy(struct)[0], "detail": axis_accuracy(struct)[1]}
    axes["E"] = {"score": axis_rule_activation(tally, rules, struct)[0],
                 "detail": axis_rule_activation(tally, rules, struct)[1]}
    axes["F"] = {"score": axis_performance(parse_secs, mb)[0],
                 "detail": axis_performance(parse_secs, mb)[1]}

    total = sum(WEIGHTS[ax] * axes[ax]["score"] for ax in "ABCDEF")
    report.update({
        "qa_score": qa.get("score"),
        "qa_fatal": qa.get("fatal"),
        "storeys": len(floors),
        "rooms": struct.get("total_rooms", 0),
        "issues": len(rev.get("all_issues", [])),
        "not_checked": len(rev.get("coverage_findings", [])),
        "parse_secs": round(parse_secs, 2),
        "entity_coverage": qa.get("entity_coverage"),
        "scale_info": struct.get("scale_info"),
        "axes": axes,
        "score": round(total, 1),
        "grade": _grade(total),
    })
    return report


def _load_all_rules(standard_id):
    std = engine.load_standard(standard_id)
    rules = []
    for key in ("civil", "eee", "building", "structural", "mep", "accessibility"):
        for r in (std.get(key) or []):
            rr = dict(r)
            rr["_prefix"] = key
            rules.append(rr)
    return rules


# ===================================================================== output ==


def _console_row(r):
    ax = r.get("axes", {})
    return (f"{r['file'][:34]:34s} {r.get('schema','?'):8s} "
            f"score={r.get('score',0):5.1f} {r.get('grade','?'):1s}  "
            f"A={ax.get('A',{}).get('score',0):3.0f} "
            f"B={ax.get('B',{}).get('score',0):3.0f} "
            f"C={ax.get('C',{}).get('score',0):3.0f} "
            f"D={ax.get('D',{}).get('score',0):3.0f} "
            f"E={ax.get('E',{}).get('score',0):3.0f} "
            f"F={ax.get('F',{}).get('score',0):3.0f}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Benchmark IFC reading coverage")
    ap.add_argument("target", help="an .ifc file or a directory of .ifc files")
    ap.add_argument("--standard", default="cn", help="rules standard (cn/sg)")
    ap.add_argument("--out", default=None, help="output dir for JSON + CSV")
    args = ap.parse_args()

    target = Path(args.target)
    files = [target] if target.is_file() else sorted(target.glob("*.ifc"))
    if not files:
        print(f"no .ifc files under {target}")
        return

    outdir = None
    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)

    reports = []
    for p in files:
        r = benchmark_file(p, args.standard)
        reports.append(r)
        print(_console_row(r))
        # per-axis detail lines for the big axes
        print(f"    B: {r['axes']['B']['detail']}")
        print(f"    C: {r['axes']['C']['detail']}")
        print(f"    E: {r['axes']['E']['detail']}   F: {r['axes']['F']['detail']}")
        if r.get("error"):
            print(f"    ERROR: {r['error']}")
        if outdir:
            (outdir / f"{Path(p).stem}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    # summary CSV
    if reports and outdir:
        csv_path = outdir / "summary.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["file", "schema", "size_mb", "score", "grade",
                        "A_robust", "B_extraction", "C_fieldcov",
                        "D_accuracy", "E_ruleactivation", "F_perf",
                        "qa_score", "storeys", "rooms", "issues", "not_checked"])
            for r in reports:
                ax = r.get("axes", {})
                w.writerow([r["file"], r.get("schema", ""), r.get("size_mb", 0),
                            r.get("score", 0), r.get("grade", ""),
                            round(ax.get("A", {}).get("score", 0), 1),
                            round(ax.get("B", {}).get("score", 0), 1),
                            round(ax.get("C", {}).get("score", 0), 1),
                            round(ax.get("D", {}).get("score", 0), 1),
                            round(ax.get("E", {}).get("score", 0), 1),
                            round(ax.get("F", {}).get("score", 0), 1),
                            r.get("qa_score", ""), r.get("storeys", ""),
                            r.get("rooms", ""), r.get("issues", ""),
                            r.get("not_checked", "")])
        print(f"\nsummary CSV: {csv_path}")

    if reports:
        avg = sum(r["score"] for r in reports) / len(reports)
        print(f"\nmean score over {len(reports)} file(s): {avg:.1f}")


if __name__ == "__main__":
    main()
