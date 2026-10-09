"""Independent fixed-order BF16 oracle for the pinned 0.8B causal GQA core.

The upstream operation boundaries are modeling_qwen3_5.py:714-811, but its
backend reduction tree and native exp are NOT this arithmetic contract. QK and
PV use increasing-index, exact integer binary32 FMA from +0, then BF16 RNE.
The shared BlockScalarFloat degree-7 exp uses separate FP32 multiply/add steps.
Passing this oracle is not native producer accuracy, RTL, timing, or QoR proof;
qwen35_bf16_reference.producer_compare remains the separate, unchanged gate.

Only finite operands/results are admitted. Finite FMA/multiply/BF16 underflow
is gradual; scalar add/subtract underflow is rejected like the shared service.
Unmasked score differences <= -80 are rejected, never silently saturated.
With at most 256 keys this exp domain also keeps division results normal FP32.
The inactive capacity suffix is never read, including for operand validation.
No checkpoints, captured native intermediates, or simulator results are inputs.
"""
from __future__ import annotations

import math

import numpy as np

from .matrix_norm_rope_candidate import fma_rne
from .model_geometry import require
from .qwen35_bf16_reference import require_bf16
from .rope_bf16_candidate import EXPONENT, SIGN, UF, add_rne, bf16_convert, mul_rne

POLICY = "qwen35_causal_gqa_sequential_fma_bf16_shared_exp7_v1"
QUERY_HEADS, KV_HEADS, HEAD_DIM = 8, 2, 256
MAX_TOKENS, MAX_CAPACITY = 128, 256


def _word(value):
    return int(np.asarray(value, dtype=np.float32).view(np.uint32))


def _float(word):
    return np.asarray(word, dtype=np.uint32).view(np.float32)[()]


def _finite(word, operation):
    require(word & EXPONENT != EXPONENT, operation + ": nonfinite result")
    return word


def _add(a, b):
    word, flags = add_rne(a, b)
    _finite(word, "scalar add/subtract")
    require(not flags & UF, "scalar add/subtract: underflow")
    return word


def _mul(a, b):
    return _finite(mul_rne(a, b)[0], "scalar multiply")


def _bf16(word):
    return _finite(bf16_convert(word)[0], "terminal BF16 conversion")


_EXP_COEFFICIENTS = tuple(_word((-math.log(2.0)) ** i / math.factorial(i)) for i in range(8))
_LOG2_E = _word(1.0 / math.log(2.0))
_SCALE = _word(1.0 / 16.0)


def exp_negative_recipe(value):
    """Scalar shared exp(-abs(x)), rejecting its unsupported saturation range.

    Each Horner product and addition rounds separately to FP32; no fused
    polynomial evaluation, np.exp, or native softmax is used.
    """
    value = np.asarray(value)
    require(value.shape == () and value.dtype == np.float32 and np.isfinite(value),
            "exp requires a finite FP32 scalar")
    require(-80 < value <= 0, "exp difference must satisfy -80 < difference <= 0")
    scaled = _mul(_word(value) & ~SIGN, _LOG2_E)
    integer = int(_float(scaled))
    fraction = _add(scaled, _word(integer) ^ SIGN)
    horner = _EXP_COEFFICIENTS[7]
    for index in range(6, -1, -1):
        horner = _add(_mul(horner, fraction), _EXP_COEFFICIENTS[index])
    result = _float(_mul(horner, (127 - integer) << 23))
    require(result > 0 and result <= 1, "exp result outside (0,1]")
    return result


def _dot_words(left, right):
    """Every term, including zero products, executes one increasing-index FMA."""
    accumulator = 0
    for a, b in zip(left, right, strict=True):
        accumulator, _ = fma_rne(int(a), int(b), accumulator)
        _finite(accumulator, "sequential FMA")
    return accumulator


def dot_bf16(left, right):
    """A bounded BF16 dot: return (final FP32, terminal decoded BF16).

    This small public arithmetic witness is useful for cancellation/order and
    subnormal tests. No per-step trace files or weights are produced.
    """
    left, right = require_bf16(left, "left"), require_bf16(right, "right")
    require(left.ndim == 1 and left.shape == right.shape and 1 <= left.size <= MAX_CAPACITY,
            "dot requires matching vectors with 1..256 elements")
    accumulator = _dot_words(left.view(np.uint32), right.view(np.uint32))
    return _float(accumulator), _float(_bf16(accumulator))


def softmax_row(logits, allowed, *, return_trace=False):
    """Stable softmax for one BF16-logit row; masked probabilities are exact +0.

    The maximum, domain check and exp use allowed entries only. Summation and
    division visit increasing key indices, with explicit +0 masked exp values.
    A wholly masked row is invalid, rather than a fabricated distribution.
    """
    logits = require_bf16(logits, "logits")
    allowed = np.asarray(allowed)
    require(logits.ndim == 1 and 1 <= logits.size <= MAX_CAPACITY,
            "softmax row requires 1..256 logits")
    require(allowed.dtype == np.bool_ and allowed.shape == logits.shape,
            "softmax allowed mask must be a matching bool vector")
    require(bool(allowed.any()), "fully masked softmax row")
    maximum = None
    for key in range(logits.size):
        if allowed[key] and (maximum is None or logits[key] > maximum):
            maximum = logits[key]
    differences = np.zeros_like(logits)
    exponentials = np.zeros_like(logits)
    total_word = 0
    for key in range(logits.size):
        if allowed[key]:
            differences[key] = _float(_add(_word(logits[key]), _word(maximum) ^ SIGN))
            exponentials[key] = exp_negative_recipe(differences[key])
        total_word = _add(total_word, _word(exponentials[key]))
    total = _float(total_word)
    require(1 <= total <= MAX_CAPACITY, "softmax denominator outside [1,256]")
    probabilities = np.zeros_like(logits)
    fp32_probabilities = np.zeros_like(logits)
    for key in range(logits.size):
        # The admitted exp domain and denominator bound prove normal nonzero
        # quotients. Check explicitly so Div's UF rejection cannot be hidden.
        probability = np.divide(exponentials[key], total, dtype=np.float32)
        require(np.isfinite(probability), "softmax division: nonfinite result")
        require(probability == 0 or probability >= np.finfo(np.float32).tiny,
                "softmax division: underflow")
        fp32_probabilities[key] = probability
        probabilities[key] = _float(_bf16(_word(probability)))
    if return_trace:
        return probabilities, {"maximum_fp32": maximum, "differences_fp32": differences,
                               "exp_fp32": exponentials, "sum_fp32": total,
                               "probabilities_fp32": fp32_probabilities}
    return probabilities


