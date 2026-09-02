"""Phase 0 dataset entry point: choose a source, return the four partitions.

Usage::

    from dloop.sim.dataset import load_partitions
    data = load_partitions(source="auto")   # cicids if present, else synthetic
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

from dloop.logging_config import get_logger
from dloop.sim import cicids, synthetic
from dloop.sim.partition import PartitionConfig, PartitionedData, build_partitions

log = get_logger("sim.dataset")

Source = Literal["auto", "cicids", "synthetic"]


def load_raw_by_day(
    source: Source = "auto",
    *,
    cicids_root: Path | str = cicids.DEFAULT_ROOT,
    synthetic_config: synthetic.SyntheticConfig | None = None,
) -> tuple[dict[str, pd.DataFrame], str]:
    """Return ``(raw_by_day, resolved_source)``."""
    if source == "auto":
        source = "cicids" if cicids.is_available(cicids_root) else "synthetic"
        log.info("auto-selected data source", source=source)

    if source == "cicids":
        return cicids.load_raw_by_day(cicids_root), "cicids"
    if source == "synthetic":
        return synthetic.generate_raw_by_day(synthetic_config), "synthetic"
    raise ValueError(f"unknown source: {source!r}")


def load_partitions(
    source: Source = "auto",
    *,
    cicids_root: Path | str = cicids.DEFAULT_ROOT,
    synthetic_config: synthetic.SyntheticConfig | None = None,
    partition_config: PartitionConfig | None = None,
) -> PartitionedData:
    raw, resolved = load_raw_by_day(
        source, cicids_root=cicids_root, synthetic_config=synthetic_config
    )
    data = build_partitions(raw, config=partition_config)
    log.info("partitions built", source=resolved, strategy=data.config.strategy,
             rows={p: len(df) for p, df in data.frames.items()},
             leak_warning=data.leakage.leak_warning)
    return data
