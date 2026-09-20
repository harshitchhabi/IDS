import numpy as np
import pandas as pd
import pytest

from dloop.adversary.base import cost_metadata, features_of
from dloop.adversary.clean import CleanAdversary
from dloop.adversary.mimicry import FidelityMeter, MimicryAdversary, assert_disjoint_from_eval
from dloop.features import schema
from dloop.loop.data import LoopDataConfig, from_partitions
from dloop.loop.labeler import auto_label
from dloop.loop.config import LoopConfig
from dloop.loop.rounds import run_arm
from dloop.defense.base import NoOpDefense
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions
from dloop.sim.partition import PartitionConfig

_SCFG = synthetic.SyntheticConfig(benign_per_day=3000, attack_per_class=600)


@pytest.fixture(scope="module")
def loop_data():
    cfg = PartitionConfig(strategy="within_day_temporal",
                          pool_withheld_families=("SSH-Patator",), seed_withheld_families=("DoS Hulk",))
    data = load_partitions(source="synthetic", synthetic_config=_SCFG, partition_config=cfg)
    return from_partitions(data, "t", LoopDataConfig(seed_train_rows=3000, eval_benign_rows=3000,
                                                     eval_attack_cap_per_family=300))


def test_fixed_ratio_accumulate_reaches_target_ratio():
    for r in (0.005, 0.05, 0.2, 0.5):
        s = LoopConfig(poison_ratio=r).budgets(30_000)
        assert len(s) == 20 and all(x >= 0 for x in s)
        assert sum(s) / (30_000 + sum(s)) == pytest.approx(r, abs=1e-4)
    assert LoopConfig(poison_ratio=0.0).budgets(30_000) == [0] * 20


def test_fixed_ratio_sliding_window_reaches_target_once_window_full():
    cfg = LoopConfig(retention="sliding_window", window_rounds=5, poison_ratio=0.2)
    b = cfg.budgets(30_000)
    assert len(set(b)) == 1                                   # constant per-round budget
    assert 5 * b[0] / (30_000 + 5 * b[0]) == pytest.approx(0.2, abs=1e-3)


def test_fixed_batch_is_constant_and_ignores_ratio():
    cfg = LoopConfig(budget_mode="fixed_batch", batch_size=250)
    assert cfg.budgets(30_000) == [250] * 20


def test_config_rejects_inconsistent_options():
    with pytest.raises(ValueError):
        LoopConfig(retention="sliding_window")                # no window
    with pytest.raises(ValueError):
        LoopConfig(retention="accumulate", window_rounds=3)   # window without window retention
    with pytest.raises(ValueError):
        LoopConfig(poison_ratio=1.0)
    assert LoopConfig().tag() == ""                            # default keeps earlier job names
    assert LoopConfig(retention="sliding_window", window_rounds=4).tag() != ""


def test_clean_batch_shape_and_labels(loop_data):
    b, cost = CleanAdversary(loop_data.pool_attack_x, seed=1).generate_batch(1, 200)
    assert isinstance(b, pd.DataFrame)
    assert features_of(b).shape == (200, len(schema.CANONICAL_FEATURES))
    assert b["true_label"].sum() == 200                    # all genuinely attack
    assert (auto_label(b) == 1).all()                      # labeler stamps malicious
    assert cost.flows == 200


def test_mimicry_batch_is_benign_but_stamped_malicious(loop_data):
    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.3, seed=1)
    b, cost = adv.generate_batch(1, 200)
    x = features_of(b)
    assert x.shape == (200, len(schema.CANONICAL_FEATURES))
    assert b["true_label"].sum() == 0                      # ground truth benign
    assert (auto_label(b) == 1).all()                      # the poison: stamped malicious
    assert (x >= 0).all() and np.isfinite(x).all()
    assert cost.flows == 200 and cost.packets > 0 and cost.bytes > 0 and cost.duration_s > 0


def test_batches_are_fresh_rows_and_nested_across_ratios(loop_data):
    a1 = CleanAdversary(loop_data.pool_attack_x, seed=3)
    x1, x2 = features_of(a1.generate_batch(1, 50)[0]), features_of(a1.generate_batch(2, 50)[0])
    assert not np.any(np.all(x1[:, None, :] == x2[None, :, :], axis=2))   # no reuse within the pool
    # same seed -> same permutation -> a larger scenario's first rows equal the smaller one's
    a2 = CleanAdversary(loop_data.pool_attack_x, seed=3)
    assert np.array_equal(features_of(a2.generate_batch(1, 50)[0]), x1)


def test_pool_exhaustion_is_flagged(loop_data):
    n = len(loop_data.pool_attack_x)
    b, _ = CleanAdversary(loop_data.pool_attack_x, seed=1).generate_batch(1, n + 5)
    assert b.attrs["resampled"]


