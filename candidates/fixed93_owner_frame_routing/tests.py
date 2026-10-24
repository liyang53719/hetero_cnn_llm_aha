"""Source/synthetic only; no DUT imports, native calls, inputs or stream reads.

Exact compiled TraceDispatcher and WholeblockObservation methods execute against
synthetic Python owners. Attention is an explicitly MOCK callback/field sink;
AST checks prove every production Attention helper is unchanged. This is not
M2, full-domain, numeric, performance or admission evidence.
"""
import argparse
import ast
import copy
import hashlib
import json
import statistics
import sys
import threading
import time
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GROUPS = {
    '_attention': ('qk_check', 'qk_pass', 'score', 'exp', 'output'),
    '_matrix_step': ('matrix_input_fp32', 'matrix_input', 'pv_check', 'pv_pass'),
    'tick': ('memory_accept', 'memory_match', 'write_ack'),
    '_write': ('store_check', 'store_pass'),
}
SUPPORT = frozenset(('owner_attention', 'owner_matrix_step', 'owner_write',
                     'owner_tick', 'scalar_op', 'exp_negative', 'jsonable'))
S = types.SimpleNamespace
DENIED = Counter()
PINS = {}


def need(value, message):
    if not value:
        raise ValueError(message)


def audit(event, args):
    blocked = event.startswith(('subprocess.', 'ctypes.', 'socket.')) or event in (
        'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.fork', 'os.forkpty', 'pty.spawn')
    if event == 'import':
        blocked = blocked or args[0].split('.')[0] in (
            'ctypes', '_ctypes', 'socket', '_socket', 'urllib', 'http', 'requests', 'candidates')
    if blocked:
        DENIED[event] += 1
        raise RuntimeError('source/synthetic audit denied ' + event)


def code_tree(code):
    yield code
    for child in code.co_consts:
        if type(child) is types.CodeType:
            yield from code_tree(child)


def source(path):
    raw = path.read_bytes()
    expected = PINS[path.resolve()]
    need(len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'],
         'source size/SHA pin mismatch before compile: ' + path.name)
    text = raw.decode('utf-8')
    return text, {c.co_qualname: c for c in code_tree(compile(text, str(path), 'exec'))}, hashlib.sha256(raw).hexdigest()


def extract(pool, name, glob):
    return types.FunctionType(pool[name], glob)


def classes(tree):
    return {x.name: x for x in tree.body if isinstance(x, ast.ClassDef)}


def methods(node):
    return {x.name: x for x in node.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))}


def source_proof(old_a, new_a, old_w, new_w):
    oa, na = ast.parse(old_a), ast.parse(new_a)
    om = methods(classes(oa)['Fixed93FullblockAttentionObservation'])
    nm = methods(classes(na)['Fixed93FullblockAttentionObservation'])
    need(om.keys() == nm.keys(), 'Attention method set changed')
    changed = {name for name in om if ast.dump(om[name]) != ast.dump(nm[name])}
    need(changed == {'__enter__'}, 'unexpected Attention helpers changed')
    body = nm['__enter__']
    calls = [n for n in ast.walk(body) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'bind_owner_line_routes']
    need(len(calls) == 1, 'exact one explicit route bind')
    for parent in ast.walk(body):
        for _, value in ast.iter_fields(parent):
            if isinstance(value, list) and calls[0] in value:
                pos = value.index(calls[0])
                need(pos > 0 and 'dispatcher.register' in ast.unparse(value[pos - 1]), 'bind must immediately follow register')
                value.remove(calls[0])
                break
    need(ast.dump(oa) == ast.dump(na), 'Attention reverse whole-module AST proof')
    for name in om.keys() - changed:
        need(ast.get_source_segment(old_a, om[name]) == ast.get_source_segment(new_a, nm[name]),
             'Attention helper byte drift: ' + name)
    ow, nw = ast.parse(old_w), ast.parse(new_w)
    oc, nc = classes(ow), classes(nw)
    need(ast.dump(oc['WholeblockObservation']) == ast.dump(nc['WholeblockObservation']), 'Whole observer changed')
    need(ast.get_source_segment(old_w, oc['WholeblockObservation']) ==
         ast.get_source_segment(new_w, nc['WholeblockObservation']), 'Whole observer byte drift')
    od, nd = methods(oc['TraceDispatcher']), methods(nc['TraceDispatcher'])
    restored = copy.deepcopy(nd['_dispatch_code'])
    restored.name = '_dispatch'
    need(restored.args.args[-1].arg == 'code', 'factored dispatch code parameter')
    restored.args.args.pop()
    restored.body.insert(0, copy.deepcopy(od['_dispatch'].body[0]))
    need(ast.dump(restored) == ast.dump(od['_dispatch']), 'original dispatch body changed')
    for name in ('start', 'stop', 'bind_scalar'):
        need(ast.get_source_segment(old_w, od[name]) == ast.get_source_segment(new_w, nd[name]),
             'dispatcher unchanged helper: ' + name)
    ow.body.remove(oc['TraceDispatcher']); nw.body.remove(nc['TraceDispatcher'])
    need(ast.dump(ow) == ast.dump(nw), 'non-dispatcher whole module changed')
    return {'attention_changed': ['__enter__'], 'attention_unchanged_helpers': len(om) - 1,
            'whole_observer_byte_identical': True, 'original_dispatch_body_ast_identical': True}


