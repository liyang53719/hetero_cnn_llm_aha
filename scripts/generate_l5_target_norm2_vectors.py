#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import random
import struct
from pathlib import Path

import numpy as np

LANES = 1536
RESIDUAL_HASH = "df2d5af8926229b7c3ea34aa7c0dfc1ad381fee5cd7149d86b5b01739f518671"


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_bits(value):
    return np.float32(struct.unpack("<f", struct.pack("<I", int(value, 16)))[0])


def add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def mul(a, b):
    return np.float32(np.float32(a) * np.float32(b))


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
    normalized = np.float32(
        struct.unpack("<f", struct.pack("<I", ((128 if odd else 127) << 23) | fraction))[0]
    )
    index = (odd << 4) | (fraction >> 19)
    low, step = ((1.0, 1.0 / 16.0) if not odd else (2.0, 1.0 / 8.0))
    x0 = low + (index & 15) * step
    x1 = x0 + step
    slope = np.float32(((1 / math.sqrt(x1)) - (1 / math.sqrt(x0))) / step)
    intercept = np.float32(1 / math.sqrt(x0) - float(slope) * x0)
    estimate = add(mul(slope, normalized), intercept)
    term = add(
        np.float32(1.5),
        -mul(np.float32(0.5), mul(normalized, mul(estimate, estimate))),
    )
    scale = np.float32(
        struct.unpack("<f", struct.pack("<I", (127 - even_exponent // 2) << 23))[0]
    )
    return mul(mul(estimate, term), scale)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--residual", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    observed = hashlib.sha256(args.residual.read_bytes()).hexdigest()
    if observed != RESIDUAL_HASH:
        raise SystemExit(f"TARGET_NORM2_INPUT_HASH_FAIL {observed}")
    residual = np.array(
        [from_bits(line) for line in args.residual.read_text().splitlines()], dtype=np.float32
    )
    rng = random.Random(0xA02B1536)
    weight = np.array([np.float32(rng.uniform(0.8, 1.2)) for _ in range(LANES)])
    total = np.float32(0)
    for chunk in range(96):
        squares = [mul(value, value) for value in residual[chunk * 16:(chunk + 1) * 16]]
        total = add(total, reduce16(squares))
    inverse = rsqrt_algorithm(add(mul(total, np.float32(1.0 / LANES)), np.float32(1e-6)))
    norm2 = np.array(
        [mul(mul(residual[i], inverse), weight[i]) for i in range(LANES)],
        dtype=np.float32,
    )
    for name, values in (("weight", weight), ("norm2", norm2)):
        (args.out / f"{name}.memh").write_text(
            "\n".join(f"{bits(value):08x}" for value in values) + "\n"
        )
    manifest = {
        "residual1_sha256": RESIDUAL_HASH,
        "lanes": LANES,
        "chunks": 96,
        "epsilon_fp32_bits": "0x358637bd",
        "weight_sha256": hashlib.sha256((args.out / "weight.memh").read_bytes()).hexdigest(),
        "norm2_sha256": hashlib.sha256((args.out / "norm2.memh").read_bytes()).hexdigest(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"L5_TARGET_NORM2_VECTORS_PASS norm2_sha256={manifest['norm2_sha256']}")


if __name__ == "__main__":
    main()
