"""Separate the two mechanisms behind A1 on CICIDS2017 (DECISIONS.md §19), and
show what the calibration fix does to the low-ratio result.

Hypothesis under test (from the flat RF effect in §17): the small distance-
independent FPR rise is *class-prior shift* — injecting rows stamped malicious
moves the class prior, which moves RF leaf probabilities, which moves FPR at a
fixed threshold. Four arms inject the same NUMBER of rows at the same realized
distance, differing in one thing each:

  a1       benign rows + jitter, stamped MALICIOUS   (the attack: label conflict)
  a1truth  the same rows,           stamped BENIGN   (no label conflict, same rows)
  s0j      attack rows + jitter,    stamped MALICIOUS (same prior shift and jitter
                                                       texture, no benign-label conflict)
  s0       attack rows, no jitter,  stamped MALICIOUS (the honest loop)

Reading: if the flat effect is prior shift, ``s0j`` reproduces it and
``a1 - s0j`` ~ 0. If it is label conflict at distance, ``a1`` exceeds ``s0j`` and
``a1truth`` ~ 0. Differences are paired per seed (same seeds, same data order).
All four are run under both calibrations (old: round-0 threshold on the raw
validation split; new: twin-free validation rows, ``val_min_nn_distance = 0.1``).

Writes ``results/phase0/mechanism/*.csv``, ``report.md``, ``mechanism_separation.png``.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path("results/phase0/loop")
DIRS = {"old": ROOT / "cicids", "new": ROOT / "cicids_recal"}
TAU_NEW = 0.1
JIT = 0.7            # realized NN ~0.56, well right of the cliff (>= 0.25)
RATIOS = (0.05, 0.2)
MODELS = ("rf", "xgboost")
RAMP = ["#c6dbef", "#6baed6", "#2171b5", "#08306b"]


def load(cal: str) -> pd.DataFrame:
    files = glob.glob(str(DIRS[cal] / "jobs" / "*.csv"))
    df = pd.concat((pd.read_csv(f, float_precision="round_trip") for f in files), ignore_index=True)
    df["val_min_nn_distance"] = df.get("val_min_nn_distance", 0.0)
    df["val_min_nn_distance"] = df["val_min_nn_distance"].fillna(0.0)
    tau = 0.0 if cal == "old" else TAU_NEW
    df = df[np.isclose(df["val_min_nn_distance"], tau)]
    # the recalibrated directory also holds defended, cost-padded and ablation runs;
    # this report compares undefended arms only (a defended S0 averaged into "s0"
    # silently changed its numbers once)
    if "defense" in df:
        df = df[df["defense"].fillna("none") == "none"]
    if "cost_padding" in df:
        df = df[df["cost_padding"].fillna(1.0) == 1.0]
    return df[df["round"] == df["round"].max()]


def arm(df: pd.DataFrame, scenario: str, model: str, mode: str, ratio: float) -> pd.Series:
    q = df[(df["scenario"] == scenario) & (df["model"] == model) & (df["threshold_mode"] == mode)
           & np.isclose(df["target_poison_ratio"], ratio)]
    if scenario in ("a1", "a1truth", "s0j"):
        q = q[np.isclose(q["jitter"], JIT)]
    return q.set_index("seed")


def control(df: pd.DataFrame, model: str, mode: str) -> pd.DataFrame:
    return df[(df["scenario"] == "control") & (df["model"] == model) & (df["threshold_mode"] == mode)].set_index("seed")


def sigma_control(cal: str, model: str, mode: str, metric: str) -> float:
    files = glob.glob(str(DIRS[cal] / "jobs" / "control_*.csv"))
    d = pd.concat((pd.read_csv(f, float_precision="round_trip") for f in files), ignore_index=True)
    tau = 0.0 if cal == "old" else TAU_NEW
    d = d[np.isclose(d.get("val_min_nn_distance", 0.0), tau) if "val_min_nn_distance" in d else np.ones(len(d), bool)]
    d = d[(d["model"] == model) & (d["threshold_mode"] == mode) & (d["round"] >= 11)]
    return float(d[metric].std(ddof=1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/mechanism"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    rows = []
    for cal in ("old", "new"):
        df = load(cal)
        for model in MODELS:
            for mode, metric in (("fixed", "fpr"), ("recalibrated", "tpr")):
                ctrl = control(df, model, mode)
                sig = sigma_control(cal, model, mode, metric)
                for ratio in RATIOS:
                    arms = {a: arm(df, a, model, mode, ratio) for a in ("a1", "a1truth", "s0j", "s0")}
                    if any(len(v) == 0 for v in arms.values()):
                        continue
                    seeds = sorted(set.intersection(*[set(v.index) for v in arms.values()]) & set(ctrl.index))
                    d = {a: (arms[a].loc[seeds, metric] - ctrl.loc[seeds, metric]).to_numpy() for a in arms}
                    contrasts = {
                        "a1 (benign->malicious, jittered)": d["a1"],
                        "a1truth (same rows, true label)": d["a1truth"],
                        "s0j (attack->malicious, jittered)": d["s0j"],
                        "s0 (attack->malicious)": d["s0"],
                        "a1 - s0j  (label conflict beyond prior shift)": d["a1"] - d["s0j"],
                        "a1 - a1truth  (effect of the label flip, same rows)": d["a1"] - d["a1truth"],
                    }
                    for name, v in contrasts.items():
                        rows.append({"calibration": cal, "model": model, "threshold_mode": mode,
                                     "metric_delta": metric, "poison_ratio": ratio, "contrast": name,
                                     "n_seeds": len(seeds), "mean": v.mean(), "sd": v.std(ddof=1),
                                     "t_paired": v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if v.std(ddof=1) > 0 else np.nan,
                                     "sigma_control": sig, "two_sigma": 2 * sig})
    tab = pd.DataFrame(rows)
    tab.to_csv(args.out / "mechanism_contrasts.csv", index=False)

    md = ["# Mechanism separation and recalibration (CICIDS2017)", "",
          f"Poison at realized NN ~0.56 (jitter {JIT}); ratios {RATIOS}; 5 seeds; final round; "
          "deltas are same-seed differences against the control of the same calibration. "
          "`t_paired` = mean / (sd / sqrt(n)). Fixed threshold -> FPR; recalibrated -> TPR.", ""]
    for cal, label in (("old", "OLD calibration (round-0 threshold on the raw validation split)"),
                       ("new", f"NEW calibration (twin-free validation rows, tau = {TAU_NEW})")):
        md += [f"## {label}", ""]
        t = tab[tab["calibration"] == cal].copy()
        t["delta"] = [f"{m:+.3f} +/- {s:.3f}" for m, s in zip(t["mean"], t["sd"])]
        t["2sigma_ctrl"] = t["two_sigma"].round(3)
        t["t"] = t["t_paired"].round(1)
        md += [t[["model", "threshold_mode", "poison_ratio", "contrast", "delta", "t", "2sigma_ctrl"]]
               .to_markdown(index=False), ""]
    (args.out / "report.md").write_text("\n".join(md), encoding="utf-8")

    # figure: fixed-threshold FPR deltas, per calibration x model, arms grouped by ratio
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), dpi=140, sharey="row")
    names = ["a1 (benign->malicious, jittered)", "s0j (attack->malicious, jittered)",
             "a1truth (same rows, true label)", "s0 (attack->malicious)"]
    short = ["A1: benign, stamped\nmalicious", "S0 jittered: attack,\nstamped malicious",
             "A1 rows, true label\n(no conflict)", "S0: attack,\nno jitter"]
    for i, cal in enumerate(("old", "new")):
        for j, model in enumerate(MODELS):
            ax = axes[i, j]
            for k, ratio in enumerate(RATIOS):
                sub = tab[(tab.calibration == cal) & (tab.model == model) & (tab.threshold_mode == "fixed")
                          & np.isclose(tab.poison_ratio, ratio)].set_index("contrast")
                if not len(sub):
                    continue
                xs = np.arange(len(names)) + (k - 0.5) * 0.36
                ax.bar(xs, [sub.loc[n, "mean"] for n in names], 0.34, yerr=[sub.loc[n, "sd"] for n in names],
                       color=RAMP[1 + 2 * k // 2] if k == 0 else RAMP[3], capsize=2, label=f"ratio {ratio}")
            sig = tab[(tab.calibration == cal) & (tab.model == model) & (tab.threshold_mode == "fixed")]["two_sigma"]
            if len(sig):
                ax.axhspan(-sig.iloc[0], sig.iloc[0], color="#888888", alpha=0.2, lw=0)
            ax.axhline(0, color="#444444", lw=0.8)
            ax.set_xticks(range(len(names)))
            ax.set_xticklabels(short, fontsize=6.5)
            ax.set_title(f"{model} - {'old' if cal == 'old' else 'new'} calibration: FPR increase over control",
                         fontsize=8.5, loc="left")
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.grid(axis="y", color="#e3e3e3", lw=0.6)
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle("Which mechanism produces the flat effect? (same row count, realized NN ~0.56; grey = +/-2 sigma of control)",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(args.out / "mechanism_separation.png")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
