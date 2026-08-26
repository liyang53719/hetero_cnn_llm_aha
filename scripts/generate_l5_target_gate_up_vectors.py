#!/usr/bin/env python3
import argparse
import ctypes
import gc
import hashlib
import json
import random
import struct
from pathlib import Path

import numpy as np

INPUTS = 1536
OUTPUTS = 8960
NORM2_HASH = "bb884b8182e44eac53dc64f5c06cdbce752509a343fe9331e2ee8db433831385"

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


def fma(a, b, c):
    return np.float32(
        fmaf(ctypes.c_float(float(a)), ctypes.c_float(float(b)), ctypes.c_float(float(c)))
    )


def generate_projection(name, seed, input_vector, out_dir):
    rng = random.Random(seed)
    weights = np.fromiter(
        (bf16_bits(rng.uniform(-0.03125, 0.03125)) for _ in range(INPUTS * OUTPUTS)),
        dtype=np.uint16,
        count=INPUTS * OUTPUTS,
    ).reshape(INPUTS, OUTPUTS)
    weight_path = out_dir / f"{name}_weights_bf16.memh"
    weight_path.write_text("\n".join(f"{int(value):04x}" for value in weights.flat) + "\n")
    output = np.empty(OUTPUTS, dtype=np.float32)
    for column in range(OUTPUTS):
        accumulator = np.float32(0)
        for row in range(INPUTS):
            weight = np.float32(
                struct.unpack("<f", struct.pack("<I", int(weights[row, column]) << 16))[0]
            )
            accumulator = fma(input_vector[row], weight, accumulator)
        output[column] = accumulator
    output_path = out_dir / f"{name}.memh"
    output_path.write_text("\n".join(f"{bits(value):08x}" for value in output) + "\n")
    result = {
        "weights_sha256": hashlib.sha256(weight_path.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }
    del weights, output
    gc.collect()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--norm2", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    observed = hashlib.sha256(args.norm2.read_bytes()).hexdigest()
    if observed != NORM2_HASH:
        raise SystemExit(f"TARGET_GATE_UP_INPUT_HASH_FAIL {observed}")
    norm2 = np.array(
        [bf16_value(from_bits(line)) for line in args.norm2.read_text().splitlines()],
        dtype=np.float32,
    )
    gate = generate_projection("gate", 0x6A7E1536, norm2, args.out)
    up = generate_projection("up", 0x0A9A1536, norm2, args.out)
    manifest = {
        "norm2_sha256": NORM2_HASH,
        "shape": [INPUTS, OUTPUTS],
        "bias": False,
        "physical_array": [16, 32],
        "array_steps_per_projection": 430080,
        "array_steps_total": 860160,
        "gate": gate,
        "up": up,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "L5_TARGET_GATE_UP_VECTORS_PASS steps_each=430080 total=860160 "
        f"gate_sha256={gate['output_sha256']} up_sha256={up['output_sha256']}"
    )


if __name__ == "__main__":
    main()
