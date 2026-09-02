from heteronpu.l9_payload_coverage import classify_layer0_payload_coverage

SFU = "if(cmd_i[7:0]==8'h32) begin active_q<=1; end"
MATRIX = "if(cmd_i[7:0] inside {8'h20,8'h21,8'h23,8'h24}) begin active_q<=1; end"
KV_PRIMITIVE = "module kv_tensor_stream_endpoint(input logic cfg_valid_i); endmodule"


def test_layer0_payload_coverage_matches_current_endpoint_boundaries():
    report = classify_layer0_payload_coverage(
        sfu_endpoint_source=SFU,
        matrix_endpoint_source=MATRIX,
        kv_endpoint_source=KV_PRIMITIVE,
    )
    assert report["status"] == "PASS_LAYER0_PAYLOAD_COVERAGE_CLASSIFIED"
    assert report["layer_commands"] == 21
    assert report["real_payload_numerically_tested"] == 2
    assert report["remaining_real_payload_commands"] == 19
    assert report["state_counts"] == {
        "real_payload_numerically_tested": 2,
        "command_endpoint_opcode_unsupported": 9,
        "kv_stream_primitive_present_command128_adapter_open": 1,
        "endpoint_opcode_supported_payload_feeder_open": 8,
        "endpoint_opcode_supported_not_numerically_tested": 1,
    }
    assert report["implementation_buckets"]["H_KV_APPEND_adapter"] == [10]


def test_kv_append_command_adapter_is_detected():
    kv_adapter = "module x(input logic cmd_valid_i); if(cmd[7:0]==8'h41); endmodule"
    report = classify_layer0_payload_coverage(
        sfu_endpoint_source=SFU,
        matrix_endpoint_source=MATRIX,
        kv_endpoint_source=kv_adapter,
    )
    row = report["commands"][9]
    assert row["operation"] == "l0.kv_append"
    assert row["state"] == "kv_command128_adapter_present_payload_not_tested"
    assert report["endpoint_opcode_sets"]["kv_command128_adapter_detected"]
