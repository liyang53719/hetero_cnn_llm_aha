import numpy as np

from heteronpu.dtypes import (
    bf16_round,
    dequantize_w4_grouped,
    pack_int4,
    quantize_w4_grouped,
    unpack_int4,
)


def test_bf16_round_is_idempotent() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=1000).astype(np.float32)
    once = bf16_round(x)
    twice = bf16_round(once)
    np.testing.assert_array_equal(once, twice)
    assert np.max(np.abs(x - once)) < 0.02


def test_signed_int4_pack_round_trip() -> None:
    values = np.arange(-8, 8, dtype=np.int8)
    packed = pack_int4(values)
    restored = unpack_int4(packed, values.size)
    np.testing.assert_array_equal(restored, values)


def test_grouped_w4_quantization_shape_and_error() -> None:
    rng = np.random.default_rng(2)
    weights = rng.normal(0, 0.2, size=(70, 13)).astype(np.float32)
    quantized = quantize_w4_grouped(weights, group_size=64)
    assert quantized.q.shape == (128, 13)
    assert quantized.scales.shape == (2, 13)
    restored = dequantize_w4_grouped(quantized)
    assert restored.shape == weights.shape
    assert float(np.mean(np.abs(restored - weights))) < 0.03
