"""Fresh official473 -> sole seqnum initializer patch -> one CI build -> tiny.

Import and cold tests perform no network or native execution. run() is called
only by the complete, separately pinned CI entry. Every process, including
acquisition and the ten host-tool probes, uses the parent's existing supervisor.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before project loads')
if __name__ == '__main__':
    raise SystemExit('load the pinned component through the CI coordinator')

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import types

HERE = Path(__file__).absolute().parent
PINS_BYTES = 2791
PINS_SHA = 'cc070fce2a6f1ef8cbba5a78cfca8937e21d6e2233d1e0aa9288dd50ee266538'
PREFIX = 'development_snapshots/'
SUPPORT = PREFIX + 'canonical_host93_fixed_core_build_source_20261018/run_build_gate.py'
ACQ = PREFIX + 'canonical_host93_official_source_acquisition_source_20261018/receipt600_future_v3/'
PATCH = PREFIX + 'canonical_host93_verilator_seqnum_build_source_20261018/'
MICRO = PREFIX + 'canonical_host93_derived_micro_source_20261018/'
MODES = PREFIX + 'canonical_host93_dependency_source_20261018/probe/MODE_DEFINITIONS.json'
COMMIT = '4e194cc3ec8e27b18e17f80d7f99c15f984bbdae'
ORIGINAL_SHA = 'bddc3100c2ce83d7a4fe4656b0ff33cca1be70ea9a8295037c6aea72bc0ec6c1'
DERIVED_SHA = '380f292c6e82ce30cd7c0b3375ac3f2b91e5c1e872a2c733ca6d0490122cf6fb'
TOOL_NAMES = ('autoconf', 'autom4te', 'bison', 'flex', 'm4', 'gcc', 'g++', 'make', 'ar', 'perl', 'python3')
FIVE = ('autoconf', 'autom4te', 'm4', 'flex', 'bison')
EXPECTED_RUN = [
    'HOST93_MICRO_SCOPE_OK same_name=dual.micro_top distinct_context=1 distinct_model=1 distinct_scope=1',
    'HOST93_MICRO_DPI_OK writes=3 export_reads_checked=1',
    'HOST93_MICRO_STATE_OK steps_a=17 steps_b=32 count_a=137 count_b=455',
    'HOST93_MICRO_LIFETIME_OK reset_a=7 preserved_b=455 closed_a=1 continued_b=469',
    'HOST93_MICRO_PASS',
]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def initial_read(path, size, expected):
    """Descriptor walk, bounded bytes, stable inode, hash before compile."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and type(size) is int and
            0 <= size <= 4 * 1024**2, 'bounded absolute source')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'source regular size')
            chunks, count = [], 0
            while count <= size:
                block = os.read(fd, min(65536, size + 1 - count))
                if not block:
                    break
                chunks.append(block)
                count += len(block)
            raw = b''.join(chunks)
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(len(raw) == size and sha(raw) == expected and
                    stamp(before) == stamp(os.fstat(fd)) ==
                    stamp(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                    'fixed stable same-buffer source')
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def module(raw, path, name):
    loaded = types.ModuleType(name)
    loaded.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), loaded.__dict__)
    return loaded


def load_sources(repo):
    pins = json.loads(initial_read(HERE / 'SOURCE_PINS.json', PINS_BYTES, PINS_SHA))
    buffers = {name: initial_read(repo / name, p['bytes'], p['sha256']) for name, p in pins.items()}
    support = module(buffers[SUPPORT], repo / SUPPORT, 'fixed_ci_toolchain_filesystem_support')
    return support, pins, buffers


