"""Run benchmark on all IFC files recursively under test-suites/.

Aggregates results into one CSV + one JSON per category, plus T/Q/P scorecards.
Usage: python scripts/run_full_benchmark.py <suites_dir> [--standard cn] [--out outdir]
"""
import csv
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from scripts.benchmark_ifc import benchmark_file  # noqa: E402


def find_ifc_files(base_dir: Path):
    return sorted(p for p in base_dir.rglob("*.ifc") if "temp_" not in str(p))


def category_of(path: Path, base: Path) -> str:
    rel = path.relative_to(base)
    parts = rel.parts
    # official/IFC4/xxx.ifc → "official/IFC4"
    # real-project/xxx.ifc → "real-project"
    # mep/hvac/xxx.ifc → "mep/hvac"
    if len(parts) >= 3:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("suites_dir", help="root dir containing test suite subdirs")
    ap.add_argument("--standard", default="cn")
    ap.add_argument("--out", default="output/benchmark_0908")
    args = ap.parse_args()

    base = Path(args.suites_dir)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    files = find_ifc_files(base)
    print(f"Found {len(files)} .ifc files under {base}")

    reports = []
    for i, p in enumerate(files, 1):
        cat = category_of(p, base)
        print(f"\n[{i}/{len(files)}] {cat} / {p.name}")
        t0 = time.time()
        r = benchmark_file(p, args.standard)
        r["category"] = cat
        r["full_path"] = str(p)
        elapsed = time.time() - t0
        print(f"    score={r.get('score',0):.1f}  grade={r.get('grade','?')}  "
              f"parse={r.get('parse_secs',0):.1f}s  wall={elapsed:.1f}s")
        reports.append(r)

    # ---- per-category JSON ----
    by_cat = {}
    for r in reports:
        by_cat.setdefault(r["category"], []).append(r)
    for cat, reps in by_cat.items():
        cat_dir = outdir / cat.replace("/", "_")
        cat_dir.mkdir(parents=True, exist_ok=True)
        for r in reps:
            fname = Path(r["full_path"]).stem + ".json"
            (cat_dir / fname).write_text(
                json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- summary CSV ----
    csv_path = outdir / "summary.csv"
    cols = ["category", "file", "schema", "size_mb", "score", "grade",
            "A_robust", "B_extraction", "C_fieldcov",
            "D_accuracy", "E_ruleactivation", "F_perf",
            "qa_score", "storeys", "rooms", "issues", "not_checked",
            "parse_secs"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in reports:
            ax = r.get("axes", {})
            w.writerow([
                r.get("category", ""), r["file"], r.get("schema", ""),
                r.get("size_mb", 0), r.get("score", 0), r.get("grade", ""),
                round(ax.get("A", {}).get("score", 0), 1),
                round(ax.get("B", {}).get("score", 0), 1),
                round(ax.get("C", {}).get("score", 0), 1),
                round(ax.get("D", {}).get("score", 0), 1),
                round(ax.get("E", {}).get("score", 0), 1),
                round(ax.get("F", {}).get("score", 0), 1),
                r.get("qa_score", ""), r.get("storeys", ""),
                r.get("rooms", ""), r.get("issues", ""),
                r.get("not_checked", ""), r.get("parse_secs", ""),
            ])

    # ---- full JSON ----
    (outdir / "all_reports.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- overview stats ----
    n = len(reports)
    avg_score = sum(r["score"] for r in reports) / n if n else 0
    print(f"\n{'='*60}")
    print(f"DONE: {n} files, mean score = {avg_score:.1f}")
    print(f"CSV: {csv_path}")
    print(f"JSON reports: {outdir}/")

    # Print per-category averages
    print(f"\n--- Per-category averages ---")
    for cat in sorted(by_cat.keys()):
        reps = by_cat[cat]
        avg = sum(r["score"] for r in reps) / len(reps)
        avg_a = sum(r["axes"]["A"]["score"] for r in reps) / len(reps)
        avg_b = sum(r["axes"]["B"]["score"] for r in reps) / len(reps)
        avg_e = sum(r["axes"]["E"]["score"] for r in reps) / len(reps)
        print(f"  {cat:28s}  n={len(reps):2d}  "
              f"avg={avg:5.1f}  A={avg_a:3.0f}  B={avg_b:3.0f}  E={avg_e:3.0f}")


if __name__ == "__main__":
    main()
