"""Pinned derived rebuild entrypoint; outer command must pin this loader before loading it."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use Python -I -S -B before loading the derived rebuild gate.')
import hashlib
import os
from pathlib import Path
import stat
import time
import types

entry = globals().get('__outer_entry_monotonic__', time.monotonic())
source = Path(__file__).absolute().parent / 'run_seqnum_rebuild.py'
size = 24603
expected = 'a5df00c76cd5482dc758ed637c3dbb886e44b86de5ede5143c6e36f88a0478ef'
parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for part in source.parent.parts[1:]:
        newer = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        os.close(parent)
        parent = newer
    fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            raise ValueError('derived rebuild runner regular length')
        pieces = []
        count = 0
        while count <= size:
            part = os.read(fd, min(65536, size + 1 - count))
            if not part:
                break
            pieces.append(part)
            count += len(part)
        raw = b''.join(pieces)
        key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected or key(before) != key(os.fstat(fd)) or key(before) != key(os.stat(source.name, dir_fd=parent, follow_symlinks=False)):
            raise ValueError('derived rebuild runner raw identity')
    finally:
        os.close(fd)
finally:
    os.close(parent)
module = types.ModuleType('verified_seqnum_rebuild')
module.__file__ = str(source)
module.__entry_monotonic__ = entry
module.__verified_runner_pin__ = {'path': str(source), 'bytes': size, 'sha256': expected}
exec(compile(raw, str(source), 'exec', dont_inherit=True), module.__dict__)
module.main()