def causal_gqa(query, cache, *, query_start, cache_length, return_trace=False):
    """Compute flattened decoded BF16 output [tokens,2048] without changing inputs.

    query: float32 containers of exact BF16 values, shape [tokens,8,256].
    cache: same storage, shape [2,capacity,512]; plane 0 is K, plane 1 is V.
    Each 512-wide row contains KV head 0 then KV head 1. Query head h maps to
    KV head h//4. The existing prefix is supplied by the caller in this cache;
    it is neither synthesized nor replaced by a captured reference output.
    Descriptors require 1<=tokens<=128 and query_start+tokens=cache_length,
    with 1<=cache_length<=capacity<=256. Only k<=query_start+row is visible.

    Optional traces hold producer boundaries in memory, never raw step files.
    QK includes all live keys; nonfinite masked QK results also fail closed.
    PV visits all live keys, including future keys with zero probability.
    """
    query = require_bf16(query, "query")
    cache = np.asarray(cache)
    require(query.ndim == 3 and query.shape[1:] == (QUERY_HEADS, HEAD_DIM),
            "query shape must be [tokens,8,256]")
    tokens = query.shape[0]
    require(1 <= tokens <= MAX_TOKENS, "tokens must be in 1..128")
    require(cache.dtype == np.float32 and cache.ndim == 3 and cache.shape[0] == 2
            and cache.shape[2] == KV_HEADS * HEAD_DIM, "cache shape/dtype must be FP32 [2,capacity,512]")
    capacity = cache.shape[1]
    require(1 <= capacity <= MAX_CAPACITY, "capacity must be in 1..256")
    require(type(query_start) is int and type(cache_length) is int,
            "query_start/cache_length must be integers")
    require(query_start >= 0 and 1 <= cache_length <= capacity
            and query_start + tokens == cache_length, "query_start/tokens/cache_length mismatch")
    live = require_bf16(cache[:, :cache_length, :], "active cache")
    q_words, cache_words = query.view(np.uint32), live.view(np.uint32)
    output_words = np.empty(query.shape, dtype=np.uint32)
    score_shape = (tokens, QUERY_HEADS, cache_length)
    trace = {}
    if return_trace:
        for field in ("qk_fp32", "qk_bf16", "logits_bf16", "probabilities_bf16"):
            trace[field] = np.empty(score_shape, dtype=np.float32)
        trace["pv_fp32"] = np.empty(query.shape, dtype=np.float32)
        trace["allowed"] = np.arange(cache_length)[None, :] <= query_start + np.arange(tokens)[:, None]
    for row in range(tokens):
        allowed = np.arange(cache_length) <= query_start + row
        for head in range(QUERY_HEADS):
            start = (head // 4) * HEAD_DIM
            end = start + HEAD_DIM
            logits = np.empty(cache_length, dtype=np.float32)
            for key in range(cache_length):
                qk = _dot_words(q_words[row, head], cache_words[0, key, start:end])
                rounded_qk = _bf16(qk)
                logits[key] = _float(_bf16(_mul(rounded_qk, _SCALE)))
                if return_trace:
                    trace["qk_fp32"][row, head, key] = _float(qk)
                    trace["qk_bf16"][row, head, key] = _float(rounded_qk)
            probabilities = softmax_row(logits, allowed)
            probability_words = probabilities.view(np.uint32)
            for channel in range(HEAD_DIM):
                accumulator = _dot_words(probability_words, cache_words[1, :, start + channel])
                output_words[row, head, channel] = _bf16(accumulator)
                if return_trace:
                    trace["pv_fp32"][row, head, channel] = _float(accumulator)
            if return_trace:
                trace["logits_bf16"][row, head] = logits
                trace["probabilities_bf16"][row, head] = probabilities
    output = output_words.view(np.float32).reshape(tokens, QUERY_HEADS * HEAD_DIM)
    if return_trace:
        trace["output_bf16"] = output.reshape(query.shape).copy()
        trace["policy"] = POLICY
        return output, trace
    return output


def fixed_compare(actual, expected):
    """Bit equality to this fixed arithmetic only, including signed-zero bits."""
    actual, expected = require_bf16(actual, "actual"), require_bf16(expected, "expected")
    require(actual.shape == expected.shape and actual.size > 0, "fixed comparison shape/empty")
    different = int(np.count_nonzero(actual.view(np.uint32) != expected.view(np.uint32)))
    return {"elements": int(actual.size), "bit_mismatches": different, "pass": different == 0,
            "scope": POLICY, "native_producer_accuracy_established": False}
