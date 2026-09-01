#!/usr/bin/env python3
"""Pack the approved first-13 Command128 prefix for the attention backend."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/results/qwen2_q1024_backend_inputs"
ENCODING = json.loads((ROOT / "config/descriptor_public_encoding.json").read_text())
assert ENCODING["approval_status"] == "APPROVED"

operations = [
    "l0.input_norm", "l0.q", "l0.q_bias", "l0.q_rope",
    "l0.k", "l0.k_bias", "l0.k_rope", "l0.v", "l0.v_bias",
    "l0.kv_append", "l0.qk", "l0.softmax", "l0.pv",
]
manifest = [
    json.loads(line)
    for line in (ROOT / "reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl")
    .read_text().splitlines()[:len(operations)]
]
assert [entry["operation"] for entry in manifest] == operations
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "first13_commands.bin").write_bytes(
    b"".join(int(entry["word"], 16).to_bytes(16, "little") for entry in manifest)
)
print("QWEN2_Q1024_ATTENTION_INPUTS_PASS commands=13 approved_descriptor=true")
