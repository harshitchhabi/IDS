"""Figure for DECISIONS.md §16: per-family median nearest-neighbour RMS from
trusted_eval to honeypot_pool on CICIDS2017 (log axis), benign included, at every
dedup grid, with the 0.25 guard-(c) "clean" bar marked. Reads
``nn_degeneracy_by_grid.csv``; writes ``degeneracy.png``."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

GRID_COLORS = {0.005: "#9ecae1", 0.01: "#6baed6", 0.02: "#3182bd", 0.05: "#08519c"}  # one hue, light -> dark
MIN_ROWS = 500


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=Path("results/phase0/cicids"))
    args = ap.parse_args(argv)

    d = pd.read_csv(args.dir / "nn_degeneracy_by_grid.csv")
    d = d[d["family"] != "ALL_ATTACK"]
    base = d[d["grid"] == d["grid"].min()].set_index("family")
    order = base.sort_values("median_rms").index.tolist()   # smallest (most degenerate) at the bottom

    fig, ax = plt.subplots(figsize=(8.0, 6.2), dpi=150)
    ax.axvline(0.25, color="#b03a2e", lw=1.5, zorder=1)
    ax.text(0.225, 2.0, "0.25 leak-clean bar (guard c)", color="#b03a2e", va="center",
            ha="right", fontsize=8)
    for y, fam in enumerate(order):
        for g, col in GRID_COLORS.items():
            r = d[(d["family"] == fam) & (d["grid"] == g)]
            if len(r):
                ax.scatter(r["median_rms"], y, s=34, color=col, edgecolor="white", linewidth=0.8,
                           zorder=3)
    labels = []
    for fam in order:
        n = int(base.loc[fam, "n_trusted_eval"])
        labels.append(f"{fam}  (n={n:,})")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(labels, fontsize=8)
    for t, fam in zip(ax.get_yticklabels(), order):
        n = int(base.loc[fam, "n_trusted_eval"])
        t.set_color("#222222" if n >= MIN_ROWS else "#888888")   # grey = under the 500-row bar
        if fam == "BENIGN":
            t.set_fontweight("bold")
    ax.set_xscale("log")
    ax.set_xlim(1e-3, 1.0)
    ax.set_xlabel("median nearest-neighbour distance, trusted_eval -> honeypot_pool (per-feature RMS, log scale)",
                  fontsize=8)
    ax.set_title("CICIDS2017 is low-entropy in CICFlowMeter space, both classes\n"
                 "every family with >=500 eval rows sits >=10x below the 0.25 bar at every dedup grid",
                 fontsize=9, loc="left")
    ax.grid(axis="x", color="#dddddd", lw=0.6, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, markeredgecolor="white", label=f"grid {g}")
               for g, c in GRID_COLORS.items()]
    ax.legend(handles=handles, title="near-dup grid (dedup strength)", fontsize=7, title_fontsize=7,
              frameon=False, loc="upper left")
    fig.text(0.01, 0.005, "burst-level split, no family withholding; grey label = <500 eval rows",
             fontsize=6.5, color="#666666")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(args.dir / "degeneracy.png")
    print(args.dir / "degeneracy.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
