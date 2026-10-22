"""Read-only terminal-receipt and LEC1 container consistency, never numerical PASS."""
import argparse
import builtins
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import sys
import time
import types

PINS = {'format.py': '936f01ff9c7152c4752305c60c1442489f4fa8d71c08d7a38458d9f9690c76c5',
        'decoder.py': '6f93cf8b6929a840f725c539a53a96f95e369b47920b4e36b4eaf0ac5d570f89'}
METADATA_CAP = 8 << 20
PLAN_CAP = 128 << 10
RECEIPTS = {'launch': 'LAUNCH.json', 'native': 'supervisor/native.json',
            'lease': 'LEASE.json', 'consumed': 'CONSUMED.json',
            'result': 'run01/RESULT.json', 'algorithm': 'run01/ALGORITHM_ARTIFACT_SEAL.json',
            'attention': 'run01/attention_observation/summary.json'}
STREAMS = {'wholeblock': 'run01/wholeblock_events.lec1',
           'attention': 'run01/attention_observation/attention-events.lec1'}
HEX = re.compile('[0-9a-f]{64}\\Z')
PLAN_SCHEMA = 'fixed93-pv-reuse-offline-container-plan-v1'
EVIDENCE_CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'
ATTENTION_SCHEMA = 'fixed93-fullblock-attention-pv-reuse-observation-v1'
ATTENTION_REUSE_DECLARATIONS = {
    'normalization_evaluations_per_causal_key': 1,
    'probability_use_repeats': 8,
    'normalization_reuses_per_causal_key': 7,
    'observed_normalization_reuses': 693504,
    'scalar_schedule_changed': True,
    'both_probability_domains_repeats_verified': True,
}


class Rejected(ValueError):
    pass


def need(ok, label):
    if not ok:
        raise Rejected(label)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exact(value, expected):
    return type(value) is type(expected) and value == expected


def keys(value, names, label):
    need(type(value) is dict and set(value) == set(names), label + ': fields')


def hex_sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def uint(value):
    return type(value) is int and 0 <= value < (1 << 63)


def json_bytes(raw, cap):
    need(type(raw) is bytes and len(raw) <= cap, 'JSON byte cap')
    depth = 0
    quoted = escaped = False
    for b in raw:
        if quoted:
            if escaped: escaped = False
            elif b == 92: escaped = True
            elif b == 34: quoted = False
        elif b == 34: quoted = True
        elif b in (91, 123):
            depth += 1
            need(depth <= 64, 'JSON depth cap')
        elif b in (93, 125): depth -= 1
    need(depth == 0 and not quoted, 'JSON incomplete')
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def constant(_): raise Rejected('nonfinite JSON constant')
    obj = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    pending, count = [obj], 0
    while pending:
        x = pending.pop(); count += 1
        need(count <= 200000, 'JSON node cap')
        if type(x) is dict: pending.extend(x.values())
        elif type(x) is list: pending.extend(x)
        elif type(x) is float: need(math.isfinite(x), 'nonfinite JSON float')
    return obj


def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def regular(path):
    path = Path(path).absolute()
    need(path == path.resolve(), 'aliased path')
    s = path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'not an unaliased regular file')
    return path, stamp(s)


def inside(root, relative):
    need(type(relative) is str and str(PurePosixPath(relative)) == relative and
         not relative.startswith('/') and all(x not in ('', '.', '..') for x in relative.split('/')),
         'relative path escape')
    p = root / relative
    need(p.resolve().is_relative_to(root), 'root path escape')
    return p


def open_checked(path):
    p, before = regular(path)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        need(stamp(os.fstat(fd)) == before, 'file changed before open')
        return os.fdopen(fd, 'rb', buffering=0), before
    except BaseException:
        os.close(fd)
        raise


def unchanged(path, stream, before):
    need(stamp(os.fstat(stream.fileno())) == before and regular(path)[1] == before,
         'file changed during read')