def test_zero_jitter_returns_pool_rows_unchanged(loop_data):
    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, seed=1)
    b, _ = adv.generate_batch(1, 20)
    pool = {tuple(r) for r in loop_data.pool_benign_x.astype("float64")}
    assert all(tuple(r) in pool for r in features_of(b))


def test_realized_fidelity_is_monotone_in_jitter(loop_data):
    norm = loop_data.normalizer
    fm = FidelityMeter(norm.transform(loop_data.eval_benign_full_x), norm)
    med = []
    for j in (0.0, 0.1, 0.4, 1.0):
        b, _ = MimicryAdversary(loop_data.pool_benign_x, norm, j, seed=1).generate_batch(1, 500)
        med.append(np.median(fm.distances(features_of(b), max_rows=500, rng=np.random.default_rng(0))))
    assert med == sorted(med) and med[-1] > med[0]


def test_cost_function_monotone_in_batch_size(loop_data):
    adv = CleanAdversary(loop_data.pool_attack_x, seed=1)
    x = features_of(adv.generate_batch(1, 400)[0])
    small, big = cost_metadata(x[:100]), cost_metadata(x)
    assert small.flows < big.flows and small.packets < big.packets
    assert small.bytes < big.bytes and small.duration_s < big.duration_s


def test_poison_source_disjoint_from_eval_and_planted_overlap_is_caught(loop_data):
    assert assert_disjoint_from_eval(loop_data.pool_benign_x, loop_data.eval_benign_full_x) > 0
    planted = np.vstack([loop_data.pool_benign_x[:5], loop_data.eval_benign_full_x[:1]])
    with pytest.raises(AssertionError):
        assert_disjoint_from_eval(planted, loop_data.eval_benign_full_x)


def test_run_arm_smoke_shares_round0_and_reaches_ratio(loop_data):
    fast = {"n_estimators": 8}
    ctrl = run_arm(loop_data, None, scenario="control", model_kind="rf", seed=1,
                   config=LoopConfig(rounds=2), hyperparams=fast)
    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, seed=1)
    a1 = run_arm(loop_data, adv, scenario="a1", model_kind="rf", seed=1,
                 config=LoopConfig(rounds=2, poison_ratio=0.2), hyperparams=fast, defense=NoOpDefense())
    r0c = [r for r in ctrl.rows if r["round"] == 0 and r["threshold_mode"] == "fixed"][0]
    r0a = [r for r in a1.rows if r["round"] == 0 and r["threshold_mode"] == "fixed"][0]
    assert r0c["fpr"] == r0a["fpr"] and r0c["tpr"] == r0a["tpr"]       # arms start identical
    last = [r for r in a1.rows if r["round"] == 2 and r["threshold_mode"] == "fixed"][0]
    assert last["poison_ratio"] == pytest.approx(0.2, abs=1e-3)
    assert last["cum_flows"] > 0 and last["cum_bytes"] > 0
    # recalibrated mode pins FPR near target by construction
    rec = [r for r in a1.rows if r["round"] == 2 and r["threshold_mode"] == "recalibrated"][0]
    assert rec["fpr"] <= 0.011
    # every row records the full confusion matrix
    assert all(k in last for k in ("tn", "fp", "fn", "tp", "precision", "f1", "auroc"))


def _hp_by_round(rows):
    return {r["round"]: r["n_honeypot"] for r in rows if r["threshold_mode"] == "fixed"}


def test_sliding_window_drops_old_batches_but_cost_stays_cumulative(loop_data):
    fast = {"n_estimators": 4}
    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, seed=1)
    cfg = LoopConfig(rounds=6, retention="sliding_window", window_rounds=2,
                     budget_mode="fixed_batch", batch_size=100)
    res = run_arm(loop_data, adv, scenario="a1", model_kind="rf", seed=1, config=cfg, hyperparams=fast)
    hp = _hp_by_round(res.rows)
    assert hp[1] == 100 and hp[2] == 200 and all(hp[k] == 200 for k in (3, 4, 5, 6))
    cost = {r["round"]: r["cum_flows"] for r in res.rows if r["threshold_mode"] == "fixed"}
    assert cost[6] == 600                                                    # attacker cost never shrinks


def test_accumulate_fixed_batch_grows_linearly(loop_data):
    fast = {"n_estimators": 4}
    adv = CleanAdversary(loop_data.pool_attack_x, seed=1)
    cfg = LoopConfig(rounds=4, budget_mode="fixed_batch", batch_size=50)
    res = run_arm(loop_data, adv, scenario="s0", model_kind="rf", seed=1, config=cfg, hyperparams=fast)
    assert _hp_by_round(res.rows) == {0: 0, 1: 50, 2: 100, 3: 150, 4: 200}
