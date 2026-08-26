#!/usr/bin/env python3
import argparse
import ctypes
import hashlib
import json
import math
import random
import struct
from pathlib import Path

import numpy as np

HIDDEN = 256
HEADS = 4
HEAD_DIM = 64
MLP = 512
CONTEXT = 2

libm = ctypes.CDLL("libm.so.6")
fmaf = libm.fmaf
fmaf.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float]
fmaf.restype = ctypes.c_float


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_bits(value):
    return struct.unpack("<f", struct.pack("<I", int(value)))[0]


def bf16_bits(value):
    word = bits(value)
    return ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) & 0xFFFF


def bf16_value(value):
    return np.float32(from_bits(bf16_bits(value) << 16))


def add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def mul(a, b):
    return np.float32(np.float32(a) * np.float32(b))


def fma(a, b, c):
    return np.float32(
        fmaf(
            ctypes.c_float(float(a)),
            ctypes.c_float(float(b)),
            ctypes.c_float(float(c)),
        )
    )


def reduce16(values):
    level = np.array(values, dtype=np.float32)
    while len(level) > 1:
        level = np.array(
            [add(level[i], level[i + 1]) for i in range(0, len(level), 2)],
            dtype=np.float32,
        )
    return level[0]


def gemv(vector, weights):
    vector_bf16 = np.array([bf16_value(value) for value in vector], dtype=np.float32)
    output = np.empty(weights.shape[1], dtype=np.float32)
    for column in range(weights.shape[1]):
        accumulator = np.float32(0)
        for row in range(weights.shape[0]):
            weight = np.float32(from_bits(int(weights[row, column]) << 16))
            accumulator = fma(vector_bf16[row], weight, accumulator)
        output[column] = accumulator
    return output