def spec_check(spec, cap):
    keys(spec, ('bytes', 'sha256'), 'file pin')
    need(uint(spec['bytes']) and spec['bytes'] <= cap and hex_sha(spec['sha256']), 'file pin type/cap')


def read_pinned(path, spec, cap):
    spec_check(spec, cap)
    stream, before = open_checked(path)
    with stream:
        need(before[4] == spec['bytes'], 'metadata size mismatch')
        raw = stream.read(spec['bytes'] + 1)
        need(len(raw) == spec['bytes'] and digest(raw) == spec['sha256'], 'metadata hash mismatch')
        unchanged(path, stream, before)
    return json_bytes(raw, cap), before


def load_codec():
    """Compile unchanged pinned sources; isolate the decoder's top-level format import."""
    root = Path(__file__).resolve().parent / 'r3'
    sources = {}
    for name, expected in PINS.items():
        p, first = regular(root / name)
        need(first[4] < 32768, 'r3 source cap before open')
        stream, before = open_checked(p)
        with stream:
            need(before == first, 'r3 source changed before read')
            raw = stream.read(before[4] + 1)
            need(len(raw) == before[4] and digest(raw) == expected, 'r3 source pin: ' + name)
            unchanged(p, stream, before)
        sources[name] = raw
    name = '_fixed93_offline_r3_format'
    need(name not in sys.modules, 'private codec module collision')
    fmt = types.ModuleType(name)
    fmt.__file__ = str(root / 'format.py')
    sys.modules[name] = fmt
    try:
        exec(compile(sources['format.py'], fmt.__file__, 'exec', dont_inherit=True), fmt.__dict__)
        dec = types.ModuleType('_fixed93_offline_r3_decoder')
        dec.__file__ = str(root / 'decoder.py')
        def private_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'format':
                need(level == 0 and bool(fromlist), 'unexpected format import')
                return fmt
            return builtins.__import__(name, globals, locals, fromlist, level)
        dec.__dict__['__builtins__'] = dict(vars(builtins), __import__=private_import)
        exec(compile(sources['decoder.py'], dec.__file__, 'exec', dont_inherit=True), dec.__dict__)
        need(dec.Seal is fmt.Seal and dec.Record is fmt.Record, 'codec dependency identity')
        return fmt, dec
    finally:
        del sys.modules[name]


def process_identity(value):
    keys(value, ('pid', 'start_ticks'), 'process identity')
    need(all(uint(x) and x > 0 for x in value.values()), 'invalid process identity')


