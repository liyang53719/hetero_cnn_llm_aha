"""Passive, source-bound RoPE operand capture. Preparation; not a launcher.

Reads the original _rope frame only after both original BF16 tuple assignments.
Never calls arithmetic, memory providers, original methods, or oracle code.
Normal-runtime constructor has no fixture/source-rewrite bypass. Pure collector
and monitor tests are control evidence only, never actual numerical acceptance.
"""
from array import array
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import threading
from types import CodeType, MappingProxyType

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / 'SOURCE_PINS.json').read_text())
SENTINEL = 0xA5963CC3
ROLE_HEADS = {3: 12, 6: 2}
TARGET_STATEMENT = "xc = tuple(self._op('bf', self._op('mul', a, b)) for a, b in zip(x, cosine))"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_identity(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': digest(raw)}


def child(code, name):
    hits = [item for item in code.co_consts if isinstance(item, CodeType) and item.co_name == name]
    need(len(hits) == 1, 'unique source code identity required: ' + name)
    return hits[0]


def expected_code(path, class_name, method):
    source = Path(path).read_bytes()
    root = compile(source, str(path), 'exec', dont_inherit=True, optimize=sys.flags.optimize)
    return child(child(root, class_name), method)


def binding(method, role, class_name, method_name):
    """Verify an already normally loaded function; never import target code."""
    pin = PINS['sources'][role]
    path = Path(pin['path']).resolve(strict=True)
    need(file_identity(path) == {key: pin[key] for key in ('bytes', 'sha256')}, 'bound source changed: ' + role)
    function = getattr(method, '__func__', None)
    need(function is not None and type(function.__code__) is CodeType, 'ordinary bound method required')
    actual = function.__code__
    need(actual.co_filename == str(path), 'non-normal source filename forbidden')
    expected = expected_code(path, class_name, method_name)
    need(actual == expected and actual.co_firstlineno == expected.co_firstlineno
         and actual.co_linetable == expected.co_linetable, 'loaded complete code differs: ' + method_name)
    module = sys.modules.get(pin['module'])
    need(module is not None and Path(module.__file__).resolve(strict=True) == path,
         'normal registered source module missing')
    need(function.__module__ == pin['module'] and function.__globals__ is module.__dict__,
         'function globals not the normally loaded source module')
    source_class = module.__dict__.get(class_name)
    need(source_class is not None and source_class.__dict__.get(method_name) is function,
         'bound method not owned by original source class')
    return actual


def capture_line():
    pin = PINS['sources']['official_owner']
    tree = ast.parse(Path(pin['path']).read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OfficialPrefixOwner')
    fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_rope')
    pattern = ast.dump(ast.parse(TARGET_STATEMENT).body[0], include_attributes=False)
    hits = [node.lineno for node in ast.walk(fn) if isinstance(node, ast.stmt)
            and ast.dump(node, include_attributes=False) == pattern]
    need(len(hits) == 1, 'missing/ambiguous post-BF16 operand capture line')
    return hits[0]


class OperandData:
    """Integer-word/presence collector. Does not certify producer provenance."""
    def __init__(self, rows, jobs):
        need(type(rows) is int and rows in (16, 128), 'rows must be M16 or M128')
        need(type(jobs) is dict and set(jobs) == {3, 6}, 'exact Q/K RoPE jobs required')
        self.rows = rows
        self.jobs = {pc: dict(job) for pc, job in jobs.items()}
        self.values = {name: array('I', [SENTINEL]) * (rows * 64) for name in ('cos', 'sin')}
        self.frequency = {name: array('B', [0]) * (rows * 64) for name in ('cos', 'sin')}
        self.cursor = 0
        self.events = hashlib.sha256()
        self.finished = False
        need(sys.byteorder == 'little' and self.values['cos'].itemsize == 4, 'little-endian uint32 words required')

    def expected_coordinate(self):
        q_chunks = self.rows * 12 * 4
        pc, position = (3, self.cursor) if self.cursor < q_chunks else (6, self.cursor - q_chunks)
        heads = ROLE_HEADS[pc]
        need(position < self.rows * heads * 4, 'excess capture event')
        return pc, position // (heads * 4), (position // 4) % heads, (position % 4) * 16

    def observe(self, *, pc, job, token, head, col, half, index, trig_index, cosine, sine):
        need(not self.finished, 'capture already finished')
        need(all(type(value) is int for value in (pc, token, head, col, half, index, trig_index)),
             'capture coordinates must be exact integers')
        need((pc, token, head, col) == self.expected_coordinate(), 'missing/duplicate/out-of-order/wrong-head operand event')
        expected = self.jobs[pc]
        need(type(job) is dict and job == expected and
             all(type(job[key]) is type(expected[key]) for key in expected),
             'job/source/destination binding changed')
        need(half == 64 and trig_index == (token * 64 + col) * 4
             and index == (token * expected['n'] + head * 128 + col) * 4,
             'source-derived RoPE indices changed')
        for name, values in (('cos', cosine), ('sin', sine)):
            need(type(values) is tuple and len(values) == 16, 'exact original BF16 tuple required')
            for lane, value in enumerate(values):
                need(type(value) is int and 0 <= value < 1 << 32 and value & 0xFFFF == 0
                     and value & 0x7F800000 != 0x7F800000,
                     'actual operand is not finite materialized BF16 word')
                offset = token * 64 + col + lane
                if self.frequency[name][offset]:
                    need(self.values[name][offset] == value, 'actual repeated RoPE operands differ')
                else:
                    self.values[name][offset] = value
                self.frequency[name][offset] += 1
            self.events.update(struct.pack('<5I2QI', pc, token, head, col, expected['tag'],
                expected['b'] + trig_index, expected['c'] + trig_index, 0 if name == 'cos' else 1))
            self.events.update(struct.pack('<16I', *values))
        self.cursor += 1

    def finish(self):
        need(not self.finished, 'one-use capture seal')
        need(self.cursor == self.rows * 14 * 4 and
             all(value == 14 for field in self.frequency.values() for value in field),
             'incomplete true operand occurrence coverage')
        result, payloads = {}, {}
        for name in ('cos', 'sin'):
            raw = self.values[name].tobytes()
            result[name] = {'physical_shape': [self.rows, 64], 'official_logical_shape': [self.rows, 128],
                'container_dtype': 'uint32_FP32_bits_materialized_BF16', 'bytes': len(raw),
                'raw_sha256': digest(raw), 'unique_words': self.rows * 64,
                'observed_occurrences': self.rows * 64 * 14, 'Q_head_frequency': 12, 'K_head_frequency': 2,
                'frequency_sha256': digest(self.frequency[name].tobytes()),
                'official_to_actual_index': '(token * 64) + (official_column % 64)',
                'independent_expanded_DUT_tensor_materialized': False}
            payloads[name] = raw
        self.finished = True
        return {'fields': result, 'capture_chunks': self.cursor, 'ordered_event_sha256': self.events.hexdigest(),
                'recomputed_operands': False, 'oracle_values_used': False}, MappingProxyType(payloads)


class ScopedLineProbe:
    """Own only unchanged registrations; cleanup never injects a DUT fault.

    CPython has no get_callback API. register_callback returns the prior
    callback; stale or foreign callbacks discovered this way are immediately
    restored, and no local masks are cleared or foreign tool IDs freed.
    Unexpected API failures leave the capture failed and any uncertain slot
    reserved/disarmed rather than claiming successful cleanup or retrying it.
    """
    def __init__(self, code, line, consume):
        need(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12), 'CPython 3.12 only')
        self.code, self.line, self.consume = code, line, consume
        self.tool = None
        self.thread = threading.get_ident()
        self.started = False
        self.closed = False
        self.error = None
        self.cleanup_errors = []
        self.cleanup_complete = False
        self.residual_tool = None
        self.registration_replaced = False
        self._tool_name = 'qwen2-real-rope-operands-' + str(id(self))
        self._line_callback = self._line
        self._disarmed = True
        self._callback_attempted = False
        self._callback_registered = False
        self._local_attempted = False
        self._local_configured = False
        self._stale_callback_restored = False
        self._cleanup_attempted = False

    def _remember(self, error, *, cleanup=False):
        message = type(error).__name__ + ': ' + str(error) if isinstance(error, BaseException) else str(error)
        if cleanup:
            self.cleanup_errors.append(message)
        if self.error is None:
            self.error = message
        elif message not in self.error:
            self.error += '; ' + message

    def _cleanup_safely(self):
        # Keep this guard outside stop too. Even a failing/replaced cleanup
        # function cannot escape a monitoring callback into the generator.
        self._disarmed = True
        self.closed = True
        try:
            self.stop()
        except BaseException as error:
            self._remember('monitoring cleanup failed: ' + type(error).__name__ + ': ' + str(error), cleanup=True)
            self.cleanup_complete = False
            self.residual_tool = self.tool

    def __enter__(self):
        need(threading.get_ident() == self.thread, 'observer thread changed before entry')
        need(not self.started and not self.closed and self.tool is None and sys.gettrace() is None,
             'single-use observation with no tracing required')
        mon = sys.monitoring
        # A free name is insufficient: free_tool_id does not remove stale
        # callback registrations or local/global event masks.
        for tool in (3, 4):
            if mon.get_tool(tool) is not None or mon.get_events(tool) or mon.get_local_events(tool, self.code):
                continue
            try:
                mon.use_tool_id(tool, self._tool_name)
            except BaseException as error:
                # A failed claim can have an uncertain outcome. Re-read the
                # owner before cleanup; never free a racing foreign claim.
                try:
                    owned = mon.get_tool(tool) == self._tool_name
                except BaseException as status_error:
                    self._remember(error)
                    self._remember(status_error, cleanup=True)
                    self.residual_tool = tool
                    self.closed = True
                    raise error
                if owned:
                    self.tool = tool
                    self._remember(error)
                    self._cleanup_safely()
                    raise
                if isinstance(error, ValueError):
                    continue
                raise
            self.tool = tool
            break
        need(self.tool is not None, 'monitor slots busy or retain events; do not take over another observer')
        try:
            need(mon.get_tool(self.tool) == self._tool_name and not mon.get_events(self.tool)
                 and not mon.get_local_events(self.tool, self.code), 'monitor claim changed before callback registration')
            self._callback_attempted = True
            previous = mon.register_callback(self.tool, mon.events.LINE, self._line_callback)
            if previous is not None:
                replaced = mon.register_callback(self.tool, mon.events.LINE, previous)
                if replaced is not self._line_callback:
                    # A concurrent replacement is not ours. Restore the most
                    # recently displaced registration and leave the tool alone.
                    mon.register_callback(self.tool, mon.events.LINE, replaced)
                    self.registration_replaced = True
                    raise ValueError('callback changed while restoring a stale registration')
                self._stale_callback_restored = True
                raise ValueError('monitor slot retains a stale LINE callback; restored without using it')
            self._callback_registered = True
            need(mon.get_tool(self.tool) == self._tool_name and not mon.get_events(self.tool)
                 and not mon.get_local_events(self.tool, self.code), 'monitor claim changed before local events')
            self._local_attempted = True
            mon.set_local_events(self.tool, self.code, mon.events.LINE)
            self._local_configured = True
            self.started = True
            self._disarmed = False
            return self
        except BaseException as error:
            self._remember(error)
            self._cleanup_safely()
            raise  # Refuse before any observed workload starts.

    def _line(self, code, line):
        if self._disarmed or code is not self.code or line != self.line:
            return
        try:
            need(threading.get_ident() == self.thread, 'observer thread changed')
            frame = sys._getframe(1)
            need(frame.f_code is code, 'actual monitoring frame mismatch')
            self.consume(frame)
        except Exception as error:
            self._remember(error)
            self._cleanup_safely()

    def _leave_foreign(self, message):
        self.registration_replaced = True
        self._remember(message)
        self.residual_tool = self.tool
        self.tool = None
        self.cleanup_complete = False

    def _stop_impl(self):
        self._disarmed = True
        self.closed = True
        if self.tool is None:
            return
        if self._cleanup_attempted:
            return  # Never retry an uncertain cleanup mutation blindly.
        self._cleanup_attempted = True
        mon, tool = sys.monitoring, self.tool
        if mon.get_tool(tool) != self._tool_name:
            self._leave_foreign('observer monitoring tool was replaced; untouched')
            return
        global_events = mon.get_events(tool)
        local_events = mon.get_local_events(tool, self.code)
        allowed_local = (mon.events.LINE,) if self.started else ((0, mon.events.LINE) if self._local_attempted else (0,))
        if global_events or local_events not in allowed_local or self.registration_replaced:
            self._leave_foreign('observer monitoring masks/registration changed; preserved')
            return
        if self._stale_callback_restored:
            # The startup claim was ours, but this pre-existing callback was
            # not. free_tool_id preserves that restored callback and masks.
            mon.free_tool_id(tool)
            self.tool = None
            self.cleanup_complete = True
            return
        # Inspect/remove the callback before touching event masks. A foreign
        # callback keeps its masks and tool name as well as the callback itself.
        previous = mon.register_callback(tool, mon.events.LINE, None)
        own = previous is self._line_callback
        absent_after_failed_install = not self.started and not self._callback_registered and previous is None
        if not own and not absent_after_failed_install:
            mon.register_callback(tool, mon.events.LINE, previous)
            self._leave_foreign('observer LINE callback was replaced; restored and preserved')
            return
        self._callback_registered = False
        if mon.get_tool(tool) != self._tool_name or mon.get_events(tool) != global_events or mon.get_local_events(tool, self.code) != local_events:
            self._leave_foreign('monitoring ownership changed during cleanup; no masks cleared or tool freed')
            return
        if local_events:
            mon.set_local_events(tool, self.code, 0)
        self._local_configured = False
        mon.free_tool_id(tool)
        self.tool = None
        self.cleanup_complete = True

    def stop(self):
        self._disarmed = True
        self.closed = True
        try:
            self._stop_impl()
        except BaseException as error:
            self._remember('monitoring cleanup failed: ' + type(error).__name__ + ': ' + str(error), cleanup=True)
            self.cleanup_complete = False
            self.residual_tool = self.tool

    def __exit__(self, *exception):
        self._cleanup_safely()
        return False


JOB_KEYS = ('kind', 'tag', 'a', 'b', 'dst', 'm', 'n', 'k', 'write_bytes', 'c',
            'weight_bf16', 'activation_bf16', 'output_bf16')


def job_record(job):
    return {name: getattr(job, name) for name in JOB_KEYS}


def jobs_from_fixture(fixture, physical, rows):
    need(physical.fixture is fixture and fixture.scope == 'QWEN2_21_METADATA_ONLY', 'original physical fixture identity')
    specs = fixture.specs
    rope = physical.regions['rope']
    need(specs['x'][1] == (rows, 1536) and specs['rope'][1] == (2, 1024, 64), 'original x/RoPE geometry')
    need(rope['readonly'] is True and rope['base'] == specs['rope'][0]
         and rope['extent'] == 2 * 1024 * 64 * 4, 'original readonly rope allocation')
    jobs = {}
    for pc, src, dst, width in ((3, 'qr', 'q', 1536), (6, 'kr', 'k', 256)):
        need(specs[src][1] == specs[dst][1] == (rows, width), 'RoPE actual source/destination shape')
        jobs[pc] = dict(kind='Rope', tag=(fixture.config.epoch << 16) | pc,
            a=specs[src][0], b=specs['rope'][0], dst=specs[dst][0], m=rows, n=width, k=width,
            write_bytes=rows * width * 4, c=specs['rope'][0] + 1024 * 64 * 4,
            weight_bf16=False, activation_bf16=False, output_bf16=False)
    return jobs


def require_whole_terminal(terminal, registry, *, terminal_type, owner, physical, rows):
    need(type(terminal) is terminal_type and terminal.consumed is True,
         'original consumed registry terminal token required')
    need(terminal.execution.prefix_owner is owner and terminal.physical is physical and physical.pending is None,
         'terminal belongs to another owner or memory')
    need(terminal.memory.physical_memory is physical and terminal.memory.workspace.finished is True,
         'whole physical workspace not retired')
    need(owner.state == 'idle' and owner.poison is False and owner.program is None,
         'actual prefix owner did not retire cleanly')
    need(type(registry) is dict and registry.get('status') == 'COMPLETE_ACTUAL_INVENTORY_NUMERIC_TEMP'
         and registry.get('rows') == rows and registry.get('whole_terminal') is True
         and registry.get('resources_clean') is True and registry.get('public_completions') == 21
         and registry.get('actual_owner_jobs') == 17 and registry.get('launch_results') == 1,
         'whole sealed registry required, not pc12/prefix completion')
    report = terminal.report
    need(report.get('reference_arithmetic_executed') is False and report.get('full_block_executed') is True,
         'actual whole block evidence required')
    host = report['host']
    result = host['launch_result']
    need(type(result) is dict and 'status' in result and result['status'] is None
         and result.get('completed') == 21 and result.get('jobs') == 17
         and [entry['pc'] for entry in host['completions']] == list(range(21))
         and all(entry['status'] is None for entry in host['completions']), 'exact whole21 completion evidence')


class RopeOperandCapture:
    """Normal-runtime only. Use during prefix, seal only after whole registry."""
    def __init__(self, *, owner, fixture, physical, rows, terminal_type):
        need(type(rows) is int and rows in (16, 128), 'rows must be M16 or M128')
        module = sys.modules.get(PINS['sources']['official_owner']['module'])
        need(module is not None and type(owner) is module.__dict__.get('OfficialPrefixOwner'),
             'exact normally loaded OfficialPrefixOwner required')
        need(owner.head_dim == 128 and owner.hidden == 1536 and owner.kv == 256
             and owner.max_tokens == 1024, 'original owner geometry')
        need(not set(('_rope', '_op', '_read')) & set(owner.__dict__), 'instance method substitution forbidden')
        self.owner, self.fixture, self.physical, self.rows = owner, fixture, physical, rows
        self.terminal_type = terminal_type
        self.bindings = {'rope': binding(owner._rope, 'official_owner', 'OfficialPrefixOwner', '_rope'),
                         'op': binding(owner._op, 'prefix_owner', 'PrefixOwner', '_op'),
                         'read': binding(owner._read, 'prefix_owner', 'PrefixOwner', '_read')}
        self.line = capture_line()
        self.data = OperandData(rows, jobs_from_fixture(fixture, physical, rows))
        self.probe = ScopedLineProbe(self.bindings['rope'], self.line, self._consume)
        self.error = None
        self.sealed = False

    def _check_binding(self):
        for name, method, role, cls, member in (
                ('rope', self.owner._rope, 'official_owner', 'OfficialPrefixOwner', '_rope'),
                ('op', self.owner._op, 'prefix_owner', 'PrefixOwner', '_op'),
                ('read', self.owner._read, 'prefix_owner', 'PrefixOwner', '_read')):
            need(binding(method, role, cls, member) is self.bindings[name], 'live function code identity changed')
        need(jobs_from_fixture(self.fixture, self.physical, self.rows) == self.data.jobs, 'fixture changed')

    def __enter__(self):
        need(self.owner.state == 'idle' and self.owner.poison is False and self.owner.program is None,
             'original idle owner required before prefix')
        # Source/code/fixture admission errors above remain hard refusals.
        # Only after that admission may monitoring-resource failure degrade
        # to unobserved original execution with sticky later capture FAIL.
        self._check_binding()
        try:
            self.probe.__enter__()
        except Exception as error:
            self._capture_failure('monitor installation failed; original prefix continues without capture', error)
            self.probe._cleanup_safely()
        return self

    def _capture_failure(self, label, error):
        message = label + ': ' + type(error).__name__ + ': ' + str(error)
        self.error = message if self.error is None else self.error + '; ' + message

    def _consume(self, frame):
        local = frame.f_locals
        # Another instance using the same class is outside this capture, not a
        # reason to attribute its values to the selected DUT.
        if local.get('self') is not self.owner:
            return
        need(self.owner.program is not None and self.owner.program.gi_frame is frame,
             'not the actual selected owner generator frame')
        job = local.get('j')
        need(job is self.owner.job and self.owner.poison is False, 'actual live job binding or poison changed')
        record = job_record(job)
        self.data.observe(pc=record['tag'] & 0xFFFF, job=record, token=local['token'], head=local['head'],
            col=local['col'], half=local['half'], index=local['index'], trig_index=local['trig_index'],
            cosine=local['cosine'], sine=local['sine'])

    def __exit__(self, *exception):
        try:
            self.probe.__exit__(*exception)
        except BaseException as error:
            # Even a defective cleanup wrapper cannot replace the original
            # driver's return or exception. Acceptance remains sticky FAIL.
            self._capture_failure('monitor cleanup failed', error)
        try:
            self._check_binding()
        except Exception as error:
            self._capture_failure('post-execution source/fixture binding changed', error)
        return False

    def seal(self, *, terminal, registry):
        need(not self.sealed and self.probe.started and self.probe.closed and self.probe.tool is None
             and self.probe.cleanup_complete is True and not self.probe.cleanup_errors,
             'observation must have finished before one-use whole seal')
        need(self.error is None and self.probe.error is None, 'passive observer failed: ' + str(self.error or self.probe.error))
        self._check_binding()
        require_whole_terminal(terminal, registry, terminal_type=self.terminal_type,
            owner=self.owner, physical=self.physical, rows=self.rows)
        report, payloads = self.data.finish()
        report.update(status='COMPLETE_ACTUAL_ROPE_OPERANDS_SOFTWARE_ONLY', rows=self.rows,
            execution_provenance='NORMAL_LOADED_SOURCE_SOFTWARE', source_pins=PINS['sources'],
            capture_line=self.line, whole_registry_terminal=True,
            observed_after_original_bf16=True, replacement_arithmetic=False,
            tensor_reconstruction=False, full_29_numeric_acceptance='NOT_READY',
            numeric_comparison_performed=False, hardware_acceptance=False,
            noninterference_proven=False,
            noninterference_scope='observer contains no DUT writes/calls; actual baseline/observed numerical equivalence not run')
        self.sealed = True
        return report, payloads
