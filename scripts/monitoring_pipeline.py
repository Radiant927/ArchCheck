"""Driver for the state-monitoring covariate experiment.

    python scripts/monitoring_pipeline.py
    python scripts/monitoring_pipeline.py --n 400 --seeds 7 1 2 3 4

Compares three monitoring regimes — none / inspection (one ultrasonic
thickness reading) / sensor (annual readings, rate-based remaining life) —
across measurement noise and sensor history length. Every fit is scored
against hidden latent truth and against that regime's noise-free ceiling.

Writes JSON (+ console log) under output/monitoring/. Fixed-seed, deterministic.
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from risk.evaluate import monitoring_experiment, summarize_monitoring
from risk.families import get_family

OUT = ROOT / "output" / "monitoring"


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def run(family_name, n, seeds):
    family = get_family(family_name)
    result = monitoring_experiment(family, n=n, seeds=tuple(seeds))
    summary = summarize_monitoring(result)
    return family, result, summary


def print_summary(family, result, summary):
    cfg = result["config"]
    print(f'\n=== 状态监测协变量实验 | {result["family"]} ===')
    print(f'n={cfg["n"]}/构件群，种子 {cfg["seeds"]}，'
          f'检修周期 {cfg["inspection_cycle_years"]} 年')
    print(f'测噪档位 {cfg["noise_levels_mm"]} mm，'
          f'传感器历史 {cfg["history_lengths"]} 年')
    n_fail = sum(1 for c in result["cells"] if not c.get("fit_ok"))
    print(f'拟合网格 {len(result["cells"])} 格，未收敛 {n_fail} 格'
          + ('（已如实记为 null，不参与均值）' if n_fail else ''))

    df = pd.DataFrame(summary["rows"])

    def row(regime, noise, hist):
        m = df[df.regime == regime]
        if noise is not None:
            m = m[m.noise_sd_mm == noise]
        if hist is not None:
            m = m[m.history_years == hist]
        return m.iloc[0] if len(m) else None

    base = row("none", None, None)
    print(f'\n[无监测]        C-index {base.c_index:.4f} | '
          f'top10% lift {base.top10_lift:.2f} | '
          f'中位年 MAE {base.median_year_mae:.2f}')

    print("\n[抽检 inspection] 一次壁厚测值")
    print("  noise(mm)   C-index   (先知天花板)   top10 lift   中位MAE")
    for noise in cfg["noise_levels_mm"]:
        r = row("inspection", noise, None)
        print(f'    {r.noise_sd_mm:<5} {r.c_index:.4f}     '
              f'{r.c_index_ceiling:.4f}       {r.top10_lift:.2f}'
              f'        {r.median_year_mae:.2f}')

    print("\n[在线 sensor] 年度测值 + 速率外推剩余寿命")
    print("  noise(mm)  history   C-index   (先知天花板)   top10 lift   中位MAE")
    for noise in cfg["noise_levels_mm"]:
        for hist in cfg["history_lengths"]:
            r = row("sensor", noise, hist)
            tag = "" if r.n_converged == r.n_total else f'  ({r.n_converged}/{r.n_total} 收敛)'
            print(f'    {r.noise_sd_mm:<5}  {r.history_years:>3}年    '
                  f'{r.c_index:.4f}     {r.c_index_ceiling:.4f}       '
                  f'{r.top10_lift:.2f}        {r.median_year_mae:.2f}{tag}')

    # Headline deltas vs none (use lowest-noise, longest-history sensor vs none)
    best = row("sensor", cfg["noise_levels_mm"][0], cfg["history_lengths"][-1])
    print("\n[结论] 相对无监测（最低噪 / 最长历史）：")
    print(f'  C-index {base.c_index:.3f} -> {best.c_index:.3f}'
          f'（+{best.c_index - base.c_index:.3f}；sensor 先知天花板 '
          f'{best.c_index_ceiling:.3f}）')
    print(f'  top10% lift {base.top10_lift:.2f} -> {best.top10_lift:.2f}')
    print(f'  中位年 MAE {base.median_year_mae:.2f} -> '
          f'{best.median_year_mae:.2f} 年')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="steel_pipe")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 1, 2, 3, 4])
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    seed_tag = "-".join(str(s) for s in args.seeds)
    stem = f"monitoring_{args.family}_n{args.n}_seeds{seed_tag}"
    log_path = OUT / f"{stem}.log"

    with open(log_path, "w", encoding="utf-8") as fh, \
            contextlib.redirect_stdout(_Tee(sys.stdout, fh)):
        family, result, summary = run(args.family, args.n, args.seeds)
        print_summary(family, result, summary)
        payload = {"family": args.family, "evidence": family["evidence"],
                   "experiment": result, "summary": summary}

    json_path = OUT / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"[输出] {json_path}")
    print(f"[输出] {log_path}")


if __name__ == "__main__":
    main()
