"""Exploratory pilot measurement (Phase B, step 4). EXPLORATORY — not a result.

For the honeypot-bound mimic flows, measure how close they land to the lab's own
benign flows, using the SAME normalisation and distance code as the paper's guard
(c): :class:`dloop.features.normalize.Normalizer` (log1p + IQR) and
:class:`dloop.adversary.mimicry.FidelityMeter` (per-feature RMS nearest-neighbour
distance in normalised space). Also computes the twin fraction at delta=0.0015 —
the same tail statistic as experiments/phase0_twin_fraction.py — and the attacker's
cost per mimic flow (connections, packets, bytes, wall-clock).

The paper's scale to compare against: realized median NN ~0.011 at copy fidelity.

Input is label.py's output (canonical features + true_intent + policy_label).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.adversary.mimicry import FidelityMeter
from dloop.features import schema
from dloop.features.normalize import fit_normalizer

TWIN_DELTA = 0.0015  # same delta as experiments/phase0_twin_fraction.py


def measure(labelled: pd.DataFrame, gt: pd.DataFrame | None,
            features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> dict:
    benign = labelled[labelled["true_intent"] == "benign"]
    mimic = labelled[(labelled["true_intent"] == "poison")
                     & (labelled["policy_label"] == 1)]
    out: dict = {"exploratory": True, "n_benign_ref": int(len(benign)),
                 "n_mimic": int(len(mimic)), "twin_delta": TWIN_DELTA}
    if benign.empty or mimic.empty:
        out["note"] = "need both benign reference flows and honeypot-bound mimic flows"
        return out

    # Normalise on the benign reference, exactly as guard (c) normalises before the
    # NN query. Distances come out in per-feature RMS (IQR) units.
    normalizer = fit_normalizer(benign, features)
    fm = FidelityMeter(normalizer.transform(benign[list(features)]), normalizer)
    rng = np.random.default_rng(0)
    dist = fm.distances(mimic[list(features)].to_numpy(), max_rows=len(mimic), rng=rng)
    out["nn_distance"] = {
        "median": float(np.median(dist)),
        "p5": float(np.percentile(dist, 5)),
        "p50": float(np.percentile(dist, 50)),
        "p95": float(np.percentile(dist, 95)),
        "min": float(np.min(dist)),
    }
    out["twin_fraction"] = float((dist <= TWIN_DELTA).mean())
    out["paper_reference_median"] = 0.011

    # Reference-density floor: how far genuine benign flows sit from their OWN
    # nearest benign neighbour (leave-one-out). With a small benign reference this
    # floor is well above the paper's dense-reference scale, so the mimic's NN
    # distance is only interpretable RELATIVE to this floor, not against 0.011.
    from sklearn.neighbors import NearestNeighbors
    ref_z = normalizer.transform(benign[list(features)])
    if len(ref_z) > 2:
        nn = NearestNeighbors(n_neighbors=2).fit(ref_z)
        dd, _ = nn.kneighbors(ref_z)
        loo = dd[:, 1] / np.sqrt(ref_z.shape[1])  # drop self (col 0)
        out["benign_loo_floor"] = {"median": float(np.median(loo)),
                                   "p5": float(np.percentile(loo, 5)),
                                   "n": int(len(loo))}
        out["mimic_over_benign_floor"] = float(np.median(dist) / np.median(loo))

    # Cost per mimic flow from the flow records themselves.
    pkts = (mimic["fwd_packets"].astype(float) + mimic["bwd_packets"].astype(float)).sum()
    byts = (mimic["fwd_bytes"].astype(float) + mimic["bwd_bytes"].astype(float)).sum()
    n = len(mimic)
    out["cost_per_flow"] = {"packets": float(pkts / n), "bytes": float(byts / n)}
    out["cost_total"] = {"flows": int(n), "packets": float(pkts), "bytes": float(byts)}
    if gt is not None and not gt.empty:
        m = gt[gt["intent"] == "poison"]
        if not m.empty:
            wall = float((m["t_end"] - m["t_start"]).sum())
            out["cost_total"]["connections"] = int(len(m))
            out["cost_total"]["wall_clock_s"] = round(wall, 2)
            out["cost_per_flow"]["wall_clock_s"] = round(wall / n, 4)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labelled", type=Path, required=True)
    ap.add_argument("--ground-truth", type=Path, nargs="*", default=[])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    labelled = pd.read_csv(args.labelled, low_memory=False)
    gt = None
    if args.ground_truth:
        from label import parse_ground_truth
        gt = parse_ground_truth(list(args.ground_truth))
    res = measure(labelled, gt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
