"""Flow-record cleaning with a full accounting of everything dropped.

CLAUDE.md, Phase 0: "CICIDS2017 gotchas to handle explicitly: whitespace in
column names (the label column is literally ``' Label'``), NaN/Inf in
``Flow Bytes/s`` and ``Flow Packets/s``, duplicate rows, severe class imbalance.
Log everything dropped."

The same pipeline runs on synthetic data — the synthetic generator injects the
same classes of corruption on purpose so the drop report is exercised without
the real dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.logging_config import get_logger

log = get_logger("features.cleaning")


@dataclass
class CleaningReport:
    """Everything that happened during :func:`clean_flows`, for logging + tests."""

    source: str
    rows_in: int
    rows_out: int = 0
    renamed_columns: dict[str, str] = field(default_factory=dict)
    dropped_columns: list[str] = field(default_factory=list)
    inf_cells_replaced: dict[str, int] = field(default_factory=dict)
    rows_dropped_nan: int = 0
    nan_by_column: dict[str, int] = field(default_factory=dict)
    rows_dropped_negative: int = 0
    negative_by_column: dict[str, int] = field(default_factory=dict)
    rows_dropped_duplicate: int = 0
    duplicate_by_class: dict[str, int] = field(default_factory=dict)
    rows_dropped_bad_timestamp: int = 0
    synthesized_timestamps: bool = False
    class_counts_in: dict[str, int] = field(default_factory=dict)
    class_counts_out: dict[str, int] = field(default_factory=dict)

    @property
    def rows_dropped_total(self) -> int:
        return self.rows_in - self.rows_out

    @property
    def imbalance_ratio_out(self) -> float:
        """majority / minority over the binary target, ``inf`` if a class is empty."""
        if not self.class_counts_out:
            return float("nan")
        benign = self.class_counts_out.get(schema.BENIGN_LABEL, 0)
        attack = self.rows_out - benign
        lo, hi = sorted((benign, attack))
        return float("inf") if lo == 0 else hi / lo

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["rows_dropped_total"] = self.rows_dropped_total
        d["imbalance_ratio_out"] = self.imbalance_ratio_out
        return d


def _rename_to_canonical(df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    # Gotcha 1: whitespace in column names (" Label", " Flow Duration", ...).
    stripped = {c: str(c).strip() for c in df.columns}
    df = df.rename(columns=stripped)

    rename: dict[str, str] = {}
    for raw, canon in schema.CICIDS_COLUMN_MAP.items():
        if raw in df.columns:
            rename[raw] = canon
    if schema.CICIDS_LABEL_COLUMN.strip() in df.columns:
        rename[schema.CICIDS_LABEL_COLUMN.strip()] = schema.LABEL
    if schema.CICIDS_TIMESTAMP_COLUMN.strip() in df.columns:
        rename[schema.CICIDS_TIMESTAMP_COLUMN.strip()] = schema.TIMESTAMP
    df = df.rename(columns=rename)
    report.renamed_columns = {**stripped, **rename}

    missing = [c for c in schema.CANONICAL_FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"input is missing required feature columns: {missing}")
    if schema.LABEL not in df.columns:
        raise ValueError("input has no label column")

    keep = [*schema.CANONICAL_FEATURES, schema.LABEL]
    for meta in (schema.DAY, schema.TIMESTAMP):
        if meta in df.columns:
            keep.append(meta)
    report.dropped_columns = sorted(set(df.columns) - set(keep))
    if report.dropped_columns:
        log.info("dropping non-schema columns", columns=report.dropped_columns, source=report.source)
    return df[keep].copy()


def clean_flows(df: pd.DataFrame, *, source: str) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean raw flow records into the canonical schema.

    Steps, each accounted for in the returned :class:`CleaningReport`:

    1. strip column-name whitespace, map to canonical names, drop extra columns;
    2. coerce features to numeric, replace +-Inf with NaN (the rate-column gotcha);
    3. drop rows with any NaN feature (per-column breakdown recorded);
    4. drop rows with a physically impossible negative feature;
    5. drop exact duplicate rows;
    6. record class balance before and after.
    """
    report = CleaningReport(source=source, rows_in=len(df))
    df = _rename_to_canonical(df, report)

    df[schema.LABEL] = df[schema.LABEL].map(schema.normalize_label)
    report.class_counts_in = df[schema.LABEL].value_counts().to_dict()

    # Step 2: numeric coercion + Inf -> NaN. CICIDS2017 stores rates as strings
    # like "Infinity" / "" for zero-duration flows.
    feats = list(schema.CANONICAL_FEATURES)
    df[feats] = df[feats].apply(pd.to_numeric, errors="coerce")
    inf_mask = np.isinf(df[feats].to_numpy(dtype="float64", na_value=np.nan))
    if inf_mask.any():
        counts = inf_mask.sum(axis=0)
        report.inf_cells_replaced = {
            f: int(n) for f, n in zip(feats, counts, strict=True) if n
        }
        df[feats] = df[feats].replace([np.inf, -np.inf], np.nan)
        log.info("replaced non-finite cells with NaN", by_column=report.inf_cells_replaced,
                 source=source)

    # Step 3: NaN rows.
    nan_cells = df[feats].isna()
    nan_row_mask = nan_cells.any(axis=1)
    report.rows_dropped_nan = int(nan_row_mask.sum())
    report.nan_by_column = {
        f: int(n) for f, n in nan_cells.sum().items() if n
    }
    if report.rows_dropped_nan:
        log.info("dropping rows with NaN features", rows=report.rows_dropped_nan,
                 by_column=report.nan_by_column, source=source)
    df = df[~nan_row_mask]

    # Step 4: impossible negatives (negative Flow Duration is a known artifact).
    neg_cells = df[list(schema.NONNEGATIVE_FEATURES)] < 0
    neg_row_mask = neg_cells.any(axis=1)
    report.rows_dropped_negative = int(neg_row_mask.sum())
    report.negative_by_column = {f: int(n) for f, n in neg_cells.sum().items() if n}
    if report.rows_dropped_negative:
        log.info("dropping rows with negative features", rows=report.rows_dropped_negative,
                 by_column=report.negative_by_column, source=source)
    df = df[~neg_row_mask]

    # Step 5: exact duplicates (features + label, ignoring the day / timestamp
    # tags). Broken out per class — a burst-heavy attack family duplicating into
    # both honeypot_pool and trusted_eval is exactly the leakage the partition
    # guards defend against, so the counts need to be visible per class.
    dedup_cols = [*feats, schema.LABEL]
    dup_mask = df.duplicated(subset=dedup_cols, keep="first")
    report.rows_dropped_duplicate = int(dup_mask.sum())
    report.duplicate_by_class = {
        str(k): int(v) for k, v in df.loc[dup_mask, schema.LABEL].value_counts().items()
    }
    if report.rows_dropped_duplicate:
        log.info("dropping exact-duplicate rows", rows=report.rows_dropped_duplicate,
                 by_class=report.duplicate_by_class, source=source)
    df = df[~dup_mask].reset_index(drop=True)

    # Step 6: timestamps. Real CICIDS2017 carries " Timestamp" (mixed formats);
    # coerce and drop unparseable rows. Synthetic data supplies real datetimes.
    # With no timestamp column at all, synthesize a monotonic one from row order
    # so the within-day temporal split still has something to sort on.
    if schema.TIMESTAMP in df.columns:
        ts = pd.to_datetime(df[schema.TIMESTAMP], errors="coerce", format="mixed")
        bad = ts.isna()
        report.rows_dropped_bad_timestamp = int(bad.sum())
        if report.rows_dropped_bad_timestamp:
            log.info("dropping rows with unparseable timestamp",
                     rows=report.rows_dropped_bad_timestamp, source=source)
        df = df.loc[~bad].copy()
        df[schema.TIMESTAMP] = ts.loc[~bad]
    else:
        report.synthesized_timestamps = True
        log.warning("no timestamp column; synthesizing monotonic order", source=source)
        df[schema.TIMESTAMP] = pd.Timestamp("2017-01-01") + pd.to_timedelta(
            np.arange(len(df)), unit="s"
        )

    # Step 7: finalize schema.
    df[schema.BINARY_LABEL] = (df[schema.LABEL] != schema.BENIGN_LABEL).astype("int8")
    if schema.DAY not in df.columns:
        df[schema.DAY] = source
    df = df[[*feats, schema.LABEL, schema.BINARY_LABEL, schema.DAY, schema.TIMESTAMP]]
    df = df.reset_index(drop=True)

    report.rows_out = len(df)
    report.class_counts_out = df[schema.LABEL].value_counts().to_dict()
    log.info(
        "cleaning complete",
        source=source,
        rows_in=report.rows_in,
        rows_out=report.rows_out,
        dropped_total=report.rows_dropped_total,
        imbalance_ratio_out=report.imbalance_ratio_out,
    )
    schema.validate_frame(df)
    return df, report
