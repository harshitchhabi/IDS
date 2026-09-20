"""CICIDS2017 degeneracy measurement across every dedup grid (DECISIONS.md §16).

For each ``near_dup_grid`` and with burst-level splitting on, and with EVERY
family exposed to ``honeypot_pool`` (no withholding — withholding removes a
family's own near-duplicates from the guard-(c) search and makes a degenerate
family look structured, §15), record the nearest-neighbour distance from
``trusted_eval`` to ``honeypot_pool`` in normalized feature space:

* one row per attack family (min / median / p5 of the per-row NN RMS), and
* one ``BENIGN`` row (the benign-class guard-(c) percentiles),

so the table is the evidence that no reasonable split separates train from
eval on this feature representation. Writes
``<out>/nn_degeneracy_by_grid.csv``.
"""

from __future__ import annotations

import argparse
import gc
from pathlib import Path

import pandas as pd

from dloop.logging_config import configure, get_logger
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions

log = get_logger("experiments.phase0_degeneracy")

GRIDS = (0.005, 0.01, 0.02, 0.05)
DEGENERATE_RMS_THRESHOLD = 0.001   # same tier cut as phase0_nn_by_family.py
LEAK_THRESHOLD = 0.25              # guard (c) leak_warning gate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/cicids"))
    args = ap.parse_args(argv)
    configure()
    from experiments._common import partition_config

    rows = []
    for grid in GRIDS:
        cfg = partition_config("cicids", "within_day_temporal", near_dup_grid=grid,
                               pool_withheld_families=(), seed_withheld_families=())
        data = load_partitions(source="cicids", synthetic_config=synthetic.SyntheticConfig(),
                               partition_config=cfg)
        stats = data.eval_family_stats().set_index("family")
        for fam, d in data.leakage.nn_by_family.items():
            rows.append({
                "grid": grid, "class": "attack", "family": fam,
                "n_trusted_eval": int(stats.loc[fam, "n_trusted_eval"]),
                "min_rms": d["min_rms"], "median_rms": d["median_rms"],
                "tier": "degenerate" if d["min_rms"] < DEGENERATE_RMS_THRESHOLD else "structured",
            })
        b = data.leakage.nn_distance["benign"]["percentiles"]
        n_benign_eval = int((data["trusted_eval"]["is_attack"] == 0).sum())
        rows.append({
            "grid": grid, "class": "benign", "family": "BENIGN",
            "n_trusted_eval": n_benign_eval,
            "min_rms": b["p0"], "median_rms": b["p50"], "p5_rms": b["p5"],
            "tier": "degenerate" if b["p0"] < DEGENERATE_RMS_THRESHOLD else "structured",
        })
        a = data.leakage.nn_distance["attack"]["percentiles"]
        rows.append({
            "grid": grid, "class": "attack", "family": "ALL_ATTACK",
            "n_trusted_eval": int(data["trusted_eval"]["is_attack"].sum()),
            "min_rms": a["p0"], "median_rms": a["p50"], "p5_rms": a["p5"],
            "tier": "degenerate" if a["p0"] < DEGENERATE_RMS_THRESHOLD else "structured",
        })
        log.info("degeneracy grid done", grid=grid, attack_p5=a["p5"], benign_p5=b["p5"])
        del data
        gc.collect()

    df = pd.DataFrame(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "nn_degeneracy_by_grid.csv", index=False)
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
