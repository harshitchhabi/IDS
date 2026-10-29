"""Phase R code (DECISIONS.md §31): per-seed eval redraw, the source-partition
baseline, the crowd-out attacker, and the NetFlow v2 loader / subsampler.

Synthetic data only; nothing here needs a download."""

import json

import numpy as np
import pandas as pd
import pytest

from dloop.adversary.base import TRUE_LABEL, features_of
from dloop.adversary.clean import CleanAdversary
from dloop.adversary.crowd import CrowdOutAdversary, StaleReplayAdversary
from dloop.adversary.mimicry import MimicryAdversary
from dloop.defense.base import NoOpDefense
from dloop.defense.generic import ShareCap, SourcePartition
from dloop.features import schema
from dloop.loop.config import LoopConfig
from dloop.loop.data import LoopData, LoopDataConfig, from_partitions
from dloop.loop.rounds import run_arm
from dloop.sim import netflow_v2, synthetic
from dloop.sim.dataset import load_partitions
from dloop.sim.partition import PartitionConfig, build_partitions

_SCFG = synthetic.SyntheticConfig(benign_per_day=3000, attack_per_class=600)
_LCFG = LoopDataConfig(seed_train_rows=3000, eval_benign_rows=1500, eval_attack_cap_per_family=150)


@pytest.fixture(scope="module")
def loop_data():
    cfg = PartitionConfig(strategy="within_day_temporal",
                          pool_withheld_families=("SSH-Patator",), seed_withheld_families=("DoS Hulk",))
    data = load_partitions(source="synthetic", synthetic_config=_SCFG, partition_config=cfg)
    return from_partitions(data, "t", _LCFG)


def _rows(ld: LoopData) -> set:
    a = np.ascontiguousarray(ld.eval_x.astype("float32"))
    return set(a.view(np.dtype((np.void, a.dtype.itemsize * a.shape[1]))).ravel().tolist())


# --------------------------------------------------------------------- eval redraw

def test_redraw_keeps_sizes_and_caps_and_only_draws_trusted_rows(loop_data):
    r = loop_data.redraw_eval(3, _LCFG)
    assert len(r.eval_x) == len(loop_data.eval_x)
    assert int((r.eval_y == 0).sum()) == int((loop_data.eval_y == 0).sum())
    for fam in set(loop_data.eval_family[loop_data.eval_y == 1].tolist()):
        assert (r.eval_family == fam).sum() == (loop_data.eval_family == fam).sum()
    assert r.arm_counts() == loop_data.arm_counts()
    full = np.vstack([loop_data.eval_benign_full_x, loop_data.eval_attack_full_x]).astype("float32")
    full = np.ascontiguousarray(full)
    full_keys = set(full.view(np.dtype((np.void, full.dtype.itemsize * full.shape[1]))).ravel().tolist())
    assert _rows(r) <= full_keys
    # training side is shared, untouched
    assert r.seed_x is loop_data.seed_x and r.pool_benign_x is loop_data.pool_benign_x


def test_redraw_is_deterministic_per_seed_and_differs_across_seeds(loop_data):
    a, b, c = (loop_data.redraw_eval(s, _LCFG) for s in (1, 1, 2))
    assert np.array_equal(a.eval_x, b.eval_x) and np.array_equal(a.eval_family, b.eval_family)
    assert not np.array_equal(a.eval_x, c.eval_x)


def test_default_eval_is_unchanged_by_the_full_eval_arrays(loop_data, tmp_path):
    """Adding the full-eval arrays must not consume rng draws: the default subsample is
    what a build without them would give, and a save/load roundtrip keeps both."""
    p = tmp_path / "t.npz"
    loop_data.save(p)
    back = LoopData.load(p)
    assert np.array_equal(back.eval_x, loop_data.eval_x)
    assert np.array_equal(back.eval_attack_full_x, loop_data.eval_attack_full_x)
    old_style = LoopData(**{k: v for k, v in vars(loop_data).items()
                            if not k.startswith("eval_attack_full")})
    old_style.save(tmp_path / "old.npz")
    old = LoopData.load(tmp_path / "old.npz")
    assert old.eval_attack_full_x is None
    with pytest.raises(ValueError, match="predates"):
        old.redraw_eval(1)


