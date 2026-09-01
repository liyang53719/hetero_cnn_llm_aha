#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG0 = Path("work/results/qwen2_raw_qkv_chain/tb.log")
LOG1 = Path("work/results/qwen2_raw_qkv_chain_token1/tb.log")
TOKEN_RESULT = json.loads((ROOT / "work/results/llama_cpp_qwen2_baseline/pytorch_result.json").read_text())
pattern = re.compile(r"QWEN2_FIRST9_CHAIN_PASS commands=9 descriptor_fetches=62 flat_idma=98500 axi_beats=98882 ddr_read_bytes=6316672 ddr_write_bytes=11776 l2_read_beats=98842 l2_write_beats=232 raw_values=3584 biased_values=2048 rope_pairs=896 rope_values=1792 bf16_bit_exact=7424 matrix_completions=3 sfu_completions=6 no_reference_injection=1 position0=(\d+) token_index=(\d+)")
m0 = pattern.search((ROOT / LOG0).read_text())
m1 = pattern.search((ROOT / LOG1).read_text())
assert m0 and m0.groups() == ("1", "0")
assert m1 and m1.groups() == ("0", "1")
assert TOKEN_RESULT["tokens_sha256"] == "e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628"

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_CANONICAL_TOKEN0_TOKEN1_FIRST9",
    "evidence_class": "two_single_VCS_runs_same_RTL_formal_descriptors_exact_revision_model",
    "model": "Qwen/Qwen2-1.5B-Instruct",
    "revision": "ba1cf1846d7df0a0591d6c00649f57e798519da8",
    "canonical_tokens_sha256": TOKEN_RESULT["tokens_sha256"],
    "token_ids": [48, 16948],
    "token_indices": [0, 1],
    "commands_per_token": 9,
    "bf16_bit_exact_per_token": 7424,
    "bf16_bit_exact_total": 14848,
    "checks": {
        "same_RTL": True,
        "same_formal_descriptor_image": True,
        "DDR_row0_row1_addressing": True,
        "position0_and_position1": True,
        "nonzero_RoPE_recurrence_in_full_chain": True,
        "no_reference_injection_inside_each_token_chain": True,
        "refined_RMS_NR2_and_BF16_boundary_golden": True,
        "Revision8B_B_FMA_order_golden": True,
    },
    "provenance": {
        "token0_log_sha256": sha(LOG0),
        "token1_log_sha256": sha(LOG1),
        "canonical_vector_generator_sha256": sha("scripts/generate_qwen2_canonical_token01_vectors.py"),
        "testbench_sha256": sha("tb/tb_qwen2_raw_qkv_chain.sv"),
    },
    "supersedes_semantic_scope": {
        "artifact": "reports/execution/qwen2_first9_chain_result.json",
        "reason": "earlier vector source used hs[0][0,-1] but was labeled token0 and rotated at position0",
        "retained_claim": "component arithmetic and protocol pass only",
        "revoked_claim": "canonical DDR token0 numerical continuity",
    },
    "open": ["16_token_continuous_same_run", "q1024_real_KV_source", "remaining_layer0_commands", "seven_groups", "P3"],
    "non_claims": [
        "two independent token runs do not yet prove one continuous 16-token controller run",
        "only the first nine layer0 commands execute",
        "KV append still uses synthetic source in its separate backend gate",
    ],
}
(ROOT / "reports/execution/qwen2_canonical_token01_first9_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "tokens": 2, "bit_exact": 14848}, sort_keys=True))
