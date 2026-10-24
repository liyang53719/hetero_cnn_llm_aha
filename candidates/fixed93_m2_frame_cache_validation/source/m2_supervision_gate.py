"""Small M2 bridge for the unchanged pinned WNOWAIT resource adapter.

No runtime import, native load, source copy, process launch or authority creation.
The parent loads this source from its reviewed manifest, never by path search.
"""
import hashlib
import math
import os
from pathlib import Path
import sys
import types

from m2_authority import BASE_MANIFEST_SHA, checked, load_source, need, parse, cache_policy

HERE = Path(__file__).resolve().parent
RECEIPT_BYTES = 32768
LOG_FILE_BYTES = 32768
SAMPLE_LINE_BYTES = 2048
SUPPORT = None


def read_checked(path, sha256=None, size=None):
    pin = None if sha256 is None else dict(bytes=size, sha256=sha256)
    return checked(Path(path), pin, cap=2 << 20)


def validate_budget(budget):
    need(type(budget) is dict and
         budget.get('schema') == 'fixed93-success-m2-frame-cache-budget-v1' and
         budget.get('actual_execution_authorized') is False and
         budget.get('automatic_retry') is False, 'explicit source-only M2 budget required')
    exact = dict(total_wall_seconds=120, outer_wall_seconds=120, inner_wall_seconds=105,
                 cpu_count=1, rss_bytes=2 << 30, output_bytes=80 << 20,
                 file_bytes=20 << 20, log_bytes=1 << 20,
                 supervisor_receipt_reserve_bytes=2 << 20,
                 free_space_margin_bytes=1 << 20, poll_seconds=1, sample_rows=121)
    need(all(type(budget.get(k)) is int and budget[k] == v for k, v in exact.items()),
         'fixed shared 120=105+5+10 M2 budget required')
    need(all(type(budget.get(k)) is dict and budget[k] for k in
             ('attention_trace_limits', 'wholeblock_trace_limits')), 'finite M2 stream limits required')
    return dict(budget)


def fixed_limits(budget):
    b = validate_budget(budget)
    return dict(total_seconds=b['outer_wall_seconds'], work_seconds=b['inner_wall_seconds'],
                cpu_seconds=b['outer_wall_seconds'], as_bytes=b['rss_bytes'],
                fsize_bytes=b['file_bytes'], log_bytes=b['log_bytes'],
                sample_rows=math.floor(b['outer_wall_seconds'] / b['poll_seconds']) + 1)


def sources(own, base):
    global SUPPORT
    need(own.get('schema') == 'fixed93-success-m2-frame-cache-source-v1' and
         own.get('actual_execution_authorized') is False, 'source is not actual authority')
    required = {'run_pair.py', 'm2_supervision_gate.py', 'm2_authority.py', 'm2_entry.py',
                'BUDGET.json', 'POLICY.json', 'CACHE_POLICY.json'}
    need(required <= own['files'].keys(), 'complete parent/child source pins required')
    for name, pin in own['files'].items():
        p = Path(name)
        need(not p.is_absolute() and '..' not in p.parts and str(p) == name, 'relative own source pin')
        checked(HERE / p, pin, retain=False, cap=2 << 20)
    need(set(own.get('parent_files',{})) == {'parent/HISTORY.json','parent/history_compare.py','parent/decode_diff.py'},
         'exact parent-only sealed comparison inventory')
    for name,pin in own['parent_files'].items():
        checked(HERE/name,pin,retain=False,cap=2<<20)
    cache_policy(own)
    base = Path(base)
    need(base.is_absolute() and base.resolve() == base and
         str(base) == own['base']['path'], 'exact pinned baseline root required')
    raw = checked(base / 'SOURCE_MANIFEST.json', own['base']['manifest'], cap=2 << 20)
    need(hashlib.sha256(raw).hexdigest() == BASE_MANIFEST_SHA, 'fixed baseline manifest required')
    baseline = parse(raw)
    SUPPORT = base / 'support'
    hashes, sizes = baseline['support_sha256'], baseline['support_bytes']
    need(len(hashes) == 6 and hashes.keys() == sizes.keys(), 'six unchanged public support pins')
    for name, digest in hashes.items():
        p = Path(name)
        need(not p.is_absolute() and '..' not in p.parts, 'relative support source pin')
        checked(SUPPORT / p, dict(bytes=sizes[name], sha256=digest), retain=False, cap=2 << 20)
    budget = validate_budget(parse(checked(HERE / 'BUDGET.json', own['files']['BUDGET.json'])))
    return baseline, budget