# ------------------------------------------------------------- source partition

def _arm(ld, adv, defense, scenario="a1", rounds=2, ratio=0.3):
    return run_arm(ld, adv, scenario=scenario, model_kind="rf", seed=1,
                   config=LoopConfig(rounds=rounds, poison_ratio=ratio), defense=defense,
                   hyperparams={"n_estimators": 10, "max_depth": 6})


def test_source_partition_alpha_zero_is_the_seed_only_model(loop_data):
    adv = lambda: MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1)
    sp0 = pd.DataFrame(_arm(loop_data, adv(), SourcePartition(0.0)).rows)
    ctrl = pd.DataFrame(_arm(loop_data, None, NoOpDefense(), scenario="control").rows)
    for col in ("fpr", "tpr", "threshold"):
        assert np.allclose(sp0[col].to_numpy(), ctrl[col].to_numpy())
    assert set(sp0.defense) == {"srcpart_a0"}


def test_source_partition_round0_is_shared_and_honeypot_model_moves_scores(loop_data):
    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1)
    sp = pd.DataFrame(_arm(loop_data, adv, SourcePartition(0.5)).rows)
    ctrl = pd.DataFrame(_arm(loop_data, None, NoOpDefense(), scenario="control").rows)
    r0 = lambda d: d[d["round"] == 0].sort_values("threshold_mode")
    assert np.allclose(r0(sp)[["fpr", "tpr", "threshold"]].to_numpy(),
                       r0(ctrl)[["fpr", "tpr", "threshold"]].to_numpy())
    last = lambda d: d[(d["round"] == 2) & (d.threshold_mode == "fixed")].iloc[0]
    assert last(sp).fpr != last(ctrl).fpr        # the honeypot model's vote changed the scores
    assert last(sp).n_honeypot > 0


def test_source_partition_refuses_a_single_class_honeypot_model(loop_data):
    adv = MimicryAdversary(loop_data.pool_benign_x, loop_data.normalizer, 0.0, 1)
    with pytest.raises(ValueError, match="one class"):
        run_arm(loop_data, adv, scenario="a1truth", model_kind="rf", seed=1,
                config=LoopConfig(rounds=1, poison_ratio=0.3, label_policy="ground_truth"),
                defense=SourcePartition(0.5), hyperparams={"n_estimators": 5, "max_depth": 4})


def test_source_partition_validates_alpha():
    with pytest.raises(ValueError):
        SourcePartition(1.5)


# -------------------------------------------------------------------- crowd-out

def _crowd(ld, factor, seed=1):
    return CrowdOutAdversary(CleanAdversary(ld.pool_attack_x, seed),
                             MimicryAdversary(ld.pool_benign_x, ld.normalizer, 0.7, seed), factor)


def test_crowd_out_batch_is_genuine_attacks_then_filler(loop_data):
    batch, cost = _crowd(loop_data, 4.0).generate_batch(1, 50)
    assert len(batch) == 250 and cost.flows == 250
    g = CrowdOutAdversary.genuine_mask(batch)
    assert g.sum() == 50
    assert (batch.loc[g, TRUE_LABEL] == 1).all() and (batch.loc[~g, TRUE_LABEL] == 0).all()
    clean, _ = CleanAdversary(loop_data.pool_attack_x, 1).generate_batch(1, 50)
    assert np.array_equal(features_of(batch)[g], features_of(clean))   # genuine part is exactly S0's
    assert cost.bytes == pytest.approx(features_of(batch)[:, [3, 4]].sum())


def test_crowd_out_factor_zero_is_s0(loop_data):
    a, _ = _crowd(loop_data, 0.0).generate_batch(1, 40)
    b, _ = CleanAdversary(loop_data.pool_attack_x, 1).generate_batch(1, 40)
    assert np.array_equal(features_of(a), features_of(b))
    with pytest.raises(ValueError):
        _crowd(loop_data, -1.0)


def _largest_seed_attack_family(ld):
    fams, counts = np.unique(ld.seed_family[ld.seed_y == 1], return_counts=True)
    return str(fams[np.argmax(counts)])