OWNER_SOURCE = '''
def _matrix_step(self):
    original = self
    value = 17
    PROBE(self, sys._getframe(), 'matrix_entry')
    if self.mode in ('owner_transient', 'owner_persistent'):
        self = object()
        value += 1
        if original.mode == 'owner_transient':
            self = original
    ACTION(original, 'before_drift')
    value += 2
    ACTION(original, 'after_drift')
    hook_matrix_input_fp32 = value
    value += 3
    hook_matrix_input = value
    value += 4
    hook_pv_check = value
    value += 5
    hook_pv_pass = value
    PROBE(original, sys._getframe(), 'matrix_exit')
    return value

def _write(self):
    value = 31
    PROBE(self, sys._getframe(), 'write_entry')
    hook_store_check = value
    value += 6
    hook_store_pass = value
    return value

def _attention(self):
    value = 41
    PROBE(self, sys._getframe(), 'attention_entry')
    hook_qk_check = value
    value += 1
    hook_qk_pass = value
    if self.mode == 'handled_throw':
        try:
            yield 3
        except ValueError:
            resume_after_throw = 71
            PROBE(self, sys._getframe(), 'after_throw')
    elif self.mode == 'close':
        try:
            yield 4
        finally:
            resume_after_close = 72
            PROBE(self, sys._getframe(), 'after_close')
    elif self.mode == 'yield':
        yield 5
        resumed_normally = 73
        PROBE(self, sys._getframe(), 'after_yield')
    elif self.mode == 'handled':
        try:
            raise ValueError('MOCK handled')
        except ValueError:
            resume_after_exception = 74
    value += 2
    hook_score = value
    value += self._matrix_step()
    hook_exp = value
    value += self._write()
    hook_output = value
    PROBE(self, sys._getframe(), 'attention_exit')
    yield value
    return 19

def tick(self):
    value = 0
    PROBE(self, sys._getframe(), 'tick_entry')
    hook_memory_accept = value
    generator = self._attention()
    if self.mode == 'handled_throw':
        value += next(generator)
        PROBE(self, generator.gi_frame, 'yielded')
        value += generator.throw(ValueError('MOCK injected'))
        PROBE(self, generator.gi_frame, 'yielded_again')
        try:
            next(generator)
        except StopIteration:
            after_exhaustion = 1
    elif self.mode == 'close':
        value += next(generator)
        PROBE(self, generator.gi_frame, 'yielded')
        generator.close()
    else:
        for returned in generator:
            value += returned
            PROBE(self, generator.gi_frame, 'yielded')
    hook_memory_match = value
    if self.mode in ('public_handled', 'public_throw'):
        self.public(self.mode)
    if self.mode == 'silu':
        self.silu_execute(self.silu, self.coupled)
    for index in range(self.loops):
        value += index & 3
        value ^= index & 1
    hook_write_ack = value
    PROBE(self, sys._getframe(), 'tick_exit')
    return value

def public(self, mode):
    if mode == 'public_throw':
        raise ValueError('MOCK uncaught public')
    try:
        raise ValueError('MOCK handled public')
    except ValueError:
        first_resume_line = 81
    return {'result_fire': True, 'value': 83}
'''
OWNER_CODES = {c.co_name: c for c in code_tree(compile(OWNER_SOURCE, '<SYNTHETIC_OWNER>', 'exec'))}
SILU_SOURCE = '\n' * 392 + 'def silu_execute(self, lib, h):\n    value = 89\n    value += 1\n    hook_silu = value\n    return value\n'
SILU_CODE = next(c for c in code_tree(compile(SILU_SOURCE, '<SYNTHETIC_SILU>', 'exec')) if c.co_name == 'silu_execute')
OWNER_CODES['silu_execute'] = SILU_CODE
HOOK_LINES = {}
for node in ast.walk(ast.parse(OWNER_SOURCE)):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith('hook_'):
                HOOK_LINES[target.id[5:]] = node.lineno
