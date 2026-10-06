"""Reprocessed CICIDS2017 loader (Engelen et al., CNS2022 "improved" release).

Phase A item B (DECISIONS.md §29.B). Mirrors :mod:`dloop.sim.cicids`: reads the
five day-CSVs, renames columns onto the canonical schema, tags the capture day,
and leaves all numeric cleaning (NaN/Inf, negatives, duplicates) to
:mod:`dloop.features.cleaning` so both releases go through the identical pipeline.

Two things differ from the original release and are handled here, not in
cleaning, because they are properties of this release's labelling, not of flow
records in general:

* **Real timestamps.** This release keeps ``Timestamp`` (microsecond resolution),
  so the within-day temporal split and burst segmentation run on real seconds
  rather than the synthesized 1-row-=-1-s order the original release forces
  (DECISIONS.md §14 erratum).
* **"<family> - Attempted" rows are dropped.** They are attack-tool flows that
  carried no malicious payload. Relabelling them BENIGN (Engelen et al.'s own
  suggestion) would put attack-looking rows labelled benign next to genuine
  attack rows -- the same benign/malicious label conflict the A1 mechanism
  measures -- and would contaminate the control arm. Keeping them as attack
  families would teach the detector that payload-less handshakes are attacks.
  Dropping is the only choice that adds no label conflict of its own. Every
  dropped row is counted per family and logged.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dloop.features import schema
from dloop.logging_config import get_logger

log = get_logger("sim.cicids_fixed")

DEFAULT_ROOT = Path("data/cicids2017-fixed")

# One CSV per capture day in this release (the original splits several days into
# morning/afternoon files).
DAY_FILES: dict[str, str] = {
    "monday.csv": "monday",
    "tuesday.csv": "tuesday",
    "wednesday.csv": "wednesday",
    "thursday.csv": "thursday",
    "friday.csv": "friday",
}

_USECOLS = [*schema.CICIDS_FIXED_COLUMN_MAP, schema.CICIDS_FIXED_LABEL_COLUMN,
            schema.CICIDS_FIXED_TIMESTAMP_COLUMN]


def is_available(root: Path | str = DEFAULT_ROOT) -> bool:
    """True if at least one day-CSV of this release is present under *root*."""
    root = Path(root)
    return any((root / name).exists() for name in DAY_FILES)


def load_raw_by_day(root: Path | str = DEFAULT_ROOT) -> dict[str, pd.DataFrame]:
    """Load present day-CSVs into ``{day: frame}`` with canonical column names.

    Only the mapped feature, label and timestamp columns are read (the release
    carries 91 columns, including IPs and ports that never enter the schema).
    ``* - Attempted`` rows are dropped here, with per-day, per-label counts logged.
    """
    root = Path(root)
    present = [(name, day) for name, day in DAY_FILES.items() if (root / name).exists()]
    if not present:
        raise FileNotFoundError(
            f"no reprocessed CICIDS2017 CSVs under {root}/ (expected e.g. {next(iter(DAY_FILES))})"
        )

    rename = {**schema.CICIDS_FIXED_COLUMN_MAP,
              schema.CICIDS_FIXED_LABEL_COLUMN: schema.LABEL,
              schema.CICIDS_FIXED_TIMESTAMP_COLUMN: schema.TIMESTAMP}
    out: dict[str, pd.DataFrame] = {}
    attempted_total: dict[str, int] = {}
    for name, day in present:
        df = pd.read_csv(root / name, usecols=_USECOLS, low_memory=False,
                         encoding="utf-8", encoding_errors="replace")
        df = df.rename(columns=rename)
        labels = df[schema.LABEL].astype(str).str.strip()
        attempted = labels.str.endswith(schema.CICIDS_FIXED_ATTEMPTED_SUFFIX)
        dropped = {str(k): int(v) for k, v in labels[attempted].value_counts().items()}
        for k, v in dropped.items():
            attempted_total[k] = attempted_total.get(k, 0) + v
        df = df.loc[~attempted].reset_index(drop=True)
        df[schema.DAY] = day
        log.info("loaded reprocessed CICIDS2017 file", file=name, day=day, rows=len(df),
                 attempted_rows_dropped=int(attempted.sum()), attempted_by_label=dropped)
        out[day] = df

    log.info("reprocessed CICIDS2017 load complete", days=sorted(out),
             rows_by_day={d: len(f) for d, f in out.items()},
             attempted_rows_dropped=sum(attempted_total.values()),
             attempted_by_label=attempted_total)
    return out
