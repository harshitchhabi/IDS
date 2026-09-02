import numpy as np

from dloop.features import schema
from dloop.sim import synthetic

_CFG = synthetic.SyntheticConfig(benign_per_day=400, attack_per_class=120)


def test_generates_all_days_in_raw_cicids_shape():
    raw = synthetic.generate_raw_by_day(_CFG)
    assert set(raw) == set(synthetic.DAYS)
    monday = raw["monday"]
    assert schema.CICIDS_LABEL_COLUMN in monday.columns      # ' Label' leading space
    assert schema.CICIDS_TIMESTAMP_COLUMN in monday.columns  # ' Timestamp' leading space
    for canon_raw in schema.CICIDS_COLUMN_MAP:
        assert canon_raw in monday.columns
    assert set(monday[schema.CICIDS_LABEL_COLUMN].unique()) == {schema.BENIGN_LABEL}


def test_attack_days_carry_expected_classes():
    raw = synthetic.generate_raw_by_day(_CFG)
    fri = set(raw["friday"][schema.CICIDS_LABEL_COLUMN].unique())
    assert {"Bot", "PortScan", "DDoS"} <= fri
    assert schema.BENIGN_LABEL in fri


def test_burst_types_place_families_on_the_timeline():
    raw = synthetic.generate_raw_by_day(_CFG)
    fri, tue = raw["friday"], raw["tuesday"]

    def frac(df):
        ts = df[schema.CICIDS_TIMESTAMP_COLUMN]
        lo, hi = df[schema.CICIDS_TIMESTAMP_COLUMN].min(), df[schema.CICIDS_TIMESTAMP_COLUMN].max()
        return lambda label: ((ts[df[schema.CICIDS_LABEL_COLUMN] == label] - lo) / (hi - lo))

    ff = frac(fri)
    assert ff("Bot").min() > 0.7                       # brief_late
    assert ff("PortScan").max() - ff("PortScan").min() > 0.5  # sustained

    ft = frac(tue)
    ssh = ft("SSH-Patator")                            # split_early_late
    assert ssh.min() < 0.15 and ssh.max() > 0.85
    assert ((ssh > 0.4) & (ssh < 0.8)).mean() < 0.02   # nothing in the middle


def test_fingerprint_tight_bursts_are_injected_for_sustained_families():
    raw = synthetic.generate_raw_by_day(
        synthetic.SyntheticConfig(benign_per_day=200, attack_per_class=400,
                                  fingerprint_tight_frac=0.1, fingerprint_centroids=4)
    )
    feat = list(schema.CICIDS_COLUMN_MAP)
    hulk = raw["wednesday"]
    hulk = hulk[hulk[schema.CICIDS_LABEL_COLUMN] == "DoS Hulk"][feat].to_numpy("float64")
    hulk = hulk[np.isfinite(hulk).all(axis=1) & (hulk >= 0).all(axis=1)]
    # many rows collapse onto a few centroids -> many near-zero pairwise distances,
    # which independent log-normal draws essentially never produce
    from scipy.spatial.distance import pdist
    d = pdist(np.log1p(hulk))
    assert (d < 1e-2).sum() > 30


def test_corruption_is_injected():
    raw = synthetic.generate_raw_by_day(_CFG)
    pooled = raw["wednesday"]
    feat_cols = list(schema.CICIDS_COLUMN_MAP)
    rate_cols = [k for k, v in schema.CICIDS_COLUMN_MAP.items() if v in schema.RATE_FEATURES]
    assert np.isinf(pooled[rate_cols].to_numpy("float64")).any()
    assert np.isnan(pooled[feat_cols].to_numpy("float64")).any()
    assert pooled.duplicated(subset=feat_cols).any()


def test_reproducible_for_fixed_seed():
    a = synthetic.generate_raw_by_day(_CFG)
    b = synthetic.generate_raw_by_day(_CFG)
    for day in synthetic.DAYS:
        assert a[day].shape == b[day].shape
        assert np.allclose(
            a[day][[*schema.CICIDS_COLUMN_MAP]].to_numpy("float64"),
            b[day][[*schema.CICIDS_COLUMN_MAP]].to_numpy("float64"),
            equal_nan=True,
        )
        assert a[day][schema.CICIDS_TIMESTAMP_COLUMN].equals(b[day][schema.CICIDS_TIMESTAMP_COLUMN])
