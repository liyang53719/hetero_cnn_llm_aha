"""Pure small fixtures: no source download, Torch import, or model execution."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backend_evidence', ROOT / 'scripts/qwen2_rms_backend_evidence.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def fixture_entries():
    entries, payloads = [], {}
    for name in ('Alpha.cpp', 'Beta.h'):
        raw = ('// ' + name + '\n').encode()
        entry = dict(file='work/source/' + name, source=M.BASE_URL + name, bytes=len(raw), sha256=M.digest(raw))
        entries.append(entry)
        payloads[entry['source']] = raw
    return entries, payloads


def test_published_pins_are_fixed_and_complete():
    raw, entries, backend = M.load_pins()
    assert M.digest(raw) == M.MANIFEST_SHA
    assert len(entries) == 14
    assert sum(len(caps) for caps in backend['dispatch_pointer_observations'].values()) == 24


@pytest.mark.parametrize('mutation', ['traversal', 'url', 'duplicate', 'boolean_bytes'])
def test_rejects_unsafe_source_records(mutation):
    _, entries, _ = M.load_pins()
    entries = copy.deepcopy(entries)
    if mutation == 'traversal':
        entries[0]['file'] = '../ReduceOps.cpp'
    elif mutation == 'url':
        entries[0]['source'] = 'https://example.com/' + Path(entries[0]['file']).name
    elif mutation == 'duplicate':
        entries[1] = entries[0].copy()
    else:
        entries[0]['bytes'] = True
    with pytest.raises(ValueError):
        M.validate_entries(entries)


def test_mock_restore_then_offline_verify_and_no_overwrite(tmp_path):
    entries, payloads = fixture_entries()
    manifest = json.dumps(entries).encode()
    output = tmp_path / 'sources'
    calls = []
    def fetch(entry):
        calls.append(entry['source'])
        return payloads[entry['source']]
    M.restore_sources(output, manifest, entries, fetch=fetch)
    assert len(calls) == 2
    assert len(M.verify_sources(output, manifest, entries)) == 2
    with pytest.raises(ValueError, match='existing source'):
        M.restore_sources(output, manifest, entries, fetch=lambda _: pytest.fail('must not fetch'))
    (output / 'Alpha.cpp').write_bytes(b'corruption')
    with pytest.raises(ValueError, match='bytes/hash drift'):
        M.verify_sources(output, manifest, entries)


def test_download_drift_creates_no_source_directory(tmp_path):
    entries, _ = fixture_entries()
    directory = tmp_path / 'source'
    with pytest.raises(ValueError, match='bytes/hash drift'):
        M.restore_sources(directory, b'[]', entries, fetch=lambda _: b'bad')
    assert not directory.exists()


def test_paths_reject_parent_traversal_and_symlink(tmp_path):
    with pytest.raises(ValueError, match='traversal'):
        M.safe_path(tmp_path / 'a' / '..' / 'b')
    target = tmp_path / 'target'
    target.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        M.safe_path(link / 'file')


def test_fresh_current_runtime_is_used_and_mismatches_are_visible(tmp_path, monkeypatch):
    _, _, backend = M.load_pins()
    source, package = tmp_path / 'source', tmp_path / 'torch'
    source.mkdir()
    (package / 'lib').mkdir(parents=True)
    library_bytes = b'mock library bytes\n' * 65536  # Crosses the 1 MiB hash chunk boundary.
    (package / 'lib/libtorch_cpu.so').write_bytes(library_bytes)
    for name, relative in M.HEADER_PATHS.items():
        raw = ('// mock header ' + name + '\n').encode()
        (source / name).write_bytes(raw)
        path = package / 'include' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(M.HEADER_PREFIX + raw + M.HEADER_SUFFIX)
    torch = SimpleNamespace(__file__=str(package / '__init__.py'), __version__='2.10.0+cpu',
        version=SimpleNamespace(git_version=M.COMMIT),
        backends=SimpleNamespace(cpu=SimpleNamespace(get_cpu_capability=lambda: 'AVX512')),
        get_num_threads=lambda: 3, get_num_interop_threads=lambda: 2,
        are_deterministic_algorithms_enabled=lambda: False)
    lookup = {v['symbol']: {'present': v['present'], 'non_null': v['non_null']}
              for caps in backend['dispatch_pointer_observations'].values() for v in caps.values()}
    monkeypatch.delenv('ATEN_CPU_CAPABILITY', raising=False)
    monkeypatch.setattr(M, 'cpu_model', lambda: 'Mock current CPU')
    report = M.inspect_backend(source, backend, torch, pointer_reader=lambda _, symbol: lookup[symbol], library_loader=lambda _: object())
    assert report['all_backend_checks_match']
    assert report['current_runtime']['num_threads'] == 3
    assert report['current_runtime']['cpu_model'] == 'Mock current CPU'
    assert report['current_torch_cpu_library'] == dict(file='libtorch_cpu.so',
        bytes=len(library_bytes), sha256=M.digest(library_bytes))
    assert 'torch_cpu_library' not in report
    assert all(set(v) >= {'present', 'non_null', 'matches'} for v in report['dispatch_pointer_observations'])
    lookup[next(iter(lookup))] = {'present': False, 'non_null': None}
    (package / 'include' / M.HEADER_PATHS['vml.h']).write_bytes(b'changed')
    report = M.inspect_backend(source, backend, torch, pointer_reader=lambda _, symbol: lookup[symbol], library_loader=lambda _: object())
    assert not report['all_backend_checks_match']
    assert any(not v['matches'] for v in report['dispatch_pointer_observations'])
    assert any(not h['upstream_bytes_match_installed_body'] for h in report['installed_header_observations'])


def test_report_is_exclusive_metadata_json(tmp_path):
    path = tmp_path / 'report.json'
    M.write_report(path, {'present': True, 'non_null': False})
    before = path.read_bytes()
    with pytest.raises(ValueError, match='existing metadata'):
        M.write_report(path, {'present': False})
    assert path.read_bytes() == before


def test_cli_refuses_output_inside_read_only_source(tmp_path):
    with pytest.raises(ValueError, match='outside the source'):
        M.main(['verify', '--sources', str(tmp_path), '--report', str(tmp_path / 'report.json')])
