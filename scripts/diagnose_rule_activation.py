"""Diagnose rule activation — which rules fire, which don't, and why.

For each rule in the standard, compute:
  - activation_rate:   share of applicable models where judged > 0
  - avg_judged:        average number of elements judged (across models that have the discipline)
  - avg_issues:        average number of issues found
  - skip_reason_breakdown:  why the rule skipped on each model

Output: rule_activation_breakdown.csv + skip_reason_summary.txt

Usage:
    python scripts/diagnose_rule_activation.py <reports_json> [--standard cn] [--out outdir]
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from core import engine                                # noqa: E402
from bim.parser import parse_ifc                       # noqa: E402
from bim.extractor import build_review_data            # noqa: E402


def load_standard_rules(standard_id):
    std = engine.load_standard(standard_id)
    rules = []
    for key in ("civil", "eee", "building", "structural", "mep", "accessibility"):
        for r in (std.get(key) or []):
            rr = dict(r)
            rr["_discipline"] = key
            rules.append(rr)
    return rules


def discipline_present(struct, prefix):
    """Same logic as benchmark_ifc.py _discipline_present."""
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
    return True


def diagnose_one_rule(rule_id, rule, models_data):
    """For one rule, compute activation stats across applicable models."""
    applicable = []  # list of (model_name, struct, review_result)
    not_applicable = []  # models lacking the discipline's data

    for model_name, data in models_data.items():
        struct = data["struct"]
        rev = data["review"]
        if discipline_present(struct, rule["_discipline"]):
            applicable.append((model_name, rev))
        else:
            not_applicable.append(model_name)

    tally_key = rule_id
    judged_models = 0
    issue_models = 0
    total_judged = 0
    total_issues = 0
    total_null = 0
    fired_detail = []  # (model_name, judged, issues, pass, null)

    for model_name, rev in applicable:
        tally = rev.get("rule_tally", {}).get(tally_key, {})
        judged = tally.get("judged", 0)
        issues = tally.get("issues", 0)
        null = tally.get("null", 0)
        passed = judged - issues
        total_judged += judged
        total_issues += issues
        total_null += null
        if judged > 0:
            judged_models += 1
            fired_detail.append((model_name, judged, issues, passed, null))
        if issues > 0:
            issue_models += 1

    n_applicable = len(applicable)
    activation_rate = (judged_models / n_applicable * 100) if n_applicable > 0 else 0

    return {
        "id": rule_id,
        "discipline": rule["_discipline"],
        "name": rule.get("name", rule.get("title", "")),
        "field": rule.get("field", ""),
        "applicable_models": n_applicable,
        "judged_models": judged_models,
        "activation_rate_pct": round(activation_rate, 1),
        "avg_judged": round(total_judged / judged_models, 1) if judged_models > 0 else 0,
        "avg_issues_per_model": round(total_issues / judged_models, 1) if judged_models > 0 else 0,
        "total_judged_across_models": total_judged,
        "total_issues_across_models": total_issues,
        "total_null_across_models": total_null,
        "issue_rate_pct": round(total_issues / total_judged * 100, 1) if total_judged > 0 else 0,
        "fired_models": ", ".join(m for m, _, _, _, _ in fired_detail[:5])
                        + (" ..." if len(fired_detail) > 5 else ""),
        "not_applicable_count": len(not_applicable),
    }


def load_all_model_data(ifc_dir: Path, standard_id):
    """Parse + review every IFC file, return dict of name -> {struct, review}."""
    import ifcopenshell

    ifc_files = sorted(ifc_dir.rglob("*.ifc"))
    ifc_files = [f for f in ifc_files if "temp_" not in str(f)]

    models = {}
    for i, p in enumerate(ifc_files, 1):
        name = p.stem
        print(f"  [{i}/{len(ifc_files)}] {name}")
        try:
            m = ifcopenshell.open(str(p))
            schema = m.schema
        except Exception as e:
            print(f"    SKIP (open failed): {e}")
            continue
        try:
            struct = parse_ifc(str(p))
            bdata = build_review_data(struct)
            rev = engine.run_review_with_standard(standard_id, bdata)
            models[name] = {
                "path": str(p),
                "schema": schema,
                "size_mb": p.stat().st_size / (1024*1024),
                "struct": struct,
                "review": rev,
            }
        except Exception as e:
            print(f"    SKIP (parse/review failed): {e}")
            continue
    return models


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc_dir", help="directory of IFC files to diagnose on")
    ap.add_argument("--standard", default="cn")
    ap.add_argument("--out", default="output/benchmark_0908")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    rules = load_standard_rules(args.standard)
    print(f"Loaded {len(rules)} rules from standard '{args.standard}'")

    print("Loading and reviewing all models...")
    models = load_all_model_data(Path(args.ifc_dir), args.standard)
    print(f"Successfully reviewed {len(models)} models\n")

    # Per-rule diagnosis
    rows = []
    for rule in rules:
        row = diagnose_one_rule(rule["id"], rule, models)
        rows.append(row)

    # Sort by activation rate ascending (worst first)
    rows.sort(key=lambda r: r["activation_rate_pct"])

    # Write CSV
    csv_path = outdir / "rule_activation_breakdown.csv"
    cols = list(rows[0].keys()) if rows else []
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # Discipline-level summary
    disc_stats = defaultdict(lambda: {"total": 0, "active": 0, "avg_activation": 0})
    for r in rows:
        d = r["discipline"]
        disc_stats[d]["total"] += 1
        if r["activation_rate_pct"] > 0:
            disc_stats[d]["active"] += 1
        disc_stats[d]["avg_activation"] += r["activation_rate_pct"]
    for d in disc_stats:
        n = disc_stats[d]["total"]
        disc_stats[d]["avg_activation"] = round(disc_stats[d]["avg_activation"] / n, 1) if n else 0

    # Dead rules (never fire on any applicable model)
    dead_rules = [r for r in rows if r["activation_rate_pct"] == 0 and r["applicable_models"] > 0]
    sleeping_rules = [r for r in rows if 0 < r["activation_rate_pct"] < 30]

    # Write text summary
    summary_lines = []
    summary_lines.append("=" * 70)
    summary_lines.append("RULE ACTIVATION DIAGNOSIS SUMMARY")
    summary_lines.append("=" * 70)
    summary_lines.append(f"Total rules: {len(rules)}")
    summary_lines.append(f"Models reviewed: {len(models)}")
    summary_lines.append("")

    summary_lines.append("--- By Discipline ---")
    summary_lines.append(f"{'Discipline':<15s} {'Rules':>5s} {'Active':>6s} {'AvgActiv%':>10s}")
    for d in sorted(disc_stats.keys()):
        s = disc_stats[d]
        summary_lines.append(f"{d:<15s} {s['total']:>5d} {s['active']:>6d} {s['avg_activation']:>10.1f}")
    summary_lines.append("")

    summary_lines.append(f"--- DEAD RULES ({len(dead_rules)}) — never fire on any applicable model ---")
    for r in dead_rules:
        summary_lines.append(f"  {r['id']:10s} [{r['discipline']:13s}] "
                             f"app={r['applicable_models']:2d}  "
                             f"{r['name'][:45]}")
        summary_lines.append(f"    field={r['field']}")
    summary_lines.append("")

    summary_lines.append(f"--- SLEEPING RULES ({len(sleeping_rules)}) — fire on <30% of applicable models ---")
    for r in sleeping_rules:
        summary_lines.append(f"  {r['id']:10s} [{r['discipline']:13s}] "
                             f"activation={r['activation_rate_pct']:5.1f}%  "
                             f"app={r['applicable_models']:2d}  "
                             f"{r['name'][:40]}")
    summary_lines.append("")

    summary_lines.append("--- Top 10 Most Active Rules ---")
    for r in sorted(rows, key=lambda x: x["activation_rate_pct"], reverse=True)[:10]:
        if r["activation_rate_pct"] > 0:
            summary_lines.append(f"  {r['id']:10s} [{r['discipline']:13s}] "
                                 f"activation={r['activation_rate_pct']:5.1f}%  "
                                 f"issues/avg={r['avg_issues_per_model']:.1f}  "
                                 f"{r['name'][:40]}")

    summary_text = "\n".join(summary_lines)
    (outdir / "rule_activation_summary.txt").write_text(summary_text, encoding="utf-8")

    print(summary_text)
    print(f"\nCSV: {csv_path}")
    print(f"Summary: {outdir / 'rule_activation_summary.txt'}")


if __name__ == "__main__":
    main()
