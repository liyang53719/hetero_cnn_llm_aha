import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from candidates.qwen2_exact_tree_scheduler.model import Op, ProtocolError
from candidates.qwen2_transposed_exact_scheduler.model import (
    TransposedScheduler, ledger, operand_wires, output_coordinate,
    physical_operands, report, run, w_address, weight_ddr_offset, x_address, panel_identity)
from candidates.qwen2_transposed_exact_scheduler.gather import Gather, segment_address, destination


def test_full_m128_x_addresses_bijection_and_capacity():
    addresses = {x_address(m, k) for m in range(128) for k in range(1536)}
    assert len(addresses) == 128*1536
    assert all(0 <= b < 16 and 0 <= w < 768 and 0 <= l < 16 for b, w, l in addresses)
    for k in range(1536):
        assert len({x_address(m, k)[:2] for m in range(128)}) == 8


def test_w_halves_banks_unique_data_and_partial_offsets():
    slots = [{w_address(h, t, n) for t in range(24) for n in range(32)} for h in range(2)]
    assert not slots[0] & slots[1] and all(len(s) == 24*32 for s in slots)
    assert all(0 <= b < 16 and 0 <= w < 160 for s in slots for b, w, l in s)
    for h in range(2):
        for t in range(24):
            assert len({w_address(h, t, n)[:2] for n in range(32)}) == 2
    offsets = {weight_ddr_offset(p, t) for p in range(64) for t in range(24)}
    assert len(offsets) == 1536 and all(a % 64 == 0 for a in offsets)


