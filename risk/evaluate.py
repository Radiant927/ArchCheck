"""Ground-truth validation for fitted survival models."""

import copy
import collections
import warnings

import numpy as np
import pandas as pd

from risk.families import design_columns, true_beta_map
from risk.generator import (
    ANALYSIS_YEAR, generate_population, oracle_measurement,
    projected_covariates, regime_measurements)
from risk.survival import (
    build_design_matrix, fit_cox, kaplan_meier, predict)


def beta_recovery(cox, family):
    """Per-coefficient true vs fitted beta with 95%-CI coverage flag."""
    truth = true_beta_map(family)
    rows = []
    for col in cox.columns:
        b = float(cox.beta[col])
        se = float(cox.se[col])
        rows.append({
            "column": col, "true": truth[col], "fitted": b, "se": se,
            "bias": b - truth[col],
            "ci_covers": bool(abs(b - truth[col]) <= 1.96 * se),
            "hr_true": float(np.exp(truth[col])),
            "hr_fitted": float(np.exp(b)),
        })
    return rows


def concordance_index(risk, times, events=None):
    """Harrell's C. When ``events`` is None all lifetimes are treated as
    exact (latent-truth evaluation). Otherwise pairs are comparable only when
    the earlier observation is an event."""
    risk = np.asarray(risk, float)
    times = np.asarray(times, float)
    n = len(times)
    concordant = 0.0
    comparable = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            if times[i] == times[j]:
                continue
            early, late = (i, j) if times[i] < times[j] else (j, i)
            if events is not None and events[early] != 1:
                continue
            comparable += 1.0
            if risk[early] == risk[late]:
                concordant += 0.5
            elif risk[early] > risk[late]:
                concordant += 1.0
    return float(concordant / comparable) if comparable > 0 else None


def ranking_metrics(cox, pop, measurements=None):
    """C-index on hidden latent lifetimes (primary) and observed data."""
    X_lp = cox.linear_predictor(
        build_design_matrix(pop, cox.family, measurements))
    latent_c = concordance_index(X_lp, pop["t_true"].to_numpy())
    observed_c = concordance_index(X_lp, pop["duration"].to_numpy(),
                                   pop["event"].to_numpy())
    return {"c_index_latent_truth": latent_c,
            "c_index_observed": observed_c}


def calibration_metrics(cox, pop, measurements=None):
    """Predicted median failure year vs latent truth (alive cohort)."""
    pr = predict(cox, pop, measurements)
    m = pr.merge(pop[["comp_id", "failure_year"]], on="comp_id")
    m = m[m["median_failure_year"].notna()]
    err = m["median_failure_year"] - m["failure_year"]
    return {
        "median_year_mae": float(err.abs().mean()),
        "median_year_bias": float(err.mean()),
        "within_2yr_rate": float((err.abs() <= 2.0).mean()),
        "within_5yr_rate": float((err.abs() <= 5.0).mean()),
        "n_predicted": int(len(m)),
    }


def km_vs_true_weibull(family, n=4000, seed=12345):
    """KM correctness check on a homogeneous (all-baseline) population: the
    observed KM curve must approach the catalog Weibull survival. Returns the
    integrated absolute error on 0-15 years."""
    homogeneous = copy.deepcopy(family)
    for spec in homogeneous["covariates"]:
        if spec["kind"] == "categorical":
            spec["mixture"] = {lvl: (1.0 if lvl == spec["baseline"] else 0.0)
                               for lvl in spec["levels"]}
        else:
            spec["poisson_lam"] = 0.0
    pop = generate_population(homogeneous, n, seed)
    t_km, s_km, _ = kaplan_meier(pop["duration"].to_numpy(),
                                 pop["event"].to_numpy())
    k = family["weibull"]["shape"]
    lam = family["weibull"]["scale_years"]
    grid = np.linspace(0.01, 15.0, 300)
    s_true = np.exp(-(grid / lam) ** k)
    s_km_at = s_km[np.searchsorted(t_km, grid, side="right") - 1]
    iae = float(np.trapz(np.abs(s_km_at - s_true), grid) / (grid[-1] - grid[0]))
    return {"km_weibull_iae": iae, "n": n,
            "event_rate": float(pop["event"].mean())}


def _binary_metrics(flag, truly):
    tp = int((flag & truly).sum())
    fp = int((flag & ~truly).sum())
    fn = int((~flag & truly).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None
          and precision + recall > 0 else None)
    return {"n_warned": int(flag.sum()), "precision": precision,
            "recall": recall, "f1": f1}


def _oracle_cycle_prob(family, alive):
    """Failure probability within the inspection cycle under the true Weibull
    model and the hidden linear predictor — the predictability ceiling."""
    k = float(family["weibull"]["shape"])
    lam = float(family["weibull"]["scale_years"])
    cycle = float(family["inspection_cycle_years"])
    a = alive["age_years"].to_numpy()
    delta_h = ((a + cycle) / lam) ** k - (a / lam) ** k
    return 1.0 - np.exp(-delta_h * np.exp(alive["eta"].to_numpy()))


