#!/usr/bin/env python3
import argparse
import ctypes
import hashlib
import json
import random
import struct
from pathlib import Path

import numpy as np

HIDDEN = 1536
ATTENTION_HASH = "86c06c97e24153ce786b30f4e15fb7b76f48eacf2126adc33be94412837eb681"
CURRENT_HASH = "b73d329b579d102621455e2b00d09f997021fa0b37a80f6f70e807a4539149e6"

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


def load_fp32(path):
    return np.array([from_bits(line) for line in path.read_text().splitlines()], dtype=np.float32)


def write_fp32(path, values):
    path.write_text("\n".join(f"{bits(value):08x}" for value in values) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attention", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path, expected, name in (
        (args.attention, ATTENTION_HASH, "attention"),
        (args.current, CURRENT_HASH, "current"),
    ):
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise SystemExit(f"TARGET_OPROJ_INPUT_HASH_FAIL {name} {observed}")
    attention = load_fp32(args.attention)
    current = load_fp32(args.current)
    rng = random.Random(0x0A0B0C0D)
    weights = np.fromiter(
        (bf16_bits(rng.uniform(-0.0625, 0.0625)) for _ in range(HIDDEN * HIDDEN)),
        dtype=np.uint16,
        count=HIDDEN * HIDDEN,
    ).reshape(HIDDEN, HIDDEN)
    input_bf16 = np.array([bf16_value(value) for value in attention], dtype=np.float32)
    oproj = np.empty(HIDDEN, dtype=np.float32)
    for column in range(HIDDEN):
        accumulator = np.float32(0)
        for row in range(HIDDEN):
            weight = np.float32(
                struct.unpack("<f", struct.pack("<I", int(weights[row, column]) << 16))[0]
            )
            accumulator = fma(input_bf16[row], weight, accumulator)
        oproj[column] = accumulator
    residual1 = np.array([add(current[i], oproj[i]) for i in range(HIDDEN)], dtype=np.float32)
    (args.out / "weights_bf16.memh").write_text(
        "\n".join(f"{int(value):04x}" for value in weights.flat) + "\n"
    )
    write_fp32(args.out / "oproj.memh", oproj)
    write_fp32(args.out / "residual1.memh", residual1)
    manifest = {
        "input_sha256": {"attention": ATTENTION_HASH, "current": CURRENT_HASH},
        "shape": [HIDDEN, HIDDEN],
        "bias": False,
        "physical_array": [16, 32],
        "expected_array_steps": 73728,
        "residual_chunks": 96,
        "weights_sha256": hashlib.sha256(
            (args.out / "weights_bf16.memh").read_bytes()
        ).hexdigest(),
        "oproj_sha256": hashlib.sha256((args.out / "oproj.memh").read_bytes()).hexdigest(),
        "residual1_sha256": hashlib.sha256(
            (args.out / "residual1.memh").read_bytes()
        ).hexdigest(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "L5_TARGET_OPROJ_VECTORS_PASS expected_array_steps=73728 "
        f"residual_sha256={manifest['residual1_sha256']}"
    )


if __name__ == "__main__":
    main()
