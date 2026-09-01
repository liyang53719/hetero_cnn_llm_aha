#!/usr/bin/env python3
"""Pack one exact-model layer tail sample for the production Matrix and SiLU RTL."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--layer", type=int, choices=range(4), default=0)
parser.add_argument("--out", type=Path)
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[1]
if args.layer == 0:
    BACKEND = ROOT / "work/results/qwen2_q1024_layer0_tail_backend"
    ATTENTION = ROOT / "work/results/qwen2_q1024_attention_backend"
    INPUT = ROOT / "work/results/qwen2_q1024_layer0_tail_inputs"
    default_out = ROOT / "work/results/qwen2_q1024_layer0_tail_rtl/vectors"
else:
    BACKEND = ROOT / f"work/results/qwen2_q1024_group0_backend/layer{args.layer}"
    ATTENTION = BACKEND
    INPUT = ROOT / f"work/results/qwen2_q1024_group0_inputs/layer{args.layer}"
    default_out = ROOT / f"work/results/qwen2_q1024_group0_rtl/layer{args.layer}/vectors"
OUT = args.out or default_out
OUT.mkdir(parents=True, exist_ok=True)

def bf16_bits(values):
    words = np.asarray(values, np.float32).view(np.uint32)
    return ((words + 0x7fff + ((words >> 16) & 1)) >> 16).astype(np.uint16)

def write_words(path, rows, lanes):
    rows = np.asarray(rows, np.uint16).reshape(-1, lanes)
    width = lanes * 4
    with path.open("w") as stream:
        for row in rows:
            word = sum(int(value) << (16 * lane) for lane, value in enumerate(row))
            stream.write(f"{word:0{width}x}\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()

spec = {
    "oproj": {
        "activation": bf16_bits(np.fromfile(ATTENTION / "attention_fp32.bin", np.float32).reshape(1024, 1536)[:16]),
        "weights": np.fromfile(INPUT / "oproj_weight_bf16.bin", np.uint16).reshape(1536, 1536),
        "expected": bf16_bits(np.fromfile(BACKEND / "oproj_fp32.bin", np.float32).reshape(1024, 1536)[:16]),
        "tiles": [0, 24, 47],
    },
    "gate": {
        "activation": bf16_bits(np.fromfile(BACKEND / "postnorm_fp32.bin", np.float32).reshape(1024, 1536)[:16]),
        "weights": np.fromfile(INPUT / "gate_weight_bf16.bin", np.uint16).reshape(8960, 1536),
        "expected": bf16_bits(np.fromfile(BACKEND / "gate_fp32.bin", np.float32).reshape(1024, 8960)[:16]),
        "tiles": [0, 140, 279],
    },
    "up": {
        "activation": bf16_bits(np.fromfile(BACKEND / "postnorm_fp32.bin", np.float32).reshape(1024, 1536)[:16]),
        "weights": np.fromfile(INPUT / "up_weight_bf16.bin", np.uint16).reshape(8960, 1536),
        "expected": bf16_bits(np.fromfile(BACKEND / "up_fp32.bin", np.float32).reshape(1024, 8960)[:16]),
        "tiles": [0, 140, 279],
    },
    "down": {
        "activation": np.fromfile(BACKEND / "silu_product_bf16.bin", np.uint16).reshape(1024, 8960)[:16],
        "weights": np.fromfile(INPUT / "down_weight_bf16.bin", np.uint16).reshape(1536, 8960),
        "expected": bf16_bits(np.fromfile(BACKEND / "down_fp32.bin", np.float32).reshape(1024, 1536)[:16]),
        "tiles": [0, 24, 47],
    },
}

hashes = {}
for name, item in spec.items():
    activation = item["activation"]
    hashes[f"{name}_activation"] = write_words(OUT / f"{name}_activation.memh", activation.T, 16)
    weight_rows = []
    expected_rows = []
    for tile in item["tiles"]:
        columns = slice(tile * 32, tile * 32 + 32)
        weight_rows.append(item["weights"][columns].T)
        expected_rows.append(item["expected"][:, columns])
    hashes[f"{name}_weights"] = write_words(OUT / f"{name}_weights.memh", np.concatenate(weight_rows), 32)
    hashes[f"{name}_expected"] = write_words(OUT / f"{name}_expected.memh", np.concatenate(expected_rows), 32)

gate = bf16_bits(np.fromfile(BACKEND / "gate_fp32.bin", np.float32)[:8192]).reshape(-1, 8)
up = bf16_bits(np.fromfile(BACKEND / "up_fp32.bin", np.float32)[:8192]).reshape(-1, 8)
product = np.fromfile(BACKEND / "silu_product_bf16.bin", np.uint16)[:8192].reshape(-1, 8)
hashes["silu_gate"] = write_words(OUT / "silu_gate8.memh", gate, 8)
hashes["silu_up"] = write_words(OUT / "silu_up8.memh", up, 8)
hashes["silu_product"] = write_words(OUT / "silu_product8.memh", product, 8)

manifest = {
    "schema_version": 1,
    "status": "PASS",
    "rows": 16,
    "matrix_tiles_per_operation": 3,
    "matrix_operations": ["oproj", "gate", "up", "down"],
    "matrix_steps": 40704,
    "matrix_bf16_expected_values": 6144,
    "silu_lanes": 8,
    "silu_values": 8192,
    "physical_tiles": {name: item["tiles"] for name, item in spec.items()},
    "hashes": hashes,
}
if args.layer != 0:
    manifest["layer"] = args.layer
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
if args.layer == 0:
    print("QWEN2_Q1024_LAYER0_TAIL_RTL_VECTORS_PASS matrix_steps=40704 matrix_values=6144 silu_values=8192")
else:
    print(f"QWEN2_Q1024_GROUP0_RTL_VECTORS_PASS layer={args.layer} matrix_steps=40704 matrix_values=6144 silu_values=8192")
