"""Same-buffer fixed-pin launcher for the reviewed source comparator."""
import hashlib
import os
from pathlib import Path
import stat
import sys

WORKER_BYTES = 21000
WORKER_SHA256 = 'e2d1a644e369147772ccd3e6b074559a9b29e9230ace172a3f4bcb4594794800'

def load(raw):
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError('FLAGS')
    if type(raw) is not bytes or len(raw) != WORKER_BYTES:
        raise ValueError('SIZE')
    if hashlib.sha256(raw).hexdigest() != WORKER_SHA256:
        raise ValueError('SHA')
    namespace = {'__name__': '_frozen_n0_comparator', '__file__': '<frozen-n0-comparator>'}
    exec(compile(raw, '<frozen-n0-comparator>', 'exec'), namespace)
    return namespace

def main():
    try:
        if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
            raise ValueError('FLAGS')
        path = Path(__file__).absolute().parent/'n0_compare.py'
        if path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('PATH')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            first = os.fstat(fd)
            if not stat.S_ISREG(first.st_mode) or first.st_size != WORKER_BYTES:
                raise ValueError('FILE')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(WORKER_BYTES + 1)
            last = os.fstat(fd)
            fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if fields(first) != fields(last) or fields(last) != fields(path.stat()):
                raise ValueError('CHANGED')
        finally:
            os.close(fd)
        return load(raw)['main']()
    except Exception:
        # Never echo a path, argv, source text or exception message.
        print('NOT_COMPLETED:SOURCE')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
