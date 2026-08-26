#!/usr/bin/env python3
import argparse
import json
import math
import random
import struct
from pathlib import Path

import numpy as np

LANES = 1536
CHUNKS = 96


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_bits(value):
    return struct.unpack("<f", struct.pack("<I", int(value)))[0]


def fp_add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def fp_mul(a, b):
    return np.float32(np.float32(a) * np.float32(b))


def reduce16(values):
    level = np.array(values, dtype=np.float32)
    while len(level) > 1:
        level = np.array(
            [fp_add(level[i], level[i + 1]) for i in range(0, len(level), 2)],
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
    estimate = fp_add(fp_mul(slope, normalized), intercept)
    square = fp_mul(estimate, estimate)
    term = fp_add(
        np.float32(1.5),
        -fp_mul(np.float32(0.5), fp_mul(normalized, square)),
    )
    scale = np.float32(from_bits((127 - even_exponent // 2) << 23))
    return fp_mul(fp_mul(estimate, term), scale)


def rmsnorm(vector, weight, epsilon):
    total = np.float32(0)
    for chunk in range(CHUNKS):
        squares = [
            fp_mul(value, value)
            for value in vector[chunk * 16:(chunk + 1) * 16]
        ]
        total = fp_add(total, reduce16(squares))
    mean = fp_mul(total, np.float32(1.0 / LANES))
    inverse = rsqrt_algorithm(fp_add(mean, epsilon))
    return np.array(
        [fp_mul(fp_mul(vector[i], inverse), weight[i]) for i in range(LANES)],
        dtype=np.float32,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    rng = random.Random(0x1536726D)
    epsilon = np.float32(1e-6)
    lines = []
    max_absolute_error = 0.0
    for vector_index in range(args.count):
        if vector_index == 0:
            vector = np.zeros(LANES, dtype=np.float32)
        elif vector_index == 1:
            vector = np.full(LANES, np.float32(0.001), dtype=np.float32)
        elif vector_index == 2:
            vector = np.array([(-1) ** i * 32 for i in range(LANES)], dtype=np.float32)
        else:
            vector = np.array([rng.uniform(-8, 8) for _ in range(LANES)], dtype=np.float32)
        weight = np.array([rng.uniform(0.5, 1.5) for _ in range(LANES)], dtype=np.float32)
        expected = rmsnorm(vector, weight, epsilon)
        reference = vector.astype(np.float64) * weight.astype(np.float64) / math.sqrt(
            float(np.mean(vector.astype(np.float64) ** 2)) + float(epsilon)
        )
        max_absolute_error = max(
            max_absolute_error,
            float(np.max(np.abs(expected.astype(np.float64) - reference))),
        )
        record = 0
        for i, value in enumerate(vector):
            record |= bits(value) << (i * 32)
        for i, value in enumerate(weight):
            record |= bits(value) << (49152 + i * 32)
        record |= bits(epsilon) << 98304
        for i, value in enumerate(expected):
            record |= bits(value) << (98336 + i * 32)
        lines.append(f"{record:036872x}")
    result = {
        "count": args.count,
        "lanes": LANES,
        "chunks": CHUNKS,
        "mean_scale_fp32_bits": "0x3a2aaaab",
        "epsilon_fp32_bits": f"0x{bits(epsilon):08x}",
        "max_absolute_error": max_absolute_error,
        "threshold": 2e-5,
        "threshold_pass": max_absolute_error <= 2e-5,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n")
    args.manifest.write_text(json.dumps(result, indent=2) + "\n")
    if not result["threshold_pass"]:
        raise SystemExit(f"RMS1536_VECTOR_FAIL {result}")
    print(
        f"RMS1536_VECTORS_PASS count={args.count} "
        f"max_abs={max_absolute_error:.9g}"
    )


if __name__ == "__main__":
    main()
