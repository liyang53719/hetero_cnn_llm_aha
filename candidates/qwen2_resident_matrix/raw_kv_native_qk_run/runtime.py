"""Source and context admission for one bounded native-only QKV/QK validation.

The original 221-source setup context is separate from this union contract.
Only source preparation occurs here; no package, payload or native code loads.
"""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import time

ROOT = Path(__file__).resolve().parents[3]
PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/'
CONTRACT = PREFIX + 'contract.json'
WORKFLOW = '.github/workflows/raw-kv-native-qk.yml'
PROFILE = 'qwen2-fresh-native-qkv-qk-m16-m128-v1'
BASE_COMMIT = '30caacb236dada5edf8353a2904f2cc46f5e0b9b'
TOTAL_SECONDS = 900
CLEANUP_SECONDS = 5
RECEIPT_SECONDS = 1
PHASE_LIMITS = dict(preflight=20, environment=120, acquisition=420,
                    kernel=30, native16=60, native128=120)
PHASES = tuple(PHASE_LIMITS)
ORIGINAL_PHASES = ('preflight', 'environment', 'acquisition')
ORIGINAL_CONTRACT = 'candidates/qwen2_resident_matrix/raw_kv_public_m128_run/launch-contract.json'
ORIGINAL_CONTRACT_SHA256 = 'e5f9dd18f6f288c98598b0935426da87588cdd20f1c197b1545a6e822e7902a7'
RECIPE_PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_native_qk/'
OLD_RECIPE_PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_native_qkv/'
OLD_SMOKE_EVIDENCE_SHA256 = 'e1a760f571841cd6423102f32a48da1beee5a9e170d9292adf67b96bd096c12d'
RECIPE_PINS_SHA256 = 'b747f252f6b488622696f3309f5f30fac9d9b3f974a9a986c7e34dd2789096c0'
SMOKE_EVIDENCE_SHA256 = '2d09797493192786da472fd37f4d8feca51ed13f54ec6df8f597d6f9475a9c52'
GATE = 'scripts/qwen2_layer0_model_gate.py'
GENERATED_MODULE_SHA256 = '4cff9eb2a4aac94c3e7fd04a9ac4eac22092ee874a1fa1fbb7d69c63b05d106f'
OWN = tuple(PREFIX + name for name in ('runtime.py', 'phase.py', 'run_ci.py',
    'test_runtime.py', 'test_phase.py', 'test_run_ci.py', 'README.md')) + (WORKFLOW,)
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
CONTEXT_KEYS = {'schema', 'profile', 'workspace', 'checkout_commit', 'source_sha256',
    'contract_sha256', 'start_ns', 'deadline_ns', 'generated_module', 'generated_module_sha256'}


def need(ok, reason='native QKV/QK contract'):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value, length=64):
    return type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value)


