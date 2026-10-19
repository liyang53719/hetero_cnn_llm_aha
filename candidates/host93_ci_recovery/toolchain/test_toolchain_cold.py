"""SOURCE and synthetic mocks only: no network, native tool or build execution."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import argparse
import ast
import builtins
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import tempfile
import types

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True, type=Path)
args = parser.parse_args()
HERE = Path(__file__).absolute().parent
RAW = (HERE / 'ci_toolchain.py').read_bytes()
EXPECTED_BYTES = 32715
EXPECTED_SHA = 'fcec5c2d6917cdfe460ff01d8a922500497971459d4269aabdbf3610e43f9b2d'
if len(RAW) != EXPECTED_BYTES or hashlib.sha256(RAW).hexdigest() != EXPECTED_SHA:
    raise ValueError('cold component pin mismatch')
g = types.ModuleType('fixed_ci_toolchain_cold')
g.__file__ = str(HERE / 'ci_toolchain.py')
exec(compile(RAW, g.__file__, 'exec', dont_inherit=True), g.__dict__)
support, pins, buffers = g.load_sources(args.repo)
tests = []


def test(name, fn):
    fn()
    tests.append(name)


def rejects(fn, part):
    try:
        fn()
    except (ValueError, KeyError, OSError, SystemExit) as error:
        g.require(part in str(error), 'wrong rejection: ' + str(error))
        return
    raise ValueError('expected rejection: ' + part)


def early_flags():
    for values in itertools.product((False, True), repeat=3):
        if all(values):
            continue
        seen = []
        fake = types.SimpleNamespace(flags=types.SimpleNamespace(
            isolated=values[0], no_site=values[1], dont_write_bytecode=values[2]))
        def importer(name, *a, **k):
            seen.append(name)
            if name == 'sys':
                return fake
            raise ValueError('late import reached')
        namespace = {'__name__': 'flags_cold', '__file__': g.__file__,
                     '__builtins__': dict(vars(builtins), __import__=importer)}
        rejects(lambda: exec(compile(RAW, g.__file__, 'exec', dont_inherit=True), namespace),
                'require Python -I -S -B')
        g.require(seen == ['sys'], 'earlyflags before all project/local loading')


test('seven_early_flag_refusals', early_flags)
test('fixed_thirteen_published_sources', lambda: g.require(len(pins) == 13, 'pins13'))
test('finite_projection_pin', lambda: g.require(g.project_micro(buffers, args.repo, Path('/synthetic/fixtures'))[1]
     ['sha256'] == '7bae86ca47e3cfe319fed2cdaf69b722be004279672a1f4c62e14dfed47b06a0', 'projection pin'))
test('limits_exact_build', lambda: g.require([(x['total_seconds'], x['work_seconds']) for x in g.BUILD_LIMITS.values()]
     == [(180, 160), (180, 160), (3600, 3570)], 'build budget'))
test('limits_exact_tiny', lambda: g.require([(x['total_seconds'], x['work_seconds']) for x in g.TINY_LIMITS.values()]
     == [(30, 10), (120, 90), (300, 240), (30, 10)], 'tiny budget'))
test('source_same_buffer_embedded_not_path_import', lambda: g.require(
    repr(buffers[g.ACQ + 'acquire_official_source.py']) in g.acquisition_argv(args.repo, Path('/synthetic/output'), buffers)[-1]
    and not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'main'
                for n in ast.walk(ast.parse(g.acquisition_argv(args.repo, Path('/synthetic/output'), buffers)[-1]))),
    'verified acquisition literal buffer'))


def fixed_read_refusals():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        (root / 'good').write_bytes(b'fixed')
        (root / 'link').symlink_to(root / 'good')
        rejects(lambda: g.initial_read(root / 'good', 5, '0'*64), 'same-buffer')
        rejects(lambda: g.initial_read(root / 'good', 4, g.sha(b'fixed')), 'regular size')
        rejects(lambda: g.initial_read(root / 'link', 5, g.sha(b'fixed')), 'Too many levels')
        os.mkfifo(root / 'fifo')
        rejects(lambda: g.initial_read(root / 'fifo', 0, g.sha(b'')), 'regular size')
test('hash_size_symlink_fifo_refused', fixed_read_refusals)

for tool, text in (('autoconf', 'autoconf (GNU Autoconf) 2.71\n'),
                   ('autom4te', 'autom4te (GNU Autoconf) 2.71\n'),
                   ('m4', 'm4 (GNU M4) 1.4.19\n'), ('flex', 'flex 2.6.4\n'),
                   ('bison', 'bison (GNU Bison) 3.8.2\n')):
    test('onsite_version_' + tool, lambda tool=tool, text=text: g.version_value(tool, text.encode()))
test('unrecognized_version_refused', lambda: rejects(lambda: g.version_value('autoconf', b'pretend 2.71\n'), 'recognized official'))

checker, _ = g.project_micro(buffers, args.repo, Path('/synthetic/fixtures'))
plan = {'phases': g.TINY_LIMITS, 'expected_run_stdout': g.EXPECTED_RUN}
expected = ('\n'.join(g.EXPECTED_RUN) + '\n').encode()
test('tiny_exact_runtime', lambda: checker['check_log'](plan, 'run', expected))
test('tiny_runtime_wrong_count_refused', lambda: rejects(lambda: checker['check_log'](plan, 'run',
     expected.replace(b'count_b=455', b'count_b=456')), 'exact runtime'))
test('tiny_native_compile_in_generate_refused', lambda: rejects(lambda: checker['check_log'](plan, 'generate',
     b'g++ -O0 -c unexpected.cpp\n'), 'unexpectedly compiled'))

cached_configure = (b'if test ${ac_cv_prog_OBJCACHE+y}\nthen :\n'
    b'  printf %s "(cached) " >&6\nelse $as_nop\n'
    b'  ac_cv_prog_OBJCACHE=ccache\n'
    b'fi\nOBJCACHE=$ac_cv_prog_OBJCACHE\n'
    b'if test "x$OBJCACHE" != "x" ; then\n'
    b'  objcache_version=$($OBJCACHE --version | head -1)\nfi\n')
test('empty_cache_finite_generated_branch', lambda: g.objcache_configure_witness(cached_configure))
test('cache_test_nonempty_instead_of_set_refused', lambda: rejects(lambda:
    g.objcache_configure_witness(cached_configure.replace(b'${ac_cv_prog_OBJCACHE+y}', b'"$ac_cv_prog_OBJCACHE"')),
    'finite OBJCACHE'))
test('cache_hit_assignment_refused', lambda: rejects(lambda:
    g.objcache_configure_witness(cached_configure.replace(b'then :\n', b'then :\n  ac_cv_prog_OBJCACHE=ccache\n', 1)),
    'finite OBJCACHE'))
test('cache_later_override_refused', lambda: rejects(lambda:
    g.objcache_configure_witness(cached_configure + b'ac_cv_prog_OBJCACHE=ccache\n'), 'bounded sole'))
test('unguarded_ccache_version_refused', lambda: rejects(lambda:
    g.objcache_configure_witness(cached_configure.replace(b'if test "x$OBJCACHE" != "x" ; then\n', b'')),
    'nonempty guard'))
test('empty_cache_environment_explicit', lambda: g.require(
    g.environment(Path('/synthetic'))['ac_cv_prog_OBJCACHE'] == '', 'empty cache environment'))


def official_inventory_mocks(corruption=None):
    table = json.loads(buffers[g.ACQ + 'FIXED_CORE_MEMBERS.json'])
    rows = {r['path']: r for r in table['members']}
    seen = []
    class MockOfficial:
        def tree_inventory(self, *a):
            entries = {name: {'kind': 'regular'} for name in rows}
            if corruption == 'extra':
                entries['foreign.o'] = {'kind': 'regular'}
            return {'files': 473, 'bytes': 11747893, 'entries': entries}
        def identity(self, path, cap, git=False):
            name = Path(path).relative_to('/synthetic').as_posix()
            row = rows[name]
            seen.append(name)
            return {'bytes': row['bytes'], 'git_blob': '0'*40 if corruption == 'blob' else row['git_blob_sha'],
                    'mode': '0o700' if corruption == 'mode' else '0o600'}
    if corruption is None:
        g.verify_official473(MockOfficial(), Path('/synthetic'), buffers)
        g.require(len(seen) == 473 and set(seen) == set(rows), 'all473 independent Git blob checks')
    else:
        rejects(lambda: g.verify_official473(MockOfficial(), Path('/synthetic'), buffers),
                'exact fresh official473' if corruption == 'extra' else 'fresh original Git blob')
test('all_473_git_blob_identity_checks', official_inventory_mocks)
for corruption in ('extra', 'blob', 'mode'):
    test('official473_' + corruption + '_refused', lambda corruption=corruption: official_inventory_mocks(corruption))


def patch_only_synthetic_file(corruption=False):
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        source = base / 'source'
        source.mkdir(mode=0o700)
        (source / 'src').mkdir(mode=0o700)
        original = buffers[g.PATCH + 'ORIGINAL_V3ProtectLib.cpp']
        (source / 'src/V3ProtectLib.cpp').write_bytes(original)
        (source / 'src/V3ProtectLib.cpp').chmod(0o600)
        pin = support.identity(source / 'src/V3ProtectLib.cpp', len(original))
        inventory = {'entries': {'src/V3ProtectLib.cpp': dict(kind='regular', **pin)}}
        table = {'members': [{'path': 'src/V3ProtectLib.cpp', 'mode': '100644'}]}
        class SyntheticTotalsSupport:
            def __getattr__(self, name):
                return getattr(support, name)
            def tree_inventory(self, *a):
                # Only the single-file patch IO is exercised here. Never claim
                # these deliberately synthetic totals represent actual473.
                result = support.tree_inventory(*a)
                result.update(files=473, bytes=11747906)
                return result
        data = dict(buffers)
        if corruption:
            data[g.PATCH + 'DERIVED_V3ProtectLib.cpp'] += b'foreign edit'
            rejects(lambda: g.materialize_patched(SyntheticTotalsSupport(), source, base / 'derived',
                    table, inventory, data), 'unique exact forward')
            g.require(not (base / 'derived').exists(), 'bad patch refused before output')
        else:
            result, _ = g.materialize_patched(SyntheticTotalsSupport(), source, base / 'derived', table, inventory, data)
            out = base / 'derived/src/V3ProtectLib.cpp'
            g.require(out.read_bytes() == buffers[g.PATCH + 'DERIVED_V3ProtectLib.cpp'] and
                      (source / 'src/V3ProtectLib.cpp').read_bytes() == original and
                      out.stat().st_ino != (source / 'src/V3ProtectLib.cpp').stat().st_ino,
                      'fresh independent patched file and preserved official original')
test('real_single_file_exact_patch_io_only', patch_only_synthetic_file)
test('extra_patch_edit_refused_before_output', lambda: patch_only_synthetic_file(True))


def synthetic_hierarchy(fixtures):
    leaf = 'micro_leaf__S3'
    child = 'V' + leaf
    boundaries = ' '.join(leaf + '_protectlib_' + x + '();' for x in ('create', 'combo_update', 'seq_update', 'final'))
    return {
        'obj/' + child + '__hierMkArgs.f': '--lib-create ' + leaf + ' --hierarchical-child 1 --top-module-encoded ' + leaf + ' -GSTEP=3\n',
        'obj/Vmicro_top__hierMkArgs.f': child + '/' + leaf + '.sv ' + str(fixtures / 'tiny.sv') + '\n',
        'obj/Vmicro_top.mk': 'include Vmicro_top_hier.mk\n',
        'obj/Vmicro_top_hier.mk': 'VM_HIER_LIBS := ' + child + '/lib' + leaf + '.a\n' + child + '.mk\n',
        'obj/' + child + '/' + leaf + '.sv': 'chandle handle__V; handle__V = ' + leaf + '_protectlib_create();\n' + boundaries,
        'obj/' + child + '/' + leaf + '.cpp': 'class ' + child + '_container: public ' + child + ' { public: long long m_seqnum; ' + child + '_container(const char* scopep__V): ' + child + '(scopep__V), m_seqnum{0} {} };\nnew ' + child + '_container; handlep__V->eval(); delete handlep__V;\n' + boundaries,
        'obj/Vmicro_top.cpp': boundaries + '\nhm_read_count(); hm_read_delta(); hm_set_delta(); Verilated::dpiScope(); exportFind(); exportInsert();\n',
        'obj/Vmicro_top__Dpi.h': 'hm_read_count(); hm_read_delta(); hm_set_delta();\n',
        'obj/' + child + '/' + child + '.cpp': 'SYNTHETIC child implementation; never compiled\n',
    }


def mock_write(path, raw=b'SYNTHETIC ONLY\n', executable=False):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o700 if executable else 0o600)


def run_synthetic(fail_at=None, corrupt_runtime=False, corrupt_initializer=False, stop_after_build=False):
    """Exercise complete run orchestration with explicit fake process outputs."""
    saved = {name: getattr(g, name) for name in ('host_identities', 'verify_official473',
                                               'materialize_patched', 'immutable_sources', 'verify_objcache_disabled')}
    calls = []
    g.host_identities = lambda support: {}
    g.verify_official473 = lambda *a: ({'members': []}, {'root': 'SYNTHETIC', 'files': 0, 'bytes': 0, 'entries': {}})
    def materialize(s, source, root, table, original, buf):
        support.fresh_directory(root)
        for name in ('bin', 'src', 'include'):
            support.fresh_directory(root / name)
        mock_write(root / 'bin/verilator', b'SYNTHETIC wrapper never run\n', True)
        mock_write(root / 'bin/verilator_includer', b'SYNTHETIC includer never run\n', True)
        mock_write(root / 'include/runtime.h', b'SYNTHETIC include\n')
        return {'synthetic_only': True}, {'entries': {}}
    g.materialize_patched = materialize
    g.immutable_sources = lambda *a: None
    g.verify_objcache_disabled = lambda *a: {'SYNTHETIC_ONLY': True}
    try:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / 'work'
            def callback(name, argv, cwd, env, bound):
                calls.append(name)
                if name == fail_at:
                    raise ValueError('synthetic requested stop')
                raw = b''
                if name == 'official_source473':
                    (work / 'acquired/verilator').mkdir(mode=0o700, parents=True)
                    (work / 'acquired').chmod(0o700)
                    g.save_private(work / 'acquired/SOURCE.json', {'commit': g.COMMIT,
                        'archive_complete': True, 'selected_bytes': 11747893,
                        'verified_members': list(range(473)), 'cleanup_errors': [], 'SYNTHETIC_ONLY': True})
                elif name.startswith('host_'):
                    probe = name[5:]
                    tool, kind = probe.rsplit('-', 1)
                    if kind == 'version':
                        raw = {'autoconf': b'autoconf (GNU Autoconf) 2.71\n',
                               'autom4te': b'autom4te (GNU Autoconf) 2.71\n',
                               'm4': b'm4 (GNU M4) 1.4.19\n', 'flex': b'flex 2.6.4\n',
                               'bison': b'bison (GNU Bison) 3.8.2\n'}[tool]
                    else:
                        definition = json.loads(buffers[g.MODES])['modes'][probe]
                        raw = definition['expected_log_exact'].encode()
                        for filename, generated in definition['generated_files'].items():
                            text = '\n'.join(generated['contains']).replace('Autoconf 2.72', 'Autoconf 2.71')
                            mock_write(cwd / filename, text.encode())
                elif name == 'fresh_autoconf':
                    mock_write(cwd / 'configure')
                elif name == 'fresh_configure':
                    for filename in ('Makefile', 'src/Makefile', 'src/Makefile_obj', 'src/config_package.h',
                                     'include/verilated.mk', 'include/verilated_config.h', 'config.status', 'config.log'):
                        mock_write(cwd / filename)
                elif name == 'fresh_make':
                    mock_write(cwd / 'bin/verilator_bin', b'SYNTHETIC backend never run\n', True)
                    mock_write(cwd / 'src/config_rev.h')
                elif name == 'derived_tiny_version':
                    raw = b'Verilator SYNTHETIC\n'
                    if corrupt_runtime:
                        mock_write(work / 'verilator/include/runtime.h', b'drift\n')
                elif name == 'derived_tiny_generate':
                    data = synthetic_hierarchy(cwd / 'fixtures')
                    if corrupt_initializer:
                        key = 'obj/Vmicro_leaf__S3/micro_leaf__S3.cpp'
                        data[key] = data[key].replace(', m_seqnum{0}', '')
                    for filename, text in data.items():
                        mock_write(cwd / filename, text.encode())
                elif name == 'derived_tiny_compile':
                    for filename in ('obj/Vmicro_leaf__S3/libmicro_leaf__S3.a', 'obj/Vmicro_top__ALL.a', 'obj/Vmicro_top'):
                        mock_write(cwd / filename)
                    raw = b'g++ -c micro_leaf__S3.cpp\ng++ main.o Vmicro_top__ALL.a -o Vmicro_top\n'
                elif name == 'derived_tiny_run':
                    raw = expected
                else:
                    raise ValueError('unexpected synthetic phase ' + name)
                return {'record': {'exit_code': 0, 'cleanup_confirmed': True}, 'raw_log': raw,
                        'usage': {'SYNTHETIC_NOT_MEASURED': True}, 'evidence_root': str(work / 'not_created')}
            if fail_at is not None:
                rejects(lambda: g.run(args.repo, work, callback), 'synthetic requested stop')
                g.require(calls[-1] == fail_at and calls.count(fail_at) == 1, 'no retry/fallback after failure')
            elif stop_after_build:
                result = g.run(args.repo, work, callback, stop_after_build=True)
                g.require(result['status']=='PASS_FRESH_DERIVED_BACKEND_BUILD_ONLY' and result['tiny'] is None, 'build-only scope')
                g.require(len(calls)==14 and calls[-1]=='fresh_make' and result['backend']['bytes']>0, 'exact14 and backend postflight')
                g.require(not (work/'micro').exists(), 'no new backend or tiny execution')
            elif corrupt_runtime:
                rejects(lambda: g.run(args.repo, work, callback), 'include closure drift')
                g.require(calls[-1] == 'derived_tiny_version', 'runtime drift before further native phase')
            elif corrupt_initializer:
                rejects(lambda: g.run(args.repo, work, callback), 'exact m_seqnum{0}')
                g.require(calls[-1] == 'derived_tiny_generate', 'no compile after initializer failure')
            else:
                result = g.run(args.repo, work, callback)
                g.require(result['status'] == 'PASS_FRESH_DERIVED_TOOLCHAIN_AND_TINY_ONLY' and
                          result['qualification']['version_count'] == result['qualification']['tiny_count'] == 5,
                          'synthetic full orchestration result')
                g.require(len(calls) == 18 and calls[0] == 'official_source473' and
                          calls[11:14] == ['fresh_autoconf', 'fresh_configure', 'fresh_make'] and
                          calls[14:] == ['derived_tiny_version', 'derived_tiny_generate', 'derived_tiny_compile', 'derived_tiny_run'],
                          'exact 18 non-native callback order')
                g.require(result['tiny']['witness']['derived_initializer_contract']['initializer_value'] == 0,
                          'synthetic initialized target witness')
                g.require('original_uninitialized_failure_preserved' not in result['tiny']['witness'],
                          'no historical runtime evidence inherited')
                g.require(all((p.stat().st_mode & 0o077) == 0 for p in work.glob('*.json')), 'private receipts')
    finally:
        for name, value in saved.items():
            setattr(g, name, value)


test('full_eighteen_phase_synthetic_orchestration', run_synthetic)
test('build_only_fourteen_phase_synthetic_orchestration', lambda: run_synthetic(stop_after_build=True))
for phase in ('official_source473', 'host_autoconf-version', 'host_bison-micro',
              'fresh_autoconf', 'fresh_configure', 'fresh_make', 'derived_tiny_compile'):
    test('stop_without_retry_' + phase, lambda phase=phase: run_synthetic(fail_at=phase))
test('configured_runtime_drift_refused', lambda: run_synthetic(corrupt_runtime=True))
test('uninitialized_generated_target_refused', lambda: run_synthetic(corrupt_initializer=True))


def missing_tool_before_work():
    saved = g.host_identities
    def missing(s):
        raise ValueError('required CI tool missing')
    g.host_identities = missing
    try:
        with tempfile.TemporaryDirectory() as t:
            work = Path(t) / 'not_created'
            calls = []
            rejects(lambda: g.run(args.repo, work, lambda *a: calls.append(a)), 'required CI tool missing')
            g.require(not work.exists() and not calls, 'missing tools before output or acquisition')
    finally:
        g.host_identities = saved
test('missing_tool_before_output_or_network', missing_tool_before_work)

test('no_native_process_api_in_component', lambda: g.require(
    not any(isinstance(n, (ast.Import, ast.ImportFrom)) and any(x.name in ('subprocess', 'socket', 'urllib')
            for x in n.names) for n in ast.walk(ast.parse(RAW))), 'component must delegate all processes'))
print(json.dumps({'status': 'PASS_COLD_SOURCE_AND_SYNTHETIC_ONLY', 'tests': len(tests),
                  'checks': tests, 'network_executed': False, 'native_tools_executed': False,
                  'real_source_acquired': False, 'real_toolchain_built': False}, sort_keys=True))
