"""Pinned M128 PV32 workload arithmetic, not an execution or cycle model.

Only source bytes are read. No owner, runner, recipe, tensor or private work
module is imported. Ratios and threshold decisions use exact Fractions.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PINS = {
    'candidates/qwen2_live_attention_model_m128/pv32_owner.py':
        '67924e28218c6d423d7a607909984c010f3b09ccac4e2200870f3003b76e747a',
    'candidates/qwen2_live_fullblock_model_m128/runner.py':
        '6d1e13444a7007f4f9f891f95d94c285295013d867cf733f0b1fcd2d36481370',
    'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py':
        'dfd44e15f274090ba7d1eca4fa6c59248e11029dad3c5fcfc0b45693c6267699',
    'candidates/qwen2_resident_matrix/official_bf16/silu_recipe.cpp':
        'd319d3431316b4ff0f299beac5931f718a6a3a446e8de06398b172ebb6e0401c',
    'candidates/qwen2_resident_matrix/ffn_fullgroup/check_numeric.py':
        '7fd62ea5f59af4ba6da36d74b289e0aba85b1eb35b1d3e060a7d8e95d0b55336',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala':
        'dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala':
        '7f2b4a623b61b6e68478b2310d441ed04ccde1cd5490cb22205113f907b7974d',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BurstProtocol.scala':
        '0f2720e741af302952854b7787f63b4df55b9437048f818319f2cecf16034aac',
    'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py':
        '9001c58559d10a0f72aea1c00f85a0da6508a3c729dd2469433f831a0da5ea8b',
}
M, HEADS, KV_HEADS, HEAD_DIM, HIDDEN, FFN = 128, 12, 2, 128, 1536, 8960
MACS, BEAT_BYTES, FP32_BYTES, BF16_BYTES = 4096, 64, 4, 2
DENSE_SHAPES = (
    ('q', 1536, 1536), ('k', 1536, 256), ('v', 1536, 256),
    ('o', 1536, 1536), ('gate', 1536, 8960), ('up', 1536, 8960),
    ('down', 8960, 1536),
)


def verify_sources(root=ROOT):
    """Fail closed on missing/drifted source; never import dependencies."""
    root = Path(root)
    for name, expected in SOURCE_PINS.items():
        path = root / name
        if not path.is_file():
            raise ValueError('missing pinned source: ' + name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('source drift; re-audit required: ' + name)
    return dict(SOURCE_PINS)


def workload():
    pairs = HEADS * M * (M + 1) // 2
    query_heads = HEADS * M
    dense = [dict(role=role, k=k, n=n, unique_weight_bytes=k*n*BF16_BYTES,
                  useful_macs=M*k*n, ideal_full_width_fma_issue_floor=M*k*n//MACS)
             for role, k, n in DENSE_SHAPES]
    dense_weights = sum(d['unique_weight_bytes'] for d in dense)
    dense_macs = sum(d['useful_macs'] for d in dense)
    dense_issue_floor = sum(d['ideal_full_width_fma_issue_floor'] for d in dense)
    qk_requests = pairs * (HEAD_DIM // 16)
    pv32_requests = pairs * (HEAD_DIM // 32)
    q_bytes = query_heads * HEAD_DIM * FP32_BYTES
    k_bytes = qk_requests * BEAT_BYTES
    v_bytes = pv32_requests * 2 * BEAT_BYTES
    output_bytes = q_bytes
    attention_bytes = q_bytes + k_bytes + v_bytes + output_bytes
    attention_macs = 2 * pairs * HEAD_DIM
    total_macs = dense_macs + attention_macs
    equivalent = Fraction(total_macs, MACS)
    known_ddr_bytes = dense_weights + attention_bytes
    known_ddr_slots = known_ddr_bytes // BEAT_BYTES
    issue_slots = dense_issue_floor + qk_requests + pv32_requests
    silu_packets = M * FFN // 16
    # Per causal pair: QK fold16 Add; softmax diff/sum2 Add;
    # QK scale1 Mul; PV32 normalized probability4 Mul (one per output col32).
    scalar_add = pairs * 18
    scalar_mul = pairs * 5
    return dict(
        geometry=dict(m=M, heads=HEADS, kv_heads=KV_HEADS, head_dim=HEAD_DIM,
                      hidden=HIDDEN, ffn=FFN, mac_capacity=MACS, shared_beat_bytes=BEAT_BYTES),
        dense=dense,
        useful=dict(dense_macs=dense_macs, attention_macs=attention_macs,
                    full_block_macs=total_macs, full_width_equivalent_slots=equivalent),
        attention=dict(causal_pairs=pairs, query_heads=query_heads,
                       q_read_bytes=q_bytes, k_repeated_read_bytes=k_bytes,
                       v_repeated_read_bytes=v_bytes, output_write_bytes=output_bytes,
                       external_bytes=attention_bytes, score_probability_external_bytes=0,
                       qk_matrix_requests=qk_requests, pv32_matrix_requests=pv32_requests,
                       matrix_requests=qk_requests+pv32_requests,
                       q_head_live_fp32_bytes=HEAD_DIM*FP32_BYTES,
                       score_peak_fp32_bytes=M*FP32_BYTES,
                       probability_peak_fp32_bytes=M*FP32_BYTES,
                       resident_kv_cache_implemented_in_pinned_path=False),
        known_ddr_subset=dict(unique_seven_dense_weight_bytes=dense_weights,
                              attention_external_bytes=attention_bytes,
                              lower_bound_bytes=known_ddr_bytes,
                              ideal_64b_service_slot_floor=known_ddr_slots,
                              full_mac_capacity_ceiling=equivalent/known_ddr_slots,
                              complete_block_traffic=False),
        issue_capacity=dict(ideal_dense_fma_issue_floor=dense_issue_floor,
                            attention_legacy_request_count=qk_requests+pv32_requests,
                            shared_issue_service_slot_floor=issue_slots,
                            full_mac_capacity_ceiling=equivalent/issue_slots,
                            assumption='At most one shared Matrix request per slot; Dense idealized at all4096 lanes.'),
        scalar_workload=dict(attention_add=scalar_add, attention_mul=scalar_mul,
                             attention_add_mul=scalar_add+scalar_mul,
                             attention_exp_negative_calls=pairs,
                             attention_div_calls=query_heads,
                             exp_internal_primitive_expansion_count=None,
                             bf16_materialization_counted_as_add_mul=False,
                             complete_block_scalar_workload=False),
        silu_workload=dict(vector_packets=silu_packets, lanes_per_packet=16,
                           phases_per_packet=6, vector_phase_invocations=silu_packets*6,
                           lane_phase_evaluations=silu_packets*6*16,
                           local_bridge_read_bytes=silu_packets*2*BEAT_BYTES,
                           local_bridge_write_bytes=silu_packets*BEAT_BYTES,
                           local_bridge_logical_payload_bytes=silu_packets*3*BEAT_BYTES,
                           local_bridge_bytes_are_ddr=False,
                           physical_sram_access_bytes=None,
                           note='Two local gate/up reads and one local act write; later act DDR drain/read excluded here.'),
    )


def target_budget(target):
    if type(target) is not Fraction or not 0 < target <= 1:
        raise ValueError('target must be an exact Fraction in (0,1]')
    w = workload()
    exact = w['useful']['full_width_equivalent_slots'] / target
    slots = exact.numerator // exact.denominator
    byte_capacity = slots * BEAT_BYTES
    return dict(target=target, exact_complete_block_slot_budget=exact,
                integer_complete_block_slot_budget=slots,
                ideal_shared_64b_byte_budget=byte_capacity,
                remaining_after_unique_dense_weights=byte_capacity-w['known_ddr_subset']['unique_seven_dense_weight_bytes'],
                necessary_only=True, feasible_schedule_proven=False)


def meets_target(total_slots, target):
    if type(total_slots) is not int or total_slots <= 0:
        raise ValueError('positive integer complete-block slots required')
    budget = target_budget(target)
    return total_slots <= budget['integer_complete_block_slot_budget']


def report(root=ROOT):
    pins = verify_sources(root)
    out = workload()
    out.update(status='STATIC_PINNED_WORKLOAD_AND_CAPACITY_BOUNDS_ONLY', source_sha256=pins,
               budgets={'80_percent': target_budget(Fraction(4, 5)),
                        '90_percent': target_budget(Fraction(9, 10))},
               rtl_cycles=None, measured_cycles=None, prediction_cycles=None,
               hardware_utilization=None, numerical_acceptance=None,
               rtl_executed=False, full_chain_executed=False,
               old_acceptance_changed=False, old_rectangular_ledger_used=False,
               exclusions=[
                   'DDR subset omits all other stage traffic, Dense activations/outputs/prefixes and metadata.',
                   'Dense issue floor omits exact-tree Add/restore, output drain and padding/hazard overhead.',
                   'Do not add DMA and issue service floors: overlap is not disproved; each is an independent bound.',
                   'Scalar and SiLU counts are operation workloads, not cycle latencies or a complete block count.',
                   'No 131727360-byte rectangular-cache ledger or software ticks are used as live measurements.',
               ])
    return out


def json_value(value):
    if isinstance(value, Fraction):
        return dict(numerator=value.numerator, denominator=value.denominator,
                    decimal_display_only=float(value))
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='source-only checkout root')
    args = parser.parse_args()
    print(json.dumps(report(args.root), default=json_value, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
