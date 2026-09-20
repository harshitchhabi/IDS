"""The second A1 mechanism, at a distance far from benign (DECISIONS.md §22).

Question: past the copy-fidelity cliff (realized NN ~0.014), what does benign-
distributed poison stamped malicious still do, and what causes it? Arms, all at the
same poison ratios, realized NN ~1.06 for the jittered ones (jitter 1.5):

  a1       benign rows + jitter, stamped MALICIOUS
  a1truth  the same rows, stamped with their TRUE label (benign)
  s0j      attack rows + the same jitter, stamped malicious (same class-prior shift,
           same volume and jitter texture, no benign-label conflict)
  junk     every feature drawn independently from the pooled benign+attack marginals
           (bulk volume that resembles neither class), stamped malicious
  s0       attack rows, no jitter (the honest loop)

Reading. A class-prior-shift effect appears in *every* arm that adds malicious-stamped
rows; a benign-label-conflict effect appears in ``a1`` and not in ``s0j`` / ``s0`` /
``a1truth``; a volume-only effect appears in ``junk``. Deltas are same-seed paired
differences against the control of the same run directory and calibration.

Also reports the two claims that make it legible: the effect scales with the poison
*ratio* at fixed distance, and does not scale with *distance* at fixed ratio (rank
correlations), and what each defense does in this regime.

Writes ``results/phase0/far/``.
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
from scipy.stats import spearmanr

ROOT = Path("results/phase0/loop")
MODELS = ("rf", "xgboost")
RATIOS = (0.02, 0.05, 0.2, 0.5)
JIT = 1.5
ARMS = {"a1": ("A1: benign, stamped malicious", "#08306b", "-"),
        "s0j": ("matched: attack rows (jittered), stamped malicious", "#d98c1f", "-"),
        "a1truth": ("same rows as A1, true label", "#2a9d8f", "-"),
        "junk": ("junk: marginal-shuffled bulk, stamped malicious", "#8e44ad", "-"),
        "s0": ("S0: attack rows, no jitter", "#888888", ":")}


def load(dirname: str, tau: float) -> pd.DataFrame:
    files = glob.glob(str(ROOT / dirname / "jobs" / "*.csv"))
    df = pd.concat((pd.read_csv(f, float_precision="round_trip") for f in files), ignore_index=True)
    for c, v in (("val_min_nn_distance", 0.0), ("defense", "none"), ("cost_padding", 1.0)):
        df[c] = df[c].fillna(v) if c in df else v
    return df[np.isclose(df["val_min_nn_distance"], tau)]


def deltas(df: pd.DataFrame, scenario: str, model: str, mode: str, metric: str, ratio: float,
           jitter: float | None = JIT, defense: str = "none") -> np.ndarray:
    fin = df[df["round"] == df["round"].max()]
    ctrl = fin[(fin.scenario == "control") & (fin.model == model) & (fin.threshold_mode == mode)].set_index("seed")[metric]
    q = fin[(fin.scenario == scenario) & (fin.model == model) & (fin.threshold_mode == mode) & (fin.defense == defense)
            & np.isclose(fin.target_poison_ratio, ratio) & (fin.cost_padding == 1.0)]
    if scenario in ("a1", "s0j", "a1truth") and jitter is not None:
        q = q[np.isclose(q.jitter, jitter)]
    q = q.set_index("seed")[metric]
    seeds = sorted(set(q.index) & set(ctrl.index))
    return (q.loc[seeds] - ctrl.loc[seeds]).to_numpy() if len(seeds) else np.array([])


def sigma(df: pd.DataFrame, model: str, mode: str, metric: str) -> float:
    c = df[(df.scenario == "control") & (df.model == model) & (df.threshold_mode == mode) & (df["round"] >= 11)]
    return float(c[metric].std(ddof=1))


def pm(v: np.ndarray) -> str:
    return "" if len(v) == 0 else f"{v.mean():+.3f} +/- {v.std(ddof=1):.3f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/far"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    cal = {"old calibration": load("cicids", 0.0), "new calibration (tau=0.1)": load("cicids_recal", 0.1)}
    md = ["# The second A1 mechanism: poison far from benign", "",
          f"Jittered arms at jitter {JIT} (realized NN ~1.06); CICIDS2017; 5 seeds; final round; paired same-seed deltas "
          "vs control. TPR is under the recalibrated threshold (identical under both calibrations), FPR under the fixed "
          "threshold. `2 sigma` = twice the control's std (rounds 11-20).", ""]

    # ---- tables ------------------------------------------------------------------------
    rows = []
    for cname, df in cal.items():
        for model in MODELS:
            for mode, metric in (("fixed", "fpr"), ("recalibrated", "tpr")):
                sg = sigma(df, model, mode, metric)
                for arm in ARMS:
                    for ratio in RATIOS:
                        v = deltas(df, arm, model, mode, metric, ratio)
                        if len(v):
                            rows.append({"calibration": cname, "model": model, "threshold_mode": mode, "metric": metric,
                                         "arm": arm, "ratio": ratio, "n": len(v), "mean": v.mean(),
                                         "sd": v.std(ddof=1), "two_sigma": 2 * sg})
    tab = pd.DataFrame(rows)
    tab.to_csv(args.out / "far_distance_ratio_sweep.csv", index=False)
    for cname in cal:
        for mode, metric, lab in (("fixed", "fpr", "FPR rise (fixed threshold)"), ("recalibrated", "tpr", "TPR change (recalibrated threshold)")):
            if mode == "recalibrated" and cname != "new calibration (tau=0.1)":
                continue
            t = tab[(tab.calibration == cname) & (tab.threshold_mode == mode)].copy()
            if t.empty:
                continue
            t["cell"] = [f"{m:+.3f} +/- {s:.3f}" for m, s in zip(t["mean"], t["sd"])]
            pv = t.pivot_table(index=["model", "arm"], columns="ratio", values="cell", aggfunc="first")
            sg = t.groupby("model").two_sigma.first().round(3).to_dict()
            md += [f"## {lab}, {cname}", "", f"2 sigma: {sg}", "", pv.to_markdown(), ""]

    # ---- ratio vs distance ----------------------------------------------------------------
    corr = []
    for cname, df in cal.items():
        for model in MODELS:
            for mode, metric, sgn in (("fixed", "fpr", 1), ("recalibrated", "tpr", -1)):
                # (i) fixed distance (jitter 1.5), across ratios
                xs, ys = [], []
                for r in RATIOS:
                    v = deltas(df, "a1", model, mode, metric, r)
                    xs += [r] * len(v); ys += list(sgn * v)
                rho_r = spearmanr(xs, ys)[0] if len(xs) > 4 else np.nan
                # (ii) fixed ratio 0.2, across jitters past the cliff (realized >= 0.014)
                fin = df[df["round"] == df["round"].max()]
                dx, dy = [], []
                for j in sorted(fin[(fin.scenario == "a1") & (fin.jitter > 0)].jitter.unique()):
                    v = deltas(df, "a1", model, mode, metric, 0.2, jitter=j)
                    dx += [j] * len(v); dy += list(sgn * v)
                rho_d = spearmanr(dx, dy)[0] if len(dx) > 4 else np.nan
                corr.append({"calibration": cname, "model": model, "threshold_mode": mode,
                             "rank_corr_vs_ratio (fixed distance)": rho_r,
                             "rank_corr_vs_distance (ratio 0.2, jitter>0)": rho_d})
    cr = pd.DataFrame(corr)
    cr.to_csv(args.out / "rank_correlations.csv", index=False)
    md += ["## Does the far effect scale with ratio or with distance? (Spearman rank correlation of the damage)", "",
           cr.round(2).to_markdown(index=False), ""]

    # ---- defenses in this regime -----------------------------------------------------------
    new = cal["new calibration (tau=0.1)"]
    drow = []
    for arm, jit in (("a1", JIT), ("junk", None)):
        for model in MODELS:
            for mode, metric, sgn in (("fixed", "fpr", 1), ("recalibrated", "tpr", -1)):
                sg = sigma(new, model, mode, metric)
                for ratio in (0.2, 0.5):
                    base = sgn * deltas(new, arm, model, mode, metric, ratio, jit, "none")
                    row = {"arm": arm, "model": model, "metric": ("FPR rise" if sgn > 0 else "TPR drop"), "ratio": ratio,
                           "2sigma": round(2 * sg, 3), "undefended": pm(base)}
                    for d in ("d1_E8_g2", "knn", "loss"):
                        v = sgn * deltas(new, arm, model, mode, metric, ratio, jit, d)
                        row[d] = pm(v)
                    drow.append(row)
    td = pd.DataFrame(drow)
    td.to_csv(args.out / "far_defended.csv", index=False)
    if len(td):
        md += ["## Defenses in the far-distance regime (new calibration)", "",
               "A1 = jitter 1.5 benign poison; junk = marginal-shuffled bulk. Positive = damage.", "",
               td.to_markdown(index=False), ""]

    # ---- figures -----------------------------------------------------------------------------
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), dpi=140, sharex=True)
    panels = (("old calibration", "fixed", "fpr", "FPR rise, fixed threshold, OLD calibration"),
              ("new calibration (tau=0.1)", "fixed", "fpr", "FPR rise, fixed threshold, NEW calibration"),
              ("new calibration (tau=0.1)", "recalibrated", "tpr", "TPR change, recalibrated threshold"))
    for i, model in enumerate(MODELS):
        for j, (cname, mode, metric, title) in enumerate(panels):
            ax = axes[i, j]
            df = cal[cname]
            sg = sigma(df, model, mode, metric)
            ax.axhspan(-2 * sg, 2 * sg, color="#888888", alpha=0.2, lw=0)
            ax.axhline(0, color="#444444", lw=0.7)
            for arm, (lab, col, ls) in ARMS.items():
                xs, ys, es = [], [], []
                for r in RATIOS:
                    v = deltas(df, arm, model, mode, metric, r)
                    if len(v):
                        xs.append(r); ys.append(v.mean()); es.append(v.std(ddof=1))
                if xs:
                    ax.errorbar(xs, ys, yerr=es, color=col, ls=ls, marker="o", ms=3.5, lw=1.5, capsize=2, label=lab)
            ax.set_xscale("log")
            ax.set_title(f"{model}: {title}", fontsize=8.5, loc="left")
            ax.set_xlabel("poison ratio (fixed realized distance ~1.06)", fontsize=8)
            ax.grid(color="#e3e3e3", lw=0.6)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
    axes[0, 0].legend(fontsize=6.3, frameon=False, loc="upper left")
    fig.suptitle("Far from benign: effect against poison ratio, by what the rows are and how they are labelled "
                 "(grey = +/-2 sigma of control)", fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(args.out / "far_effect_vs_ratio.png")
    plt.close(fig)

    old = cal["old calibration"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9), dpi=140)
    fin = old[old["round"] == old["round"].max()]
    for ax, (model, mode, metric, sgn, title) in zip(axes, (("rf", "recalibrated", "tpr", -1, "RF: TPR drop, recalibrated"),
                                                           ("xgboost", "fixed", "fpr", 1, "XGBoost: FPR rise, fixed (old calibration)"))):
        for r, col in ((0.05, "#6baed6"), (0.2, "#08306b")):
            xs, ys, es = [], [], []
            for j in sorted(fin[(fin.scenario == "a1")].jitter.unique()):
                v = deltas(old, "a1", model, mode, metric, r, jitter=j)
                nn = fin[(fin.scenario == "a1") & np.isclose(fin.jitter, j) & np.isclose(fin.target_poison_ratio, r)
                         & (fin.model == model)].fidelity_median.mean()
                if len(v) and np.isfinite(nn):
                    xs.append(nn); ys.append(sgn * v.mean()); es.append(v.std(ddof=1))
            ax.errorbar(xs, ys, yerr=es, color=col, marker="o", ms=3.5, lw=1.5, capsize=2, label=f"ratio {r}")
        sg = sigma(old, model, mode, metric)
        ax.axhspan(-2 * sg, 2 * sg, color="#888888", alpha=0.2, lw=0)
        ax.axvline(0.25, color="#b03a2e", ls="--", lw=1.1)
        ax.set_xscale("log")
        ax.set_title(title, fontsize=9, loc="left")
        ax.set_xlabel("realized NN distance, poison -> trusted benign (log)", fontsize=8)
        ax.grid(color="#e3e3e3", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].legend(fontsize=7, frameon=False)
    fig.suptitle("The far effect does not fall off with distance (cliff at the left edge; red = 0.25)", fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(args.out / "far_effect_vs_distance.png")
    plt.close(fig)

    (args.out / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
