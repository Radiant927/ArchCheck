# -*- coding: utf-8 -*-
"""End-to-end verification for the predictive rule layer.

Three groups:
  A. FZK zero-regression: 29 issues / 16-coverage baseline must hold, with the
     only delta being one MEP-PRED-001 NotChecked coverage finding.
  B. Positive path: risk-generator population reverse-assembled into a bdata
     fixture -> Predictive issues + ranked inspection list, sanity-scored on
     latent truth (C-index / top10 lift in the Phase-1 ballpark).
  C. Abstention: no data, missing service records, and small sample each yield
     NotChecked and zero fabricated predictions.
  D. Monitoring covariates: wall-thickness readings must lift C-index and the
     ranked-allocation lift well past the static-only fit, keep the ranking
     covering the whole cohort, and abstain when readings are incomplete or
     mix regimes.

Exit code is nonzero on the first failed assertion.
"""

import collections
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bim.parser import parse_ifc, build_review_data
from core.engine import set_standard, run_full_review
from risk.families import get_family
from risk.generator import (generate_population, annual_maintenance_log,
                            regime_measurements)
from risk.adapter import population_from_building, monitoring_measurements
from risk.survival import fit_cox, build_design_matrix
from risk.evaluate import concordance_index

set_standard("cn")

FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


BASELINE_RULES = collections.Counter({
    "ACC-003": 6, "BLD-001": 1, "BLD-002": 1, "BLD-003": 1, "BLD-004": 1,
    "BLD-007": 1, "BLD-008": 1, "BLD-009": 1, "CIVIL-003": 1, "CIVIL-004": 5,
    "CIVIL-005": 1, "CIVIL-006": 1, "CIVIL-007": 2, "STR-002": 3, "STR-004": 3})
BASELINE_DISCIPLINE = {"civil": 10, "eee": 0, "building": 7,
                       "structural": 6, "mep": 0, "accessibility": 6}
BASELINE_COVERAGE = collections.Counter({
    "ACC-002": 1, "ACC-004": 1, "ACC-005": 1, "BLD-005": 1, "BLD-006": 1,
    "CIVIL-008": 1, "CIVIL-009": 1, "CIVIL-010": 1, "CIVIL-012": 1,
    "CIVIL-013": 1, "CIVIL-014": 1, "STR-001": 1, "scope::duct": 1,
    "scope::equipment": 1, "scope::pipe": 1, "scope::zone": 1})

# ---------- A. FZK zero regression ----------
print("=== A. FZK zero regression ===")
fzk = build_review_data(parse_ifc("bim/samples/FZK_Haus.ifc"))
r = run_full_review(fzk)
issues = r["all_issues"]
check("FZK all_issues == 29", len(issues) == 29, str(len(issues)))
check("FZK rule_id multiset unchanged",
      collections.Counter(i["rule_id"] for i in issues) == BASELINE_RULES)
disc = {k.replace("_results", ""): len(r[k]) for k in
        ("civil_results", "eee_results", "building_results",
         "structural_results", "mep_results", "accessibility_results")}
check("FZK per-discipline counts unchanged", disc == BASELINE_DISCIPLINE,
      str(disc))
cov = collections.Counter(c["rule_id"] for c in r["coverage_findings"])
check("FZK coverage = baseline + MEP-PRED-001",
      cov == BASELINE_COVERAGE + collections.Counter({"MEP-PRED-001": 1}),
      f"{len(cov)} findings")
pred_cov = [c for c in r["coverage_findings"]
            if c["rule_id"] == "MEP-PRED-001"]
check("FZK predictive finding is NotChecked",
      len(pred_cov) == 1 and pred_cov[0]["severity"] == "NotChecked")
check("FZK zero predictive issues / ranking",
      not r["predictive_results"] and not r["predictive_ranking"])

# extractor global_id on a model that actually contains pipes
duplex = build_review_data(parse_ifc("bim/samples/Duplex_MEP_20110907.ifc"))
dpipes = [p for fl in duplex.get("floors", []) for p in fl.get("pipes", [])]
check("Duplex_MEP has extracted pipes", len(dpipes) > 0, str(len(dpipes)))
check("every extracted pipe carries global_id",
      all(p.get("global_id") for p in dpipes))


