"""Source-only tensor inventory, offset, native-gate and receipt regression.

No downloaded payload, native fixture or generated vectors are checked in.
require() keeps the checks alive when this suite is run under Python -O.
"""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from heteronpu import matrix_norm_rope_tensor_candidate as t
from heteronpu.model_geometry import require

ROOT = Path(__file__).resolve().parents[1]


def test_inventory_covers_every_head_at_both_ends_of_selected_ranges():
    require(len(t.CASES) == 40 and len(t.COMMANDS) == 4, 'tensor inventory changed')
    require(len({tuple(case.items()) for case in t.CASES}) == 40, 'duplicate head case')
    for phase, tokens in t.PHASE_TOKENS:
        for token in tokens:
            for role, heads in (('q', 8), ('k', 2)):
                selected = [c for c in t.CASES if (c['phase'], c['token'], c['role']) == (phase, token, role)]
                require([c['head'] for c in selected] == list(range(heads)), 'head coverage gap')
                for case in selected:
                    t.chain.validate_descriptor(case)
    require(sorted(i for command in t.COMMANDS for i in command['case_ids']) == list(range(40)),
            'command partition repeats or omits heads')
    require([command['positions'] for command in t.COMMANDS] == [[0, 1], [0, 1], [254, 255], [254, 255]],
            'carried position offset lost')


@pytest.mark.parametrize('start,count', [(0, 128), (0, 1), (126, 2), (127, 1), (1, 127)])
def test_legal_tensor_ranges(start, count):
    t.validate_token_range(start, count)


@pytest.mark.parametrize('start,count', [(-1, 1), (128, 1), (127, 2), (0, 0), (0, 129),
    (1, 128), (True, 1), (0, True), (0.0, 1), (0, 1.0), ('0', 1), (0, None)])
def test_bad_tensor_ranges_fail_closed(start, count):
    with pytest.raises(ValueError):
        t.validate_token_range(start, count)


@pytest.mark.parametrize('role,token,head', [('q', 0, 0), ('q', 127, 7), ('k', 127, 1), ('k', 126, 0)])
def test_absolute_tensor_offsets_do_not_rebase_carried_tokens(role, token, head):
    result = t.tensor_offsets(role, token, head)
    columns, heads = (512, 8) if role == 'q' else (256, 2)
    require(result['activation'] == token * 2048 and result['trig'] == token * 128, 'token byte offset drift')
    require(result['packed'] == 2 * columns * (token * heads + head), 'packed DDR head offset drift')
    require(result['norm'] == result['rope'] == 512 * (token * heads + head), 'normalized DDR offset drift')
    require(result['weight_column'] == head * columns * 2
            and result['weight_k_stride'] == heads * columns * 2, 'weight address orientation drift')


@pytest.mark.parametrize('args', [('v', 0, 0), (0, 0, 0), ('q', -1, 0), ('k', 128, 0),
    ('q', True, 0), ('q', 0, 8), ('k', 0, 2), ('q', 0, -1), ('q', 0, False), ('k', 0, 0.0)])
def test_bad_tensor_offsets_fail_closed(args):
    with pytest.raises(ValueError):
        t.tensor_offsets(*args)


def test_totals_count_both_dispatches_and_every_accumulator():
    totals = t.expected_totals()
    require(totals['owner_commands'] == 8 and totals['head_transactions'] == 80, 'transaction count drift')
    require(totals['matrix_accumulator_steps'] == 37748736, 'sequential FMA coverage understated')
    require(totals['matrix_bf16_columns'] == 36864 and totals['matrix_fp32_columns'] == 36864,
            'packed projection coverage drift')
    require(totals['q_gate_bf16_words'] == 16384 and totals['norm_bf16_words'] == 20480
            and totals['rope_bf16_words'] == 20480 and totals['unique_trig_bf16_words'] == 512,
            'gate/norm/rope/per-token coefficient inventory drift')


def _operands():
    result = {}
    for i, case in enumerate(t.CASES):
        projected = np.full(case['columns'], 0x3f80, dtype='<u2')
        if case['role'] == 'q':
            projected[256:] = 0x4000 + case['head']
        n = np.full(256, 0x3f00 + case['head'], dtype='<u2')
        r = n.copy()
        r[:64] = 0x3f80 + case['token']
        result[i] = {'activation': np.full(1024, 0x3f80 + case['token'], dtype='<u2'),
            'trig': np.full(64, 0x3f00 + case['token'], dtype='<u2'),
            'norm_weight': np.zeros(256, dtype='<u2'), 'projected': projected,
            'norm': n, 'rope': r, 'native_projection': projected.copy(),
            'native_norm': n.copy(), 'native_rope': r.copy()}
    return result


