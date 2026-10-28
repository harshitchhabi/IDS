"""Stratified, order-preserving subsample of a UQ NetFlow v2 CSV (Phase R item R3,
DECISIONS.md §31). Run on the full download before anything else touches it.

Rule (pre-registered): every attack family keeps all its rows up to ``--attack-cap``
(200,000); benign keeps ``--benign-cap`` rows; the rows kept within each class are a
uniform draw without replacement (``default_rng(--seed)``, one draw per class in
sorted class order) and are written in their original file order, because file order
is the time axis the within-day partition splits on (NetFlow v2 has no timestamp).
Two streaming passes, so an 18M-row file never sits in memory. Writes
``<out>/<stem>.csv`` and ``<out>/<stem>.sampling.json`` (source sha256, per-class
counts before and after, caps, seed).

    python -m experiments.phaseR_netflow_subsample path/to/NF-ToN-IoT-v2.csv --out data/netflow-v2
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema

CHUNK = 1_000_000


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _classes(chunk: pd.DataFrame) -> pd.Series:
    return chunk[schema.NETFLOW_V2_ATTACK_COLUMN].astype(str).map(schema.normalize_label)


def subsample(src: Path, out_dir: Path, *, attack_cap: int, benign_cap: int, seed: int,
              chunksize: int = CHUNK) -> dict:
    counts: dict[str, int] = {}
    for chunk in pd.read_csv(src, usecols=[schema.NETFLOW_V2_ATTACK_COLUMN], chunksize=chunksize):
        for c, n in _classes(chunk).value_counts().items():
            counts[c] = counts.get(c, 0) + int(n)

    rng = np.random.default_rng(seed)
    keep: dict[str, np.ndarray] = {}
    for c in sorted(counts):
        cap = benign_cap if c == schema.BENIGN_LABEL else attack_cap
        k = min(cap, counts[c])
        keep[c] = np.sort(rng.choice(counts[c], k, replace=False)) if k < counts[c] else np.arange(counts[c])

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / src.name
    seen = {c: 0 for c in counts}
    kept = {c: 0 for c in counts}
    header = True
    for chunk in pd.read_csv(src, chunksize=chunksize, low_memory=False):
        cls = _classes(chunk).to_numpy()
        mask = np.zeros(len(chunk), dtype=bool)
        for c in np.unique(cls):
            pos = np.flatnonzero(cls == c)
            ordinal = seen[c] + np.arange(len(pos))      # this class's running row index
            sel = np.isin(ordinal, keep[c], assume_unique=True)
            mask[pos[sel]] = True
            seen[c] += len(pos)
            kept[c] += int(sel.sum())
        chunk.loc[mask].to_csv(out_csv, mode="w" if header else "a", header=header, index=False)
        header = False

    record = {"source_file": src.name, "source_sha256": _sha256(src), "seed": seed,
              "attack_cap_per_family": attack_cap, "benign_cap": benign_cap,
              "rows_before": counts, "rows_after": kept,
              "total_before": int(sum(counts.values())), "total_after": int(sum(kept.values())),
              "order": "original file order preserved"}
    (out_dir / f"{src.stem}.sampling.json").write_text(json.dumps(record, indent=2))
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/netflow-v2"))
    ap.add_argument("--attack-cap", type=int, default=200_000)
    ap.add_argument("--benign-cap", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=20261028)
    args = ap.parse_args(argv)
    rec = subsample(args.src, args.out, attack_cap=args.attack_cap, benign_cap=args.benign_cap,
                    seed=args.seed)
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
