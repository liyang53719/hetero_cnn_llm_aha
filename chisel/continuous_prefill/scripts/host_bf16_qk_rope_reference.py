#!/usr/bin/env python3
"""Live bounded Norm256/partial64 references for the production Host CI.

The factory consumes authenticated same-invocation projection expectations.
Those values are reference inputs only, never preloaded Host intermediates.
It runs the unchanged integer and independent C Norm/RoPE implementations,
then issues a process-local authority. Saved receipts are never trust loaders.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import tempfile
import weakref

import numpy as np

import host_bf16_qkv_reference as projection
import prepare_qk_norm_rope_owner_fixture as arithmetic
from pack_host_bf16_v_fixture import ROOT, CaptureSession, capture, load_payload

require = projection.require
digest = projection.digest
file_digest = projection.file_digest
ORACLE_PINS = dict(arithmetic.ORACLE_PINS)
OPERATOR_GATE_SOURCE_PINS = {
    'scripts/run_qk_norm256_candidate.py': 'a88f99107355f4e1c85b81f952394ed94278fa4c4162a9a0817f31960fa7886b',
    'scripts/run_rope_bf16_candidate.py': '1ad7d3923ab8eb7cd0df6ed2a74b93389ec189f622b1667ee8767b9391e1a0ad',
}
WINDOWS = projection.WINDOWS
VARIANTS = projection.VARIANTS
ORIGIN = 'fresh_same_invocation_projection_bound_norm256_partial64_integer_c'
POLICY = 'norm_c1_reduce16_serial16_pwl_newton1_rope_b1_products_bf16_rne_v1'
TERMINALS = ('norm_q', 'norm_k', 'gate', 'rope_q', 'rope_k')
PARAMETERS = ('q_gamma', 'k_gamma', 'trig')
NATIVE_TERMINALS = ('native_norm_q', 'native_norm_k', 'native_rope_q_prefix', 'native_rope_k_prefix')
STAGES = {'norm_q': 'self_attn.q_norm|cast_bf16|0', 'norm_k': 'self_attn.k_norm|cast_bf16|0',
          'rope_q': 'self_attn|aten.add.Tensor|0', 'rope_k': 'self_attn|aten.add.Tensor|1'}


def _source_identity():
    paths = [Path(__file__).resolve(), Path(projection.__file__).resolve(), Path(arithmetic.__file__).resolve(),
             ROOT / 'chisel/continuous_prefill/scripts/pack_host_bf16_v_fixture.py',
             ROOT / 'src/heteronpu/qk_norm256_materialization.py', ROOT / 'src/heteronpu/pinned_block_payload.py',
             ROOT / 'src/heteronpu/weight_header_contract.py', ROOT / 'src/heteronpu/model_geometry.py']
    for name, expected in (ORACLE_PINS | OPERATOR_GATE_SOURCE_PINS).items():
        arithmetic.checked(ROOT / name, expected)
        paths.append(ROOT / name)
    require(Path(arithmetic.norm.__file__).resolve() == ROOT / 'src/heteronpu/qk_norm256_candidate.py'
            and Path(arithmetic.rope.__file__).resolve() == ROOT / 'src/heteronpu/rope_bf16_candidate.py', 'arithmetic import identity drift')
    require(all(path.is_relative_to(ROOT) and path.is_file() and not path.is_symlink() for path in paths), 'reference source path drift')
    return {str(path.relative_to(ROOT)): file_digest(path) for path in paths}


def _compile_references(output):
    # Exactly the prior helper's two unchanged C sources and compiler options.
    return arithmetic.compiler_tools(output)


def _verify_tools(tools):
    records = [tools['compiler'], tools['python'], *tools['executables'].values(), *tools['dynamic_runtime'].values()]
    require(all(projection._tool_file(item['path']) == item for item in records), 'attention reference tool/runtime drift')
    require(tools['python_version'] == sys.version and tools['numpy_version'] == np.__version__, 'attention reference Python/NumPy drift')


def _parameters(session):
    manifest, raw = load_payload(ROOT, session.payload_layer3)
    require(manifest['revision'] == arithmetic.MODEL_REVISION, 'attention checkpoint revision drift')
    gamma = {}
    for role, expected in zip(('q', 'k'), arithmetic.norm.WEIGHT_SHA256):
        value = raw['self_attn.' + role + '_norm.weight']
        require(len(value) == 512 and digest(value) == expected, 'attention gamma checkpoint pin drift')
        gamma[role + '_gamma'] = value
    return gamma


def _native_evidence(session, official):
    failures = projection._native_failures(session, official)
    reports = {}
    for variant in VARIANTS:
        path = session.directory / variant / 'native/result.json'
        capture._verify_file(path, official['corpora'][variant]['fresh_audit_report'])
        report = json.loads(path.read_text())
        selected = [row for row in report['comparisons'] if row['producer'] in STAGES.values()]
        require(len(selected) == 8 and all(type(row['pass']) is bool for row in selected), 'native stage comparison inventory drift')
        require(set(report['thresholds']['operator']) == {'max_abs', 'mean_abs'}, 'native operator threshold schema drift')
        for row in selected:
            require(row['max_abs_limit'] == report['thresholds']['operator']['max_abs']
                    and row['mean_abs_limit'] == report['thresholds']['operator']['mean_abs'], 'native per-stage threshold drift')
        reports[variant] = dict(report_sha256=file_digest(path), thresholds=report['thresholds'], original_stage_comparisons=selected)
    return failures, reports


def _load_window(session, official, variant, phase, token):
    activation, native_projection = projection._load_window(session, official, variant, phase, token)
    path = session.directory / variant / 'native/all_bf16_producers.npz'
    prefix = phase + '_m128_'
    with np.load(path, allow_pickle=False) as source:
        cosine = capture._bf16_words(source[prefix + 'native_cos'], (1, 128, 64), 'native cos')[0, token]
        sine = capture._bf16_words(source[prefix + 'native_sin'], (1, 128, 64), 'native sin')[0, token]
        require(np.array_equal(cosine[:32], cosine[32:]) and np.array_equal(sine[:32], sine[32:]), 'native trig half-pair layout drift')
        trig = (np.concatenate((cosine[:32], sine[:32])) >> 16).astype('<u2').tobytes()
        native = {}
        for role, heads, norm_index, rope_index in (('q', 8, 16, 29), ('k', 2, 25, 32)):
            native['norm_' + role] = capture._bf16_words(source[prefix + f'native_producer_{norm_index:02d}'],
                (1, 128, heads, 256), 'native norm')[0, token].copy()
            native['rope_' + role] = capture._bf16_words(source[prefix + f'native_producer_{rope_index:02d}'],
                (1, heads, 128, 64), 'native rope')[0, :, token].copy()
            for suffix, index in (('cos_product', rope_index - 2), ('sin_product', rope_index - 1)):
                native['rope_' + role + '_' + suffix] = capture._bf16_words(source[prefix + f'native_producer_{index:02d}'],
                    (1, heads, 128, 64), 'native rope product')[0, :, token].copy()
    return activation, native_projection, trig, native


def _native_diagnostic(actual, expected, original):
    result = arithmetic.diagnostic(actual, expected)
    # These are copied from the already authenticated native report, not new
    # stage limits. They remain diagnostic and cannot admit hardware execution.
    result.update(diagnostic_only=True, original_native_comparison=original,
                  original_thresholds=dict(max_abs=original['max_abs_limit'], mean_abs=original['mean_abs_limit']))
    result['acceptance_threshold'] = dict(result['original_thresholds'])
    result['within_original_thresholds'] = (result['max_abs'] <= original['max_abs_limit']
                                           and result['mean_abs'] <= original['mean_abs_limit'])
    return result


def _evaluate(projected, parameters, native, native_projection, original_rows):
    require(set(projected) == {'q', 'k', 'v'}, 'projection terminal inventory drift')
    for role, length in (('q', 8192), ('k', 1024), ('v', 1024)):
        require(type(projected[role]) is bytes and len(projected[role]) == length, 'bounded projection terminal geometry drift')
    q = np.frombuffer(projected['q'], dtype='<u2').reshape(8, 512)
    k = np.frombuffer(projected['k'], dtype='<u2').reshape(2, 256)
    trig = np.frombuffer(parameters['trig'], dtype='<u2').astype('<u4') << 16
    files = {'gate.bf16le': q[:, 256:].copy().tobytes()}
    ni, nt, ri, rt, diagnostics, original_checks = [], [], [], [], {}, {}
    for role, inputs in (('q', q[:, :256]), ('k', k)):
        weights = np.frombuffer(parameters[role + '_gamma'], dtype='<u2').astype('<u4') << 16
        values = inputs.astype('<u4') << 16
        scalars, conversions, rope_scalars, rope_conversions, normalized, rotated = ([] for _ in range(6))
        raw_native = native_projection[role].reshape(8, 512)[:, :256] if role == 'q' else native_projection[role].reshape(2, 256)
        original_norm, product_mismatches, terminal_mismatches = [], 0, 0
        for head_index, head in enumerate(values):
            scalar, conversion, trace = arithmetic.norm_execution_trace(head, weights)
            scalars.append(scalar); conversions.append(conversion); normalized.append(trace['output_bf16'])
            ni.append(np.concatenate((head, weights))); nt.append(arithmetic.norm.trace_words(trace))
            out, scalar, conversion, full, pairs = arithmetic.rope_execution_trace(trace['output_bf16'], trig)
            rope_scalars.append(scalar); rope_conversions.append(conversion); rotated.append(out)
            ri.extend(pairs); rt.extend(full)
            # Preserve the original operator tests on their original native
            # predecessors, separately from the composed expectations above.
            native_input = raw_native[head_index].astype('<u4') << 16
            _, _, conditional_norm = arithmetic.norm_execution_trace(native_input, weights)
            original_norm.append(conditional_norm['output_bf16'])
            ni.append(np.concatenate((native_input, weights))); nt.append(arithmetic.norm.trace_words(conditional_norm))
            _, _, _, conditional_rope, conditional_pairs = arithmetic.rope_execution_trace(native['norm_' + role][head_index], trig)
            ri.extend(conditional_pairs); rt.extend(conditional_rope)
            cp, sp = native['rope_' + role + '_cos_product'][head_index], native['rope_' + role + '_sin_product'][head_index]
            native_products = np.stack((cp[:32], sp[:32] ^ np.uint32(0x80000000), sp[32:], cp[32:]), axis=1)
            terminal = native['rope_' + role][head_index]
            native_terminals = np.stack((terminal[:32], terminal[32:]), axis=1)
            product_mismatches += int(np.count_nonzero(conditional_rope[:, 8:12] != native_products))
            terminal_mismatches += int(np.count_nonzero(conditional_rope[:, 20:22] != native_terminals))
        normalized, rotated = np.asarray(normalized, dtype='<u4'), np.asarray(rotated, dtype='<u4')
        require(np.array_equal(normalized[:, 64:], rotated[:, 64:]), 'partial64 tail changed')
        files['norm_' + role + '.bf16le'] = (normalized >> 16).astype('<u2').tobytes()
        files['rope_' + role + '.bf16le'] = (rotated >> 16).astype('<u2').tobytes()
        files['native_norm_' + role + '.bf16le'] = (native['norm_' + role] >> 16).astype('<u2').tobytes()
        files['native_rope_' + role + '_prefix.bf16le'] = (native['rope_' + role] >> 16).astype('<u2').tobytes()
        for stage, scalar, conversion in (('norm', scalars, conversions), ('rope', rope_scalars, rope_conversions)):
            files[stage + '_' + role + '_scalar_trace.u32le'] = np.asarray(scalar, dtype='<u4').tobytes()
            files[stage + '_' + role + '_conversion_trace.u32le'] = np.asarray(conversion, dtype='<u4').tobytes()
        diagnostics['norm_' + role] = _native_diagnostic(normalized, native['norm_' + role], original_rows['norm_' + role])
        diagnostics['norm_' + role]['projection_input_equals_native'] = bool(np.array_equal(inputs, raw_native))
        diagnostics['rope_' + role] = _native_diagnostic(rotated[:, :64], native['rope_' + role], original_rows['rope_' + role])
        diagnostics['rope_' + role]['norm_input_equals_native'] = bool(np.array_equal(normalized, native['norm_' + role]))
        original_checks['norm_' + role] = _native_diagnostic(np.asarray(original_norm, dtype='<u4'), native['norm_' + role], original_rows['norm_' + role])
        original_checks['norm_' + role].update(same_native_projected_input=True,
            diagnostic_only=False, reference_component_gate=True, rtl_executed=False,
            pass_=original_checks['norm_' + role]['within_original_thresholds'])
        original_checks['norm_' + role]['pass'] = original_checks['norm_' + role].pop('pass_')
        original_checks['rope_' + role] = dict(same_native_normalized_input=True,
            native_product_bit_mismatches=product_mismatches, native_terminal_bit_mismatches=terminal_mismatches,
            native_products_checked=inputs.shape[0] * 32 * 4, native_terminal_values_checked=inputs.shape[0] * 64,
            acceptance_criterion='bitexact four BF16 products and two BF16 terminals per pair',
            pass_=(product_mismatches == 0 and terminal_mismatches == 0))
        original_checks['rope_' + role]['pass'] = original_checks['rope_' + role].pop('pass_')
    return files, diagnostics, original_checks, (ni, np.asarray(nt, dtype='<u4'), ri, np.asarray(rt, dtype='<u4'))


@dataclass(frozen=True)
class _Authority:
    directory: Path
    capture_session: CaptureSession
    projection_session: projection.FreshProjectionReferenceSession
    receipt_bytes: bytes


_ISSUED = weakref.WeakKeyDictionary()


def _sessions(session, reference_session):
    require(type(session) is CaptureSession and session.fresh is True, 'live fresh CaptureSession required')
    require(type(reference_session) is projection.FreshProjectionReferenceSession, 'live FreshProjectionReferenceSession required')
    return reference_session.verify(session=session)


def _projection_argument(projection_reference_session, reference_session):
    require(projection_reference_session is None or reference_session is None
            or projection_reference_session is reference_session, 'conflicting projection authorities')
    return projection_reference_session if projection_reference_session is not None else reference_session


def _actual_inputs(activation, weights):
    """Accept caller's original BF16LE backing bytes or strictly typed arrays."""
    if type(activation) is bytes:
        require(len(activation) == 128 * 1024 * 2, 'activation backing byte length drift')
        activation = np.frombuffer(activation, dtype='<u2').reshape(128, 1024)
    require(type(weights) is dict and set(weights) == {'q', 'k', 'v'}, 'projection weight inventory drift')
    converted = {}
    for role, columns, _, _ in projection.ROLES:
        value = weights[role]
        if type(value) is bytes:
            require(len(value) == 1024 * columns * 2, 'weight backing byte length drift')
            value = np.frombuffer(value, dtype='<u2').reshape(1024, columns)
        converted[role] = value
    # The existing input hashing routine checks array dtype/shape/contiguity.
    projection._input_hashes(activation, converted, 0)
    return activation, converted


