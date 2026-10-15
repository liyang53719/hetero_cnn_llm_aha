"""Local, same-run observation of Python ELF plus its loaded libpython only.

This is not independent approval, historical equivalence, or a full system DSO
closure. No old expected libpython digest exists: observe its actual bytes and
bind that observation for the current run. Other libraries are outside scope.
Default performs no I/O. No summary upload, model execution, or numeric imports.
"""
import copy
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = Path('/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
PYTHON_HOME = Path('/opt/hostedtoolcache/Python/3.12.14/x64')
LIBPYTHON = PYTHON_HOME / 'lib/libpython3.12.so.1.0'
PYTHON_IDENTITY = {'bytes': 17752, 'sha256': 'bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0'}
STAT_KEYS = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def canonical(path):
    need(path.is_absolute() and path.resolve(strict=True) == path,
         'canonical absolute file required')
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'path alias refused')


def _stable(a, b):
    return all(getattr(a, k) == getattr(b, k) for k in STAT_KEYS)


def identity(path):
    """Stream a regular file; bind descriptor, path, and before/after metadata."""
    canonical(path)
    before = path.stat()
    need(stat.S_ISREG(before.st_mode), 'regular file required')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        need(stat.S_ISREG(opened.st_mode) and _stable(before, opened), 'file changed before hashing')
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
        after = os.fstat(stream.fileno())
    canonical(path)
    need(_stable(before, after) and _stable(after, path.stat()), 'file changed during hashing')
    return dict(path=str(path), bytes=after.st_size, sha256=digest.hexdigest(),
                device=after.st_dev, inode=after.st_ino)


def read_maps():
    return Path('/proc/self/maps').read_text(encoding='utf-8', errors='strict')


def mapped_libpython(text):
    """All libpython mappings must belong to one exact file, including data segments."""
    need(type(text) is str, 'maps text required')
    records = []
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6 or 'libpython' not in fields[5]:
            continue
        address, perms, offset, device, inode, path = fields
        need(path == str(LIBPYTHON), 'foreign, deleted, or aliased libpython mapping')
        need(re.fullmatch('[0-9a-f]+-[0-9a-f]+', address) is not None and
             re.fullmatch('[r-][w-][x-][ps]', perms) is not None and
             re.fullmatch('[0-9a-f]+', offset) is not None and
             re.fullmatch('[0-9a-f]+:[0-9a-f]+', device) is not None and
             inode.isdecimal() and int(inode) > 0, 'malformed libpython map')
        lo, hi = (int(v, 16) for v in address.split('-'))
        need(lo < hi, 'invalid libpython mapped address range')
        major, minor = (int(v, 16) for v in device.split(':'))
        records.append((major, minor, int(inode), perms[2] == 'x'))
    need(records and any(r[3] for r in records), 'loaded executable libpython mapping required')
    need(len({r[:3] for r in records}) == 1, 'multiple libpython file identities')
    major, minor, inode, _ = records[0]
    return dict(device=os.makedev(major, minor), inode=inode)


def location():
    need(ROOT == CI_ROOT and ROOT.resolve() == ROOT, 'fixed CI checkout required')
    need(not any(p.is_symlink() for p in (ROOT, *ROOT.parents)), 'checkout path alias')
    need(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 12, 14),
         'fixed CPython 3.12.14 required')
    executable = Path(sys.executable).resolve(strict=True)
    need(executable != PYTHON_HOME and executable.is_relative_to(PYTHON_HOME),
         'fixed setup-python executable location required')
    canonical(executable)
    return executable


def _python(path):
    record = identity(path)
    need(same({k:record[k] for k in ('bytes','sha256')}, PYTHON_IDENTITY),
         'reviewed Python ELF drift')
    return record


def observe(*, execute=False):
    need(type(execute) is bool, 'execute must be boolean')
    if not execute:
        return dict(status='NOT_EXECUTED', numeric_execution_allowed=False)
    executable = location()
    python = _python(executable)
    mapped = mapped_libpython(read_maps())
    library = identity(LIBPYTHON)
    need(same(mapped, {k:library[k] for k in ('device','inode')}), 'loaded libpython stat identity mismatch')
    need(same(mapped, mapped_libpython(read_maps())), 'libpython maps changed during observation')
    need(same(library, identity(LIBPYTHON)), 'libpython changed during observation')
    need(location() == executable and same(python, _python(executable)), 'Python changed during observation')
    return dict(schema=1, status='CURRENT_PROCESS_PLATFORM_OBSERVED_ONLY',
                scope='PYTHON_ELF_AND_LOADED_LIBPYTHON_ONLY', python_version=[3,12,14],
                process_id=os.getpid(), python=python, libpython=library,
                independently_reviewed=False, historical_equivalence_claimed=False,
                full_system_closure=False, numeric_execution_allowed=False)


def verify_same(frozen):
    """Re-observe now and require the same two files in this same process.

    Call immediately before and after the DUT. Equality is an observation
    consistency check, not proof of approval or of other supporting libraries.
    """
    need(type(frozen) is dict and frozen.get('status') == 'CURRENT_PROCESS_PLATFORM_OBSERVED_ONLY',
         'executed local freeze required')
    current = observe(execute=True)
    need(same(frozen, current), 'same-run platform freeze drift')
    return copy.deepcopy(current)
