"""Phase R follow-up R3.4 statistics (docs/phaseR/r3-followup-prereg.md), per NetFlow v2 dataset.

* **Stage a, onset:** A1 (no defense, jitter 0) fixed-threshold final-round dFPR minus the
  same-seed control, at ratios {0.01, 0.02, 0.05, 0.10}; Holm within the 4 per (dataset, model),
  positive direction, both tests. Onset = smallest ratio that clears.
* **Stage b:** A1 at ratio 0.5 under ShareCap c in {0.005, 0.01, 0.02, 0.05}. R_c as in R3.3
  (``phaseR_r3_stats.recovery``), Holm within the 4 caps on defended minus undefended dFPR
  ("defense lowers FPR"). S0 retention U_c as in R2.1: g = S0 TPR minus control TPR, fixed
  threshold, final round, all attack rows; U = mean g_def / mean g_none, undefined unless g_none
  is positive with paired-t p < 0.05.
* **Bar:** at c* = the largest tested c strictly below the onset (0.05 when the onset is
  "> 0.10"), "the onset rule holds" iff R_{c*} >= 0.90.

The cell machinery (paired t, permutation, Holm, control pairing) is imported from
``phaseA_datasets_stats`` / ``phase0_stats_recompute`` / ``phaseR_r3_stats``, not copied.

    python -m experiments.phaseR_r3_4_stats --dataset nf-unsw-nb15-v2 --tau 0.2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import report_cell
from experiments.phaseA_datasets_stats import SEEDS, _final, holm, load_jobs, paired_deltas
from experiments.phaseR_r3_stats import BOOT, BOOT_SEED, R_BAR, boot_ci, defended_deltas, recovery

ONSET_RATIOS = (0.01, 0.02, 0.05, 0.1)
CAPS = (0.005, 0.01, 0.02, 0.05)
UNIFORM_W = 0.05


def c_star(onset: float | None) -> float | None:
    """Largest tested cap strictly below the onset; ``None`` onset means "> 0.10"."""
    below = [c for c in CAPS if onset is None or c < onset - 1e-12]
    return max(below) if below else None


def s0_gains(df: pd.DataFrame, model: str, tau: float, defense: str) -> np.ndarray:
    """Per-seed S0 (ratio 0.2) fixed-threshold final-round TPR minus same-seed control TPR."""
    base = df[(df.model == model) & (df.threshold_mode == "fixed")
              & np.isclose(df.val_min_nn_distance.fillna(0.0), tau) & df.seed.isin(SEEDS)]
    ctrl = _final(base[(base.scenario == "control") & (base.defense.fillna("none") == "none")])
    s0 = base[(base.scenario == "s0") & np.isclose(base.target_poison_ratio, 0.2)]
    arm = _final(s0[s0.defense.fillna("none") == defense])
    seeds = sorted(set(ctrl.index) & set(arm.index))
    if len(seeds) != len(SEEDS):
        raise ValueError(f"S0 {model} {defense}: {len(seeds)} paired seeds, expected {len(SEEDS)}")
    return np.array([arm.loc[s, "tpr"] - ctrl.loc[s, "tpr"] for s in seeds])


def u_diff_boot(g_a: np.ndarray, g_b: np.ndarray, g_none: np.ndarray) -> tuple[float, float]:
    """Seed-bootstrap 95% CI of U_a - U_b (seeds resampled jointly)."""
    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(0, len(g_none), size=(BOOT, len(g_none)))
    den = g_none[idx].mean(axis=1)
    ok = den != 0
    d = (g_a[idx].mean(axis=1) - g_b[idx].mean(axis=1))[ok] / den[ok]
    return float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))


def r31_damage_clears(r3_stats: pd.DataFrame, model: str) -> bool:
    """R3.1's undefended ratio-0.5 jitter-0 fixed dFPR cell, as R3 read it (both tests, positive)."""
    c = r3_stats[(r3_stats.family == f"R3.1 {model}") & np.isclose(r3_stats.ratio, 0.5)
                 & (r3_stats.jitter == 0.0) & (r3_stats.metric == "dFPR")].iloc[0]
    return bool(c.clears_both and c.damage_direction)


