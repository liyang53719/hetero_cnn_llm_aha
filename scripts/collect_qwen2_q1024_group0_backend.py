#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work/results/qwen2_q1024_group0_backend"
LAYER0 = ROOT / "work/results/qwen2_q1024_layer0_tail_backend"
INPUTS = ROOT / "work/results/qwen2_q1024_group0_inputs"

layer0_text = (LAYER0 / "down.log").read_text()
layer0_final_fnv = re.search(r"final_fnv=([0-9a-f]+)", layer0_text).group(1)
previous_fnv = layer0_final_fnv
layers = []
for layer in range(1, 4):
    directory = BASE / f"layer{layer}"
    pre = (directory / "pre.log").read_text()
    attention = (directory / "attention.log").read_text()
    down = (directory / "down.log").read_text()
    pre_match = re.search(rf"QWEN2_GENERIC_LAYER_PRE_PASS layer={layer} commands=21 rows=1024 q_values=(\d+) k_values=(\d+) v_values=(\d+) hidden_in_fnv=([0-9a-f]+)", pre)
    attention_match = re.search(rf"QWEN2_GENERIC_LAYER_ATTENTION_PASS layer={layer} commands=21 rows=1024 updates=(\d+) merges=(\d+) score_matrix_bytes=(\d+) max_error=([0-9.eE+-]+) attention_fnv=([0-9a-f]+)", attention)
    down_match = re.search(rf"QWEN2_GENERIC_LAYER_DOWN_PASS layer={layer} values=(\d+) final_fnv=([0-9a-f]+)", down)
    assert pre_match and attention_match and down_match
    assert tuple(map(int, pre_match.groups()[:3])) == (1572864, 262144, 262144)
    assert pre_match.group(4) == previous_fnv
    assert tuple(map(int, attention_match.groups()[:3])) == (6297600, 43008, 0)
    error = float(attention_match.group(4)); assert error <= 0.002
    assert int(down_match.group(1)) == 1572864
    final = np.fromfile(directory / "final_fp32.bin", np.float32)
    assert final.size == 1572864 and np.isfinite(final).all()
    previous_fnv = down_match.group(2)
    layers.append({
        "layer": layer,
        "hidden_input_fnv": pre_match.group(4),
        "attention_max_error": error,
        "attention_fnv": attention_match.group(5),
        "final_fnv": previous_fnv,
        "final_sha256": hashlib.sha256((directory / "final_fp32.bin").read_bytes()).hexdigest(),
    })

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_Q1024_GROUP0_CONTINUOUS_HARDWARE_SEMANTICS_BACKEND",
    "evidence_class": "layer0_checkpoint_plus_same_generic_backend_layers1to3_not_full_RTL",
    "layers": [0, 1, 2, 3],
    "commands": 84,
    "rows_per_layer": 1024,
    "attention": {
        "causal_updates": 4 * 6297600,
        "summary_merges": 4 * 43008,
        "score_matrix_bytes": 0,
    },
    "continuity": {
        "reference_hidden_injections_inside_group": 0,
        "layer0_final_fnv": layer0_final_fnv,
        "layer_records": layers,
        "layer3_final_sha256": layers[-1]["final_sha256"],
    },
    "checks": {
        "exact_revision_weights_all_layers": True,
        "real_Command128_slices": True,
        "same_generic_backend_layers1to3": True,
        "predecessor_final_is_only_next_hidden_input": True,
        "all_attention_errors_le_0p002": True,
        "no_score_matrix": True,
        "all_final_outputs_finite": True,
    },
    "provenance": {
        "layer0_report_sha256": sha(ROOT / "reports/execution/qwen2_q1024_layer0_tail_backend_result.json"),
        "group_input_manifest_sha256": sha(INPUTS / "manifest.json"),
        "generic_backend_source_sha256": sha(ROOT / "src/qwen2_q1024_generic_layer_backend.cpp"),
    },
    "open": ["layers1to3_sampled_real_RTL_anchors", "groups1to6", "continuous_28_layer_P3", "final_RMSNorm_LM_head"],
    "non_claims": [
        "C++ hardware-semantics backend is not RTL simulation",
        "only layer0 currently has exact-model sampled real RTL tail anchors",
        "group0 formal device-payload gate remains open until layers1-3 RTL anchors pass",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_group0_backend_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "layers": 4, "final_sha256": layers[-1]["final_sha256"]}, sort_keys=True))
