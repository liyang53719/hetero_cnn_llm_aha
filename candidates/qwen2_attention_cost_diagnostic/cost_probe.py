"""Bounded selective CPython counters, not a profiler or hardware time model.

Clean arms never install this probe. Count arms record only exact source-bound
methods. Inclusive CPU times overlap and include instrumentation overhead;
they must not be added or treated as baseline arithmetic cost.
"""
import hashlib
import importlib.util
from pathlib import Path
import sys
import threading
import time
import types


def need(ok, message):
    if not ok:
        raise ValueError(message)


class Stages:
    def __init__(self):
        self.rows = []
        self.previous = (time.process_time_ns(), time.monotonic_ns())

    def mark(self, stage):
        current = (time.process_time_ns(), time.monotonic_ns())
        self.rows.append(dict(stage=stage, cpu_ns=current[0]-self.previous[0],
                             wall_ns=current[1]-self.previous[1]))
        self.previous = current


def free_function_code(fn, path, pin):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == pin, 'free-function source pin')
    actual = fn.__code__
    expected = [c for c in compile(raw, str(path), 'exec', dont_inherit=True,
                optimize=sys.flags.optimize).co_consts
                if type(c) is types.CodeType and c.co_name == fn.__name__]
    need(actual.co_filename == str(path) and len(expected) == 1 and
         actual == expected[0] and actual.co_linetable == expected[0].co_linetable,
         'free-function complete code identity')
    return actual


def targets(owner, config, bind):
    from candidates.qwen2_resident_matrix.ffn_public import prefix_arithmetic as scalar
    from candidates.qwen2_resident_matrix.production_qk16_model.ordered_work import StrictLaneOps
    root = Path(config['source_root']) / 'candidates/qwen2_resident_matrix'
    specs = (
        ('owner_op', owner._op, 'ffn_attention/attention_owner.py', 'AttentionOwner', '_op'),
        ('scalar_op', owner.scalar.op, 'ffn_public/prefix_arithmetic.py', 'ScalarService', 'op'),
        ('matrix_step', owner._matrix_step, 'ffn_attention/attention_owner.py', 'AttentionOwner', '_matrix_step'),
        ('owner_tick', owner.tick, 'ffn_attention/attention_owner.py', 'AttentionOwner', 'tick'),
        ('owner_advance', owner._advance, 'ffn_attention/attention_owner.py', 'AttentionOwner', '_advance'),
        ('ordered_tick', owner.ordered_adapter.tick, 'production_qk16_model/ordered_work.py', 'OrderedFoldAdapter', 'tick'),
        ('lane_primitive', StrictLaneOps.primitive, 'production_qk16_model/ordered_work.py', 'StrictLaneOps', 'primitive'),
        ('lane_materialize', StrictLaneOps.materialize, 'production_qk16_model/ordered_work.py', 'StrictLaneOps', 'materialize'),
        ('service_accept_step', owner.matrix.accept_step, 'ffn_attention/matrix_service.py', 'MatrixService', 'accept_step'),
    )
    codes = {bind(fn, root/rel, config['files'][str(root/rel)]['sha256'], cls, method, False): role
             for role, fn, rel, cls, method in specs}
    path = root / 'ffn_public/prefix_arithmetic.py'
    codes[free_function_code(scalar.bf, path, config['files'][str(path)]['sha256'])] = 'scalar_bf'
    return codes


def load_reviewed_lease(config):
    """Direct unchanged admitted module reuse; never copy/reimplement its lease."""
    path = Path(config['monitor_lease_source']).resolve(strict=True)
    raw = path.read_bytes()
    pin = config['files'][str(path)]
    need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'],
         'reviewed monitor lease source drift')
    name = '_attention_cost_reviewed_monitor_lease'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    module = sys.modules[name]
    need(Path(module.__file__).resolve() == path, 'reviewed monitor lease origin')
    for name in ('monitoring_enter', 'monitoring_stop', 'capture_error'):
        free_function_code(getattr(module, name), path, pin['sha256'])
    return module


