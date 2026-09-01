#!/usr/bin/env python3
"""Freeze exact-revision layers 1-3 and their real 21-command graph slices."""
import argparse
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

parser = argparse.ArgumentParser()
parser.add_argument("--start-layer", type=int, choices=range(28), default=1)
parser.add_argument("--end-layer", type=int, choices=range(28), default=3)
parser.add_argument("--out", type=Path)
args = parser.parse_args()
assert args.start_layer <= args.end_layer
MODEL = ROOT / "work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors"
OUT = args.out or ROOT / "work/results/qwen2_q1024_group0_inputs"
MANIFEST = [json.loads(line) for line in (ROOT / "reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl").read_text().splitlines()]
SUFFIXES = [
    "input_norm", "q", "q_bias", "q_rope", "k", "k_bias", "k_rope", "v",
    "v_bias", "kv_append", "qk", "softmax", "pv", "oproj", "attn_residual",
    "post_norm", "gate", "up", "silu_mul", "down", "residual",
]

tensor_suffix = {
    "input_norm_weight_bf16.bin": "input_layernorm.weight",
    "q_weight_bf16.bin": "self_attn.q_proj.weight",
    "q_bias_fp32.bin": "self_attn.q_proj.bias",
    "k_weight_bf16.bin": "self_attn.k_proj.weight",
    "k_bias_fp32.bin": "self_attn.k_proj.bias",
    "v_weight_bf16.bin": "self_attn.v_proj.weight",
    "v_bias_fp32.bin": "self_attn.v_proj.bias",
    "oproj_weight_bf16.bin": "self_attn.o_proj.weight",
    "post_norm_weight_bf16.bin": "post_attention_layernorm.weight",
    "gate_weight_bf16.bin": "mlp.gate_proj.weight",
    "up_weight_bf16.bin": "mlp.up_proj.weight",
    "down_weight_bf16.bin": "mlp.down_proj.weight",
}

summary = {"schema_version": 1, "status": "PASS", "layers": {}}
with safe_open(MODEL, framework="pt", device="cpu") as model:
    if args.start_layer == 0:
        tokens = np.asarray([int(value) for value in (ROOT / "work/results/llama_cpp_qwen2_baseline/tokens.txt").read_text().splitlines()], np.int32)
        assert tokens.size == 1024
        embedding_dir = OUT / "embedding"
        embedding_dir.mkdir(parents=True, exist_ok=True)
        embedding = model.get_tensor("model.embed_tokens.weight")[torch.tensor(tokens, dtype=torch.long)].float().numpy().astype(np.float32)
        embedding.tofile(embedding_dir / "final_fp32.bin")
        summary["embedding_sha256"] = hashlib.sha256((embedding_dir / "final_fp32.bin").read_bytes()).hexdigest()
        final_dir = OUT / "final_head"
        final_dir.mkdir(parents=True, exist_ok=True)
        model.get_tensor("model.norm.weight").contiguous().view(torch.uint16).numpy().tofile(final_dir / "final_norm_weight_bf16.bin")
        model.get_tensor("model.embed_tokens.weight").contiguous().view(torch.uint16).numpy().tofile(final_dir / "lm_head_weight_bf16.bin")
        summary["final_norm_weight_sha256"] = hashlib.sha256((final_dir / "final_norm_weight_bf16.bin").read_bytes()).hexdigest()
        summary["lm_head_weight_sha256"] = hashlib.sha256((final_dir / "lm_head_weight_bf16.bin").read_bytes()).hexdigest()
    for layer in range(args.start_layer, args.end_layer + 1):
        directory = OUT / f"layer{layer}"
        directory.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for filename, suffix in tensor_suffix.items():
            tensor = model.get_tensor(f"model.layers.{layer}.{suffix}").contiguous()
            if filename.endswith("_fp32.bin"):
                tensor.float().numpy().astype(np.float32).tofile(directory / filename)
            else:
                assert tensor.dtype == torch.bfloat16
                tensor.view(torch.uint16).numpy().tofile(directory / filename)
            hashes[filename] = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        np.asarray(ROM, np.uint16).tofile(directory / "silu_lut_fp16.bin")
        hashes["silu_lut_fp16.bin"] = hashlib.sha256((directory / "silu_lut_fp16.bin").read_bytes()).hexdigest()
        records = MANIFEST[layer * 21:(layer + 1) * 21]
        assert [entry["operation"] for entry in records] == [f"l{layer}.{suffix}" for suffix in SUFFIXES]
        (directory / "first21_commands.bin").write_bytes(
            b"".join(int(entry["word"], 16).to_bytes(16, "little") for entry in records)
        )
        hashes["first21_commands.bin"] = hashlib.sha256((directory / "first21_commands.bin").read_bytes()).hexdigest()
        layer_result = {"layer": layer, "commands": 21, "operations": [entry["operation"] for entry in records], "hashes": hashes}
        (directory / "manifest.json").write_text(json.dumps(layer_result, indent=2, sort_keys=True) + "\n")
        summary["layers"][str(layer)] = {"manifest_sha256": hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest(), "commands": 21}

(OUT / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(f"QWEN2_Q1024_LAYER_INPUTS_PASS layers={args.start_layer}-{args.end_layer} commands={(args.end_layer-args.start_layer+1)*21} exact_revision=true")
