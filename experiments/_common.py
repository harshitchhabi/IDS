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

# CICIDS2017 withholding: high-volume families only, so the arm is large enough
# to carry a stable per-family TPR (>500 trusted_eval rows). DDoS is kept out of
# honeypot_pool -> seed_only, A4's controlled arm (PortScan was the other
# candidate but its post-cleaning volume is too small: ~1.9k rows total for the
# whole day, nowhere near "tens of thousands" once deduplicated and split).
# DoS Hulk is kept out of seed_train -> honeypot_only, the loop teaching a
# family the detector only saw through the decoy. DECISIONS.md §15: with every
# family exposed to honeypot_pool, BOTH are guard-(c) degenerate (DDoS min_rms
# 3.8e-05, DoS Hulk 5.8e-05) — no CICIDS2017 family is simultaneously
# reportable (>=500 rows) and non-degenerate, so these two are chosen for
# volume/row-count bookkeeping only. Their arm TPRs measure memorization
# capacity on this dataset, not the learning claim.
_CICIDS_WITHHOLD = dict(
    pool_withheld_families=("DDoS",),
    seed_withheld_families=("DoS Hulk",),
    # Gentlest grid that still passes assert_disjoint (phase0_grid_sweep.py);
    # burst splitting (DECISIONS.md §14) makes the more aggressive grids
    # unnecessary for boundary safety, and a coarser grid guts exactly the
    # lower-volume families that would otherwise be candidates for a
    # structured arm.
    near_dup_grid=0.005,
)

# Reprocessed CICIDS2017 (Phase A item B, DECISIONS.md §29.B): the same two
# families exist under the same names, and are withheld the same way so the only
# axis that changes against CICIDS2017 is the dataset. The grid is chosen by the
# same rule as CICIDS2017's (gentlest grid in phase0_grid_sweep.py's sweep that
# passes assert_disjoint), recorded in docs/phaseA/datasets-results.md.
_CICIDS_FIXED_WITHHOLD = dict(
    pool_withheld_families=("DDoS",),
    seed_withheld_families=("DoS Hulk",),
    near_dup_grid=0.005,   # results/phaseA/datasets/cicids-fixed/grid_sweep.csv
)

# UNSW-NB15: no family withholding (no counterpart to CICIDS2017's DDoS / DoS Hulk
# arms; docs/phaseA/datasets-results.md §2); grid by the same sweep rule.
_UNSW_PARTITION = dict(
    near_dup_grid=0.005,   # results/phaseA/datasets/unsw-nb15/grid_sweep.csv
)


# UQ NetFlow v2 (Phase R item R3, DECISIONS.md §31): no family withholding, as for
# UNSW-NB15. Each grid starts at 0.005; the R3 session runs phase0_grid_sweep.py
# first and, if 0.005 fails assert_disjoint for a dataset, sets that dataset's
# entry to the gentlest grid that passes (the rule every other dataset used),
# recording the sweep in results/phaseR/r3/<dataset>/.
NETFLOW_GRID: dict[str, float] = {
    "nf-unsw-nb15-v2": 0.005,
    "nf-cse-cic-ids2018-v2": 0.005,
    "nf-ton-iot-v2": 0.005,
}
NETFLOW_SOURCES = tuple(NETFLOW_GRID)


def partition_config(source: str, strategy: str = "within_day_temporal", **overrides) -> PartitionConfig:
    kw: dict = {"strategy": strategy}
    if strategy == "within_day_temporal":
        if source == "synthetic":
            kw.update(_SYNTHETIC_WITHHOLD)
        elif source == "cicids":
            kw.update(_CICIDS_WITHHOLD)
        elif source == "cicids-fixed":
            kw.update(_CICIDS_FIXED_WITHHOLD)
        elif source == "unsw-nb15":
            kw.update(_UNSW_PARTITION)
        elif source in NETFLOW_SOURCES:
            kw.update(near_dup_grid=NETFLOW_GRID[source])
    kw.update({k: v for k, v in overrides.items() if v is not None})
    return PartitionConfig(**kw)