def test_stale_filler_replays_correctly_labelled_seed_rows_of_one_family(loop_data):
    fam = _largest_seed_attack_family(loop_data)
    rows = loop_data.seed_family_rows(fam)
    assert len(rows) == int(((loop_data.seed_family == fam) & (loop_data.seed_y == 1)).sum())
    adv = CrowdOutAdversary(CleanAdversary(loop_data.pool_attack_x, 1), StaleReplayAdversary(rows, 1), 4.0)
    batch, cost = adv.generate_batch(1, 40)
    filler = features_of(batch)[~CrowdOutAdversary.genuine_mask(batch)]
    assert len(filler) == 160 and cost.flows == 200
    assert (batch[TRUE_LABEL] == 1).all()                      # no label conflict anywhere
    seed_keys = {r.tobytes() for r in rows.astype("float64")}
    assert all(r.tobytes() in seed_keys for r in filler)       # every filler row is already trained on


def test_stale_filler_reuses_rows_once_the_family_runs_out(loop_data):
    rows = loop_data.seed_family_rows(_largest_seed_attack_family(loop_data))
    batch, _ = StaleReplayAdversary(rows, 1).generate_batch(1, 3 * len(rows))
    assert len(batch) == 3 * len(rows) and batch.attrs["resampled"]


def test_stale_filler_refuses_a_family_absent_from_seed_train(loop_data):
    # DoS Hulk is withheld from seed_train in this fixture (and on CICIDS2017)
    with pytest.raises(ValueError, match="no seed_train attack rows"):
        loop_data.seed_family_rows("DoS Hulk")
    old = LoopData(**{k: v for k, v in vars(loop_data).items() if k != "seed_family"})
    with pytest.raises(ValueError, match="predates"):
        old.seed_family_rows("DDoS")


def test_crowd_out_dilutes_genuine_rows_under_share_cap(loop_data):
    """Under ShareCap the honeypot's effective share is fixed, so every filler row
    takes weight from the genuine attack rows: genuine effective weight falls ~1/(1+m)."""
    res = {m: pd.DataFrame(_arm(loop_data, _crowd(loop_data, m), ShareCap(0.05),
                                scenario="s0crowd", ratio=0.3).rows) for m in (0.0, 4.0)}
    last = {m: d[(d["round"] == 2) & (d.threshold_mode == "fixed")].iloc[0] for m, d in res.items()}
    assert last[0.0].hp_effective_ratio == pytest.approx(0.05, abs=1e-6)
    assert last[4.0].hp_effective_ratio == pytest.approx(0.05, abs=1e-6)
    assert last[4.0].n_honeypot == pytest.approx(5 * last[0.0].n_honeypot, rel=0.01)
    assert last[4.0].hp_mean_weight == pytest.approx(last[0.0].hp_mean_weight / 5, rel=0.02)


# ------------------------------------------------------------------- NetFlow v2

def test_netflow_feature_set_is_valid_and_has_no_identifier_or_code():
    f = schema.check_feature_subset(schema.NETFLOW_V2_FEATURES)
    assert f[:5] == schema.COST_FEATURES and len(f) == 29
    raw = set(schema.NETFLOW_V2_COLUMN_MAP)
    assert not raw & set(schema.NETFLOW_V2_DROPPED)
    assert len(raw) + len(schema.NETFLOW_V2_DROPPED) == 43          # the full v2 field set
    assert set(f) <= schema.NONNEGATIVE_FEATURES
    with pytest.raises(ValueError):                                  # extension before canonical
        schema.check_feature_subset(schema.NETFLOW_V2_EXTENSION_FEATURES + schema.COST_FEATURES)


