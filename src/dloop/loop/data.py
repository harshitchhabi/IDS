"""The compact, self-contained dataset the loop runs on.

The loop is cheap per round but is run thousands of times, so it works on a
fixed, seeded subsample of the Phase 0 partitions rather than millions of rows,
and is saved as one ``.npz`` that worker processes load without re-running the
partition pipeline. Nothing here is fit on eval rows; ``trusted_eval`` is only
ever read.

The subsample is fixed by ``LoopDataConfig.seed`` (not by the per-run seeds), so
between-seed variance in results reflects model/adversary randomness, not a
changing test set. :meth:`LoopData.redraw_eval` is the opt-in alternative
(Phase R item R1, DECISIONS.md §31): the eval subsample is redrawn per run seed,
at the same sizes and caps, so between-seed variance also covers which trusted
rows happen to be scored. The fixed subsample stays the default so every
published result reproduces unchanged.
"""

from __future__ import annotations

import dataclasses
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
    # column order of every *_x array; the full canonical set unless the dataset
    # has no analogue for some features (files saved before this field existed
    # load as the full set, which is what they hold)
    features: tuple[str, ...] = schema.CANONICAL_FEATURES
    # ALL trusted_eval attack rows in reportable arms (for redraw_eval); None in
    # files built before this field existed
    eval_attack_full_x: np.ndarray | None = None
    eval_attack_full_family: np.ndarray | None = None
    eval_attack_full_arm: np.ndarray | None = None
    # family label of every seed_x row ("BENIGN" for benign); None in older files
    seed_family: np.ndarray | None = None

    @property
    def normalizer(self) -> Normalizer:
        return Normalizer(self.features, self.norm_center, self.norm_scale)

    def arm_counts(self) -> dict[str, int]:
        return {a: int(np.sum(self.eval_arm == a)) for a in ARMS}

    def seed_family_rows(self, family: str) -> np.ndarray:
        """seed_train rows of one attack family: correctly labelled traffic the
        detector already trained on (the stale-replay crowd-out filler)."""
        if self.seed_family is None:
            raise ValueError("this loop .npz predates seed_family; rebuild it with "
                             "python -m experiments.phase0_loop_data --source <dataset>")
        sel = (self.seed_family == family) & (self.seed_y == 1)
        if not sel.any():
            raise ValueError(f"no seed_train attack rows of family {family!r}; families: "
                             f"{sorted(set(self.seed_family[self.seed_y == 1].tolist()))}")
        return self.seed_x[sel]

    def redraw_eval(self, run_seed: int, cfg: "LoopDataConfig | None" = None) -> "LoopData":
        """A copy whose eval subsample is redrawn for ``run_seed``: the same benign
        size and per-family attack cap as the default subsample, drawn from all of
        trusted_eval with ``default_rng([cfg.seed, run_seed])``. Training and pool
        arrays are shared, not copied; nothing outside trusted_eval is touched."""
        if self.eval_attack_full_x is None:
            raise ValueError("this loop .npz predates per-seed eval redraw; rebuild it with "
                             "python -m experiments.phase0_loop_data --source <dataset>")
        cfg = cfg or LoopDataConfig()
        rng = np.random.default_rng([cfg.seed, int(run_seed)])
        n_b = len(self.eval_benign_full_x)
        ib = np.sort(rng.choice(n_b, min(cfg.eval_benign_rows, n_b), replace=False))
        xs, fams, arms = [self.eval_benign_full_x[ib]], [np.full(len(ib), schema.BENIGN_LABEL)], [
            np.full(len(ib), "benign")]
        for fam in sorted(set(self.eval_attack_full_family.tolist())):
            idx = np.flatnonzero(self.eval_attack_full_family == fam)
            take = idx[np.sort(rng.choice(len(idx), min(cfg.eval_attack_cap_per_family, len(idx)),
                                          replace=False))]
            xs.append(self.eval_attack_full_x[take])
            fams.append(self.eval_attack_full_family[take])
            arms.append(self.eval_attack_full_arm[take])
        n_atk = sum(len(a) for a in xs[1:])
        return dataclasses.replace(
            self,
            eval_x=np.concatenate(xs).astype("float32"),
            eval_y=np.concatenate([np.zeros(len(ib), dtype="int64"), np.ones(n_atk, dtype="int64")]),
            eval_family=np.concatenate(fams).astype("U40"),
            eval_arm=np.concatenate(arms).astype("U16"),
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        extra = {}
        if self.eval_attack_full_x is not None:
            extra = dict(eval_attack_full_x=self.eval_attack_full_x,
                         eval_attack_full_family=self.eval_attack_full_family,
                         eval_attack_full_arm=self.eval_attack_full_arm)
        if self.seed_family is not None:
            extra["seed_family"] = self.seed_family
        np.savez_compressed(p, name=np.array(self.name), seed_x=self.seed_x, seed_y=self.seed_y,
                            pool_benign_x=self.pool_benign_x, pool_attack_x=self.pool_attack_x,
                            eval_x=self.eval_x, eval_y=self.eval_y, eval_family=self.eval_family,
                            eval_arm=self.eval_arm, eval_benign_full_x=self.eval_benign_full_x,
                            norm_center=self.norm_center, norm_scale=self.norm_scale,
                            features=np.array(self.features), **extra)

    @classmethod
    def load(cls, path: str | Path) -> "LoopData":
        z = np.load(Path(path), allow_pickle=False)
        kw = {k: z[k] for k in z.files if k not in ("name", "features")}
        if "features" in z.files:
            kw["features"] = tuple(str(f) for f in z["features"])
        return cls(name=str(z["name"]), **kw)


def _x(df, features: tuple[str, ...]) -> np.ndarray:
    return df[list(features)].to_numpy("float32")


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
    full_parts, full_arms = [], []
    for fam, g in te_a.groupby(schema.LABEL, sort=True):
        arm = data.eval_family_arm(str(fam))
        if arm not in ARMS:           # novel: n=0 and no prospect of filling it
            continue
        k = min(cfg.eval_attack_cap_per_family, len(g))
        parts.append(g.iloc[np.sort(rng.choice(len(g), k, replace=False))])
        arms.extend([arm] * k)
        full_parts.append(g)          # no rng draw: the default subsample is unchanged
        full_arms.extend([arm] * len(g))
    sub_a = pd.concat(parts)
    full_a = pd.concat(full_parts)

    eval_df = pd.concat([sub_b, sub_a])
    eval_arm = np.array(["benign"] * len(sub_b) + arms, dtype="U16")
    feats = data.features
    ld = LoopData(
        name=name,
        seed_x=_x(seed_df, feats), seed_y=seed_df[schema.BINARY_LABEL].to_numpy("int64"),
        pool_benign_x=_x(pool_b, feats), pool_attack_x=_x(pool_a, feats),
        eval_x=_x(eval_df, feats), eval_y=eval_df[schema.BINARY_LABEL].to_numpy("int64"),
        eval_family=eval_df[schema.LABEL].to_numpy().astype("U40"),
        eval_arm=eval_arm,
        eval_benign_full_x=_x(te_b, feats),
        norm_center=np.asarray(data.normalizer.center), norm_scale=np.asarray(data.normalizer.scale),
        features=feats,
        eval_attack_full_x=_x(full_a, feats),
        eval_attack_full_family=full_a[schema.LABEL].to_numpy().astype("U40"),
        eval_attack_full_arm=np.array(full_arms, dtype="U16"),
        seed_family=seed_df[schema.LABEL].to_numpy().astype("U40"),
    )
    log.info("loop data built", name=name, config=asdict(cfg), seed_rows=len(ld.seed_x),
             pool_benign=len(ld.pool_benign_x), pool_attack=len(ld.pool_attack_x),
             eval_rows=len(ld.eval_x), arm_counts=ld.arm_counts())
    return ld
