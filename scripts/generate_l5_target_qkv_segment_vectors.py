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

HIDDEN = 1536
KV_WIDTH = 256
HEADS = 12
KV_HEADS = 2
HEAD_DIM = 128
GQA_GROUPS = 6

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


def rsqrt_algorithm(value):
    word = bits(value)
    exponent = (word >> 23) & 0xFF
    fraction = word & 0x7FFFFF
    unbiased = exponent - 127
    odd = unbiased & 1
    even_exponent = unbiased - 1 if odd else unbiased
    normalized = np.float32(from_bits(((128 if odd else 127) << 23) | fraction))
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


def rmsnorm1536(vector, weight):
    total = np.float32(0)
    for chunk in range(96):
        squares = [mul(value, value) for value in vector[chunk * 16:(chunk + 1) * 16]]
        total = add(total, reduce16(squares))
    inverse = rsqrt_algorithm(
        add(mul(total, np.float32(1.0 / HIDDEN)), np.float32(1e-6))
    )
    return np.array(
        [mul(mul(vector[i], inverse), weight[i]) for i in range(HIDDEN)],
        dtype=np.float32,
    )


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


def add_bias(vector, bias):
    return np.array([add(vector[i], bias[i]) for i in range(len(vector))], dtype=np.float32)


def expand_gqa(vector):
    output = np.empty(HIDDEN, dtype=np.float32)
    for query_head in range(HEADS):
        kv_head = query_head // GQA_GROUPS
        output[query_head * HEAD_DIM:(query_head + 1) * HEAD_DIM] = vector[
            kv_head * HEAD_DIM:(kv_head + 1) * HEAD_DIM
        ]
    return output


def write_fp32(path, values):
    path.write_text("\n".join(f"{bits(value):08x}" for value in values) + "\n")


def write_bf16(path, values):
    path.write_text("\n".join(f"{int(value):04x}" for value in values) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0x1536A5E6)

    def random_input():
        return np.array([bf16_value(rng.uniform(-1, 1)) for _ in range(HIDDEN)], dtype=np.float32)

    def random_weight_matrix(columns):
        return np.fromiter(
            (bf16_bits(rng.uniform(-0.0625, 0.0625)) for _ in range(HIDDEN * columns)),
            dtype=np.uint16,
            count=HIDDEN * columns,
        ).reshape(HIDDEN, columns)

    previous = random_input()
    current = random_input()
    norm_weight = np.array([np.float32(rng.uniform(0.8, 1.2)) for _ in range(HIDDEN)])
    q_weight = random_weight_matrix(HIDDEN)
    k_weight = random_weight_matrix(KV_WIDTH)
    v_weight = random_weight_matrix(KV_WIDTH)
    q_bias = np.array([np.float32(rng.uniform(-0.125, 0.125)) for _ in range(HIDDEN)])
    k_bias = np.array([np.float32(rng.uniform(-0.125, 0.125)) for _ in range(KV_WIDTH)])
    v_bias = np.array([np.float32(rng.uniform(-0.125, 0.125)) for _ in range(KV_WIDTH)])

    norm_previous = rmsnorm1536(previous, norm_weight)
    norm_current = rmsnorm1536(current, norm_weight)
    q_raw = gemv(norm_current, q_weight)
    k_raw = [gemv(norm_previous, k_weight), gemv(norm_current, k_weight)]
    v_raw = [gemv(norm_previous, v_weight), gemv(norm_current, v_weight)]
    q_biased = add_bias(q_raw, q_bias)
    k_biased = [add_bias(value, k_bias) for value in k_raw]
    v_biased = [add_bias(value, v_bias) for value in v_raw]
    k_gqa = [expand_gqa(value) for value in k_biased]
    v_gqa = [expand_gqa(value) for value in v_biased]

    nodes = {
        "x_previous": previous,
        "x_current": current,
        "norm_weight": norm_weight,
        "norm_previous": norm_previous,
        "norm_current": norm_current,
        "q_bias": q_bias,
        "k_bias": k_bias,
        "v_bias": v_bias,
        "q_raw": q_raw,
        "k_raw": np.concatenate(k_raw),
        "v_raw": np.concatenate(v_raw),
        "q_biased": q_biased,
        "k_biased": np.concatenate(k_biased),
        "v_biased": np.concatenate(v_biased),
        "k_gqa": np.concatenate(k_gqa),
        "v_gqa": np.concatenate(v_gqa),
    }
    for name, values in nodes.items():
        write_fp32(args.out / f"{name}.memh", values)

    weight_offsets = {
        "q": {"offset": 0, "rows": HIDDEN, "columns": HIDDEN},
        "k": {"offset": HIDDEN * HIDDEN, "rows": HIDDEN, "columns": KV_WIDTH},
        "v": {
            "offset": HIDDEN * HIDDEN + HIDDEN * KV_WIDTH,
            "rows": HIDDEN,
            "columns": KV_WIDTH,
        },
    }
    flat_weights = np.concatenate((q_weight.flat, k_weight.flat, v_weight.flat))
    write_bf16(args.out / "weights_bf16.memh", flat_weights)

    manifest = {
        "model": "Qwen/Qwen2-1.5B-Instruct",
        "revision": "ba1cf1846d7df0a0591d6c00649f57e798519da8",
        "hidden": HIDDEN,
        "kv_width": KV_WIDTH,
        "heads": HEADS,
        "kv_heads": KV_HEADS,
        "head_dim": HEAD_DIM,
        "gqa_groups": GQA_GROUPS,
        "tokens": 2,
        "physical_array": [16, 32],
        "expected_array_steps": 122880,
        "weight_offsets": weight_offsets,
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
        "L5_TARGET_QKV_SEGMENT_VECTORS_PASS "
        f"nodes={len(nodes)} expected_array_steps={manifest['expected_array_steps']} "
        f"q_sha256={manifest['node_sha256']['q_biased']}"
    )


if __name__ == "__main__":
    main()
