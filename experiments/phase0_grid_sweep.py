"""Guard (a) grid-resolution sweep.

On real CICIDS2017 the near-duplicate guard removes ~49% of the cleaned dataset
at the default grid (0.02), most of it benign — which reshapes the benign
distribution that FPR is measured against. This sweeps the grid and reports, for
each setting: rows removed per class, partition sizes, the leak warning, and
RF/XGBoost trusted_eval metrics (fast configs — this is a sensitivity check, not
the final numbers). If S0/A1 conclusions move with this parameter, the guard is
doing the work the attack should be doing.

Writes ``<out>/grid_sweep.csv``.
"""

from __future__ import annotations

import argparse
import gc
import io
from contextlib import redirect_stderr
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.logging_config import configure, get_logger
from dloop.models import ModelConfig, make_model
from dloop.models.metrics import binary_metrics
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions

log = get_logger("experiments.phase0_grid_sweep")

GRIDS = (0.0, 0.005, 0.01, 0.02, 0.05)   # 0.0 == guard (a) off
FAST = {"rf": {"n_estimators": 40}, "xgboost": {"n_estimators": 40}}
SEED = 20250903


def _xy(df: pd.DataFrame):
    return (df[list(schema.CANONICAL_FEATURES)].to_numpy("float64"),
            df[schema.BINARY_LABEL].to_numpy("int64"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["auto", "cicids", "synthetic"], default="synthetic")
    ap.add_argument("--strategy", choices=["within_day_temporal", "day_split"],
                    default="within_day_temporal")
    ap.add_argument("--out", type=Path, default=Path("results/phase0"))
    args = ap.parse_args(argv)
    configure()
    from experiments._common import partition_config

    rows = []
    for grid in GRIDS:
        cfg = partition_config(args.source, args.strategy, near_dup_grid=grid)
        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                data = load_partitions(source=args.source,
                                       synthetic_config=synthetic.SyntheticConfig(),
                                       partition_config=cfg)
        except AssertionError as e:
            # e.g. guard (a) off -> the partition has genuine row-content overlap
            log.warning("grid point produced an invalid partition", grid=grid, error=str(e))
            rows.append({"grid": grid, "partition_valid": False, "note": str(e)})
            continue
        nd = data.leakage.near_dups_removed
        by_class: dict[str, int] = {}
        for day in nd.values():
            for k, v in day.items():
                by_class[k] = by_class.get(k, 0) + v
        nd_benign = by_class.pop(schema.BENIGN_LABEL, 0)
        nd_attack = sum(by_class.values())

        Xtr, ytr = _xy(data["seed_train"])
        te = data["trusted_eval"]
        Xte, yte = _xy(te)
        row = {
            "grid": grid,
            "partition_valid": True,
            "near_dup_benign": nd_benign,
            "near_dup_attack": nd_attack,
            "seed_train": len(data["seed_train"]),
            "honeypot_pool": len(data["honeypot_pool"]),
            "trusted_eval": len(te),
            "leak_warning": data.leakage.leak_warning,
            "nn_attack_p5": round(
                data.leakage.nn_distance.get("attack", {}).get("percentiles", {}).get("p5", float("nan")), 4),
        }
        for kind in ("rf", "xgboost"):
            model = make_model(ModelConfig(kind=kind, seed=SEED, target_fpr=0.01,
                                          hyperparams=FAST[kind])).fit(Xtr, ytr)
            m = binary_metrics(yte, model.score_samples(Xte), model.threshold_)
            row[f"{kind}_eval_fpr"] = round(m["fpr"], 4)
            row[f"{kind}_eval_tpr"] = round(m["tpr"], 4)
            row[f"{kind}_auroc"] = round(m["auroc"], 4)
            del model
        log.info("grid point done", **row)
        rows.append(row)
        del data, Xtr, ytr, Xte, yte, te
        gc.collect()

    df = pd.DataFrame(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "grid_sweep.csv", index=False)
    print(f"\n=== guard (a) grid sweep ({args.source} / {args.strategy}) ===\n")
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
