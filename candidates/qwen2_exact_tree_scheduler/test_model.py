import ctypes
import hashlib
from dataclasses import replace
from pathlib import Path
import random
import subprocess
import sys

import pytest

from candidates.qwen2_exact_tree_scheduler import arithmetic as fp
from candidates.qwen2_exact_tree_scheduler.model import (CONTEXTS, Costs, Op, ProtocolError, Scheduler, SUBTREES,
                    TILE_BYTES, a_address, leaves, program, report, run)


@pytest.fixture(scope='module')
def oracle(tmp_path_factory):
    path = tmp_path_factory.mktemp('exact-tree') / 'oracle.so'
    subprocess.run(['/usr/bin/g++', '-std=c++17', '-O2', '-shared', '-fPIC',
                    '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
                    str(Path(__file__).with_name('oracle.cpp')), '-o', str(path)],
                   check=True, capture_output=True, timeout=30)
    lib = ctypes.CDLL(str(path))
    u = ctypes.c_uint32
    lib.oracle_add.argtypes = [u, u]; lib.oracle_add.restype = u
    lib.oracle_fma.argtypes = [u, u, u]; lib.oracle_fma.restype = u
    lib.oracle_reduce.argtypes = [ctypes.POINTER(u)]; lib.oracle_reduce.restype = u
    lib.oracle_dot.argtypes = [ctypes.POINTER(u), ctypes.POINTER(u)]; lib.oracle_dot.restype = u
    assert lib.supported_environment() == 1, 'RNE with FTZ/DAZ disabled required'
    return lib


def array(xs):
    return (ctypes.c_uint32 * len(xs))(*xs)


def test_exact_original_graph_and_five_contexts():
    assert leaves(SUBTREES['S04']) == [0, 32, 16, 48, 8, 40, 24, 56, 4, 36, 20, 52, 12, 44, 28, 60]
    assert sorted(sum((leaves(v) for v in SUBTREES.values()), [])) == list(range(64))
    p = program()
    assert [(x.node, x.slot) for x in p if x.kind == 'spill'] == [('S04', 0), ('T0', 0), ('S15', 1)]
    assert [(x.node, x.slot) for x in p if x.kind == 'restore'] == [('S04', 0), ('S15', 1), ('T0', 0)]
    assert [(x.node, x.left, x.right) for x in p if x.kind == 'add'][-2:] == [
        ('T1', 'S15', 'S37'), ('ROOT', 'T0', 'T1')]
    for partial in range(64):
        ops = [x for x in p if x.kind == 'fma' and x.p == partial]
        assert [x.t for x in ops] == list(range(24))
        assert [64*x.t+x.p for x in ops] == list(range(partial, 1536, 64))
    e = run()
    assert e.done and e.credit == 1 and e.peak_live_contexts == CONTEXTS
    assert e.cycle == sum(e.service_cycles.values())
    assert e.stats['acked_bytes:a_write_ack'] == 3 * TILE_BYTES
    assert e.stats['acked_bytes:a_read_two_banks'] == 3 * TILE_BYTES
    assert e.stats['acked:fma_nonemit_return'] == 1536
    assert e.stats['acked:new_wide_fp32_add_return'] == 64
    assert e.stats['acked_bytes:external_output_write_ack'] == TILE_BYTES


def test_addresses_fit_distinct_existing_banks_and_reserved_rows():
    words = [a_address(s, p, h) for s in range(2) for p in range(256) for h in range(2)]
    assert len(set(words)) == 1024
    assert all(0 <= bank < 16 and 768 <= row < 832 for bank, row in words)
    assert all(a_address(s, p, 0)[0] != a_address(s, p, 1)[0] for s in range(2) for p in range(256))


def test_fp32_edges_and_fused_rounding(oracle):
    pairs = [(0, 0x80000000), (0x80000000, 0x80000000), (0x3f800000, 0xbf800000),
             (1, 1), (0x007fffff, 1), (0x00800000, 0x807fffff),
             (0x7f7fffff, 0xff7ffffe), (0x3f800000, 0x33800000),
             (0x3f800001, 0x33800000)]
    for a, b in pairs:
        assert fp.add(a, b) == oracle.oracle_add(a, b)
    triples = [(0, 0xbf800000, 0x80000000), (0x80000000, 0x3f800000, 0x80000000),
               (0x3f800001, 0x3f7fffff, 0xbf800000), (1, 0x3f000000, 0),
               (3, 0x3f000000, 0), (0x7f7f0000, 0x3f800000, 0),
               (0x7f000000, 0x40000000, 0xff000000)]
    for a, b, c in triples:
        assert fp.fma(a, b, c) == oracle.oracle_fma(a, b, c)
    assert fp.add(0x80000000, 0) == 0  # Original explicit +0 changes -0.
    with pytest.raises(ProtocolError, match='nonfinite'):
        fp.add(0x7f7fffff, 0x7f7fffff)


