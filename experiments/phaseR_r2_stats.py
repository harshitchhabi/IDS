"""Phase R item R2 statistics (DECISIONS.md §31.2): ShareCap generality, per (dataset, model).

The tests are ``experiments.phase0_stats_recompute``'s paired t-test and paired sign-flip
permutation test (Monte Carlo, 10,000 resamples at n=15), imported, not reimplemented; Holm is
``experiments.phaseA_datasets_stats.holm``. Only the row selection is new: R2 arms differ by
defense (and, for R2.4, by crowd factor), which that machinery does not key on.

* **R2.1** per pair: recovery R (fixed-threshold Delta FPR, A1 ratio 0.5, jitter 0) and
  retention U (S0 ratio 0.2 gain on ``tpr_honeypot_only``, or overall ``tpr`` on UNSW-NB15) for
  every defense; the 15-cell Holm family (defended minus undefended FPR, direction "defense
  lowers FPR"); the two evaluability checks; the verdict; the cap curve; seed-bootstrap CIs for
  R_0.05 and U_0.05 - U_uniform0.05.
* **R2.3** (cicids, RF/XGBoost): R and U of ``srcpart_a0.5`` next to ShareCap 0.05, dominance by
  mean.
* **R2.4** (cicids, RF/XGBoost): loss l(m, d) = g(S0, d) - g(s0crowd_m, d), 6-cell Holm family per
  model (direction loss > 0), the bar, the dilution-attributable difference, and fixed-threshold
  Delta FPR for every crowd arm.

"Clears Holm" uses the paired t-test (primary, §31); the permutation family is reported beside it.

    python -m experiments.phaseR_r2_stats --dataset cicids
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import report_cell
from experiments.phaseA_datasets_stats import holm, load_jobs

ALPHA = 0.05
SEEDS = list(range(1, 16))
N_BOOT = 10_000
TAU = {"cicids": 0.1, "cicids-fixed": 0.0, "unsw-nb15": 0.0}
MODELS = {"cicids": ["rf", "xgboost", "logreg", "mlp"], "cicids-fixed": ["rf", "xgboost"],
          "unsw-nb15": ["rf", "xgboost"]}
# §31.2: honeypot_only (DoS Hulk) where it has >= 500 eval rows, all attack rows on UNSW-NB15.
U_METRIC = {"cicids": "tpr_honeypot_only", "cicids-fixed": "tpr_honeypot_only", "unsw-nb15": "tpr"}
CAPS = (0.02, 0.05, 0.1, 0.2)
DEFENSES = ["none"] + [f"sharecap_c{c:g}" for c in CAPS] + ["uniform_w0.05"]
RATIOS = (0.2, 0.5, 0.9)
CROWD = (1, 4, 9)


def defense_label(df: pd.DataFrame) -> pd.Series:
    """The job-key suffix form of each row's defense (phase0_loop._defense_suffix)."""
    d = df.defense.fillna("none")
    out = d.copy()
    out[d == "sharecap"] = "sharecap_c" + df.share_cap[d == "sharecap"].map(lambda v: f"{v:g}")
    out[d == "uniform"] = "uniform_w" + df.uniform_w[d == "uniform"].map(lambda v: f"{v:g}")
    out[d == "srcpart"] = "srcpart_a" + df.sp_alpha[d == "srcpart"].map(lambda v: f"{v:g}")
    return out


def final_by_seed(df: pd.DataFrame, model: str, scenario: str, defense: str, mode: str, metric: str,
                  ratio: float | None = None, crowd: float | None = None) -> pd.Series:
    """Final-round ``metric`` per seed (index = seed) for one arm."""
    sub = df[(df.model == model) & (df.scenario == scenario) & (df.threshold_mode == mode)
             & (df.def_label == defense) & df.seed.isin(SEEDS)]
    if scenario != "control":
        sub = sub[np.isclose(sub.target_poison_ratio, ratio)]
    if scenario == "a1":
        sub = sub[np.isclose(sub.jitter.fillna(0.0), 0.0)]
    if scenario == "s0crowd":
        sub = sub[np.isclose(sub.crowd_factor, crowd)]
    if sub.empty:
        return pd.Series(dtype=float)
    last = sub.groupby("seed")["round"].transform("max")
    sub = sub[sub["round"] == last]
    if sub.seed.duplicated().any():
        raise ValueError(f"duplicate final rows for {model} {scenario} {defense} {ratio} {crowd}")
    return sub.set_index("seed")[metric].sort_index()


