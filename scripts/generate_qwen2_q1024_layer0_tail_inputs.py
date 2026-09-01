#!/usr/bin/env python3
"""Freeze exact-revision layer-0 tail tensors and the first 21 Command128 words."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.silu_lut_rtl_contract import ROM

MODEL = ROOT / "work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors"
TOKENS = ROOT / "work/results/llama_cpp_qwen2_baseline/tokens.txt"
OUT = ROOT / "work/results/qwen2_q1024_layer0_tail_inputs"
OUT.mkdir(parents=True, exist_ok=True)

ids = np.asarray([int(value) for value in TOKENS.read_text().splitlines()], np.int32)
assert ids.size == 1024
assert hashlib.sha256(ids.tobytes()).hexdigest() == "e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628"

tensor_map = {
    "oproj_weight_bf16.bin": "model.layers.0.self_attn.o_proj.weight",
    "post_norm_weight_bf16.bin": "model.layers.0.post_attention_layernorm.weight",
    "gate_weight_bf16.bin": "model.layers.0.mlp.gate_proj.weight",
    "up_weight_bf16.bin": "model.layers.0.mlp.up_proj.weight",
    "down_weight_bf16.bin": "model.layers.0.mlp.down_proj.weight",
}
hashes = {}
with safe_open(MODEL, framework="pt", device="cpu") as model:
    hidden = model.get_tensor("model.embed_tokens.weight")[torch.tensor(ids, dtype=torch.long)]
    hidden.contiguous().view(torch.uint16).numpy().tofile(OUT / "hidden_bf16.bin")
    hashes["hidden_bf16.bin"] = hashlib.sha256((OUT / "hidden_bf16.bin").read_bytes()).hexdigest()
    for filename, tensor_name in tensor_map.items():
        tensor = model.get_tensor(tensor_name)
        assert tensor.dtype == torch.bfloat16
        tensor.contiguous().view(torch.uint16).numpy().tofile(OUT / filename)
        hashes[filename] = hashlib.sha256((OUT / filename).read_bytes()).hexdigest()

np.asarray(ROM, np.uint16).tofile(OUT / "silu_lut_fp16.bin")
hashes["silu_lut_fp16.bin"] = hashlib.sha256((OUT / "silu_lut_fp16.bin").read_bytes()).hexdigest()

operations = [
    "l0.input_norm", "l0.q", "l0.q_bias", "l0.q_rope", "l0.k", "l0.k_bias",
    "l0.k_rope", "l0.v", "l0.v_bias", "l0.kv_append", "l0.qk", "l0.softmax",
    "l0.pv", "l0.oproj", "l0.attn_residual", "l0.post_norm", "l0.gate", "l0.up",
    "l0.silu_mul", "l0.down", "l0.residual",
]
manifest = [
    json.loads(line)
    for line in (ROOT / "reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl")
    .read_text().splitlines()[:len(operations)]
]
assert [entry["operation"] for entry in manifest] == operations
(OUT / "first21_commands.bin").write_bytes(
    b"".join(int(entry["word"], 16).to_bytes(16, "little") for entry in manifest)
)
hashes["first21_commands.bin"] = hashlib.sha256((OUT / "first21_commands.bin").read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_Q1024_LAYER0_TAIL_INPUTS",
    "model_revision": "ba1cf1846d7df0a0591d6c00649f57e798519da8",
    "commands": 21,
    "operations": operations,
    "tokens": 1024,
    "hidden": 1536,
    "intermediate": 8960,
    "hashes": hashes,
}
(OUT / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print("QWEN2_Q1024_LAYER0_TAIL_INPUTS_PASS commands=21 tokens=1024 hidden=1536 intermediate=8960")