def rsqrt_algorithm(value):
    word = bits(value)
    exponent = (word >> 23) & 0xFF
    fraction = word & 0x7FFFFF
    unbiased = exponent - 127
    odd = unbiased & 1
    even_exponent = unbiased - 1 if odd else unbiased
    normalized = np.float32(
        from_bits(((128 if odd else 127) << 23) | fraction)
    )
    index = (odd << 4) | (fraction >> 19)
    low, step = ((1.0, 1.0 / 16.0) if not odd else (2.0, 1.0 / 8.0))
    x0 = low + (index & 15) * step
    x1 = x0 + step
    slope = np.float32(((1 / math.sqrt(x1)) - (1 / math.sqrt(x0))) / step)
    intercept = np.float32(1 / math.sqrt(x0) - float(slope) * x0)
    estimate = add(mul(slope, normalized), intercept)
    square = mul(estimate, estimate)
    term = add(np.float32(1.5), -mul(np.float32(0.5), mul(normalized, square)))
    scale = np.float32(from_bits((127 - even_exponent // 2) << 23))
    return mul(mul(estimate, term), scale)


def reciprocal_algorithm(value):
    word = bits(value)
    exponent = (word >> 23) & 0xFF
    fraction = word & 0x7FFFFF
    normalized = np.float32(from_bits((127 << 23) | fraction))
    index = fraction >> 19
    x0 = 1.0 + index / 16.0
    x1 = x0 + 1.0 / 16.0
    slope = np.float32(((1 / x1) - (1 / x0)) / (1.0 / 16.0))
    intercept = np.float32(1 / x0 - float(slope) * x0)
    estimate = add(mul(slope, normalized), intercept)
    refined = mul(estimate, add(np.float32(2.0), -mul(normalized, estimate)))
    return mul(refined, np.float32(from_bits((254 - exponent) << 23)))


def rmsnorm256(vector, weight, epsilon=np.float32(1e-5)):
    total = np.float32(0)
    for chunk in range(16):
        squares = [mul(value, value) for value in vector[chunk * 16:(chunk + 1) * 16]]
        total = add(total, reduce16(squares))
    mean = mul(total, np.float32(1.0 / 256.0))
    inverse = rsqrt_algorithm(add(mean, epsilon))
    return np.array(
        [mul(mul(vector[i], inverse), weight[i]) for i in range(HIDDEN)],
        dtype=np.float32,
    )


def exp2_pwl(value):
    value = np.float32(value)
    if value < -16:
        return np.float32(0)
    if value >= 0:
        return np.float32(1)
    index = max(0, min(255, math.floor(float(value) * 16) + 256))
    x0 = np.float32(index / 16 - 16)
    x1 = np.float32(x0 + np.float32(1.0 / 16.0))
    y0 = np.float32(np.exp2(x0))
    y1 = np.float32(np.exp2(x1))
    slope = np.float32((np.float64(y1) - np.float64(y0)) / (1.0 / 16.0))
    intercept = np.float32(np.float64(y0) - np.float64(slope) * np.float64(x0))
    return add(mul(slope, value), intercept)


def silu(value):
    exponential = exp2_pwl(
        mul(np.float32(-abs(float(value))), np.float32(1.4426950408889634))
    )
    base = mul(value, reciprocal_algorithm(add(np.float32(1), exponential)))
    return mul(base, exponential) if value < 0 else base


def rope(vector, position):
    output = vector.copy()
    for pair in range(HIDDEN // 2):
        angle = np.float32(0.03125 * (position + 1) * (pair + 1))
        cosine = np.float32(math.cos(float(angle)))
        sine = np.float32(math.sin(float(angle)))
        even = vector[2 * pair]
        odd = vector[2 * pair + 1]
        output[2 * pair] = add(mul(even, cosine), -mul(odd, sine))
        output[2 * pair + 1] = add(mul(even, sine), mul(odd, cosine))
    return output


def dot64_scaled(a, b):
    total = np.float32(0)
    for chunk in range(4):
        products = [mul(a[chunk * 16 + i], b[chunk * 16 + i]) for i in range(16)]
        total = add(total, reduce16(products))
    return mul(total, np.float32(0.125))


def online_attention(query, keys, values):
    m_values = np.empty(HEADS, dtype=np.float32)
    l_values = np.empty(HEADS, dtype=np.float32)
    numerator = np.empty(HIDDEN, dtype=np.float32)
    attention = np.empty(HIDDEN, dtype=np.float32)
    log2e = np.float32(1.4426950408889634)
    for head in range(HEADS):
        sl = slice(head * HEAD_DIM, (head + 1) * HEAD_DIM)
        score0 = dot64_scaled(query[sl], keys[0][sl])
        m_state = score0
        l_state = np.float32(1)
        o_state = values[0][sl].copy()
        score1 = dot64_scaled(query[sl], keys[1][sl])
        m_new = score1 if score1 > m_state else m_state
        alpha = exp2_pwl(mul(add(m_state, -m_new), log2e))
        beta = exp2_pwl(mul(add(score1, -m_new), log2e))
        l_state = add(mul(l_state, alpha), beta)
        o_state = np.array(
            [add(mul(o_state[i], alpha), mul(values[1][sl][i], beta)) for i in range(HEAD_DIM)],
            dtype=np.float32,
        )
        inverse_l = reciprocal_algorithm(l_state)
        normalized = np.array([mul(value, inverse_l) for value in o_state], dtype=np.float32)
        m_values[head] = m_new
        l_values[head] = l_state
        numerator[sl] = o_state
        attention[sl] = normalized
    return m_values, l_values, numerator, attention


def write_fp32(path, values):
    path.write_text("\n".join(f"{bits(value):08x}" for value in values) + "\n")


def write_bf16(path, values):
    path.write_text("\n".join(f"{int(value):04x}" for value in values) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0x256B10C)

    def random_input():
        return np.array([bf16_value(rng.uniform(-1, 1)) for _ in range(HIDDEN)], dtype=np.float32)

    def random_weights(rows, columns, scale=0.125):
        return np.array(
            [[bf16_bits(rng.uniform(-scale, scale)) for _ in range(columns)] for _ in range(rows)],
            dtype=np.uint16,
        )

    previous = random_input()
    current = random_input()
    norm_weight1 = np.array([np.float32(rng.uniform(0.8, 1.2)) for _ in range(HIDDEN)])
    norm_weight2 = np.array([np.float32(rng.uniform(0.8, 1.2)) for _ in range(HIDDEN)])
    weights = {
        "wq": random_weights(HIDDEN, HIDDEN),
        "wk": random_weights(HIDDEN, HIDDEN),
        "wv": random_weights(HIDDEN, HIDDEN),
        "wo": random_weights(HIDDEN, HIDDEN),
        "wg": random_weights(HIDDEN, MLP),
        "wu": random_weights(HIDDEN, MLP),
        "wd": random_weights(MLP, HIDDEN),
    }

    norm_previous = rmsnorm256(previous, norm_weight1)
    norm_current = rmsnorm256(current, norm_weight1)
    query = gemv(norm_current, weights["wq"])
    keys = [gemv(norm_previous, weights["wk"]), gemv(norm_current, weights["wk"])]
    values = [gemv(norm_previous, weights["wv"]), gemv(norm_current, weights["wv"])]
    query_rope = rope(query, 1)
    keys_rope = [rope(keys[0], 0), rope(keys[1], 1)]
    softmax_m, softmax_l, softmax_o, attention = online_attention(query_rope, keys_rope, values)
    oproj = gemv(attention, weights["wo"])
    residual1 = np.array([add(current[i], oproj[i]) for i in range(HIDDEN)], dtype=np.float32)
    norm2 = rmsnorm256(residual1, norm_weight2)
    gate = gemv(norm2, weights["wg"])
    up = gemv(norm2, weights["wu"])
    activated = np.array([silu(value) for value in gate], dtype=np.float32)
    product = np.array([mul(activated[i], up[i]) for i in range(MLP)], dtype=np.float32)
    down = gemv(product, weights["wd"])
    final = np.array([add(residual1[i], down[i]) for i in range(HIDDEN)], dtype=np.float32)

    nodes = {
        "x_previous": previous,
        "x_current": current,
        "norm_previous": norm_previous,
        "norm_current": norm_current,
        "q": query,
        "k": np.concatenate(keys),
        "v": np.concatenate(values),
        "q_rope": query_rope,
        "k_rope": np.concatenate(keys_rope),
        "softmax_m": softmax_m,
        "softmax_l": softmax_l,
        "softmax_o": softmax_o,
        "attention": attention,
        "oproj": oproj,
        "residual1": residual1,
        "norm2": norm2,
        "gate": gate,
        "up": up,
        "silu": activated,
        "gate_mul_up": product,
        "down": down,
        "final": final,
    }
    for name, values_node in nodes.items():
        write_fp32(args.out / f"{name}.memh", values_node)
    write_fp32(args.out / "norm_weight1.memh", norm_weight1)
    write_fp32(args.out / "norm_weight2.memh", norm_weight2)

    rope_coefficients = []
    for position in range(CONTEXT):
        for pair in range(HIDDEN // 2):
            angle = np.float32(0.03125 * (position + 1) * (pair + 1))
            rope_coefficients.extend(
                [np.float32(math.cos(float(angle))), np.float32(math.sin(float(angle)))]
            )
    write_fp32(args.out / "rope_coeff.memh", rope_coefficients)

    offsets = {}
    flat_weights = []
    for name, matrix in weights.items():
        offsets[name] = {
            "offset": len(flat_weights),
            "rows": int(matrix.shape[0]),
            "cols": int(matrix.shape[1]),
        }
        flat_weights.extend(int(value) for value in matrix.flat)
    write_bf16(args.out / "weights_bf16.memh", flat_weights)

    manifest = {
        "hidden": HIDDEN,
        "heads": HEADS,
        "head_dim": HEAD_DIM,
        "context": CONTEXT,
        "mlp": MLP,
        "physical_array": [16, 32],
        "array_steps": 24576,
        "score_matrix_materialized": False,
        "weight_offsets": offsets,
        "node_sha256": {
            name: hashlib.sha256((args.out / f"{name}.memh").read_bytes()).hexdigest()
            for name in nodes
        },
        "weights_sha256": hashlib.sha256(
            (args.out / "weights_bf16.memh").read_bytes()
        ).hexdigest(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "L5_HIDDEN256_BLOCK_VECTORS_PASS "
        f"nodes={len(nodes)} array_steps={manifest['array_steps']} "
        f"final_sha256={manifest['node_sha256']['final']}"
    )


if __name__ == "__main__":
    main()
