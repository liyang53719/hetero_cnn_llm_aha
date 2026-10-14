#!/usr/bin/env python3
"""Explicit synthetic public3 M2 recorded equivalence and M8 unrecorded ABBA; default performs no execution.

The exact frozen Attention driver, Host, Tile, services and observer execute.
Two externally recorded equivalence arms precede unrecorded ABBA timing arms.
An existing source-verified library is shared by identity, never by C state.
This source does not authorize any run. A reviewed manifest and explicit opt-in
are mandatory. Public21, official inputs, M128, and Host-tail arms are absent.
"""
import argparse
from array import array
from collections import Counter, deque
from contextlib import nullcontext
from dataclasses import asdict, fields, is_dataclass
import ctypes
import enum
import hashlib
import gzip
import inspect
import io
import json
import os
from pathlib import Path
import pickle
import re
import resource
import signal
import statistics
import struct
import subprocess
import sys
import time
import threading
import traceback
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
OUTPUT_ROOT = ROOT / 'work/qwen2_attention_idle_fastpath_20261014'
HISTORICAL = (
    ('work/qwen2_live_attention_numeric_m128_20261014/m128_pv32_actual_v1/RESULT.json', 169),
    ('work/qwen2_live_attention_numeric_m16_20261014/m16_pv32_actual_v1/RESULT.json', 188),
)
THREAD_KEYS = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')
OUTER_SECONDS = 45
FINALIZE_RESERVE = 2.0
NEW_SOURCE_FILES = ('__init__.py', 'owner.py', 'public_binding.py', 'probe.py', 'test_owner.py', 'test_probe.py')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def source_manifest():
    """Union, never rewrite, both historical closures and every new source."""
    result = {}
    for relative, count in HISTORICAL:
        old = json.loads((ROOT / relative).read_text())['source_sha256_before']
        require(len(old) == count, 'historical source count changed: ' + relative)
        for name, digest in old.items():
            require(name not in result or result[name] == digest, 'historical closure conflict: ' + name)
            require(sha(ROOT / name) == digest, 'historical source drift: ' + name)
            result[name] = digest
    # Include current M16 source additions, without replacing any historical pin.
    from candidates.qwen2_live_attention_model_m16 import gates
    for name, digest in gates.sources().items():
        require(name not in result or result[name] == digest, 'M16 closure conflict: ' + name)
        result[name] = digest
    require({p.name for p in HERE.glob('*.py')} == set(NEW_SOURCE_FILES), 'unreviewed new Python source inventory')
    for name in NEW_SOURCE_FILES:
        path = HERE / name
        result[str(path.relative_to(ROOT))] = sha(path)
    return result


def reviewed_manifest(path):
    expected = json.loads(Path(path).read_text())
    require(expected.get('status') == 'REVIEWED_SOURCE_ONLY_FOR_M2_RECORDED_M8_ABBA',
            'explicit independent source review manifest required')
    require(expected.get('recorded_rows') == 2 and expected.get('timing_rows') == 8 and expected.get('outer_budget_seconds') == 45,
            'review must explicitly select complete recorded M2 and unrecorded M8 ABBA within 45 seconds')
    require(expected['source_sha256'] == source_manifest(), 'reviewed source manifest drift')
    require(isinstance(expected.get('reviewer'), str) and expected['reviewer'], 'reviewer identity required')
    return expected


def tool_snapshot(receipt):
    old = json.loads((ROOT / HISTORICAL[1][0]).read_text())['tools_before']
    paths = {key: Path(item['path']) for key, item in old.items() if key != 'matrix_library'}
    require(Path(sys.executable).resolve() == paths['python'].resolve(), 'use the pinned CPython executable')
    paths['matrix_library'] = Path(receipt['library']).resolve()
    current = {key: dict(path=str(path.resolve()), sha256=sha(path), bytes=path.stat().st_size)
               for key, path in paths.items()}
    for key, item in old.items():
        if key != 'matrix_library':
            require(current[key]['sha256'] == item['sha256'], 'historical tool drift: ' + key)
    require(current['matrix_library']['sha256'] == receipt['library_sha256'], 'library receipt identity')
    return current


class Graph:
    """Typed, ordered state graph with explicit object correspondence/aliases."""
    def __init__(self, anchors=()):
        self.anchors = {id(value): name for name, value in anchors if value is not None}
        self.seen = {}

    def encode(self, value):
        t = type(value)
        if value is None or t in (bool, int, str):
            return (t.__name__, value)
        if t is float:
            return ('float64', struct.pack('>d', value).hex())
        if t is bytes:
            return ('bytes', value.hex())
        if id(value) in self.anchors:
            return ('anchor', self.anchors[id(value)])
        if id(value) in self.seen:
            return ('ref', self.seen[id(value)])
        ref = len(self.seen)
        self.seen[id(value)] = ref
        name = t.__module__ + '.' + t.__qualname__
        if isinstance(value, dict):
            body = [(self.encode(k), self.encode(v)) for k, v in value.items()]
        elif t in (list, tuple, deque):
            body = [self.encode(v) for v in value]
        elif t in (set, frozenset):
            # Model sets contain typed scalar values/tuples, never model objects.
            body = [self.encode(v) for v in sorted(value, key=repr)]
        elif t is range:
            body = (value.start, value.stop, value.step)
        elif t in (bytearray, memoryview):
            body = bytes(value).hex()
        elif t is array:
            body = (value.typecode, value.tobytes().hex())
        elif isinstance(value, enum.Enum):
            body = self.encode(value.value)
        elif is_dataclass(value):
            body = [(f.name, self.encode(getattr(value, f.name))) for f in fields(value)]
        elif isinstance(value, types.MethodType):
            body = (value.__func__.__module__, value.__func__.__qualname__, self.encode(value.__self__))
        elif hasattr(value, '__dict__') and not callable(value):
            body = self.encode(vars(value))
        else:
            raise TypeError('unsupported state field: ' + name)
        return ('node', ref, name, body)


def fixture_identity(fixture, job):
    """Identity of actual geometry-specific packed metadata and decoded job."""
    tables = {}
    for name, table in (('commands', fixture.config.command), ('descriptors', fixture.config.descriptor)):
        raw = bytes(fixture.memory.mappings[table.base])
        tables[name] = dict(base=table.base, limit=table.limit, record_count=table.count,
                            packed_span_bytes=len(raw), packed_span_sha256=hashlib.sha256(raw).hexdigest())
    require(fixture.config.command.count == len(fixture.commands)
            and fixture.config.descriptor.count == len(fixture.records), 'actual fixture record count mismatch')
    return dict(scope=fixture.scope, config=asdict(fixture.config), tables=tables, decoded_job=asdict(job))


