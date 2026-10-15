"""Synthetic maintenance-data generator.

Fully controlled: latent Weibull-PH lifetimes are generated for every
component and retained (``t_true``), including for components that are
right-censored at the analysis date. Downstream evaluation therefore scores
fitted models against hidden truth rather than against censored observations.
"""

import zlib

import numpy as np
import pandas as pd

from risk.families import covariate_specs

ANALYSIS_YEAR = 2026
MAX_AGE_YEARS = 15
MIN_AGE_YEARS = 0.5


def _sample_categorical(spec, n, rng):
    levels = list(spec["levels"])
    mix = spec["mixture"]
    if set(mix) != set(levels):
        raise ValueError(f'mixture for {spec["name"]} must cover exactly its levels')
    probs = np.array([mix[lvl] for lvl in levels], dtype=float)
    probs /= probs.sum()
    idx = rng.choice(len(levels), size=n, p=probs)
    return [levels[i] for i in idx]


def generate_population(family, n, seed, analysis_year=ANALYSIS_YEAR,
                        max_age_years=MAX_AGE_YEARS,
                        min_age_years=MIN_AGE_YEARS):
    """Generate n components with covariates, latent truth, and observed data.

    Returns a DataFrame with one row per component:
      comp_id, install_year, age_years, <covariates>, eta (true linear
      predictor), t_true (latent lifetime, years), duration, event,
      failure_year (absolute, = install_year + t_true).
    """
    rng = np.random.default_rng(seed)
    k = float(family["weibull"]["shape"])
    lam = float(family["weibull"]["scale_years"])

    age = rng.uniform(min_age_years, max_age_years, size=n)
    cols = {"comp_id": [f"P{i + 1:04d}" for i in range(n)],
            "age_years": np.round(age, 3)}
    eta = np.zeros(n)
    for spec in covariate_specs(family):
        if spec["kind"] == "categorical":
            values = _sample_categorical(spec, n, rng)
            beta_lookup = spec["levels"]
            eta += np.array([beta_lookup[v] for v in values], dtype=float)
        else:
            values = np.minimum(rng.poisson(spec["poisson_lam"], size=n),
                                spec["max"]).astype(float)
            eta += values * float(spec["effect_per_unit"])
        cols[spec["name"]] = values

    u = rng.random(size=n)
    t_true = lam * np.exp(-eta / k) * (-np.log(u)) ** (1.0 / k)

    event = (t_true <= age).astype(int)
    duration = np.where(event == 1, t_true, age)
    install_year = analysis_year - age
    failure_year = install_year + t_true

    # critical depth d_c: wall thickness lost at perforation. Sampled last so
    # existing fixed-seed draws (covariates / t_true) stay reproducible.
    dc = rng.uniform(float(family["corrosion"]["critical_depth_mm"]["min"]),
                     float(family["corrosion"]["critical_depth_mm"]["max"]),
                     size=n)

    df = pd.DataFrame(cols)
    df["install_year"] = np.round(install_year, 3)
    tdf = pd.DataFrame({
        "eta": eta, "t_true": t_true, "duration": duration,
        "event": event, "failure_year": failure_year,
        "critical_depth_mm": dc})
    df = pd.concat([df, tdf], axis=1)
    front = ["comp_id", "install_year", "age_years"]
    rest = [c for c in df.columns if c not in front]
    return df[front + rest]


def depth_true(family, pop, t):
    """True corrosion depth (mm) at component age(s) ``t``: d_c (t/T)^n."""
    n_exp = float(family["corrosion"]["growth_exponent"])
    dc = pop["critical_depth_mm"].to_numpy()
    T = pop["t_true"].to_numpy()
    t = np.broadcast_to(np.asarray(t, float), T.shape)
    return dc * np.maximum(t / T, 0.0) ** n_exp


def _meas_rng(seed, regime, noise_sd):
    # stable across processes: Python's hash() is salted per process.
    return np.random.default_rng(
        np.random.SeedSequence([seed, zlib.crc32(regime.encode()),
                                int(noise_sd * 1000)]))


def inspection_reading(family, pop, seed, noise_sd):
    """One noisy ultrasonic thickness-loss reading at the analysis date.
    Returns DataFrame with depth_now_mm for the supplied (alive) pop."""
    rng = _meas_rng(seed, "inspection", noise_sd)
    d = depth_true(family, pop, pop["age_years"].to_numpy())
    d = d + rng.normal(0.0, noise_sd, size=len(d))
    return pd.DataFrame({"comp_id": pop["comp_id"].to_numpy(),
                         "depth_now_mm": np.maximum(d, 0.0)})


