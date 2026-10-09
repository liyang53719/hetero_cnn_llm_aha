"""Small synthetic arithmetic checks only: no weights, raw traces, or RTL."""
import numpy as np
import pytest

from heteronpu import qwen35_gqa_fixed_reference as reference
from heteronpu.model_geometry import ModelContractError
from heteronpu.qwen35_bf16_reference import bf16, producer_compare


def inputs(tokens=1, capacity=1):
    return (np.zeros((tokens, 8, 256), np.float32),
            np.zeros((2, capacity, 512), np.float32))


def test_causal_boundary_keeps_self_and_zeroes_future_probability():
    query, cache = inputs(tokens=2, capacity=2)
    query[0, :, 0] = 1
    cache[0, 1, [0, 256]] = 2048  # A masked +128 score must not set row-0 max.
    cache[1, 0] = 2
    cache[1, 1] = 6
    output, trace = reference.causal_gqa(query, cache, query_start=0, cache_length=2, return_trace=True)
    assert output.shape == (2, 2048) and output.dtype == np.float32
    np.testing.assert_array_equal(output[0], np.full(2048, 2, np.float32))
    np.testing.assert_array_equal(output[1], np.full(2048, 4, np.float32))
    np.testing.assert_array_equal(trace["probabilities_bf16"][0, :, 1].view(np.uint32), np.zeros(8, np.uint32))
    np.testing.assert_array_equal(trace["allowed"], [[True, False], [True, True]])


def test_four_query_heads_share_each_actual_kv_head():
    query, cache = inputs(capacity=2)
    query[:, :, 0] = 1
    cache[0, 1, 0], cache[0, 1, 256] = 16, -16
    cache[1, 0, :256], cache[1, 1, :256] = 2, 10
    cache[1, 0, 256:], cache[1, 1, 256:] = 20, 40
    output, trace = reference.causal_gqa(query, cache, query_start=1, cache_length=2, return_trace=True)
    heads = output.reshape(1, 8, 256)[0]
    np.testing.assert_array_equal(trace["logits_bf16"][0, :4], np.tile([0, 1], (4, 1)))
    np.testing.assert_array_equal(trace["logits_bf16"][0, 4:], np.tile([0, -1], (4, 1)))
    for first, last in ((0, 4), (4, 8)):
        np.testing.assert_array_equal(heads[first:last], np.tile(heads[first], (4, 1)))
    # Independent native-exp estimate is only a loose diagnostic here.
    np.testing.assert_allclose(heads[0], (2 + 10 * np.exp(1)) / (1 + np.exp(1)), atol=.05, rtol=0)
    np.testing.assert_allclose(heads[4], (20 + 40 * np.exp(-1)) / (1 + np.exp(-1)), atol=.1, rtol=0)


def test_carried_query_consumes_real_prefix_and_does_not_mutate_cache():
    cold_query, cache = inputs(tokens=2, capacity=3)
    cache[1, 0], cache[1, 1], cache[1, 2] = 1, 3, 8
    original = cache.copy()
    cold = reference.causal_gqa(cold_query, cache, query_start=0, cache_length=2)
    carried = reference.causal_gqa(cold_query[:1], cache, query_start=2, cache_length=3)
    without_prefix = reference.causal_gqa(cold_query[:1], cache[:, 2:3], query_start=0, cache_length=1)
    np.testing.assert_array_equal(cold[-1], np.full(2048, 2, np.float32))
    np.testing.assert_array_equal(carried[0], np.full(2048, 4, np.float32))
    np.testing.assert_array_equal(without_prefix[0], np.full(2048, 8, np.float32))
    np.testing.assert_array_equal(cache.view(np.uint32), original.view(np.uint32))


def test_inactive_capacity_padding_is_never_an_operand():
    query, cache = inputs(capacity=256)
    cache[1, 0] = 7
    cache[:, 1:] = np.nan
    padded = reference.causal_gqa(query, cache, query_start=0, cache_length=1)
    compact = reference.causal_gqa(query, cache[:, :1], query_start=0, cache_length=1)
    assert reference.fixed_compare(padded, compact)["pass"]
    np.testing.assert_array_equal(padded, np.full((1, 2048), 7, np.float32))


def test_fully_masked_row_is_rejected():
    with pytest.raises(ModelContractError, match="fully masked"):
        reference.softmax_row(np.zeros(2, np.float32), np.zeros(2, bool))


@pytest.mark.parametrize("difference", [-80, -81, -128])
def test_unmasked_saturation_domain_is_rejected_but_masked_entry_is_zero(difference):
    logits = np.array([0, difference], np.float32)
    with pytest.raises(ModelContractError, match="-80 <"):
        reference.softmax_row(logits, np.ones(2, bool))
    probability = reference.softmax_row(logits, np.array([True, False]))
    np.testing.assert_array_equal(probability.view(np.uint32), [0x3F800000, 0])


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("operand", ["query", "key", "value"])
def test_nonfinite_live_operands_fail_closed(value, operand):
    query, cache = inputs()
    if operand == "query":
        query[0, 0, 0] = value
    else:
        cache[0 if operand == "key" else 1, 0, 0] = value
    with pytest.raises(ModelContractError, match="finite decoded BF16"):
        reference.causal_gqa(query, cache, query_start=0, cache_length=1)


