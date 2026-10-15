# -*- coding: utf-8 -*-
"""Presentation figures for the state-monitoring covariate experiment.

Outputs PNGs into presentation/2026-09-29/monitoring_figures/:
  1 cindex_regime.png      C-index by regime (none/inspection/sensor) vs ceilings
  2 sensor_noise_history   C-index vs measurement noise, one line per history
  3 information_lift.png   headline: ordered information levels -> C-index
                           and top10%-allocation lift, vs the ceiling
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

from risk.evaluate import monitoring_experiment, summarize_monitoring
from risk.families import get_family

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = REPO / "presentation" / "2026-09-29" / "monitoring_figures"
OUT.mkdir(parents=True, exist_ok=True)

FAMILY = get_family("steel_pipe")
experiment = monitoring_experiment(FAMILY, n=400, seeds=(7, 1, 2, 3, 4))
S = summarize_monitoring(experiment)
ROWS = S["rows"]
NOISES = S["config"]["noise_levels_mm"]
HISTS = S["config"]["history_lengths"]

C_BLUE, C_RED, C_GRAY, C_GREEN, C_ORANGE = (
    "#2E5A88", "#C0392B", "#9AA5B1", "#2E8B57", "#E0A32E")


def find(regime, noise=None, hist=None):
    for r in ROWS:
        if r["regime"] != regime:
            continue
        if noise is not None and r["noise_sd_mm"] != noise:
            continue
        if hist is not None and r["history_years"] != hist:
            continue
        return r
    return None


NONE = find("none")
INSP0 = find("inspection", NOISES[0])
SENS0 = {h: find("sensor", NOISES[0], h) for h in HISTS}


# ---------- 1. C-index by regime ----------
def fig_regime():
    labels = ["无监测", "壁厚抽检\n(一次测值)", "在线传感器\n(速率外推)"]
    vals = [NONE["c_index"], INSP0["c_index"],
            SENS0[HISTS[-1]]["c_index"]]
    ceil = [NONE["c_index_ceiling"], INSP0["c_index_ceiling"],
            SENS0[HISTS[-1]]["c_index_ceiling"]]
    x = np.arange(3)
    w = 0.36
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    ax.bar(x - w / 2, vals, w, color=C_BLUE, label="含噪实测下的 C-index")
    ax.bar(x + w / 2, ceil, w, color=C_GRAY, label="该体制的无噪天花板")
    for xi, v in zip(x - w / 2, vals):
        ax.text(xi, v + 0.005, f"{v:.3f}", ha="center", fontsize=9)
    ax.axhline(0.5, color=C_RED, ls=":", lw=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0.5, 0.9)
    ax.set_ylabel("C-index（对潜真实寿命排序，1=完美）")
    ax.set_title(f"监测信息量越大，寿命排序越准\n（测噪 {NOISES[0]} mm）",
                 fontsize=12)
    ax.legend(fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "1_cindex_regime.png", dpi=160)
    plt.close(fig)


# ---------- 2. sensor: noise x history ----------
def fig_noise_history():
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    palette = {HISTS[0]: C_GREEN, HISTS[1]: C_ORANGE, HISTS[2]: C_RED}
    for h in HISTS:
        ys = [find("sensor", n, h)["c_index"] for n in NOISES]
        ax.plot(NOISES, ys, "o-", color=palette[h],
                label=f"传感器历史 {h} 年")
    ax.axhline(SENS0[HISTS[-1]]["c_index_ceiling"], color=C_GRAY, ls="--",
               lw=1.4, label=f"sensor 无噪天花板 "
               f'{SENS0[HISTS[-1]]["c_index_ceiling"]:.3f}')
    ax.axhline(NONE["c_index"], color=C_BLUE, ls=":", lw=1.4,
               label=f'无监测 {NONE["c_index"]:.3f}')
    ax.set_xlabel("单次测量噪声标准差（mm）")
    ax.set_ylabel("C-index")
    ax.set_title("传感器的预测价值：抗噪靠更长的观测历史", fontsize=12)
    ax.legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "2_sensor_noise_history.png", dpi=160)
    plt.close(fig)


# ---------- 3. headline information -> lift ----------
def fig_information():
    order = [("无监测", NONE)]
    order.append(("壁厚抽检", INSP0))
    for h in HISTS:
        order.append((f"sensor\n{h}年历史", SENS0[h]))
    labels = [o[0] for o in order]
    cidx = [o[1]["c_index"] for o in order]
    lift = [o[1]["top10_lift"] for o in order]
    ceilc = [o[1]["c_index_ceiling"] for o in order]
    x = np.arange(len(order))

    fig, ax1 = plt.subplots(figsize=(9.0, 4.7))
    ax1.bar(x, cidx, 0.55, color=C_BLUE, label="C-index（实测）")
    ax1.plot(x, ceilc, "s--", color=C_GRAY, ms=6, label="C-index 无噪天花板")
    for xi, v in zip(x, cidx):
        ax1.text(xi, v + 0.006, f"{v:.3f}", ha="center", fontsize=8.5)
    ax1.set_ylim(0.5, 0.92)
    ax1.set_ylabel("C-index")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(x, lift, "o-", color=C_RED, lw=1.8,
             label="top10% 检修 lift")
    for xi, v in zip(x, lift):
        ax2.text(xi, v + 0.08, f"{v:.2f}", ha="center", fontsize=8.5,
                 color=C_RED)
    ax2.set_ylim(0, 7.5)
    ax2.set_ylabel("top10% 检修命中率提升倍数 lift", color=C_RED)

    lines1, lab1 = ax1.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, lab1 + lab2, fontsize=8.5, loc="upper left")
    ax1.set_title("信息量 → 预测力：每加一档监测，排序与检修命中都在提升\n"
                  f"（测噪 {NOISES[0]} mm；C-index 达天花板 "
                  f'{cidx[-1] / ceilc[-1]:.0%}）', fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "3_information_lift.png", dpi=160)
    plt.close(fig)


fig_regime()
fig_noise_history()
fig_information()
print("figures ->", OUT)
for p in sorted(OUT.glob("*.png")):
    print(" ", p.name, p.stat().st_size, "bytes")
