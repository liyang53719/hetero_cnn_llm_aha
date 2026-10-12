"""Posthoc frozen gates for a sealed, complete two-window typed L0 execution.

This module never launches an owner, recaptures a block, or feeds native bytes
back into execution. Existing original full-block captures supply every stage.
The only reference arithmetic is the source-pinned full-shape Conv fallback,
to recover its unobserved pre-SiLU boundary and condition Conv on ACTUAL QKV
and ACTUAL prior history. M128 remains one function call with two chunks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.matrix_norm_rope_candidate import compare_native
from heteronpu.qwen35_numpy_reference import compare as compare_state
from .conv import reference as conv_reference
from .native.capture import validate_manifest, validate_tensor_record

ORDER = ('input_norm', 'qkv', 'z', 'ab', 'conv_silu', 'prep', 'chunk',
         'gated_norm', 'o', 'attention_residual', 'post_norm', 'gate', 'up',
         'silu_mul', 'down', 'output')
PHASES = ('cold128', 'carried128')
WIDTHS = dict(input_norm=1024, qkv=6144, z=2048, ab=32, conv_silu=6144,
              conv_before_silu=6144, prep=6400, chunk=2048, gated_norm=2048,
              o=1024, attention_residual=1024, post_norm=1024, gate=3584,
              up=3584, silu_mul=3584, down=1024, output=1024)
ROLES = (*ORDER, 'conv_before_silu', 'history_staging', 'state_staging')
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
FRAMEWORK_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'
GATE_SOURCES = {
    'src/heteronpu/matrix_norm_rope_candidate.py': '41a4a25575de2f1b7323582b1b79553417ce99f90a38b2ee5a54948da111e764',
    'src/heteronpu/qwen35_numpy_reference.py': '5bb02fb33def33ff30494fb0780cff4827c33db66a5181fcc3fd0660138191ea',
    'chisel/continuous_prefill/scripts/pack_host_bf16_gdn_fixture.py': '764c5040062bc153cee365b1f5ad78a54c7cdcd8ded68184791a12c48a50e1ca',
    'chisel/continuous_prefill/scripts/pack_host_bf16_gdn_core_fixture.py': '5aac60ae804840f9a32684bda84d5d7f4bbafb68bbdd70fb087ce5c62cb7a061',
    'chisel/continuous_prefill/scripts/pack_host_bf16_gdn_block_fixture.py': '2bd451cc8af952d45c3985431aa32e20a7036e42cbe7933904e4ec2fc3b84e8f',
    'chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json': '3f55253cc9aff3f7875e2764a61cfef2b695d808e2fe4938eb9a2ca78b91596d',
}
MODULES = dict(input_norm='input_layernorm.result', qkv='linear_attn.in_proj_qkv.result',
    z='linear_attn.in_proj_z.result', gated_norm='linear_attn.norm.result',
    o='linear_attn.out_proj.result', attention_residual='post_attention_layernorm.args.0',
    post_norm='post_attention_layernorm.result', gate='mlp.gate_proj.result',
    up='mlp.up_proj.result', silu_mul='mlp.down_proj.args.0', down='mlp.down_proj.result')


def require(ok, message):
    if not ok:
        raise ValueError('full comparison: ' + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_bytes(directory, filename):
    directory, filename = Path(directory), str(filename)
    require(filename not in ('', '.', '..') and Path(filename).name == filename,
            'file path escape')
    path = directory / filename
    require(not path.is_symlink() and path.is_file() and
            path.resolve().parent == directory.resolve(), 'missing file or path escape: ' + filename)
    return path.read_bytes()


def verify_record(raw, record, label):
    require(type(record) is dict and type(record.get('bytes')) is int and
            len(raw) == record['bytes'] and sha(raw) == record.get('sha256'),
            'bytes/hash mismatch: ' + label)


def filename(phase, role):
    dtype = 'fp32le' if role in ('prep', 'state_staging') else 'bf16le'
    return f'{phase}.{role}.actual.{dtype}'


def byte_extent(role, rows):
    if role == 'history_staging':
        return 6144 * 4 * 2
    if role == 'state_staging':
        return 16 * 128 * 128 * 4
    return rows * WIDTHS[role] * (4 if role == 'prep' else 2)


def verify_source_hashes(hashes, root):
    require(type(hashes) is dict and hashes, 'source identities missing')
    for name, digest in hashes.items():
        path = Path(root) / name
        require(not Path(name).is_absolute() and path.resolve().is_relative_to(Path(root).resolve()),
                'source path escape')
        require(sha(path.read_bytes()) == digest, 'source identity changed: ' + name)


def load_actual(directory, *, root=ROOT):
    """Validate the entire seal BEFORE opening any native manifest/reference."""
    directory = Path(directory)
    summary_raw = file_bytes(directory, 'summary.json')
    require(summary_raw == file_bytes(directory, 'actual_terminal.json'),
            'summary is not the sealed actual terminal')
    summary = json.loads(summary_raw)
    identity = json.loads(file_bytes(directory, 'identity.json'))
    require(summary.get('status') == 'ACTUAL_COMPLETE_UNCOMPARED' and
            summary.get('scope') == 'QWEN35_L0_COMPLETE_TYPED_SOFTWARE_COORDINATOR' and
            summary.get('identity') == identity, 'actual completion/identity seal missing')
    require(identity.get('rows') in (16, 128) and type(identity['rows']) is int, 'M16/M128 only')
    rows = identity['rows']
    require(summary.get('full_block_executed') is True and summary.get('reset_required') is False and
            summary.get('roots', {}).get('generation') == 2 and
            summary.get('response', {}).get('status') is None and
            summary['response'].get('generation') == 2, 'two successful dual-root commits required')
    require(summary.get('source_initialization') == 'raw_inputs_and_parameters_only_before_launch' and
            summary.get('carried_dependency') == 'preceding_actual_committed_history_and_fp32_state',
            'actual provenance contract missing')
    for flag in ('source_unchanged', 'fixture_unchanged', 'library_unchanged', 'vector_library_unchanged'):
        require(summary.get(flag) is True, 'unverified actual identity: ' + flag)
    final_identity = summary.get('final_identity', {})
    require(final_identity and final_identity.get('identity_read_errors') == {} and
            all(v is True for k, v in final_identity.items() if k != 'identity_read_errors'),
            'final source/input/output verification failed')
    commands = summary.get('commands', [])
    require(summary.get('terminal_count') == 32 and len(commands) == 32 and
            [(x.get('phase'), x.get('role')) for x in commands] ==
            [(phase, role) for phase in PHASES for role in ORDER], 'all 32 ordered terminals required')
    require(all(c.get('complete') is True and c.get('status', 'missing') is None and
                c.get('terminal_accepted') is True for c in commands), 'failed/missing owner terminal')
    require([c.get('owner_tag') for c in commands] == list(range(1, 33)), 'owner terminal tag order')
    verify_source_hashes(identity.get('source_sha256'), root)
    require(type(identity.get('identity_file_sha256')) is dict and identity['identity_file_sha256'],
            'ELF/receipt/fixture identities missing')
    for path, digest in identity['identity_file_sha256'].items():
        require(sha(Path(path).read_bytes()) == digest, 'actual identity file changed: ' + path)
    files = summary.get('output_files', {})
    expected = {filename(phase, role) for phase in PHASES for role in ROLES}
    require(set(files) == expected, 'complete 38-file actual output inventory required')
    actual = {}
    for phase in PHASES:
        actual[phase] = {}
        for role in ROLES:
            name = filename(phase, role)
            raw = file_bytes(directory, name)
            verify_record(raw, files[name], name)
            require(len(raw) == byte_extent(role, rows), 'actual shape mismatch: ' + name)
            actual[phase][role] = raw
    for command in commands:
        phase, role = command['phase'], command['role']
        require(command.get('output_sha256') == sha(actual[phase][role]), 'terminal output hash: ' + role)
        if role in ('conv_silu', 'chunk'):
            stage, key = ('history_staging', 'history_staging_sha256') if role == 'conv_silu' else ('state_staging', 'state_sha256')
            require(command.get(key) == sha(actual[phase][stage]) and command.get('staging_complete') is True,
                    'staging terminal hash/coverage: ' + role)
        if role == 'conv_silu':
            observation = command.get('conv_before_silu_observation', {})
            require(observation.get('complete') is True and
                    observation.get('output_sha256') == sha(actual[phase]['conv_before_silu']),
                    'pre-SiLU actual observation incomplete')
    inputs = summary.get('window_inputs')
    require(inputs == [dict(phase='cold128', cold=True, expected_generation=0,
                           history_sha256=None, state_sha256=None),
                       dict(phase='carried128', cold=False, expected_generation=1,
                           history_sha256=sha(actual['cold128']['history_staging']),
                           state_sha256=sha(actual['cold128']['state_staging']))],
            'carried invocation did not consume the preceding actual root pair')
    roots = summary['roots']
    require(roots.get('history_sha256') == sha(actual['carried128']['history_staging']) and
            roots.get('state_sha256') == sha(actual['carried128']['state_staging']) and
            all(type(roots.get(k)) is int and roots[k] > 0 for k in ('history', 'state', 'output')) and
            len({roots[k] for k in ('history', 'state', 'output')}) == 3,
            'final committed root pair/output differs from sealed actual')
    return summary, actual, sha(summary_raw)


class MissingNode(ValueError):
    """An unobserved native node is never replaced by a fabricated tensor."""


class NativeTensors:
    def __init__(self, directory, records):
        self.directory, self.records = Path(directory), records
        self.raw = {}
        for name, record in records.items():
            validate_tensor_record(record)
            raw = file_bytes(directory, record['file'])
            verify_record(raw, record, name)
            self.raw[name] = raw

    def get(self, name, shape, dtype='BF16'):
        if name not in self.records:
            raise MissingNode('missing captured native node: ' + name)
        record = self.records[name]
        require(record['shape'] == list(shape) and record['dtype'] == dtype,
                'native shape/dtype mismatch: ' + name)
        return self.raw[name]


def native_role(tensors, case, role, rows):
    """Map exact observed boundaries; only original layout changes are allowed."""
    if role in MODULES:
        shape = (rows * 16, 128) if role == 'gated_norm' else (1, rows, WIDTHS[role])
        return tensors.get(case + '.module.' + MODULES[role], shape)
    if role == 'ab':
        values = [np.frombuffer(tensors.get(case + '.module.linear_attn.in_proj_' + name + '.result',
                                           (1, rows, 16)), '<u2').reshape(rows, 16) for name in ('a', 'b')]
        return np.concatenate(values, axis=1).astype('<u2', copy=False).tobytes()
    if role == 'conv_silu':
        length = rows + (4 if case.startswith('carried') else 0)
        raw = tensors.get(case + '.causal_conv1d_fn.output', (1, 6144, length))
        return np.frombuffer(raw, '<u2').reshape(1, 6144, length)[:, :, -rows:].transpose(0, 2, 1).copy().tobytes()
    if role == 'chunk':
        return tensors.get(case + '.chunk0.output', (1, rows, 16, 128))
    if role == 'history_staging':
        return tensors.get(case + '.final_cache.conv_state', (1, 6144, 4))
    if role == 'state_staging':
        return tensors.get(case + '.final_cache.recurrent_state', (1, 16, 128, 128), 'F32')
    if role == 'output':
        return tensors.get(case + '.output', (1, rows, 1024))
    raise MissingNode('no captured equivalent packed boundary: ' + role)


def verify_native_continuity(manifest, tensors, inputs, rows):
    """Check original cache continuity and raw Conv history/QKV bytes directly."""
    cold, carried = manifest['cases']
    for index, case in enumerate((cold, carried)):
        name = case['name']
        require(name == ('cold' if index == 0 else 'carried') + str(rows), 'native case name')
        require(tensors.get(case['input'], (1, rows, 1024)) == inputs[PHASES[index]],
                'native and actual raw input differ')
        prior, final = case['prior_cache'], case['final_cache']
        require(prior.get('has_previous_state') is bool(index) and final.get('has_previous_state') is True,
                'true cold/carried cache flag mismatch')
        if index:
            for key, shape, dtype in (('conv_state', (1, 6144, 4), 'BF16'),
                                      ('recurrent_state', (1, 16, 128, 128), 'F32')):
                require(tensors.get(prior[key], shape, dtype) == tensors.get(cold['final_cache'][key], shape, dtype),
                        'pure official prior/final cache discontinuity')
        chunk = case['chunk_calls'][0]
        require(tensors.get(chunk['final_state'], (1, 16, 128, 128), 'F32') ==
                tensors.get(final['recurrent_state'], (1, 16, 128, 128), 'F32'), 'native chunk/cache final differs')
        if index:
            require(tensors.get(chunk['initial_state'], (1, 16, 128, 128), 'F32') ==
                    tensors.get(prior['recurrent_state'], (1, 16, 128, 128), 'F32'), 'native chunk/cache initial differs')
        calls = case.get('conv_calls', [])
        require(len(calls) == 1 and calls[0].get('activation') == 'silu' and
                calls[0].get('includes_prior_history') is bool(index), 'one original prefill Conv call required')
        qkv = np.frombuffer(native_role(tensors, name, 'qkv', rows), '<u2').reshape(rows, 6144).T
        full = np.concatenate((np.frombuffer(tensors.get(prior['conv_state'], (1, 6144, 4)), '<u2').reshape(6144, 4), qkv), axis=1) if index else qkv
        require(tensors.get(calls[0]['input'], (1, 6144, rows + index * 4)) == full.tobytes(),
                'native Conv input differs from its own QKV/prior history')
        require(tensors.get(final['conv_state'], (1, 6144, 4)) == qkv[:, -4:].copy().tobytes(),
                'native final raw history differs from last four QKV rows')


def verify_native_identity(manifest, *, root=ROOT):
    require(manifest.get('status') == 'CAPTURED_OFFICIAL_SOFTWARE_REFERENCE_ONLY' and
            manifest.get('official_complete_layer0_executed') is True and
            manifest.get('original_parameter_bytes_verified') is True and
            manifest.get('input_fixture_reverified') is True and
            manifest.get('revision') == MODEL_REVISION and manifest.get('framework_revision') == FRAMEWORK_REVISION,
            'original complete official capture identity missing')
    env = manifest.get('environment', {})
    require(env.get('aten_cpu_capability') == 'default' and env.get('torch_cpu_capability') == 'DEFAULT' and
            env.get('torch_threads') == 1 and env.get('torch_interop_threads') == 1 and
            env.get('autocast') is False and env.get('eval') is True and env.get('inference') is True and
            env.get('deterministic_algorithms') is True and env.get('float32_matmul_precision') == 'highest' and
            env.get('packages', {}).get('torch') == '2.10.0+cpu', 'native runtime policy drift')
    require(manifest.get('source_files') and manifest.get('runtime_files'), 'native source/runtime receipts missing')
    for group in ('source_files', 'runtime_files'):
        for name, record in manifest[group].items():
            verify_record(Path(record['path']).read_bytes(), record, group + '.' + name)
    require(manifest['source_files']['modeling']['sha256'] == conv_reference.SOURCE_SHA and
            sha((Path(root) / conv_reference.SOURCE).read_bytes()) == conv_reference.SOURCE_SHA,
            'original official model source drift')


def bf16_metric(actual, expected, *, gate='node'):
    stats = conv_reference.compare_bf16(actual, expected)
    require(gate in ('node', 'output', 'ulp'), 'unknown frozen gate')
    if gate == 'ulp':
        stats.update(thresholds={'max_bf16_ulp': 1}, passed=stats['max_bf16_ulp'] <= 1,
                     gate='ORIGINAL_SAME_ACTUAL_INPUT_CONV_SILU_1_BF16_ULP')
    else:
        original = compare_native(np.frombuffer(actual, '<u2'), np.frombuffer(expected, '<u2'))
        require(original['thresholds'] == {'max_abs': .03125, 'mean_abs': .005}, 'original node thresholds changed')
        limits = {'max_abs': .05, 'mean_abs': .01} if gate == 'output' else original['thresholds']
        stats.update(thresholds=limits, passed=stats['max_abs'] <= limits['max_abs'] and
                     stats['mean_abs'] <= limits['mean_abs'], gate='ORIGINAL_FULL_BLOCK_OUTPUT' if gate == 'output' else 'ORIGINAL_NATIVE_PER_NODE')
    stats.update(status='PASS' if stats['passed'] else 'FAIL', signed_zero_numeric_equal=True,
                 native_sha256=stats.pop('expected_sha256'))
    return stats


def state_metric(actual, expected):
    require(type(actual) is bytes and type(expected) is bytes and len(actual) == len(expected) and
            len(actual) > 0 and len(actual) % 4 == 0, 'same complete FP32 byte shape required')
    a, b = np.frombuffer(actual, '<f4'), np.frombuffer(expected, '<f4')
    metric = compare_state(a, b, atol=1e-4, rtol=1e-4)
    metric.update(elements=int(metric['elements']), actual_sha256=sha(actual), native_sha256=sha(expected),
                  bit_mismatches=int(np.count_nonzero(a.view('<u4') != b.view('<u4'))),
                  numerical_mismatches=int(np.count_nonzero(a != b)),
                  signed_zero_only_mismatches=int(np.count_nonzero((a.view('<u4') != b.view('<u4')) & (a == b))),
                  passed=metric['mismatches'] == 0, gate='ORIGINAL_EVERY_ELEMENT_FP32_STATE',
                  thresholds={'atol': 1e-4, 'rtol': 1e-4})
    metric['status'] = 'PASS' if metric['passed'] else 'FAIL'
    return metric


def missing_metric(error, actual=None):
    return dict(status='MISSING', passed=False, detail=str(error), actual_sha256=None if actual is None else sha(actual),
                native_sha256=None, thresholds=None)


def assigned_pass(checks, *, prep_unassigned=False):
    """Every assigned gate must explicitly pass; absent/None cannot pass."""
    expected = set(ORDER) | {'history_staging', 'state_staging'} if prep_unassigned else {
        'qkv', 'z', 'ab', 'end_to_end_silu', 'end_to_end_conv',
        'conv_same_actual_input', 'silu_same_actual_input'}
    require(set(checks) == expected, 'assigned gate inventory incomplete')
    if prep_unassigned:
        require(checks['prep'].get('passed') is None and checks['prep'].get('thresholds') is None,
                'no packed prep threshold was assigned')
    return all(value.get('passed') is True for name, value in checks.items() if name != 'prep')


def prep_diagnostic(actual, tensors, case, rows):
    """The capture has raw Q/K, not the packed internally normalized Q/K.

    Value, g and widened BF16 beta are observable equivalent sub-boundaries.
    Their numerical facts remain unassigned diagnostics, even when equal.
    """
    require(len(actual) == rows * 6400 * 4, 'packed prep extent')
    x = np.frombuffer(actual, '<f4').reshape(rows, 6400)
    require(np.isfinite(x).all(), 'nonfinite actual prep')
    result = dict(status='DIAGNOSTIC_UNASSIGNED', passed=None, thresholds=None,
                  actual_sha256=sha(actual), native_sha256=None, elements=int(x.size),
                  packed_native_boundary_observed=False,
                  reason='Official capture observes Q/K before internal L2 normalization; no packed InputPrep gate was frozen.',
                  captured_components={})
    for name, value, shape, dtype in (
            ('value', x[:, 4096:6144], (1, rows, 16, 128), 'BF16'),
            ('g', x[:, 6144:].reshape(rows, 16, 16)[:, :, 0], (1, rows, 16), 'F32'),
            ('beta', x[:, 6144:].reshape(rows, 16, 16)[:, :, 1], (1, rows, 16), 'BF16')):
        try:
            raw = tensors.get(case + '.chunk0.' + name, shape, dtype)
        except MissingNode as error:
            result['captured_components'][name] = dict(status='MISSING', passed=None, detail=str(error))
            continue
        expected = np.frombuffer(raw, '<f4') if dtype == 'F32' else (np.frombuffer(raw, '<u2').astype('<u4') << 16).view('<f4')
        require(np.isfinite(expected).all(), 'nonfinite official prep component')
        delta = np.abs(value.reshape(-1).astype(np.float64) - expected.astype(np.float64))
        result['captured_components'][name] = dict(elements=int(value.size), max_abs=float(delta.max()),
            mean_abs=float(delta.mean()), actual_sha256=sha(value.astype('<f4').tobytes()),
            native_sha256=sha(raw), passed=None, thresholds=None)
    return result


def captured_conv_reference(tensors, case, rows, weight_raw, *, root=ROOT):
    """Derive pre-SiLU from the exact captured [1,C,M(+4)] operator input.

    Verify ALL activated bytes against its captured output before selecting
    the last M samples. This is the original BF16 F.conv1d padding=3/group6144
    fallback; it never uses the M1 update operator or a reshaped backend.
    """
    require(os.environ.get('ATEN_CPU_CAPABILITY') == 'default',
            'set ATEN_CPU_CAPABILITY=default before importing Torch')
    import torch
    require(torch.__version__.split('+')[0] == '2.10.0', 'frozen Torch 2.10 required')
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    require(torch.backends.cpu.get_cpu_capability() in ('NO AVX', 'DEFAULT'), 'frozen DEFAULT backend required')
    length = rows + (4 if case.startswith('carried') else 0)
    input_raw = tensors.get(case + '.causal_conv1d_fn.input', (1, 6144, length))
    output_raw = tensors.get(case + '.causal_conv1d_fn.output', (1, 6144, length))
    source = (Path(root) / conv_reference.SOURCE).read_bytes()
    function = conv_reference.original_conv_functions(source, torch)['causal_conv1d_fn']
    require(len(weight_raw) == 6144 * 4 * 2, 'original Conv weight shape')
    x = torch.frombuffer(bytearray(input_raw), dtype=torch.bfloat16).reshape(1, 6144, length)
    w = torch.frombuffer(bytearray(weight_raw), dtype=torch.bfloat16).reshape(6144, 4)
    with torch.inference_mode():
        before = function(x, w, bias=None, activation=None)
        activated = function(x, w, bias=None, activation='silu')
    words = lambda value: value.contiguous().view(torch.int16).numpy().astype('<i2', copy=False).tobytes()
    require(words(activated) == output_raw, 'derived official Conv activation differs from original capture')
    require(torch.isfinite(before).all().item(), 'nonfinite derived native pre-SiLU')
    raw = words(before[:, :, -rows:].transpose(1, 2))
    return raw, dict(operator='causal_conv1d_fn', original_source_sha256=sha(source),
        input_shape=[1, 6144, length], weight_shape=[6144, 4], padding=3, groups=6144,
        input_sha256=sha(input_raw), weight_sha256=sha(weight_raw), output_sha256=sha(raw),
        all_activated_bytes_verified=True, activated_capture_sha256=sha(output_raw),
        update_operator_called=False, torch=torch.__version__, threads=torch.get_num_threads(),
        cpu_capability=torch.backends.cpu.get_cpu_capability())


def compare_run(actual_dir, native_manifest, fixture, output, *, root=ROOT):
    """Return and save compact metrics; rejected seals raise before native work.

    ``output`` is a new JSON file outside the immutable actual/native folders.
    Only ``native_conv`` evaluates reference arithmetic, after all checks.
    """
    root, actual_dir, native_manifest, fixture, output = map(Path, (root, actual_dir, native_manifest, fixture, output))
    require(not output.exists() and not output.is_symlink() and
            not output.resolve().is_relative_to(actual_dir.resolve()) and
            not output.resolve().is_relative_to(native_manifest.parent.resolve()), 'fresh independent comparison output required')
    summary, actual, seal_sha = load_actual(actual_dir, root=root)
    identity, rows = summary['identity'], summary['identity']['rows']
    verify_source_hashes(GATE_SOURCES, root)
    sources = {p: sha((root / p).read_bytes()) for p in (
        'candidates/qwen35_gdn_prefill/full_compare.py', 'candidates/qwen35_gdn_prefill/conv/reference.py',
        'candidates/qwen35_gdn_prefill/native/capture.py', conv_reference.SOURCE)}
    from .input_fixture import load_fixture, gdn
    fixture_manifest, raw_inputs = load_fixture(root, fixture)
    _, weights = gdn.load_payload(root, Path(fixture_manifest['sources']['layer0_directory']))
    input_bytes = {phase: raw_inputs[phase + '.hidden.bf16le'][:rows * 2048] for phase in PHASES}
    require(identity.get('input_sha256') == {name: sha(raw) for name, raw in input_bytes.items()} and
            identity.get('authenticated_input_sha256') == {name: sha(raw) for name, raw in raw_inputs.items()} and
            identity.get('parameter_sha256') == {name: sha(raw) for name, raw in weights.items()},
            'actual raw inputs/weights differ from original pinned fixture')
    native_raw = native_manifest.read_bytes()
    native = json.loads(native_raw)
    validate_manifest(native, native_manifest.parent)
    verify_native_identity(native, root=root)
    require(native['query_tokens'] == rows, 'actual/native M mismatch')
    require(native['fixture']['manifest']['sha256'] == sha((fixture / 'manifest.json').read_bytes()) and
            {name: item['sha256'] for name, item in native['payload']['tensors'].items()} == identity['parameter_sha256'],
            'native raw fixture/weights differ from actual')
    tensors = NativeTensors(native_manifest.parent, native['tensors'])
    verify_native_continuity(native, tensors, input_bytes, rows)
    reports, operator_reports, conv_identities = [], [], []
    for index, phase in enumerate(PHASES):
        case = native['cases'][index]['name']
        values, nodes = actual[phase], {}
        for role in (*ORDER, 'history_staging', 'state_staging'):
            if role == 'prep':
                nodes[role] = prep_diagnostic(values[role], tensors, case, rows)
                continue
            try:
                expected = native_role(tensors, case, role, rows)
                nodes[role] = state_metric(values[role], expected) if role == 'state_staging' else bf16_metric(
                    values[role], expected, gate='output' if role == 'output' else 'node')
            except MissingNode as error:
                nodes[role] = missing_metric(error, values[role])
        operators = {role: nodes[role] for role in ('qkv', 'z', 'ab')}
        operators['end_to_end_silu'] = nodes['conv_silu']
        try:
            pure, pure_identity = captured_conv_reference(tensors, case, rows,
                                                         weights['linear_attn.conv1d.weight'], root=root)
            operators['end_to_end_conv'] = bf16_metric(values['conv_before_silu'], pure)
            prior_actual = None if index == 0 else actual[PHASES[index - 1]]['history_staging']
            conditioned, conditioned_identity = conv_reference.native_conv(values['qkv'], weights['linear_attn.conv1d.weight'],
                rows, history_raw=prior_actual, root=root)
            operators['conv_same_actual_input'] = bf16_metric(values['conv_before_silu'], conditioned['conv'], gate='ulp')
            operators['silu_same_actual_input'] = bf16_metric(values['conv_silu'], conditioned['silu'], gate='ulp')
            conv_identities.append(dict(phase=phase, original_input=pure_identity, same_actual_input=conditioned_identity,
                                        official_activation_capture_verified=True))
        except MissingNode as error:
            for name in ('end_to_end_conv', 'conv_same_actual_input', 'silu_same_actual_input'):
                operators.setdefault(name, missing_metric(error))
        reports.append(dict(phase=phase, official_case=case, checks=nodes,
                            passed=assigned_pass(nodes, prep_unassigned=True)))
        operator_reports.append(dict(phase=phase, comparisons=operators,
                                     passed=assigned_pass(operators)))
    # A source/file edit while references run invalidates the result, rather
    # than giving a passing report for inputs that no longer match its seal.
    _, _, seal_after = load_actual(actual_dir, root=root)
    require(seal_after == seal_sha and native_manifest.read_bytes() == native_raw, 'actual/native seal changed during comparison')
    verify_source_hashes(GATE_SOURCES, root)
    verify_source_hashes(sources, root)
    verify_native_identity(native, root=root)
    final_fixture, final_inputs = load_fixture(root, fixture)
    _, final_weights = gdn.load_payload(root, Path(final_fixture['sources']['layer0_directory']))
    require(final_fixture == fixture_manifest and
            {name: sha(raw) for name, raw in final_inputs.items()} == identity['authenticated_input_sha256'] and
            {name: sha(raw) for name, raw in final_weights.items()} == identity['parameter_sha256'],
            'original raw inputs/weights changed during comparison')
    for name, record in native['tensors'].items():
        verify_record(file_bytes(native_manifest.parent, record['file']), record, name)
    passed = all(r['passed'] for r in reports + operator_reports)
    missing = any(v.get('status') == 'MISSING' for r in reports for v in r['checks'].values())
    result = dict(schema_version=1, scope='POSTHOC_COMPLETE_TYPED_L0_FROZEN_ORIGINAL_GATES', rows=rows,
        status='PASS' if passed else 'MISSING' if missing else 'FAIL', passed=passed,
        actual_summary_sha256=seal_sha, native_manifest_sha256=sha(native_raw),
        input_fixture_sha256=sha((fixture / 'manifest.json').read_bytes()),
        actual_directory=str(actual_dir.resolve()), native_manifest=str(native_manifest.resolve()),
        input_sha256=identity['input_sha256'], parameter_sha256=identity['parameter_sha256'],
        actual_source_sha256=identity['source_sha256'], comparison_source_sha256=sources,
        frozen_gate_source_sha256=GATE_SOURCES, native_source_files=native['source_files'],
        native_runtime_files=native['runtime_files'], native_environment=native['environment'],
        actual_identity_file_sha256=identity['identity_file_sha256'], actual_output_files=summary['output_files'],
        native_tensor_sha256={name: record['sha256'] for name, record in native['tensors'].items()},
        actual_generation=2, actual_terminal_count=32, actual_cache_continuity_verified=True,
        official_cache_continuity_verified=True, full_block_gate_pass=all(r['passed'] for r in reports),
        frozen_operator_gate_pass=all(r['passed'] for r in operator_reports),
        native_full_block_metrics=reports, frozen_operator_metrics=operator_reports,
        conv_reference_identity=conv_identities, prep_threshold_assigned=False,
        actual_rerun=False, official_block_recaptured=False, downstream_golden_injection=False,
        hardware_executed=False, rtl_executed=False, hardware_cycles=None, hardware_mac_utilization=None)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual', required=True)
    parser.add_argument('--native-manifest', required=True)
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    result = compare_run(args.actual, args.native_manifest, args.fixture, args.output)
    print(json.dumps({'status': result['status'], 'passed': result['passed'], 'rows': result['rows']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