def save_private(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    require(len(raw) <= 4 * 1024**2, 'private receipt cap')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        require(stream.write(raw) == len(raw), 'complete receipt write')
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def write_fixture(path, raw):
    require(type(raw) is bytes and len(raw) <= 1024**2, 'small fixed fixture')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        require(stream.write(raw) == len(raw), 'complete fixture write')


def limits(total, work, as_mib, fsize_mib, tree_mib, log_bytes=1024**2):
    return {'total_seconds': total, 'work_seconds': work, 'cpu_seconds': work,
            'as_bytes': as_mib * 1024**2, 'fsize_bytes': fsize_mib * 1024**2,
            'tree_bytes': tree_mib * 1024**2, 'log_bytes': log_bytes,
            'sample_rows': total + 2, 'file_count': 4096, 'entry_count': 8192}


SOURCE_LIMITS = limits(420, 400, 512, 64, 80, 128 * 1024)
PROBE_LIMITS = limits(30, 10, 512, 4, 8, 65536)
BUILD_LIMITS = {
    'autoconf': limits(180, 160, 1024, 64, 64, 256 * 1024),
    'configure': limits(180, 160, 1024, 64, 128, 256 * 1024),
    'make': limits(3600, 3570, 4096, 1024, 2048),
}
TINY_LIMITS = {
    'version': limits(30, 10, 512, 4, 1),
    'generate': limits(120, 90, 1024, 8, 16),
    'compile': limits(300, 240, 2048, 32, 96),
    'run': limits(30, 10, 512, 4, 96),
}
for _item in TINY_LIMITS.values():
    _item.update(file_count=512, entry_count=1024)


def host_identities(support):
    result = {}
    for invoked in tuple('/usr/bin/' + x for x in TOOL_NAMES) + ('/bin/sh',):
        path = Path(os.path.realpath(invoked))
        observed = support.identity(path, 64 * 1024**2)
        require(int(observed['mode'], 8) & 0o111, 'required CI tool not executable')
        result[invoked] = {'path': str(path), **observed}
    return result


def unchanged_tools(support, expected):
    require(host_identities(support) == expected, 'in-job tool identity or resolution changed')


def environment(work, verilator=None):
    env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC',
           'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'), 'SHELL': '/bin/sh',
           'CONFIG_SHELL': '/bin/sh', 'CONFIG_SITE': '/dev/null',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
           'MAKE': '/usr/bin/make', 'CC': '/usr/bin/gcc', 'CXX': '/usr/bin/g++',
           'AR': '/usr/bin/ar', 'PERL': '/usr/bin/perl', 'PYTHON3': '/usr/bin/python3',
           'LEX': '/usr/bin/flex', 'YACC': '/usr/bin/bison', 'M4': '/usr/bin/m4',
           'AUTOM4TE': '/usr/bin/autom4te', 'OBJCACHE': '', 'ac_cv_prog_OBJCACHE': ''}
    if verilator is not None:
        env.update(VERILATOR_ROOT=str(verilator), VERILATOR_BIN='verilator_bin',
                   VERILATOR_SRC_VERSION=COMMIT)
    return env


def acquisition_argv(repo, output, buffers):
    raw = buffers[ACQ + 'acquire_official_source.py']
    # The fixed source buffer itself is embedded, never path-imported in child.
    code = ('import sys\n'
            'if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode): raise SystemExit(1)\n'
            'import types,time\nfrom pathlib import Path\n'
            "m=types.ModuleType('fixed_ci_official473_acquisition')\n"
            'm.__file__=' + repr(str(repo / (ACQ + 'acquire_official_source.py'))) + '\n'
            'exec(compile(' + repr(raw) + ",m.__file__,'exec',dont_inherit=True),m.__dict__)\n"
            'base,plan,selected=m.load_inputs()\n'
            'root=m.checked_output_root(base,Path(' + repr(str(output)) + '),Path(' + repr(str(repo)) + '))\n'
            'start=time.monotonic()\n'
            'budget=m.shared_budget(base,start,start+400)\n'
            'm.execute(base,plan,selected,root,budget)\n')
    return ['/usr/bin/python3', '-I', '-S', '-B', '-c', code]


ACQUISITION_PHASES = ('official_source473',)

TRANSPORT_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                  'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
                  'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE')


