import numpy as np

from heteronpu.cgra_sfu import CgraSfuModel


def test_online_softmax_matches_dense() -> None:
    rng = np.random.default_rng(7)
    x = rng.normal(size=131).astype(np.float32)
    got = CgraSfuModel.online_softmax_1d(x, block=17)
    expected = CgraSfuModel.softmax(x)
    np.testing.assert_allclose(got, expected, rtol=2e-6, atol=2e-7)
    np.testing.assert_allclose(np.sum(got), 1.0, rtol=0, atol=2e-6)


def test_rope_preserves_pair_norm() -> None:
    rng = np.random.default_rng(8)
    x = rng.normal(size=(12, 4, 16)).astype(np.float32)
    y = CgraSfuModel.rope(x)
    x_norm = np.sum(x.reshape(12, 4, 8, 2) ** 2, axis=-1)
    y_norm = np.sum(y.reshape(12, 4, 8, 2) ** 2, axis=-1)
    np.testing.assert_allclose(y_norm, x_norm, rtol=0.02, atol=0.03)


def test_rmsnorm_is_finite() -> None:
    x = np.zeros((3, 32), dtype=np.float32)
    w = np.ones(32, dtype=np.float32)
    y = CgraSfuModel.rmsnorm(x, w)
    assert np.all(np.isfinite(y))
    np.testing.assert_array_equal(y, np.zeros_like(y))
