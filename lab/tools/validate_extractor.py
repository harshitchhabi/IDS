"""Extractor validation (Phase B, docs/phaseB/extractor-validation.md).

Extract a slice of the CICIDS2017 raw pcap with this lab's Dockerised fixed
CICFlowMeter, then compare the result, flow by flow, against Engelen's published
reprocessed CSV (IDS-data/cicids2017-fixed). Both came from the same tool, so
agreement should be near-exact; a low match rate means this lab's extractor build
or invocation differs from the one that made the release.

**Matching.** A flow is identified by its 5-tuple (CICFlowMeter's ``Flow ID``,
i.e. ``srcip-dstip-srcport-dstport-proto``) and its start time. The published CSV
covers the whole capture day and its timestamps are in the dataset's local zone
(Halifax/ADT); a 30-minute slice extracted here is timestamped in the container's
zone (UTC). So we do NOT join on the raw timestamp. We:

  1. match candidate flows by ``Flow ID``;
  2. auto-detect the constant start-time offset between the two sides (the median
     of published-minus-lab start over Flow IDs unique on both sides) — this is
     the timezone/representation difference, reported, not tuned away;
  3. for each lab flow, accept the same-Flow-ID published flow whose
     offset-corrected start time is within ``--tolerance`` seconds (nearest wins).

For every canonical feature we then report the exact-match rate and, for the rest,
the median relative error.

    python lab/tools/validate_extractor.py --lab <lab_extracted.csv> \
        --published ../IDS-data/cicids2017-fixed/monday.csv \
        --out results/phaseB/extractor_match.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema

FLOW_ID, TS = "Flow ID", "Timestamp"
# Feature source columns needed from the published CSV, plus the match keys.
_PUB_USECOLS = [FLOW_ID, TS, *schema.CICIDS_FIXED_COLUMN_MAP]


def _canon(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    return df.rename(columns=schema.CICIDS_FIXED_COLUMN_MAP)


def _epoch(ts: pd.Series) -> np.ndarray:
    parsed = pd.to_datetime(ts, errors="coerce").to_numpy("datetime64[ns]")
    return (parsed - np.datetime64("1970-01-01T00:00:00", "ns")) / np.timedelta64(1, "s")


def detect_offset(lab: pd.DataFrame, pub: pd.DataFrame) -> float:
    """Median (published_start - lab_start) over Flow IDs unique on both sides."""
    lab_u = lab.drop_duplicates(FLOW_ID, keep=False).set_index(FLOW_ID)["_ts"]
    pub_u = pub.drop_duplicates(FLOW_ID, keep=False).set_index(FLOW_ID)["_ts"]
    common = lab_u.index.intersection(pub_u.index)
    if len(common) == 0:
        return 0.0
    return float(np.median(pub_u.loc[common].to_numpy() - lab_u.loc[common].to_numpy()))


def match(lab: pd.DataFrame, pub: pd.DataFrame, *, offset: float | None,
          tolerance: float) -> tuple[pd.DataFrame, dict]:
    """Return (merged lab/pub rows, diagnostics). Each lab flow is matched to at
    most one published flow (same Flow ID, nearest offset-corrected start)."""
    lab, pub = _canon(lab).copy(), _canon(pub).copy()
    lab["_ts"], pub["_ts"] = _epoch(lab[TS]), _epoch(pub[TS])
    if offset is None:
        offset = detect_offset(lab, pub)

    pub_by_id = {fid: g for fid, g in pub.groupby(FLOW_ID)}
    lab_idx, pub_idx = [], []
    for li, row in lab.iterrows():
        cand = pub_by_id.get(row[FLOW_ID])
        if cand is None:
            continue
        # offset = median(published - lab), so published - offset aligns to lab.
        dt = np.abs(cand["_ts"].to_numpy() - offset - row["_ts"])
        j = int(np.argmin(dt))
        if dt[j] <= tolerance:
            lab_idx.append(li)
            pub_idx.append(cand.index[j])
    merged = lab.loc[lab_idx].reset_index(drop=True).join(
        pub.loc[pub_idx].reset_index(drop=True), lsuffix="_lab", rsuffix="_pub")
    diag = {"offset_s": offset, "tolerance_s": tolerance,
            "n_lab": len(lab), "n_published": len(pub), "n_matched": len(merged),
            "match_share_of_lab": len(merged) / len(lab) if len(lab) else float("nan")}
    return merged, diag


def feature_agreement(merged: pd.DataFrame,
                      features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> pd.DataFrame:
    rows = []
    for f in features:
        a, b = f"{f}_lab", f"{f}_pub"
        if a not in merged or b not in merged or merged.empty:
            rows.append({"feature": f, "n": 0, "exact_match_rate": float("nan"),
                         "median_rel_err": float("nan")})
            continue
        x = pd.to_numeric(merged[a], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(merged[b], errors="coerce").to_numpy(dtype=float)
        exact = np.isclose(x, y, rtol=0, atol=0, equal_nan=True)
        denom = np.where(np.abs(y) > 0, np.abs(y), np.nan)
        rel = np.abs(x - y) / denom
        rel = rel[~np.isclose(x, y)]  # relative error only over the non-exact rows
        rows.append({"feature": f, "n": int(len(x)),
                     "exact_match_rate": float(np.mean(exact)),
                     "median_rel_err": float(np.nanmedian(rel)) if len(rel) and not np.all(np.isnan(rel)) else 0.0})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lab", type=Path, required=True)
    ap.add_argument("--published", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tolerance", type=float, default=2.0, help="start-time match window (s)")
    ap.add_argument("--offset", type=float, default=None,
                    help="published-minus-lab start offset (s); default: auto-detect")
    args = ap.parse_args(argv)

    lab = pd.read_csv(args.lab, low_memory=False)
    # Published CSV is the whole day; read only the columns we need to stay in RAM.
    pub = pd.read_csv(args.published, low_memory=False,
                      usecols=lambda c: str(c).strip() in _PUB_USECOLS)
    merged, diag = match(lab, pub, offset=args.offset, tolerance=args.tolerance)
    agree = feature_agreement(merged)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    agree.to_csv(args.out, index=False)

    print(f"lab flows: {diag['n_lab']}  published flows: {diag['n_published']}")
    print(f"detected offset: {diag['offset_s']:.1f} s  (= published - lab start)")
    print(f"matched: {diag['n_matched']} "
          f"({100 * diag['match_share_of_lab']:.1f}% of lab flows), tolerance {diag['tolerance_s']} s")
    print(agree.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
