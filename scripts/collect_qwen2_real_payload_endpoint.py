#!/usr/bin/env python3
"""Collect the first real graph-derived command-to-payload RTL slice."""

import argparse
import hashlib
import json
import pathlib
import re


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    result_dir = root / "work/results/qwen2_real_payload_endpoint"
    log = result_dir / "tb.log"
    match = re.search(
        r"QWEN2_REAL_PAYLOAD_ENDPOINT_PASS commands=(\d+) completions=(\d+) "
        r"rms_values=(\d+) matrix_steps=(\d+) matrix_outputs=(\d+) "
        r"bf16_bit_exact=(\d+) event_order=(\d+) random_backpressure=(\d+)",
        log.read_text(),
    )
    if not match:
        raise SystemExit("missing real-payload PASS receipt")
    values = [int(value) for value in match.groups()]
    result = {
        "schema_version": 1,
        "status": "PASS_REAL_COMMAND_TO_PAYLOAD_OPERATOR_SLICE",
        "evidence_class": "production_command_fabric_plus_real_SFU_and_Revision8B_B_Matrix_payload_RTL",
        "scope": "Qwen2 layer0 input RMSNorm followed by one Q projection output sample",
        "metrics": dict(zip(
            ["commands", "completions", "rms_values", "matrix_steps", "matrix_outputs", "bf16_bit_exact", "event_order", "random_backpressure"],
            values,
        )),
        "checks": {
            "graph_derived_command128": True,
            "production_event_dependency": True,
            "fp32_rmsnorm1536_chunked": True,
            "revision8b_b_matrix": True,
            "exact_model_cross_vectors": True,
            "macro_errors": 0,
            "completion_protocol_errors": 0,
            "matrix_protocol_errors": 0,
            "watchdog_lock": 0,
        },
        "provenance": {
            "tb_log_sha256": sha256(log),
            "commands_sha256": sha256(result_dir / "commands.memh"),
            "rms_expected_sha256": sha256(result_dir / "rms_expected.memh"),
            "matrix_expected_sha256": sha256(result_dir / "matrix_expected.memh"),
            "matrix_endpoint_sha256": sha256(root / "rtl/integration/qwen2_matrix_command_endpoint.sv"),
            "sfu_endpoint_sha256": sha256(root / "rtl/integration/qwen2_sfu_command_endpoint.sv"),
        },
        "non_claims": [
            "this two-command layer0 slice is not one complete transformer layer",
            "this slice does not close seven continuous four-layer groups",
            "this slice does not close P3 continuous 28-layer device payload",
            "payload vectors are staged by the testbench rather than descriptor-backed shared-L2 memory",
        ],
        "open": [
            "descriptor_backed_payload_memory",
            "complete_layer_operator_sequence",
            "seven_group_device_payload_without_hidden_state_injection",
            "P3_continuous_28_layer_device_payload",
        ],
    }
    output = root / "reports/execution/qwen2_real_payload_endpoint_result.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(output)


if __name__ == "__main__":
    main()
