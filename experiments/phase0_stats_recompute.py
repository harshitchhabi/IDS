"""Paired permutation test alongside every paired t-test used in this paper, plus 95% CIs for
the mechanism-isolation family (DECISIONS.md s27, external review items 7-9).

Exact sign-flip test (enumerate all 2^n sign patterns) for n<=12; Monte Carlo (10,000 resamples)
above that. Reads only already-committed per-seed job CSVs under
results/phase0/loop/cicids_recal/jobs/ -- no new experiments, consistent with the s26.10 freeze.

    python -m experiments.phase0_stats_recompute
"""

from __future__ import annotations

import argparse
import glob
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

JOBS = Path("results/phase0/loop/cicids_recal/jobs")
OUT = Path("results/phase0/loop/s27_permutation_tests.csv")


def load_all() -> pd.DataFrame:
    frames = [pd.read_csv(f) for f in glob.glob(str(JOBS / "*.csv"))]
    return pd.concat(frames, ignore_index=True)


def paired_deltas(df: pd.DataFrame, scenario: str, model: str, mode: str, jitter: float | None,
                  ratio: float | None, seeds: list[int], metric: str) -> np.ndarray:
    """Final-round arm metric minus same-seed control metric, for the given seeds."""
    sub = df[(df.scenario == scenario) & (df.model == model) & (df.threshold_mode == mode)]
    if jitter is not None:
        sub = sub[np.isclose(sub.jitter.fillna(0.0), jitter)]
    if ratio is not None:
        sub = sub[np.isclose(sub.target_poison_ratio, ratio)]
    sub = sub[sub.defense.fillna("none") == "none"]
    sub = sub[sub.cost_padding.fillna(1.0) == 1.0]
    sub = sub[sub.val_min_nn_distance.fillna(0.0) == 0.1]
    sub = sub[sub.seed.isin(seeds)]
    last = sub.groupby("seed")["round"].transform("max")
    sub = sub[sub["round"] == last]

    ctrl = df[(df.scenario == "control") & (df.model == model) & (df.threshold_mode == mode)]
    ctrl = ctrl[ctrl.defense.fillna("none") == "none"]
    ctrl = ctrl[ctrl.val_min_nn_distance.fillna(0.0) == 0.1]
    ctrl = ctrl[ctrl.seed.isin(seeds)]
    last_c = ctrl.groupby("seed")["round"].transform("max")
    ctrl = ctrl[ctrl["round"] == last_c].set_index("seed")

    d = []
    for s in sorted(sub.seed.unique()):
        row = sub[sub.seed == s]
        if len(row) == 0 or s not in ctrl.index:
            continue
        d.append(row[metric].iloc[0] - ctrl.loc[s, metric])
    return np.array(d)


def paired_permutation_p(d: np.ndarray, n_mc: int = 10_000, seed: int = 0) -> tuple[float, int]:
    """Exact sign-flip test for n<=12 (2^n enumerations); Monte Carlo (n_mc draws) above that.
    Two-sided: fraction of |mean of sign-flipped d| >= |observed mean|. At n=5 the minimum
    achievable p is 2/32=0.0625 (the two unanimous-sign patterns) -- a floor, not a bug;
    see DECISIONS.md s27.1. When the Monte Carlo count is 0, the true p is unknown below the
    resolution 1/n_mc, not exactly 0 -- callers should report it as "< 1/n_mc", never "0"."""
    n = len(d)
    obs = abs(d.mean())
    if n <= 12:
        count = total = 0
        for signs in itertools.product([1, -1], repeat=n):
            if abs((np.array(signs) * d).mean()) >= obs - 1e-12:
                count += 1
            total += 1
        return count / total, total
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n_mc):
        signs = rng.choice([1, -1], size=n)
        if abs((signs * d).mean()) >= obs - 1e-12:
            count += 1
    return count / n_mc, n_mc


