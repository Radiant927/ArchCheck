# -*- coding: utf-8 -*-
"""B1 — 31 模型大样本语义层实测。

对 bim/test-suites/ 下的真实模型逐个跑「解析 → 语义富化」，
统计每个模型的：候选数 / AI 救回 / 诚实弃权 / 越界拒绝 / 缓存命中，
并汇总三类语义（房型 / 材料 / 管道）在大样本上是否成立。

用法：
    python scripts/benchmark_enrichment_batch.py                 # 全部
    python scripts/benchmark_enrichment_batch.py --limit 5       # 前 5 个
    python scripts/benchmark_enrichment_batch.py --glob "real-project/*"
    python scripts/benchmark_enrichment_batch.py --save out.json
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bim.parser import parse_ifc, build_review_data
from agents.enricher import enrich_review_data
from core import engine
from core.engine import run_full_review

SUITES = REPO / "bim" / "test-suites"


def iter_models(pattern):
    return sorted(SUITES.glob(f"**/{pattern}.ifc" if not pattern.endswith(".ifc") else pattern))


def run_one(path):
    """跑单个模型，返回一行统计。"""
    row = {"model": path.name, "rel": str(path.relative_to(SUITES)),
           "ok": False, "error": ""}
    t0 = time.time()
    try:
        struct = parse_ifc(str(path))
    except Exception as ex:
        row["error"] = f"parse: {ex}"
        return row
    try:
        bdata = build_review_data(struct)
    except Exception as ex:
        row["error"] = f"build: {ex}"
        return row

    n_rooms = sum(len(f.get("rooms") or []) for f in bdata.get("floors", []))
    n_pipes = sum(len(f.get("pipes") or []) for f in bdata.get("floors", []))
    n_elems = sum(len(f.get("structural_elements") or []) for f in bdata.get("floors", []))
    row.update({"floors": len(bdata.get("floors", [])),
                "rooms": n_rooms, "pipes": n_pipes, "struct_elems": n_elems})

    try:
        enrich_review_data(bdata)
    except Exception as ex:
        row["error"] = f"enrich: {ex}"
        return row

    led = bdata.get("_enrichment", {})
    st = led.get("stats", {})
    row["stats"] = st
    row["llm_used"] = led.get("llm_used", False)

    # 富化后跑审查（验证「违规总数零回归」安全承诺的可比基线）
    try:
        res = run_full_review(bdata)
        row["issues"] = len(res.get("all_issues", []))
    except Exception as ex:
        row["error"] = f"review: {ex}"
        return row

    row["ok"] = True
    row["secs"] = round(time.time() - t0, 1)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="*.ifc", help="test-suites 下的文件名模式")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--save", default="output/enrichment/batch_run.json")
    args = ap.parse_args()

    engine.set_standard("cn")
    models = sorted(SUITES.glob(f"**/{args.glob}"))
    if args.limit:
        models = models[:args.limit]
    print(f"models: {len(models)}\n")

    rows = []
    tot = {"candidates": 0, "ai_resolved": 0, "ai_abstained": 0,
           "rejected": 0, "cached": 0, "rooms": 0, "elements": 0, "pipes": 0}
    for i, m in enumerate(models, 1):
        r = run_one(m)
        rows.append(r)
        s = r.get("stats") or {}
        for k in ("candidates", "ai_resolved", "ai_abstained", "rejected", "cached",
                  "rooms", "elements", "pipes"):
            tot[k] += s.get(k, 0)
        flag = "OK " if r["ok"] else "ERR"
        print(f"[{i}/{len(models)}] {flag} {r['rel']:52} "
              f"cand={s.get('candidates',0):3} resolved={s.get('ai_resolved',0):3} "
              f"abstain={s.get('ai_abstained',0):3} rej={s.get('rejected',0)} "
              f"cached={s.get('cached',0):3} issues={r.get('issues','-')} "
              f"{r.get('error','')}")

    print("\n" + "=" * 72)
    print("TOTAL across models")
    for k, v in tot.items():
        print(f"  {k:14}: {v}")
    n_used = sum(1 for r in rows if r.get("llm_used"))
    print(f"  models where LLM used: {n_used}/{len(rows)}")
    print(f"  models parsed OK      : {sum(1 for r in rows if r['ok'])}/{len(rows)}")

    out = {"totals": tot, "models": len(rows), "rows": rows}
    p = REPO / args.save
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nsaved:", p)


if __name__ == "__main__":
    main()
