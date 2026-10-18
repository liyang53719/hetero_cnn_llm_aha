"""Pinned entrypoint; never import the local project before checking its raw bytes."""
import hashlib
import os
from pathlib import Path
import stat
import sys
import time
import types

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use python -I -S -B load_build_gate.py --phase PHASE.')
entry = time.monotonic()
source = Path(__file__).absolute().parent / 'run_build_gate.py'
size = 28551
expected = '8f1560c5f0a8e78a991f98c30031cbd18df220e3eb82cf2c78de4ec0438bdafb'
fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for part in source.parent.parts[1:]:
        newer = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        os.close(fd)
        fd = newer
    handle = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        before = os.fstat(handle)
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            raise ValueError('fixed runner type/length mismatch')
        pieces = []
        count = 0
        while count <= size:
            part = os.read(handle, min(65536, size + 1 - count))
            if not part:
                break
            pieces.append(part)
            count += len(part)
        raw = b''.join(pieces)
        after = os.fstat(handle)
        current = os.stat(source.name, dir_fd=fd, follow_symlinks=False)
        key = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected or key(before) != key(after) or key(before) != key(current):
            raise ValueError('fixed runner identity mismatch')
    finally:
        os.close(handle)
finally:
    os.close(fd)
module = types.ModuleType('verified_fixed_build_gate')
module.__file__ = str(source)
module.__entry_monotonic__ = entry
module.__verified_runner_pin__ = {'path': str(source), 'bytes': size, 'sha256': expected}
exec(compile(raw, str(source), 'exec', dont_inherit=True), module.__dict__)
module.main()
