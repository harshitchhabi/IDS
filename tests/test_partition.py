import numpy as np
import pandas as pd
import pytest

from dloop.features import schema
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions
from dloop.sim.partition import (
    ATTACK_ROUTE,
    BENIGN_ROUTE,
    PARTITIONS,
    POISON_SWEEP,
    PartitionConfig,
    PartitionedData,
    assert_disjoint,
    build_partitions,
)

_SCFG = synthetic.SyntheticConfig(benign_per_day=3000, attack_per_class=600)


@pytest.fixture(scope="module")
def within_day() -> PartitionedData:
    return load_partitions(source="synthetic", synthetic_config=_SCFG,
                           partition_config=PartitionConfig(strategy="within_day_temporal"))


@pytest.fixture(scope="module")
def within_day_arms() -> PartitionedData:
    # populate all four eval-family arms explicitly
    cfg = PartitionConfig(
        strategy="within_day_temporal",
        pool_withheld_families=("SSH-Patator", "Bot"),
        seed_withheld_families=("DoS Hulk", "Bot"),
    )
    return load_partitions(source="synthetic", synthetic_config=_SCFG, partition_config=cfg)


@pytest.fixture(scope="module")
def day_split() -> PartitionedData:
    return load_partitions(source="synthetic", synthetic_config=_SCFG,
                           partition_config=PartitionConfig(strategy="day_split"))


# --- shape -------------------------------------------------------------------
def test_all_partitions_non_empty(within_day):
    for p in PARTITIONS:
        assert len(within_day[p]) > 0


def test_adversary_pool_is_two_class(within_day):
    hp = within_day["honeypot_pool"]
    assert hp[schema.BINARY_LABEL].nunique() == 2, "A1 needs benign rows in the pool"
    assert (hp[schema.BINARY_LABEL] == 0).sum() > 100
    assert (hp[schema.BINARY_LABEL] == 1).sum() > 100


def test_prod_benign_has_no_attacks(within_day, day_split):
    assert within_day["prod_benign"][schema.BINARY_LABEL].sum() == 0
    assert day_split["prod_benign"][schema.BINARY_LABEL].sum() == 0


def test_trusted_eval_and_seed_train_have_both_classes(within_day):
    for p in ("trusted_eval", "seed_train"):
        assert within_day[p][schema.BINARY_LABEL].nunique() == 2


def test_pool_reaches_20k_scale_at_default_volume():
    data = load_partitions(source="synthetic")  # default SyntheticConfig volumes
    assert len(data["honeypot_pool"]) > 18_000


# --- disjointness ----------------------------------------------------------
def test_row_content_disjoint_within_day(within_day):
    assert set(assert_disjoint(within_day).values()) == {0}


def test_row_content_disjoint_day_split(day_split):
    assert set(assert_disjoint(day_split).values()) == {0}


def test_within_day_segments_are_time_ordered(within_day):
    # per (day, family): seed_train < honeypot_pool < trusted_eval in time
    st, hp, te = (within_day[p] for p in ("seed_train", "honeypot_pool", "trusted_eval"))
    fams = te.loc[te[schema.BINARY_LABEL] == 1, schema.LABEL].unique()
    for day in st[schema.DAY].unique():
        for fam in fams:
            def ts(df):
                return df[(df[schema.DAY] == day) & (df[schema.LABEL] == fam)][schema.TIMESTAMP]
            a, b, c = ts(st), ts(hp), ts(te)
            if len(a) and len(b):
                assert a.max() < b.min()
            if len(b) and len(c):
                assert b.max() < c.min()


def test_day_split_partitions_are_day_disjoint(day_split):
    seen: set[str] = set()
    for p in PARTITIONS:
        days = set(day_split[p][schema.DAY].unique())
        assert not (days & seen)
        seen |= days


def test_planted_row_overlap_is_caught(within_day):
    poisoned = dict(within_day.frames)
    poisoned["trusted_eval"] = pd.concat(
        [within_day["trusted_eval"], within_day["seed_train"].iloc[:5]], ignore_index=True
    )
    bad = PartitionedData(poisoned, within_day.cleaning, within_day.leakage,
                          within_day.config, within_day.normalizer)
    with pytest.raises(AssertionError):
        assert_disjoint(bad)