def test_transposed_packet_routes_all4096_cells_without_copy():
    x, w = tuple(range(128)), tuple(range(1000, 1032))
    a, b = operand_wires(x, w)
    coordinates = set()
    for m in range(128):
        for n in range(32):
            row, col = output_coordinate(m, n); coordinates.add((row, col))
            assert physical_operands(a, b, col//32, row, col % 32) == (w[n], x[m])
    assert len(coordinates) == 4096 and len(a) == 16 and len(b) == 256
    assert b[144:] == (0,)*112


def test_cold_event_counts_exact_tree_spills_and_fills():
    e = run()
    assert e.done and e.credit == 1 and e.peak_live_contexts == 5
    assert e.cycle == sum(e.service_cycles.values())
    assert e.stats['acked_bytes:external_read_x'] == 786432
    assert e.stats['acked_bytes:external_read_w'] == 98304
    assert e.stats['acked:x_rmw_commit_ack'] == 12288
    assert e.stats['acked:x_zero_all_banks_ack'] == 768
    assert e.stats['acked:fma_nonemit_return'] == 1536
    assert e.stats['acked:new_wide_fp32_add_return'] == 64
    assert e.stats['acked_bytes:a_write_ack'] == e.stats['acked_bytes:a_read_two_banks'] == 49152
    assert e.stats['acked_bytes:external_output_write_ack'] == 16384


def test_same_engine_lease_requires_exact_terminal_and_bounds():
    e = TransposedScheduler()
    with pytest.raises(ProtocolError, match='previous output'):
        e.next_panel(1)
    e = run(2)
    assert e.stats['acked_bytes:external_read_x'] == 786432
    assert e.stats['acked_bytes:external_read_w'] == 2*98304
    assert e.stats['acked_bytes:external_output_write_ack'] == 2*16384
    e.abort()
    with pytest.raises(ProtocolError, match='previous output'):
        e.next_panel(2)


def test_backpressure_does_not_change_canonical_counts():
    fast = run()
    slow = run(ready=lambda e: dict(request_ready=e.cycle % 7 != 0, response_ready=e.cycle % 5 != 0))
    assert slow.stats == fast.stats and slow.cycle > fast.cycle
    assert slow.contexts == fast.contexts and slow.done


def test_cold_scope_cannot_claim80_or_shared_rms_residency():
    r = ledger(); b = r['bounds']
    assert b['warm_arithmetic_ceiling'] == 0.96
    assert b['warm_existing_singlebeat_dma_mac_ceiling'] == .5
    assert b['whole_context_lock_min_cycles_per_panel'] == 2124
    assert b['whole_context_lock_mac_ceiling'] < .8
    assert r['unique_bytes']['x_wire'] == 786432
    assert r['unique_bytes']['x_sram'] == 393216
    assert b['new_shared_x_lease_cold_cycles_floor'] == 114944
    assert b['new_shared_x_lease_cold_mac_ceiling'] < .8
    assert b['legacy_two_job_cold_mac_ceiling'] < b['new_shared_x_lease_cold_mac_ceiling']
    assert b['fullblock_shared_rms_residency_cycles'] is None
    assert r['hardware_cycles'] is r['hardware_utilization'] is None
    assert not r['physical']['result_fifo_borrowed']


def test_imported_protocol_source_is_pinned():
    p = Path(__file__).resolve().parents[1] / 'qwen2_exact_tree_scheduler/model.py'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == '3724464b20170fd0e39e65d76a574669b099cebe1148f1b1ff3af296fa5712cb'


def test_supply_identity_and_panel_successor_are_bound_to_returns():
    e = run()
    with pytest.raises(ProtocolError, match='successor'):
        e.next_panel(0)
    with pytest.raises(ProtocolError, match='successor'):
        e.next_panel(2)
    e.next_panel(1)
    e.start(Op('fill_b', p=32))
    tag = e.pending.tag
    assert (tag.tensor, tag.width, tag.nbase) == ('Q', 1536, 32)
    assert tag.address == weight_ddr_offset(32, 0, 32, 1536)
    assert tag.x_k == 32 and tag.b_t == 0
    e.tick(); e.cycle += 2
    with pytest.raises(ProtocolError, match='mismatch'):
        e.accept_response(replace(tag, address=tag.address+64))
    assert e.poisoned and e.credit == 0
    assert panel_identity(47) == ('Q', 1536, 1504)
    assert panel_identity(48) == ('K', 256, 0)
    assert panel_identity(55) == ('K', 256, 224)


def test_two_gather_buffers_masks_source_stride_and_no_early_reuse():
    g = Gather()
    for row in range(16):
        address = segment_address(0, row)
        assert address == row*6144
        g.issue_segment(('r', row), 0, row, address)
        if row == 0:
            with pytest.raises(ProtocolError, match='DMA credit'):
                g.issue_segment('bad', 0, 1, segment_address(0, 1))
        g.accept_segment(('r', row))
        if row < 15:
            with pytest.raises(ProtocolError, match='all16'):
                g.issue_commit('early', 0)
    g.issue_commit('w0', 0)
    g.issue_segment('r1', 1, 0, segment_address(1, 0)); g.accept_segment('r1')
    assert g.peak_buffers == 2 and not g.ready
    with pytest.raises(ProtocolError, match='reuse'):
        g.issue_segment('reuse', 2, 0, segment_address(2, 0))
    with pytest.raises(ProtocolError, match='identity'):
        g.accept_commit('wrong')
    g.accept_commit('w0')
    assert g.buffers[0] is None and g.committed == 1
    for block in (0, 7, 8, 767):
        for row in range(16):
            for lane in range(16):
                q, group = divmod(block, 8)
                assert destination(block, row, lane) == x_address(group*16+row, q*16+lane)


def test_gather_error_abort_drains_without_ready():
    g = Gather(); g.issue_segment('x', 0, 0, 0)
    g.accept_segment('x', success=False)
    assert g.poisoned and not g.ready and g.dma is None
    with pytest.raises(ProtocolError, match='poison'):
        g.issue_segment('y', 0, 1, segment_address(0, 1))


def test_gather_integrated_final_bulk_ack_is_a_readiness_fence():
    e = TransposedScheduler(ingress='gather2_candidate'); e.start(Op('load_a'))
    while not (e.inflight and e.inflight[0].tag.kind == 'new_x_16bank_bulk_commit_ack' and
               e.inflight[0].tag.block == 767):
        e.tick()
    for _ in range(8): e.tick(drop_ack=True)
    assert not e.a_ready and not e.gather.ready and e.credit == 0
    e.tick()
    assert e.a_ready and e.gather.ready and e.credit == 1
    full = run(ingress='gather2_candidate')
    assert full.done and full.stats['acked_bytes:external_read_x'] == 786432
    assert full.stats['acked:new_x_16bank_bulk_commit_ack'] == 768
    assert not full.stats['acked:x_rmw_commit_ack'] and not full.stats['acked:x_zero_all_banks_ack']
    assert full.cycle == 67712


def test_rejected_reentrant_start_preserves_gather_state():
    e = TransposedScheduler(ingress='gather2_candidate'); e.start(Op('load_a'))
    for _ in range(3): e.tick()
    old = e.gather
    state = (old.allocated, old.committed, old.buffers[0].mask, e.pending)
    assert state[2] == 1
    with pytest.raises(ProtocolError, match='hazard'):
        e.start(Op('load_a'))
    assert e.gather is old
    assert (old.allocated, old.committed, old.buffers[0].mask, e.pending) == state


@pytest.mark.parametrize('shared', [False, True])
def test_q_to_k_engine_gate_requires_explicit_new_shared_lease(shared):
    e = run(shared_qk_lease=shared, ingress='gather2_candidate')
    # Protocol-unit fixture: move the completed Q panel identity to the final Q
    # panel, retaining the actually ACKed cold A and drained output state.
    e.tile, e.panel = 47, panel_identity(47)
    e.next_panel(48)
    assert e.panel == ('K', 256, 0)
    assert e.a_ready is shared and e.gather.ready is shared
    e.start(Op('fill_b', p=0))
    while e.active is not None: e.tick()
    if not shared:
        with pytest.raises(ProtocolError, match='supply'):
            e.start(Op('fma', 0, node='p0:0', p=0, t=0))
    else:
        e.start(Op('fma', 0, node='p0:0', p=0, t=0))
        while e.active is not None: e.tick()
        assert e.context_progress[0] == (0, 1)