def phase_environment(name, base):
    """Only fixed acquisition phases inherit existing platform transport settings.

    Values are forwarded as-is, never written into a receipt or public evidence.
    Native/build phases retain their original clean environment. No proxy or CA
    is created and no direct-network fallback is attempted.
    """
    result = dict(base)
    if name in ACQUISITION_PHASES:
        for key in TRANSPORT_KEYS:
            if key in os.environ:
                result[key] = os.environ[key]
    return result


def checked_phase(call_phase, support, tools, name, argv, cwd, env, bound, tree_root=None):
    unchanged_tools(support, tools)
    result = call_phase(name, list(argv), Path(cwd), phase_environment(name, env), dict(bound))
    require(type(result) is dict and result['record']['exit_code'] == 0 and
            result['record']['cleanup_confirmed'] is True, 'supervised phase did not succeed')
    raw = result['raw_log']
    require(type(raw) is bytes and len(raw) <= bound['log_bytes'], 'bounded private phase log')
    unchanged_tools(support, tools)
    inventory = None
    if tree_root is not None:
        inventory = support.tree_inventory(tree_root, bound['tree_bytes'], bound['file_count'],
                                           bound['entry_count'], bound['fsize_bytes'])
    return result, inventory


def verify_official473(support, source, buffers):
    table = json.loads(buffers[ACQ + 'FIXED_CORE_MEMBERS.json'])
    require(table['revision'] == COMMIT and table['count'] == 473 and
            table['blob_bytes'] == 11747893, 'fixed official473 totals')
    inventory = support.tree_inventory(source, 16 * 1024**2, 473, 1024, 1024**2)
    expected = {row['path']: row for row in table['members']}
    actual = {n: row for n, row in inventory['entries'].items() if row['kind'] == 'regular'}
    require(set(actual) == set(expected) and inventory['files'] == 473 and
            inventory['bytes'] == 11747893, 'exact fresh official473 inventory')
    for name, row in expected.items():
        identity = support.identity(source / name, row['bytes'], git=True)
        require(identity['bytes'] == row['bytes'] and identity['git_blob'] == row['git_blob_sha'] and
                identity['mode'] == '0o600', 'fresh original Git blob or source mode')
    return table, inventory


def materialize_patched(support, source, destination, table, original_inventory, buffers):
    original = buffers[PATCH + 'ORIGINAL_V3ProtectLib.cpp']
    derived = buffers[PATCH + 'DERIVED_V3ProtectLib.cpp']
    patch = json.loads(buffers[PATCH + 'PATCH.json'])
    old, new = patch['old_exact_utf8'].encode(), patch['new_exact_utf8'].encode()
    require(len(original) == 22417 and sha(original) == ORIGINAL_SHA and
            len(derived) == 22430 and sha(derived) == DERIVED_SHA and
            original.count(old) == 1 and derived == original.replace(old, new, 1) and
            derived.count(new) == 1 and derived.replace(new, old, 1) == original,
            'unique exact forward and reverse initializer patch')
    support.fresh_directory(destination)
    for row in table['members']:
        name = row['path']
        before = original_inventory['entries'][name]
        support.copy_member(source / name, destination, name, before,
                            0o700 if row['mode'] == '100755' else 0o600)
    target = destination / 'src/V3ProtectLib.cpp'
    require(support.checked_read(target, len(original), ORIGINAL_SHA) == original, 'patch exact fresh original')
    parent, fd, info = support.regular_fd(target)
    os.close(fd)
    try:
        require(info.st_nlink == 1, 'independent fresh patch inode')
        fd = os.open(target.name, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, dir_fd=parent)
        try:
            require(os.fstat(fd).st_ino == info.st_ino, 'patch same fresh inode')
            offset = 0
            while offset < len(derived):
                count = os.write(fd, derived[offset:])
                require(count > 0, 'complete patch write')
                offset += count
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    require(support.checked_read(target, len(derived), DERIVED_SHA) == derived, 'derived source readback')
    after = support.tree_inventory(destination, 16 * 1024**2, 473, 1024, 1024**2)
    require(after['files'] == 473 and after['bytes'] == 11747906, 'only thirteen added initializer bytes')
    for row in table['members']:
        name = row['path']
        entry = after['entries'][name]
        require(entry['mode'] == ('0o700' if row['mode'] == '100755' else '0o600'), 'fresh copied executable mapping')
        expected = DERIVED_SHA if name == 'src/V3ProtectLib.cpp' else original_inventory['entries'][name]['sha256']
        require(entry['sha256'] == expected, 'fresh derived source has unauthorized edit')
    return {'original': {'bytes': 22417, 'sha256': ORIGINAL_SHA},
            'derived': {'path': str(target), 'bytes': 22430, 'sha256': DERIVED_SHA},
            'only_changed_member': 'src/V3ProtectLib.cpp', 'replacement_count': 1,
            'fresh_build_no_reused_objects': True}, after


