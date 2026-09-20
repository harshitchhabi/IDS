"""Build the compact loop dataset (``data/loop/<source>.npz``, gitignored) from
the Phase 0 partitions. Run once per source; the loop runner and its worker
processes only load the result."""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stderr
from pathlib import Path

from dloop.logging_config import configure
from dloop.loop.data import from_partitions
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["cicids", "synthetic"], required=True)
    ap.add_argument("--out", type=Path, default=Path("data/loop"))
    args = ap.parse_args(argv)
    configure()
    from experiments._common import partition_config

    cfg = partition_config(args.source, "within_day_temporal")   # cicids: grid 0.005, DDoS/Hulk arms
    with redirect_stderr(io.StringIO()):
        data = load_partitions(source=args.source, synthetic_config=synthetic.SyntheticConfig(),
                               partition_config=cfg)
    ld = from_partitions(data, args.source)
    path = args.out / f"{args.source}.npz"
    ld.save(path)
    print(json.dumps({"path": str(path), "seed_rows": len(ld.seed_x),
                      "pool_benign": len(ld.pool_benign_x), "pool_attack": len(ld.pool_attack_x),
                      "eval_rows": len(ld.eval_x), "arm_counts": ld.arm_counts(),
                      "near_dup_grid": cfg.near_dup_grid, "leak_warning": data.leakage.leak_warning},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
