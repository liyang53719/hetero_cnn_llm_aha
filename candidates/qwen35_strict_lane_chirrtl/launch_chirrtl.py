"""Root-invoked emitter compile and one-owner CHIRRTL attempt; one shared 180-second deadline."""
import time
START = time.monotonic()
STOP, WORK_STOP = START + 180, START + 150
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
    raise TimeoutError('ISOLATED_LANE_CHIRRTL_GLOBAL_DEADLINE_OR_RESOURCE_STOP')


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
resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
HERE = Path(__file__).resolve().parent
PINS = {'FROZEN_PLAN.json': {'bytes': 234495, 'sha256': '49773df02f3045008a7ea081e92c68972a8ff6cd248857327a292704bf12f463'}, 'run_chirrtl.py': {'bytes': 22401, 'sha256': 'be9b9f32ddf7a08d0bc74c6f138c5bfb1197a76869a6ed8da9475682de61671e'}}


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
    source = raw_fixed('run_chirrtl.py')
    launch_count = [0]
    sequence = [plan['compile_argv'], plan['elaborate_argv']]

    def audit(event, args):
        if event.startswith('socket.') or event == 'urllib.Request':
            raise RuntimeError('coordinator network forbidden')
        if event in {'os.system', 'os.exec', 'os.posix_spawn'}:
            raise RuntimeError('other process entry forbidden')
        if event == 'subprocess.Popen':
            executable, argv, cwd, environment = args
            need(launch_count[0] < 2, 'at most compile and elaboration JVMs')
            expected = sequence[launch_count[0]]
            need(executable == expected[0] and list(argv) == expected and
                 str(cwd) == plan['work'] and environment == plan['environment'],
                 'exact ordered compile then elaboration child')
            launch_count[0] += 1

    sys.addaudithook(audit)
    namespace = {'__name__': 'frozen_qwen35_owner_chirrtl_driver', '__file__': str(HERE / 'run_chirrtl.py')}
    exec(compile(source, str(HERE / 'run_chirrtl.py'), 'exec', dont_inherit=True), namespace)
    namespace['main'](plan, START, STOP, WORK_STOP, expired)
    need(launch_count[0] == 2, 'exactly two sequential JVM children')
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
