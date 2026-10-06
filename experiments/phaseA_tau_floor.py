"""Derive ``--val-nn-tau`` for a Phase A dataset with DECISIONS.md s19's rule.

s19 rule, fixed before measuring (docs/phaseA/datasets-results.md §1): the
smallest tau at which the control arm's fixed-threshold FPR, averaged over
rounds 11-20 and 5 seeds, is <= 1.5x the 0.01 target (<= 0.015) for both RF
and XGBoost. Also reports the fraction of benign validation rows the tau filter
drops, as s19's table did. Writes ``<dir>/control_floor_by_tau.csv``.

    python -m experiments.phaseA_tau_floor results/phaseA/datasets/cicids-fixed/tau_sweep
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import pandas as pd

TARGET = 0.01
BAR = 1.5 * TARGET


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", type=Path)
    args = ap.parse_args(argv)
    df = pd.concat([pd.read_csv(f) for f in glob.glob(str(args.dir / "jobs" / "*.csv"))],
                   ignore_index=True)
    df = df[(df.scenario == "control") & df["round"].between(11, 20)]
    df["tau"] = df.val_min_nn_distance.fillna(0.0)
    fixed = df[df.threshold_mode == "fixed"]
    g = fixed.groupby(["tau", "model"])
    per_seed = fixed.groupby(["tau", "model", "seed"]).fpr.mean()
    out = pd.DataFrame({
        "fpr_mean": g.fpr.mean(),
        "fpr_sd_across_seeds": per_seed.groupby(["tau", "model"]).std(),
        "tpr_mean": g.tpr.mean(),
        "auroc_mean": g.auroc.mean() if "auroc" in fixed else float("nan"),
        "n_seeds": g.seed.nunique(),
    }).reset_index()
    drop_col = next((c for c in ("val_benign_dropped_frac", "val_dropped_frac") if c in fixed), None)
    if drop_col:
        out = out.merge(fixed.groupby(["tau", "model"])[drop_col].mean().reset_index(),
                        on=["tau", "model"], how="left")
    wide = out.pivot(index="tau", columns="model", values="fpr_mean")
    ok = (wide <= BAR).all(axis=1)
    chosen = float(ok[ok].index.min()) if ok.any() else float("nan")
    out["meets_bar_both_models"] = out.tau.map(ok)
    out.to_csv(args.dir / "control_floor_by_tau.csv", index=False)
    print(out.to_string(index=False))
    print(f"\nchosen tau (smallest with fixed FPR <= {BAR} for both models): {chosen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
