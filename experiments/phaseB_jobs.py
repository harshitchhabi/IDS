"""Phase B job-safety guards (DECISIONS §33/§34 follow-up).

Two failures from the B.4 run motivate this module:

1. A loop reused cached job CSVs produced from a *different* condition's npz
   (``phase0_loop`` skips any job whose output CSV already exists). Guard:
   :func:`run_dir` puts every Phase B loop's output under a directory that
   embeds the condition name **and** a hash of the npz it trains on, so jobs
   from one condition/dataset can never be read as another's.
2. An OOM-killed loop left a truncated job CSV that broke the stats read. Guard:
   :func:`validate_dir` checks every job CSV (parseable, expected columns, every
   round present for each threshold mode, uniform row width) and raises loudly on
   the first bad file, so stats never run on corrupt results.
"""
from __future__ import annotations

import glob
import hashlib
from pathlib import Path

import pandas as pd

# Columns every loop job CSV must carry (a stable subset of the schema).
REQUIRED_COLUMNS = (
    "scenario", "model", "seed", "target_poison_ratio", "round", "threshold_mode",
    "threshold", "fpr", "tpr",
)


def npz_hash(npz_path: str | Path, length: int = 12) -> str:
    """Short hex hash of the npz file bytes — identifies the training data."""
    h = hashlib.sha256()
    with open(npz_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:length]


def run_dir(base: str | Path, condition: str, npz_path: str | Path) -> Path:
    """`<base>/<condition>__npz<hash>` — distinct per condition AND per dataset,
    so a cached job from one can never be reused for another."""
    return Path(base) / f"{condition}__npz{npz_hash(npz_path)}"


def validate_job_csv(path: str | Path, min_rounds: int = 20) -> tuple[bool, str]:
    """(ok, reason). A job CSV is valid iff it parses with a uniform row width,
    carries REQUIRED_COLUMNS, and — for every (threshold_mode) present — has every
    round 0..min_rounds."""
    try:
        df = pd.read_csv(path)
    except Exception as e:  # truncated / malformed -> pandas raises
        return False, f"unparseable: {str(e)[:60]}"
    if df.empty:
        return False, "empty"
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return False, f"missing columns {missing}"
    for mode, g in df.groupby("threshold_mode"):
        rounds = set(int(r) for r in g["round"].unique())
        need = set(range(0, min_rounds + 1))
        if not need.issubset(rounds):
            return False, f"threshold_mode={mode} missing rounds {sorted(need - rounds)[:5]}"
    return True, "ok"


def validate_dir(job_dir: str | Path, min_rounds: int = 20) -> int:
    """Validate every CSV in *job_dir*; raise ValueError listing bad files.
    Returns the number of valid files."""
    files = sorted(glob.glob(str(Path(job_dir) / "*.csv")))
    if not files:
        raise ValueError(f"no job CSVs under {job_dir}")
    bad = []
    for f in files:
        ok, reason = validate_job_csv(f, min_rounds)
        if not ok:
            bad.append(f"{Path(f).name}: {reason}")
    if bad:
        raise ValueError(f"{len(bad)} invalid job CSV(s) under {job_dir}:\n  " + "\n  ".join(bad))
    return len(files)


def resolve_jobs_dir(root: str | Path, condition: str) -> Path:
    """The condition's jobs dir: the **newest** by mtime among the exact
    ``<root>/<condition>/jobs`` (B.4 layout) and the hashed
    ``<root>/<condition>__npz*/jobs`` (guarded layout) — so a fresh re-run under a
    new npz is never shadowed by a stale plain dir."""
    root = Path(root)
    cands = []
    exact = root / condition / "jobs"
    if exact.is_dir():
        cands.append(exact)
    cands += list(root.glob(f"{condition}__npz*/jobs"))
    if not cands:
        raise ValueError(f"no jobs dir for condition {condition!r} under {root}")
    return max(cands, key=lambda p: p.stat().st_mtime)
