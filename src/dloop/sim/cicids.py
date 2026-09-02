"""CICIDS2017 CSV loader (Phase 0 offline data source).

Reads the eight ``MachineLearningCVE`` day-CSVs into raw per-day frames. All
cleaning — whitespace, NaN/Inf, duplicates — is deferred to
:mod:`dloop.features.cleaning`; this module only reads bytes and tags the
capture day so the partition can split temporally.

Nothing here is required to run: :mod:`dloop.sim.synthetic` is the fallback and
the whole pipeline works without these files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dloop.features import schema
from dloop.logging_config import get_logger

log = get_logger("sim.cicids")

DEFAULT_ROOT = Path("data/cicids2017")

# Canonical CICIDS2017 release filenames -> capture day. Several days are split
# across two capture sessions (morning/afternoon); both map to the same day so
# the temporal partition stays clean.
DAY_FILES: dict[str, str] = {
    "Monday-WorkingHours.pcap_ISCX.csv": "monday",
    "Tuesday-WorkingHours.pcap_ISCX.csv": "tuesday",
    "Wednesday-workingHours.pcap_ISCX.csv": "wednesday",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv": "thursday",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv": "thursday",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv": "friday",
    "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv": "friday",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv": "friday",
}


def is_available(root: Path | str = DEFAULT_ROOT) -> bool:
    """True if at least one known CICIDS2017 day-CSV is present under *root*."""
    root = Path(root)
    return any((root / name).exists() for name in DAY_FILES)


def load_raw_by_day(root: Path | str = DEFAULT_ROOT) -> dict[str, pd.DataFrame]:
    """Load present day-CSVs into ``{day: raw concatenated frame}``.

    Raw means: original columns (whitespace intact), a ``day`` column added, and
    the CICIDS label column renamed only to the schema's canonical label name so
    downstream code is dataset-agnostic. Rates such as ``Flow Bytes/s`` are read
    as-is (often object dtype with ``"Infinity"``); cleaning coerces them.
    """
    root = Path(root)
    present = [(name, day) for name, day in DAY_FILES.items() if (root / name).exists()]
    if not present:
        raise FileNotFoundError(
            f"no CICIDS2017 CSVs under {root}/ (expected e.g. {next(iter(DAY_FILES))})"
        )

    by_day: dict[str, list[pd.DataFrame]] = {}
    for name, day in present:
        path = root / name
        # low_memory=False: rate columns mix ints, floats and "Infinity".
        df = pd.read_csv(path, low_memory=False, skipinitialspace=False)
        df.columns = [str(c).strip() for c in df.columns]
        if "Label" in df.columns:
            df = df.rename(columns={"Label": schema.LABEL})
        df[schema.DAY] = day
        log.info("loaded CICIDS2017 file", file=name, day=day, rows=len(df),
                 columns=len(df.columns))
        by_day.setdefault(day, []).append(df)

    out = {day: pd.concat(frames, ignore_index=True) for day, frames in by_day.items()}
    log.info("CICIDS2017 load complete", days=sorted(out), rows_by_day={d: len(f) for d, f in out.items()})
    return out