def warning_simulation(cox, pop, measurements=None, oracle_probs=None):
    """Dry-run of the engine's future predictive layer, scored against latent
    truth on the alive cohort.

    Compares three framings: (1) the proposal's literal median-year rule,
    (2) probability thresholds, (3) risk-ranked inspection allocation
    (top 5/10/20%) for both the fitted model and the ceiling oracle so the
    gap to the predictability ceiling is visible. ``measurements`` must match
    the fitted regime; ``oracle_probs`` (aligned to the alive cohort)
    overrides the default physical Weibull oracle.
    """
    cycle = float(cox.family["inspection_cycle_years"])
    cutoff = ANALYSIS_YEAR + cycle
    pr = predict(cox, pop, measurements)
    alive = pop[pop["event"] == 0]
    # Full alive cohort: p_fail_cycle is finite for everyone, so base rate and
    # the ranked allocation are computed on the same set across regimes.
    f = pr.merge(alive[["comp_id", "failure_year", "eta"]],
                 on="comp_id")
    truly = (f["failure_year"] <= cutoff).to_numpy()
    base_rate = float(truly.mean())
    if oracle_probs is not None:
        f = f.merge(oracle_probs, on="comp_id")
        p_oracle = f["p_oracle"].to_numpy()
    else:
        p_oracle = _oracle_cycle_prob(cox.family, f)
    p_fit = f["p_fail_cycle"].to_numpy()

    # Median rule / probability thresholds only make sense where a finite
    # median exists (Breslow+Weibull tail reaches 0.5 within the horizon).
    m = f[f["median_failure_year"].notna()]
    m_truly = (m["failure_year"] <= cutoff).to_numpy()
    median_rule = _binary_metrics(
        (m["median_failure_year"] <= cutoff).to_numpy(), m_truly)
    prob_rules = []
    for thr in (0.3, 0.5, 0.7):
        metrics = _binary_metrics((m["p_fail_cycle"] >= thr).to_numpy(), m_truly)
        prob_rules.append({"threshold": thr, **metrics})

    allocation = []
    n = len(f)
    for frac in (0.05, 0.10, 0.20):
        k_n = max(1, int(frac * n))
        row = {"fraction": frac, "k": k_n}
        for name, p in (("fitted", p_fit), ("oracle", p_oracle)):
            top = np.argsort(-p)[:k_n]
            prec = float(truly[top].mean())
            row[f"precision_{name}"] = prec
            row[f"lift_{name}"] = prec / base_rate if base_rate else None
        allocation.append(row)

    return {
        "cycle_years": cycle, "cutoff_year": cutoff,
        "base_rate": base_rate, "n_alive": n,
        "n_true_failure": int(truly.sum()),
        "median_year_rule": median_rule,
        "probability_rules": prob_rules,
        "top_allocation": allocation,
    }


MONITORING_COL = {"inspection": "consumed_frac",
                  "sensor": "projected_rem_years"}


