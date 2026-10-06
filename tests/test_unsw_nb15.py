"""UNSW-NB15 loader and the feature-subset path it needs.

UNSW-NB15 has a direct analogue for only 9 of the 24 canonical features, so it
runs on a subset. These tests pin that the loader names columns from the
dictionary (not by position guesses), and that a subset flows through cleaning,
partitioning, the loop data and a loop arm without a fabricated column.
"""

import numpy as np
import pandas as pd
import pytest

from dloop.adversary.mimicry import MimicryAdversary
from dloop.features import schema
from dloop.loop.config import LoopConfig
from dloop.loop.data import LoopData, LoopDataConfig, from_partitions
from dloop.loop.rounds import run_arm
from dloop.sim import synthetic, unsw_nb15
from dloop.sim.partition import PartitionConfig, build_partitions

# Dictionary rows in file order, spelled the way the official file spells them
# (mixed case, a stray space inside "ct_src_ ltm").
_DICT_NAMES = ["srcip", "dur", "Spkts", "Dpkts", "sbytes", "dbytes", "smeansz", "dmeansz",
               "Stime", "Sintpkt", "Dintpkt", "ct_src_ ltm", "attack_cat", "Label"]


def _write_unsw(root, rows):
    pd.DataFrame({"No.": range(1, len(_DICT_NAMES) + 1), "Name": _DICT_NAMES,
                  "Type ": "x", "Description": "x"}).to_csv(
        root / unsw_nb15.DICTIONARY_FILE, index=False, encoding="latin1")
    pd.DataFrame(rows).to_csv(root / "UNSW-NB15_1.csv", index=False, header=False)


def test_unsw_subset_is_valid_and_starts_with_cost_features():
    assert schema.check_feature_subset(schema.UNSW_FEATURES) == schema.UNSW_FEATURES
    assert len(schema.UNSW_FEATURES) == 9


def test_loader_names_columns_from_dictionary_and_converts_units(tmp_path):
    jan, feb = 1421927414, 1424235000   # 2015-01-22 and 2015-02-18 (UTC)
    rows = [
        ["1.1.1.1", 0.5, 2, 3, 100, 200, 50, 66, jan, 1.5, 2.0, 1, "", 0],
        ["1.1.1.2", 1.0, 4, 1, 300, 10, 75, 10, feb, 3.0, 0.0, 1, " Backdoors ", 1],
        ["1.1.1.3", 1.0, 4, 1, 300, 10, 75, 10, feb, 3.0, 0.0, 1, "", 1],   # label/category disagree
    ]
    _write_unsw(tmp_path, rows)
    by_day = unsw_nb15.load_raw_by_day(tmp_path)
    assert set(by_day) == {"jan22", "feb18"}
    jan_row = by_day["jan22"].iloc[0]
    assert jan_row["flow_duration"] == pytest.approx(0.5e6)       # s -> us
    assert jan_row["fwd_iat_mean"] == pytest.approx(1.5e3)        # ms -> us
    assert jan_row["fwd_bytes"] == 100 and jan_row["bwd_pkt_len_mean"] == 66
    assert jan_row[schema.LABEL] == schema.BENIGN_LABEL
    assert by_day["feb18"][schema.LABEL].tolist() == ["Backdoor"]   # alias merged, mismatch dropped
    assert list(by_day["jan22"].columns[:9]) == list(schema.UNSW_FEATURES)


def test_loader_refuses_without_dictionary(tmp_path):
    pd.DataFrame([[1]]).to_csv(tmp_path / "UNSW-NB15_1.csv", index=False, header=False)
    with pytest.raises(FileNotFoundError):
        unsw_nb15.load_raw_by_day(tmp_path)


def test_feature_subset_runs_through_partition_and_loop(tmp_path):
    raw = synthetic.generate_raw_by_day(
        synthetic.SyntheticConfig(benign_per_day=2000, attack_per_class=400))
    data = build_partitions(raw, config=PartitionConfig(strategy="within_day_temporal"),
                            features=schema.UNSW_FEATURES)
    assert data.features == schema.UNSW_FEATURES
    for df in data.frames.values():
        schema.validate_frame(df, schema.UNSW_FEATURES)

    ld = from_partitions(data, "t", LoopDataConfig(seed_train_rows=2000, eval_benign_rows=2000,
                                                   eval_attack_cap_per_family=200))
    assert ld.seed_x.shape[1] == 9 and ld.features == schema.UNSW_FEATURES
    ld.save(tmp_path / "t.npz")
    back = LoopData.load(tmp_path / "t.npz")
    assert back.features == schema.UNSW_FEATURES
    np.testing.assert_array_equal(back.eval_x, ld.eval_x)

    adv = MimicryAdversary(ld.pool_benign_x, ld.normalizer, 0.7, 1)
    res = run_arm(ld, adv, scenario="a1", model_kind="rf", seed=1,
                  config=LoopConfig(rounds=2, poison_ratio=0.2, val_min_nn_distance=0.1),
                  hyperparams={"n_estimators": 5})
    assert res.poison_x.shape[1] == 9
    assert {r["round"] for r in res.rows} == {0, 1, 2}