def paired(a: pd.Series, b: pd.Series) -> np.ndarray:
    """a - b on the seeds both have."""
    s = sorted(set(a.index) & set(b.index))
    return (a.loc[s] - b.loc[s]).to_numpy()


def cell(d: np.ndarray, label: str, **meta) -> dict:
    r = report_cell(d, label)
    r.update(meta)
    return r


def apply_holm(rows: list[dict], direction: str) -> None:
    """Holm on p_t (primary) and p_perm; a cell clears only in the family's named direction."""
    for key in ("t", "perm"):
        thr, rej = holm(np.array([r[f"p_{key}"] for r in rows]))
        for r, th, rj in zip(rows, thr, rej, strict=True):
            r[f"holm_thr_{key}"], r[f"holm_reject_{key}"] = float(th), bool(rj)
    for r in rows:
        right_way = r["mean"] < 0 if direction == "negative" else r["mean"] > 0
        r["in_direction"] = bool(right_way)
        r["clears_holm"] = bool(r["holm_reject_t"] and right_way)
        r["clears_holm_perm"] = bool(r["holm_reject_perm"] and right_way)
        r["clears_opposite"] = bool(r["holm_reject_t"] and not right_way)


class Pair:
    """Per-seed final-round series for one (dataset, model)."""

    def __init__(self, df: pd.DataFrame, dataset: str, model: str):
        self.df, self.dataset, self.model = df, dataset, model
        self.u_metric = U_METRIC[dataset]
        self.ctrl_fpr = final_by_seed(df, model, "control", "none", "fixed", "fpr")
        self.ctrl_u = final_by_seed(df, model, "control", "none", "fixed", self.u_metric)
        self.ctrl_tpr_rec = final_by_seed(df, model, "control", "none", "recalibrated", "tpr")

    def a1(self, defense: str, ratio: float, mode: str = "fixed", metric: str = "fpr") -> pd.Series:
        return final_by_seed(self.df, self.model, "a1", defense, mode, metric, ratio)

    def dfpr(self, defense: str, ratio: float) -> pd.Series:
        a = self.a1(defense, ratio)
        s = sorted(set(a.index) & set(self.ctrl_fpr.index))
        return a.loc[s] - self.ctrl_fpr.loc[s]

    def g(self, defense: str, scenario: str = "s0", crowd: float | None = None,
          metric: str | None = None) -> pd.Series:
        metric = metric or self.u_metric
        ctrl = self.ctrl_u if metric == self.u_metric else final_by_seed(
            self.df, self.model, "control", "none", "fixed", metric)
        a = final_by_seed(self.df, self.model, scenario, defense, "fixed", metric, 0.2, crowd)
        s = sorted(set(a.index) & set(ctrl.index))
        return a.loc[s] - ctrl.loc[s]


def ratio_of_means(num: pd.Series, den: pd.Series) -> float:
    s = sorted(set(num.index) & set(den.index))
    return float(num.loc[s].mean() / den.loc[s].mean()) if s else float("nan")


def recovery(dmg_def: pd.Series, dmg_none: pd.Series) -> float:
    return 1.0 - ratio_of_means(dmg_def, dmg_none)


