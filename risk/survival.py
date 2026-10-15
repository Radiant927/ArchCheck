"""Survival modelling: Kaplan-Meier, Cox PH (statsmodels PHReg), and
predictions from a hand-computed Breslow baseline.

The Breslow baseline is computed at the all-baseline covariate point (linear
predictor 0), avoiding PHReg's covariate-centring convention. Its tail beyond
the last observed event time is extended with a Weibull fitted to the Breslow
curve (log-linear), so near-term failure probabilities stay available for
old, healthy components.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.duration.hazard_regression import PHReg

from risk.families import covariate_specs, design_columns


def kaplan_meier(t, event):
    """KM step curve. Returns (death_times, S, greenwood_var)."""
    t = np.asarray(t, float)
    event = np.asarray(event, int)
    order = np.argsort(t)
    t_sorted, e_sorted = t[order], event[order]
    n = len(t_sorted)
    times, surv, var = [], [], []
    s, cum = 1.0, 0.0
    i = 0
    while i < n:
        tj = t_sorted[i]
        j = i
        while j < n and t_sorted[j] == tj:
            j += 1
        d = int(e_sorted[i:j].sum())
        at_risk = n - i
        if d > 0:
            s *= 1.0 - d / at_risk
            denom = at_risk * (at_risk - d)
            if denom > 0:
                cum += d / denom
            times.append(tj)
            surv.append(s)
            var.append((s ** 2) * cum)
        i = j
    return np.array(times), np.array(surv), np.array(var)


def build_design_matrix(df, family, measurements=None):
    """One-hot matrix for categoricals (baseline level omitted), raw numerics.
    With ``measurements`` (merged on comp_id), monitoring projection columns
    are appended (consumed_frac, plus projected_rem_years when available)."""
    out = {}
    for spec in covariate_specs(family):
        col = df[spec["name"]]
        if spec["kind"] == "categorical":
            for lvl in spec["levels"]:
                if lvl == spec["baseline"]:
                    continue
                out[f'{spec["name"]}::{lvl}'] = (col == lvl).astype(float).to_numpy()
        else:
            out[spec["name"]] = col.astype(float).to_numpy()
    X = pd.DataFrame(out, columns=design_columns(family))
    X.insert(0, "comp_id", df["comp_id"].to_numpy())
    if measurements is not None:
        mcols = [c for c in measurements.columns if c != "comp_id"]
        X = X.merge(measurements[["comp_id"] + mcols], on="comp_id", how="left")
    return X.drop(columns="comp_id")


@dataclass
class CoxModel:
    family: dict
    columns: list
    beta: pd.Series          # log HR
    hr: pd.Series
    ci: pd.DataFrame         # 95% CI on HR
    se: pd.Series
    result: object
    base_times: np.ndarray
    base_cumhaz: np.ndarray  # Breslow H0 at the lp=0 point
    weibull_tail: tuple      # (shape, scale) fitted to Breslow for extrapolation

    def linear_predictor(self, X):
        return X[self.columns].to_numpy() @ self.beta.to_numpy()


def _breslow(times, events, lp):
    """Breslow baseline cumulative hazard at lp=0."""
    order = np.argsort(times)
    t, e, lp = times[order], events[order], lp[order]
    risk = np.exp(lp)
    out_t, out_h, cum = [], [], 0.0
    n = len(t)
    i = 0
    while i < n:
        tj = t[i]
        j = i
        while j < n and t[j] == tj:
            j += 1
        d = e[i:j].sum()
        if d > 0:
            cum += d / risk[i:].sum()
            out_t.append(tj)
            out_h.append(cum)
        i = j
    return np.array(out_t), np.array(out_h)


def _fit_weibull_tail(base_t, base_h):
    """Fit (t/lambda)^k to the Breslow curve by log-linear regression."""
    mask = base_h > 0
    x = np.log(base_t[mask])
    y = np.log(base_h[mask])
    k, b = np.polyfit(x, y, 1)
    return float(k), float(np.exp(-b / k))


def fit_cox(pop, family, measurements=None):
    X_full = build_design_matrix(pop, family, measurements)
    # A column with zero variance (e.g. an IFC where every pipe maps to the
    # same material baseline) carries no information and makes the observed
    # information matrix singular; drop it before fitting.
    active = [c for c in X_full.columns
              if np.ptp(X_full[c].to_numpy()) > 1e-12]
    X = X_full[active]
    t = pop["duration"].to_numpy(float)
    e = pop["event"].to_numpy(int)
    reg = PHReg(t, X.to_numpy(), status=e)
    result = reg.fit()
    if not np.isfinite(result.params).all():
        # Newton can overshoot to NaN on a strongly separated covariate;
        # L-BFGS has a line search and converges on the same likelihood.
        result = reg.fit(method="lbfgs", maxiter=500)
    beta = pd.Series(result.params, index=X.columns)
    try:
        ci_raw = result.conf_int()
    except np.linalg.LinAlgError:
        ci_raw = np.column_stack([result.params, result.params])
    ci_beta = np.clip(ci_raw, -20.0, 20.0)
    base_t, base_h = _breslow(t, e, X.to_numpy() @ beta.to_numpy())
    tail = _fit_weibull_tail(base_t, base_h)
    return CoxModel(
        family=family, columns=list(X.columns), beta=beta,
        hr=np.exp(beta),
        ci=pd.DataFrame(np.exp(ci_beta), index=X.columns,
                        columns=["hr_low", "hr_high"]),
        se=pd.Series(result.bse, index=X.columns),
        result=result, base_times=base_t, base_cumhaz=base_h,
        weibull_tail=tail,
    )


def baseline_cumhaz(cox, t):
    """H0 at times t: Breslow step on the observed grid, Weibull-fit beyond."""
    t = np.asarray(t, float)
    k_tail, lam_tail = cox.weibull_tail
    i = np.searchsorted(cox.base_times, t, side="right") - 1
    in_grid = i >= 0
    h = np.where(in_grid, cox.base_cumhaz[np.maximum(i, 0)], 0.0)
    beyond = t > cox.base_times[-1]
    h = np.where(beyond, (np.maximum(t, 1e-9) / lam_tail) ** k_tail, h)
    return h


def predict(cox, pop, measurements=None):
    """Predictions for the currently-alive cohort (event == 0).

    Columns: comp_id, age_years, install_year, lp, median_failure_year,
    p_fail_1yr, p_fail_cycle. Median is None when 0.5 survival is not reached
    within the 60-year horizon. ``measurements`` must match the fitted regime.
    """
    alive = pop[pop["event"] == 0].copy()
    if measurements is not None:
        measurements = measurements[measurements["comp_id"].isin(alive["comp_id"])]
    X = build_design_matrix(alive, cox.family, measurements)
    lp = cox.linear_predictor(X)
    a = alive["age_years"].to_numpy(float)
    h_a = baseline_cumhaz(cox, a)
    cycle = float(cox.family["inspection_cycle_years"])

    # median: smallest t with H0(t) = H0(a) + ln2/exp(lp). Search a dense grid
    # that reaches into the Weibull-fit tail (step Breslow on observed range).
    horizon = 60.0
    grid = np.linspace(0.0, horizon, 6001)
    h_grid = baseline_cumhaz(cox, grid)
    target = h_a + np.log(2.0) / np.exp(lp)
    med_idx = np.searchsorted(h_grid, target)
    med_t = np.where(med_idx < len(grid), grid[np.minimum(med_idx, len(grid) - 1)],
                     np.nan)
    med_year = alive["install_year"].to_numpy() + med_t

    def p_fail(horizon):
        h_end = baseline_cumhaz(cox, a + horizon)
        return 1.0 - np.exp(-(h_end - h_a) * np.exp(lp))

    return pd.DataFrame({
        "comp_id": alive["comp_id"].to_numpy(),
        "install_year": alive["install_year"].to_numpy(),
        "age_years": a,
        "lp": lp,
        "median_failure_year": med_year,
        "p_fail_1yr": p_fail(1.0),
        "p_fail_cycle": p_fail(cycle),
    })
