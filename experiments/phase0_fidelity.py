"""Realized mimicry fidelity per jitter setting: the full NN-distance
distribution, and the disjointness assertion, on the rows actually injected.

Jitter is a knob; the x-axis of the A1 damage curve is the *realized* nearest-
neighbour distance (per-feature RMS, normalized feature space, the guard-(c)
metric) from the poison rows to the full ``trusted_eval`` benign set. For every
jitter this records percentiles of that distribution — not only the median — and
asserts, by row content, that no injected poison row is identical to a
``trusted_eval`` benign row (the pre-jitter source rows are asserted in
``phase0_loop.py``; this checks the post-jitter rows, which is what the model
actually sees).

The lower end of the sweep is the dataset's own duplicate scale: jitter can only
move poison *away* from raw benign, so realized distance cannot go below the raw
pool->eval distance (on CICIDS a median of ~0.011, a 5th percentile of ~0.001).

Writes ``results/phase0/loop/<dataset>/mimicry_fidelity_distribution.csv``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.adversary.base import features_of
from dloop.adversary.mimicry import FidelityMeter, MimicryAdversary, assert_disjoint_from_eval
from dloop.logging_config import configure
from dloop.loop.data import LoopData

# roughly log-spaced in realized distance; 0 is raw benign (the leftmost point)
JITTERS = (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.07, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5)
PCTS = (0, 1, 5, 25, 50, 75, 95, 99, 100)
N_ROWS = 5000
SEED = 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=["cicids", "synthetic"], required=True)
    ap.add_argument("--root", type=Path, default=Path("results/phase0/loop"))
    args = ap.parse_args(argv)
    configure("WARNING")

    data = LoopData.load(Path("data/loop") / f"{args.dataset}.npz")
    norm = data.normalizer
    meter = FidelityMeter(norm.transform(data.eval_benign_full_x), norm)
    rows = []
    for jit in JITTERS:
        adv = MimicryAdversary(data.pool_benign_x, norm, jit, SEED)
        batch, cost = adv.generate_batch(1, N_ROWS)
        x = features_of(batch)
        n_checked = assert_disjoint_from_eval(x, data.eval_benign_full_x)   # post-jitter rows
        d = meter.distances(x, max_rows=N_ROWS, rng=np.random.default_rng(SEED))
        row = {"dataset": args.dataset, "jitter": jit, "n_poison_rows": len(x),
               "disjoint_from_eval_benign_rows_checked": n_checked,
               "nn_mean": float(d.mean())}
        row.update({f"nn_p{p}": float(np.percentile(d, p)) for p in PCTS})
        rows.append(row)
    out = args.root / args.dataset / "mimicry_fidelity_distribution.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    print(df[["jitter", "nn_p0", "nn_p5", "nn_p25", "nn_p50", "nn_p75", "nn_p95", "nn_p100"]]
          .round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
