"""Adapter: real building review data (bdata) -> risk population table.

The engine's predictive layer consumes this: maintenance records carried on
bdata are assembled into the population schema expected by ``risk.survival``.
When maintenance data is absent (e.g. a plain IFC upload), the adapter reports
unavailable and the engine emits an honest NotChecked finding — survival
numbers are never fabricated from a geometry-only model.

bdata contract:
  bdata["pipe_service"]: list of {"global_id", "install_year",
      "floor_env": dry|humid|underground, "prior_repairs": int}
  bdata["maintenance_log"]: list of {"global_id", "year",
      "status": "alive"|"failed"|"not_installed"}
  bdata["pipe_monitoring"]: optional list of {"global_id", "depth_now_mm",
      "growth_rate_mm_yr"} — the growth rate is present only under the sensor
      regime, absent under a one-off inspection. All records must share one
      regime.
Only pipes present in floors[].pipes (with a global_id) are modeled.
"""

import collections

import numpy as np
import pandas as pd

from risk.generator import ANALYSIS_YEAR, projected_covariates
from risk.families import covariate_specs


def maintenance_available(bdata):
    """Whether bdata carries both the per-pipe service records and a history
    log — the minimum information for a survival fit."""
    svc = bdata.get("pipe_service")
    log = bdata.get("maintenance_log")
    return bool(isinstance(svc, list) and svc
                and isinstance(log, list) and log)


def _iter_pipes(bdata):
    for fi, fl in enumerate(bdata.get("floors", [])):
        for p in fl.get("pipes", []):
            gid = p.get("global_id")
            if gid:
                yield gid, p, fi, fl


def _normalize_material(raw):
    s = str(raw or "").strip().lower()
    if not s:
        return None
    if "stainless" in s or s in ("ss304", "ss316", "304", "316"):
        return "stainless"
    if "galvan" in s:
        return "galvanized"
    if "steel" in s or s in ("cs", "metal", "iron"):
        return "carbon_steel"
    return None


def _level_or_baseline(value, spec, unknown_counter):
    levels = set(spec["levels"])
    v = str(value or "").strip().lower()
    if v in levels:
        return v
    unknown_counter[spec["name"]] += 1
    return spec["baseline"]


def population_from_building(bdata, family):
    """Assemble the fitted-population table from pipes + maintenance inputs.

    Returns ``(pop, meta)`` or ``None`` when no pipe has a usable service
    record. Events and their observed timing come from ``maintenance_log``
    (failure recorded at the first year-end snapshot with status failed).
    Covariate values that cannot be mapped to a family level fall back to the
    baseline level and are counted in ``meta["unknown_<field>"]``.
    """
    service = {str(r["global_id"]): r for r in bdata.get("pipe_service", [])
               if r.get("global_id") is not None}
    fail_year = {}
    for rec in bdata.get("maintenance_log", []):
        if rec.get("status") != "failed":
            continue
        # the bdata contract uses global_id; risk.generator logs use comp_id.
        raw_gid = rec.get("global_id")
        if raw_gid is None:
            raw_gid = rec.get("comp_id")
        gid = str(raw_gid)
        y = int(rec["year"])
        if gid not in fail_year or y < fail_year[gid]:
            fail_year[gid] = y

    specs = {s["name"]: s for s in covariate_specs(family)}
    unknown = collections.defaultdict(int)
    seen = set()
    rows = []
    skipped_no_service = 0
    floor_name_by_gid = {}
    for gid, pipe, _fi, fl in _iter_pipes(bdata):
        if gid in seen:
            continue
        seen.add(gid)
        svc = service.get(gid)
        if svc is None:
            skipped_no_service += 1
            continue
        floor_name_by_gid[gid] = fl.get("name")
        install_year = float(svc["install_year"])
        age_now = ANALYSIS_YEAR - install_year
        if gid in fail_year:
            event = 1
            duration = float(fail_year[gid]) - install_year
            failure_year = float(fail_year[gid])
        else:
            event = 0
            duration = age_now
            failure_year = np.nan

        material = _normalize_material(pipe.get("material"))
        if material is None:
            unknown["material"] += 1
            material = specs["material"]["baseline"]
        floor_env = _level_or_baseline(svc.get("floor_env"),
                                       specs["floor_env"], unknown)
        pipe_type = _level_or_baseline(pipe.get("pipe_type"),
                                       specs["pipe_type"], unknown)
        try:
            prior_repairs = max(int(svc.get("prior_repairs") or 0), 0)
        except (TypeError, ValueError):
            prior_repairs = 0

        rows.append({
            "comp_id": gid, "install_year": install_year,
            "age_years": age_now, "material": material,
            "pipe_type": pipe_type, "floor_env": floor_env,
            "prior_repairs": prior_repairs,
            "duration": max(duration, 0.0), "event": event,
            "failure_year": failure_year,
        })

    if not rows:
        return None

    pop = pd.DataFrame(rows, columns=[
        "comp_id", "install_year", "age_years", "material", "pipe_type",
        "floor_env", "prior_repairs", "duration", "event", "failure_year"])
    meta = {
        "n_modeled": len(rows),
        "skipped_no_service": skipped_no_service,
        "n_events": int(pop["event"].sum()),
        "unknown_material": unknown["material"],
        "unknown_floor_env": unknown["floor_env"],
        "unknown_pipe_type": unknown["pipe_type"],
        "floor_name_by_gid": floor_name_by_gid,
    }
    return pop, meta


