"""Synthetic byte/identity controls only; no model, compiler, RTL, or CI."""
from pathlib import Path
import copy
import importlib.util
import io
import json
import stat
import warnings
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('replay_pack', ROOT/'tools/attention_native/pack_replay.py')
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return pack.sha(raw)


@pytest.fixture
def material(tmp_path):
    """Different actual values by phase; golden data deliberately disagrees."""
    build, fixture = tmp_path/'build', tmp_path/'fixture'
    h = dict(base=4096, scratch=8192, cache=8192, capacity=256)
    cursor, launches = h['cache']+h['capacity']*2048, []
    for index in range(2):
        spans = []
        for name, width in pack.WIDTHS.items():
            begin = (h['cache'] + (h['capacity']*1024 if name == 'cache_v' else 0) + index*1024
                     if name.startswith('cache_') else cursor)
            spans.append(dict(name=name, begin=begin, bytes=width*2))
            if not name.startswith('cache_'):
                cursor += width*2
        launches.append(dict(spans=spans))
    h['limit'] = cursor+64
    layout = dict(header=h, launches=launches)
    inputs = {}
    for phase in ('cold0', 'cold1'):
        name = phase+'_hidden.bf16le'
        raw = b'\x80\x3f'*1024
        inputs[name] = dict(bytes=len(raw), sha256=put(fixture/'input'/name, raw))
    raw = b'\x00\x3f'*(32768//2)
    inputs['trig.bf16le'] = dict(bytes=len(raw), sha256=put(fixture/'input/trig.bf16le', raw))
    for name in pack.INPUT_NAMES-set(inputs):
        inputs[name] = dict(bytes=1, sha256='a'*64)  # hashes only, never weight files
    actual, terminals, runs = {}, {}, []
    memory = bytearray(h['limit']-h['base'])
    for index, phase in enumerate(pack.PHASES):
        terminals[phase] = {}
        for span in launches[index]['spans']:
            name, size, begin = span['name'], span['bytes'], span['begin']-h['base']
            # Distinct token/head/channel and K/V values reveal layout errors.
            role = 1 if name in ('v', 'cache_v') else 0
            raw = b''.join(bytes(((j % 256 + 3*(j//256) + 17*role + 31*index) % 128, 0x3f))
                           for j in range(size//2))
            if index == 1 and name == 'input_norm':
                memory[begin:begin+size] = raw
                snapshot = bytes(memory[h['scratch']-h['base']:])
                path = phase+'/writable_after_command0.bin'
                actual[path] = put(build/'pass'/path, snapshot)
            memory[begin:begin+size] = raw
            path = phase+'/actual_'+name+'.bf16le'
            terminals[phase][name] = actual[path] = put(build/'pass'/path, raw)
        path = phase+'/ddr_after.bin'
        actual[path] = put(build/'pass'/path, bytes(memory))
        runs.append(dict(phase=phase, status=0, checkpoint_accepted=True,
            inferred_committed_length=index+1, inferred_committed_generation=index+1,
            ddr_sha256=actual[path], snapshot_sha256={} if not index else {
                'writable_after_command0.bin': actual[phase+'/writable_after_command0.bin']}))
    # This must never be used as the retained prior or final cache.
    put(fixture/'reference/cold0/cache_k.bf16le', b'\x20\x42'*512)
    result = dict(actual_sha256=terminals, runs=runs,
        execution_identity=dict(files_sha256=actual, log_sha256='b'*64),
        input_sha256={name: row['sha256'] for name, row in inputs.items()})
    admission = dict(layout=layout)
    reference = dict(inputs=inputs)
    files, records = pack._collect(build, fixture, result, admission, reference)
    identity = dict(original_commit='1'*40, run_id='100', job_id='200', CPU_variant='baseline',
        model=dict(model_id='Qwen/Qwen3.5-0.8B', revision='2'*40, layer_id=3,
            framework_revision='3'*40, contract_sha256='4'*64, payload_pin_sha256='5'*64,
            official_modeling_sha256='6'*64, torch_version='2.10.0', numpy_version='2.3.5'),
        input_sha256=result['input_sha256'], source_files_sha256={p: '7'*64 for p in pack.SOURCE_PATHS},
        retained_execution_sha256={name: actual[name] for name in pack.EXECUTION_PATHS},
        **{key: '8'*64 for key in pack.DIGEST_KEYS})
    manifest = dict(schema=pack.SCHEMA, identity=identity, pair_sha256=pack.sha(pack.encoded(identity)),
        launches=copy.deepcopy(pack.LAUNCHES), files=records, raw_bytes=pack.RAW_BYTES,
        privacy_description=pack.PRIVACY, hardware_authority_verified=False,
        native_full_block_acceptance=False, downloadable_weights_included=False,
        evidence_status='retained_bytes_only_external_CI_authentication_required')
    return dict(build=build, fixture=fixture, result=result, admission=admission,
                reference=reference, manifest=manifest, files=files)


def verify(path, raw, manifest, **overrides):
    path.write_bytes(raw)
    identity = manifest['identity']
    kwargs = dict(expected_commit=identity['original_commit'], expected_run_id=identity['run_id'],
        expected_job_id=identity['job_id'], expected_reference_sha256=identity['reference_receipt_sha256'])
    kwargs.update(overrides)
    return pack.verify_pack(path, pack.sha(raw), **kwargs)


def test_exact_small_pack_roundtrip_with_actual_readback_provenance(material, tmp_path):
    m, files = material['manifest'], material['files']
    pack._check_files(m, files)
    raw = pack._zip_bytes(m, files)
    assert len(files) == 49 and sum(map(len, files.values())) == 147712
    assert len(raw) <= 256*1024 and len(pack.encoded(m)) <= 64*1024
    assert verify(tmp_path/'pack.zip', raw, m) == m
    assert raw == pack._zip_bytes(m, files)
    prior = m['files']['cache/prior_carried1_k.bf16le']
    assert prior['source_file'] == 'carried1/writable_after_command0.bin'
    assert prior['origin'] == 'actual_ddr_after_input_norm_before_kv_append'
    assert files['cache/prior_carried1_k.bf16le'] == files['cold0/actual_rope_k.bf16le']
    assert files['cache/final_carried1_k.bf16le'] == (
        files['cold0/actual_rope_k.bf16le']+files['carried1/actual_rope_k.bf16le'])
    assert files['cache/prior_carried1_k.bf16le'] != files['cache/prior_carried1_v.bf16le']
    assert files['cache/prior_carried1_k.bf16le'][:512] != files['cache/prior_carried1_k.bf16le'][512:]
    assert not m['hardware_authority_verified'] and not m['native_full_block_acceptance']
    assert not any('weight_' in p or p.endswith('.npz') for p in files)


@pytest.mark.parametrize('kind', ['extra', 'missing', 'traversal', 'weights', 'npz', 'duplicate', 'symlink'])
def test_reject_archive_inventory_and_types(material, tmp_path, kind):
    m, files = material['manifest'], material['files']
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        manifest_entry = zipfile.ZipInfo(pack.MANIFEST)
        manifest_entry.create_system = 3
        manifest_entry.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(manifest_entry, pack.encoded(m))
        for index, name in enumerate(sorted(files)):
            raw = files[name]
            if index == 0 and kind == 'missing':
                continue
            if index == 0 and kind in ('traversal', 'weights', 'npz'):
                name = {'traversal': '../escape', 'weights': 'input/weight_q.bf16le', 'npz': 'raw.npz'}[kind]
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            if index == 0 and kind == 'symlink':
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, raw)
        if kind in ('extra', 'duplicate'):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr('extra.bin' if kind == 'extra' else next(iter(files)), b'extra')
    expected = 'nonregular/compressed/oversized archive entry' if kind == 'symlink' else 'archive file inventory'
    with pytest.raises(ValueError, match=expected):
        verify(tmp_path/'bad.zip', buffer.getvalue(), m)


@pytest.mark.parametrize('fault', ['dtype', 'shape', 'size', 'sha', 'phase', 'source', 'authority', 'privacy', 'pair'])
def test_reject_manifest_contract_drift(material, tmp_path, fault):
    m = copy.deepcopy(material['manifest'])
    row = m['files']['cold0/actual_q.bf16le']
    if fault == 'dtype': row['dtype'] = 'f32le'
    if fault == 'shape': row['shape'] = [1, 4096]
    if fault == 'size': row['bytes'] += 2
    if fault == 'sha': row['sha256'] = 'e'*64
    if fault == 'phase': m['launches'][1]['source_phase'] = 'carried1'
    if fault == 'source': row['source_file'] = 'carried1/actual_q.bf16le'
    if fault == 'authority': m['hardware_authority_verified'] = True
    if fault == 'privacy': m['privacy_description'] = 'unreviewed user prompt'
    if fault == 'pair': m['pair_sha256'] = 'e'*64
    with pytest.raises(ValueError):
        verify(tmp_path/'bad.zip', pack._zip_bytes(m, material['files']), m)


@pytest.mark.parametrize('field,value', [('expected_commit', 'f'*40), ('expected_run_id', '999'),
    ('expected_job_id', '999'), ('expected_reference_sha256', 'f'*64)])
def test_cannot_mix_original_pairs_or_reference(material, tmp_path, field, value):
    m = material['manifest']
    with pytest.raises(ValueError, match='original pair/reference'):
        verify(tmp_path/'bad.zip', pack._zip_bytes(m, material['files']), m, **{field: value})


def test_corruption_oversize_and_trailing_bytes_rejected(material, tmp_path):
    m, files = material['manifest'], material['files']
    raw = pack._zip_bytes(m, files)
    path = tmp_path/'bad.zip'
    with pytest.raises(ValueError, match='trailing'):
        verify(path, raw+b'extra', m)
    with pytest.raises(ValueError, match='bound'):
        verify(path, bytes(pack.MAX_BYTES+1), m)
    changed = dict(files)
    name = 'cold0/actual_q.bf16le'
    changed[name] = b'\x00\x00'+files[name][2:]
    with pytest.raises(ValueError, match='hash mismatch'):
        verify(path, pack._zip_bytes(m, changed), m)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match='archive digest'):
        pack.verify_pack(path, '0'*64, expected_commit='1'*40, expected_run_id='100',
                         expected_job_id='200', expected_reference_sha256='8'*64)


def test_snapshot_missing_changed_or_linked_cannot_be_replaced_by_gold(material):
    path = material['build']/'pass/carried1/writable_after_command0.bin'
    original = path.read_bytes()
    path.unlink()
    args = [material[k] for k in ('build', 'fixture', 'result', 'admission', 'reference')]
    with pytest.raises(ValueError, match='missing regular'):
        pack._collect(*args)
    path.write_bytes(b'\x02'+original[1:])
    with pytest.raises(ValueError, match='snapshot hash'):
        pack._collect(*args)
    other = path.with_suffix('.saved'); other.write_bytes(original)
    path.unlink(); path.symlink_to(other)
    with pytest.raises(ValueError, match='symlink'):
        pack._collect(*args)


def test_actual_terminal_must_match_authenticated_ddr(material):
    path = 'cold0/actual_q.bf16le'
    raw = b'\x30\x3f'*(pack.SPECS[path]['bytes']//2)
    pin = put(material['build']/'pass'/path, raw)
    result = material['result']
    result['actual_sha256']['cold0']['q'] = pin
    result['execution_identity']['files_sha256'][path] = pin
    with pytest.raises(ValueError, match='terminal differs from actual DDR'):
        pack._collect(*(material[k] for k in ('build', 'fixture', 'result', 'admission', 'reference')))


def test_same_hash_rebinding_does_not_hide_changed_prior(material):
    files, m = material['files'], material['manifest']
    name = 'cache/prior_carried1_k.bf16le'
    files[name] = b'\x03\x3f'*512
    m['files'][name]['sha256'] = pack.sha(files[name])
    with pytest.raises(ValueError, match='cache trajectory'):
        pack._check_files(m, files)


def test_slices_stream_source_identity_and_correct_offset(tmp_path):
    path = tmp_path/'snapshot.bin'
    raw = bytes(range(256))*9000
    path.write_bytes(raw)
    assert pack._slices(path, pack.sha(raw), len(raw), {'cross': (1024*1024-17, 4096)}) == {
        'cross': raw[1024*1024-17:1024*1024-17+4096]}
    with pytest.raises(ValueError, match='slice bounds'):
        pack._slices(path, pack.sha(raw), len(raw), {'bad': (-1, 4)})


def test_saved_receipts_cannot_supply_live_authority(tmp_path):
    with pytest.raises(ValueError, match='same-invocation live authorities'):
        pack._admit_completed_case(tmp_path, tmp_path, {}, '1'*40, {})
    with pytest.raises(ValueError, match='live block factory authority'):
        pack._admit_completed_case(tmp_path, tmp_path, {}, '1'*40,
            dict(block_session={}, session=None, projection_session=None, attention_session=None))


def test_archive_symlink_and_repository_output_rejected(material, tmp_path):
    m = material['manifest']; raw = pack._zip_bytes(m, material['files'])
    target = tmp_path/'target.zip'; target.write_bytes(raw)
    link = tmp_path/'link.zip'; link.symlink_to(target)
    with pytest.raises(ValueError, match='symlink'):
        pack.verify_pack(link, pack.sha(raw), expected_commit='1'*40, expected_run_id='100',
                         expected_job_id='200', expected_reference_sha256='8'*64)
    with pytest.raises(ValueError, match='ignored work'):
        pack.pack_verified_case(tmp_path, tmp_path, ROOT/'bad.zip', result={},
            original_commit='1'*40, run_id='100', job_id='200', authorities={})
    with pytest.raises(ValueError, match='path traversal'):
        pack.pack_verified_case(tmp_path, tmp_path, ROOT/'work/../bad.zip', result={},
            original_commit='1'*40, run_id='100', job_id='200', authorities={})


@pytest.mark.parametrize('state', ['missing_root', 'existing_root', 'symlink_root',
                                  'file_root', 'existing_archive_directory'])
def test_archive_must_be_a_file_below_a_real_work_directory(tmp_path, monkeypatch, state):
    repo = tmp_path/'repo'; repo.mkdir()
    work = repo/'work'
    archive = work
    reason = 'proper descendant'
    if state == 'existing_root':
        work.mkdir(); reason = 'fresh nonsymlink'
    elif state == 'symlink_root':
        target = tmp_path/'outside'; target.mkdir()
        work.symlink_to(target, target_is_directory=True)
        archive = work/'replay.zip'; reason = 'fresh nonsymlink'
    elif state == 'file_root':
        work.write_bytes(b'original file')
        archive = work/'replay.zip'; reason = 'ancestors must be directories'
    elif state == 'existing_archive_directory':
        archive = work/'replay.zip'; archive.mkdir(parents=True)
        reason = 'fresh nonsymlink'
    monkeypatch.setattr(pack, 'ROOT', repo)
    monkeypatch.setattr(pack, '_admit_completed_case', lambda *a: pytest.fail('unexpected live admission'))
    with pytest.raises(ValueError, match=reason):
        pack.pack_verified_case(tmp_path, tmp_path, archive, result={},
            original_commit='1'*40, run_id='100', job_id='200', authorities={})
    if state == 'missing_root':
        assert not work.exists()  # Never create a Git-visible file named "work".
    if state == 'file_root':
        assert work.read_bytes() == b'original file'


def test_cli_verifies_only_and_never_calls_live_wrapper(material, tmp_path, monkeypatch, capsys):
    m = material['manifest']; path = tmp_path/'pack.zip'; raw = pack._zip_bytes(m, material['files'])
    path.write_bytes(raw)
    monkeypatch.setattr(pack, '_admit_completed_case', lambda *a: pytest.fail('unexpected live work'))
    monkeypatch.setattr('sys.argv', ['pack_replay.py', str(path), '--expected-sha256', pack.sha(raw),
        '--expected-commit', '1'*40, '--expected-run-id', '100', '--expected-job-id', '200',
        '--expected-reference-sha256', '8'*64])
    pack.main()
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'REPLAY_BYTES_CONSISTENT_NOT_AUTHENTICATED'
    assert not result['hardware_authority_verified'] and not result['native_full_block_acceptance']


def test_metadata_budget_and_changed_execution_source_rejected(material, monkeypatch):
    m = copy.deepcopy(material['manifest'])
    m['files']['cache/prior_carried1_k.bf16le']['source_sha256'] = '0'*64
    with pytest.raises(ValueError, match='original execution identity'):
        pack._check_files(m, material['files'])
    monkeypatch.setattr(pack, 'MAX_METADATA_BYTES', len(pack.encoded(material['manifest']))-1)
    with pytest.raises(ValueError, match='metadata byte budget'):
        pack._check_files(material['manifest'], material['files'])


@pytest.mark.parametrize('drift', [False, True])
def test_future_sealing_hook_with_synthetic_authority_adapter(material, tmp_path, monkeypatch, drift):
    """Exercise assembly/publication; adapter is explicitly not a real live run."""
    repo = tmp_path/'repo'
    config = 'config/upstream/qwen3_5_0p8b/'
    for name in ('layer3_bf16_contract.json', 'layer3_payload_pin.json'):
        put(repo/config/name, (ROOT/config/name).read_bytes())
    contract = json.loads((repo/config/'layer3_bf16_contract.json').read_bytes())
    m = material['manifest']; result = material['result']
    result.update(binary_sha256='8'*64, rtl_sha256='8'*64, build_ready_sha256='8'*64,
                  block_reference_receipt_sha256='8'*64)
    put(material['build']/'pass.result.json', pack.encoded(result))
    admitted = material['admission']
    admitted.update(manifest_sha256='8'*64, source_sha256=m['identity']['source_files_sha256'])
    reference = material['reference']
    reference.update(model_revision=contract['revision'], variant='baseline',
        official_manifest_sha256='8'*64, source_sha256_before={'source.py': '9'*64})
    put(material['fixture']/'reference_receipt.json', pack.encoded(reference))
    built = {'toolchain.json': '8'*64, 'sources.sha256.json': '8'*64}
    calls = []
    def admit(*args):
        calls.append(args)
        if drift and len(calls) == 2:
            return dict(admitted, manifest_sha256='a'*64), built, reference
        return admitted, built, reference
    monkeypatch.setattr(pack, '_admit_completed_case', admit)
    monkeypatch.setattr(pack, 'ROOT', repo)
    path = repo/'work/replay.zip'
    kwargs = dict(result=result, original_commit='1'*40, run_id='100', job_id='200', authorities={})
    if drift:
        with pytest.raises(ValueError, match='changed during packaging'):
            pack.pack_verified_case(material['build'], material['fixture'], path, **kwargs)
        assert not path.exists()
    else:
        receipt = pack.pack_verified_case(material['build'], material['fixture'], path, **kwargs)
        assert receipt['raw_bytes'] == 147712 and receipt['archive_bytes'] == path.stat().st_size
        assert receipt['archive_bytes'] <= 256*1024
        assert not receipt['hardware_authority_verified'] and not receipt['native_full_block_acceptance']
        manifest = pack.verify_pack(path, receipt['archive_sha256'], expected_commit='1'*40,
            expected_run_id='100', expected_job_id='200', expected_reference_sha256='8'*64)
        assert manifest['identity']['reference_receipt_file_sha256'] == pack.sha(
            (material['fixture']/'reference_receipt.json').read_bytes())
    assert len(calls) == 2