def _nf_frame(n_benign=400, n_attack=150, seed=0):
    rng = np.random.default_rng(seed)
    n = n_benign + 2 * n_attack
    df = pd.DataFrame({c: rng.integers(1, 1000, n) for c in
                       [*schema.NETFLOW_V2_COLUMN_MAP, *schema.NETFLOW_V2_DROPPED]})
    fam = ["Benign"] * n_benign + ["DDoS"] * n_attack + ["scanning"] * n_attack
    df["Attack"] = fam
    df["Label"] = [0 if a == "Benign" else 1 for a in fam]
    return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def test_netflow_loader_maps_converts_and_drops_inconsistent_rows(tmp_path):
    df = _nf_frame()
    df.loc[0, "Label"] = 1 - df.loc[0, "Label"]                      # family/label disagree
    df.to_csv(tmp_path / "NF-ToN-IoT-v2.csv", index=False)
    out = netflow_v2.load_raw_by_day("nf-ton-iot-v2", tmp_path)[netflow_v2.DAY]
    assert len(out) == len(df) - 1
    assert list(out.columns[:29]) == list(schema.NETFLOW_V2_FEATURES)
    kept = df.drop(index=0).reset_index(drop=True)
    assert np.allclose(out.flow_duration, kept.FLOW_DURATION_MILLISECONDS * 1e3)   # ms -> us
    assert np.array_equal(out.fwd_bytes, kept.IN_BYTES) and np.array_equal(out.bwd_packets, kept.OUT_PKTS)
    assert set(out.label) == {"BENIGN", "DDoS", "scanning"}
    assert not any(c.lower() in out.columns for c in schema.NETFLOW_V2_DROPPED)


def test_netflow_loader_reports_a_missing_column_instead_of_guessing(tmp_path):
    _nf_frame().drop(columns=["TCP_WIN_MAX_IN"]).to_csv(tmp_path / "NF-UNSW-NB15-v2.csv", index=False)
    with pytest.raises(ValueError, match="TCP_WIN_MAX_IN"):
        netflow_v2.load_raw_by_day("nf-unsw-nb15-v2", tmp_path)


def test_netflow_frames_partition_and_run_a_loop_arm(tmp_path):
    _nf_frame(n_benign=3000, n_attack=900).to_csv(tmp_path / "NF-CSE-CIC-IDS2018-v2.csv", index=False)
    raw = netflow_v2.load_raw_by_day("nf-cse-cic-ids2018-v2", tmp_path)
    data = build_partitions(raw, config=PartitionConfig(strategy="within_day_temporal"),
                            features=schema.NETFLOW_V2_FEATURES)
    ld = from_partitions(data, "nf", LoopDataConfig(seed_train_rows=2000, eval_benign_rows=500,
                                                    eval_attack_cap_per_family=100))
    assert ld.features == schema.NETFLOW_V2_FEATURES and ld.seed_x.shape[1] == 29
    adv = MimicryAdversary(ld.pool_benign_x, ld.normalizer, 0.0, 1)
    rows = run_arm(ld, adv, scenario="a1", model_kind="rf", seed=1,
                   config=LoopConfig(rounds=1, poison_ratio=0.2),
                   hyperparams={"n_estimators": 5, "max_depth": 4}).rows
    assert rows[-1]["n_honeypot"] > 0


def test_netflow_subsample_is_stratified_capped_and_keeps_file_order(tmp_path):
    from experiments.phaseR_netflow_subsample import subsample

    df = _nf_frame(n_benign=500, n_attack=300)
    df["row_id"] = np.arange(len(df))
    src = tmp_path / "NF-ToN-IoT-v2.csv"
    df.to_csv(src, index=False)
    rec = subsample(src, tmp_path / "out", attack_cap=100, benign_cap=200, seed=7, chunksize=97)
    out = pd.read_csv(tmp_path / "out" / src.name)
    assert out.Attack.value_counts().to_dict() == {"Benign": 200, "DDoS": 100, "scanning": 100}
    assert out.row_id.is_monotonic_increasing                       # file order preserved
    assert rec["rows_before"] == {"BENIGN": 500, "DDoS": 300, "scanning": 300}
    again = subsample(src, tmp_path / "out2", attack_cap=100, benign_cap=200, seed=7, chunksize=500)
    assert again["rows_after"] == rec["rows_after"]
    assert pd.read_csv(tmp_path / "out2" / src.name).row_id.tolist() == out.row_id.tolist()  # chunking-independent
    assert json.loads((tmp_path / "out" / "NF-ToN-IoT-v2.sampling.json").read_text())["seed"] == 7
