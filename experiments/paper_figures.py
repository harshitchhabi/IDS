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

# ACM sigconf column widths (in): single-column figures render at COL_W, full-width (figure*)
# ones at PAGE_W, so rcParams font sizes below come out ~8pt on the printed page -- matplotlib
# text is sized in points independent of figsize, so an oversized figure scaled down by
# \includegraphics{width=\linewidth} shrinks its text along with it.
COL_W, PAGE_W = 3.33, 7.0


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


# The tau=0.1 (honest-calibration) A1 damage-vs-distance sweep. F3/F4 predate this: their
# original source was the old round-0-calibration checkpoint, and the calibration fix (s19.1)
# moved the FPR channel's onset from ~1-2% to ~10-20% poison (s23) -- so a figure built on the
# old data would be showing a superseded result. This re-run (DECISIONS.md, rerun log) is
# scenarios {control, a1}, ratios {0.05, 0.1, 0.2, 0.5}, jitter {0, 0.01, 0.03, 0.1, 0.3, 0.7,
# 1.5}, 5 seeds, RF + XGBoost, both threshold modes, tau=0.1, results/phase0/loop/cicids_recal.
_RECAL_RATIOS = (0.05, 0.1, 0.2, 0.5)
# 0.002/0.005 (ratios 0.2, 0.5 only) were added to locate the cliff finer -- DECISIONS.md s26.2:
# they showed the MEDIAN barely moves (0.011 -> 0.012) while the damage already collapses, so
# the cliff is governed by the lower-tail p5 of the realized-distance distribution, not the
# median this figure's x-axis uses.
_RECAL_JITTERS = (0.0, 0.002, 0.005, 0.01, 0.03, 0.1, 0.3, 0.7, 1.5)


def _load_recal(root: Path = ROOT / "loop" / "cicids_recal") -> pd.DataFrame:
    """Undefended, tau=0.1 rows for the damage-vs-distance re-run: control + a1, the exact
    ratio/jitter grid above (the job directory also holds other sweeps' runs at other grid
    points, e.g. D1's ratio 0.8/0.9 jobs, which are excluded here so F3/F4 show a clean grid)."""
    files = glob.glob(str(root / "jobs" / "*.csv"))
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df = df[df.defense.fillna("none") == "none"]
    df = df[df.cost_padding.fillna(1.0) == 1.0]
    df = df[df.val_min_nn_distance.fillna(0.0) == 0.1]
    df = df[df.scenario.isin(("control", "a1"))]
    in_ratio = df.target_poison_ratio.apply(lambda r: any(np.isclose(r, x) for x in _RECAL_RATIOS))
    in_jitter = df.jitter.fillna(0.0).apply(lambda j: any(np.isclose(j, x) for x in _RECAL_JITTERS))
    return df[(df.scenario == "control") | (in_ratio & in_jitter)]


def _control_floor_recal(df: pd.DataFrame) -> pd.DataFrame:
    c = df[(df.scenario == "control") & (df["round"] >= 11)]
    return pd.DataFrame([
        {"model": model, "threshold_mode": mode, "metric": metric, "sigma_control": g[metric].std(ddof=1)}
        for (model, mode), g in c.groupby(["model", "threshold_mode"]) for metric in ("fpr", "tpr")])


