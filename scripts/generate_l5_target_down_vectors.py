#!/usr/bin/env python3
import argparse
import ctypes
import hashlib
import json
import random
import struct
from pathlib import Path

import numpy as np

INPUTS = 8960
OUTPUTS = 1536
PRODUCT_HASH = "5076748a33e3b316acc2647554cea7d193b50099d6fa40ebdb1dec67a716fb1c"
RESIDUAL_HASH = "df2d5af8926229b7c3ea34aa7c0dfc1ad381fee5cd7149d86b5b01739f518671"

libm = ctypes.CDLL("libm.so.6")
fmaf = libm.fmaf
fmaf.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float]
fmaf.restype = ctypes.c_float


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_bits(value):
    return np.float32(struct.unpack("<f", struct.pack("<I", int(value, 16)))[0])


def bf16_bits(value):
    word = bits(value)
    return ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) & 0xFFFF


def bf16_value(value):
    return np.float32(struct.unpack("<f", struct.pack("<I", bf16_bits(value) << 16))[0])


def add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def fma(a, b, c):
    return np.float32(
        fmaf(ctypes.c_float(float(a)), ctypes.c_float(float(b)), ctypes.c_float(float(c)))
    )


def load(path):
    return np.array([from_bits(line) for line in path.read_text().splitlines()], dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--residual", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path, expected, name in (
        (args.product, PRODUCT_HASH, "product"),
        (args.residual, RESIDUAL_HASH, "residual1"),
    ):
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise SystemExit(f"TARGET_DOWN_INPUT_HASH_FAIL {name} {observed}")
    product = np.array([bf16_value(value) for value in load(args.product)], dtype=np.float32)
    residual = load(args.residual)
    rng = random.Random(0xD0A01536)
    weights = np.fromiter(
        (bf16_bits(rng.uniform(-0.03125, 0.03125)) for _ in range(INPUTS * OUTPUTS)),
        dtype=np.uint16,
        count=INPUTS * OUTPUTS,
    ).reshape(INPUTS, OUTPUTS)
    weight_path = args.out / "weights_bf16.memh"
    weight_path.write_text("\n".join(f"{int(value):04x}" for value in weights.flat) + "\n")
    down = np.empty(OUTPUTS, dtype=np.float32)
    for column in range(OUTPUTS):
        accumulator = np.float32(0)
        for row in range(INPUTS):
            weight = np.float32(
                struct.unpack("<f", struct.pack("<I", int(weights[row, column]) << 16))[0]
            )
            accumulator = fma(product[row], weight, accumulator)
        down[column] = accumulator
    final = np.array([add(residual[i], down[i]) for i in range(OUTPUTS)], dtype=np.float32)
    for name, values in (("down", down), ("final", final)):
        (args.out / f"{name}.memh").write_text(
            "\n".join(f"{bits(value):08x}" for value in values) + "\n"
        )
    manifest = {
        "input_sha256": {"product": PRODUCT_HASH, "residual1": RESIDUAL_HASH},
        "shape": [INPUTS, OUTPUTS],
        "bias": False,
        "physical_array": [16, 32],
        "expected_array_steps": 430080,
        "residual_chunks": 96,
        "weights_sha256": hashlib.sha256(weight_path.read_bytes()).hexdigest(),
        "down_sha256": hashlib.sha256((args.out / "down.memh").read_bytes()).hexdigest(),
        "final_sha256": hashlib.sha256((args.out / "final.memh").read_bytes()).hexdigest(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "L5_TARGET_DOWN_VECTORS_PASS expected_array_steps=430080 "
        f"final_sha256={manifest['final_sha256']}"
    )


if __name__ == "__main__":
    main()
