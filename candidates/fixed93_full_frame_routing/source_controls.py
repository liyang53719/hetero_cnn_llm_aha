"""Pure-source controls for canonical fullblock observer loading and long budget.

Executes pinned stdlib-only module top levels and their source identity checks.
No DUT import/constructor, factory, native, child, payload, or model execution.
A tiny temporary canonical source fixture is not an assembled fullblock run.
"""
import argparse
import ast
import builtins
import copy
import hashlib
import importlib
import importlib.machinery
import inspect
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import tempfile
import threading
import time
import types
from array import array
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, fields, is_dataclass
import dis
import struct
from abc import ABCMeta

HERE = Path(__file__).resolve().parent
RESULTS = []

def need(ok, text):
    if not ok:
        raise AssertionError(text)

def pin(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def load(path, raw, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module

def accepted(name, call):
    result = call()
    RESULTS.append(dict(name=name, status='PASS'))
    return result

def rejected(name, call, expected=ValueError):
    try:
        call()
    except expected as exc:
        RESULTS.append(dict(name=name, status='PASS_REJECTED', error=type(exc).__name__))
        return
    raise AssertionError('accepted negative: ' + name)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-pins', type=Path, required=True)
    parser.add_argument('--owned', type=Path, required=True)
    args = parser.parse_args()
    need(sys.version_info[:3] == (3, 12, 14), 'exact target CPython 3.12.14')
    need(args.owned.is_absolute() and args.owned.resolve() == args.owned and not args.owned.exists(), 'fresh owned fixture')
    source = json.loads(args.input_pins.read_bytes())
    payloads = {}
    for key, item in source['files'].items():
        path = Path(item['path'])
        need(path.is_absolute() and path.resolve() == path and path.is_file() and path.stat().st_nlink == 1, 'exact small source')
        need(path.stat().st_size <= 1000000, 'small source cap')
        raw = path.read_bytes()
        need(pin(raw) == {k: item[k] for k in ('bytes', 'sha256')}, 'source pin ' + key)
        payloads[key] = raw
    args.owned.mkdir()
    fixture = args.owned / 'fixture'
    fixture.mkdir()
    fixture_keys = ('fullblock_runtime.py', 'capture/wholeblock.py', 'capture/anchors.json',
        'capture/CODEC_PINS.json', 'observation/__init__.py', 'observation/source_guard.py',
        'observation/event_stream.py', 'observation/fullblock_attention.py',
        'contract/FRAME_ROUTING_POLICY.json', 'supervision/gate.py',
        'supervision/ci_support_v3_long.py', 'supervision/SUPPORT_PINS.json')
    for key in fixture_keys:
        path = fixture / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payloads[key])
    for key, raw in payloads.items():
        if key.startswith('support/'):
            path = fixture/key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    # Deliberately present an unpinned bytecode neighbour. Raw loaders must not read it.
    pycache = fixture / 'observation/__pycache__'
    pycache.mkdir()
    (pycache / 'fullblock_attention.cpython-312.pyc').write_bytes(b'UNTRUSTED BYTECODE MUST NOT BE READ')
    prep = {key: pin(payloads[key]) for key in fixture_keys}
    binding = dict(path='contract/FRAME_ROUTING_POLICY.json', policy_id='source-attested-owner-frame-routing-v1', **prep['contract/FRAME_ROUTING_POLICY.json'])
    manifest = dict(preparation_files=prep, observation_integrity_policy=binding)
    declaration = dict(files=copy.deepcopy(prep), observation_integrity_policy=copy.deepcopy(binding))
    (fixture/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
    audit_state = dict(denied=[], pyc_reads=[], writes=[])
    def audit(event, values):
        denied = event.startswith(('ctypes.', 'subprocess.', 'socket.', 'os.exec', 'os.spawn')) or event in ('os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn')
        if event == 'import' and values[0].split('.')[0] in ('candidates', 'numpy', 'ctypes', 'torch'):
            denied = True
        if event == 'open':
            path, mode, flags = values
            writing = (type(mode) is str and any(c in mode for c in 'wax+')) or (type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            if type(path) in (str, bytes):
                p = Path(os.fsdecode(path))
                if not writing and p.suffix == '.pyc' and fixture in p.parents:
                    audit_state['pyc_reads'].append(str(p.relative_to(fixture))); denied = True
                if writing:
                    audit_state['writes'].append(str(p))
                    denied = denied or not (p.is_absolute() and (p == args.owned or args.owned in p.parents))
        if denied:
            audit_state['denied'].append(event)
            raise RuntimeError('source-only denied: ' + event)
    sys.addaudithook(audit)
    start = time.monotonic()
    F = load(fixture / 'fullblock_runtime.py', payloads['fullblock_runtime.py'], '_source_control_factory')
    accepted('strict full routing policy', lambda: F.validate_observation_integrity_policy(manifest, declaration))
    for name, mutate in (
        ('missing policy', lambda x: x.pop('observation_integrity_policy')),
        ('old op policy id', lambda x: x['observation_integrity_policy'].__setitem__('policy_id', 'op-evidence-boundary-v1')),
        ('mixed observer pin', lambda x: x['preparation_files']['capture/wholeblock.py'].__setitem__('sha256', '0'*64)),
        ('bool byte count', lambda x: x['observation_integrity_policy'].__setitem__('bytes', True)),
    ):
        broken = copy.deepcopy(manifest); mutate(broken)
        rejected(name, lambda broken=broken: F.validate_observation_integrity_policy(broken, declaration))
    polluted = load(fixture / 'fullblock_runtime.py', payloads['fullblock_runtime.py'], '_source_polluted_factory')
    sys.modules['capture'] = types.ModuleType('capture')
    try:
        rejected('preloaded namespace rejected', lambda: polluted.initialize_observers(manifest, declaration))
    finally:
        sys.modules.pop('capture')
    accepted('actual raw top-level installation', lambda: F.initialize_observers(manifest, declaration))
    accepted('full loaded source verification', lambda: F._check_loaded_observers(declaration, manifest))
    rejected('once loader consumed', lambda: F.initialize_observers(manifest, declaration))
    W = sys.modules['capture.wholeblock']; A = sys.modules['observation.fullblock_attention']
    need(W.__file__ == str(fixture/'capture/wholeblock.py') and A.__file__ == str(fixture/'observation/fullblock_attention.py'), 'canonical real paths')
    count = sum(len(item['functions']) for item in F._OBSERVER_BINDING['inspected'].values())
    need(count >= 70, 'all original and new source functions inspected')
    check = lambda: F._check_loaded_observers(declaration, manifest)
    def mutation(name, apply, restore):
        apply()
        try:
            rejected(name, check)
        finally:
            restore()
    old = W.TraceDispatcher._dispatch
    mutation('dispatcher method replacement', lambda: setattr(W.TraceDispatcher, '_dispatch', lambda self, frame, event, arg: None), lambda: setattr(W.TraceDispatcher, '_dispatch', old))
    old_code = A.Fixed93FullblockAttentionObservation._trace.__code__
    mutation('Attention trace CodeType replacement', lambda: setattr(A.Fixed93FullblockAttentionObservation._trace, '__code__', (lambda self, frame, event, arg: None).__code__), lambda: setattr(A.Fixed93FullblockAttentionObservation._trace, '__code__', old_code))
    old_kw = W.TraceDispatcher.__init__.__kwdefaults__
    mutation('dispatcher keyword defaults', lambda: setattr(W.TraceDispatcher.__init__, '__kwdefaults__', dict(old_kw, max_exception_frames=63)), lambda: setattr(W.TraceDispatcher.__init__, '__kwdefaults__', old_kw))
    old_defaults = A.Fixed93FullblockAttentionObservation.__init__.__defaults__
    mutation('Attention positional defaults', lambda: setattr(A.Fixed93FullblockAttentionObservation.__init__, '__defaults__', (1,)), lambda: setattr(A.Fixed93FullblockAttentionObservation.__init__, '__defaults__', old_defaults))
    mutation('class member injection', lambda: setattr(W.TraceDispatcher, 'extra_control', True), lambda: delattr(W.TraceDispatcher, 'extra_control'))
    old = A.require
    mutation('direct function global', lambda: setattr(A, 'require', lambda *a: None), lambda: setattr(A, 'require', old))
    old = W.LINE_ANCHORS
    mutation('direct frozenset global', lambda: setattr(W, 'LINE_ANCHORS', frozenset()), lambda: setattr(W, 'LINE_ANCHORS', old))
    old = W.REQUIRED_COUNTS['normal_steps']
    mutation('nested mutable direct global', lambda: W.REQUIRED_COUNTS.__setitem__('normal_steps', old+1), lambda: W.REQUIRED_COUNTS.__setitem__('normal_steps', old))
    old = W.__spec__.origin
    mutation('module spec origin', lambda: setattr(W.__spec__, 'origin', old+'.wrong'), lambda: setattr(W.__spec__, 'origin', old))
    old = sys.modules['capture'].__path__[:]
    mutation('namespace path addition', lambda: sys.modules['capture'].__path__.append(str(fixture/'other')), lambda: sys.modules['capture'].__path__.__setitem__(slice(None), old))
    mutation('sys.modules alias', lambda: sys.modules.__setitem__('_wrong_capture_alias', W), lambda: sys.modules.pop('_wrong_capture_alias'))
    old = sys.modules['capture'].wholeblock
    mutation('namespace parent replacement', lambda: setattr(sys.modules['capture'], 'wholeblock', types.ModuleType('wrong')), lambda: setattr(sys.modules['capture'], 'wholeblock', old))
    old = sys.modules['observation.source_guard'].require.__code__
    mutation('source guard CodeType', lambda: setattr(sys.modules['observation.source_guard'].require, '__code__', (lambda x,y: None).__code__), lambda: setattr(sys.modules['observation.source_guard'].require, '__code__', old))
    accepted('all mutations restored exact', check)
    need(not F._FACTORY_USED, 'no factory-purpose consumed')
    G = load(fixture/'supervision/gate.py', payloads['supervision/gate.py'], '_source_gate')
    accepted('real supervision policy gate', lambda: G.observation_integrity_policy(manifest))
    budget = json.loads(payloads['BUDGET_PROPOSAL.json'])
    accepted('exact 43200 budget', lambda: G.validate_budget(budget))
    limits = G.fixed_limits(budget)
    need(limits['total_seconds'] == 43200 and limits['work_seconds'] == 43185 and limits['sample_rows'] == 43201, 'exact long limits')
    for name, key, value in (('OPEN rejected','status','OPEN'), ('over ceiling','outer_wall_seconds',43201), ('work cleanup reserve','inner_wall_seconds',43186), ('wrong rows','sample_rows',6601), ('bool total','outer_wall_seconds',True)):
        bad=copy.deepcopy(budget); bad[key]=value
        rejected(name, lambda bad=bad: G.validate_budget(bad))
    base_budget=json.loads(payloads['baseline/BUDGET_PROPOSAL.json'])
    need(budget['owned_reservation_components']['other_fixed_files_and_samples'] - base_budget['owned_reservation_components']['other_fixed_files_and_samples'] == (43201-6601)*2048, 'all sample rows preserved')
    need(sum(budget['owned_reservation_components'].values()) == budget['output_bytes'] and budget['output_bytes']+budget['free_space_margin_bytes'] == budget['startup_available_bytes_required'], 'complete owned storage sum')
    accepted('sample storage accounting', lambda: None)
    # Literal-only duration extension, not a changed supervisor implementation.
    need(payloads['supervision/ci_support_v3_long.py'].replace(b'SHARED_SECONDS = 43200', b'SHARED_SECONDS = 6600', 1) == payloads['baseline/ci_support_v3.py'], 'exact one-literal support extension')
    accepted('support duration inverse bytes', lambda: None)
    ci=load(fixture/'supervision/ci_support_v3_long.py',payloads['supervision/ci_support_v3_long.py'],'_source_ci')
    need(ci.remaining_work(100,43300,100,43200,43185)==43285, 'real long work stop')
    rejected('real support over ceiling', lambda:ci.remaining_work(100,43301,100,43201,43186), Exception)
    rejected('real support exhausted wall', lambda:ci.remaining_work(43300,43300,100,43200,43185), Exception)
    accepted('real support long work boundary',lambda:None)
    provenance=dict(support_files={key[len('support/'):]:pin(raw) for key,raw in payloads.items() if key.startswith('support/')})
    projection=accepted('actual full production projection without execution',lambda:G.projection_preflight(budget,provenance))
    need(projection['production_projection_assembled'] and not projection['child_created'], 'projection only')
    builder=load(HERE/'prepare_fullblock.py',payloads['prepare_fullblock.py'],'_source_builder')
    accepted('builder exact budget delta',lambda:builder.validate_successor_budget(base_budget,budget))
    bad=copy.deepcopy(budget);bad['one_cpu']=1
    rejected('builder bool/int strictness',lambda:builder.validate_successor_budget(base_budget,bad))
    bad=copy.deepcopy(budget);bad['attention_trace_limits']['codec_limits']['max_raw']-=1
    rejected('builder no stream cap reduction',lambda:builder.validate_successor_budget(base_budget,bad))
    # Check the real runner remains exactly the old full producer→KV→attention→tail body.
    def tree(raw): return ast.parse(raw)
    old_tree=tree(payloads['baseline/integration/runner.py']); new_tree=tree(payloads['integration/runner.py'])
    removed=0
    for node in ast.walk(new_tree):
        if isinstance(node,ast.Call):
            before=len(node.keywords)
            node.keywords=[k for k in node.keywords if k.arg!='observation_integrity_policy']
            removed+=before-len(node.keywords)
    need(removed==1 and ast.dump(old_tree)==ast.dump(new_tree), 'full runner only report binding delta')
    accepted('full runner reverse AST',lambda:None)
    base_attention=tree(payloads['baseline/observation/fullblock_attention.py'])
    new_attention=tree(payloads['observation/fullblock_attention.py'])
    find=lambda tr,name:next(n for n in ast.walk(tr) if isinstance(n,ast.FunctionDef) and n.name==name)
    for name in ('native_snapshot','_identity'):
        need(ast.dump(find(base_attention,name))==ast.dump(find(new_attention,name)), 'original ABI/identity remains '+name)
    accepted('original native ABI and identity AST',lambda:None)
    need(not audit_state['pyc_reads'] and not audit_state['denied'] and not audit_state['writes'], 'no unexpected audit activity')
    print(json.dumps(dict(status='PASS_PURE_SOURCE_LOADER_BUDGET_CONTROLS_ONLY',python=sys.version,controls=len(RESULTS),results=RESULTS,elapsed_seconds=time.monotonic()-start,projection=projection,checked_observer_functions=count,canonical_modules=list(F._OBSERVER_BINDING['modules']),factory_used=F._FACTORY_USED,audit=audit_state,native_or_dut_imported=False,actual_authorized=False,fullblock_executed=False),sort_keys=True))

if __name__=='__main__':
    main()
