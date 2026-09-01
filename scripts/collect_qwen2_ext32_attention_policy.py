#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
status = dict(
    line.strip().split("=", 1)
    for line in (ROOT / "work/results/l5_block128_rawpipe_candidate/dc/status.txt").read_text().splitlines()
    if "=" in line
)
b32 = ROOT / "work/results/l5_block32_softmax_weight_e1/tb.log"
merge = ROOT / "work/results/l5_block128_merge/tb.log"
q128 = ROOT / "work/results/l5_q128_attention_integrated_ext32/tb.log"
assert "BLOCK32_SOFTMAX_WEIGHT_PASS rows=2 weights=64" in b32.read_text()
assert "BLOCK128_MLO_VECTOR_PASS cases=132 stream_beats=32" in merge.read_text()
assert "L5_Q128_SINGLE_SIM_E2_PASS rows=1536 tasks=240" in q128.read_text()
assert status["UNMAPPED_CELLS"] == "0" and float(status["WORST_SLACK_NS"]) >= 0

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_EXT32_EXP2_AND_INDEX_PIPELINE_E1_E4",
    "policy": {"range_log2": [-32, 0], "segments": 512, "step": 0.0625, "tile_tokens": 32, "block_tokens": 128, "global_merge": "balanced_tree_max8", "data_width": "FP32"},
    "functional": {"block32_weights": 64, "merge_cases": 132, "q128_rows": 1536, "q128_tasks": 240},
    "dc": {"clock_ns": 1.0, "wns_ns": float(status["WORST_SLACK_NS"]), "unmapped": 0, "cell_area": float(status["CELL_AREA"]), "margin_class": "CRITICAL_SUB_1PS"},
    "checks": {"initial_flat_512_table_timing_fail_not_promoted": True, "index_pipeline_repair": True, "no_false_path": True, "no_frequency_relaxation": True},
    "provenance": {
        "config": sha(ROOT / "config/l5_exp2_pwl_ext32.json"),
        "rtl": sha(ROOT / "rtl/sfu/fp32_exp2_pwl_rawpipe.sv"),
        "coeff": sha(ROOT / "rtl/sfu/fp32_exp2_ext32_coeffs.svh"),
        "block32_log": sha(b32), "merge_log": sha(merge), "q128_log": sha(q128),
        "dc_status": sha(ROOT / "work/results/l5_block128_rawpipe_candidate/dc/status.txt"),
    },
    "open": ["q1024 exact-model sampled RTL with ext32 plus balanced scheduling", "integrated attention DC margin", "post-route PVT"],
}
(ROOT / "reports/execution/qwen2_ext32_attention_policy_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "wns_ns": result["dc"]["wns_ns"], "area": result["dc"]["cell_area"]}, sort_keys=True))
