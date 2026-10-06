"""Reprocessed CICIDS2017 loader: column mapping, Attempted-row drop, day tag."""

import pandas as pd

from dloop.features import schema
from dloop.features.cleaning import clean_flows
from dloop.sim import cicids_fixed


def test_column_map_covers_every_canonical_feature_once():
    assert sorted(schema.CICIDS_FIXED_COLUMN_MAP.values()) == sorted(schema.CANONICAL_FEATURES)


def _write_day(path, labels):
    rows = []
    for i, lab in enumerate(labels):
        row = {raw: float(i + 1) for raw in schema.CICIDS_FIXED_COLUMN_MAP}
        row["id"] = i
        row["Src IP"] = "10.0.0.1"  # unmapped column the loader must not read
        row["Timestamp"] = f"2017-07-04 12:00:{i:02d}.000000"
        row["Label"] = lab
        row["Attempted Category"] = -1 if not lab.endswith("Attempted") else 0
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_loader_drops_attempted_and_cleans(tmp_path):
    _write_day(tmp_path / "tuesday.csv",
               ["BENIGN", "FTP-Patator", "FTP-Patator - Attempted", "SSH-Patator - Attempted"])
    by_day = cicids_fixed.load_raw_by_day(tmp_path)
    assert list(by_day) == ["tuesday"]
    raw = by_day["tuesday"]
    assert len(raw) == 2
    assert not raw[schema.LABEL].str.contains("Attempted").any()
    assert "Src IP" not in raw.columns

    df, rep = clean_flows(raw, source="tuesday")
    schema.validate_frame(df)
    assert not rep.synthesized_timestamps
    assert df[schema.BINARY_LABEL].tolist() == [0, 1]
    assert (df[schema.DAY] == "tuesday").all()