def test_tree_bit_equivalence_cancel_signed_zero_and_finite_edges(oracle):
    rng = random.Random(6064)
    cases = [[0] * 64, [0x80000000] * 64, [0x3f800000, 0xbf800000] * 32,
             [1, 0x80000001] * 32, [0x00800000, 0x807fffff] * 32]
    # All positive intermediates remain finite, including a near-max root.
    cases.append([0x7c7fffff] * 64)
    cases += [[rng.getrandbits(1) << 31 | rng.randrange(100, 131) << 23 |
               rng.getrandbits(23) for _ in range(64)] for _ in range(80)]
    for values in cases:
        expected = oracle.oracle_reduce(array(values))
        assert fp.original_reduce(values) == fp.execute(partials=values) == expected


def test_full_k1536_partial_fma_and_exact_tree(oracle):
    rng = random.Random(1536)
    cases = [([0] * 1536, [0xbf800000] * 1536),
             ([0x3f800000, 0xbf800000] * 768, [0x3f800000] * 1536)]
    for _ in range(5):
        cases.append(tuple([rng.getrandbits(1) << 31 | rng.randrange(118, 130) << 23 |
                            rng.getrandbits(7) << 16 for _ in range(1536)] for _ in range(2)))
    for a, b in cases:
        assert fp.execute(a=a, b=b) == oracle.oracle_dot(array(a), array(b))


def _operand_ready(p=0):
    """Private protocol-unit fixture; integration run() executes the real fills."""
    e = Scheduler(); e.a_ready = True; e.b_partial = p
    return e


def drain(e, **kwargs):
    while e.active is not None:
        e.tick(**kwargs)


def test_context_early_reuse_wrong_sources_and_order_rejected():
    e = _operand_ready(); first = Op('fma', 0, node='p0:0', p=0, t=0)
    e.start(first)
    with pytest.raises(ProtocolError, match='hazard'):
        e.start(Op('fma', 0, node='p1:0', p=1, t=0))
    drain(e)
    with pytest.raises(ProtocolError, match='early context reuse'):
        e.start(Op('fma', 0, node='p1:0', p=1, t=0))
    with pytest.raises(ProtocolError, match='RAW'):
        e.start(Op('fma', 0, node='p0:2', left='p0:1', p=0, t=2))
    with pytest.raises(ProtocolError, match='canonical'):
        e.start(Op('add', 0, 1, 'bad', 'p0:0', 'missing'))
    with pytest.raises(ProtocolError, match='out of range'):
        e.start(replace(first, dst=5))


@pytest.mark.parametrize('field,value', [('epoch', 9), ('tile', 9), ('sequence', 9),
                                      ('context', 4), ('packet', 9), ('kind', 'bad'),
                                      ('node', 'bad'), ('partial', 4), ('k', 9),
                                      ('rhs', 3), ('slot', 1), ('half', 1)])
def test_wrong_return_tag_poison_without_credit_forgery(field, value):
    e = _operand_ready(); e.start(Op('fma', 0, node='p0:0', p=0, t=0)); e.tick()
    req, _ = e.inflight
    e.cycle += req.latency
    with pytest.raises(ProtocolError, match='mismatch'):
        e.accept_response(replace(req.tag, **{field: value}))
    assert e.poisoned and e.credit == 0 and not e.done
    e.accept_response(req.tag)
    assert e.credit == 1
    e.reset_epoch()
    with pytest.raises(ProtocolError, match='unsolicited'):
        e.accept_response(req.tag)