def version_value(tool, raw):
    text = raw.decode('utf-8')
    head = text.splitlines()[0] if text.splitlines() else ''
    patterns = {'autoconf': r'autoconf \(GNU Autoconf\) (\d+\.\d+(?:\.\d+)?)',
                'autom4te': r'autom4te \(GNU Autoconf\) (\d+\.\d+(?:\.\d+)?)',
                'm4': r'm4 \(GNU M4\) (\d+\.\d+(?:\.\d+)?)',
                'flex': r'flex (\d+\.\d+(?:\.\d+)?)',
                'bison': r'bison \(GNU Bison\) (\d+\.\d+(?:\.\d+)?)'}
    match = re.fullmatch(patterns[tool], head)
    require(match is not None and len(raw) <= 65536, 'recognized official tool version')
    return match[1]


def qualify_tools(support, tools, buffers, work, call_phase, env):
    modes = json.loads(buffers[MODES])['modes']
    root = work / 'qualification'
    support.fresh_directory(root)
    results, versions = {}, {}
    for kind in ('version', 'micro'):
        for tool in FIVE:
            name = tool + '-' + kind
            mode = modes[name]
            folder = root / name
            support.fresh_directory(folder)
            for filename, text in mode['fixture_files'].items():
                support.relative_name(filename)
                write_fixture(folder / filename, text.encode())
            result, tree = checked_phase(call_phase, support, tools, 'host_' + name,
                ['/usr/bin/' + tool] + mode['argv_tail'], folder, env, PROBE_LIMITS, folder)
            raw = result['raw_log']
            if kind == 'version':
                versions[tool] = version_value(tool, raw)
                if tool == 'autom4te':
                    require(versions['autom4te'] == versions['autoconf'], 'autoconf and autom4te version pair')
            else:
                require(raw.decode('utf-8') == mode['expected_log_exact'], 'exact tiny tool output')
                for filename, output in mode['generated_files'].items():
                    pin = tree['entries'].get(filename)
                    require(pin is not None and pin['kind'] == 'regular', 'tiny generated file missing')
                    text = support.checked_read(folder / filename, pin['bytes'], pin['sha256']).decode('utf-8')
                    for token in output['contains']:
                        if token == 'Generated by GNU Autoconf 2.72':
                            token = 'Generated by GNU Autoconf ' + versions[tool]
                        require(token in text, 'tiny generated resource witness')
            results[name] = {'exit_code': 0, 'cleanup_confirmed': True,
                             'log_sha256': sha(raw), 'generated_files': tree['files'],
                             'usage': result['usage']}
    return {'versions': versions, 'probes': results, 'version_count': 5, 'tiny_count': 5,
            'generated_probe_code_executed': False,
            'scope': 'onsite official-image tool identity and finite generation probes only'}


