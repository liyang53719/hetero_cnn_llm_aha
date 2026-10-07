"""Fail-closed BF16 arithmetic, diagnostic boundaries, and prefix admission.

These small tests require neither downloaded checkpoint payloads nor Torch.
They do not establish model-level BF16 acceptance or execute RTL.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from heteronpu.model_geometry import ModelContractError
from heteronpu import qwen35_bf16_reference as reference


ROOT = Path(__file__).resolve().parents[1]
SAVED_REPORT = ROOT / "reports/execution/U00_2_PREFIX_CHAIN_20261006/numerical_result.json"


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location(
        "qwen35_bf16_audit_test", ROOT / "scripts/run_qwen35_bf16_audit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contract(runner):
    return runner.load_contract(ROOT)


def row(key, values, dtype="bfloat16"):
    return {"key": key, "dtype": dtype, "value": np.asarray(values, dtype=np.float32)}


def test_bf16_preserves_signed_zero_and_exact_values():
    bits = np.array([0, 0x80000000, 0x3F800000, 0xBF800000, 0x7F7F0000], dtype=np.uint32)
    np.testing.assert_array_equal(reference.bf16(bits.view(np.float32)).view(np.uint32), bits)


@pytest.mark.parametrize("raw, expected", [
    (0x3F807FFF, 0x3F800000), (0x3F808000, 0x3F800000),
    (0x3F808001, 0x3F810000), (0x3F818000, 0x3F820000),
    (0xBF807FFF, 0xBF800000), (0xBF808000, 0xBF800000),
    (0xBF808001, 0xBF810000), (0xBF818000, 0xBF820000),
    (0x00008000, 0x00000000), (0x00018000, 0x00020000),
    (0x80008000, 0x80000000), (0x80018000, 0x80020000),
])
def test_bf16_rne_ties_and_neighbors(raw, expected):
    value = np.array([raw], dtype=np.uint32).view(np.float32)
    assert reference.bf16(value).view(np.uint32).item() == expected


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_bf16_rejects_nonfinite(value):
    with pytest.raises(ModelContractError, match="nonfinite"):
        reference.bf16(np.array([value], dtype=np.float32))


@pytest.mark.parametrize("sign", [1, -1])
def test_bf16_rejects_finite_overflow(sign):
    with pytest.raises(ModelContractError, match="finite overflow"):
        reference.bf16(np.array([sign * np.finfo(np.float32).max], dtype=np.float32))


@pytest.mark.parametrize("value", [
    np.array([1.0], dtype=np.float64), np.array([1], dtype=np.int32),
    np.array([np.nextafter(np.float32(1), np.float32(2))], dtype=np.float32),
    np.array([np.nan], dtype=np.float32),
])
def test_require_bf16_rejects_wrong_storage_or_unrounded_bits(value):
    with pytest.raises(ModelContractError):
        reference.require_bf16(value, "fixture")


@pytest.mark.parametrize("shape", [(128, 1024), (2, 128, 1024), (1, 127, 1024), (1, 128, 512)])
def test_forward_rejects_unsupported_input_geometry(shape):
    with pytest.raises(ModelContractError, match="B1 M128 H1024"):
        reference.forward(np.zeros(shape, dtype=np.float32), {})


@pytest.mark.parametrize("offset", [True, -1, 1, 256, 128.0, np.int64(128)])
def test_forward_rejects_unsupported_positions(offset):
    with pytest.raises(ModelContractError, match="positions"):
        reference.forward(np.zeros((1, 128, 1024), dtype=np.float32), {}, position_start=offset)


@pytest.fixture(scope="module")
def zero_weights():
    shapes = {
        "input_layernorm.weight": (1024,), "post_attention_layernorm.weight": (1024,),
        "self_attn.q_norm.weight": (256,), "self_attn.k_norm.weight": (256,),
        "self_attn.q_proj.weight": (4096, 1024), "self_attn.k_proj.weight": (512, 1024),
        "self_attn.v_proj.weight": (512, 1024), "self_attn.o_proj.weight": (1024, 2048),
        "mlp.gate_proj.weight": (3584, 1024), "mlp.up_proj.weight": (3584, 1024),
        "mlp.down_proj.weight": (1024, 3584),
    }
    return {name: np.broadcast_to(np.float32(0), shape) for name, shape in shapes.items()}


@pytest.mark.parametrize("mutation", ["missing", "extra", "geometry", "fp32_bits"])
def test_forward_rejects_weight_contract_drift(zero_weights, mutation):
    weights = dict(zero_weights)
    if mutation == "missing":
        del weights["self_attn.q_norm.weight"]
    elif mutation == "extra":
        weights["self_attn.q_proj.bias"] = np.zeros(4096, dtype=np.float32)
    elif mutation == "geometry":
        weights["self_attn.q_norm.weight"] = np.zeros(255, dtype=np.float32)
    else:
        weights["self_attn.q_norm.weight"] = np.full(256, np.nextafter(np.float32(1), np.float32(2)))
    with pytest.raises(ModelContractError):
        reference.forward(np.zeros((1, 128, 1024), dtype=np.float32), weights)


@pytest.mark.parametrize("past, offset", [
    (None, 128), ((), 0), ((), 128),
    ((np.zeros((1, 2, 127, 256), np.float32),) * 2, 128),
    ((np.zeros((1, 2, 128, 256), np.float64),) * 2, 128),
])
def test_forward_rejects_bad_cache_position_pair(zero_weights, past, offset):
    with pytest.raises(ModelContractError):
        reference.forward(np.zeros((1, 128, 1024), dtype=np.float32), zero_weights, past,
                          position_start=offset)


def test_operator_and_block_thresholds_remain_frozen(contract):
    assert contract["thresholds"] == {
        "operator": {"max_abs": 0.03125, "mean_abs": 0.005},
        "block": {"max_abs": 0.05, "mean_abs": 0.01},
    }
    actual = np.zeros(20, dtype=np.float64)
    actual[0] = 0.03125
    assert reference.producer_compare(actual, np.zeros_like(actual))["pass"]
    actual[0] = np.nextafter(0.03125, np.inf)
    assert not reference.producer_compare(actual, np.zeros_like(actual))["pass"]
    actual[0] = 0.05
    assert reference.producer_compare(actual, np.zeros_like(actual), block=True)["pass"]
    actual[0] = np.nextafter(0.05, np.inf)
    assert not reference.producer_compare(actual, np.zeros_like(actual), block=True)["pass"]
    assert not reference.producer_compare(np.full(20, 0.006), np.zeros(20))["pass"]
    assert not reference.producer_compare(np.full(20, 0.011), np.zeros(20), block=True)["pass"]


@pytest.mark.parametrize("a, b", [
    (np.zeros(2), np.zeros(3)), (np.zeros(0), np.zeros(0)),
    (np.array([np.nan]), np.zeros(1)), (np.zeros(1), np.array([np.inf])),
])
def test_producer_comparison_rejects_invalid_tensors(a, b):
    with pytest.raises(ModelContractError):
        reference.producer_compare(a, b)


def test_bit_counter_distinguishes_signed_zero_without_numerical_failure():
    result = reference.producer_compare(np.array([0.0], np.float32), np.array([-0.0], np.float32))
    assert result["bit_different"] == 1
    assert result["max_abs_error"] == 0 and result["pass"]


def test_signed_zero_only_diagnosis_selects_an_actually_different_coordinate():
    native = [row("hidden|aten.mul.Tensor|0", [1.0, 0.0])]
    oracle = [row("hidden|aten.mul.Tensor|0", [1.0, -0.0])]
    result = reference.diagnose_trace(native, oracle, {})
    witness = result["first_bit_difference"]
    assert witness["coordinate"] == [1]
    assert not np.signbit(witness["native"]) and np.signbit(witness["numpy"])
    assert result["first_operator_failure"] is None


@pytest.mark.parametrize("correct_native", [True, False])
def test_cast_witness_own_input_check_preserves_signed_zero(correct_native):
    native = [row("norm|aten.mul.Tensor|1", [0.0 if correct_native else -0.0], "float32"),
              row("norm|cast_bf16|0", [0.0])]
    oracle = [row("norm|aten.mul.Tensor|1", [-0.0], "float32"),
              row("norm|cast_bf16|0", [-0.0])]
    result = reference.diagnose_trace(native, oracle, {})
    assert result["first_cast_witness"]["both_RNE_correct_for_own_input"] is correct_native


def test_hidden_producer_failure_survives_equal_final_output():
    native = [row("hidden|aten.mul.Tensor|0", [0.0625]), row("|aten.add.Tensor|1", [1.0])]
    oracle = [row("hidden|aten.mul.Tensor|0", [0.0]), row("|aten.add.Tensor|1", [1.0])]
    assert reference.producer_compare(native[-1]["value"], oracle[-1]["value"], block=True)["pass"]
    result = reference.diagnose_trace(native, oracle, {})
    assert result["first_operator_failure"] == "hidden|aten.mul.Tensor|0"
    assert result["changed_producers"] == 1
    assert not result["native_accumulation_tree_identified"]


def test_cast_midpoint_witness_uses_each_graphs_own_input():
    midpoint = np.float32(1.00390625)
    native = [row("norm|aten.mul.Tensor|1", [np.nextafter(midpoint, np.float32(2))], "float32"),
              row("norm|cast_bf16|0", [1.0078125])]
    oracle = [row("norm|aten.mul.Tensor|1", [midpoint], "float32"),
              row("norm|cast_bf16|0", [1.0])]
    before = [r["value"].tobytes() for r in native + oracle]
    result = reference.diagnose_trace(native, oracle, {})
    witness = result["first_cast_witness"]
    assert result["first_bit_difference"]["storage_dtype"] == "float32"
    assert result["first_bf16_difference"]["producer"] == "norm|cast_bf16|0"
    assert witness["both_RNE_correct_for_own_input"]
    assert witness["native_minus_midpoint"] > 0 and witness["numpy_minus_midpoint"] == 0
    assert [r["value"].tobytes() for r in native + oracle] == before


def test_same_operand_projection_diagnostic_is_exact_and_nonmutating():
    left = np.ones((1, 1, 2), dtype=np.float32)
    native = [row("norm|cast_bf16|0", left),
              row("self_attn.q_proj|aten.linear.default|0", [[[1.0078125]]])]
    oracle = [row("norm|cast_bf16|0", left.copy()),
              row("self_attn.q_proj|aten.linear.default|0", [[[1.0]]])]
    weights = {"self_attn.q_proj.weight": np.array([[1.0, 1 / 256]], dtype=np.float32)}
    before = [r["value"].tobytes() for r in native + oracle] + [weights["self_attn.q_proj.weight"].tobytes()]
    result = reference.diagnose_trace(native, oracle, weights)
    assert result["first_projection_operands_bit_identical"]
    witness = result["first_projection_exact_dot_witness"]
    assert (witness["exact_dot_numerator"], witness["exact_dot_denominator"]) == ("257", "256")
    assert witness["exact_dot_minus_midpoint"] == 0
    assert [r["value"].tobytes() for r in native + oracle] + [weights["self_attn.q_proj.weight"].tobytes()] == before


def softmax_fixture():
    p = np.array([[[[1.0, 0.0], [0.25, 0.75]], [[1.0, 0.0], [0.5, 0.5]]]], dtype=np.float32)
    mask = np.array([[[[0.0, -3.3895313892515355e38], [0.0, 0.0]]]], dtype=np.float32)
    return p, mask


def test_fp32_softmax_row_invariants_and_limit():
    p, mask = softmax_fixture()
    result = reference.softmax_invariants(p, mask)
    assert result["pass"] and result["rows"] == 4
    assert result["row_sum_abs_limit"] == 2e-5
    p[0, 0, 1, 0] += np.float32(1e-5)
    assert reference.softmax_invariants(p, mask)["pass"]
    p[0, 0, 1, 0] += np.float32(2e-5)
    assert not reference.softmax_invariants(p, mask)["pass"]


def test_softmax_masked_leakage_rejected_even_with_normalized_rows():
    p, mask = softmax_fixture()
    p[0, 0, 0] = [1 - 2**-10, 2**-10]
    result = reference.softmax_invariants(p, mask)
    assert result["max_row_sum_abs_error"] == 0 and result["masked_nonzeros"] == 1
    assert not result["pass"]


def test_softmax_negative_probability_rejected_even_with_normalized_rows():
    p, mask = softmax_fixture()
    p[0, 0, 1] = [-0.125, 1.125]
    result = reference.softmax_invariants(p, mask)
    assert result["max_row_sum_abs_error"] == 0
    assert not result["probabilities_in_unit_interval"] and not result["pass"]


@pytest.mark.parametrize("mutation", ["float64", "rank", "empty", "nan", "mask_shape", "mask_value", "mask_nan"])
def test_softmax_invalid_boundaries_rejected(mutation):
    p, mask = softmax_fixture()
    if mutation == "float64": p = p.astype(np.float64)
    elif mutation == "rank": p = p[0]
    elif mutation == "empty": p = p[:, :, :0]
    elif mutation == "nan": p[0, 0, 0, 0] = np.nan
    elif mutation == "mask_shape": mask = mask[0]
    elif mutation == "mask_value": mask[0, 0, 0, 1] = -1
    else: mask[0, 0, 0, 1] = np.nan
    with pytest.raises(ModelContractError):
        reference.softmax_invariants(p, mask)


def test_local_bound_handles_subnormal_bf16_output_after_normal_products():
    a = np.array([[1.0703125, -1.140625]], dtype=np.float32)
    b = np.array([[np.ldexp(np.float32(1.0703125), -126)], [np.ldexp(np.float32(1), -126)]], dtype=np.float32)
    exact = a.astype(np.float64) @ b.astype(np.float64)
    actual = reference.bf16(exact)
    assert actual.item() == 2**-133
    result = reference.local_gemm_bound(actual, a, b)
    assert result["mismatches"] == 0 and result["max_error_to_bound_ratio"] <= 1
    assert result["max_bound"] >= 2**-134


def test_local_bound_zero_does_not_get_normal_half_bin():
    actual = np.zeros((1, 1), dtype=np.float32)
    result = reference.local_gemm_bound(actual, np.ones((1, 1), np.float32),
                                        np.full((1, 1), 2**-20, np.float32))
    assert result["mismatches"] == 1
    assert result["max_bound"] < 2**-40


@pytest.mark.parametrize("magnitude, message", [(2**-126, "underflow"), (2**100, "overflow")])
def test_local_bound_rejects_unsupported_products(magnitude, message):
    value = np.full((1, 1), magnitude, dtype=np.float32)
    with pytest.raises(ModelContractError, match=message):
        reference.local_gemm_bound(np.zeros((1, 1), np.float32), value, value)


def sequence_fixture(contract):
    return [row(pin["key"], [1.0], pin["storage_dtype"]) for pin in contract["producer_sequence"]]


def test_contract_producer_order_and_storage_are_frozen(runner, contract):
    trace = sequence_fixture(contract)
    assert len(trace) == 57
    assert trace[0]["key"] == "input_layernorm|aten.pow.Tensor_Scalar|0"
    assert trace[-1]["key"] == "|aten.add.Tensor|1"
    runner.verify_sequence(trace, contract)


@pytest.mark.parametrize("mutation", ["missing", "extra", "order", "label", "float64", "nonfinite", "subnormal", "unrounded"])
def test_sequence_rejects_boundary_drift(runner, contract, mutation):
    trace = sequence_fixture(contract)
    if mutation == "missing": trace.pop()
    elif mutation == "extra": trace.append(deepcopy(trace[-1]))
    elif mutation == "order": trace[0], trace[1] = trace[1], trace[0]
    elif mutation == "label": trace[0]["dtype"] = "bfloat16"
    elif mutation == "float64": trace[0]["value"] = trace[0]["value"].astype(np.float64)
    elif mutation == "nonfinite": trace[0]["value"][0] = np.nan
    elif mutation == "subnormal": trace[0]["value"][0] = np.float32(2**-140)
    else:
        i = next(i for i, r in enumerate(trace) if r["dtype"] == "bfloat16")
        trace[i]["value"][0] = np.nextafter(np.float32(1), np.float32(2))
    with pytest.raises(ModelContractError):
        runner.verify_sequence(trace, contract)


@pytest.mark.parametrize("field, value", [
    ("model_id", "WRONG_MODEL"), ("fixture", {"token_ids": [-1]}),
    ("official_source_sha256", {"modeling": "0" * 64}), ("payload_manifests", {}),
    ("partition_replay_comparisons", [{"mismatches": 999}]),
    ("activation_links", []), ("parameter_dtype_reports", []),
    ("isolated_state_influence", []), ("kv_continuity", []),
    ("comparisons", [{"mismatches": 0}] * 32),
])
def test_saved_prefix_report_mutation_rejected_before_parsing(runner, contract, tmp_path, monkeypatch, field, value):
    report = json.loads(SAVED_REPORT.read_text())
    report[field] = value
    (tmp_path / "result.json").write_text(json.dumps(report))
    def forbidden_parse(path):
        pytest.fail("untrusted report was parsed before its immutable digest was checked")
    monkeypatch.setattr(runner, "load_json", forbidden_parse)
    with pytest.raises(ModelContractError, match="untrusted upstream report"):
        runner.load_upstream(ROOT, tmp_path, contract)


def test_malformed_prefix_report_rejected_by_digest_before_json(runner, contract, tmp_path, monkeypatch):
    (tmp_path / "result.json").write_bytes(b"not JSON")
    monkeypatch.setattr(runner, "load_json", lambda path: pytest.fail("untrusted JSON was parsed"))
    with pytest.raises(ModelContractError, match="untrusted upstream report"):
        runner.load_upstream(ROOT, tmp_path, contract)


def test_saved_report_matches_independent_admission_pin(runner, contract):
    assert runner.sha256(SAVED_REPORT.read_bytes()) == contract["saved_upstream_report_sha256"]
    assert contract["hardware_v0_semantics_accepted"] is False


@pytest.mark.parametrize("name", [
    "scripts/run_qwen35_prefix_chain.py", "src/heteronpu/pinned_prefix_payload.py",
    "src/heteronpu/qwen35_prefix_reference.py", "src/heteronpu/qwen35_gdn_numpy_reference.py",
    "src/heteronpu/qwen35_numpy_reference.py", "src/heteronpu/pinned_gdn_payload.py",
    "src/heteronpu/pinned_block_payload.py", "src/heteronpu/model_geometry.py",
    "src/heteronpu/weight_header_contract.py", "src/heteronpu/qwen35_dense_contract.py",
    "src/heteronpu/qwen_family_contracts.py",
])
def test_fresh_prefix_source_drift_rejected_before_execution(runner, contract, tmp_path, monkeypatch, name):
    assert name in contract["fresh_prefix_source_sha256"]
    original_read = Path.read_bytes
    target = (ROOT / name).resolve()
    def changed_bytes(path):
        raw = original_read(path)
        return raw + b"\n# source drift test\n" if path.resolve() == target else raw
    monkeypatch.setattr(Path, "read_bytes", changed_bytes)
    monkeypatch.setattr(runner, "load_payload", lambda *args: ({"tensors": []}, {}))
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *args, **kwargs: pytest.fail("drifted prefix was imported"))
    with pytest.raises(ModelContractError, match="pinned prefix source drift"):
        runner.run(ROOT, tmp_path / "layer3", tmp_path / "upstream", tmp_path / "output",
                   rebuild_layer0=tmp_path / "layer0", rebuild_extra=tmp_path / "extra")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("which", ["rebuild_layer0", "rebuild_extra"])
def test_fresh_prefix_requires_both_payloads(runner, tmp_path, monkeypatch, which):
    monkeypatch.setattr(runner, "load_payload", lambda *args: ({"tensors": []}, {}))
    with pytest.raises(ModelContractError, match="both prefix rebuild payloads"):
        runner.run(ROOT, tmp_path / "layer3", tmp_path / "upstream", tmp_path / "output", **{which: tmp_path})
    assert not (tmp_path / "output").exists()


def test_failed_validation_never_publishes_or_overwrites_result(runner, tmp_path, monkeypatch):
    def corrupt_payload(*args):
        raise ModelContractError("injected corrupt payload")
    monkeypatch.setattr(runner, "load_payload", corrupt_payload)
    output = tmp_path / "output"
    with pytest.raises(ModelContractError, match="corrupt payload"):
        runner.run(ROOT, tmp_path, tmp_path, output)
    assert not output.exists()
    output.mkdir()
    (output / "result.json").write_text("existing evidence")
    with pytest.raises(ModelContractError, match="fresh or empty"):
        runner.run(ROOT, tmp_path, tmp_path, output)
    assert (output / "result.json").read_text() == "existing evidence"
