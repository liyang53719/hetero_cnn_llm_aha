import ctypes
import ctypes.util
import importlib.util
import json
import random
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'rectangular_attention', ROOT/'scripts/qwen2_rectangular_attention_model.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


@pytest.mark.parametrize('tokens', [128, 1024])
def test_full_causal_dag_coverage_and_gqa_layout(tokens):
    # Independently enumerate each row's keys, detecting overlaps and gaps;
    # do not merely compare two copies of the triangular-number formula.
    covered = [[] for _ in range(tokens)]
    physical_pairs = 0
    for tile in m.qk_tiles(tokens):
        assert tile['columns'] % 32 == 0
        assert tile['slice_mask'].bit_count()*32 == tile['columns']
        physical_pairs += 16*tile['columns']
        for row, count in enumerate(tile['causal_valid_columns']):
            query = tile['qbase']+row
            if query < tokens:
                covered[query].extend(range(tile['kbase'], tile['kbase']+count))
    for query, keys in enumerate(covered):
        assert keys == list(range(query+1))
    pv_pairs = 0
    captured_rows = []
    for tile in m.pv_tiles(tokens):
        assert tile['slice_mask'] == 15 and tile['columns'] == 128
        for row in range(tile['rows']):
            query = tile['qbase']+row
            keys = [key for key in range(tile['keys']) if key <= query]
            assert keys == covered[query]
            pv_pairs += len(keys)
            captured_rows.append(query)
    assert captured_rows == list(range(tokens))
    assert [m.kv_head(head) for head in range(12)] == [0]*6+[1]*6
    report = m.report(ROOT, tokens)
    assert report['macs']['useful_total'] == (sum(map(len, covered))+pv_pairs)*12*128
    assert report['macs']['qk_issued_executed'] == physical_pairs*12*128
    assert report['macs']['issued_executed_total'] >= report['macs']['useful_total']


@pytest.mark.parametrize('tokens,contexts', [(128, 1), (128, 5), (1024, 1), (1024, 5)])
def test_original_bank_depths_capacity_and_no_cross_object_alias(tokens, contexts):
    layout = m.scratch_layout(tokens, contexts)
    occupied = {'A': set(), 'B': set()}
    for obj in layout['objects']:
        for bank in range(16):
            for word in range(obj['base_word'], obj['base_word']+obj['words_per_bank']):
                key = (bank, word)
                assert key not in occupied[obj['bank_group']]
                assert word < {'A': 1376, 'B': 160}[obj['bank_group']]
                occupied[obj['bank_group']].add(key)
        # Unique element addresses, independent of allocated padding words.
        addresses = {m.scratch_address(layout, obj['name'], row, col)
                     for row in range(obj['rows']) for col in range(obj['columns'])}
        assert len(addresses) == obj['rows']*obj['columns']
    assert len(occupied['A'])*32 == layout['used_a_bytes']
    assert len(occupied['B'])*32 == layout['used_b_bytes']
    assert layout['used_a_bytes'] <= 704512
    assert layout['used_b_bytes'] == contexts*16384 <= 81920
    assert layout['allocated_total_bytes'] == 786432
    assert not layout['borrow_separate_core_or_elementwise_sram']
    if tokens == 1024:
        assert layout['used_a_bytes'] == 659456
        assert layout['allocated_a_bytes']-layout['used_a_bytes'] == 45056