def _paired_damage_recal(df: pd.DataFrame, floor: pd.DataFrame) -> pd.DataFrame:
    """Same-seed final-round delta vs control, by (model, threshold_mode, jitter, ratio) --
    the same definition experiments/phase0_loop_report.py:paired_damage uses."""
    last = df["round"].max()
    fin = df[df["round"] == last]
    ctrl = fin[fin.scenario == "control"].set_index(["model", "threshold_mode", "seed"])
    a1 = fin[fin.scenario == "a1"]
    fl = floor.set_index(["model", "threshold_mode", "metric"])
    # A few (model, jitter) cells were generated by an earlier sweep with --no-fidelity and
    # carry no fidelity_median; realized distance for a given jitter does not depend on the
    # poison ratio (confirmed: <1% spread across ratios for every other jitter here), so a
    # missing cell is filled from the same jitter's median over the ratios that do have it,
    # rather than left as NaN (which would mislabel the point instead of just plotting it).
    jitter_fidelity = a1.groupby("jitter")["fidelity_median"].median()
    rows = []
    for (model, mode, jit, ratio), g in a1.groupby(["model", "threshold_mode", "jitter", "target_poison_ratio"]):
        d_fpr = [r.fpr - ctrl.loc[(model, mode, r.seed)].fpr for r in g.itertuples()]
        d_tpr = [r.tpr - ctrl.loc[(model, mode, r.seed)].tpr for r in g.itertuples()]
        fid = g.fidelity_median.mean()
        if pd.isna(fid):
            fid = jitter_fidelity.get(jit, np.nan)
        rows.append({"model": model, "threshold_mode": mode, "jitter": jit, "poison_ratio": ratio,
                    "fidelity_median": fid, "n_seeds": len(g),
                    "delta_fpr": np.mean(d_fpr), "delta_tpr": np.mean(d_tpr),
                    "sigma_control_fpr": fl.loc[(model, mode, "fpr"), "sigma_control"],
                    "sigma_control_tpr": fl.loc[(model, mode, "tpr"), "sigma_control"]})
    return pd.DataFrame(rows)


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

    fig, ax = plt.subplots(figsize=(COL_W, 4.1))
    y = np.arange(len(d))
    colors = [BLUE if inc else MUT for inc in included]
    # Dots only: on a log x-axis a stem's length is dominated by the (arbitrary) left edge, not
    # the value it represents, so a stem here would carry no information (dataviz anti-pattern).
    ax.scatter(d.median_rms, y, color=colors, s=22, zorder=3, edgecolor="white", linewidth=0.4)
    ax.set_yticks(y)
    ax.set_yticklabels(d.family)
    for lbl, f in zip(ax.get_yticklabels(), d.family):
        if f == "BENIGN":
            lbl.set_fontweight("bold")
    ax.set_xscale("log")
    ax.set_xlim(3e-6, 2)
    ax.set_ylim(-1.2, len(d) - 0.2)
    ax.axvline(LEAK_BAR, color=RED, ls="--", lw=1.1, zorder=1)
    # Label sits low, right of the line, where no point in this dataset falls within two
    # decades of the threshold -- clear of Heartbleed (top row) and of every other point.
    ax.text(LEAK_BAR * 1.3, 1.6, "guard c\n= 0.25", color=RED, fontsize=6.5, va="center", ha="left")
    ax.set_xlabel("median NN RMS distance to a same-label\ntraining twin, normalized space, log scale", fontsize=7.5)
    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=BLUE, markersize=5.5,
                          label="≥500 eval rows"),
              plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=MUT, markersize=5.5,
                          label="<500 eval rows")]
    ax.legend(handles=handles, frameon=True, framealpha=0.9, edgecolor="none", fontsize=6.5,
             loc="lower right")
    _style(ax)
    fig.tight_layout()
    save(fig, "F2_nn_by_family")


# ---- F3: damage vs realized mimicry distance (tau=0.1 re-run) ---------------------------------
def fig_f3() -> None:
    df = _load_recal()
    floor = _control_floor_recal(df)
    dm = _paired_damage_recal(df, floor)
    ratios = sorted(dm.poison_ratio.unique())
    models = ("rf", "xgboost")
    fig, axes = plt.subplots(2, 2, figsize=(PAGE_W, 4.9), sharex=True)
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
            ax.axvline(LEAK_BAR, color=RED, ls="--", lw=1.1)
            ax.set_xscale("log")
            ax.set_title(f"{model}: {ylab}", fontsize=8.5, loc="left")
            _style(ax)
    for ax in axes[1]:
        ax.set_xlabel("realized mimicry distance (log)", fontsize=8)
    axes[0, 0].legend(fontsize=6, frameon=False, title="final poison ratio", title_fontsize=6, ncol=2)
    fig.tight_layout()
    save(fig, "F3_damage_vs_fidelity")