def build_commands(root, work):
    return {
        'autoconf': ['/usr/bin/autoconf', '--warnings=all', '--output=configure', 'configure.ac'],
        'configure': ['/bin/sh', './configure', '--srcdir=.', '--cache-file=/dev/null',
            '--prefix=' + str(work / 'unused-install-prefix'), '--disable-partial-static',
            '--disable-tcmalloc', '--disable-jemalloc', '--disable-defenv', '--disable-ccwarn',
            '--disable-longtests', '--with-solver=no', 'CC=/usr/bin/gcc', 'CXX=/usr/bin/g++',
            'AR=/usr/bin/ar', 'PERL=/usr/bin/perl', 'PYTHON3=/usr/bin/python3',
            'LEX=/usr/bin/flex', 'YACC=/usr/bin/bison', 'CPPFLAGS=', 'CFLAGS=-g0',
            'CXXFLAGS=-g0', 'LDFLAGS=', 'LIBS='],
        'make': ['/usr/bin/make', '-C', 'src', '-j1', 'opt', 'SHELL=/bin/sh',
            'MAKE=/usr/bin/make', 'BEAR=', 'BEAR_OBJ_OPT=', 'OBJCACHE=',
            'VERILATOR_NO_OPT_BUILD=0', 'VL_NOOPT=0', 'VL_DEBUG=', 'VL_VLCOV='],
    }


def objcache_configure_witness(raw):
    """Finite generated AC_CHECK_PROG cache-hit branch, not a shell parser.

    With ac_cv_prog_OBJCACHE present and empty, ${name+y} expands to y;
    POSIX test y succeeds, so the search branch is skipped. The exact hit
    branch below only reports cached, then the generated assignment is empty.
    Unknown autoconf rendering fails before configure execution.
    """
    text = raw.decode('utf-8')
    prefix = ('if test ${ac_cv_prog_OBJCACHE+y}\nthen :\n'
              '  printf %s "(cached) " >&6\nelse $as_nop\n')
    suffix = '\nfi\nOBJCACHE=$ac_cv_prog_OBJCACHE\n'
    require(text.count(prefix) == 1 and text.count(suffix) == 1, 'finite OBJCACHE cache branch')
    start = text.index(prefix)
    end = text.index(suffix, start) + len(suffix)
    require(end - start <= 8192 and 'ac_cv_prog_OBJCACHE' not in text[:start] and
            'ac_cv_prog_OBJCACHE' not in text[end:], 'bounded sole OBJCACHE cache block')
    require('if test "x$OBJCACHE" != "x" ; then\n  objcache_version=$($OBJCACHE --version | head -1)' in text[end:],
            'ccache version call retains official nonempty guard')
    return {'cache_variable': 'ac_cv_prog_OBJCACHE', 'cache_value': '',
            'generated_branch_bytes': len(text[start:end].encode('utf-8')),
            'generated_branch_sha256': sha(text[start:end].encode('utf-8')),
            'semantics': 'set-empty cache takes exact cached branch; no ccache discovery or version call'}


def verify_objcache_disabled(support, root, configured=False):
    original = support.checked_read(root / 'configure.ac', 33835,
        'e9c0af2019ff3e2786596fccf4ed5b90048cead25c5ee385d033285a5d330e88')
    fixed = (b'AC_CHECK_PROG(OBJCACHE,ccache,ccache)\n'
             b'if test "x$OBJCACHE" != "x" ; then\n'
             b'  objcache_version=$($OBJCACHE --version | head -1)\n')
    require(original.count(fixed) == 1, 'official OBJCACHE check and nonempty invocation guard')
    pin = support.identity(root / 'configure', 4 * 1024**2)
    proof = objcache_configure_witness(support.checked_read(root / 'configure', pin['bytes'], pin['sha256']))
    proof['official_configure_ac'] = {'bytes': 33835,
        'sha256': 'e9c0af2019ff3e2786596fccf4ed5b90048cead25c5ee385d033285a5d330e88', 'lines': [298, 299, 300, 301]}
    if configured:
        outputs = []
        for name in ('Makefile', 'src/Makefile', 'src/Makefile_obj', 'include/verilated.mk'):
            source_pin = support.identity(root / (name + '.in'), 4 * 1024**2)
            source = support.checked_read(root / (name + '.in'), source_pin['bytes'], source_pin['sha256']).decode('utf-8')
            lines = [line for line in source.splitlines() if '@OBJCACHE@' in line]
            if not lines:
                continue
            require(len(lines) == 1 and re.fullmatch(r'[ \t]*OBJCACHE[ \t]*[:?]?=[ \t]*@OBJCACHE@[ \t]*', lines[0]),
                    'finite official OBJCACHE substitution assignment')
            output_pin = support.identity(root / name, 4 * 1024**2)
            output = support.checked_read(root / name, output_pin['bytes'], output_pin['sha256']).decode('utf-8')
            assignments = re.findall(r'(?m)^[ \t]*OBJCACHE[ \t]*[:?+]?=[^\n]*$', output)
            require(assignments == [lines[0].replace('@OBJCACHE@', '')], 'configured OBJCACHE must be exactly empty')
            outputs.append(name)
        require(outputs, 'configured OBJCACHE assignment witness missing')
        proof['configured_empty_assignments'] = outputs
    return proof


