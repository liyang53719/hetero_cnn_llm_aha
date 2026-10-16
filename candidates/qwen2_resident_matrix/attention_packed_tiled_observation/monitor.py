"""Pinned CPython 3.12 packed Attention observation; no execution producer.

Only exact run/_op/tick code gets events. We read live locals and actual return
words. Missing source points, scalar return sequences or successful retirement
reject the capture. No reference, arithmetic call, native load or gate override.
"""
import ast
from dataclasses import asdict
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys
import threading
import types

from .capture import PackedFields, VERSION, require

ROOT = Path(__file__).resolve().parents[3]
PREFIX = 'candidates/qwen2_resident_matrix/attention_packed_tiled_observation/'
SCHEDULE = 'candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py'
OWNER = 'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py'
SCALAR_OWNER = OWNER
POINTS = {
    'dot': "score=o._op('bf',o._op('mul',o._op('bf',total),0x3db504f3))",
    'dot_done': 'if o._less(maxima[h],score):maxima[h]=score',
    'exp': 'weights.append(weight)',
    'inverse': "inverses.append(o._op('div',0x3f800000,total))",
    'prob': "a=tuple(o._op('bf',o._op('mul',panel[h][key%16],inverses[h]))>>16 for h in range(6))+(0,)*10",
    'prob_done': 'b=[]',
    'store': 'yield from o._write(j.dst+(token*1536+(kv*6+h)*128+d)*4,words)',
}


LOADED = (
    'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py',
    'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py',
    'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
    'candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py',
    'candidates/qwen2_resident_matrix/official_bf16/owners.py',
    'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py',
    'candidates/qwen2_resident_matrix/official_bf16/observation.py',
    'candidates/qwen2_resident_matrix/dense_block_reduce/matrix_binding.py',
    'candidates/qwen2_resident_matrix/dense_block_reduce/profile.py',
    'candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py',
    'candidates/qwen2_resident_matrix/attention_packed_owner/client.py',
    'candidates/qwen2_resident_matrix/attention_packed_owner/protocol.py',
    'candidates/qwen2_resident_matrix/attention_packed_owner/hooks.py',
    'scripts/observe_qwen2_attention_model.py',
    PREFIX+'capture.py',PREFIX+'monitor.py',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_check(sources):
    require(type(sources) is dict and 1 <= len(sources) <= 1024, 'frozen source map required')
    pins_path = ROOT / PREFIX / 'pins.json'
    require(sources.get(PREFIX+'pins.json') == digest(pins_path), 'observer pins absent or changed')
    pins = json.loads(pins_path.read_text())
    require(set(pins) == {'schema','runtime','own'} and pins['schema'] == VERSION,
            'packed observer pin schema')
    expected = dict(pins['runtime'], **pins['own'])
    require(all(sources.get(n) == h for n,h in expected.items()), 'packed observer closure mismatch')
    for name, value in sources.items():
        require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts
                and type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'noncanonical frozen source entry')
        path = ROOT / name
        require(path.is_file() and not path.is_symlink() and path.resolve() == ROOT/name and
                Path(name).as_posix() == name and path.stat().st_size <= 2*1024*1024,
                'invalid or oversized frozen source')
        require(digest(path) == value, 'frozen source drift: '+name)
    return pins


def _code(code, name):
    matches = [c for c in code.co_consts if isinstance(c,types.CodeType) and c.co_name == name]
    require(len(matches) == 1, 'ambiguous pinned code: '+name)
    return matches[0]


def code_equal(actual, expected):
    return (actual == expected and actual.co_filename == expected.co_filename and
            actual.co_firstlineno == expected.co_firstlineno and
            actual.co_linetable == expected.co_linetable and
            actual.co_exceptiontable == expected.co_exceptiontable)


def method_code(instance, relative, cls, name):
    path = ROOT / relative
    compiled = compile(path.read_text(), str(path), 'exec', dont_inherit=True, optimize=0)
    expected = _code(_code(compiled,cls),name)
    method = getattr(instance,name)
    require(isinstance(method,types.MethodType) and code_equal(method.__func__.__code__,expected),
            'patched observation target: '+name)
    return method.__func__.__code__


def capture_points(source):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == 'PackedSchedule')
    method = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name == 'run')
    points = {}
    for name, statement in POINTS.items():
        expected = ast.dump(ast.parse(statement).body[0],include_attributes=False)
        matches = [n.lineno for n in ast.walk(method) if isinstance(n,ast.stmt) and
                   ast.dump(n,include_attributes=False) == expected]
        require(len(matches) == 1, 'missing or ambiguous packed observation point: '+name)
        points[name] = matches[0]
    require(len(set(points.values())) == len(points), 'overlapping packed observation lines')
    return points