# ---- F4: A1 trajectories, fixed vs recalibrated (tau=0.1 re-run) ------------------------------
def fig_f4(ratio: float = 0.2) -> None:
    df = _load_recal()
    a1_all = df[df.scenario == "a1"]
    a1 = a1_all[np.isclose(a1_all.target_poison_ratio, ratio)]
    ctrl = df[df.scenario == "control"]
    jits = sorted(a1.jitter.unique())
    # See _paired_damage_recal: a few (model, jitter) cells at this ratio predate fidelity
    # recording; fill from the same jitter's median fidelity at another ratio rather than
    # showing "realized NN nan" (realized distance does not depend on poison ratio).
    jitter_fidelity = a1_all.groupby("jitter")["fidelity_median"].median()
    models = ("rf", "xgboost")
    fig, axes = plt.subplots(2, 2, figsize=(PAGE_W, 4.9), sharex=True)
    for i, model in enumerate(models):
        for j, (mode, metric, title) in enumerate((("fixed", "fpr", "FPR, fixed threshold"),
                                                    ("recalibrated", "tpr", "TPR, recalibrated threshold"))):
            ax = axes[i, j]
            for k, jit in enumerate(jits):
                g = a1[(a1.model == model) & (a1.threshold_mode == mode) & (a1.jitter == jit)]
                m = g.groupby("round")[metric].mean()
                fid = g.fidelity_median.mean()
                if pd.isna(fid):
                    fid = jitter_fidelity.get(jit, float("nan"))
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
    fig.tight_layout()
    save(fig, "F4_a1_trajectory")


# ---- F5: mechanism isolation -------------------------------------------------------------------
def _mechanism_rows() -> pd.DataFrame:
    """The four F5 bars: RF, recalibrated threshold, ratio 0.2, honest calibration (cicids_recal).
    A1 / a1truth / s0j share the jitter-0.70 run (realized NN ~0.56, DECISIONS.md s23); junk has no
    jitter parameter of its own but was launched under that same jitter-1.5 sweep config."""
    d = pd.read_csv(ROOT / "export" / "summary.csv")
    d = d[(d.model == "rf") & (d.threshold_mode == "recalibrated") & (d.target_poison_ratio == 0.2)
         & (d.defense.fillna("none") == "none") & (d.run_dir == "cicids_recal")]
    picks = [("a1", 0.70, RED), ("a1truth", 0.70, MUT), ("s0j", 0.70, MUT), ("junk", -1.00, MUT)]
    rows = []
    for sc, jit, color in picks:
        r = d[(d.scenario == sc) & np.isclose(d.jitter, jit)]
        if len(r) != 1:
            raise ValueError(f"expected exactly one row for {sc} jitter={jit}, got {len(r)}")
        r = r.iloc[0]
        rows.append({"scenario": sc, "mean": r.delta_tpr_mean, "sd": r.delta_tpr_std, "n": r.n_seeds,
                    "sigma_control": r.sigma_control_tpr, "fidelity_median": r.fidelity_median_mean,
                    "color": color})
    return pd.DataFrame(rows)


