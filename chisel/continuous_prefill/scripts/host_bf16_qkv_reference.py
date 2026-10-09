#!/usr/bin/env python3
"""Bounded same-invocation QKV terminals from the established integer/C oracle.

No command-line trust loader is provided. A factory executes the existing
integer and C arithmetic once for cold0/carried127, then returns an opaque live
authority. Repacking only verifies/selects that authority; it never computes.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import weakref
import numpy as np
from pack_host_bf16_v_fixture import ROOT, CaptureSession, capture, load_payload
from heteronpu import matrix_norm_rope_candidate as integer
from heteronpu import rope_bf16_candidate as rounding
from heteronpu import qk_norm256_candidate as imported_norm
from heteronpu import model_geometry

ROLES = (('q', 4096, 512, '08'), ('k', 512, 256, '17'), ('v', 512, 256, '26'))
WINDOWS = (('cold', 0, 1), ('carried', 127, 1))
VARIANTS = ('baseline', 'avx2')
POLICY = 'existing_integer_fma_rne_and_independent_c_fmaf_k1024_terminal_bf16_rne_v1'
ORIGIN = 'fresh_same_invocation_integer_c'
REQUIRED_SCRATCH_BYTES = 32 * 1024 * 1024
# Fixed geometry bounds work. This budget is checked between synchronous heads;
# the caller's process/job deadline supplies any required hard wall-clock cap.
VARIANT_PROGRESS_BUDGET_SECONDS = 900


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def _file_record(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'missing/symlink reference file')
    return dict(bytes=path.stat().st_size, sha256=file_digest(path))


def _source_identity():
    # The numerical implementation is imported from the existing tracked core.
    expected = {
        integer: 'src/heteronpu/matrix_norm_rope_candidate.py',
        rounding: 'src/heteronpu/rope_bf16_candidate.py',
        imported_norm: 'src/heteronpu/qk_norm256_candidate.py',
        model_geometry: 'src/heteronpu/model_geometry.py',
    }
    for module, relative in expected.items():
        require(Path(module.__file__).resolve() == ROOT / relative, 'reference import origin drift')
    paths = [ROOT / relative for relative in expected.values()]
    paths += [ROOT / 'scripts/matrix_norm_rope_reference.c', Path(__file__).resolve(),
              ROOT / 'chisel/continuous_prefill/scripts/pack_host_bf16_v_fixture.py',
              ROOT / 'src/heteronpu/qk_norm256_materialization.py',
              ROOT / 'src/heteronpu/pinned_block_payload.py',
              ROOT / 'src/heteronpu/weight_header_contract.py']
    require(all(path.is_relative_to(ROOT) for path in paths), 'reference source path escape')
    return {str(path.relative_to(ROOT)): file_digest(path) for path in paths}


def _tool_file(path):
    path = Path(path).resolve()
    return dict(path=str(path), **_file_record(path))


def _compile_matrix(directory, *, source=None):
    compiler = shutil.which('cc')
    require(compiler is not None, 'existing C compiler required')
    compiler = Path(compiler).resolve()
    executable = directory / 'c_matrix'
    source = ROOT / 'scripts/matrix_norm_rope_reference.c' if source is None else Path(source).resolve()
    require(source.is_file() and not source.is_symlink() and source.is_relative_to(ROOT), 'reference C source must be repository source')
    command = [str(compiler), '-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off',
               '-frounding-math', str(source), '-lm', '-o', str(executable)]
    before = _tool_file(compiler)
    version = subprocess.run([str(compiler), '--version'], check=True, capture_output=True, text=True, timeout=15).stdout
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    require(_tool_file(compiler) == before, 'compiler changed during reference build')
    # This is our just-built trusted executable. Record actual dynamic runtime.
    linked = subprocess.run(['ldd', str(executable)], check=True, capture_output=True, text=True, timeout=15).stdout
    libraries = {}
    for line in linked.splitlines():
        for token in line.split():
            if token.startswith('/') and Path(token).is_file():
                record = _tool_file(token); libraries[record['path']] = record
    require(libraries, 'C dynamic runtime identity unavailable')
    return executable, dict(compiler=before, compiler_version=version, compile_argv=command,
        executable=_tool_file(executable), dynamic_runtime=libraries, python=_tool_file(sys.executable),
        python_version=sys.version, numpy_version=np.__version__, platform=platform.platform())


def _verify_tools(tools):
    records = [tools['compiler'], tools['executable'], tools['python'], *tools['dynamic_runtime'].values()]
    require(all(_tool_file(record['path']) == record for record in records), 'reference tool/executable/runtime drift')
    require(tools['python_version'] == sys.version and tools['numpy_version'] == np.__version__, 'reference Python/NumPy drift')


def _project_and_crosscheck(activation, weight, executable, scratch):
    """One head only, with the exact existing arithmetic and C binary formats."""
    columns = weight.shape[1]
    integer.bf16_array(activation, (1024,), 'actual A')
    integer.bf16_array(weight, (1024, columns), 'actual W')
    require(columns in (256, 512), 'bounded existing head width required')
    projected = integer.projection_trace(activation, weight)
    require(projected['steps_fp32'].shape == (1024, columns) and projected['steps_fp32'].dtype == np.dtype('<u4'), 'integer step shape drift')
    source = scratch / 'matrix_c_inputs.bin'; target = scratch / 'matrix_c_outputs.bin'
    inputs = np.concatenate((np.asarray([1024, columns], dtype='<u4'), activation.astype('<u4') << 16,
                             weight.reshape(-1).astype('<u4') << 16))
    inputs.tofile(source)
    subprocess.run([str(executable), str(source), str(target)], check=True, capture_output=True, timeout=120)
    require(target.stat().st_size == 4 * (1024 + 3) * columns, 'C terminal/trace output size drift')
    actual = np.fromfile(target, dtype='<u4')
    expected = np.concatenate((np.asarray(projected['fp32'], dtype='<u4'),
                               np.asarray(projected['bf16'], dtype='<u4') << 16,
                               np.asarray(projected['fma_flags'], dtype='<u4'), projected['steps_fp32'].reshape(-1)))
    require(np.array_equal(actual, expected), 'independent integer/C FP32/BF16/FMA flag/step mismatch')
    receipt = dict(columns=columns, k=1024, matrix_accumulator_steps=1024 * columns,
        matrix_fp32_columns=columns, matrix_bf16_columns=columns, matrix_fma_flags=columns,
        bit_mismatches=0, flag_mismatches=0, pass_=True,
        c_input_sha256=file_digest(source), c_output_sha256=file_digest(target),
        integer_step_sha256=digest(projected['steps_fp32'].tobytes()),
        c_step_sha256=digest(actual[3 * columns:].tobytes()),
        bf16_conversion_flags_independently_checked=False)
    receipt['pass'] = receipt.pop('pass_')
    result = {key: np.asarray(projected[name], dtype=dtype).tobytes()
              for key, name, dtype in (('fp32', 'fp32', '<u4'), ('bf16', 'bf16', '<u2'), ('fma_flags', 'fma_flags', '<u4'))}
    # Never retain a whole-program accumulator corpus. Each head's scratch goes.
    source.unlink(); target.unlink()
    return result, receipt


def _load_weights(session):
    manifest, raw = load_payload(ROOT, session.payload_layer3)
    weights = {role: np.ascontiguousarray(np.frombuffer(raw['self_attn.' + role + '_proj.weight'], dtype='<u2').reshape(n, 1024).T)
               for role, n, _, _ in ROLES}
    hashes = {role: digest(raw['self_attn.' + role + '_proj.weight']) for role, _, _, _ in ROLES}
    return manifest, weights, hashes


def _load_window(session, official, variant, phase, token):
    path = session.directory / variant / 'native/all_bf16_producers.npz'
    capture._verify_file(path, official['corpora'][variant]['fresh_audit_arrays'])
    prefix = phase + '_m128_native_producer_'
    with np.load(path, allow_pickle=False) as producers:
        require(len(producers.files) == len(set(producers.files)), 'duplicate source arrays')
        activation = (capture._bf16_words(producers[prefix + '07'], (1, 128, 1024), prefix + '07')[0] >> 16).astype('<u2')
        native = {role: (capture._bf16_words(producers[prefix + index], (1, 128, n), prefix + index)[0, token] >> 16).astype('<u2')
                  for role, n, _, index in ROLES}
    return activation, native


def _input_hashes(activation, weights, token):
    integer.bf16_array(activation, (128, 1024), 'full A')
    for role, n, _, _ in ROLES:
        integer.bf16_array(weights[role], (1024, n), 'full W_' + role)
    return dict(activation_tensor=digest(activation.tobytes()), activation_window=digest(activation[token].tobytes()),
                weight_tensor={role: digest(weights[role].tobytes()) for role, _, _, _ in ROLES})


def _native_failures(session, official):
    result = {}
    for variant in VARIANTS:
        path = session.directory / variant / 'native/result.json'
        capture._verify_file(path, official['corpora'][variant]['fresh_audit_report'])
        report = json.loads(path.read_text())
        result[variant] = {key: report[key] for key in ('status', 'gate_pass', 'failed_producers')}
        result[variant]['failed_softmax_invariants'] = [item for item in report.get('softmax_invariants', []) if not item['pass']]
        result[variant]['report_sha256'] = file_digest(path)
    return result


@dataclass(frozen=True)
class _Authority:
    directory: Path
    capture_session: CaptureSession
    receipt_bytes: bytes


_ISSUED = weakref.WeakKeyDictionary()


class FreshProjectionReferenceSession:
    """Opaque live factory result. A saved path/digest cannot construct one."""
    __slots__ = ('__weakref__',)

    def __init__(self, *args, **kwargs):
        raise TypeError('use the in-process independent reference generation factory')

    def _authority(self):
        authority = _ISSUED.get(self)
        require(authority is not None, 'unissued or expired independent reference authority')
        return authority

    @property
    def directory(self):
        return self._authority().directory

    @property
    def receipt_sha256(self):
        return digest(self._authority().receipt_bytes)

    def verify(self, *, session):
        authority = self._authority()
        require(type(session) is CaptureSession and session is authority.capture_session, 'different live CaptureSession authority')
        official = session.verify()
        directory = authority.directory
        require(not directory.is_symlink() and directory.is_dir(), 'reference directory changed')
        path = directory / 'receipt.json'
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == authority.receipt_bytes, 'reference receipt differs from live authority')
        receipt = json.loads(authority.receipt_bytes)
        require(session.manifest_sha256 == receipt['official_manifest_sha256'], 'capture digest changed')
        require(_source_identity() == receipt['source_sha256'], 'reference source changed')
        _verify_tools(receipt['tools'])
        require(_native_failures(session, official) == receipt['native_full_block_failures'], 'native audit evidence changed')
        expected = {'receipt.json', 'c_matrix', *receipt['files']}
        files, directories = set(), set()
        for item in directory.rglob('*'):
            require(not item.is_symlink(), 'reference symlink')
            if item.is_file(): files.add(str(item.relative_to(directory)))
            elif item.is_dir(): directories.add(str(item.relative_to(directory)))
        expected_directories = {str(parent) for relative in receipt['files'] for parent in Path(relative).parents if str(parent) != '.'}
        require(files == expected, 'reference file inventory changed')
        require(directories == expected_directories, 'reference directory inventory changed')
        for relative, record in receipt['files'].items():
            require(_file_record(directory / relative) == record, 'terminal bytes changed: ' + relative)
        return receipt

    def select(self, activation, weights, *, session, variant, phase, token_base, token_count):
        require(type(token_base) is int and type(token_count) is int and (phase, token_base, token_count) in WINDOWS,
                'fresh independent references only cover cold0/carried127 count1')
        receipt = self.verify(session=session)
        require(variant in receipt['variants'], 'uncomputed CPU variant')
        key = variant + '/' + phase + str(token_base)
        row = receipt['windows'][key]
        require(_input_hashes(activation, weights, token_base) == row['input_sha256'], 'actual activation/weight differs from independent proof')
        result = {role: (self.directory / row['terminals'][role]['bf16']).read_bytes() for role, _, _, _ in ROLES}
        return result, dict(status='GENERATED_FRESH_SAME_INVOCATION_INTEGER_AND_C_TERMINALS', origin=ORIGIN,
            generated=True, reused=False, receipt_sha256=self.receipt_sha256,
            official_manifest_sha256=session.manifest_sha256, selected_heads=12,
            full128_reference_generated=False, frozen_accumulator_traces_loaded=False,
            bounded_head_accumulators_computed=True, maximum_head_accumulator_bytes=2097152,
            source_sha256=receipt['source_sha256'])


def independent_admitted(admission):
    """Read only an admission returned by the source verifier, never a manifest."""
    proof = admission['independent_reference']
    if proof.get('reused') is True:
        return True
    return (proof.get('origin') == ORIGIN and proof.get('generated') is True and
            admission.get('fresh_reference_authority_verified') is True)


def generate_projection_references(session, output, *, variants=VARIANTS):
    """Execute once; return authority only after all bounded checks pass.

    No NPZ/weight/reference/digest override, no M16/full128 option, no dedup by
    assumed backend identity. Baseline and AVX2 each select exactly two windows.
    """
    require(type(session) is CaptureSession, 'live CaptureSession required')
    require(type(variants) is tuple and variants and len(set(variants)) == len(variants) and
            all(type(v) is str and v in VARIANTS for v in variants), 'invalid independent variant scope')
    original = Path(output)
    require(not original.is_symlink(), 'reference output symlink')
    output = original.resolve()
    require(output.is_relative_to(ROOT / 'work') and output != ROOT / 'work' and not output.exists(), 'fresh output beneath ignored work required')
    require(shutil.disk_usage(output.parent).free >= REQUIRED_SCRATCH_BYTES, 'insufficient bounded reference scratch space')
    official = session.verify(); sources = _source_identity(); failures = _native_failures(session, official)
    manifest, weights, raw_weight_hashes = _load_weights(session)
    output.mkdir(parents=True)
    executable, tools = _compile_matrix(output)
    receipt = dict(schema_version=1, status='VERIFIED_BOUNDED_INTEGER_C_QKV_TERMINALS', origin=ORIGIN,
        scope='PROJECTION_ONLY', policy=POLICY, variants=list(variants), windows={}, files={}, heads=[],
        official_manifest_sha256=session.manifest_sha256, source_sha256=sources, tools=tools,
        source_weight_sha256=raw_weight_hashes, model_revision=manifest['revision'],
        native_full_block_failures=failures, native_full_block_gate_pass=session.evidence(official)['native_full_block_gate_pass'],
        native_operator_gate_pass=True, native_thresholds={'max_abs': .03125, 'mean_abs': .005},
        norm_supported=False, rope_supported=False, full_block_supported=False,
        maximum_head_accumulator_bytes=2097152, persistent_accumulator_traces=False,
        full128_reference_generated=False, cross_variant_input_identity_assumed=False)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='.head_', dir=output) as temporary:
        scratch = Path(temporary)
        for variant in variants:
            variant_start = time.monotonic()
            for phase, token, count in WINDOWS:
                activation, native = _load_window(session, official, variant, phase, token)
                key = variant + '/' + phase + str(token)
                destination = output / key; destination.mkdir(parents=True)
                window = dict(variant=variant, phase=phase, token_base=token, token_count=count,
                              input_sha256=_input_hashes(activation, weights, token), terminals={}, native={})
                for role, n, width, _ in ROLES:
                    values = {name: [] for name in ('fp32', 'bf16', 'fma_flags')}
                    for head in range(n // width):
                        require(time.monotonic() - variant_start < VARIANT_PROGRESS_BUDGET_SECONDS, 'reference progress budget exceeded; no weaker fallback')
                        selected = np.ascontiguousarray(weights[role][:, head * width:(head + 1) * width])
                        head_start = time.monotonic()
                        result, checked = _project_and_crosscheck(activation[token], selected, executable, scratch)
                        require(checked['pass'] is True and checked['bit_mismatches'] == checked['flag_mismatches'] == 0,
                                'independent head did not pass')
                        for name in values: values[name].append(result[name])
                        receipt['heads'].append(dict(variant=variant, phase=phase, token=token, role=role, head=head,
                            activation_sha256=digest(activation[token].tobytes()), selected_weight_k_major_sha256=digest(selected.tobytes()),
                            elapsed_seconds=time.monotonic() - head_start, c_reference=checked))
                    window['terminals'][role] = {}
                    for name, parts in values.items():
                        suffix = 'bf16le' if name == 'bf16' else 'u32le'
                        relative = key + '/' + role + '_' + name + '.' + suffix
                        path = output / relative; path.write_bytes(b''.join(parts))
                        expected_size = n * (2 if name == 'bf16' else 4)
                        require(path.stat().st_size == expected_size, 'assembled terminal width drift')
                        receipt['files'][relative] = _file_record(path); window['terminals'][role][name] = relative
                    actual = np.frombuffer((output / window['terminals'][role]['bf16']).read_bytes(), dtype='<u2')
                    if role == 'q':
                        a, b = actual.reshape(8, 512), native[role].reshape(8, 512)
                        window['native']['q_content'] = integer.compare_native(a[:, :256].copy(), b[:, :256].copy())
                        window['native']['q_gate'] = integer.compare_native(a[:, 256:].copy(), b[:, 256:].copy())
                    else: window['native'][role] = integer.compare_native(actual, native[role])
                receipt['native_operator_gate_pass'] &= all(row['pass'] for row in window['native'].values())
                receipt['windows'][key] = window
            require(time.monotonic() - variant_start < VARIANT_PROGRESS_BUDGET_SECONDS, 'reference progress budget exceeded; no weaker fallback')
    require(len(receipt['heads']) == 24 * len(variants) and len(receipt['windows']) == 2 * len(variants), 'incomplete bounded reference inventory')
    receipt['head_jobs'] = len(receipt['heads'])
    receipt['matrix_accumulator_steps'] = sum(head['c_reference']['matrix_accumulator_steps'] for head in receipt['heads'])
    require(receipt['matrix_accumulator_steps'] == 10485760 * len(variants), 'independent FMA coverage drift')
    require(_source_identity() == sources, 'reference source changed during arithmetic')
    _verify_tools(tools)
    require(session.verify() == official and _native_failures(session, official) == failures, 'capture/native evidence changed during arithmetic')
    _, final_weights, final_raw_hashes = _load_weights(session)
    require(final_raw_hashes == raw_weight_hashes and all(np.array_equal(final_weights[role], weights[role]) for role, _, _, _ in ROLES), 'weight changed during arithmetic')
    receipt['elapsed_seconds'] = time.monotonic() - started
    raw = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
    (output / 'receipt.json').write_bytes(raw)
    reference = object.__new__(FreshProjectionReferenceSession)
    _ISSUED[reference] = _Authority(output, session, raw)
    try:
        reference.verify(session=session)
    except Exception:
        del _ISSUED[reference]
        raise
    return reference