def normalized_backend_report(report, verified_resource_address):
    """Only the explicitly verified ELF accumulator root may cross ASLR."""
    require(type(verified_resource_address) is int and verified_resource_address > 0
            and 'matrix_resource_address' in report and report['matrix_resource_address'] == verified_resource_address,
            'backend report differs from the verified Matrix accumulator root')
    result = dict(report)
    result['matrix_resource_address'] = '@same_pinned_matrix_accumulator'
    return result


def full_public_state(x, memory):
    """Every public/control field, owner state, bank contents and physical ACK."""
    roots = [('execution', x), ('owner', x.owner), ('host', x.host),
             ('frontend', x.frontend), ('metadata_port', x.frontend.port),
             ('metadata_reader', x.frontend.reader), ('record_machine', x.frontend.port.machine),
             ('metadata_memory', x.frontend.memory), ('trace', x.trace),
             ('physical', memory), ('prefix_owner', x.prefix_owner),
             ('attention_owner', x.attention_owner), ('matrix_service', x.matrix_service)]
    # Opaque input providers are fixed named roles; their exact bytes are pinned
    # in the stimulus manifest. No callable implementation/state is ignored.
    roots += [('input_provider:' + n, r.get('provider')) for n, r in memory.regions.items()
              if r.get('provider') is not None]
    state = dict(vars(x))
    state['deadline'] = '@same_outer_deadline'
    require(x.bank_ids == (id(x.owner), id(x.owner.a_banks), id(x.owner.b_banks), id(x.owner.tiles.banks)),
            'public bank identity changed')
    state['bank_ids'] = ('owner', 'a_banks', 'b_banks', 'a_banks')
    trace_state = dict(vars(x.trace))
    trace_state['stream'] = None if x.trace.stream is None else '@host_trace_stream'
    trace_state['digest'] = dict(hex=x.trace.digest.copy().hexdigest(), name=x.trace.digest.name,
                                digest_size=x.trace.digest.digest_size, block_size=x.trace.digest.block_size)
    final_backends = {}
    if x.attention_owner is not None:
        shared = x.attention_owner.scalar
        roots += [('scalar_service', shared), ('matrix_library', x.matrix_service.lib)]
        for name, obj in (('prefix', x.prefix_owner), ('attention', x.attention_owner),
                          ('matrix', x.matrix_service), ('scalar', shared)):
            fields = dict(vars(obj))
            program = fields.get('program')
            if isinstance(program, types.GeneratorType):
                require(inspect.getgeneratorstate(program) == 'GEN_CLOSED' and program.gi_frame is None,
                        'complete final backend snapshot requires a genuinely closed generator')
                fields['program'] = dict(state='GEN_CLOSED', qualified_name=program.gi_code.co_qualname,
                    source=str(Path(program.gi_code.co_filename).resolve().relative_to(ROOT)))
            if name == 'matrix':
                require(obj.resource_address == obj.lib.matrix_accumulator_address(), 'final physical accumulator identity changed')
                fields['resource_address'] = '@same_pinned_matrix_accumulator'
            final_backends[name] = fields
    payload = dict(execution=state, final_backend_fields=final_backends,
                   controls={name: vars(obj) for name, obj in roots[1:8]}, trace_state=trace_state,
                   physical=vars(memory), owner=vars(x.owner), public_report=x.report(),
                   trace_report=x.trace.report())
    return Graph(roots).encode(payload)


