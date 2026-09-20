"""The compact, self-contained dataset the loop runs on.

The loop is cheap per round but is run thousands of times, so it works on a
fixed, seeded subsample of the Phase 0 partitions rather than millions of rows,
and is saved as one ``.npz`` that worker processes load without re-running the
partition pipeline. Nothing here is fit on eval rows; ``trusted_eval`` is only
ever read.

The subsample is fixed by ``LoopDataConfig.seed`` (not by the per-run seeds), so
between-seed variance in results reflects model/adversary randomness, not a
changing test set.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.features.normalize import Normalizer
from dloop.logging_config import get_logger
from dloop.sim.partition import PartitionedData

log = get_logger("loop.data")

ARMS: tuple[str, ...] = ("seen_both", "seed_only", "honeypot_only")   # novel dropped: n=0
MIN_ARM_ROWS = 500   # same bar as per-family reporting (DECISIONS.md §1)


@dataclass(frozen=True)
class LoopDataConfig:
    seed_train_rows: int = 30_000
    eval_benign_rows: int = 40_000
    eval_attack_cap_per_family: int = 4_000
    seed: int = 20250903


@dataclass
class LoopData:
    name: str
    seed_x: np.ndarray            # (n, F) float32 raw features
    seed_y: np.ndarray            # (n,) int64
    pool_benign_x: np.ndarray
    pool_attack_x: np.ndarray
    eval_x: np.ndarray            # subsample used for per-round scoring
    eval_y: np.ndarray
    eval_family: np.ndarray       # str; "BENIGN" for benign rows
    eval_arm: np.ndarray          # str; "benign" | one of ARMS
    eval_benign_full_x: np.ndarray  # ALL trusted_eval benign rows (fidelity reference)
    norm_center: np.ndarray
    norm_scale: np.ndarray

    @property
    def normalizer(self) -> Normalizer:
        return Normalizer(schema.CANONICAL_FEATURES, self.norm_center, self.norm_scale)

    def arm_counts(self) -> dict[str, int]:
        return {a: int(np.sum(self.eval_arm == a)) for a in ARMS}

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(p, name=np.array(self.name), seed_x=self.seed_x, seed_y=self.seed_y,
                            pool_benign_x=self.pool_benign_x, pool_attack_x=self.pool_attack_x,
                            eval_x=self.eval_x, eval_y=self.eval_y, eval_family=self.eval_family,
                            eval_arm=self.eval_arm, eval_benign_full_x=self.eval_benign_full_x,
                            norm_center=self.norm_center, norm_scale=self.norm_scale)

    @classmethod
    def load(cls, path: str | Path) -> "LoopData":
        z = np.load(Path(path), allow_pickle=False)
        return cls(name=str(z["name"]), **{k: z[k] for k in z.files if k != "name"})


def _x(df) -> np.ndarray:
    return df[list(schema.CANONICAL_FEATURES)].to_numpy("float32")


def from_partitions(data: PartitionedData, name: str, cfg: LoopDataConfig | None = None) -> LoopData:
    cfg = cfg or LoopDataConfig()
    rng = np.random.default_rng(cfg.seed)

    seed_df = data["seed_train"]
    n = min(cfg.seed_train_rows, len(seed_df))
    seed_df = seed_df.iloc[np.sort(rng.choice(len(seed_df), n, replace=False))]

    pool = data["honeypot_pool"]
    pool_b = pool[pool[schema.BINARY_LABEL] == 0]
    pool_a = pool[pool[schema.BINARY_LABEL] == 1]

    te = data["trusted_eval"]
    te_b = te[te[schema.BINARY_LABEL] == 0]
    te_a = te[te[schema.BINARY_LABEL] == 1]
    sub_b = te_b.iloc[np.sort(rng.choice(len(te_b), min(cfg.eval_benign_rows, len(te_b)), replace=False))]

    parts, arms = [], []
    for fam, g in te_a.groupby(schema.LABEL, sort=True):
        arm = data.eval_family_arm(str(fam))
        if arm not in ARMS:           # novel: n=0 and no prospect of filling it
            continue
        k = min(cfg.eval_attack_cap_per_family, len(g))
        parts.append(g.iloc[np.sort(rng.choice(len(g), k, replace=False))])
        arms.extend([arm] * k)
    sub_a = pd.concat(parts)

    eval_df = pd.concat([sub_b, sub_a])
    eval_arm = np.array(["benign"] * len(sub_b) + arms, dtype="U16")
    ld = LoopData(
        name=name,
        seed_x=_x(seed_df), seed_y=seed_df[schema.BINARY_LABEL].to_numpy("int64"),
        pool_benign_x=_x(pool_b), pool_attack_x=_x(pool_a),
        eval_x=_x(eval_df), eval_y=eval_df[schema.BINARY_LABEL].to_numpy("int64"),
        eval_family=eval_df[schema.LABEL].to_numpy().astype("U40"),
        eval_arm=eval_arm,
        eval_benign_full_x=_x(te_b),
        norm_center=np.asarray(data.normalizer.center), norm_scale=np.asarray(data.normalizer.scale),
    )
    log.info("loop data built", name=name, config=asdict(cfg), seed_rows=len(ld.seed_x),
             pool_benign=len(ld.pool_benign_x), pool_attack=len(ld.pool_attack_x),
             eval_rows=len(ld.eval_x), arm_counts=ld.arm_counts())
    return ld
