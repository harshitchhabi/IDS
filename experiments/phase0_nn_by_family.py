"""Commit the per-family guard-(c) nearest-neighbour table as data, not prose
(DECISIONS.md §14). For every trusted_eval attack family, the NN distance in
normalized feature space to its nearest honeypot_pool row of the same class,
plus a **measured** degeneracy tier:

  degenerate  min_rms < DEGENERATE_RMS_THRESHOLD — one honeypot_pool flow is
              close enough to teach the detector the whole family; an S0 gain
              here is not evidence of learning.
  structured  everything else — genuine held-out signal, S0's learning claim
              is reported on this tier only.

The tier is a property of the family's flow-statistic distribution under
CICFlowMeter, not of the split strategy: it does not change whether the cut is
row-level or burst-level (DECISIONS.md §14 measured both).

Writes ``<out>/nn_by_family.csv``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dloop.logging_config import configure, get_logger
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions

log = get_logger("experiments.phase0_nn_by_family")

# Below this normalized per-feature RMS, a single honeypot_pool row is
# functionally the same flow as the trusted_eval row it is nearest to — the
# family carries no held-out signal. Chosen well inside the near-duplicate
# guard's own grid range (0.005-0.05) and an order of magnitude below the
# leak_warning gate (0.25) used for the aggregate check: this is a per-family
# tier cut, not a restatement of guard (c).
DEGENERATE_RMS_THRESHOLD = 0.001


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["auto", "cicids", "synthetic"], default="cicids")
    ap.add_argument("--strategy", choices=["within_day_temporal", "day_split"],
                    default="within_day_temporal")
    ap.add_argument("--near-dup-grid", type=float, default=0.005)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/cicids"))
    ap.add_argument("--withhold", action="store_true",
                    help="apply the configured A4/honeypot_only withholding (default: off). "
                         "Withholding a family from honeypot_pool removes its own same-family "
                         "neighbours from the guard-(c) search, which can make a degenerate "
                         "family look 'structured' as an artifact of the arm assignment, not "
                         "its actual feature-space structure. The tier here is meant to be an "
                         "intrinsic per-family property, so it is measured with every family "
                         "exposed to honeypot_pool (seen_both) by default.")
    args = ap.parse_args(argv)
    configure()
    from experiments._common import partition_config

    overrides = {"near_dup_grid": args.near_dup_grid}
    if not args.withhold:
        overrides["pool_withheld_families"] = ()
        overrides["seed_withheld_families"] = ()
    cfg = partition_config(args.source, args.strategy, **overrides)
    data = load_partitions(source=args.source, synthetic_config=synthetic.SyntheticConfig(),
                           partition_config=cfg)

    stats = data.eval_family_stats().set_index("family")
    rows = []
    for fam, d in data.leakage.nn_by_family.items():
        tier = "degenerate" if d["min_rms"] < DEGENERATE_RMS_THRESHOLD else "structured"
        s = stats.loc[fam] if fam in stats.index else None
        rows.append({
            "family": fam,
            "arm": d["arm"],
            # d["n"] is the NN-check QUERY count, capped at nn_check_query_sample
            # (subsampled across the whole trusted_eval attack class, not
            # per-family) — not the true partition row count. Use the real
            # count from eval_family_stats for reportability; keep the query
            # count too since min_rms/median_rms were computed on that sample.
            "n_trusted_eval": int(s["n_trusted_eval"]) if s is not None else d["n"],
            "n_nn_query": d["n"],
            "min_rms": d["min_rms"],
            "median_rms": d["median_rms"],
            "tier": tier,
            "reportable": bool(s["reportable"]) if s is not None else False,
            "n_seed_train": int(s["n_seed_train"]) if s is not None else 0,
            "n_honeypot_pool": int(s["n_honeypot_pool"]) if s is not None else 0,
        })
    df = pd.DataFrame(rows).sort_values(["tier", "family"]).reset_index(drop=True)
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "nn_by_family.csv", index=False)

    print(f"\n=== per-family guard (c) NN distance + tier "
          f"({args.source}/{args.strategy}, near_dup_grid={args.near_dup_grid}) ===\n")
    print(df.to_string(index=False))
    print(f"\nleak_warning (aggregate, attack-class p5 gate): {data.leakage.leak_warning}")
    print(f"nn_attack_p5: {data.leakage.nn_distance.get('attack', {}).get('percentiles', {}).get('p5')}")
    print(f"nn_benign_p5: {data.leakage.nn_distance.get('benign', {}).get('percentiles', {}).get('p5')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