def test_a_commit_fence_missing_last_ack_and_unread_overwrite():
    e = Scheduler(); e.contexts[0] = 'S04'; e.start(Op('spill', 0, node='S04', left='S04', slot=0))
    while not (e.inflight and e.inflight[0].tag.kind == 'a_write_ack' and
               e.inflight[0].tag.packet == 255 and e.inflight[0].tag.half == 1):
        e.tick()
    assert not e.slot_committed[0] and e.contexts[0] == 'S04'
    for _ in range(20): e.tick(drop_ack=True)
    assert e.credit == 0 and not e.done and not e.slot_committed[0]
    with pytest.raises(ProtocolError, match='hazard'):
        e.start(Op('restore', 1, node='S04', slot=0))
    e.tick()
    assert e.slot_committed[0] and e.contexts[0] is None
    e.contexts[0] = 'T0'
    with pytest.raises(ProtocolError, match='unread A slot'):
        e.start(Op('spill', 0, node='T0', left='T0', slot=0))


def test_restore_before_committed_ack_rejected():
    e = Scheduler(); e.slots[0] = 'S04'
    with pytest.raises(ProtocolError, match='commit fence'):
        e.start(Op('restore', 0, node='S04', slot=0))


def test_backpressure_holds_tag_credit_and_extends_cycles():
    e = _operand_ready(); e.start(Op('fma', 0, node='p0:0', p=0, t=0))
    pending = e.pending
    for _ in range(4): e.tick(request_ready=False)
    assert e.pending == pending and e.credit == 1
    e.tick(); accepted = e.inflight
    for _ in range(7): e.tick(response_ready=False)
    assert e.inflight == accepted and e.credit == 0 and e.contexts[0] is None
    drain(e)
    fast = run()
    slow = run(ready=lambda state: dict(request_ready=state.cycle % 7 != 0,
                                      response_ready=state.cycle % 5 != 0))
    assert slow.done and slow.contexts == fast.contexts and slow.stats == fast.stats
    assert slow.cycle > fast.cycle and sum(slow.stall_cycles.values()) > 0


def test_abort_drains_accepts_no_new_work_and_invalidates_slots():
    e = _operand_ready(); e.slots[0] = 'old'; e.slot_committed[0] = True
    e.start(Op('fma', 0, node='p0:0', p=0, t=0)); e.tick(); tag = e.inflight[0].tag
    e.abort()
    assert e.poisoned and not any(e.slot_committed) and not e.done
    with pytest.raises(ProtocolError, match='locked'):
        e.start(Op('load_a'))
    with pytest.raises(ProtocolError, match='drain'):
        e.reset_epoch()
    while e.inflight: e.tick()
    e.reset_epoch(); assert e.epoch == tag.epoch + 1
    e.start(Op('load_a')); e.tick()
    with pytest.raises(ProtocolError, match='mismatch'):
        e.accept_response(tag)
    assert not e.done and e.poisoned


def test_final_output_ack_is_completion_boundary():
    e = Scheduler(); e.contexts[0] = 'RAW'; e.start(Op('output', 0, node='RAW', left='RAW'))
    while not (e.inflight and e.inflight[0].tag.kind == 'external_output_write_ack' and
               e.inflight[0].tag.packet == 255):
        e.tick()
    for _ in range(10): e.tick(drop_ack=True)
    assert not e.done and e.credit == 0
    drain(e); assert e.done and e.credit == 1


def test_conditional_costs_not_hardware_measurement():
    wide, vector = report(), report(Costs(mode='vector16_baseline'))
    assert wide['modeled_tile_cycles'] < vector['modeled_tile_cycles']
    assert wide['hardware_cycles'] is wide['hardware_utilization'] is None
    assert not wide['rtl_executed'] and not wide['resources']['old_result_fifo_borrowed']
    assert wide['conditional_architectural_min_tile_cycles'] == 1600
    assert wide['conditional_cold_b_fill_min_cycles'] == 12288
    assert wide['conditional_cold_tile_min_cycles'] == 12288
    assert wide['conditional_cold_tile_mac_ratio_ceiling'] == 0.125
    assert vector['conditional_cold_tile_mac_ratio_ceiling'] == 0.03125
    with pytest.raises(ProtocolError, match='five stages'):
        Costs(fma=4)


def test_add_return_locks_both_sources_and_abort_wins():
    e = Scheduler(); e.contexts[:2] = ['S04', 'S26']
    e.start(Op('add', 0, 1, 'T0', 'S04', 'S26')); e.tick()
    for _ in range(8): e.tick(response_ready=False)
    assert e.contexts[:2] == ['S04', 'S26'] and e.credit == 0
    with pytest.raises(ProtocolError, match='hazard'):
        e.start(Op('fma', 1, node='p1:0', p=1, t=0))
    e.abort(); e.tick()
    assert e.poisoned and e.credit == 1 and e.contexts == [None] * 5 and not e.done