def monitoring_regime(bdata):
    """'sensor' | 'inspection' | None. None covers both "no monitoring data"
    and "records mix regimes" — a building is expected to report one regime."""
    recs = bdata.get("pipe_monitoring")
    if not isinstance(recs, list) or not recs:
        return None
    has_rate = ["growth_rate_mm_yr" in r for r in recs]
    if all(has_rate):
        return "sensor"
    if not any(has_rate):
        return "inspection"
    return None


def _finite_nonneg(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) and f >= 0 else None


def monitoring_measurements(bdata, family, pop):
    """Assemble the monitoring covariates for a survived-inspection fit.

    Returns ``(measurements, meta)``. ``meta["status"]`` is one of:
      absent     — no monitoring data; caller fits on static covariates alone
      ok         — readings cover every modeled pipe (``regime`` reported)
      incomplete — some modeled pipes have no usable reading (covered/modeled)
      invalid    — records mix regimes; nothing is guessed from them

    Projections reuse ``risk.generator.projected_covariates`` so the engine's
    covariate is bit-identical to the one validated in the monitoring
    experiment. Readings for pipes outside the fitted population are ignored;
    a reading is never fabricated for a pipe that lacks one.
    """
    regime = monitoring_regime(bdata)
    if not isinstance(bdata.get("pipe_monitoring"), list) or not bdata["pipe_monitoring"]:
        return None, {"status": "absent"}
    if regime is None:
        return None, {"status": "invalid"}

    modeled = [str(c) for c in pop["comp_id"]]
    modeled_set = set(modeled)
    confirmed = {}
    for r in bdata["pipe_monitoring"]:
        gid = r.get("global_id")
        if gid is None:
            continue
        comp_id = str(gid)
        if comp_id not in modeled_set or comp_id in confirmed:
            continue
        depth = _finite_nonneg(r.get("depth_now_mm"))
        if depth is None:
            continue
        rec = {"comp_id": comp_id, "depth_now_mm": depth}
        if regime == "sensor":
            rate = _finite_nonneg(r.get("growth_rate_mm_yr"))
            if rate is None:
                continue
            rec["growth_rate_mm_yr"] = rate
        confirmed[comp_id] = rec

    if len(confirmed) < len(modeled):
        return None, {"status": "incomplete",
                      "covered": len(confirmed), "modeled": len(modeled)}

    reading = pd.DataFrame([confirmed[c] for c in modeled])
    proj = projected_covariates(family, reading)
    cols = ["comp_id", "consumed_frac"]
    if regime == "sensor":
        cols.append("projected_rem_years")
    return proj[cols], {"status": "ok", "regime": regime,
                        "n_modeled": len(modeled)}
