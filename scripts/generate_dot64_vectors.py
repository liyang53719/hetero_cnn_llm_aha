#!/usr/bin/env python3
import argparse
import json
import random
import struct
from pathlib import Path

import numpy as np


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


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


def dot64(a, b, scale):
    total = np.float32(0)
    for chunk in range(4):
        products = [fp_mul(a[chunk * 16 + i], b[chunk * 16 + i]) for i in range(16)]
        total = fp_add(total, reduce16(products))
    return fp_mul(total, scale)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10000)
    args = parser.parse_args()
    rng = random.Random(0xD0764)
    lines = []
    max_absolute_error = 0.0
    for vector in range(args.count):
        if vector == 0:
            a = np.zeros(64, dtype=np.float32)
            b = np.zeros(64, dtype=np.float32)
        elif vector == 1:
            a = np.ones(64, dtype=np.float32)
            b = np.ones(64, dtype=np.float32)
        else:
            a = np.array([rng.uniform(-2, 2) for _ in range(64)], dtype=np.float32)
            b = np.array([rng.uniform(-2, 2) for _ in range(64)], dtype=np.float32)
        scale = np.float32((0.125, 0.25, 0.5, 1.0)[vector & 3])
        expected = dot64(a, b, scale)
        reference = float(np.dot(a.astype(np.float64), b.astype(np.float64))) * float(scale)
        max_absolute_error = max(max_absolute_error, abs(float(expected) - reference))
        record = 0
        for i, value in enumerate(a):
            record |= bits(value) << (i * 32)
        for i, value in enumerate(b):
            record |= bits(value) << (2048 + i * 32)
        record |= bits(scale) << 4096
        record |= bits(expected) << 4128
        lines.append(f"{record:01040x}")
    result = {
        "count": args.count,
        "lanes": 64,
        "chunks": 4,
        "max_absolute_error": max_absolute_error,
        "threshold": 5e-5,
        "threshold_pass": max_absolute_error <= 5e-5,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n")
    args.manifest.write_text(json.dumps(result, indent=2) + "\n")
    if not result["threshold_pass"]:
        raise SystemExit(f"DOT64_VECTOR_FAIL {result}")
    print(
        f"DOT64_VECTORS_PASS count={args.count} "
        f"max_abs={max_absolute_error:.9g}"
    )


if __name__ == "__main__":
    main()
