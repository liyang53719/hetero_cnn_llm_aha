"""Source-only tensor inventory, offset, native-gate and receipt regression.

No downloaded payload, native fixture or generated vectors are checked in.
require() keeps the checks alive when this suite is run under Python -O.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from heteronpu import matrix_norm_rope_tile16_candidate as t
from heteronpu.model_geometry import require

ROOT = Path(__file__).resolve().parents[1]


def test_inventory_covers_every_head_at_both_ends_of_selected_ranges():
    require(len(t.CASES) == 320 and len(t.COMMANDS) == 4, 'tensor inventory changed')
    require(len({tuple(case.items()) for case in t.CASES}) == 320, 'duplicate head case')
    for phase, tokens in t.PHASE_TOKENS:
        for token in tokens:
            for role, heads in (('q', 8), ('k', 2)):
                selected = [c for c in t.CASES if (c['phase'], c['token'], c['role']) == (phase, token, role)]
                require([c['head'] for c in selected] == list(range(heads)), 'head coverage gap')
                for case in selected:
                    t.chain.validate_descriptor(case)
    require(sorted(i for command in t.COMMANDS for i in command['case_ids']) == list(range(320)),
            'command partition repeats or omits heads')
    require([command['positions'] for command in t.COMMANDS] == [list(range(16)), list(range(16)), list(range(240, 256)), list(range(240, 256))],
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
    require(totals['owner_commands'] == 8 and totals['head_transactions'] == 640, 'transaction count drift')
    require(totals['matrix_accumulator_steps'] == 301989888, 'sequential FMA coverage understated')
    require(totals['matrix_bf16_columns'] == 294912 and totals['matrix_fp32_columns'] == 294912,
            'packed projection coverage drift')
    require(totals['q_gate_bf16_words'] == 131072 and totals['norm_bf16_words'] == 163840
            and totals['rope_bf16_words'] == 163840 and totals['unique_trig_bf16_words'] == 4096,
            'gate/norm/rope/per-token coefficient inventory drift')


def _operands():
    result = {}
    for i, case in enumerate(t.CASES + t.SUPPLEMENTAL_CASES):
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
            output = arrays['rope'].reshape(16, heads, 256)[token_offset, head]
            require(np.all(output[:64] == 0x3f80 + token) and np.all(output[64:] == 0x3f00 + head),
                    'head/token/tail tensor layout drift')
    if command['role'] == 'q':
        require(np.array_equal(arrays['gate'].reshape(16, 8, 256), arrays['projected'].reshape(16, 8, 512)[:, :, 256:]),
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
    t._verify_comparisons(comparisons, 'q', 128)


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
    cases, supplemental_cases, commands = [], [], []
    for variant in t.capture.VARIANTS:
        prefix = '' if variant == 'baseline' else 'avx2/'
        for i, case in enumerate(t.CASES + t.SUPPLEMENTAL_CASES):
            row = rows[i]
            comp = t._native_comparisons(case['role'], row['projected'], row['norm'], row['rope'],
                row['native_projection'], row['native_norm'], row['native_rope'])
            destination = cases if i < len(t.CASES) else supplemental_cases
            destination.append({**case, 'case_id': i, 'variant': variant, 'directory': prefix + f'case{i}',
                'files': {}, 'shared_weight': 'shared_weights/' + case['role'] + '_head' + str(case['head']) + '/weight.memh',
                'selected_weight_k_major_sha256': 'a' * 64, 'ddr_byte_offsets': t.tensor_offsets(case['role'], case['token'], case['head']),
                'native_comparisons': comp, 'native_gate_pass': True,
                'c_reference': {'matrix_fp32_columns': case['columns'], 'matrix_bf16_columns': case['columns'],
                    'matrix_accumulator_steps': 1024 * case['columns'], 'matrix_fma_flags': case['columns'],
                    'norm_trace_words': t.chain.norm.TRACE_WORDS,
                    'rope_trace_words': 32 * len(t.chain.rope.COLUMNS), 'bit_mismatches': 0,
                    'flag_mismatches': 0, 'pass': True,
                    'matrix_output_sha256': 'b' * 64, 'norm_output_sha256': 'c' * 64}})
        for command in t.COMMANDS:
            _, comp = t._assemble_command(command, rows)
            commands.append({**deepcopy(command), 'variant': variant, 'directory': prefix + f"command{command['command_id']}",
                'files': {}, 'native_comparisons': comp, 'native_gate_pass': True,
                'file_tensor_origin_token': command['token_start'], 'ddr_tensor_origin_token': 0,
                'order': 'token_head_dimension', 'trig_order': 'token_cos32_sin32',
                'packed_q_order': 'token_head_content256_gate256'})
    summary = {'schema_version': 1, 'status': t.STATUS, 'policy': t.POLICY,
        'source_sha256': {'test': 'a' * 64}, 'official_manifest_sha256': '0' * 64,
        'fresh_official_executions': 2,
        'variants': list(t.capture.VARIANTS), 'cases_per_variant': 320, 'commands_per_variant': 4,
        'cases': cases, 'commands': commands, 'totals': t.expected_totals(),
        'supplemental_cases': supplemental_cases, 'supplemental_cases_per_variant': 2,
        'supplemental_totals': t.expected_supplemental_totals(),
        'supplemental_native_gate_pass': True, 'supplemental_native_failed_comparisons': [],
        'native_thresholds': {'max_abs': 0.03125, 'mean_abs': 0.005}, 'native_gate_pass': True,
        'native_failed_comparisons': [], 'native_failed_command_comparisons': [],
        'shared_weights': [], 'projected_steps_layout': 'tile32_k_lane_uint32_le',
        'weight_storage': 'hardlinks_to_unique_checkpoint_heads', 'native_arrays_injected_after_matrix': False,
        'all_q8_k2_heads_covered': True, 'all_128_tokens_covered': False, 'rtl_executed': False,
        'native_full_block_gate_pass': {'baseline': False, 'avx2': False}}
    monkeypatch.setattr(t, '_source_hashes', lambda root: {'test': 'a' * 64})
    monkeypatch.setattr(t.capture, '_location', lambda root, output: (ROOT, output))
    monkeypatch.setattr(t.capture, 'load_materialized', lambda *args, **kwargs:
        {v: (None, {'native_audit_gate_pass': False}) for v in t.capture.VARIANTS})
    monkeypatch.setattr(t, '_verify_output_inventory', lambda *args: None)
    monkeypatch.setattr(t, '_verify_files', lambda *args, **kwargs: None)
    monkeypatch.setattr(t, '_verify_case_input_bindings', lambda *args: None)
    monkeypatch.setattr(t, '_verify_command_case_links', lambda *args: None)
    monkeypatch.setattr(t, '_verify_shared_weights', lambda *args: {
        (role, head): {'directory': 'shared_weights/' + role + '_head' + str(head),
                      'k_major_bf16_sha256': 'a' * 64, 'file': {}}
        for role, heads in (('q', 8), ('k', 2)) for head in range(heads)})
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
    elif kind == 'wrong_positions': summary['commands'][2]['positions'][0] = 112
    elif kind == 'wrong_offset': summary['cases'][160]['ddr_byte_offsets']['packed'] = 0
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
    cli = (ROOT / 'scripts/materialize_matrix_norm_rope_tile16_vectors.py').read_text()
    require(all(option not in cli for option in ('--input-npz', '--trusted', '--manifest')), 'corpus trust bypass')
    source = (ROOT / 'src/heteronpu/matrix_norm_rope_tile16_candidate.py').read_text()
    require('matrix_norm_rope_tensor_candidate.py' not in t.MATERIALIZER_SOURCES,
            'tile16 must not modify or depend on legacy tensor materializer')
    require('chain.chain_trace(activation, weight, nw, trig' in source, 'raw-input chain binding absent')
    require('np.matmul' not in source and 'urlopen' not in source and 'requests.get' not in source,
            'native projection approximation/download added')


def test_supplemental_token16_k_heads_are_separate_from_frozen_primary_tiles():
    require(t.SUPPLEMENTAL_CASES == tuple({'role': 'k', 'phase': 'cold', 'token': 16,
        'head': head, 'position': 16, 'columns': 256} for head in range(2)), 'tail17 case mapping drift')
    require(all(c['token'] != 16 for c in t.CASES), 'supplemental token leaked into primary coverage')
    require(t.expected_totals()['head_transactions'] == 640
            and t.expected_supplemental_totals()['head_transactions'] == 4,
            'primary and supplemental evidence conflated')
    require(t.expected_totals()['projected_steps_bytes'] == 1207959552
            and t.expected_totals()['unique_weight_memh_bytes'] == 23592960
            and t.expected_supplemental_totals()['projected_steps_bytes'] == 4194304,
            'bounded binary/weight storage budget drift')


def test_binary_steps_are_exact_little_endian_tile_k_lane_and_hash_bound(tmp_path):
    original = np.arange(1024 * 256, dtype='<u4').reshape(1024, 256)
    tiled = original.reshape(1024, 8, 32).transpose(1, 0, 2)
    record = t._binary_steps(tmp_path / 'projected_steps.bin', tiled)
    data = (tmp_path / 'projected_steps.bin').read_bytes()
    require(data[:8] == bytes.fromhex('0000000001000000')
            and int.from_bytes(data[128:132], 'little') == int(original[1, 0])
            and int.from_bytes(data[131072:131076], 'little') == int(original[0, 32]),
            'binary step endianness or tile/K/lane order drift')
    require(np.array_equal(np.frombuffer(data, dtype='<u4').reshape(8, 1024, 32), tiled),
            'not every accumulator survived binary serialization')
    t._verify_files(tmp_path, {'projected_steps': record}, {'projected_steps': (262144, 'uint32_le')})
    raw = bytearray(data)
    raw[100] ^= 1
    (tmp_path / 'projected_steps.bin').write_bytes(raw)
    with pytest.raises(ValueError):
        t._verify_files(tmp_path, {'projected_steps': record}, {'projected_steps': (262144, 'uint32_le')})


@pytest.mark.parametrize('kind', ['truncated', 'extra', 'symlink', 'extra_file', 'wrong_encoding'])
def test_binary_receipt_rejects_extent_inventory_symlink_and_encoding(tmp_path, kind):
    path = tmp_path / 'projected_steps.bin'
    steps = np.zeros((8, 1024, 32), dtype='<u4')
    record = t._binary_steps(path, steps)
    if kind == 'truncated': path.write_bytes(path.read_bytes()[:-4])
    elif kind == 'extra': path.write_bytes(path.read_bytes() + b'\0' * 4)
    elif kind == 'symlink':
        path.rename(tmp_path / 'outside')
        path.symlink_to(tmp_path / 'outside')
    elif kind == 'extra_file': (tmp_path / 'unbound.memh').write_text('0000\n')
    elif kind == 'wrong_encoding': record['encoding'] = 'uint32_be'
    with pytest.raises(ValueError):
        t._verify_files(tmp_path, {'projected_steps': record}, {'projected_steps': (262144, 'uint32_le')})


def test_case_weight_requires_actual_hardlink_not_just_equal_bytes(tmp_path):
    shared = tmp_path / 'shared'
    case = tmp_path / 'case'
    shared.mkdir()
    case.mkdir()
    values = np.array([0, 0x3f80], dtype='<u2')
    record = t.chain._memh(shared / 'weight.memh', values, width=4)
    (case / 'weight.memh').hardlink_to(shared / 'weight.memh')
    t._verify_files(case, {'weight': record}, {'weight': (2, 4)},
                    verified_weight=(shared / 'weight.memh', record))
    (case / 'weight.memh').unlink()
    shutil.copyfile(shared / 'weight.memh', case / 'weight.memh')
    with pytest.raises(ValueError):
        t._verify_files(case, {'weight': record}, {'weight': (2, 4)},
                        verified_weight=(shared / 'weight.memh', record))


def test_whole_command_native_failure_cannot_be_hidden_by_head_passes(receipt):
    summary, verify = receipt
    command = summary['commands'][0]
    value = command['native_comparisons']['norm']
    value.update(bit_mismatches=1, max_abs=0.0625, mean_abs=0.0625 / value['elements'], **{'pass': False})
    with pytest.raises(ValueError):
        verify(summary)
    command['native_gate_pass'] = False
    summary['native_gate_pass'] = False
    summary['native_failed_command_comparisons'] = t._failed_commands(summary['commands'])
    require(verify(summary)['native_gate_pass'] is False, 'command native failure hidden')


def test_supplemental_native_failure_is_disclosed_and_rejects_combined_gate(receipt):
    summary, verify = receipt
    case = summary['supplemental_cases'][0]
    value = case['native_comparisons']['norm']
    value.update(bit_mismatches=1, max_abs=0.0625, mean_abs=0.0625 / 256, **{'pass': False})
    case['native_gate_pass'] = False
    with pytest.raises(ValueError):
        verify(summary)
    summary['supplemental_native_gate_pass'] = False
    summary['native_gate_pass'] = False
    summary['supplemental_native_failed_comparisons'] = t._failed_heads(summary['supplemental_cases'])
    require(verify(summary)['native_gate_pass'] is False, 'tail17 native failure hidden')


def test_full_synthetic_k1024_integer_c_binary_evidence_and_scratch_cleanup(tmp_path):
    if shutil.which('cc') is None:
        pytest.skip('independent C compiler unavailable')
    executables = t.chain._compile_references(ROOT, tmp_path)
    case = tmp_path / 'case'
    case.mkdir()
    activation = np.zeros(1024, dtype='<u2')
    activation[0], activation[1], activation[-1] = 0x3f80, 0x4000, 0xbf80
    weight = np.zeros((1024, 256), dtype='<u2')
    weight[0] = np.asarray([0x3f00 + (i % 128) for i in range(256)], dtype='<u2')
    weight[1], weight[-1] = 0x3c00, 0x3b80
    gamma = np.zeros(256, dtype='<u2')
    trig = np.concatenate((np.full(32, 0x3f80, dtype='<u2'), np.zeros(32, dtype='<u2')))
    trace = t.chain.chain_trace(activation, weight, gamma, trig, role='k')
    crosscheck = t._crosscheck_c(case, executables, activation, weight, gamma, trig, trace)
    require(crosscheck['matrix_accumulator_steps'] == 262144 and crosscheck['pass'],
            'independent C did not check every K/lane')
    require(not list(case.iterdir()), 'duplicate C weight/steps payloads retained')
    projection = trace['projected']
    c_output = np.concatenate((np.asarray(projection['fp32'], dtype='<u4'),
        np.asarray(projection['bf16'], dtype='<u4') << 16,
        np.asarray(projection['fma_flags'], dtype='<u4'), projection['steps_fp32'].reshape(-1)))
    require(crosscheck['matrix_output_sha256'] == t.chain._sha(c_output.tobytes()),
            'C all-accumulator evidence digest missing')
    shared = t._write_shared_weight(tmp_path, {'role': 'k', 'head': 0, 'columns': 256}, weight)
    files = t._write_case(case, activation, weight, gamma, trig, trace,
                          shared=tmp_path / shared['directory'] / 'weight.memh')
    t._verify_files(case, files, t._case_schema(256),
                    verified_weight=(tmp_path / shared['directory'] / 'weight.memh', shared['file']))
    restored = np.fromfile(case / 'projected_steps.bin', dtype='<u4').reshape(8, 1024, 32)
    require(np.array_equal(restored.transpose(1, 0, 2).reshape(1024, 256), projection['steps_fp32']),
            'binary projection steps differ from independent integer/C evidence')


@pytest.mark.parametrize('field', ['activation', 'trig', 'projected', 'norm', 'rope', 'gate', 'norm_weight'])
def test_command_case_arithmetic_inputs_outputs_and_gate_are_linked(tmp_path, field):
    command = {**t.COMMANDS[0], 'directory': 'command0', 'variant': 'baseline'}
    operands = _operands()
    rows = []
    for index, descriptor in enumerate(t.CASES):
        row = {**descriptor, 'case_id': index, 'directory': 'case' + str(index), 'variant': 'baseline'}
        rows.append(row)
        if index not in command['case_ids']:
            continue
        path = tmp_path / row['directory']
        path.mkdir()
        for name in ('activation', 'trig', 'norm_weight', 'projected', 'norm', 'rope'):
            t.chain._memh(path / (name + '.memh'), operands[index][name], width=4)
    arrays, _ = t._assemble_command(command, operands)
    path = tmp_path / 'command0'
    path.mkdir()
    for name, value in arrays.items():
        t.chain._memh(path / (name + '.memh'), value, width=4)
    t._verify_command_case_links(tmp_path, command, rows)
    arrays[field][0] ^= 1
    t.chain._memh(path / (field + '.memh'), arrays[field], width=4)
    with pytest.raises(ValueError):
        t._verify_command_case_links(tmp_path, command, rows)


def test_all_source_bindings_exist_and_legacy_tensor_is_unchanged_by_dependency():
    hashes = t._source_hashes(ROOT)
    require(len(hashes) == len(t.MATERIALIZER_SOURCES)
            and all(len(value) == 64 for value in hashes.values()), 'source pin inventory drift')
    require(t.POLICY != t.chain.POLICY and 'tile16' in t.POLICY, 'new opt-in policy identity missing')
