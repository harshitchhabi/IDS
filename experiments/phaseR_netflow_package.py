"""Zip a NetFlow v2 subsample for the IDS-data repo, under a per-file size limit
(Phase R item R3, DECISIONS.md §31.7).

``<stem>.zip`` holding ``<stem>.csv`` if that fits under ``--max-mb``; otherwise the
CSV is split into contiguous row ranges, ``<stem>.part01.csv``, ``part02``, ... (each
with the header, rows in original order), each zipped on its own as
``<stem>.partNN.zip``. The part count starts at the smallest that the whole-file zip
size suggests and grows until every zip fits. Streams in chunks; the loader
(:func:`dloop.sim.netflow_v2.files_for`) reads the parts back in name order.

    python -m experiments.phaseR_netflow_package data/netflow-v2/NF-ToN-IoT-v2.csv --out ../IDS-data/netflow-v2
"""

from __future__ import annotations

import argparse
import json
import math
import zipfile
from pathlib import Path

import pandas as pd

CHUNK = 500_000


def _zip(csv: Path, dest: Path) -> int:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(csv, arcname=csv.name)
    return dest.stat().st_size


def _count_rows(csv: Path, chunksize: int) -> int:
    return sum(len(c) for c in pd.read_csv(csv, usecols=[0], chunksize=chunksize))


def _write_parts(csv: Path, work: Path, n_parts: int, n_rows: int, chunksize: int) -> list[Path]:
    per = math.ceil(n_rows / n_parts)
    parts = [work / f"{csv.stem}.part{i + 1:02d}.csv" for i in range(n_parts)]
    for p in parts:
        p.unlink(missing_ok=True)
    written = [0] * n_parts
    row = 0
    for chunk in pd.read_csv(csv, chunksize=chunksize, dtype=str, keep_default_na=False):
        start = 0
        while start < len(chunk):
            i = min(row // per, n_parts - 1)
            take = min(len(chunk) - start, per * (i + 1) - row) if i < n_parts - 1 else len(chunk) - start
            piece = chunk.iloc[start:start + take]
            piece.to_csv(parts[i], mode="a", header=written[i] == 0, index=False)
            written[i] += len(piece)
            start += take
            row += take
    return [p for p, w in zip(parts, written) if w]


def package(csv: Path, out: Path, *, max_mb: float = 95.0, chunksize: int = CHUNK) -> dict:
    """Write the zip(s) into ``out`` and return a record of what was written."""
    out.mkdir(parents=True, exist_ok=True)
    limit = int(max_mb * 1024 * 1024)
    whole = out / f"{csv.stem}.zip"
    size = _zip(csv, whole)
    if size <= limit:
        return {"source": csv.name, "split": False, "rows": _count_rows(csv, chunksize),
                "zips": {whole.name: size}}
    whole.unlink()
    n_rows = _count_rows(csv, chunksize)
    n_parts = math.ceil(size / (0.9 * limit))
    work = out / f".{csv.stem}.parts"
    work.mkdir(exist_ok=True)
    while True:
        parts = _write_parts(csv, work, n_parts, n_rows, chunksize)
        zips = {}
        for p in parts:
            zips[f"{p.stem}.zip"] = _zip(p, out / f"{p.stem}.zip")
        if max(zips.values()) <= limit:
            break
        for name in zips:
            (out / name).unlink()
        n_parts += 1
    rows_per_part = {p.name: _count_rows(p, chunksize) for p in parts}
    for p in parts:
        p.unlink()
    work.rmdir()
    if sum(rows_per_part.values()) != n_rows:
        raise AssertionError("parts lost or duplicated rows")
    return {"source": csv.name, "split": True, "rows": n_rows, "rows_per_part": rows_per_part,
            "zips": zips}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-mb", type=float, default=95.0)
    args = ap.parse_args(argv)
    print(json.dumps(package(args.csv, args.out, max_mb=args.max_mb), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
