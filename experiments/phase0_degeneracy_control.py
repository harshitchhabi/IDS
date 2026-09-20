"""Shuffled-partition control for the degeneracy measurement (DECISIONS.md §16).

The MachineLearningCVE CICIDS2017 CSVs carry no Timestamp column; the cleaner
synthesizes a 1-row = 1-second file-order clock (``synthesized_timestamps``).
The temporal / burst splits are therefore splits on *file-order contiguity*, not
real time. This control shows the degeneracy does not depend on that: for each
family (and benign), pool the rows of seed_train + honeypot_pool + trusted_eval,
shuffle them uniformly at random, re-split into the same three sizes, and
measure the same guard-(c) statistic (median NN RMS, eval -> pool). A random
split has no temporal or burst structure to exploit or lose. If it gives the
same distances as the real partition, no split of any kind — real timestamps
included — can separate train from eval on this feature representation, because
the distances are set by the feature distribution, not by where the cut falls.

Writes ``<out>/nn_degeneracy_control.csv``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.logging_config import configure, get_logger
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions

log = get_logger("experiments.phase0_degeneracy_control")
QUERY_CAP = 20_000


def _nn_median(q: np.ndarray, ref: np.ndarray) -> tuple[float, float]:
    from sklearn.neighbors import NearestNeighbors

    d, _ = NearestNeighbors(n_neighbors=1).fit(ref).kneighbors(q)
    r = d.ravel() / np.sqrt(q.shape[1])
    return float(np.median(r)), float(np.percentile(r, 5))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/cicids"))
    ap.add_argument("--grid", type=float, default=0.005)
    ap.add_argument("--seed", type=int, default=20250903)
    args = ap.parse_args(argv)
    configure()
    from experiments._common import partition_config

    cfg = partition_config("cicids", "within_day_temporal", near_dup_grid=args.grid,
                           pool_withheld_families=(), seed_withheld_families=())
    data = load_partitions(source="cicids", synthetic_config=synthetic.SyntheticConfig(),
                           partition_config=cfg)
    norm = data.normalizer
    rng = np.random.default_rng(args.seed)
    frames = {p: data[p] for p in ("seed_train", "honeypot_pool", "trusted_eval")}

    rows = []
    fams = sorted(set(data["trusted_eval"][schema.LABEL].unique()))
    for fam in fams:
        parts = {p: df[df[schema.LABEL] == fam] for p, df in frames.items()}
        n_te, n_hp, n_sd = (len(parts["trusted_eval"]), len(parts["honeypot_pool"]),
                            len(parts["seed_train"]))
        if n_te < 2 or n_hp < 2:
            continue
        real_q, real_ref = parts["trusted_eval"], parts["honeypot_pool"]
        allx = norm.transform(pd.concat(list(parts.values())))
        perm = rng.permutation(len(allx))
        sh_te = allx[perm[:n_te]]
        sh_hp = allx[perm[n_te:n_te + n_hp]]
        for name, q, ref in (
            ("real_partition", norm.transform(real_q), norm.transform(real_ref)),
            ("shuffled_partition", sh_te, sh_hp),
        ):
            if len(q) > QUERY_CAP:
                q = q[np.sort(rng.choice(len(q), QUERY_CAP, replace=False))]
            med, p5 = _nn_median(q, ref)
            rows.append({"family": fam, "split": name, "n_trusted_eval": n_te,
                         "n_honeypot_pool": n_hp, "median_rms": med, "p5_rms": p5})
        log.info("control family done", family=fam)

    df = pd.DataFrame(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "nn_degeneracy_control.csv", index=False)
    wide = df.pivot(index="family", columns="split", values="median_rms")
    wide["ratio_shuffled_over_real"] = wide["shuffled_partition"] / wide["real_partition"]
    print(wide.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