need(set(HOOK_LINES) == {label for labels in GROUPS.values() for label in labels}, 'synthetic hook inventory')
LINES = types.MappingProxyType({OWNER_CODES[name]: frozenset(HOOK_LINES[x] for x in labels)
                               for name, labels in GROUPS.items()})
LABELS = {line: label for label, line in HOOK_LINES.items()}
ALL = frozenset(OWNER_CODES[name] for name in (*GROUPS, 'public', 'silu_execute'))
UNKNOWN = next(c for c in code_tree(compile('def _attention(self): return 97', '<UNKNOWN_SAME_NAME>', 'exec')) if c.co_name == '_attention')


def normalized(arg):
    if type(arg) in (int, str, bool, type(None)):
        return arg
    if type(arg) is dict:
        return tuple(sorted((k, normalized(v)) for k, v in arg.items()))
    if isinstance(arg, tuple) and len(arg) == 3 and isinstance(arg[0], type) and issubclass(arg[0], BaseException):
        return (arg[0].__name__, str(arg[1]))
    if type(arg) in (tuple, list):
        return tuple(normalized(v) for v in arg)
    return type(arg).__name__


class ObservedCodes(dict):
    # Test-only read instrumentation. The exact original _observe executes
    # unchanged. No wrapper replaces its bound callback, and no frame is saved.
    def __init__(self, values, sink):
        super().__init__(values)
        self.sink = sink
        self.enabled = True

    def __getitem__(self, key):
        if self.enabled:
            caller = sys._getframe(1)
            local = caller.f_locals
            frame = local['frame']
            self.sink.append((frame.f_code.co_name, local['event'], frame.f_lineno))
        return super().__getitem__(key)


class MockAttention:
    """MOCK identity/records only. Not production _trace/_line/_identity execution."""
    def __init__(self, owner):
        self.owner = owner
        self.codes = {name: OWNER_CODES[name] for name in GROUPS}
        self.all_codes = ALL
        self.evidence_lines = LINES
        self.thread = threading.get_ident()
        self.identity_tick_frame = None
        self.error = None
        self.disarmed = False
        self.stream = S(failed=False)
        self._callback = self._trace
        self.deliveries = []
        self.controls = []
        self.fields = []
        self.call_routes = []
        self.raise_on_call = False

    def _trace(self, frame, event, arg):
        code = frame.f_code
        self.deliveries.append((code.co_name, event, frame.f_lineno))
        if event != 'line':
            self.controls.append((code.co_name, event, normalized(arg)))
        if self.raise_on_call and event == 'call':
            raise ValueError('MOCK listener call error')
        closing = code is self.codes['tick'] and event == 'return' and self.identity_tick_frame == id(frame)
        try:
            if code in self.evidence_lines:
                need(threading.get_ident() == self.thread, 'MOCK observation thread changed')
                need(frame.f_locals.get('self') is self.owner, 'MOCK wrong owner instance')
                if code is self.codes['tick'] and event == 'call':
                    need(self.identity_tick_frame is None, 'MOCK nested tick')
                    self.identity_tick_frame = id(frame)
                elif self.identity_tick_frame is not None:
                    cursor = frame
                    for _ in range(128):
                        if cursor is None or id(cursor) == self.identity_tick_frame:
                            break
                        cursor = cursor.f_back
                    need(cursor is not None and id(cursor) == self.identity_tick_frame, 'MOCK wrong active tick ancestry')
                if event == 'line' and frame.f_lineno in self.evidence_lines[code]:
                    self.fields.append((LABELS[frame.f_lineno], frame.f_locals.get('value')))
        except Exception as error:
            self.error = self.error or str(error)
        finally:
            if closing:
                self.identity_tick_frame = None
        return self._callback


