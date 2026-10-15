# -*- coding: utf-8 -*-
"""Semantic-enrichment before/after accuracy benchmark.

Runs the SAME multilingual gold set two ways:
  * baseline = deterministic keyword classifier only (what the BIM Reader did
    before the AI layer)
  * enriched = keyword classifier + the invisible AI semantic layer

Metrics per category (rooms / structural-element materials):
  accuracy      predictions equal to gold / total  (gold 'Unknown' counts — it
                is the CORRECT answer for numeric codes / residential types /
                generic members that carry no evidence)
  resolved      non-Unknown predictions / total (coverage)
  harmful_guess gold is Unknown but the model predicted a real category
                (= hallucinating a function/material with no evidence) — the
                key safety metric, must stay ~0
  recovered     baseline missed (Unknown/wrong) but enriched is correct on a
                gold item that genuinely has a category (real AI value)

Usage:
    python scripts/benchmark_enrichment.py            # live AI (uses API/cache)
    python scripts/benchmark_enrichment.py --offline  # keyword baseline only

Gold: scripts/semantic_gold.json
"""
import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bim.extractor import _classify_room_type
from agents.enricher import classify_material, enrich_review_data

GOLD_PATH = REPO / "scripts" / "semantic_gold.json"
UNKNOWN = {"room": "Unknown", "element": "unknown"}


def load_gold():
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def build_synthetic_bdata(gold):
    rooms, elements = [], []
    for i, c in enumerate(gold["rooms"]):
        rooms.append({
            "id": f"gr{i}", "name": c["name"],
            "type": _classify_room_type(c["name"]),
        })
    for i, c in enumerate(gold["elements"]):
        elements.append({
            "id": f"ge{i}", "name": c["name"],
            "element_type": c["element_type"], "material": c["material"],
        })
    return {"source": "ifc", "floors": [{
        "floor_id": "F1", "floor_name": "bench",
        "rooms": rooms, "structural_elements": elements, "pipes": [],
    }]}


def baseline_predictions(bdata):
    rooms = {r["id"]: r["type"] for r in bdata["floors"][0]["rooms"]}
    elems = {e["id"]: classify_material(e.get("material"))
             for e in bdata["floors"][0]["structural_elements"]}
    return rooms, elems


def enriched_predictions(bdata):
    enrich_review_data(bdata)
    rooms = {r["id"]: r["type"] for r in bdata["floors"][0]["rooms"]}
    elems = {e["id"]: e.get("material_class", "unknown")
             for e in bdata["floors"][0]["structural_elements"]}
    return rooms, elems, bdata.get("_enrichment", {})


def score(cases, pred, kind, id_prefix):
    unk = UNKNOWN[kind]
    rows = []
    n = len(cases)
    correct = resolved = harmful = recovered_correct = 0
    base_field = "base_" + kind
    for i, c in enumerate(cases):
        cid = f"{id_prefix}{i}"
        p = pred.get(cid, unk)
        gold = c["gold"]
        ok = p == gold
        correct += ok
        resolved += p != unk
        harmful += (gold == unk and p != unk)
        rows.append({
            "name": c["name"], "gold": gold, "pred": p,
            "ok": ok, "harmful_guess": gold == unk and p != unk,
        })
    # precision among cases the classifier committed to a real category
    resolved_correct = sum(1 for r in rows if r["pred"] != UNKNOWN[kind] and r["ok"])
    resolved_precision = round(resolved_correct / resolved, 3) if resolved else None
    return {
        "n": n,
        "accuracy": round(correct / n, 3) if n else None,
        "resolved_rate": round(resolved / n, 3) if n else None,
        "resolved_precision": resolved_precision,
        "harmful_guesses": harmful,
        "rows": rows,
    }


def delta(base_res, enr_res, cases, id_prefix):
    """How many gold-real categories baseline missed but enriched recovered,
    and how many baseline-correct enriched broke."""
    recovered = broke = 0
    unk = None
    for i, c in enumerate(cases):
        cid = f"{id_prefix}{i}"
        b = next(r for r in base_res["rows"] if r["name"] == c["name"])
        e = next(r for r in enr_res["rows"] if r["name"] == c["name"])
        if not b["ok"] and e["ok"]:
            recovered += 1
        if b["ok"] and not e["ok"]:
            broke += 1
    return recovered, broke


