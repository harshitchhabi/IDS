"""B.3 cost (DECISIONS.md §32.3).

Per poison flow accepted into training: packets, bytes, connections and
wall-clock (from the ground-truth logs joined to the admitted mimic flows). And
the time to reach a 20%% honeypot share of the training set at one retrain every
N = 10 minutes, from the measured mimic flow-rate.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.loop.data import LoopData

N_MINUTES = 10          # retrain cadence (stated in §32.3)
TARGET_SHARE = 0.20
PRIMARY_KINDS = {"profile": "mimic_profile", "oracle": "mimic_oracle", "replay": "mimic_replay"}


def cost(labelled: pd.DataFrame, gt: pd.DataFrame, ld: LoopData, strategy: str) -> dict:
    kind = PRIMARY_KINDS[strategy]
    mim = labelled[(labelled["true_intent"] == "poison")]
    # honeypot-bound mimic flows of the primary strategy, if true_kind present
    if "true_kind" in mim.columns:
        mim = mim[mim["true_kind"] == kind]
    n_flows = len(mim)
    pkts = (mim["fwd_packets"].astype(float) + mim["bwd_packets"].astype(float)).sum()
    byts = (mim["fwd_bytes"].astype(float) + mim["bwd_bytes"].astype(float)).sum()

    gm = gt[(gt["intent"] == "poison") & (gt["kind"] == kind)] if not gt.empty else gt
    conns = int(len(gm))
    span_min = float((gm["t_end"].max() - gm["t_start"].min()) / 60.0) if conns else float("nan")
    wall = float((gm["t_end"] - gm["t_start"]).sum()) if conns else float("nan")

    per = {"packets": pkts / n_flows, "bytes": byts / n_flows,
           "connections": conns / n_flows if n_flows else float("nan"),
           "wall_clock_s": wall / n_flows if n_flows and not math.isnan(wall) else float("nan")}

    # time to 20% share. honeypot share H/(S+H)=0.2 -> H = 0.25*S.
    S = int(len(ld.seed_x))
    H_needed = TARGET_SHARE / (1 - TARGET_SHARE) * S
    flows_per_min = n_flows / span_min if span_min and not math.isnan(span_min) and span_min > 0 else float("nan")
    flows_per_round = flows_per_min * N_MINUTES if not math.isnan(flows_per_min) else float("nan")
    rounds = math.ceil(H_needed / flows_per_round) if flows_per_round and not math.isnan(flows_per_round) and flows_per_round > 0 else None
    return {"strategy": strategy, "n_mimic_flows": n_flows, "total_packets": float(pkts),
            "total_bytes": float(byts), "connections": conns, "capture_span_min": span_min,
            "per_flow_packets": per["packets"], "per_flow_bytes": per["bytes"],
            "per_flow_connections": per["connections"], "per_flow_wall_clock_s": per["wall_clock_s"],
            "seed_train_rows": S, "honeypot_rows_for_20pct": H_needed,
            "mimic_flows_per_min": flows_per_min, "retrain_every_min": N_MINUTES,
            "rounds_to_20pct": rounds,
            "wall_clock_to_20pct_min": rounds * N_MINUTES if rounds else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labelled", type=Path, default=Path("lab/data/lab_labelled.csv"))
    ap.add_argument("--ground-truth", type=Path, nargs="+",
                    default=[Path("lab/data/logs/ground_truth/attacker.jsonl")])
    ap.add_argument("--npz", type=Path, default=Path("data/loop/lab.npz"))
    ap.add_argument("--strategy", default="oracle")
    ap.add_argument("--out", type=Path, default=Path("results/phaseB/b3_cost.csv"))
    args = ap.parse_args(argv)

    import sys
    sys.path.insert(0, str(Path("lab/tools").resolve()))
    from label import parse_ground_truth  # noqa: E402

    labelled = pd.read_csv(args.labelled, low_memory=False)
    gt = parse_ground_truth(list(args.ground_truth))
    ld = LoopData.load(args.npz)
    rec = cost(labelled, gt, ld, args.strategy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([rec]).to_csv(args.out, index=False)
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
