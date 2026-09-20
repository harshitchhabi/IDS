"""Tables and figures from the loop sweeps (results/phase0/loop/<dataset>/jobs).

Report order (fixed by the experiment brief):

1. **Control-arm variance** — the noise floor everything else is read against:
   the std of the control metric over seeds x rounds 11-20 (``sigma_control``),
   its round-to-round component, and its across-seed component.
2. **A1 trajectories** — FPR under the fixed threshold, TPR under the
   recalibrated threshold.
3. **Damage vs realized mimicry distance**, paired final-round difference
   against the same-seed control, with the 0.25 line marked. The x-axis is the
   median NN distance from the injected poison to trusted_eval benign, not the
   jitter knob.
4. **The poison ratio at which A1 first clears control variance.**
5. **S0 on synthetic, per arm.**

"Clears control variance" means: mean paired final-round delta > 2 x
sigma_control (one-measurement sigma, deliberately conservative: the mean over 5
seeds has a smaller standard error). Fixed mode looks at the FPR increase,
recalibrated mode at the TPR drop.
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

RAMP = ["#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"]   # one hue, light -> dark
LEAK_BAR = 0.25
MODELS = ("rf", "xgboost")


def load(dataset: str, root: Path) -> pd.DataFrame:
    files = glob.glob(str(root / dataset / "jobs" / "*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    # This report is the undefended, original-calibration loop. The same directory
    # also holds defended runs, cost-padded runs and re-calibrated runs (see
    # phase0_defense_report.py / phase0_mechanism_report.py); averaging them in
    # would silently corrupt every table here.
    for col, keep in (("defense", lambda c: c.fillna("none") == "none"),
                      ("val_min_nn_distance", lambda c: c.fillna(0.0) == 0.0),
                      ("cost_padding", lambda c: c.fillna(1.0) == 1.0)):
        if col in df:
            df = df[keep(df[col])]
    return df


def control_floor(df: pd.DataFrame) -> pd.DataFrame:
    c = df[(df["scenario"] == "control") & (df["round"] >= 11)]
    rows = []
    for (model, mode), g in c.groupby(["model", "threshold_mode"]):
        for metric in ("fpr", "tpr", "auroc"):
            per_seed = g.groupby("seed")[metric].mean()
            within = g.groupby("seed")[metric].std(ddof=1).mean()   # round-to-round, avg over seeds
            rows.append({"model": model, "threshold_mode": mode, "metric": metric,
                         "mean": g[metric].mean(), "sigma_control": g[metric].std(ddof=1),
                         "round_to_round_sd": within,
                         "std_across_seeds": per_seed.std(ddof=1),
                         "n_obs": int(len(g)), "n_seeds": int(g["seed"].nunique())})
    return pd.DataFrame(rows)


def paired_damage(df: pd.DataFrame, floor: pd.DataFrame, scenario: str = "a1") -> pd.DataFrame:
    """Scenario final-round metric minus same-seed control final-round metric.
    Cells with fewer seeds than the full set (an interrupted sweep) are dropped."""
    last = df["round"].max()
    fin = df[df["round"] == last]
    ctrl = fin[fin["scenario"] == "control"].set_index(["model", "threshold_mode", "seed"])
    a1 = fin[fin["scenario"] == scenario].copy()
    a1["jitter"] = a1["jitter"].fillna(-1.0)          # S0 has no jitter
    n_full = int(ctrl.index.get_level_values("seed").nunique())
    rows = []
    for (model, mode, jit, ratio), g in a1.groupby(["model", "threshold_mode", "jitter", "target_poison_ratio"]):
        if g["seed"].nunique() < n_full:
            continue
        d_fpr, d_tpr = [], []
        for _, r in g.iterrows():
            c = ctrl.loc[(model, mode, r["seed"])]
            d_fpr.append(r["fpr"] - c["fpr"])
            d_tpr.append(r["tpr"] - c["tpr"])
        fl = floor.set_index(["model", "threshold_mode", "metric"])
        s_fpr = fl.loc[(model, mode, "fpr"), "sigma_control"]
        s_tpr = fl.loc[(model, mode, "tpr"), "sigma_control"]
        rows.append({
            "model": model, "threshold_mode": mode, "jitter": jit, "poison_ratio": ratio,
            "fidelity_median": g["fidelity_median"].mean() if "fidelity_median" in g else float("nan"),
            "n_seeds": len(g),
            "delta_fpr": np.mean(d_fpr), "delta_fpr_sd": np.std(d_fpr, ddof=1),
            "delta_tpr": np.mean(d_tpr), "delta_tpr_sd": np.std(d_tpr, ddof=1),
            "sigma_control_fpr": s_fpr, "sigma_control_tpr": s_tpr,
            # fixed mode: damage shows as FPR rise; recalibrated: as TPR drop
            "exceeds_noise": bool((np.mean(d_fpr) > 2 * s_fpr) if mode == "fixed"
                                  else (-np.mean(d_tpr) > 2 * s_tpr)),
        })
    return pd.DataFrame(rows)


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color="#e3e3e3", lw=0.6)


SHOW_JITTERS = (0.0, 0.01, 0.03, 0.1, 0.3, 1.5)


def fig_trajectory(df: pd.DataFrame, ratio: float, out: Path) -> None:
    a1 = df[(df["scenario"] == "a1") & np.isclose(df["target_poison_ratio"], ratio)]
    ctrl = df[df["scenario"] == "control"]
    jits = [j for j in sorted(a1["jitter"].unique()) if any(np.isclose(j, sj) for sj in SHOW_JITTERS)]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), dpi=140, sharex=True)
    for i, model in enumerate(MODELS):
        for j, (mode, metric, title) in enumerate((("fixed", "fpr", "FPR, fixed threshold"),
                                                    ("recalibrated", "tpr", "TPR, recalibrated threshold"))):
            ax = axes[i, j]
            for k, jit in enumerate(jits):
                g = a1[(a1["model"] == model) & (a1["threshold_mode"] == mode) & (a1["jitter"] == jit)]
                m = g.groupby("round")[metric].mean()
                fid = g["fidelity_median"].mean()
                ax.plot(m.index, m.values, color=RAMP[min(k * len(RAMP) // max(len(jits), 1), len(RAMP) - 1)],
                        lw=1.6, label=f"realized NN {fid:.3f}")
            c = ctrl[(ctrl["model"] == model) & (ctrl["threshold_mode"] == mode)].groupby("round")[metric]
            cm, cs = c.mean(), c.std()
            ax.plot(cm.index, cm.values, color="#222222", lw=1.6, ls="--", label="control")
            ax.fill_between(cm.index, cm - 2 * cs, cm + 2 * cs, color="#888888", alpha=0.18, lw=0)
            ax.set_title(f"{model}: {title}", fontsize=9, loc="left")
            ax.set_xlabel("round", fontsize=8)
            _style(ax)
    axes[0, 0].legend(fontsize=6.5, frameon=False, title=f"poison ratio {ratio}, by mimicry fidelity",
                      title_fontsize=6.5)
    fig.suptitle(f"A1 on CICIDS2017, poison ratio {ratio} (band = control mean +/- 2 sd across seeds)",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_damage(dm: pd.DataFrame, out: Path, s0: pd.DataFrame | None = None) -> None:
    ratios = sorted(dm["poison_ratio"].unique())
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), dpi=140, sharex=True)
    for i, model in enumerate(MODELS):
        for j, (mode, col, ylab, sgn) in enumerate((
                ("fixed", "delta_fpr", "FPR increase vs control", 1),
                ("recalibrated", "delta_tpr", "TPR drop vs control", -1))):
            ax = axes[i, j]
            sub = dm[(dm["model"] == model) & (dm["threshold_mode"] == mode)]
            sig = sub["sigma_control_fpr" if mode == "fixed" else "sigma_control_tpr"].iloc[0]
            ax.axhspan(-2 * sig, 2 * sig, color="#888888", alpha=0.2, lw=0)
            for k, r in enumerate(ratios):
                g = sub[np.isclose(sub["poison_ratio"], r)].sort_values("fidelity_median")
                ax.plot(g["fidelity_median"], sgn * g[col], marker="o", ms=4, lw=1.4,
                        color=RAMP[min(k, len(RAMP) - 1)], label=f"ratio {r:g}")
            if s0 is not None and len(s0):
                ref = s0[(s0["model"] == model) & (s0["threshold_mode"] == mode)]
                for k, r in enumerate(ratios):
                    v = ref[np.isclose(ref["poison_ratio"], r)]
                    if len(v):
                        ax.axhline(sgn * v[col].iloc[0], color=RAMP[min(k, len(RAMP) - 1)], ls=":", lw=1.2)
            ax.axvline(LEAK_BAR, color="#b03a2e", ls="--", lw=1.2)
            ax.set_xscale("log")
            ax.set_title(f"{model}: {ylab}", fontsize=9, loc="left")
            ax.set_xlabel("realized mimicry distance: median NN(poison -> trusted_eval benign), log", fontsize=7.5)
            _style(ax)
    axes[0, 0].text(LEAK_BAR * 1.05, axes[0, 0].get_ylim()[1] * 0.92, "0.25", color="#b03a2e", fontsize=8)
    axes[0, 0].legend(fontsize=6.5, frameon=False, title="final poison ratio", title_fontsize=6.5)
    fig.suptitle("A1 damage vs how close the attacker gets (grey band = +/-2 sigma of control; "
                 "dotted = S0 at the same ratio, i.e. adding genuine attack rows)",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_s0(df: pd.DataFrame, ratio: float, out: Path) -> None:
    arms = ("seen_both", "seed_only", "honeypot_only")
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.5), dpi=140, sharex=True)
    for i, model in enumerate(MODELS):
        for j, arm in enumerate(arms):
            ax = axes[i, j]
            for sc, col, ls in (("control", "#222222", "--"), ("s0", "#2171b5", "-")):
                g = df[(df["scenario"] == sc) & (df["model"] == model) & (df["threshold_mode"] == "fixed")]
                if sc == "s0":
                    g = g[np.isclose(g["target_poison_ratio"], ratio)]
                m = g.groupby("round")[f"tpr_{arm}"]
                mu, sd = m.mean(), m.std()
                ax.plot(mu.index, mu.values, color=col, ls=ls, lw=1.6, label=sc)
                ax.fill_between(mu.index, mu - sd, mu + sd, color=col, alpha=0.15, lw=0)
            ax.set_title(f"{model} / {arm}", fontsize=9, loc="left")
            ax.set_xlabel("round", fontsize=8)
            _style(ax)
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle(f"S0 on synthetic, poison ratio {ratio}: per-arm TPR, fixed threshold (band = +/-1 sd over seeds)",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def first_clears(dm: pd.DataFrame, s0: pd.DataFrame | None = None) -> pd.DataFrame:
    """Smallest poison ratio at which the mean paired delta clears 2 sigma_control,
    per (model, threshold mode, jitter). ``nan`` = no tested ratio clears it.

    Two criteria, both reported:

    * ``first_clears_ratio`` - the brief's definition: delta vs the same-seed
      control > 2 sigma_control (FPR rise for the fixed threshold, TPR drop for
      the recalibrated threshold).
    * ``first_clears_beyond_s0_ratio`` - stricter, fixed threshold only: A1's FPR
      rise *in excess of S0's at the same ratio* > 2 sigma_control. Adding any
      malicious-labeled rows shifts the class prior and raises fixed-threshold FPR
      (RF especially), which is not mimicry; S0 (genuine attack rows) isolates that
      effect. Needs an S0 run at that ratio, else the ratio is skipped.
    """
    s0_fpr = {}
    if s0 is not None and len(s0):
        s0_fpr = {(r.model, r.threshold_mode, round(r.poison_ratio, 6)): r.delta_fpr for r in s0.itertuples()}
    rows = []
    for (model, mode, jit), g in dm.groupby(["model", "threshold_mode", "jitter"]):
        g = g.sort_values("poison_ratio")
        hit = g[g["exceeds_noise"]]
        beyond = float("nan")
        if mode == "fixed":
            for r in g.itertuples():
                ref = s0_fpr.get((model, mode, round(r.poison_ratio, 6)))
                if ref is not None and (r.delta_fpr - ref) > 2 * r.sigma_control_fpr:
                    beyond = float(r.poison_ratio)
                    break
        rows.append({"model": model, "threshold_mode": mode, "jitter": jit,
                     "realized_nn_median": g["fidelity_median"].mean(),
                     "ratios_tested": ",".join(f"{r:g}" for r in g["poison_ratio"]),
                     "first_clears_ratio": float(hit["poison_ratio"].iloc[0]) if len(hit) else float("nan"),
                     "first_clears_beyond_s0_ratio": beyond})
    return pd.DataFrame(rows).sort_values(["model", "threshold_mode", "realized_nn_median"])


def fig_control(df: pd.DataFrame, out: Path, title: str) -> None:
    ctrl = df[df["scenario"] == "control"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), dpi=140, sharex=True)
    for i, model in enumerate(MODELS):
        for j, (mode, metric, lab) in enumerate((("fixed", "fpr", "FPR, fixed threshold"),
                                                  ("recalibrated", "tpr", "TPR, recalibrated threshold"))):
            ax = axes[i, j]
            g = ctrl[(ctrl["model"] == model) & (ctrl["threshold_mode"] == mode)]
            for _, gs in g.groupby("seed"):
                ax.plot(gs["round"], gs[metric], color="#9ecae1", lw=0.9)
            m = g.groupby("round")[metric].mean()
            ax.plot(m.index, m.values, color="#08519c", lw=2, label="mean over seeds")
            ax.set_title(f"{model}: {lab}", fontsize=9, loc="left")
            ax.set_xlabel("round", fontsize=8)
            _style(ax)
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle(title, fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def _pm(mean: float, sd: float) -> str:
    return f"{mean:+.3f} +/- {sd:.3f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("results/phase0/loop"))
    args = ap.parse_args(argv)
    md: list[str] = ["# Phase 0 loop results", "",
                     "5 seeds, 20 rounds, RF (25 trees, depth<=16) + XGBoost (60 trees). All values are "
                     "mean +/- std across seeds unless stated. Control = no ingestion, retrain on seed_train "
                     "each round (model seed varies by round, shared across arms).", ""]

    cic = load("cicids", args.root)
    syn = load("synthetic", args.root)
    cdir, sdir = args.root / "cicids", args.root / "synthetic"

    # ---- 1. control variance ------------------------------------------------
    md += ["## 1. Control-arm variance (the noise floor)", "",
           "`sigma_control` = std over seeds x rounds 11-20; `round_to_round_sd` = std over rounds within a "
           "seed (avg over seeds); `std_across_seeds` = std of the per-seed means.", ""]
    floors = {}
    for name, df, d in (("CICIDS2017", cic, cdir), ("synthetic", syn, sdir)):
        if len(df):
            floors[name] = control_floor(df)
            floors[name].to_csv(d / "control_noise_floor.csv", index=False)
            fig_control(df, d / "control_variance.png", f"Control arm on {name}: per-seed trajectories (light) and mean")
            md += [f"### {name}", "", floors[name].round(4).to_markdown(index=False), ""]

    dm = s0c = None
    if len(cic):
        floor = floors["CICIDS2017"]
        dm = paired_damage(cic, floor)
        dm.to_csv(cdir / "a1_damage_vs_fidelity.csv", index=False)
        s0c = paired_damage(cic, floor, "s0") if (cic["scenario"] == "s0").any() else None
        if s0c is not None and len(s0c):
            s0c.to_csv(cdir / "s0_reference_damage.csv", index=False)

        # ---- 2. A1 trajectories ----------------------------------------------
        for r in (0.05, 0.2):
            fig_trajectory(cic, r, cdir / f"a1_trajectory_r{r}.png")
        last = cic["round"].max()
        fin = cic[(cic["round"] == last) & (cic["scenario"].isin(["control", "a1"]))].copy()
        fin["jitter"] = fin["jitter"].fillna(-1.0)
        traj = (fin[(fin["target_poison_ratio"].isin([0.0, 0.05, 0.2]))]
                .groupby(["model", "threshold_mode", "scenario", "target_poison_ratio", "jitter"])
                .agg(fpr_mean=("fpr", "mean"), fpr_sd=("fpr", "std"), tpr_mean=("tpr", "mean"),
                     tpr_sd=("tpr", "std"), realized_nn=("fidelity_median", "mean")).reset_index())
        traj.to_csv(cdir / "a1_final_round.csv", index=False)
        md += ["## 2. A1 on CICIDS2017: FPR trajectory (fixed threshold), TPR (recalibrated)", "",
               "Figures: `cicids/a1_trajectory_r0.05.png`, `cicids/a1_trajectory_r0.2.png` (band = control mean "
               "+/- 2 sd). Final round (20), ratio 0.2:", ""]
        t = traj[(traj["target_poison_ratio"].isin([0.0, 0.2]))].copy()
        t["FPR"] = [f"{m:.3f} +/- {s:.3f}" for m, s in zip(t["fpr_mean"], t["fpr_sd"])]
        t["TPR"] = [f"{m:.3f} +/- {s:.3f}" for m, s in zip(t["tpr_mean"], t["tpr_sd"])]
        md += [t[["model", "threshold_mode", "scenario", "jitter", "realized_nn", "FPR", "TPR"]]
               .round(4).to_markdown(index=False), ""]

        # ---- 3. damage vs realized distance -----------------------------------
        fig_damage(dm, cdir / "a1_damage_vs_fidelity.png", s0c)
        md += ["## 3. Damage vs realized mimicry distance (CICIDS2017)", "",
               "Figure: `cicids/a1_damage_vs_fidelity.png` (red dashed = 0.25; grey band = +/-2 sigma_control; "
               "dotted = S0 at the same ratio). Paired final-round delta vs same-seed control:", ""]
        for model in MODELS:
            for mode, col, sd, lab in (("fixed", "delta_fpr", "delta_fpr_sd", "FPR increase"),
                                       ("recalibrated", "delta_tpr", "delta_tpr_sd", "TPR change")):
                sub = dm[(dm["model"] == model) & (dm["threshold_mode"] == mode)].copy()
                sub["cell"] = [_pm(m, s) for m, s in zip(sub[col], sub[sd])]
                sub["realized_nn"] = sub["fidelity_median"].round(4)
                pv = sub.pivot_table(index=["jitter", "realized_nn"], columns="poison_ratio", values="cell",
                                     aggfunc="first").fillna("")
                md += [f"**{model}, {mode} threshold - {lab}**", "", pv.to_markdown(), ""]

        # ---- 4. first clears --------------------------------------------------
        fc = first_clears(dm, s0c)
        fc.to_csv(cdir / "a1_first_clears_control_variance.csv", index=False)
        md += ["## 4. Poison ratio at which A1 first clears control variance (CICIDS2017)", "",
               "`first_clears_ratio` = smallest tested ratio whose mean paired delta exceeds 2 sigma_control "
               "(`nan` = none of the tested ratios does). `first_clears_beyond_s0_ratio` (fixed threshold only) "
               "subtracts S0's FPR rise at the same ratio first, removing the class-prior effect of adding any "
               "malicious-labeled rows.", "",
               fc.round(4).to_markdown(index=False), ""]

    # ---- 5. S0 on synthetic ---------------------------------------------------
    if len(syn) and (syn["scenario"] == "s0").any():
        fig_s0(syn, 0.2, sdir / "s0_arms_r0.2.png")
        lastr = syn[(syn["round"] == syn["round"].max()) & (syn["threshold_mode"] == "fixed")]
        arm_cols = [c for c in lastr.columns if c.startswith("tpr_") and c != "tpr"]
        sub = lastr[lastr["scenario"].isin(["control", "s0"])]
        agg = sub.groupby(["model", "scenario", "target_poison_ratio"])[arm_cols + ["fpr", "tpr"]].agg(["mean", "std"])
        agg.to_csv(sdir / "s0_final_round.csv")
        cells = sub.groupby(["model", "scenario", "target_poison_ratio"])[arm_cols + ["fpr"]].agg(["mean", "std"])
        pretty = pd.DataFrame({c: [f"{cells.loc[i, (c, 'mean')]:.3f} +/- {cells.loc[i, (c, 'std')]:.3f}"
                                   for i in cells.index] for c in arm_cols + ["fpr"]}, index=cells.index)
        md += ["## 5. S0 on synthetic, per arm (final round, fixed threshold)", "",
               "Figure: `synthetic/s0_arms_r0.2.png`. `novel` dropped (n=0).", "", pretty.to_markdown(), ""]

    # ---- appendix ------------------------------------------------------------------
    md += ["## Appendix", ""]
    if len(cic):
        fdist = cdir / "mimicry_fidelity_distribution.csv"
        if fdist.exists():
            fd = pd.read_csv(fdist)
            md += ["### Realized NN distance distribution per jitter (CICIDS2017, 5000 poison rows, all "
                   "asserted disjoint from trusted_eval benign by row content)", "",
                   fd[["jitter", "nn_p0", "nn_p5", "nn_p25", "nn_p50", "nn_p75", "nn_p95", "nn_p100"]]
                   .round(4).to_markdown(index=False), ""]
        if s0c is not None and len(s0c):
            md += ["### S0 on CICIDS as a class-prior reference (genuine attack rows, same ratios)", "",
                   s0c[["model", "threshold_mode", "poison_ratio", "delta_fpr", "delta_fpr_sd", "delta_tpr",
                        "delta_tpr_sd"]].round(4).to_markdown(index=False), ""]
        cost = (cic[(cic["scenario"] == "a1") & (cic["round"] == cic["round"].max())
                    & (cic["threshold_mode"] == "fixed")]
                .groupby("target_poison_ratio")[["cum_flows", "cum_packets", "cum_bytes", "cum_duration_s"]].mean())
        md += ["### Attacker cost of the poison (mean over jitter/seeds/models, final round; duration = summed "
               "flow time in seconds)", "", cost.round(1).to_markdown(), ""]
    if len(syn) and (syn["scenario"] == "a1").any():
        dsyn = paired_damage(syn, floors["synthetic"])
        dsyn.to_csv(sdir / "a1_damage_vs_fidelity.csv", index=False)
        md += ["### A1 on synthetic (raw benign already sits at realized NN ~0.49)", "",
               dsyn[["model", "threshold_mode", "poison_ratio", "jitter", "fidelity_median", "delta_fpr",
                     "delta_fpr_sd", "delta_tpr", "sigma_control_fpr", "sigma_control_tpr",
                     "exceeds_noise"]].round(4).to_markdown(index=False), ""]
    (args.root / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
