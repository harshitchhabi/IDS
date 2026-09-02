"""Cleaning drops exactly what CLAUDE.md's Phase 0 gotcha list names."""

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.features.cleaning import clean_flows

_RAW_TO_CANON = schema.CICIDS_COLUMN_MAP


def _raw_row(label="BENIGN", **overrides):
    row = {raw: 1.0 for raw in _RAW_TO_CANON}
    row[schema.CICIDS_LABEL_COLUMN] = label  # " Label" with leading space
    for canon, val in overrides.items():
        raw = next(r for r, c in _RAW_TO_CANON.items() if c == canon)
        row[raw] = val
    return row


def _raw_frame(rows, timestamps=None):
    df = pd.DataFrame(rows)
    if timestamps is not None:
        df[schema.CICIDS_TIMESTAMP_COLUMN] = timestamps
    # add whitespace to a couple of column names, mimicking the real CSVs
    return df.rename(columns={"Flow Duration": " Flow Duration "})


def test_clean_handles_all_documented_gotchas():
    rows = [
        _raw_row("BENIGN"),
        _raw_row("PortScan"),
        _raw_row("BENIGN", flow_bytes_per_s=np.inf, flow_pkts_per_s=np.inf),  # rate Inf
        _raw_row("BENIGN", fwd_packets=np.nan),                               # NaN cell
        _raw_row("DDoS", flow_duration=-5.0),                                 # negative
        _raw_row("BENIGN"),  # exact duplicate of row 0
    ]
    df, rep = clean_flows(_raw_frame(rows), source="unit")

    assert rep.rows_in == 6
    assert rep.inf_cells_replaced == {"flow_bytes_per_s": 1, "flow_pkts_per_s": 1}
    assert rep.rows_dropped_nan == 2  # the explicit NaN row + the Inf->NaN row
    assert rep.nan_by_column["fwd_packets"] == 1
    assert rep.rows_dropped_negative == 1
    assert rep.negative_by_column["flow_duration"] == 1
    assert rep.rows_dropped_duplicate == 1
    assert rep.rows_out == 2  # one BENIGN + one PortScan survive

    schema.validate_frame(df)
    assert set(df[schema.LABEL]) == {"BENIGN", "PortScan"}
    assert df[schema.BINARY_LABEL].tolist() == [0, 1]


def test_whitespace_label_column_is_recognized():
    df, rep = clean_flows(_raw_frame([_raw_row("BENIGN"), _raw_row("Bot")]), source="unit")
    assert schema.LABEL in df.columns
    assert rep.class_counts_out == {"BENIGN": 1, "Bot": 1}


def test_imbalance_ratio_reported():
    rows = [_raw_row("BENIGN", fwd_bytes=float(i)) for i in range(9)]
    rows.append(_raw_row("Bot", fwd_bytes=99.0))
    _, rep = clean_flows(_raw_frame(rows), source="unit")
    assert rep.imbalance_ratio_out == 9.0


def test_missing_timestamp_column_is_synthesized_monotonically():
    df, rep = clean_flows(_raw_frame([_raw_row("BENIGN", fwd_bytes=float(i)) for i in range(4)]),
                          source="unit")
    assert rep.synthesized_timestamps is True
    assert df[schema.TIMESTAMP].is_monotonic_increasing


def test_unparseable_timestamps_are_dropped_and_counted():
    rows = [_raw_row("BENIGN", fwd_bytes=float(i)) for i in range(3)]
    df, rep = clean_flows(
        _raw_frame(rows, timestamps=["2017-07-07 03:23:00", "not-a-date", "2017-07-07 03:25:00"]),
        source="unit",
    )
    assert rep.rows_dropped_bad_timestamp == 1
    assert rep.synthesized_timestamps is False
    assert len(df) == 2
    assert str(df[schema.TIMESTAMP].dtype).startswith("datetime64")
