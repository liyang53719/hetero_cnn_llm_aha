"""Integer-only schedule/capacity proposal. No tensor arithmetic or RTL execution."""
from dataclasses import dataclass, asdict
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
M, K, NQ, NK = 128, 1536, 1536, 256
MACS, CONTEXTS, LANES = 4096, 5, 16
TILE_BYTES = MACS * 4
A_BYTES, B_BYTES = 704512, 81920
WHOLE_USEFUL_MACS = 6014828544
BLOCK_COUNTER_SOURCE = 'candidates/qwen2_official_platform_fullblock/runner.py'


def need(value, message):
    if not value:
        raise ValueError(message)


def reduction_tree(nodes):
    """Offsets 4,2,1, preserving ordered left/right children exactly."""
    nodes = list(nodes)
    while len(nodes) > 1:
        half = len(nodes) // 2
        nodes = [(nodes[i], nodes[i + half]) for i in range(half)]
    return nodes[0]


def full_tree():
    return reduction_tree(reduction_tree(8 * r + lane for r in range(8))
                          for lane in range(8))


def leaves(node):
    return [node] if isinstance(node, int) else leaves(node[0]) + leaves(node[1])


def postorder(node):
    return [] if isinstance(node, int) else postorder(node[0]) + postorder(node[1]) + [node]


def schedule(group_size=5):
    """Group leaf partials, spill, then do ready ordered postorder additions.

    All output snapshots spill before this group's reductions. One add reuses
    its lhs slot only AFTER both operands were read. Slot release occurs only
    after all 256 output packet writes were acknowledged. This is an ordering
    contract, not an implemented handshake machine or bank controller.
    """
    need(type(group_size) is int and 1 <= group_size <= CONTEXTS, 'five real contexts only')
    root = full_tree()
    order, adds = leaves(root), postorder(root)
    live, slots, trace = {}, list(range(11)), []
    peak = ai = 0
    for begin in range(0, 64, group_size):
        group = order[begin:begin + group_size]
        for context, p in enumerate(group):
            need(bool(slots), 'bounded slot allocator exhausted')
            slot = slots.pop(0)
            live[p] = slot
            peak = max(peak, len(live))
            trace.append(dict(op='partial', context=context, p=p, slot=slot,
                              k=[64 * t + p for t in range(24)],
                              clear_at_t=0, emit_last_at_t=23,
                              finish=context == len(group) - 1))
        while ai < len(adds) and all(child in live for child in adds[ai]):
            node = adds[ai]
            lhs, rhs = live.pop(node[0]), live.pop(node[1])
            trace.append(dict(op='add', lhs_slot=lhs, rhs_slot=rhs, dst_slot=lhs,
                              left=node[0], right=node[1], packets=256,
                              release_rhs_after_last_write_ack=True))
            live[node] = lhs
            slots.append(rhs)
            slots.sort()
            ai += 1
        trace.append(dict(op='group_fence', live_slots=len(live),
                          require_matrix_done=True, require_loan_drained=True,
                          require_all_local_write_acks=True))
    need(ai == 63 and list(live) == [root], 'incomplete ordered reduction')
    return dict(leaf_order=order, groups=(64 + group_size - 1) // group_size,
                group_size=group_size, peak_partial_slots=peak, trace=trace,
                root_slot=live[root])


def partial_address(slot, packet, half):
    """32B words, 16 banks, region after a conservative full M128 A reserve."""
    need(0 <= slot < 11 and 0 <= packet < 256 and half in (0, 1), 'partial bounds')
    word = packet * 2 + half
    return word % 16, 768 + slot * 32 + word // 16


@dataclass(frozen=True)
class Costs:
    # Positive hypothetical serialized service units; NEVER measured clocks.
    recurrence: int = 5
    external_64b: int = 1
    local_bank_phase: int = 1  # one parallel read phase OR one selected 32B A write
    vector_16_add: int = 1
    activation_16_convert: int = 1
    group_command_done: int = 4
    external_request_ack: int = 2