# ---------- fixture builder ----------
def make_bdata(pop, log, include_service=True, include_log=True):
    pipes = [{"name": row.comp_id, "global_id": row.comp_id,
              "pipe_type": row.pipe_type, "material": row.material}
             for row in pop.itertuples(index=False)]
    bdata = {
        "source": "ifc",
        "floors": [{
            "floor_id": "F1", "name": "一层",
            "pipes": pipes, "rooms": [], "structural_elements": [],
            "ducts": [], "electrical_elements": [],
        }],
        "building_params": {},
    }
    if include_service:
        bdata["pipe_service"] = [
            {"global_id": row.comp_id, "install_year": row.install_year,
             "floor_env": row.floor_env,
             "prior_repairs": int(row.prior_repairs)}
            for row in pop.itertuples(index=False)]
    if include_log:
        bdata["maintenance_log"] = log.to_dict("records")
    return bdata


# ---------- B. positive path ----------
print("\n=== B. positive path (synthetic n=400, seed 7) ===")
family = get_family("steel_pipe")
pop = generate_population(family, 400, seed=7)
# Last observed year-end snapshot is 2025 (analysis conducted 2026): the
# generator's 2026 snapshot would record failures up to a year in the future
# (failure_year <= y+1), which cannot be known at analysis time.
log = annual_maintenance_log(pop, years=range(2016, 2026))
fixture = make_bdata(pop, log)
fr = run_full_review(fixture)
pred = fr["predictive_results"]
ranking = fr["predictive_ranking"]

n_alive = int((pop["event"] == 0).sum())
check("ranking covers every alive pipe", len(ranking) == n_alive,
      f"{len(ranking)} vs {n_alive}")
probs = [x["p_fail_cycle"] for x in ranking]
check("ranking probabilities sorted descending",
      all(a >= b for a, b in zip(probs, probs[1:])))
check("predictive issues are the threshold-exceeding subset",
      len(pred) == sum(1 for p in probs if p >= 0.5),
      f"{len(pred)} issues")
check("predictive issues shaped correctly",
      all(i["severity"] == "Predictive" and i["type"] == "mep"
          and len(i["element_global_ids"]) == 1 for i in pred))

# latent-truth sanity scoring over the alive cohort
alive = pop[pop["event"] == 0].copy()
truth = dict(zip(alive["comp_id"], alive["t_true"]))
age = dict(zip(alive["comp_id"], alive["age_years"]))
cycle = family["inspection_cycle_years"]
truly = {cid: (truth[cid] - age[cid]) <= cycle for cid in truth}
base_rate = sum(truly.values()) / len(truly)
top = ranking[:max(1, int(0.1 * len(ranking)))]
prec = sum(truly[x["global_id"]] for x in top) / len(top)
lift = prec / base_rate
check(f"top10 lift in Phase-1 ballpark (base {base_rate:.1%})",
      1.5 < lift < 4.0, f"lift {lift:.2f}")

# Phase-1 headline is the latent-lifetime C-index on the model's linear
# predictor; the engine ranks by p_fail_cycle instead, a cycle-window
# conditional that also folds in current age. Both are scored here: the
# C-index must reproduce the Phase-1 ballpark, and the operational ordering
# (by p_fail_cycle) is judged by the top10 lift above.
bpop, _bmeta = population_from_building(fixture, family)
bcox = fit_cox(bpop, family)
X = build_design_matrix(bpop, family)
lp_alive = bcox.linear_predictor(X)[bpop["event"].to_numpy() == 0]
ids_alive = bpop.loc[bpop["event"] == 0, "comp_id"].to_numpy()
cindex = concordance_index(lp_alive, np.array([truth[c] for c in ids_alive]))
check("latent-truth C-index in Phase-1 ballpark", cindex > 0.65,
      f"{cindex:.3f}")

# ---------- C. abstention variants ----------
print("\n=== C. abstention ===")
no_data = run_full_review({"source": "ifc", "floors": [
    {"floor_id": "F1", "name": "一层", "pipes": [
        {"global_id": "X1", "pipe_type": "water"}],
     "rooms": [], "structural_elements": [], "ducts": [],
     "electrical_elements": []}], "building_params": {}})
nc = [c for c in no_data["coverage_findings"]
      if c["rule_id"] == "MEP-PRED-001"]
check("no maintenance data -> NotChecked",
      len(nc) == 1 and nc[0]["severity"] == "NotChecked"
      and not no_data["predictive_results"])

no_svc = run_full_review(make_bdata(pop, log, include_service=False))
nc = [c for c in no_svc["coverage_findings"]
      if c["rule_id"] == "MEP-PRED-001"]
check("missing pipe_service -> NotChecked",
      len(nc) == 1 and not no_svc["predictive_results"])

small_pop = generate_population(family, 50, seed=7)
small_log = annual_maintenance_log(small_pop)
small = run_full_review(make_bdata(small_pop, small_log))
nc = [c for c in small["coverage_findings"]
      if c["rule_id"] == "MEP-PRED-001"]
