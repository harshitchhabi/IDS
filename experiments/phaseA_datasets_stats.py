"""Phase A item B statistics (DECISIONS.md §29.B): families B.1 and B.2, per dataset.

The tests are ``experiments.phase0_stats_recompute``'s own paired t-test and paired
sign-flip permutation test (Monte Carlo, 10,000 resamples at n=15), imported, not
reimplemented. Only the row selection differs: that module hard-codes the paper's
job directory and tau = 0.1, while each Phase A dataset has its own measured tau.

* **B.1** (damage grid, per model): ratio {0.2, 0.5} x jitter {0, 0.7} x
  {Delta FPR at the fixed threshold, Delta TPR at the recalibrated threshold}.
  8 cells, Holm-Bonferroni within the (dataset, model) family, applied to each
  test's p-values separately.
* **B.2** (mechanism isolation, RF, recalibrated Delta TPR, ratio 0.2): a1 (jitter
  0.7, from the B.1 run), a1truth and s0j (jitter 0.7), junk (jitter 0). 4 cells,
  Bonferroni alpha/4 = 0.0125.

Every delta is final-round arm metric minus same-seed control metric.

    python -m experiments.phaseA_datasets_stats --dataset cicids-fixed --tau 0.1
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import report_cell

ALPHA = 0.05
SEEDS = list(range(1, 16))


def load_jobs(job_dir: Path) -> pd.DataFrame:
    frames = [pd.read_csv(f) for f in sorted(glob.glob(str(job_dir / "*.csv")))]
    if not frames:
        raise FileNotFoundError(f"no job CSVs under {job_dir}")
    return pd.concat(frames, ignore_index=True)


def _final(sub: pd.DataFrame) -> pd.DataFrame:
    last = sub.groupby("seed")["round"].transform("max")
    return sub[sub["round"] == last].set_index("seed")


def paired_deltas(df: pd.DataFrame, scenario: str, model: str, mode: str, jitter: float,
                  ratio: float, tau: float, metric: str) -> np.ndarray:
    """Final-round ``metric`` of the arm minus the same-seed control, seeds 1-15.
    Same filters as phase0_stats_recompute.paired_deltas, with tau as a parameter."""
    base = df[(df.model == model) & (df.threshold_mode == mode)
              & (df.defense.fillna("none") == "none")
              & np.isclose(df.val_min_nn_distance.fillna(0.0), tau)
              & df.seed.isin(SEEDS)]
    arm = base[(base.scenario == scenario) & np.isclose(base.target_poison_ratio, ratio)
               & np.isclose(base.jitter.fillna(0.0), jitter)
               & (base.cost_padding.fillna(1.0) == 1.0)]
    arm, ctrl = _final(arm), _final(base[base.scenario == "control"])
    seeds = sorted(set(arm.index) & set(ctrl.index))
    return np.array([arm.loc[s, metric] - ctrl.loc[s, metric] for s in seeds])


def holm(p: np.ndarray, alpha: float = ALPHA) -> tuple[np.ndarray, np.ndarray]:
    """Holm step-down: (per-cell threshold at its rank, rejected?). A cell is
    rejected only if every smaller p before it was also rejected."""
    order = np.argsort(p)
    m = len(p)
    thr = np.empty(m)
    rej = np.zeros(m, dtype=bool)
    still = True
    for rank, i in enumerate(order):
        thr[i] = alpha / (m - rank)
        still = still and p[i] <= thr[i]
        rej[i] = still
    return thr, rej


def b1(df: pd.DataFrame, dataset: str, model: str, tau: float) -> list[dict]:
    rows = []
    for ratio in (0.2, 0.5):
        for jitter in (0.0, 0.7):
            for mode, metric in (("fixed", "fpr"), ("recalibrated", "tpr")):
                d = paired_deltas(df, "a1", model, mode, jitter, ratio, tau, metric)
                r = report_cell(d, f"B.1 {dataset} {model} r={ratio} j={jitter} {mode} d{metric.upper()}")
                r.update(dataset=dataset, family=f"B.1 {model}", model=model, arm="a1", ratio=ratio,
                         jitter=jitter, threshold_mode=mode, metric=f"d{metric.upper()}")
                rows.append(r)
    pt = np.array([r["p_t"] for r in rows])
    pp = np.array([r["p_perm"] for r in rows])
    for key, p in (("t", pt), ("perm", pp)):
        thr, rej = holm(p)
        for r, th, rj in zip(rows, thr, rej, strict=True):
            r[f"holm_thr_{key}"], r[f"holm_reject_{key}"] = th, bool(rj)
    for r in rows:
        r["clears_both"] = r["holm_reject_t"] and r["holm_reject_perm"]
        # damage direction: FPR up, TPR down
        r["damage_direction"] = bool(r["mean"] > 0) if r["metric"] == "dFPR" else bool(r["mean"] < 0)
    return rows


def b2(df: pd.DataFrame, dataset: str, tau: float) -> list[dict]:
    rows = []
    for arm, jitter in (("a1", 0.7), ("a1truth", 0.7), ("s0j", 0.7), ("junk", 0.0)):
        d = paired_deltas(df, arm, "rf", "recalibrated", jitter, 0.2, tau, "tpr")
        r = report_cell(d, f"B.2 {dataset} {arm}")
        thr = ALPHA / 4
        r.update(dataset=dataset, family="B.2", model="rf", arm=arm, ratio=0.2, jitter=jitter,
                 threshold_mode="recalibrated", metric="dTPR", bonf_thr=thr,
                 clears_both=bool(r["p_t"] <= thr and r["p_perm"] <= thr),
                 ci_includes_0=bool(r["ci_lo"] <= 0 <= r["ci_hi"]))
        rows.append(r)
    return rows


def verdicts(rows: list[dict]) -> dict:
    """§29.A bar, applied per (dataset, model) for B.1 and per dataset for B.2:
    (a) both jitter-0 fixed-threshold dFPR cells clear Holm (by both tests, in the
        damage direction); (b) the a1 arm clears alpha/4 by both tests and every
        null arm's 95% CI includes 0."""
    df = pd.DataFrame(rows)
    out = {}
    m2 = df[df.family == "B.2"]
    b_met = bool(m2[m2.arm == "a1"].clears_both.iloc[0]
                 and m2[m2.arm != "a1"].ci_includes_0.all()) if len(m2) else False
    for model in sorted(df[df.family.str.startswith("B.1")].model.unique()):
        cells = df[(df.family == f"B.1 {model}") & (df.jitter == 0.0) & (df.metric == "dFPR")]
        per_ratio = {float(r.ratio): bool(r.clears_both and r.damage_direction)
                     for r in cells.itertuples()}
        a_met = all(per_ratio.values())
        out[model] = {"a_per_ratio": per_ratio, "a_met": a_met}
    out["b_met"] = b_met
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--tau", type=float, required=True)
    ap.add_argument("--root", type=Path, default=Path("results/phaseA/datasets"))
    args = ap.parse_args(argv)
    df = load_jobs(args.root / args.dataset / "jobs")
    rows = b1(df, args.dataset, "rf", args.tau) + b1(df, args.dataset, "xgboost", args.tau)
    rows += b2(df, args.dataset, args.tau)
    out = args.root / args.dataset / "stats.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(verdicts(rows))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