@pytest.mark.parametrize('contexts', [1, 5])
@pytest.mark.parametrize('tokens', [1, 17, 33])
def test_event_protocol_pending_contexts_stripe_slots_and_row_finalization(tokens, contexts):
    pending, seen, closed, slots = {}, set(), set(), set()
    live_result = False
    peak_pending = 0
    group = None
    finished = False
    reduced_stripes = {}
    captures, acked = set(), set()
    useful = {'QK': 0, 'PV': 0}
    for e in m.iter_events(tokens, contexts):
        kind = e['event']
        if kind == 'group_start':
            assert not pending and not slots and not live_result
            assert group is None
            group = e['group']
            seen, closed, finished = set(), set(), False
        elif kind == 'matrix_issue':
            ctx = e['context']
            assert not finished and ctx < 5 and ctx not in pending and ctx not in closed
            assert e['clear'] == (ctx not in seen)
            seen.add(ctx)
            if e['last']:
                closed.add(ctx)
            if e['finish']:
                assert e['last'] and closed == seen
                finished = True
            pending[ctx] = e
            peak_pending = max(peak_pending, len(pending))
            assert len(pending) <= 8  # existing metadata FIFO
            useful[e['phase']] += e['useful_macs']
        elif kind == 'matrix_return':
            issued = pending.pop(e['context'])
            assert issued['emit'] == e['emit']
            if e['phase'] == 'QK':
                assert bool(e['returned_value_finite_check']) == issued['last']
            else:
                assert e['returned_value_finite_check_rows'] == issued['row_final']
            if e['emit']:
                assert not live_result
                live_result = True
        elif kind == 'partial_store':
            assert live_result and e['slot'] not in slots
            slots.add(e['slot'])
            live_result = False
        elif kind == 'ordered_stripe_add':
            assert e['context'] in slots
            key = e['head'], e['qbase'], e['kbase']
            stripes = reduced_stripes.setdefault(key, [])
            assert e['stripe'] == len(stripes)
            assert e['initial_positive_zero'] == (len(stripes) == 0)
            stripes.append(e['stripe'])
        elif kind == 'partial_release':
            slots.remove(e['slot'])
        elif kind == 'capture_final_row':
            assert live_result
            for row in e['rows']:
                key = e['head'], e['qbase']+row
                assert e['key'] == key[1] and key not in captures
                captures.add(key)
            live_result = False
        elif kind == 'group_done':
            assert finished and not pending and not slots and not live_result
            group = None
        elif kind == 'output_ack':
            for query in range(e['qbase'], min(tokens, e['qbase']+16)):
                assert (e['head'], query) in captures
                acked.add((e['head'], query))
        elif kind == 'owner_release':
            assert len(acked) == 12*tokens and group is None
    assert peak_pending == contexts
    assert all(stripes == list(range(16)) for stripes in reduced_stripes.values())
    assert useful['QK'] == useful['PV'] == sum(q+1 for q in range(tokens))*12*128


@pytest.mark.parametrize('contexts', [1, 5])
def test_m128_report_matches_explicit_issued_events(contexts):
    r = m.report(ROOT, 128, contexts)
    issued = {'QK': 0, 'PV': 0}
    useful, executed, groups = 0, 0, 0
    for e in m.iter_events(128, contexts):
        if e['event'] == 'matrix_issue':
            issued[e['phase']] += 1
            useful += e['useful_macs']
            executed += e['executed_macs']
        elif e['event'] == 'group_start':
            groups += 1
    assert issued == {'QK': r['schedule']['qk_wide_steps'], 'PV': r['schedule']['pv_wide_steps']}
    assert useful == r['macs']['useful_total']
    assert executed == r['macs']['issued_executed_total']
    assert groups == r['schedule']['qk_groups']+r['schedule']['pv_groups']


def test_source_drift_scope_and_current_fp32_transport(tmp_path):
    with pytest.raises(ValueError, match='source changed'):
        m.report(tmp_path, 128)
    r = m.report(ROOT, 128, 5)
    assert not any(r['scope'].values())
    assert r['predicted_attention_cycles'] is None
    assert r['predicted_full_block_cycles'] is None
    assert r['rtl_measured_cycles'] is None
    assert r['rtl_measured_utilization'] is None
    assert r['attention_80_percent_excluded_by_issue_geometry'] is True
    assert r['can_assess_full_block_80_percent_target'] is False
    assert r['macs']['scope'] == 'Attention QK+PV only, not full decoder block'
    assert r['macs']['fractions_are_not_cycle_utilization']
    assert r['traffic']['external_total_bytes'] == 1835008
    assert r['traffic']['external_partial_or_score_bytes'] == 0
    assert r['traffic']['qk_k_read_bank_bytes'] == 16*r['traffic']['qk_k_read_payload_bytes']
    assert r['schedule']['seed_restore_count'] == 0
    assert r['schedule']['pv_used_contexts'] == 1
    assert r['scratch']['additional_data_sram_bytes'] == 0
    assert r['traffic']['a_bank_read_total_bytes'] > r['traffic']['qk_k_read_bank_bytes']
    assert r['scope']['scalar_error_status_policy_validated'] is False
    assert 'underflow rejection' in r['arithmetic']['scalar_status']


