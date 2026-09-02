import numpy as np
import pytest

from dloop.features import schema
from dloop.features.normalize import Normalizer
from dloop.models import MODELS, ModelConfig, load_model, make_model
from dloop.models.base import train_val_split
from dloop.models.metrics import binary_metrics
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions

_KINDS = ["rf", "xgboost", "autoencoder"]
_FAST = {
    "rf": {"n_estimators": 40},
    "xgboost": {"n_estimators": 40},
    "autoencoder": {"epochs": 60},
}


@pytest.fixture(scope="module")
def data():
    return load_partitions(
        source="synthetic",
        synthetic_config=synthetic.SyntheticConfig(benign_per_day=2500, attack_per_class=500),
    )


@pytest.fixture(scope="module")
def xy(data):
    def arr(part):
        df = data[part]
        return (df[list(schema.CANONICAL_FEATURES)].to_numpy("float64"),
                df[schema.BINARY_LABEL].to_numpy("int64"))
    return arr


def _cfg(kind):
    return ModelConfig(kind=kind, seed=123, target_fpr=0.01, hyperparams=_FAST[kind])


@pytest.mark.parametrize("kind", _KINDS)
def test_determinism_identical_seed(kind, xy):
    Xtr, ytr = xy("seed_train")
    Xte, _ = xy("trusted_eval")
    a = make_model(_cfg(kind)).fit(Xtr, ytr)
    b = make_model(_cfg(kind)).fit(Xtr, ytr)
    assert np.array_equal(a.score_samples(Xte), b.score_samples(Xte))
    assert a.threshold_ == b.threshold_
    assert np.array_equal(a.predict(Xte), b.predict(Xte))


@pytest.mark.parametrize("kind", _KINDS)
def test_sample_weight_changes_the_model(kind, xy):
    Xtr, ytr = xy("seed_train")
    Xte, _ = xy("trusted_eval")
    base = make_model(_cfg(kind)).fit(Xtr, ytr)

    w = np.ones(len(ytr))
    if kind == "autoencoder":
        col = schema.CANONICAL_FEATURES.index("fwd_bytes")
        benign = ytr == 0
        w[benign & (Xtr[:, col] > np.median(Xtr[benign, col]))] = 0.0
    else:
        w[ytr == 1] = 0.0  # zero-weight the attack class entirely
    alt = make_model(_cfg(kind)).fit(Xtr, ytr, sample_weight=w)

    assert not np.array_equal(base.score_samples(Xte), alt.score_samples(Xte))
    assert np.mean(base.predict(Xte) != alt.predict(Xte)) > 0.0


@pytest.mark.parametrize("kind", _KINDS)
def test_sample_weight_is_not_optional_and_shape_checked(kind, xy):
    Xtr, ytr = xy("seed_train")
    with pytest.raises(ValueError):
        make_model(_cfg(kind)).fit(Xtr, ytr, sample_weight=np.ones(len(ytr) - 1))


@pytest.mark.parametrize("kind", _KINDS)
def test_save_load_roundtrip_preserves_predictions_and_threshold(kind, xy, tmp_path):
    Xtr, ytr = xy("seed_train")
    Xte, _ = xy("trusted_eval")
    m = make_model(_cfg(kind)).fit(Xtr, ytr)
    p = tmp_path / f"m_{kind}"
    m.save(p)
    r = load_model(p)
    assert r.threshold_ == m.threshold_
    assert np.array_equal(r.score_samples(Xte), m.score_samples(Xte))
    assert np.array_equal(r.predict(Xte), m.predict(Xte))
    meta = (p.with_suffix(p.suffix + ".meta.json"))
    assert meta.exists()


@pytest.mark.parametrize("kind", _KINDS)
def test_scaler_fit_on_train_split_only(kind, xy):
    Xtr, ytr = xy("seed_train")
    cfg = _cfg(kind)
    m = make_model(cfg).fit(Xtr, ytr)

    x_tr, *_ = train_val_split(Xtr, ytr, np.ones(len(ytr)),
                               val_fraction=cfg.val_fraction, seed=cfg.seed)
    expected = Normalizer.fit(x_tr)
    assert np.allclose(m.scaler_.center, expected.center)
    assert np.allclose(m.scaler_.scale, expected.scale)
    # and NOT equal to a scaler fit on the whole set (would be the leak)
    whole = Normalizer.fit(Xtr)
    assert not np.allclose(m.scaler_.center, whole.center)


@pytest.mark.parametrize("kind", _KINDS)
def test_threshold_hits_target_fpr_on_validation(kind, xy):
    Xtr, ytr = xy("seed_train")
    cfg = _cfg(kind)
    m = make_model(cfg).fit(Xtr, ytr)
    _, x_val, _, y_val, *_ = train_val_split(Xtr, ytr, np.ones(len(ytr)),
                                             val_fraction=cfg.val_fraction, seed=cfg.seed)
    fpr = binary_metrics(y_val, m.score_samples(x_val), m.threshold_)["fpr"]
    # discrete quantile on a finite benign sample: within a few /n of target
    assert fpr <= cfg.target_fpr + 0.01


def test_recalibrate_moves_threshold_and_caps_fpr(xy):
    Xtr, ytr = xy("seed_train")
    te_X, te_y = xy("trusted_eval")
    m = make_model(_cfg("rf")).fit(Xtr, ytr)
    before = m.threshold_
    m.calibrate_threshold(te_X[te_y == 0], te_y[te_y == 0])
    assert m.threshold_ != before
    # conservative calibration: FPR on the calibration benign set never exceeds target
    fpr = binary_metrics(te_y, m.score_samples(te_X), m.threshold_)["fpr"]
    assert fpr <= 0.01 + 1e-9


def test_no_model_uses_automatic_class_weighting():
    # guard the single-weight-channel rule against future edits
    for kind, klass in MODELS.items():
        m = make_model(ModelConfig(kind=kind, hyperparams=_FAST[kind]))
        if kind == "rf":
            assert m.clf.class_weight is None
        elif kind == "xgboost":
            assert m.clf.get_params().get("scale_pos_weight") in (None, 1.0)
