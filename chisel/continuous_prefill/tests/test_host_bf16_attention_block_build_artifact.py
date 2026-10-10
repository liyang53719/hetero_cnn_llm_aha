"""Synthetic transfer controls: no model, compiler, Java or simulator execution."""
from pathlib import Path
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import host_bf16_attention_block_build_artifact as artifact
import host_bf16_qkv_execution as execution
import real2_ci
import run_host_bf16_qkv_fresh_gate as checkout


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else artifact.encoded(data))


def commit_repo(path):
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Transfer Test',
                    '-c', 'user.email=transfer@example.invalid', 'commit', '-qm', 'synthetic control'], check=True)
    return real2_ci.git_commit(path)


@pytest.fixture
def control(tmp_path, monkeypatch):
    root, build = tmp_path/'repo', tmp_path/'build'
    write(root/'source.py', b'# public control source\n')
    verifier = 'chisel/continuous_prefill/scripts/production_source_identity.py'
    write(root/verifier, (SCRIPTS/'production_source_identity.py').read_bytes())
    commit = commit_repo(root)
    sources = {name: artifact.sha(root/name) for name in ('source.py', verifier)}
    hf = tmp_path/'hardfloat'
    hf_name = 'hardfloat/src/main/scala/Control.scala'
    write(hf/hf_name, b'// synthetic public HardFloat source\n')
    commit_repo(hf)
    hardfloat = {hf_name: artifact.sha(hf/hf_name)}
    # Only the upstream commit marker is synthetic. Source files, clean Git
    # state, manifests and all existing live/source verifiers remain real.
    original_git_commit = real2_ci.git_commit
    monkeypatch.setattr(real2_ci, 'git_commit', lambda path:
                        real2_ci.HF_PIN if Path(path) == hf else original_git_commit(path))
    monkeypatch.setattr(artifact, 'ROOT', root)
    monkeypatch.setattr(artifact.live, 'ROOT', root)
    monkeypatch.setattr(execution, 'ROOT', root)
    monkeypatch.setattr(checkout, 'ROOT', root)
    monkeypatch.setattr(checkout, '_git_head', lambda: original_git_commit(root))
    monkeypatch.setattr(artifact.live.fixture, 'source_identity', lambda: sources)
    monkeypatch.setenv('GITHUB_SHA', commit)
    monkeypatch.setenv('HARDFLOAT_SOURCE', str(hf))
    tools = {}
    for name in ('verilator_launcher', 'verilator_backend', 'firtool', 'java', 'cxx'):
        path = tmp_path/'tools'/name
        write(path, (b'\x7fELF' if name == 'verilator_backend' else b'#') + b' CONTROL ONLY; DO NOT EXECUTE\n')
        version = 'Verilator 5.032' if 'verilator' in name else 'firtool 1.62.1' if name == 'firtool' else 'control'
        tools[name] = dict(path=str(path), sha256=artifact.sha(path), version=version)
    actual = dict(entrypoint=dict(tools['verilator_backend'], kind='ELF'),
                  actual_elf=dict(tools['verilator_backend'], kind='ELF'))
    runtime = tmp_path/'runtime'
    jar_name = 'https/repo1.maven.org/maven2/org/control/compiler/1/compiler-1.jar'
    write(runtime/'jars'/jar_name, b'public compiler cache control\n')
    jars = {jar_name: artifact.sha(runtime/'jars'/jar_name)}
    monkeypatch.setenv('OFFLINE_TOOLS', str(runtime))
    idma = tmp_path/'idma'
    write(idma/'rtl/idma.sv', b'// public iDMA control\n')
    monkeypatch.setenv('IDMA_EXPORT', str(idma))
    toolchain = dict(tools=tools, compiler_jars_sha256=jars, compiler_jars_verified_after_build=True,
                     hardfloat_source_sha256=hardfloat, idma_identity={'control_only': True},
                     idma_export_source_sha256={'rtl/idma.sv': artifact.sha(idma/'rtl/idma.sv')})
    scope = dict(scope=artifact.live.SCOPE, attention_block_policy_version=3, default_enabled=False,
                 input_norm_dut=True, sigmoid_gate_dut=True, output_projection_dut=True, ffn_supported=True,
                 full_block_supported=True, numerical_acceptance=False, fault_restore_supported=False,
                 full_m128_supported=False, max_declared_rows=128, active_tokens_supported=1, max_cache_tokens=256,
                 logical_matrix_engines=1, physical_matrix_slices=8, pinned_idma_instances=1, scalar_service_shared=True)
    payload = {'obj/VHostBlockTop': b'\x7fELF SYNTHETIC CONTROL; NEVER RUN\n',
               'generated/HostBlockTop.sv': b'// synthetic generated RTL\n',
               'generated/SCOPE.json': scope, 'source_base_commit.txt': (commit+'\n').encode(),
               'build.exit': b'0\n', 'initial_verilation.exit': b'0\n',
               'sources.sha256.json': sources, 'hardfloat.sha256.json': hardfloat,
               'source_scope.json': {'scope': 'full', 'unrelated_helpers_bound': True},
               'compiler_jars.sha256.json': jars, 'toolchain.json': toolchain,
               'idma_identity.json': toolchain['idma_identity'],
               'actual_verilator_before.json': actual, 'actual_verilator_after.json': actual}
    for name, data in payload.items():
        write(build/name, data)
    (build/'obj/VHostBlockTop').chmod(0o755)
    names = {'obj/VHostBlockTop': 'binary_sha256', 'generated/HostBlockTop.sv': 'rtl_sha256',
             'sources.sha256.json': 'source_manifest_sha256', 'generated/SCOPE.json': 'scope_sha256',
             'toolchain.json': 'toolchain_sha256', 'actual_verilator_after.json': 'actual_verilator_sha256',
             'compiler_jars.sha256.json': 'compiler_jars_sha256', 'hardfloat.sha256.json': 'hardfloat_manifest_sha256'}
    ready = dict(status=artifact.live.BUILD_STATUS, numerical_pass=False, source_base_commit=commit,
                 hardfloat_source=str(hf), initial_verilation_exit=0, actual_verilator=actual)
    ready.update({key: artifact.sha(build/name) for name, key in names.items()})
    write(build/'build_ready.json', ready)
    return SimpleNamespace(root=root, build=build, commit=commit, sources=sources, hf=hf, idma=idma,
                           runtime=runtime, tools=tools, ready=ready,
                           archive=tmp_path/'build.tar.gz', destination=tmp_path/'restored')