@pytest.mark.parametrize('command', t.COMMANDS)
def test_command_files_keep_full_token_trig_all_head_gates_and_ddr_order(command):
    rows = _operands()
    arrays, comparisons = t._assemble_command(command, rows)
    require(all(item['pass'] for item in comparisons.values()), 'exact synthetic native target failed')
    schema = t._command_schema(command)
    require(set(arrays) == set(schema), 'command file inventory drift')
    for name, (words, width) in schema.items():
        require(arrays[name].dtype == np.dtype('<u2') and arrays[name].size == words and width == 4,
                'command encoding/shape drift')
    heads = command['heads']
    for token_offset in range(command['token_count']):
        token = command['token_start'] + token_offset
        require(np.all(arrays['trig'][token_offset * 64:(token_offset + 1) * 64] == 0x3f00 + token),
                'one token coefficient table reused for another token')
        for head in range(heads):
            output = arrays['rope'].reshape(2, heads, 256)[token_offset, head]
            require(np.all(output[:64] == 0x3f80 + token) and np.all(output[64:] == 0x3f00 + head),
                    'head/token/tail tensor layout drift')
    if command['role'] == 'q':
        require(np.array_equal(arrays['gate'].reshape(2, 8, 256), arrays['projected'].reshape(2, 8, 512)[:, :, 256:]),
                'packed gate differs from separately transported gate')
    else:
        require('gate' not in arrays, 'K acquired a Q gate')


@pytest.mark.parametrize('field', ['activation', 'trig', 'norm_weight'])
def test_same_token_all_head_input_consistency(field):
    rows = _operands()
    rows[1][field] = rows[1][field].copy()
    rows[1][field][0] ^= 0x3f80
    with pytest.raises(ValueError):
        t._assemble_command(t.COMMANDS[0], rows)


def test_gate_failure_remains_visible_even_if_tensor_mean_dilutes_it():
    rows = _operands()
    rows[0]['native_projection'][256] = 0x4100
    arrays, comparisons = t._assemble_command(t.COMMANDS[0], rows)
    result = comparisons['projected_gate']
    require(not result['pass'] and result['bit_mismatches'] == 1 and result['max_abs'] == 6.0,
            'Q gate native failure hidden')
    require(result['thresholds'] == {'max_abs': 0.03125, 'mean_abs': 0.005}, 'threshold loosened')
    require(arrays['gate'][0] == 0x4000, 'native gate target injected into oracle')
    t._verify_comparisons(comparisons, 'q', 16)


@pytest.fixture(scope='module')
def native_producers():
    producers, raw = {}, {}
    for phase, tokens in t.PHASE_TOKENS:
        stem = phase + '_m128_native_'
        x = np.empty((1, 128, 1024), dtype='<f4')
        for token in range(128):
            x[0, token] = token + 1
        producers[stem + 'producer_07'] = x
        for role, heads, columns, indices in (('q', 8, 512, (8, 16, 29)), ('k', 2, 256, (17, 25, 32))):
            producers[stem + f'producer_{indices[0]:02d}'] = np.full((1, 128, heads * columns), 9, dtype='<f4')
            producers[stem + f'producer_{indices[1]:02d}'] = np.full((1, 128, heads, 256), 3, dtype='<f4')
            producers[stem + f'producer_{indices[2]:02d}'] = np.full((1, heads, 128, 64), 4, dtype='<f4')
            w = np.empty((heads * columns, 1024), dtype='<u2')
            for head in range(heads):
                w[head * columns:(head + 1) * columns] = 0x3f80 + head
            raw[f'self_attn.{role}_proj.weight'] = w.tobytes()
            raw[f'self_attn.{role}_norm.weight'] = np.zeros(256, dtype='<u2').tobytes()
        for name in ('cos', 'sin'):
            array = np.empty((1, 128, 64), dtype='<f4')
            for token in range(128):
                array[0, token] = token + (1 if name == 'cos' else 2)
            producers[stem + name] = array
    return producers, raw


