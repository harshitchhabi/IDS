import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.features.normalize import fit_normalizer


def _frame(n, rng):
    data = {f: rng.lognormal(3.0, 1.0, n) for f in schema.CANONICAL_FEATURES}
    return pd.DataFrame(data)


def test_transform_is_roughly_centered_and_scaled_on_fit_data():
    rng = np.random.default_rng(0)
    df = _frame(4000, rng)
    norm = fit_normalizer(df)
    x = norm.transform(df)
    assert x.shape == (4000, len(schema.CANONICAL_FEATURES))
    # median maps to ~0, IQR to ~1 by construction
    assert np.allclose(np.median(x, axis=0), 0.0, atol=1e-6)
    q75, q25 = np.percentile(x, [75, 25], axis=0)
    assert np.allclose(q75 - q25, 1.0, atol=1e-6)


def test_constant_feature_does_not_blow_up():
    rng = np.random.default_rng(1)
    df = _frame(500, rng)
    df["syn_flag_count"] = 0.0
    norm = fit_normalizer(df)
    x = norm.transform(df)
    assert np.isfinite(x).all()


def test_log1p_is_float64_path_so_transform_is_platform_independent():
    # Regression for the R1 determinism fix (DECISIONS §31.2): log1p must be computed
    # in float64 and rounded once to float32, not via numpy's SIMD-dispatched float32
    # log1p, which is 1 ulp off on some x86 builds and flips near-dup grid rows.
    from dloop.features.normalize import _log1p32

    rng = np.random.default_rng(7)
    x = rng.lognormal(3.0, 1.0, 50_000).astype("float32")
    expected = np.log1p(x.astype("float64")).astype("float32")
    got = _log1p32(x)
    # Bit-identical to the correctly-rounded float64 path, every input.
    assert np.array_equal(got.view("uint32"), expected.view("uint32"))
