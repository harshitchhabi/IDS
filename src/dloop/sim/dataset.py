"""Phase 0 dataset entry point: choose a source, return the four partitions.

Usage::

    from dloop.sim.dataset import load_partitions
    data = load_partitions(source="auto")   # cicids if present, else synthetic
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

from dloop.features import schema
from dloop.logging_config import get_logger
from dloop.sim import cicids, cicids_fixed, netflow_v2, synthetic, unsw_nb15
from dloop.sim.partition import PartitionConfig, PartitionedData, build_partitions

log = get_logger("sim.dataset")

Source = Literal["auto", "cicids", "cicids-fixed", "unsw-nb15", "nf-unsw-nb15-v2",
                 "nf-cse-cic-ids2018-v2", "nf-ton-iot-v2", "lab", "synthetic"]

# Feature set per source: every canonical feature unless the dataset has no
# analogue for some of them (then they are left out, not fabricated).
SOURCE_FEATURES: dict[str, tuple[str, ...]] = {
    "unsw-nb15": schema.UNSW_FEATURES,
    **{s: schema.NETFLOW_V2_FEATURES for s in netflow_v2.DATASETS},
}
# every --dataset / --source value the experiment scripts accept
ALL_SOURCES: tuple[str, ...] = ("cicids", "cicids-fixed", "unsw-nb15", *netflow_v2.DATASETS, "lab", "synthetic")


def features_for(source: str) -> tuple[str, ...]:
    return SOURCE_FEATURES.get(source, schema.CANONICAL_FEATURES)


def load_raw_by_day(
    source: Source = "auto",
    *,
    cicids_root: Path | str = cicids.DEFAULT_ROOT,
    cicids_fixed_root: Path | str = cicids_fixed.DEFAULT_ROOT,
    unsw_root: Path | str = unsw_nb15.DEFAULT_ROOT,
    netflow_root: Path | str = netflow_v2.DEFAULT_ROOT,
    synthetic_config: synthetic.SyntheticConfig | None = None,
) -> tuple[dict[str, pd.DataFrame], str]:
    """Return ``(raw_by_day, resolved_source)``."""
    if source == "auto":
        source = "cicids" if cicids.is_available(cicids_root) else "synthetic"
        log.info("auto-selected data source", source=source)

    if source == "cicids":
        return cicids.load_raw_by_day(cicids_root), "cicids"
    if source == "cicids-fixed":
        return cicids_fixed.load_raw_by_day(cicids_fixed_root), "cicids-fixed"
    if source == "unsw-nb15":
        return unsw_nb15.load_raw_by_day(unsw_root), "unsw-nb15"
    if source in netflow_v2.DATASETS:
        return netflow_v2.load_raw_by_day(source, netflow_root), source
    if source == "synthetic":
        return synthetic.generate_raw_by_day(synthetic_config), "synthetic"
    raise ValueError(f"unknown source: {source!r}")


def load_partitions(
    source: Source = "auto",
    *,
    cicids_root: Path | str = cicids.DEFAULT_ROOT,
    cicids_fixed_root: Path | str = cicids_fixed.DEFAULT_ROOT,
    unsw_root: Path | str = unsw_nb15.DEFAULT_ROOT,
    netflow_root: Path | str = netflow_v2.DEFAULT_ROOT,
    synthetic_config: synthetic.SyntheticConfig | None = None,
    partition_config: PartitionConfig | None = None,
) -> PartitionedData:
    raw, resolved = load_raw_by_day(
        source, cicids_root=cicids_root, cicids_fixed_root=cicids_fixed_root,
        unsw_root=unsw_root, netflow_root=netflow_root, synthetic_config=synthetic_config,
    )
    data = build_partitions(raw, config=partition_config, features=features_for(resolved))
    log.info("partitions built", source=resolved, strategy=data.config.strategy,
             rows={p: len(df) for p, df in data.frames.items()},
             leak_warning=data.leakage.leak_warning)
    return data
