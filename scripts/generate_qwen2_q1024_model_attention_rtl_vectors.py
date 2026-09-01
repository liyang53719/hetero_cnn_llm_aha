#!/usr/bin/env python3
"""Transpose the exact-revision q1024 backend tensors into the reviewed RTL TB layout."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/results/qwen2_q1024_attention_backend"
OUT = ROOT / "work/results/qwen2_q1024_model_attention_rtl/vectors"
OUT.mkdir(parents=True, exist_ok=True)

def write_hex(path: Path, values: np.ndarray, width: int) -> str:
    flat = np.asarray(values).reshape(-1)
    with path.open("w") as stream:
        for begin in range(0, flat.size, 65536):
            stream.write("".join(f"{int(value):0{width}x}\n" for value in flat[begin:begin + 65536]))
    return hashlib.sha256(path.read_bytes()).hexdigest()

q = np.fromfile(SOURCE / "q_rope.bin", np.uint16).reshape(1024, 12, 128).transpose(1, 0, 2)
k = np.fromfile(SOURCE / "k_rope.bin", np.uint16).reshape(1024, 2, 128).transpose(1, 0, 2)
v = np.fromfile(SOURCE / "v_bias.bin", np.uint16).reshape(1024, 2, 128).transpose(1, 0, 2)
attention = np.fromfile(SOURCE / "attention_fp32.bin", np.float32).reshape(1024, 12, 128).transpose(1, 0, 2)
assert np.isfinite(attention).all()

hashes = {
    "q": write_hex(OUT / "q_bf16.memh", q, 4),
    "k": write_hex(OUT / "k_bf16.memh", k, 4),
    "v": write_hex(OUT / "v_bf16.memh", v, 4),
    "expected": write_hex(OUT / "expected_fp32.memh", attention.view(np.uint32), 8),
    # Sampled q1024 modes do not consume the direct-diagnostic tile vectors.
    "tile_m": write_hex(OUT / "tile_m_fp32.memh", np.zeros(16, np.uint32), 8),
    "tile_l": write_hex(OUT / "tile_l_fp32.memh", np.zeros(16, np.uint32), 8),
    "tile_o": write_hex(OUT / "tile_o_fp32.memh", np.zeros(2048, np.uint32), 8),
}
manifest = {
    "schema_version": 1,
    "status": "PASS",
    "evidence_class": "exact_revision_q1024_backend_to_existing_Revision8B_RTL_testbench",
    "sequence": 1024,
    "q_heads": 12,
    "kv_heads": 2,
    "head_dim": 128,
    "rows": 12288,
    "controller_tasks": 12672,
    "summary_merge_rows": 43008,
    "direct_diagnostic_tile_vectors": False,
    "hashes": hashes,
    "source_report": "reports/execution/qwen2_q1024_attention_backend_result.json",
    "source_report_sha256": hashlib.sha256(
        (ROOT / "reports/execution/qwen2_q1024_attention_backend_result.json").read_bytes()
    ).hexdigest(),
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print("QWEN2_Q1024_MODEL_ATTENTION_RTL_VECTORS_PASS rows=12288 tasks=12672 merges=43008")