def sealed(control):
    return artifact.seal(control.build, control.archive, control.commit)


def changed_archive(control, *, extra=None, change_manifest=None, omit=None, change_file=None):
    path = control.archive.with_name('changed.tar.gz')
    with tarfile.open(control.archive, 'r:gz') as source, \
            tarfile.open(path, 'w:gz', format=tarfile.USTAR_FORMAT) as destination:
        for entry in source:
            if entry.name == omit:
                continue
            data = source.extractfile(entry).read()
            if entry.name == artifact.MANIFEST and change_manifest:
                manifest = json.loads(data)
                change_manifest(manifest)
                data = artifact.encoded(manifest)
            if change_file:
                entry, data = change_file(entry, data)
            entry.size = len(data)
            destination.addfile(entry, io.BytesIO(data))
        if extra is not None:
            destination.addfile(extra, io.BytesIO(b'x') if extra.isreg() else None)
    return path


def reject(control, archive, *, digest=None, commit=None, match=None):
    with pytest.raises(ValueError, match=match):
        artifact.restore(archive, control.destination, digest or artifact.sha(archive), commit or control.commit)
    assert not control.destination.exists()
    assert not list(control.destination.parent.glob('.attention-build-*'))


def test_roundtrip_uses_original_live_identity_without_compilation(control, monkeypatch):
    # Only Git reads and the real Python source verifier run during transfer.
    original_run = subprocess.run
    commands = []
    def guarded_run(argv, **kwargs):
        assert argv[0] == 'git' or (argv[0] == sys.executable and Path(argv[1]).name == 'production_source_identity.py')
        if argv[0] != 'git':
            commands.append(argv)
        return original_run(argv, **kwargs)
    monkeypatch.setattr(subprocess, 'run', guarded_run)
    before = artifact.live.build_identity(control.build, control.sources)
    receipt = sealed(control)
    received = artifact.restore(control.archive, control.destination, receipt['package_sha256'], control.commit)
    assert received == receipt and received['numerical_pass'] is False
    assert received['status'] == artifact.live.BUILD_STATUS
    assert artifact.live.build_identity(control.destination, control.sources) == before
    assert {str(path.relative_to(control.destination)) for path in control.destination.rglob('*') if path.is_file()} == artifact.FILES | {artifact.MANIFEST}
    artifact.live.verify_all_build_sources(control.destination)
    assert (control.destination/'final_source_verify.log').read_text().strip() == 'SOURCE_IMMUTABILITY_PASS'
    assert len(commands) == 4
    for name in artifact.FILES | {artifact.MANIFEST}:
        assert (control.destination/name).stat().st_mode & 0o777 == (0o555 if name == 'obj/VHostBlockTop' else 0o444)
    assert not any(path.suffix in ('.jar', '.npz', '.bin', '.bf16le') for path in control.destination.rglob('*'))