def check_terminal(root, plan, docs, attestation):
    identity = plan['identity']
    keys(identity, ('source_manifest_sha256', 'admission_sha256', 'budget_sha256', 'source_map_sha256',
                    'reviewed_source_manifest'), 'expected identity')
    need(all(hex_sha(value) for value in identity.values()), 'identity types')
    need(identity['reviewed_source_manifest'] == identity['source_manifest_sha256'],
         'reviewed closure digest differs from manifest-file digest')
    a, n, lease, consumed, r = (docs[k] for k in ('launch', 'native', 'lease', 'consumed', 'result'))
    for name, obj in (('launch', a), ('lease', lease)):
        for k in ('source_manifest_sha256', 'admission_sha256', 'budget_sha256'):
            need(exact(obj.get(k), identity[k]), name + ' identity mismatch: ' + k)
    for k in ('source_manifest_sha256', 'admission_sha256'):
        need(exact(consumed.get(k), identity[k]), 'consumed identity mismatch')
    need(a.get('status') == 'PASS_FULLBLOCK_PROCESS_SUPERVISION_ONLY' and
         exact(a.get('returncode'), 0) and a.get('cleanup_confirmed') is True and
         a.get('ownership_uncertain', False) is False, 'launcher not successful terminal')
    need(a.get('actual_arithmetic_accepted') is False and a.get('M128_acceptance') is False and
         a.get('independent_actual_review_required') is True, 'launcher scope mismatch')
    need(n.get('status') == 'PASS' and exact(n.get('exit_code'), 0) and
         n.get('anchor_confirmed') is True and n.get('reaped') is True and
         n.get('group_state') == 'absent' and n.get('cleanup_confirmed') is True and
         n.get('timed_out') is False and n.get('parent_exception') is None and
         n.get('stage') == 'native' and n.get('spawn_handle_acquired') is True and
         exact(n.get('expected_exit'), 0), 'native supervision incomplete')
    keys(plan['invocation'], ('argv','cwd'), 'expected invocation')
    need(type(plan['invocation']['argv']) is list and plan['invocation']['argv'] and
         all(type(v) is str for v in plan['invocation']['argv']) and type(plan['invocation']['cwd']) is str and
         n.get('argv') == plan['invocation']['argv'] and n.get('cwd') == plan['invocation']['cwd'], 'native invocation mismatch')
    need(not any(k in n for k in ('anchor_error','reap_error','cleanup_probe_error','output_limit_exceeded')),
         'native success contradicts error fields')
    before_reap = n.get('group_before_reap')
    need((before_reap == 'absent' and n.get('kill_attempted') is False and n.get('kill_result') == 'not_requested') or
         (before_reap in ('present','unknown') and n.get('kill_attempted') is True and
          n.get('kill_result') in ('signal_sent_before_reap','group_already_absent')), 'native anchored cleanup contradiction')
    d = a.get('diagnostics', {})
    kill_map = {'not_requested':'NOT_REQUESTED', 'signal_sent_before_reap':'SIGNAL_SENT_BEFORE_REAP',
                'group_already_absent':'GROUP_ALREADY_ABSENT'}
    need(d.get('kill_attempted') is n['kill_attempted'] and d.get('kill_result') == kill_map[n['kill_result']],
         'diagnostic cleanup projection mismatch')
    for k, v in {'native_record_status':'PASS', 'exit_code':0, 'waitid_code':1, 'waitid_status':0,
                 'receipt_timed_out':False, 'cleanup_confirmed':True,
                 'failure_code':'NONE', 'failure_boundary':'NONE'}.items():
        need(exact(d.get(k), v), 'diagnostics mismatch: ' + k)
    process_identity(lease.get('parent')); process_identity(consumed.get('parent'))
    process_identity(consumed.get('child'))
    need(consumed.get('parent') == lease['parent'] and exact(n.get('pid'), consumed['child']['pid']) and
         exact(n.get('pgid'), consumed['child']['pid']), 'parent/child identity mismatch')
    observed_exit = n.get('exit_observed_while_unreaped')
    keys(observed_exit, ('pid','code','status'), 'unreaped exit observation')
    need(exact(observed_exit['pid'], consumed['child']['pid']) and exact(observed_exit['code'], 1) and
         exact(observed_exit['status'], 0), 'not observed natural exit0 while anchored')
    output = str(root / 'run01')
    need(a.get('actual_output') == output and lease.get('out') == output, 'run output identity mismatch')
    keys(attestation, ('schema', 'original_session_id', 'launcher_exit_code', 'cleanup_confirmed',
                      'ownership_uncertain', 'run_root', 'parent', 'child', 'identity'), 'terminal attestation')
    process_identity(attestation['parent']); process_identity(attestation['child'])
    need(attestation['schema'] == 'fixed93-original-session-terminal-v1' and
         uint(attestation['original_session_id']) and attestation['original_session_id'] > 0 and
         exact(attestation['launcher_exit_code'], 0) and attestation['cleanup_confirmed'] is True and
         attestation['ownership_uncertain'] is False and attestation['run_root'] == str(root) and
         attestation['parent'] == lease['parent'] and attestation['child'] == consumed['child'] and
         attestation['identity'] == identity, 'trusted original-session terminal attestation mismatch')
    need(r.get('status') == 'PASS_FIXED93_M128_OFFICIAL_OBSERVED_FULLBLOCK_PUBLIC21' and
         all(r.get(k) is True for k in ('official_observed_node_pass','acceptance_sealed',
             'whole_block_terminal','actual_outputs_sealed','finalfence','fullblock_pass')), 'fullblock report is not terminal/complete')
    need(r.get('reviewed_source_manifest') == identity['reviewed_source_manifest'], 'reviewed manifest digest mismatch')
    source = r.get('source_sha256_before')
    need(type(source) is dict and source and all(type(k) is str and hex_sha(v) for k,v in source.items()) and
         r.get('source_sha256_after') == source, 'source map before/after mismatch')
    computed = digest(json.dumps(source, sort_keys=True).encode())
    need(computed == identity['source_map_sha256'] == r.get('source_manifest_sha256'), 'source MAP digest mismatch')
    debts = r.get('backend_debts')
    need(type(debts) is dict and debts and all(v is False for v in debts.values()), 'unclosed reported debts')
    need(r.get('same_live_identity_initial') == r.get('same_live_identity_final') and
         type(r.get('same_live_identity_initial')) is dict and r['same_live_identity_initial'], 'same-live identity mismatch')
    need(docs['algorithm'] == r.get('algorithm_artifact_seal') and
         docs['algorithm'].get('schema') == 'fixed93-actual-algorithm-artifact-seal-v1' and
         docs['algorithm'].get('complete_algorithm_arrays') is True, 'algorithm seal missing/mismatch')
    obs = docs['attention']
    need(obs == r.get('observation') and obs.get('schema') == ATTENTION_SCHEMA and
         obs.get('complete_observation') is True and obs.get('status') == 'COMPLETE_ATTENTION_OBSERVATION_NOT_FULLBLOCK_ACCEPTANCE' and
         obs.get('observer_error') is None and obs.get('event_file') == 'attention-events.lec1' and
         all(obs.get(k) is False for k in ('control_only','numerical_acceptance','native_acceptance','fullblock_acceptance')), 'Attention incomplete/mismatch')
    need(obs.get('source_manifest_sha256') == identity['source_manifest_sha256'] and
         obs.get('source_sha256') == source, 'Attention source identity mismatch')
    for key, expected in ATTENTION_REUSE_DECLARATIONS.items():
        need(exact(obs.get(key), expected) and exact(r['observation'].get(key), expected),
             'Attention PV-reuse declaration mismatch: ' + key)
    whole = r.get('wholeblock_observation', {})
    need(exact(r.get('evidence_contract'), plan['evidence_contract']) and
         exact(whole.get('evidence_contract'), plan['evidence_contract']), 'evidence contract mismatch')
    need(whole.get('lossless_streams_sealed') is True and whole.get('complete_declared_schedule') is True and
         whole.get('complete_declared_cache') is True, 'wholeblock observation incomplete')
    return whole, obs


