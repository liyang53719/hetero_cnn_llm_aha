"""Narrow resume tests: Python/data only; never run shell, tools, or network."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B')
import argparse, ast, copy, hashlib, json, os, resource, signal, stat, tempfile, types
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).absolute().parent
CHECKS = []
LOCAL_PINS = {
    'resume_toolchain.py': {'bytes': 8626, 'sha256': 'e0e0c10015ed96f36bbf63c1bff7454c59a63468aa243b84a0024bedd03a0d7a'},
    'continuation_entry.py': {'bytes': 17732, 'sha256': 'b0f344600b9ab86d5fa53ac4b3fec1e33db416438f49014786a53a490deeca14'},
    'source_entry.py': {'bytes': 8588, 'sha256': '512bac7105e1977100107d252e74dd11546ccc9a59d699958d18a2b84cd82f65'},
}

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def rejects(function, label):
    try:
        function()
    except (ValueError, KeyError, TypeError, OSError):
        CHECKS.append(label)
        return
    raise ValueError('missing rejection: ' + label)

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in (
            'urllib.Request', 'os.system', 'os.fork', 'os.forkpty', 'os.exec',
            'os.posix_spawn', 'pty.spawn'):
        raise RuntimeError('cold resume tests forbid native and network execution')

sys.addaudithook(audit)
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (50, 50))
signal.alarm(90)

parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('--repo', type=Path, required=True)
parser.add_argument('--caller-source', type=Path)
args = parser.parse_args()
REPO = args.repo
need(REPO.is_absolute() and '..' not in REPO.parts, 'absolute repository')

def load(path, expected=None):
    path = Path(path)
    raw = path.read_bytes()
    if expected is not None:
        need(pin(raw) == expected, 'fixed source pin: ' + path.name)
    module = types.ModuleType('_resume_cold_' + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module, raw

ADAPTER_PATH = (args.caller_source / 'local_toolchain_adapter.py' if args.caller_source
                else REPO / 'candidates/host93_first_n0_sources/local_toolchain_caller/local_toolchain_adapter.py')
adapter, _ = load(ADAPTER_PATH, {'bytes': 8776,
    'sha256': '5b21cf3d8969873b3d751f52d64dc7e9528edc0a7d68ce3b91d88f65c8ca3896'})
ci, CI_RAW = load(REPO / adapter.CI, adapter.CI_PIN)
source_pins = json.loads(ci.initial_read(REPO / 'candidates/host93_ci_recovery/toolchain/SOURCE_PINS.json',
                                        ci.PINS_BYTES, ci.PINS_SHA))
support, _ = load(REPO / ci.SUPPORT, source_pins[ci.SUPPORT])
resume, RESUME_RAW = load(ROOT / 'resume_toolchain.py', LOCAL_PINS['resume_toolchain.py'])

def checked(path, expected, cap=4 * 1024**2):
    need(type(expected) is dict and expected['bytes'] <= cap, 'finite checked buffer')
    return ci.initial_read(Path(path), expected['bytes'], expected['sha256'])

g = types.SimpleNamespace(need=need, pin=pin, checked=checked,
                          clean=support.safe_path, decode=json.loads, MIB=1024**2)

def make_ci():
    component = types.ModuleType('_resume_cold_ci')
    component.__file__ = str(REPO / adapter.CI)
    exec(compile(CI_RAW, component.__file__, 'exec', dont_inherit=True), component.__dict__)
    return component

# Exact official autoconf 2.72 rendering, copied as inert test data.
BLOCK_272 = (
    'if test ${ac_cv_prog_OBJCACHE+y}\nthen :\n'
    '  printf %s "(cached) " >&6\nelse case e in #(\n'
    '  e) if test -n "$OBJCACHE"; then\n'
    '  ac_cv_prog_OBJCACHE="$OBJCACHE" # Let the user override the test.\nelse\n'
    'as_save_IFS=$IFS; IFS=$PATH_SEPARATOR\nfor as_dir in $PATH\ndo\n'
    '  IFS=$as_save_IFS\n  case $as_dir in #(((\n'
    "    '') as_dir=./ ;;\n    */) ;;\n    *) as_dir=$as_dir/ ;;\n  esac\n"
    "    for ac_exec_ext in '' $ac_executable_extensions; do\n"
    '  if as_fn_executable_p "$as_dir$ac_word$ac_exec_ext"; then\n'
    '    ac_cv_prog_OBJCACHE="ccache"\n'
    '    printf "%s\\n" "$as_me:${as_lineno-$LINENO}: found $as_dir$ac_word$ac_exec_ext" >&5\n'
    '    break 2\n  fi\ndone\n  done\nIFS=$as_save_IFS\n\n'
    'fi ;;\nesac\nfi\nOBJCACHE=$ac_cv_prog_OBJCACHE\n').encode()
GUARD = (b'if test "x$OBJCACHE" != "x" ; then\n'
         b'  objcache_version=$($OBJCACHE --version | head -1)\nfi\n')
RAW_272 = b'# inert generated configure fixture\n' + BLOCK_272 + b'\n' + GUARD
need(pin(BLOCK_272) == {'bytes': 688,
    'sha256': 'f735474b483bdc4f30f18a57d97f3d0c527d692e6434f388dc2bf3befa777722'},
    'exact official 2.72 test block')

proof = resume.objcache_witness(ci.objcache_configure_witness, RAW_272)
need(proof['cache_variable'] == 'ac_cv_prog_OBJCACHE' and proof['cache_value'] == '' and
     proof['generated_branch_bytes'] == len(BLOCK_272) and
     proof['generated_branch_sha256'] == pin(BLOCK_272)['sha256'],
     'actual case-e block identity, set-empty semantics')
CHECKS.append('exact_272_case_e_set_empty_hit_and_actual_block_identity')
legacy = RAW_272.replace(b'else case e in #(\n  e) ', b'else $as_nop\n').replace(
    b'fi ;;\nesac\nfi\nOBJCACHE=', b'fi\nfi\nOBJCACHE=')
need(resume.objcache_witness(ci.objcache_configure_witness, legacy) ==
     ci.objcache_configure_witness(legacy), 'unchanged legacy witness')
CHECKS.append('legacy_rendering_retains_original_witness')
for label, old, new in (
        ('set_empty_hit_test_drift', b'${ac_cv_prog_OBJCACHE+y}', b'${ac_cv_prog_OBJCACHE:+y}'),
        ('cached_print_drift', b'printf %s "(cached) " >&6', b'printf %s "cached!" >&6'),
        ('cache_assignment_drift', b'OBJCACHE=$ac_cv_prog_OBJCACHE\n', b'OBJCACHE=ccache\n'),
        ('version_nonempty_guard_drift', b'if test "x$OBJCACHE" != "x" ; then', b'if true; then'),
        ('case_e_selector_drift', b'else case e in #(', b'else case x in #('),
        ('cache_miss_body_drift', b'ac_cv_prog_OBJCACHE="ccache"', b'ac_cv_prog_OBJCACHE="other"'),
        ('case_e_close_drift', b'fi ;;\nesac\nfi', b'fi\nesac\nfi')):
    need(RAW_272.count(old) == 1, 'single negative fixture mutation')
    rejects(lambda old=old, new=new: resume.objcache_witness(
        ci.objcache_configure_witness, RAW_272.replace(old, new)), label + '_rejected')
for label, raw in (
        ('duplicate_case_e_block', RAW_272 + BLOCK_272),
        ('outside_cache_variable_before', b'ac_cv_prog_OBJCACHE=ccache\n' + RAW_272),
        ('outside_cache_variable_after', RAW_272 + b'ac_cv_prog_OBJCACHE=ccache\n'),
        ('missing_nonempty_guard', RAW_272.replace(GUARD, b''))):
    rejects(lambda raw=raw: resume.objcache_witness(ci.objcache_configure_witness, raw),
            label + '_rejected')

# Further tests below exercise synthetic source data and callback-only run paths.
class ReachedOriginalMaterialization(Exception):
    pass

with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
    home = Path(temporary)
    cache = home / 'old-cache'
    support.fresh_directory(cache)
    support.fresh_directory(cache / 'verilator')
    payloads = {'group/member_%03d.cpp' % n:
                ('synthetic cached source %03d; never compiled\n' % n).encode() for n in range(473)}
    for name, raw in payloads.items():
        target = cache / 'verilator' / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        ci.write_fixture(target, raw)
    receipt_document = {'commit': ci.COMMIT, 'archive_complete': True,
                        'selected_bytes': 11747893, 'verified_members': list(payloads),
                        'cleanup_errors': []}
    receipt_raw = json.dumps(receipt_document, sort_keys=True).encode()
    ci.write_fixture(cache / 'SOURCE.json', receipt_raw)
    ci.write_fixture(cache / 'old_archive.tar.gz', b'inert old archive; never copied')
    table = {'members': [{'path': name} for name in payloads]}
    verify_calls, receipt_reads = [], []
    expected_receipt = [receipt_raw]

    def mock_checked(path, expected, cap=4 * 1024**2):
        path = Path(path)
        if path.name == 'SOURCE.json':
            need(expected == resume.RECEIPT_PIN and cap == 1024**2, 'fixed receipt identity requested')
            receipt_reads.append(path)
            return support.checked_read(path, len(expected_receipt[0]), pin(expected_receipt[0])['sha256'])
        return checked(path, expected, cap)

    test_g = types.SimpleNamespace(**dict(g.__dict__, checked=mock_checked))

    def verify_synthetic(fs, source, buffers):
        need(fs is support and buffers == {'synthetic': '473 tiny buffers'},
             'exact synthetic source context')
        source = Path(source)
        verify_calls.append(source)
        inventory = fs.tree_inventory(source, 1024**2, 473, 1024, 1024**2)
        regular = {n: row for n, row in inventory['entries'].items() if row['kind'] == 'regular'}
        need(set(regular) == set(payloads) and inventory['files'] == 473 and
             inventory['bytes'] == sum(map(len, payloads.values())), 'exact synthetic473 inventory')
        for name, raw in payloads.items():
            need(fs.identity(source / name, len(raw)) == dict(pin(raw), mode='0o600'),
                 'synthetic member hash/mode unchanged')
        return table, inventory

    def component_fixture():
        component = make_ci()
        component.load_sources = lambda repo: (support, {}, {'synthetic': '473 tiny buffers'})
        component.verify_official473 = verify_synthetic
        component.host_identities = lambda fs: {}
        component.acquisition_argv = mock.Mock(side_effect=AssertionError('download acquisition forbidden'))
        return component

    component = component_fixture()
    copied = home / 'copied'
    observation = resume.stage_cache(test_g, component, REPO, cache, copied)
    need(verify_calls == [cache / 'verilator', copied / 'verilator', cache / 'verilator'],
         'original before, copied postflight, original after')
    need(receipt_reads == [cache / 'SOURCE.json', copied / 'SOURCE.json', cache / 'SOURCE.json'],
         'fixed receipt checked before and both after')
    need({path.name for path in copied.iterdir()} == {'verilator', 'SOURCE.json'} and
         not (copied / 'old_archive.tar.gz').exists() and
         observation['kind'] == 'PARENT_DATA_ONLY' and observation['files'] == 473 and
         observation['native_started'] is observation['network_started'] is
         observation['archive_copied'] is observation['prior_phase_cleanup_inherited'] is False,
         'truthful data-only copy of source and receipt without archive or qualification')
    CHECKS.append('synthetic473_data_copy_three_verifications_truthful_receipt_no_archive')

    first_name = next(iter(payloads))
    first_path = cache / 'verilator' / first_name
    first_raw = payloads[first_name]
    for label in ('missing_member', 'changed_member', 'extra_member', 'symlink_member',
                  'receipt_content_drift', 'failed_receipt_marker'):
        destination = home / ('reject-' + label)
        if label == 'missing_member':
            first_path.unlink()
        elif label == 'changed_member':
            first_path.write_bytes(b'X' + first_raw[1:])
        elif label == 'extra_member':
            ci.write_fixture(cache / 'verilator/extra.cpp', b'extra')
        elif label == 'symlink_member':
            first_path.unlink()
            first_path.symlink_to(cache / 'verilator' / list(payloads)[1])
        elif label == 'receipt_content_drift':
            (cache / 'SOURCE.json').write_bytes(b'{}')
        else:
            ci.write_fixture(cache / 'FAILED.json', b'{}')
        rejects(lambda: resume.stage_cache(test_g, component, REPO, cache, destination),
                'cached473_' + label + '_rejected')
        need(not destination.exists(), 'bad source fails before output: ' + label)
        if label in ('missing_member', 'changed_member', 'symlink_member'):
            if os.path.lexists(first_path):
                first_path.unlink()
            ci.write_fixture(first_path, first_raw)
        elif label == 'extra_member':
            (cache / 'verilator/extra.cpp').unlink()
        elif label == 'receipt_content_drift':
            (cache / 'SOURCE.json').write_bytes(receipt_raw)
        else:
            (cache / 'FAILED.json').unlink()

    for key, bad in (('commit', 'wrong'), ('archive_complete', False),
                     ('selected_bytes', 0), ('verified_members', []), ('cleanup_errors', ['bad'])):
        mutated = dict(receipt_document, **{key: bad})
        expected_receipt[0] = json.dumps(mutated, sort_keys=True).encode()
        (cache / 'SOURCE.json').write_bytes(expected_receipt[0])
        rejects(lambda: resume.stage_cache(test_g, component, REPO, cache, home / ('bad-' + key)),
                'cached473_receipt_' + key + '_rejected')
    expected_receipt[0] = receipt_raw
    (cache / 'SOURCE.json').write_bytes(receipt_raw)

    for label, destination in (('existing_destination', copied), ('same_cache_destination', cache),
                               ('destination_below_cache', cache / 'nested'),
                               ('destination_above_cache', home), ('relative_destination', Path('relative'))):
        rejects(lambda destination=destination: resume.stage_cache(
            test_g, component, REPO, cache, destination), label + '_rejected')
    link = home / 'linked-destination'
    link.symlink_to(copied, target_is_directory=True)
    rejects(lambda: resume.stage_cache(test_g, component, REPO, cache, link),
            'symlink_destination_rejected')

    original_copy = support.copy_member
    for label in ('source_changes_during_copy', 'destination_changes_after_copy', 'receipt_changes_during_copy'):
        destination = home / label
        altered = []
        def interfering_copy(source, target, relative, member_pin, mode):
            original_copy(source, target, relative, member_pin, mode)
            if not altered:
                altered.append(relative)
                if label == 'source_changes_during_copy':
                    Path(source).write_bytes(b'X' + payloads[relative][1:])
                elif label == 'destination_changes_after_copy':
                    (Path(target) / relative).write_bytes(b'X' + payloads[relative][1:])
                else:
                    (cache / 'SOURCE.json').write_bytes(b'{}')
        with mock.patch.object(support, 'copy_member', side_effect=interfering_copy):
            rejects(lambda: resume.stage_cache(test_g, component, REPO, cache, destination),
                    label + '_rejected_by_postflight')
        need(altered == [first_name], 'single deliberate copy-time mutation')
        first_path.write_bytes(first_raw)
        (cache / 'SOURCE.json').write_bytes(receipt_raw)
        if label == 'receipt_changes_during_copy':
            need((destination / 'SOURCE.json').read_bytes() == receipt_raw,
                 'receipt write consumed the already validated buffer')
    CHECKS.append('receipt_copy_consumes_original_checked_buffer_before_source_postflight')

    # Original copy_member consumes the one checked_read buffer even if the
    # source changes after that read. stage_cache's later source check then
    # rejects such drift; this isolated test establishes the buffer data flow.
    same_buffer_destination = home / 'same-buffer'
    support.fresh_directory(same_buffer_destination)
    original_read = support.checked_read
    observed_reads = []
    def mutate_after_checked_read(path, size, digest):
        raw = original_read(path, size, digest)
        observed_reads.append(Path(path))
        Path(path).write_bytes(b'X' + raw[1:])
        return raw
    with mock.patch.object(support, 'checked_read', side_effect=mutate_after_checked_read):
        original_copy(first_path, same_buffer_destination, first_name, pin(first_raw), 0o600)
    need(observed_reads == [first_path] and
         (same_buffer_destination / first_name).read_bytes() == first_raw and
         first_path.read_bytes() != first_raw,
         'one already verified buffer supplies the copy and readback')
    first_path.write_bytes(first_raw)
    CHECKS.append('original_copy_member_checked_buffer_consumed_once_and_readback_verified')

    # Exact original run postflight is reached without source download or any
    # native callback. Stop at materialization, before any native build phase.
    component = component_fixture()
    materialized = []
    def stop_at_materialization(fs, source, destination, actual_table, inventory, buffers):
        materialized.append((Path(source), Path(destination), actual_table, inventory['files']))
        raise ReachedOriginalMaterialization()
    component.materialize_patched = stop_at_materialization
    callback = mock.Mock(side_effect=AssertionError('native callback forbidden'))
    verify_calls.clear()
    binding_proof = resume.bind(test_g, adapter, component, REPO, copied)
    need(binding_proof['run']['inverse_exact'] is True and
         binding_proof['run']['substitutions'] == 5 and
         binding_proof['old_receipt_not_new_native_qualification'] is True,
         'finite inverse five-anchor run projection')
    try:
        component.run(REPO, home / 'fresh-build', callback)
    except ReachedOriginalMaterialization:
        pass
    else:
        raise ValueError('did not reach exact original materialization')
    need(verify_calls == [copied / 'verilator'] and len(materialized) == 1 and
         materialized[0][0] == copied / 'verilator' and materialized[0][3] == 473 and
         callback.call_count == component.acquisition_argv.call_count == 0 and
         not (home / 'fresh-build/acquired').exists(),
         'original receipt and473 postflight precede unchanged patch with no download')
    CHECKS.append('projected_run_reuses_original_receipt_473_postflight_and_patch_no_download')
    for label, repo, work in (('wrong_repo', home, home / 'new-wrong-repo'),
                             ('wrong_work_parent', REPO, home / 'nested/new'),
                             ('work_is_copy', REPO, copied)):
        rejects(lambda repo=repo, work=work: component.run(repo, work, callback),
                'projected_run_' + label + '_rejected')
    (copied / 'SOURCE.json').write_bytes(b'{}')
    rejects(lambda: component.run(REPO, home / 'bad-copy-receipt', callback),
            'projected_run_rechecks_cached_receipt_before_output')
    need(not (home / 'bad-copy-receipt').exists() and callback.call_count == 0,
         'receipt drift stops before fresh build or callback')

for error, expected in (
        (None, {'safe_contract_boundary': None, 'safe_contract_code': None}),
        (ValueError('private path /must/not/leak'), {'safe_contract_boundary': None, 'safe_contract_code': None}),
        (ci.ContractFailure('BUILD_AUTOCONF_OBJCACHE_AFTER', 'OBJCACHE_BRANCH'),
         {'safe_contract_boundary': 'BUILD_AUTOCONF_OBJCACHE_AFTER', 'safe_contract_code': 'OBJCACHE_BRANCH'})):
    need(resume.safe_contract(ci, error) == expected, 'finite safe-contract result')
CHECKS.append('safe_contract_returns_only_exact_allowlisted_original_error_fields')
for label in ('forged_exception', 'subclass_exception', 'mutated_boundary', 'mutated_code', 'nonstring_code'):
    if label == 'forged_exception':
        error = ValueError('secret')
        error.safe_contract_boundary = 'BUILD_AUTOCONF_OBJCACHE_AFTER'
        error.safe_contract_code = 'OBJCACHE_BRANCH'
    elif label == 'subclass_exception':
        class Subclass(ci.ContractFailure):
            pass
        error = Subclass('BUILD_AUTOCONF_OBJCACHE_AFTER', 'OBJCACHE_BRANCH')
    else:
        error = ci.ContractFailure('BUILD_AUTOCONF_OBJCACHE_AFTER', 'OBJCACHE_BRANCH')
        if label == 'mutated_boundary':
            error.safe_contract_boundary = '/private/path'
        else:
            error.safe_contract_code = '/private/path' if label == 'mutated_code' else 123
    need(resume.safe_contract(ci, error) == {'safe_contract_boundary': None, 'safe_contract_code': None},
         'untrusted diagnostic rejected: ' + label)
    CHECKS.append(label + '_not_exposed')

continuation, CONTINUATION_RAW = load(ROOT / 'continuation_entry.py', LOCAL_PINS['continuation_entry.py'])
expected_phases = ('local_flex_header_cached', 'flex_header_compile', 'fresh_autoconf',
    'fresh_configure', 'fresh_make', 'derived_tiny_version', 'derived_tiny_generate',
    'derived_tiny_compile', 'derived_tiny_run', 'idma319_extract', 'retained13_assemble',
    'host93_configuration', 'host93_cpp_generate', 'host93_cpp_compile',
    'host93_first_n0', 'host93_n0_compare')
need(continuation.PHASES == expected_phases and len(continuation.PHASES) == 16 and
     'official_source473' not in continuation.PHASES, 'exact remaining sixteen native stages')
CHECKS.append('sixteen_native_stages_retained_with_official_source_download_removed')

entry, ENTRY_RAW = load(ROOT / 'source_entry.py', LOCAL_PINS['source_entry.py'])
need(all(entry.LOCAL_PINS[name] == expected for name, expected in LOCAL_PINS.items()
         if name != 'source_entry.py'), 'entry pins exact new local modules')
CHECKS.append('fixed_source_entry_pins_resume_and_continuation_before_same_buffer_compile')
need(continuation.budget(100.0, 6700.0) == {
    'total_stop': 6700.0, 'work_stop': 6580.0, 'pre_stop': 2980.0,
    'numeric_seconds': 3600, 'tail_seconds': 120}, 'original single total clock and numeric/tail reserve')
rejects(lambda: continuation.budget(100.0, 6760.0), 'cache_copy_cannot_extend_original_6600_second_total')

timer_source = '''cache_stop=min(times['pre_stop'],time.monotonic()+60)
signal.setitimer(signal.ITIMER_REAL,max(0.001,cache_stop-time.monotonic()))
parent_stages.append(resume.stage_cache(g,component,repo,p['source_cache'],work/'cached-official473'))
need(time.monotonic()<cache_stop,'cached473 data stage sixty-second bound')
signal.setitimer(signal.ITIMER_REAL,max(0.001,times['pre_stop']-time.monotonic()))
tools=component.run(repo,work/'toolchain',callback)
'''
expected_ast = ast.parse(timer_source).body
parsed = ast.parse(CONTINUATION_RAW)
matches = []
for node in ast.walk(parsed):
    for field, value in ast.iter_fields(node):
        if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
            for offset in range(len(value) - len(expected_ast) + 1):
                sequence = value[offset:offset + len(expected_ast)]
                if [ast.dump(item) for item in sequence] == [ast.dump(item) for item in expected_ast]:
                    matches.append(sequence)
need(len(matches) == 1, 'single exact production cache timer/copy/check/reset/run sequence')
timer_code = compile(ast.fix_missing_locations(ast.Module(body=matches[0], type_ignores=[])),
                     'verified_production_cache_timer_sequence', 'exec', dont_inherit=True)
for label, pre_stop, clock_values, expected_timers in (
        ('sixty_seconds', 200, [100, 100, 105, 105], [60, 95]),
        ('pre_stop_caps_sixty', 130, [100, 100, 105, 105], [30, 25]),
        ('expired_copy', 200, [100, 100, 161], [60])):
    timer_calls = []
    clock_iter = iter(clock_values)
    mocked_component = types.SimpleNamespace(run=mock.Mock(return_value={'synthetic': 'tools'}))
    mocked_resume = types.SimpleNamespace(stage_cache=mock.Mock(return_value={'kind': 'PARENT_DATA_ONLY'}))
    environment = {'times': {'pre_stop': pre_stop},
        'time': types.SimpleNamespace(monotonic=lambda: next(clock_iter)),
        'signal': types.SimpleNamespace(ITIMER_REAL=42, setitimer=lambda kind, seconds: timer_calls.append((kind, seconds))),
        'parent_stages': [], 'resume': mocked_resume, 'g': g, 'component': mocked_component,
        'repo': REPO, 'p': {'source_cache': Path('/synthetic-cache')},
        'work': Path('/synthetic-fresh-work'), 'need': need, 'callback': object()}
    if label == 'expired_copy':
        rejects(lambda: exec(timer_code, environment), 'expired_cache_copy_blocks_all_native_phases')
        need(mocked_component.run.call_count == 0, 'expired copy must never enter native pipeline')
    else:
        exec(timer_code, environment)
        need(mocked_component.run.call_count == 1 and environment['tools'] == {'synthetic': 'tools'},
             'successful parent data copy enters one existing pipeline')
        CHECKS.append('cache_timer_' + label + '_then_restores_original_pre_stop')
    need(timer_calls == [(42, seconds) for seconds in expected_timers] and
         mocked_resume.stage_cache.call_count == 1 and
         environment['parent_stages'] == [{'kind': 'PARENT_DATA_ONLY'}],
         'exact bounded parent data stage and timer calls')

safe_calls = [node for node in ast.walk(parsed) if isinstance(node, ast.Call) and
              isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and
              node.func.value.id == 'resume' and node.func.attr == 'safe_contract']
need(len(safe_calls) == 1 and ast.dump(safe_calls[0]) ==
     ast.dump(ast.parse('resume.safe_contract(component,failure)', mode='eval').body),
     'coordinator safe fields use original component and first failure')
CHECKS.append('coordinator_reports_only_safe_contract_for_original_first_failure')

print(json.dumps({'status': 'PASS_NARROW_OBJCACHE_CACHED473_RESUME_COLD',
    'tests': len(CHECKS), 'checks': CHECKS, 'optimized': sys.flags.optimize,
    'native_started': False, 'network_started': False,
    'actual_cache_copied': False, 'actual_cache_readonly_check_rerun': False,
    'synthetic_cache_members': 473, 'historical_full_cold_suite_rerun': False}, sort_keys=True))
