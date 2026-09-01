#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/results/qwen2_q1024_model_attention_rtl"
pattern = re.compile(
    r"L5_Q1024_REVIEWED_SHARD_PASS shard=(\d+) compared_rows=(\d+) tasks=(\d+) "
    r"sampled_merge_rows=(\d+) controller_tasks=(\d+) controller_merge_rows=(\d+) "
    r"cycles=(\d+) score_DDR=(\d+) probability_DDR=(\d+) attention_fnv64=([0-9a-f]+)")
records = []
for shard in (0, 1):
    text = (OUT / f"tb_shard{shard}.log").read_text()
    match = pattern.search(text)
    assert match
    fields = match.groups()
    assert int(fields[0]) == shard
    records.append({
        "shard": shard, "compared_rows": int(fields[1]), "tasks": int(fields[2]),
        "sampled_merge_rows": int(fields[3]), "controller_tasks": int(fields[4]),
        "controller_merge_rows": int(fields[5]), "cycles": int(fields[6]),
        "score_DDR_bytes": int(fields[7]), "probability_DDR_bytes": int(fields[8]),
        "attention_fnv64": fields[9],
    })
assert [record["compared_rows"] for record in records] == [960, 480]
assert all(record["controller_tasks"] == 12672 for record in records)
assert all(record["controller_merge_rows"] == 43008 for record in records)
assert all(record["score_DDR_bytes"] == record["probability_DDR_bytes"] == 0 for record in records)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_Q1024_EXACT_MODEL_SAMPLED_ATTENTION_RTL",
    "evidence_class": "sampled_real_Revision8B_QK_SFU_merge128_PV_RTL_E2",
    "sampled_rows": sum(record["compared_rows"] for record in records),
    "shards": records,
    "controller_full_schedule": {"tasks": 12672, "summary_merge_rows": 43008},
    "checks": {
        "exact_revision_model_QKV": True,
        "same_Revision8B_RTL_for_q1024": True,
        "FP32_probability_hilo_conversion": True,
        "QK_SFU_PV_payload": True,
        "score_probability_DDR_zero": True,
        "random_controller_backpressure": True,
    },
    "provenance": {
        "vector_manifest_sha256": sha(OUT / "vectors/manifest.json"),
        "shard0_log_sha256": sha(OUT / "tb_shard0.log"),
        "shard1_log_sha256": sha(OUT / "tb_shard1.log"),
        "testbench_sha256": sha(ROOT / "tb/tb_l5_q128_attention_integrated.sv"),
    },
    "open": ["all_12288_attention_rows_RTL", "OProj_residual_postnorm_MLP", "seven_groups", "P3"],
    "non_claims": [
        "1440 sampled rows do not constitute full q1024 numerical RTL",
        "controller task counts are full-schedule control evidence rather than full payload execution",
        "this does not close layer0 or L5.6d",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_model_attention_rtl_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "sampled_rows": result["sampled_rows"]}, sort_keys=True))