class DenseReturnCapture:
    """Read-only exact Dense PY_RETURN capture in a separate monitoring slot.

    Never substitutes a method, wraps the observed frame, modifies model state,
    or touches PV32 registrations. Foreign execution invalidates this capture.
    Diagnostic callback failures are retained and raised at the driver boundary.
    """
    def __init__(self, owner, *, source_sha256):
        from .owner import DenseIdleOwnerV1, DenseReductionOwner, _TILE_TYPE, _BANK_TYPE
        from candidates.qwen2_resident_matrix.official_bf16 import observation as verify
        require(type(owner) in (DenseReductionOwner, DenseIdleOwnerV1), 'exact Dense class required')
        require('tick' not in vars(owner), 'shadowed Dense tick refused')
        require(type(owner.tiles) is _TILE_TYPE and type(owner.a_banks) is _BANK_TYPE
                and type(owner.b_banks) is _BANK_TYPE and owner.tiles.banks is owner.a_banks,
                'exact original Tile/bank objects required')
        require(owner.ports.__func__ is DenseReductionOwner.ports, 'original Dense ports binding required')
        self.objects = (owner.tiles, owner.a_banks, owner.b_banks)
        self.ports_function = DenseReductionOwner.ports
        self.owner = owner
        self.function = type(owner).tick
        self.code = self.function.__code__
        self.thread = threading.get_ident()
        self.sources = dict(source_sha256)
        self.bindings = []
        self.files = {}
        compiled = {}
        # Source-bind every function on the owner/Tile/bank MROs. These are
        # inspections only; no candidate method is executed to establish trust.
        classes = set(type(owner).__mro__ + type(owner.tiles).__mro__ + type(owner.a_banks).__mro__)
        for cls in sorted(classes, key=lambda c: (c.__module__, c.__qualname__)):
            for name, descriptor in vars(cls).items():
                fn = descriptor.fget if isinstance(descriptor, property) else descriptor
                if not isinstance(fn, types.FunctionType):
                    continue
                path = Path(fn.__code__.co_filename).resolve()
                relative = str(path.relative_to(ROOT))
                require(relative in self.sources and sha(path) == self.sources[relative], 'Dense recorder source drift: ' + relative)
                if relative not in compiled:
                    compiled[relative] = compile(path.read_text(), str(path), 'exec', dont_inherit=True, optimize=0)
                expected = compiled[relative]
                for part in fn.__qualname__.split('.'):
                    expected = verify._code(expected, part)
                require(verify._same_code(fn.__code__, expected), 'Dense recorder loaded code differs: ' + fn.__qualname__)
                self.bindings.append((cls, name, descriptor, fn, fn.__code__))
                self.files[relative] = self.sources[relative]
        self.tool_id = None
        self.name = 'dense-idle-return-' + str(id(self))
        self.callback = self._return
        self.registered = self.configured = False
        self.active = self.closed = False
        self.error = None
        self.pending = None
        self.returns = self.consumed = 0

    def check_bindings(self):
        require((self.owner.tiles, self.owner.a_banks, self.owner.b_banks) == self.objects
                and all(a is b for a, b in zip((self.owner.tiles, self.owner.a_banks, self.owner.b_banks), self.objects))
                and self.owner.tiles.banks is self.owner.a_banks, 'Dense recorder model object replaced')
        require(not {'tick', 'ports', '_read_command', '_write_command', '_write_data'}.intersection(vars(self.owner))
                and not {'tick', 'idle', 'leased'}.intersection(vars(self.owner.tiles))
                and all(not {'begin_cycle', 'read', 'write'}.intersection(vars(b)) for b in self.objects[1:])
                and self.owner.ports.__func__ is self.ports_function, 'Dense recorder shadowed method')
        require(type(self.owner).tick is self.function and self.owner.tick.__func__ is self.function
                and self.function.__code__ is self.code, 'Dense recorder selected code changed')
        require(all(vars(cls).get(name) is descriptor and fn.__code__ is code
                    for cls, name, descriptor, fn, code in self.bindings), 'Dense/Tile/bank loaded binding changed')

    def __enter__(self):
        require(not self.active and not self.closed, 'Dense recorder is single-use')
        require(threading.get_ident() == self.thread, 'Dense recorder thread changed')
        require(sys.gettrace() is None and sys.getprofile() is None, 'Dense recorder refuses existing tracer/profiler')
        self.check_bindings()
        monitor = sys.monitoring
        try:
            for tool in (4, 3):
                if monitor.get_tool(tool) is not None or monitor.get_events(tool) or monitor.get_local_events(tool, self.code):
                    continue
                try:
                    monitor.use_tool_id(tool, self.name)
                except ValueError:
                    continue
                self.tool_id = tool
                break
            require(self.tool_id is not None, 'no independent unused Dense monitoring slot')
            previous = monitor.register_callback(self.tool_id, monitor.events.PY_RETURN, self.callback)
            if previous is not None:
                monitor.register_callback(self.tool_id, monitor.events.PY_RETURN, previous)
                raise ValueError('Dense slot contains a stale callback')
            self.registered = True
            monitor.set_local_events(self.tool_id, self.code, monitor.events.PY_RETURN)
            self.configured = True
            self.active = True
            return self
        except BaseException:
            self._stop()
            self.closed = True
            raise

    def _stop(self):
        self.active = False
        if self.tool_id is None:
            return
        monitor, tool = sys.monitoring, self.tool_id
        intact = monitor.get_tool(tool) == self.name
        if not intact:
            self.error = self.error or 'Dense monitoring slot owner replaced'
            self.tool_id = None
            return
        intact = monitor.get_events(tool) == 0
        if self.configured:
            if monitor.get_local_events(tool, self.code) == monitor.events.PY_RETURN:
                monitor.set_local_events(tool, self.code, 0)
            else:
                intact = False
        if self.registered:
            previous = monitor.register_callback(tool, monitor.events.PY_RETURN, None)
            if previous is not self.callback:
                monitor.register_callback(tool, monitor.events.PY_RETURN, previous)
                intact = False
        if intact:
            monitor.free_tool_id(tool)
        else:
            self.error = self.error or 'Dense monitoring registration replaced'
        self.tool_id = None
        self.registered = self.configured = False

    def _return(self, code, offset, edge):
        if not self.active:
            return
        try:
            frame = sys._getframe(1)
            require(code is self.code and frame.f_code is self.code, 'foreign Dense return code/frame')
            require(frame.f_locals.get('self') is self.owner, 'foreign Dense owner executed observed code')
            require(threading.get_ident() == self.thread, 'Dense return thread changed')
            require(not frame.f_locals.get('args', ()) and not frame.f_locals.get('kwargs', {})
                    and frame.f_locals.get('window') is None, 'Dense capture requires argument-free idle calls')
            require(type(edge) is dict and self.pending is None, 'missing/overlapping Dense return')
            self.check_bindings()
            self.pending = edge
            self.returns += 1
        except Exception as error:
            self.error = self.error or str(error)
            self._stop()

    def take(self):
        require(self.error is None, 'Dense recorder invalid: ' + str(self.error))
        require(self.pending is not None and self.returns == self.consumed + 1, 'one actual Dense return required per public edge')
        edge = self.pending
        self.pending = None
        self.consumed += 1
        return edge

    def __exit__(self, kind, error, tb):
        try:
            self._stop()
            if kind is not None:
                self.error = self.error or 'driver body raised: ' + kind.__name__
            if self.pending is not None or self.returns != self.consumed:
                self.error = self.error or 'unconsumed Dense return'
            if threading.get_ident() != self.thread or sys.gettrace() is not None or sys.getprofile() is not None:
                self.error = self.error or 'Dense recorder thread/tracer/profiler changed'
            self.check_bindings()
            require(all(sha(ROOT / n) == h for n, h in self.files.items()), 'Dense recorder source changed at exit')
        except Exception as failure:
            self.error = self.error or str(failure)
            if kind is None:
                raise
        finally:
            self.closed = True
        if kind is None:
            require(self.error is None, 'Dense recorder invalid: ' + str(self.error))
        return False


