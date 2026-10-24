"""Stdlib-only, fresh fullblock supervision gates. No historical actual authority."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import types

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent
OLD = CANDIDATE.parent / 'candidate_attention_owner_m2_sampler_20261020T0936'
OWNED = CANDIDATE / 'work/fixed93_fullblock'
OUTPUT = OWNED / 'run01'
SUPPORT = CANDIDATE / 'support'
CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'
RECEIPT_BYTES = 32768
LOG_FILE_BYTES = 32768
SAMPLE_LINE_BYTES = 2048
CLEANUP_SECONDS = 5
POST_SECONDS = 10
PUBLIC_TOTAL_CEILING_SECONDS = 45
POLL_SECONDS = 1


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha_string(value):
    return (type(value) is str and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value))


def canonical(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)),
         'canonical nonaliased path required')
    return path


def read_checked(path, sha256=None, size=None, *, cap=None):
    path = canonical(path)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'regular unaliased file required')
        need(size is None or before.st_size == size, 'byte count drift: ' + str(path))
        need(cap is None or before.st_size <= cap, 'bounded file exceeded: ' + str(path))
        raw = stream.read() if cap is None else stream.read(cap + 1)
        need(cap is None or len(raw) <= cap, 'bounded file read exceeded: ' + str(path))
        after = os.fstat(stream.fileno())
    stamp = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    need(stamp(before) == stamp(after) == stamp(path.stat()), 'file changed during read')
    need(sha256 is None or digest(raw) == sha256, 'hash drift: ' + str(path))
    return raw


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError('nonfinite JSON')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def pinned(spec, *, cap=None):
    need(type(spec) is dict and set(spec) == {'path', 'bytes', 'sha256'}, 'exact external pin required')
    need(type(spec['bytes']) is int and spec['bytes'] >= 0 and sha_string(spec['sha256']), 'invalid external pin')
    return read_checked(Path(spec['path']), spec['sha256'], spec['bytes'], cap=cap)


def identity(path):
    raw = read_checked(path)
    return dict(bytes=len(raw), sha256=digest(raw))


def validate_budget(budget):
    """No default resource values. OPEN/null cannot become an actual allowance."""
    need(type(budget) is dict and budget.get('schema') == 'fixed93-startup-probe-resource-v1' and
         budget.get('status') == 'REVIEWED_FIXED93_STARTUP_PROBE_BUDGET',
         'OPEN/missing wholeblock budget is not actual authority')
    integer_fields = ('inner_wall_seconds', 'outer_wall_seconds', 'rss_bytes', 'output_bytes',
                      'file_bytes', 'log_bytes', 'supervisor_receipt_reserve_bytes',
                      'free_space_margin_bytes')
    for name in integer_fields:
        need(type(budget.get(name)) is int and budget[name] > 0, 'reviewed positive integer required: ' + name)
    inner, outer = budget['inner_wall_seconds'], budget['outer_wall_seconds']
    need(inner == 30 and outer == 45 and budget['rss_bytes'] == 2147483648 and
         budget['output_bytes'] == 16777216 and budget['file_bytes'] == 8388608 and
         budget['log_bytes'] == 65536 and budget.get('sample_rows') == 46 and
         budget.get('one_cpu') is True and budget.get('guaranteed_time_or_rss_fit') is False,
         'exact 45-second/one-CPU/2-GiB/small-output startup budget required')
    need(inner + CLEANUP_SECONDS + POST_SECONDS <= outer <= PUBLIC_TOTAL_CEILING_SECONDS,
         'reviewed work/cleanup/post exceeds unchanged public support limits')
    need(budget.get('automatic_retry') is False and budget.get('wholeblock_scope_required') is False and budget.get('startup_only_scope_required') is True and
         budget.get('progress_loop_interval') == 131072 and
         type(budget.get('poll_seconds')) is int and budget['poll_seconds'] == POLL_SECONDS,
         'reviewed fullblock scope/progress/public sampler coupling required')
    need(RECEIPT_BYTES <= budget['file_bytes'] <= budget['output_bytes'] and
         budget['log_bytes'] <= budget['output_bytes'] and
         6 * RECEIPT_BYTES <= budget['supervisor_receipt_reserve_bytes'] < budget['output_bytes'],
         'whole-owned/file/log/temporary receipt reservation inconsistent')
    sample_rows = math.floor(outer / POLL_SECONDS) + 1
    need(sample_rows * SAMPLE_LINE_BYTES <= budget['file_bytes'], 'leader samples exceed admitted file capacity')
    if 'sample_rows' in budget:
        need(type(budget['sample_rows']) is int and budget['sample_rows'] == sample_rows,
             'reviewed sample_rows must be floor(total/poll)+1')
    for name in ('wholeblock_trace_limits', 'attention_trace_limits'):
        need(type(budget.get(name)) is dict and bool(budget[name]), 'complete reviewed stream allocation missing: ' + name)
    need(budget['attention_trace_limits'].get('source_manifest_sha256') ==
         'DERIVE_FROM_REVIEWED_SOURCE_MANIFEST', 'noncircular reviewed Attention manifest derivation required')
    return dict(budget)


def read_budget(expected_sha):
    need(sha_string(expected_sha), 'explicit reviewed budget SHA required')
    value = strict_json(read_checked(CANDIDATE / 'BUDGET_PROPOSAL.json', expected_sha, cap=1 << 20))
    return validate_budget(value)


def fixed_limits(budget):
    budget = validate_budget(budget)
    return dict(total_seconds=budget['outer_wall_seconds'], work_seconds=budget['inner_wall_seconds'],
                cpu_seconds=budget['outer_wall_seconds'], as_bytes=budget['rss_bytes'],
                fsize_bytes=budget['file_bytes'], log_bytes=budget['log_bytes'],
                sample_rows=math.floor(budget['outer_wall_seconds'] / POLL_SECONDS) + 1)


def source_dependencies(manifest):
    """Verify original support files, adapter provenance, and complete new source pins."""
    files = manifest['preparation_files']
    required = {str(path.relative_to(CANDIDATE)) for path in HERE.iterdir()
                if path.is_file() and path.suffix in ('.py', '.json')}
    need(required <= files.keys(), 'supervision source/pins missing from NEW complete source manifest')
    for name in required:
        pin = files[name]
        read_checked(CANDIDATE / name, pin['sha256'], pin['bytes'])
    provenance = strict_json(read_checked(HERE / 'EXTERNAL_PINS.json'))
    pinned(provenance['old_supervisor_adapter'])
    pinned(provenance['old_supervisor_pins'])
    for name, pin in provenance['support_files'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts, 'relative support source required')
        read_checked(SUPPORT / name, pin['sha256'], pin['bytes'])
    return provenance


def fresh_owned():
    canonical(OWNED)
    need(not os.path.lexists(OWNED), 'whole-owned once namespace already exists; no automatic retry')


def projection_preflight(budget, provenance):
    """Assemble the real production projections without configuring the adapter.

    This is called only inside preflight's native/process/write-denying scope.
    OPEN budgets never load public support or derive historical default limits.
    """
    if budget.get('status') != 'REVIEWED_FIXED93_STARTUP_PROBE_BUDGET':
        return dict(status='BLOCKED_OPEN_OR_UNREVIEWED_BUDGET',
                    budget_status=budget.get('status'), limits=None,
                    projection_hashes=None, public_support_loaded=False,
                    production_projection_assembled=False, child_created=False,
                    runtime_output_created=False, dut_imported=False)
    limits = fixed_limits(budget)
    relative = 'candidates/host93_ci_recovery/ci_support_v3.py'
    pin = provenance['support_files'][relative]
    path = SUPPORT / relative
    raw = read_checked(path, pin['sha256'], pin['bytes'])
    # Separate ephemeral namespace: do not import/configure the canonical
    # supervisor_adapter, and do not spend its one-use actual configuration.
    ci = types.ModuleType('_source_only_fixed93_public_projection')
    ci.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), ci.__dict__)
    support, base, pins = ci.fixed_support(SUPPORT)
    need(pins == {name: provenance['support_files'][name] for name in pins},
         'actual public projection dependency pins differ')
    plan = dict(published_sources=base['published_sources'],
                phases={'micro': limits}, environment={})
    supervisor, observation = support.projected_sources(plan, 'micro')
    hashes = dict(supervisor=digest(supervisor), observation=digest(observation))
    unused = HERE / '__NO_PROJECTION_OUTPUT__'
    need(not os.path.lexists(unused), 'pure projection output marker already exists')
    runner = support.make_runner(plan, 'micro', unused)
    need(runner['projection_hashes'] == hashes and
         all(callable(runner[name]) for name in
             ('bounded', 'observe_exit', 'group_state', 'sample_leader', 'save')),
         'real production projection/runner interfaces differ')
    need(not os.path.lexists(unused), 'pure projection created an output')
    return dict(status='ASSEMBLED_REAL_PUBLIC_PROJECTION_NO_EXECUTION',
                budget_status=budget['status'], limits=limits,
                projection_hashes=hashes, public_support_loaded=True,
                production_projection_assembled=True, child_created=False,
                runtime_output_created=False, dut_imported=False)


def preflight(expected_sha, *, fresh=True):
    # Own an outer denial scope through both assembly checks AND real production
    # projection assembly. An imported stdlib subprocess module is not a Popen.
    state = {'active': True, 'attempts': []}
    def audit(event, args):
        if not state['active']:
            return
        denied = (event.startswith(('ctypes.', 'subprocess.', 'socket.', 'os.exec', 'os.spawn')) or
                  event in ('os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn',
                            'os.kill', 'os.killpg', 'os.mkdir', 'os.remove', 'os.rmdir',
                            'os.rename', 'os.link', 'os.symlink', 'os.truncate'))
        if event == 'import' and args[0].split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates'):
            denied = True
        if event == 'open':
            _, mode, flags = args
            denied = denied or (type(mode) is str and any(c in mode for c in 'wax+')) or (
                type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
        if denied:
            state['attempts'].append(event)
            raise RuntimeError('fullblock preflight native/process/write boundary denied: ' + event)
    sys.addaudithook(audit)
    try:
        # Actual assembly verifier, never a mocked gate or import-only substitute.
        sys.path.insert(0, str(CANDIDATE))
        from assembly_preflight import preflight as assembly_preflight
        report, manifest, runtime, budget = assembly_preflight(expected_sha)
        provenance = source_dependencies(manifest)
        if fresh:
            fresh_owned()
        projection = projection_preflight(budget, provenance)
        need(not any(n.split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates') for n in sys.modules),
             'DUT/native import before actual authorization')
        need(not state['attempts'], 'production source preflight attempted a denied boundary')
        report.update(supervision_source_ready=True, whole_owned_root=str(OWNED),
                      resource_gate_closed=False, production_supervision_preflight=projection,
                      budget_values_validated=projection['production_projection_assembled'],
                      denied_boundary_attempts=list(state['attempts']),
                      actual_authorized=False, child_created=False, M128_executed=False,
                      complete_actual_admission=False)
        return report, manifest, runtime, budget
    finally:
        state['active'] = False


def actual_gate(manifest_sha, admission_sha, budget_sha, *, fresh=True):
    """Mirror child prerequisites before mkdir/spawn; does not consume child authority."""
    report, manifest, runtime, budget = preflight(manifest_sha, fresh=fresh)
    need(budget == read_budget(budget_sha), 'reviewed source budget differs')
    need(sha_string(admission_sha), 'explicit NEW root admission SHA required')
    declaration = strict_json(read_checked(CANDIDATE / 'ADMISSION.json', admission_sha, cap=2 << 20))
    fixed = dict(schema='fixed93-startup-probe-admission-v1',
                 startup_only=True, fullblock_authorized=False, M128_authorized=False,
                 entrypoint='integration/startup_probe.py', stop_before='first_x.advance_to_request',
                 status='REVIEWED_FIXED93_STARTUP_PROBE_ACTUAL', authorized_by='/root',
                 maximum_invocations=1, automatic_retry=False, actual_execution_authorized=True,
                 source_only=False, evidence_contract=CONTRACT, budget_reviewed=True)
    need(all(type(declaration.get(k)) is type(v) and declaration[k] == v for k, v in fixed.items()),
         'explicit NEW one-use root fullblock authority required')
    need(declaration.get('source_manifest_sha256') == manifest_sha and
         declaration.get('budget_sha256') == budget_sha,
         'root authority must explicitly bind NEW source and budget hashes')
    files = declaration.get('files')
    need(type(files) is dict and {'SOURCE_MANIFEST.json', 'BUDGET_PROPOSAL.json'} <= files.keys(),
         'NEW authority file bindings missing')
    required = set(manifest['preparation_files']) | {'SOURCE_MANIFEST.json'}
    need(required <= files.keys(), 'root authority omits complete prepared source closure')
    for name, pin in files.items():
        need(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts and
             type(pin) is dict and set(pin) == {'bytes', 'sha256'}, 'exact relative authority pin required')
        read_checked(CANDIDATE / name, pin['sha256'], pin['bytes'])
    reviewer = declaration.get('reviewer')
    need(type(reviewer) is str and reviewer.startswith('/root/') and
         'audit_attention_schedule_correspondence' not in reviewer, 'independent reviewer required')
    review = strict_json(pinned(declaration['source_cold_review'], cap=2 << 20))
    need(review.get('status') == 'GO_FIXED93_STARTUP_PROBE_SOURCE_COLD' and
         review.get('source_manifest_sha256') == manifest_sha and review.get('reviewer') == reviewer and
         review.get('actual_authorized') is False and review.get('native_executed') is False and
         review.get('budget_sha256') == budget_sha,
         'same-source, same-budget independent source/cold GO required')
    cold = strict_json(pinned(review['supervision_cold_result'], cap=2 << 20))
    need(cold.get('status') == 'PASS_SOURCE_PROJECTION_AND_MOCK_ONLY' and
         cold.get('source_manifest_sha256') == manifest_sha and cold.get('budget_sha256') == budget_sha and
         cold.get('actual_executed') is False and cold.get('real_child_created') is False and
         cold.get('numpy_imported') is False and cold.get('ctypes_imported') is False and
         cold.get('native_authorized') is False and cold.get('projection_delta_verified') is True and
         cold.get('denied_boundary_attempts') == [] and cold.get('limits') == fixed_limits(budget),
         'reviewed no-native supervisor cold result is missing or not same-budget')
    projections = cold.get('projection_hashes')
    provenance = strict_json(read_checked(HERE / 'EXTERNAL_PINS.json'))
    need(type(projections) is dict and set(projections) == {'supervisor', 'observation'} and
         all(sha_string(value) for value in projections.values()) and
         cold.get('old_projection_hashes') == provenance['original_projection_hashes'],
         'exact reviewed old/new supervisor projection identities required')
    need(report['production_supervision_preflight']['projection_hashes'] == projections and
         report['production_supervision_preflight']['limits'] == fixed_limits(budget),
         'real production preflight differs from independently reviewed same-budget cold projection')
    report['supervision_projection_hashes'] = projections
    scalar = strict_json(pinned(declaration['scalar_actual_prerequisite'], cap=2 << 20))
    need(declaration['scalar_actual_prerequisite'] == provenance['scalar_actual_prerequisite'] and
         scalar.get('status') == 'PASS_LIMITED_ACTUAL_ORIGINAL_SCALAR_SERVICE' and
         scalar.get('scope') == 'FIXED_19_GROUP_115_ENTRY_SOFTWARE_SCALAR_SERVICE_ONLY' and
         scalar.get('independent_fraction_recalculation') is True and
         scalar.get('all_fixed_graph_inputs_and_raw_returns') is True and
         scalar.get('case_groups') == 19 and scalar.get('primitive_entries') == 115 and
         scalar.get('fullblock') is False and scalar.get('M128') is False and scalar.get('RTL') is False and
         scalar.get('native_SiLU_inner_exp') is False and scalar.get('actual_host_or_hardware_flags') is False and
         scalar.get('all_inputs') is False and scalar.get('new_execution_authorized') is False,
         'independent actual scalar prerequisite required; not inherited M128 success')
    return declaration, manifest, runtime, budget, report


def parent_identity(pid):
    raw = read_checked(Path('/proc') / str(pid) / 'stat', cap=65536).decode('ascii')
    prefix, sep, rest = raw.rpartition(') ')
    fields = rest.split()
    need(sep and prefix.split(' ', 1)[0] == str(pid) and len(fields) >= 20, 'live parent identity')
    return dict(pid=pid, start_ticks=int(fields[19]))


def free_space(budget):
    """Reserve whole no-compression output plus reviewed free-space margin."""
    ancestor = OWNED.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    canonical(ancestor)
    value = os.statvfs(ancestor)
    available = value.f_bavail * value.f_frsize
    need(available >= budget['output_bytes'] + budget['free_space_margin_bytes'],
         'insufficient free space for whole admitted output and reviewed margin')
    return available
