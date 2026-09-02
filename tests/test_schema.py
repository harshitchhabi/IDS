import pandas as pd
import pytest

from dloop.features import schema


def test_canonical_features_unique_and_ordered():
    assert len(schema.CANONICAL_FEATURES) == len(set(schema.CANONICAL_FEATURES))


def test_column_map_covers_every_feature_exactly_once():
    mapped = list(schema.CICIDS_COLUMN_MAP.values())
    assert sorted(mapped) == sorted(schema.CANONICAL_FEATURES)
    assert len(mapped) == len(set(mapped))


def test_rate_features_are_canonical():
    assert schema.RATE_FEATURES <= set(schema.CANONICAL_FEATURES)


def test_normalize_label_collapses_benign_whitespace_and_case():
    assert schema.normalize_label(" BENIGN ") == "BENIGN"
    assert schema.normalize_label("benign") == "BENIGN"
    assert schema.normalize_label(" PortScan") == "PortScan"


def test_validate_frame_rejects_wrong_schema():
    df = pd.DataFrame({c: [0.0] for c in schema.CANONICAL_FEATURES})
    with pytest.raises(ValueError):
        schema.validate_frame(df)  # missing label / is_attack / day