def load_adapter(base, baseline):
    """Explicit tiny gate module bridge; original adapter bytes stay unchanged."""
    need(SUPPORT == Path(base) / 'support' and 'gate' not in sys.modules,
         'fresh explicit adapter gate bridge required')
    bridge = types.ModuleType('gate')
    for name in ('HERE', 'SUPPORT', 'need', 'read_checked', 'validate_budget',
                 'fixed_limits', 'RECEIPT_BYTES', 'LOG_FILE_BYTES', 'SAMPLE_LINE_BYTES'):
        setattr(bridge, name, globals()[name])
    sys.modules['gate'] = bridge
    try:
        relative = 'supervision/supervisor_adapter.py'
        return load_source(Path(base) / relative, '_m2_exact_wnowait_adapter',
                           baseline['preparation_files'][relative])
    finally:
        need(sys.modules.get('gate') is bridge, 'adapter gate bridge replaced')
        del sys.modules['gate']


def projection(adapter, budget):
    """Build the exact production projection under a no-write/no-native scope."""
    state = {'active': True, 'attempts': []}
    def audit(event, args):
        if not state['active']:
            return
        denied = event.startswith(('ctypes.', 'subprocess.', 'socket.', 'os.exec', 'os.spawn')) or event in (
            'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.kill', 'os.killpg',
            'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.truncate')
        if event == 'import' and args[0].split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates'):
            denied = True
        if event == 'open':
            _, mode, flags = args
            denied = denied or (type(mode) is str and any(c in mode for c in 'wax+')) or (
                type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
        if denied:
            state['attempts'].append(event)
            raise RuntimeError('M2 projection denied boundary: ' + event)
    sys.addaudithook(audit)
    try:
        _, support, base, _ = adapter.load_public()
        limits = fixed_limits(budget)
        plan = dict(published_sources=base['published_sources'], phases={'micro': limits}, environment={})
        supervisor, observation = support.projected_sources(plan, 'micro')
        hashes = dict(supervisor=hashlib.sha256(supervisor).hexdigest(),
                      observation=hashlib.sha256(observation).hexdigest())
        unused = HERE / '__NO_M2_PROJECTION_OUTPUT__'
        need(not os.path.lexists(unused), 'projection marker already exists')
        runner = support.make_runner(plan, 'micro', unused)
        need(runner['projection_hashes'] == hashes and all(callable(runner[k]) for k in
             ('bounded', 'observe_exit', 'group_state', 'sample_leader', 'save')),
             'unchanged public projection interface required')
        need(not os.path.lexists(unused) and not state['attempts'], 'projection was not source-only')
        need(not any(n.split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates') for n in sys.modules),
             'runtime/DUT import in source-only parent')
        return dict(status='ASSEMBLED_REAL_PUBLIC_PROJECTION_NO_EXECUTION',
                    projection_hashes=hashes, limits=limits, actual_authorized=False,
                    child_created=False, runtime_output_created=False, dut_imported=False)
    finally:
        state['active'] = False


def admission(own, rootout, approval, admission_sha, manifest_sha, hashes):
    """Validate root-authored permission without granting or consuming either arm."""
    rootout, approval = Path(rootout), Path(approval)
    need(rootout.is_absolute() and rootout.resolve() == rootout and
         not any(p.is_symlink() for p in (rootout, *rootout.parents)) and
         rootout.parent == HERE / 'work' and rootout.is_dir() and
         approval == rootout / 'ADMISSION.json', 'fresh exact root-owned output namespace')
    need({p.name for p in rootout.iterdir()} == {'ADMISSION.json'},
         'root namespace already used; retained evidence forbids retry')
    raw = checked(approval, cap=1 << 20)
    need(hashlib.sha256(raw).hexdigest() == admission_sha, 'exact root admission SHA')
    a = parse(raw)
    need(a.get('schema') == 'fixed93-success-m2-frame-cache-admission-v1' and
         a.get('status') == 'REVIEWED_SINGLE_SUCCESS_M2_FRAME_CACHE_ACTUAL' and
         a.get('authorized_by') == '/root' and a.get('actual_execution_authorized') is True and
         type(a.get('maximum_invocations')) is int and a['maximum_invocations'] == 1 and
         a.get('arms') == ['new'] and a.get('automatic_retry') is False and
         a.get('M128_authorized') is False and a.get('fullblock_authorized') is False,
         'explicit new single-arm M2-only root authority required')
    need(a.get('output_root') == str(rootout) and
         a.get('source_manifest_sha256') == manifest_sha and
         a.get('base_source_manifest_sha256') == BASE_MANIFEST_SHA and
         a.get('policy_sha256') == own['files']['POLICY.json']['sha256'] and
         a.get('cache_policy_sha256') == own['files']['CACHE_POLICY.json']['sha256'] and
         a.get('historical_comparison_sha256') == own['parent_files']['parent/HISTORY.json']['sha256'] and
         a.get('historical_comparison_only') is True and a.get('sampling_enabled') is False and
         a.get('budget_sha256') == own['files']['BUDGET.json']['sha256'],
         'exact source/budget/policy/output authority binding')
    review_pin = a['source_cold_review']
    need(set(review_pin) == {'path', 'bytes', 'sha256'}, 'exact independent source/cold review pin')
    review = parse(checked(Path(review_pin['path']), review_pin, cap=1 << 20))
    need(review.get('status') == 'GO_SINGLE_SUCCESS_M2_FRAME_CACHE_SOURCE_COLD' and
         review.get('source_manifest_sha256') == manifest_sha and
         review.get('actual_authorized') is False and
         review.get('projection_hashes') == hashes == a.get('reviewed_projection_hashes'),
         'independent same-source same-budget projection review required')
    return a


def decoder_arguments(base, baseline, budget):
    """Raw-load only pinned representation decoders, never runtime or DUT.

    Synthetic packages supply explicit relative-import bridges. Their empty
    search paths prevent ordinary sibling discovery or ambient bytecode use.
    """
    base = Path(base)
    pins = baseline['preparation_files']
    def package(name):
        need(name not in sys.modules, 'fresh representation package required')
        value = types.ModuleType(name)
        value.__package__, value.__path__ = name, []
        sys.modules[name] = value
        return value
    def source(relative, name, parent=None):
        value = load_source(base / relative, name, pins[relative])
        if parent is not None:
            setattr(parent, name.rsplit('.', 1)[1], value)
        return value
    codec_root = Path(budget['attention_trace_limits']['codec_root'])
    codec_pins = parse(checked(base / 'capture/CODEC_PINS.json', pins['capture/CODEC_PINS.json']))
    need(set(codec_pins) == {'format.py', 'decoder.py', 'writer.py'}, 'original r3 codec inventory')
    codec_specs = {}
    for name, digest in codec_pins.items():
        raw = checked(codec_root / name, cap=2 << 20)
        need(hashlib.sha256(raw).hexdigest() == digest, 'pinned original codec source differs')
        codec_specs[name] = dict(bytes=len(raw), sha256=digest)
    fmt = load_source(codec_root / 'format.py', 'format', codec_specs['format.py'])
    decoder = load_source(codec_root / 'decoder.py', '_m2_original_r3_decoder', codec_specs['decoder.py'])
    capture = package('_m2_decode_capture')
    source('capture/fixed_token_table.py', capture.__name__ + '.fixed_token_table', capture)
    token = source('capture/token_decoder.py', capture.__name__ + '.token_decoder', capture)
    operands = source('capture/representation_decoder.py', capture.__name__ + '.representation_decoder', capture)
    observation = package('_m2_decode_observation')
    source('observation/source_guard.py', observation.__name__ + '.source_guard', observation)
    events = source('observation/event_stream.py', observation.__name__ + '.event_stream', observation)
    need(not any(n.split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates') for n in sys.modules),
         'parent representation loader imported runtime/DUT')
    return dict(Decoder=decoder.Decoder, Limits=fmt.Limits, decode_exp=events.decode_exp_envelope,
                TokenDecoder=token.TokenRecordDecoder, OperandDecoder=operands.OperandDictionaryDecoder,
                attention_limits=budget['attention_trace_limits']['codec_limits'],
                whole_limits=budget['wholeblock_trace_limits']['codec'])
