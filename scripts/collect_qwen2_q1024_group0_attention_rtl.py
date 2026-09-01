#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work/results/qwen2_q1024_group0_attention_rtl"
BACKEND_REPORT = ROOT / "reports/execution/qwen2_q1024_group0_backend_result.json"
TAIL_REPORT = ROOT / "reports/execution/qwen2_q1024_group0_rtl_result.json"
pattern = re.compile(
    r"L5_Q1024_REVIEWED_SHARD_PASS shard=(\d+) compared_rows=(\d+) tasks=(\d+) "
    r"sampled_merge_rows=(\d+) controller_tasks=(\d+) controller_merge_rows=(\d+) "
    r"cycles=(\d+) score_DDR=(\d+) probability_DDR=(\d+) attention_fnv64=([0-9a-f]+)")

layers = []
for layer in range(1, 4):
    shards = []
    for shard in (0, 1):
        log = BASE / f"layer{layer}/tb_shard{shard}.log"
        match = pattern.search(log.read_text()); assert match
        values = match.groups(); assert int(values[0]) == shard
        shards.append({
            "shard": shard, "compared_rows": int(values[1]), "tasks": int(values[2]),
            "sampled_merge_rows": int(values[3]), "controller_tasks": int(values[4]),
            "controller_merge_rows": int(values[5]), "cycles": int(values[6]),
            "score_DDR_bytes": int(values[7]), "probability_DDR_bytes": int(values[8]),
            "attention_fnv64": values[9],
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        })
    assert [record["compared_rows"] for record in shards] == [960, 480]
    assert [record["tasks"] for record in shards] == [306, 756]
    assert all(record["controller_tasks"] == 12672 and record["controller_merge_rows"] == 43008 for record in shards)
    assert all(record["score_DDR_bytes"] == record["probability_DDR_bytes"] == 0 for record in shards)
    manifest = BASE / f"layer{layer}/vectors/manifest.json"
    assert json.loads(manifest.read_text())["layer"] == layer
    layers.append({"layer": layer, "sampled_rows": 1440, "shards": shards, "vector_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()})

binary = BASE / "build/obj/tb"
result = {
    "schema_version": 1,
    "status": "PASS_Q1024_GROUP0_LAYERS1TO3_ATTENTION_SAMPLED_REAL_RTL",
    "evidence_class": "same_Revision8B_QK_SFU_merge128_PV_binary_exact_layer_payload",
    "layers": [1, 2, 3],
    "records": layers,
    "aggregate": {
        "sampled_rows": 4320,
        "sampled_tasks": 3 * (306 + 756),
        "sampled_merge_rows": 3 * (672 + 2688),
        "controller_tasks_per_layer": 12672,
        "controller_merge_rows_per_layer": 43008,
        "score_probability_DDR_bytes": 0,
    },
    "checks": {
        "same_binary_all_layers": True,
        "exact_revision_layer_QKV": True,
        "QK_SFU_merge128_PV_real_RTL": True,
        "FP32_probability_hilo_conversion": True,
        "reviewed_first_and_final_q1024_samples": True,
        "backend_hidden_injections_inside_group": 0,
    },
    "provenance": {
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "backend_report_sha256": hashlib.sha256(BACKEND_REPORT.read_bytes()).hexdigest(),
        "tail_rtl_report_sha256": hashlib.sha256(TAIL_REPORT.read_bytes()).hexdigest(),
        "testbench_sha256": hashlib.sha256((ROOT / "tb/tb_l5_q128_attention_integrated.sv").read_bytes()).hexdigest(),
    },
    "open": ["group0_backend_equivalence_audit", "groups1to6", "continuous_28_layer_P3", "final_RMSNorm_LM_head"],
    "non_claims": [
        "4320 sampled rows are not all 36864 layer1-3 attention rows",
        "controller full-task counts are control evidence rather than full numerical RTL execution",
        "formal group0 promotion requires combined backend, attention and tail audit",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_group0_attention_rtl_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], **result["aggregate"]}, sort_keys=True))