@pytest.mark.parametrize("start,length", [(0, 2), (1, 1), (-1, 1), (0, 0), (True, 1), (0, 1.0), (np.int64(0), 1)])
def test_invalid_or_mismatched_descriptors_are_rejected(start, length):
    query, cache = inputs(capacity=2)
    with pytest.raises(ModelContractError):
        reference.causal_gqa(query, cache, query_start=start, cache_length=length)


@pytest.mark.parametrize("tokens,capacity", [(0, 1), (129, 129), (1, 0), (1, 257)])
def test_token_and_capacity_bounds(tokens, capacity):
    query, cache = inputs(tokens, capacity)
    with pytest.raises(ModelContractError):
        reference.causal_gqa(query, cache, query_start=0, cache_length=tokens)


def test_wrong_geometry_dtype_and_unrounded_operands_are_rejected():
    query, cache = inputs()
    for q, kv in ((query[:, :7], cache), (query, cache[:, :, :256]),
                  (query.astype(np.float64), cache), (query, cache.astype(np.float64))):
        with pytest.raises(ModelContractError):
            reference.causal_gqa(q, kv, query_start=0, cache_length=1)
    query[0, 0, 0] = np.nextafter(np.float32(1), np.float32(2))
    with pytest.raises(ModelContractError, match="unrounded"):
        reference.causal_gqa(query, cache, query_start=0, cache_length=1)


def test_sequential_qk_order_is_not_an_exact_or_reassociated_sum():
    query, cache = inputs()
    query[:, :, :3] = 1
    cache[0, 0, :3] = [2**24, 1, -(2**24)]
    cache[0, 0, 256:259] = cache[0, 0, :3]
    _, trace = reference.causal_gqa(query, cache, query_start=0, cache_length=1, return_trace=True)
    np.testing.assert_array_equal(trace["qk_fp32"], np.zeros((1, 8, 1), np.float32))
    ordered, _ = reference.dot_bf16(np.array([2**24, 1, -(2**24)], np.float32), np.ones(3, np.float32))
    regrouped, _ = reference.dot_bf16(np.array([2**24, -(2**24), 1], np.float32), np.ones(3, np.float32))
    assert ordered == 0 and regrouped == 1


def test_pv_uses_increasing_key_order_with_terminal_bf16_only():
    query, cache = inputs(capacity=3)
    cache[1, 0], cache[1, 1], cache[1, 2] = 2**30, 1, -(2**30)
    out, trace = reference.causal_gqa(query, cache, query_start=2, cache_length=3, return_trace=True)
    np.testing.assert_array_equal(out, np.zeros((1, 2048), np.float32))
    np.testing.assert_array_equal(trace["probabilities_bf16"], np.full((1, 8, 3), bf16(np.float32(1 / 3)), np.float32))
    reordered = reference.causal_gqa(query, cache[:, [0, 2, 1]], query_start=2, cache_length=3)
    np.testing.assert_array_equal(reordered, np.full((1, 2048), bf16(np.float32(1 / 3)), np.float32))


def test_fma_is_fused_and_allows_gradual_underflow():
    smallest_bf16 = np.array([0x00010000], np.uint32).view(np.float32)[0]
    accumulated, rounded = reference.dot_bf16(np.array([smallest_bf16] * 2, np.float32),
                                             np.array([2**-16, 2**-17], np.float32))
    # 1 + 1/2 minimum FP32 subnormals ties to even 2; separate mul/add gives 1.
    assert accumulated.view(np.uint32) == 2
    assert rounded.view(np.uint32) == 0


def test_fp32_fma_and_terminal_bf16_overflow_are_rejected():
    largest = np.array([0x7F7F0000], np.uint32).view(np.float32)
    with pytest.raises(ModelContractError, match="sequential FMA: nonfinite"):
        reference.dot_bf16(largest, np.array([2], np.float32))
    # The FP32 sum is finite but rounds past the greatest finite BF16 value.
    with pytest.raises(ModelContractError, match="terminal BF16.*nonfinite"):
        reference.dot_bf16(np.array([largest[0], 2**119], np.float32), np.ones(2, np.float32))


def test_shared_exp7_rounding_and_normal_smallest_admitted_probability():
    # Independent separately-rounded published recipe, not native exp.
    from heteronpu.qwen35_gdn_recurrent_fp32 import exp_negative_recipe
    for value in np.array([-0., 0., -.5, -1, -2.25, -79.5], np.float32):
        expected = exp_negative_recipe(value)
        assert reference.exp_negative_recipe(value).view(np.uint32) == expected.view(np.uint32)
    logits = np.zeros(256, np.float32)
    logits[-1] = -79.5
    _, trace = reference.softmax_row(logits, np.ones(256, bool), return_trace=True)
    assert trace["probabilities_fp32"][-1] >= np.finfo(np.float32).tiny


def test_fixed_equality_is_separate_from_unchanged_native_thresholds():
    a, b = np.array([0.], np.float32), np.array([-0.], np.float32)
    comparison = reference.fixed_compare(a, b)
    assert comparison["bit_mismatches"] == 1 and not comparison["pass"]
    assert comparison["native_producer_accuracy_established"] is False
    native = producer_compare(np.array([.0625], np.float32), a)
    assert not native["pass"]
    assert native["max_abs_limit"] == .03125 and native["mean_abs_limit"] == .005
