"""Source-only oracle for the opt-in Matrix -> Norm256 -> partial64 RoPE chain.

The Matrix reduction is increasing-K sequential binary32 FMA, starting at +0,
with BF16 operands and one BF16-RNE conversion only after the final K. Q has
512 columns: content[256], then gate[256]. Only content enters Norm and RoPE.
The integer oracle shares no arithmetic with the independent host C reference.
Native framework arrays are comparison targets, never intermediate operands.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from .model_geometry import require
from . import qk_norm256_candidate as norm
from . import rope_bf16_candidate as rope

K_DIM = 1024
HEAD_DIM = 256
ROTARY_DIM = 64
MAX_ABS = 0.03125
MEAN_ABS = 0.005
POLICY = 'matrix_sequential_fma_fp32_bf16_rne_norm256_c1_rope_all_products_bf16_v1'
MATERIALIZER_SOURCES = (
    'src/heteronpu/matrix_norm_rope_candidate.py',
    'scripts/materialize_matrix_norm_rope_vectors.py',
    'scripts/matrix_norm_rope_reference.c',
    'scripts/qk_norm256_reference.c',
    'scripts/rope_bf16_candidate_reference.c',
    'src/heteronpu/qk_norm256_candidate.py',
    'src/heteronpu/rope_bf16_candidate.py',
    'src/heteronpu/qk_norm256_materialization.py',
)
CASES = (
    {'role': 'q', 'phase': 'cold', 'token': 0, 'head': 0, 'position': 0, 'columns': 512},
    {'role': 'k', 'phase': 'cold', 'token': 0, 'head': 0, 'position': 0, 'columns': 256},
    {'role': 'q', 'phase': 'carried', 'token': 127, 'head': 7, 'position': 255, 'columns': 512},
    {'role': 'k', 'phase': 'carried', 'token': 127, 'head': 1, 'position': 255, 'columns': 256},
)


def validate_descriptor(case: dict) -> None:
    require(isinstance(case, dict) and set(case) == set(CASES[0]), 'descriptor fields drift')
    require(type(case['role']) is str and case['role'] in ('q', 'k'), 'invalid role')
    require(type(case['phase']) is str and case['phase'] in ('cold', 'carried'), 'invalid phase')
    for key in ('token', 'head', 'position', 'columns'):
        require(type(case[key]) is int, 'descriptor integer required: ' + key)
    require(0 <= case['token'] < 128, 'invalid token')
    require(0 <= case['head'] < (8 if case['role'] == 'q' else 2), 'invalid head')
    require(case['position'] == case['token'] + (128 if case['phase'] == 'carried' else 0),
            'position/phase/token mismatch')
    require(case['columns'] == (512 if case['role'] == 'q' else 256), 'role/column mismatch')


def fma_rne(a: int, b: int, c: int) -> tuple[int, int]:
    """Exact integer binary32 a*b+c with one rounding, flags and canonical NaN.

    This is fused, not mul_rne followed by add_rne. In particular the exact
    product can exceed binary32 or underflow before cancellation by c.
    """
    for word in (a, b, c):
        rope._validate_word(word)
    invalid_product = ((rope._is_inf(a) and not (b & ~rope.SIGN)) or
                       (rope._is_inf(b) and not (a & ~rope.SIGN)))
    if any(rope._is_nan(v) for v in (a, b, c)):
        return rope.QUIET_NAN, rope.NV if invalid_product or any(rope._is_snan(v) for v in (a, b, c)) else 0
    if invalid_product:
        return rope.QUIET_NAN, rope.NV
    sign_product = (a ^ b) >> 31
    if rope._is_inf(a) or rope._is_inf(b):
        if rope._is_inf(c) and (c >> 31) != sign_product:
            return rope.QUIET_NAN, rope.NV
        return (sign_product << 31) | rope.EXPONENT, 0
    if rope._is_inf(c):
        return c, 0
    sa, ma, ea = rope._decode_finite(a)
    sb, mb, eb = rope._decode_finite(b)
    sc, mc, ec = rope._decode_finite(c)
    exponent = min(ea + eb, ec)
    product = (ma * mb) << (ea + eb - exponent)
    addend = mc << (ec - exponent)
    total = (-product if sa ^ sb else product) + (-addend if sc else addend)
    sign = int(total < 0) if total else (sa ^ sb) & sc
    return rope._round_finite(sign, abs(total), exponent)


def bf16_array(value: np.ndarray, shape: tuple[int, ...], name: str) -> np.ndarray:
    """Strict raw uint16 BF16 encoding; reject subnormal/nonfinite operands."""
    require(isinstance(value, np.ndarray) and value.dtype == np.dtype('<u2') and value.shape == shape,
            name + ': expected little-endian uint16' + str(shape))
    exponent = (value >> 7) & 255
    require(not np.any(exponent == 255), name + ': nonfinite BF16')
    require(not np.any((exponent == 0) & ((value & 0x7f) != 0)), name + ': subnormal BF16')
    return value


def projection_trace(activation: np.ndarray, weight: np.ndarray) -> dict:
    """weight[k,column], 1024 increasing K; returns every final column only."""
    bf16_array(activation, (K_DIM,), 'activation')
    require(isinstance(weight, np.ndarray) and weight.ndim == 2 and weight.shape[1] in (256, 512),
            'weight: expected K-major 1024x256/512')
    columns = weight.shape[1]
    bf16_array(weight, (K_DIM, columns), 'weight')
    # All accumulation is integer dyadic math; neither numpy.matmul nor host
    # floating-point arithmetic computes an oracle projection.
    acc = [0] * columns
    aggregate = [0] * columns
    steps = np.empty((K_DIM, columns), dtype='<u4')
    for k in range(K_DIM):
        a = int(activation[k]) << 16
        for column in range(columns):
            acc[column], flags = fma_rne(a, int(weight[k, column]) << 16, acc[column])
            aggregate[column] |= flags
        steps[k] = acc
    converted = [rope.bf16_convert(v) for v in acc]
    require(all((v & rope.EXPONENT) != rope.EXPONENT for v, _ in converted),
            'projection overflow/nonfinite boundary')
    return {'fp32': tuple(acc), 'steps_fp32': steps, 'fma_flags': tuple(aggregate),
            'bf16': tuple(v >> 16 for v, _ in converted),
            'conversion_flags': tuple(f for _, f in converted)}


def chain_trace(activation: np.ndarray, weight: np.ndarray,
                norm_weight: np.ndarray, trig: np.ndarray, *, role: str) -> dict:
    require(type(role) is str and role in ('q', 'k'), 'invalid role')
    bf16_array(weight, (K_DIM, 512 if role == 'q' else 256), 'weight')
    bf16_array(norm_weight, (HEAD_DIM,), 'norm_weight')
    bf16_array(trig, (ROTARY_DIM,), 'trig')
    projected = projection_trace(activation, weight)
    # The only Norm inputs are THIS projection's rounded content columns.
    normalized = norm.head_trace(tuple(v << 16 for v in projected['bf16'][:256]),
                                 tuple(int(v) << 16 for v in norm_weight))
    output = list(normalized['output_bf16'])
    pairs = []
    for pair in range(32):
        trace = rope.pair_trace(output[pair], output[pair + 32],
                                int(trig[pair]) << 16, int(trig[pair + 32]) << 16)
        pairs.append(trace)
        output[pair], output[pair + 32] = trace[20:22]
    require(tuple(output[64:]) == normalized['output_bf16'][64:], 'RoPE passthrough drift')
    return {'projected': projected, 'norm': normalized, 'rope_pairs': tuple(pairs),
            'rope_bf16': tuple(v >> 16 for v in output),
            'gate_bf16': projected['bf16'][256:] if role == 'q' else ()}


def compare_native(actual_bf16, expected_bf16) -> dict:
    """Unchanged operator thresholds, diagnostic only and separate from RTL."""
    a = np.asarray(actual_bf16)
    b = np.asarray(expected_bf16)
    require(a.dtype == np.dtype('<u2') and b.dtype == np.dtype('<u2')
            and a.shape == b.shape and a.size > 0, 'native comparison shape/dtype drift')
    for name, value in (('actual', a), ('native', b)):
        bf16_array(value, value.shape, name)
    af = (a.astype('<u4') << 16).view('<f4').astype(np.float64)
    bf = (b.astype('<u4') << 16).view('<f4').astype(np.float64)
    error = np.abs(af - bf)
    maximum, mean = float(error.max()), float(error.mean())
    return {'elements': int(a.size), 'bit_mismatches': int(np.count_nonzero(a != b)),
            'max_abs': maximum, 'mean_abs': mean,
            'thresholds': {'max_abs': MAX_ABS, 'mean_abs': MEAN_ABS},
            'pass': maximum <= MAX_ABS and mean <= MEAN_ABS}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_hashes(root: Path) -> dict:
    return {name: _sha((root / name).read_bytes()) for name in MATERIALIZER_SOURCES}


def _memh(path: Path, values, *, width: int) -> dict:
    value = np.asarray(values)
    require(value.dtype.kind in ('u', 'i') and value.size > 0, 'memh integer words required')
    require(width in (4, 8) and np.all(value >= 0) and np.all(value < (1 << (4 * width))),
            'memh word range')
    path.write_text(''.join(f'{int(v):0{width}x}\n' for v in value.reshape(-1)))
    raw = path.read_bytes()
    return {'file': path.name, 'words': int(value.size), 'hex_digits': width,
            'bytes': len(raw), 'sha256': _sha(raw)}


def _compile_references(root: Path, output: Path) -> dict:
    result = {}
    for name, source in (('matrix', 'matrix_norm_rope_reference.c'),
                         ('norm', 'qk_norm256_reference.c'),
                         ('rope', 'rope_bf16_candidate_reference.c')):
        executable = output / ('c_' + name)
        command = ['cc', '-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off',
                   '-frounding-math', str(root / 'scripts' / source), '-lm', '-o', str(executable)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        result[name] = executable
    return result


def _crosscheck_c(path: Path, executables: dict, activation, weight, norm_weight, trig, trace) -> dict:
    columns = weight.shape[1]
    inputs = np.concatenate((np.array([1024, columns], dtype='<u4'),
                             activation.astype('<u4') << 16, weight.reshape(-1).astype('<u4') << 16))
    inputs.tofile(path / 'matrix_c_inputs.bin')
    subprocess.run([str(executables['matrix']), str(path / 'matrix_c_inputs.bin'),
                    str(path / 'matrix_c_outputs.bin')], check=True)
    actual = np.fromfile(path / 'matrix_c_outputs.bin', dtype='<u4')
    projected = trace['projected']
    expected = np.concatenate((np.asarray(projected['fp32'], dtype='<u4'),
                               np.asarray(projected['bf16'], dtype='<u4') << 16,
                               np.asarray(projected['fma_flags'], dtype='<u4'),
                               projected['steps_fp32'].reshape(-1)))
    require(np.array_equal(actual, expected), 'independent C Matrix FMA/rounding/flags mismatch')
    norm_inputs = np.concatenate((np.asarray(projected['bf16'][:256], dtype='<u4') << 16,
                                  norm_weight.astype('<u4') << 16))
    norm_inputs.tofile(path / 'norm_c_inputs.bin')
    subprocess.run([str(executables['norm']), str(path / 'norm_c_inputs.bin'),
                    str(path / 'norm_c_outputs.bin')], check=True)
    require(np.array_equal(np.fromfile(path / 'norm_c_outputs.bin', dtype='<u4'),
                           np.asarray(norm.trace_words(trace['norm']), dtype='<u4')),
            'independent C Norm256 full trace mismatch')
    values = trace['norm']['output_bf16']
    rows = [(values[i], values[i + 32], int(trig[i]) << 16, int(trig[i + 32]) << 16) for i in range(32)]
    input_text = ''.join(' '.join(f'{v:08x}' for v in row) + '\n' for row in rows)
    completed = subprocess.run([str(executables['rope'])], input=input_text,
                               text=True, capture_output=True, check=True)
    parsed = tuple(tuple(int(v, 16) for v in line.split()) for line in completed.stdout.splitlines())
    require(parsed == trace['rope_pairs'], 'independent C RoPE full trace mismatch')
    return {'matrix_fp32_columns': columns, 'matrix_bf16_columns': columns,
            'matrix_accumulator_steps': K_DIM * columns, 'matrix_fma_flags': columns,
            'norm_trace_words': norm.TRACE_WORDS, 'rope_trace_words': 32 * len(rope.COLUMNS),
            'bit_mismatches': 0, 'flag_mismatches': 0, 'pass': True}


def _extract_case(producers, raw: dict, case: dict) -> tuple:
    from .qk_norm256_materialization import _bf16_words
    validate_descriptor(case)
    phase, role = case['phase'] + '_m128', case['role']
    token, head, columns = case['token'], case['head'], case['columns']
    def producer(index, shape):
        name = f'{phase}_native_producer_{index:02d}'
        return (_bf16_words(producers[name], shape, name) >> 16).astype('<u2')
    # This is the true q_proj/k_proj operand from the official layer's input
    # RMSNorm, not layer3_input (pre-norm) and never a captured projection.
    activation = producer(7, (1, 128, 1024))[0, token].copy()
    weight_name = f'self_attn.{role}_proj.weight'
    full = np.frombuffer(raw[weight_name], dtype='<u2').reshape(4096 if role == 'q' else 512, 1024)
    weight = np.ascontiguousarray(full[head * columns:(head + 1) * columns].T)
    norm_weight = np.frombuffer(raw[f'self_attn.{role}_norm.weight'], dtype='<u2').copy()
    trig_parts = []
    for name in ('cos', 'sin'):
        key = f'{phase}_native_{name}'
        all_words = (_bf16_words(producers[key], (1, 128, 64), key) >> 16).astype('<u2')
        values = all_words[0, token]
        require(np.array_equal(values[:32], values[32:]), 'partial64 text-axis coefficient duplication drift')
        trig_parts.append(values[:32])
    trig = np.concatenate(trig_parts)
    projected = producer(8 if role == 'q' else 17, (1, 128, 4096 if role == 'q' else 512))[0, token]
    projected = projected[head * columns:(head + 1) * columns].copy()
    normalized = producer(16 if role == 'q' else 25, (1, 128, 8 if role == 'q' else 2, 256))[0, token, head].copy()
    rotated = producer(29 if role == 'q' else 32, (1, 8 if role == 'q' else 2, 128, 64))[0, head, token].copy()
    native_rope = np.concatenate((rotated, normalized[64:]))
    return activation, weight, norm_weight, trig, projected, normalized, native_rope


def materialize(root: Path, payload0: Path, payload3: Path, payload_extra: Path, output: Path) -> dict:
    """Fresh pinned official execution -> bounded independent vectors, in work/.

    There is deliberately no saved-array/NPZ URL input or download fallback.
    Both native CPU dispatches run fresh. Existing pinned payload loaders check
    exact ranges, bytes, tensor identities and per-tensor hashes. They do not
    claim a whole-checkpoint download/hash or useful-wall numerical acceptance.
    Returned summary_sha256 is an in-process receipt, not stored in the file.
    """
    from . import qk_norm256_materialization as capture
    from .pinned_block_payload import load_payload
    root, output = capture._location(root, output, fresh=True)
    sources = _source_hashes(root)
    output.mkdir(parents=True, exist_ok=True)
    manifest, raw = load_payload(root, Path(payload3).resolve())
    weight_hashes = {name: _sha(raw[name]) for name in
                     ('self_attn.q_proj.weight', 'self_attn.k_proj.weight',
                      'self_attn.q_norm.weight', 'self_attn.k_norm.weight')}
    _, official_digest = capture.rebuild(root, payload0, payload3, payload_extra, output / 'official')
    official = json.loads((output / 'official/provenance.json').read_text())
    executables = _compile_references(root, output)
    cases = []
    for variant in capture.VARIANTS:
        directory = output if variant == 'baseline' else output / variant
        directory.mkdir(parents=True, exist_ok=True)
        native_path = output / 'official' / variant / 'native/all_bf16_producers.npz'
        capture._verify_file(native_path, official['corpora'][variant]['fresh_audit_arrays'])
        with np.load(native_path, allow_pickle=False) as producers:
            require(len(producers.files) == len(set(producers.files)), 'duplicate native producer arrays')
            for case_id, case in enumerate(CASES):
                activation, weight, norm_weight, trig, native_projection, native_norm, native_rope = _extract_case(producers, raw, case)
                trace = chain_trace(activation, weight, norm_weight, trig, role=case['role'])
                path = directory / ('case' + str(case_id))
                path.mkdir()
                c_reference = _crosscheck_c(path, executables, activation, weight, norm_weight, trig, trace)
                projected = trace['projected']
                normalized = np.asarray(trace['norm']['output_bf16'], dtype='<u4') >> 16
                # RTL accepts tile-major, then increasing K, then lanes0..31.
                steps = projected['steps_fp32'].reshape(1024, case['columns'] // 32, 32).transpose(1, 0, 2)
                arrays = {'activation': (activation, 4), 'weight': (weight, 4),
                          'norm_weight': (norm_weight, 4), 'trig': (trig, 4),
                          'projected': (projected['bf16'], 4), 'projected_fp32': (projected['fp32'], 8),
                          'projected_steps': (steps, 8), 'norm': (normalized, 4), 'rope': (trace['rope_bf16'], 4)}
                files = {name: _memh(path / (name + '.memh'), value, width=width)
                         for name, (value, width) in arrays.items()}
                actual_projection = np.asarray(projected['bf16'], dtype='<u2')
                actual_norm = normalized.astype('<u2')
                actual_rope = np.asarray(trace['rope_bf16'], dtype='<u2')
                comparisons = {name: compare_native(a, b) for name, a, b in (
                    ('projected_content', actual_projection[:256], native_projection[:256]),
                    ('norm', actual_norm, native_norm),
                    ('rope_rotated64', actual_rope[:64], native_rope[:64]),
                    ('rope_passthrough192', actual_rope[64:], native_rope[64:]),
                    ('rope_full256', actual_rope, native_rope))}
                if case['role'] == 'q':
                    comparisons['projected_gate'] = compare_native(actual_projection[256:], native_projection[256:])
                cases.append({**case, 'case_id': case_id, 'variant': variant,
                              'directory': str(path.relative_to(output)), 'files': files,
                              'input_producer': 'input_layernorm|cast_bf16|0',
                              'activation_sha256': _sha(activation.tobytes()),
                              'selected_weight_k_major_sha256': _sha(weight.tobytes()),
                              'norm_weight_sha256': _sha(norm_weight.tobytes()),
                              'trig_sha256': _sha(trig.tobytes()),
                              'c_reference': c_reference, 'native_comparisons': comparisons,
                              'native_gate_pass': all(value['pass'] for value in comparisons.values())})
    require(_source_hashes(root) == sources, 'candidate source changed during materialization')
    require(load_payload(root, Path(payload3).resolve()) == (manifest, raw), 'payload changed during materialization')
    capture.load_materialized(root, output / 'official', trusted_manifest_sha256=official_digest)
    failed = [{'variant': case['variant'], 'case_id': case['case_id'], 'stage': name, **comparison}
              for case in cases for name, comparison in case['native_comparisons'].items() if not comparison['pass']]
    summary = {'schema_version': 1, 'status': 'MATERIALIZED_INDEPENDENT_CHAIN_VECTORS', 'policy': POLICY,
               'source_sha256': sources, 'official_manifest_sha256': official_digest,
               'model_id': official['model_id'], 'revision': official['revision'],
               'framework_revision': official['framework_revision'], 'layer_id': 3,
               'weight_sha256': weight_hashes, 'cases_per_variant': 4,
               'variants': list(capture.VARIANTS), 'cases': cases,
               'native_thresholds': {'max_abs': MAX_ABS, 'mean_abs': MEAN_ABS},
               'native_gate_pass': not failed, 'native_failed_comparisons': failed,
               'fresh_official_executions': 2, 'native_arrays_injected_after_matrix': False,
               'all_heads_or_tokens_claimed': False, 'rtl_executed': False,
               'native_full_block_gate_pass': {name: official['corpora'][name]['native_audit_gate_pass']
                                              for name in capture.VARIANTS},
               'scope': '4 bounded real-prefix transactions per CPU dispatch; Matrix sequential FMA, content Norm256, partial64 RoPE; Q raw gate transported unchanged'}
    summary_path = output / 'summary.json'
    summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
    digest = _sha(summary_path.read_bytes())
    verify_materialized(output, trusted_summary_sha256=digest)
    return {**summary, 'summary_sha256': digest}


def verify_materialized(output: Path, *, trusted_summary_sha256: str) -> dict:
    """Recheck source/receipt/file bindings before consuming generated vectors.

    The digest must come from materialize() in this invocation, never from an
    untrusted CLI argument or from a self-declared saved manifest field.
    """
    from . import qk_norm256_materialization as capture
    root, output = capture._location(Path(__file__).resolve().parents[2], output)
    raw = (output / 'summary.json').read_bytes()
    require(type(trusted_summary_sha256) is str and len(trusted_summary_sha256) == 64
            and _sha(raw) == trusted_summary_sha256, 'untrusted chain summary digest')
    summary = json.loads(raw)
    require(type(summary['schema_version']) is int and summary['schema_version'] == 1
            and summary['policy'] == POLICY and summary['status'] == 'MATERIALIZED_INDEPENDENT_CHAIN_VECTORS',
            'chain summary policy/schema drift')
    require(summary['source_sha256'] == _source_hashes(root), 'candidate source binding drift')
    require(summary['variants'] == list(capture.VARIANTS) and summary['cases_per_variant'] == 4
            and len(summary['cases']) == 8, 'chain case inventory drift')
    capture.load_materialized(root, output / 'official',
                              trusted_manifest_sha256=summary['official_manifest_sha256'])
    for index, case in enumerate(summary['cases']):
        descriptor = {name: case[name] for name in CASES[0]}
        validate_descriptor(descriptor)
        expected_case = CASES[index % 4]
        variant = list(capture.VARIANTS)[index // 4]
        relative = ('avx2/' if variant == 'avx2' else '') + 'case' + str(index % 4)
        require(descriptor == expected_case and case['variant'] == variant
                and type(case['case_id']) is int and case['case_id'] == index % 4
                and case['directory'] == relative, 'chain source/case mapping drift')
        schema = {'activation': (1024, 4), 'weight': (1024 * case['columns'], 4),
                  'norm_weight': (256, 4), 'trig': (64, 4), 'projected': (case['columns'], 4),
                  'projected_fp32': (case['columns'], 8),
                  'projected_steps': (1024 * case['columns'], 8), 'norm': (256, 4), 'rope': (256, 4)}
        require(set(case['files']) == set(schema), 'chain file inventory drift')
        for name, (words, width) in schema.items():
            record = case['files'][name]
            path = (output / relative / (name + '.memh')).resolve()
            require(path.is_relative_to(output), 'chain vector path escape')
            data = path.read_bytes()
            require(record == {'file': path.name, 'words': words, 'hex_digits': width,
                               'bytes': len(data), 'sha256': _sha(data)}
                    and len(data) == words * (width + 1), 'chain vector binding drift: ' + name)
            # Strict lower-case, fixed-width, exactly one word on every line.
            lines = data.splitlines()
            require(len(lines) == words and all(len(line) == width and all(c in b'0123456789abcdef' for c in line)
                                               for line in lines), 'chain vector encoding drift: ' + name)
    return summary
