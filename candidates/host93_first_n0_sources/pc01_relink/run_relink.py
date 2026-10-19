"""Fixed two-phase driver-only relink. Import performs no native action."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time
import types

CONFIG_PIN = (1258, '7783c61b84692ed8e353bb26db934f250f614b6a408e8dbe379b499758d0c0af')
CATALOG_PIN = (18466, '3882312fb75efa443fbe65af05cf882cea420a9af5be9a4ca69e4b0b2773e1e1')
REUSE_PIN = (3849, 'dcadbcf1d8220a3bfe259409cfbdf835a1e01d22863dccd895d72362e3ab1958')
GATE_PIN = (5122, '49281296cb6daa034c6e7f2f741ff6d7af9b0e61abdd96d77c1856349e8597c7')
HELPER_PIN = (14870, 'a1eef5869774d6b66aa332966d1de7a3b0cbca5fad640e65d9ee666d609f9684')
PRODUCTION_PIN = (4472, '40ebb6c1957941b90906c4dc5c0d561816fa413aa5a4431a1bd2d191f39dc5b1')
ORIGINAL_PINS = (8657, 'f6257e57710d16c93ee3edd406814e6b1aa4e5004f5258eac73173e20c34f7e4')
COMMAND_PIN = (3446, '6e35a033308211c65da7f8d0c647e287338599362dc85851c961f8b522de82b7')
SHARED_SECONDS = 180
TAIL_SECONDS = 30
MIB = 1024**2


def need(ok, code='PC01_RELINK_CONTRACT'):
    if not ok:
        raise ValueError(code)


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, pin):
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and p.resolve(strict=True) == p and
         not any(x.is_symlink() for x in (p, *p.parents)), 'SOURCE_CANONICAL')
    size, digest = pin
    need(type(size) is int and 0 <= size <= MIB, 'SOURCE_CAP')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size == size, 'SOURCE_SIZE')
        raw = bytearray()
        while len(raw) <= size:
            chunk = os.read(fd, min(65536, size + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        raw = bytes(raw)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need((len(raw), hashlib.sha256(raw).hexdigest()) == pin and
             stamp(before) == stamp(os.fstat(fd)) == stamp(p.stat(follow_symlinks=False)), 'SOURCE_HASH_OR_DRIFT')
        return raw
    finally:
        os.close(fd)


def module(path, pin, name):
    raw = read(path, pin)
    m = types.ModuleType(name)
    m.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), m.__dict__)
    return m


def write_exact(path, raw):
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and not any(x.is_symlink() for x in p.parents), 'STAGE_PATH')
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        written = 0
        while written < len(raw):
            n = os.write(fd, raw[written:])
            need(n > 0, 'STAGE_WRITE')
            written += n
        os.fsync(fd)
    finally:
        os.close(fd)


def resource_gate(root):
    rows = Path('/proc/meminfo').read_text().splitlines()
    values = [int(x.split()[1]) * 1024 for x in rows if x.startswith('MemAvailable:')]
    need(len(values) == 1 and values[0] >= 8 * 1024**3, 'MEM_AVAILABLE_8G')
    v = os.statvfs(root)
    available = v.f_bavail * v.f_frsize
    need(available >= 3 * 1024**3, 'DISK_AVAILABLE_3G')
    return {'mem_available_bytes': values[0], 'disk_available_bytes': available}


def input_buffers(g, repo, source, reuse):
    production = json.loads(read(source / 'PRODUCTION_MANIFEST.json', PRODUCTION_PIN))
    source_pins = json.loads(read(source / 'SOURCE_PINS.json', ORIGINAL_PINS))
    need(len(production['files']) == 28 and len(source_pins['sources']) == 44 and
         len(reuse['files']) == 19, 'FIXED_SOURCE_COUNTS')
    for rel, pin in source_pins['sources'].items():
        g.checked(repo / rel, pin, 4 * MIB)
    buffers = {}
    for rel, pin in production['files'].items():
        need(rel.startswith('bridge/') and '..' not in Path(rel).parts, 'FIXED_SOURCE_RELATIVE')
        buffers['source/' + rel] = g.checked(source / rel, pin, 4 * MIB)
    old = g.clean(reuse['old_work_readonly'])
    for rel, pin in reuse['files'].items():
        need(not Path(rel).is_absolute() and '..' not in Path(rel).parts, 'FIXED_CACHE_RELATIVE')
        buffers['cache/' + rel] = g.checked(old / rel, pin, 32 * MIB, fixed_leaf=Path(rel).name)
    archive = buffers['cache/host_execution/obj/VHostBlockTop__ALL.a']
    need(archive.startswith(b'!<arch>\n') and not archive.startswith(b'!<thin>\n'), 'REGULAR_NOT_THIN_ARCHIVE')
    for role in ('original_build_log', 'original_dependency_receipt'):
        row = reuse[role]
        g.checked(old / row['path'], {k: row[k] for k in ('bytes', 'sha256')}, MIB, fixed_leaf=Path(row['path']).name)
    return buffers


def verify_copies(g, work, buffers):
    for rel, raw in buffers.items():
        need(g.checked(work / rel, identity(raw), 32 * MIB, fixed_leaf=Path(rel).name) == raw, 'STAGED_BYTES_CHANGED')


def commands(catalog, work, contract):
    include = work / 'source/bridge/include'
    obj = work / 'cache/host_execution/obj'
    vlt = work / 'cache/toolchain/verilator/include'
    keys = {'FIXED_APPROVED_CXX': catalog['programs']['g++'], 'FRESH_SOURCE_INCLUDE': str(include),
            'FIXED_GENERATED_HEADER_ROOT': str(obj), 'FIXED_VERILATOR_INCLUDE': str(vlt),
            'FIXED_VERILATOR_VLTSTD': str(vlt / 'vltstd'),
            'FRESH_PC01_MAIN_CPP': str(work / 'source/bridge/source/pc01_main.cpp'),
            'FRESH_PC01_MAIN_O': str(work / 'pc01_main.o'),
            'FIXED_VERILATED_O': str(obj / 'verilated.o'), 'FIXED_VERILATED_DPI_O': str(obj / 'verilated_dpi.o'),
            'FIXED_VERILATED_THREADS_O': str(obj / 'verilated_threads.o'),
            'FIXED_HOST_ARCHIVE': str(obj / 'VHostBlockTop__ALL.a'),
            'FRESH_PC01_EXECUTABLE': str(work / 'pc01')}
    out = {}
    for name, role in (('compile', 'compile_command_template'), ('link', 'link_command_template')):
        argv = [keys.get(x, x) for x in contract[role]]
        need(argv[0] == catalog['programs']['g++'] and all(not x.startswith(('FIXED_', 'FRESH_')) for x in argv), 'FIXED_ARGV_MAPPING')
        argv[1:1] = ['-B', str(work / 'compiler-search') + '/']
        out[name] = argv
    return out


def environment(catalog, work):
    libdirs = {str(Path(p).parent) for p in catalog['libraries'].values()}
    need(len(libdirs) == 1, 'FIXED_LIBRARY_DIRECTORY')
    return {'PATH': str(work / 'compiler-search'), 'LD_LIBRARY_PATH': next(iter(libdirs)),
            'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'),
            'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC'}


def phase_limits(name):
    total, work, cpu = {'compile': (95, 80, 80), 'link': (25, 10, 10)}[name]
    return {'total_seconds': total, 'work_seconds': work, 'cpu_seconds': cpu,
            'as_bytes': 6 * 1024**3, 'fsize_bytes': 64 * MIB, 'tree_bytes': 256 * MIB,
            'log_bytes': MIB, 'sample_rows': total + 2, 'file_count': 128, 'entry_count': 256}


def supervised_sequence(s, support, base, work, argv, env, stop, owner, preflight, check_binary, result):
    for name in ('compile', 'link'):
        limits = phase_limits(name)
        need(time.monotonic() + limits['total_seconds'] <= stop - TAIL_SECONDS, 'INCOMPLETE_PHASE_WINDOW')
        preflight()
        resource_gate(work)
        need(time.monotonic() + limits['total_seconds'] <= stop - TAIL_SECONDS, 'INCOMPLETE_PHASE_WINDOW')
        stage = {'name': name, 'record': None, 'usage': None, 'diagnostics': {}}
        try:
            record, raw, usage = s.run_phase(support, base, 'pc01_driver_' + name, argv[name], work,
                work / 'phases' / name, env, limits, stop, owner, stage['diagnostics'])
            stage['record'], stage['usage'] = record, usage
            need(type(record['exit_code']) is int and record['exit_code'] == 0 and
                 record['cleanup_confirmed'] is True, 'PHASE_EXIT_OR_CLEANUP')
            need(type(usage['maxrss_kib_cumulative_parent_children']) is int and
                 0 <= usage['maxrss_kib_cumulative_parent_children'] <= 6 * 1024**2, 'CUMULATIVE_RSS_GATE_6G')
            if name == 'compile':
                p = work / 'pc01_main.o'
                need(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 64 * MIB, 'COMPILE_OBJECT')
                raw = p.read_bytes()
                need(raw[:4] == b'\x7fELF' and int.from_bytes(raw[16:18], 'little') == 1, 'COMPILE_RELOCATABLE_ELF')
                result['object'] = identity(raw)
            else:
                result['binary'] = check_binary()
        finally:
            result['stages'].append(stage)
        preflight()
        if name == 'compile':
            need(identity((work / 'pc01_main.o').read_bytes()) == result['object'], 'OBJECT_CHANGED_POSTFLIGHT')
        else:
            need(check_binary() == result['binary'], 'BINARY_CHANGED_POSTFLIGHT')
    return result['binary']


def run(config_path, execute=False, *, started=None, source_pin=None):
    need(execute and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
         'EXPLICIT_RELINK_AND_ISOLATION_REQUIRED')
    need(type(started) is float and 0 <= time.monotonic() - started < 30, 'ENTRY_T0_REQUIRED')
    stop = started + SHARED_SECONDS
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0) and
         signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'TIMER_OWNERSHIP')
    old_alarm = signal.getsignal(signal.SIGALRM)
    def expired(*unused):
        raise TimeoutError('PC01_RELINK_SHARED_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, stop - time.monotonic()))
    owner = {'handler': expired, 'deadline': stop}
    result = {'schema': 1, 'status': 'INCOMPLETE', 'scope': 'DRIVER_COMPILE_LINK_ONLY',
              'stages': [], 'rtl_executed': False, 'pc01_executable_invoked': False, 'full_block_pass': False}
    failure, work, h = None, None, None
    try:
        for kind, limit in ((resource.RLIMIT_AS, 6 * 1024**3), (resource.RLIMIT_CPU, 180),
                            (resource.RLIMIT_FSIZE, 64 * MIB)):
            _, hard = resource.getrlimit(kind)
            need(hard == resource.RLIM_INFINITY or hard >= limit, 'INHERITED_HARD_LIMIT')
            resource.setrlimit(kind, (limit, limit))
        allowed = os.sched_getaffinity(0)
        need(bool(allowed), 'CPU_AFFINITY')
        os.sched_setaffinity(0, {min(allowed)})
        own_source = read(Path(__file__).resolve(), source_pin)
        config_raw = read(config_path, CONFIG_PIN)
        cfg = json.loads(config_raw)
        need(set(cfg) == {'schema', 'repo', 'binding_source', 'binding', 'profile', 'dependencies',
                         'reuse_binding', 'source', 'work'} and cfg['schema'] == 'PC01_RELINK_PRIVATE_BINDING_V1', 'FIXED_CONFIG')
        repo, source = Path(cfg['repo']), Path(cfg['source'])
        h = module(repo / 'candidates/host93_first_n0_sources/pc1_reference_execution/run_reference.py', HELPER_PIN, 'fixed_reference_execution_helpers')
        g = h.module(repo / 'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py', h.PINS['bootstrap.py'], 'relink_bootstrap')
        bdir = Path(cfg['binding_source'])
        o = h.module(bdir / 'binding_observer.py', h.PINS['binding_observer.py'], 'relink_observer')
        l = h.module(bdir / 'local_mount_profile.py', h.PINS['local_mount_profile.py'], 'relink_mount')
        s = h.module(repo / 'candidates/host93_ci_recovery/ci_support_v3.py', h.PINS['ci_support_v3.py'], 'relink_supervisor')
        d = module(Path(__file__).resolve().parent / 'dependency_gate.py', GATE_PIN, 'relink_dependencies')
        support, base, support_pins = s.fixed_support(repo)
        binding_raw = g.checked(Path(cfg['binding']['path']), cfg['binding']['identity'])
        binding = g.binding(binding_raw, cfg['binding']['identity'], repo)
        profile = g.decode(g.checked(Path(cfg['profile']['path']), cfg['profile']['identity']))
        catalog_raw = read(Path(cfg['dependencies']), CATALOG_PIN)
        catalog = json.loads(catalog_raw)
        need(len(catalog['files']) == 39 and catalog['programs']['g++'] == binding['system_programs']['/usr/bin/g++']['path'], 'FIXED_COMPILER_CATALOG')
        for key in ('bytes', 'sha256', 'mode'):
            need(catalog['files'][catalog['programs']['g++']][key] == binding['system_programs']['/usr/bin/g++'][key], 'ORIGINAL_COMPILER_IDENTITY')
        need(str(Path(sys.executable).resolve(strict=True)) == binding['system_programs']['/usr/bin/python3']['path'], 'FIXED_INTERPRETER')
        l.validate(g, o, binding, profile)
        baseline = d.verify(g, o, l, repo, catalog)
        reuse_raw = read(Path(cfg['reuse_binding']), REUSE_PIN)
        reuse = json.loads(reuse_raw)
        buffers = input_buffers(g, repo, source, reuse)
        command_raw = read(source / 'RELINK_CONTRACT.json', COMMAND_PIN)
        contract = json.loads(command_raw)
        target = g.clean(cfg['work'])
        old = g.clean(reuse['old_work_readonly'])
        need(not target.exists() and all(not target.is_relative_to(p) and not p.is_relative_to(target)
             for p in (repo, source, old, bdir)), 'FRESH_DISJOINT_WORK')
        result['admission'] = resource_gate(target.parent)
        support.fresh_directory(target)
        work = target
        for name in ('home', 'tmp', 'phases', 'compiler-search'):
            support.fresh_directory(work / name)
        for rel, raw in buffers.items():
            need(time.monotonic() < started + 30, 'INCOMPLETE_INITIAL_STAGE_WINDOW')
            write_exact(work / rel, raw)
        result['staged_files'] = {rel: identity(raw) for rel, raw in buffers.items()}
        search = work / 'compiler-search'
        for name in ('cc1plus', 'collect2', 'as', 'ld'):
            (search / name).symlink_to(catalog['programs'][name])
        env = environment(catalog, work)
        argv = commands(catalog, work, contract)
        def preflight():
            need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_TAIL_RESERVE')
            need(read(Path(__file__).resolve(), source_pin) == own_source, 'CALLER_SOURCE_CHANGED')
            need(read(config_path, CONFIG_PIN) == config_raw and read(Path(cfg['dependencies']), CATALOG_PIN) == catalog_raw and
                 read(Path(cfg['reuse_binding']), REUSE_PIN) == reuse_raw, 'CONFIG_CHANGED')
            need(read(source / 'RELINK_CONTRACT.json', COMMAND_PIN) == command_raw, 'COMMAND_SOURCE_CHANGED')
            read(Path(__file__).resolve().parent / 'dependency_gate.py', GATE_PIN)
            read(repo / 'candidates/host93_first_n0_sources/pc1_reference_execution/run_reference.py', HELPER_PIN)
            need(d.verify(g, o, l, repo, catalog) == baseline, 'DEPENDENCY_CHANGED')
            l.validate(g, o, binding, profile)
            for path, expected in ((repo / 'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py', h.PINS['bootstrap.py']),
                    (bdir / 'binding_observer.py', h.PINS['binding_observer.py']),
                    (bdir / 'local_mount_profile.py', h.PINS['local_mount_profile.py']),
                    (repo / 'candidates/host93_ci_recovery/ci_support_v3.py', h.PINS['ci_support_v3.py'])):
                read(path, expected)
            need(g.checked(Path(cfg['binding']['path']), cfg['binding']['identity']) == binding_raw and
                 g.decode(g.checked(Path(cfg['profile']['path']), cfg['profile']['identity'])) == profile, 'PROFILE_CHANGED')
            need(input_buffers(g, repo, source, reuse) == buffers, 'ORIGINAL_SOURCE_OR_CACHE_CHANGED')
            verify_copies(g, work, buffers)
            need(commands(catalog, work, contract) == argv, 'ARGV_CHANGED')
            need(environment(catalog, work) == env, 'ENV_CHANGED')
            need(sorted(p.name for p in search.iterdir()) == ['as', 'cc1plus', 'collect2', 'ld'], 'SEARCH_ENTRIES')
            for name in ('cc1plus', 'collect2', 'as', 'ld'):
                need((search / name).is_symlink() and str((search / name).resolve(strict=True)) == catalog['programs'][name], 'SEARCH_TARGET')
            if 'object' in result:
                need(g.checked(work / 'pc01_main.o', result['object'], 64 * MIB, fixed_leaf='pc01_main.o') is not None, 'OBJECT_CHANGED')
        binary_check = lambda: d.check_binary(g, repo, catalog, work / 'pc01')
        need(time.monotonic() <= started + 30, 'INCOMPLETE_INITIAL_STAGE_WINDOW')
        supervised_sequence(s, support, base, work, argv, env, stop, owner, preflight, binary_check, result)
        preflight()
        need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_POSTFLIGHT_WINDOW')
        result.update(status='COMPLETE_DRIVER_COMPILE_LINK_ONLY', seconds=time.monotonic() - started,
                      shared_seconds_cap=180, tail_reserved_seconds=30, cpu_affinity_count=1,
                      compiler_catalog_identity=identity(catalog_raw), reuse_identity=identity(reuse_raw))
    except BaseException as error:
        failure = error
        result['failure_type'] = type(error).__name__
        result['failure_code'] = safe_failure_code(error)
    finally:
        # Fixed original helpers retain first failure and restore owner timer.
        if h is not None:
            failure = h.save_preserving_failure(work, result, failure)
            failure = h.restore_preserving_failure(old_alarm, failure)
        else:
            for fn, args in ((signal.setitimer, (signal.ITIMER_REAL, 0)), (signal.signal, (signal.SIGALRM, old_alarm))):
                try:
                    fn(*args)
                except BaseException as error:
                    if failure is None:
                        failure = error
    if failure is not None:
        raise failure
    return result


SAFE_FAILURE_CODES = ('CALLER_SOURCE_CHANGED', 'CUMULATIVE_RSS_GATE_6G', 'FIXED_INTERPRETER', 'ARGV_CHANGED', 'BINARY_CHANGED_POSTFLIGHT', 'COMMAND_SOURCE_CHANGED', 'COMPILE_OBJECT', 'COMPILE_RELOCATABLE_ELF', 'CONFIG_CHANGED', 'CPU_AFFINITY', 'DEPENDENCY_CHANGED', 'DISK_AVAILABLE_3G', 'ENTRY_T0_REQUIRED', 'ENV_CHANGED', 'EXPLICIT_RELINK_AND_ISOLATION_REQUIRED', 'FIXED_ARGV_MAPPING', 'FIXED_CACHE_RELATIVE', 'FIXED_COMPILER_CATALOG', 'FIXED_CONFIG', 'FIXED_LIBRARY_DIRECTORY', 'FIXED_SOURCE_COUNTS', 'FIXED_SOURCE_RELATIVE', 'FRESH_DISJOINT_WORK', 'INCOMPLETE_INITIAL_STAGE_WINDOW', 'INCOMPLETE_PHASE_WINDOW', 'INCOMPLETE_POSTFLIGHT_WINDOW', 'INCOMPLETE_TAIL_RESERVE', 'INHERITED_HARD_LIMIT', 'MEM_AVAILABLE_8G', 'NETWORK_FORBIDDEN', 'OBJECT_CHANGED', 'OBJECT_CHANGED_POSTFLIGHT', 'ORIGINAL_COMPILER_IDENTITY', 'ORIGINAL_SOURCE_OR_CACHE_CHANGED', 'PC01_RELINK_SHARED_DEADLINE', 'PHASE_EXIT_OR_CLEANUP', 'PROFILE_CHANGED', 'REGULAR_NOT_THIN_ARCHIVE', 'SEARCH_ENTRIES', 'SEARCH_TARGET', 'SOURCE_CANONICAL', 'SOURCE_CAP', 'SOURCE_HASH_OR_DRIFT', 'SOURCE_SIZE', 'STAGED_BYTES_CHANGED', 'STAGE_PATH', 'STAGE_WRITE', 'TIMER_OWNERSHIP')


def safe_failure_code(error):
    return str(error) if type(error) in (ValueError, TimeoutError, RuntimeError) and str(error) in SAFE_FAILURE_CODES else None


def main(argv=None, *, started=None, source_pin=None):
    import argparse
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--private-config', required=True, type=Path)
    p.add_argument('--execute-reviewed-relink', action='store_true')
    args = p.parse_args(argv)
    def audit(event, unused):
        if event.startswith('socket.') or event == 'urllib.Request':
            raise RuntimeError('NETWORK_FORBIDDEN')
    sys.addaudithook(audit)
    result = run(args.private_config, args.execute_reviewed_relink, started=started, source_pin=source_pin)
    print(json.dumps({'status': result['status'], 'phases': len(result['stages']), 'rtl_executed': False}))
