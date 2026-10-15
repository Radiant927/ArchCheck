"""Component-family degradation catalog.

Each family declares a Weibull baseline (shape k, scale lambda in years at the
all-baseline covariate point), covariate effects on the Cox log-hazard scale
(beta), population mixture probabilities for the synthetic generator, the
inspection cycle, and an evidence ledger.

Evidence grades: A = anchored to standards / peer-reviewed literature,
C = synthetic assumption. Grade-C values exist only to validate the statistics;
they must be replaced with sourced values before any external claim.
"""

FAMILIES = {
    "steel_pipe": {
        "display_name_zh": "钢制管道（锈蚀穿孔）",
        "failure_mode": "corrosion_perforation",
        "weibull": {"shape": 2.0, "scale_years": 24.0},
        "inspection_cycle_years": 2,
        # Physical corrosion process consistent with the latent Weibull lifetime:
        # depth d(t) reaches critical depth d_c exactly at failure time T.
        #   d(t) = d_c * (t / T)^n
        "corrosion": {
            # linear (steady uniform corrosion, mm/yr): the standard engineering
            # model; depth = d_c * t/T so it reaches d_c exactly at failure.
            "growth_exponent": 1.0,
            "critical_depth_mm": {"min": 3.0, "max": 6.0},
        },
        # Monitoring regimes. "inspection" = one ultrasonic thickness reading at
        # the analysis date; "sensor" = annual readings over the last 5 years
        # (current depth + fitted growth rate). noise_sd is absolute Gaussian
        # measurement noise in millimetres.
        "monitoring": {
            "regimes": ["none", "inspection", "sensor"],
            "noise_sd_mm": [0.05, 0.1, 0.2, 0.4],
            "sensor_history_years": 5,
        },
        "covariates": [
            {
                "name": "material",
                "kind": "categorical",
                "baseline": "carbon_steel",
                "levels": {
                    "carbon_steel": 0.0,
                    "galvanized": -0.6,
                    "stainless": -2.2,
                },
                "mixture": {"carbon_steel": 0.55, "galvanized": 0.30, "stainless": 0.15},
            },
            {
                # named pipe_type (system) to match the field produced by bim/extractor.py
                "name": "pipe_type",
                "kind": "categorical",
                "baseline": "water",
                "levels": {
                    "water": 0.0,
                    "fire": 0.0,
                    "hvac": 0.2,
                    "gas": 0.3,
                    "drainage": 0.7,
                },
                "mixture": {
                    "water": 0.30, "fire": 0.20, "hvac": 0.15,
                    "gas": 0.15, "drainage": 0.20,
                },
            },
            {
                "name": "floor_env",
                "kind": "categorical",
                "baseline": "dry",
                "levels": {"dry": 0.0, "humid": 0.9, "underground": 1.4},
                "mixture": {"dry": 0.60, "humid": 0.25, "underground": 0.15},
            },
            {
                "name": "prior_repairs",
                "kind": "numeric",
                "effect_per_unit": 0.35,
                "poisson_lam": 0.8,
                "max": 3,
            },
        ],
        "evidence": {
            "weibull": "C",
            "covariate_effects": "C",
            "mixture": "C",
            "inspection_cycle": "C",
            "corrosion": "C",
            "monitoring_noise": "C",
            "note": ("合成假设参数，仅用于方法学验证；报送/论文版需以规范与可靠性"
                     "文献替换并标注出处"),
        },
    },
}


def get_family(name):
    if name not in FAMILIES:
        raise KeyError(f"unknown family {name!r}; have {sorted(FAMILIES)}")
    return FAMILIES[name]


def list_families():
    return sorted(FAMILIES)


def covariate_specs(family):
    return family["covariates"]


def _categorical(specs):
    return [s for s in specs if s["kind"] == "categorical"]


def design_columns(family):
    """Design-matrix column names. Categoricals expand to name::level for every
    non-baseline level; numerics keep their name."""
    cols = []
    for s in covariate_specs(family):
        if s["kind"] == "categorical":
            cols += [f'{s["name"]}::{lvl}'
                     for lvl in s["levels"] if lvl != s["baseline"]]
        else:
            cols.append(s["name"])
    return cols


def true_beta_map(family):
    """column name -> true log-HR coefficient used by the generator."""
    out = {}
    for s in covariate_specs(family):
        if s["kind"] == "categorical":
            for lvl, beta in s["levels"].items():
                if lvl != s["baseline"]:
                    out[f'{s["name"]}::{lvl}'] = float(beta)
        else:
            out[s["name"]] = float(s["effect_per_unit"])
    return out