class HashedReader:
    def __init__(self, stream, cap, deadline):
        self.stream, self.cap, self.deadline = stream, cap, deadline
        self.count, self.hasher = 0, hashlib.sha256()
    def read(self, size):
        need(type(size) is int and 0 <= size <= 69720, 'read allocation bound')
        need(time.monotonic() <= self.deadline, 'scan deadline')
        # A final read(1) is permitted to prove real EOF, but nonempty bytes beyond cap reject.
        need(self.count + size <= self.cap + 1, 'stream input cap before read')
        raw = self.stream.read(size)
        need(type(raw) is bytes, 'nonbytes reader')
        self.count += len(raw)
        need(self.count <= self.cap, 'stream byte cap exceeded')
        self.hasher.update(raw)
        return raw


def seal_shape(seal):
    keys(seal, ('records','raw_bytes','encoded_bytes','final_hash'), 'external stream seal')
    need(all(uint(seal[k]) for k in ('records','raw_bytes','encoded_bytes')) and hex_sha(seal['final_hash']), 'seal types')
    need(seal['records'] > 0 and seal['raw_bytes'] > 0, 'empty stream cannot qualify fullblock container')


def scan(path, role, entry, external, fmt, decoder, deadline):
    keys(entry, ('bytes','sha256','limits'), 'stream plan')
    spec_check({k:entry[k] for k in ('bytes','sha256')}, (1 << 63)-1)
    keys(entry['limits'], vars(fmt.Limits()), 'decoder policy')
    policy = fmt.Limits(**entry['limits']).validate()
    need(entry['bytes'] <= policy.max_output, 'stream exceeds fixed policy')
    seal_shape(external)
    source, before = open_checked(path)
    with source:
        need(before[4] == entry['bytes'], 'stream size mismatch')
        reader = HashedReader(source, entry['bytes'], deadline)
        parsed = decoder.Decoder(reader, policy)
        count = 0
        for record in parsed.records():
            count += 1
            if role == 'wholeblock':
                need(record.kind in (5,6,7,8) and set(record.metadata) == {'schema','semantic'} and
                     record.metadata['schema'] == 'wholeblock-token-envelope-v1' and
                     type(record.metadata['semantic']) is bool, 'wholeblock envelope role/schema')
            else:
                need(record.kind == 8 and set(record.metadata) == {'schema','sequence','kind'} and
                     record.metadata['schema'] in ('fixed93-attention-event-v2','fixed93-attention-exp-envelope-v1') and
                     exact(record.metadata['sequence'], count-1) and type(record.metadata['kind']) is str,
                     'Attention envelope role/schema/sequence')
        need(parsed.seal is not None and type(parsed.seal) is fmt.Seal, 'real decoder EOF seal missing')
        observed = vars(parsed.seal)
        need(observed == external and observed['records'] == count, 'external stream seal mismatch')
        need(reader.count == entry['bytes'] == observed['encoded_bytes'] and
             reader.hasher.hexdigest() == entry['sha256'], 'stream full-file identity mismatch')
        unchanged(path, source, before)
    return {'records':count,'bytes':reader.count,'sha256':reader.hasher.hexdigest(),'codec_seal':observed}, before


