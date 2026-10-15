"""Driver for the survival-analysis milestone.

Single run:  python scripts/risk_pipeline.py --family steel_pipe --n 400 --seed 7
Repeated:    python scripts/risk_pipeline.py --repeats 20

Writes metrics JSON (+ console log, + maintenance CSV for single runs) under
output/risk/. Everything is fixed-seed and deterministic.
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from risk import evaluate as EV
from risk.families import get_family
from risk.generator import annual_maintenance_log, generate_population
from risk.survival import fit_cox

OUT = ROOT / "output" / "risk"


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def run_once(family_name, n, seed, export_log=False):
    family = get_family(family_name)
    pop = generate_population(family, n, seed)
    suff = EV.data_sufficiency(pop, family)
    result = {
        "family": family_name,
        "family_display_name_zh": family["display_name_zh"],
        "n": n,
        "seed": seed,
        "analysis_year": 2026,
        "events": int(pop["event"].sum()),
        "event_rate": float(pop["event"].mean()),
        "catalog_weibull": family["weibull"],
        "inspection_cycle_years": family["inspection_cycle_years"],
        "sufficiency": suff,
        "evidence": family["evidence"],
    }
    if suff["sufficient"]:
        cox = fit_cox(pop, family)
        result["beta_recovery"] = EV.beta_recovery(cox, family)
        result["ranking"] = EV.ranking_metrics(cox, pop)
        result["calibration"] = EV.calibration_metrics(cox, pop)
        result["warning"] = EV.warning_simulation(cox, pop)
        result["fitted_baseline_weibull"] = {
            "shape": cox.weibull_tail[0], "scale_years": cox.weibull_tail[1]}
    if export_log:
        result["maintenance_csv"] = True
    return result, pop


def print_single(result):
    print(f'\n=== {result["family_display_name_zh"]} | n={result["n"]} '
          f'seed={result["seed"]} ===')
    print(f'事件 {result["events"]}（{result["event_rate"]:.1%}），'
          f'目录 Weibull k={result["catalog_weibull"]["shape"]} '
          f'lambda={result["catalog_weibull"]["scale_years"]} 年')
    suff = result["sufficiency"]
    if not suff["sufficient"]:
        print('-> 数据不足，诚实弃权，不出任何构件级预测：'
              + "；".join(suff["reasons"]))
        return
    br = pd.DataFrame(result["beta_recovery"]).set_index("column")
    print("\n[β 恢复] log-HR（HR: 真值 -> 拟合）")
    print(pd.DataFrame({
        "HR真": br["hr_true"], "HR合": br["hr_fitted"],
        "SE": br["se"], "CI覆盖": br["ci_covers"]}).round(3).to_string())
    rk, cal, warn = result["ranking"], result["calibration"], result["warning"]
    print(f'\n[排序] C-index（潜真值）{rk["c_index_latent_truth"]:.3f} | '
          f'C-index（观测）{rk["c_index_observed"]:.3f}')
    print(f'[校准] 中位失效年 MAE {cal["median_year_mae"]:.2f} 年，'
          f'±2 年 {cal["within_2yr_rate"]:.1%}，±5 年 {cal["within_5yr_rate"]:.1%}')
    print(f'[预测层 dry-run] 在役 {warn["n_alive"]}，2 年内真实失效 '
          f'{warn["n_true_failure"]}（基础率 {warn["base_rate"]:.1%}）')
    med = warn["median_year_rule"]
    print(f'  中位年规则（项目书原写法）：报 {med["n_warned"]}，'
          f'P {fmt(med["precision"])}，R {fmt(med["recall"])}')
    print('  风险排序检修（precision / lift：拟合 vs 先知天花板）')
    for a in warn["top_allocation"]:
        print(f'    top {int(a["fraction"] * 100):2d}%: '
              f'P {a["precision_fitted"]:.3f}/{a["precision_oracle"]:.3f}  '
              f'lift {a["lift_fitted"]:.2f}/{a["lift_oracle"]:.2f}')
    tail = result["fitted_baseline_weibull"]
    print(f'[基线拟合] 尾部 Weibull k={tail["shape"]:.2f} '
          f'lambda={tail["scale_years"]:.2f} 年（真值 2.0 / 24.0）')


def fmt(x):
    return "—" if x is None else f"{x:.3f}"


def run_repeated(family_name, n, repeats):
    rows, coverage = [], {}
    for seed in range(1, repeats + 1):
        result, _ = run_once(family_name, n, seed)
        top10 = next(a for a in result["warning"]["top_allocation"]
                     if a["fraction"] == 0.10)
        rows.append({
            "seed": seed, "event_rate": result["event_rate"],
            "c_latent": result["ranking"]["c_index_latent_truth"],
            "c_observed": result["ranking"]["c_index_observed"],
            "mae": result["calibration"]["median_year_mae"],
            "base_rate_2yr": result["warning"]["base_rate"],
            "top10_precision_fitted": top10["precision_fitted"],
            "top10_lift_fitted": top10["lift_fitted"],
            "top10_precision_oracle": top10["precision_oracle"],
        })
        for b in result["beta_recovery"]:
            coverage.setdefault(b["column"], []).append(b["ci_covers"])
    df = pd.DataFrame(rows)
    out = {
        "family": family_name, "n": n, "repeats": repeats,
        "seeds": rows,
        "aggregates": {
            "event_rate_mean": float(df["event_rate"].mean()),
            "c_latent_mean": float(df["c_latent"].mean()),
            "c_observed_mean": float(df["c_observed"].mean()),
            "mae_mean": float(df["mae"].mean()),
            "base_rate_2yr_mean": float(df["base_rate_2yr"].mean()),
            "top10_precision_fitted_mean": float(df["top10_precision_fitted"].mean()),
            "top10_lift_fitted_mean": float(df["top10_lift_fitted"].mean()),
            "top10_precision_oracle_mean": float(df["top10_precision_oracle"].mean()),
        },
        "beta_ci_coverage": {k: float(np.mean(v)) for k, v in coverage.items()},
        "evidence": get_family(family_name)["evidence"],
    }
    print(f"\n=== {repeats} 次重复 | family={family_name} n={n} ===")
    print(pd.Series(out["aggregates"]).round(3).to_string())
    print("\n[β 95%CI 经验覆盖率，期望≈0.95]")
    for k, v in out["beta_ci_coverage"].items():
        print(f"  {k:28s} {v:.2f}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="steel_pipe")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--repeats", type=int, default=1)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if args.repeats > 1:
        stem = f"sim_{args.family}_n{args.n}_repeats{args.repeats}"
    else:
        stem = f"sim_{args.family}_n{args.n}_seed{args.seed}"
    log_path = OUT / f"{stem}.log"

    with open(log_path, "w", encoding="utf-8") as fh, \
            contextlib.redirect_stdout(_Tee(sys.stdout, fh)):
        if args.repeats > 1:
            payload = run_repeated(args.family, args.n, args.repeats)
        else:
            result, pop = run_once(args.family, args.n, args.seed,
                                   export_log=True)
            result["km_correctness"] = EV.km_vs_true_weibull(
                get_family(args.family))
            print_single(result)
            print(f'\n[KM 正确性] 同质人群 KM-Weibull 积分误差 '
                  f'{result["km_correctness"]["km_weibull_iae"]:.4f}')
            payload = result
            csv_path = OUT / f"maintenance_{args.family}_n{args.n}_seed{args.seed}.csv"
            annual_maintenance_log(pop).to_csv(csv_path, index=False,
                                               encoding="utf-8-sig")
            print(f"[输出] 维保日志 -> {csv_path}")

    json_path = OUT / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"[输出] {json_path}")
    print(f"[输出] {log_path}")


if __name__ == "__main__":
    main()
