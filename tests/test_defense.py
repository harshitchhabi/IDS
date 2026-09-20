from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dloop.adversary.base import PER_FLOW_COLUMNS, cost_metadata, features_of, per_flow_cost
from dloop.adversary.mimicry import JitterAdversary, MimicryAdversary
from dloop.defense.base import DefenseDecision, NoOpDefense, TrainingView
from dloop.defense.d1_cost_weighting import COMPONENTS, CostFunction, D1Config, D1CostWeighting
from dloop.defense.generic import KNNSanitize, LossFilter
from dloop.features import schema
from dloop.features.normalize import Normalizer
from dloop.loop.config import LoopConfig
from dloop.loop.data import LoopDataConfig, from_partitions
from dloop.loop.rounds import run_arm
from dloop.models import ModelConfig, make_model
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions
from dloop.sim.partition import PartitionConfig

_F = len(schema.CANONICAL_FEATURES)
_IDX = {n: i for i, n in enumerate(schema.CANONICAL_FEATURES)}


@pytest.fixture(scope="module")
def loop_data():
    cfg = PartitionConfig(strategy="within_day_temporal",
                          pool_withheld_families=("SSH-Patator",), seed_withheld_families=("DoS Hulk",))
    data = load_partitions(source="synthetic",
                           synthetic_config=synthetic.SyntheticConfig(benign_per_day=3000, attack_per_class=600),
                           partition_config=cfg)
    return from_partitions(data, "t", LoopDataConfig(seed_train_rows=3000, eval_benign_rows=3000,
                                                     eval_attack_cap_per_family=300))


def _flow(duration_us=0.0, fwd_p=0.0, bwd_p=0.0, fwd_b=0.0, bwd_b=0.0) -> np.ndarray:
    x = np.zeros((1, _F))
    x[0, _IDX["flow_duration"]], x[0, _IDX["fwd_packets"]], x[0, _IDX["bwd_packets"]] = duration_us, fwd_p, bwd_p
    x[0, _IDX["fwd_bytes"]], x[0, _IDX["bwd_bytes"]] = fwd_b, bwd_b
    return x


REF = per_flow_cost(np.vstack([_flow(2e6, 4, 3, 400, 300), _flow(2e6, 4, 3, 400, 300), _flow(2e6, 4, 3, 400, 300)]))


# ---- D1's stated properties (DECISIONS.md 20) --------------------------------
def test_d1_weight_is_bounded_and_zero_at_zero_cost():
    cf = CostFunction(REF, D1Config())
    assert cf.weight(np.zeros((1, 4)))[0] == 0.0
    grid = np.random.default_rng(0).uniform(0, 1e6, size=(500, 4))
    w = cf.weight(grid)
    assert (w >= 0).all() and (w <= 1).all()


@pytest.mark.parametrize("col", range(4))
def test_d1_weight_and_effort_are_monotone_in_every_component(col):
    cf = CostFunction(REF, D1Config())
    base = np.array([[3.0, 20.0, 5e3, 4.0]])
    ws, es = [], []
    for v in np.geomspace(1e-3, 1e6, 40):
        x = base.copy()
        x[0, col] = v
        ws.append(cf.weight(x)[0])
        es.append(cf.effort(x)[0])
    assert all(a <= b + 1e-12 for a, b in zip(ws, ws[1:]))
    assert all(a < b for a, b in zip(es, es[1:]))            # effort strictly increasing


def test_d1_reference_flow_has_unit_effort_and_default_weight():
    cf = CostFunction(REF, D1Config())
    ref_flow = cf.reference[None, :]
    assert cf.effort(ref_flow)[0] == pytest.approx(1.0)
    assert cf.weight(ref_flow)[0] == pytest.approx((1 / 8) ** 2)


def test_d1_is_invariant_to_component_units():
    x = np.array([[3.0, 20.0, 5e3, 4.0], [0.2, 2.0, 100.0, 1.0]])
    a = CostFunction(REF, D1Config()).weight(x)
    scale = np.array([1000.0, 1.0, 0.001, 1.0])              # e.g. seconds -> ms, bytes -> kB
    b = CostFunction(REF * scale, D1Config()).weight(x * scale)
    assert np.allclose(a, b)


def test_d1_weight_full_only_above_saturation():
    cf = CostFunction(REF, D1Config(e_star=4.0, gamma=1.0))
    assert cf.weight((cf.reference * 1000)[None, :])[0] == 1.0
    assert cf.weight((cf.reference * 0.01)[None, :])[0] < 0.05