def immutable_sources(support, root, original):
    for name, row in original['entries'].items():
        if row['kind'] == 'regular':
            require(support.identity(root / name, row['bytes']) ==
                    {k: row[k] for k in ('bytes', 'sha256', 'mode')}, 'derived input changed during build')


def project_micro(buffers, repo, fixtures):
    raw = buffers[MICRO + 'run_micro_gate.py']
    lines = raw.splitlines(keepends=True)
    wanted = ('inventory_text', 'hierarchy_witness', 'check_log')
    functions = {n.name: b''.join(lines[n.lineno - 1:n.end_lineno]) + b'\n'
                 for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name in wanted}
    require(set(functions) == set(wanted), 'exact finite micro projection')
    contract = module(buffers[MICRO + 'init_contract.py'], repo / (MICRO + 'init_contract.py'),
                      'fixed_finite_ci_initializer_contract')
    namespace = {'require': require, 're': re, 'shlex': shlex, 'Path': Path,
                 'F': str(fixtures), 'contract_module': lambda: contract}
    projection = b'\n'.join(functions[name] for name in wanted)
    require(len(projection) == 6055 and sha(projection) ==
            '7bae86ca47e3cfe319fed2cdaf69b722be004279672a1f4c62e14dfed47b06a0',
            'fixed finite micro projection bytes before compile')
    exec(compile(projection, 'verified_fixed_micro_projection', 'exec', dont_inherit=True), namespace)
    return namespace, {'bytes': len(projection), 'sha256': sha(projection), 'functions': list(wanted)}


def verify_runtime(support, root, runtime):
    require(support.tree_inventory(root / 'include', 32 * 1024**2, 256, 512, 4 * 1024**2) ==
            runtime['include'], 'same-job configured include closure drift')
    for name, pin in runtime['wrappers'].items():
        require(pin['path'] == str(root / 'bin' / name) and
                support.identity(pin['path'], 4 * 1024**2) ==
                {k: pin[k] for k in ('bytes', 'sha256', 'mode')}, 'same-job runtime wrapper drift')