@pytest.mark.parametrize('kind', ['sha', 'commit'])
def test_independent_trusted_sha_and_source_commit_required(control, kind):
    receipt = sealed(control)
    reject(control, control.archive, digest='0'*64 if kind == 'sha' else receipt['package_sha256'],
           commit='f'*40 if kind == 'commit' else control.commit,
           match='digest differs|commit/schema')


@pytest.mark.parametrize('name,kind', [('../outside', tarfile.REGTYPE), ('/outside', tarfile.REGTYPE),
    ('obj//hidden', tarfile.REGTYPE), ('link', tarfile.SYMTYPE), ('hardlink', tarfile.LNKTYPE),
    ('device', tarfile.CHRTYPE), ('directory', tarfile.DIRTYPE),
    ('toolchain.json', tarfile.REGTYPE), ('weights.npz', tarfile.REGTYPE),
    ('actual_tensor.bf16le', tarfile.REGTYPE), ('unexpected_receipt.json', tarfile.REGTYPE)])
def test_unsafe_links_duplicate_tensor_and_unexpected_entries_never_extract(control, name, kind):
    sealed(control)
    extra = tarfile.TarInfo(name)
    extra.type, extra.mode = kind, 0o644
    extra.size = int(kind == tarfile.REGTYPE)
    extra.linkname = '../outside' if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ''
    reject(control, changed_archive(control, extra=extra))


@pytest.mark.parametrize('name', sorted(artifact.FILES))
def test_every_required_file_is_mandatory(control, name):
    sealed(control)
    reject(control, changed_archive(control, omit=name), match='incomplete')


@pytest.mark.parametrize('change', [
    lambda m: m.update(numerical_pass=True), lambda m: m.update(status='PASS'),
    lambda m: m.update(schema=True), lambda m: m.update(scope='GDN'),
    lambda m: m.update(hidden_tensor=[1, 2]),
    lambda m: m['files']['toolchain.json'].update(sha256='f'*64),
    lambda m: m['files']['toolchain.json'].update(bytes=artifact.MAX_BYTES+1),
    lambda m: m['sources'].update({'../outside': 'f'*64}),
    lambda m: m['files'].update({'weights.npz': {'bytes': 1, 'sha256': 'f'*64}}),
])
def test_forged_manifest_cannot_change_profile_pass_bounds_or_allowlist(control, change):
    sealed(control)
    reject(control, changed_archive(control, change_manifest=change))


def test_duplicate_json_keys_rejected(control):
    sealed(control)
    def duplicate(entry, data):
        if entry.name == artifact.MANIFEST:
            data = data.replace(b'"schema": 1', b'"schema": 1, "schema": 1')
        return entry, data
    reject(control, changed_archive(control, change_file=duplicate), match='duplicate JSON')


@pytest.mark.parametrize('count', [1, 8, 100])
def test_truncated_archive_rejected_even_with_recomputed_digest(control, count):
    sealed(control)
    truncated = control.archive.with_name('truncated.tar.gz')
    truncated.write_bytes(control.archive.read_bytes()[:-count])
    reject(control, truncated, match='truncated')