def print_block(title, base, enr, recovered, broke):
    print("\n" + "=" * 72)
    print(title)
    print("-" * 72)
    print(f"{'name':38} {'gold':15} {'base':15} {'enriched':15} {'ok'}")
    for br, er in zip(base["rows"], enr["rows"]):
        mark = "OK " if er["ok"] else ("!! " if er["harmful_guess"] else "x  ")
        print(f"{br['name'][:36]:38} {br['gold'][:14]:15} "
              f"{br['pred'][:14]:15} {er['pred'][:14]:15} {mark}")
    print("-" * 72)
    bp = f"{base['resolved_precision']:.0%}" if base['resolved_precision'] is not None else "-"
    ep = f"{enr['resolved_precision']:.0%}" if enr['resolved_precision'] is not None else "-"
    print(f"  accuracy        : {base['accuracy']:.1%}  ->  {enr['accuracy']:.1%}")
    print(f"  resolved rate   : {base['resolved_rate']:.1%}  ->  {enr['resolved_rate']:.1%}  (coverage)")
    print(f"  resolved precision: {bp}  ->  {ep}  (of real categories assigned, share correct)")
    print(f"  harmful guesses : {base['harmful_guesses']}  ->  {enr['harmful_guesses']}  (must stay ~0)")
    print(f"  recovered by AI : {recovered}    broken by AI: {broke}  (must stay 0)")


def write_csv(path, cases, base, enr):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["name", "gold", "before_keyword", "after_keyword_plus_AI",
                    "correct_after", "changed", "harmful_guess"])
        for c, br, er in zip(cases, base["rows"], enr["rows"]):
            w.writerow([c["name"], c["gold"], br["pred"], er["pred"],
                        int(er["ok"]), int(br["pred"] != er["pred"]),
                        int(er["harmful_guess"])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="keyword baseline only (no AI call)")
    ap.add_argument("--save", default="", help="optional JSON report path")
    args = ap.parse_args()

    gold = load_gold()
    base_bd = build_synthetic_bdata(gold)
    base_rooms, base_elems = baseline_predictions(base_bd)

    br = score(gold["rooms"], base_rooms, "room", "gr")
    be = score(gold["elements"], base_elems, "element", "ge")

    report = {"mode": "offline" if args.offline else "live-ai"}
    if args.offline:
        print("OFFLINE — keyword baseline only (AI layer not called)\n")
        for title, res in (("ROOMS (keyword baseline)", br),
                           ("ELEMENT MATERIAL (keyword baseline)", be)):
            print("=" * 72); print(title)
            for r in res["rows"]:
                print(f"  {r['name'][:36]:38} gold={r['gold'][:12]:13} pred={r['pred']}")
            print(f"  accuracy={res['accuracy']:.1%} resolved={res['resolved_rate']:.1%} "
                  f"harmful={res['harmful_guesses']}")
        report["baseline"] = {"rooms": {k: v for k, v in br.items() if k != "rows"},
                              "elements": {k: v for k, v in be.items() if k != "rows"}}
    else:
        enr_bd = build_synthetic_bdata(gold)
        enr_rooms, enr_elems, ledger = enriched_predictions(enr_bd)
        er = score(gold["rooms"], enr_rooms, "room", "gr")
        ee = score(gold["elements"], enr_elems, "element", "ge")
        rec_r, broke_r = delta(br, er, gold["rooms"], "gr")
        rec_e, broke_e = delta(be, ee, gold["elements"], "ge")
        print_block("ROOM TYPE — keyword (before) vs keyword+AI (after)", br, er, rec_r, broke_r)
        print_block("ELEMENT MATERIAL — keyword (before) vs keyword+AI (after)",
                    be, ee, rec_e, broke_e)
        print("\nLLM used:", ledger.get("llm_used"), "| stats:", ledger.get("stats"))
        report.update({
            "enrichment_stats": ledger.get("stats"),
            "llm_used": ledger.get("llm_used"),
            "rooms": {"baseline": {k: v for k, v in br.items() if k != "rows"},
                      "enriched": {k: v for k, v in er.items() if k != "rows"},
                      "recovered": rec_r, "broken": broke_r},
            "elements": {"baseline": {k: v for k, v in be.items() if k != "rows"},
                         "enriched": {k: v for k, v in ee.items() if k != "rows"},
                         "recovered": rec_e, "broken": broke_e},
        })

    if args.save:
        out_dir = Path(args.save).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print("\nsaved:", args.save)
        if not args.offline:
            for cat, cases, base, enr in (
                ("rooms", gold["rooms"], br, er),
                ("elements", gold["elements"], be, ee),
            ):
                p = out_dir / f"semantic_{cat}.csv"
                write_csv(p, cases, base, enr)
                print("saved:", p)


if __name__ == "__main__":
    main()