def run_micro(support, tools, buffers, repo, work, root, call_phase, backend, runtime):
    micro = work / 'micro'
    support.fresh_directory(micro)
    for name in ('obj', 'fixtures', 'home', 'tmp'):
        support.fresh_directory(micro / name)
    fixtures = micro / 'fixtures'
    for name in ('tiny.sv', 'main.cpp'):
        write_fixture(fixtures / name, buffers[MICRO + 'fixtures/' + name])
    checker, projection = project_micro(buffers, repo, fixtures)
    env = environment(micro, root)
    argv = {
        'version': [backend['path'], '--version'],
        'generate': [backend['path'], '--cc', '--hierarchical', '--exe', '--threads', '1',
            '--build-jobs', '1', '--verilate-jobs', '1', '--top-module', 'micro_top',
            '--prefix', 'Vmicro_top', '--Mdir', str(micro / 'obj'),
            str(fixtures / 'tiny.sv'), str(fixtures / 'main.cpp')],
        'compile': ['/usr/bin/make', '-C', str(micro / 'obj'), '-f', 'Vmicro_top.mk', '-j1',
            'OPT_FAST=-O0', 'OPT_SLOW=-O0', 'OPT_GLOBAL=-O0', 'Vmicro_top'],
        'run': [str(micro / 'obj/Vmicro_top')],
    }
    plan = {'phases': TINY_LIMITS, 'expected_run_stdout': EXPECTED_RUN}
    results, witness = {}, None
    for phase in ('version', 'generate', 'compile', 'run'):
        verify_runtime(support, root, runtime)
        for name in ('tiny.sv', 'main.cpp'):
            fixed = buffers[MICRO + 'fixtures/' + name]
            require(support.checked_read(fixtures / name, len(fixed), sha(fixed)) == fixed,
                    'fixed tiny input drift')
        require(support.identity(backend['path'], 64 * 1024**2) ==
                {k: backend[k] for k in ('bytes', 'sha256', 'mode')}, 'same-job backend drift')
        result, tree = checked_phase(call_phase, support, tools, 'derived_tiny_' + phase,
                                    argv[phase], micro, env, TINY_LIMITS[phase], micro)
        if phase in ('generate', 'compile', 'run'):
            witness = checker['hierarchy_witness'](support, tree, phase != 'generate')
            # Historical witness wording is not imported as evidence in this job.
            witness.pop('original_uninitialized_failure_preserved', None)
            witness['status'] = 'SAME_JOB_FINITE_DERIVED_STRUCTURAL_WITNESS'
        checker['check_log'](plan, phase, result['raw_log'], witness)
        verify_runtime(support, root, runtime)
        for name in ('tiny.sv', 'main.cpp'):
            fixed = buffers[MICRO + 'fixtures/' + name]
            require(support.checked_read(fixtures / name, len(fixed), sha(fixed)) == fixed,
                    'fixed tiny input drift')
        results[phase] = {'exit_code': 0, 'cleanup_confirmed': True,
                          'log_sha256': sha(result['raw_log']), 'usage': result['usage'],
                          'tree_sha256': sha(json.dumps(tree, sort_keys=True).encode())}
        save_private(work / ('tiny_' + phase + '_tree.json'), tree)
    return {'status': 'PASS_NEW_DERIVED_FOUR_STAGE_TINY', 'phases': results,
            'witness': witness, 'projection': projection,
            'expected_run_stdout': EXPECTED_RUN,
            'does_not_claim_production_host_or_full_system_rtl': True}


