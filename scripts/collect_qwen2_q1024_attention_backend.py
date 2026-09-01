#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/results/qwen2_q1024_attention_backend"
LOG = OUT / "run.log"
BASE = json.loads((ROOT / "reports/execution/qwen2_q1024_exact_backend_result.json").read_text())

text = LOG.read_text()
match = re.search(
    r"QWEN2_Q1024_ATTENTION_BACKEND_PASS commands=(\d+) rows=(\d+) updates=(\d+) "
    r"merges=(\d+) attention_values=(\d+) score_matrix_bytes=(\d+) "
    r"max_fp32_error=([0-9.eE+-]+) max_bf16_error=([0-9.eE+-]+)", text)
assert match
commands, rows, updates, merges, values, score_bytes = map(int, match.groups()[:6])
fp32_error, bf16_error = map(float, match.groups()[6:])
assert (commands, rows, updates, merges, values, score_bytes) == (
    13, 1024, 6297600, 43008, 1572864, 0)
assert fp32_error <= 0.002

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

for name in ("q_rope", "k_rope", "v_bias"):
    assert sha(OUT / f"{name}.bin") == BASE["hashes"][name]

attention_fp32 = np.fromfile(OUT / "attention_fp32.bin", np.float32).reshape(1024, 1536)
attention_bf16 = np.fromfile(OUT / "attention_bf16.bin", np.uint16).reshape(1024, 1536)
q_bf16 = np.fromfile(OUT / "q_rope.bin", np.uint16).reshape(1024, 1536)
k_bf16 = np.fromfile(OUT / "k_rope.bin", np.uint16).reshape(1024, 256)
v_bf16 = np.fromfile(OUT / "v_bias.bin", np.uint16).reshape(1024, 256)
assert np.isfinite(attention_fp32).all()
for head in range(12):
    kv_head = head // 6
    np.testing.assert_array_equal(
        attention_bf16[0, head * 128:(head + 1) * 128],
        v_bf16[0, kv_head * 128:(kv_head + 1) * 128],
    )

def bf16_to_fp32(values):
    return (values.astype(np.uint32) << 16).view(np.float32)

independent_max_error = 0.0
scale = np.frombuffer(bytes.fromhex("f304b53d"), dtype=np.float32)[0]
for token in (0, 127, 128, 383, 1023):
    for head in (0, 5, 6, 11):
        kv_head = head // 6
        q_row = bf16_to_fp32(q_bf16[token, head * 128:(head + 1) * 128]).astype(np.float64)
        k_rows = bf16_to_fp32(k_bf16[:token + 1, kv_head * 128:(kv_head + 1) * 128]).astype(np.float64)
        v_rows = bf16_to_fp32(v_bf16[:token + 1, kv_head * 128:(kv_head + 1) * 128]).astype(np.float64)
        scores = (k_rows @ q_row) * float(scale)
        weights = np.exp(scores - scores.max())
        truth = (weights[:, None] * v_rows).sum(axis=0) / weights.sum()
        actual = attention_fp32[token, head * 128:(head + 1) * 128].astype(np.float64)
        independent_max_error = max(independent_max_error, float(np.max(np.abs(actual - truth))))
assert independent_max_error <= 0.002

result = {
    "schema_version": 1,
    "status": "PASS_Q1024_FIRST13_EXACT_ATTENTION_BACKEND",
    "evidence_class": "chained_CXX_OpenMP_hardware_semantics_backend_not_RTL",
    "commands": 13,
    "rows": 1024,
    "attention_values": values,
    "causal_updates": updates,
    "hierarchical_block_tokens": 128,
    "summary_merges": merges,
    "score_matrix_materialized": False,
    "score_matrix_bytes": 0,
    "max_attention_error": {
        "fp32_probability": fp32_error,
        "bf16_boundary": bf16_error,
        "required_fp32_threshold": 0.002,
        "independent_sample_fp64_reference": independent_max_error,
    },
    "pv_probability_path": "FP32_probability_input_conversion_required",
    "checks": {
        "approved_public_descriptor_encoding": True,
        "first13_Command128_consumed": True,
        "first9_outputs_match_accepted_backend_hashes": True,
        "no_external_reference_tensor_injection_after_first9": True,
        "GQA_12Q_2KV_mapping": True,
        "causal_token0_equals_V_bit_exact": True,
        "independent_tokens_0_127_128_383_1023_heads_0_5_6_11": True,
        "universal_hierarchical_block128": True,
        "no_score_matrix": True,
        "direct_BF16_probability_rejected_over_threshold": True,
    },
    "hashes": {
        name: sha(OUT / name)
        for name in (
            "attention_fp32.bin", "attention_bf16.bin",
            "attention_m_fp32.bin", "attention_l_fp32.bin", "run.log")
    },
    "open": [
        "real_Revision8B_QK_tile_RTL_anchor",
        "real_softmax_merge128_PV_RTL_anchor",
        "OProj_residual_postnorm_MLP",
        "seven_groups",
        "P3",
    ],
    "non_claims": [
        "attention payload is a chained hardware-semantics C++ backend rather than RTL simulation",
        "the existing first16 RTL anchor ends at first-nine QKV bias RoPE",
        "this does not close layer0 or L5.6d",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_attention_backend_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "max_error": fp32_error, "merges": merges}, sort_keys=True))