def fig_f5() -> None:
    t = _mechanism_rows()
    sigma = t.sigma_control.iloc[0]
    a1_nn = t.loc[t.scenario == "a1", "fidelity_median"].iloc[0]
    labels = {"a1": "A1", "a1truth": "a1truth", "s0j": "s0j", "junk": "junk"}

    fig, ax = plt.subplots(figsize=(COL_W, 2.7))
    x = np.arange(len(t))
    ax.axhspan(-2 * sigma, 2 * sigma, color=MUT, alpha=0.18, lw=0, zorder=1)
    ax.axhline(0, color="#4a4a4a", lw=0.8, zorder=1)
    ax.bar(x, t["mean"], yerr=t.sd, color=t.color, width=0.55, zorder=3,
          error_kw=dict(elinewidth=1.0, capsize=2.5, ecolor="#1a1a1a"))
    ax.set_xticks(x)
    ax.set_xticklabels([labels[s] for s in t.scenario], fontsize=7.5)
    ax.set_xlim(-0.6, len(t) - 0.4)
    ax.text(0.02, 0.965, "control ±2σ", color="#5a5a5a", fontsize=6, transform=ax.transAxes,
           va="top", ha="left")
    ax.set_ylabel("Δ TPR vs control (RF, recal.,\nratio 0.2, n=5 seeds)", fontsize=7)
    _style(ax)
    fig.tight_layout()
    save(fig, "F5_mechanism_isolation")
    return a1_nn


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
    """Recovery (poison ratios 0.5 and 0.9) and retention (CICIDS 0.2, synthetic 0.05/0.2) for
    each cap, from the raw per-seed job CSVs (DECISIONS.md s25.5). Independent of
    frontier_points.csv on purpose -- that file only has the three caps chosen for s25.2-25.3,
    not the full curve."""
    cic_jobs = ROOT / "loop" / "cicids_recal" / "jobs"
    syn_jobs = ROOT / "loop" / "synthetic" / "jobs"

    def retention(c, ratio, jobs, tag):
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

    rows = []
    for c in caps:
        row = {"defense": f"sharecap_c{c:g}", "family": "ShareCap", "cap": c,
              "retention_cicids r0.2": retention(c, 0.2, cic_jobs, "_vt0.1"),
              "retention_synthetic r0.05": retention(c, 0.05, syn_jobs, ""),
              "retention_synthetic r0.2": retention(c, 0.2, syn_jobs, "")}
        for ratio in (0.5, 0.9):
            rec, n = _paired_last_round(
                glob.glob(str(cic_jobs / f"a1_xgboost_s*_j0.0_r{ratio}_vt0.1_sharecap_c{c:g}.csv")),
                glob.glob(str(cic_jobs / f"a1_xgboost_s*_j0.0_r{ratio}_vt0.1.csv")), "fpr")
            row[f"recovery_r{ratio}"] = float(1 - rec["a"].mean() / rec["b"].mean()) if rec else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


_F6_COL = {"D1": BLUE, "D1q": AQUA, "D1fixed": VIOLET, "kNN sanitize": RED, "loss filter": YELLOW,
          "uniform": MUT, "ShareCap": ORANGE}
_F6_CAPS_TO_LABEL = (0.05, 0.1, 0.2)


