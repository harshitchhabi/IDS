"""Shared Phase 0 experiment config so the explore and model scripts agree."""

from __future__ import annotations

from dloop.sim.partition import PartitionConfig

# On synthetic data the four eval-family arms are populated explicitly so the
# committed results table is meaningful: SSH-Patator withheld from the pool
# (seed_only / A4), DoS Hulk withheld from seed_train (honeypot_only), Bot
# withheld from both (novel). Everything else is seen_both. On real CICIDS2017
# nothing is withheld by default — S0's baseline is all-seen_both, and A4
# experiments set the withholding lists themselves.
_SYNTHETIC_WITHHOLD = dict(
    pool_withheld_families=("SSH-Patator", "Bot"),
    seed_withheld_families=("DoS Hulk", "Bot"),
)


def partition_config(source: str, strategy: str = "within_day_temporal", **overrides) -> PartitionConfig:
    kw: dict = {"strategy": strategy}
    if source == "synthetic" and strategy == "within_day_temporal":
        kw.update(_SYNTHETIC_WITHHOLD)
    kw.update({k: v for k, v in overrides.items() if v is not None})
    return PartitionConfig(**kw)
