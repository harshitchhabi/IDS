"""Per-(day, family) inter-flow gap distribution on cleaned CICIDS2017 attack
streams — run *before* choosing ``PartitionConfig.burst_gap_seconds`` (guard b,
DECISIONS.md §14). Reports percentiles of the gap between consecutive flows
within a family's stream, plus the fraction of gaps exceeding a few candidate
thresholds, so the burst-segmentation threshold is picked from evidence rather
than a guess.

Writes ``<out>/burst_gap_distribution.csv``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.features.cleaning import clean_flows
from dloop.logging_config import configure, get_logger
from dloop.sim import cicids

log = get_logger("experiments.phase0_burst_gaps")

CANDIDATE_THRESHOLDS_S = (1.0, 2.0, 5.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/cicids"))
    args = ap.parse_args(argv)
    configure()

    raw = cicids.load_raw_by_day(cicids.DEFAULT_ROOT)
    rows = []
    for day, df in raw.items():
        clean, _ = clean_flows(df, source=day)
        for (label, is_atk), grp in clean.groupby([schema.LABEL, schema.BINARY_LABEL], sort=True):
            if is_atk == 0:
                continue
            ts = grp.sort_values(schema.TIMESTAMP)[schema.TIMESTAMP].to_numpy("datetime64[ns]")
            if len(ts) < 2:
                continue
            gaps = np.diff(ts) / np.timedelta64(1, "s")
            pct = np.percentile(gaps, [1, 5, 25, 50, 75, 90, 95, 99])
            row = {
                "day": day, "family": label, "n": len(ts),
                "p1": pct[0], "p5": pct[1], "p25": pct[2], "p50": pct[3],
                "p75": pct[4], "p90": pct[5], "p95": pct[6], "p99": pct[7],
                "max_gap": float(gaps.max()),
            }
            for t in CANDIDATE_THRESHOLDS_S:
                row[f"frac_gap_gt_{t:g}s"] = float(np.mean(gaps > t))
                row[f"n_bursts_at_{t:g}s"] = int(np.sum(gaps > t)) + 1
            rows.append(row)

    out_df = pd.DataFrame(rows).sort_values(["day", "family"]).reset_index(drop=True)
    args.out.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out / "burst_gap_distribution.csv", index=False)
    print("\n=== per-family inter-flow gap distribution (seconds), cleaned CICIDS2017 ===\n")
    print(out_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