def report_cell(d: np.ndarray, label: str) -> dict:
    n = len(d)
    mean = d.mean()
    sd = d.std(ddof=1) if n > 1 else float("nan")
    ci_half = stats.t.ppf(0.975, n - 1) * (sd / np.sqrt(n))
    t, p_t = stats.ttest_1samp(d, 0.0)
    p_perm, n_perm = paired_permutation_p(d)
    # A Monte Carlo count of 0 means p < 1/n_perm, not p == 0 -- report it as a bound, not a value.
    p_perm_display = f"<{1 / n_perm:.4g}" if p_perm == 0 and n > 12 else f"{p_perm:.6g}"
    p_perm_is_bound = bool(p_perm == 0 and n > 12)
    print(f"{label}: n={n} mean={mean:.4f} sd={sd:.4f} ci95=[{mean - ci_half:.4f},{mean + ci_half:.4f}] "
          f"t={t:.3f} p_t={p_t:.6g} p_perm={p_perm_display} (perm_total={n_perm})")
    return {"label": label, "n": n, "mean": mean, "sd": sd, "ci_lo": mean - ci_half,
            "ci_hi": mean + ci_half, "t": t, "p_t": p_t, "p_perm": p_perm, "n_perm": n_perm,
            "p_perm_is_bound": p_perm_is_bound, "p_perm_display": p_perm_display}


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    df = load_all()
    rows = []

    jitters = (0.0, 0.01, 0.03, 0.1, 0.3, 0.7, 1.5)
    ratios = (0.05, 0.1, 0.2, 0.5)
    seeds5 = [1, 2, 3, 4, 5]
    for model in ("rf", "xgboost"):
        for ratio in ratios:
            for jitter in jitters:
                d = paired_deltas(df, "a1", model, "recalibrated", jitter, ratio, seeds5, "tpr")
                if len(d) == 0:
                    continue
                r = report_cell(d, f"grid36 model={model} ratio={ratio} jitter={jitter}")
                r.update(family="grid36", model=model, ratio=ratio, jitter=jitter)
                rows.append(r)

    seeds15 = list(range(1, 16))
    seeds10new = list(range(6, 16))
    for fam_name, seeds in (("grid6_15seed", seeds15), ("grid6_10new", seeds10new)):
        for jitter in (0.3, 0.7, 1.5):
            for ratio in (0.2, 0.5):
                d = paired_deltas(df, "a1", "rf", "recalibrated", jitter, ratio, seeds, "tpr")
                r = report_cell(d, f"{fam_name} ratio={ratio} jitter={jitter}")
                r.update(family=fam_name, model="rf", ratio=ratio, jitter=jitter)
                rows.append(r)

    arms = [
        ("a1", 0.7, 0.2), ("a1truth", 0.7, 0.2), ("s0j", 0.7, 0.2), ("junk", 0.0, 0.2),
    ]
    for arm, jitter, ratio in arms:
        d = paired_deltas(df, arm, "rf", "recalibrated", jitter, ratio, seeds5, "tpr")
        r = report_cell(d, f"mechanism {arm}")
        r.update(family="mechanism", arm=arm)
        rows.append(r)

    # DECISIONS.md s28: mechanism isolation at 15 seeds (a1 reused from the s26.6 follow-up;
    # a1truth/s0j/junk need seeds 6-15 new). Only run once results/phase0/loop/cicids_recal/jobs
    # has those seeds for all three null arms -- otherwise paired_deltas returns an empty array
    # and report_cell would divide by zero, so skip gracefully if the data isn't there yet.
    for arm, jitter, ratio in arms:
        d15 = paired_deltas(df, arm, "rf", "recalibrated", jitter, ratio, seeds15, "tpr")
        if len(d15) < 15:
            print(f"mechanism15 {arm}: only {len(d15)}/15 seeds present, skipping")
            continue
        r = report_cell(d15, f"mechanism15 {arm}")
        r.update(family="mechanism15", arm=arm)
        rows.append(r)

    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