def analyse(df: pd.DataFrame, dataset: str, model: str, tau: float,
            damage_clears: bool) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    # stage a
    onset_rows = []
    for ratio in ONSET_RATIOS:
        d = paired_deltas(df, "a1", model, "fixed", 0.0, ratio, tau, "fpr")
        if len(d) != len(SEEDS):
            raise ValueError(f"onset {model} r={ratio}: {len(d)} seeds")
        r = report_cell(d, f"R3.4a {dataset} {model} r={ratio} dFPR")
        r.update(dataset=dataset, family=f"R3.4a {model}", model=model, arm="a1", ratio=ratio,
                 cap=np.nan, metric="dFPR")
        onset_rows.append(r)
    for key in ("t", "perm"):
        thr, rej = holm(np.array([r[f"p_{key}"] for r in onset_rows]))
        for r, th, rj in zip(onset_rows, thr, rej, strict=True):
            r[f"holm_thr_{key}"], r[f"holm_reject_{key}"] = th, bool(rj)
    for r in onset_rows:
        r["clears"] = bool(r["holm_reject_t"] and r["holm_reject_perm"] and r["mean"] > 0)
    rows += onset_rows
    cleared = [r["ratio"] for r in onset_rows if r["clears"]]
    onset = min(cleared) if cleared else None


    # stage b recovery
    rec_rows = []
    for c in CAPS:
        d_def, d_none = defended_deltas(df, model, 0.5, tau, cap=c)
        r = report_cell(d_def - d_none, f"R3.4b {dataset} {model} c={c} def-none dFPR")
        lo, hi = boot_ci(d_def, d_none)
        r.update(dataset=dataset, family=f"R3.4b {model}", model=model, arm="a1 sharecap", ratio=0.5,
                 cap=c, metric="dFPR(def-none)", R=recovery(d_def, d_none), R_boot_lo=lo, R_boot_hi=hi)
        rec_rows.append(r)
    for key in ("t", "perm"):
        thr, rej = holm(np.array([r[f"p_{key}"] for r in rec_rows]))
        for r, th, rj in zip(rec_rows, thr, rej, strict=True):
            r[f"holm_thr_{key}"], r[f"holm_reject_{key}"] = th, bool(rj)
    for r in rec_rows:
        r["clears"] = bool(r["holm_reject_t"] and r["holm_reject_perm"] and r["mean"] < 0)

    # retention
    g_none = s0_gains(df, model, tau, "none")
    gn = report_cell(g_none, f"R3.4b {dataset} {model} S0 gain, no defense")
    gn.update(dataset=dataset, family=f"R3.4b-S0 {model}", model=model, arm="s0 none", ratio=0.2,
              cap=np.nan, metric="gTPR")
    u_defined = bool(gn["mean"] > 0 and gn["p_t"] < 0.05)
    g_uni = s0_gains(df, model, tau, f"uniform_w{UNIFORM_W:g}")
    u_uni = float(g_uni.mean() / g_none.mean()) if u_defined else np.nan
    gains = {c: s0_gains(df, model, tau, f"sharecap_c{c:g}") for c in CAPS}
    for r in rec_rows:
        c = r["cap"]
        r["U"] = float(gains[c].mean() / g_none.mean()) if u_defined else np.nan
        r["U_uniform"] = u_uni
        if u_defined:
            r["U_minus_uniform_lo"], r["U_minus_uniform_hi"] = u_diff_boot(gains[c], g_uni, g_none)
    rows += rec_rows + [gn]

    cs = c_star(onset)
    if not damage_clears:
        verdict = "not evaluable"
    elif cs is None:
        verdict = "no tested c is below the onset"
    else:
        rc = next(r for r in rec_rows if np.isclose(r["cap"], cs))
        verdict = "holds" if rc["R"] >= R_BAR else "does not hold"
    at = next((r for r in rec_rows if cs is not None and np.isclose(r["cap"], cs)), None)
    summary = {"onset": onset if onset is not None else "> 0.10", "c_star": cs, "verdict": verdict,
               "R_c_star": None if at is None else at["R"],
               "U_c_star": None if at is None or not u_defined else at["U"],
               "U_uniform_0.05": None if not u_defined else u_uni,
               "U_defined": u_defined, "g_none_mean": float(g_none.mean()), "g_none_p_t": float(gn["p_t"])}
    return rows, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--tau", type=float, required=True)
    ap.add_argument("--root", type=Path, default=Path("results/phaseR/r3"))
    args = ap.parse_args(argv)
    out_dir = args.root / args.dataset
    df = load_jobs(out_dir / "jobs")
    r3 = pd.read_csv(out_dir / "stats.csv")
    rows, verdicts = [], {}
    for model in ("rf", "xgboost"):
        r, v = analyse(df, args.dataset, model, args.tau, r31_damage_clears(r3, model))
        rows += r
        verdicts[model] = v
    pd.DataFrame(rows).to_csv(out_dir / "stats_r3_4.csv", index=False)
    (out_dir / "verdicts_r3_4.json").write_text(json.dumps(verdicts, indent=2) + "\n")
    print(json.dumps(verdicts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