def test_original_arithmetic_source_pin():
    root = Path(__file__).resolve().parents[2]
    path = root / 'candidates/qwen2_aten_q_projection_candidate/kernel.cpp'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == 'e44aa434113f62a7b0d1f37efcffaf38775e8e9e130ee178bd54bb0a41e080ff'


def test_forged_partial_label_and_skipped_progress_are_rejected():
    e = _operand_ready()
    with pytest.raises(ProtocolError, match='output label'):
        e.start(Op('fma', 0, node='p0:22', p=0, t=0))
    e.start(Op('fma', 0, node='p0:0', p=0, t=0)); drain(e)
    with pytest.raises(ProtocolError, match='RAW'):
        e.start(Op('fma', 0, node='p0', left='p0:22', p=0, t=23))
    # Even a corrupt caller-supplied label cannot replace stored progress.
    e.contexts[0] = 'p0:22'
    with pytest.raises(ProtocolError, match='progress'):
        e.start(Op('fma', 0, node='p0', left='p0:22', p=0, t=23))


def test_real_operand_fills_commit_and_bind_partial_before_fma():
    e = Scheduler(); op = Op('fma', 0, node='p0:0', p=0, t=0)
    with pytest.raises(ProtocolError, match='supply'):
        e.start(op)
    e.start(Op('load_a'))
    while not (e.inflight and e.inflight[0].tag.kind == 'activation_write' and
               e.inflight[0].tag.packet == 767 and e.inflight[0].tag.half == 1):
        e.tick()
    for _ in range(3): e.tick(drop_ack=True)
    assert not e.a_ready
    drain(e); assert e.a_ready
    with pytest.raises(ProtocolError, match='supply'):
        e.start(op)
    e.start(Op('fill_b', p=1)); drain(e)
    with pytest.raises(ProtocolError, match='supply'):
        e.start(op)
    e.start(Op('fill_b', p=0))
    while not (e.inflight and e.inflight[0].tag.kind == 'b_write_two_banks' and
               e.inflight[0].tag.packet == 191):
        e.tick()
    for _ in range(3): e.tick(drop_ack=True)
    assert e.b_partial is None
    drain(e); assert e.b_partial == 0
    e.start(op); drain(e)
    assert e.context_progress[0] == (0, 1)
    e.abort(); assert not e.a_ready and e.b_partial is None


def test_canonical_tree_spill_zero_output_and_restore_consumption():
    e = Scheduler(); e.contexts[0] = 'S04'
    with pytest.raises(ProtocolError, match='spill identity'):
        e.start(Op('spill', 0, node='T0', left='S04', slot=0))
    e.start(Op('spill', 0, node='S04', left='S04', slot=0)); drain(e)
    e.start(Op('restore', 0, node='S04', slot=0)); drain(e)
    with pytest.raises(ProtocolError, match='duplicate A restore'):
        e.start(Op('restore', 1, node='S04', slot=0))
    for bad in (Op('add', 0, 1, 'RAW', 'p0', 'p1'),
                Op('add', 0, 1, 'T0', 'S26', 'S04'),
                Op('zero', 0, node='RAW', left='S04'),
                Op('output', 0, node='S04', left='S04')):
        with pytest.raises(ProtocolError, match='canonical'):
            e.start(bad)
    assert not e.done and e.stats['commands:spill'] == 1


def test_oracle_rejects_sse_only_non_rne_in_isolated_process(oracle):
    code = r"""
import ctypes, sys
lib = ctypes.CDLL(sys.argv[1])
lib.oracle_get_mxcsr.restype = ctypes.c_uint32
lib.oracle_set_mxcsr.argtypes = [ctypes.c_uint32]
lib.oracle_add.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
lib.oracle_add.restype = ctypes.c_uint32
old = lib.oracle_get_mxcsr()
assert lib.supported_environment() == 1
try:
    lib.oracle_set_mxcsr((old & ~0x6000) | 0x4000)
    assert lib.supported_environment() == 0
    assert lib.oracle_add(0x3f800000, 0x33000000) == 0x3f800001
finally:
    lib.oracle_set_mxcsr(old)
assert lib.supported_environment() == 1
"""
    subprocess.run([sys.executable, '-c', code, oracle._name], check=True,
                   capture_output=True, timeout=10)
    assert oracle.supported_environment() == 1
