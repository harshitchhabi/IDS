"""B.1 achievable fidelity (DECISIONS.md §32.1). Descriptive, no hypothesis test.

For each mimic strategy, in the loop's own normalised space, the median NN RMS
distance and twin fraction (delta=0.0015) of the honeypot-bound mimic flows to the
defender's benign reference, the benign-to-benign floor computed against a
reference of the same size, and the ratio of the two.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.adversary.mimicry import FidelityMeter
from dloop.features import schema
from dloop.loop.data import LoopData

TWIN_DELTA = 0.0015
STRATEGIES = {"profile": "mimic_profile", "oracle": "mimic_oracle", "replay": "mimic_replay"}


def _feats(df: pd.DataFrame) -> np.ndarray:
    """Canonical feature block, cleaned like the pipeline (coerce numeric, drop
    rows with +-Inf/NaN or any negative feature) so the NN query has finite input."""
    x = df[list(schema.CANONICAL_FEATURES)].apply(pd.to_numeric, errors="coerce")
    x = x.replace([np.inf, -np.inf], np.nan)
    x = x[x.notna().all(axis=1) & (x >= 0).all(axis=1)]
    return x.to_numpy(dtype="float64")


def measure(labelled: pd.DataFrame, ld: LoopData) -> pd.DataFrame:
    nz = ld.normalizer
    ref_all = ld.eval_benign_full_x                      # defender benign reference
    rng = np.random.default_rng(0)
    # split the reference in two: one half is the reference R, the other the
    # benign query for the floor — same |R| for both measurements.
    perm = rng.permutation(len(ref_all))
    half = len(ref_all) // 2
    R = ref_all[np.sort(perm[:half])]
    Bq = ref_all[np.sort(perm[half:2 * half])]
    fm = FidelityMeter(nz.transform(R), nz)
    floor = fm.distances(Bq, max_rows=len(Bq), rng=rng)
    floor_med = float(np.median(floor))

    rows = []
    poison = labelled[(labelled["true_intent"] == "poison")]
    for strat, kind in STRATEGIES.items():
        m = poison[poison["true_kind"] == kind]
        if m.empty:
            rows.append({"strategy": strat, "n_mimic": 0, "median_nn": float("nan"),
                         "twin_fraction": float("nan"), "benign_floor": floor_med,
                         "ratio_to_floor": float("nan")})
            continue
        fx = _feats(m)
        d = fm.distances(fx, max_rows=len(fx), rng=rng)
        rows.append({"strategy": strat, "n_mimic": int(len(fx)),
                     "median_nn": float(np.median(d)),
                     "twin_fraction": float((d <= TWIN_DELTA).mean()),
                     "benign_floor": floor_med,
                     "ratio_to_floor": float(np.median(d) / floor_med) if floor_med else float("nan")})
    out = pd.DataFrame(rows)
    out.attrs["floor_n_ref"] = int(len(R))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labelled", type=Path, default=Path("lab/data/lab_labelled.csv"))
    ap.add_argument("--npz", type=Path, default=Path("data/loop/lab.npz"))
    ap.add_argument("--out", type=Path, default=Path("results/phaseB/b1_fidelity.csv"))
    args = ap.parse_args(argv)
    labelled = pd.read_csv(args.labelled, low_memory=False)
    ld = LoopData.load(args.npz)
    res = measure(labelled, ld)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.out, index=False)
    print(f"benign floor computed against |R|={res.attrs['floor_n_ref']} reference rows")
    print(res.to_string(index=False))
    # the primary B.2 strategy is the one with the smallest ratio (most realistic)
    valid = res.dropna(subset=["ratio_to_floor"])
    if not valid.empty:
        best = valid.loc[valid["ratio_to_floor"].idxmin(), "strategy"]
        print(f"\nprimary strategy for B.2 (smallest ratio-to-floor): {best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
