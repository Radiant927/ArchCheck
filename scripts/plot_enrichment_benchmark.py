# -*- coding: utf-8 -*-
"""Plot the semantic-enrichment before/after benchmark.

Reads the JSON produced by scripts/benchmark_enrichment.py and renders two
figures into both output/benchmark_semantic/ and the presentation folder:
  1. semantic_metrics_before_after.png  accuracy / coverage / precision
  2. semantic_recovery_safety.png       correct counts + harmful-guess safety
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "output" / "benchmark_semantic" / "semantic_benchmark.json"
DESTS = [
    REPO / "output" / "benchmark_semantic",
    REPO / "presentation" / "2026-09-15",
]

# Prefer a CJK font on Windows; fall back silently (labels stay readable EN).
for cand in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
    if any(cand.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False

C_BEFORE = "#9aa7b8"   # grey-blue
C_AFTER = "#2f6fed"    # ArchCheck blue
C_GOOD = "#1f9d55"
C_BAD = "#d64545"


def pct(x):
    return None if x is None else x * 100


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    rooms, elems = d["rooms"], d["elements"]

    # ---- Figure 1: three rate metrics, before vs after, two categories -----
    metrics = [
        ("总准确率 Accuracy", "accuracy"),
        ("覆盖率 Coverage", "resolved_rate"),
        ("已归类精确率 Precision", "resolved_precision"),
    ]
    cats = [("房型 Room", rooms), ("构件材料 Material", elems)]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, (label, blk) in zip(axes, cats):
        b = [pct(blk["baseline"][k]) for _, k in metrics]
        a = [pct(blk["enriched"][k]) for _, k in metrics]
        x = range(len(metrics))
        w = 0.38
        ax.bar([i - w / 2 for i in x], b, w, label="改善前 keyword", color=C_BEFORE)
        ax.bar([i + w / 2 for i in x], a, w, label="改善后 keyword+AI", color=C_AFTER)
        for i, (bv, av) in enumerate(zip(b, a)):
            ax.text(i - w / 2, bv + 1.5, f"{bv:.0f}", ha="center", fontsize=9, color="#55606e")
            ax.text(i + w / 2, av + 1.5, f"{av:.0f}", ha="center", fontsize=9, fontweight="bold", color=C_AFTER)
        ax.set_xticks(list(x))
        ax.set_xticklabels([m[0] for m in metrics], fontsize=9)
        ax.set_ylim(0, 112)
        ax.set_title(label, fontsize=12, fontweight="bold")
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("百分比 %")
    axes[0].legend(loc="lower right", fontsize=9, frameon=False)
    fig.suptitle("AI 语义预处理：改善前 vs 改善后（金标准确率）", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])

    # ---- Figure 2: correct count recovered + harmful-guess safety ----------
    fig2, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    # left: correct counts before/after (out of n)
    labels = ["房型", "构件材料"]
    nb = [rooms["baseline"]["n"], elems["baseline"]["n"]]
    cb = [round(rooms["baseline"]["accuracy"] * nb[0]),
          round(elems["baseline"]["accuracy"] * nb[1])]
    ca = [round(rooms["enriched"]["accuracy"] * nb[0]),
          round(elems["enriched"]["accuracy"] * nb[1])]
    x = range(len(labels)); w = 0.38
    ax[0].bar([i - w / 2 for i in x], cb, w, color=C_BEFORE, label="改善前正确数")
    ax[0].bar([i + w / 2 for i in x], ca, w, color=C_AFTER, label="改善后正确数")
    for i, (n, bv, av) in enumerate(zip(nb, cb, ca)):
        ax[0].text(i - w / 2, bv + 0.2, f"{bv}/{n}", ha="center", fontsize=10, color="#55606e")
        ax[0].text(i + w / 2, av + 0.2, f"{av}/{n}", ha="center", fontsize=10, fontweight="bold", color=C_AFTER)
    ax[0].set_xticks(list(x)); ax[0].set_xticklabels(labels)
    ax[0].set_ylim(0, max(nb) * 1.18)
    ax[0].set_title("答对数量（共 n 个金标样本）", fontsize=12, fontweight="bold")
    ax[0].grid(axis="y", alpha=0.25); ax[0].spines[["top", "right"]].set_visible(False)
    ax[0].legend(fontsize=9, frameon=False)

    # right: harmful guesses before/after (must be 0) and recovered
    rec = [rooms["recovered"], elems["recovered"]]
    hb = [rooms["baseline"]["harmful_guesses"], elems["baseline"]["harmful_guesses"]]
    ha = [rooms["enriched"]["harmful_guesses"], elems["enriched"]["harmful_guesses"]]
    xx = range(len(labels)); w = 0.27
    ax[1].bar([i - w for i in xx], rec, w, color=C_GOOD, label="AI 救回的正确数")
    ax[1].bar([i for i in xx], hb, w, color="#c9d2dc", label="乱猜(改善前)")
    ax[1].bar([i + w for i in xx], ha, w, color=C_BAD, label="乱猜(改善后)")
    for i in xx:
        ax[1].text(i - w, rec[i] + 0.08, str(rec[i]), ha="center", fontsize=10, color=C_GOOD, fontweight="bold")
        ax[1].text(i, hb[i] + 0.08, str(hb[i]), ha="center", fontsize=10, color="#55606e")
        ax[1].text(i + w, ha[i] + 0.08, str(ha[i]), ha="center", fontsize=10, color=C_BAD, fontweight="bold")
    ax[1].set_xticks(list(xx)); ax[1].set_xticklabels(labels)
    ax[1].set_ylim(0, max(max(rec), 1) + 1.4)
    ax[1].set_title("增益与安全：救回正确 vs 无依据乱猜(须为0)", fontsize=12, fontweight="bold")
    ax[1].grid(axis="y", alpha=0.25); ax[1].spines[["top", "right"]].set_visible(False)
    ax[1].legend(fontsize=9, frameon=False)
    fig2.suptitle("AI 增益全部来自真实补全，零乱猜、零破坏", fontsize=13, fontweight="bold")
    fig2.tight_layout(rect=[0, 0, 1, 0.93])

    names = ("semantic_metrics_before_after.png", "semantic_recovery_safety.png")
    figs = (fig, fig2)
    for dest in DESTS:
        dest.mkdir(parents=True, exist_ok=True)
        for name, f in zip(names, figs):
            p = dest / name
            f.savefig(p, dpi=160, bbox_inches="tight")
            print("saved:", p)


if __name__ == "__main__":
    main()