def test_per_flow_costs_sum_to_batch_totals(loop_data):
    b, cost = JitterAdversary(loop_data.pool_attack_x, loop_data.normalizer, 0.0, 1, true_label=1).generate_batch(1, 300)
    pf = cost.per_flow
    assert pf.shape == (300, len(PER_FLOW_COLUMNS))
    assert pf[:, 0].sum() == pytest.approx(cost.duration_s)
    assert pf[:, 1].sum() == pytest.approx(cost.packets)
    assert pf[:, 2].sum() == pytest.approx(cost.bytes)
    assert (pf[:, 3] <= pf[:, 1]).all()                      # depth cannot exceed packets


def test_d1_defense_returns_per_row_weights_and_never_touches_labels(loop_data):
    d1 = D1CostWeighting(loop_data.seed_x, loop_data.seed_y)
    b, cost = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1).generate_batch(1, 200)
    dec = d1.apply(b, cost, np.ones(200, dtype=int))
    assert dec.weights.shape == (200,) and dec.admit and (dec.weights >= 0).all() and (dec.weights <= 1).all()


def test_d1_config_validation_and_component_ablation():
    with pytest.raises(ValueError):
        D1Config(e_star=0)
    with pytest.raises(ValueError):
        D1Config(gamma=0.5)
    with pytest.raises(ValueError):
        D1Config(alpha=(0, 0, 0, 0))
    dur_only = CostFunction(REF, D1Config(alpha=(1, 0, 0, 0)))
    x = np.array([[3.0, 1e9, 1e9, 1e9]])                     # huge everything except duration
    y = np.array([[3.0, 0.0, 0.0, 0.0]])
    assert dur_only.effort(x)[0] == pytest.approx(dur_only.effort(y)[0])


def test_single_component_ablations_have_distinct_tags():
    tags = {D1Config(alpha=tuple(1.0 if i == j else 0.0 for j in range(4))).tag() for i in range(4)}
    assert len(tags) == 4                       # a collision once made the resume logic skip a run
    assert D1Config().tag() == "d1_E8_g2"


def test_attacker_padding_raises_cost_and_moves_row_away_from_benign(loop_data):
    pool, norm = loop_data.pool_benign_x, loop_data.normalizer
    plain, c0 = MimicryAdversary(pool, norm, 0.0, 1).generate_batch(1, 200)
    padded, c1 = MimicryAdversary(pool, norm, 0.0, 1, cost_padding=8.0).generate_batch(1, 200)
    assert c1.packets > c0.packets and c1.bytes > c0.bytes and c1.duration_s > c0.duration_s
    dz = norm.transform(features_of(padded)) - norm.transform(features_of(plain))
    assert np.abs(dz).max() > 0.5                            # a real move in feature space
    with pytest.raises(ValueError):
        MimicryAdversary(pool, norm, 0.0, 1, cost_padding=0.5)


# ---- generic baselines ----------------------------------------------------------
def _blobs(seed=0, n=400):
    rng = np.random.default_rng(seed)
    benign = np.abs(rng.normal([50, 10, 8, 900, 700], 3, size=(n, 5)))
    attack = np.abs(rng.normal([5, 200, 1, 40, 20], 3, size=(n, 5)))
    def widen(a):
        x = np.zeros((len(a), _F)) + 1.0
        for j, name in enumerate(("flow_duration", "fwd_packets", "bwd_packets", "fwd_bytes", "bwd_bytes")):
            x[:, _IDX[name]] = a[:, j]
        return x
    return widen(benign), widen(attack)


def test_knn_sanitize_drops_benign_looking_rows_stamped_malicious_and_keeps_real_attacks():
    ben, atk = _blobs()
    seed_x = np.vstack([ben[:300], atk[:300]])
    seed_y = np.r_[np.zeros(300, int), np.ones(300, int)]
    knn = KNNSanitize(seed_x, seed_y)
    poison = ben[300:340]
    batch = pd.DataFrame(poison, columns=list(schema.CANONICAL_FEATURES))
    dropped = knn.apply(batch, cost_metadata(poison), np.ones(40, dtype=int)).weights
    real = pd.DataFrame(atk[300:340], columns=list(schema.CANONICAL_FEATURES))
    kept = knn.apply(real, cost_metadata(atk[300:340]), np.ones(40, dtype=int)).weights
    assert dropped.mean() < 0.1 and kept.mean() > 0.9


