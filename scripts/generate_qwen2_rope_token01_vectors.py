#!/usr/bin/env python3
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/results/qwen2_rope_token01_vectors"
OUT.mkdir(parents=True, exist_ok=True)

def f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]

def bits(value):
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]

def bf16(value):
    word = bits(value)
    return ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) & 0xFFFF

def load_bf16(path):
    values = []
    for line in path.read_text().splitlines():
        word = int(line, 16)
        values.extend((word >> (16 * lane)) & 0xFFFF for lane in range(32))
    return values

def write_beats(path, values):
    path.write_text("".join(f"{sum(int(v) << (16*i) for i,v in enumerate(values[j:j+32])):0128x}\n" for j in range(0, len(values), 32)))

def rotate(values, heads):
    result = [0] * len(values)
    for head in range(heads):
        for dim in range(64):
            even_bits = values[head * 128 + dim]
            odd_bits = values[head * 128 + 64 + dim]
            even = struct.unpack("<f", struct.pack("<I", even_bits << 16))[0]
            odd = struct.unpack("<f", struct.pack("<I", odd_bits << 16))[0]
            angle = 1_000_000.0 ** (-2.0 * dim / 128.0)
            cosine = f32(math.cos(angle))
            sine = f32(math.sin(angle))
            even_out = f32(f32(even * cosine) - f32(odd * sine))
            odd_out = f32(f32(even * sine) + f32(odd * cosine))
            result[head * 128 + dim] = bf16(even_out)
            result[head * 128 + 64 + dim] = bf16(odd_out)
    return result

q = load_bf16(ROOT / "work/results/qwen2_shared_l2_tile_payload/q_biased_expected_all_beats.memh")
k = load_bf16(ROOT / "work/results/qwen2_kv_projection_vectors/k_biased_expected_beats.memh")
write_beats(OUT / "q_input.memh", q)
write_beats(OUT / "k_input.memh", k)
write_beats(OUT / "q_position1_expected.memh", rotate(q, 12))
write_beats(OUT / "k_position1_expected.memh", rotate(k, 2))
print("QWEN2_ROPE_TOKEN01_VECTORS_PASS theta=1000000 Q_values=1536 K_values=256 positions=0,1")
