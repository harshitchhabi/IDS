"""The live (stepwise) loop must reproduce ``run_arm`` row for row: the demo shows what the paper measured."""

import numpy as np
import pytest

from dloop.adversary.clean import CleanAdversary
from dloop.adversary.mimicry import MimicryAdversary
from dloop.defense.generic import ShareCap
from dloop.loop.config import LoopConfig
from dloop.loop.live import SHARECAP_C, LiveLoop
from dloop.loop.registry import ModelRegistry
from dloop.loop.rounds import run_arm
from dloop.store.sqlite import Store
from tests.test_loop import loop_data  # noqa: F401  (fixture)

ROUNDS, BATCH = 3, 150


def _live(loop_data, tmp_path):
    return LiveLoop(loop_data, ModelRegistry(tmp_path, Store(":memory:")), model_kind="rf", seed=1,
                    batch_size=BATCH, val_min_nn_distance=0.0)


def _ref(loop_data, adv, defense=None):
    cfg = LoopConfig(rounds=ROUNDS, budget_mode="fixed_batch", batch_size=BATCH)
    rows = run_arm(loop_data, adv, scenario="x", model_kind="rf", seed=1, config=cfg, defense=defense).rows
    return {(r["round"], r["threshold_mode"]): r for r in rows}


@pytest.mark.parametrize("scenario", ["s0", "a1"])
def test_live_matches_run_arm_undefended(loop_data, tmp_path, scenario):
    adv = (CleanAdversary(loop_data.pool_attack_x, 1) if scenario == "s0"
           else MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1))
    ref = _ref(loop_data, adv)
    live = _live(loop_data, tmp_path)
    rows = [live.history[0]] + [live.step(scenario, "off") for _ in range(ROUNDS)]
    for r in rows:
        for mode, key in (("fixed", "fixed"), ("recalibrated", "recal")):
            assert r[f"{key}_fpr"] == ref[(r["round"], mode)]["fpr"]
            assert r[f"{key}_tpr"] == ref[(r["round"], mode)]["tpr"]
        assert r["poison_ratio"] == ref[(r["round"], "fixed")]["poison_ratio"]


def test_live_matches_run_arm_with_sharecap_and_registers_versions(loop_data, tmp_path):
    ref = _ref(loop_data, MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1),
               ShareCap(SHARECAP_C))
    live = _live(loop_data, tmp_path)
    live.reset()
    rows = [live.history[0]] + [live.step("a1", "sharecap") for _ in range(ROUNDS)]
    for r in rows:
        assert r["fixed_fpr"] == ref[(r["round"], "fixed")]["fpr"]
    versions = live.registry.store.models()
    assert [v["version"] for v in versions] == list(range(ROUNDS + 1))   # every retrain is a version
    _, model, _ = live.registry.current()
    assert np.isfinite(model.score_samples(loop_data.eval_x[:5])).all()  # loaded from disk, scores


def test_defense_can_be_switched_on_after_poison_is_in_the_training_set(loop_data, tmp_path):
    live = _live(loop_data, tmp_path)
    for _ in range(ROUNDS):
        live.step("a1", "off")
    before = live.history[-1]
    after = live.step("none", "sharecap")
    assert before["hp_effective_ratio"] > SHARECAP_C
    assert after["hp_effective_ratio"] == pytest.approx(SHARECAP_C, abs=1e-6)   # cap binds retroactively