class Fixture:
    def __init__(self, pool, routed, mode='normal', loops=0, probe=None, action=None):
        self.routed = routed
        self.profiled = []
        self.routes = []
        self.probe_action = probe
        self.action_action = action
        self.values = []
        self.caught = None
        glob = {'sys': sys, 'PROBE': self.probe, 'ACTION': self.action}
        owner_type = type('SyntheticOwner', (), {name: types.FunctionType(OWNER_CODES[name], glob)
                                               for name in (*GROUPS, 'public', 'silu_execute')})
        self.owner = owner_type()
        self.owner.mode, self.owner.loops = mode, loops
        self.owner.silu, self.owner.coupled = object(), object()
        self.a = MockAttention(self.owner)
        glob_w = {'need': need, 'types': types, 'sys': sys, 'threading': threading,
                  'CaptureError': ValueError, 'SUPPORT_ANCHORS': SUPPORT}
        wnames = ('_observe', '_belongs')
        W = type('WholeblockObservation', (), {name: extract(pool, 'WholeblockObservation.' + name, glob_w)
                                             for name in wnames})
        glob_w['WholeblockObservation'] = W
        names = [name.split('.', 1)[1] for name in pool if name.startswith('TraceDispatcher.') and name.count('.') == 1]
        D = type('TraceDispatcher', (), {name: extract(pool, 'TraceDispatcher.' + name, glob_w) for name in names})
        self.w = W()
        self.w.by_code = ObservedCodes({OWNER_CODES[name]: 'owner_' + name.strip('_') for name in GROUPS}, self.profiled)
        self.w.by_code.update({OWNER_CODES['public']: 'public_MOCK', SILU_CODE: 'silu_execute'})
        self.w.objects = {'x': self.owner, 'silu': self.owner.silu}
        self.w.limits = {'max_exception_frames': 32}
        self.w._exceptions = set()
        self.w.failure = None
        self.w.records = []
        self.w.silu = []
        self.w._event = lambda key, frame, values: self.w.records.append((key, normalized(values)))
        self.w._poison = lambda value: setattr(self.w, 'failure', self.w.failure or value)
        self.w._capture_silu = lambda frame, local: self.w.silu.append((frame.f_lineno, local['value']))
        self.d = D(ALL, max_listeners=4, on_error=self.w._poison,
                   line_codes=tuple(LINES) + (SILU_CODE,), scalar_code=None, exp_code=None, max_exception_frames=32)
        self.w.trace_dispatcher = self.d
        self.a.dispatcher = self.d
        self.wtoken = self.d.register(self.w._observe, self.w.by_code)
        self.wcode = pool['WholeblockObservation._observe']

    def open(self, bind=True, profiling=True):
        self.d.start()
        self.a.registration = self.d.register(self.a._callback, self.a.all_codes)
        if self.routed and bind:
            self.d.bind_owner_line_routes(self.a)
        self.w.by_code.enabled = profiling
        return self

    def close(self):
        self.d.stop()
        need(sys.gettrace() is None and sys.getprofile() is None, 'trace/profile not restored')

    def probe(self, owner, frame, location):
        route = None if frame is None else frame.f_trace
        self.routes.append((location, route, None if frame is None else id(frame)))
        if self.probe_action is not None:
            self.probe_action(self, frame, location)

    def action(self, owner, location):
        if self.action_action is not None:
            self.action_action(self, location)

    def run(self, iterations=1, profiling=True):
        self.open(profiling=profiling)
        try:
            try:
                for _ in range(iterations):
                    self.values.append(self.owner.tick())
            except ValueError as error:
                self.caught = str(error)
        finally:
            self.close()
        need(not self.d._resume_lines and not self.w._exceptions, 'exception bookkeeping leaked')
        need(self.a.identity_tick_frame is None, 'MOCK tick scope leaked')
        return self

    def evidence(self):
        return {'controls': self.a.controls, 'fields': self.a.fields, 'whole_records': self.w.records,
                'silu': self.w.silu, 'values': self.values, 'caught': self.caught,
                'attention_error': self.a.error, 'whole_failure': self.w.failure, 'dispatcher_failure': self.d.failed}


def real_differentials(old, new):
    results = []
    for mode in ('normal', 'yield', 'handled_throw', 'close', 'handled', 'public_handled', 'public_throw', 'silu'):
        x = Fixture(old, False, mode).run()
        y = Fixture(new, True, mode).run()
        need(x.evidence() == y.evidence(), 'real trace evidence mismatch ' + mode)
        for source_deliveries, name in ((x.a.deliveries, 'attention'), (x.profiled, 'whole')):
            target = y.a.deliveries if name == 'attention' else y.profiled
            need([e for e in source_deliveries if e[1] != 'line'] == [e for e in target if e[1] != 'line'],
                 'control delivery reduction ' + mode + ' ' + name)
            for idx, entry in enumerate(source_deliveries[:-1]):
                if entry[1] == 'exception':
                    following = next((r for r in source_deliveries[idx + 1:] if r[0] == entry[0]), None)
                    if following and following[1] == 'line':
                        need(following in target, 'first post-exception line dropped ' + mode + ' ' + name)
        need(y.profiled == y.a.deliveries, 'exact Whole SUPPORT listener delivery disagrees with MOCK Attention')
        if mode == 'normal':
            need({label for label, _ in y.a.fields} == set(HOOK_LINES) and len(y.a.fields) == 14, 'fourteen hooks lost/duplicated')
            need(len(y.a.deliveries) < len(x.a.deliveries), 'eligible nonhook lines not skipped')
        results.append({'mode': mode, 'controls_each': len(y.a.controls), 'hooks_each': len(y.a.fields),
                        'baseline_listener_calls': len(x.a.deliveries), 'routed_listener_calls': len(y.a.deliveries)})
    return results


