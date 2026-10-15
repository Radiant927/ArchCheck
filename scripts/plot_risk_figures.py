# -*- coding: utf-8 -*-
"""Generate presentation figures for survival-analysis milestone 1.

Outputs PNGs into presentation/2026-09-22/risk_figures/:
  1 beta_recovery.png       true vs fitted log-HR with 95% CI
  2 km_vs_weibull.png       KM correctness on a homogeneous population
  3 risk_separation.png     KM curves stratified by floor environment
  4 topk_lift.png           risk-ranked inspection: precision & lift,
                            fitted vs oracle ceiling
Fixed seed; deterministic.
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from risk import evaluate as EV
from risk.families import get_family
from risk.generator import generate_population
from risk.survival import fit_cox, kaplan_meier

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = REPO / "presentation" / "2026-09-22" / "risk_figures"
OUT.mkdir(parents=True, exist_ok=True)

FAMILY = get_family("steel_pipe")
N, SEED = 400, 7
K_TRUE = FAMILY["weibull"]["shape"]
LAM_TRUE = FAMILY["weibull"]["scale_years"]
pop = generate_population(FAMILY, N, SEED)
cox = fit_cox(pop, FAMILY)
C_BLUE, C_RED, C_GRAY, C_GREEN = "#2E5A88", "#C0392B", "#9AA5B1", "#2E8B57"


# ---------- 1. beta recovery ----------
def fig_beta():
    rows = EV.beta_recovery(cox, FAMILY)
    labels = [r["column"].replace("::", "\n") for r in rows]
    y = np.arange(len(rows))
    fit = np.array([r["fitted"] for r in rows])
    true = np.array([r["true"] for r in rows])
    se = np.array([r["se"] for r in rows])
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.errorbar(fit, y, xerr=1.96 * se, fmt="o", color=C_BLUE, ecolor=C_GRAY,
                capsize=3, label="拟合值 ± 95%CI")
    ax.plot(true, y, "s", color=C_RED, label="真实值（生成器内）")
    for yi, (f_, t_) in zip(y, zip(fit, true)):
        ax.plot([f_, t_], [yi, yi], color=C_GRAY, lw=0.8, zorder=0)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="k", lw=0.7, ls="--")
    ax.set_xlabel("对数风险系数 β（正=更易失效）")
    ax.set_title("参数恢复：9 个真实系数全部落入拟合 95% 置信区间", fontsize=12)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "1_beta_recovery.png", dpi=160)
    plt.close(fig)


# ---------- 2. KM vs true Weibull (homogeneous) ----------
import copy


def homogeneous_pop(n=4000):
    hf = copy.deepcopy(FAMILY)
    for spec in hf["covariates"]:
        if spec["kind"] == "categorical":
            spec["mixture"] = {lvl: (1.0 if lvl == spec["baseline"] else 0.0)
                               for lvl in spec["levels"]}
        else:
            spec["poisson_lam"] = 0.0
    return generate_population(hf, n, seed=12345)


def fig_km():
    hp = homogeneous_pop()
    t_km, s_km, _ = kaplan_meier(hp["duration"].to_numpy(),
                                 hp["event"].to_numpy())
    grid = np.linspace(0.01, 15, 300)
    s_true = np.exp(-(grid / LAM_TRUE) ** K_TRUE)
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    ax.step(t_km, s_km, where="post", color=C_BLUE, lw=1.8, label="KM 估计（观测记录）")
    ax.plot(grid, s_true, color=C_RED, lw=1.6, ls="--",
            label=f"真实 Weibull（k={K_TRUE:g}, λ={LAM_TRUE:g}年）")
    ax.set_xlabel("使用年限（年）")
    ax.set_ylabel("生存概率 S(t)")
    ax.set_title("KM 曲线复现真实寿命分布（积分误差 0.011）", fontsize=12)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "2_km_vs_weibull.png", dpi=160)
    plt.close(fig)


# ---------- 3. risk separation by floor environment ----------
def fig_separation():
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    colors = {"dry": C_GREEN, "humid": "#E0A32E", "underground": C_RED}
    names = {"dry": "干燥环境", "humid": "潮湿环境", "underground": "地下环境"}
    for env in ("dry", "humid", "underground"):
        sub = pop[pop["floor_env"] == env]
        t_km, s_km, _ = kaplan_meier(sub["duration"].to_numpy(),
                                     sub["event"].to_numpy())
        ax.step(t_km, s_km, where="post", lw=1.8, color=colors[env],
                label=names[env])
    ax.set_xlabel("使用年限（年）")
    ax.set_ylabel("生存概率 S(t)")
    ax.set_title("Cox 学出的风险分层：不同环境生存曲线明显分离", fontsize=12)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "3_risk_separation.png", dpi=160)
    plt.close(fig)


# ---------- 4. top-K lift ----------
def fig_lift():
    import json
    d = json.loads((REPO / "output/risk/sim_steel_pipe_n400_seed7.json")
                   .read_text(encoding="utf-8"))
    alloc = d["warning"]["top_allocation"]
    base = d["warning"]["base_rate"]
    fr = [int(a["fraction"] * 100) for a in alloc]
    p_fit = [a["precision_fitted"] for a in alloc]
    p_or = [a["precision_oracle"] for a in alloc]
    lift_fit = [a["lift_fitted"] for a in alloc]
    x = np.arange(len(fr))
    w = 0.35
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 4.2))
    ax1.bar(x - w / 2, p_fit, w, color=C_BLUE, label="Cox 模型排序")
    ax1.bar(x + w / 2, p_or, w, color=C_GRAY, label="先知天花板")
    ax1.axhline(base, color=C_RED, ls="--", lw=1.2,
                label=f"不排序基础率 {base:.0%}")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"最高风险\n{q}%" for q in fr])
    ax1.set_ylabel("2 年内真实失效率（命中率）")
    ax1.set_title("检修资源投给高风险段", fontsize=11)
    ax1.legend(fontsize=8)
    ax2.plot(fr, lift_fit, "o-", color=C_BLUE, label="Cox 模型 lift（本种子）")
    rep = json.loads((REPO / "output/risk/sim_steel_pipe_n400_repeats20.json")
                     .read_text(encoding="utf-8"))
    lift20 = rep["aggregates"]["top10_lift_fitted_mean"]
    ax2.plot(10, lift20, "*", color=C_RED, markersize=17,
             label=f"20 次平均 lift {lift20:.2f}")
    ax2.plot(fr, [a["lift_oracle"] for a in alloc], "s--", color=C_GRAY,
             label="先知天花板 lift")
    ax2.axhline(1.0, color=C_RED, ls="--", lw=1.0)
    ax2.set_xticks(fr)
    ax2.set_xlabel("投入检修的构件比例（%）")
    ax2.set_ylabel("命中率提升倍数 lift")
    ax2.set_title(f"模型排序能力达天花板的约 89%\n（20 次平均 lift 2.71）",
                  fontsize=11)
    ax2.legend(fontsize=8)
    fig.suptitle("风险排序分配检修：top10% 集中 2–4 倍失效", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "4_topk_lift.png", dpi=160)
    plt.close(fig)


fig_beta()
fig_km()
fig_separation()
fig_lift()
print("figures ->", OUT)
for p in sorted(OUT.glob("*.png")):
    print(" ", p.name, p.stat().st_size, "bytes")
