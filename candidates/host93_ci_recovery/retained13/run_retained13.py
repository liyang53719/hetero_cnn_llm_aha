#!/usr/bin/env python3
"""Portable fixed-buffer entry for retained13; all project inputs remain read-only."""
import sys, time
started = time.monotonic()
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('python -I -S -B required before project compile')
import signal
if signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK, set()):
    raise SystemExit('inherited SIGALRM blocked; refusing before project compile')
if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
    raise SystemExit('inherited ITIMER_REAL occupied; refusing before project compile')
import hashlib, os, stat
from pathlib import Path
path = Path(__file__).absolute().parent/'assemble_retained13.py'
pin = {'bytes': 13594, 'sha256': '9fe24041b1d60da848494586e54b75d1e3f830058a9b565f2d80b125db99cb31'}
if any(p.is_symlink() for p in (path, *path.parents)):
    raise SystemExit('entry symlink rejected')
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
    meta = os.fstat(fd)
    if not stat.S_ISREG(meta.st_mode) or meta.st_size != pin['bytes']:
        raise SystemExit('fixed runner size mismatch before compile')
    with os.fdopen(fd, 'rb', closefd=False) as stream:
        raw = stream.read(pin['bytes'] + 1)
finally:
    os.close(fd)
if len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
    raise SystemExit('fixed runner SHA256 mismatch before compile')
sys.argv = [str(path)] + sys.argv[1:]
os.umask(0o077)
exec(compile(raw, str(path), 'exec', dont_inherit=True),
     {'__name__': '__main__', '__file__': str(path), '__verified_entry__': 'ci-retained13-v1',
      '__runner_pin__': pin, '__entry_started__': started})
