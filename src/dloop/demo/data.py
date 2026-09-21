"""Demo dataset: the Phase 0 loop dataset with the seed set subsampled so one retrain takes well under a second."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from dloop.loop.data import LoopData

DEMO_SEED_ROWS = 20_000
DEMO_SUBSAMPLE_SEED = 20250903   # fixed: the demo's seed set is the same on every run


def load_demo_data(path: str | Path = "data/loop/cicids.npz", seed_rows: int = DEMO_SEED_ROWS) -> LoopData:
    d = LoopData.load(path)
    if seed_rows >= len(d.seed_x):
        return d
    idx = np.sort(np.random.default_rng(DEMO_SUBSAMPLE_SEED).choice(len(d.seed_x), seed_rows, replace=False))
    return replace(d, seed_x=d.seed_x[idx], seed_y=d.seed_y[idx])