@pytest.mark.parametrize('tokens,expected_bound,expected_scalar', [
    (128, .3225, 2082048), (1024, .6101190476190477, 132261888),
])
def test_attention_geometry_excludes_eighty_percent_and_counts_scalar_port(tokens, expected_bound, expected_scalar):
    one, five = m.calculate(tokens, 1), m.calculate(tokens, 5)
    assert one['attention_bounds'] == five['attention_bounds']
    b = five['attention_bounds']
    assert b['useful_utilization_issue_geometry_upper_bound'] == expected_bound < .8
    assert b['required_scalar_requests_lower_bound'] == expected_scalar
    assert b['required_scalar_requests_lower_bound'] == sum(five['schedule'][name] for name in (
        'qk_stripe_reduction_fp32_adds', 'qk_scale_fp32_multiplies',
        'softmax_diff_exp_sum_scalar_requests', 'softmax_reciprocal_scalar_requests',
        'probability_scale_fp32_multiplies'))
    assert b['scalar_single_port_cycles_lower_bound'] == expected_scalar
    assert b['useful_utilization_serialized_upper_bound'] <= b['useful_utilization_scalar_port_upper_bound'] < .003
    assert five['predicted_attention_cycles'] is None


def test_numerical_semantics_sources_are_pinned_and_drift_fails_closed(tmp_path):
    required = {
        m.BASE+'Protocol.scala', m.BASE+'BlockFloat.scala',
        'integration/gemmini/EmitHeteroBF16Fma.scala',
        'integration/gemmini/EmitHeteroFP32Alu.scala',
        'rtl/integration/qwen2_matrix_command_endpoint.sv',
        'rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv',
    }
    assert required <= m.SOURCE_PINS.keys()
    assert len(m.SOURCE_PINS) == 14
    for name in m.SOURCE_PINS:
        dst = tmp_path/name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT/name).read_bytes())
    target = tmp_path/m.BASE/'BlockFloat.scala'
    target.write_text(target.read_text().replace('round_near_even', 'round_minMag'))
    with pytest.raises(ValueError, match='BlockFloat.scala'):
        m.report(tmp_path, 128)


def test_cli_out_creates_parent_and_preserves_stdout_default(tmp_path):
    output = tmp_path/'nested'/'report.json'
    command = [sys.executable, str(ROOT/'scripts/qwen2_rectangular_attention_model.py'),
               '--tokens', '128', '--contexts', '5', '--root', str(ROOT)]
    saved = subprocess.run(command+['--out', str(output)], capture_output=True, text=True, check=True)
    assert saved.stdout == ''
    report = json.loads(output.read_text())
    printed = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(printed.stdout) == report
    assert report['attention_bounds']['useful_utilization_issue_geometry_upper_bound'] == .3225


def test_returned_value_finite_check_ignores_only_invalid_lanes():
    assert m.returned_values_finite([0x80000000, 0x7fc00000, 0x7f800000], [True, False, False])
    assert not m.returned_values_finite([0x7fc00000], [True])
    assert not m.returned_values_finite([0xff800000], [True])


def test_nonfinite_accumulator_cannot_recover_under_later_finite_fmas():
    # Independent IEEE result-class evidence, not a simulated endpoint or FP
    # flags transport claim. Overflow enters infinity; NaN/Inf stay nonfinite
    # until clear, so causal stripe-final / PV row-final checking suffices.
    lib = ctypes.CDLL(ctypes.util.find_library('m'))
    lib.fmaf.argtypes = [ctypes.c_float]*3
    lib.fmaf.restype = ctypes.c_float
    largest_bf16 = fvalue(0x7f7f0000)
    overflow = fbits(lib.fmaf(largest_bf16, largest_bf16, 0.0))
    assert overflow == 0x7f800000
    operands = [(1.0, -1.0), (-largest_bf16, largest_bf16),
                (0.0, 1.0), (fvalue(0x00010000), fvalue(0x00010000))]
    for initial in (overflow, 0xff800000, 0x7fc00001):
        accum = initial
        for a, b in operands*4:
            accum = fbits(lib.fmaf(a, b, fvalue(accum)))
            assert not m.returned_values_finite([accum], [True])


@pytest.mark.parametrize('tokens', [0, True, 128.0, 17, 1025])
def test_reject_unsupported_public_workloads(tokens):
    with pytest.raises(ValueError):
        m.calculate(tokens)


