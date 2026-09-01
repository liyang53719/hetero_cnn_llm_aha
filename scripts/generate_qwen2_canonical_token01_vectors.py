#!/usr/bin/env python3
import hashlib
import math
import struct
import sys
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_l5_q128_qkv_batch_vectors import add, bf16_value, fma, from_word, mul, reduce16, rsqrt_algorithm

MODEL = ROOT / "work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors"
TOKENS = ROOT / "work/results/llama_cpp_qwen2_baseline/tokens.txt"
OUT = ROOT / "work/results/qwen2_canonical_token01_vectors"
EXPECTED_TOKEN_HASH = "e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628"
OUT.mkdir(parents=True, exist_ok=True)

def f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]

def bits(value):
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]

def bf16(value):
    word = bits(value)
    return ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) & 0xFFFF

def write_beats(path, values, width=16):
    lanes = 512 // width
    path.write_text("".join(f"{sum(int(v) << (width*i) for i,v in enumerate(values[j:j+lanes])):0128x}\n" for j in range(0, len(values), lanes)))

def rotate(values, heads, position):
    result = [0] * len(values)
    for head in range(heads):
        for dim in range(64):
            even = struct.unpack("<f", struct.pack("<I", int(values[head*128+dim]) << 16))[0]
            odd = struct.unpack("<f", struct.pack("<I", int(values[head*128+64+dim]) << 16))[0]
            angle = position * (1_000_000.0 ** (-2.0 * dim / 128.0))
            cosine, sine = f32(math.cos(angle)), f32(math.sin(angle))
            result[head*128+dim] = bf16(f32(f32(even*cosine)-f32(odd*sine)))
            result[head*128+64+dim] = bf16(f32(f32(even*sine)+f32(odd*cosine)))
    return result

def exact_matrix_bf16(vector, weight):
    vector_values = vector.float().numpy()
    weight_bits = weight.contiguous().view(torch.uint16).numpy()
    output = []
    for column in range(weight_bits.shape[0]):
        accumulator = np.float32(0)
        for row in range(weight_bits.shape[1]):
            accumulator = fma(bf16_value(vector_values[row]), from_word(int(weight_bits[column, row]) << 16), accumulator)
        output.append(bf16(accumulator))
    return torch.tensor(output, dtype=torch.uint16).view(torch.bfloat16)

def refined_rmsnorm(vector, weight):
    total = np.float32(0)
    for chunk in range(96):
        total = add(total, reduce16([mul(value, value) for value in vector[chunk*16:(chunk+1)*16]]))
    mean_epsilon = add(mul(total, np.float32(1.0 / 1536)), np.float32(1e-6))
    first = rsqrt_algorithm(mean_epsilon)
    second_term = add(np.float32(1.5), -mul(np.float32(0.5), mul(mean_epsilon, mul(first, first))))
    inverse = mul(first, second_term)
    return np.asarray([mul(bf16_value(mul(vector[i], inverse)), weight[i]) for i in range(1536)], dtype=np.float32)

token_ids = np.asarray([int(line) for line in TOKENS.read_text().splitlines()], dtype=np.int32)
assert token_ids.size == 1024 and hashlib.sha256(token_ids.tobytes()).hexdigest() == EXPECTED_TOKEN_HASH
with safe_open(MODEL, framework="pt", device="cpu") as model:
    embedding = model.get_tensor("model.embed_tokens.weight")[torch.tensor(token_ids[:2], dtype=torch.long)].contiguous()
    norm_weight = model.get_tensor("model.layers.0.input_layernorm.weight").float().contiguous()
    q_weight = model.get_tensor("model.layers.0.self_attn.q_proj.weight").contiguous()
    k_weight = model.get_tensor("model.layers.0.self_attn.k_proj.weight").contiguous()
    v_weight = model.get_tensor("model.layers.0.self_attn.v_proj.weight").contiguous()
    q_bias = model.get_tensor("model.layers.0.self_attn.q_proj.bias").float().contiguous()
    k_bias = model.get_tensor("model.layers.0.self_attn.k_proj.bias").float().contiguous()
    v_bias = model.get_tensor("model.layers.0.self_attn.v_proj.bias").float().contiguous()

for token in range(2):
    token_dir = OUT / f"token{token}"
    token_dir.mkdir(exist_ok=True)
    hidden = embedding[token].contiguous()
    normalized_fp32 = refined_rmsnorm(hidden.float().numpy(), norm_weight.numpy())
    normalized = torch.from_numpy(normalized_fp32).to(torch.bfloat16).contiguous()
    q_raw = exact_matrix_bf16(normalized, q_weight).contiguous()
    k_raw = exact_matrix_bf16(normalized, k_weight).contiguous()
    v_raw = exact_matrix_bf16(normalized, v_weight).contiguous()
    q_biased = (q_raw.float() + q_bias).to(torch.bfloat16).contiguous()
    k_biased = (k_raw.float() + k_bias).to(torch.bfloat16).contiguous()
    v_biased = (v_raw.float() + v_bias).to(torch.bfloat16).contiguous()
    q_bits = q_biased.view(torch.uint16).tolist()
    k_bits = k_biased.view(torch.uint16).tolist()
    write_beats(token_dir / "hidden_beats.memh", hidden.view(torch.uint16).tolist())
    write_beats(token_dir / "norm_expected_beats.memh", normalized.view(torch.uint16).tolist())
    write_beats(token_dir / "q_raw_expected.memh", q_raw.view(torch.uint16).tolist())
    write_beats(token_dir / "k_raw_expected.memh", k_raw.view(torch.uint16).tolist())
    write_beats(token_dir / "v_raw_expected.memh", v_raw.view(torch.uint16).tolist())
    write_beats(token_dir / "q_biased_expected.memh", q_bits)
    write_beats(token_dir / "k_biased_expected.memh", k_bits)
    write_beats(token_dir / "v_biased_expected.memh", v_biased.view(torch.uint16).tolist())
    write_beats(token_dir / "q_rope_expected.memh", rotate(q_bits, 12, token))
    write_beats(token_dir / "k_rope_expected.memh", rotate(k_bits, 2, token))

positions = list(range(16))
write_beats(OUT / "positions_0_15.memh", positions, 32)
print(f"QWEN2_CANONICAL_TOKEN01_VECTORS_PASS token_ids={token_ids[0]},{token_ids[1]} token_hash={EXPECTED_TOKEN_HASH} rows=0,1 theta=1000000")