@pytest.mark.parametrize('case', t.CASES)
def test_all_head_extraction_uses_preprojection_and_token_specific_trig(case, native_producers):
    producers, raw = native_producers
    x, weight, nw, trig, target, normalized, rotated = t.chain._extract_case(producers, raw, case)
    expected = lambda value: int(np.asarray([value], dtype='<f4').view('<u4')[0]) >> 16
    require(np.all(x == expected(case['token'] + 1)) and np.all(target == expected(9)),
            'native projection injected instead of preprojection activation')
    require(np.all(weight == 0x3f80 + case['head']) and weight.shape == (1024, case['columns']),
            'wrong head weight or K-major orientation')
    require(np.all(trig[:32] == expected(case['token'] + 1))
            and np.all(trig[32:] == expected(case['token'] + 2)), 'wrong token trigonometric coefficients')
    require(np.all(rotated[:64] == expected(4)) and np.all(rotated[64:] == normalized[64:]),
            'native partial64/tail layout drift')


def test_memh_file_hash_encoding_and_inventory_are_checked(tmp_path):
    values = np.array([0, 0x3f80, 0x8000], dtype='<u2')
    record = t.chain._memh(tmp_path / 'x.memh', values, width=4)
    t._verify_files(tmp_path, {'x': record}, {'x': (3, 4)})
    with pytest.raises(ValueError):
        t._verify_files(tmp_path, {'x': record, 'extra': record}, {'x': (3, 4)})
    (tmp_path / 'x.memh').write_text('0000\n3F80\n8000\n')
    raw = (tmp_path / 'x.memh').read_bytes()
    record['sha256'] = t.chain._sha(raw)
    with pytest.raises(ValueError):
        t._verify_files(tmp_path, {'x': record}, {'x': (3, 4)})


@pytest.fixture
def receipt(tmp_path, monkeypatch):
    rows = _operands()
    cases, commands = [], []
    for variant in t.capture.VARIANTS:
        prefix = '' if variant == 'baseline' else 'avx2/'
        for i, case in enumerate(t.CASES):
            row = rows[i]
            comp = t._native_comparisons(case['role'], row['projected'], row['norm'], row['rope'],
                row['native_projection'], row['native_norm'], row['native_rope'])
            cases.append({**case, 'case_id': i, 'variant': variant, 'directory': prefix + f'case{i}',
                'files': {}, 'ddr_byte_offsets': t.tensor_offsets(case['role'], case['token'], case['head']),
                'native_comparisons': comp, 'native_gate_pass': True,
                'c_reference': {'matrix_fp32_columns': case['columns'], 'matrix_bf16_columns': case['columns'],
                    'matrix_accumulator_steps': 1024 * case['columns'], 'matrix_fma_flags': case['columns'],
                    'norm_trace_words': t.chain.norm.TRACE_WORDS,
                    'rope_trace_words': 32 * len(t.chain.rope.COLUMNS), 'bit_mismatches': 0,
                    'flag_mismatches': 0, 'pass': True}})
        for command in t.COMMANDS:
            _, comp = t._assemble_command(command, rows)
            commands.append({**deepcopy(command), 'variant': variant, 'directory': prefix + f"command{command['command_id']}",
                'files': {}, 'native_comparisons': comp, 'native_gate_pass': True,
                'file_tensor_origin_token': command['token_start'], 'ddr_tensor_origin_token': 0,
                'order': 'token_head_dimension', 'trig_order': 'token_cos32_sin32',
                'packed_q_order': 'token_head_content256_gate256'})
    summary = {'schema_version': 1, 'status': t.STATUS, 'policy': t.POLICY,
        'source_sha256': t._source_hashes(ROOT), 'official_manifest_sha256': '0' * 64,
        'variants': list(t.capture.VARIANTS), 'cases_per_variant': 40, 'commands_per_variant': 4,
        'cases': cases, 'commands': commands, 'totals': t.expected_totals(),
        'native_thresholds': {'max_abs': 0.03125, 'mean_abs': 0.005}, 'native_gate_pass': True,
        'native_failed_comparisons': [], 'native_arrays_injected_after_matrix': False,
        'all_q8_k2_heads_covered': True, 'all_128_tokens_covered': False, 'rtl_executed': False,
        'native_full_block_gate_pass': {'baseline': False, 'avx2': False}}
    monkeypatch.setattr(t.capture, '_location', lambda root, output: (ROOT, output))
    monkeypatch.setattr(t.capture, 'load_materialized', lambda *args, **kwargs:
        {v: (None, {'native_audit_gate_pass': False}) for v in t.capture.VARIANTS})
    monkeypatch.setattr(t, '_verify_files', lambda *args: None)
    def verify(value, digest=None):
        data = json.dumps(value, sort_keys=True).encode()
        (tmp_path / 'summary.json').write_bytes(data)
        return t.verify_materialized(tmp_path, trusted_summary_sha256=digest or t.chain._sha(data))
    return summary, verify


