"""Join extracted flows with the lab's ground-truth logs (Phase B, docs/phaseB).

Emits, for every flow, *both* labels the research cares about:

  * ``policy_label`` — what the deception loop would stamp: 1 (malicious) if the
    flow's destination is a honeypot, else 0. This is the public auto-label policy;
    it needs nothing but the destination.
  * ``true_intent`` — what the traffic actually was (``benign`` / ``poison`` /
    ``attack`` / ``unknown``), taken from the generator that produced it.

The gap between the two columns is the whole point: mimic flows carry
``true_intent="poison"`` yet ``policy_label=1``, because the honest policy cannot
see intent.

Flow features are mapped onto the canonical schema with the SAME mapping the
reprocessed-CICIDS2017 loader uses (``dloop.features.schema.CICIDS_FIXED_COLUMN_MAP``),
because Engelen's fixed CICFlowMeter produced both this lab's CSVs and that release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Import the canonical schema from the installed dloop package.
from dloop.features import schema

HONEYPOT_IPS = ("172.28.0.20", "172.28.0.21")
# Extractor timestamps are flow-start wall-clock; allow a small slack each side of
# a ground-truth session window to absorb clock skew and flow-assembly lag.
MATCH_SLACK_S = 3.0

# Extractor column names (Engelen fixed CICFlowMeter) for the join keys.
F_SRC, F_DST, F_DPORT, F_TS = "Src IP", "Dst IP", "Dst Port", "Timestamp"


def parse_ground_truth(paths: list[Path]) -> pd.DataFrame:
    """Load ground-truth JSONL files into a frame with one row per session."""
    rows: list[dict] = []
    for p in paths:
        if not p.is_file():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        return pd.DataFrame(columns=["src", "dst", "dst_port", "t_start", "t_end",
                                     "intent", "kind"])
    df = pd.DataFrame(rows)
    df["dst_port"] = df["dst_port"].astype(int)
    return df


def policy_label(dst_ip: object, honeypots: tuple[str, ...] = HONEYPOT_IPS) -> int:
    """The loop's auto-label: 1 if the destination is a honeypot, else 0."""
    return 1 if str(dst_ip) in honeypots else 0


def _flow_ts_seconds(ts: pd.Series) -> pd.Series:
    """Extractor Timestamp -> unix seconds (epoch float). The fixed CICFlowMeter
    writes 'YYYY-MM-DD HH:MM:SS.ffffff'; ground truth is epoch float."""
    parsed = pd.to_datetime(ts, errors="coerce").to_numpy("datetime64[ns]")
    # Treat the naive extractor timestamp as UTC and convert to epoch seconds via
    # numpy (NaT -> NaN), so the result is machine-timezone-independent.
    secs = (parsed - np.datetime64("1970-01-01T00:00:00", "ns")) / np.timedelta64(1, "s")
    return pd.Series(secs, index=getattr(ts, "index", None))


def match_intent(flow: pd.Series, gt: pd.DataFrame, slack: float = MATCH_SLACK_S) -> str:
    """True intent of one flow: the ground-truth session with the same
    (src, dst, dst_port) whose [t_start, t_end] window contains the flow start
    (within *slack*). Nearest window centre wins ties. ``unknown`` if none —
    background traffic (ARP, retransmit-only flows) that no generator logged."""
    if gt.empty:
        return "unknown"
    cand = gt[(gt["src"] == flow[F_SRC]) & (gt["dst"] == flow[F_DST])
              & (gt["dst_port"] == int(flow[F_DPORT]))]
    if cand.empty:
        return "unknown"
    t = flow["_ts_s"]
    if pd.isna(t):
        # No usable timestamp: fall back to the only intent present, else unknown.
        intents = cand["intent"].unique()
        return str(intents[0]) if len(intents) == 1 else "unknown"
    within = cand[(cand["t_start"] - slack <= t) & (t <= cand["t_end"] + slack)]
    if within.empty:
        return "unknown"
    centre = (within["t_start"] + within["t_end"]) / 2.0
    return str(within.loc[(centre - t).abs().idxmin(), "intent"])


def map_to_canonical(flows: pd.DataFrame,
                     features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> pd.DataFrame:
    """Rename extractor feature columns onto canonical names (fixed-CICIDS map),
    keeping only the requested canonical features. Raises if any is absent."""
    stripped = {c: str(c).strip() for c in flows.columns}
    df = flows.rename(columns=stripped).rename(columns=schema.CICIDS_FIXED_COLUMN_MAP)
    missing = [f for f in features if f not in df.columns]
    if missing:
        raise KeyError(f"extractor output is missing mapped features: {missing}")
    return df[list(features)].copy()


def label_flows(flows: pd.DataFrame, gt: pd.DataFrame, *,
                honeypots: tuple[str, ...] = HONEYPOT_IPS,
                features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> pd.DataFrame:
    """Full pipeline: canonical features + policy_label + true_intent, one row per flow."""
    flows = flows.rename(columns={c: str(c).strip() for c in flows.columns})
    out = map_to_canonical(flows, features)
    flows = flows.assign(_ts_s=_flow_ts_seconds(flows[F_TS]))
    out["policy_label"] = [policy_label(d, honeypots) for d in flows[F_DST]]
    out["true_intent"] = [match_intent(r, gt) for _, r in flows.iterrows()]
    out["dst_ip"] = flows[F_DST].to_numpy()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--flows", type=Path, required=True, help="extracted flows CSV")
    ap.add_argument("--ground-truth", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    flows = pd.read_csv(args.flows, low_memory=False)
    gt = parse_ground_truth(list(args.ground_truth))
    labelled = label_flows(flows, gt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    labelled.to_csv(args.out, index=False)
    counts = labelled.groupby(["true_intent", "policy_label"]).size().to_dict()
    print(f"wrote {args.out}: {len(labelled)} flows; (true_intent, policy_label) -> {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
