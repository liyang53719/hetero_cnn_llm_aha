#!/usr/bin/env python3
"""Prepare bounded owner-only vectors from authenticated actual Host Q/K/V.

Reuses exactly cold0 and carried127 of the retained production Host run. No
Torch, capture, Matrix, JVM, Verilator, candidate RTL or full Host execution is
started. The immutable Python arithmetic and independent C references are
cross-checked node for node. This is fixture preparation, never hardware or
native-framework acceptance. All generated payloads belong in ignored work/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu import qk_norm256_candidate as norm
from heteronpu import qk_norm256_materialization as capture
from heteronpu import rope_bf16_candidate as rope
from heteronpu.model_geometry import require
from heteronpu.pinned_block_payload import load_payload

BUILD = ROOT / 'work/host_qkv_projection_build_20261009T0146Z'
FIXTURE = ROOT / 'work/host_qkv_projection_frozen_6ie4nawh'
OFFICIAL = ROOT / 'work/matrix_tile16_final/vectors/official'
OFFICIAL_SHA = '21eb0f6f3f59b3b1a33650a07692084eabe69a0d04cec60036a434357b2c1b02'
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
FRAMEWORK_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'
BUILD_READY_SHA = 'cda38bce8b9cbc0046e6002f687f97a375e3c0d667ebf34f6036fd02b85c6240'
SOURCE_MANIFEST_SHA = '73fbc1871dadffa07c9f085502c9479e7345b7a0ab558d69620c3add52f5b6e2'
HISTORICAL_COMMITS = ('78e60a5ea661b295d1e1e04669a9d0c7cc52cb0b',
                      'bd332a6d1e10442d7de975a27aa1a65a730126c6')
CASES = {
    'cold0': ('cold', 0, 0, '89d2d755736b6e569f122d7fc157edc5297512415421d4cb5a3bace6a4167a9b'),
    'carried127': ('carried', 127, 255, '86a4a3c3a3c56e8f9aed92a67e5502b93d9cdbf64af1f9c3bec05411a602c472'),
}
ORACLE_PINS = {
    'src/heteronpu/qk_norm256_candidate.py': '1307cfd77b105fea758e0e434caab35db908739cc8bdfa0c3857306820532f06',
    'src/heteronpu/rope_bf16_candidate.py': 'fa647411e2c9f33c58c0b8c62d14063ebe249b199a8fcbc2c0d2cc645ff10bfd',
    'scripts/qk_norm256_reference.c': '79db3d6fad3a43d2e1cde22702c3a0aa4237b1b9bc157bf286eeed3fabd411ab',
    'scripts/rope_bf16_candidate_reference.c': '045f69dcddafcfd834552009adf03734b39af8f79c7ec331347fa178e53946e2',
}
NORM_OPS_PER_HEAD = 1290
SCALAR_COLUMNS = ['op', 'a', 'b', 'result', 'primitive_flags']
CONVERSION_COLUMNS = ['input_fp32', 'bf16_widened', 'conversion_flags']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked(path, expected):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'missing/symlink evidence: ' + str(path))
    require(file_sha(path) == expected, 'evidence hash drift: ' + str(path))
    return path


def record(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=file_sha(path))


def historical_sources():
    """Verify every original build-source byte against its pinned manifest.

    Current files may legitimately have changed since the retained run. A git
    blob or frozen override is accepted only when its bytes match the original
    build's exact SHA256, never merely because a commit/path has the right name.
    """
    checked(BUILD / 'sources.sha256.json', SOURCE_MANIFEST_SHA)
    sources = json.loads((BUILD / 'sources.sha256.json').read_text())
    origins = {}
    for name, digest in sources.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'source path escape')
        for location in (ROOT / name, BUILD / 'frozen_source_overrides' / name):
            if location.is_file() and not location.is_symlink() and file_sha(location) == digest:
                origins[name] = dict(sha256=digest, verified_from=str(location.relative_to(ROOT)))
                break
        else:
            for commit in HISTORICAL_COMMITS:
                result = subprocess.run(['git', 'show', commit + ':' + name], cwd=ROOT, capture_output=True, timeout=10)
                if result.returncode == 0 and sha(result.stdout) == digest:
                    origins[name] = dict(sha256=digest, verified_from='git:' + commit + ':' + name)
                    break
            else:
                raise ValueError('original build source cannot be recovered: ' + name)
    return origins


def verify_host_sources():
    ready = json.loads(checked(BUILD / 'build_ready.json', BUILD_READY_SHA).read_text())
    require(ready['source_manifest_sha256'] == SOURCE_MANIFEST_SHA, 'build source pin drift')
    checked(BUILD / 'obj/VHostBlockTop', ready['binary_sha256'])
    checked(BUILD / 'generated/HostBlockTop.sv', ready['rtl_sha256'])
    for tool in ready['actual_verilator'].values():
        checked(tool['path'], tool['sha256'])
    hardfloat = BUILD / 'hardfloat.sha256.json'
    checked(hardfloat, '27d18303cad34f031dad8f5889d3e0c8ea538ac5ec037cacc00b2278dce022cf')
    for name, digest in json.loads(hardfloat.read_text()).items():
        checked(Path(ready['hardfloat_source']) / name, digest)
    return dict(build_ready=record(BUILD / 'build_ready.json'),
                executable=record(BUILD / 'obj/VHostBlockTop'), rtl=record(BUILD / 'generated/HostBlockTop.sv'),
                source_manifest=record(BUILD / 'sources.sha256.json'), sources=historical_sources(),
                actual_verilator=ready['actual_verilator'], hardfloat_manifest=record(hardfloat),
                source_base_commit=ready['source_base_commit'])


def verify_host_window(name):
    phase, token, _, digest = CASES[name]
    report_path = checked(BUILD / (name + '_pass.result.json'), digest)
    report = json.loads(report_path.read_text())
    require(report['status'] == 'PASS_PRODUCTION_HOST_QKV_CASE'
            and report['actual_dut_identity_verified'] is True
            and report['source_immutability_verified'] is True
            and report['numerical_acceptance_eligible'] is True, 'original Host pass not authenticated')
    require(report['build_ready_sha256'] == BUILD_READY_SHA and report['scope'] == 'PROJECTION_ONLY', 'Host scope drift')
    ready = json.loads((BUILD / 'build_ready.json').read_text())
    require(all(report[k] == ready[k] for k in ('binary_sha256', 'rtl_sha256')), 'Host executable binding drift')
    require(len(report['runs']) == 1, 'unexpected Host run count')
    run = report['runs'][0]
    require(run['status'] == 0 and run['successful_commands'] == 3 and run['independent_terminal_checked'] is True,
            'incomplete original Host commands')
    checked(BUILD / (name + '_pass.log'), report['log_sha256'])
    directory = BUILD / (name + '_pass')
    checked(directory / 'ddr_after.bin', run['ddr_after_sha256'])
    for filename, expected in run['writable_snapshot_sha256'].items():
        checked(directory / filename, expected)
    fixture = FIXTURE / name
    manifest = json.loads(checked(fixture / 'manifest.json', report['fixture_sha256']).read_text())
    require((manifest['phase'], manifest['token_base'], manifest['token_count'], manifest['variant'])
            == (phase, token, 1, 'baseline'), 'Host window drift')
    require((manifest['model_revision'], manifest['framework_revision']) == (MODEL_REVISION, FRAMEWORK_REVISION), 'Host revision drift')
    require(manifest['official_manifest_sha256'] == OFFICIAL_SHA, 'Host capture binding drift')
    for filename, info in manifest['files'].items():
        require(Path(filename).name == filename, 'fixture file path escape')
        path = checked(fixture / filename, info['sha256'])
        require(path.stat().st_size == info['bytes'], 'fixture file length drift')
    actual_inputs = dict(activation_tensor=file_sha(fixture / 'activation.bf16le'),
                        activation_window=sha((fixture / 'activation.bf16le').read_bytes()[token * 2048:(token + 1) * 2048]),
                        weight_tensor={role: file_sha(fixture / ('weight_' + role + '.bf16le')) for role in 'qkv'},
                        command=file_sha(fixture / 'host_commands.bin'), descriptors=file_sha(fixture / 'host_descriptors.bin'),
                        launch=file_sha(fixture / 'launch.txt'))
    require(actual_inputs == report['input_sha256'] == manifest['input_sha256'], 'Host input binding drift')
    actual = {}
    for role, elements in zip('qkv', (4096, 512, 512)):
        path = checked(directory / ('actual_' + role + '.bf16le'), run['actual_sha256'][role])
        reference = checked(directory / ('reference_' + role + '.bf16le'), run['reference_sha256'][role])
        require(path.stat().st_size == 2 * elements and path.read_bytes() == reference.read_bytes()
                == (fixture / ('independent_' + role + '.bf16le')).read_bytes(), 'actual/independent projection mismatch')
        actual[role] = np.fromfile(path, dtype='<u2')
    return actual, report, dict(report=record(report_path), fixture_manifest=record(fixture / 'manifest.json'),
                               input_sha256=actual_inputs, source_admission=report['source_admission'])


def norm_execution_trace(inputs, weights):
    """Reorder frozen trace fields into the physical chunked Scalar schedule."""
    inputs, weights = tuple(map(int, inputs)), tuple(map(int, weights))
    trace = norm.head_trace(inputs, weights)
    rows = []
    def emit(op, a, b, result, flags):
        rows.append((op, a, b, result, flags))
    for chunk in range(16):
        for lane in range(chunk * 16, chunk * 16 + 16):
            emit(1, inputs[lane], inputs[lane], trace['squares'][lane], trace['square_flags'][lane])
        level = list(trace['squares'][chunk * 16:chunk * 16 + 16])
        index = chunk * 15
        while len(level) > 1:
            following = []
            for lane in range(0, len(level), 2):
                result = trace['tree'][index]
                emit(0, level[lane], level[lane + 1], result, trace['tree_flags'][index])
                following.append(result)
                index += 1
            level = following
        emit(0, trace['running'][chunk - 1] if chunk else 0, level[0], trace['running'][chunk], trace['running_flags'][chunk])
    emit(1, trace['running'][-1], 0x3B800000, trace['mean'], trace['mean_flags'])
    emit(0, trace['mean'], norm.EPSILON, trace['mean_eps'], trace['mean_eps_flags'])
    r, n = trace['rsqrt_values'], trace['rsqrt_norm']
    coefficient = norm.RSQRT_COEFFICIENTS[trace['rsqrt_index']]
    args = ((1, coefficient >> 32, n), (0, r[0], coefficient & 0xFFFFFFFF),
            (1, r[1], r[1]), (1, n, r[2]), (1, 0x3F000000, r[3]),
            (0, 0x3FC00000, r[4] ^ 0x80000000), (1, r[1], r[5]), (1, r[6], trace['rsqrt_scale']))
    for index, (op, a, b) in enumerate(args):
        emit(op, a, b, r[index], trace['rsqrt_flags'][index])
    for lane in range(256):
        emit(0, 0x3F800000, weights[lane], trace['gamma'][lane], trace['gamma_flags'][lane])
        emit(1, inputs[lane], trace['inverse'], trace['scaled'][lane], trace['scaled_flags'][lane])
        emit(1, trace['scaled'][lane], trace['gamma'][lane], trace['output_fp32'][lane], trace['output_fp32_flags'][lane])
    require(len(rows) == NORM_OPS_PER_HEAD and not trace['domain_error'], 'Norm schedule/domain drift')
    converted = list(zip(trace['output_fp32'], trace['output_bf16'], trace['output_bf16_flags']))
    require(not (trace['aggregate_flags'] & 0x1E), 'Norm NV/DZ/OF/UF rejected; NX retained')
    return np.asarray(rows, dtype='<u4'), np.asarray(converted, dtype='<u4'), trace


def rope_execution_trace(inputs, trig):
    """Four individually BF16 products, two BF16 sums; preserve tail bits."""
    inputs, trig = tuple(map(int, inputs)), tuple(map(int, trig))
    require(len(inputs) == 256 and len(trig) == 64, 'RoPE head/trig geometry drift')
    output, scalar, conversion, full, pairs = list(inputs), [], [], [], []
    for lane in range(32):
        e, o, c, s = inputs[lane], inputs[lane + 32], trig[lane], trig[lane + 32]
        pair = (e, o, c, s)
        trace = rope.pair_trace(*pair)
        args = ((1, e, c), (1, o, s), (1, e, s), (1, o, c),
                (0, trace[8], trace[9] ^ 0x80000000), (0, trace[10], trace[11]))
        for index, (op, a, b) in enumerate(args):
            result, flags = (trace[index], trace[index + 4]) if index < 4 else (trace[index + 12], trace[index + 14])
            scalar.append((op, a, b, result, flags))
            converted, cf = (trace[index + 8], trace[index + 12]) if index < 4 else (trace[index + 16], trace[index + 18])
            conversion.append((result, converted, cf))
        output[lane], output[lane + 32] = trace[20:22]
        require(not (trace[24] & 0x1E), 'RoPE NV/DZ/OF/UF rejected; NX retained')
        full.append(trace)
        pairs.append(pair)
    return tuple(np.asarray(v, dtype='<u4') for v in (output, scalar, conversion, full, pairs))


def diagnostic(actual, native):
    actual, native = np.asarray(actual, dtype='<u4'), np.asarray(native, dtype='<u4')
    require(actual.shape == native.shape, 'native diagnostic geometry mismatch')
    delta = np.abs(actual.view('<f4').astype(np.float64) - native.view('<f4').astype(np.float64))
    return dict(elements=actual.size, bit_differences=int(np.count_nonzero(actual != native)),
                max_abs=float(delta.max()), mean_abs=float(delta.mean()), acceptance_threshold=None,
                acceptance_claimed=False)


def compiler_tools(scratch):
    compiler = shutil.which('cc')
    require(compiler is not None, 'independent C compiler unavailable')
    compiler = str(Path(compiler).resolve())
    executables = {}
    flags = ['-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math']
    for name, source in (('norm', 'scripts/qk_norm256_reference.c'), ('rope', 'scripts/rope_bf16_candidate_reference.c')):
        executable = scratch / name
        subprocess.run([compiler, *flags, str(ROOT / source), '-lm', '-o', str(executable)], check=True, capture_output=True, timeout=30)
        executables[name] = executable
    libraries = {}
    for executable in executables.values():
        linked = subprocess.check_output(['ldd', str(executable)], text=True)
        for line in linked.splitlines():
            for word in line.split():
                if word.startswith('/') and Path(word).is_file():
                    libraries[word] = record(Path(word).resolve())
    return executables, dict(compiler=record(compiler), compiler_version=subprocess.check_output([compiler, '--version'], text=True),
                             flags=flags, python=record(Path(sys.executable).resolve()), python_version=sys.version,
                             numpy_version=np.__version__, platform=platform.platform(), cpu=platform.processor(),
                             executables={name: record(path) for name, path in executables.items()}, dynamic_runtime=libraries)


def crosscheck_c(executables, scratch, norm_inputs, norm_expected, rope_inputs, rope_expected):
    input_path, result_path = scratch / 'norm_input.bin', scratch / 'norm_output.bin'
    np.asarray(norm_inputs, dtype='<u4').tofile(input_path)
    subprocess.run([str(executables['norm']), str(input_path), str(result_path)], check=True, capture_output=True, timeout=30)
    actual = np.fromfile(result_path, dtype='<u4').reshape(-1, norm.TRACE_WORDS)
    require(np.array_equal(actual, norm_expected), 'independent Norm C node/flag mismatch')
    rope_text = ''.join(' '.join(f'{int(word):08x}' for word in row) + '\n' for row in rope_inputs)
    run = subprocess.run([str(executables['rope'])], input=rope_text, text=True, capture_output=True, check=True, timeout=30)
    actual_rope = np.asarray([int(word, 16) for word in run.stdout.split()], dtype='<u4').reshape(-1, len(rope.COLUMNS))
    require(np.array_equal(actual_rope, rope_expected), 'independent RoPE C node/flag mismatch')
    return dict(status='PASS_INDEPENDENT_C_ALL_NODES_AND_FLAGS', norm_heads=len(norm_inputs),
                norm_trace_words=int(actual.size), norm_bit_or_flag_mismatches=0,
                norm_c_input_sha256=file_sha(input_path), norm_c_output_sha256=file_sha(result_path),
                rope_pairs=len(rope_inputs), rope_trace_words=int(actual_rope.size), rope_bit_or_flag_mismatches=0,
                rope_c_input_sha256=sha(rope_text.encode()), rope_c_stdout_sha256=sha(run.stdout.encode()))


def prepare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / 'work') and output != ROOT / 'work' and not output.exists(),
            'fresh output directory under ignored work/ required')
    for name, digest in ORACLE_PINS.items():
        checked(ROOT / name, digest)
    host_identity = verify_host_sources()
    # This validates the saved producer reports, source/runtime identity,
    # captured-array hashes and bit extraction; it executes no model math.
    corpora = capture.load_materialized(ROOT, OFFICIAL, trusted_manifest_sha256=OFFICIAL_SHA)
    official = json.loads((OFFICIAL / 'provenance.json').read_text())
    require((official['revision'], official['framework_revision']) == (MODEL_REVISION, FRAMEWORK_REVISION), 'capture revision drift')
    payload, weights = load_payload(ROOT, ROOT / 'work/qwen35_layer3_payload')
    checked(ROOT / 'work/qwen35_layer3_payload/manifest.json', official['payload_manifests']['layer3']['sha256'])
    for name, directory in (('layer0', 'qwen35_layer0_payload'), ('additional_prefix', 'qwen35_prefix_payload')):
        checked(ROOT / 'work' / directory / 'manifest.json', official['payload_manifests'][name]['sha256'])
    data = corpora['baseline'][0]
    windows, all_norm_inputs, all_norm_trace, all_rope_inputs, all_rope_trace = {}, [], [], [], []
    native_path = OFFICIAL / 'baseline/native/all_bf16_producers.npz'
    with np.load(native_path, allow_pickle=False) as native:
        for name, (phase, token, position, _) in CASES.items():
            actual, host_report, identity = verify_host_window(name)
            prefix = phase + '_m128_'
            projected = {}
            for role, count, index in (('q', 4096, 8), ('k', 512, 17), ('v', 512, 26)):
                projected[role] = capture._bf16_words(native[prefix + f'native_producer_{index:02d}'], (1, 128, count), role)[0, token]
                source_weight = np.frombuffer(weights['self_attn.' + role + '_proj.weight'], dtype='<u2').reshape(count, 1024)
                require(sha(np.ascontiguousarray(source_weight.T).tobytes()) == identity['input_sha256']['weight_tensor'][role], 'projection checkpoint binding drift')
            require(np.array_equal(actual['q'].astype('<u4') << 16, projected['q'])
                    and np.array_equal(actual['k'].astype('<u4') << 16, projected['k']), 'actual Host Q/K differ from selected native inputs')
            cosine = capture._bf16_words(native[prefix + 'native_cos'], (1, 128, 64), 'cos')[0, token]
            sine = capture._bf16_words(native[prefix + 'native_sin'], (1, 128, 64), 'sin')[0, token]
            require(np.array_equal(cosine[:32], cosine[32:]) and np.array_equal(sine[:32], sine[32:]), 'official half-pair trig duplication drift')
            trig = np.concatenate((cosine[:32], sine[:32]))
            packed_q = actual['q'].reshape(8, 512)
            arrays = {'packed_q.bf16le': actual['q'], 'k.bf16le': actual['k'], 'v.bf16le': actual['v'],
                      'gate.bf16le': packed_q[:, 256:].reshape(-1), 'trig.bf16le': (trig >> 16).astype('<u2')}
            diagnostics = {}
            for role_id, role, heads, norm_index, rope_index in ((0, 'q', 8, 16, 29), (1, 'k', 2, 25, 32)):
                gamma = np.frombuffer(weights['self_attn.' + role + '_norm.weight'], dtype='<u2')
                require(sha(gamma.tobytes()) == norm.WEIGHT_SHA256[role_id], 'gamma checkpoint pin drift')
                arrays[role + '_gamma.bf16le'] = gamma
                x = (packed_q[:, :256] if role == 'q' else actual['k'].reshape(heads, 256)).astype('<u4') << 16
                native_norm = capture._bf16_words(native[prefix + f'native_producer_{norm_index:02d}'], (1, 128, heads, 256), 'native norm')[0, token]
                native_rope = capture._bf16_words(native[prefix + f'native_producer_{rope_index:02d}'], (1, heads, 128, 64), 'native rope')[0, :, token]
                mask = (data['phase'] == int(phase == 'carried')) & (data['token'] == token) & (data['role'] == role_id)
                require(np.array_equal(x, data['input_bf16_u32'][mask]) and np.array_equal(native_norm, data['native_bf16_u32'][mask]), 'selected corpus row binding drift')
                ns, nc, nf, outputs, rs, rc, rf, pairs, rotated, native_conditioned = ([] for _ in range(10))
                for head in range(heads):
                    scalar, conversion, trace = norm_execution_trace(x[head], gamma.astype('<u4') << 16)
                    ns.append(scalar); nc.append(conversion); nf.append(norm.trace_words(trace)); outputs.append(trace['output_bf16'])
                    all_norm_inputs.append(np.concatenate((x[head], gamma.astype('<u4') << 16)))
                    all_norm_trace.append(norm.trace_words(trace))
                    result, scalar, conversion, full, pair = rope_execution_trace(trace['output_bf16'], trig)
                    rotated.append(result); rs.append(scalar); rc.append(conversion); rf.append(full); pairs.append(pair)
                    all_rope_inputs.extend(pair); all_rope_trace.extend(full)
                    native_conditioned.append(rope_execution_trace(native_norm[head], trig)[0][:64])
                output_words, rotated_words = np.asarray(outputs, dtype='<u4'), np.asarray(rotated, dtype='<u4')
                arrays['norm_' + role + '.bf16le'] = (output_words >> 16).astype('<u2')
                arrays['rope_' + role + '.bf16le'] = (rotated_words >> 16).astype('<u2')
                arrays['native_norm_' + role + '.bf16le'] = (native_norm >> 16).astype('<u2')
                arrays['native_rope_' + role + '_prefix.bf16le'] = (native_rope >> 16).astype('<u2')
                for stage, scalar, conversion, full in (('norm', ns, nc, nf), ('rope', rs, rc, rf)):
                    arrays[stage + '_' + role + '_scalar_trace.u32le'] = np.asarray(scalar, dtype='<u4')
                    arrays[stage + '_' + role + '_conversion_trace.u32le'] = np.asarray(conversion, dtype='<u4')
                    arrays[stage + '_' + role + '_oracle_trace.u32le'] = np.asarray(full, dtype='<u4')
                require(np.array_equal(rotated_words[:, 64:], output_words[:, 64:]), 'RoPE tail transport drift')
                diagnostics[role] = dict(norm_same_actual_host_input=True, norm_vs_native=diagnostic(output_words, native_norm),
                    rope_composed_input_equals_native_norm=bool(np.array_equal(output_words, native_norm)),
                    rope_composed_prefix_vs_native=diagnostic(rotated_words[:, :64], native_rope),
                    rope_on_native_norm_same_input_vs_native=diagnostic(np.asarray(native_conditioned, dtype='<u4'), native_rope))
            windows[name] = dict(arrays=arrays, phase=phase, token_base=token, token_count=1, positionBase=position,
                                 trigTokens=position + 1, trig_file_rows=1, trig_file_row_index=position,
                                 host_provenance=identity, native_diagnostics=diagnostics,
                                 native_full_block_failures=host_report['native_full_block_failures'])
    with tempfile.TemporaryDirectory(prefix='qk-owner-oracle-') as temporary:
        scratch = Path(temporary)
        executables, tools = compiler_tools(scratch)
        independent = crosscheck_c(executables, scratch, all_norm_inputs, np.asarray(all_norm_trace, dtype='<u4'),
                                  all_rope_inputs, np.asarray(all_rope_trace, dtype='<u4'))
    output.mkdir()
    case_reports, all_files = {}, {}
    for name, window in windows.items():
        directory = output / name
        directory.mkdir()
        arrays = window.pop('arrays')
        files = {}
        for filename, values in arrays.items():
            raw = np.ascontiguousarray(values).tobytes()
            (directory / filename).write_bytes(raw)
            files[filename] = dict(bytes=len(raw), elements=int(values.size), dtype=values.dtype.str,
                                   shape=list(values.shape), sha256=sha(raw))
            all_files[name + '/' + filename] = files[filename]
        window.update(files=files, norm_policy=0xC1, rope_policy=0xB1, epsilon_word=norm.EPSILON,
                      head_dim=256, q_heads=8, k_heads=2, rotary_dim=64,
                      gamma_semantics='raw checkpoint delta; Scalar computes FP32 1 + gamma',
                      q_layout='head8, content256 then gate256',
                      trig_layout='single BF16 row cos32 then sin32; place at positionBase * 128 bytes',
                      scalar_columns=SCALAR_COLUMNS, scalar_opcodes=dict(Add=0, Mul=1),
                      conversion_columns=CONVERSION_COLUMNS, norm_scalar_ops_per_head=NORM_OPS_PER_HEAD,
                      rope_scalar_ops_per_head=192, norm_conversions_per_head=256, rope_conversions_per_head=192,
                      norm_execution_order='head, chunk: squares16/tree8,4,2,1/running; mean,epsilon,rsqrt8; lane:gamma,scaled,output',
                      rope_execution_order='head,pair0..31: Mul ec,os,es,oc; Add even,odd',
                      flags='NV,DZ,OF,UF,NX bits4..0; reject mask0x1e, preserve NX',
                      independent_reference=independent, owner_rtl_executed=False, full_host_chain_executed=False)
        (directory / 'manifest.json').write_text(json.dumps(window, indent=2, sort_keys=True) + '\n')
        case_reports[name] = record(directory / 'manifest.json')
        all_files[name + '/manifest.json'] = {key: case_reports[name][key] for key in ('bytes', 'sha256')}
    summary = dict(status='PASS_PREPARED_OWNER_ONLY_FIXTURE_PYTHON_C', hardware_acceptance_claimed=False,
        model_revision=MODEL_REVISION, framework_revision=FRAMEWORK_REVISION, layer_id=3,
        capture_mode='code_pinned_reuse', fresh_capture_count=0, fresh_official_executions=0,
        reused_official_executions=2, matrix_rerun=False, full_reference_rerun=False, host_output_injection=False,
        source_actual_host_build=host_identity, official_manifest=record(OFFICIAL / 'provenance.json'),
        official_source_sha256=official['source_sha256'], payload_manifests=official['payload_manifests'],
        checkpoint_qk_gamma_sha256=dict(zip(capture.WEIGHTS, norm.WEIGHT_SHA256)),
        capture_cpu_environment={v: official['corpora'][v]['environment'] for v in capture.VARIANTS},
        original_native_gate_pass={v: official['corpora'][v]['native_audit_gate_pass'] for v in capture.VARIANTS},
        original_native_status={v: official['corpora'][v]['native_audit_status'] for v in capture.VARIANTS},
        original_native_failed_comparisons={v: official['corpora'][v]['native_failed_comparisons'] for v in capture.VARIANTS},
        oracle_source_sha256=ORACLE_PINS, preparation_source=record(Path(__file__)),
        independent_reference=independent, reference_tools=tools, cases=case_reports, files=all_files)
    text = json.dumps(summary, indent=2, sort_keys=True) + '\n'
    (output / 'manifest.json').write_text(text)
    (output / 'summary.json').write_text(text)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    result = prepare(parser.parse_args().output)
    print(json.dumps({key: result[key] for key in ('status', 'fresh_capture_count', 'independent_reference', 'cases')}, indent=2))
