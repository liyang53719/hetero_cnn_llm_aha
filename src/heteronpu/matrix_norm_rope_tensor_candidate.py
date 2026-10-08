"""Source-only full-Q8/K2 owner vectors for selected cold/carried token ranges.

Every head uses actual preprojection H1024 activation and checkpoint weights.
The reused integer sequential-FMA/Norm256/partial64-RoPE oracle is independently
checked by C. Native projections are comparison targets, never pipeline inputs.
The selection is four tokens, not an assertion of all-128-token/block coverage.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .model_geometry import require
from . import matrix_norm_rope_candidate as chain
from . import qk_norm256_materialization as capture

POLICY = chain.POLICY + '_q8_k2_tensor_owner_v1'
PHASE_TOKENS = (('cold', (0, 1)), ('carried', (126, 127)))
CASES = tuple({'role': role, 'phase': phase, 'token': token, 'head': head,
               'position': token + (128 if phase == 'carried' else 0),
               'columns': 512 if role == 'q' else 256}
              for phase, tokens in PHASE_TOKENS for token in tokens
              for role, heads in (('q', 8), ('k', 2)) for head in range(heads))
COMMANDS = tuple({'command_id': command_id, 'role': role, 'phase': phase,
                  'token_start': tokens[0], 'token_count': len(tokens),
                  'heads': 8 if role == 'q' else 2,
                  'positions': [token + (128 if phase == 'carried' else 0) for token in tokens],
                  'case_ids': [i for i, case in enumerate(CASES)
                               if case['phase'] == phase and case['role'] == role]}
                 for command_id, (phase, tokens, role) in enumerate(
                     (phase, tokens, role) for phase, tokens in PHASE_TOKENS for role in ('q', 'k')))
MATERIALIZER_SOURCES = (*chain.MATERIALIZER_SOURCES,
    'src/heteronpu/matrix_norm_rope_tensor_candidate.py',
    'scripts/materialize_matrix_norm_rope_tensor_vectors.py',
    'config/upstream/qwen3_5_0p8b/matrix_norm_rope_tensor_contract.json')
STATUS = 'MATERIALIZED_INDEPENDENT_Q8_K2_TENSOR_VECTORS'


def validate_token_range(token_start: int, token_count: int) -> None:
    require(type(token_start) is int and type(token_count) is int
            and 0 <= token_start < 128 and 1 <= token_count <= 128
            and token_start + token_count <= 128, 'invalid tensor token range')


def tensor_offsets(role: str, token: int, head: int) -> dict:
    """Absolute DDR byte offsets; command-local files begin at token_start.

    Packed Q keeps each head's content256 followed by its unmodified gate256.
    Normalized/RoPE tensors are token, head, dimension. Coefficients are token,
    cos32 then sin32. The owner may reuse fixed L2 staging between heads.
    """
    require(type(role) is str and role in ('q', 'k'), 'invalid tensor role')
    require(type(token) is int and 0 <= token < 128, 'invalid tensor token')
    heads, columns = (8, 512) if role == 'q' else (2, 256)
    require(type(head) is int and 0 <= head < heads, 'invalid tensor head')
    return {'activation': token * 2048,
            'weight_column': head * columns * 2,
            'packed': (token * heads + head) * columns * 2,
            'norm': (token * heads + head) * 512,
            'rope': (token * heads + head) * 512,
            'trig': token * 128,
            'weight_k_stride': heads * columns * 2}


def expected_totals() -> dict:
    variants = len(capture.VARIANTS)
    heads = len(CASES) * variants
    columns = sum(case['columns'] for case in CASES) * variants
    return {'variants': variants, 'owner_commands': len(COMMANDS) * variants,
            'head_transactions': heads, 'q_head_transactions': 32 * variants,
            'k_head_transactions': 8 * variants,
            'selected_phase_tokens': 4 * variants,
            'matrix_fp32_columns': columns, 'matrix_bf16_columns': columns,
            'matrix_accumulator_steps': chain.K_DIM * columns,
            'matrix_fma_flags': columns,
            'norm_bf16_words': heads * 256, 'rope_bf16_words': heads * 256,
            'q_gate_bf16_words': 32 * variants * 256,
            'unique_trig_bf16_words': 4 * variants * 64,
            'norm_trace_words': heads * chain.norm.TRACE_WORDS,
            'rope_trace_words': heads * 32 * len(chain.rope.COLUMNS)}


def _source_hashes(root: Path) -> dict:
    return {name: chain._sha((root / name).read_bytes()) for name in MATERIALIZER_SOURCES}


def _case_schema(columns: int) -> dict:
    return {'activation': (1024, 4), 'weight': (1024 * columns, 4),
            'norm_weight': (256, 4), 'trig': (64, 4), 'projected': (columns, 4),
            'projected_fp32': (columns, 8), 'projected_steps': (1024 * columns, 8),
            'norm': (256, 4), 'rope': (256, 4)}


def _command_schema(command: dict) -> dict:
    heads, count = command['heads'], command['token_count']
    columns = 512 if command['role'] == 'q' else 256
    schema = {'activation': (count * 1024, 4), 'trig': (count * 64, 4),
              'norm_weight': (256, 4), 'projected': (count * heads * columns, 4),
              'norm': (count * heads * 256, 4), 'rope': (count * heads * 256, 4)}
    if command['role'] == 'q':
        schema['gate'] = (count * heads * 256, 4)
    return schema


def _native_comparisons(role: str, projected, normalized, rotated,
                        native_projection, native_norm, native_rope) -> dict:
    columns = 512 if role == 'q' else 256
    p = np.asarray(projected, dtype='<u2').reshape(-1, columns)
    n = np.asarray(normalized, dtype='<u2').reshape(-1, 256)
    r = np.asarray(rotated, dtype='<u2').reshape(-1, 256)
    npj = np.asarray(native_projection, dtype='<u2').reshape(p.shape)
    nn = np.asarray(native_norm, dtype='<u2').reshape(n.shape)
    nr = np.asarray(native_rope, dtype='<u2').reshape(r.shape)
    comparisons = {name: chain.compare_native(a, b) for name, a, b in (
        ('projected_content', p[:, :256], npj[:, :256]), ('norm', n, nn),
        ('rope_rotated64', r[:, :64], nr[:, :64]),
        ('rope_passthrough192', r[:, 64:], nr[:, 64:]), ('rope_full256', r, nr))}
    if role == 'q':
        comparisons['projected_gate'] = chain.compare_native(p[:, 256:], npj[:, 256:])
    return comparisons


def _assemble_command(command: dict, operands: dict) -> tuple[dict, dict]:
    """Build token-major contiguous DDR expectations from actual head results."""
    validate_token_range(command['token_start'], command['token_count'])
    selected = [operands[index] for index in command['case_ids']]
    heads = command['heads']
    require(len(selected) == command['token_count'] * heads, 'command head inventory drift')
    for token_index in range(command['token_count']):
        first = selected[token_index * heads]
        for row in selected[token_index * heads:(token_index + 1) * heads]:
            require(np.array_equal(first['activation'], row['activation'])
                    and np.array_equal(first['trig'], row['trig']),
                    'activation/trig must agree across every head of each token')
    require(all(np.array_equal(selected[0]['norm_weight'], row['norm_weight']) for row in selected),
            'per-role Norm weight drift')
    arrays = {name: np.concatenate([row[name] for row in selected])
              for name in ('projected', 'norm', 'rope')}
    arrays.update({name: np.concatenate([selected[i * heads][name]
                                         for i in range(command['token_count'])])
                   for name in ('activation', 'trig')})
    arrays['norm_weight'] = selected[0]['norm_weight']
    if command['role'] == 'q':
        arrays['gate'] = np.concatenate([row['projected'][256:] for row in selected])
    comparisons = _native_comparisons(command['role'], arrays['projected'], arrays['norm'], arrays['rope'],
        *[np.concatenate([row[name] for row in selected])
          for name in ('native_projection', 'native_norm', 'native_rope')])
    return arrays, comparisons


def _write_case(path: Path, activation, weight, norm_weight, trig, trace) -> dict:
    projected = trace['projected']
    columns = weight.shape[1]
    steps = projected['steps_fp32'].reshape(1024, columns // 32, 32).transpose(1, 0, 2)
    arrays = {'activation': (activation, 4), 'weight': (weight, 4),
              'norm_weight': (norm_weight, 4), 'trig': (trig, 4),
              'projected': (projected['bf16'], 4), 'projected_fp32': (projected['fp32'], 8),
              'projected_steps': (steps, 8),
              'norm': (np.asarray(trace['norm']['output_bf16'], dtype='<u4') >> 16, 4),
              'rope': (trace['rope_bf16'], 4)}
    return {name: chain._memh(path / (name + '.memh'), value, width=width)
            for name, (value, width) in arrays.items()}


def materialize(root: Path, payload0: Path, payload3: Path, payload_extra: Path, output: Path) -> dict:
    """Fresh official baseline/AVX2 execution and every Q8/K2 head in four tokens.

    Native failures are retained in the result; they do not hide oracle/C/RTL
    evidence. No arbitrary saved arrays, downloaded NPZ or digest CLI is used.
    The returned digest is an in-process receipt, absent from the saved summary.
    """
    from .pinned_block_payload import load_payload
    root, output = capture._location(root, output, fresh=True)
    sources = _source_hashes(root)
    output.mkdir(parents=True, exist_ok=True)
    manifest, raw = load_payload(root, Path(payload3).resolve())
    weights = {name: chain._sha(raw[name]) for name in
               ('self_attn.q_proj.weight', 'self_attn.k_proj.weight',
                'self_attn.q_norm.weight', 'self_attn.k_norm.weight')}
    _, official_digest = capture.rebuild(root, payload0, payload3, payload_extra, output / 'official')
    official = json.loads((output / 'official/provenance.json').read_text())
    executables = chain._compile_references(root, output)
    cases, commands = [], []
    for variant in capture.VARIANTS:
        directory = output if variant == 'baseline' else output / variant
        directory.mkdir(parents=True, exist_ok=True)
        native_path = output / 'official' / variant / 'native/all_bf16_producers.npz'
        capture._verify_file(native_path, official['corpora'][variant]['fresh_audit_arrays'])
        operands = {}
        with np.load(native_path, allow_pickle=False) as producers:
            require(len(producers.files) == len(set(producers.files)), 'duplicate native producer arrays')
            for case_id, case in enumerate(CASES):
                activation, weight, nw, trig, native_p, native_n, native_r = chain._extract_case(producers, raw, case)
                trace = chain.chain_trace(activation, weight, nw, trig, role=case['role'])
                path = directory / ('case' + str(case_id))
                path.mkdir()
                reference = chain._crosscheck_c(path, executables, activation, weight, nw, trig, trace)
                files = _write_case(path, activation, weight, nw, trig, trace)
                p = np.asarray(trace['projected']['bf16'], dtype='<u2')
                n = (np.asarray(trace['norm']['output_bf16'], dtype='<u4') >> 16).astype('<u2')
                r = np.asarray(trace['rope_bf16'], dtype='<u2')
                comparisons = _native_comparisons(case['role'], p, n, r, native_p, native_n, native_r)
                operands[case_id] = {'activation': activation, 'trig': trig, 'norm_weight': nw,
                    'projected': p, 'norm': n, 'rope': r, 'native_projection': native_p,
                    'native_norm': native_n, 'native_rope': native_r}
                cases.append({**case, 'case_id': case_id, 'variant': variant,
                    'directory': str(path.relative_to(output)), 'files': files,
                    'input_producer': 'input_layernorm|cast_bf16|0',
                    'activation_sha256': chain._sha(activation.tobytes()),
                    'selected_weight_k_major_sha256': chain._sha(weight.tobytes()),
                    'norm_weight_sha256': chain._sha(nw.tobytes()), 'trig_sha256': chain._sha(trig.tobytes()),
                    'ddr_byte_offsets': tensor_offsets(case['role'], case['token'], case['head']),
                    'c_reference': reference, 'native_comparisons': comparisons,
                    'native_gate_pass': all(value['pass'] for value in comparisons.values())})
        for command in COMMANDS:
            path = directory / ('command' + str(command['command_id']))
            path.mkdir()
            arrays, comparisons = _assemble_command(command, operands)
            files = {name: chain._memh(path / (name + '.memh'), values, width=4)
                     for name, values in arrays.items()}
            commands.append({**command, 'variant': variant, 'directory': str(path.relative_to(output)),
                'files': files, 'native_comparisons': comparisons,
                'native_gate_pass': all(cases[(0 if variant == 'baseline' else len(CASES)) + index]['native_gate_pass']
                                        for index in command['case_ids']),
                'file_tensor_origin_token': command['token_start'],
                'ddr_tensor_origin_token': 0, 'order': 'token_head_dimension',
                'trig_order': 'token_cos32_sin32', 'packed_q_order': 'token_head_content256_gate256'})
    require(_source_hashes(root) == sources, 'tensor candidate source changed during materialization')
    require(load_payload(root, Path(payload3).resolve()) == (manifest, raw), 'payload changed during materialization')
    capture.load_materialized(root, output / 'official', trusted_manifest_sha256=official_digest)
    failed = [{'variant': case['variant'], 'case_id': case['case_id'], 'phase': case['phase'],
               'token': case['token'], 'role': case['role'], 'head': case['head'],
               'stage': name, **comparison}
              for case in cases for name, comparison in case['native_comparisons'].items() if not comparison['pass']]
    summary = {'schema_version': 1, 'status': STATUS, 'policy': POLICY, 'source_sha256': sources,
        'official_manifest_sha256': official_digest, 'model_id': official['model_id'],
        'revision': official['revision'], 'framework_revision': official['framework_revision'],
        'layer_id': 3, 'weight_sha256': weights, 'cases_per_variant': len(CASES),
        'commands_per_variant': len(COMMANDS), 'variants': list(capture.VARIANTS),
        'cases': cases, 'commands': commands, 'totals': expected_totals(),
        'native_thresholds': {'max_abs': chain.MAX_ABS, 'mean_abs': chain.MEAN_ABS},
        'native_gate_pass': not failed, 'native_failed_comparisons': failed,
        'fresh_official_executions': len(capture.VARIANTS), 'native_arrays_injected_after_matrix': False,
        'all_q8_k2_heads_covered': True, 'all_128_tokens_covered': False, 'rtl_executed': False,
        'native_full_block_gate_pass': {name: official['corpora'][name]['native_audit_gate_pass']
                                       for name in capture.VARIANTS},
        'scope': 'All Q8/K2 heads in cold tokens0,1 and carried tokens126,127 (positions254,255); '
                 'sequential FMA then Norm256 and partial64 RoPE, every Q gate unchanged; no full block claim'}
    summary_path = output / 'summary.json'
    summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
    digest = chain._sha(summary_path.read_bytes())
    verify_materialized(output, trusted_summary_sha256=digest)
    return {**summary, 'summary_sha256': digest}


def _verify_files(path: Path, records: dict, schema: dict) -> None:
    require(set(records) == set(schema), 'tensor vector file inventory drift')
    for name, (words, width) in schema.items():
        file = path / (name + '.memh')
        require(file.resolve().is_relative_to(path.resolve()), 'tensor vector path escape')
        data = file.read_bytes()
        require(records[name] == {'file': file.name, 'words': words, 'hex_digits': width,
                 'bytes': len(data), 'sha256': chain._sha(data)}
                and len(data) == words * (width + 1), 'tensor vector binding drift: ' + name)
        lines = data.splitlines()
        require(len(lines) == words and all(len(line) == width and all(c in b'0123456789abcdef' for c in line)
                                            for line in lines), 'tensor vector encoding drift: ' + name)


def _verify_comparisons(comparisons: dict, role: str, heads: int) -> None:
    sizes = {'projected_content': 256, 'norm': 256, 'rope_rotated64': 64,
             'rope_passthrough192': 192, 'rope_full256': 256}
    if role == 'q':
        sizes['projected_gate'] = 256
    require(set(comparisons) == set(sizes), 'tensor native comparison inventory drift')
    for name, size in sizes.items():
        value = comparisons[name]
        require(type(value['elements']) is int and value['elements'] == size * heads
                and type(value['bit_mismatches']) is int and 0 <= value['bit_mismatches'] <= size * heads,
                'tensor native comparison count drift')
        require(all(type(value[k]) in (int, float) and math.isfinite(value[k]) and value[k] >= 0
                    for k in ('max_abs', 'mean_abs')) and value['mean_abs'] <= value['max_abs'],
                'tensor native error metric drift')
        require(value['thresholds'] == {'max_abs': chain.MAX_ABS, 'mean_abs': chain.MEAN_ABS}
                and value['pass'] is (value['max_abs'] <= chain.MAX_ABS and value['mean_abs'] <= chain.MEAN_ABS),
                'tensor native threshold/result drift')


def verify_materialized(output: Path, *, trusted_summary_sha256: str) -> dict:
    """Revalidate the fresh in-process receipt, complete inventory and every memh."""
    root, output = capture._location(Path(__file__).resolve().parents[2], output)
    raw = (output / 'summary.json').read_bytes()
    require(type(trusted_summary_sha256) is str and len(trusted_summary_sha256) == 64
            and chain._sha(raw) == trusted_summary_sha256, 'untrusted tensor summary digest')
    summary = json.loads(raw)
    require(type(summary['schema_version']) is int and summary['schema_version'] == 1
            and summary['policy'] == POLICY and summary['status'] == STATUS, 'tensor summary schema/policy drift')
    require(summary['source_sha256'] == _source_hashes(root), 'tensor source binding drift')
    require(summary['variants'] == list(capture.VARIANTS) and summary['cases_per_variant'] == len(CASES)
            and summary['commands_per_variant'] == len(COMMANDS)
            and len(summary['cases']) == len(CASES) * len(capture.VARIANTS)
            and len(summary['commands']) == len(COMMANDS) * len(capture.VARIANTS), 'tensor case inventory drift')
    require(summary['totals'] == expected_totals(), 'tensor count drift')
    require(summary['native_thresholds'] == {'max_abs': chain.MAX_ABS, 'mean_abs': chain.MEAN_ABS}
            and summary['native_arrays_injected_after_matrix'] is False
            and summary['all_q8_k2_heads_covered'] is True
            and summary['all_128_tokens_covered'] is False and summary['rtl_executed'] is False,
            'tensor numerical/scope policy drift')
    official = capture.load_materialized(root, output / 'official',
                                        trusted_manifest_sha256=summary['official_manifest_sha256'])
    require(summary['native_full_block_gate_pass'] ==
            {variant: official[variant][1]['native_audit_gate_pass'] for variant in capture.VARIANTS},
            'tensor full-block failure disclosure drift')
    for index, case in enumerate(summary['cases']):
        descriptor = {name: case[name] for name in CASES[0]}
        chain.validate_descriptor(descriptor)
        case_id = index % len(CASES)
        variant = list(capture.VARIANTS)[index // len(CASES)]
        relative = ('avx2/' if variant == 'avx2' else '') + 'case' + str(case_id)
        require(descriptor == CASES[case_id] and case['variant'] == variant
                and type(case['case_id']) is int and case['case_id'] == case_id
                and case['directory'] == relative, 'tensor case mapping drift')
        require(case['ddr_byte_offsets'] == tensor_offsets(case['role'], case['token'], case['head']),
                'tensor DDR offsets drift')
        _verify_comparisons(case['native_comparisons'], case['role'], 1)
        require(case['native_gate_pass'] is all(value['pass'] for value in case['native_comparisons'].values()),
                'tensor per-head native failure hidden')
        reference = case['c_reference']
        require(reference == {'matrix_fp32_columns': case['columns'], 'matrix_bf16_columns': case['columns'],
            'matrix_accumulator_steps': 1024 * case['columns'], 'matrix_fma_flags': case['columns'],
            'norm_trace_words': chain.norm.TRACE_WORDS, 'rope_trace_words': 32 * len(chain.rope.COLUMNS),
            'bit_mismatches': 0, 'flag_mismatches': 0, 'pass': True}, 'tensor independent C coverage drift')
        _verify_files(output / relative, case['files'], _case_schema(case['columns']))
    for index, command in enumerate(summary['commands']):
        command_id = index % len(COMMANDS)
        expected = COMMANDS[command_id]
        variant = list(capture.VARIANTS)[index // len(COMMANDS)]
        relative = ('avx2/' if variant == 'avx2' else '') + 'command' + str(command_id)
        require(all(type(command[key]) is type(value) and command[key] == value for key, value in expected.items())
                and command['variant'] == variant and command['directory'] == relative,
                'tensor owner command mapping drift')
        validate_token_range(command['token_start'], command['token_count'])
        _verify_comparisons(command['native_comparisons'], command['role'], command['heads'] * command['token_count'])
        offset = list(capture.VARIANTS).index(variant) * len(CASES)
        require(command['native_gate_pass'] is all(summary['cases'][offset + i]['native_gate_pass']
                                                   for i in command['case_ids']),
                'tensor command per-head native failure hidden')
        require(command['file_tensor_origin_token'] == command['token_start']
                and command['ddr_tensor_origin_token'] == 0 and command['order'] == 'token_head_dimension'
                and command['trig_order'] == 'token_cos32_sin32'
                and command['packed_q_order'] == 'token_head_content256_gate256', 'tensor output layout drift')
        _verify_files(output / relative, command['files'], _command_schema(command))
    failed = [{'variant': case['variant'], 'case_id': case['case_id'], 'phase': case['phase'],
               'token': case['token'], 'role': case['role'], 'head': case['head'], 'stage': name, **value}
              for case in summary['cases'] for name, value in case['native_comparisons'].items() if not value['pass']]
    # json sort_keys changes comparison insertion order; inventory equality is
    # keyed by the identity of each failing head/stage rather than JSON order.
    order = lambda item: (item['variant'], item['case_id'], item['stage'])
    require(sorted(summary['native_failed_comparisons'], key=order) == sorted(failed, key=order)
            and summary['native_gate_pass'] is (not failed), 'tensor native failure disclosure drift')
    return summary