def relative_name(value):
    return (type(value) is str and bool(value) and '\\' not in value and '\0' not in value and
            not PurePosixPath(value).is_absolute() and '..' not in PurePosixPath(value).parts and
            str(PurePosixPath(value)) == value and value != '.')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def same(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(same(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def json_bytes(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate metadata key')
            result[key] = value
        return result
    def finite(value):
        parsed = float(value)
        need(math.isfinite(parsed), 'nonfinite metadata')
        return parsed
    def reject(_):
        raise ValueError('nonfinite metadata')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=finite, parse_constant=reject)


def safe_path(path, *, directory=False):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts and '\\' not in str(path) and '\0' not in str(path),
         'unsafe private path')
    need(all(not p.is_symlink() for p in (path, *path.parents)), 'symlink private path')
    mode = path.stat().st_mode
    need(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode), 'private file type')
    return path


def read_bytes(path, limit=262144):
    """Read one bounded regular-file identity; parse/hash callers use these bytes."""
    path = safe_path(path)
    before = path.stat()
    need(0 <= before.st_size <= limit, 'metadata size')
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        need(identity(os.fstat(stream.fileno())) == identity(before), 'metadata identity changed')
        raw = stream.read(limit + 1)
        need(identity(os.fstat(stream.fileno())) == identity(before), 'metadata identity changed')
    need(len(raw) == before.st_size and identity(path.stat()) == identity(before) and not path.is_symlink(),
         'metadata changed during read')
    return raw


def read_source(name, limit=4194304):
    need(relative_name(name), 'unsafe source name')
    return read_bytes(ROOT / name, limit)


def read_json(path, limit=262144):
    return json_bytes(read_bytes(path, limit))


def baseline_contract():
    """Read old frozen identities without requiring overlays already installed."""
    from ..raw_kv_public_m128_run import launch
    from ..raw_kv_native_qk import prepare as recipe
    need(ROOT == launch.ROOT == recipe.ROOT, 'source root differs')
    old_raw, old = launch.contract_value()
    need(sha(old_raw) == ORIGINAL_CONTRACT_SHA256, 'original launch contract drift')
    original = dict(old['source_sha256'])
    original[ORIGINAL_CONTRACT] = sha(old_raw)
    need(len(original) == 221, 'original setup inventory')
    qkv = recipe.snapshot()
    need(qkv['pins_sha256'] == RECIPE_PINS_SHA256 and
         qkv['generated_module_sha256'] == GENERATED_MODULE_SHA256, 'recipe contract drift')
    union = dict(original)
    for name, value in qkv['source_sha256'].items():
        need(name not in union or union[name] == value, 'overlapping source identity differs')
        union[name] = value
    union[RECIPE_PREFIX + 'pins.json'] = RECIPE_PINS_SHA256
    union[RECIPE_PREFIX + 'SMOKE_EVIDENCE.json'] = SMOKE_EVIDENCE_SHA256
    union[OLD_RECIPE_PREFIX + 'SMOKE_EVIDENCE.json'] = OLD_SMOKE_EVIDENCE_SHA256
    need(len(union) == 238, 'original plus recipes inventory')
    return original, union, dict(old['generated_sha256'])


def validate_contract(value):
    fixed = dict(schema=1, profile=PROFILE, base_commit=BASE_COMMIT, total_budget_seconds=TOTAL_SECONDS,
        cleanup_grace_seconds=CLEANUP_SECONDS, receipt_reserve_seconds=RECEIPT_SECONDS,
        phase_limits=PHASE_LIMITS, original_launch_contract_sha256=ORIGINAL_CONTRACT_SHA256,
        recipe_pins_sha256=RECIPE_PINS_SHA256, smoke_evidence_sha256=SMOKE_EVIDENCE_SHA256,
        old_smoke_evidence_sha256=OLD_SMOKE_EVIDENCE_SHA256,
        generated_module_sha256=GENERATED_MODULE_SHA256)
    need(type(value) is dict and set(value) == set(fixed) | {'source_sha256', 'generated_sha256'},
         'exact native QKV/QK contract fields')
    need(all(same(value[k], v) for k, v in fixed.items()), 'native QKV/QK fixed contract differs')
    original, union, generated = baseline_contract()
    sources = value['source_sha256']
    need(type(sources) is dict and set(sources) == set(union) | set(OWN) and len(sources) == 246,
         'exact native QKV/QK source inventory')
    need(all(relative_name(n) and digest(h) for n, h in sources.items()), 'source identity type')
    need(all(sources[n] == h for n, h in union.items()), 'published source identity changed')
    need(sources[PREFIX + 'runtime.py'] == IMPORTED_SHA256, 'loaded runtime drift')
    need(same(value['generated_sha256'], generated) and len(generated) == 10, 'original ten overlays changed')
    return original


def snapshot(*, composed=False):
    need(type(composed) is bool, 'canonical source mode required')
    raw = read_source(CONTRACT, 131072)
    value = json_bytes(raw)
    original = validate_contract(value)
    sources = dict(value['source_sha256'])
    setup_sources = dict(original)
    if composed:
        sources.update(value['generated_sha256'])
        setup_sources.update(value['generated_sha256'])
    blobs = {}
    for name, identity in sources.items():
        content = read_source(name)
        need(sha(content) == identity, 'native QKV/QK source drift')
        if not composed:
            blobs[name] = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
    sources[CONTRACT] = sha(raw)
    if not composed:
        blobs[CONTRACT] = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    return dict(profile=PROFILE, contract_sha256=sha(raw), sources=sources, inputs=dict(sources),
        generated=dict(value['generated_sha256']), generated_module_sha256=GENERATED_MODULE_SHA256,
        original_setup_sources=setup_sources, git_blobs=blobs)


def source_snapshot():
    return snapshot(composed=True)['sources']


def prepare_outputs(out):
    """Prepare ten unchanged setup overlays and a separately located gate."""
    from ..raw_kv_public_m128_run import prepare as original_prepare
    from ..raw_kv_native_qk import prepare as recipe_prepare
    out = Path(out)
    need(out.is_absolute() and '..' not in out.parts and not out.exists() and not out.is_symlink() and
         all(not parent.is_symlink() for parent in out.parents), 'fresh preparation directory required')
    frozen = snapshot(composed=False)
    out.mkdir()
    old = original_prepare.prepare(out / 'overlays', enable_raw_kv=True)
    need(same(old['inputs'], frozen['original_setup_sources']) and same(old['generated'], frozen['generated']),
         'original preparation identity differs')
    recipe = recipe_prepare.prepare(out / 'generated')
    need(recipe['generated_module_sha256'] == GENERATED_MODULE_SHA256 and
         sha(read_bytes(out / 'generated' / GATE, 4194304)) == GENERATED_MODULE_SHA256,
         'separate generated module differs')
    need(same(snapshot(composed=False), frozen), 'preparation source postflight drift')
    return dict(status='PASS_SOURCE_PREPARATION_ONLY', sources=frozen['sources'],
        generated=frozen['generated'], generated_module_sha256=GENERATED_MODULE_SHA256,
        numerical_execution=False, public_execution=False, rtl_execution=False)


def check_context(context, *, check_deadline=True):
    """Validate canonical metadata before following any referenced path."""
    need(type(check_deadline) is bool)
    need(type(context) is dict and set(context) == CONTEXT_KEYS, 'exact native QKV/QK context')
    need(type(context['schema']) is int and context['schema'] == 1 and context['profile'] == PROFILE and
         type(context['profile']) is str and digest(context['checkout_commit'], 40), 'context profile')
    need(type(context['start_ns']) is int and type(context['deadline_ns']) is int and
         0 < context['start_ns'] < context['deadline_ns'] and
         context['deadline_ns'] - context['start_ns'] == TOTAL_SECONDS * 1000000000, 'context deadline scope')
    now = time.monotonic_ns()
    need(context['start_ns'] <= now, 'context starts in future')
    if check_deadline:
        need(context['deadline_ns'] - (CLEANUP_SECONDS + RECEIPT_SECONDS) * 1000000000 > now,
             'native QKV/QK deadline exhausted')
    need(type(context['workspace']) is str and type(context['generated_module']) is str and
         digest(context['contract_sha256']) and digest(context['generated_module_sha256']) and
         context['generated_module_sha256'] == GENERATED_MODULE_SHA256 and
         type(context['source_sha256']) is dict and
         all(relative_name(n) and digest(h) for n, h in context['source_sha256'].items()), 'context identity')
    workspace = Path(context['workspace'])
    need(Path(context['generated_module']) == workspace / 'generated' / GATE, 'fixed generated module path')
    return context


def read_context(path, *, check_deadline=True):
    path = Path(path)
    context = check_context(read_json(path), check_deadline=check_deadline)
    workspace = safe_path(context['workspace'], directory=True)
    need(safe_path(path) == workspace / 'validation_context.json', 'context workspace differs')
    frozen = snapshot(composed=True)
    need(same(context['source_sha256'], frozen['sources']) and
         context['contract_sha256'] == frozen['contract_sha256'], 'context source identity differs')
    need(sha(read_bytes(context['generated_module'], 4194304)) == GENERATED_MODULE_SHA256,
         'generated module source drift')
    return context, workspace


def original_setup_context(context):
    """Exact original setup schema, retaining its independently frozen 221 map."""
    check_context(context)
    workspace = safe_path(context['workspace'], directory=True)
    frozen = snapshot(composed=True)
    need(same(context['source_sha256'], frozen['sources']) and
         context['contract_sha256'] == frozen['contract_sha256'], 'context source identity differs')
    return dict(schema=1, workspace=str(workspace), checkout_commit=context['checkout_commit'],
        enable_raw_kv=True, source_sha256=dict(frozen['original_setup_sources']),
        asset_source_sha256=dict(frozen['original_setup_sources']),
        work_deadline_ns=context['deadline_ns'] - (CLEANUP_SECONDS + RECEIPT_SECONDS) * 1000000000)


def make_context(workspace, commit, start_ns, deadline_ns, frozen):
    current = snapshot(composed=True)
    need(same(frozen, current), 'context snapshot differs')
    workspace = safe_path(workspace, directory=True)
    context = dict(schema=1, profile=PROFILE, workspace=str(workspace), checkout_commit=commit,
        source_sha256=dict(current['sources']), contract_sha256=current['contract_sha256'],
        start_ns=start_ns, deadline_ns=deadline_ns,
        generated_module=str(workspace / 'generated' / GATE),
        generated_module_sha256=GENERATED_MODULE_SHA256)
    check_context(context)
    need(sha(read_bytes(context['generated_module'], 4194304)) == GENERATED_MODULE_SHA256,
         'generated module source drift')
    return context


def old_setup_context(context, frozen):
    need(same(frozen, snapshot(composed=True)), 'original context snapshot differs')
    return original_setup_context(context)


def remaining(context, ceiling):
    need(type(ceiling) in (int, float) and math.isfinite(ceiling) and 0 < ceiling <= TOTAL_SECONDS,
         'phase ceiling')
    check_context(context)
    result = min(ceiling, (context['deadline_ns'] - time.monotonic_ns()) / 1000000000
                 - CLEANUP_SECONDS - RECEIPT_SECONDS)
    if result <= 0:
        raise TimeoutError('native QKV/QK deadline exhausted')
    return result