def closure_cells(route, expected_frame):
    todo, seen, names = [route], set(), []
    while todo:
        fn = todo.pop()
        if type(fn) is not types.FunctionType or id(fn) in seen:
            continue
        seen.add(id(fn))
        for name, cell in zip(fn.__code__.co_freevars, fn.__closure__ or ()):
            value = cell.cell_contents
            names.append(name)
            need(type(value) is not types.FrameType and value is not expected_frame, 'closure directly captures frame')
            need(value is not expected_frame.f_locals, 'closure directly captures locals')
            need(name not in ('frame', 'current', 'arg'), 'closure retains frame parameter')
            if type(value) is types.FunctionType:
                todo.append(value)
    need('frame_id' in names and 'code' in names and 'tick_id' in names, 'expected readonly closure identities absent')
    return sorted(set(names))


def closure_lifecycle(new):
    checks = []
    saved = {}
    def probe(fx, frame, where):
        if where == 'attention_entry':
            need(frame.f_trace is not fx.d.callback, 'eligible actual owner call did not bind')
            saved['entry'] = frame.f_trace
            saved['cells'] = closure_cells(frame.f_trace, frame)
        elif where == 'yielded':
            # Keep this negative probe separate from the positive resume path.
            # A suspended generator has no live tick ancestry; calling the
            # original listener here would intentionally poison the MOCK sink.
            route = frame.f_trace
            saved.setdefault('expired', []).append(route)
            saved.setdefault('expired_pairs', []).append((frame, route))
        elif where == 'after_yield':
            need(frame.f_trace is not saved['entry'] and frame.f_trace not in saved['expired'], 'resume reused expired closure')
            checks.append('fresh_generator_resume_closure')
        elif where == 'matrix_exit':
            # The fixture retains this frame solely to probe post-return expiry,
            # then releases it below. Production closures must not retain it.
            saved['returned_frame'], saved['returned_route'] = frame, frame.f_trace
    fx = Fixture(new, True, 'yield', probe=probe).run()
    need(fx.caught is None, 'positive closure lifecycle failed: ' + str(fx.caught))
    for expired_frame, expired_route in saved.pop('expired_pairs'):
        before = len(fx.a.deliveries)
        result = expired_route(expired_frame, 'line', None)
        need(result is fx.d.callback and len(fx.a.deliveries) == before + 1,
             'yielded closure still bypasses original after completed tick')
    del expired_frame, expired_route
    frame, route = saved.pop('returned_frame'), saved.pop('returned_route')
    need(route is not fx.d.callback, 'matrix route never created')
    before = len(fx.a.deliveries)
    need(route(frame, 'line', None) is fx.d.callback, 'normal-return closure not expired')
    need(len(fx.a.deliveries) == before + 1, 'expired normal-return closure did not use original')
    del frame, route
    checks += ['yield_closure_expired', 'normal_return_closure_expired', 'no_captured_frame_or_locals']
    return {'checks': checks, 'closure_cell_names': saved['cells']}


