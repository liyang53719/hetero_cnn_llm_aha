"""Root-invoked dependency, compile/link and native-software diagnostic; one shared 60-second deadline."""
import time
START = time.monotonic()
STOP, WORK_STOP = START + 60, START + 40
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys


def need(ok, why):
    if not ok:
        raise ValueError(why)


def expired(*_):
    raise TimeoutError('UF_NATIVE_GLOBAL_DEADLINE_OR_RESOURCE_STOP')


need(len(sys.argv) == 1, 'no variable compile arguments')
need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and
     not sys.flags.optimize and sys.version_info[:3] == (3, 12, 14), 'fixed isolated target CPython 3.12.14')
need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0) and
     signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'free unblocked deadline')
signal.signal(signal.SIGALRM, expired)
signal.signal(signal.SIGTERM, expired)
signal.setitimer(signal.ITIMER_REAL, max(.001, STOP - time.monotonic()))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
os.umask(0o077)
resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
HERE = Path(__file__).resolve().parent
PINS = {'FROZEN_PLAN.json': {'bytes': 704781, 'sha256': '2f7153133e9e1a6f4f4966d005ce2bda2c085904c998ed3da42376d45836ad37'}, 'run_native.py': {'bytes': 17688, 'sha256': '5ddb9898800cbda97f1876564fa1b25f9224ca6dac5e7ab8745f76f67b8c0aa2'}}


def raw_fixed(name):
    p = HERE / name
    pin = PINS[name]
    before = p.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size == pin['bytes'], 'fixed small file')
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    with p.open('rb') as f:
        need(stamp(before) == stamp(os.fstat(f.fileno())), 'fixed file FD')
        raw = f.read(pin['bytes'] + 1)
        need(stamp(before) == stamp(os.fstat(f.fileno())) == stamp(p.lstat()), 'fixed file changed')
    need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'fixed raw SHA')
    return raw


try:
    plan = json.loads(raw_fixed('FROZEN_PLAN.json'))
    source = raw_fixed('run_native.py')
    launch_count = [0]
    sequence = [plan['dependency_argv'], plan['compile_argv'], plan['native_argv']]

    def audit(event, args):
        if event.startswith('socket.') or event == 'urllib.Request':
            raise RuntimeError('coordinator network forbidden')
        if event in {'os.system', 'os.exec', 'os.posix_spawn'}:
            raise RuntimeError('other process entry forbidden')
        if event == 'subprocess.Popen':
            executable, argv, cwd, environment = args
            need(launch_count[0] < 3, 'at most dependency, compile/link and native children')
            expected = sequence[launch_count[0]]
            need(executable == expected[0] and list(argv) == expected and
                 str(cwd) == plan['work'] and environment == plan['environment'],
                 'exact ordered dependency, compile/link, native child')
            launch_count[0] += 1

    sys.addaudithook(audit)
    namespace = {'__name__': 'frozen_uf_native_driver', '__file__': str(HERE / 'run_native.py')}
    exec(compile(source, str(HERE / 'run_native.py'), 'exec', dont_inherit=True), namespace)
    namespace['main'](plan, START, STOP, WORK_STOP, expired)
    need(launch_count[0] == 3, 'exactly three sequential bounded children')
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