def test_concatenated_gzip_members_are_also_inspected(control):
    sealed(control)
    extra = io.BytesIO()
    with tarfile.open(fileobj=extra, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        entry = tarfile.TarInfo('weights.npz'); entry.size = 1; entry.mode = 0o644
        archive.addfile(entry, io.BytesIO(b'x'))
    path = control.archive.with_name('concatenated.tar.gz')
    path.write_bytes(control.archive.read_bytes() + gzip.compress(extra.getvalue()))
    reject(control, path)


def test_recompressed_tar_with_missing_terminator_is_truncated(control):
    sealed(control)
    with tarfile.open(control.archive, 'r:gz') as archive:
        last = archive.getmembers()[-1]
        end = last.offset_data + (last.size + 511) // 512 * 512
    path = control.archive.with_name('missing-terminator.tar.gz')
    path.write_bytes(gzip.compress(gzip.decompress(control.archive.read_bytes())[:end]))
    reject(control, path, match='truncated tar terminator')


def test_decompressed_padding_is_bounded(control, monkeypatch):
    sealed(control)
    monkeypatch.setattr(real2_ci, 'MAX_BYTES', 1024)
    path = control.archive.with_name('padding.tar.gz')
    path.write_bytes(control.archive.read_bytes() + gzip.compress(b'\0'*(1024*1024+2048)))
    reject(control, path, match='decompressed archive exceeds')


@pytest.mark.parametrize('name', ['obj/VHostBlockTop', 'generated/HostBlockTop.sv', 'toolchain.json'])
def test_payload_content_drift_fails_before_extract(control, name):
    sealed(control)
    def drift(entry, data):
        return entry, data[:-1]+b'!' if entry.name == name else data
    reject(control, changed_archive(control, change_file=drift), match='digest mismatch')


@pytest.mark.parametrize('mode', [0o644, 0o777, 0o4755])
def test_noncanonical_elf_permissions_rejected(control, mode):
    sealed(control)
    def change(entry, data):
        if entry.name == 'obj/VHostBlockTop':
            entry.mode = mode
        return entry, data
    reject(control, changed_archive(control, change_file=change), match='permissions')


@pytest.mark.parametrize('change', ['source', 'hf', 'jar', 'tool', 'idma', 'hardfloat_path'])
def test_receiver_must_readmit_unchanged_sources_tools_jars_and_external_paths(control, monkeypatch, change):
    sealed(control)
    if change == 'hardfloat_path':
        monkeypatch.setenv('HARDFLOAT_SOURCE', str(control.hf.parent/'other'))
    else:
        paths = {'source': control.root/'source.py', 'hf': next(control.hf.rglob('*.scala')),
                 'jar': next(control.runtime.rglob('*.jar')), 'tool': Path(control.tools['java']['path']),
                 'idma': control.idma/'rtl/idma.sv'}
        paths[change].write_bytes(b'CHANGED')
    reject(control, control.archive)


def test_missing_reacquired_compiler_jar_fails_without_rebuild(control):
    sealed(control)
    next(control.runtime.rglob('*.jar')).unlink()
    reject(control, control.archive)


def test_receiver_rejects_untracked_checkout_source(control):
    sealed(control)
    (control.root/'untracked.py').write_text('# unexpected source\n')
    reject(control, control.archive, match='clean tracked/index/untracked')


def test_external_hardfloat_pin_is_not_replaced_by_archive_trust(control, monkeypatch):
    sealed(control)
    monkeypatch.setattr(real2_ci, 'git_commit', lambda path: 'f'*40)
    reject(control, control.archive, match='HardFloat pin drift')


def test_source_map_cannot_omit_live_source_dependencies(control):
    sources = dict(control.sources)
    sources.pop('source.py')
    write(control.build/'sources.sha256.json', sources)
    control.ready['source_manifest_sha256'] = artifact.sha(control.build/'sources.sha256.json')
    write(control.build/'build_ready.json', control.ready)
    with pytest.raises(ValueError, match='incomplete live source closure'):
        sealed(control)
    assert not control.archive.exists()


@pytest.mark.parametrize('change', ['missing', 'elf_magic', 'nonexecutable', 'scope', 'source_commit', 'failed'])
def test_seal_rejects_unfinished_rebound_or_invalid_build(control, change):
    if change == 'missing':
        (control.build/'idma_identity.json').unlink()
    elif change == 'elf_magic':
        (control.build/'obj/VHostBlockTop').write_bytes(b'fake')
        control.ready['binary_sha256'] = artifact.sha(control.build/'obj/VHostBlockTop')
        write(control.build/'build_ready.json', control.ready)
    elif change == 'nonexecutable':
        (control.build/'obj/VHostBlockTop').chmod(0o644)
    elif change == 'scope':
        write(control.build/'source_scope.json', {'scope': 'legacy_host_gate', 'unrelated_helpers_bound': False})
    elif change == 'source_commit':
        control.ready['source_base_commit'] = 'f'*40
        write(control.build/'build_ready.json', control.ready)
    else:
        (control.build/'build.exit').write_text('1\n')
    with pytest.raises(ValueError):
        sealed(control)
    assert not control.archive.exists()


def test_archive_and_destination_cannot_overwrite_or_use_symlink_parents(control):
    receipt = sealed(control)
    with pytest.raises(ValueError, match='overwrite'):
        sealed(control)
    control.destination.mkdir()
    with pytest.raises(ValueError, match='overwrite'):
        artifact.restore(control.archive, control.destination, receipt['package_sha256'], control.commit)
    link = control.destination.parent/'link'; link.symlink_to(control.destination, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        artifact.restore(control.archive, link/'child', receipt['package_sha256'], control.commit)


def test_unallowlisted_local_build_payload_is_never_uploaded(control):
    write(control.build/'private/weights.npz', b'NOT UPLOADABLE')
    receipt = sealed(control)
    manifest = artifact._read_archive(control.archive, receipt['package_sha256'], control.commit)
    assert set(manifest['files']) == artifact.FILES


class MavenResponse(io.BytesIO):
    def __init__(self, data, url, *, length=True, status=200):
        super().__init__(data)
        self.url, self.status = url, status
        self.headers = {'Content-Length': str(len(data))} if length else {}

    def geturl(self):
        return self.url


@pytest.fixture
def compiler_download(control, monkeypatch):
    rows = artifact.read_json(control.build/'compiler_jars.sha256.json')
    existing = next(iter(rows))
    bridge = artifact.MAVEN_PREFIX+'org/scala-lang/scala2-sbt-bridge/2.13.16/scala2-sbt-bridge-2.13.16.jar'
    data = {existing: (control.runtime/'jars'/existing).read_bytes(),
            bridge: b'synthetic public compiler bridge; never execute\n'}
    rows[bridge] = hashlib.sha256(data[bridge]).hexdigest()
    write(control.runtime/'jars'/bridge, data[bridge])
    write(control.build/'compiler_jars.sha256.json', rows)
    toolchain = artifact.read_json(control.build/'toolchain.json')
    toolchain['compiler_jars_sha256'] = rows
    write(control.build/'toolchain.json', toolchain)
    control.ready.update(compiler_jars_sha256=artifact.sha(control.build/'compiler_jars.sha256.json'),
                         toolchain_sha256=artifact.sha(control.build/'toolchain.json'))
    write(control.build/'build_ready.json', control.ready)
    receipt = sealed(control)
    calls = []
    def fetch(url, timeout):
        calls.append((url, timeout))
        key = 'https/'+url[len('https://'):]
        return MavenResponse(data[key], url)
    monkeypatch.setattr(artifact, '_open_maven', fetch)
    runtime = control.runtime.with_name('received-runtime')
    def prepare():
        return artifact.prepare_compiler_jars(control.archive, runtime, receipt['package_sha256'], control.commit)
    return SimpleNamespace(control=control, runtime=runtime, data=data, rows=rows, calls=calls,
                           receipt=receipt, prepare=prepare, fetch=fetch)


def no_published_jars(download):
    assert not download.runtime.exists() or not any(path.is_file() for path in download.runtime.rglob('*'))
    assert not list(download.runtime.parent.glob('.attention-jars-*'))


def test_prepare_exact_jars_then_existing_restore_rechecks_them(compiler_download, monkeypatch):
    download = compiler_download
    report = download.prepare()
    assert report['downloaded_files'] == report['jar_count'] == 2 and report['reused_files'] == 0
    assert report['total_bytes'] == sum(map(len, download.data.values()))
    assert all(url.startswith('https://repo1.maven.org/maven2/') and 0 < timeout <= 30
               for url, timeout in download.calls)
    for name, data in download.data.items():
        path = download.runtime/'jars'/name
        assert path.read_bytes() == data and path.stat().st_nlink == 1
        assert path.stat().st_mode & 0o777 == 0o444
    download.calls.clear()
    reused = download.prepare()
    assert reused['downloaded_files'] == 0 and reused['reused_files'] == 2 and download.calls == []
    monkeypatch.setenv('OFFLINE_TOOLS', str(download.runtime))
    control = download.control
    assert artifact.restore(control.archive, control.destination, download.receipt['package_sha256'], control.commit) == download.receipt


def test_prepare_jars_reuses_partial_correct_cache(compiler_download):
    download = compiler_download
    name = next(iter(download.data))
    write(download.runtime/'jars'/name, download.data[name])
    report = download.prepare()
    assert report['reused_files'] == report['downloaded_files'] == 1
    assert len(download.calls) == 1


@pytest.mark.parametrize('name', ['http/repo1.maven.org/maven2/a.jar',
    'https/repo.maven.apache.org/maven2/a.jar', 'https/evil.invalid/maven2/a.jar',
    'https/repo1.maven.org/maven2x/a.jar', 'file/etc/a.jar',
    'https/repo1.maven.org/maven2/a/../b.jar', 'https/repo1.maven.org/maven2/%2e%2e/a.jar',
    'https/repo1.maven.org/maven2/a.jar?secret=1', 'https/repo1.maven.org/maven2/a.jar#x',
    'https/repo1.maven.org@maven.evil/maven2/a.jar', 'https/repo1.maven.org/maven2/a.zip'])
def test_compiler_receipt_origin_scheme_and_encoded_paths_are_narrow(name):
    with pytest.raises(ValueError):
        artifact._jar_url(name)


def test_untrusted_compiler_map_rejected_before_any_network(compiler_download, monkeypatch):
    download = compiler_download
    path = changed_archive(download.control)
    # The archive must be fully authenticated before even one public download.
    with pytest.raises(ValueError, match='digest differs'):
        artifact.prepare_compiler_jars(path, download.runtime, 'f'*64, download.control.commit)
    assert download.calls == []
    no_published_jars(download)


def test_authenticated_compiler_map_with_wrong_origin_never_downloads(compiler_download):
    download = compiler_download
    data = artifact.encoded({'https/evil.invalid/maven2/compiler.jar': 'f'*64})
    def manifest(value):
        value['files']['compiler_jars.sha256.json'] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    def contents(entry, original):
        return entry, data if entry.name == 'compiler_jars.sha256.json' else original
    path = changed_archive(download.control, change_manifest=manifest, change_file=contents)
    with pytest.raises(ValueError, match='origin/path'):
        artifact.prepare_compiler_jars(path, download.runtime, artifact.sha(path), download.control.commit)
    assert download.calls == []
    no_published_jars(download)


@pytest.mark.parametrize('invalid', ['missing_entry', 'wrong_commit', 'dirty_checkout'])
def test_complete_archive_and_source_admission_precede_jar_downloads(compiler_download, invalid):
    download = compiler_download
    archive, commit = download.control.archive, download.control.commit
    if invalid == 'missing_entry':
        archive = changed_archive(download.control, omit='generated/HostBlockTop.sv')
    elif invalid == 'wrong_commit':
        commit = 'f'*40
    else:
        (download.control.root/'source.py').write_text('# changed before download\n')
    with pytest.raises(ValueError):
        artifact.prepare_compiler_jars(archive, download.runtime, artifact.sha(archive), commit)
    assert download.calls == []
    no_published_jars(download)


def test_redirect_handler_rejects_before_a_second_origin_is_opened():
    with pytest.raises(ValueError, match='redirect'):
        artifact._NoRedirect().redirect_request(None, None, 302, 'redirect', {}, 'https://evil.invalid/a.jar')


@pytest.mark.parametrize('kind', ['wrong_hash', 'network', 'oversize_header', 'oversize_stream',
                                  'redirected', 'timeout', 'total_bytes', 'count'])
def test_prepare_download_failure_leaves_no_runtime_payload(compiler_download, monkeypatch, kind):
    download = compiler_download
    if kind == 'count':
        monkeypatch.setattr(artifact, 'MAX_JARS', 1)
    if kind == 'total_bytes':
        monkeypatch.setattr(artifact, 'MAX_JAR_TOTAL_BYTES', 1)
    if kind == 'timeout':
        monkeypatch.setattr(artifact, 'JAR_TOTAL_TIMEOUT_SECONDS', 0)
    def fetch(url, timeout):
        if kind == 'network':
            raise OSError('synthetic network failure')
        data = download.data['https/'+url[len('https://'):]]
        response = MavenResponse(b'wrong bytes' if kind == 'wrong_hash' else data,
                                 'https://evil.invalid/a.jar' if kind == 'redirected' else url,
                                 length=kind != 'oversize_stream')
        if kind == 'oversize_header':
            response.headers['Content-Length'] = str(artifact.MAX_JAR_BYTES+1)
        return response
    if kind == 'oversize_stream':
        monkeypatch.setattr(artifact, 'MAX_JAR_BYTES', 1)
    monkeypatch.setattr(artifact, '_open_maven', fetch)
    with pytest.raises((ValueError, OSError)):
        download.prepare()
    no_published_jars(download)


def test_later_download_failure_does_not_publish_earlier_verified_jar(compiler_download, monkeypatch):
    download = compiler_download
    count = 0
    def fetch(url, timeout):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError('second artifact unavailable')
        return download.fetch(url, timeout)
    monkeypatch.setattr(artifact, '_open_maven', fetch)
    with pytest.raises(OSError):
        download.prepare()
    assert count == 2
    no_published_jars(download)


def test_wrong_existing_cache_fails_without_download_or_replacement(compiler_download):
    download = compiler_download
    name = next(iter(download.data))
    path = download.runtime/'jars'/name
    write(path, b'wrong existing cache')
    with pytest.raises(ValueError, match='existing compiler JAR cache digest mismatch'):
        download.prepare()
    assert path.read_bytes() == b'wrong existing cache' and download.calls == []


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_existing_jar_cache_links_are_rejected(compiler_download, kind):
    download = compiler_download
    name = next(iter(download.data))
    path = download.runtime/'jars'/name
    path.parent.mkdir(parents=True)
    source = download.control.runtime/'jars'/name
    if kind == 'symlink':
        path.symlink_to(source)
    else:
        path.hardlink_to(source)
    with pytest.raises(ValueError, match='link'):
        download.prepare()
    assert download.calls == []


def test_archive_changed_during_download_never_publishes_jars(compiler_download, monkeypatch):
    download = compiler_download
    def fetch(url, timeout):
        archive = download.control.archive
        archive.chmod(0o644)
        with archive.open('ab') as stream:
            stream.write(b'changed')
        return download.fetch(url, timeout)
    monkeypatch.setattr(artifact, '_open_maven', fetch)
    with pytest.raises(ValueError, match='archive changed'):
        download.prepare()
    no_published_jars(download)


def test_source_changed_during_download_never_publishes_jars(compiler_download, monkeypatch):
    download = compiler_download
    def fetch(url, timeout):
        (download.control.root/'source.py').write_text('# changed during download\n')
        return download.fetch(url, timeout)
    monkeypatch.setattr(artifact, '_open_maven', fetch)
    with pytest.raises(ValueError, match='clean tracked/index/untracked'):
        download.prepare()
    no_published_jars(download)


def test_prepare_jars_cli_has_same_independent_trust_inputs(compiler_download, capsys):
    download = compiler_download
    artifact.main(['--prepare-jars', '--archive', str(download.control.archive),
                   '--runtime', str(download.runtime), '--expected-sha256', download.receipt['package_sha256'],
                   '--expected-commit', download.control.commit])
    report = json.loads(capsys.readouterr().out)
    assert report['package_sha256'] == download.receipt['package_sha256'] and report['jar_count'] == 2