# --- leakage guards -------------------------------------------------------
def test_guard_a_self_test_fires_on_fingerprint_tight_bursts():
    # fingerprint_tight_frac > 0 (the default) injects near-identical tool bursts;
    # the near-duplicate guard must remove them before splitting.
    tight = load_partitions(
        source="synthetic",
        synthetic_config=synthetic.SyntheticConfig(benign_per_day=3000, attack_per_class=600,
                                                   fingerprint_tight_frac=0.05),
    )
    removed = tight.leakage.near_dups_removed
    assert removed, "guard (a) removed nothing on fingerprint-tight data"
    assert sum(sum(v.values()) for v in removed.values()) > 50

    loose = load_partitions(
        source="synthetic",
        synthetic_config=synthetic.SyntheticConfig(benign_per_day=3000, attack_per_class=600,
                                                   fingerprint_tight_frac=0.0),
    )
    total_loose = sum(sum(v.values()) for v in loose.leakage.near_dups_removed.values())
    assert total_loose < 20, "guard (a) should be near-silent without fingerprint bursts"


def test_guard_c_runs_for_both_classes_gates_on_attack_only(within_day):
    assert set(within_day.leakage.nn_distance) == {"attack", "benign"}
    assert within_day.leakage.nn_distance["attack"]["percentiles"]["p5"] > 0.25
    assert not within_day.leakage.leak_warning


def test_within_day_default_puts_every_family_in_every_partition(within_day):
    # no withholding -> every trusted_eval attack family is seen_both
    split = within_day.eval_family_split()
    assert split["seed_only"] == [] and split["honeypot_only"] == [] and split["novel"] == []
    assert len(split["seen_both"]) >= 5


def test_eval_family_split_is_four_way(within_day_arms):
    split = within_day_arms.eval_family_split()
    assert split["seed_only"] == ["SSH-Patator"]       # A4
    assert split["honeypot_only"] == ["DoS Hulk"]      # decoy-only teaching
    assert split["novel"] == ["Bot"]
    assert set(split["seen_both"]) >= {"DDoS", "PortScan"}


def test_withheld_families_actually_absent_from_their_partitions(within_day_arms):
    seed_fams = set(within_day_arms["seed_train"].loc[
        within_day_arms["seed_train"][schema.BINARY_LABEL] == 1, schema.LABEL].unique())
    pool_fams = set(within_day_arms["honeypot_pool"].loc[
        within_day_arms["honeypot_pool"][schema.BINARY_LABEL] == 1, schema.LABEL].unique())
    assert "SSH-Patator" not in pool_fams          # pool-withheld
    assert "DoS Hulk" not in seed_fams             # seed-withheld
    assert "Bot" not in seed_fams and "Bot" not in pool_fams   # both


def test_eval_family_stats_row_counts_and_reportable_flag(within_day):
    stats = within_day.eval_family_stats()
    assert set(stats.columns) >= {"family", "arm", "n_seed_train", "n_honeypot_pool",
                                  "n_trusted_eval", "reportable"}
    assert (stats["reportable"] == (stats["n_trusted_eval"] >= 500)).all()


# --- config -------------------------------------------------------------
def test_split_lengths_match_routes():
    assert len(BENIGN_ROUTE) == 4
    assert len(ATTACK_ROUTE) == 3
    with pytest.raises(ValueError):
        PartitionConfig(benign_split=(0.5, 0.3, 0.2))  # wrong length (needs 4)
    with pytest.raises(ValueError):
        PartitionConfig(attack_split=(0.4, 0.4, 0.1))  # does not sum to 1


def test_poison_sweep_is_log_spaced_and_starts_at_zero():
    assert POISON_SWEEP[0] == 0.0
    ratios = np.diff(np.log(np.array(POISON_SWEEP[1:])))
    assert np.all(ratios > 0)  # strictly increasing on a log scale


def test_day_split_rejects_unknown_day():
    raw = synthetic.generate_raw_by_day(_SCFG)
    raw["someday"] = raw["monday"]
    with pytest.raises(ValueError):
        build_partitions(raw, config=PartitionConfig(strategy="day_split"))
