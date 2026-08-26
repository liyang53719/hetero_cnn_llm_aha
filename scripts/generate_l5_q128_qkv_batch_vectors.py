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

BATCH_ROWS = 16
HIDDEN = 1536
KV_WIDTH = 256
EXPECTED_BASE_HASHES = {
    "weights_bf16": "4beac16c43bdf4ce8f728e6a315ea22a21eb2600fc172ec6fdc8b1d5a7b5fec9",
    "norm_weight": "edad7057752e1f59419a1b8cc7234297431de92b87fea6fa2234929485dd65a3",
    "q_bias": "c6847566277e24f5ed023276d1b4516bdb48262514e09e6dc32fa661b619cf1b",
    "k_bias": "4ecbdd1d17e88b335cc166a64fc8b4e74824488d9cb835bc97d82067eb48e207",
    "v_bias": "8360a20d9e8ef8af84f6b655064ae967523327a84e36c05371fcb6951d38e51a",
}

libm = ctypes.CDLL("libm.so.6")
fmaf = libm.fmaf
fmaf.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float]
fmaf.restype = ctypes.c_float


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_word(word):
    return np.float32(struct.unpack("<f", struct.pack("<I", int(word)))[0])


def from_hex(value):
    return from_word(int(value, 16))


def bf16_bits(value):
    word = bits(value)
    return ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) & 0xFFFF


def bf16_value(value):
    return from_word(bf16_bits(value) << 16)


def add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def mul(a, b):
    return np.float32(np.float32(a) * np.float32(b))


