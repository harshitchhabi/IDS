"""Extractor validation (Phase B, step 3).

Extract a slice of the CICIDS2017 raw pcap with this lab's Dockerised fixed
CICFlowMeter, then compare the result, flow by flow, against the matching rows of
Engelen's published reprocessed CSV (IDS-data/cicids2017-fixed). Both came from the
same tool, so agreement should be near-exact; a low match rate means this lab's
extractor build or invocation differs from the one that made the release, and the
Phase B pilot cannot be compared to the paper's feature-space numbers.

Join key: (Flow ID, Timestamp) — the fixed CICFlowMeter emits both, and together
they identify a flow. For each canonical feature, report the fraction of joined
flows whose values agree within a relative tolerance.

    python lab/tools/validate_extractor.py --lab <lab_extracted.csv> \
        --published ../IDS-data/cicids2017-fixed/monday.csv --out results/phaseB/extractor_match.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema

KEY = ["Flow ID", "Timestamp"]
RTOL, ATOL = 1e-3, 1e-6


def _canon(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    return df.rename(columns=schema.CICIDS_FIXED_COLUMN_MAP)


def compare(lab: pd.DataFrame, published: pd.DataFrame,
            features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> pd.DataFrame:
    lab, published = _canon(lab), _canon(published)
    for df in (lab, published):
        for k in KEY:
            if k not in df.columns:
                raise KeyError(f"join key {k!r} missing from a CSV (columns: {list(df.columns)[:8]}...)")
    merged = lab.merge(published, on=KEY, suffixes=("_lab", "_pub"), how="inner")
    rows = []
    for f in features:
        a, b = f"{f}_lab", f"{f}_pub"
        if a not in merged or b not in merged:
            rows.append({"feature": f, "n": 0, "match_rate": float("nan"), "note": "absent"})
            continue
        x = pd.to_numeric(merged[a], errors="coerce").to_numpy()
        y = pd.to_numeric(merged[b], errors="coerce").to_numpy()
        ok = np.isclose(x, y, rtol=RTOL, atol=ATOL, equal_nan=True)
        rows.append({"feature": f, "n": int(len(ok)),
                     "match_rate": float(np.mean(ok)) if len(ok) else float("nan"),
                     "note": ""})
    out = pd.DataFrame(rows)
    out.attrs["n_joined"] = len(merged)
    out.attrs["n_lab"] = len(lab)
    out.attrs["n_published"] = len(published)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lab", type=Path, required=True)
    ap.add_argument("--published", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    lab = pd.read_csv(args.lab, low_memory=False)
    pub = pd.read_csv(args.published, low_memory=False)
    res = compare(lab, pub)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.out, index=False)
    print(f"joined {res.attrs['n_joined']} flows (lab {res.attrs['n_lab']}, "
          f"published {res.attrs['n_published']})")
    print(res.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
