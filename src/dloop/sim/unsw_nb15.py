"""UNSW-NB15 loader (Phase A item B, DECISIONS.md §29.B).

Mirrors :mod:`dloop.sim.cicids`: reads the four part CSVs, maps columns onto the
canonical schema, tags the capture session, and leaves numeric cleaning to
:mod:`dloop.features.cleaning`.

The part CSVs have no header row. Column names come from the official
dictionary ``NUSW-NB15_features.csv`` (one row per column, in file order),
matched ignoring case and whitespace, never assumed from documentation.

UNSW-NB15 is Argus/Bro-derived, not CICFlowMeter, so only 9 of the 24 canonical
features have a direct per-flow analogue (:data:`schema.UNSW_FEATURES`); the run
uses exactly those. Durations and inter-packet times are converted into
CICFlowMeter's microseconds so attacker-cost metadata keeps one unit.

Capture "day" is the capture session: UNSW-NB15 was recorded in two sessions
(22-23 Jan 2015 and 18 Feb 2015, Sydney time), each split along its own timeline
by the within-day temporal partition. The first session crosses midnight, so it
is tagged by session rather than calendar date.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dloop.features import schema
from dloop.logging_config import get_logger

log = get_logger("sim.unsw_nb15")

DEFAULT_ROOT = Path("data/unsw-nb15")
PART_FILES: tuple[str, ...] = tuple(f"UNSW-NB15_{i}.csv" for i in range(1, 5))
DICTIONARY_FILE = "NUSW-NB15_features.csv"

# capture sessions, split at a date between them (unix seconds, UTC)
_SESSION_SPLIT = pd.Timestamp("2015-02-01", tz="UTC")
SESSIONS = ("jan22", "feb18")


def is_available(root: Path | str = DEFAULT_ROOT) -> bool:
    root = Path(root)
    return (root / DICTIONARY_FILE).exists() and any((root / f).exists() for f in PART_FILES)


def column_names(root: Path | str = DEFAULT_ROOT) -> list[str]:
    """Normalized column names, in file order, from the official dictionary."""
    d = pd.read_csv(Path(root) / DICTIONARY_FILE, encoding="latin1")
    d.columns = [schema.normalize_column_name(c) for c in d.columns]
    d = d.sort_values("no.")
    names = [schema.normalize_column_name(n) for n in d["name"]]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate column names in {DICTIONARY_FILE}: {names}")
    return names


def load_raw_by_day(root: Path | str = DEFAULT_ROOT) -> dict[str, pd.DataFrame]:
    """Load present part files into ``{session: frame}`` with canonical columns
    (only :data:`schema.UNSW_FEATURES`), ``label`` and ``timestamp``."""
    root = Path(root)
    if not (root / DICTIONARY_FILE).exists():
        raise FileNotFoundError(f"{root / DICTIONARY_FILE} missing: UNSW-NB15 columns are unknown "
                                "without it and are not guessed")
    names = column_names(root)
    needed = [*schema.UNSW_COLUMN_MAP, schema.UNSW_LABEL_COLUMN,
              schema.UNSW_CATEGORY_COLUMN, schema.UNSW_TIMESTAMP_COLUMN]
    missing = [c for c in needed if c not in names]
    if missing:
        raise ValueError(f"dictionary lacks expected columns: {missing}")

    present = [f for f in PART_FILES if (root / f).exists()]
    if not present:
        raise FileNotFoundError(f"no UNSW-NB15 part CSVs under {root}/")
    parts = []
    for f in present:
        df = pd.read_csv(root / f, header=None, names=names, usecols=needed,
                         encoding="utf-8-sig", low_memory=False)
        log.info("loaded UNSW-NB15 file", file=f, rows=len(df))
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)

    out = pd.DataFrame(index=df.index)
    for raw, (canon, mult) in schema.UNSW_COLUMN_MAP.items():
        out[canon] = pd.to_numeric(df[raw], errors="coerce") * mult
    out = out[list(schema.UNSW_FEATURES)]

    cat = df[schema.UNSW_CATEGORY_COLUMN].fillna("").astype(str).str.strip()
    cat = cat.replace(schema.UNSW_CATEGORY_ALIASES)
    is_attack = pd.to_numeric(df[schema.UNSW_LABEL_COLUMN], errors="coerce")
    # A row whose binary label and category disagree cannot be labelled without
    # guessing which of the two is wrong; drop and count it.
    inconsistent = ((is_attack == 1) & (cat == "")) | ((is_attack == 0) & (cat != "")) | is_attack.isna()
    out[schema.LABEL] = cat.where(is_attack == 1, schema.BENIGN_LABEL)
    ts = pd.to_datetime(pd.to_numeric(df[schema.UNSW_TIMESTAMP_COLUMN], errors="coerce"),
                        unit="s", utc=True)
    out[schema.TIMESTAMP] = ts.dt.tz_localize(None)
    out[schema.DAY] = SESSIONS[0]
    out.loc[ts >= _SESSION_SPLIT, schema.DAY] = SESSIONS[1]
    if inconsistent.any():
        log.info("dropping rows whose label and attack_cat disagree", rows=int(inconsistent.sum()))
    out = out.loc[~inconsistent]

    by_day = {str(s): g.reset_index(drop=True)
              for s, g in out.groupby(schema.DAY, sort=True)}
    log.info("UNSW-NB15 load complete", sessions=sorted(by_day),
             rows_by_session={d: len(f) for d, f in by_day.items()},
             label_and_category_disagree=int(inconsistent.sum()),
             families=out[schema.LABEL].value_counts().to_dict())
    return by_day