def screen(costs=Costs(), group_size=5):
    need(type(costs) is Costs and all(type(x) is int and x > 0 for x in asdict(costs).values()),
         'positive explicit integer assumptions required')
    need(costs.recurrence >= 5, 'retained feedback latency cannot be shortened')
    sched = schedule(group_size)
    outputs = M * (NQ + NK)
    tiles = outputs // MACS
    groups = [min(group_size, 64 - i) for i in range(0, 64, group_size)]
    issues = tiles * K
    useful = outputs * K
    # Each independent partial uses the same physical cell through t=0..23.
    issue_span = tiles * sum(23 * max(c, costs.recurrence) + c for c in groups)
    drain = tiles * len(groups) * (costs.recurrence - 1)
    partial_beats = outputs * 64 * 4 // 64
    tree_requests = outputs * 63 // LANES
    tail_requests = outputs // LANES
    # Separate 63-node tree, explicit +0, raw output. No bias/RoPE fusion.
    raw_beats = outputs * 4 // 64
    activation_read = 2 * M * K * 4  # independent Q and K calls, FP32 transport
    weight_read = (M // 16) * K * (NQ + NK) * 2
    # Existing Bias reads every 16-word bias packet again for every token.
    bias_bytes = outputs * 12  # raw read + bias read + output store
    rope_bytes = outputs * 12  # 4 reads + 2 writes for each output pair
    projection_external = activation_read + weight_read + outputs * 4
    # B native BF16 writes use two distinct banks. A FP32 conversion writes
    # only 32B per 16-word DDR beat, through its existing single selected bank.
    activation_writes = activation_read // 64
    weight_writes = weight_read // 64
    external_beats = projection_external // 64
    # Safe conservative request+ACK accounting: one transaction per 64B beat.
    # Burst coalescing is possible but deliberately not credited here.
    ledger = {
        'matrix_issue_and_recurrence': issue_span,
        'matrix_fill_drain': drain,
        'operand_sram_service': issues * costs.local_bank_phase,
        'activation_convert_and_local_write': activation_writes * (costs.activation_16_convert + costs.local_bank_phase),
        'weight_local_fill': weight_writes * costs.local_bank_phase,
        'external_activation_weight_raw_output': external_beats * costs.external_64b,
        # Keep StreamingDense's one selected A-bank write per cycle: every
        # 64B snapshot/result is TWO distinct 32B accepted writes, not a new
        # two-bank write broadcast. The lender holds its result until both.
        'partial_snapshot_writes': 2 * partial_beats * costs.local_bank_phase,
        'tree_operand_read_write_bank_phases': 4 * tree_requests * costs.local_bank_phase,
        'tree_vector_adds': tree_requests * costs.vector_16_add,
        'tail_zero_read_write_and_add': tail_requests * (3 * costs.local_bank_phase + costs.vector_16_add),
        'raw_output_local_read': raw_beats * costs.local_bank_phase,
        'group_command_done_fences': tiles * len(groups) * costs.group_command_done,
        'external_request_ack': external_beats * costs.external_request_ack,
    }
    total = sum(ledger.values())
    other_ideal = (WHOLE_USEFUL_MACS - useful + MACS - 1) // MACS
    return dict(status='SCHEDULE_CAPACITY_ONLY_NOT_HARDWARE_PASS',
        physical_macs=MACS, physical_contexts=CONTEXTS,
        accumulator_bytes=CONTEXTS * TILE_BYTES, additional_mac_lanes=0,
        additional_accumulator_words=0, borrowed_shared_fp32_add_lanes=16,
        group_size=group_size, groups_per_tile=len(groups), output_tiles=tiles,
        peak_partial_slots=sched['peak_partial_slots'],
        peak_partial_bytes=sched['peak_partial_slots'] * TILE_BYTES,
        reserved_partial_slots=11, reserved_partial_bytes=11 * TILE_BYTES,
        conservative_full_m128_bf16_activation_reserve=M * K * 2,
        a_total_reserved_bytes=M * K * 2 + 11 * TILE_BYTES,
        a_capacity_bytes=A_BYTES, a_spare_bytes=A_BYTES - M * K * 2 - 11 * TILE_BYTES,
        b_group_payload_bytes=group_size * 24 * 256 * 2,
        b_capacity_bytes=B_BYTES, b_prefetch_double_buffer_credited=False,
        additional_wide_hold_bytes=64,  # one explicitly priced lhs packet
        result_fifo_bytes=32768, final_value_bytes=TILE_BYTES,
        retained_leaf_result_register_bytes=CONTEXTS * TILE_BYTES,
        useful_qk_macs=useful, physical_issue_slots=issues * MACS,
        issue_geometry_fill=1, partial_snapshot_bytes=partial_beats * 64,
        partial_snapshot_selected_bank_writes=2 * partial_beats,
        tree_read_bank_phases=2 * tree_requests,
        tree_selected_bank_writes=2 * tree_requests,
        ordered_tree_adds=outputs * 63, zero_tail_adds=outputs,
        activation_read_bytes=activation_read, weight_read_bytes=weight_read,
        projection_raw_store_ack_bytes=outputs * 4,
        unchanged_bias=dict(fp32_adds=outputs, external_bytes=bias_bytes,
                            conversion_count=None, follow_existing_owner=True),
        unchanged_rope=dict(fp32_multiplies=2 * outputs, fp32_adds=outputs,
                            external_bytes=rope_bytes, conversion_count=None,
                            follow_existing_owner=True),
        assumptions=asdict(costs), conditional_serial_projection_cost_units=ledger,
        conditional_serial_projection_total=total,
        conditional_projection_mac_ratio=useful / (MACS * total),
        full_block_useful_macs=WHOLE_USEFUL_MACS,
        full_block_denominator='4096 * (launch acceptance through accepted terminal result, all pc0..20, writes/ACKs/drain)',
        full_block_cost_formula='projection_core + unchanged_bias_rope_conversion + all_other_owners + interowner_control_and_stalls',
        conditional_other_matrix_ideal_min_units=other_ideal,
        conditional_full_block_ceiling_using_serial_projection=WHOLE_USEFUL_MACS / (MACS * (total + other_ideal)),
        # Excludes even known bias/RoPE costs from ceiling, so remains optimistic.
        hardware_cycles=None, measured_utilization=None, cycle_prediction=None,
        full_block_cost=None, conversion_service_cost=None,
        numeric_executed=False, rtl_executed=False, hardware_implemented=False)


def source_check():
    sources = json.loads((HERE / 'sources.json').read_text())
    for name, expected in sources.items():
        need(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, 'source drift: ' + name)
    need(BLOCK_COUNTER_SOURCE in sources, 'published fullblock counter source required')
    # Parse only; do not import or execute the fullblock runner. This published
    # source carries the same original shape count as the local recovery run.
    tree = ast.parse((ROOT / BLOCK_COUNTER_SOURCE).read_text())
    counts = [node.value.value for node in ast.walk(tree)
              if isinstance(node, ast.keyword) and node.arg == 'whole_useful_macs'
              and isinstance(node.value, ast.Constant)]
    need(counts == [WHOLE_USEFUL_MACS], 'full block fixed work counter drift')
    return len(sources)


if __name__ == '__main__':
    source_check()
    print(json.dumps(screen(), indent=2, sort_keys=True))
