"""The recovery / retention frontier for D1 and its variants (DECISIONS.md §24).

Every defense is one point on two axes, both against the same-seed control (5 seeds):

* **Recovery** R = 1 - mean(dFPR_defended) / mean(dFPR_undefended): A1 at raw benign fidelity
  (jitter 0), CICIDS, honest calibration (tau = 0.1), fixed threshold, XGBoost. Ratio 0.5 is
  the frontier ratio; ratio 0.9 is recorded for the points that were run there, because a
  defense that only caps the poison's *effective share* stops working when the nominal ratio
  rises.
* **Retention** U = mean(gain_defended) / mean(gain_undefended): S0 (genuine attack rows), the
  ``honeypot_only`` TPR gain over the control, fixed threshold, XGBoost. Measured twice:
  on **synthetic** (ratios 0.05 / 0.2; the dataset that can carry a learning claim) and on
  **CICIDS** (ratio 0.2), so that recovery and retention come from the *same* dataset. The
  first version of this report measured them on different datasets, which lets a defense that
  normalises per dataset look better than one that does not.

Points: kNN sanitize, loss filter, the D1 grid (E* x gamma), D1q (quantile E*), D1fixed (no
trusted data), and the uniform-weight no-skill line. Dominance is tested against kNN and against
the uniform points, by mean and by seed bootstrap. Also measured: how well cost separates benign
from attack flows in each dataset (AUROC of effort), and D1's overhead vs kNN's at full precision.

Writes ``results/phase0/frontier/``.
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

from dloop.adversary.base import per_flow_cost
from dloop.defense.d1_cost_weighting import CostFunction, D1Config
from dloop.loop.data import LoopData
from dloop.models.metrics import auroc

ROOT = Path("results/phase0/loop")
DAMAGE_RATIO = 0.5
HIGH_RATIO = 0.9
N_BOOT = 4000
RNG = np.random.default_rng(20250903)
# (label, dataset key, S0 ratio): the retention axes
UTIL = (("synthetic r0.05", "syn", 0.05), ("synthetic r0.2", "syn", 0.2), ("cicids r0.2", "cic", 0.2))


def _load(dirname: str, tau: float) -> pd.DataFrame:
    files = glob.glob(str(ROOT / dirname / "jobs" / "*.csv"))
    use = {"scenario", "model", "seed", "target_poison_ratio", "round", "threshold_mode", "fpr", "tpr",
           "tpr_honeypot_only", "tpr_seen_both", "jitter", "val_min_nn_distance", "defense", "cost_padding",
           "hp_mean_weight", "defense_seconds", "fit_seconds", "n_honeypot"}
    df = pd.concat((pd.read_csv(f, float_precision="round_trip", usecols=lambda c: c in use) for f in files),
                   ignore_index=True)
    for c, v in (("val_min_nn_distance", 0.0), ("defense", "none"), ("cost_padding", 1.0)):
        df[c] = df[c].fillna(v) if c in df else v
    return df[np.isclose(df["val_min_nn_distance"], tau) & (df["cost_padding"] == 1.0)]


def _fin(df: pd.DataFrame, model: str = "xgboost") -> pd.DataFrame:
    return df[(df["round"] == df["round"].max()) & (df["model"] == model) & (df["threshold_mode"] == "fixed")]


def _paired(df: pd.DataFrame, scenario: str, defense: str, ratio: float, metric: str, jitter: float | None) -> pd.Series:
    ctrl = df[df.scenario == "control"].set_index("seed")[metric]
    q = df[(df.scenario == scenario) & (df.defense == defense) & np.isclose(df.target_poison_ratio, ratio)]
    if jitter is not None:
        q = q[np.isclose(q.jitter, jitter)]
    q = q.set_index("seed")[metric]
    seeds = sorted(set(q.index) & set(ctrl.index))
    return (q.loc[seeds] - ctrl.loc[seeds]) if seeds else pd.Series(dtype=float)


def _boot(num: np.ndarray, den: np.ndarray, kind: str) -> tuple[float, np.ndarray]:
    """kind='recovery': 1 - mean(num)/mean(den); kind='retention': mean(num)/mean(den)."""
    f = (lambda a, b: 1.0 - a / b) if kind == "recovery" else (lambda a, b: a / b)
    idx = RNG.integers(0, len(num), size=(N_BOOT, len(num)))
    return f(num.mean(), den.mean()), f(num[idx].mean(axis=1), den[idx].mean(axis=1))


def family(d: str) -> str:
    if d.startswith("d1q_"):
        return "D1q"
    if d.startswith("d1fixed_"):
        return "D1fixed"
    if d.startswith("d1_") and d.count("_") == 2:
        return "D1"
    if d.startswith("sharecap"):
        return "ShareCap"
    return {"knn": "kNN sanitize", "loss": "loss filter"}.get(d, "uniform" if d.startswith("uniform") else d)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/frontier"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    cic_all, syn_all = _load("cicids_recal", 0.1), _load("synthetic", 0.0)
    cic, syn = _fin(cic_all), _fin(syn_all)
    ds = {"cic": cic, "syn": syn}
    defenses = sorted(set(cic[(cic.scenario == "a1")].defense) & set(syn[(syn.scenario == "s0")].defense) - {"none"})

    dmg_und = _paired(cic, "a1", "none", DAMAGE_RATIO, "fpr", 0.0)
    dmg_und_hi = _paired(cic, "a1", "none", HIGH_RATIO, "fpr", 0.0)
    gain_und = {(k, r): _paired(ds[k], "s0", "none", r, "tpr_honeypot_only", None) for _, k, r in UTIL}

    rows = []
    for d in defenses:
        dmg = _paired(cic, "a1", d, DAMAGE_RATIO, "fpr", 0.0)
        seeds = sorted(set(dmg.index) & set(dmg_und.index))
        if len(seeds) < 3:
            continue
        rec, rb = _boot(dmg.loc[seeds].to_numpy(), dmg_und.loc[seeds].to_numpy(), "recovery")
        row = {"defense": d, "family": family(d), "recovery_r0.5": rec, "recovery_r0.5_boot_sd": rb.std(),
               "residual_fpr_rise_r0.5": dmg.mean()}
        hi = _paired(cic, "a1", d, HIGH_RATIO, "fpr", 0.0)
        sh = sorted(set(hi.index) & set(dmg_und_hi.index))
        if len(sh) >= 3:
            rec_hi, rhb = _boot(hi.loc[sh].to_numpy(), dmg_und_hi.loc[sh].to_numpy(), "recovery")
            row["recovery_r0.9"], row["recovery_r0.9_boot_sd"] = rec_hi, rhb.std()
        for label, k, r in UTIL:
            g, gu = _paired(ds[k], "s0", d, r, "tpr_honeypot_only", None), gain_und[(k, r)]
            s = sorted(set(g.index) & set(gu.index))
            if len(s) >= 3 and gu.loc[s].mean() > 0.01:
                est, b = _boot(g.loc[s].to_numpy(), gu.loc[s].to_numpy(), "retention")
                row[f"retention_{label}"], row[f"retention_{label}_boot_sd"] = est, b.std()
        w = syn[(syn.scenario == "s0") & (syn.defense == d) & np.isclose(syn.target_poison_ratio, 0.2)]["hp_mean_weight"]
        wc = cic[(cic.scenario == "s0") & (cic.defense == d) & np.isclose(cic.target_poison_ratio, 0.2)]["hp_mean_weight"]
        row["s0_mean_weight_synthetic"], row["s0_mean_weight_cicids"] = (w.mean() if len(w) else np.nan,
                                                                       wc.mean() if len(wc) else np.nan)
        rows.append(row)
    tab = pd.DataFrame(rows).sort_values(["family", "defense"])
    tab.to_csv(args.out / "frontier_points.csv", index=False)

    # ---- dominance: D1 settings against kNN and against the uniform baselines -----------------
    def dominance(challenger: str, ref: str, label: str, k: str, r: float) -> dict | None:
        a, b = _paired(cic, "a1", challenger, DAMAGE_RATIO, "fpr", 0.0), _paired(cic, "a1", ref, DAMAGE_RATIO, "fpr", 0.0)
        ga, gb = _paired(ds[k], "s0", challenger, r, "tpr_honeypot_only", None), _paired(ds[k], "s0", ref, r, "tpr_honeypot_only", None)
        gu = gain_und[(k, r)]
        s1, s2 = sorted(set(a.index) & set(b.index) & set(dmg_und.index)), sorted(set(ga.index) & set(gb.index) & set(gu.index))
        if len(s1) < 3 or len(s2) < 3:
            return None
        rec = lambda x, i: 1 - x.loc[s1].to_numpy()[i].mean() / dmg_und.loc[s1].to_numpy()[i].mean()   # noqa: E731
        ret = lambda x, j: x.loc[s2].to_numpy()[j].mean() / gu.loc[s2].to_numpy()[j].mean()           # noqa: E731
        hit = 0
        for _ in range(N_BOOT):
            i, j = RNG.integers(0, len(s1), len(s1)), RNG.integers(0, len(s2), len(s2))
            hit += (rec(a, i) >= rec(b, i)) and (ret(ga, j) >= ret(gb, j))
        i0, j0 = np.arange(len(s1)), np.arange(len(s2))
        return {"challenger": challenger, "vs": ref, "retention_axis": label,
                "challenger_recovery": rec(a, i0), "ref_recovery": rec(b, i0),
                "challenger_retention": ret(ga, j0), "ref_retention": ret(gb, j0),
                "dominates_by_mean": bool(rec(a, i0) >= rec(b, i0) and ret(ga, j0) >= ret(gb, j0)),
                "challenger_recovery_r0.9": _rec_hi(challenger), "ref_recovery_r0.9": _rec_hi(ref),
                "P_dominates_bootstrap": hit / N_BOOT}

    def _rec_hi(d: str) -> float:
        hi_ = _paired(cic, "a1", d, HIGH_RATIO, "fpr", 0.0)
        sh_ = sorted(set(hi_.index) & set(dmg_und_hi.index))
        return float(1 - hi_.loc[sh_].mean() / dmg_und_hi.loc[sh_].mean()) if len(sh_) >= 3 else float("nan")

    dom = []
    refs = [d for d in ("knn", "uniform_w0.1", "uniform_w0.05", "sharecap_c0.03", "sharecap_c0.05", "sharecap_c0.08")
            if d in set(tab.defense)]
    for c in tab[tab.family.isin(["D1", "D1q", "D1fixed"])].defense:
        for ref in refs:
            for label, k, r in UTIL:
                x = dominance(c, ref, label, k, r)
                if x:
                    dom.append(x)
    td = pd.DataFrame(dom)
    if len(td):
        # both poison ratios: a challenger must also match the reference at 0.9 wherever both were run
        both = td["challenger_recovery_r0.9"].notna() & td["ref_recovery_r0.9"].notna()
        td["dominates_at_both_ratios"] = td["dominates_by_mean"] & (~both | (td["challenger_recovery_r0.9"] >= td["ref_recovery_r0.9"]))
    td.to_csv(args.out / "dominance.csv", index=False)

    # ---- cost separability ------------------------------------------------------------------
    sep = []
    for name in ("cicids", "synthetic"):
        d = LoopData.load(f"data/loop/{name}.npz")
        cf = CostFunction(per_flow_cost(d.seed_x[d.seed_y == 0]), D1Config())
        e_b, e_a = cf.effort(per_flow_cost(d.pool_benign_x[::10])), cf.effort(per_flow_cost(d.pool_attack_x[::4]))
        y = np.r_[np.zeros(len(e_b)), np.ones(len(e_a))]
        sep.append({"dataset": name, "auroc_effort_attack_vs_benign": auroc(y, np.r_[e_b, e_a]),
                    "benign_effort_p50": np.median(e_b), "benign_effort_p90": np.percentile(e_b, 90),
                    "attack_effort_p50": np.median(e_a), "attack_effort_p10": np.percentile(e_a, 10),
                    "attack_share_above_benign_p90": float((e_a > np.percentile(e_b, 90)).mean())})
    ts = pd.DataFrame(sep)
    ts.to_csv(args.out / "cost_separability.csv", index=False)

    # ---- overhead ---------------------------------------------------------------------------
    ov = []
    for f in glob.glob(str(ROOT / "cicids_recal" / "jobs" / "a1_xgboost_*_j0.0_r0.5_*.csv")):
        if "_pad" in f:                      # cost-padded runs share the defense name
            continue
        x = pd.read_csv(f, usecols=["defense", "seed", "round", "threshold_mode", "defense_seconds", "fit_seconds", "n_honeypot"])
        x = x[(x.threshold_mode == "fixed") & (x.n_honeypot > 0)]
        if len(x) and x.defense.iloc[0] in ("d1_E8_g2", "knn", "loss"):
            ov.append({"defense": x.defense.iloc[0], "seed": x.seed.iloc[0], "defense_s": x.defense_seconds.mean(),
                       "fit_s": x.fit_seconds.mean()})
    to = pd.DataFrame(ov)
    g = None
    ratio_txt = ""
    if len(to):
        g = to.groupby("defense").agg(defense_s_mean=("defense_s", "mean"), fit_s_mean=("fit_s", "mean"), n_jobs=("seed", "count"))
        g["overhead_vs_fit"] = g["defense_s_mean"] / g["fit_s_mean"]
        g.to_csv(args.out / "overhead_full_precision.csv")
        if {"d1_E8_g2", "knn"} <= set(to.defense):
            a, b = to[to.defense == "d1_E8_g2"].defense_s.to_numpy(), to[to.defense == "knn"].defense_s.to_numpy()
            rr = [b[RNG.integers(0, len(b), len(b))].mean() / a[RNG.integers(0, len(a), len(a))].mean() for _ in range(N_BOOT)]
            ratio_txt = (f"kNN / D1 overhead ratio: **{b.mean() / a.mean():,.0f}x** "
                         f"(95% bootstrap interval {np.percentile(rr, 2.5):,.0f}x - {np.percentile(rr, 97.5):,.0f}x).")

    # ---- figure: three retention axes ---------------------------------------------------------
    col = {"D1": "#08519c", "D1q": "#2a9d8f", "D1fixed": "#8e44ad", "kNN sanitize": "#d62728", "loss filter": "#d98c1f",
           "uniform": "#888888", "ShareCap": "#e377c2"}
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2), dpi=140, sharey=True)
    for ax, (label, _, _) in zip(axes, UTIL):
        c = f"retention_{label}"
        for fam, sub in tab.groupby("family"):
            s = sub.dropna(subset=[c]) if c in sub else sub.iloc[0:0]
            if s.empty:
                continue
            big = fam in ("kNN sanitize", "loss filter", "ShareCap")
            ax.scatter(100 * s[c], 100 * s["recovery_r0.5"], s=75 if big else 20, color=col.get(fam, "#333333"),
                       marker={"kNN sanitize": "D", "ShareCap": "s"}.get(fam, "o"), edgecolor="white", linewidth=0.5,
                       label=fam, zorder=3)
        u = tab[tab.family == "uniform"].dropna(subset=[c]).sort_values(c) if c in tab else tab.iloc[0:0]
        if len(u) > 1:
            ax.plot(100 * u[c], 100 * u["recovery_r0.5"], color=col["uniform"], lw=1.2, ls=":", zorder=2)
        ax.set_xlabel(f"retention of honeypot_only gain ({label}), %", fontsize=8)
        ax.set_xlim(-5, 110)
        ax.set_ylim(-5, 108)
        ax.grid(color="#e3e3e3", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("recovery of A1 damage (CICIDS, ratio 0.5), %", fontsize=8)
    axes[0].legend(fontsize=7, frameon=False, loc="lower left")
    fig.suptitle("Defense frontier (XGBoost, 5 seeds). Dotted = uniform down-weighting, the no-skill line. "
                 "Right panel measures both axes on CICIDS.", fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(args.out / "frontier.png")
    plt.close(fig)

    md = ["# Recovery / retention frontier", "",
          "Recovery: A1 copy fidelity, CICIDS (tau 0.1), XGBoost, 5 seeds, ratio 0.5 (and 0.9 where run). Retention: S0 "
          "`honeypot_only` gain on synthetic (ratios 0.05 / 0.2) and on CICIDS (ratio 0.2). Figure: `frontier.png`.", "",
          "## Points", "", tab.round(3).to_markdown(index=False), ""]
    if len(td):
        md += ["## Dominance", "",
               "Challenger dominates the reference iff its recovery >= and retention >= by mean; `P` is the seed-bootstrap "
               "probability of that joint event (clear if >= 0.9).", ""]
        for ref in refs:
            t = td[td.vs == ref]
            md += [f"### against `{ref}`: dominates by mean in {int(t.dominates_by_mean.sum())} of {len(t)} cases "
                   f"({int(t.dominates_at_both_ratios.sum())} also at ratio 0.9); clearly (P >= 0.9) in "
                   f"{int((t.P_dominates_bootstrap >= 0.9).sum())}", "",
                   t.sort_values("P_dominates_bootstrap", ascending=False).head(12).round(3).to_markdown(index=False), ""]
    md += ["## Cost separability of benign vs attack flows", "", ts.round(3).to_markdown(index=False), ""]
    if g is not None:
        md += ["## Overhead at full precision (mean seconds per round, rounds with honeypot data)", "", g.round(6).to_markdown(), "",
               ratio_txt, ""]
    (args.out / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
