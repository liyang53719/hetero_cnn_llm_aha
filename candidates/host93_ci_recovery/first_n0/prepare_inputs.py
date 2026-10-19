"""Fixed raw13 -> canonical16 composition. SOURCE_ONLY unless --execute.
The parent owns wall/CPU/address-space supervision. No networking or reference.
"""
from __future__ import annotations

import argparse
import builtins
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import types

PROVIDER = 'candidates/host93_first_n0_sources/inputs/'
META = 'development_snapshots/canonical_host_metadata_source_20261018/'
PINS = {
    PROVIDER + 'convert_providers.py': (17116, 'abcf7854796e6e90350ac832b53b070326f810d3a16bf1127919d59049768ee6'),
    PROVIDER + 'CONVERSION_SPEC.json': (17884, 'ab1fabb72d69f0f196dafd19fe7324a1413b000952e0ee04baa3cbaaff4a14ac'),
    META + 'replay_metadata.py': (11370, 'dbfa667b87aa1c44813d041d0053c9afa7b804ea7dc3b907b285a76171b53bfe'),
    META + 'SOURCE_PIN.json': (3008, '2a40768093f4529fe9a4ad69363178bcf3ef817ca53ebb5694f8e82b03427758'),
    META + 'EXPECTED_LAYOUT.json': (15795, '4ededb349c9206841e464f786c8b64d8744de60d789150ce533e17fe544bc7a7'),
}
COMMANDS = (384, '618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4')
DESCRIPTORS = (3456, '1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02')
INPUT_BYTES = 94920448
PROVIDER_BYTES = 94916608
CODES = ('FLAGS', 'PATH', 'SOURCE', 'PROVIDER_SOURCE', 'RAW_RECEIPT',
         'PROVIDER_OUTPUT', 'METADATA_REPLAY', 'INPUT_IDENTITY', 'DEADLINE',
         'PRIVATE_SAVE', 'RESOURCE', 'UNEXPECTED')


class ContractError(ValueError):
    def __init__(self, code):
        self.code = code if code in CODES else 'UNEXPECTED'
        super().__init__(self.code)


def need(ok, code):
    if not ok:
        raise ContractError(code)


def flags():
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'FLAGS')


def tick(deadline):
    need(type(deadline) in (int, float) and math.isfinite(deadline)
         and time.monotonic() < deadline, 'DEADLINE')


def plain(value):
    p = Path(value)
    need(p.is_absolute() and '..' not in p.parts and not any(
        c in str(p) for c in ('\n', '\r', '\x00')), 'PATH')
    need(all(not q.is_symlink() for q in (p, *p.parents)), 'PATH')
    return p


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def read(path, pin, retain=True, deadline=None):
    """Check one stable regular-file buffer; executable callers compile this buffer."""
    if deadline is not None:
        tick(deadline)
    path = plain(path)
    size, digest = pin
    need(type(size) is int and 0 <= size <= 94920448, 'INPUT_IDENTITY')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size == size, 'INPUT_IDENTITY')
        hasher, parts, count = hashlib.sha256(), [], 0
        while count < size:
            if deadline is not None:
                tick(deadline)
            raw = stream.read(min(65536, size - count))
            need(bool(raw), 'INPUT_IDENTITY')
            count += len(raw)
            hasher.update(raw)
            if retain:
                parts.append(raw)
        need(stream.read(1) == b'', 'INPUT_IDENTITY')
        after = os.fstat(stream.fileno())
    need(stamp(before) == stamp(after) == stamp(path.stat(follow_symlinks=False))
         and hasher.hexdigest() == digest, 'INPUT_IDENTITY')
    if deadline is not None:
        tick(deadline)
    return b''.join(parts) if retain else {'bytes': size, 'sha256': digest}