class IdleBankInvariant:
    """Factored invariant, not a newly measured bank hash on each edge.

    Complete SRAM values are captured before and after. Every intermediate edge
    verifies source-bound idle return/access events and bank/row identities.
    Within this exact unmodified execution closure, empty physical accesses mean
    bank cells cannot change. Arbitrary external memory mutation is not proved.
    """
    def __init__(self, owner):
        self.owner = owner
        self.banks = (owner.a_banks, owner.b_banks)
        self.words = tuple(bank.words for bank in self.banks)
        self.rows = tuple(tuple(bank.words) for bank in self.banks)
        self.baseline = tuple(tuple(tuple(row) for row in bank.words) for bank in self.banks)
        self.digest = hashlib.sha256(pickle.dumps(self.baseline, protocol=4)).hexdigest()
        self.previous_a = (owner.a_banks.reads, owner.a_banks.writes)
        self.original_b = (owner.b_banks.reads, owner.b_banks.writes)
        self.edges = 0

    def check(self, edge):
        o = self.owner
        require(o.a_banks is self.banks[0] and o.b_banks is self.banks[1] and o.tiles.banks is self.banks[0], 'bank object changed')
        for bank, words, rows in zip(self.banks, self.words, self.rows):
            require(bank.words is words and len(words) == len(rows) and all(a is b for a, b in zip(words, rows)), 'bank words/row identity changed')
        d = vars(o)
        none_debts = ('error', 'lease', 'window_request', 'window_result', 'drain_request',
                      'drain_result', 'drain_expected', 'read_active', 'a_hold', 'a_rmw_pending',
                      'pending', 'accepted_write', 'final_value', 'seed_hold')
        require(all(name in d and d[name] is None for name in none_debts)
                and all(d.get(name) is True for name in ('enable_dense_drain', 'enable_k_window',
                    'enable_ffn_window', 'enable_ffn_tiles', 'enable_ffn_drain'))
                and type(d.get('state')) is str and d['state'] == 'idle'
                and d.get('drain_poison') is False
                and type(d.get('drain_phase')) is str and d['drain_phase'] == 'idle'
                and type(d.get('write_state')) is str and d['write_state'] == 'idle'
                and type(d.get('seed_state')) is str and d['seed_state'] == 'idle'
                and d.get('seed_outstanding') is False and d.get('restoring') is False
                and type(d.get('fifo')) is deque and not d['fifo']
                and type(d.get('group_started')) is bool and type(d.get('group_done')) is bool
                and (not d['group_started'] or d['group_done'])
                and o.tiles.pending is None and o.tiles.response is None and o.tiles.poison is False
                and len(o.tiles.tags) == 3 and all(tag.live is False for tag in o.tiles.tags),
                'recorded Dense/Tile is not fully clean/debt-free')
        require(all(edge[name] == {} for name in ('a_reads', 'a_writes', 'b_reads', 'b_writes'))
                and edge['tile']['reads'] == {} and edge['tile']['writes'] == {}
                and not any(edge['tile'][k] for k in ('ctl_fire', 'write_fire', 'read_fire', 'response_fire', 'rmw_commit', 'dense_grant')),
                'recorded edge accessed Dense/Tile SRAM')
        require(edge['a_reads'] is edge['tile']['reads'] and edge['a_writes'] is edge['tile']['writes'], 'Dense/Tile actual event aliases changed')
        require(o.a_banks.reads is not self.previous_a[0] and o.a_banks.writes is not self.previous_a[1]
                and o.a_banks.reads == o.a_banks.writes == {}, 'A-bank cycle dictionaries were not freshly replaced')
        require(o.b_banks.reads is self.original_b[0] and o.b_banks.writes is self.original_b[1], 'idle edge replaced B bookkeeping')
        self.previous_a = (o.a_banks.reads, o.a_banks.writes)
        self.edges += 1

    def seal(self):
        actual = tuple(tuple(tuple(row) for row in bank.words) for bank in self.banks)
        require(actual == self.baseline, 'Dense SRAM changed over the recorded interval')
        return dict(kind='factored_source_bound_idle_sram_invariant', complete_baseline_sha256=self.digest,
                    complete_final_equal=True, checked_edges=self.edges, per_edge_bank_hash_observed=False)


class SnapshotPickler(pickle.Pickler):
    """C pickle transport with baseline references and cross-edge alias IDs."""
    def __init__(self, stream, anchors, previous, serial):
        super().__init__(stream, protocol=4)
        self.anchors, self.previous, self.serial = anchors, previous, serial
        self.current = {}
        self.identities = []

    def persistent_id(self, value):
        # Primitive values have no mutable model identity to track. This fast
        # dispatch changes neither the pickle body nor any alias token.
        if type(value) in (int, str, bool, float, bytes, type(None)):
            return None
        ident = id(value)
        if ident in self.anchors:
            return ('source_bound_reference', self.anchors[ident])
        if isinstance(value, (dict, list, set, deque, bytearray)) or (is_dataclass(value) and not isinstance(value, type)):
            if ident not in self.current:
                old = self.previous.get(ident)
                if old is not None and old[0] is value:
                    token = old[1]
                else:
                    self.serial += 1
                    token = self.serial
                self.current[ident] = (value, token)
                self.identities.append(token)
        return None


def snapshot_load(raw):
    header, payload, continuity = pickle.loads(raw)
    require(header == 'dense-public-edge-v2', 'unknown edge snapshot')
    references = {}
    class Reader(pickle.Unpickler):
        def persistent_load(self, key):
            require(key[0] == 'source_bound_reference', 'unknown persistent snapshot reference')
            return references.setdefault(key, ('source_bound_reference', key[1]))
    return dict(state=Reader(io.BytesIO(payload)).load(), alias_continuity=continuity)


class EdgeRecorder:
    """External recorder: writes only its own fields, buffers and output stream."""
    def __init__(self, stream, *, dense_capture=None, execution=None, memory=None):
        require(dense_capture is None or (execution is not None and memory is not None),
                'recorded interval needs original execution/physical roots before first edge')
        self.root_baseline = None if execution is None else tuple(self._roots(execution, memory))
        method = None if execution is None else execution.frontend.memory.read64
        self.read64_binding = None if method is None else (method.__self__, method.__func__)
        self.stream = stream
        self.capture = dense_capture
        self.invariant = None if dense_capture is None else IdleBankInvariant(dense_capture.owner)
        self.previous = {}
        self.serial = 0
        self.edges = 0
        self.uncompressed_bytes = 0

    @staticmethod
    def _roots(x, memory):
        return [('execution', x), ('owner', x.owner), ('tile', x.owner.tiles),
                 ('a_bank', x.owner.a_banks), ('b_bank', x.owner.b_banks), ('host', x.host),
                 ('frontend', x.frontend), ('metadata_port', x.frontend.port),
                 ('metadata_reader', x.frontend.reader), ('record_machine', x.frontend.port.machine),
                 ('metadata_memory', x.frontend.memory), ('trace', x.trace), ('physical', memory),
                 ('prefix_owner', x.prefix_owner), ('attention_owner', x.attention_owner),
                 ('matrix_service', x.matrix_service)]

    def record(self, x, inputs, edge, memory):
        dense = None if self.capture is None else self.capture.take()
        if self.invariant is not None:
            self.invariant.check(dense)
        roots = self._roots(x, memory)
        if self.root_baseline is None:
            self.root_baseline = tuple(roots)
            method = x.frontend.memory.read64
            self.read64_binding = (method.__self__, method.__func__)
        require(len(roots) == len(self.root_baseline) and all(name == old_name and obj is old
                for (name, obj), (old_name, old) in zip(roots, self.root_baseline)),
                'recorded public/model root object replaced')
        method = x.frontend.memory.read64
        require(isinstance(method, types.MethodType) and method.__self__ is self.read64_binding[0]
                and method.__func__ is self.read64_binding[1], 'physical read64 method binding replaced')
        roots.append(('metadata_read64', method))
        anchors = {id(obj): name for name, obj in roots if obj is not None}
        if self.invariant is not None:
            for name, words, rows in zip(('a', 'b'), self.invariant.words, self.invariant.rows):
                anchors[id(words)] = name + '_sram_baseline:' + self.invariant.digest
                anchors.update({id(row): name + '_sram_row:' + str(i) for i, row in enumerate(rows)})
        state = dict(vars(x))
        state['deadline'] = '@same_outer_deadline'
        require(x.bank_ids == (id(x.owner), id(x.owner.a_banks), id(x.owner.b_banks), id(x.owner.tiles.banks)), 'public bank identity changed')
        state['bank_ids'] = ('owner', 'a_bank', 'b_bank', 'a_bank')
        trace = dict(vars(x.trace))
        trace['stream'] = None if x.trace.stream is None else '@host_trace_stream'
        trace['digest'] = (x.trace.digest.copy().hexdigest(), x.trace.digest.name, x.trace.digest.digest_size, x.trace.digest.block_size)
        backend = x.attention_owner
        live = None if backend is None else dict(clock=backend.clock, state=backend.state, counts=backend.counts,
            functional_state_ticks=backend.functional_state_ticks, memory_pending=backend.memory_pending,
            matrix_request=backend.matrix_request, request=backend.request, result=backend.result,
            ack_bytes=backend.ack_bytes, poison=backend.poison, pv32_borrowed=backend.pv32_borrowed,
            matrix_client_state=None if backend.matrix_client is None else backend.matrix_client.state,
            matrix_counts=x.matrix_service.counts, scalar_calls=backend.scalar.calls)
        payload = dict(inputs=inputs, attention_event=edge, dense_event=dense, host_event=x.last_host_edge,
            execution=state, controls={name: vars(obj) for name, obj in roots[1:11]}, trace=trace,
            live_backend_summary=live, physical_counts=memory.counts, physical_read_regions=memory.read_regions)
        stream = io.BytesIO()
        writer = SnapshotPickler(stream, anchors, self.previous, self.serial)
        writer.dump(payload)
        raw = pickle.dumps(('dense-public-edge-v2', stream.getvalue(), writer.identities), protocol=4)
        self.previous, self.serial = writer.current, writer.serial
        self.stream.write(struct.pack('<I', len(raw)))
        self.stream.write(raw)
        self.edges += 1
        self.uncompressed_bytes += len(raw) + 4