def fallback_cases(new):
    results = []
    for kind in ('tuple_replacement', 'callback_replacement', 'registry_replacement', 'extra_listener',
                 'register_unregister', 'evidence_map_replacement', 'whole_code_change', 'attention_error',
                 'whole_failure', 'disarmed', 'stream_failed', 'wrong_frame', 'unknown_frame', 'unknown_event'):
        observed = {}
        def probe(fx, frame, where):
            if where != 'matrix_entry':
                return
            d, a = fx.d, fx.a
            route = frame.f_trace
            need(route is not d.callback, 'fallback fixture not routed ' + kind)
            before = len(a.deliveries)
            generation = d._listener_generation
            if kind == 'tuple_replacement':
                old_entry = d._listeners[a.registration]
                d._listeners[a.registration] = tuple([old_entry[0], old_entry[1]])
                need(d._listeners[a.registration] is not old_entry and d._listener_generation == generation,
                     'direct tuple replacement fixture incorrect')
            elif kind == 'callback_replacement':
                def replacement(fr, ev, arg):
                    observed['replacement'] = observed.get('replacement', 0) + 1
                    return a._callback(fr, ev, arg)
                d._listeners[a.registration] = (replacement, a.all_codes)
            elif kind == 'registry_replacement':
                d._listeners = dict(d._listeners)
            elif kind in ('extra_listener', 'register_unregister'):
                token = d.register(lambda fr, ev, arg: observed.setdefault('extra', []).append(ev), a.all_codes)
                need(d._listener_generation == generation + 1, 'register generation did not change')
                if kind == 'register_unregister':
                    d.unregister(token)
                    need(d._listener_generation == generation + 2, 'unregister generation did not change')
            elif kind == 'evidence_map_replacement':
                a.evidence_lines = types.MappingProxyType(dict(a.evidence_lines))
            elif kind == 'whole_code_change':
                fx.w.by_code[frame.f_code] = 'public_MOCK'
            elif kind == 'attention_error':
                a.error = 'MOCK sticky error'
            elif kind == 'whole_failure':
                fx.w.failure = 'MOCK sticky whole failure'
            elif kind == 'disarmed':
                a.disarmed = True
            elif kind == 'stream_failed':
                a.stream.failed = True
            fake = frame
            event = 'line'
            if kind in ('wrong_frame', 'unknown_frame'):
                fake = S(f_code=frame.f_code if kind == 'wrong_frame' else UNKNOWN,
                         f_back=frame.f_back, f_locals={'self': fx.owner, 'value': 17},
                         f_lineno=frame.f_lineno, f_trace_lines=True)
            if kind == 'unknown_event':
                event = 'SYNTHETIC_UNKNOWN_CONTROL'
            returned = route(fake, event, None)
            if kind == 'unknown_frame':
                need(returned is None and len(a.deliveries) == before, 'unknown frame must use original rejection')
            else:
                need(len(a.deliveries) == before + 1, 'fallback failed original delivery ' + kind)
                need(returned is d.callback or kind == 'unknown_event', 'fallback returned local route ' + kind)
            # A closure invalidated by frame/registry/sticky mismatch stays dead,
            # even after directly restoring the registry entry or error flag.
            if kind in ('wrong_frame', 'tuple_replacement', 'attention_error'):
                if kind == 'tuple_replacement':
                    d._listeners[a.registration] = old_entry
                if kind == 'attention_error':
                    a.error = None
                before = len(a.deliveries)
                need(route(frame, 'line', None) is d.callback and len(a.deliveries) == before + 1,
                     'invalidated closure resurrected ' + kind)
            observed['checked'] = True
        fx = Fixture(new, True, probe=probe).run()
        need(observed.get('checked'), 'fallback probe not reached ' + kind)
        need(fx.d.failed is None, 'fallback injected dispatcher failure ' + kind)
        if kind == 'callback_replacement':
            need(observed.get('replacement', 0) > 1, 'replaced callback not honored')
        if kind == 'extra_listener':
            need('line' in observed.get('extra', []), 'added listener lost lines')
        results.append(kind)
    return results


def rejected_binding(new):
    results = []
    for kind in ('mutable_map', 'missing_hook', 'wrong_support', 'wrong_attention_callback',
                 'whole_subclass', 'whole_wrapper', 'aliased_code'):
        fx = Fixture(new, True)
        fx.open(bind=False, profiling=False)
        try:
            d, a, w = fx.d, fx.a, fx.w
            if kind == 'mutable_map':
                a.evidence_lines = dict(a.evidence_lines)
            elif kind == 'missing_hook':
                mapping = dict(a.evidence_lines)
                code = a.codes['_attention']
                mapping[code] = frozenset(sorted(mapping[code])[1:])
                a.evidence_lines = types.MappingProxyType(mapping)
            elif kind == 'wrong_support':
                w.by_code[a.codes['_attention']] = 'silu_execute'
            elif kind == 'wrong_attention_callback':
                d._listeners[a.registration] = (lambda *args: None, a.all_codes)
            elif kind == 'whole_subclass':
                sub = type('NotExactWholeblock', (type(w),), {})()
                sub.__dict__.update(w.__dict__)
                d._listeners[fx.wtoken] = (sub._observe, frozenset(w.by_code))
            elif kind == 'whole_wrapper':
                d._listeners[fx.wtoken] = (lambda *args: w._observe(*args), frozenset(w.by_code))
            elif kind == 'aliased_code':
                a.codes = dict(a.codes)
                a.codes['_write'] = a.codes['_attention']
            try:
                d.bind_owner_line_routes(a)
            except ValueError:
                results.append(kind)
            else:
                raise ValueError('invalid binding accepted: ' + kind)
            need(d._owner_route is None, 'rejected binding partially installed')
        finally:
            fx.close()
    return results



