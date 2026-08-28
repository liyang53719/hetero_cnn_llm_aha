from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.revision8_early_commit import differential_stress, validate_candidate_sources


def test_revision8a_candidate_sources_remove_completion_data_path():
    result = validate_candidate_sources(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract"]["contexts"] == 4
    assert result["contract"]["feedback_latency_cycles"] == 4
    assert result["contract"]["completion_to_pre_combinational_path_removed"] is True


def test_revision8a_cycle_exact_random_stall_and_contexts():
    result = differential_stress(
        accepted_operations=100_000,
        seed=0x8A17C0DE,
        output_stall_probability=0.31,
        input_bubble_probability=0.17,
    )
    assert result["status"] == "PASS"
    assert result["public_cycle_exact"] is True
    assert result["final_state_equal"] is True
    assert result["same_cycle_reuses"] > 10_000


def test_revision8a_no_stall_high_recurrence():
    result = differential_stress(
        accepted_operations=50_000,
        seed=0x8A000001,
        output_stall_probability=0.0,
        input_bubble_probability=0.0,
    )
    assert result["status"] == "PASS"
    assert result["same_cycle_reuses"] > 20_000


def test_revision8a_local_flow_has_no_timing_exception_or_top_compile():
    from heteronpu.revision8_early_commit import validate_local_flow
    result = validate_local_flow(ROOT)
    assert result["status"] == "PASS", result