class RecordedPublicEdges:
    """Structural driver argument; its real execution remains unmodified."""
    def __init__(self, execution, memory, recorder):
        self.execution, self.memory, self.recorder = execution, memory, recorder

    def __getattr__(self, name):
        return getattr(self.execution, name)

    def attention_edge(self, **inputs):
        edge = self.execution.attention_edge(**inputs)
        self.recorder.record(self.execution, inputs, edge, self.memory)
        return edge


def read_frames(path):
    opener = gzip.open if Path(path).suffix == '.gz' else open
    with opener(path, 'rb') as stream:
        while header := stream.read(4):
            require(len(header) == 4, 'truncated edge frame header')
            size = struct.unpack('<I', header)[0]
            raw = stream.read(size)
            require(len(raw) == size, 'truncated edge frame body')
            yield raw


def first_difference(left, right, path='$'):
    if type(left) is not type(right):
        return dict(path=path, reason='type', left=repr(left), right=repr(right))
    if isinstance(left, bytes):
        if left != right:
            offset = next((i for i, (a, b) in enumerate(zip(left, right)) if a != b), min(len(left), len(right)))
            return dict(path=path, reason='bytes', offset=offset, left_length=len(left), right_length=len(right),
                        left=left[max(0, offset-8):offset+9].hex(), right=right[max(0, offset-8):offset+9].hex())
    elif isinstance(left, dict):
        if list(left) != list(right):
            return dict(path=path, reason='ordered_keys', left=repr(list(left)), right=repr(list(right)))
        for key in left:
            found = first_difference(left[key], right[key], path + '[' + repr(key) + ']')
            if found:
                return found
    elif isinstance(left, (tuple, list)):
        if len(left) != len(right):
            return dict(path=path, reason='length', left=len(left), right=len(right))
        for i, (a, b) in enumerate(zip(left, right)):
            found = first_difference(a, b, path + '[' + str(i) + ']')
            if found:
                return found
    elif left != right:
        return dict(path=path, reason='value', left=repr(left), right=repr(right))
    return None


def compare_frames(left, right, divergence, expected_edges):
    from itertools import zip_longest
    count = 0
    for index, (a, b) in enumerate(zip_longest(read_frames(left), read_frames(right))):
        if a != b:
            ga = None if a is None else Graph().encode(snapshot_load(a))
            gb = None if b is None else Graph().encode(snapshot_load(b))
            detail = first_difference(ga, gb)
            save(divergence, dict(kind='first_edge_divergence', edge=index,
                                 left_frame_sha256=None if a is None else hashlib.sha256(a).hexdigest(),
                                 right_frame_sha256=None if b is None else hashlib.sha256(b).hexdigest(),
                                 detail=detail or {'reason': 'pickle_identity_encoding'}))
            raise ValueError('per-edge divergence at ' + str(index))
        count += 1
    require(count == expected_edges, 'recorded actual Attention edge count')
    return count


def check_equal(left, right, divergence, kind):
    if left != right:
        save(divergence, dict(kind=kind, detail=first_difference(left, right)))
        raise ValueError(kind)


def method_identities():
    from .public_binding import (DenseIdlePublic3ExecutionV1, DenseIdlePV32PublicExecutionV1,
                                DenseIdlePV32ReductionDriverV1, PublicExecution,
                                PV32PublicExecution, PV32ReductionDriver)
    result = {}
    for new, old in ((DenseIdlePublic3ExecutionV1, PublicExecution),
                     (DenseIdlePV32PublicExecutionV1, PV32PublicExecution),
                     (DenseIdlePV32ReductionDriverV1, PV32ReductionDriver)):
        names = {name for cls in old.__mro__ for name, member in vars(cls).items()
                 if isinstance(member, types.FunctionType) and name != '__init__'}
        for name in sorted(names):
            a, b = getattr(new, name), getattr(old, name)
            require(a is b, 'inherited execution method changed: ' + name)
            path = Path(a.__code__.co_filename).resolve()
            result[new.__name__ + '.' + name] = dict(inherited_identity=True,
                qualified_name=a.__qualname__, source=str(path.relative_to(ROOT)),
                source_sha256=sha(path), first_line=a.__code__.co_firstlineno)
    return result


