"""One early t0 and fixed same-buffer entry; no native action on import."""
import time
STARTED = time.monotonic()
import hashlib
import os
from pathlib import Path
import stat
import sys

CALLER_PIN = (19837, '008e432e35b9b4d3c92f95a37f5eda52ad39d76f8cb7905f9855e7068306f802')


def checked(path, pin):
    p = Path(path)
    if not p.is_absolute() or '..' in p.parts or any(x.is_symlink() for x in (p, *p.parents)):
        raise ValueError('ENTRY_CANONICAL')
    size, digest = pin
    if type(size) is not int or not 0 < size <= 1024**2:
        raise ValueError('ENTRY_CAP')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            raise ValueError('ENTRY_SIZE')
        raw = bytearray()
        while len(raw) <= size:
            chunk = os.read(fd, min(65536, size + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        raw = bytes(raw)
        stamp = lambda v: (v.st_dev, v.st_ino, v.st_mode, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != pin or stamp(before) != stamp(os.fstat(fd)) or stamp(before) != stamp(p.stat(follow_symlinks=False)):
            raise ValueError('ENTRY_HASH_OR_DRIFT')
        return raw
    finally:
        os.close(fd)


def main(argv=None, *, started=None):
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError('ENTRY_ISOLATION')
    origin = STARTED if started is None else started
    if type(origin) is not float or not 0 <= time.monotonic() - origin < 30:
        raise ValueError('ENTRY_T0')
    p = Path(__file__).absolute().parent / 'run_relink.py'
    raw = checked(p, CALLER_PIN)
    ns = {'__name__': 'fixed_pc01_relink', '__file__': str(p)}
    exec(compile(raw, str(p), 'exec', dont_inherit=True), ns)
    ns['main'](argv, started=origin, source_pin=CALLER_PIN)


if __name__ == '__main__':
    main()