class FreshAttentionReferenceSession:
    """Factory-issued identity; matching saved JSON/digests cannot issue one."""
    __slots__ = ('__weakref__',)

    def __init__(self, *args, **kwargs):
        raise TypeError('use generate_attention_references with live capture/projection authorities')

    def _authority(self):
        authority = _ISSUED.get(self)
        require(authority is not None, 'unissued or expired attention reference authority')
        return authority

    @property
    def directory(self):
        return self._authority().directory

    @property
    def receipt_sha256(self):
        return digest(self._authority().receipt_bytes)

    def verify(self, *, session, projection_reference_session=None, reference_session=None):
        projection_reference_session = _projection_argument(projection_reference_session, reference_session)
        authority = self._authority()
        require(session is authority.capture_session and projection_reference_session is authority.projection_session,
                'different live capture/projection authority')
        source_projection = _sessions(session, projection_reference_session)
        official = session.verify()
        directory = authority.directory
        path = directory / 'receipt.json'
        require(directory.is_dir() and not directory.is_symlink() and path.is_file() and not path.is_symlink()
                and path.read_bytes() == authority.receipt_bytes, 'attention receipt differs from live authority')
        receipt = json.loads(authority.receipt_bytes)
        require(session.manifest_sha256 == receipt['official_manifest_sha256']
                and projection_reference_session.receipt_sha256 == receipt['projection_reference_receipt_sha256'], 'capture/projection receipt drift')
        require(source_projection['source_sha256'] == receipt['projection_source_sha256'], 'projection source identity drift')
        require(_source_identity() == receipt['source_sha256'], 'attention reference source changed')
        _verify_tools(receipt['tools'])
        failures, reports = _native_evidence(session, official)
        require(failures == receipt['native_full_block_failures'] and reports == receipt['native_stage_evidence'], 'native evidence/threshold drift')
        expected = {'receipt.json', 'norm', 'rope', *receipt['files']}
        files, directories = set(), set()
        for item in directory.rglob('*'):
            require(not item.is_symlink(), 'attention reference symlink')
            if item.is_file(): files.add(str(item.relative_to(directory)))
            elif item.is_dir(): directories.add(str(item.relative_to(directory)))
        wanted_directories = {str(parent) for relative in receipt['files'] for parent in Path(relative).parents if str(parent) != '.'}
        require(files == expected and directories == wanted_directories, 'attention reference inventory changed')
        for relative, item in receipt['files'].items():
            require(projection._file_record(directory / relative) == item, 'attention reference bytes changed: ' + relative)
        parameters = _parameters(session)
        _, weights, _ = projection._load_weights(session)
        for key, window in receipt['windows'].items():
            variant, phase, token = window['variant'], window['phase'], window['token_base']
            activation, _, trig, native = _load_window(session, official, variant, phase, token)
            selected, proof = projection_reference_session.select(activation, weights, session=session,
                variant=variant, phase=phase, token_base=token, token_count=1)
            require(projection._input_hashes(activation, weights, token) == window['input_sha256'], 'source A/W changed')
            require({role: digest(raw) for role, raw in selected.items()} == window['projection_terminal_sha256']
                    and proof['receipt_sha256'] == receipt['projection_reference_receipt_sha256'], 'projection expectations changed')
            require({name: digest(raw) for name, raw in (parameters | {'trig': trig}).items()} == window['parameter_sha256'], 'source gamma/trig changed')
            require({name: digest(value.tobytes()) for name, value in native.items()} == window['native_stage_sha256'], 'native stage bytes changed')
        return receipt

    def select(self, activation, weights, *, session, projection_reference_session=None, reference_session=None,
               variant, phase, token_base, token_count):
        projection_reference_session = _projection_argument(projection_reference_session, reference_session)
        require(type(token_base) is int and type(token_count) is int and (phase, token_base, token_count) in WINDOWS,
                'attention references only cover cold0/carried127 count1')
        activation, weights = _actual_inputs(activation, weights)
        receipt = self.verify(session=session, projection_reference_session=projection_reference_session)
        require(variant in receipt['variants'], 'uncomputed attention CPU variant')
        window = receipt['windows'][variant + '/' + phase + str(token_base)]
        require(projection._input_hashes(activation, weights, token_base) == window['input_sha256'], 'actual A/W differs from attention proof')
        terminals = {name: (self.directory / relative).read_bytes() for name, relative in window['terminals'].items()}
        parameters = {name: (self.directory / relative).read_bytes() for name, relative in window['parameters'].items()}
        native = {name: (self.directory / relative).read_bytes() for name, relative in window['native_terminals'].items()}
        return terminals | parameters | native, dict(status='GENERATED_FRESH_PROJECTION_BOUND_NORM_ROPE_INTEGER_C',
            origin=ORIGIN, generated=True, reused=False, receipt_sha256=self.receipt_sha256,
            projection_reference_receipt_sha256=receipt['projection_reference_receipt_sha256'],
            official_manifest_sha256=session.manifest_sha256, positionBase=window['positionBase'],
            input_sha256=window['input_sha256'], projection_terminal_sha256=window['projection_terminal_sha256'],
            parameter_sha256=window['parameter_sha256'], native_diagnostics=window['native_diagnostics'],
            native_operator_gate_pass=window['native_operator_gate_pass'],
            original_operator_gate_pass=window['original_operator_gate_pass'],
            original_operator_checks=window['original_operator_checks'],
            native_full_block_failures=receipt['native_full_block_failures'],
            native_stage_evidence=receipt['native_stage_evidence'][variant],
            independent_reference=window['independent_reference'], source_sha256=receipt['source_sha256'],
            expected_only=True, intermediate_preload_allowed=False, full_block_supported=False)