def loaded_check(owner, pins):
    from ..official_bf16.owners import OfficialAttentionOwner
    from ..dense_block_reduce.matrix_binding import ProfiledMatrixService
    from ..dense_block_reduce.profile import ReductionProfile, QWEN2_QKV_PROFILE
    from ..ffn_public.prefix_arithmetic import ScalarService
    from ..attention_packed_owner.schedule import PackedSchedule
    from ..official_bf16.observation import _verify_module
    from scripts.observe_qwen2_attention_model import verify_loaded_dependencies
    require(type(owner) is OfficialAttentionOwner and type(owner.matrix) is ProfiledMatrixService and
            type(owner.scalar) is ScalarService and (owner.packed_schedule is None or
            (type(owner.packed_schedule) is PackedSchedule and owner.packed_schedule.owner is owner)),
            'exact packed owner/services/schedule required')
    require(type(owner.matrix.profile) is ReductionProfile and owner.matrix.profile == QWEN2_QKV_PROFILE and
            set(vars(owner.matrix.profile)) == set(ReductionProfile.__dataclass_fields__),
            'exact reduction profile required')
    owner.matrix.profile.validate(1536)
    count = verify_loaded_dependencies(owner)
    # The original verifier independently handles these five legacy modules,
    # including builtin exception bases and their exact defaults/imports.
    legacy = set(LOADED[:5])
    for relative in LOADED:
        require(relative in pins['runtime'] or relative in pins['own'], 'missing loaded dependency pin')
        if relative.endswith('.py') and relative not in legacy:
            module = importlib.import_module(relative[:-3].replace('/','.'))
            require(Path(module.__file__).resolve() == ROOT/relative, 'loaded dependency path drift')
            count += _verify_module(module,relative)
    for instance in (owner,owner.matrix,owner.scalar,owner.packed_schedule):
        if instance is None:
            continue
        for name in {n for cls in type(instance).__mro__ for n in vars(cls)}:
            descriptor = inspect.getattr_static(type(instance),name)
            if isinstance(descriptor,types.FunctionType):
                method = getattr(instance,name)
                require(isinstance(method,types.MethodType) and method.__func__ is descriptor,
                        'patched instance method: '+name)
    return count


