import numpy as np
from heteronpu.p3_backend_evidence import audit_p3, classify_bindings, inspect_sources
from heteronpu.logits_parity import compare_files, compare_logits

BACKEND = '''
if(graph->n_nodes==958){ hetero_qwen2_submit_588(&config); }
static ggml_backend_buffer_type_t x(){return ggml_backend_cpu_buffer_type();}
static ggml_backend_buffer_t y(){return ggml_backend_cpu_buffer_from_ptr(nullptr,0);}
'''
API = '''
#include "qwen2_q1024_generic_layer_backend.cpp"
qwen2_generic_layer_embedded_main(6,argv);
while(!config->completion_ready_cb(layer,attempt,config->completion_user_data)){}
int max_completion_waits;
'''
GENERIC = '''
void validate_commands(){ uint8_t opcodes[21]; auto x=commands[index * 16]; }
#pragma omp parallel for
'''
DIRECT = {
    "gguf": {"direct_buffer_bindings": 338, "norm_f32_to_bf16_RNE": 57},
    "graph": {"nodes": 958, "splits": 1, "commands": 588, "layers": 28, "groups": 7, "cpu_fallback": 0},
    "output": {"vocab": 151936, "argmax": 7559, "top10_overlap": 10},
}
BACKPRESSURE = {"completions": 28, "stalls": 7}
FINAL = {"requirements": {"argmax": 7559}}


def test_source_semantics_detect_software_monolithic_backend():
    s = inspect_sources(BACKEND, API, GENERIC)
    assert s.original_graph_guard and s.monolithic_submission
    assert s.host_cpu_buffer_type and s.software_stage_backend
    assert s.command_manifest_validation and not s.command_rtl_interpreter
    assert s.layer_completion_callback_backpressure


def test_binding_classification_separates_raw_and_converted():
    b = classify_bindings(DIRECT)
    assert b.total_bindings == 338
    assert b.raw_storage_byte_parity == 281
    assert b.canonical_converted_parity == 57


def test_p3_accepts_backend_equivalent_but_not_hardware():
    r = audit_p3(backend_cpp=BACKEND, device_api_cpp=API, generic_backend_cpp=GENERIC,
                 direct_report=DIRECT, backpressure_report=BACKPRESSURE, final_report=FINAL)
    assert r["status"] == "PASS_LLAMA_BACKEND_FUNCTIONAL_SOFTWARE_EMULATION"
    assert r["graph"]["commands_executed_by_RTL_frontend"] == 0
    assert r["open_gates"]["Command128_RTL_execution"]
    assert r["backpressure_scope"]["not_internal_matrix_sfu_kv_ready_valid"]


def test_exact_logits_pass():
    x = np.linspace(-3, 3, 128, dtype=np.float32)
    r = compare_logits(x, x.copy())
    assert r["status"] == "PASS_FULL_LOGITS_PARITY"
    assert r["metrics"]["topk_overlap"] == 10


def test_top10_only_can_hide_large_tail_error():
    ref = np.arange(100, dtype=np.float32)
    actual = ref.copy()
    actual[:80] += 100.0
    actual[:80] = np.minimum(actual[:80], 88.5)
    r = compare_logits(actual, ref)
    assert r["metrics"]["argmax_actual"] == r["metrics"]["argmax_reference"]
    assert r["metrics"]["topk_overlap"] == 10
    assert r["status"] == "FAIL_FULL_LOGITS_PARITY"
    assert not r["checks"]["relative_l2"]


def test_small_logit_noise_passes_review_threshold():
    rng = np.random.default_rng(7)
    ref = rng.normal(size=4096).astype(np.float32)
    actual = ref + rng.normal(scale=1e-4, size=ref.size).astype(np.float32)
    top = np.argpartition(ref, -10)[-10:]
    actual[top] = ref[top]
    actual[np.argmax(ref)] = ref[np.argmax(ref)]
    r = compare_logits(actual, ref)
    assert r["status"] == "PASS_FULL_LOGITS_PARITY"


def test_file_comparator_records_sha256(tmp_path):
    actual = tmp_path / "actual.bin"
    reference = tmp_path / "reference.bin"
    values = np.linspace(-1, 1, 64, dtype=np.float32)
    values.tofile(actual)
    values.tofile(reference)
    r = compare_files(actual, reference)
    assert r["status"] == "PASS_FULL_LOGITS_PARITY"
    assert r["inputs"]["actual"]["bytes"] == values.nbytes
    assert len(r["inputs"]["actual"]["sha256"]) == 64
    assert r["inputs"]["actual"]["sha256"] == r["inputs"]["reference"]["sha256"]


def test_zero_logit_vectors_have_unit_cosine():
    values = np.zeros(64, dtype=np.float32)
    report = compare_logits(values, values.copy())
    assert report["status"] == "PASS_FULL_LOGITS_PARITY"
    assert report["metrics"]["cosine"] == 1.0
    assert report["metrics"]["relative_l2"] == 0.0


def test_identical_nonfinite_masks_fail_strict_acceptance():
    values = np.arange(32, dtype=np.float32)
    values[3] = np.nan
    report = compare_logits(values, values.copy())
    assert report["metrics"]["finite_mask_equal"]
    assert not report["metrics"]["all_finite"]
    assert not report["checks"]["all_finite"]
    assert report["status"] == "FAIL_FULL_LOGITS_PARITY"


def test_stable_topk_uses_lower_index_for_ties():
    values = np.ones(16, dtype=np.float32)
    report = compare_logits(values, values.copy())
    assert report["metrics"]["topk_actual_indices"] == list(range(10))
    assert report["metrics"]["topk_reference_indices"] == list(range(10))


def test_expected_vocab_count_is_a_hard_check():
    from heteronpu.logits_parity import LogitThresholds

    values = np.zeros(31, dtype=np.float32)
    report = compare_logits(values, values, LogitThresholds(expected_count=32))
    assert not report["checks"]["count"]
    assert report["status"] == "FAIL_FULL_LOGITS_PARITY"


def test_file_comparator_rejects_trailing_partial_float(tmp_path):
    actual = tmp_path / "actual.bin"
    reference = tmp_path / "reference.bin"
    actual.write_bytes(b"\x00" * 5)
    reference.write_bytes(b"\x00" * 4)
    import pytest

    with pytest.raises(ValueError, match="multiple of float32"):
        compare_files(actual, reference)


def test_nonzero_actual_against_zero_reference_has_json_safe_failed_relative_l2():
    ref = np.zeros(16, dtype=np.float32)
    actual = ref.copy()
    actual[0] = 1.0
    report = compare_logits(actual, ref)
    assert report["metrics"]["relative_l2"] is None
    assert not report["checks"]["relative_l2"]
    assert report["status"] == "FAIL_FULL_LOGITS_PARITY"
