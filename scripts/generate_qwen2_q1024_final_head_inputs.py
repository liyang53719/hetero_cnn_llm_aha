#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors"
OUT = ROOT / "work/results/qwen2_q1024_final_head_inputs"
OUT.mkdir(parents=True, exist_ok=True)
with safe_open(MODEL, framework="pt", device="cpu") as model:
    norm = model.get_tensor("model.norm.weight").contiguous()
    lm_head = model.get_tensor("model.embed_tokens.weight").contiguous()
    assert norm.dtype == lm_head.dtype == torch.bfloat16
    norm.view(torch.uint16).numpy().tofile(OUT / "final_norm_weight_bf16.bin")
    lm_head.view(torch.uint16).numpy().tofile(OUT / "lm_head_weight_bf16.bin")

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
result = {
    "schema_version": 1, "status": "PASS_Q1024_FINAL_HEAD_INPUTS",
    "model_revision": "ba1cf1846d7df0a0591d6c00649f57e798519da8",
    "hidden": 1536, "vocab": 151936, "tied_embedding_weight": True,
    "hashes": {
        "final_norm_weight": sha(OUT / "final_norm_weight_bf16.bin"),
        "lm_head_weight": sha(OUT / "lm_head_weight_bf16.bin"),
    },
}
(OUT / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print("QWEN2_Q1024_FINAL_HEAD_INPUTS_PASS hidden=1536 vocab=151936 tied=true")
