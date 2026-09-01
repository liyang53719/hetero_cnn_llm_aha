#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


cpu = load("work/results/llama_cpp_qwen2_baseline/result.json")
graph = load("reports/execution/llama_cpp_qwen2_graph_lowering_result.json")
closure = load("reports/execution/upstream_closure.json")
log = (ROOT / "work/results/qwen2_real_command_submission/tb.log").read_text()
match = re.search(
    r"QWEN2_REAL_COMMAND_SUBMISSION_PASS commands=(\d+) completions=(\d+) "
    r"matrix=(\d+) sfu=(\d+) kv=(\d+) event_grants=(\d+) "
    r"random_backpressure=1 macro_errors=0 protocol_errors=0", log)
if not match:
    raise SystemExit("submission PASS missing")
commands, completions, matrix, sfu, kv, grants = map(int, match.groups())
expected = graph["lowering"]["engine_counts"]
checks = {
    "llama_commit": closure["repositories"]["llama_cpp"]["commit"] ==
                    "0b5be7e4a25862bc2777d0c47eae18788a8c963a" and
                    not closure["repositories"]["llama_cpp"]["dirty"],
    "cpu_baseline": cpu["status"] == "PASS_REAL_LLAMA_CPU_BASELINE" and
                    cpu["argmax_match"] and cpu["top10_overlap"] == 10,
    "real_q1024_graph": graph["status"] ==
                        "PASS_REAL_Q1024_GGML_NODE_TENSOR_COMMAND128_LOWERING" and
                        graph["graph"]["nodes"] == 930 and graph["graph"]["ubatch"] == 1024 and
                        graph["gguf"]["tensors"] == 338,
    "traceable_lowering": graph["lowering"]["commands"] == 588 and
                          graph["lowering"]["manifest_records"] == 588,
    "submission": commands == completions == grants == 588 and
                  matrix == expected["MATRIX"] and sfu == expected["SFU_CGRA"] and
                  kv == expected["KV"],
}
if not all(checks.values()):
    raise SystemExit(f"readiness: {checks}")
result = {
    "schema_version": 2,
    "status": "PASS_REAL_Q1024_GRAPH_TRACEABLE_COMMAND_SUBMISSION_PAYLOAD_MEMORY_OPEN",
    "evidence_class": "real_llama_CPU_q1024_graph_GGUF_traceable_Command128_and_production_fabric_not_full_device_payload",
    "model": "Qwen/Qwen2-1.5B-Instruct", "revision": graph["revision"],
    "llama_cpp": {
        "commit": graph["llama_cpp_commit"], "gguf_sha256": graph["gguf"]["sha256"],
        "cpu_argmax": cpu["llama_argmax"], "pytorch_argmax": cpu["pytorch_argmax"],
        "top10_overlap": cpu["top10_overlap"], "sequence": 1024, "ubatch": 1024,
    },
    "graph": {
        "nodes": 930, "tensors": 338, "commands": commands,
        "commands_per_layer": graph["lowering"]["commands_per_layer"],
        "matrix_commands": matrix, "sfu_commands": sfu, "kv_commands": kv,
        "command_sha256": graph["lowering"]["command_sha256"],
        "node_tensor_bindings": graph["lowering"]["manifest_records"],
    },
    "submission": {
        "commands": commands, "completions": completions, "event_grants": grants,
        "random_backpressure": True, "macro_errors": 0, "protocol_errors": 0,
    },
    "checks": checks,
    "provenance": {
        "cpu_result_sha256": sha("work/results/llama_cpp_qwen2_baseline/result.json"),
        "graph_capture_sha256": sha("work/results/llama_cpp_qwen2_baseline/graph.tsv"),
        "lowering_report_sha256": sha("reports/execution/llama_cpp_qwen2_graph_lowering_result.json"),
        "submission_log_sha256": sha("work/results/qwen2_real_command_submission/tb.log"),
    },
    "open": ["descriptor_record_image", "descriptor_backed_payload_memory",
             "complete_layer_device_payload", "seven_group_device_payload",
             "P3_continuous_device_payload"],
    "non_claims": [
        "stock llama.cpp CPU is not the project device backend",
        "production command submission uses completion endpoint models",
        "traceable command submission is not complete Matrix/SFU/KV payload execution",
    ],
}
output = ROOT / "reports/execution/llama_cpp_qwen2_device_readiness_result.json"
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "commands": commands,
                  "matrix": matrix, "sfu": sfu, "kv": kv}, sort_keys=True))