def run(repo: Path, work: Path, call_phase):
    """One fresh run; no retries, package installs, old objects, or old reviews.

    call_phase(name, argv, cwd, environment, limits) returns record/raw_log/usage;
    raw bytes stay private. It owns the shared 6600-second wall and 1-CPU limit.
    This function returns JSON-friendly private in-job identities to its caller.
    """
    repo, work = Path(repo), Path(work)
    require(repo.is_absolute() and work.is_absolute() and '..' not in repo.parts and
            '..' not in work.parts and repo != work and repo not in work.parents and
            work != HERE and HERE not in work.parents,
            'fresh private output outside repository')
    support, pins, buffers = load_sources(repo)
    tools = host_identities(support)  # Missing tools fail before output/network.
    require(not os.path.lexists(work), 'fresh component work required')
    old_umask = os.umask(0o077)
    try:
        support.fresh_directory(work)
        for name in ('home', 'tmp'):
            support.fresh_directory(work / name)
        save_private(work / 'host_tools.json', tools)
        save_private(work / 'source_pins.json', pins)
        env = environment(work)
        acquired, _ = checked_phase(call_phase, support, tools, 'official_source473',
            acquisition_argv(repo, work / 'acquired', buffers), work, env, SOURCE_LIMITS, work / 'acquired')
        receipt_pin = support.identity(work / 'acquired/SOURCE.json', 1024**2)
        receipt = json.loads(support.checked_read(work / 'acquired/SOURCE.json',
                                                receipt_pin['bytes'], receipt_pin['sha256']))
        require(not os.path.lexists(work / 'acquired/FAILED.json') and
                receipt['commit'] == COMMIT and receipt['archive_complete'] is True and
                receipt['selected_bytes'] == 11747893 and len(receipt['verified_members']) == 473 and
                receipt['cleanup_errors'] == [], 'fresh complete official source receipt')
        table, original = verify_official473(support, work / 'acquired/verilator', buffers)
        root = work / 'verilator'
        patch, derived = materialize_patched(support, work / 'acquired/verilator', root,
                                            table, original, buffers)
        save_private(work / 'official473_tree.json', original)
        save_private(work / 'derived473_tree.json', derived)
        qualification = qualify_tools(support, tools, buffers, work, call_phase, env)
        save_private(work / 'tool_qualification.json', qualification)
        env = environment(work, root)
        commands = build_commands(root, work)
        builds = {}
        required = {
            'autoconf': ('configure',),
            'configure': ('Makefile', 'src/Makefile', 'src/Makefile_obj', 'src/config_package.h',
                          'include/verilated.mk', 'include/verilated_config.h', 'config.status', 'config.log'),
            'make': ('bin/verilator_bin', 'src/config_rev.h'),
        }
        for phase in ('autoconf', 'configure', 'make'):
            immutable_sources(support, root, derived)
            for relative in ('.autom4te.cfg', 'aclocal.m4', '.git'):
                require(not os.path.lexists(root / relative), 'unapproved build configuration')
            require(not os.path.lexists(work / 'home/.autom4te.cfg'), 'unapproved HOME configuration')
            if phase == 'configure':
                require(env['ac_cv_prog_OBJCACHE'] == env['OBJCACHE'] == '', 'explicit empty ccache cache binding')
                verify_objcache_disabled(support, root)
            result, tree = checked_phase(call_phase, support, tools, 'fresh_' + phase,
                                        commands[phase], root, env, BUILD_LIMITS[phase], root)
            immutable_sources(support, root, derived)
            require(all(tree['entries'].get(n, {}).get('bytes', 0) > 0 for n in required[phase]),
                    'required fresh build output missing')
            builds[phase] = {'exit_code': 0, 'cleanup_confirmed': True,
                             'log_sha256': sha(result['raw_log']), 'usage': result['usage']}
            if phase in ('autoconf', 'configure'):
                builds[phase]['objcache_disabled'] = verify_objcache_disabled(support, root, phase == 'configure')
            save_private(work / ('build_' + phase + '_tree.json'), tree)
        backend = {'path': str(root / 'bin/verilator_bin'),
                   **support.identity(root / 'bin/verilator_bin', 64 * 1024**2)}
        require(int(backend['mode'], 8) & 0o111 and backend['bytes'] > 0, 'new backend executable')
        runtime = {'include': support.tree_inventory(root / 'include', 32 * 1024**2, 256, 512, 4 * 1024**2),
                   'wrappers': {name: {'path': str(root / 'bin' / name),
                       **support.identity(root / 'bin' / name, 4 * 1024**2)}
                       for name in ('verilator', 'verilator_includer')}}
        runtime_pin = save_private(work / 'configured_runtime.json', runtime)
        tiny = run_micro(support, tools, buffers, repo, work, root, call_phase, backend, runtime)
        immutable_sources(support, root, derived)
        unchanged_tools(support, tools)
        result = {'schema': 'CI_FRESH_PATCHED_VERILATOR473_AND_TINY_V1',
                  'status': 'PASS_FRESH_DERIVED_TOOLCHAIN_AND_TINY_ONLY',
                  'backend': backend, 'verilator_root': str(root), 'host_programs': tools,
                  'source_commit': COMMIT, 'source_members': 473, 'source_original_bytes': 11747893,
                  'source_receipt': receipt_pin, 'source_phase_usage': acquired['usage'],
                  'patch': patch, 'qualification': qualification, 'build': builds,
                  'configured_runtime': runtime_pin, 'tiny': tiny,
                  'historical_actual_or_review_inherited': False,
                  'production_host_claim': False}
        save_private(work / 'RESULT.json', result)
        return result
    finally:
        os.umask(old_umask)
