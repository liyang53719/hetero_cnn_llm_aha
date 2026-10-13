"""Independent FP32 graph for H2048, with final BF16 RNE materialization.

This vectorized host diagnostic is not a memory owner or a hardware model.
There is no input-specific correction, alternate reference output, or epsilon
adjustment. Every accumulation, multiply, sqrt and divide rounds to FP32.
"""
from __future__ import annotations

import numpy as np

from .reference import EPS, WIDTH, validate_raw


class NumericDomainError(ValueError):
    pass


def decode(raw, shape):
    return (np.frombuffer(raw, "<u2").astype("<u4") << 16).view("<f4").reshape(shape)


def bf16(values):
    bits = np.asarray(values, dtype="<f4").view("<u4")
    return ((bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) >> 16).astype("<u2").tobytes()


def formula(hidden, weight, tokens, *, reduction="torch210_cpu_default2048"):
    validate_raw(hidden, weight, tokens)
    if reduction not in ("torch210_cpu_default2048", "legacy_ascending"):
        raise ValueError("35B RMS: unknown reduction")
    x, w = decode(hidden, (1, tokens, WIDTH)), decode(weight, (WIDTH,))
    trace = {"input_fp32": x, "weight_fp32": w}

    def record(name, value):
        if not np.isfinite(value).all():
            raise NumericDomainError("nonfinite " + name)
        trace[name] = value
        return value

    add = lambda a, b: np.add(a, b, dtype=np.float32)
    mul = lambda a, b: np.multiply(a, b, dtype=np.float32)
    with np.errstate(all="ignore"):
        squares = record("squares", mul(x, x))
        total = np.zeros((1, tokens, 1), dtype=np.float32)
        if reduction == "legacy_ascending":
            for i in range(WIDTH):
                total = add(total, squares[..., i:i + 1])
        else:
            for lane in range(8):
                lane_sum = np.zeros_like(total)
                for residue in range(4):
                    residue_sum = np.zeros_like(total)
                    for block in range(4):
                        partial = np.zeros_like(total)
                        for term in range(16):
                            i = block * 512 + term * 32 + residue * 8 + lane
                            partial = add(partial, squares[..., i:i + 1])
                        residue_sum = add(residue_sum, partial)
                    lane_sum = add(lane_sum, residue_sum)
                total = add(total, lane_sum)
        record("sum", total)
        mean = record("mean", mul(total, np.float32(1 / WIDTH)))
        variance = record("mean_eps", add(mean, np.float32(EPS)))
        root = record("root", np.sqrt(variance, dtype=np.float32))
        inverse = record("inverse", np.divide(np.float32(1), root, dtype=np.float32))
        normalized = record("scaled", mul(x, inverse))
        gamma = record("gamma", add(np.float32(1), w))
        result = record("weighted", mul(normalized, gamma))
        output = bf16(result)
        if np.any((np.frombuffer(output, "<u2") & 0x7f80) == 0x7f80):
            raise NumericDomainError("nonfinite final BF16 conversion")
    return dict(output=output, trace=trace, reduction=reduction,
                scalar_exception_policy_executed=False, full_native_forward=False, rtl_executed=False)
