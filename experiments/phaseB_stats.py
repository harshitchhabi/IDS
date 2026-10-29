"""B.2 statistics (DECISIONS.md §32.2). The real-traffic A1 damage, its null arms,
and ShareCap recovery, on the lab dataset.

Reuses the paper's own paired t-test + sign-flip permutation test + CI
(``phase0_stats_recompute.report_cell``) and the arm-minus-control delta
(``phaseA_datasets_stats.paired_deltas``). Lab A1 uses the replay adversary, so
jitter is 0 throughout.
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import report_cell
from experiments.phaseA_datasets_stats import _final, paired_deltas

ALPHA = 0.05
SEEDS = list(range(1, 16))
TAU = 0.1


def load_jobs(*dirs: Path) -> pd.DataFrame:
    frames = []
    for d in dirs:
        frames += [pd.read_csv(f) for f in sorted(glob.glob(str(d / "*.csv")))]
    if not frames:
        raise FileNotFoundError(f"no job CSVs under {dirs}")
    return pd.concat(frames, ignore_index=True)


def family(df: pd.DataFrame) -> list[dict]:
    """Full B.2 family: a1/a1truth/junk vs control, RF+XGB, fixed dFPR & recal dTPR,
    ratios 0.2/0.5. Bonferroni alpha/4 per (model, threshold mode)."""
    rows = []
    for model in ("rf", "xgboost"):
        for mode, metric in (("fixed", "fpr"), ("recalibrated", "tpr")):
            for ratio in (0.2, 0.5):
                for arm in ("a1", "a1truth", "junk"):
                    d = paired_deltas(df, arm, model, mode, 0.0, ratio, TAU, metric)
                    r = report_cell(d, f"B.2 {model} {mode} r={ratio} {arm} d{metric.upper()}")
                    thr = ALPHA / 4
                    r.update(model=model, threshold_mode=mode, metric=f"d{metric.upper()}",
                             ratio=ratio, arm=arm, bonf_thr=thr,
                             clears_both=bool(r["p_t"] <= thr and r["p_perm"] <= thr),
                             ci_includes_0=bool(r["ci_lo"] <= 0 <= r["ci_hi"]))
                    rows.append(r)
    return rows


def sharecap_recovery(df: pd.DataFrame, sc: pd.DataFrame) -> list[dict]:
    """R = 1 - mean dFPR(defended) / mean dFPR(undefended), A1 fixed threshold,
    final round, per model and ratio (s24's definition). Descriptive."""
    rows = []
    for model in ("rf", "xgboost"):
        for ratio in (0.2, 0.5):
            und = paired_deltas(df, "a1", model, "fixed", 0.0, ratio, TAU, "fpr")
            # defended: ShareCap a1 minus the SAME control (defense column = sharecap)
            base = sc[(sc.model == model) & (sc.threshold_mode == "fixed")
                      & sc.seed.isin(SEEDS) & (sc.scenario == "a1")
                      & np.isclose(sc.target_poison_ratio, ratio)]
            ctrl = df[(df.model == model) & (df.threshold_mode == "fixed")
                      & (df.defense.fillna("none") == "none") & (df.scenario == "control")
                      & df.seed.isin(SEEDS)]
            a, c = _final(base), _final(ctrl)
            seeds = sorted(set(a.index) & set(c.index))
            defd = np.array([a.loc[s, "fpr"] - c.loc[s, "fpr"] for s in seeds])
            R = float(1 - defd.mean() / und.mean()) if len(und) and und.mean() != 0 else float("nan")
            rows.append({"model": model, "ratio": ratio, "mean_dfpr_undef": float(und.mean()),
                         "mean_dfpr_sharecap": float(defd.mean()) if len(defd) else float("nan"),
                         "recovery_R": R})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loop-dir", type=Path, default=Path("results/phaseB/loop/lab/jobs"))
    ap.add_argument("--sharecap-dir", type=Path, default=Path("results/phaseB/loop/lab_sharecap/jobs"))
    ap.add_argument("--out", type=Path, default=Path("results/phaseB/b2_stats.csv"))
    args = ap.parse_args(argv)

    df = load_jobs(args.loop_dir)
    fam = family(df)
    out = pd.DataFrame(fam)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    # primary bar: RF recalibrated dTPR ratio 0.2
    prim = out[(out.model == "rf") & (out.threshold_mode == "recalibrated")
               & (out.ratio == 0.2)]
    a1 = prim[prim.arm == "a1"].iloc[0] if len(prim[prim.arm == "a1"]) else None
    nulls_ok = bool(prim[prim.arm != "a1"].ci_includes_0.all()) if len(prim) else False
    if a1 is not None:
        verdict = ("replicates" if (a1.clears_both and nulls_ok)
                   else "does not replicate" if not a1.clears_both
                   else "mixed")
        print(f"PRIMARY B.2 (RF recal dTPR r=0.2): a1 mean={a1['mean']:.4f} "
              f"p_t={a1['p_t']:.4g} p_perm={a1['p_perm']:.4g} clears(a/4)={a1.clears_both}; "
              f"nulls CI-include-0={nulls_ok} -> {verdict}")
    print(out[["model", "threshold_mode", "ratio", "arm", "mean", "ci_lo", "ci_hi",
               "p_t", "p_perm", "clears_both", "ci_includes_0"]].to_string(index=False))

    if args.sharecap_dir.exists():
        sc = load_jobs(args.sharecap_dir)
        rec = pd.DataFrame(sharecap_recovery(df, sc))
        rec.to_csv(args.out.with_name("b2_sharecap_recovery.csv"), index=False)
        print("\nShareCap c=0.05 recovery (A1 fixed dFPR):")
        print(rec.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