check("n<100 gate -> NotChecked with reasons",
      len(nc) == 1 and "100" in nc[0]["description"]
      and not small["predictive_results"])

# ---------- D. monitoring covariates ----------
print("\n=== D. monitoring covariates (wall-thickness readings) ===")
n_alive = int((pop["event"] == 0).sum())


def lift10(ranking):
    """top-10% inspection lift against latent truth (same framing as B)."""
    truly = {cid: (truth[cid] - age[cid]) <= cycle for cid in truth}
    base = sum(truly.values()) / len(truly)
    top = ranking[:max(1, int(0.1 * len(ranking)))]
    prec = sum(truly[x["global_id"]] for x in top) / len(top)
    return prec / base


def with_monitoring(regime, noise, history=None):
    bd = make_bdata(pop, log)
    reading = regime_measurements(family, pop, 7, regime, noise, history)
    recs = []
    for r in reading.itertuples(index=False):
        rec = {"global_id": r.comp_id, "depth_now_mm": float(r.depth_now_mm)}
        if regime == "sensor":
            rec["growth_rate_mm_yr"] = float(r.growth_rate_mm_yr)
        recs.append(rec)
    bd["pipe_monitoring"] = recs
    return bd


static_lift = lift10(ranking)   # from section B: no monitoring data
check("static-only lift reproduced for comparison", 1.5 < static_lift < 4.0,
      f"lift {static_lift:.2f}")

for regime, noise, hist, lo, hi, cmin in (
        ("inspection", 0.05, None, 4.0, 7.0, 0.76),
        ("sensor", 0.05, 5, 4.5, 8.0, 0.82)):
    bd = with_monitoring(regime, noise, hist)
    fr = run_full_review(bd)
    mon = fr["predictive_monitor"]
    rk = fr["predictive_ranking"]
    check(f"{regime}: regime reported to caller",
          mon.get("regime") == regime, str(mon))
    check(f"{regime}: ranking covers every alive pipe",
          len(rk) == n_alive, f"{len(rk)} vs {n_alive}")
    lft = lift10(rk)
    check(f"{regime}: top10 lift in expected band", lo < lft < hi,
          f"lift {lft:.2f}")
    check(f"{regime}: lift beats static-only by >50%",
          lft > static_lift * 1.5, f"{lft:.2f} vs {static_lift:.2f}")

    # Latent-truth C-index through the same adapter path the engine uses.
    # Scored on the FULL cohort (as risk.evaluate.ranking_metrics does) so this
    # reproduces the monitoring experiment's headline numbers, not the alive-only
    # operational ordering.
    pop2, _m = population_from_building(bd, family)
    meas, meta = monitoring_measurements(bd, family, pop2)
    check(f"{regime}: measurements assembled", meta["status"] == "ok"
          and meas is not None, str(meas.columns.tolist() if meas is not None else None))
    cox = fit_cox(pop2, family, measurements=meas)
    lp_all = cox.linear_predictor(build_design_matrix(pop2, family, meas))
    truth_all = dict(zip(pop["comp_id"], pop["t_true"]))
    cidx = concordance_index(lp_all, np.array([truth_all[c] for c in pop2["comp_id"]]))
    check(f"{regime}: latent C-index > {cmin}", cidx > cmin, f"{cidx:.3f}")

# D4/D5. monitoring data that cannot cover the cohort must abstain
bd = with_monitoring("sensor", 0.05, 5)
bd["pipe_monitoring"] = bd["pipe_monitoring"][:-1]
fr = run_full_review(bd)
nc = [c for c in fr["coverage_findings"] if c["rule_id"] == "MEP-PRED-001"]
check("incomplete coverage -> NotChecked, no prediction",
      len(nc) == 1 and nc[0]["severity"] == "NotChecked"
      and not fr["predictive_results"] and not fr["predictive_ranking"],
      nc[0]["description"][:46] if nc else "")

bd = with_monitoring("sensor", 0.05, 5)
for rec in bd["pipe_monitoring"][:len(bd["pipe_monitoring"]) // 2]:
    rec.pop("growth_rate_mm_yr", None)
fr = run_full_review(bd)
nc = [c for c in fr["coverage_findings"] if c["rule_id"] == "MEP-PRED-001"]
check("mixed regime -> NotChecked, no prediction",
      len(nc) == 1 and nc[0]["severity"] == "NotChecked"
      and not fr["predictive_results"], nc[0]["description"][:46] if nc else "")

print("\n" + ("ALL CHECKS PASSED" if not FAILS
               else f"{len(FAILS)} CHECK(S) FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