def _f6_panel(ax, tab, sc, ycol: str, xcol: str, zoom: dict | None = None) -> None:
    """One (retention axis, poison ratio) panel: points for every non-ShareCap family that has
    ``ycol`` recorded, the uniform no-skill line, and the full ShareCap cap curve."""
    def draw(a, xscale=1.0, yscale=1.0, annotate=False, marker_scale=1.0):
        for fam, sub in tab[tab.family != "ShareCap"].groupby("family"):
            s = sub.dropna(subset=[xcol, ycol]) if {xcol, ycol} <= set(sub.columns) else sub.iloc[0:0]
            if s.empty:
                continue
            pre = s.defense == "d1_E8_g2"
            a.scatter(xscale * s.loc[~pre, xcol], yscale * s.loc[~pre, ycol], s=16 * marker_scale,
                     color=_F6_COL.get(fam, "#333333"), marker={"kNN sanitize": "D"}.get(fam, "o"),
                     edgecolor="white", linewidth=0.4, label=fam, zorder=4)
            if pre.any():
                p = s[pre]
                a.scatter(xscale * p[xcol], yscale * p[ycol], s=95 * marker_scale, facecolor="none",
                         edgecolor="black", linewidth=1.2, marker="o", zorder=5)
        u = tab[tab.family == "uniform"].dropna(subset=[xcol, ycol]).sort_values(xcol) if xcol in tab else tab.iloc[0:0]
        if len(u) > 1:
            a.plot(xscale * u[xcol], yscale * u[ycol], color=_F6_COL["uniform"], lw=1.0, ls=":", zorder=2)
        s6 = sc.dropna(subset=[xcol, ycol]).sort_values("cap") if {xcol, ycol} <= set(sc.columns) else sc.iloc[0:0]
        if len(s6):
            a.plot(xscale * s6[xcol], yscale * s6[ycol], color=_F6_COL["ShareCap"], lw=1.4, zorder=2)
            a.scatter(xscale * s6[xcol], yscale * s6[ycol], s=18 * marker_scale, color=_F6_COL["ShareCap"],
                     marker="s", edgecolor="white", linewidth=0.4, label="ShareCap (cap curve)", zorder=3)
            if annotate:
                offsets = [(4, -10), (4, 3), (4, 16)]
                for i, cap in enumerate(_F6_CAPS_TO_LABEL):
                    row = s6[np.isclose(s6.cap, cap)]
                    if len(row):
                        dx, dy = offsets[i % len(offsets)]
                        a.annotate(f"c={cap:g}", (xscale * row[xcol].iloc[0], yscale * row[ycol].iloc[0]),
                                  fontsize=5, color=_F6_COL["ShareCap"], xytext=(dx, dy),
                                  textcoords="offset points", ha="left" if dx >= 0 else "right", va="center")

    # Cap labels go in whichever view (the main panel, or the zoomed inset) has room for them.
    draw(ax, xscale=100, yscale=100, annotate=zoom is None)
    ax.set_xlim(-5, 110)
    ax.set_ylim(-5, 108)
    _style(ax)
    if zoom is not None:
        iax = ax.inset_axes(zoom["pos"])
        draw(iax, xscale=100, yscale=100, marker_scale=0.7, annotate=True)
        iax.set_xlim(*zoom["xlim"])
        iax.set_ylim(*zoom["ylim"])
        iax.set_xticks([]); iax.set_yticks([])
        for s in iax.spines.values():
            s.set_edgecolor("#888888")
            s.set_linewidth(0.6)
        ax.indicate_inset_zoom(iax, edgecolor="#888888", linewidth=0.6)


def fig_f6() -> None:
    tab = pd.read_csv(ROOT / "frontier" / "frontier_points.csv")
    caps = [0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5]
    sc = _sharecap_curve(caps)

    # (retention axis label, x column, inset zoom into the crowded top-right corner or None)
    panels = [("CICIDS r0.2", "retention_cicids r0.2",
              {"pos": [0.03, 0.42, 0.5, 0.55], "xlim": (55, 102), "ylim": (78, 103)}),
             ("synthetic r0.05", "retention_synthetic r0.05",
              {"pos": [0.06, 0.06, 0.55, 0.5], "xlim": (85, 102), "ylim": (82, 103)}),
             ("synthetic r0.2", "retention_synthetic r0.2",
              {"pos": [0.06, 0.06, 0.55, 0.5], "xlim": (80, 102), "ylim": (78, 103)})]
    fig, axes = plt.subplots(2, 3, figsize=(PAGE_W, 4.6), sharex="col", sharey="row")
    for row, ratio in enumerate((0.5, 0.9)):
        ycol = f"recovery_r{ratio}"
        for col_i, (label, xcol, zoom) in enumerate(panels):
            ax = axes[row, col_i]
            _f6_panel(ax, tab, sc, ycol, xcol, zoom=zoom if row == 0 else None)
            if row == 1:
                ax.set_xlabel(f"retention of S0 gain ({label}), %", fontsize=7)
        axes[row, 0].set_ylabel(f"recovery of A1 damage\n(ratio {ratio}), %", fontsize=7)
    h, l = axes[0, 0].get_legend_handles_labels()
    seen = dict(zip(l, h))
    seen["D1 (pre-registered)"] = plt.Line2D([0], [0], marker="o", color="none", markerfacecolor="none",
                                             markeredgecolor="black", markersize=8, markeredgewidth=1.2)
    fig.legend(seen.values(), seen.keys(), fontsize=6, frameon=False, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
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