def run_condition(config):
    """One fresh isolated address space, one real public3 transaction."""
    from candidates.qwen2_live_attention_model_m128.runner import dependencies
    from candidates.qwen2_live_attention_model_m16.budget_fixture import attention_fixture
    from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
    from candidates.qwen2_live_attention_model_m128.pv32_observation import PV32AttentionObservation
    from .owner import DenseIdleOwnerV1, diagnostics
    from .public_binding import DenseIdlePublic3ExecutionV1
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    require(not sys.flags.optimize and sys.version_info[:2] == (3, 12), 'CPython3.12 without -O required')
    require(all(os.environ.get(k) == '1' for k in THREAD_KEYS), 'single-thread environment required')
    os.sched_setaffinity(0, config['affinity'])
    require(sorted(os.sched_getaffinity(0)) == config['affinity'], 'child affinity mismatch')
    review = reviewed_manifest(config['review_manifest'])
    sources = review['source_sha256']
    out = Path(config['out']).absolute()
    require(out.resolve() == out and out.parent.parent == OUTPUT_ROOT and not out.exists(),
            'child must be fresh beneath one direct-child probe run')
    require(config['mode'] in ('old', 'new') and config['observer'] is True and type(config['record']) is bool,
            'exact child mode/observer/record domain')
    require(0 < config['deadline'] - time.monotonic() <= OUTER_SECONDS, 'bounded live child deadline required')
    out.mkdir()
    deps = dependencies()
    r, dense, native, helper, original, fixtures, public, prefix, scalar, owner_module, binding, profiles, execution, suffix, observation = deps
    receipt = dense.verify_library(config['library_receipt'])
    tools_before = tool_snapshot(receipt)
    lib = dense.configure_silu_library(dense.configure_library(ctypes.CDLL(receipt['library'])))
    require(lib.td_reset() == 0, 'fresh process C Matrix reset')
    service = binding.ProfiledMatrixService(lib, profiles.QWEN2_QKV_PROFILE)
    shared = scalar.ScalarService()
    backend = OfficialPV32AttentionOwner(service, shared)
    rows = config['rows']
    require(type(rows) is int and rows == (2 if config['record'] else 8), 'recorded M2/unrecorded M8 scope required')
    q = tuple(scalar.word((i % 17 - 8) / 32) for i in range(rows * 1536))
    k = tuple(scalar.word((i % 13 - 6) / 32) for i in range(rows * 256))
    v = tuple(scalar.word((i % 19 - 9) / 32 + .0007) for i in range(rows * 256))
    stimulus = {name: struct.pack('<%dI' % len(words), *words) for name, words in (('q', q), ('k', k), ('v', v))}
    fixture = attention_fixture(rows)
    memory = prefix.PhysicalMemory(fixture, {n: r.base.bytes_provider(raw) for n, raw in stimulus.items()})
    region = fixture.config.regions[3]
    selected = owner_module.DenseReductionOwner if config['mode'] == 'old' else DenseIdleOwnerV1
    owner = selected(original.numeric.model.PrefixWorkspace(region.base, region.limit - region.base,
        fixture.config.epoch + 1, 2560), enable_dense_drain=True, enable_k_window=True,
        enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
    public_class = original.PublicExecution if config['mode'] == 'old' else DenseIdlePublic3ExecutionV1
    trace = original.numeric.CappedTrace(out / 'host_trace.jsonl')
    x = public_class(public.PublicFrontend(memory.metadata_port(), fixture.config), owner, trace,
        config['deadline'], host=public.group.HostControl(enabled=True, legacy_prefix=True, legacy_attention=True),
        prefix_owner=execution.OfficialPrefixOwner(shared), attention_owner=backend, matrix_service=service)
    job = x.advance_to_request()['ordinary_request']
    require(job.kind == 'Attention' and job.m == rows, 'real decoded synthetic public3 geometry')
    identity = method_identities()
    before = (x.counts['host_model_ticks'], owner.clock, owner.tiles.cycle,
              int(lib.matrix_normal_fmas()), service.counts['normal_steps'])
    diag_before = diagnostics(owner)
    capture = PV32AttentionObservation(backend, source_sha256=sources) if config['observer'] else None
    recorder = None
    dense_capture = DenseReturnCapture(owner, source_sha256=sources) if config['record'] else None
    edge_stream = gzip.open(out / 'edges.pickle.gz', 'wb', compresslevel=1) if config['record'] else None
    if edge_stream is not None:
        recorder = EdgeRecorder(edge_stream, dense_capture=dense_capture, execution=x, memory=memory)
        (out / 'dense_sram_baseline.pickle').write_bytes(pickle.dumps(recorder.invariant.baseline, protocol=4))
    driver_x = RecordedPublicEdges(x, memory, recorder) if recorder else x
    try:
        with capture if capture else nullcontext(), dense_capture if dense_capture else nullcontext():
            started = time.perf_counter()
            cpu = time.process_time()
            detail = suffix.execute_attention_owner(driver_x, memory, job)
            cpu_seconds = time.process_time() - cpu
            wall_seconds = time.perf_counter() - started
    finally:
        if edge_stream is not None:
            edge_stream.close()
    bank_seal = None if recorder is None else recorder.invariant.seal()
    after = (x.counts['host_model_ticks'], owner.clock, owner.tiles.cycle,
             int(lib.matrix_normal_fmas()), service.counts['normal_steps'])
    actual = dict(zip(('host_edges', 'dense_edges', 'tile_edges', 'c_fmas', 'normal_steps'),
                      (a - b for a, b in zip(after, before))))
    actual.update(driver_ticks=detail['accepted']['ticks'], reads=detail['accepted']['read_requests'],
                  acks=detail['accepted']['write_acks'])
    require(actual['host_edges'] == actual['dense_edges'] == actual['tile_edges'] == actual['driver_ticks'] + 1,
            'one actual Host/Dense/Tile edge per driver call including admission')
    # Independent schedule expectations, not counter assignments: causal pairs
    # per head = m(m+1)/2; QK has eight steps, PV32 four; each step executes
    # 512 actual C FMAs. Reads = 8 Q per token plus 16 K/V per causal pair.
    causal = rows * (rows + 1) // 2
    expected = dict(c_fmas=12 * causal * 12 * 512, normal_steps=12 * causal * 12,
                    reads=12 * (8 * rows + 16 * causal), acks=12 * rows * 8)
    require(all(actual[k] == v for k, v in expected.items()), 'source-derived actual work mismatch: ' + repr(actual))
    if rows == 8:
        require(actual == dict(host_edges=44037, dense_edges=44037, tile_edges=44037,
                              c_fmas=2654208, normal_steps=5184, driver_ticks=44036, reads=7680, acks=768),
                'actual synthetic M8 exact schedule mismatch: ' + repr(actual))
    require(detail['result']['status'] is None and backend.state == owner.state == 'idle'
            and service.owner is None and shared.client is None and backend.matrix_client is None
            and memory.pending is None, 'successful genuine all-debt terminal')
    raw = memory.raw(job.dst, job.write_bytes)
    (out / 'att.f32le').write_bytes(raw)
    resource_address = service.resource_address
    require(resource_address == lib.matrix_accumulator_address(), 'actual shared Matrix accumulator root changed')
    raw_owner_report = backend.report()
    save(out / 'raw_backend_reports.json', dict(owner=raw_owner_report, detail_backend=detail['backend'],
                                               verified_actual_accumulator_address=resource_address))
    comparable_detail = dict(detail, backend=normalized_backend_report(detail['backend'], resource_address))
    functional = dict(detail=comparable_detail, actual=actual, owner=normalized_backend_report(raw_owner_report, resource_address), matrix=service.report(),
        scalar_calls=dict(shared.calls), physical=memory.report(), public=full_public_state(x, memory),
        output_sha256=hashlib.sha256(raw).hexdigest())
    save(out / 'functional.json', functional)
    observed = None
    if capture:
        observed = capture.report()
        require(observed['status'].startswith('COMPLETE_'), 'observer coverage incomplete')
        buffers = {name: dict(shape=field['shape'], words=field['words'].tobytes(),
                   presence=bytes(field['observed']), frequency=field['frequency'].tobytes(),
                   writes=field['writes'], repeats=field['repeats']) for name, field in capture.fields.items()}
        (out / 'observer_buffers.pickle').write_bytes(pickle.dumps(buffers, protocol=4))
        save(out / 'observation.json', observed)
    diag_after = diagnostics(owner)
    diag_delta = {key: diag_after[key] - diag_before[key] for key in ('fast', 'fallback')}
    if config['mode'] == 'new':
        require(diag_delta == dict(fast=actual['dense_edges'], fallback=0), 'new Attention idle route was not hit on every edge')
    require(source_manifest() == sources and tool_snapshot(receipt) == tools_before, 'source/tool drift in child')
    result = dict(status='PASS_SYNTHETIC_PUBLIC3_ARM', rows=rows, geometry=dict(heads=12, kv_heads=2, head_dim=128, causal=True), mode=config['mode'], observer=config['observer'],
        recorded=config['record'], wall_seconds=wall_seconds, cpu_seconds=cpu_seconds,
        process_id=os.getpid(), affinity=sorted(os.sched_getaffinity(0)), environment={k: os.environ[k] for k in THREAD_KEYS},
        tools=tools_before, source_sha256=sources, loaded_methods=identity, actual=actual,
        actual_matrix_resource_address=resource_address, diagnostics=diag_delta, recording_scope='external per-edge' if recorder else 'none',
        recorded_edges=None if recorder is None else recorder.edges,
        dense_return_capture=None if dense_capture is None else dict(returns=dense_capture.returns, consumed=dense_capture.consumed, closed=dense_capture.closed, error=dense_capture.error),
        factored_sram_invariant=bank_seal, recorder_uncompressed_bytes=None if recorder is None else recorder.uncompressed_bytes,
        fixture_identity=fixture_identity(fixture, job),
        stimulus={n: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()) for n, data in stimulus.items()},
        stalls=dict(memory=5, matrix_request=7, matrix_result=11, service_result=13, service_done=17, final_ack=5),
        functional_sha256=sha(out / 'functional.json'), output_sha256=hashlib.sha256(raw).hexdigest(),
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(out / 'RESULT.json', result)
    trace.close()


def validate_output(value):
    path = Path(value).absolute()
    require(path.resolve() == path and path.parent == OUTPUT_ROOT and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', path.name), 'fresh direct-child probe output required')
    require(not path.exists(), 'probe output already exists')
    return path


def run(out, manifest, receipt_path, affinity):
    """Supervisor enforces a wall bound across preparation and all children."""
    started = time.monotonic()
    deadline = started + OUTER_SECONDS
    out = validate_output(out)
    review = reviewed_manifest(manifest)
    sources = review['source_sha256']
    require(len(affinity) == 1 and set(affinity) <= os.sched_getaffinity(0), 'one permitted pinned CPU required')
    require(all(os.environ.get(k) == '1' for k in THREAD_KEYS), 'env=1 required before supervisor startup')
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu as dense
    receipt = dense.verify_library(receipt_path)
    tools_before = tool_snapshot(receipt)
    out.mkdir()
    report = dict(status='STARTED_M2_RECORDED_M8_ABBA', recorded_rows=2, timing_rows=8, scope='public3 Dense-idle: complete M2 per-edge equivalence; M8 observed ABBA final-state equality',
                  outer_budget_seconds=45, old_m128_restarted=False, official_numeric=False,
                  hardware_cycles=None, hardware_utilization=None, architecture_speedup_claim=False,
                  source_sha256_before=sources, tools_before=tools_before, conditions=[],
                  publication_metadata_sha256={str(p.relative_to(ROOT)): sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ('.md', '.json')},
                  timing_order=['old', 'new', 'new', 'old'], observer_off='NOT_IN_AUTHORIZED_SIX_ARM_SCOPE',
                  edge_scope='actual Attention/Dense/Host events and all Dense/Tile/public fields per edge; source-bound factored SRAM baseline invariant with full initial/final values; backend fields labeled live summary')
    def checkpoint():
        report['outer_wall_seconds'] = time.monotonic() - started
        save(out / 'RESULT.json', report)
    checkpoint()
    try:
        for name, digest in sources.items():
            raw = (ROOT / name).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == digest, 'source freeze drift')
            target = out / 'frozen_sources' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        save(out / 'reviewed_source_manifest.json', review)
        save(out / 'library_receipt.json', receipt)
        durations = []
        def condition(mode, observe, record):
            index = len(report['conditions'])
            child_out = out / ('arm_%02d_%s_%s_%s' % (index, mode, 'observed' if observe else 'off', 'recorded' if record else 'timed'))
            config = dict(mode=mode, observer=observe, record=record, rows=2 if record else 8, out=str(child_out),
                          review_manifest=str(Path(manifest).resolve()), library_receipt=str(Path(receipt_path).resolve()),
                          deadline=deadline - FINALIZE_RESERVE, affinity=affinity)
            path = out / ('arm_%02d.json' % index)
            save(path, config)
            remaining = deadline - FINALIZE_RESERVE - time.monotonic()
            require(remaining > 0, 'outer budget exhausted before arm')
            t0 = time.monotonic()
            command = [str(Path(sys.executable).resolve()), '-B', '-m', 'candidates.qwen2_attention_idle_fastpath.probe',
                       '--actual-budget', '--child-config', str(path)]
            with (out / ('arm_%02d.log' % index)).open('wb') as log:
                process = subprocess.Popen(command, cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=remaining)
                except BaseException:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise
            duration = time.monotonic() - t0
            durations.append(duration)
            require(code == 0, 'child failed; inspect ' + str(out / ('arm_%02d.log' % index)))
            result = json.loads((child_out / 'RESULT.json').read_text())
            require(result['tools'] == tools_before and result['source_sha256'] == sources, 'cross-process tool/source drift')
            result.update(directory=str(child_out), process_wall_seconds=duration)
            report['conditions'].append(result)
            checkpoint()
            return child_out, result
        first, first_result = condition('old', True, True)
        second, second_result = condition('new', True, True)
        # Load the original module names before internal pickled frame inspection.
        from candidates.qwen2_live_attention_model_m128.runner import dependencies
        dependencies()
        report['m2_equal_recorded_edges'] = compare_frames(first / 'edges.pickle.gz', second / 'edges.pickle.gz', out / 'FIRST_DIVERGENCE.json', first_result['actual']['dense_edges'])
        baseline = json.loads((first / 'functional.json').read_text())
        baseline_observer = (first / 'observer_buffers.pickle').read_bytes()
        baseline_raw = (first / 'att.f32le').read_bytes()
        check_equal(baseline_raw, (second / 'att.f32le').read_bytes(), out / 'FIRST_DIVERGENCE.json', 'actual_output_bytes_divergence')
        check_equal(baseline, json.loads((second / 'functional.json').read_text()), out / 'FIRST_DIVERGENCE.json', 'full_public_functional_divergence')
        check_equal(baseline_observer, (second / 'observer_buffers.pickle').read_bytes(), out / 'FIRST_DIVERGENCE.json', 'observer_buffer_divergence')
        check_equal(json.loads((first / 'observation.json').read_text()), json.loads((second / 'observation.json').read_text()), out / 'FIRST_DIVERGENCE.json', 'observer_report_divergence')
        report['m2_complete_recorded_equivalence'] = True
        measured = []
        baseline = baseline_observer = baseline_raw = None
        for mode in ('old', 'new', 'new', 'old'):
            directory, result = condition(mode, True, False)
            if baseline is None:
                baseline = json.loads((directory / 'functional.json').read_text())
                baseline_observer = (directory / 'observer_buffers.pickle').read_bytes()
                baseline_raw = (directory / 'att.f32le').read_bytes()
            check_equal(baseline, json.loads((directory / 'functional.json').read_text()), out / 'FIRST_DIVERGENCE.json', 'timing_arm_functional_divergence')
            check_equal(baseline_observer, (directory / 'observer_buffers.pickle').read_bytes(), out / 'FIRST_DIVERGENCE.json', 'timing_arm_observer_divergence')
            check_equal(baseline_raw, (directory / 'att.f32le').read_bytes(), out / 'FIRST_DIVERGENCE.json', 'timing_arm_raw_bytes_divergence')
            measured.append(result)
        report['observer_on_pairs'] = [dict(order='AB', old_wall=measured[0]['wall_seconds'], new_wall=measured[1]['wall_seconds'],
                                            old_cpu=measured[0]['cpu_seconds'], new_cpu=measured[1]['cpu_seconds']),
                                        dict(order='BA', old_wall=measured[3]['wall_seconds'], new_wall=measured[2]['wall_seconds'],
                                            old_cpu=measured[3]['cpu_seconds'], new_cpu=measured[2]['cpu_seconds'])]
        report['observer_on_medians'] = {mode: dict(wall=statistics.median(r['wall_seconds'] for r in measured if r['mode'] == mode),
                    cpu=statistics.median(r['cpu_seconds'] for r in measured if r['mode'] == mode)) for mode in ('old', 'new')}
        report['repeatable_improvement'] = all(p['new_wall'] < p['old_wall'] and p['new_cpu'] < p['old_cpu'] for p in report['observer_on_pairs'])
        require(len(report['conditions']) == 6, 'exact authorized six-arm scope')
        report['source_sha256_after'] = source_manifest()
        report['tools_after'] = tool_snapshot(receipt)
        require(report['source_sha256_after'] == sources and report['tools_after'] == tools_before, 'final source/tool drift')
        require(time.monotonic() < deadline, 'outer bound exceeded during finalization')
        report.update(status='PASS_M2_PER_EDGE_M8_FINAL_STATE_ABBA_ONLY',
                      timing_scope='unrecorded observed ABBA, each arm isolated; no component timers',
                      recording_overhead='separate functional arms; not subtracted from unrecorded timings',
                      m8_per_edge_equality_claim=False, m8_final_state_observer_raw_equality=True, full_public21_budget_established=False, m128_ready=False)
        checkpoint()
    except BaseException as error:
        report.update(status='FAILED_M2_RECORDED_M8_ABBA', error=repr(error), traceback=traceback.format_exc())
        checkpoint()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual-budget', action='store_true')
    parser.add_argument('--out')
    parser.add_argument('--review-manifest')
    parser.add_argument('--library-receipt')
    parser.add_argument('--cpu', type=int)
    parser.add_argument('--child-config', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.actual_budget:
        require(all(value is None for value in (args.out, args.review_manifest, args.library_receipt, args.cpu, args.child_config)),
                'runtime arguments require explicit --actual-budget')
        print(json.dumps(dict(status='NOT_EXECUTED', default_owner='old', numeric_executed=False)))
        return 0
    if args.child_config:
        require(all(value is None for value in (args.out, args.review_manifest, args.library_receipt, args.cpu)), 'child arguments mixed with supervisor')
        run_condition(json.loads(Path(args.child_config).read_text()))
    else:
        require(args.out and args.review_manifest and args.library_receipt and args.cpu is not None,
                'fresh output, reviewed source manifest, verified library receipt and pinned CPU required')
        # Reserve half a second for child reaping and failure-report writes.
        # The executor should additionally use a 45-second process-group timeout.
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'refuse an existing wall timer')
        previous = signal.getsignal(signal.SIGALRM)
        def expired(signum, frame):
            raise TimeoutError('44.5-second supervisor wall alarm; 45-second outer bound')
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, OUTER_SECONDS - 0.5)
        try:
            run(args.out, args.review_manifest, args.library_receipt, [args.cpu])
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
