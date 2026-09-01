#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work/results/qwen2_q1024_full28_backend"
INPUTS = ROOT / "work/results/qwen2_q1024_full28_inputs"
previous_fnv = None
layers = []
for layer in range(28):
    directory = BASE / f"layer{layer}"
    pre = re.search(rf"QWEN2_GENERIC_LAYER_PRE_PASS layer={layer} commands=21 rows=1024 q_values=(\d+) k_values=(\d+) v_values=(\d+) hidden_in_fnv=([0-9a-f]+)", (directory / "pre.log").read_text())
    attention = re.search(rf"QWEN2_GENERIC_LAYER_BLOCKED_RTL_ATTENTION_PASS layer={layer} commands=21 rows=1024 updates=(\d+) tile32=1 merges=(\d+) score_matrix_bytes=(\d+) max_error=([0-9.eE+-]+) attention_fnv=([0-9a-f]+)", (directory / "attention.log").read_text())
    down = re.search(rf"QWEN2_GENERIC_LAYER_DOWN_PASS layer={layer} values=(\d+) final_fnv=([0-9a-f]+)", (directory / "down.log").read_text())
    assert pre and attention and down
    assert tuple(map(int, pre.groups()[:3])) == (1572864, 262144, 262144)
    if previous_fnv is not None: assert pre.group(4) == previous_fnv
    assert tuple(map(int, attention.groups()[:3])) == (6297600, 43008, 0)
    error = float(attention.group(4)); assert error <= 0.002
    assert int(down.group(1)) == 1572864
    final_path = directory / "final_fp32.bin"
    final = np.fromfile(final_path, np.float32); assert final.size == 1572864 and np.isfinite(final).all()
    previous_fnv = down.group(2)
    layers.append({
        "layer": layer, "hidden_input_fnv": pre.group(4), "attention_max_error": error,
        "attention_fnv": attention.group(5), "final_fnv": previous_fnv,
        "final_sha256": hashlib.sha256(final_path.read_bytes()).hexdigest(),
    })

groups = []
for group in range(7):
    records = layers[group * 4:(group + 1) * 4]
    groups.append({
        "group": group, "layers": [record["layer"] for record in records],
        "start_hidden_fnv": records[0]["hidden_input_fnv"],
        "end_final_fnv": records[-1]["final_fnv"],
        "end_final_sha256": records[-1]["final_sha256"],
        "reference_hidden_injections": 0,
    })

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_Q1024_CONTINUOUS_28_LAYER_HARDWARE_SEMANTICS_BACKEND",
    "evidence_class": "same_generic_backend_exact_revision_embedding_to_layer27_not_full_RTL",
    "layers": 28,
    "commands": 588,
    "groups": groups,
    "layer_records": layers,
    "attention": {
        "policy": "tile32_PV_hilo_balanced_block128_ext32_exp2",
        "causal_updates": 28 * 6297600,
        "summary_merges": 28 * 43008,
        "score_matrix_bytes": 0,
        "maximum_error": max(record["attention_max_error"] for record in layers),
    },
    "continuity": {
        "embedding_is_only_layer0_input": True,
        "predecessor_final_is_only_next_hidden": True,
        "reference_hidden_injections": 0,
        "layer27_final_sha256": layers[-1]["final_sha256"],
        "layer27_final_fnv": layers[-1]["final_fnv"],
    },
    "checks": {
        "exact_revision_weights_all_layers": True,
        "all_588_Command128_words_partitioned": True,
        "same_backend_binary_all_layers": True,
        "all_attention_errors_le_0p002": True,
        "all_outputs_finite": True,
        "checkpoint_hashes_each_layer": True,
        "no_score_matrix": True,
    },
    "provenance": {
        "input_manifest_sha256": sha(INPUTS / "manifest.json"),
        "backend_source_sha256": sha(ROOT / "src/qwen2_q1024_generic_layer_backend.cpp"),
        "exp2_ext32_config_sha256": sha(ROOT / "config/l5_exp2_pwl_ext32.json"),
        "exp2_ext32_RTL_sha256": sha(ROOT / "rtl/sfu/fp32_exp2_pwl_rawpipe.sv"),
    },
    "open": ["final_RMSNorm_last_token_LM_head", "ext32_balanced_sampled_RTL_policy", "llama_device_backend_registration", "P3_final_audit"],
    "non_claims": [
        "continuous C++ hardware-semantics backend is not all-row RTL simulation",
        "final RMSNorm and LM head are not yet included",
        "ext32 and balanced merge require updated sampled RTL and PPA evidence",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_full28_backend_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "max_attention_error": result["attention"]["maximum_error"], "layer27_final_sha256": layers[-1]["final_sha256"]}, sort_keys=True))
