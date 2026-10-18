"""Fixed M128 metadata replay; eight pinned source modules, no tensor payloads."""
import argparse
import builtins
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types

HERE = Path(__file__).resolve().parent
STDLIB = frozenset(('__future__', 'argparse', 'collections', 'copy', 'dataclasses',
                   'enum', 'hashlib', 'json', 'math', 'numbers', 'pathlib', 're',
                   'shutil', 'struct', 'typing'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def relative(value):
    require(isinstance(value, str) and value and '\\' not in value
            and not value.startswith('/') and all(x not in ('', '.', '..')
            for x in value.split('/')), 'unsafe relative source path')
    return Path(value)


def module(name, path, source_key, expected, importer):
    # Same minimal pattern as source recovery test_recovery.py: the exact buffer
    # hashed below is compiled. No importlib loader, second read or pyc lookup.
    raw = path.read_bytes()
    require(digest(raw) == expected, 'project source bytes differ before execution: ' + source_key)
    result = types.ModuleType(name)
    result.__file__ = str(path.resolve())
    result.__package__ = name.rpartition('.')[0]
    result.__builtins__ = dict(vars(builtins), __import__=importer)
    sys.modules[name] = result
    try:
        exec(compile(raw, source_key, 'exec', dont_inherit=True), result.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return result


class FixedPathRequest:
    """Only the two known packer insert requests are suppressed and recorded."""
    def __init__(self, root):
        self.expected = str(root / 'src')
        self.requests = []

    def insert(self, index, value):
        require(type(index) is int and index == 0 and value == self.expected,
                'unexpected project sys.path request')
        self.requests.append({'index': 0, 'relative_path': 'src', 'applied': False})


def fixed_importer(loaded, path_requests):
    # A finite routing shim, not a general package finder or a hostile-code
    # sandbox. Original trusted source is unchanged; the original top-level
    # sys.path insertion is intentionally NOT given its normal global meaning.
    local_sys = types.SimpleNamespace(path=path_requests)

    def imports(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split('.')[0] in ('numpy', 'torch'):
            raise ImportError('metadata-only replay forbids numerical library: ' + name)
        if level:
            require(level == 1 and globals.get('__package__') == 'heteronpu',
                    'unexpected relative project import')
            name = 'heteronpu.' + name
        if name == 'sys':
            return local_sys
        if name in loaded:
            require(bool(fromlist), 'unexpected project package import form')
            return loaded[name]
        if name == 'heteronpu' or name.startswith('heteronpu.'):
            raise ImportError('unlisted or unordered project import: ' + name)
        if name.split('.')[0] not in STDLIB:
            raise ImportError('not an allowed stdlib import: ' + name)
        return builtins.__import__(name, globals, locals, fromlist, 0)
    return imports


def no_numeric_modules():
    require(not any(n.split('.')[0] in ('numpy', 'torch') for n in sys.modules),
            'numerical library already imported')


def layout(manifest, cb, db):
    """Project existing fields, using fixture.py's four-region integer layout."""
    allocations = []
    for name in manifest['allocations']:
        t = manifest['tensors'][name]
        allocations.append(dict(name=name, base=t['address'],
            bytes=t.get('storage_bytes', t['words'] * 4), reserved_bytes=t['words'] * 4,
            readonly=t['readonly'], virtual=t['virtual'], shape=list(t['dims']),
            descriptor_dtype=t.get('storage_dtype', 7)))
    regions = [dict(base=a, limit=b, read=True, write=w) for a, b, w in (
        (manifest['metadataLimit'], manifest['scratchBase'], False),
        (manifest['scratchBase'], manifest['limit'], True),
        (manifest['base'], manifest['metadataLimit'], False),
        (manifest['limit'], manifest['limit'] + 786432, True))]
    tables = {}
    for key, prefix, data in (('commands', 'command', cb), ('descriptors', 'descriptor', db)):
        tables[key] = dict(base=manifest[prefix + 'Base'], limit=manifest[prefix + 'Limit'],
                           count=manifest[key], **digest(data))
    return dict(rows=128, epoch=7, relocate=0, shape=manifest['shape'], tables=tables,
        regions=regions, allocations=allocations, schedule=manifest['schedule'],
        payload_layout_bytes=len(cb) + len(db) + sum(a['bytes'] for a in allocations if a['readonly']),
        views={name: manifest['tensors'][name] for name in ('cache_k', 'cache_v')})


def replay(repository):
    root = Path(repository).resolve(strict=True)
    pin = json.loads((HERE / 'SOURCE_PIN.json').read_text())
    no_numeric_modules()
    require(not any(n == 'heteronpu' or n.startswith('heteronpu.')
                    or n.startswith('metadata_original_') for n in sys.modules),
            'fresh project module namespace required')
    for key, expected in pin['reference_only_sources'].items():
        path = root / relative(key)
        require(path.resolve().is_relative_to(root), 'source outside repository')
        require(digest(path.read_bytes()) == expected, 'reference source drift: ' + key)
    loaded = {}
    requests = FixedPathRequest(root)
    imports = fixed_importer(loaded, requests)
    before_path = tuple(sys.path)
    original_names = set(sys.modules)
    try:
        for record in pin['executed_modules']:
            key = record['path']
            path = root / relative(key)
            require(path.resolve().is_relative_to(root), 'source outside repository')
            expected = {k: record[k] for k in ('bytes', 'sha256')}
            loaded[record['module']] = module(record['module'], path, key, expected, imports)
        require(len(requests.requests) == 2, 'expected exactly two suppressed path requests')
        require(tuple(sys.path) == before_path, 'global sys.path changed')
        # Original functions run directly. The converter's numerical pack_words
        # is neither replaced nor called; no .npy/.npz or tensor binaries exist.
        with tempfile.TemporaryDirectory(prefix='fixed_m128_metadata_') as temporary:
            work = Path(temporary)
            loaded['metadata_original_packer'].pack(
                dict(H=1536, F=8960, HEADS=12, KVHEADS=2, HD=128, MAX_TOKENS=1024),
                128, work / 'fp32', 0)
            manifest = loaded['metadata_original_converter'].convert(work / 'fp32', work / 'bf16')
            require({p.name for p in (work / 'bf16').iterdir()} ==
                    {'manifest.json', 'owner_fixture.h', 'host_commands.bin', 'host_descriptors.bin'},
                    'unexpected metadata producer output')
            cb = (work / 'bf16/host_commands.bin').read_bytes()
            db = (work / 'bf16/host_descriptors.bin').read_bytes()
        derived = layout(manifest, cb, db)
        expected = json.loads((HERE / 'EXPECTED_LAYOUT.json').read_text())
        require(derived == expected, 'exact M128 metadata layout mismatch')
        require(tuple(sys.path) == before_path, 'global sys.path changed')
        no_numeric_modules()
        new_project_modules = {n for n in set(sys.modules) - original_names
                               if n.startswith(('heteronpu.', 'metadata_original_'))}
        require(new_project_modules == set(loaded), 'unexpected project module executed')
        audit = dict(project_modules_executed=list(loaded),
            suppressed_path_requests=requests.requests, project_bytecode_loader_used=False,
            source_buffer_hashed_and_compiled_same=True, numpy_imported=False, torch_imported=False,
            numeric_payload_loaded=False, numerical_pack_words_called=False,
            historical_stream_framing_recovered=False, resident_ddr_permissions_established=False,
            native_compiled=False, eda_executed=False)
        return derived, cb, db, audit
    finally:
        for name in loaded:
            sys.modules.pop(name, None)


def header(data):
    # These PODs describe fixture metadata only. They are not WritePermits,
    # launch admission, a loader receipt, or physical/resident DDR permissions.
    lines = ['// Source-derived fixture layout only; no DDR or launch authorization.',
        '// New metadata header, not recovery of unpublished host_memory.hpp.',
        '#pragma once', '#include <cstdint>', 'namespace metadata_layout_replay {',
        'inline constexpr unsigned rows=128, epoch=7;',
        'struct Table { uint64_t base, limit; unsigned count; };']
    for name, t in data['tables'].items():
        lines.append('inline constexpr Table %s{%dULL,%dULL,%d};' % (name, t['base'], t['limit'], t['count']))
    lines += ['struct FixtureRegion { uint64_t base, limit; bool fixture_read, fixture_write; };',
              'inline constexpr FixtureRegion fixture_regions[]={']
    for r in data['regions']:
        lines.append('{%dULL,%dULL,%s,%s},' % (r['base'], r['limit'], str(r['read']).lower(), str(r['write']).lower()))
    lines += ['};', 'struct Reservation { const char* name; uint64_t base, storage_bytes, reserved_bytes; bool fixture_readonly, fixture_virtual; };',
              'inline constexpr Reservation reservations[]={']
    for a in data['allocations']:
        lines.append('{"%s",%dULL,%dULL,%dULL,%s,%s},' % (a['name'], a['base'], a['bytes'], a['reserved_bytes'], str(a['readonly']).lower(), str(a['virtual']).lower()))
    lines += ['};', 'inline constexpr bool resident_ddr_permissions_established=false;',
              'inline constexpr bool historical_stream_framing_recovered=false;', '}', '']
    return '\n'.join(lines).encode()


def artifacts(repository):
    data, cb, db, audit = replay(repository)
    document = dict(schema=1, status='EXACT_SOURCE_METADATA_REPLAY_ONLY',
                    layout=data, audit=audit)
    return {'metadata.json': (json.dumps(document, indent=2, sort_keys=True) + '\n').encode(),
            'host_commands.bin': cb, 'host_descriptors.bin': db,
            'metadata_layout.hpp': header(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), 'output already exists')
    require(not output.resolve().is_relative_to(root), 'output must be outside source repository')
    files = artifacts(root)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        (output / name).write_bytes(raw)
    print(json.dumps(dict(status='EXACT_SOURCE_METADATA_REPLAY_ONLY', files={name: digest(raw)
        for name, raw in files.items()}, tensor_payload_bytes_written=0), sort_keys=True))


if __name__ == '__main__':
    main()
