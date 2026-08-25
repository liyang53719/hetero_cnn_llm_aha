import numpy as np

from heteronpu.dtypes import bf16_round
from heteronpu.matrix_engine import MatrixEngineModel
from heteronpu.workloads import direct_conv2d_nhwc


def test_int8_gemm_exact() -> None:
    rng = np.random.default_rng(3)
    a = rng.integers(-8, 8, size=(9, 17), dtype=np.int8)
    b = rng.integers(-8, 8, size=(17, 11), dtype=np.int8)
    model = MatrixEngineModel()
    got = model.gemm(a, b, mode="int8")
    expected = a.astype(np.int32) @ b.astype(np.int32)
    np.testing.assert_array_equal(got, expected)
    assert model.stats.macs == 9 * 17 * 11


def test_bf16_gemm_contract() -> None:
    rng = np.random.default_rng(4)
    a = rng.normal(size=(7, 15)).astype(np.float32)
    b = rng.normal(size=(15, 5)).astype(np.float32)
    expected = bf16_round(a) @ bf16_round(b)
    got = MatrixEngineModel().gemm(a, b, mode="bf16")
    np.testing.assert_allclose(got, expected, rtol=0, atol=0)


def test_w4a8_grouped_contract() -> None:
    rng = np.random.default_rng(5)
    a = rng.normal(0, 0.5, size=(8, 70)).astype(np.float32)
    b = rng.normal(0, 0.2, size=(70, 19)).astype(np.float32)
    model = MatrixEngineModel()
    qb = model.quantize_w4(b, group_size=64)
    got = model.gemm(a, qb, mode="w4a8")
    expected = a @ model.dequantize_w4(qb)
    # Both activation and weights are quantized in the engine contract.
    assert got.shape == expected.shape
    assert float(np.mean(np.abs(got - expected))) < 0.25


def test_im2col_convolution_matches_direct() -> None:
    rng = np.random.default_rng(6)
    x = rng.integers(-5, 6, size=(2, 7, 8, 3), dtype=np.int8)
    w = rng.integers(-4, 5, size=(3, 2, 3, 5), dtype=np.int8)
    bias = rng.integers(-10, 11, size=(5,), dtype=np.int32)
    expected = direct_conv2d_nhwc(x, w, stride=(2, 1), padding=(1, 1), bias=bias)
    got = MatrixEngineModel().conv2d_nhwc(
        x, w, stride=(2, 1), padding=(1, 1), mode="int8", bias=bias
    )
    np.testing.assert_array_equal(got, expected)