def initial_extra_listener(old, new):
    evidence = []
    totals = []
    for pool, routed in ((old, False), (new, True)):
        fx = Fixture(pool, routed).open(bind=False)
        third = []
        try:
            fx.d.register(lambda frame, event, arg: third.append((frame.f_code.co_name, event, frame.f_lineno)), ALL)
            if routed:
                need(fx.d.bind_owner_line_routes(fx.a) is False and fx.d._owner_route is None,
                     'initial third listener did not decline optimization')
            fx.values.append(fx.owner.tick())
        finally:
            fx.close()
        need(third == fx.a.deliveries == fx.profiled, 'initial third subscriber lost full line delivery')
        evidence.append(fx.evidence())
        totals.append(len(third))
    need(evidence[0] == evidence[1] and totals[0] == totals[1], 'initial-third fallback differential')
    return {'optimization_declined': True, 'original_listener_calls_each': totals[0]}


def routing_guard_failure(new):
    def probe(fx, frame, where):
        if where == 'matrix_entry':
            del fx.a.disarmed
    healthy = Fixture(new, True).run(profiling=False)
    fx = Fixture(new, True, probe=probe).open(profiling=False)
    try:
        result = fx.owner.tick()
    finally:
        fx.close()
    need([result] == healthy.values, 'routing guard failure replaced original return')
    need(fx.d.failed is not None and 'AttributeError' in fx.d.failed and fx.w.failure == fx.d.failed,
         'routing guard failure did not latch bounded poison')
    need(len(fx.d.failed) <= 530, 'routing guard failure text unbounded')
    return {'original_return_preserved': True, 'poison_type': 'AttributeError'}

def synthetic_frame(code, owner, back=None, line=1):
    return S(f_code=code, f_locals={'self': owner, 'value': 0}, f_back=back,
             f_lineno=line, f_trace_lines=True)


def call_before_route(new):
    results = []
    for kind in ('no_tick', 'wrong_owner', 'listener_exception', 'sticky_error', 'wrong_ancestor'):
        fx = Fixture(new, True).open(profiling=False)
        try:
            a, d = fx.a, fx.d
            tick = synthetic_frame(a.codes['tick'], fx.owner)
            if kind != 'no_tick':
                d.callback(tick, 'call', None)
            frame = synthetic_frame(a.codes['_matrix_step'], fx.owner, tick if kind != 'wrong_ancestor' else None)
            if kind == 'wrong_owner':
                frame.f_locals['self'] = object()
            if kind == 'listener_exception':
                a.raise_on_call = True
            if kind == 'sticky_error':
                a.error = 'MOCK sticky before call'
            before = len(a.deliveries)
            returned = d.callback(frame, 'call', None)
            need(len(a.deliveries) == before + 1, 'original call not delivered first ' + kind)
            need(returned is d.callback, 'unsafe call acquired local route ' + kind)
            if kind not in ('no_tick', 'sticky_error'):
                need(a.error is not None or d.failed is not None, 'expected original-call failure missing ' + kind)
            results.append(kind)
        finally:
            fx.close()
    return results


def ownership_sampling(old, new):
    results = []
    for family in ('owner', 'thread'):
        for persistent in (False, True):
            mode = 'owner_' + ('persistent' if persistent else 'transient') if family == 'owner' else 'normal'
            def action(fx, where):
                if family == 'thread':
                    if where == 'before_drift':
                        fx.a.thread = -1
                    elif where == 'after_drift' and not persistent:
                        fx.a.thread = threading.get_ident()
            x = Fixture(old, False, mode, action=action).run()
            y = Fixture(new, True, mode, action=action).run()
            need(x.a.error is not None and bool(y.a.error) == persistent,
                 'declared weak ownership sampling difference missing ' + family + str(persistent))
            need(x.values == y.values and x.a.controls == y.a.controls, 'ownership check changed body/control result')
            results.append({'kind': family, 'persistent': persistent, 'baseline_rejected': True,
                            'routed_rejected': persistent})
    return results


