from heteronpu.workloads import run_toy_cnn, run_toy_llm_block


def test_cnn_end_to_end_exact() -> None:
    result = run_toy_cnn()
    assert result["max_abs_error"] == 0
    assert result["matrix_stats"]["invocations"] == 2


def test_llm_bf16_paged_end_to_end_exact() -> None:
    result = run_toy_llm_block(tokens=7, storage_format="bf16")
    assert result["max_abs_error"] == 0.0
    assert result["kv_stats"]["pages_in_use"] == 2


def test_llm_int8_kv_error_bound() -> None:
    result = run_toy_llm_block(tokens=7, storage_format="int8")
    assert result["max_abs_error"] < 0.03
    assert result["mean_abs_error"] < 0.01
