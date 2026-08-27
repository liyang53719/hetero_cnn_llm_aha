from __future__ import annotations

from heteronpu.matrix_context_pipeline import dependent_round_robin, randomized_backpressure
from heteronpu.qwen38_budget import full_budget_report, selected_tokens_for_visible_length, sum_selected_tokens
from heteronpu.qwen38_liveness import liveness_report
from heteronpu.qwen38_memory_dse import expert_bytes, memory_dse_report, ple_trace, simulate_lru
from heteronpu.qwen38_qsa_streaming import QSAIndexConfig, StreamingTopK, coalesce_selected_tokens, run_random_parity
from heteronpu.qwen38_quantization import quantization_screen_report
from heteronpu.qwen38_state_transaction import SyntheticHybridState, execute_speculation, run_transaction_stress, state_digest, synthetic_step, verify_prefix


def test_qsa_streaming_parity_and_zero_score_materialization() -> None:
    result = run_random_parity(cases=20, seed=1)
    assert result["status"] == "PASS"
    assert result["score_materialization_bytes"] == 0


def test_qsa_stable_tie_break_and_page_restore() -> None:
    topk = StreamingTopK(3)
    for block in (5, 2, 9, 1, 7):
        topk.offer(1.0, block)
    assert [block for _, block in topk.winners()] == [1, 2, 5]
    selected = (31, 2, 17, 16, 0, 47)
    plan = coalesce_selected_tokens(selected, 16)
    assert plan.restore(plan.memory_order_tokens) == selected


def test_qsa_rejects_fractional_block_budget() -> None:
    try:
        QSAIndexConfig(16, 4, 4, 30, 8, 16)
    except ValueError:
        return
    raise AssertionError("invalid QSA budget accepted")


def test_selected_token_total_matches_bruteforce() -> None:
    for ratio in (2, 4, 8):
        for budget in (ratio, 2 * ratio, 7 * ratio):
            for length in range(40):
                expected = sum(selected_tokens_for_visible_length(v, ratio, budget) for v in range(1, length + 1))
                assert sum_selected_tokens(length, ratio, budget) == expected


def test_full_shape_budget_forces_more_than_single_bf16_array() -> None:
    report = full_budget_report(contexts=(1024, 262144))
    points = report["cases"]["1024"]["prefill"]["compute_points"]
    assert not points["bf16_16x32"]["target_feasible_below_100pct"]
    assert points["native_w4_dual_dot"]["required_wall_utilization"] < 0.5
    state = report["cases"]["262144"]["persistent_state"]
    assert state["gdn_recurrent_state"] == 108 * 1024 * 1024
    assert state["qsa_compressed_index"] == 192 * 1024 * 1024
    assert state["qsa_kv"] == 6 * 1024 * 1024 * 1024


def test_cross_state_transaction_commit_and_random_stress() -> None:
    base = SyntheticHybridState.initial()
    verification, committed = execute_speculation(synthetic_step, base, (3, 5, 7, 9), (3, 5, 8, 1))
    expected = synthetic_step(5, synthetic_step(3, base))
    assert verification.accepted == 2
    assert state_digest(committed) == state_digest(expected)
    assert run_transaction_stress(cases=100, seed=2)["status"] == "PASS"
    assert verify_prefix((1, 2, 3), (1, 2, 9, 8)).accepted == 2


def test_ple_and_expert_memory_bounds() -> None:
    adverse = ple_trace(64, pattern="adversarial")
    cache = simulate_lru((row for token in adverse for row in token), 4096, 320)
    assert cache.hits == 0
    assert expert_bytes(bits=4) == 2_611_200
    report = memory_dse_report(tokens=256)
    assert report["status"] == "PASS"
    assert report["moe"]["w4"]["patterns"]["hotset64"]["cache_mib"]["256"]["hit_rate"] > 0.9


def test_quantization_screen_and_liveness_candidate() -> None:
    quant = quantization_screen_report()
    assert quant["formats"]["fp32"]["gdn_state"]["relative_l2"] == 0.0
    assert quant["formats"]["fp32"]["qsa_selection"]["exact_order_rate"] == 1.0
    assert quant["formats"]["fp8_e4m3fn"]["gdn_state"]["relative_l2"] > quant["formats"]["bf16"]["gdn_state"]["relative_l2"]
    live = liveness_report()
    assert live["status"] == "PASS"
    assert live["total_sram_kib"] == 4096
    assert all(pool["headroom_bytes"] >= 0 for pool in live["pools"].values())


def test_four_context_recurrence_and_backpressure() -> None:
    recurrence = dependent_round_robin(10_000, 4, 4)
    assert recurrence["issue_utilization"] > 0.999
    assert randomized_backpressure(1_000, 4, 4, seed=3)["status"] == "PASS"
