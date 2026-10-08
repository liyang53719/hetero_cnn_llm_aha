"""Source-only tile16 gate: all Q8/K2 heads in two selected sixteen-token tiles.

Cold tokens 0..15 and carried tokens 112..127 use actual H1024 preprojection
operands. Every increasing-K accumulator is independently checked by integer
Python and host C, then stored as transient little-endian uint32, tile32/K/lane.
Weights are hardlinked to ten shared, source-bound checkpoint head files. Native
failures are diagnostics retained at both head and whole-command granularity.
Nothing here changes the existing tensor gate or claims all-M128/full-block RTL.
"""
from __future__ import annotations

import json
import math
import hashlib
import os
from pathlib import Path

import numpy as np

from .model_geometry import require
from . import matrix_norm_rope_candidate as chain
from . import qk_norm256_materialization as capture

POLICY = chain.POLICY + '_q8_k2_tile16_owner_v1'
PHASE_TOKENS = (('cold', tuple(range(16))), ('carried', tuple(range(112, 128))))
CASES = tuple({'role': role, 'phase': phase, 'token': token, 'head': head,
               'position': token + (128 if phase == 'carried' else 0),
               'columns': 512 if role == 'q' else 256}
              for phase, tokens in PHASE_TOKENS for token in tokens
              for role, heads in (('q', 8), ('k', 2)) for head in range(heads))
SUPPLEMENTAL_CASES = tuple({'role': 'k', 'phase': 'cold', 'token': 16, 'head': head,
                            'position': 16, 'columns': 256} for head in range(2))
COMMANDS = tuple({'command_id': command_id, 'role': role, 'phase': phase,
                  'token_start': tokens[0], 'token_count': len(tokens),
                  'heads': 8 if role == 'q' else 2,
                  'positions': [token + (128 if phase == 'carried' else 0) for token in tokens],
                  'case_ids': [i for i, case in enumerate(CASES)
                               if case['phase'] == phase and case['role'] == role]}
                 for command_id, (phase, tokens, role) in enumerate(
                     (phase, tokens, role) for phase, tokens in PHASE_TOKENS for role in ('q', 'k')))
MATERIALIZER_SOURCES = (*chain.MATERIALIZER_SOURCES,
    'src/heteronpu/matrix_norm_rope_tile16_candidate.py',
    'scripts/materialize_matrix_norm_rope_tile16_vectors.py',
    'config/upstream/qwen3_5_0p8b/matrix_norm_rope_tile16_contract.json')
STATUS = 'MATERIALIZED_INDEPENDENT_Q8_K2_TILE16_VECTORS'


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
            'head_transactions': heads, 'q_head_transactions': 256 * variants,
            'k_head_transactions': 64 * variants,
            'selected_phase_tokens': 32 * variants,
            'matrix_fp32_columns': columns, 'matrix_bf16_columns': columns,
            'matrix_accumulator_steps': chain.K_DIM * columns,
            'matrix_fma_flags': columns, 'projected_steps_bytes': 4 * chain.K_DIM * columns,
            'norm_bf16_words': heads * 256, 'rope_bf16_words': heads * 256,
            'q_gate_bf16_words': 256 * variants * 256,
            'unique_trig_bf16_words': 32 * variants * 64,
            'unique_weight_files': 10, 'unique_weight_memh_bytes': 1024 * (8 * 512 + 2 * 256) * 5,
            'norm_trace_words': heads * chain.norm.TRACE_WORDS,
            'rope_trace_words': heads * 32 * len(chain.rope.COLUMNS)}


