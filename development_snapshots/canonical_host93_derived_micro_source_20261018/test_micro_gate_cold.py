"""Pure source/mock tests. No Verilator, compiler, make or child-process execution."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Cold tests require -I -S -B before loading local source.')
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import types

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', required=True, help='Explicit repository root containing the three pinned published support files; cold only.')
args = parser.parse_args()
REPO = Path(args.repo)
if not REPO.is_absolute() or '..' in REPO.parts:
    raise ValueError('--repo must be absolute without parent traversal')
HERE = Path(__file__).absolute().parent
RUNNER_SIZE = 27056
RUNNER_SHA = '2e2fd07edd71aef9d5abaa446f9d77c89a0c32060006dd699b4f0bc612e0c062'
count = 0


def require(ok, why):
    if not ok:
        raise ValueError(why)


def pinned(path, size, sha):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)), 'cold safe source path')
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        require(before.st_size == size, 'cold raw size before read')
        raw = f.read(size + 1)
        after = os.fstat(f.fileno())
    key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(key(before) == key(after) == key(path.stat()) and len(raw) == size and
            hashlib.sha256(raw).hexdigest() == sha, 'cold same-buffer raw identity')
    return raw


raw = pinned(HERE / 'run_micro_gate.py', RUNNER_SIZE, RUNNER_SHA)
g = types.ModuleType('verified_micro_gate_under_cold')
g.__file__ = str(HERE / 'run_micro_gate.py')
g.__verified_runner_pin__ = {'path': g.__file__, 'bytes': RUNNER_SIZE, 'sha256': RUNNER_SHA}
exec(compile(raw, g.__file__, 'exec', dont_inherit=True), g.__dict__)
production_plan = g.load_plan()
for phase in g.PHASES:
    g.validate_contract(production_plan, phase)
p = copy.deepcopy(production_plan)
# Cold-only resolution. No production source/build/evidence or actual binding is supplied.
g.SUPPORT_PIN = dict(g.SUPPORT_PIN, path=str(REPO / 'development_snapshots/canonical_host93_fixed_core_build_source_20261018/run_build_gate.py'))
g.initial_read(g.SUPPORT_PIN)
p['reused_support_candidate'] = g.SUPPORT_PIN
g.CONTRACT_PIN = dict(g.CONTRACT_PIN, path=str(HERE / 'init_contract.py'))
g.initial_read(g.CONTRACT_PIN)
p['initializer_contract'] = g.CONTRACT_PIN
for name in ('supervisor', 'observation'):
    item = p['published_sources'][name]
    relative = Path(item['repo_relative'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'fixed repository relative source')
    item['path'] = str(REPO / relative)
    g.initial_read(item)


def test(name, fn):
    global count
    fn()
    count += 1
    print('PASS ' + name)


def rejects(fn, part):
    try:
        fn()
    except (ValueError, KeyError, TypeError) as e:
        require(part in str(e), 'wrong refusal: ' + str(e))
        return
    raise ValueError('expected refusal: ' + part)


test('fixed_contract_all_four', lambda: [g.validate_contract(p, s) for s in g.PHASES])
test('all_actual_bindings_pending', lambda: require(p['actual_entry_enabled'] is False and
     all(v is None for v in p['required_actual'].values()) and all(v is None for v in p['previous_actual'].values()), 'actual not pending'))
for phase in g.PHASES:
    test('pending_refuses_' + phase, lambda phase=phase: rejects(lambda: g.pending_gate(p, phase), 'actual entry PENDING'))


def no_launch_pending():
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('forbidden')
        raise RuntimeError('native/source enumeration forbidden')
    old = g.support_module
    old_pop = g.subprocess.Popen
    try:
        g.support_module = forbidden
        g.subprocess.Popen = forbidden
        for s in g.PHASES:
            rejects(lambda: g.execute(p, s, 0), 'actual entry PENDING')
    finally:
        g.support_module = old
        g.subprocess.Popen = old_pop
    require(not calls, 'pending gate performed forbidden work')
test('pending_before_support_or_spawn', no_launch_pending)


def mutated(section, key, value, phase='version'):
    q = copy.deepcopy(p)
    q[section][key] = value
    return q
test('wrong_work_root', lambda: rejects(lambda: g.validate_contract(dict(p, work_root='/synthetic/escape'), 'version'), 'fixed roots'))
test('wrong_environment', lambda: rejects(lambda: g.validate_contract(mutated('environment', 'VERILATOR_BIN', 'verilator_bin_dbg'), 'version'), 'fixed environment'))
for key, val in [('argv', ['/usr/bin/verilator', '--version']), ('work_max_seconds', 11),
                 ('work_stop_absolute_offset_seconds', 21), ('fsize_bytes', 999), ('cleanup_seconds', 6)]:
    def change(key=key, val=val):
        q = copy.deepcopy(p)
        q['phases']['version'][key] = val
        rejects(lambda: g.validate_contract(q, 'version'), 'fixed phase')
    test('reject_contract_change_' + key, change)


def missing_each_binding():
    q = copy.deepcopy(p)
    q['actual_entry_enabled'] = True
    for key in g.REQUIRED:
        for k in g.REQUIRED:
            q['required_actual'][k] = {} if k != key else None
        rejects(lambda: g.pending_gate(q, 'version'), key + ' PENDING')
test('every_actual_binding_required', missing_each_binding)


def missing_previous():
    q = copy.deepcopy(p)
    q['actual_entry_enabled'] = True
    q['required_actual'] = {k: {} for k in g.REQUIRED}
    for phase in ('generate', 'compile', 'run'):
        rejects(lambda: g.pending_gate(q, phase), 'version previous accepted actual PENDING')
    q['previous_actual']['version'] = {}
    rejects(lambda: g.pending_gate(q, 'compile'), 'generate previous accepted actual PENDING')
    q['previous_actual']['generate'] = {}
    rejects(lambda: g.pending_gate(q, 'run'), 'compile previous accepted actual PENDING')
test('no_phase_skip', missing_previous)

support = g.support_module()
for phase in g.PHASES:
    def projection(phase=phase):
        sup, obs = support.projected_sources(p, phase)
        for name, b in (('supervisor', sup), ('observation', obs)):
            pin = p['projection_pins'][phase][name]
            require(len(b) == pin['bytes'] and hashlib.sha256(b).hexdigest() == pin['sha256'], 'fixed projection pin')
        n = g.projected_runner(support, p, phase, HERE / 'NOT_CREATED')
        require(set(('bounded', 'group_state', 'observe_exit', 'save', 'require', 'usage')).issubset(n), 'reused functions')
    test('same_buffer_projection_' + phase, projection)
test('bad_projection_refused', lambda: rejects(lambda: g.projected_runner(support,
     dict(p, projection_pins={s: {'supervisor': {'bytes': 0, 'sha256': '0'*64}, 'observation': p['projection_pins'][s]['observation']} for s in g.PHASES}),
     'version', HERE / 'NOT_CREATED'), 'projected raw identity'))

texts = {
 'obj/Vmicro_leaf__S3__hierMkArgs.f': "--lib-create micro_leaf__S3 --hierarchical-child 1 --top-module-encoded micro_leaf__S3 -GSTEP=32\\'h3\n",
 'obj/Vmicro_top__hierMkArgs.f': 'Vmicro_leaf__S3/micro_leaf__S3.sv ' + g.F + '/tiny.sv\n',
 'obj/Vmicro_top.mk': 'include Vmicro_top_hier.mk\n',
 'obj/Vmicro_top_hier.mk': 'VM_HIER_LIBS := Vmicro_leaf__S3/libmicro_leaf__S3.a\nVmicro_leaf__S3.mk\n',
 'obj/Vmicro_leaf__S3/micro_leaf__S3.sv': 'chandle handle__V;\nhandle__V = micro_leaf__S3_protectlib_create();\nmicro_leaf__S3_protectlib_combo_update();\nmicro_leaf__S3_protectlib_seq_update();\nmicro_leaf__S3_protectlib_final();\n',
 'obj/Vmicro_leaf__S3/micro_leaf__S3.cpp': 'class Vmicro_leaf__S3_container: public Vmicro_leaf__S3 { public: long long m_seqnum; Vmicro_leaf__S3_container(const char* scopep__V): Vmicro_leaf__S3(scopep__V), m_seqnum{0} {} };\nnew Vmicro_leaf__S3_container;\nhandlep__V->eval(); delete handlep__V;\nmicro_leaf__S3_protectlib_create(); micro_leaf__S3_protectlib_combo_update(); micro_leaf__S3_protectlib_seq_update(); micro_leaf__S3_protectlib_final();\n',
 'obj/Vmicro_top.cpp': 'micro_leaf__S3_protectlib_create(); micro_leaf__S3_protectlib_combo_update(); micro_leaf__S3_protectlib_seq_update(); micro_leaf__S3_protectlib_final();\nhm_read_count(); hm_read_delta(); hm_set_delta(); Verilated::dpiScope(); exportFind(); exportInsert();\n',
 'obj/Vmicro_top__Dpi.h': 'hm_read_count(); hm_read_delta(); hm_set_delta();\n',
 'obj/Vmicro_leaf__S3/Vmicro_leaf__S3.cpp': '/* synthetic independent child; not native proof */\n',
 'obj/Vmicro_leaf__S3/libmicro_leaf__S3.a': 'synthetic archive placeholder\n',
 'obj/Vmicro_top__ALL.a': 'synthetic combined archive placeholder\n',
 'obj/Vmicro_top': 'synthetic executable placeholder, never executed\n'}


class MockSupport:
    def __init__(self, data):
        self.data = data
    def checked_read(self, path, size, sha):
        raw = self.data[str(Path(path).relative_to('/synthetic'))].encode()
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha, 'mock same-buffer pin')
        return raw


def tree(data):
    return {'root': '/synthetic', 'entries': {n: {'kind': 'regular', 'bytes': len(s.encode()),
            'sha256': hashlib.sha256(s.encode()).hexdigest()} for n, s in data.items()}}


def witness(data=None, compiled=False):
    data = texts if data is None else data
    return g.hierarchy_witness(MockSupport(data), tree(data), compiled)
test('synthetic_hier_generated_shape', lambda: require(witness()['specialized_leaf'] == 'micro_leaf__S3', 'mock leaf'))
test('synthetic_hier_compiled_shape', lambda: require(witness(compiled=True)['compiled_artifacts_present'], 'mock archive shape'))
test('inline_only_rejected', lambda: rejects(lambda: witness({'obj/Vmicro_top.cpp': 'inlined numbers can pass'}), 'separately generated specialized leaf'))
test('missing_archive_rejected', lambda: rejects(lambda: witness({k:v for k,v in texts.items() if not k.endswith('libmicro_leaf__S3.a')}, True), 'child static archive missing'))
test('wrong_step_rejected', lambda: rejects(lambda: witness(dict(texts, **{'obj/Vmicro_leaf__S3__hierMkArgs.f': texts['obj/Vmicro_leaf__S3__hierMkArgs.f'].replace('h3', 'h1')})), 'STEP must be 3'))
test('missing_top_boundary_rejected', lambda: rejects(lambda: witness(dict(texts, **{'obj/Vmicro_top.cpp': 'hm_read_count(); hm_read_delta(); hm_set_delta();'})), 'top invokes real boundary'))
test('missing_top_scope_dispatch_rejected', lambda: rejects(lambda: witness(dict(texts, **{'obj/Vmicro_top.cpp': texts['obj/Vmicro_top.cpp'].replace('exportFind', 'not_dispatch')})), 'top DPI scope dispatch'))
test('missing_handle_allocation_rejected', lambda: rejects(lambda: witness(dict(texts, **{'obj/Vmicro_leaf__S3/micro_leaf__S3.cpp': texts['obj/Vmicro_leaf__S3/micro_leaf__S3.cpp'].replace('new Vmicro_leaf__S3_container', 'static int shared')})), 'generated handle allocation'))
test('version_log_shape', lambda: g.check_log(p, 'version', b'Verilator SYNTHETIC\n'))
test('version_extra_line_rejected', lambda: rejects(lambda: g.check_log(p, 'version', b'Verilator SYNTHETIC\nextra\n'), 'version output'))
test('generation_compiler_rejected', lambda: rejects(lambda: g.check_log(p, 'generate', b'g++ -O0 -c foo.cpp\n'), 'unexpectedly compiled'))
test('silent_archive_recipe_allowed', lambda: g.check_log(p, 'compile', b'g++ -c micro_leaf__S3.cpp\ng++ main.o Vmicro_top__ALL.a -o Vmicro_top\n', witness(compiled=True)))
test('missing_actual_link_rejected', lambda: rejects(lambda: g.check_log(p, 'compile', b'g++ -c micro_leaf__S3.cpp\n', witness(compiled=True)), 'actual top link'))
expected = ('\n'.join(p['expected_run_stdout']) + '\n').encode()
test('runtime_exact_log', lambda: g.check_log(p, 'run', expected))
test('runtime_wrong_B_count_rejected', lambda: rejects(lambda: g.check_log(p, 'run', expected.replace(b'count_b=455', b'count_b=456')), 'exact runtime'))
test('runtime_missing_final_rejected', lambda: rejects(lambda: g.check_log(p, 'run', expected.replace(b'HOST93_MICRO_PASS\n', b'')), 'exact runtime'))
test('no_bare_assert_statements', lambda: require(b'\nassert ' not in raw and b'\n    assert ' not in raw, 'bare assert'))
# Derived-specific source boundaries. No new source/build/binary identity is invented.
test('new_build_root_required', lambda: rejects(lambda: g.validate_contract(dict(p, build_root='/UNBOUND/host93_verilator_fixed_build_attempt_v1_20261018/verilator'), 'version'), 'fixed roots'))
test('initializer_contract_pin_required', lambda: rejects(lambda: g.validate_contract(dict(p, initializer_contract={}), 'version'), 'finite initialization contract'))
test('derived_build_and_patch_slots_pending', lambda: require(p['required_actual']['derived_backend_build_review'] is None and p['required_actual']['derived_patch_identity'] is None, 'derived actual prematurely bound'))
test('synthetic_scoped_initializer_witness', lambda: require(witness()['derived_initializer_contract']['initializer_value'] == 0, 'scoped constructor witness'))
test('uninitialized_target_rejected', lambda: rejects(lambda: witness(dict(texts, **{'obj/Vmicro_leaf__S3/micro_leaf__S3.cpp': texts['obj/Vmicro_leaf__S3/micro_leaf__S3.cpp'].replace(', m_seqnum{0}', '')})), 'exact m_seqnum{0}'))
test('elsewhere_initializer_cannot_compensate', lambda: rejects(lambda: witness(dict(texts, **{'obj/Vmicro_leaf__S3/micro_leaf__S3.cpp': texts['obj/Vmicro_leaf__S3/micro_leaf__S3.cpp'].replace(', m_seqnum{0}', '') + '\nstruct Other { long long m_seqnum{0}; };'})), 'exact m_seqnum{0}'))
def step_data(literal):
    return dict(texts, **{'obj/Vmicro_leaf__S3__hierMkArgs.f': "--lib-create micro_leaf__S3 --hierarchical-child 1 --top-module-encoded micro_leaf__S3 -GSTEP=" + literal.replace("'", "\\'") + "\n"})
for value in ("'sh3", "'SH03"):
    test('signed_unsized_hex_' + value, lambda value=value: witness(step_data(value)))
for value in ("'sh4", "'sh0", "'h3", "'sd3", "'shx", "'shz", "'sh+3", "'sh-3", "'sh_3", "'sh3_", "'sh3junk", "'sh"):
    test('reject_unsupported_step_' + value, lambda value=value: rejects(lambda: witness(step_data(value)), 'STEP must be 3'))
class PatchSupport:
    def __init__(self): self.seen = []
    def fixed(self, pin): self.seen.append(pin); return b'synthetic source bytes, not actual acceptance'
patch = {'original_source': {'path': str(g.ROOT / 'host93_verilator_fixed_build_attempt_v1_20261018/verilator/src/V3ProtectLib.cpp'), 'bytes': 22417, 'sha256': 'bddc3100c2ce83d7a4fe4656b0ff33cca1be70ea9a8295037c6aea72bc0ec6c1'},
         'derived_source': {'path': g.B + '/src/V3ProtectLib.cpp', 'bytes': 22430, 'sha256': '380f292c6e82ce30cd7c0b3375ac3f2b91e5c1e872a2c733ca6d0490122cf6fb'},
         'patch_record': {'path': '/synthetic/PATCH.json', 'bytes': 1, 'sha256': '0'*64}}
test('synthetic_patch_exact_shape', lambda: g.verify_patch_identity(PatchSupport(), {'derived_patch_identity': patch}, patch))
test('patch_not_bound_by_build_refused', lambda: rejects(lambda: g.verify_patch_identity(PatchSupport(), {}, patch), 'build binds exact derived patch'))
def wrong_derived_sha():
    q = copy.deepcopy(patch); q['derived_source']['sha256'] = '0'*64
    rejects(lambda: g.verify_patch_identity(PatchSupport(), {'derived_patch_identity': q}, q), 'single-initializer derived source identities')
test('wrong_derived_source_sha_refused', wrong_derived_sha)
test('unknown_patch_identity_key_refused', lambda: rejects(lambda: g.verify_patch_identity(PatchSupport(), {}, dict(patch, extra={})), 'patch identity shape'))
print(json.dumps({'status': 'PASS_SOURCE_AND_SYNTHETIC_ONLY', 'tests': count,
      'native_executed': False, 'generated_verilator_output_verified': False, 'all_new_actual_bindings': 'PENDING'}, sort_keys=True))
