#!/usr/bin/env python3
"""Authenticate and pack one real layer3 Q/K/V fan-out for HostBlockTop.

Only the existing CaptureSession factories supply official inputs. There is no
caller-provided NPZ, trust digest, replacement weight, or native-output injection
route. A fresh session must remain live in the invocation that rebuilt it.
"""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
from host_bf16_qkv_descriptor import HostQkvBinding, ROLES, COLUMNS, RECORDS_PER_COMMAND, build_qkv_commands
from pack_host_bf16_v_fixture import ROOT, CaptureSession, pinned_session, rebuild_session, capture, load_payload

FROZEN_REFERENCE = ROOT / 'work/qwen35_qkv_command_full128_vectors'
FROZEN_REFERENCE_SHA256 = '7a825ff9195db77e5889ecd2c4a4cf6f120454a39160493cd82661b806f97a51'
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
FRAMEWORK_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def frozen_terminals(activation, weights, *, variant, phase, token_base, token_count):
    """Read terminal words only, never expand/regenerate accumulator traces.

    The code-pinned summary binds the independent integer + C cross-check.
    Reuse requires exact actual raw A and selected K-major W hashes per head;
    a different legitimate fresh capture simply does not reuse this oracle.
    """
    path = FROZEN_REFERENCE / 'summary.json'
    if not path.exists():
        return {}, dict(status='NOT_AVAILABLE', reused=False)
    if path.is_symlink() or sha(path.read_bytes()) != FROZEN_REFERENCE_SHA256:
        raise ValueError('frozen independent summary identity drift')
    summary = json.loads(path.read_text())
    if (summary['revision'], summary['framework_revision'], summary['token_count_per_phase']) != (MODEL_REVISION, FRAMEWORK_REVISION, 128):
        raise ValueError('frozen independent source scope drift')
    cases = {(c['variant'], c['phase'], c['role'], c['token'], c['head']): c for c in summary['cases']}
    selected, weight_hashes = [], {}
    for role, n in zip(ROLES, COLUMNS):
        width = 512 if role == 'q' else 256
        for head in range(n // width):
            weight_hashes[(role, head)] = sha(np.ascontiguousarray(weights[role][:, head * width:(head + 1) * width]).tobytes())
        for token in range(token_base, token_base + token_count):
            for head in range(n // width):
                case = cases[(variant, phase, role, token, head)]
                if case['activation_sha256'] != sha(activation[token].tobytes()) or case['selected_weight_k_major_sha256'] != weight_hashes[(role, head)]:
                    return {}, dict(status='NOT_REUSED_ACTUAL_INPUT_HASH_MISMATCH', reused=False,
                                    summary_sha256=FROZEN_REFERENCE_SHA256)
                receipt = case['c_reference']
                if receipt['pass'] is not True or receipt['bit_mismatches'] or receipt['flag_mismatches'] or receipt['matrix_bf16_columns'] != width:
                    raise ValueError('frozen independent C reference failed')
                selected.append((role, case))
    result = {role: [] for role in ROLES}
    for role, case in selected:
        record = case['files']['projected']
        file = FROZEN_REFERENCE / case['directory'] / record['file']
        if file.is_symlink() or not file.resolve().is_relative_to(FROZEN_REFERENCE.resolve()):
            raise ValueError('frozen terminal path escape')
        raw = file.read_bytes()
        if len(raw) != record['bytes'] or sha(raw) != record['sha256'] or record['hex_digits'] != 4:
            raise ValueError('frozen terminal bytes drift')
        values = raw.decode('ascii').split()
        if len(values) != case['columns'] or any(len(v) != 4 for v in values):
            raise ValueError('frozen terminal shape drift')
        result[role].append(np.asarray([int(v, 16) for v in values], dtype='<u2'))
    return {role: np.concatenate(values).tobytes() for role, values in result.items()}, dict(
        status='REUSED_EXACT_INPUT_BOUND_INTEGER_AND_C_TERMINALS', reused=True,
        summary_sha256=FROZEN_REFERENCE_SHA256, selected_heads=len(selected),
        accumulator_traces_regenerated=False, accumulator_traces_loaded=False)


def pack_fixture(output: Path, *, variant='baseline', phase='cold', token_base=0, token_count=1, session=None, reference_session=None):
    if variant not in capture.VARIANTS or phase not in ('cold', 'carried'):
        raise ValueError('invalid official source selection')
    if type(token_base) is not int or type(token_count) is not int or not 0 <= token_base < 128 or not 1 <= token_count <= 128 or token_base + token_count > 128:
        raise ValueError('invalid token window')
    out = Path(output).resolve()
    if not out.is_relative_to(ROOT / 'work') or out.exists():
        raise ValueError('fresh output under ignored work required')
    session = pinned_session() if session is None else session
    if type(session) is not CaptureSession:
        raise ValueError('live CaptureSession required')
    official = session.verify()
    source = session.directory
    native_failures = {}
    for dispatch in capture.VARIANTS:
        audit = source / dispatch / 'native/result.json'
        capture._verify_file(audit, official['corpora'][dispatch]['fresh_audit_report'])
        report = json.loads(audit.read_text())
        native_failures[dispatch] = {key: report[key] for key in ('status', 'gate_pass', 'failed_producers')}
    native = source / variant / 'native/all_bf16_producers.npz'
    capture._verify_file(native, official['corpora'][variant]['fresh_audit_arrays'])
    prefix = phase + '_m128_native_producer_'
    with np.load(native, allow_pickle=False) as producers:
        if len(producers.files) != len(set(producers.files)):
            raise ValueError('duplicate source arrays')
        activation = (capture._bf16_words(producers[prefix + '07'], (1, 128, 1024), prefix + '07')[0] >> 16).astype('<u2')
        native_outputs = {role: (capture._bf16_words(producers[prefix + index], (1, 128, n), prefix + index)[0] >> 16).astype('<u2')
                          for role, n, index in zip(ROLES, COLUMNS, ('08', '17', '26'))}
    manifest, raw = load_payload(ROOT, session.payload_layer3)  # validates every one of the 11 pinned weights
    if manifest['revision'] != MODEL_REVISION:
        raise ValueError('official checkpoint revision drift')
    weights = {role: np.ascontiguousarray(np.frombuffer(raw['self_attn.' + role + '_proj.weight'], dtype='<u2').reshape(n, 1024).T)
               for role, n in zip(ROLES, COLUMNS)}
    if reference_session is None:
        terminals, independent = frozen_terminals(activation, weights, variant=variant, phase=phase, token_base=token_base, token_count=token_count)
    else:
        from host_bf16_qkv_reference import FreshProjectionReferenceSession
        if type(reference_session) is not FreshProjectionReferenceSession:
            raise ValueError('live independent integer/C reference authority required')
        terminals, independent = reference_session.select(activation, weights, session=session, variant=variant,
            phase=phase, token_base=token_base, token_count=token_count)
    base = 0x120000000
    cb, db, meta, aa = base, base + 0x1000, base + 0x2000, base + 0x10000
    cursor = aa + activation.nbytes + 0x1000
    weight_addresses = []
    for role in ROLES:
        weight_addresses.append(cursor)
        cursor += weights[role].nbytes + 0x1000
    scratch = cursor
    cursor += 0x1000
    outputs = []
    for n in COLUMNS:
        outputs.append(cursor)
        cursor += 128 * n * 2 + 0x1000
    limit = cursor
    bindings = [HostQkvBinding(role, 128, token_base, token_count, aa, weight_addresses[role], outputs[role]) for role in range(3)]
    commands, records = build_qkv_commands(bindings)
    command_bytes = b''.join(c.pack().to_bytes(16, 'little') for c in commands)
    command_bytes += bytes(-len(command_bytes) % 64)
    descriptor_bytes = b''.join(records[i].pack().to_bytes(16, 'little') for i in range(len(records)))
    descriptor_bytes += bytes(-len(descriptor_bytes) % 64)
    out.mkdir(parents=True)
    files = {}
    def write(name, data):
        (out / name).write_bytes(data)
        files[name] = dict(bytes=len(data), sha256=sha(data))
    write('activation.bf16le', activation.tobytes())
    for role in ROLES:
        write('weight_' + role + '.bf16le', weights[role].tobytes())
        write('native_' + role + '.bf16le', native_outputs[role].tobytes())
        if terminals:
            write('independent_' + role + '.bf16le', terminals[role])
    write('host_commands.bin', command_bytes)
    write('host_descriptors.bin', descriptor_bytes)
    values = [base, limit, cb, cb + len(command_bytes), len(commands), db, db + len(descriptor_bytes), len(records), meta, scratch, aa, 128, token_base, token_count, int(bool(terminals))]
    launch = 'HOST_QKV_PROJECTION_V1\n' + ' '.join(map(str, values)) + '\n'
    for binding, command in zip(bindings, commands):
        launch += ' '.join(map(str, (binding.role, binding.n, binding.weight_ddr, binding.output_ddr, RECORDS_PER_COMMAND, command.event_wait, command.event_signal, command.dst))) + '\n'
    write('launch.txt', launch.encode())
    report = dict(status='SOURCE_AUTHENTICATED_HOST_QKV_INPUTS_ONLY', scope='PROJECTION_ONLY',
        variant=variant, phase=phase, token_base=token_base, token_count=token_count, rows=128,
        official_capture=str(source.relative_to(ROOT)), model_revision=manifest['revision'], framework_revision=FRAMEWORK_REVISION,
        producer_activation=prefix + '07', producer_native={role: prefix + index for role, index in zip(ROLES, ('08', '17', '26'))},
        source_weight_sha256={role: sha(raw['self_attn.' + role + '_proj.weight']) for role in ROLES},
        capture_mode='fresh_same_invocation' if session.fresh else 'code_pinned_reuse',
        command_order=list(ROLES), fan_out_shared_activation=True, command_data_dependency=False,
        q_layout='token, head8, content256 then gate256 (interleaved per head)',
        norm_supported=False, rope_supported=False, attention_supported=False, full_block_supported=False,
        independent_reference=independent, files=files,
        native_full_block_failures=native_failures,
        sources={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in
                 (Path(__file__).resolve(), Path(__file__).with_name('host_bf16_qkv_descriptor.py'),
                  Path(__file__).with_name('pack_host_bf16_v_fixture.py'),
                  ROOT / 'chisel/continuous_prefill/config/host_bf16_qkv_descriptor_contract.json')},
        **session.evidence(official))
    report['input_sha256'] = fixture_input_hashes(out, report)
    (out / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def fixture_input_hashes(directory, manifest):
    directory = Path(directory)
    base, count = manifest['token_base'], manifest['token_count']
    activation = (directory / 'activation.bf16le').read_bytes()
    return dict(activation_tensor=sha(activation), activation_window=sha(activation[base * 2048:(base + count) * 2048]),
                weight_tensor={role: sha((directory / ('weight_' + role + '.bf16le')).read_bytes()) for role in ROLES},
                command=sha((directory / 'host_commands.bin').read_bytes()),
                descriptors=sha((directory / 'host_descriptors.bin').read_bytes()), launch=sha((directory / 'launch.txt').read_bytes()))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--variant', choices=('baseline', 'avx2'), default='baseline')
    p.add_argument('--phase', choices=('cold', 'carried'), default='cold')
    p.add_argument('--token-base', type=int, default=0)
    p.add_argument('--token-count', type=int, default=1)
    return p


if __name__ == '__main__':
    args = parser().parse_args()
    result = pack_fixture(args.output, variant=args.variant, phase=args.phase, token_base=args.token_base, token_count=args.token_count)
    print(json.dumps({k: result[k] for k in ('status', 'scope', 'variant', 'phase', 'token_base', 'token_count', 'independent_reference', 'native_full_block_gate_pass')}, indent=2))