def fbits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fvalue(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def test_exact_fma_against_independent_libm_fmaf():
    lib = ctypes.CDLL(ctypes.util.find_library('m'))
    lib.fmaf.argtypes = [ctypes.c_float]*3
    lib.fmaf.restype = ctypes.c_float
    rng = random.Random(0x128)
    cases = [(0x00010000, 0x80010000, 0), (0, 0x3f800000, 0x80000000),
             (0x80000000, 0x3f800000, 0x80000000),
             (0x3f800001, 0x3f7ffffe, 0xbf800000)]
    for _ in range(2000):
        # Wide exponents, finite BF16 products and finite FP32 addends.
        a = rng.randrange(0x0080, 0x5f00) | rng.randrange(2) << 15
        b = rng.randrange(0x0080, 0x5f00) | rng.randrange(2) << 15
        c = rng.randrange(0x00000000, 0x6f000000) | rng.randrange(2) << 31
        cases.append((a << 16, b << 16, c))
    for a, b, c in cases:
        expected = fbits(lib.fmaf(fvalue(a), fvalue(b), fvalue(c)))
        assert m.fp32_fma_bits(a, b, c) == expected


def test_fp16_ingress_bf16_ties_gradual_underflow_and_signed_zero():
    for bits in [0, 0x8000, 1, 0x3c00, 0x7bff, 0x3555, 0x8001]:
        native = struct.unpack('<e', struct.pack('<H', bits))[0]
        assert m.fp16_to_fp32_bits(bits) == fbits(native)
    assert m.bf16_rne_bits(0x3f808000) == 0x3f80
    assert m.bf16_rne_bits(0x3f818000) == 0x3f82
    assert m.bf16_rne_bits(0x80000000) == 0x8000
    assert m.fp32_fma_bits(0x00010000, 0x80010000, 0) == 0x80000000
    assert m.fp32_fma_bits(0x00010000, 0x3f000000, 0) == 0x00008000
    with pytest.raises(ValueError):
        m.fp32_fma_bits(0x7f800000, 0, 0)
    with pytest.raises(ValueError):
        m.bf16_rne_bits(0x7f7fffff)


def test_qk_preserves_sixteen_stripes_not_sequential_128_dot():
    q, k = [fbits(1.0)]*128, [0]*128
    k[0], k[1], k[16] = fbits(2**24), fbits(1.0), fbits(-2**24)
    assert m.legacy_qk_bits(q, k) == fbits(1.0)
    assert m.rectangular_qk_bits([q], [k])[0][0] == fbits(1.0)
    sequential = 0
    for a, b in zip(q, k):
        sequential = m.fp32_fma_bits(a, b, sequential)
    assert sequential == fbits(0.0)


def test_small_rectangular_qk_all_causal_outputs_bit_match_original_order():
    rng = random.Random(1024)
    pool = [fbits(x) for x in (-16384, -3.25, -0.0, 0.0, 2**-16, .125, 1.0, 65536)]
    q = [[rng.choice(pool) for _ in range(128)] for _ in range(3)]
    k = [[rng.choice(pool) for _ in range(128)] for _ in range(5)]
    actual = m.rectangular_qk_bits(q, k, query_base=1)
    for row in range(3):
        for key in range(5):
            expected = m.legacy_qk_bits(q[row], k[key]) if key <= row+1 else None
            assert actual[row][key] == expected


def test_synthetic_gqa_heads_use_two_distinct_kv_caches():
    caches = [[[fbits(value)]*128 for _ in range(3)] for value in (.5, -2)]
    for head in range(12):
        q = [[fbits(head+1)]*128 for _ in range(3)]
        selected = m.kv_head(head)
        scores = m.rectangular_qk_bits(q, caches[selected])
        expected = fbits(128*(head+1)*(.5 if head < 6 else -2))
        for row in range(3):
            assert scores[row] == [expected]*(row+1)+[None]*(2-row)


def test_pv_causal_capture_preserves_negative_zero_lost_by_padding():
    p = [[0x00010000, 0], [fbits(.5), fbits(.5)]]
    v = [[0x80010000]*128, [fbits(1)]*128]
    captured, padded = m.rectangular_pv_bits(p, v)
    assert captured[0] == [0x80000000]*128
    assert padded[0] == [0]*128  # zero padding is not bitwise neutral
    assert captured[1] == padded[1]


def test_pv_ascending_keys_and_each_output_dimension_match_independent_loop():
    p = [[fbits(.5)]*4, [fbits(.25)]*4, [fbits(.125)]*4]
    v = [[fbits(value+column/128) for column in range(128)]
         for value in (2**24, 1, -2**24, 3)]
    captured, _ = m.rectangular_pv_bits(p, v, query_base=1)
    for row in range(3):
        for column in range(128):
            acc = 0
            for key in range(row+2):
                acc = m.fp32_fma_bits(m.bf16_rne_bits(p[row][key]) << 16,
                                     m.bf16_rne_bits(v[key][column]) << 16, acc)
            assert captured[row][column] == acc
