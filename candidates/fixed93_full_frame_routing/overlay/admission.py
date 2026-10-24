"""New fullblock one-use authority boundary. No default or historical admission.

Pure import is stdlib-only. Source preparation with OPEN budget cannot reach any
runtime import. The future supervisor must create a fresh, explicitly reviewed
root authority and parent process lease. This module does not launch a process.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_STATE = None
_USED = False
_REQUESTS = set()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def _identity(path):
    from assembly_preflight import checked, digest
    raw = checked(Path(path))
    return dict(bytes=len(raw), sha256=digest(raw))


def _record(spec):
    from assembly_preflight import checked
    need(type(spec) is dict and set(spec) == {'path', 'bytes', 'sha256'}, 'exact external review pin required')
    return json.loads(checked(Path(spec['path']), spec))


def _process_identity(pid):
    text = Path('/proc/' + str(pid) + '/stat').read_text()
    prefix, sep, rest = text.rpartition(') ')
    words = rest.split()
    need(sep and prefix.split(' ', 1)[0] == str(pid) and len(words) >= 20, 'live parent identity unavailable')
    return dict(pid=pid, start_ticks=int(words[19]))


def require_actual_runtime(purpose):
    need(_STATE is not None and _STATE['pid'] == os.getpid() and _USED, 'NEW fullblock actual authority not installed')
    need(purpose in ('existing_profile2_elf_load', 'wholeblock_observation_factory') and
         purpose not in _REQUESTS, 'unadmitted/repeated actual runtime purpose')
    need(_process_identity(os.getppid()) == _STATE['parent'], 'supervisor identity changed')
    _REQUESTS.add(purpose)
    return _STATE


def _load_genuine_git(runtime):
    """Execute only verified source bytes; never a SourceFileLoader/pyc path."""
    import types
    from assembly_preflight import checked
    key = '_fullblock_genuine_git'
    need(key not in sys.modules, 'unexpected previously loaded Git profile')
    path = Path(runtime['git_profile_root']) / 'git_profile.py'
    raw = checked(path, runtime['files'][str(path)])
    code = compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
    module = types.ModuleType(key)
    module.__file__, module.__package__ = str(path), ''
    sys.modules[key] = module
    try:
        exec(code, module.__dict__)
        need(sys.modules.get(key) is module and module.__name__ == key and
             module.__file__ == str(path) and type(module.verify) is types.FunctionType and
             module.verify.__globals__ is vars(module), 'canonical checked Git profile required')
        module.verify()
    except BaseException:
        if sys.modules.get(key) is module:
            del sys.modules[key]
        raise
    return module


def _load_fullblock_runtime(manifest):
    """Bind the new observer loader/factory to source, never an unpinned pyc."""
    import types
    from assembly_preflight import checked
    name = 'fullblock_runtime'
    need(name not in sys.modules, 'unexpected preloaded fullblock factory')
    path = HERE / 'fullblock_runtime.py'
    raw = checked(path, manifest['preparation_files']['fullblock_runtime.py'])
    module = types.ModuleType(name)
    module.__file__, module.__package__ = str(path), ''
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), 'exec', dont_inherit=True, optimize=0), vars(module))
        need(sys.modules.get(name) is module and module.__file__ == str(path) and
             module.__name__ == name, 'canonical source factory required')
    except BaseException:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        raise
    return module


def admit(request):
    global _STATE, _USED
    need(not _USED and _STATE is None and __name__ == 'admission' and sys.modules.get('admission') is sys.modules[__name__],
         'one canonical new admission instance required')
    need(type(request) is dict and Path(request['candidate']).resolve() == HERE, 'new candidate request required')
    from assembly_preflight import preflight, checked, CONTRACT, digest, frozen_layout
    manifest_sha = request['reviewed_source_manifest']
    cold, manifest, runtime, budget = preflight(manifest_sha)
    layout = frozen_layout(manifest)
    declaration = request['declaration']
    need(type(declaration) is dict and declaration.get('authorized_by') == '/root' and
         declaration.get('maximum_invocations') == 1 and declaration.get('automatic_retry') is False and
         declaration.get('schema') == 'fixed93-fullblock-admission-v1' and
         declaration.get('status') == 'REVIEWED_FIXED93_M128_PUBLIC21_ACTUAL' and
         declaration.get('actual_execution_authorized') is True and declaration.get('source_only') is False and
         declaration.get('evidence_contract') == CONTRACT,
         'explicit new root wholeblock authority required')
    approval_path = HERE / 'ADMISSION.json'
    approval_raw = checked(approval_path)
    approval_sha = digest(approval_raw)
    need(json.loads(approval_raw) == declaration and os.environ.get('QWEN2_FIXED93_ADMISSION_SHA256') == approval_sha,
         'externally bound root authority differs')
    need(declaration.get('budget_reviewed') is True and budget.get('status') == 'REVIEWED_FIXED93_FULLBLOCK_BUDGET',
         'OPEN source resource proposal is not wholeblock admission')
    for key in ('inner_wall_seconds', 'outer_wall_seconds', 'rss_bytes', 'output_bytes', 'file_bytes', 'log_bytes'):
        need(type(budget.get(key)) is int and budget[key] > 0, 'reviewed wholeblock integer limit: ' + key)
    need(budget['outer_wall_seconds'] >= budget['inner_wall_seconds'] + 15 and
         budget['file_bytes'] <= budget['output_bytes'] and budget['automatic_retry'] is False and
         budget['progress_loop_interval'] == 131072, 'wholeblock shared budget/receipt reserves')
    need(type(budget.get('wholeblock_trace_limits')) is dict and
         type(budget.get('attention_trace_limits')) is dict, 'complete bounded stream allocations required')
    # The budget is itself pinned by the source manifest. Store a derivation
    # marker there rather than creating budget-hash <-> manifest-hash recursion.
    need(budget['attention_trace_limits'].get('source_manifest_sha256') ==
         'DERIVE_FROM_REVIEWED_SOURCE_MANIFEST',
         'Attention manifest binding must be derived without a circular seal')
    attention_limits = dict(budget['attention_trace_limits'], source_manifest_sha256=manifest_sha)
    factory = _load_fullblock_runtime(manifest)
    factory.validate_observation_integrity_policy(manifest, declaration)
    reviewer = declaration.get('reviewer')
    need(type(reviewer) is str and reviewer.startswith('/root/') and
         'audit_attention_schedule_correspondence' not in reviewer, 'independent source reviewer required')
    review = _record(declaration['source_cold_review'])
    need(review.get('status') == 'GO_FIXED93_M128_FULLBLOCK_SOURCE_COLD' and
         review.get('source_manifest_sha256') == manifest_sha and review.get('reviewer') == reviewer and
         review.get('actual_authorized') is False and review.get('native_executed') is False and
         declaration.get('observation_integrity_policy') == manifest.get('observation_integrity_policy') ==
         review.get('observation_integrity_policy'),
         'new complete source/cold review missing')
    scalar = _record(declaration['scalar_actual_prerequisite'])
    need(declaration['scalar_actual_prerequisite'] == dict(
             path=str(HERE.parent / 'review_scalar_service_actual_20261020T1101/DECISION.json'),
             bytes=3129, sha256='5980db048484bb8dc13a691d427eb140aa74556b1ab3ff33a68366b05c8741f6') and
         scalar.get('status') == 'PASS_LIMITED_ACTUAL_ORIGINAL_SCALAR_SERVICE' and
         scalar.get('scope') == 'FIXED_19_GROUP_115_ENTRY_SOFTWARE_SCALAR_SERVICE_ONLY' and
         scalar.get('independent_fraction_recalculation') is True and
         scalar.get('all_fixed_graph_inputs_and_raw_returns') is True and
         scalar.get('case_groups') == 19 and scalar.get('primitive_entries') == 115 and
         scalar.get('fullblock') is False and scalar.get('M128') is False and scalar.get('RTL') is False and
         scalar.get('native_SiLU_inner_exp') is False and scalar.get('actual_host_or_hardware_flags') is False and
         scalar.get('all_inputs') is False and scalar.get('new_execution_authorized') is False,
         'actual nontrivial scalar qualification is still required')
    need(os.environ.get('FIXED93_FULLBLOCK_PARENT_PID') == str(os.getppid()), 'supervised child required')
    out = Path(request['out']).absolute()
    need(out.parent == HERE / 'work/fixed93_fullblock' and not out.exists(), 'fresh sole wholeblock output path')
    lease_path = out.parent / 'LEASE.json'
    lease = json.loads(checked(lease_path))
    parent = _process_identity(os.getppid())
    need(lease.get('parent') == parent and lease.get('source_manifest_sha256') == manifest_sha and
         lease.get('admission_sha256') == approval_sha and lease.get('out') == str(out),
         'new exact parent lease required')
    need(len(os.sched_getaffinity(0)) == 1 and all(os.environ.get(k) == '1' for k in
         ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')), 'single CPU/thread wholeblock runtime')
    need(os.environ.get('PATH') == '/usr/bin:/bin' and
         not any(k.startswith('GIT_') or k in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME')
                 for k in os.environ), 'unsanitized parent runtime environment')
    with (out.parent / 'CONSUMED.json').open('x') as stream:
        json.dump(dict(child=_process_identity(os.getpid()), parent=parent,
                       source_manifest_sha256=manifest_sha, admission_sha256=approval_sha), stream)
    _USED = True
    _STATE = dict(pid=os.getpid(), parent=parent, source_manifest=manifest, runtime_pins=runtime,
                  external_layout_identity=cold['external_layout_identity'],
                  wholeblock_trace_limits=budget['wholeblock_trace_limits'],
                  attention_trace_limits=attention_limits, limits=budget,
                  budget_sha256=_identity(HERE / 'BUDGET_PROPOSAL.json')['sha256'])
    # From this point actual-only imports are permitted by this explicit authority.
    sys.path[:0] = [str(HERE), str(HERE / 'source')]
    os.environ['QWEN2_FIXED93_SOURCE_MANIFEST_SHA256'] = manifest_sha
    os.environ['QWEN2_FIXED93_FROZEN_BINDING_SHA256'] = _identity(
        HERE / 'source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json')['sha256']
    os.environ['QWEN2_FIXED93_ARTIFACTS_SHA256'] = layout.identity(
        'work/qwen2_recovered_inputs/ARTIFACTS.json')['sha256']
    layout.finish()
    from integration.runtime_support import gates, native_artifact, runtime_adapter
    wholeblock_observation = factory.wholeblock_observation
    initialize_observers = factory.initialize_observers
    initialized = False
    def initialize_runtime():
        nonlocal initialized
        need(not initialized and _STATE['pid'] == os.getpid(), 'one actual runtime initialization required')
        need(not any(n.split('.')[0] in ('numpy', 'yaml', 'torch') for n in sys.modules), 'runtime initialized too early')
        for key, value in runtime['git_environment'].items():
            need(key not in os.environ, 'inherited Git override')
            os.environ[key] = value
        _load_genuine_git(runtime)
        roots = [str(Path(p['path']).parent.parent) for p in runtime['package_roots'].values()]
        sys.path[:0] = list(dict.fromkeys(roots))
        runtime_adapter.initialize()
        # Only pinned stdlib-only observers load here, before their canonical runner imports.
        # This does not consume the separate one-use fullblock factory purpose.
        initialize_observers(manifest, declaration)
        initialized = True
    return dict(gates=gates, native_artifact=native_artifact, initialize_runtime=initialize_runtime,
                source_root=str(HERE / 'source'), source_manifest=str(HERE / 'SOURCE_MANIFEST.json'),
                source_sha256=manifest['source_sha256'], limits=budget,
                attention_trace_limits=attention_limits,
                wholeblock_observation=wholeblock_observation, one_use_authority_verified=True,
                native_artifact_mode='verified_existing_profile2_elf_reused', evidence_contract=CONTRACT,
                observation_integrity_policy=manifest['observation_integrity_policy'])
