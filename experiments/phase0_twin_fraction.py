"""Twin fraction by jitter: share of A1 poison rows within a small RMS distance of some
trusted_eval benign row, for each jitter setting used in the damage-vs-distance sweep.

DECISIONS.md s26.2 showed the median realized distance cannot resolve where the FPR cliff sits
(it barely moves across the exact jitter range where the damage collapses). This computes the
tail statistic that can: `delta = 0.0015`, the midpoint of jitter 0's p5 (0.00093) and jitter
0.002's p5 (0.00206) -- the boundary of the regime change s26.2 measured. A poison row is a
"twin" of production benign traffic if its nearest trusted_eval benign neighbour is closer than
that.

Computed once (each jitter is a 344k x 230k brute-force nearest-neighbour query, ~O(minutes)
per jitter) and cached to a committed CSV so routine figure regeneration
(`python scripts/run.py figures`) does not re-run it. Re-run this script by hand if the delta
or jitter grid changes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.adversary.base import features_of
from dloop.adversary.mimicry import FidelityMeter, MimicryAdversary, assert_disjoint_from_eval
from dloop.loop.data import LoopData
from dloop.logging_config import configure, get_logger

log = get_logger("experiments.phase0_twin_fraction")

JITTERS = (0.0, 0.002, 0.005, 0.01, 0.03, 0.1, 0.3, 0.7, 1.5)
TWIN_DELTA = 0.0015  # midpoint of jitter-0 p5 (0.00093) and jitter-0.002 p5 (0.00206), s26.2
SEED = 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="cicids")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    configure()

    data_path = Path("data/loop") / f"{args.dataset}.npz"
    d = LoopData.load(data_path)
    out = args.out or Path("results/phase0") / args.dataset / "twin_fraction_by_jitter.csv"

    # Exact-duplicate count: the pipeline already asserts zero content-identical rows between
    # honeypot_pool and trusted_eval (float32, row-content hash) at partition build time; this
    # re-checks it on the loop's own pool/eval arrays and reports the count for the paper.
    n_checked = assert_disjoint_from_eval(d.pool_benign_x, d.eval_benign_full_x)
    log.info("exact float32 duplicates between pool_benign and trusted_eval benign: 0",
            n_checked=n_checked)

    fm = FidelityMeter(d.normalizer.transform(d.eval_benign_full_x), d.normalizer)
    rng = np.random.default_rng(0)
    rows = []
    for jit in JITTERS:
        adv = MimicryAdversary(d.pool_benign_x, d.normalizer, jit, SEED)
        batch, _ = adv.generate_batch(1, len(d.pool_benign_x))
        x = features_of(batch)
        dist = fm.distances(x, max_rows=len(x), rng=rng)
        row = {"jitter": jit, "n": len(dist), "median": float(np.median(dist)),
              "p5": float(np.percentile(dist, 5)), "twin_delta": TWIN_DELTA,
              "twin_fraction": float((dist <= TWIN_DELTA).mean()),
              "exact_duplicates": 0 if jit == 0.0 else None}
        rows.append(row)
        log.info("twin fraction", **row)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
