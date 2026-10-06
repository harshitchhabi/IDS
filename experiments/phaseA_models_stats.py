"""Phase A item A statistics (DECISIONS.md s29.A): family A.1 (8-cell damage grid per model,
Holm) and family A.2 (4-arm mechanism isolation per model, Bonferroni), on the per-seed job CSVs
under results/phaseA/models/jobs/.

Reuses experiments/phase0_stats_recompute.py's paired-delta extraction, paired t-test and
paired permutation test unchanged -- s29 requires identical methodology, so nothing here
re-implements a test; only the family definitions and the corrections differ.

Holm/Bonferroni are applied to the t-test p (the project's primary test, s27) and, separately,
to the permutation p, and both verdicts are written out so the write-up can quote either.

    python -m experiments.phaseA_models_stats
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import paired_deltas, report_cell

JOBS = Path("results/phaseA/models/jobs")
OUT = Path("results/phaseA/models/stats.csv")
ALPHA = 0.05
SEEDS = list(range(1, 16))
MODELS = ("logreg", "mlp")


def holm(pvals: list[float], alpha: float = ALPHA) -> tuple[list[float], list[bool]]:
    """Holm-Bonferroni step-down. Returns each cell's own threshold alpha/(m-rank) and whether
    it survives; once one ranked cell fails, every later-ranked cell fails too."""
    m = len(pvals)
    order = np.argsort(pvals, kind="stable")
    thresholds = [0.0] * m
    survives = [False] * m
    still = True
    for rank, i in enumerate(order):
        thresholds[i] = alpha / (m - rank)
        still = still and pvals[i] <= thresholds[i]
        survives[i] = still
    return thresholds, survives


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    df = pd.concat([pd.read_csv(f) for f in glob.glob(str(JOBS / "*.csv"))], ignore_index=True)
    rows = []

    # Family A.1: per model, (ratio, jitter, threshold mode) = 8 cells. Fixed mode reads FPR,
    # recalibrated mode reads TPR (s29.A).
    for model in MODELS:
        fam = []
        for mode, metric in (("fixed", "fpr"), ("recalibrated", "tpr")):
            for ratio in (0.2, 0.5):
                for jitter in (0.0, 0.7):
                    d = paired_deltas(df, "a1", model, mode, jitter, ratio, SEEDS, metric)
                    r = report_cell(d, f"A.1 {model} {mode} d{metric} ratio={ratio} jitter={jitter}")
                    r.update(family=f"A.1/{model}", model=model, arm="a1", mode=mode,
                             metric=metric, ratio=ratio, jitter=jitter)
                    fam.append(r)
        for key in ("p_t", "p_perm"):
            thr, ok = holm([r[key] for r in fam])
            for r, t_, o in zip(fam, thr, ok):
                r[f"threshold_{key}"] = t_
                r[f"survives_{key}"] = o
        rows += fam

    # Family A.2: per model, recalibrated TPR, four arms at s28's cells, Bonferroni alpha/4.
    arms = [("a1", 0.7, 0.2), ("a1truth", 0.7, 0.2), ("s0j", 0.7, 0.2), ("junk", 0.0, 0.2)]
    for model in MODELS:
        for arm, jitter, ratio in arms:
            d = paired_deltas(df, arm, model, "recalibrated", jitter, ratio, SEEDS, "tpr")
            r = report_cell(d, f"A.2 {model} {arm}")
            r.update(family=f"A.2/{model}", model=model, arm=arm, mode="recalibrated",
                     metric="tpr", ratio=ratio, jitter=jitter)
            for key in ("p_t", "p_perm"):
                r[f"threshold_{key}"] = ALPHA / len(arms)
                r[f"survives_{key}"] = r[key] <= ALPHA / len(arms)
            r["ci_includes_0"] = r["ci_lo"] <= 0.0 <= r["ci_hi"]
            rows.append(r)

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