def verify(root, plan_path, expected_plan_sha, terminal_path, budget_path, *, seconds=30):
    """Only call with independently reviewed plan/attestation; no authority is generated."""
    need(type(seconds) is int and 1 <= seconds <= 3600, 'offline seconds bound')
    deadline = time.monotonic() + seconds
    root = Path(root).absolute()
    need(root.resolve() == root and root.is_dir(), 'aliased/missing run root')
    need(hex_sha(expected_plan_sha), 'expected plan SHA required')
    pp, ps = regular(plan_path)
    need(ps[4] <= PLAN_CAP, 'plan cap')
    plan, pstamp = read_pinned(pp, {'bytes':ps[4],'sha256':expected_plan_sha}, PLAN_CAP)
    keys(plan, ('schema','evidence_contract','identity','invocation','receipts','streams','terminal_attestation','budget'), 'plan')
    need(exact(plan['schema'], PLAN_SCHEMA), 'plan schema')
    need(exact(plan['evidence_contract'], EVIDENCE_CONTRACT), 'plan evidence contract')
    keys(plan['receipts'], RECEIPTS, 'receipt inventory'); keys(plan['streams'], STREAMS, 'stream inventory')
    docs, stamps = {}, []
    for role, rel in RECEIPTS.items():
        path = inside(root, rel)
        docs[role], before = read_pinned(path, plan['receipts'][role], METADATA_CAP)
        stamps.append((path, before))
    attestation, astamp = read_pinned(terminal_path, plan['terminal_attestation'], PLAN_CAP)
    whole, attention = check_terminal(root, plan, docs, attestation)
    budget, bstamp = read_pinned(budget_path, plan['budget'], PLAN_CAP)
    need(plan['budget']['sha256'] == plan['identity']['budget_sha256'] and
         budget.get('schema') == 'fixed93-fullblock-resource-proposal-v1' and
         budget.get('status') == 'REVIEWED_FIXED93_FULLBLOCK_BUDGET', 'budget identity/schema')
    need(plan['streams']['wholeblock']['limits'] == budget.get('wholeblock_trace_limits', {}).get('codec') and
         plan['streams']['attention']['limits'] == budget.get('attention_trace_limits', {}).get('codec_limits'),
         'stream policies differ from pinned budget')
    artifact = whole.get('artifacts', {}).get('wholeblock_events.lec1', {})
    need(artifact.get('path') == str(root / STREAMS['wholeblock']) and
         exact(artifact.get('bytes'), plan['streams']['wholeblock']['bytes']) and
         artifact.get('sha256') == plan['streams']['wholeblock']['sha256'], 'wholeblock file external identity')
    need(attention.get('event_codec_source_sha256', {}).get('format.py') == PINS['format.py'] and
         attention.get('event_codec_source_sha256', {}).get('decoder.py') == PINS['decoder.py'], 'reported codec source identity')
    need(exact(attention.get('event_count'), attention.get('event_codec_seal', {}).get('records')), 'Attention event count mismatch')
    fmt, decoder = load_codec()
    observed = {}
    for role, external in [('wholeblock', whole.get('codec_seal')), ('attention', attention.get('event_codec_seal'))]:
        path = inside(root, STREAMS[role])
        observed[role], before = scan(path, role, plan['streams'][role], external, fmt, decoder, deadline)
        stamps.append((path, before))
    for path, before in stamps + [(pp,pstamp),(Path(terminal_path).absolute(),astamp),(Path(budget_path).absolute(),bstamp)]:
        need(regular(path)[1] == before, 'evidence changed before final verdict')
    need(time.monotonic() <= deadline, 'verification deadline')
    return {'status':'PASS_REPORTED_TERMINAL_AND_TWO_STREAM_CONTAINERS_ONLY',
            'plan_sha256':expected_plan_sha,'streams':observed,
            'terminal_basis':'externally trusted, SHA-pinned original-session attestation plus matching receipts',
            'independently_observed_process_exit':False,'algorithm_artifact_bytes_checked':False,
            'token_operand_payload_semantics_checked':False,'schedule_cache_correspondence_checked':False,
            'attention_logical_payload_digest_checked':False,'numerical_acceptance':False,
            'fullblock_acceptance':False,'RTL':False}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run-root', required=True); ap.add_argument('--plan', required=True)
    ap.add_argument('--plan-sha256', required=True); ap.add_argument('--terminal-attestation', required=True)
    ap.add_argument('--budget', required=True)
    ap.add_argument('--seconds', type=int, default=30); ap.add_argument('--scan', action='store_true')
    args=ap.parse_args(argv)
    armed = False
    try:
        need(args.scan, 'explicit --scan required; no implicit large scan')
        need(1 <= args.seconds <= 3600, 'seconds bound')
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (256 << 20,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (args.seconds,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        def timeout(*_): raise Rejected('offline wall deadline')
        need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'existing alarm ownership')
        signal.signal(signal.SIGALRM, timeout); signal.setitimer(signal.ITIMER_REAL, args.seconds); armed = True
        result=verify(args.run_root,args.plan,args.plan_sha256,args.terminal_attestation,args.budget,seconds=args.seconds)
        print(json.dumps(result,sort_keys=True)); return 0
    except Exception as exc:
        print(json.dumps({'status':'REJECTED_NO_ACCEPTANCE','error_type':type(exc).__name__,'error':str(exc)[:512],
                          'fullblock_acceptance':False,'numerical_acceptance':False},sort_keys=True)); return 1
    finally:
        if armed: signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == '__main__':
    raise SystemExit(main())
