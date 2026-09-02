from __future__ import annotations

import pytest

from heteronpu.rtl_transport_evidence import (
    classify_existing_rtl_evidence,
    inspect_existing_rtl_evidence,
)

SUBMISSION_SCRIPT = """
grep -q 'QWEN2_REAL_COMMAND_SUBMISSION_PASS commands=588 completions=588 matrix=252 sfu=308 kv=28'
"""
SUBMISSION_TB = """
hetero_l3_command_fabric dut();
logic [127:0] held[0:5]; logic [7:0] delay[0:5]; logic [31:0] lfsr;
assign er[e]=!busy[e]&&(lfsr[e]||lfsr[e+8]);
assign cd[e*56+:56]={held[e][55:40],8'd0,3'(e),29'd0};
assign rv=0; assign wv=0; assign prspv=0;
completed<=completed+1;
$display("QWEN2_REAL_COMMAND_SUBMISSION_PASS commands=588 completions=588 matrix=252 sfu=308 kv=28 event_grants=588 random_backpressure=1");
"""
PAYLOAD_TB = """
assign rv=0; assign wv=0; assign prspv=0;
logic [31:0] lfsr; assign sor=lfsr[0]||lfsr[4]; assign mor=lfsr[1]||lfsr[6];
$display("QWEN2_REAL_PAYLOAD_ENDPOINT_PASS commands=2 completions=2 rms_values=1536 matrix_steps=1536 matrix_outputs=32 bf16_bit_exact=1568 event_order=1 random_backpressure=1");
"""
PAYLOAD_SCRIPT = """
qwen2_sfu_command_endpoint.sv qwen2_matrix_command_endpoint.sv
rms_expected.memh matrix_expected.memh
QWEN2_REAL_PAYLOAD_ENDPOINT_PASS commands=2 completions=2 rms_values=1536 matrix_steps=1536 matrix_outputs=32 bf16_bit_exact=1568
"""


def test_existing_rtl_evidence_is_split_into_two_levels():
    report = classify_existing_rtl_evidence(
        submission_script=SUBMISSION_SCRIPT,
        submission_tb=SUBMISSION_TB,
        payload_script=PAYLOAD_SCRIPT,
        payload_tb=PAYLOAD_TB,
    )
    assert report["status"] == "PASS_EXISTING_RTL_EVIDENCE_CLASSIFIED"
    assert report["checks"]["588_command_frontend_dispatch"]
    assert report["checks"]["submission_is_stub_endpoint_smoke"]
    assert report["checks"]["two_command_real_payload_endpoint"]
    assert not report["checks"]["complete_21_command_layer_payload"]
    assert report["checks"]["two_command_endpoint_output_backpressure"]
    assert not report["checks"]["full_matrix_sfu_kv_internal_backpressure"]
    assert report["next_gate"]["remaining_real_payload_commands_after_existing_endpoint"] == 19


def test_submission_random_ready_is_not_internal_payload_backpressure():
    evidence = inspect_existing_rtl_evidence(
        submission_script=SUBMISSION_SCRIPT,
        submission_tb=SUBMISSION_TB,
        payload_script=PAYLOAD_SCRIPT,
        payload_tb=PAYLOAD_TB,
    )
    assert evidence.command_port_random_backpressure
    assert evidence.real_payload_output_backpressure_proven
    assert not evidence.full_matrix_sfu_kv_internal_backpressure_proven
    assert evidence.descriptor_l2_activity_tied_off
    assert not evidence.real_payload_modules_in_submission


def test_missing_pass_signature_fails_classification():
    with pytest.raises(ValueError, match="submission PASS signature"):
        inspect_existing_rtl_evidence(
            submission_script="",
            submission_tb=SUBMISSION_TB.replace("QWEN2_REAL_COMMAND_SUBMISSION_PASS", "NO_PASS"),
            payload_script=PAYLOAD_SCRIPT,
            payload_tb=PAYLOAD_TB,
        )