def test_complete_inventory_receipt_and_true_native_failures_are_independent(receipt):
    summary, verify = receipt
    result = verify(summary)
    require(result['native_gate_pass'] and not result['native_full_block_gate_pass']['baseline'],
            'selected heads incorrectly promoted to native full-block acceptance')
    with pytest.raises(ValueError):
        verify(summary, '0' * 64)


def test_genuine_selected_head_failure_is_preserved_without_aborting_receipt(receipt):
    summary, verify = receipt
    case = summary['cases'][0]
    comparison = case['native_comparisons']['norm']
    comparison.update(bit_mismatches=1, max_abs=0.0625, mean_abs=0.0625 / 256, **{'pass': False})
    case['native_gate_pass'] = False
    summary['commands'][0]['native_gate_pass'] = False
    summary['native_gate_pass'] = False
    summary['native_failed_comparisons'] = [{key: case[key] for key in
        ('variant', 'case_id', 'phase', 'token', 'role', 'head')} | {'stage': 'norm', **comparison}]
    result = verify(summary)
    require(result['native_gate_pass'] is False and len(result['native_failed_comparisons']) == 1,
            'real numerical failure aborted or disappeared from materialization')


def test_mean_threshold_is_not_replaced_by_maximum_only_gate():
    actual = np.full(256, 0x3f80, dtype='<u2')
    target = np.full(256, 0x3f81, dtype='<u2')
    result = t.chain.compare_native(actual, target)
    require(result['max_abs'] <= 0.03125 and result['mean_abs'] > 0.005 and result['pass'] is False,
            'mean error gate silently dropped')


@pytest.mark.parametrize('kind', ['missing_case', 'duplicate_case', 'case_bool', 'missing_command',
    'wrong_case_ids', 'wrong_positions', 'wrong_offset', 'count', 'policy', 'native_threshold',
    'native_pass', 'native_count', 'c_steps', 'full_block', 'all_tokens', 'native_injection',
    'false_failure_list', 'command_gate', 'file_origin'])
def test_malformed_receipt_fails_closed(receipt, kind):
    summary, verify = receipt
    if kind == 'missing_case': summary['cases'].pop()
    elif kind == 'duplicate_case': summary['cases'][1] = deepcopy(summary['cases'][0])
    elif kind == 'case_bool': summary['cases'][0]['case_id'] = False
    elif kind == 'missing_command': summary['commands'].pop()
    elif kind == 'wrong_case_ids': summary['commands'][0]['case_ids'][0] = 1
    elif kind == 'wrong_positions': summary['commands'][2]['positions'][0] = 126
    elif kind == 'wrong_offset': summary['cases'][20]['ddr_byte_offsets']['packed'] = 0
    elif kind == 'count': summary['totals']['matrix_accumulator_steps'] -= 1
    elif kind == 'policy': summary['policy'] = t.chain.POLICY
    elif kind == 'native_threshold': summary['native_thresholds']['max_abs'] = 0.5
    elif kind == 'native_pass': summary['cases'][0]['native_comparisons']['norm']['pass'] = False
    elif kind == 'native_count': summary['cases'][0]['native_comparisons']['norm']['elements'] = 1
    elif kind == 'c_steps': summary['cases'][0]['c_reference']['matrix_accumulator_steps'] -= 1
    elif kind == 'full_block': summary['native_full_block_gate_pass']['baseline'] = True
    elif kind == 'all_tokens': summary['all_128_tokens_covered'] = True
    elif kind == 'native_injection': summary['native_arrays_injected_after_matrix'] = True
    elif kind == 'false_failure_list': summary['native_gate_pass'] = False
    elif kind == 'command_gate': summary['commands'][0]['native_gate_pass'] = False
    elif kind == 'file_origin': summary['commands'][2]['file_tensor_origin_token'] = 0
    with pytest.raises(ValueError):
        verify(summary)


def test_source_cli_does_not_allow_native_replay_or_trust_override():
    cli = (ROOT / 'scripts/materialize_matrix_norm_rope_tensor_vectors.py').read_text()
    require(all(option not in cli for option in ('--input-npz', '--trusted', '--manifest')), 'corpus trust bypass')
    source = (ROOT / 'src/heteronpu/matrix_norm_rope_tensor_candidate.py').read_text()
    require('chain.chain_trace(activation, weight, nw, trig' in source, 'raw-input chain binding absent')
    require('np.matmul' not in source and 'urlopen' not in source and 'requests.get' not in source,
            'native projection approximation/download added')