def boot(series: dict[str, pd.Series], fn, seed: int = 0) -> tuple[float, float]:
    """Seed bootstrap: resample seeds with replacement, jointly across every series, so the
    pairing by seed survives; percentile 95% interval of ``fn(resampled series)``."""
    seeds = sorted(set.intersection(*(set(s.index) for s in series.values())))
    arr = {k: v.loc[seeds].to_numpy() for k, v in series.items()}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(N_BOOT):
        idx = rng.integers(0, len(seeds), len(seeds))
        vals.append(fn({k: v[idx] for k, v in arr.items()}))
    vals = np.array(vals)
    vals = vals[np.isfinite(vals)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def r21(p: Pair) -> tuple[list[dict], list[dict], dict]:
    """Holm family rows, cap-curve rows, verdict dict."""
    fam = []
    for ratio in RATIOS:
        und = p.a1("none", ratio)
        for d in DEFENSES[1:]:
            fam.append(cell(paired(p.a1(d, ratio), und),
                            f"R2.1 {p.dataset} {p.model} r={ratio} {d} minus none, fixed FPR",
                            dataset=p.dataset, model=p.model, family=f"R2.1 {p.dataset} {p.model}",
                            ratio=ratio, defense=d, metric="FPR_def - FPR_none (fixed)"))
    apply_holm(fam, "negative")

    curve = []
    g_none = p.g("none")
    for d in DEFENSES:
        for ratio in RATIOS:
            dm, dn = p.dfpr(d, ratio), p.dfpr("none", ratio)
            curve.append({"dataset": p.dataset, "model": p.model, "defense": d, "ratio": ratio,
                          "n": len(dm), "dFPR_fixed": float(dm.mean()),
                          "R": recovery(dm, dn) if d != "none" else float("nan"),
                          "batch_resampled_any": bool(p.df[(p.df.model == p.model) & (p.df.scenario == "a1")
                                                           & (p.df.def_label == d)
                                                           & np.isclose(p.df.target_poison_ratio, ratio)
                                                           ].batch_resampled.astype(bool).any())})
        gd = p.g(d)
        curve.append({"dataset": p.dataset, "model": p.model, "defense": d, "ratio": "S0 0.2",
                      "n": len(gd), "g_S0": float(gd.mean()),
                      "U": ratio_of_means(gd, g_none) if d != "none" else 1.0})

    # evaluability checks
    dmg = p.dfpr("none", 0.5).to_numpy()
    dmg_cell = cell(dmg, f"R2.1 {p.dataset} {p.model} undefended A1 r=0.5 dFPR fixed (evaluability)")
    gn_cell = cell(g_none.to_numpy(), f"R2.1 {p.dataset} {p.model} undefended S0 gain {p.u_metric} (evaluability)")
    rec_eval = bool(dmg_cell["mean"] > 0 and dmg_cell["p_t"] < 0.05)
    ret_eval = bool(gn_cell["mean"] > 0 and gn_cell["p_t"] < 0.05)

    R = {d: recovery(p.dfpr(d, 0.5), p.dfpr("none", 0.5)) for d in DEFENSES[1:]}
    U = {d: ratio_of_means(p.g(d), g_none) for d in DEFENSES[1:]}
    v: dict = {"dataset": p.dataset, "model": p.model, "R": R, "U": U,
               "undef_dFPR_r0.5": {k: dmg_cell[k] for k in ("n", "mean", "ci_lo", "ci_hi", "t", "p_t", "p_perm")},
               "g_none": {k: gn_cell[k] for k in ("n", "mean", "ci_lo", "ci_hi", "t", "p_t", "p_perm")},
               "recovery_evaluable": rec_eval, "retention_evaluable": ret_eval}

    sc = "sharecap_c0.05"
    v["boot_R_0.05"] = boot({"d": p.dfpr(sc, 0.5), "n": p.dfpr("none", 0.5)},
                            lambda a: 1 - a["d"].mean() / a["n"].mean())
    v["boot_U_0.05_minus_U_uniform"] = boot(
        {"s": p.g(sc), "u": p.g("uniform_w0.05"), "n": g_none},
        lambda a: (a["s"].mean() - a["u"].mean()) / a["n"].mean())

    if not rec_eval:
        v["verdict"] = "not evaluable"
        # descriptive fallback: recovery of recalibrated Delta TPR at ratio 0.5
        def dtpr(d):
            a = p.a1(d, 0.5, "recalibrated", "tpr")
            s = sorted(set(a.index) & set(p.ctrl_tpr_rec.index))
            return a.loc[s] - p.ctrl_tpr_rec.loc[s]
        v["dTPR_rec_none"] = float(dtpr("none").mean())
        v["R_tpr_recalibrated"] = {d: recovery(dtpr(d), dtpr("none")) for d in DEFENSES[1:]}
        v["dTPR_rec"] = {d: float(dtpr(d).mean()) for d in DEFENSES[1:]}
    else:
        c_rec = R[sc] >= 0.90
        if not ret_eval:
            v["verdict"] = "mixed (retention not evaluable)" if c_rec else "does not hold (retention not evaluable)"
        else:
            c_ret = U[sc] >= U["uniform_w0.05"]
            v["verdict"] = ("holds" if c_rec and c_ret else
                            "does not hold" if not c_rec and not c_ret else "mixed")
            v["cond_retention"] = bool(c_ret)
        v["cond_recovery"] = bool(c_rec)
    v["n_holm_clear"] = int(sum(r["clears_holm"] for r in fam))
    v["n_holm_opposite"] = int(sum(r["clears_opposite"] for r in fam))
    return fam + [dmg_cell | {"family": "evaluability"}, gn_cell | {"family": "evaluability"}], curve, v


def r23(p: Pair) -> dict:
    g_none = p.g("none")
    sp, sc = "srcpart_a0.5", "sharecap_c0.05"
    R_sp, R_sc = recovery(p.dfpr(sp, 0.5), p.dfpr("none", 0.5)), recovery(p.dfpr(sc, 0.5), p.dfpr("none", 0.5))
    U_sp, U_sc = ratio_of_means(p.g(sp), g_none), ratio_of_means(p.g(sc), g_none)
    sp_dom = R_sp >= R_sc and U_sp >= U_sc
    sc_dom = R_sc >= R_sp and U_sc >= U_sp
    return {"model": p.model, "R_srcpart": R_sp, "U_srcpart": U_sp, "R_sharecap0.05": R_sc,
            "U_sharecap0.05": U_sc,
            "dFPR_srcpart": {r: float(p.dfpr(sp, r).mean()) for r in RATIOS},
            "statement": ("srcpart dominates ShareCap 0.05" if sp_dom and not sc_dom else
                          "ShareCap 0.05 dominates srcpart" if sc_dom and not sp_dom else
                          "tie on both" if sp_dom and sc_dom else "neither dominates")}


def r24(p: Pair) -> tuple[list[dict], dict]:
    sc = "sharecap_c0.05"
    fam, extra = [], []
    for d in ("none", sc):
        g0 = p.g(d)
        for m in CROWD:
            gm = p.g(d, "s0crowd", m)
            fam.append(cell(paired(g0, gm), f"R2.4 {p.model} loss m={m} {d}", model=p.model,
                            family=f"R2.4 {p.model}", crowd_factor=m, defense=d, metric="loss l(m,d)"))
    apply_holm(fam, "positive")
    for m in CROWD:
        l_sc = p.g(sc) - p.g(sc, "s0crowd", m)
        l_none = p.g("none") - p.g("none", "s0crowd", m)
        extra.append(cell(paired(l_sc.dropna(), l_none.dropna()),
                          f"R2.4 {p.model} dilution-attributable m={m}", model=p.model,
                          family="R2.4 dilution (descriptive)", crowd_factor=m,
                          metric="l(m,c0.05) - l(m,none)"))
        for d in ("none", sc):
            a = final_by_seed(p.df, p.model, "s0crowd", d, "fixed", "fpr", 0.2, m)
            extra.append(cell(paired(a, p.ctrl_fpr), f"R2.4 {p.model} crowd m={m} {d} dFPR fixed",
                              model=p.model, family="R2.4 crowd FPR (descriptive)", crowd_factor=m,
                              defense=d, metric="dFPR fixed"))
    by = {(r["crowd_factor"], r["defense"]): r for r in fam}
    g_sc = float(p.g(sc).mean())
    l9 = by[(9, sc)]["mean"]
    any_clear = any(by[(m, sc)]["clears_holm"] for m in CROWD)
    holds = by[(9, sc)]["clears_holm"] and l9 >= 0.5 * g_sc
    v = {"model": p.model, "l9_c0.05": l9, "half_g_S0_c0.05": 0.5 * g_sc, "g_S0_c0.05": g_sc,
         "m9_clears_holm": by[(9, sc)]["clears_holm"], "any_m_clears_holm_c0.05": any_clear,
         "verdict": "holds" if holds else "does not hold" if not any_clear else "mixed"}
    return fam + extra, v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True, choices=sorted(TAU))
    ap.add_argument("--root", type=Path, default=Path("results/phaseR/r2"))
    args = ap.parse_args(argv)
    df = load_jobs(args.root / args.dataset / "jobs")
    df = df[np.isclose(df.val_min_nn_distance.fillna(0.0), TAU[args.dataset])
            & (df.cost_padding.fillna(1.0) == 1.0)].copy()
    df["def_label"] = defense_label(df)

    cells, curves, verdicts = [], [], {"R2.1": [], "R2.3": [], "R2.4": []}
    for model in MODELS[args.dataset]:
        p = Pair(df, args.dataset, model)
        fam, curve, v = r21(p)
        cells += fam
        curves += curve
        verdicts["R2.1"].append(v)
        if args.dataset == "cicids" and model in ("rf", "xgboost"):
            verdicts["R2.3"].append(r23(p))
            fam4, v4 = r24(p)
            cells += fam4
            verdicts["R2.4"].append(v4)

    out = args.root / args.dataset
    pd.DataFrame(cells).to_csv(out / "stats.csv", index=False)
    pd.DataFrame(curves).to_csv(out / "cap_curve.csv", index=False)
    (out / "verdicts.json").write_text(json.dumps(verdicts, indent=2, default=float))
    print(json.dumps(verdicts, indent=2, default=float))
    print(f"wrote {out}/stats.csv, cap_curve.csv, verdicts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
