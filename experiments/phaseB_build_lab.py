"""Build the Phase B lab loop cache ``data/loop/lab.npz`` from the captured,
extracted and labelled lab flows (DECISIONS.md §32.0, §32.4).

Input is ``label.py``'s output for the whole lab capture (canonical features +
``true_intent`` + ``true_kind`` + ``policy_label``). We build the role-based
partitions (``dloop.sim.lab``) and the loop cache (``LoopData.from_partitions``).
The npz is gitignored; only this code is committed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dloop.features import schema
from dloop.loop.data import from_partitions
from dloop.logging_config import configure, get_logger
from dloop.sim.lab import LabSplitConfig, build_lab_partitions

log = get_logger("experiments.phaseB_build_lab")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labelled", type=Path, default=Path("lab/data/lab_labelled.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/loop/lab.npz"))
    ap.add_argument("--primary-strategy", default="oracle",
                    help="mimic strategy that feeds honeypot_pool (set from B.1)")
    args = ap.parse_args(argv)
    configure()

    labelled = pd.read_csv(args.labelled, low_memory=False)
    data = build_lab_partitions(labelled, LabSplitConfig(primary_strategy=args.primary_strategy),
                                features=schema.CANONICAL_FEATURES)
    ld = from_partitions(data, name="lab")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ld.save(args.out)
    print(f"wrote {args.out}: seed={len(ld.seed_x)} pool_benign={len(ld.pool_benign_x)} "
          f"pool_attack={len(ld.pool_attack_x)} eval={len(ld.eval_x)} "
          f"eval_benign_full={len(ld.eval_benign_full_x)}; leak_warning={data.leakage.leak_warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