def generate_attention_references(session, projection_reference_session, output, *, variants=VARIANTS):
    """Generate bounded expectations once, with fresh authority binding.

    Reuses the already computed independent Matrix terminals. This factory
    never invokes capture, Torch, the Matrix oracle, JVM or RTL simulation.
    """
    projection_receipt = _sessions(session, projection_reference_session)
    require(type(variants) is tuple and variants and len(set(variants)) == len(variants)
            and all(type(v) is str and v in VARIANTS and v in projection_receipt['variants'] for v in variants), 'invalid attention variant scope')
    original = Path(output)
    require(not original.is_symlink(), 'attention reference output symlink')
    output = original.resolve()
    require(output.is_relative_to(ROOT / 'work') and output != ROOT / 'work' and not output.exists(), 'fresh output beneath ignored work required')
    official = session.verify()
    require((official['revision'], official['framework_revision']) == (arithmetic.MODEL_REVISION, arithmetic.FRAMEWORK_REVISION), 'official model/framework drift')
    sources = _source_identity()
    failures, reports = _native_evidence(session, official)
    gamma = _parameters(session)
    _, weights, _ = projection._load_weights(session)
    output.mkdir(parents=True)
    executables, tools = _compile_references(output)
    receipt = dict(schema_version=1, status='VERIFIED_BOUNDED_NORM256_PARTIAL64_INTEGER_C_EXPECTATIONS',
        scope='QKV_NORM256_PARTIAL64_EXPECTED_ONLY', origin=ORIGIN, policy=POLICY, variants=list(variants),
        model_revision=arithmetic.MODEL_REVISION, framework_revision=arithmetic.FRAMEWORK_REVISION,
        norm_policy=0xC1, rope_policy=0xB1, epsilon_word=arithmetic.norm.EPSILON,
        source_sha256=sources, oracle_source_sha256=ORACLE_PINS, tools=tools,
        original_operator_gate_source_sha256=OPERATOR_GATE_SOURCE_PINS,
        official_manifest_sha256=session.manifest_sha256,
        projection_reference_receipt_sha256=projection_reference_session.receipt_sha256,
        projection_source_sha256=projection_receipt['source_sha256'],
        native_full_block_failures=failures, native_stage_evidence=reports,
        native_full_block_gate_pass=session.evidence(official)['native_full_block_gate_pass'],
        fresh_official_executions_in_this_factory=0, additional_matrix_evaluations=0,
        full128_reference_generated=False, native_diagnostic_only=True,
        native_operator_gate_pass=True, original_operator_gate_pass=True,
        original_native_criteria=dict(norm='max_abs <= 0.03125 and mean_abs <= 0.005 on same native projected inputs',
            rope='native products and terminal bitexact on same native normalized inputs; not inferred from a different predecessor'),
        expected_only=True, intermediate_preload_allowed=False, full_block_supported=False,
        scalar_columns=arithmetic.SCALAR_COLUMNS, conversion_columns=arithmetic.CONVERSION_COLUMNS,
        scalar_opcodes=dict(Add=0, Mul=1), flags='NV,DZ,OF,UF,NX bits4..0; reject mask0x1e, retain NX',
        windows={}, files={})
    with tempfile.TemporaryDirectory(prefix='.oracle_', dir=output) as temporary:
        for variant in variants:
            for phase, token, count in WINDOWS:
                activation, native_projection, trig, native = _load_window(session, official, variant, phase, token)
                projected, proof = projection_reference_session.select(activation, weights, session=session,
                    variant=variant, phase=phase, token_base=token, token_count=count)
                require(proof['receipt_sha256'] == receipt['projection_reference_receipt_sha256'], 'projection authority changed during selection')
                parameters = gamma | {'trig': trig}
                originals = {stage: next(row for row in reports[variant]['original_stage_comparisons']
                    if row['case'] == phase + '_m128' and row['producer'] == producer) for stage, producer in STAGES.items()}
                files, diagnostics, original_checks, traces = _evaluate(projected, parameters, native, native_projection, originals)
                independent = arithmetic.crosscheck_c(executables, Path(temporary), *traces)
                independent.update(composed_expected_norm_heads=10, original_conditioned_norm_heads=10,
                                   composed_expected_rope_pairs=320, original_conditioned_rope_pairs=320)
                key = variant + '/' + phase + str(token)
                directory = output / key; directory.mkdir(parents=True)
                files.update({name + '.bf16le': raw for name, raw in parameters.items()})
                for name, raw in files.items():
                    path = directory / name; path.write_bytes(raw)
                    receipt['files'][key + '/' + name] = projection._file_record(path)
                receipt['windows'][key] = dict(variant=variant, phase=phase, token_base=token, token_count=count,
                    positionBase=token + (128 if phase == 'carried' else 0), trig_file_rows=1,
                    trig_layout='cos32 then sin32; row belongs at positionBase * 128 bytes',
                    input_sha256=projection._input_hashes(activation, weights, token),
                    projection_terminal_sha256={role: digest(raw) for role, raw in projected.items()},
                    parameter_sha256={name: digest(raw) for name, raw in parameters.items()},
                    native_stage_sha256={name: digest(value.tobytes()) for name, value in native.items()},
                    terminals={name: key + '/' + name + '.bf16le' for name in TERMINALS},
                    parameters={name: key + '/' + name + '.bf16le' for name in PARAMETERS},
                    native_terminals={name: key + '/' + name + '.bf16le' for name in NATIVE_TERMINALS},
                    native_diagnostics=diagnostics,
                    native_operator_gate_pass=all(row['within_original_thresholds'] for row in diagnostics.values()),
                    original_operator_checks=original_checks,
                    original_operator_gate_pass=all(row['pass'] for row in original_checks.values()),
                    independent_reference=independent)
                receipt['native_operator_gate_pass'] &= receipt['windows'][key]['native_operator_gate_pass']
                receipt['original_operator_gate_pass'] &= receipt['windows'][key]['original_operator_gate_pass']
    require(len(receipt['windows']) == 2 * len(variants), 'incomplete attention window inventory')
    require(_source_identity() == sources, 'attention reference source changed during arithmetic')
    _verify_tools(tools)
    require(session.verify() == official and _native_evidence(session, official) == (failures, reports), 'source/native changed during arithmetic')
    raw = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    (output / 'receipt.json').write_bytes(raw)
    reference = object.__new__(FreshAttentionReferenceSession)
    _ISSUED[reference] = _Authority(output, session, projection_reference_session, raw)
    try:
        reference.verify(session=session, projection_reference_session=projection_reference_session)
    except Exception:
        del _ISSUED[reference]
        raise
    return reference


# Short adapter name retained for the production fixture packer.
generate_reference = generate_attention_references