class PackedAttentionMonitoringObservation:
    def __init__(self, owner, *, source_sha256):
        require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,12) and
                not sys.flags.optimize, 'reviewed CPython 3.12 without -O required')
        self.owner, self.sources = owner, dict(source_sha256)
        self.pins = source_check(self.sources)
        self.checked = loaded_check(owner,self.pins)
        self.services = owner.matrix,owner.scalar,owner.packed_schedule
        from ..attention_packed_owner.schedule import PackedSchedule
        schedule_target = owner.packed_schedule if owner.packed_schedule is not None else PackedSchedule()
        self.codes = dict(run=method_code(schedule_target,SCHEDULE,'PackedSchedule','run'),
                          tick=method_code(owner,OWNER,'AttentionOwner','tick'),
                          op=method_code(owner,SCALAR_OWNER,'AttentionOwner','_op'))
        self.points = capture_points((ROOT/SCHEDULE).read_text())
        # Only the probability tuple's generator, not unrelated packet BF16
        # generators, may provide a probability scalar return.
        matches = [c for c in self.codes['run'].co_consts if isinstance(c,types.CodeType) and
                   c.co_name == '<genexpr>' and c.co_firstlineno == self.points['prob']]
        require(len(matches) == 1, 'ambiguous packed probability generator')
        self.prob_code = matches[0]
        self.thread = threading.get_ident()
        self.tool_id = None
        self.tool_name = 'packed-causal-observation-'+str(id(self))
        self.active = self.closed = self.disarmed = False
        self.started = 0
        self.job = self.terminal = self.retirement = self.error = self.capture = None
        self.fields = {}
        self._registered = {}
        self._configured = {}
        self._line_callback = self._line
        self._return_callback = self._return

    def __enter__(self):
        require(threading.get_ident() == self.thread and not self.active and not self.closed and
                self.started == 0 and sys.gettrace() is None, 'single-use untraced observer required')
        o = self.owner
        require(o.state == 'idle' and not o.poison and o.matrix.owner is None and
                not o.matrix.reset_required and o.scalar.client is None and
                not o.scratch_pending and not o.scratch_leased, 'observe before idle packed launch')
        require(source_check(self.sources) == self.pins and loaded_check(o,self.pins) == self.checked,
                'observer dependency drift before entry')
        monitor = sys.monitoring
        for ident in (3,4):
            if monitor.get_tool(ident) is not None or monitor.get_events(ident) or any(
                    monitor.get_local_events(ident,code) for code in self.codes.values()):
                continue
            try:
                monitor.use_tool_id(ident,self.tool_name)
            except ValueError:
                continue
            self.tool_id = ident
            break
        require(self.tool_id is not None, 'no unused monitoring tool ID')
        try:
            for event,callback in ((monitor.events.LINE,self._line_callback),
                                   (monitor.events.PY_RETURN,self._return_callback)):
                previous = monitor.register_callback(self.tool_id,event,callback)
                if previous is not None:
                    monitor.register_callback(self.tool_id,event,previous)
                    raise ValueError('monitor callback was occupied')
                self._registered[event] = callback
            for name,code in self.codes.items():
                events = monitor.events.LINE if name == 'run' else monitor.events.PY_RETURN
                monitor.set_local_events(self.tool_id,code,events)
                self._configured[code] = events
            self.active = True
            return self
        except Exception:
            self._stop()
            raise

    def _stop(self):
        # Match the original observer's ownership-preserving cleanup contract.
        self.disarmed = True
        monitor,ident = sys.monitoring,self.tool_id
        if ident is None:
            return
        if monitor.get_tool(ident) != self.tool_name:
            self.error = self.error or 'monitor ownership changed'
            self.tool_id = None
            return
        intact = monitor.get_events(ident) == 0
        for code,events in tuple(self._configured.items()):
            if monitor.get_local_events(ident,code) != events:
                intact = False
            else:
                monitor.set_local_events(ident,code,0)
        for event,callback in tuple(self._registered.items()):
            previous = monitor.register_callback(ident,event,None)
            if previous is not callback:
                intact = False
                monitor.register_callback(ident,event,previous)
        if not intact:
            self.error = self.error or 'monitor registration changed'
        if intact:
            monitor.free_tool_id(ident)
        self._configured.clear(); self._registered.clear()
        self.tool_id = None

    def _failed(self, error):
        self.error = self.error or str(error)
        try:
            self._stop()
        except Exception:
            self.error = self.error or 'monitor cleanup failed'

    def _line(self, code, line):
        if code is not self.codes['run']:
            return
        if line not in self.points.values():
            return sys.monitoring.DISABLE
        if not self.active or self.disarmed or self.error is not None:
            return
        try:
            frame = sys._getframe(1)
            require(frame.f_code is code and frame.f_lineno == line, 'monitor LINE frame changed')
            local = frame.f_locals
            if local.get('self') is not self.services[2] or local.get('o') is not self.owner:
                return
            require(threading.get_ident() == self.thread and self.started == 1, 'unowned capture event')
            c = self.capture
            if line == self.points['dot']: c.begin_dot(local)
            elif line == self.points['dot_done']: c.end_dot(local)
            elif line == self.points['exp']: c.exponential(local)
            elif line == self.points['prob']: c.begin_probability(local)
            elif line == self.points['prob_done']: c.end_probability(local)
            elif line == self.points['store']: c.store(local)
        except Exception as error:
            self._failed(error)

    def _return(self, code, offset, value):
        if not self.active or self.disarmed or self.error is not None:
            return
        try:
            frame = sys._getframe(1)
            require(frame.f_code is code, 'monitor RETURN frame changed')
            local = frame.f_locals
            if local.get('self') is not self.owner:
                return
            require(threading.get_ident() == self.thread, 'observer thread changed')
            if code is self.codes['op']:
                caller = frame.f_back
                if caller is None or self.started != 1:
                    return
                operation,a,b = local['operation'],local['a'],local['b']
                if caller.f_code is self.codes['run'] and caller.f_locals.get('self') is self.services[2]:
                    if caller.f_lineno == self.points['dot']:
                        self.capture.dot_return(operation,a,b,value)
                    elif caller.f_lineno == self.points['inverse']:
                        self.capture.inverse_return(caller.f_locals,operation,a,b,value)
                elif caller.f_code is self.prob_code:
                    parent = caller.f_back
                    require(parent is not None and parent.f_code is self.codes['run'] and
                            parent.f_locals.get('self') is self.services[2], 'probability caller changed')
                    self.capture.probability_return(parent.f_locals,caller.f_locals['h'],operation,a,b,value)
            elif code is self.codes['tick'] and type(value) is dict:
                if value['job_fire']:
                    require(self.started == 0 and self.owner.job is not None, 'duplicate launch')
                    from ..attention_packed_owner.schedule import PackedSchedule
                    schedule = self.owner.packed_schedule
                    require(type(schedule) is PackedSchedule and schedule.owner is self.owner and
                            (self.services[2] is None or self.services[2] is schedule),
                            'accepted launch lacks exact packed schedule')
                    require(method_code(schedule,SCHEDULE,'PackedSchedule','run') is self.codes['run'],
                            'accepted packed schedule code changed')
                    self.services = self.services[0],self.services[1],schedule
                    self.job = asdict(self.owner.job)
                    self.capture = PackedFields(self.job['m']); self.fields = self.capture.fields
                    self.started = 1
                if value['response_fire']:
                    require(self.started == 1 and self.terminal is None, 'unowned terminal')
                    o = self.owner
                    self.terminal = asdict(value['response'])
                    self.retirement = dict(state=o.state,poison=o.poison,
                        same_services=(o.matrix is self.services[0] and o.scalar is self.services[1]
                                       and o.packed_schedule is self.services[2]),same_job=asdict(o.job)==self.job,
                        matrix_released=o.matrix.owner is None,matrix_reset_required=o.matrix.reset_required,
                        client_retired=o.matrix_client is None,memory_pending=o.memory_pending,
                        scalar_released=o.scalar.client is None,scratch_pending=o.scratch_pending,
                        scratch_leased=o.scratch_leased,scratch_request=o.scratch_request is not None,
                        scratch_write_tag=o.scratch_write_tag is not None,
                        packed_memory_tag=o.packed_memory_tag is not None)
                    self._stop()
        except Exception as error:
            self._failed(error)

    def __exit__(self, kind, error, traceback):
        try:
            self._stop()
        finally:
            self.active,self.closed = False,True
        if kind is not None: self.error = self.error or 'driver exited with an exception'
        if threading.get_ident() != self.thread or sys.gettrace() is not None:
            self.error = self.error or 'thread or tracer changed'
        try:
            require(source_check(self.sources) == self.pins and loaded_check(self.owner,self.pins) == self.checked,
                    'observer dependency drift after capture')
        except Exception as failure:
            self.error = self.error or str(failure)
            raise
        return False

    def _bytes(self, name, kind='words'):
        require(self.capture is not None, 'capture has no accepted launch')
        return self.capture._bytes(name,kind)

    def report(self):
        require(self.closed and not self.active, 'close observer before report')
        complete = self.error is None and self.started == 1 and self.terminal is not None
        if complete:
            t,r,j = self.terminal,self.retirement,self.job
            complete = (t['status'] is None and t['tag'] == j['tag'] and
                t['write_bytes'] == j['write_bytes'] == j['m']*1536*4 and r['state'] == 'idle' and
                r['same_services'] and r['same_job'] and r['matrix_released'] and r['client_retired'] and
                r['scalar_released'] and not any(r[n] for n in ('poison','matrix_reset_required',
                'memory_pending','scratch_pending','scratch_leased','scratch_request','scratch_write_tag',
                'packed_memory_tag')) and self.capture.coverage())
        return dict(schema=VERSION,status='COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED' if complete else 'INCOMPLETE',
            source_sha256=self.sources,source_version=VERSION,job=self.job,terminal=self.terminal,
            accepted_retirement=self.retirement,observer_error=self.error,
            fields={} if self.capture is None else self.capture.field_summary(),
            packed_multiplicity=dict(causal_field=1,normalizer_per_head_query=1,pv_word=1,
                legacy_probability_repeats=8,legacy_normalizer_repeats='8*(query+1)',synthetic_repeats=0),
            trace_api='CPython sys.monitoring pinned packed run LINE and actual scalar/tick PY_RETURN',
            prior_observation_results_inherited=False,full_29_node_gate=False,
            whole_block_terminal_observed=False,physical_publication_observed=False,hardware_simulation=False,
            future_scores_observed=False,numerical_policy='official-bf16-v1',native_acceptance='NOT_EVALUATED_BY_OBSERVER',
            matrix_binary_provenance_verified_by_observer=False,
            pv_bf16_boundary='actual store words; ACK coverage requires accepted successful owner terminal')

    def save(self, out):
        report = self.report()
        out = Path(out); out.mkdir(parents=True,exist_ok=False)
        for name,field in self.fields.items():
            (out/(name+'.u32le')).write_bytes(self._bytes(name))
            (out/(name+'.presence')).write_bytes(bytes(field['observed']))
            (out/(name+'.count.u16le')).write_bytes(self._bytes(name,'frequency'))
        (out/'summary.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
        return report