def module(raw, file, name, importer=None):
    flags()  # Always before exec, including direct callers of this helper.
    need(type(raw) is bytes and name not in sys.modules, 'SOURCE')
    result = types.ModuleType(name)
    result.__file__ = str(file)
    result.__package__ = name.rpartition('.')[0]
    if importer is not None:
        result.__builtins__ = dict(vars(builtins), __import__=importer)
    sys.modules[name] = result
    try:
        exec(compile(raw, str(file), 'exec', dont_inherit=True), result.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return result


def source_buffers(repo, deadline):
    return {name: read(repo / name, pin, deadline=deadline) for name, pin in PINS.items()}


def metadata_sources(repo, buffers, deadline):
    pin = json.loads(buffers[META + 'SOURCE_PIN.json'])
    rows = [(row['path'], (row['bytes'], row['sha256'])) for row in pin['executed_modules']]
    rows += [(name, (row['bytes'], row['sha256'])) for name, row in pin['reference_only_sources'].items()]
    need(len(rows) == len({name for name, _ in rows}) == 13, 'METADATA_REPLAY')
    return {name: read(repo / name, identity, deadline=deadline) for name, identity in rows}


def save(path, raw, deadline):
    tick(deadline)
    need(type(raw) is bytes and len(raw) <= 65536, 'PRIVATE_SAVE')
    path = plain(path)
    with path.open('xb') as stream:
        need(stream.write(raw) == len(raw), 'PRIVATE_SAVE')
        stream.flush()
        os.fsync(stream.fileno())
    tick(deadline)


def metadata_artifacts(repo, private, buffers, sources, deadline):
    """Original metadata producers; only their loading shim uses stable buffers."""
    tick(deadline)
    for name in ('SOURCE_PIN.json', 'EXPECTED_LAYOUT.json'):
        save(private / name, buffers[META + name], deadline)
    metadata = module(buffers[META + 'replay_metadata.py'], private / 'replay_metadata.py',
                      '_fixed_original_metadata')
    records = {row['path']: row for row in json.loads(buffers[META + 'SOURCE_PIN.json'])['executed_modules']}

    def fixed_module(name, path, source_key, expected, importer):
        tick(deadline)
        row = records.get(source_key)
        need(row is not None and row['module'] == name and path == repo / source_key
             and expected == {key: row[key] for key in ('bytes', 'sha256')}, 'METADATA_REPLAY')
        raw = sources[source_key]
        need(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'METADATA_REPLAY')
        return module(raw, path, name, importer)

    # No converter function is edited; the eight original project bodies execute
    # from the exact stable buffers captured above, under the original importer.
    metadata.module = fixed_module
    metadata.tempfile = types.SimpleNamespace(TemporaryDirectory=lambda prefix:
        tempfile.TemporaryDirectory(prefix=prefix, dir=private))
    try:
        result = metadata.artifacts(repo)
    finally:
        sys.modules.pop('_fixed_original_metadata', None)
    tick(deadline)
    need(set(result) == {'metadata.json', 'host_commands.bin',
                         'host_descriptors.bin', 'metadata_layout.hpp'}, 'METADATA_REPLAY')
    for name, pin in (('host_commands.bin', COMMANDS), ('host_descriptors.bin', DESCRIPTORS)):
        raw = result[name]
        need(type(raw) is bytes and (len(raw), hashlib.sha256(raw).hexdigest()) == pin, 'INPUT_IDENTITY')
    return result


def verify_inputs(out, spec, deadline):
    expected = [('commands', 'metadata/host_commands.bin', COMMANDS),
                ('descriptors', 'metadata/host_descriptors.bin', DESCRIPTORS)]
    expected += [(row['name'], 'providers/' + row['output_filename'],
                  (row['output_bytes'], row['expected_output_sha256'])) for row in spec['providers']]
    need(len(expected) == 16 and len({name for name, _, _ in expected}) == 16
         and sum(pin[0] for _, _, pin in expected) == INPUT_BYTES, 'INPUT_IDENTITY')
    return [{'name': name, **read(out / relative, pin, False, deadline)}
            for name, relative, pin in expected]


def prepare(repo, raw_root, out, shared_stop):
    flags()
    tick(shared_stop)
    # Calculated once at entry, never reset between preparation and verification.
    deadline = min(float(shared_stop), time.monotonic() + 120.0)
    repo, raw_root, out = map(plain, (repo, raw_root, out))
    need(repo.is_dir() and raw_root.is_dir() and out.parent.is_dir()
         and not os.path.lexists(out) and not out.is_relative_to(repo)
         and not out.is_relative_to(raw_root), 'PATH')
    boundary = 'SOURCE'
    converter = None
    created = False
    try:
        buffers = source_buffers(repo, deadline)
        sources = metadata_sources(repo, buffers, deadline)
        out.mkdir(mode=0o700)
        created = True
        # Known source emits no output here. Discard unexpected source output so
        # even exceptional/mocked execution cannot turn paths or payloads public.
        with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            boundary = 'PROVIDER_SOURCE'
            converter = module(buffers[PROVIDER + 'convert_providers.py'],
                               repo / (PROVIDER + 'convert_providers.py'), '_fixed_current_provider')
            tick(deadline)
            spec = converter.check_sources(repo)
            need(spec == json.loads(buffers[PROVIDER + 'CONVERSION_SPEC.json']), 'PROVIDER_SOURCE')
            tick(deadline)
            boundary = 'RAW_RECEIPT'
            converter.check_receipt(raw_root, spec, deadline)
            tick(deadline)
            boundary = 'PROVIDER_OUTPUT'
            provider_out = converter.prepare_output(repo, raw_root, out / 'providers', spec)
            tick(deadline)
            report = converter.collect(spec, raw_root, provider_out, deadline)
            need(report['status'] == 'FIXED_PROVIDER14_BYTES_VERIFIED'
                 and report['provider_payload_bytes'] == PROVIDER_BYTES
                 and report['conversion_spec_sha256'] == PINS[PROVIDER + 'CONVERSION_SPEC.json'][1]
                 and report['raw_receipt_sha256'] == spec['raw_receipt']['sha256']
                 and report['providers'] == [dict(name=row['name'], file=row['output_filename'],
                     bytes=row['output_bytes'], sha256=row['expected_output_sha256']) for row in spec['providers']],
                 'PROVIDER_OUTPUT')
            tick(deadline)
            boundary = 'METADATA_REPLAY'
            private = out / 'metadata_source'
            private.mkdir(mode=0o700)
            artifacts = metadata_artifacts(repo, private, buffers, sources, deadline)
            md = out / 'metadata'
            md.mkdir(mode=0o700)
            for name, raw in artifacts.items():
                save(md / name, raw, deadline)
            boundary = 'INPUT_IDENTITY'
            identities = verify_inputs(out, spec, deadline)
            boundary = 'SOURCE'
            need(source_buffers(repo, deadline) == buffers
                 and metadata_sources(repo, buffers, deadline) == sources, 'SOURCE')
            boundary = 'DEADLINE'
            tick(deadline)
            receipt = {'schema': 1, 'status': 'CANONICAL16_PREPARED_ONLY',
                       'inputs': identities, 'input_bytes': INPUT_BYTES,
                       'weights_loaded_into_rtl': False, 'reference_used': False}
            save(out / 'INPUTS_READY.part', (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode(), deadline)
            tick(deadline)
            os.link(out / 'INPUTS_READY.part', out / 'INPUTS_READY.json')
            (out / 'INPUTS_READY.part').unlink()
            tick(deadline)
            return receipt
    except BaseException as error:
        if created:
            try:
                (out / 'INPUTS_READY.json').unlink(missing_ok=True)
            except OSError:
                pass
        # No arbitrary exception text or argv is saved in the public result.
        if isinstance(error, ContractError):
            raise
        if isinstance(error, (TimeoutError, MemoryError)):
            raise ContractError('RESOURCE') from None
        raise ContractError(boundary) from None
    finally:
        if converter is not None:
            sys.modules.pop('_fixed_current_provider', None)


class FixedParser(argparse.ArgumentParser):
    def error(self, message):
        raise ContractError('FLAGS')


def main(argv=None):
    try:
        parser = FixedParser(prog='N0_INPUTS', allow_abbrev=False, add_help=False)
        parser.add_argument('--repo')
        parser.add_argument('--raw-root')
        parser.add_argument('--out')
        parser.add_argument('--shared-stop', type=float)
        parser.add_argument('--execute', action='store_true')
        args = parser.parse_args(argv)
        if not args.execute:
            print('N0_INPUTS_SOURCE_ONLY')
            return 0
        need(all(value is not None for value in (args.repo, args.raw_root, args.out, args.shared_stop)), 'FLAGS')
        prepare(args.repo, args.raw_root, args.out, args.shared_stop)
        print('N0_INPUTS_PREPARED')
        return 0
    except ContractError as error:
        print('N0_INPUTS_INCOMPLETE:' + error.code)
        return 2 if error.code == 'RESOURCE' else 1
    except BaseException:
        print('N0_INPUTS_INCOMPLETE:UNEXPECTED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