def _ceiling(family, pop, regime):
    """Fit with noise-free projections; return ceiling Cox + alive-cycle probs."""
    oracle = oracle_measurement(family, pop, regime)
    meas = oracle[["comp_id", MONITORING_COL[regime]]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cox = fit_cox(pop, family, measurements=meas)
        pr = predict(cox, pop, meas)[["comp_id", "p_fail_cycle"]]
    return {"cox": cox, "meas": meas,
            "probs": pr.rename(columns={"p_fail_cycle": "p_oracle"})}


def _converged(cox):
    try:
        return bool(cox.result.mle_retvals.get("converged", True))
    except Exception:
        return True


def _fit_cell(family, pop, seed, regime, noise, history, ceiling):
    """One (seed, regime, noise, history) fit, scored against latent truth."""
    cell = {"seed": seed, "regime": regime,
            "noise_sd_mm": noise, "history_years": history}
    if regime == "none":
        proj, oracle_probs = None, None
    else:
        reading = regime_measurements(family, pop, seed, regime, noise, history)
        proj = projected_covariates(family, reading)
        proj = proj[["comp_id", MONITORING_COL[regime]]]
        oracle_probs = ceiling["probs"]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cox = fit_cox(pop, family, measurements=proj)
    except Exception as exc:
        cell.update(fit_ok=False, converged=False,
                    fit_error=type(exc).__name__)
        return cell
    finite = bool(np.isfinite(cox.beta).all())
    cell.update(fit_ok=finite, converged=_converged(cox))
    if not finite:
        return cell

    rank = ranking_metrics(cox, pop, proj)
    ws = warning_simulation(cox, pop, proj, oracle_probs)
    cal = calibration_metrics(cox, pop, proj)
    if regime == "none":
        c_oracle = concordance_index(pop["eta"].to_numpy(),
                                     pop["t_true"].to_numpy())
        cal_oracle = None
    else:
        c_oracle = ranking_metrics(ceiling["cox"], pop,
                                   ceiling["meas"])["c_index_latent_truth"]
        cal_oracle = calibration_metrics(ceiling["cox"], pop,
                                         ceiling["meas"])
    cell.update({
        "c_index_latent_truth": rank["c_index_latent_truth"],
        "c_index_observed": rank["c_index_observed"],
        "c_index_ceiling": c_oracle,
        "base_rate": ws["base_rate"],
        "top_allocation": ws["top_allocation"],
        "median_year_mae": cal["median_year_mae"],
        "median_year_mae_ceiling": (None if cal_oracle is None
                                    else cal_oracle["median_year_mae"]),
    })
    return cell


def monitoring_experiment(family, n=400, seeds=(7, 1, 2, 3, 4),
                          noise_levels=(0.05, 0.1, 0.2, 0.4),
                          history_lengths=(2, 5, 10)):
    """Three-regime information-value experiment.

    none / inspection (one thickness reading) / sensor (annual readings,
    rate-based remaining life). Each noisy fit is scored on latent-truth
    C-index, risk-ranked top-K inspection allocation, and median-year MAE,
    alongside that regime's noise-free ceiling.
    """
    cells = []
    for seed in seeds:
        pop = generate_population(family, n, seed=seed)
        ceilings = {
            "inspection": _ceiling(family, pop, "inspection"),
            "sensor": _ceiling(family, pop, "sensor"),
        }
        cells.append(_fit_cell(family, pop, seed, "none", None, None, None))
        for noise in noise_levels:
            cells.append(_fit_cell(family, pop, seed, "inspection",
                                   noise, None, ceilings["inspection"]))
            for history in history_lengths:
                cells.append(_fit_cell(family, pop, seed, "sensor",
                                       noise, history, ceilings["sensor"]))
    return {
        "family": family["display_name_zh"],
        "config": {"n": n, "seeds": list(seeds),
                   "noise_levels_mm": list(noise_levels),
                   "history_lengths": list(history_lengths),
                   "inspection_cycle_years": family["inspection_cycle_years"],
                   "sensor_covariate": "projected_rem_years",
                   "inspection_covariate": "consumed_frac"},
        "cells": cells,
    }


def _mean(vals):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return float(np.mean(vals)) if vals else None


def summarize_monitoring(result):
    """Collapse cells to mean-over-seeds tables.

    Rows keyed by (regime, noise_sd_mm, history_years); columns give mean
    C-index (and its noise-free ceiling), top-10%-allocation fitted vs ceiling
    lift, median-year MAE (and ceiling), and how many fits converged.
    """
    cfg = result["config"]
    groups = collections.OrderedDict()
    for c in result["cells"]:
        h = c.get("history_years")
        key = (c["regime"], c.get("noise_sd_mm"), h)
        groups.setdefault(key, []).append(c)

    rows = []
    for (regime, noise, hist), cells in groups.items():
        ok = [c for c in cells if c.get("fit_ok")]
        lift10_fit, lift10_oracle, prec10_fit = [], [], []
        for c in ok:
            for a in c.get("top_allocation", []):
                if abs(a["fraction"] - 0.10) < 1e-9:
                    lift10_fit.append(a["lift_fitted"])
                    lift10_oracle.append(a.get("lift_oracle"))
                    prec10_fit.append(a["precision_fitted"])
        rows.append({
            "regime": regime, "noise_sd_mm": noise,
            "history_years": hist,
            "c_index": _mean([c.get("c_index_latent_truth") for c in ok]),
            "c_index_ceiling": _mean([c.get("c_index_ceiling") for c in ok]),
            "top10_lift": _mean(lift10_fit),
            "top10_lift_ceiling": _mean(lift10_oracle),
            "top10_precision": _mean(prec10_fit),
            "median_year_mae": _mean([c.get("median_year_mae") for c in ok]),
            "median_year_mae_ceiling": _mean(
                [c.get("median_year_mae_ceiling") for c in ok]),
            "n_converged": len(ok), "n_total": len(cells),
        })
    return {"config": cfg, "rows": rows}


MIN_EVENTS = 25


def data_sufficiency(pop, family, extra_columns=0):
    """Honest-abstention gate. Refuses prediction when events or events-per-
    variable are too low for stable Cox estimation. ``extra_columns`` accounts
    for covariates fitted beyond the family catalog (monitoring projections)."""
    n = int(len(pop))
    events = int(pop["event"].sum())
    epv = events / max(len(design_columns(family)) + extra_columns, 1)
    reasons = []
    if n < 100:
        reasons.append(f"样本量 {n} < 100")
    if events < MIN_EVENTS:
        reasons.append(f"失效事件 {events} < {MIN_EVENTS}")
    if epv < 5:
        reasons.append(f"每变量事件数 {epv:.1f} < 5")
    return {"sufficient": not reasons, "reasons": reasons,
            "n": n, "events": events, "epv": epv}