def fma(a, b, c):
    return np.float32(
        fmaf(ctypes.c_float(float(a)), ctypes.c_float(float(b)), ctypes.c_float(float(c)))
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
    normalized = from_word(((128 if odd else 127) << 23) | fraction)
    index = (odd << 4) | (fraction >> 19)
    low, step = ((1.0, 1.0 / 16.0) if not odd else (2.0, 1.0 / 8.0))
    x0 = low + (index & 15) * step
    x1 = x0 + step
    slope = np.float32(((1 / math.sqrt(x1)) - (1 / math.sqrt(x0))) / step)
    intercept = np.float32(1 / math.sqrt(x0) - float(slope) * x0)
    estimate = add(mul(slope, normalized), intercept)
    term = add(np.float32(1.5), -mul(np.float32(0.5), mul(normalized, mul(estimate, estimate))))
    return mul(mul(estimate, term), from_word((127 - even_exponent // 2) << 23))


def rmsnorm(vector, weight):
    total = np.float32(0)
    for chunk in range(96):
        total = add(
            total,
            reduce16([mul(value, value) for value in vector[chunk * 16:(chunk + 1) * 16]]),
        )
    inverse = rsqrt_algorithm(add(mul(total, np.float32(1.0 / HIDDEN)), np.float32(1e-6)))
    return np.array(
        [mul(mul(vector[i], inverse), weight[i]) for i in range(HIDDEN)],
        dtype=np.float32,
    )


def gemv_batch(vectors, weights):
    rows, columns = weights.shape
    outputs = np.empty((BATCH_ROWS, columns), dtype=np.float32)
    bf16_vectors = np.array(
        [[bf16_value(vectors[token, row]) for row in range(rows)] for token in range(BATCH_ROWS)],
        dtype=np.float32,
    )
    for column in range(columns):
        accumulators = [np.float32(0) for _ in range(BATCH_ROWS)]
        for row in range(rows):
            weight = from_word(int(weights[row, column]) << 16)
            for token in range(BATCH_ROWS):
                accumulators[token] = fma(bf16_vectors[token, row], weight, accumulators[token])
        for token in range(BATCH_ROWS):
            outputs[token, column] = accumulators[token]
    return outputs


def write_fp32(path, values):
    path.write_text("\n".join(f"{bits(value):08x}" for value in values.flat) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--tokens", type=int, choices=(128, 384, 1024), default=128)
    parser.add_argument("--skip-shared-write", action="store_true")
    parser.add_argument("--shared-out", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.shared_out.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, expected in EXPECTED_BASE_HASHES.items():
        path = args.base_dir / f"{name}.memh"
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise SystemExit(f"Q128_QKV_BASE_HASH_FAIL {name} {observed}")

    if args.batch_index < 0 or args.batch_index >= args.tokens // BATCH_ROWS:
        raise SystemExit("QKV_BATCH_INDEX_FAIL")
    rng = random.Random({128: 0x1281536, 384: 0x3841536, 1024: 0x10241536}[args.tokens])
    inputs = np.array(
        [[bf16_value(rng.uniform(-1, 1)) for _ in range(HIDDEN)] for _ in range(args.tokens)],
        dtype=np.float32,
    )
    input_path = args.shared_out / "inputs.memh"
    if not args.skip_shared_write:
        write_fp32(input_path, inputs)
    start = args.batch_index * BATCH_ROWS
    batch = inputs[start:start + BATCH_ROWS]
    norm_weight = np.array(
        [from_hex(line) for line in (args.base_dir / "norm_weight.memh").read_text().splitlines()],
        dtype=np.float32,
    )
    normalized = np.array([rmsnorm(batch[token], norm_weight) for token in range(BATCH_ROWS)])
    weight_words = np.array(
        [int(line, 16) for line in (args.base_dir / "weights_bf16.memh").read_text().splitlines()],
        dtype=np.uint16,
    )
    q_weight = weight_words[:HIDDEN * HIDDEN].reshape(HIDDEN, HIDDEN)
    k_weight = weight_words[HIDDEN * HIDDEN:HIDDEN * HIDDEN + HIDDEN * KV_WIDTH].reshape(HIDDEN, KV_WIDTH)
    v_weight = weight_words[HIDDEN * HIDDEN + HIDDEN * KV_WIDTH:].reshape(HIDDEN, KV_WIDTH)
    q_raw = gemv_batch(normalized, q_weight)
    k_raw = gemv_batch(normalized, k_weight)
    v_raw = gemv_batch(normalized, v_weight)
    q_bias = np.array([from_hex(line) for line in (args.base_dir / "q_bias.memh").read_text().splitlines()])
    k_bias = np.array([from_hex(line) for line in (args.base_dir / "k_bias.memh").read_text().splitlines()])
    v_bias = np.array([from_hex(line) for line in (args.base_dir / "v_bias.memh").read_text().splitlines()])
    q = np.array([[add(q_raw[t, i], q_bias[i]) for i in range(HIDDEN)] for t in range(BATCH_ROWS)])
    k = np.array([[add(k_raw[t, i], k_bias[i]) for i in range(KV_WIDTH)] for t in range(BATCH_ROWS)])
    v = np.array([[add(v_raw[t, i], v_bias[i]) for i in range(KV_WIDTH)] for t in range(BATCH_ROWS)])
    nodes = {"input": batch, "norm": normalized, "q": q, "k": k, "v": v}
    for name, values in nodes.items():
        write_fp32(args.out / f"{name}.memh", values)
    manifest = {
        "batch_index": args.batch_index,
        "workload_tokens": args.tokens,
        "token_range": [start, start + BATCH_ROWS - 1],
        "rows": BATCH_ROWS,
        "hidden": HIDDEN,
        "kv_width": KV_WIDTH,
        "physical_array": [16, 32],
        "expected_steps": {"q": 73728, "k": 12288, "v": 12288, "total": 98304},
        "shared_input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "node_sha256": {
            name: hashlib.sha256((args.out / f"{name}.memh").read_bytes()).hexdigest()
            for name in nodes
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"L5_Q_PREFILL_QKV_BATCH_VECTORS_PASS workload={args.tokens} batch={args.batch_index} tokens={start}-{start+15} "
        f"steps=98304 q_sha256={manifest['node_sha256']['q']}"
    )


if __name__ == "__main__":
    main()