class SelectiveProbe:
    """No wrapping, monkeypatching, arithmetic, mutation of DUT or global profile."""
    EVENTS = ('PY_START', 'PY_RESUME', 'PY_RETURN', 'PY_YIELD')

    def __init__(self, codes, *, lease, max_callbacks=300000):
        self.codes = codes
        self.lease = lease
        self.cleanup_error = None
        self.bound_code_identity = [dict(role=role, filename=code.co_filename, qualname=code.co_qualname, first_line=code.co_firstlineno, code_bytes_sha256=hashlib.sha256(code.co_code).hexdigest()) for code, role in codes.items()]
        self.max_callbacks = max_callbacks
        self.callbacks = 0
        self.rows = {}
        self.active = {}
        self.tool = None
        self.closed = False
        self.error = None
        self.thread = threading.get_ident()

    def __enter__(self):
        try:
            need(sys.getprofile() is None, 'selective probe without global profiler')
            mon = sys.monitoring
            callbacks = tuple((getattr(mon.events, name), callback) for name, callback in
                zip(self.EVENTS, (self._start, self._resume, self._return, self._yield)))
            mask = 0
            for event, callback in callbacks:
                mask |= event
            return self.lease.monitoring_enter(self, 'attention-cost-selective', (2,),
                callbacks, self.codes, mask)
        except BaseException as error:
            self.lease.capture_error(self, error)
            # Same cancellation precedence as reviewed observe_driver: an
            # already-active original error wins over a cleanup error.
            self.stop(original_error=error)
            raise

    def stop(self, *, original_error=None):
        try:
            self.lease.monitoring_stop(self,
                tuple(getattr(sys.monitoring.events, name) for name in self.EVENTS), self.codes)
        except BaseException as error:
            self.lease.capture_error(self, error)
            if self.cleanup_error is None:
                self.cleanup_error = type(error).__name__ + ': ' + str(error)
            self.closed = True
            if isinstance(error, KeyboardInterrupt) and original_error is None:
                raise

    def __exit__(self, kind, value, traceback):
        self.stop(original_error=value)
        return False

    def event(self, code, frame, action):
        try:
            self.callbacks += 1
            need(self.callbacks <= self.max_callbacks and threading.get_ident() == self.thread,
                 'bounded single-thread probe callback contract')
            role = self.codes[code]
            operation = frame.f_locals.get('operation') if role in ('owner_op', 'scalar_op', 'lane_primitive') else None
            key = role + (':' + operation if operation is not None else '')
            row = self.rows.setdefault(key, dict(starts=0, resumes=0, returns=0,
                yields=0, unwinds=0, inclusive_instrumented_cpu_ns=0))
            token = id(frame)
            now = time.process_time_ns()
            if action in ('starts', 'resumes'):
                need(token not in self.active, 'overlapping frame segment')
                self.active[token] = (key, now)
            else:
                old_key, before = self.active.pop(token)
                need(old_key == key, 'operation key changed within frame')
                row['inclusive_instrumented_cpu_ns'] += now - before
            row[action] += 1
        except BaseException as error:
            self.lease.capture_error(self, error)
            self.stop(original_error=error)
            # Instrumentation SystemExit is a sticky measurement failure, not a
            # substitute task exception. An explicit user cancel still escapes.
            if isinstance(error, KeyboardInterrupt):
                raise

    def _start(self, code, offset):
        self.event(code, sys._getframe(1), 'starts')

    def _resume(self, code, offset):
        self.event(code, sys._getframe(1), 'resumes')

    def _return(self, code, offset, value):
        self.event(code, sys._getframe(1), 'returns')

    def _yield(self, code, offset, value):
        self.event(code, sys._getframe(1), 'yields')

    # Exceptional unwind is deliberately not globally monitored. The original
    # exception propagates; incomplete segment state rejects acceptance.
    def seal(self, arm):
        need(self.closed and self.tool is None and self.error is None and not self.active,
             'selective probe failed or incomplete: ' + str(self.error))
        for operation, count in arm['scalar_calls'].items():
            need(self.rows['scalar_op:' + operation]['starts'] == count,
                 'measured scalar calls differ from original counter')
        need(self.rows['scalar_bf']['starts'] == arm['scalar_calls']['bf'], 'actual scalar BF call count')
        need(self.rows['matrix_step']['starts'] == 288, 'M2 original PV generator calls')
        need(self.rows['lane_primitive:add']['starts'] == 576 and
             self.rows['lane_primitive:mul']['starts'] == 36 and
             self.rows['lane_materialize']['starts'] == 72, 'M2 strict lane call separation')
        need(arm['scalar_calls']['bf'] == 19968, 'M2 original Scalar BF count')
        return dict(status='PASS_BOUNDED_SELECTIVE_CALL_COUNTS', rows=self.rows,
            callbacks=self.callbacks, callback_limit=self.max_callbacks, bound_code_identity=self.bound_code_identity,
            reviewed_lease_source=self.lease.__file__, cleanup_error=self.cleanup_error,
            time_semantics='Inclusive instrumented process CPU; overlapping, not additive or baseline native cost',
            native_ctypes_calls_individually_timed=False, sys_profile_used=False)


def compare_four(arms, compare_pair):
    need(len(arms) == 4, 'exactly four arms')
    need([a['count_enabled'] for a in arms] == [False, False, True, True], 'clean then count arms')
    controls = [compare_pair(arms[:2]), compare_pair(arms[2:]),
                compare_pair([arms[0], arms[3]]), compare_pair([arms[2], arms[1]])]
    return dict(status='PASS_FOUR_ARM_OUTPUT_SERVICE_CONTROL_EQUIVALENCE', controls=controls,
        clean_timing_arms=[0, 1], instrumented_arms=[2, 3],
        fixed_order_not_statistical_benchmark=True,
        no_hardware_utilization_or_cycle_inference=True)
