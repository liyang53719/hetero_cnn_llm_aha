"""Integer-only conditional cost screen, never hardware measurement or admission."""
from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCES={
 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala':'dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d',
 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedMatrix.scala':'80dc285af2208b3f3aa3d811a561cfe729e2c764b45c1da62de360f9578321bb',
 'candidates/qwen2_resident_matrix/dense_block_reduce/vector_add_model.py':'4784e8b5a7a5c45c4d25c2daa328c78735b22944bebb70b7c54f77f418f660da',
 'candidates/qwen2_resident_matrix/dense_block_reduce/sum_tiles.py':'ef718cb76e744ae560cc95d67093ea7b7e9bf33fbfe7c1eb310cea1e8faffda0',
 'candidates/qwen2_transposed_dense/README.md':'be998833ef07ad8467e712d08eb4dbe8a8b7af79bf48bcd0c22197d0cd9c5b04'}
M=128;N=1536;K=1536;MACS=4096;CONTEXTS=5;PARTIALS=64
OUTPUTS=M*N;USEFUL_MACS=OUTPUTS*K;OUTPUTS_PER_CONTEXT=64
VECTOR_LANES=16


def ceildiv(n,d):return (n+d-1)//d


@dataclass(frozen=True)
class Assumptions:
    # Explicit hypothetical service times, NOT observations of the old ports.
    recurrence_cycles:int=5
    vector_request_cycles:int=1
    local_64byte_transfer_cycles:int=1
    external_64byte_transfer_cycles:int=1
    rounding_16word_cycles:int=1
    protocol_cycles_per_tile:int=4


def resource_mapping():
    return dict(mac_lanes=MACS,accumulator_words=CONTEXTS*MACS,
        accumulator_bytes=CONTEXTS*MACS*4,partials_per_output=PARTIALS,
        outputs_per_context=OUTPUTS_PER_CONTEXT,maximum_live_outputs=320,
        new_mac_lanes=0,new_accumulator_words=0,borrowed_vector_add_lanes=16,
        vector_add_resource_is_shared=True,extra_routing_control_area_quantified=False)


def screen(route='outer_product_sparse',assumptions=Assumptions()):
    if route not in ('outer_product_sparse','wide_k_hypothesis'):raise ValueError('fixed route required')
    if type(assumptions) is not Assumptions or any(type(v) is not int or v<1 for v in asdict(assumptions).values()):
        raise ValueError('explicit positive integer service assumptions required')
    if assumptions.recurrence_cycles<5:raise ValueError('retained recurrence cannot be shortened')
    tiles=OUTPUTS//OUTPUTS_PER_CONTEXT
    full,tail=divmod(tiles,CONTEXTS)
    updates=K if route=='outer_product_sparse' else K//PARTIALS
    # Sparse: one k, 64 useful cells/issue. Wide hypothetical: 64 k and all cells.
    issue_count=tiles*updates
    group_count=full+bool(tail)
    def issue_span(contexts):
        return (updates-1)*max(contexts,assumptions.recurrence_cycles)+contexts
    issue_span_total=full*issue_span(CONTEXTS)+(issue_span(tail) if tail else 0)
    pipeline_drain=group_count*(assumptions.recurrence_cycles-1)
    # 56 register-tree + 7 lane-tree + one signed-zero-preserving +0 + bias.
    vector_adds=OUTPUTS*65
    vector_requests=vector_adds//VECTOR_LANES
    # One input load and final output store is an optimistic explicit reuse plan.
    # x and final q use original widened FP32 transport; weights are BF16.
    external_bytes=OUTPUTS*4+K*N*2+N*4+OUTPUTS*4
    # Snapshot partials once into existing storage, then charge every add as
    # two 64B reads + one 64B write, plus one final-result read for conversion.
    partial_snapshot_beats=OUTPUTS*PARTIALS*4//64
    reduction_beats=3*vector_requests
    final_read_beats=OUTPUTS*4//64
    ledger={
      'fma_issue_and_recurrence':issue_span_total,
      'fma_pipeline_fill_drain':pipeline_drain,
      # Existing A16/B256 stream: wide-K needs 1024B A vs 32B/step,
      # hence at least 32 serialized service units with unimplemented staging.
      'operand_stream_service':issue_count*(1 if route=='outer_product_sparse' else 32),
      'external_input_bias_output_transfer':ceildiv(external_bytes,64)*assumptions.external_64byte_transfer_cycles,
      'partial_snapshot_transfer':partial_snapshot_beats*assumptions.local_64byte_transfer_cycles,
      'tree_tailzero_bias_read_write':reduction_beats*assumptions.local_64byte_transfer_cycles,
      'tree_tailzero_bias_vector_service':vector_requests*assumptions.vector_request_cycles,
      'final_read':final_read_beats*assumptions.local_64byte_transfer_cycles,
      'bf16_round_and_widen_service':ceildiv(OUTPUTS,16)*assumptions.rounding_16word_cycles,
      'command_completion_ack_control':tiles*assumptions.protocol_cycles_per_tile}
    total=sum(ledger.values())
    # No overlap credit. Wide-K costs deliberately omit neither IO nor the tree,
    # but its operand route is absent and cannot be treated as an implementation.
    return dict(status='BLOCKED_UNIMPLEMENTED_MAPPING',route=route,resources=resource_mapping(),
        assumptions=asdict(assumptions),useful_macs=USEFUL_MACS,issued_physical_mac_slots=issue_count*MACS,
        geometric_issue_fill=USEFUL_MACS/(issue_count*MACS),vector_fp32_adds=vector_adds,
        conditional_serial_cost_units=ledger,conditional_serial_total=total,
        conditional_effective_mac_ratio=USEFUL_MACS/(MACS*total),
        hypothetical_perfect_overlap_resource_ceiling=USEFUL_MACS/(MACS*max(ledger.values())),
        hardware_cycles=None,cycle_prediction=None,measured_utilization=None,
        hardware_implemented=False,original_dut_requires_this_reduction=False,
        arithmetic_equivalence_established=False,
        blockers=['partial_select_write_enable_unimplemented','partial_to_vector_route_unimplemented',
                  'tree_order_and_signed_zero_hardware_unverified','vector_loan_and_bank_schedule_unimplemented',
                  'rounding_transport_ack_schedule_unverified']+
                 (['wide_k_operand_routes_exceed_current_stream'] if route=='wide_k_hypothesis' else []))


def source_check(root=ROOT):
    for name,digest in SOURCES.items():
        path=root/name
        if path.resolve()!=path or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('reviewed resource source drift')
    return len(SOURCES)


if __name__=='__main__':
    source_check()
    print(json.dumps({route:screen(route) for route in ('outer_product_sparse','wide_k_hypothesis')},sort_keys=True,indent=2))