def _loss_filter_keep_fraction(n_flipped: int) -> tuple[float, bool]:
    ben, atk = _blobs()
    x = np.vstack([ben[:300], atk[:300], ben[300:300 + n_flipped]])     # benign-looking rows...
    y = np.r_[np.zeros(300, int), np.ones(300, int), np.ones(n_flipped, int)]   # ...stamped malicious
    is_hp = np.r_[np.zeros(600, bool), np.ones(n_flipped, bool)]
    w = LossFilter().sanitize(TrainingView(x, y, np.ones(len(y)), is_hp, 1, 1))
    return float(w[600:].mean()), bool(np.array_equal(w[:600], np.ones(600)))


def test_loss_filter_drops_sparse_flipped_labels_and_never_touches_seed_rows():
    kept, seed_untouched = _loss_filter_keep_fraction(15)
    assert seed_untouched
    assert kept < 0.2


def test_loss_filter_is_weaker_when_the_poison_is_dense_enough_to_be_self_consistent():
    # DECISIONS.md 20, expectation (ii): a large block of identically-mislabeled rows
    # teaches the auxiliary model its own label, so out-of-fold loss stops flagging it.
    sparse, _ = _loss_filter_keep_fraction(15)
    dense, _ = _loss_filter_keep_fraction(100)
    assert dense > sparse + 0.2


def test_run_arm_rejects_a_defense_that_touches_seed_weights(loop_data):
    class Cheat(NoOpDefense):
        def sanitize(self, view):
            w = view.w.copy()
            w[0] = 0.5
            return w

    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1)
    with pytest.raises(AssertionError):
        run_arm(loop_data, adv, scenario="a1", model_kind="rf", seed=1,
                config=LoopConfig(rounds=1, poison_ratio=0.1), hyperparams={"n_estimators": 3}, defense=Cheat())


def test_run_arm_records_defense_statistics(loop_data):
    d1 = D1CostWeighting(loop_data.seed_x, loop_data.seed_y)
    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1)
    res = run_arm(loop_data, adv, scenario="a1", model_kind="rf", seed=1,
                  config=LoopConfig(rounds=2, poison_ratio=0.2), hyperparams={"n_estimators": 3}, defense=d1)
    last = [r for r in res.rows if r["round"] == 2 and r["threshold_mode"] == "fixed"][0]
    assert last["defense"] == d1.name and 0 <= last["hp_mean_weight"] <= 1
    assert last["hp_effective_ratio"] < last["poison_ratio"]      # D1 shrinks effective poison share
    assert last["defense_seconds"] >= 0 and last["fit_seconds"] > 0


# ---- calibration on twin-free validation rows -----------------------------------------
def test_validation_twin_filter_drops_rows_with_a_training_twin():
    rng = np.random.default_rng(0)
    ben = np.abs(rng.normal(20, 4, size=(600, _F))) + 1
    y = np.zeros(600, int)
    m = make_model(ModelConfig(kind="rf", seed=1, hyperparams={"n_estimators": 3})).fit(ben, y)  # sets scaler_
    x_tr, x_val = ben[:400], np.vstack([ben[:50], ben[400:550] + 5.0])   # 50 exact twins, 150 far rows
    m.config = replace(m.config, val_min_nn_distance=0.05)
    keep = m._val_rows_without_twins(x_tr, m.scaler_.transform(x_val), np.zeros(400, int), np.zeros(200, int))
    assert keep[:50].mean() < 0.1 and keep[50:].mean() > 0.9


def test_validation_filter_off_is_the_original_behaviour():
    rng = np.random.default_rng(0)
    x = np.abs(rng.normal(20, 4, size=(800, _F))) + 1
    y = (rng.random(800) < 0.3).astype(int)
    a = make_model(ModelConfig(kind="rf", seed=1, hyperparams={"n_estimators": 5})).fit(x, y)
    b = make_model(ModelConfig(kind="rf", seed=1, hyperparams={"n_estimators": 5}, val_min_nn_distance=0.0)).fit(x, y)
    assert a.threshold_ == b.threshold_ and a.val_benign_dropped_frac_ == 0.0
    assert a.config.hash() == make_model(ModelConfig(kind="rf", seed=1, hyperparams={"n_estimators": 5})).config.hash()