def cpu_loop(old, new):
    samples = []
    # Three balanced alternations, identical synthetic bodies and event records.
    # No wall-clock model estimate and no M2 speed claim are made from this loop.
    for index in range(3):
        pair = {}
        for label, pool, routed in ((('baseline', old, False), ('routed', new, True)) if index % 2 == 0
                                    else (('routed', new, True), ('baseline', old, False))):
            fixture = Fixture(pool, routed, loops=80)
            start = time.process_time_ns()
            fixture.run(iterations=30, profiling=False)
            pair[label] = (time.process_time_ns() - start, fixture)
        need(pair['baseline'][1].evidence() == pair['routed'][1].evidence(), 'CPU loop evidence mismatch')
        samples.append({'baseline_cpu_ns': pair['baseline'][0], 'routed_cpu_ns': pair['routed'][0],
                        'controls_each': len(pair['routed'][1].a.controls),
                        'fieldlike_hook_records_each': len(pair['routed'][1].a.fields)})
    return samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    base = args.baseline.resolve()
    manifest = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_bytes())
    for relative, path, section in (
            ('baseline/cached_wholeblock.py', base / 'cached_wholeblock.py', 'test_inputs'),
            ('baseline/narrow_fullblock_attention.py', base / 'narrow_fullblock_attention.py', 'test_inputs'),
            ('overlay/cached_wholeblock.py', ROOT / 'overlay/cached_wholeblock.py', 'files'),
            ('overlay/narrow_fullblock_attention.py', ROOT / 'overlay/narrow_fullblock_attention.py', 'files')):
        pin = manifest[section][relative]
        need(type(pin) is dict and type(pin.get('sha256')) is str, 'invalid source pin entry')
        size = pin.get('bytes', pin.get('size'))
        need(type(size) is int and size > 0, 'source size pin required')
        PINS[path.resolve()] = {'sha256': pin['sha256'], 'bytes': size}
    sys.addaudithook(audit)
    old_w, old_pool, old_w_hash = source(base / 'cached_wholeblock.py')
    new_w, new_pool, new_w_hash = source(ROOT / 'overlay/cached_wholeblock.py')
    old_a, _, old_a_hash = source(base / 'narrow_fullblock_attention.py')
    new_a, _, new_a_hash = source(ROOT / 'overlay/narrow_fullblock_attention.py')
    proof = source_proof(old_a, new_a, old_w, new_w)
    differential = real_differentials(old_pool, new_pool)
    lifecycle = closure_lifecycle(new_pool)
    fallback = fallback_cases(new_pool)
    bindings = rejected_binding(new_pool)
    initial_extra = initial_extra_listener(old_pool, new_pool)
    guard_failure = routing_guard_failure(new_pool)
    gates = call_before_route(new_pool)
    sampling = ownership_sampling(old_pool, new_pool)
    benchmark = cpu_loop(old_pool, new_pool)
    need(not DENIED and 'ctypes' not in sys.modules and not any(n.startswith('candidates.') for n in sys.modules),
         'forbidden native/model operation')
    print(json.dumps({
        'status': 'PASS_SOURCE_SYNTHETIC_FRAME_ROUTING_ONLY',
        'policy': 'source-attested-owner-frame-routing-v1',
        'source_sha256': {'baseline_whole': old_w_hash, 'candidate_whole': new_w_hash,
                          'baseline_attention': old_a_hash, 'candidate_attention': new_a_hash},
        'source_proof': proof, 'real_trace_differentials': differential,
        'closure_lifecycle': lifecycle, 'fallback_cases': fallback, 'rejected_bindings': bindings,
        'initial_extra_listener_fallback': initial_extra, 'routing_guard_failure': guard_failure,
        'original_call_before_route_gates': gates, 'weak_ownership_sampling': sampling,
        'cpu_loop': benchmark,
        'synthetic_cpu_median_ratio': statistics.median(x['baseline_cpu_ns'] for x in benchmark) /
                                      statistics.median(x['routed_cpu_ns'] for x in benchmark),
        'original_whole_support_method_executed': True,
        'whole_delivery_counter_is_test_only_by_code_dict_subclass': True,
        'attention_listener_is_mock': True, 'fieldlike_records_are_mock_not_production_fields': True,
        'production_attention_helpers_source_preserved_not_runtime_tested_here': True,
        'silu_capture_sink_is_mock': True, 'silu_and_nonline_resume_production_source_unchanged': True,
        'old_per_line_integrity_equivalent': False,
        'actual_authorized': False, 'M2_executed': False, 'all_48_domains_executed': False,
        'model_or_native_imported': False, 'input_reference_or_streams_read': False,
        'forbidden_attempts': dict(DENIED),
    }, sort_keys=True))


if __name__ == '__main__':
    main()