def sensor_readings(family, pop, seed, noise_sd, history_years=None):
    """Annual noisy readings over the last ``history_years`` (defaults to the
    family config); fit a linear growth rate (mm/yr), current depth + rate."""
    hist = int(history_years
               if history_years is not None
               else family["monitoring"]["sensor_history_years"])
    rng = _meas_rng(seed, "sensor", noise_sd)
    a = pop["age_years"].to_numpy()
    offsets = np.arange(hist, -1, -1, dtype=float)
    times = a[:, None] - offsets[None, :]
    # readings only exist since installation; pre-install points sit at t=0,
    # depth 0. Each row therefore has its own regression x-grid.
    times = np.maximum(times, 0.0)
    T = pop["t_true"].to_numpy()[:, None]
    d = (pop["critical_depth_mm"].to_numpy()[:, None]
         * (times / T) ** float(family["corrosion"]["growth_exponent"]))
    d = d + rng.normal(0.0, noise_sd, size=d.shape)
    d = np.maximum(d, 0.0)
    rate, depth_now = [], []
    for row, trow in zip(d, times):
        xm = trow - trow.mean()
        sxx = (xm ** 2).sum()
        slope = (xm * (row - row.mean())).sum() / sxx if sxx > 0 else 0.0
        rate.append(slope)
        depth_now.append(row[-1])
    return pd.DataFrame({
        "comp_id": pop["comp_id"].to_numpy(),
        "depth_now_mm": depth_now,
        "growth_rate_mm_yr": np.maximum(rate, 0.0),
    })


def regime_measurements(family, pop, seed, regime, noise_sd, history_years=None):
    """Noisy monitoring table covering ALL components.

    Alive components get the regime reading at the analysis date; failed
    components are 'measured at discovery', i.e. depth at failure (~d_c,
    same noise) plus growth rate at failure under the sensor regime.
    """
    alive = pop[pop["event"] == 0]
    failed = pop[pop["event"] == 1]
    if regime == "inspection":
        parts = [inspection_reading(family, alive, seed, noise_sd)]
    elif regime == "sensor":
        parts = [sensor_readings(family, alive, seed, noise_sd, history_years)]
    else:
        raise ValueError(regime)
    rng = _meas_rng(seed, f"{regime}_failed", noise_sd)
    f_dc = failed["critical_depth_mm"].to_numpy()
    frow = pd.DataFrame({
        "comp_id": failed["comp_id"].to_numpy(),
        "depth_now_mm": np.maximum(f_dc + rng.normal(0, noise_sd, len(f_dc)), 0)})
    if regime == "sensor":
        n_exp = float(family["corrosion"]["growth_exponent"])
        rate = (f_dc * n_exp / failed["t_true"].to_numpy()
                + rng.normal(0, noise_sd, len(f_dc)))
        frow["growth_rate_mm_yr"] = np.maximum(rate, 0.0)
    parts.append(frow)
    out = pd.concat(parts, ignore_index=True)
    return pop[["comp_id"]].merge(out, on="comp_id")


def _assumed_dc(family):
    cd = family["corrosion"]["critical_depth_mm"]
    return 0.5 * (cd["min"] + cd["max"])


def projected_covariates(family, reading):
    """Engineering-standard projections from noisy readings (age-comparable,
    unlike raw rate which is inflated for young components when n<1):

    consumed_frac       = depth / assumed critical depth      [inspection]
    projected_rem_years = (assumed dc - depth) / rate         [sensor]
    """
    dc0 = _assumed_dc(family)
    out = pd.DataFrame({"comp_id": reading["comp_id"].to_numpy(),
                        "consumed_frac": reading["depth_now_mm"].to_numpy() / dc0})
    if "growth_rate_mm_yr" in reading.columns:
        rate = np.maximum(reading["growth_rate_mm_yr"].to_numpy(), 0.01)
        rem = (dc0 - reading["depth_now_mm"].to_numpy()) / rate
        # negative = "already past average perforation depth" (valid alarm);
        # clip only to keep the PH fit finite.
        out["projected_rem_years"] = np.clip(rem, -5.0, 100.0)
    return out


def oracle_measurement(family, pop, regime):
    """Noise-free engineering projections available under ``regime``.

    Mirrors the observation protocol: failed components are 'measured at
    discovery' (depth d_c, rate at T), alive ones at the analysis date."""
    dc0 = _assumed_dc(family)
    n_exp = float(family["corrosion"]["growth_exponent"])
    a = pop["age_years"].to_numpy()
    T = pop["t_true"].to_numpy()
    dc = pop["critical_depth_mm"].to_numpy()
    failed = pop["event"].to_numpy() == 1
    t_obs = np.where(failed, T, a)
    depth = dc * np.maximum(t_obs / T, 0.0) ** n_exp
    out = pd.DataFrame({"comp_id": pop["comp_id"].to_numpy(),
                        "consumed_frac": depth / dc0})
    if regime == "sensor":
        rate = np.maximum(dc * n_exp / T * (t_obs / T) ** (n_exp - 1.0), 0.01)
        out["projected_rem_years"] = np.clip((dc0 - depth) / rate, -5.0, 100.0)
    return out


def annual_maintenance_log(pop, years=range(2016, 2027)):
    """Long table of year-end maintenance snapshots: comp_id, year, status.

    status is one of not_installed / alive / failed. Failure is recorded at the
    first year-end after the component's (latent) failure year.
    """
    rows = []
    for _, r in pop.iterrows():
        for y in years:
            if r["install_year"] > y:
                status = "not_installed"
            elif r["failure_year"] <= y + 1:
                status = "failed"
            else:
                status = "alive"
            rows.append({"comp_id": r["comp_id"], "year": y, "status": status})
    return pd.DataFrame(rows)