def expected_supplemental_totals() -> dict:
    variants = len(capture.VARIANTS)
    return {'variants': variants, 'selected_phase_tokens': variants,
            'head_transactions': 2 * variants, 'matrix_fp32_columns': 512 * variants,
            'matrix_bf16_columns': 512 * variants, 'matrix_fma_flags': 512 * variants,
            'matrix_accumulator_steps': 524288 * variants,
            'projected_steps_bytes': 2097152 * variants,
            'norm_bf16_words': 512 * variants, 'rope_bf16_words': 512 * variants,
            'norm_trace_words': 2 * variants * chain.norm.TRACE_WORDS,
            'rope_trace_words': 2 * variants * 32 * len(chain.rope.COLUMNS)}


def _source_hashes(root: Path) -> dict:
    return {name: chain._sha((root / name).read_bytes()) for name in MATERIALIZER_SOURCES}


def _case_schema(columns: int) -> dict:
    return {'activation': (1024, 4), 'weight': (1024 * columns, 4),
            'norm_weight': (256, 4), 'trig': (64, 4), 'projected': (columns, 4),
            'projected_fp32': (columns, 8), 'projected_steps': (1024 * columns, 'uint32_le'),
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


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _binary_steps(path: Path, steps: np.ndarray) -> dict:
    require(isinstance(steps, np.ndarray) and steps.dtype == np.dtype('<u4')
            and steps.ndim == 3 and steps.shape[0] in (8, 16) and steps.shape[1:] == (1024, 32),
            'tile16 accumulator binary shape/dtype drift')
    np.ascontiguousarray(steps).tofile(path)
    return {'file': path.name, 'words': int(steps.size), 'encoding': 'uint32_le',
            'bytes': path.stat().st_size, 'sha256': _file_sha(path)}


def _write_shared_weight(output: Path, case: dict, weight: np.ndarray) -> dict:
    relative = 'shared_weights/' + case['role'] + '_head' + str(case['head'])
    path = output / relative / 'weight.memh'
    if path.exists():
        # The key is shared across tokens, phases and native dispatches, but
        # never permits different checkpoint operands to reuse one file.
        require(path.is_file() and not path.is_symlink(), 'shared weight is not a regular file')
        source = _read_memh(path, 4)
        require(np.array_equal(source, weight.reshape(-1)), 'shared checkpoint weight drift')
        record = {'file': path.name, 'words': int(weight.size), 'hex_digits': 4,
                  'bytes': path.stat().st_size, 'sha256': _file_sha(path)}
    else:
        path.parent.mkdir(parents=True)
        record = chain._memh(path, weight, width=4)
    return {'role': case['role'], 'head': case['head'], 'columns': case['columns'],
            'directory': relative, 'file': record,
            'k_major_bf16_sha256': chain._sha(weight.tobytes())}


def _read_memh(path: Path, digits: int) -> np.ndarray:
    raw = path.read_bytes()
    lines = raw.splitlines()
    require(raw.endswith(b'\n') and all(len(line) == digits
            and all(c in b'0123456789abcdef' for c in line) for line in lines),
            'tile16 vector encoding drift: ' + path.name)
    return np.asarray([int(line, 16) for line in lines], dtype='<u2' if digits == 4 else '<u4')


def _write_case(path: Path, activation, weight, norm_weight, trig, trace, *, shared: Path) -> dict:
    projected = trace['projected']
    columns = weight.shape[1]
    steps = projected['steps_fp32'].reshape(1024, columns // 32, 32).transpose(1, 0, 2)
    arrays = {'activation': (activation, 4), 'norm_weight': (norm_weight, 4), 'trig': (trig, 4),
              'projected': (projected['bf16'], 4), 'projected_fp32': (projected['fp32'], 8),
              'norm': (np.asarray(trace['norm']['output_bf16'], dtype='<u4') >> 16, 4),
              'rope': (trace['rope_bf16'], 4)}
    files = {name: chain._memh(path / (name + '.memh'), value, width=width)
             for name, (value, width) in arrays.items()}
    os.link(shared, path / 'weight.memh')
    require((path / 'weight.memh').samefile(shared), 'weight hardlink was not created')
    files['weight'] = {'file': 'weight.memh', 'words': int(weight.size), 'hex_digits': 4,
                       'bytes': shared.stat().st_size, 'sha256': _file_sha(shared)}
    files['projected_steps'] = _binary_steps(path / 'projected_steps.bin', steps)
    return files


def _crosscheck_c(path: Path, executables: dict, activation, weight, nw, trig, trace) -> dict:
    reference = chain._crosscheck_c(path, executables, activation, weight, nw, trig, trace)
    # The independent C output contains every accumulator in increasing-K
    # order. Retain its digest in the receipt; do not retain duplicate payloads.
    reference['matrix_output_sha256'] = _file_sha(path / 'matrix_c_outputs.bin')
    reference['norm_output_sha256'] = _file_sha(path / 'norm_c_outputs.bin')
    for name in ('matrix_c_inputs.bin', 'matrix_c_outputs.bin',
                 'norm_c_inputs.bin', 'norm_c_outputs.bin'):
        (path / name).unlink()
    return reference


def _failed_heads(cases: list) -> list:
    return [{'variant': case['variant'], 'case_id': case['case_id'], 'phase': case['phase'],
             'token': case['token'], 'role': case['role'], 'head': case['head'], 'stage': name, **value}
            for case in cases for name, value in case['native_comparisons'].items() if not value['pass']]


def _failed_commands(commands: list) -> list:
    return [{'variant': command['variant'], 'command_id': command['command_id'],
             'phase': command['phase'], 'role': command['role'], 'stage': name, **value}
            for command in commands for name, value in command['native_comparisons'].items()
            if not value['pass']]


def _selected_producers(producers) -> dict:
    # NpzFile decompression is otherwise repeated for every head of every row.
    # Cache only the nine required arrays per phase, never the full producer
    # archive or intermediate arithmetic traces for hundreds of heads.
    names = [phase + '_m128_native_' + suffix for phase, _ in PHASE_TOKENS
             for suffix in ('producer_07', 'producer_08', 'producer_16', 'producer_29',
                            'producer_17', 'producer_25', 'producer_32', 'cos', 'sin')]
    return {name: producers[name] for name in names}


def materialize(root: Path, payload0: Path, payload3: Path, payload_extra: Path, output: Path) -> dict:
    """Fresh official baseline/AVX2 execution and every Q8/K2 head in 32 selected tokens.

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
    cases, supplemental_cases, commands, shared_weights = [], [], [], {}
    for variant in capture.VARIANTS:
        directory = output if variant == 'baseline' else output / variant
        directory.mkdir(parents=True, exist_ok=True)
        native_path = output / 'official' / variant / 'native/all_bf16_producers.npz'
        capture._verify_file(native_path, official['corpora'][variant]['fresh_audit_arrays'])
        operands = {}
        with np.load(native_path, allow_pickle=False) as producers:
            require(len(producers.files) == len(set(producers.files)), 'duplicate native producer arrays')
            selected_producers = _selected_producers(producers)
            for case_id, case in enumerate(CASES + SUPPLEMENTAL_CASES):
                activation, weight, nw, trig, native_p, native_n, native_r = chain._extract_case(selected_producers, raw, case)
                trace = chain.chain_trace(activation, weight, nw, trig, role=case['role'])
                path = directory / ('case' + str(case_id))
                path.mkdir()
                reference = _crosscheck_c(path, executables, activation, weight, nw, trig, trace)
                key = (case['role'], case['head'])
                if key not in shared_weights:
                    shared_weights[key] = _write_shared_weight(output, case, weight)
                shared = shared_weights[key]
                require(shared['k_major_bf16_sha256'] == chain._sha(weight.tobytes()),
                        'shared checkpoint head weight changed')
                files = _write_case(path, activation, weight, nw, trig, trace,
                                    shared=output / shared['directory'] / 'weight.memh')
                p = np.asarray(trace['projected']['bf16'], dtype='<u2')
                n = (np.asarray(trace['norm']['output_bf16'], dtype='<u4') >> 16).astype('<u2')
                r = np.asarray(trace['rope_bf16'], dtype='<u2')
                comparisons = _native_comparisons(case['role'], p, n, r, native_p, native_n, native_r)
                operands[case_id] = {'activation': activation, 'trig': trig, 'norm_weight': nw,
                    'projected': p, 'norm': n, 'rope': r, 'native_projection': native_p,
                    'native_norm': native_n, 'native_rope': native_r}
                destination = cases if case_id < len(CASES) else supplemental_cases
                destination.append({**case, 'case_id': case_id, 'variant': variant,
                    'directory': str(path.relative_to(output)), 'files': files,
                    'shared_weight': shared['directory'] + '/weight.memh',
                    'input_producer': 'input_layernorm|cast_bf16|0',
                    'activation_sha256': chain._sha(activation.tobytes()),
                    'selected_weight_k_major_sha256': chain._sha(weight.tobytes()),
                    'norm_weight_sha256': chain._sha(nw.tobytes()), 'trig_sha256': chain._sha(trig.tobytes()),
                    'ddr_byte_offsets': tensor_offsets(case['role'], case['token'], case['head']),
                    'c_reference': reference, 'native_comparisons': comparisons,
                    'native_gate_pass': all(value['pass'] for value in comparisons.values())})
                if (case_id + 1) % 40 == 0 or case_id + 1 == len(CASES) + len(SUPPLEMENTAL_CASES):
                    print(f'tile16 {variant}: independently crosschecked {case_id + 1}/'
                          f'{len(CASES) + len(SUPPLEMENTAL_CASES)} head-token rows', flush=True)
        for command in COMMANDS:
            path = directory / ('command' + str(command['command_id']))
            path.mkdir()
            arrays, comparisons = _assemble_command(command, operands)
            files = {name: chain._memh(path / (name + '.memh'), values, width=4)
                     for name, values in arrays.items()}
            commands.append({**command, 'variant': variant, 'directory': str(path.relative_to(output)),
                'files': files, 'native_comparisons': comparisons,
                'native_gate_pass': all(value['pass'] for value in comparisons.values()) and all(cases[(0 if variant == 'baseline' else len(CASES)) + index]['native_gate_pass']
                                        for index in command['case_ids']),
                'file_tensor_origin_token': command['token_start'],
                'ddr_tensor_origin_token': 0, 'order': 'token_head_dimension',
                'trig_order': 'token_cos32_sin32', 'packed_q_order': 'token_head_content256_gate256'})
    require(_source_hashes(root) == sources, 'tile16 candidate source changed during materialization')
    require(load_payload(root, Path(payload3).resolve()) == (manifest, raw), 'payload changed during materialization')
    capture.load_materialized(root, output / 'official', trusted_manifest_sha256=official_digest)
    failed = _failed_heads(cases)
    failed_commands = _failed_commands(commands)
    supplemental_failed = _failed_heads(supplemental_cases)
    summary = {'schema_version': 1, 'status': STATUS, 'policy': POLICY, 'source_sha256': sources,
        'official_manifest_sha256': official_digest, 'model_id': official['model_id'],
        'revision': official['revision'], 'framework_revision': official['framework_revision'],
        'layer_id': 3, 'weight_sha256': weights, 'cases_per_variant': len(CASES),
        'commands_per_variant': len(COMMANDS), 'variants': list(capture.VARIANTS),
        'cases': cases, 'commands': commands, 'totals': expected_totals(),
        'supplemental_cases': supplemental_cases,
        'supplemental_cases_per_variant': len(SUPPLEMENTAL_CASES),
        'supplemental_totals': expected_supplemental_totals(),
        'supplemental_native_gate_pass': not supplemental_failed,
        'supplemental_native_failed_comparisons': supplemental_failed,
        'shared_weights': list(shared_weights.values()),
        'projected_steps_layout': 'tile32_k_lane_uint32_le',
        'weight_storage': 'hardlinks_to_unique_checkpoint_heads',
        'native_thresholds': {'max_abs': chain.MAX_ABS, 'mean_abs': chain.MEAN_ABS},
        'native_gate_pass': not failed and not failed_commands and not supplemental_failed, 'native_failed_comparisons': failed,
        'native_failed_command_comparisons': failed_commands,
        'fresh_official_executions': len(capture.VARIANTS), 'native_arrays_injected_after_matrix': False,
        'all_q8_k2_heads_covered': True, 'all_128_tokens_covered': False, 'rtl_executed': False,
        'native_full_block_gate_pass': {name: official['corpora'][name]['native_audit_gate_pass']
                                       for name in capture.VARIANTS},
        'scope': 'All Q8/K2 heads in cold tokens0..15 and carried tokens112..127 (positions240..255); '
                 'sequential FMA then Norm256 and partial64 RoPE, every Q gate unchanged; no full block claim'}
    summary_path = output / 'summary.json'
    summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
    digest = chain._sha(summary_path.read_bytes())
    verify_materialized(output, trusted_summary_sha256=digest)
    return {**summary, 'summary_sha256': digest}


def _verify_files(path: Path, records: dict, schema: dict, *, verified_weight=None) -> None:
    require(not path.is_symlink() and path.is_dir(), 'tile16 vector directory path escape')
    require(set(records) == set(schema), 'tile16 vector file inventory drift')
    expected_names = {name + ('.bin' if width == 'uint32_le' else '.memh')
                      for name, (_, width) in schema.items()}
    require(set(p.name for p in path.iterdir()) == expected_names,
            'tile16 directory file inventory drift')
    for name, (words, width) in schema.items():
        binary = width == 'uint32_le'
        file = path / (name + ('.bin' if binary else '.memh'))
        require(not file.is_symlink() and file.is_file()
                and file.resolve().is_relative_to(path.resolve()), 'tile16 vector path escape')
        if name == 'weight' and verified_weight is not None:
            shared_file, shared_record = verified_weight
            require(file.samefile(shared_file) and records[name] == shared_record,
                    'tile16 shared weight hardlink/binding drift')
            continue
        record = {'file': file.name, 'words': words,
                  **({'encoding': width} if binary else {'hex_digits': width}),
                  'bytes': file.stat().st_size, 'sha256': _file_sha(file)}
        require(records[name] == record and record['bytes'] == words * (4 if binary else width + 1),
                'tile16 vector binding drift: ' + name)
        if not binary:
            require(_read_memh(file, width).size == words, 'tile16 vector word count drift')


def _verify_shared_weights(output: Path, records: list) -> dict:
    expected = [(role, head, 512 if role == 'q' else 256)
                for role, heads in (('q', 8), ('k', 2)) for head in range(heads)]
    require(type(records) is list and len(records) == len(expected), 'shared weight inventory drift')
    names = set()
    result = {}
    for record, (role, head, columns) in zip(records, expected):
        relative = 'shared_weights/' + role + '_head' + str(head)
        require(set(record) == {'role', 'head', 'columns', 'directory', 'file', 'k_major_bf16_sha256'}
                and record['role'] == role and type(record['head']) is int and record['head'] == head
                and type(record['columns']) is int and record['columns'] == columns
                and record['directory'] == relative, 'shared weight identity drift')
        _verify_files(output / relative, {'weight': record['file']}, {'weight': (1024 * columns, 4)})
        file = output / relative / 'weight.memh'
        require(record['k_major_bf16_sha256'] == chain._sha(_read_memh(file, 4).tobytes()),
                'shared weight raw checkpoint binding drift')
        result[(role, head)] = record
        names.add(relative.split('/')[1])
    require(set(p.name for p in (output / 'shared_weights').iterdir()) == names,
            'shared weight directory inventory drift')
    return result


def _verify_case_input_bindings(path: Path, case: dict) -> None:
    require(case['input_producer'] == 'input_layernorm|cast_bf16|0',
            'tile16 input must be actual preprojection producer')
    for name in ('activation', 'norm_weight', 'trig'):
        require(case[name + '_sha256'] == chain._sha(_read_memh(path / (name + '.memh'), 4).tobytes()),
                'tile16 input raw-word binding drift: ' + name)


def _verify_command_case_links(output: Path, command: dict, cases: list) -> None:
    selected = [case for case in cases if case['variant'] == command['variant']]
    selected = [selected[i] for i in command['case_ids']]
    path = output / command['directory']
    heads = command['heads']
    for name in ('projected', 'norm', 'rope', 'activation', 'trig', 'norm_weight', 'gate'):
        if name == 'gate' and command['role'] != 'q':
            continue
        field = 'projected' if name == 'gate' else name
        rows = [_read_memh(output / case['directory'] / (field + '.memh'), 4) for case in selected]
        if name in ('activation', 'trig'):
            require(all(np.array_equal(rows[i], rows[(i // heads) * heads]) for i in range(len(rows))),
                    'tile16 per-token shared input mismatch: ' + name)
            expected = np.concatenate(rows[::heads])
        elif name == 'norm_weight':
            require(all(np.array_equal(rows[0], row) for row in rows), 'tile16 gamma differs between heads')
            expected = rows[0]
        elif name == 'gate':
            expected = np.concatenate([row[256:] for row in rows])
        else:
            expected = np.concatenate(rows)
        require(np.array_equal(_read_memh(path / (name + '.memh'), 4), expected),
                'tile16 command/case binding drift: ' + name)


def _verify_output_inventory(output: Path) -> None:
    case_names = {'case' + str(i) for i in range(len(CASES) + len(SUPPLEMENTAL_CASES))}
    command_names = {'command' + str(i) for i in range(len(COMMANDS))}
    top_names = case_names | command_names | {'summary.json', 'official', 'avx2',
                                               'shared_weights', 'c_matrix', 'c_norm', 'c_rope'}
    require(not output.is_symlink() and all(not p.is_symlink() for p in output.iterdir())
            and set(p.name for p in output.iterdir()) == top_names,
            'tile16 root file inventory drift')
    avx2 = output / 'avx2'
    require(all(not p.is_symlink() for p in avx2.iterdir())
            and set(p.name for p in avx2.iterdir()) == case_names | command_names,
            'tile16 AVX2 file inventory drift')


def _verify_comparisons(comparisons: dict, role: str, heads: int) -> None:
    sizes = {'projected_content': 256, 'norm': 256, 'rope_rotated64': 64,
             'rope_passthrough192': 192, 'rope_full256': 256}
    if role == 'q':
        sizes['projected_gate'] = 256
    require(set(comparisons) == set(sizes), 'tile16 native comparison inventory drift')
    for name, size in sizes.items():
        value = comparisons[name]
        require(set(value) == {'elements', 'bit_mismatches', 'max_abs', 'mean_abs', 'thresholds', 'pass'},
                'tile16 native comparison fields drift')
        require(type(value['elements']) is int and value['elements'] == size * heads
                and type(value['bit_mismatches']) is int and 0 <= value['bit_mismatches'] <= size * heads,
                'tile16 native comparison count drift')
        require(all(type(value[k]) in (int, float) and math.isfinite(value[k]) and value[k] >= 0
                    for k in ('max_abs', 'mean_abs')) and value['mean_abs'] <= value['max_abs'],
                'tile16 native error metric drift')
        require(value['thresholds'] == {'max_abs': chain.MAX_ABS, 'mean_abs': chain.MEAN_ABS}
                and value['pass'] is (value['max_abs'] <= chain.MAX_ABS and value['mean_abs'] <= chain.MEAN_ABS),
                'tile16 native threshold/result drift')


def _verify_cases(output: Path, rows: list, descriptors: tuple, first_case_id: int, shared_weights: dict) -> None:
    for index, case in enumerate(rows):
        descriptor = {name: case[name] for name in descriptors[0]}
        chain.validate_descriptor(descriptor)
        case_id = first_case_id + index % len(descriptors)
        variant = list(capture.VARIANTS)[index // len(descriptors)]
        relative = ('avx2/' if variant == 'avx2' else '') + 'case' + str(case_id)
        require(descriptor == descriptors[case_id - first_case_id] and case['variant'] == variant
                and type(case['case_id']) is int and case['case_id'] == case_id
                and case['directory'] == relative, 'tile16 case mapping drift')
        require(case['ddr_byte_offsets'] == tensor_offsets(case['role'], case['token'], case['head']),
                'tile16 DDR offsets drift')
        _verify_comparisons(case['native_comparisons'], case['role'], 1)
        require(case['native_gate_pass'] is all(value['pass'] for value in case['native_comparisons'].values()),
                'tile16 per-head native failure hidden')
        reference = case['c_reference']
        require(all(type(reference.get(key)) is str and len(reference[key]) == 64
                    and all(c in '0123456789abcdef' for c in reference[key])
                    for key in ('matrix_output_sha256', 'norm_output_sha256')),
                'tile16 independent C evidence digest drift')
        coverage = {key: value for key, value in reference.items()
                    if key not in ('matrix_output_sha256', 'norm_output_sha256')}
        require(coverage == {'matrix_fp32_columns': case['columns'], 'matrix_bf16_columns': case['columns'],
            'matrix_accumulator_steps': 1024 * case['columns'], 'matrix_fma_flags': case['columns'],
            'norm_trace_words': chain.norm.TRACE_WORDS, 'rope_trace_words': 32 * len(chain.rope.COLUMNS),
            'bit_mismatches': 0, 'flag_mismatches': 0, 'pass': True}, 'tile16 independent C coverage drift')
        shared = shared_weights[(case['role'], case['head'])]
        require(case['shared_weight'] == shared['directory'] + '/weight.memh'
                and case['selected_weight_k_major_sha256'] == shared['k_major_bf16_sha256'],
                'tile16 case shared checkpoint weight binding drift')
        _verify_files(output / relative, case['files'], _case_schema(case['columns']),
                      verified_weight=(output / case['shared_weight'], shared['file']))
        _verify_case_input_bindings(output / relative, case)

def verify_materialized(output: Path, *, trusted_summary_sha256: str) -> dict:
    """Revalidate the fresh receipt, binary/hex inventory, and weight hardlinks."""
    root, output = capture._location(Path(__file__).resolve().parents[2], output)
    raw = (output / 'summary.json').read_bytes()
    require(type(trusted_summary_sha256) is str and len(trusted_summary_sha256) == 64
            and chain._sha(raw) == trusted_summary_sha256, 'untrusted tensor summary digest')
    summary = json.loads(raw)
    require(type(summary['schema_version']) is int and summary['schema_version'] == 1
            and summary['policy'] == POLICY and summary['status'] == STATUS, 'tile16 summary schema/policy drift')
    require(summary['source_sha256'] == _source_hashes(root), 'tile16 source binding drift')
    require(summary['variants'] == list(capture.VARIANTS) and summary['cases_per_variant'] == len(CASES)
            and summary['commands_per_variant'] == len(COMMANDS)
            and len(summary['cases']) == len(CASES) * len(capture.VARIANTS)
            and len(summary['commands']) == len(COMMANDS) * len(capture.VARIANTS), 'tile16 case inventory drift')
    require(summary['totals'] == expected_totals()
            and type(summary['fresh_official_executions']) is int
            and summary['fresh_official_executions'] == len(capture.VARIANTS), 'tile16 count drift')
    require(summary['native_thresholds'] == {'max_abs': chain.MAX_ABS, 'mean_abs': chain.MEAN_ABS}
            and summary['native_arrays_injected_after_matrix'] is False
            and summary['all_q8_k2_heads_covered'] is True
            and summary['all_128_tokens_covered'] is False and summary['rtl_executed'] is False,
            'tile16 numerical/scope policy drift')
    official = capture.load_materialized(root, output / 'official',
                                        trusted_manifest_sha256=summary['official_manifest_sha256'])
    require(summary['native_full_block_gate_pass'] ==
            {variant: official[variant][1]['native_audit_gate_pass'] for variant in capture.VARIANTS},
            'tile16 full-block failure disclosure drift')
    require(summary['projected_steps_layout'] == 'tile32_k_lane_uint32_le'
            and summary['weight_storage'] == 'hardlinks_to_unique_checkpoint_heads',
            'tile16 evidence storage policy drift')
    _verify_output_inventory(output)
    shared_weights = _verify_shared_weights(output, summary['shared_weights'])
    _verify_cases(output, summary['cases'], CASES, 0, shared_weights)
    require(summary['supplemental_cases_per_variant'] == len(SUPPLEMENTAL_CASES)
            and len(summary['supplemental_cases']) == len(SUPPLEMENTAL_CASES) * len(capture.VARIANTS)
            and summary['supplemental_totals'] == expected_supplemental_totals(),
            'tile16 supplemental inventory/count drift')
    _verify_cases(output, summary['supplemental_cases'], SUPPLEMENTAL_CASES, len(CASES), shared_weights)
    for index, command in enumerate(summary['commands']):
        command_id = index % len(COMMANDS)
        expected = COMMANDS[command_id]
        variant = list(capture.VARIANTS)[index // len(COMMANDS)]
        relative = ('avx2/' if variant == 'avx2' else '') + 'command' + str(command_id)
        require(all(type(command[key]) is type(value) and command[key] == value for key, value in expected.items())
                and command['variant'] == variant and command['directory'] == relative,
                'tile16 owner command mapping drift')
        validate_token_range(command['token_start'], command['token_count'])
        _verify_comparisons(command['native_comparisons'], command['role'], command['heads'] * command['token_count'])
        offset = list(capture.VARIANTS).index(variant) * len(CASES)
        require(command['native_gate_pass'] is (all(value['pass'] for value in command['native_comparisons'].values())
                and all(summary['cases'][offset + i]['native_gate_pass'] for i in command['case_ids'])),
                'tile16 command per-head native failure hidden')
        require(command['file_tensor_origin_token'] == command['token_start']
                and command['ddr_tensor_origin_token'] == 0 and command['order'] == 'token_head_dimension'
                and command['trig_order'] == 'token_cos32_sin32'
                and command['packed_q_order'] == 'token_head_content256_gate256', 'tile16 output layout drift')
        _verify_files(output / relative, command['files'], _command_schema(command))
        _verify_command_case_links(output, command, summary['cases'])
    failed = _failed_heads(summary['cases'])
    failed_commands = _failed_commands(summary['commands'])
    supplemental_failed = _failed_heads(summary['supplemental_cases'])
    order = lambda item: (item['variant'], item['case_id'], item['stage'])
    command_order = lambda item: (item['variant'], item['command_id'], item['stage'])
    require(sorted(summary['native_failed_comparisons'], key=order) == sorted(failed, key=order)
            and sorted(summary['native_failed_command_comparisons'], key=command_order)
                == sorted(failed_commands, key=command_order)
            and sorted(summary['supplemental_native_failed_comparisons'], key=order)
                == sorted(supplemental_failed, key=order)
            and summary['supplemental_native_gate_pass'] is (not supplemental_failed)
            and summary['native_gate_pass'] is (not failed and not failed_commands and not supplemental_failed),
            'tile16 native failure disclosure drift')
    return summary
