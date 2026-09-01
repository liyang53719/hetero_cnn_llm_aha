#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/results/qwen2_q1024_layer0_tail_rtl"
LOG = OUT / "tb.log"
text = LOG.read_text()
for operation, ksteps in (("oproj", 1536), ("gate", 1536), ("up", 1536), ("down", 8960)):
    assert f"QWEN2_LAYER0_MATRIX_SAMPLE_PASS operation={operation} tiles=3 k={ksteps} values=1536" in text
match = re.search(r"QWEN2_Q1024_LAYER0_TAIL_RTL_PASS matrix_steps=(\d+) matrix_values=(\d+) silu_lanes=(\d+) silu_values=(\d+) silu_random_backpressure=(\d+) matrix_out_ready=(\d+) same_RTL=(\d+)", text)
assert match and tuple(map(int, match.groups())) == (40704, 6144, 8, 8192, 1, 1, 1)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_Q1024_LAYER0_TAIL_SAMPLED_REAL_RTL",
    "evidence_class": "exact_model_sampled_Revision8B_Matrix_and_8lane_SiLU_RTL_E2",
    "rows": 16,
    "matrix": {
        "operations": ["oproj", "gate", "up", "down"],
        "physical_tiles_each": 3,
        "physical_tile_policy": "first_middle_last",
        "steps": 40704,
        "bf16_bit_exact_values": 6144,
    },
    "silu": {"physical_lanes": 8, "values": 8192, "bit_exact": 8192},
    "checks": {
        "same_Revision8B_Matrix_source": True,
        "same_parameterized_SiLU_source": True,
        "no_sequence_specific_RTL": True,
        "silu_random_output_backpressure": True,
        "matrix_output_ready_held_high_as_in_existing_component_tests": True,
        "generated_or_upstream_RTL_modified": False,
    },
    "provenance": {
        "log_sha256": sha(LOG),
        "vector_manifest_sha256": sha(OUT / "vectors/manifest.json"),
        "testbench_sha256": sha(ROOT / "tb/tb_qwen2_q1024_layer0_tail_rtl.sv"),
        "matrix_rtl_sha256": sha(ROOT / "rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv"),
        "silu_rtl_sha256": sha(ROOT / "rtl/sfu/bf16_silu_mul_lut_array.sv"),
    },
    "open": ["all_layer0_tail_tiles_RTL", "all_attention_rows_RTL", "seven_groups", "P3"],
    "non_claims": [
        "first-middle-last Matrix tiles are sampled rather than all output tiles",
        "rows0-15 do not constitute full q1024 tail RTL",
        "this checkpoint does not add Matrix result-side random backpressure beyond existing Matrix protocol regressions",
        "this anchor does not close L5.6d",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_layer0_tail_rtl_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "matrix_values": 6144, "silu_values": 8192}, sort_keys=True))
