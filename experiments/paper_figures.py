"""Paper figures, regenerated from committed CSVs alone (no re-running any experiment).

Six figures share one style module (fonts, spines, the two locked color scales) so the paper
reads as one document rather than a patchwork of report scripts. Each writes a vector PDF to
``paper/figures/`` plus a PNG preview at the same stem. Called via ``python scripts/run.py
figures``; see docs/PAPER_PLAN.md for what each figure argues and docs/DECISIONS.md for the
numbers behind it.

Two color scales, used consistently everywhere in this module (dataviz skill: categorical hues
in fixed order, never cycled; sequential = one hue, light -> dark; color follows the entity):

* ``CAT`` -- the validated 8-hue categorical palette, in its fixed order. Used only for identity
  (which defense, which mechanism arm). A family keeps its color across figures where it recurs.
* ``SEQ_BLUE`` -- one hue, seven steps, light -> dark. Used only for an ordered quantity (poison
  ratio, mimicry-jitter ladder). Never used for identity.
* ``MUT`` -- neutral grey, reserved for "excluded from the claim" (too few eval rows) or "null
  control, not the point of the figure" -- a status, not a fifth category.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

ROOT = Path("results/phase0")
OUT = Path("paper/figures")

# ---- shared style -----------------------------------------------------------------------------
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
CAT = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED]
SEQ_BLUE = ["#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"]
MUT = "#8a8a86"
LEAK_BAR = 0.25   # guard-(c) leakage threshold, DECISIONS.md ss10/15


def setup_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 8.5,
        "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
        "figure.dpi": 140, "savefig.dpi": 300, "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.color": "#e3e3e3", "grid.linewidth": 0.6, "axes.edgecolor": "#4a4a4a",
        "text.color": "#1a1a1a", "axes.labelcolor": "#1a1a1a",
    })


def _style(ax) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(color="#e3e3e3", lw=0.6)


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / name}.pdf (+.png)")


def _load_jobs(dataset: str, root: Path = ROOT / "loop") -> pd.DataFrame:
    """Undefended, original-calibration loop rows for ``dataset`` -- the same filter
    experiments/phase0_loop_report.py uses, so F3/F4 read exactly what that report reads."""
    files = glob.glob(str(root / dataset / "jobs" / "*.csv"))
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    for col, keep in (("defense", lambda c: c.fillna("none") == "none"),
                      ("val_min_nn_distance", lambda c: c.fillna(0.0) == 0.0),
                      ("cost_padding", lambda c: c.fillna(1.0) == 1.0)):
        if col in df:
            df = df[keep(df[col])]
    return df


# ---- F2: per-family NN distance -------------------------------------------------------------
def fig_f2() -> None:
    fam = pd.read_csv(ROOT / "cicids" / "nn_by_family.csv")
    leak = json.loads((ROOT / "cicids" / "leakage_report.json").read_text())
    benign = leak["nn_distance"]["benign"]
    rows = [{"family": "BENIGN", "median_rms": benign["percentiles"]["p50"], "n": benign["n_query"]}]
    rows += [{"family": r.family, "median_rms": r.median_rms, "n": r.n_trusted_eval}
            for r in fam.itertuples()]
    d = pd.DataFrame(rows).sort_values("median_rms")
    included = d.n >= 500

    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    y = np.arange(len(d))
    colors = [BLUE if inc else MUT for inc in included]
    ax.hlines(y, 3e-6, d.median_rms, color=colors, lw=1.4, zorder=2)
    ax.scatter(d.median_rms, y, color=colors, s=34, zorder=3,
               edgecolor="white", linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(d.family)
    for lbl, f in zip(ax.get_yticklabels(), d.family):
        if f == "BENIGN":
            lbl.set_fontweight("bold")
    ax.set_xscale("log")
    ax.set_xlim(3e-6, 2)
    ax.axvline(LEAK_BAR, color=RED, ls="--", lw=1.2, zorder=1)
    ax.text(0.815, 0.99, "leakage threshold\n(guard c) = 0.25", color=RED, fontsize=7, va="top", ha="left",
           transform=ax.transAxes)
    ax.set_xlabel("median nearest-neighbour RMS distance to a\nsame-label training twin, normalized space, log scale")
    ax.set_title("CICIDS2017 is near-degenerate in CICFlowMeter feature space", loc="left", fontsize=9.5)
    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=BLUE, markersize=6,
                          label="≥500 eval rows (reportable)"),
              plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=MUT, markersize=6,
                          label="<500 eval rows")]
    ax.legend(handles=handles, frameon=True, framealpha=0.9, edgecolor="none", loc="lower left",
             bbox_to_anchor=(0.0, 0.0))
    _style(ax)
    fig.tight_layout()
    save(fig, "F2_nn_by_family")


# ---- F3: damage vs realized mimicry distance (restyle) ---------------------------------------
def fig_f3() -> None:
    dm = pd.read_csv(ROOT / "loop" / "cicids" / "a1_damage_vs_fidelity.csv")
    s0 = pd.read_csv(ROOT / "loop" / "cicids" / "s0_reference_damage.csv")
    ratios = sorted(dm.poison_ratio.unique())
    models = ("rf", "xgboost")
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), sharex=True)
    for i, model in enumerate(models):
        for j, (mode, col, ylab, sgn) in enumerate((
                ("fixed", "delta_fpr", "FPR increase vs control", 1),
                ("recalibrated", "delta_tpr", "TPR drop vs control", -1))):
            ax = axes[i, j]
            sub = dm[(dm.model == model) & (dm.threshold_mode == mode)]
            sig = sub["sigma_control_fpr" if mode == "fixed" else "sigma_control_tpr"].iloc[0]
            ax.axhspan(-2 * sig, 2 * sig, color=MUT, alpha=0.2, lw=0)
            for k, r in enumerate(ratios):
                g = sub[np.isclose(sub.poison_ratio, r)].sort_values("fidelity_median")
                ax.plot(g.fidelity_median, sgn * g[col], marker="o", ms=3.5, lw=1.3,
                        color=SEQ_BLUE[min(k, len(SEQ_BLUE) - 1)], label=f"ratio {r:g}")
            ref = s0[(s0.model == model) & (s0.threshold_mode == mode)]
            for k, r in enumerate(ratios):
                v = ref[np.isclose(ref.poison_ratio, r)]
                if len(v):
                    ax.axhline(sgn * v[col].iloc[0], color=SEQ_BLUE[min(k, len(SEQ_BLUE) - 1)], ls=":", lw=1.0)
            ax.axvline(LEAK_BAR, color=RED, ls="--", lw=1.1)
            ax.set_xscale("log")
            ax.set_title(f"{model}: {ylab}", fontsize=8.5, loc="left")
            _style(ax)
    for ax in axes[1]:
        ax.set_xlabel("realized mimicry distance (log)", fontsize=8)
    axes[0, 0].legend(fontsize=6, frameon=False, title="final poison ratio", title_fontsize=6, ncol=2)
    fig.suptitle("A1 damage vs realized mimicry fidelity (grey band = ±2σ of control; "
                 "dotted = S0 at the same ratio)", fontsize=9.5, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, "F3_damage_vs_fidelity")


# ---- F4: A1 trajectories, fixed vs recalibrated (restyle) -------------------------------------
def fig_f4(ratio: float = 0.2) -> None:
    df = _load_jobs("cicids")
    show_jitters = (0.0, 0.01, 0.03, 0.1, 0.3, 1.5)
    a1 = df[(df.scenario == "a1") & np.isclose(df.target_poison_ratio, ratio)]
    ctrl = df[df.scenario == "control"]
    jits = [j for j in sorted(a1.jitter.unique()) if any(np.isclose(j, sj) for sj in show_jitters)]
    models = ("rf", "xgboost")
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), sharex=True)
    for i, model in enumerate(models):
        for j, (mode, metric, title) in enumerate((("fixed", "fpr", "FPR, fixed threshold"),
                                                    ("recalibrated", "tpr", "TPR, recalibrated threshold"))):
            ax = axes[i, j]
            for k, jit in enumerate(jits):
                g = a1[(a1.model == model) & (a1.threshold_mode == mode) & (a1.jitter == jit)]
                m = g.groupby("round")[metric].mean()
                fid = g.fidelity_median.mean()
                ax.plot(m.index, m.values, color=SEQ_BLUE[min(k * len(SEQ_BLUE) // max(len(jits), 1),
                                                              len(SEQ_BLUE) - 1)],
                        lw=1.5, label=f"realized NN {fid:.3f}")
            c = ctrl[(ctrl.model == model) & (ctrl.threshold_mode == mode)].groupby("round")[metric]
            cm, cs = c.mean(), c.std()
            ax.plot(cm.index, cm.values, color="#222222", lw=1.5, ls="--", label="control")
            ax.fill_between(cm.index, cm - 2 * cs, cm + 2 * cs, color=MUT, alpha=0.2, lw=0)
            ax.set_title(f"{model}: {title}", fontsize=8.5, loc="left")
            _style(ax)
    for ax in axes[1]:
        ax.set_xlabel("round", fontsize=8)
    axes[0, 0].legend(fontsize=6, frameon=False, title=f"poison ratio {ratio}, by mimicry fidelity",
                      title_fontsize=6)
    fig.suptitle(f"A1 on CICIDS2017, poison ratio {ratio} (band = control mean ± 2 sd across seeds)",
                 fontsize=9.5, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, "F4_a1_trajectory")


# ---- F5: mechanism isolation -------------------------------------------------------------------
def fig_f5() -> None:
    d = pd.read_csv(ROOT / "export" / "summary.csv")
    d = d[(d.model == "rf") & (d.threshold_mode == "recalibrated") & (d.target_poison_ratio == 0.2)
         & (d.defense.fillna("none") == "none") & (d.run_dir == "cicids_recal")]
    picks = [("a1", 0.70, "A1", RED), ("a1truth", 0.70, "a1truth", MUT), ("s0j", 0.70, "s0j", MUT),
             ("junk", -1.00, "junk", MUT)]
    rows = []
    for sc, jit, label, color in picks:
        r = d[(d.scenario == sc) & np.isclose(d.jitter, jit)]
        if len(r) != 1:
            raise ValueError(f"expected exactly one row for {sc} jitter={jit}, got {len(r)}")
        r = r.iloc[0]
        rows.append({"label": label, "mean": r.delta_tpr_mean, "sd": r.delta_tpr_std,
                    "n": r.n_seeds, "sigma_control": r.sigma_control_tpr, "color": color})
    t = pd.DataFrame(rows)
    sigma = t.sigma_control.iloc[0]

    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    x = np.arange(len(t))
    ax.axhspan(-2 * sigma, 2 * sigma, color=MUT, alpha=0.18, lw=0, zorder=1)
    ax.axhline(0, color="#4a4a4a", lw=0.8, zorder=1)
    ax.bar(x, t["mean"], yerr=t.sd, color=t.color, width=0.55, zorder=3,
          error_kw=dict(elinewidth=1.1, capsize=3, ecolor="#1a1a1a"))
    ax.set_xticks(x)
    ax.set_xticklabels(t.label, fontsize=8.5)
    ax.set_xlim(-0.6, len(t) - 0.4)
    ax.text(0.02, 0.965, "control ±2σ (noise floor)", color="#5a5a5a", fontsize=6.5,
           transform=ax.transAxes, va="top", ha="left")
    ax.set_ylabel("Δ TPR vs control, recalibrated\nthreshold (RF, ratio 0.2, n=5 seeds)", fontsize=8)
    ax.set_title("Only label conflict on high-fidelity poison moves the detector", loc="left", fontsize=9.5)
    caption = ("A1: benign, copy fidelity   ·   a1truth: same rows, true label   ·   "
              "s0j: genuine attack, jittered   ·   junk: marginal-shuffled bulk")
    fig.text(0.5, 0.005, caption, fontsize=6.5, ha="center", color="#5a5a5a")
    _style(ax)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, "F5_mechanism_isolation")


# ---- F6: defense frontier + ShareCap cap curve --------------------------------------------------
def _paired_last_round(files_a, files_b, metric: str, at_round: int = 20):
    """mean(files_a[metric] - files_b[metric]) at ``at_round``, paired by seed; None if <3 shared seeds."""
    def last(files):
        out = {}
        for f in files:
            seed = Path(f).name.split("_s")[1][0]
            x = pd.read_csv(f, float_precision="round_trip")
            x = x[(x.threshold_mode == "fixed") & (x["round"] == at_round)]
            if len(x):
                out[seed] = float(x[metric].iloc[0])
        return out
    a, b = last(files_a), last(files_b)
    shared = sorted(set(a) & set(b))
    if len(shared) < 3:
        return None, len(shared)
    return {"a": np.array([a[s] for s in shared]), "b": np.array([b[s] for s in shared])}, len(shared)


def _sharecap_curve(caps) -> pd.DataFrame:
    """Recovery (ratio 0.5) and retention (CICIDS 0.2, synthetic 0.05/0.2) for each cap, from the
    raw per-seed job CSVs (DECISIONS.md s25.5). Independent of frontier_points.csv on purpose --
    that file only has the three caps chosen for s25.2-25.3, not the full curve."""
    cic_jobs = ROOT / "loop" / "cicids_recal" / "jobs"
    syn_jobs = ROOT / "loop" / "synthetic" / "jobs"
    rows = []
    for c in caps:
        rec, n = _paired_last_round(
            glob.glob(str(cic_jobs / f"a1_xgboost_s*_j0.0_r0.5_vt0.1_sharecap_c{c:g}.csv")),
            glob.glob(str(cic_jobs / f"a1_xgboost_s*_j0.0_r0.5_vt0.1.csv")), "fpr")
        recovery = float(1 - rec["a"].mean() / rec["b"].mean()) if rec else np.nan

        def retention(ratio, dataset, jobs, tag):
            hp = glob.glob(str(jobs / f"s0_xgboost_s*_j0.0_r{ratio}{tag}_sharecap_c{c:g}.csv"))
            und = glob.glob(str(jobs / f"s0_xgboost_s*_j0.0_r{ratio}{tag}.csv"))
            ctl = glob.glob(str(jobs / f"control_xgboost_s*{tag}.csv"))
            def last_tpr(files):
                out = {}
                for f in files:
                    seed = Path(f).name.split("_s")[1][0]
                    x = pd.read_csv(f, float_precision="round_trip")
                    x = x[(x.threshold_mode == "fixed") & (x["round"] == 20)]
                    if len(x):
                        out[seed] = float(x.tpr.iloc[0])
                return out
            tp_hp, tp_und, tp_ctl = last_tpr(hp), last_tpr(und), last_tpr(ctl)
            shared = sorted(set(tp_hp) & set(tp_und) & set(tp_ctl))
            if len(shared) < 3:
                return np.nan
            gain_und = np.mean([tp_und[s] - tp_ctl[s] for s in shared])
            gain_hp = np.mean([tp_hp[s] - tp_ctl[s] for s in shared])
            return float(gain_hp / gain_und) if gain_und else np.nan

        rows.append({"defense": f"sharecap_c{c:g}", "family": "ShareCap", "cap": c,
                    "recovery_r0.5": recovery,
                    "retention_cicids r0.2": retention(0.2, "cicids", cic_jobs, "_vt0.1"),
                    "retention_synthetic r0.05": retention(0.05, "synthetic", syn_jobs, ""),
                    "retention_synthetic r0.2": retention(0.2, "synthetic", syn_jobs, "")})
    return pd.DataFrame(rows)


def fig_f6() -> None:
    tab = pd.read_csv(ROOT / "frontier" / "frontier_points.csv")
    caps = [0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5]
    sc = _sharecap_curve(caps).sort_values("cap")

    col = {"D1": BLUE, "D1q": AQUA, "D1fixed": VIOLET, "kNN sanitize": RED, "loss filter": YELLOW,
          "uniform": MUT, "ShareCap": ORANGE}
    panels = [("cicids r0.2", "retention_cicids r0.2"), ("synthetic r0.05", "retention_synthetic r0.05"),
             ("synthetic r0.2", "retention_synthetic r0.2")]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.6), sharey=True)
    for ax, (label, c) in zip(axes, panels):
        for fam, sub in tab[tab.family != "ShareCap"].groupby("family"):
            s = sub.dropna(subset=[c]) if c in sub else sub.iloc[0:0]
            if s.empty:
                continue
            is_preregistered = s.defense == "d1_E8_g2"
            ax.scatter(100 * s.loc[~is_preregistered, c], 100 * s.loc[~is_preregistered, "recovery_r0.5"],
                      s=18, color=col.get(fam, "#333333"), marker={"kNN sanitize": "D"}.get(fam, "o"),
                      edgecolor="white", linewidth=0.4, label=fam, zorder=3)
            if is_preregistered.any():
                p = s[is_preregistered]
                ax.scatter(100 * p[c], 100 * p["recovery_r0.5"], s=110, facecolor="none",
                          edgecolor="black", linewidth=1.3, marker="o", zorder=4)
        u = tab[tab.family == "uniform"].dropna(subset=[c]).sort_values(c) if c in tab else tab.iloc[0:0]
        if len(u) > 1:
            ax.plot(100 * u[c], 100 * u["recovery_r0.5"], color=col["uniform"], lw=1.1, ls=":", zorder=2)
        s6 = sc.dropna(subset=[c]).sort_values(c) if c in sc else sc.iloc[0:0]
        if len(s6):
            ax.plot(100 * s6[c], 100 * s6["recovery_r0.5"], color=col["ShareCap"], lw=1.6, zorder=2)
            ax.scatter(100 * s6[c], 100 * s6["recovery_r0.5"], s=24, color=col["ShareCap"],
                      marker="s", edgecolor="white", linewidth=0.4, label="ShareCap (full cap curve)", zorder=3)
        ax.set_xlabel(f"retention of honeypot_only gain ({label}), %", fontsize=7.5)
        ax.set_xlim(-5, 110)
        ax.set_ylim(-5, 108)
        _style(ax)
    axes[0].set_ylabel("recovery of A1 damage (CICIDS, ratio 0.5), %")
    h, l = axes[0].get_legend_handles_labels()
    seen = dict(zip(l, h))
    seen["D1 (pre-registered E*=8, g=2)"] = plt.Line2D([0], [0], marker="o", color="none", markerfacecolor="none",
                                                       markeredgecolor="black", markersize=9, markeredgewidth=1.3)
    axes[0].legend(seen.values(), seen.keys(), fontsize=6, frameon=False, loc="lower left")
    fig.suptitle("Defense frontier (XGBoost, 5 seeds). ShareCap's full cap-sensitivity curve "
                "(0.01-0.5) is undominated at every cap tested (DECISIONS.md s25.5).",
                fontsize=9.5, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, "F6_frontier")


FIGURES = {"F2": fig_f2, "F3": fig_f3, "F4": fig_f4, "F5": fig_f5, "F6": fig_f6}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="+", choices=list(FIGURES), default=None)
    args = ap.parse_args(argv)
    setup_style()
    for name in args.only or FIGURES:
        FIGURES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
