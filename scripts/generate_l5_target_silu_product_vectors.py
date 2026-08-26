#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

LANES = 8960
GATE_HASH = "ec204a74ad5bc7b68f34595ac7b24ffac5ca432de41077857476e92de6f1bcab"
UP_HASH = "581709c8d740185c32f457470a1965102e648ac0dacedf14191fbb836a7a98ac"


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_bits(value):
    return np.float32(struct.unpack("<f", struct.pack("<I", int(value, 16)))[0])


def add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def mul(a, b):
    return np.float32(np.float32(a) * np.float32(b))


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


def reciprocal(value):
    word = bits(value)
    exponent = (word >> 23) & 0xFF
    fraction = word & 0x7FFFFF
    normalized = np.float32(struct.unpack("<f", struct.pack("<I", (127 << 23) | fraction))[0])
    index = fraction >> 19
    x0 = 1.0 + index / 16.0
    x1 = x0 + 1.0 / 16.0
    slope = np.float32(((1 / x1) - (1 / x0)) / (1.0 / 16.0))
    intercept = np.float32(1 / x0 - float(slope) * x0)
    estimate = add(mul(slope, normalized), intercept)
    refined = mul(estimate, add(np.float32(2.0), -mul(normalized, estimate)))
    scale = np.float32(struct.unpack("<f", struct.pack("<I", (254 - exponent) << 23))[0])
    return mul(refined, scale)


def silu(value):
    exponential = exp2_pwl(
        mul(np.float32(-abs(float(value))), np.float32(1.4426950408889634))
    )
    base = mul(value, reciprocal(add(np.float32(1), exponential)))
    return mul(base, exponential) if value < 0 else base


def load(path):
    return np.array([from_bits(line) for line in path.read_text().splitlines()], dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--up", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path, expected, name in ((args.gate, GATE_HASH, "gate"), (args.up, UP_HASH, "up")):
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise SystemExit(f"TARGET_SILU_PRODUCT_INPUT_HASH_FAIL {name} {observed}")
    gate = load(args.gate)
    up = load(args.up)
    activated = np.array([silu(value) for value in gate], dtype=np.float32)
    product = np.array([mul(activated[i], up[i]) for i in range(LANES)], dtype=np.float32)
    true_silu = gate.astype(np.float64) / (1.0 + np.exp(-gate.astype(np.float64)))
    max_silu_error = float(np.max(np.abs(activated.astype(np.float64) - true_silu)))
    for name, values in (("silu", activated), ("product", product)):
        (args.out / f"{name}.memh").write_text(
            "\n".join(f"{bits(value):08x}" for value in values) + "\n"
        )
    manifest = {
        "input_sha256": {"gate": GATE_HASH, "up": UP_HASH},
        "lanes": LANES,
        "product_chunks": 560,
        "max_silu_error": max_silu_error,
        "silu_error_threshold": 0.002,
        "silu_error_pass": max_silu_error <= 0.002,
        "silu_sha256": hashlib.sha256((args.out / "silu.memh").read_bytes()).hexdigest(),
        "product_sha256": hashlib.sha256((args.out / "product.memh").read_bytes()).hexdigest(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if not manifest["silu_error_pass"]:
        raise SystemExit(f"TARGET_SILU_ERROR_FAIL {max_silu_error}")
    print(
        "L5_TARGET_SILU_PRODUCT_VECTORS_PASS lanes=8960 chunks=560 "
        f"max_silu_error={max_silu_error:.9g} product_sha256={manifest['product_sha256']}"
    )


if __name__ == "__main__":
    main()
