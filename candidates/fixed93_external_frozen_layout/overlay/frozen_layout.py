"""Exact, read-only relocation of frozen files; logical identities never change.

This is a source-reviewed Python I/O guard, not an OS sandbox or a defense
against arbitrary native syscalls or previously opened writable descriptors.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = 'fixed93-readonly-external-frozen-layout-v1'
LAYOUT_FILE = 'FROZEN_EXTERNAL_LAYOUT.json'
COPY_FILE = 'contract/FROZEN_DATA_COPIES.json'
PREFIXES = ('work/qwen2_recovered_inputs', 'work/qwen2_recovered_reference')
REFERENCE_PREFIX = PREFIXES[1] + '/first/'
MAX_METADATA = 2 * 1024 * 1024


def need(ok, message):
    if not ok:
        raise ValueError(message)


def logical_name(value):
    need(type(value) is str and value and not Path(value).is_absolute() and
         str(Path(value)) == value and all(p not in ('', '.', '..') for p in value.split('/')),
         'canonical relative logical name required')
    return value


def canonical(value):
    need(type(value) in (str, Path) or isinstance(value, Path), 'path required')
    p = Path(value)
    need(p.is_absolute() and str(p) == str(value) and p.resolve() == p and
         not any(q.is_symlink() for q in (p, *p.parents)), 'aliased frozen path')
    return p


def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def regular(path):
    path = canonical(path)
    s = path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'regular nlink1 frozen file required')
    return s


def spec(value):
    need(type(value) is dict and set(value) == {'bytes', 'sha256'} and
         type(value['bytes']) is int and value['bytes'] >= 0 and
         type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']),
         'exact typed byte/SHA pin required')
    return dict(value)


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_metadata(path, expected=None):
    before = regular(path)
    need(before.st_size <= MAX_METADATA, 'metadata exceeds bounded size')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        need(stamp(opened) == stamp(before), 'metadata replaced before open')
        raw = stream.read(MAX_METADATA + 1)
        after = os.fstat(stream.fileno())
    need(len(raw) <= MAX_METADATA and stamp(before) == stamp(after) == stamp(regular(path)),
         'metadata changed during read')
    identity = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    need(expected is None or identity == spec(expected), 'metadata byte/hash drift')
    return raw, identity


class FrozenLayout:
    """No writing API. path() supplies identity locations, not read permission."""
    def __init__(self, roots, files, *, candidate, declaration):
        need(type(roots) is dict and set(roots) == set(PREFIXES), 'exact two frozen roots')
        self.candidate = canonical(candidate)
        self.roots = {name: canonical(value) for name, value in roots.items()}
        self.frozen_roots = tuple(self.roots[name] for name in PREFIXES)
        for root in self.frozen_roots:
            need(root.is_dir() and not root.is_relative_to(self.candidate) and
                 not self.candidate.is_relative_to(root), 'frozen root overlaps candidate')
        a, b = self.frozen_roots
        need(not a.is_relative_to(b) and not b.is_relative_to(a), 'frozen roots overlap')
        need(type(files) is dict and bool(files), 'exact frozen files required')
        self.files, self.paths, self._initial, self._reverse = {}, {}, {}, {}
        self._root_stamps = {p: stamp(p.stat()) for p in self.frozen_roots}
        inodes = set()
        for name, value in files.items():
            logical_name(name)
            matches = [prefix for prefix in PREFIXES if name.startswith(prefix + '/')]
            need(len(matches) == 1, 'logical file outside fixed frozen namespaces')
            prefix = matches[0]
            p = canonical(self.roots[prefix] / name[len(prefix) + 1:])
            need(p.is_relative_to(self.roots[prefix]), 'frozen file escapes root')
            expected, before = spec(value), regular(p)
            need(before.st_size == expected['bytes'], 'frozen file extent differs')
            inode = (before.st_dev, before.st_ino)
            need(inode not in inodes and p not in self._reverse, 'duplicate frozen inode/path alias')
            inodes.add(inode)
            self.files[name], self.paths[name] = expected, p
            self._initial[name], self._reverse[p] = stamp(before), name
        self.declaration = dict(declaration)
        self._write_guard_installed = False

    @property
    def input_directory(self):
        return canonical(self.roots[PREFIXES[0]] / 'typed')

    @property
    def reference_directory(self):
        return canonical(self.roots[PREFIXES[1]] / 'first')

    def contains(self, name):
        logical_name(name)
        return name in self.files

    def is_reference(self, name):
        return name.startswith(REFERENCE_PREFIX) and name.endswith(('.f32le', '.bf16le'))

    def path(self, name):
        logical_name(name)
        need(name in self.files, 'undeclared frozen logical file')
        p = self.paths[name]
        need(stamp(regular(p)) == self._initial[name], 'frozen path identity changed')
        return p

    def logical(self, path):
        p = canonical(path)
        need(p in self._reverse, 'undeclared frozen physical file')
        name = self._reverse[p]
        need(self.path(name) == p, 'frozen reverse mapping drift')
        return name

    def _read(self, name, reference_opened, retain):
        need(type(reference_opened) is bool, 'explicit reference-open state required')
        p = self.path(name)
        need(not self.is_reference(name) or reference_opened, 'reference payload before output seal')
        before = self._initial[name]
        digest, total, chunks = hashlib.sha256(), 0, [] if retain else None
        with os.fdopen(os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            need(stamp(opened) == before, 'frozen file replaced between stat/open')
            while raw := stream.read(1 << 20):
                total += len(raw)
                need(total <= self.files[name]['bytes'], 'frozen file grew during read')
                digest.update(raw)
                if retain:
                    chunks.append(raw)
            after = os.fstat(stream.fileno())
        need(before == stamp(after) == stamp(regular(p)), 'frozen file changed during read')
        result = dict(bytes=total, sha256=digest.hexdigest())
        need(result == self.files[name], 'frozen content pin differs')
        return b''.join(chunks) if retain else result

    def read(self, name, *, reference_opened=False):
        return self._read(name, reference_opened, True)

    def identity(self, name, *, reference_opened=False):
        return self._read(name, reference_opened, False)

    def stat_reference(self, name):
        need(self.is_reference(logical_name(name)), 'stat-only is limited to reference payloads')
        p = self.path(name)
        need(stamp(regular(p)) == self._initial[name], 'reference changed during stat')
        return dict(logical_name=name, bytes=self.files[name]['bytes'], payload_opened=False)

    def finish(self):
        for p, before in self._root_stamps.items():
            need(stamp(canonical(p).stat()) == before, 'frozen root changed during batch')
        for name in self.files:
            self.path(name)
        return dict(files=len(self.files), all_initial_file_stamps_preserved=True)

    def _write_path(self, value, dir_fd=None):
        if type(value) is int:
            value = os.readlink('/proc/self/fd/' + str(value))
        need(isinstance(value, (str, bytes, os.PathLike)), 'unresolved mutation path')
        p = Path(os.fsdecode(value))
        if not p.is_absolute():
            base = Path(os.getcwd()) if dir_fd is None or dir_fd == -1 else Path(os.readlink('/proc/self/fd/' + str(dir_fd)))
            p = base / p
        # Resolving aliases is intentional for DENY only, never read admission.
        resolved = p.resolve()
        need(not any(resolved == root or resolved.is_relative_to(root) or root.is_relative_to(resolved)
                     for root in self.frozen_roots),
             'frozen roots are permanently read-only')

    def audit_write(self, event, args):
        if event == 'open':
            path, mode, flags = args
            writing = (type(mode) is str and any(c in mode for c in 'wax+')) or (
                type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            if writing:
                # Python's open audit event omits dir_fd; never guess its base.
                need(type(path) is int or Path(os.fsdecode(path)).is_absolute(),
                     'relative writable open cannot prove a nonfrozen target')
                self._write_path(path)
        elif event in ('os.remove', 'os.rmdir'):
            self._write_path(args[0], args[1])
        elif event in ('os.mkdir', 'os.chmod'):
            self._write_path(args[0], args[2])
        elif event in ('os.chown', 'os.utime'):
            self._write_path(args[0], args[3])
        elif event in ('os.rename', 'os.link'):
            self._write_path(args[0], args[2]); self._write_path(args[1], args[3])
        elif event == 'os.symlink':
            # A relative target is interpreted from the link's directory.
            target, destination, dir_fd = args
            destination = Path(os.fsdecode(destination))
            if not destination.is_absolute():
                base = Path(os.getcwd()) if dir_fd is None or dir_fd == -1 else Path(os.readlink('/proc/self/fd/' + str(dir_fd)))
                destination = base / destination
            target = Path(os.fsdecode(target))
            if not target.is_absolute():
                target = destination.parent / target
            self._write_path(target); self._write_path(destination)
        elif event == 'os.truncate':
            self._write_path(args[0])

    def install_write_guard(self):
        need(not self._write_guard_installed, 'write guard installs once')
        sys.addaudithook(self.audit_write)
        self._write_guard_installed = True


def load(candidate, manifest=None):
    candidate = canonical(candidate)
    if manifest is None:
        raw, identity = read_metadata(candidate / 'SOURCE_MANIFEST.json')
        expected = os.environ.get('QWEN2_FIXED93_SOURCE_MANIFEST_SHA256')
        need(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected) and
             identity['sha256'] == expected, 'explicit admitted source manifest identity required')
        manifest = parse(raw)
    need(type(manifest) is dict and type(manifest.get('preparation_files')) is dict,
         'checked source manifest required')
    pins = manifest['preparation_files']
    raw, identity = read_metadata(candidate / LAYOUT_FILE, pins[LAYOUT_FILE])
    value = parse(raw)
    need(type(value) is dict and set(value) == {'schema', 'roots', 'files', 'copy_manifest', 'read_only', 'copy_payloads'} and
         value['schema'] == SCHEMA and value['read_only'] is True and value['copy_payloads'] is False,
         'exact readonly external layout schema')
    copies_raw, copies_identity = read_metadata(candidate / COPY_FILE, pins[COPY_FILE])
    need(value['copy_manifest'] == copies_identity, 'frozen logical inventory origin pin differs')
    copies = parse(copies_raw)
    need(type(value['files']) is dict and value['files'] == copies['files'] and len(value['files']) == 76,
         'exact unchanged76 frozen logical file pins required')
    layout = FrozenLayout(value['roots'], value['files'], candidate=candidate,
                          declaration=dict(schema=SCHEMA, layout=identity, copy_manifest=copies_identity))
    need(sum(layout.is_reference(name) for name in layout.files) == 30, 'exact30 reference payloads')
    layout.install_write_guard()
    return layout
