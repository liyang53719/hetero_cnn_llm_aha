#!/usr/bin/env python3
"""Small, weight-free retention for a FUTURE completed Attention M1 pair.

Nothing here runs a model, compiler, simulator, download, or CI job. A future
authoritative runner may call ``pack_verified_case`` immediately after its
existing run_case/final live checks, while the SAME live authorities and raw
files still exist. There is deliberately no receipt-only sealing CLI. This
helper rechecks those authorities and file identities; it issues no hardware
or native numerical authority. The old 98-pass bytes were not retained and
cannot be recovered or retrospectively authenticated by creating this pack.

Prior KV is read from carried1/writable_after_command0.bin: actual DDR after
input_norm, before command 8 appends KV. The existing physical audit verifies
the whole snapshot and proves that command 0 cannot write KV. Final KV is
read from carried1/ddr_after.bin. Neither is assembled from golden data or
terminal appends. Record this timing explicitly; it is not a pre-launch dump.
The driver already emits these authoritative readbacks. Internal GQA producer
dumps are NOT emitted and remain a future instrumentation dependency.

Only the 49 allowlisted BF16 files (147712 bytes) plus <=64 KiB metadata enter
a deterministic, uncompressed ZIP of <=256 KiB. Full DDR, weights, NPZ,
reference gold, ELF, SV and logs never enter the archive. Their hashes bind
the retained slices. Keep archives in authorized CI artifacts, NEVER in Git.
The later downloader must independently authenticate the GitHub run/job and
artifact digest; a caller-supplied ZIP hash establishes consistency only.
An artifact-service envelope digest is not automatically this ZIP's digest.
``reference_receipt_sha256`` is the existing live factory's canonical-JSON
digest; ``reference_receipt_file_sha256`` is the saved file's distinct digest.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = 'replay_manifest.json'
SCHEMA = 'ATTENTION_M1_REPLAY_PACK_V1'
MAX_BYTES = 256 * 1024
MAX_METADATA_BYTES = 64 * 1024
RAW_BYTES = 147712
PHASES = ('cold0', 'carried1')
WIDTHS = dict(input_norm=1024, q=4096, k=512, v=512, norm_q=2048,
    gate=2048, norm_k=512, rope_q=2048, rope_k=512, cache_k=512,
    cache_v=512, context=2048, sigmoid_mul=2048, o=1024, residual1=1024,
    post_norm=1024, ffn_gate=3584, ffn_up=3584, silu_mul=3584,
    down=1024, residual2=1024)
PRIVACY = ('Model-derived activation, KV and output tensors from the fixed '
    'artificial-token fixture; authorized CI artifacts only, never Git; '
    'no downloadable model weights or raw NPZ.')
LAUNCHES = [dict(phase=p, source_phase=s, position=i, tokens=1,
    cache_length_before=i, cache_length_after=i+1)
    for i, (p, s) in enumerate(zip(PHASES, ('cold0', 'cold1')))]
DIGEST_KEYS = ('binary_sha256', 'rtl_sha256', 'build_ready_sha256',
    'toolchain_sha256', 'official_capture_manifest_sha256',
    'reference_receipt_sha256', 'reference_receipt_file_sha256', 'fixture_manifest_sha256',
    'result_receipt_sha256', 'execution_identity_sha256', 'log_sha256',
    'build_sources_manifest_sha256', 'reference_sources_sha256',
    'fixture_sources_sha256', 'packer_sha256')
SOURCE_PATHS = ('chisel/continuous_prefill/tests/host_bf16_attention_block.cpp',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_fixture.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_execution.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_live_gate.py')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode()


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value),
            'invalid SHA256')
    return value


def safe_name(name):
    require(type(name) is str and name and len(name) <= 180 and
            str(PurePosixPath(name)) == name and not name.startswith('/') and
            all(p not in ('', '.', '..') for p in name.split('/')) and
            '\\' not in name and '\x00' not in name, 'unsafe relative path')
    return name


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink evidence')
    require(path.is_file() and stat.S_ISREG(path.stat().st_mode),
            'missing regular evidence: ' + str(path))
    return path


def read_bounded(path, limit):
    path = regular(path)
    require(path.stat().st_size <= limit, 'evidence exceeds byte bound')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    require(len(raw) <= limit, 'evidence grew beyond byte bound')
    return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def read_json(path):
    return json.loads(read_bounded(path, 16 * 1024 * 1024),
                      object_pairs_hook=unique_object)


def specifications():
    records = {}
    def add(name, size, shape, layout, source, kind, phase):
        records[name] = dict(bytes=size, dtype='bf16le', shape=shape,
            layout=layout, source_file=source, origin=kind, phase=phase)
    for phase in ('cold0', 'cold1'):
        name = 'input/' + phase + '_hidden.bf16le'
        add(name, 2048, [1, 1, 1024], 'batch_token_channel', name,
            'original_raw_input', phase)
    add('input/trig_first_two_rows.bf16le', 256, [2, 2, 32],
        'position_cosine_then_sine_channel', 'input/trig.bf16le',
        'original_raw_input_slice', 'positions0_1')
    for phase in PHASES:
        for name, width in WIDTHS.items():
            path = phase + '/actual_' + name + '.bf16le'
            add(path, 2*width, [width], 'flat_driver_terminal_span', path,
                'actual_acknowledged_terminal', phase)
    for when, tokens, source, kind in (
            ('prior', 1, 'carried1/writable_after_command0.bin',
             'actual_ddr_after_input_norm_before_kv_append'),
            ('final', 2, 'carried1/ddr_after.bin', 'actual_ddr_after_pair')):
        for role in ('k', 'v'):
            add(f'cache/{when}_carried1_{role}.bf16le', tokens*1024,
                [tokens, 2, 256], 'token_head_channel', source, kind, 'carried1')
    return records


SPECS = specifications()
EXECUTION_PATHS = frozenset({name for name in SPECS if '/actual_' in name} |
    {'cold0/ddr_after.bin', 'carried1/ddr_after.bin', 'carried1/writable_after_command0.bin'})
INPUT_NAMES = frozenset(('cold0_hidden.bf16le', 'cold1_hidden.bf16le', 'trig.bf16le',
    *('weight_'+n+'.bf16le' for n in ('q', 'k', 'v', 'o', 'ffn_gate',
        'ffn_up', 'down', 'input_norm', 'post_norm', 'q_gamma', 'k_gamma'))))


def _identity(value):
    expected = {'original_commit', 'run_id', 'job_id', 'CPU_variant', 'model',
                'input_sha256', 'source_files_sha256', 'retained_execution_sha256', *DIGEST_KEYS}
    require(type(value) is dict and set(value) == expected, 'identity field inventory')
    require(type(value['original_commit']) is str and
            re.fullmatch('[0-9a-f]{40}', value['original_commit']), 'exact original commit required')
    for key in ('run_id', 'job_id'):
        require(type(value[key]) is str and re.fullmatch('[1-9][0-9]{0,23}', value[key]),
                'numeric GitHub run/job ID required')
    require(value['CPU_variant'] in ('baseline', 'avx2'), 'CPU variant')
    for key in DIGEST_KEYS:
        digest(value[key])
    require(set(value['input_sha256']) == INPUT_NAMES, 'input identity inventory')
    require(set(value['source_files_sha256']) == set(SOURCE_PATHS), 'source identity inventory')
    require(set(value['retained_execution_sha256']) == EXECUTION_PATHS, 'execution identity inventory')
    for mapping in ('input_sha256', 'source_files_sha256', 'retained_execution_sha256'):
        for pin in value[mapping].values():
            digest(pin)
    model = value['model']
    require(set(model) == {'model_id', 'revision', 'layer_id', 'framework_revision',
        'contract_sha256', 'payload_pin_sha256', 'official_modeling_sha256',
        'torch_version', 'numpy_version'}, 'model identity inventory')
    require(model['model_id'] == 'Qwen/Qwen3.5-0.8B' and
            type(model['layer_id']) is int and model['layer_id'] == 3, 'model/layer identity')
    for key in ('revision', 'framework_revision'):
        require(type(model[key]) is str and re.fullmatch('[0-9a-f]{40}', model[key]), 'model revision')
    for key in ('contract_sha256', 'payload_pin_sha256', 'official_modeling_sha256'):
        digest(model[key])
    for key in ('torch_version', 'numpy_version'):
        require(type(model[key]) is str and re.fullmatch('[0-9A-Za-z.+_-]{1,48}', model[key]), 'runtime version')


def _validate_manifest(manifest):
    require(type(manifest) is dict and set(manifest) == {'schema', 'identity',
        'pair_sha256', 'launches', 'files', 'raw_bytes', 'privacy_description',
        'hardware_authority_verified', 'native_full_block_acceptance',
        'downloadable_weights_included', 'evidence_status'}, 'manifest field inventory')
    require(manifest['schema'] == SCHEMA and encoded(manifest['launches']) == encoded(LAUNCHES),
            'schema/phase/cache trajectory mismatch')
    require(manifest['privacy_description'] == PRIVACY and
            manifest['evidence_status'] == 'retained_bytes_only_external_CI_authentication_required' and
            all(manifest[k] is False for k in ('hardware_authority_verified',
                'native_full_block_acceptance', 'downloadable_weights_included')),
            'privacy/authority boundary')
    _identity(manifest['identity'])
    require(manifest['pair_sha256'] == sha(encoded(manifest['identity'])), 'pair identity mismatch')
    files = manifest['files']
    require(type(files) is dict and set(files) == set(SPECS), 'replay file allowlist mismatch')
    for name, row in files.items():
        safe_name(name)
        require(type(row) is dict and set(row) == set(SPECS[name]) | {
            'sha256', 'source_sha256', 'source_bytes', 'source_offset'}, 'file metadata inventory')
        require(all(type(row[k]) is type(v) and encoded(row[k]) == encoded(v) for k, v in SPECS[name].items()),
                'file path/dtype/shape/phase/byte geometry mismatch')
        digest(row['sha256']); digest(row['source_sha256'])
        require(type(row['source_bytes']) is int and 0 < row['source_bytes'] <= 128*1024*1024 and
                type(row['source_offset']) is int and row['source_offset'] >= 0 and
                row['source_offset'] + row['bytes'] <= row['source_bytes'], 'source slice bounds')
        if row['origin'] in ('original_raw_input', 'actual_acknowledged_terminal'):
            require(row['source_bytes'] == row['bytes'] and row['source_offset'] == 0 and
                    row['source_sha256'] == row['sha256'], 'whole-file source identity')
        if name.startswith('input/'):
            require(row['source_sha256'] == manifest['identity']['input_sha256'][
                row['source_file'].split('/')[-1]], 'original input identity mismatch')
            if 'trig_' in name:
                require(row['source_bytes'] == 32768 and row['source_offset'] == 0, 'trig slice geometry')
        else:
            require(row['source_sha256'] == manifest['identity']['retained_execution_sha256'][row['source_file']],
                    'retained source differs from original execution identity')
    require(type(manifest['raw_bytes']) is int and manifest['raw_bytes'] ==
            sum(row['bytes'] for row in files.values()) == RAW_BYTES <= MAX_BYTES, 'raw byte budget')
    for when in ('prior', 'final'):
        k, v = (files[f'cache/{when}_carried1_{r}.bf16le'] for r in ('k', 'v'))
        require(k['source_sha256'] == v['source_sha256'] and k['source_bytes'] == v['source_bytes'] and
                v['source_offset']-k['source_offset'] == 256*1024, 'shared physical KV snapshot identity')
    require(len(encoded(manifest)) <= MAX_METADATA_BYTES, 'metadata byte budget')


def _zip_bytes(manifest, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name in [MANIFEST] + sorted(files):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, encoded(manifest) if name == MANIFEST else files[name])
    raw = buffer.getvalue()
    require(len(raw) <= MAX_BYTES, 'archive byte budget')
    return raw


def _check_files(manifest, files):
    _validate_manifest(manifest)
    require(set(files) == set(SPECS), 'replay file allowlist mismatch')
    for name, raw in files.items():
        require(type(raw) is bytes and len(raw) == SPECS[name]['bytes'] and
                sha(raw) == manifest['files'][name]['sha256'], 'file byte/hash mismatch: '+name)
        # Inputs and accepted terminals are finite BF16, not arbitrary ZIP/NPZ payloads.
        require(all((int.from_bytes(raw[i:i+2], 'little') & 0x7f80) != 0x7f80
                    for i in range(0, len(raw), 2)), 'nonfinite BF16 tensor')
    for role, producer in (('k', 'rope_k'), ('v', 'v')):
        prior = files[f'cache/prior_carried1_{role}.bf16le']
        final = files[f'cache/final_carried1_{role}.bf16le']
        require(prior == files[f'cold0/actual_cache_{role}.bf16le'] and
                final[:1024] == prior and final[1024:] == files[f'carried1/actual_cache_{role}.bf16le'],
                'actual prior/final cache trajectory mismatch')
        for phase in PHASES:
            require(files[f'{phase}/actual_cache_{role}.bf16le'] ==
                    files[f'{phase}/actual_{producer}.bf16le'], 'actual append/producer mismatch')


def verify_pack(archive, expected_sha256, *, expected_commit, expected_run_id,
                expected_job_id, expected_reference_sha256):
    """Offline consistency only; expected values must come from authenticated CI."""
    raw = read_bounded(archive, MAX_BYTES)
    require(sha(raw) == digest(expected_sha256), 'archive digest mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            entries = package.infolist()
            require(len(entries) == len(SPECS)+1 and
                    {e.filename for e in entries} == set(SPECS) | {MANIFEST}, 'archive file inventory')
            for entry in entries:
                safe_name(entry.filename)
                require(entry.compress_type == zipfile.ZIP_STORED and
                        entry.compress_size == entry.file_size and
                        entry.file_size <= (MAX_METADATA_BYTES if entry.filename == MANIFEST
                            else SPECS[entry.filename]['bytes']) and not entry.extra and not entry.comment and
                        entry.external_attr >> 16 == stat.S_IFREG | 0o644,
                        'nonregular/compressed/oversized archive entry')
            manifest_raw = package.read(MANIFEST)
            manifest = json.loads(manifest_raw, object_pairs_hook=unique_object)
            _validate_manifest(manifest)
            require(manifest_raw == encoded(manifest), 'noncanonical manifest')
            files = {name: package.read(name) for name in SPECS}
    except (zipfile.BadZipFile, RuntimeError, KeyError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('invalid replay archive') from error
    identity = manifest['identity']
    require((identity['original_commit'], identity['run_id'], identity['job_id'],
             identity['reference_receipt_sha256']) == (expected_commit, expected_run_id,
             expected_job_id, expected_reference_sha256), 'original pair/reference identity mismatch')
    _check_files(manifest, files)
    require(_zip_bytes(manifest, files) == raw, 'noncanonical archive or trailing data')
    return manifest


def _slices(path, expected_sha256, size, ranges):
    """Hash complete original DDR/input without retaining its weights or suffix."""
    path = regular(path)
    require(path.stat().st_size == size, 'source snapshot size mismatch')
    require(all(type(a) is int and type(n) is int and 0 <= a < a+n <= size
                for a, n in ranges.values()), 'source slice bounds')
    result = {name: bytearray() for name in ranges}
    hashed, cursor = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while chunk := stream.read(1024*1024):
            hashed.update(chunk)
            for name, (begin, count) in ranges.items():
                start, end = max(cursor, begin), min(cursor+len(chunk), begin+count)
                if start < end:
                    result[name].extend(chunk[start-cursor:end-cursor])
            cursor += len(chunk)
            require(cursor <= size, 'source snapshot grew')
    require(cursor == size and hashed.hexdigest() == digest(expected_sha256), 'source snapshot hash mismatch')
    require(all(len(result[name]) == size for name, (_, size) in ranges.items()), 'short snapshot slice')
    return {name: bytes(raw) for name, raw in result.items()}


def _admit_completed_case(build, fixture_path, result, original_commit, authorities):
    """Existing live workflow remains the sole authority; this is read-only."""
    require(set(authorities) == {'block_session', 'session', 'projection_session', 'attention_session'},
            'same-invocation live authorities required')
    scripts = str(ROOT/'chisel/continuous_prefill/scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import host_bf16_attention_block_live_gate as live
    from run_host_bf16_qkv_fresh_gate import verify_checkout
    admission = live.admit_fixture(fixture_path, **authorities)
    build_identity = live.build_identity(build, admission['source_sha256'])
    sources = read_json(build/'sources.sha256.json')
    verify_checkout(original_commit, sources)
    ready = read_json(build/'build_ready.json')
    require(ready['source_base_commit'] == original_commit, 'original build commit mismatch')
    require(read_json(build/'pass.result.json') == result, 'original result changed')
    require(result['status'] == live.CASE_STATUS and result['mode'] == 'pass' and
            result['same_dut_launches'] == 2 and result['resets_between_launches'] == 0 and
            all(result[k] is True for k in ('actual_dut_identity_verified', 'live_authorities_verified',
                'source_immutability_verified', 'full_block_m1_executed', 'full_block_artifact_consistency',
                'frozen_recipe_block_acceptance')) and
            all(result[k] is False for k in ('native_full_block_acceptance', 'intermediate_preload',
                'prior_cache_preload')), 'completed authenticated pass pair required')
    require(result['binary_sha256'] == build_identity['obj/VHostBlockTop'] and
            result['rtl_sha256'] == build_identity['generated/HostBlockTop.sv'] and
            result['build_ready_sha256'] == build_identity['build_ready.json'] and
            result['fixture_sha256'] == admission['manifest_sha256'] and
            result['block_reference_receipt_sha256'] == admission['block_reference_receipt_sha256'] and
            result['input_sha256'] == admission['input_sha256'], 'original execution/reference/build identity mismatch')
    live.verify_case_outputs(build, result)
    # Audit is physical readback consistency, never a new native/RTL authority.
    audit = live.execution.audit(fixture_path, build/'pass', build/'pass.log', 'pass')
    require(all(result[key] == audit[key] for key in ('runs', 'log_sha256', 'fixture_sha256')),
            'original physical execution audit mismatch')
    reference = read_json(fixture_path/'reference_receipt.json')
    require(sha(encoded(reference)) == result['block_reference_receipt_sha256'],
            'canonical live reference receipt identity mismatch')
    require(reference['original_prefix_report']['input_origin'] ==
        'fixed_artificial_token_IDs_with_real_pinned_checkpoint_embedding_and_official_prefix_activations',
        'fixed artificial-token fixture required')
    return admission, build_identity, reference


def _collect(build, fixture_path, result, admission, reference):
    files, records = {}, {}
    layout = admission['layout']; h = layout['header']
    actual = result['execution_identity']['files_sha256']
    require(set(result['actual_sha256']) == set(PHASES), 'actual phase inventory')
    require(len(result['runs']) == 2 and all(
        (r['phase'], r['status'], r['checkpoint_accepted'], r['inferred_committed_length'],
         r['inferred_committed_generation']) == (p, 0, True, i+1, i+1)
        for i, (p, r) in enumerate(zip(PHASES, result['runs']))), 'actual phase/cache commit mismatch')
    def retain(name, raw, source_sha, source_size, offset):
        require(name not in files, 'duplicate retained file')
        files[name] = raw
        records[name] = dict(SPECS[name], sha256=sha(raw), source_sha256=source_sha,
                             source_bytes=source_size, source_offset=offset)
    for name, spec in SPECS.items():
        if name.startswith('input/'):
            source = spec['source_file']; row = reference['inputs'][source.split('/')[-1]]
            raw = _slices(fixture_path/source, row['sha256'], row['bytes'], {name: (0, spec['bytes'])})[name]
            retain(name, raw, row['sha256'], row['bytes'], 0)
    for index, phase in enumerate(PHASES):
        require(set(result['actual_sha256'][phase]) == set(WIDTHS), 'actual terminal inventory')
        snapshot = phase+'/ddr_after.bin'
        require(actual[snapshot] == result['runs'][index]['ddr_sha256'], 'DDR execution identity mismatch')
        ranges = {phase+'/actual_'+s['name']+'.bf16le': (s['begin']-h['base'], s['bytes'])
                  for s in layout['launches'][index]['spans']}
        if index == 1:
            ranges.update({f'cache/final_carried1_{r}.bf16le':
                (h['cache']-h['base']+i*h['capacity']*1024, 2048) for i, r in enumerate(('k', 'v'))})
        sliced = _slices(build/'pass'/snapshot, actual[snapshot], h['limit']-h['base'], ranges)
        for name, raw in sliced.items():
            if name.startswith('cache/'):
                retain(name, raw, actual[snapshot], h['limit']-h['base'], ranges[name][0])
                continue
            terminal = name.split('/actual_')[1].removesuffix('.bf16le')
            require(actual[name] == result['actual_sha256'][phase][terminal], 'terminal execution identity mismatch')
            direct = _slices(build/'pass'/name, actual[name], len(raw), {name: (0, len(raw))})[name]
            require(raw == direct, 'terminal differs from actual DDR')
            retain(name, direct, actual[name], len(raw), 0)
    snapshot = 'carried1/writable_after_command0.bin'
    require(actual[snapshot] == result['runs'][1]['snapshot_sha256']['writable_after_command0.bin'],
            'prior snapshot execution identity mismatch')
    ranges = {f'cache/prior_carried1_{r}.bf16le':
        (h['cache']-h['scratch']+i*h['capacity']*1024, 1024) for i, r in enumerate(('k', 'v'))}
    for name, raw in _slices(build/'pass'/snapshot, actual[snapshot], h['limit']-h['scratch'], ranges).items():
        retain(name, raw, actual[snapshot], h['limit']-h['scratch'], ranges[name][0])
    return files, records


def pack_verified_case(build, fixture, archive, *, result, original_commit,
                       run_id, job_id, authorities):
    """Dormant future wrapper hook; call only after the original verified run.

    ``job_id`` is the numeric GitHub job ID, not GITHUB_JOB's display key.
    The caller supplies the original run/job IDs, later independently checked
    by the artifact downloader. No workflow is installed by this function.
    """
    build, fixture, archive = Path(build), Path(fixture), Path(archive).absolute()
    require(not archive.exists() and not any(p.is_symlink() for p in (archive, *archive.parents)),
            'fresh nonsymlink archive required')
    require('..' not in archive.parts, 'archive path traversal')
    # Work is ignored by Git; no tensor artifact may be written alongside source.
    work_root = ROOT/'work'
    require(archive != work_root and archive.is_relative_to(work_root),
            'archive must be a proper descendant of ignored work, never Git')
    require(all(not p.exists() or p.is_dir() for p in archive.parents),
            'archive ancestors must be directories')
    admitted, built, reference = _admit_completed_case(build, fixture, result, original_commit, authorities)
    files, records = _collect(build, fixture, result, admitted, reference)
    contract_path = ROOT/'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json'
    contract = read_json(contract_path)
    require(reference['model_revision'] == contract['revision'], 'original model revision mismatch')
    identity = dict(original_commit=original_commit, run_id=run_id, job_id=job_id,
        CPU_variant=reference['variant'], model={k: contract[k] for k in (
            'model_id', 'revision', 'layer_id', 'framework_revision', 'official_modeling_sha256',
            'torch_version', 'numpy_version')}, binary_sha256=result['binary_sha256'],
        rtl_sha256=result['rtl_sha256'], build_ready_sha256=result['build_ready_sha256'],
        toolchain_sha256=built['toolchain.json'], official_capture_manifest_sha256=reference['official_manifest_sha256'],
        reference_receipt_sha256=result['block_reference_receipt_sha256'],
        reference_receipt_file_sha256=sha(read_bounded(fixture/'reference_receipt.json', 16*1024*1024)),
        fixture_manifest_sha256=admitted['manifest_sha256'],
        result_receipt_sha256=sha(read_bounded(build/'pass.result.json', 16*1024*1024)),
        execution_identity_sha256=sha(encoded(result['execution_identity'])),
        log_sha256=result['execution_identity']['log_sha256'],
        input_sha256=result['input_sha256'],
        retained_execution_sha256={name: result['execution_identity']['files_sha256'][name]
                                   for name in EXECUTION_PATHS},
        build_sources_manifest_sha256=built['sources.sha256.json'],
        reference_sources_sha256=sha(encoded(reference['source_sha256_before'])),
        fixture_sources_sha256=sha(encoded(admitted['source_sha256'])),
        source_files_sha256={name: admitted['source_sha256'][name] for name in SOURCE_PATHS},
        packer_sha256=sha(read_bounded(__file__, MAX_BYTES)))
    identity['model'].update(contract_sha256=sha(read_bounded(contract_path, MAX_BYTES)),
        payload_pin_sha256=sha(read_bounded(ROOT/'config/upstream/qwen3_5_0p8b/layer3_payload_pin.json', MAX_BYTES)))
    manifest = dict(schema=SCHEMA, identity=identity, pair_sha256=sha(encoded(identity)),
        launches=LAUNCHES, files=records, raw_bytes=RAW_BYTES, privacy_description=PRIVACY,
        hardware_authority_verified=False, native_full_block_acceptance=False,
        downloadable_weights_included=False,
        evidence_status='retained_bytes_only_external_CI_authentication_required')
    _check_files(manifest, files)
    raw = _zip_bytes(manifest, files)
    require(_admit_completed_case(build, fixture, result, original_commit, authorities) ==
            (admitted, built, reference), 'original execution changed during packaging')
    archive.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with archive.open('xb') as stream:
            created = True
            stream.write(raw)
        verify_pack(archive, sha(raw), expected_commit=original_commit, expected_run_id=run_id,
                    expected_job_id=job_id, expected_reference_sha256=identity['reference_receipt_sha256'])
    except BaseException:
        # Remove only the file this invocation created, never existing evidence.
        if created and archive.exists() and archive.read_bytes() == raw:
            archive.unlink()
        raise
    return dict(status='RETAINED_REPLAY_BYTES_NOT_NEW_ACCEPTANCE', archive_sha256=sha(raw),
        archive_bytes=len(raw), raw_bytes=RAW_BYTES, metadata_bytes=len(encoded(manifest)),
        pair_sha256=manifest['pair_sha256'], hardware_authority_verified=False,
        native_full_block_acceptance=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    for flag in ('sha256', 'commit', 'run-id', 'job-id', 'reference-sha256'):
        parser.add_argument('--expected-'+flag, required=True)
    args = vars(parser.parse_args())
    manifest = verify_pack(**args)
    print(json.dumps(dict(status='REPLAY_BYTES_CONSISTENT_NOT_AUTHENTICATED',
        pair_sha256=manifest['pair_sha256'], raw_bytes=manifest['raw_bytes'],
        hardware_authority_verified=False, native_full_block_acceptance=False), sort_keys=True))


if __name__ == '__main__':
    main()
