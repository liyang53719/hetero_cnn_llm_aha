"""Source-only M<=128 Fixed93 observer adapter; no DUT or native import.

Construct around one already admitted owner operation. Observation never invokes
an owner/service primitive; sys.settrace reads actual locals/returns. Candidate
normalization evaluates once and reuses seven times; all eight
FP32 probability operands are read at the actual pre-BF16 Matrix boundary.
TEMP source-only candidate: not integrated or admitted as a fullblock run.
"""
from array import array
import ast
from collections import Counter
from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
import sys
import threading
import types
from .source_guard import (OWNER_MODULE, CLIENT_MODULE, MATRIX_MODULE, ARITHMETIC_MODULE,
    PROFILED_MODULE, OFFICIAL_MATRIX_MODULE, PROFILE_MODULE, REVIEWED_MANIFEST_SHA256,
    CANDIDATE_IDENTITY, PREDECESSOR_REVIEWED_MANIFEST_SHA256,
    SELECTED, SENTINEL, require, sha, verify_closure, verify_loaded)
from .event_stream import EventStream, CODEC_PINS


def field_shapes(m):
    require(type(m) is int and 1 <= m <= 128, 'bounded M<=128 fields only')
    shapes = {name: (12, m, m) for name in ('dot_raw', 'dot_bf16', 'scale_fp32', 'score_bf16', 'score_difference', 'exp_fp32', 'denominator_step')}
    shapes.update({name: (12, m, m, 16) for name in ('packed_stripes', 'fold_before', 'fold_after')})
    shapes.update({name: (12, m, m, 8) for name in ('probability_fp32', 'probability_bf16')})
    shapes.update(pv_key_raw=(12, m, m, 8, 16), normalizer=(12, m, 3),
                  pv_final_raw=(12, m, 128), pv_bf16=(12, m, 128))
    return shapes


def field_storage_bytes(m):
    from math import prod
    return 5 * sum(prod(shape) for shape in field_shapes(m).values())


def native_snapshot(library):
    """Inspect only already configured C function instances; never resolve/call one.

    CDLL stores its callable _FuncPtr *class* alongside the 33 configured
    instances. Its class-level argtypes/restype are descriptors, not signatures.
    Class metadata is bound separately and every symbol uses an explicit ABI.
    """
    C = sys.modules.get('ctypes')
    require(type(C) is types.ModuleType and type(library) is C.CDLL,
            'exact already loaded ctypes CDLL required')
    namespace = vars(library)
    function_type = namespace.get('_FuncPtr')
    require(type(function_type) is type(C._CFuncPtr) and
            function_type.__bases__ == (C._CFuncPtr,), 'exact CDLL function pointer class required')
    type_members = dict(vars(function_type))
    for name in ('argtypes', 'restype'):
        descriptor = vars(C._CFuncPtr).get(name)
        require(type(descriptor) is types.GetSetDescriptorType and
                inspect.getattr_static(function_type, name) is descriptor,
                'native signature descriptor overridden: ' + name)
    require(type(type_members.get('_flags_')) is int and
            type_members['_flags_'] == C._FUNCFLAG_CDECL and
            type_members.get('_restype_') is C.c_int, 'CDLL function class ABI metadata changed')
    u, q, p16, p32 = C.c_uint, C.c_uint64, C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
    arguments = {
        'td_reset': (), 'td_group': (u,) * 3, 'td_seed_begin': (u,),
        'td_seed_beat': (u, u, p32), 'td_seed_commit': (u,),
        'td_step': (u,) * 6 + (p16, p16, p32),
        'td_reference': (p32, p16, p32, u),
        'matrix_guard_enable': (), 'matrix_acquire': (u, q),
        'matrix_owner_reply_retire': (u, q), 'matrix_release': (u, q),
        'matrix_abort': (), 'matrix_done_ready': (),
        'matrix_result_retire': (q, u, u), 'matrix_done_retire': (q, u, u),
        'matrix_seed_ack': (q, u, u), 'matrix_legacy_reply_retire': (q,),
        'matrix_normal_group': (u,) * 4, 'matrix_normal_group_v1': (u,) * 5,
        'matrix_normal_step': (u,) * 6 + (p16, p16, p32),
        'sf_vector': (p32,) * 6, 'sf_vector_bf16_v1': (p32,) * 6,
        'sf_reset': (), 'sf_reset_bf16_v1': (),
        'sf_reference': (p32, p32, p32, u),
    }
    expected = {name: (args, C.c_int) for name, args in arguments.items()}
    for name in ('matrix_ticket', 'matrix_dense_fmas', 'matrix_normal_fmas',
                 'sf_bf16_v1_calls', 'sf_bf16_v1_failures'):
        expected[name] = ((), q)
    for name in ('matrix_state', 'matrix_accumulator_bytes'):
        expected[name] = ((), u)
    expected['matrix_accumulator_address'] = ((), C.c_size_t)
    require(len(expected) == 33 and
            {name for name, obj in namespace.items() if callable(obj)} == set(expected) | {'_FuncPtr'},
            'complete configured native callable inventory changed')
    functions, signatures = {}, {}
    for name, (arguments, result_type) in expected.items():
        function = namespace.get(name)
        require(type(function) is function_type, 'exact configured native function instance required: ' + name)
        arguments_now, result_now = function.argtypes, function.restype
        require(type(arguments_now) in (list, tuple) and
                len(arguments_now) == len(arguments) and
                all(actual is expected for actual, expected in zip(arguments_now, arguments)) and
                result_now is result_type, 'configured native signature changed: ' + name)
        functions[name] = function
        signatures[name] = (tuple(arguments_now), result_now)
    return function_type, type_members, functions, signatures


class Fixed93FullblockAttentionObservation:
    def __init__(self, owner, source_root, source_manifest, destination, *, trace_limits, trace_dispatcher=None):
        required = {'schema', 'max_m', 'max_field_bytes', 'codec_root', 'codec_limits',
                    'source_manifest_sha256', 'native_library_path', 'native_library_sha256'}
        require(type(trace_limits) is dict and set(trace_limits) == required, 'explicit exact trace_limits schema required')
        require(array('I').itemsize == 4, 'uint32 observation storage required')
        require(trace_limits['schema'] == 'fixed93-attention-pv-reuse-trace-limits-v1', 'trace limits schema')
        require(type(trace_limits['max_m']) is int and 1 <= trace_limits['max_m'] <= 128, 'trace M cap')
        require(type(trace_limits['max_field_bytes']) is int and
                field_storage_bytes(trace_limits['max_m']) <= trace_limits['max_field_bytes'], 'field storage budget missing/too small')
        require(type(trace_limits['codec_limits']) is dict and set(trace_limits['codec_limits']) ==
                {'contexts', 'bank_bytes', 'max_chunk', 'max_metadata', 'max_record', 'max_records', 'max_output', 'max_raw'},
                'all codec limits must be explicit')
        self.trace_limits = json.loads(json.dumps(trace_limits))
        require(trace_limits['max_m'] < 128 or trace_dispatcher is not None, 'M128 requires wholeblock dispatcher composition')
        self.dispatcher, self.registration = trace_dispatcher, None
        self.owner, self.root, self.manifest = owner, Path(source_root).resolve(), Path(source_manifest).resolve()
        self.destination = Path(destination).resolve()
        self.closure_sha256, self.sources = verify_closure(self.root, self.manifest, trace_limits['source_manifest_sha256'])
        self.loaded_checked = verify_loaded(owner, self.root)
        self.instrumentation = {p.name: sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')}
        self.services = owner.matrix, owner.scalar
        self.library = owner.matrix.lib
        self.resource_address = owner.matrix.resource_address
        self.profile = owner.matrix.profile
        self.profile_snapshot = asdict(self.profile)
        self.binding_snapshot = dict(owner.matrix._bindings)
        self.native_path = Path(trace_limits['native_library_path']).resolve()
        require(Path(self.library._name).resolve() == self.native_path and
                sha(self.native_path.read_bytes()) == trace_limits['native_library_sha256'], 'loaded native library file identity missing/drifted')
        (self.native_type, self.native_type_members, self.native_functions,
         self.native_signatures) = native_snapshot(self.library)
        self.job_object = None
        self.codes = {name: getattr(owner, name).__func__.__code__ for name in
                      ('_attention', '_matrix_step', '_op', '_write', '_advance', '_finish', '_fault', 'tick')}
        client = sys.modules[CLIENT_MODULE]
        self.codes['packed_tick'] = client.PackedQkClient.tick.__code__
        self.codes['packed_commit'] = client.PackedQkClient.commit.__code__
        self.points = {}
        for method in ('_attention', '_matrix_step', '_write', '_advance', 'tick'):
            code = self.codes[method]
            tree = ast.parse(Path(code.co_filename).read_text())
            candidates = [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef) and x.name == method
                          and x.lineno == code.co_firstlineno]
            require(len(candidates) == 1, 'trace method source location mismatch')
            self.points[method] = {ast.unparse(x): x.lineno for x in ast.walk(candidates[0]) if isinstance(x, ast.stmt)}
        self.line = {}
        def point(label, method, beginning):
            found = [v for k, v in self.points[method].items() if k.startswith(beginning)]
            require(len(found) == 1, 'ambiguous trace point: ' + label)
            self.line[label] = found[0]
        point('qk_check', '_attention', 'if any((not finite(x) for x in lanes)):')
        point('qk_pass', '_attention', 'total = 0')
        point('fold', '_attention', "total = self._op('add', total, lane)")
        point('dot', '_attention', "dot = self._op('bf', total)")
        point('scale', '_attention', "score = self._op('bf', self._op('mul', dot, 1035273459))")
        point('score', '_attention', 'scores.append(score)')
        point('exp', '_attention', 'probabilities.append(probability)')
        point('denominator', '_attention', "total = self._op('add', total, probability)")
        point('inverse', '_attention', "inverse = self._op('div', 1065353216, total)")
        point('normalize', '_attention', "probability = self._op('mul', probability, inverse)")
        point('output', '_attention', 'yield from self._write(')
        # A generator call event repeats on resume. This first-statement line
        # executes exactly once for each real helper invocation, before BF16.
        point('matrix_input_fp32', '_matrix_step', "a = tuple((self._op('bf', x) >> 16 for x in a))")
        point('matrix_input', '_matrix_step', 'result = (yield LegacyRequest(')
        point('pv_check', '_matrix_step', 'if lanes is not None and any((not finite(x) for x in lanes)):')
        point('pv_pass', '_matrix_step', 'return lanes')
        point('store_check', '_write', 'if len(words) != LANES or any((not finite(v) for v in words)):')
        point('store_pass', '_write', 'yield (address, struct.pack(')
        point('write_ack', 'tick', "self.counts['write_acks'] += 1")
        self.thread = threading.get_ident()
        self.active = self.closed = self.disarmed = False
        self.started = 0
        self.job = self.terminal = self.retirement = None
        self.error = None
        self.fields = {}
        self.fold_coord, self.fold_index = None, 0
        self.event_counts = Counter()
        self.pending_normalization = None
        self.normalization_reuse_count = 0
        self.lease, self.last_packed_tag, self.completed_groups = None, -1, 0
        self.pending_memory = None
        self.last_memory_tag = -1
        self.last_ticket = None
        self.client_identity = None
        self.identity_tick_frame = None
        self.stream = None
        self.service_pending_result = None
        self.service_group = None
        self.service_release_seen = False
        self.start_epoch = owner.matrix.epoch
        self.stream_seal = None
        self.saved = False
        self._callback = self._trace
        matrix_type = sys.modules[MATRIX_MODULE].MatrixService
        self.service_codes = {inspect.getattr_static(matrix_type, name).__code__: name for name in
            ('acquire', 'accept_group', 'accept_step', 'retire_result', 'retire_done',
             'retire_legacy_reply', 'abort', 'release', 'retire_owner_response', 'reset')}
        self.ticket_code = inspect.getattr_static(matrix_type, 'ticket').fget.__code__
        self.scalar_code = sys.modules[ARITHMETIC_MODULE].ScalarService.op.__code__
        self.exp_code = sys.modules['candidates.qwen2_resident_matrix.ffn_attention.scalar_recipe'].exp_negative.__code__
        self.exp_nodes, self.exp_coord = None, None
        self.legacy_code = sys.modules[MATRIX_MODULE].LegacyMatrixClient.tick.__code__
        self.all_codes = frozenset((*self.codes.values(), *self.service_codes, self.ticket_code,
                                   self.scalar_code, self.exp_code, self.legacy_code))
        point('memory_accept', 'tick', "self.counts['write_requests' if self.request.write else 'read_requests'] += 1")
        point('memory_match', 'tick', 'self.memory_pending = False')
        # event-only-owner-lines-v1: exact source-derived evidence consumers.
        # Scalar returns consume caller f_lineno independently of line delivery.
        self.evidence_lines = types.MappingProxyType({
            self.codes['_attention']: frozenset(self.line[name] for name in
                ('qk_check', 'qk_pass', 'score', 'exp', 'output')),
            self.codes['_matrix_step']: frozenset(self.line[name] for name in
                ('matrix_input_fp32', 'matrix_input', 'pv_check', 'pv_pass')),
            self.codes['tick']: frozenset(self.line[name] for name in
                ('memory_accept', 'memory_match', 'write_ack')),
            self.codes['_write']: frozenset(self.line[name] for name in
                ('store_check', 'store_pass')),
        })
        require(len(self.evidence_lines) == 4 and sum(map(len, self.evidence_lines.values())) == 14,
                'exact fourteen owner line consumers required')


    def _validate(self):
        require(verify_closure(self.root, self.manifest, self.trace_limits['source_manifest_sha256']) ==
                (self.closure_sha256, self.sources), 'closure inventory changed during observation')
        require(verify_loaded(self.owner, self.root) == self.loaded_checked, 'loaded dependency inventory changed')
        require(self.instrumentation == {p.name: sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')},
                'observation adapter source changed')
        require(sha(self.native_path.read_bytes()) == self.trace_limits['native_library_sha256'], 'native file bytes changed')
        self._identity()

    def _identity(self):
        require(threading.get_ident() == self.thread, 'observation thread changed')
        require(self.owner.matrix is self.services[0] and self.owner.scalar is self.services[1] and
                self.owner.matrix.lib is self.library and self.owner.matrix.resource_address == self.resource_address,
                'owned service/native resource identity changed')
        require(self.owner.matrix.profile is self.profile and asdict(self.profile) == self.profile_snapshot,
                'QKV profile replaced/mutated')
        require(self.owner.matrix._bindings.keys() == self.binding_snapshot.keys() and all(
                self.owner.matrix._bindings[tag] is binding for tag, binding in self.binding_snapshot.items()),
                'public Dense role bindings changed during Attention')
        native_type, type_members, functions, signatures = native_snapshot(self.library)
        require(native_type is self.native_type and type_members.keys() == self.native_type_members.keys() and
                all(value is self.native_type_members[name] for name, value in type_members.items()) and
                functions.keys() == self.native_functions.keys() and
                all(function is self.native_functions[name] for name, function in functions.items()) and
                signatures == self.native_signatures, 'native entrypoint/class identity/signature changed')
        if self.job_object is not None:
            require(self.owner.job is self.job_object, 'accepted Attention Job instance replaced')
        client = self.owner.matrix_client
        if client is not None:
            module, matrix = sys.modules[CLIENT_MODULE], sys.modules[MATRIX_MODULE]
            require(type(client) is module.Fixed93MatrixClient and client.service is self.services[0] and
                    type(client.packed) is module.PackedQkClient and type(client.legacy) is matrix.LegacyMatrixClient and
                    client.packed.owner is self.owner and client.legacy.owner is self.owner and
                    client.packed.service is self.services[0] and client.legacy.service is self.services[0],
                    'exact owned client/service binding changed')
            ids = (id(client), id(client.packed), id(client.legacy))
            if self.client_identity is None:
                self.client_identity = ids
            require(ids == self.client_identity, 'owned Matrix client instance replaced')

    def _cheap_identity(self):
        require(threading.get_ident() == self.thread, 'observation thread changed')
        require(self.owner.matrix is self.services[0] and self.owner.scalar is self.services[1] and
                self.owner.matrix.lib is self.library and self.owner.matrix.resource_address == self.resource_address,
                'owned service/native resource identity changed')
        require(self.owner.matrix.profile is self.profile,
                'QKV profile replaced')
        require(self.owner.matrix._bindings.keys() == self.binding_snapshot.keys() and all(
                self.owner.matrix._bindings[tag] is binding for tag, binding in self.binding_snapshot.items()),
                'public Dense role bindings changed during Attention')
        if self.job_object is not None:
            require(self.owner.job is self.job_object, 'accepted Attention Job instance replaced')
        client = self.owner.matrix_client
        if client is not None:
            module, matrix = sys.modules[CLIENT_MODULE], sys.modules[MATRIX_MODULE]
            require(type(client) is module.Fixed93MatrixClient and client.service is self.services[0] and
                    type(client.packed) is module.PackedQkClient and type(client.legacy) is matrix.LegacyMatrixClient and
                    client.packed.owner is self.owner and client.legacy.owner is self.owner and
                    client.packed.service is self.services[0] and client.legacy.service is self.services[0],
                    'exact owned client/service binding changed')
            ids = (id(client), id(client.packed), id(client.legacy))
            if self.client_identity is None:
                self.client_identity = ids
            require(ids == self.client_identity, 'owned Matrix client instance replaced')

    def _integrity(self, frame, event, code):
        # tick-boundary-metadata-integrity-v1: only deep profile values and
        # native ABI metadata move to full boundaries. Ownership stays live.
        if code is self.codes['tick']:
            require(frame.f_locals.get('self') is self.owner,
                    'wrong owner instance reached tick integrity boundary')
            if event == 'call':
                require(self.identity_tick_frame is None, 'nested/reentered observed owner tick')
                self._identity()
                self.identity_tick_frame = id(frame)
                return
            require(self.identity_tick_frame == id(frame), 'unmatched observed owner tick frame')
            if event in ('return', 'exception'):
                self._identity()
                return
        if (self.identity_tick_frame is None or event not in ('call', 'line', 'return') or self.error is not None or
                (code is self.codes['_attention'] and event == 'call' and not self.started)):
            self._identity()
            return
        # No frame retention or cross-callback code cache. Prove this callback
        # is dynamically inside the one admitted, still-live tick frame.
        cursor = frame
        for _ in range(128):
            if cursor is None or id(cursor) == self.identity_tick_frame:
                break
            cursor = cursor.f_back
        require(cursor is not None and id(cursor) == self.identity_tick_frame,
                'observed callback outside active owner tick frame')
        self._cheap_identity()

    def _trace_intact(self):
        if self.dispatcher is None:
            return sys.gettrace() is self._callback
        return (threading.get_ident() == self.dispatcher.thread and self.dispatcher.failed is None and
                sys.gettrace() is self.dispatcher.callback)

    def __enter__(self):
        require(threading.get_ident() == self.thread and not self.active and not self.closed, 'observer single-use/thread violation')
        require(self.owner.state == 'idle' and not self.owner.poison and self.owner.matrix.owner is None
                and self.owner.scalar.client is None, 'observe only before an idle launch')
        if self.dispatcher is None:
            require(sys.gettrace() is None, 'an existing trace must not be replaced')
        else:
            require(self._trace_intact(), 'wholeblock dispatcher is not the installed single-thread trace')
        self._validate()
        self.stream = EventStream(self.destination, self.trace_limits)
        self.active = True
        if self.dispatcher is None:
            sys.settrace(self._callback)
        else:
            self.registration = self.dispatcher.register(self._callback, self.all_codes)
        return self

    def __exit__(self, kind, error, tb):
        intact = self._trace_intact()
        if self.dispatcher is None:
            if sys.gettrace() is self._callback:
                sys.settrace(None)
        elif self.registration is not None:
            try:
                self.dispatcher.unregister(self.registration)
            except Exception as exc:
                self.error = self.error or 'dispatcher unregister failed: ' + str(exc)
        self.active, self.closed = False, True
        if not intact:
            self.error = self.error or 'trace replaced during observation'
        if kind is not None:
            self.error = self.error or 'driver exited with an exception'
        if self.identity_tick_frame is not None:
            self.error = self.error or 'observation closed with an open owner tick frame'
            self.identity_tick_frame = None
        # Verification/stream errors cannot replace a driver exception or result.
        try:
            self._validate()
        except Exception as exc:
            self.error = self.error or str(exc)
        if self.stream is not None:
            try:
                self.stream_seal = self.stream.close()
            except Exception as exc:
                self.error = self.error or 'stream close failed: ' + str(exc)
        return False

    def _start(self):
        require(self.started == 0, 'more than one owner job')
        job = self.owner.job
        require(job is not None and type(job.m) is int and 1 <= job.m <= self.trace_limits['max_m'] and
                job.n == 1536 and job.k == 128 and job.write_bytes == job.m * 1536 * 4,
                'invalid observed Attention job geometry')
        self.started, self.job, self.job_object = 1, asdict(job), job
        require(field_storage_bytes(job.m) <= self.trace_limits['max_field_bytes'], 'field allocation exceeds reviewed cap')
        for name, shape in field_shapes(job.m).items():
            count = 1
            for size in shape:
                count *= size
            self.fields[name] = dict(shape=shape, words=array('I', [SENTINEL]) * count, frequency=bytearray(count))
        self._event('job_accepted', job_object=id(job), owner_object=id(self.owner), matrix_object=id(self.services[0]),
                    scalar_object=id(self.services[1]), epoch=self.start_epoch, **{'job_' + k: v for k, v in self.job.items()})

    def _put(self, name, indices, words):
        require(self.started == 1, 'observation occurred before job admission')
        f, offset = self.fields[name], 0
        require(len(indices) == len(f['shape']), 'observation rank mismatch')
        for i, dimension in zip(indices, f['shape']):
            require(type(i) is int and 0 <= i < dimension, 'observation coordinate out of bounds')
            offset = offset * dimension + i
        require(1 <= len(words) <= 16 and offset + len(words) <= len(f['words']), 'observation vector exceeds field')
        for i, word in enumerate(words, offset):
            require(type(word) is int and 0 <= word < 1 << 32, 'observed value is not uint32')
            require(f['frequency'][i] == 0, 'duplicate observation: ' + name)
            f['words'][i], f['frequency'][i] = word, 1

    def _event(self, kind, **values):
        # Single pass: raw event persisted first; fixed-state fence updated next.
        # A rejected fence keeps its actual event and makes final report fail.
        require(self.stream is not None, 'event sink absent')
        self.stream.emit(kind, self.owner.clock, values)
        self.event_counts[kind] += 1
        self._fence_event(kind, values)

    def _fence_event(self, kind, e):
        # After a latched failure keep raw actual drain/ACK/fault events. No
        # success-state repair or successful completeness claim is possible.
        if self.error is not None:
            return
        if kind == 'pv_normalize':
            require(self.pending_normalization is None and e['col'] == 0,
                    'normalization must occur once immediately before first use')
            coord = e['head'], e['token'], e['key']
            require(0 <= e['key'] <= e['token'] < self.job['m'], 'noncausal normalization')
            self.pending_normalization = (coord, e['fp32_word'])
        elif kind == 'pv_probability_fp32_use':
            h, t, k, use = e['head'], e['token'], e['key'], e['col'] // 16
            require(type(e['is_reuse']) is bool and e['is_reuse'] == (use > 0), 'probability reuse tag mismatch')
            if use == 0:
                require(self.pending_normalization == ((h, t, k), e['probability_word']),
                        'first actual probability use differs from actual normalization return')
                self.pending_normalization = None
            else:
                f, m = self.fields['probability_fp32'], self.job['m']
                start = ((h * m + t) * m + k) * 8
                require(self.pending_normalization is None and f['frequency'][start] == 1 and
                        f['frequency'][start + use - 1] == 1 and
                        f['words'][start] == e['probability_word'],
                        'reuse must follow and equal actual first probability use')
                self.normalization_reuse_count += 1
        elif kind == 'packed_start_fire':
            require(self.lease is None and e['tag'] > self.last_packed_tag and 1 <= e['count'] <= 16,
                    'duplicate/stale/concurrent packed lease')
            self.last_packed_tag = e['tag']
            self.lease = dict(tag=e['tag'], count=e['count'], steps=0, scores=0, state='steps')
        elif kind in ('packed_step_fire', 'packed_borrow_fire', 'score_finite_commit', 'packed_scores_committed',
                      'service_result_fire', 'service_done_fire', 'packed_completion_fire'):
            lease = self.lease
            require(lease is not None and e['tag'] == lease['tag'], 'wrong packed lease/tag')
            if kind == 'packed_step_fire':
                require(lease['state'] == 'steps' and e['index'] == lease['steps'] + 1, 'packed step order')
                lease['steps'] += 1
                if lease['steps'] == 8:
                    lease['state'] = 'final'
            elif kind == 'packed_borrow_fire':
                require(lease['state'] == 'final', 'borrow before final packed step')
                lease.update(state='borrowed', fifo_object=e['fifo_object'])
            elif kind == 'score_finite_commit':
                require(lease['state'] == 'borrowed' and lease['scores'] < lease['count'], 'score outside borrowed lease')
                lease['scores'] += 1
            elif kind == 'packed_scores_committed':
                require(lease['state'] == 'borrowed' and lease['scores'] == lease['count'] == e['count'] and
                        lease['fifo_object'] == e['fifo_object'], 'commit lost scores/FIFO identity')
                lease['state'] = 'committed'
            elif kind == 'service_result_fire':
                require(lease['state'] == 'committed', 'FIFO retired before score commit')
                lease['state'] = 'result_retired'
            elif kind == 'service_done_fire':
                require(lease['state'] == 'result_retired', 'Done retired before FIFO')
                lease['state'] = 'done_retired'
            else:
                require(lease['state'] == 'done_retired', 'packed completion before Done')
                self.lease, self.completed_groups = None, self.completed_groups + 1
        elif kind in ('memory_read_accepted', 'memory_write_accepted'):
            require(self.pending_memory is None and e['tag'] > self.last_memory_tag, 'memory outstanding debt/stale tag')
            self.pending_memory = (e['tag'], e['address'], kind == 'memory_write_accepted')
            self.last_memory_tag = e['tag']
        elif kind in ('read_response', 'write_response'):
            require(self.pending_memory == (e['tag'], e['address'], kind == 'write_response'), 'response cannot discharge foreign debt')
            require(not e['error'] and e['nbytes'] == 64, 'accepted memory error/width')
            self.pending_memory = None
        elif kind == 'owner_finish_called':
            require(e['status'] is None and self.pending_memory is None and self.lease is None and
                    e['ack_bytes'] == self.job['m'] * 1536 * 4 and not e['memory_pending'] and
                    e['packed_state'] == e['legacy_state'] == 'idle' and not e['matrix_group_open'] and
                    not e['matrix_result_present'] and not e['matrix_cached_done_present'], 'owner finish before complete zero-debt fence')
        elif kind in ('owner_fault', 'matrix_abort', 'matrix_reset', 'observed_exception'):
            raise ValueError('fault/reset/exception observed: ' + kind)
    def _context(self, frame):
        while frame is not None:
            if frame.f_code is self.codes['_attention'] and frame.f_locals.get('self') is self.owner:
                return frame.f_locals
            frame = frame.f_back
        raise ValueError('actual Attention generator caller missing')

    @staticmethod
    def _h_t_k(c):
        return c['head'], c['token'], c['key']

    def _scalar(self, frame, result):
        caller = frame.f_back
        if caller is None or caller.f_code is not self.codes['_attention']:
            return
        c, local, line = caller.f_locals, frame.f_locals, caller.f_lineno
        h, t = c['head'], c['token']
        if line == self.line['fold']:
            coord = self._h_t_k(c)
            if self.fold_coord != coord:
                require(self.fold_coord is None, 'unfinished prior fold sequence')
                self.fold_coord, self.fold_index = coord, 0
            index = self.fold_index
            self._put('fold_before', (*coord, index), (local['a'],))
            self._put('fold_after', (*coord, index), (result,))
            self.fold_index = index + 1
        elif line == self.line['dot']:
            coord = self._h_t_k(c)
            require(self.fold_coord == coord and self.fold_index == 16, 'dot without sixteen actual ordered folds')
            self.fold_coord, self.fold_index = None, 0
            self._put('dot_raw', coord, (local['a'],))
            self._put('dot_bf16', coord, (result,))
        elif line == self.line['scale']:
            self._put('scale_fp32' if local['operation'] == 'mul' else 'score_bf16', self._h_t_k(c), (result,))
        elif line == self.line['denominator']:
            self._put('denominator_step', (h, t, len(c['probabilities'])-1), (result,))
        elif line == self.line['inverse']:
            self._put('normalizer', (h, t, 0), (c['maximum'], c['total'], result))
        elif line == self.line['normalize']:
            require(c['col'] == 0 and local['operation'] == 'mul', 'extra/non-first normalization evaluation')
            self._event('pv_normalize', head=h, token=t, key=c['key'], col=c['col'],
                        exp_word=local['a'], inverse_word=local['b'], fp32_word=result)

    def _line(self, frame):
        local, line, code = frame.f_locals, frame.f_lineno, frame.f_code
        if code is self.codes['_attention']:
            if line == self.line['qk_check']:
                self._put('packed_stripes', (*self._h_t_k(local), 0), tuple(local['lanes']))
                self._event('qk_selected16_finite_check', head=local['head'], token=local['token'], key=local['key'])
            elif line == self.line['qk_pass']:
                self._event('qk_selected16_finite_pass', head=local['head'], token=local['token'], key=local['key'])
            elif line == self.line['score']:
                self._event('score_finite_commit', head=local['head'], token=local['token'], key=local['key'], tag=self.owner.matrix_client.packed.tag)
            elif line == self.line['exp']:
                coord = local['head'], local['token'], len(local['probabilities'])
                self._put('score_difference', coord, (local['difference'],))
                self._put('exp_fp32', coord, (local['probability'],))
            elif line == self.line['output']:
                self._put('pv_final_raw', (local['head'], local['token'], local['col']), tuple(local['lanes']))
                self._put('pv_bf16', (local['head'], local['token'], local['col']), tuple(local['output']))
        elif code is self.codes['_matrix_step']:
            c = self._context(frame)
            require(local['opcode'] == 0x24, 'fixed93 PV helper unexpectedly used for QK')
            coord = (*self._h_t_k(c), c['col']//16)
            require(type(c['col']) is int and 0 <= c['col'] < 128 and c['col'] % 16 == 0 and
                    0 <= c['key'] <= c['token'] < self.job['m'], 'invalid/noncausal PV use coordinate')
            if line == self.line['matrix_input_fp32']:
                # Read this invocation's actual a[0]. Never project/repeat a
                # saved Scalar result into any of the eight operand slots.
                self._put('probability_fp32', coord, (local['a'][0],))
                self._event('pv_probability_fp32_use', head=c['head'], token=c['token'], key=c['key'],
                            col=c['col'], probability_word=local['a'][0], is_reuse=c['col'] != 0)
            elif line == self.line['matrix_input']:
                self._put('probability_bf16', coord, (local['a'][0] << 16,))
                self._event('pv_bf16_input', head=c['head'], token=c['token'], key=c['key'], col=c['col'], probability_word=local['a'][0] << 16)
            elif line == self.line['pv_check']:
                if local['lanes'] is not None:
                    self._put('pv_key_raw', (*coord, 0), tuple(local['lanes']))
                self._event('pv_selected16_finite_check', head=c['head'], token=c['token'], key=c['key'], col=c['col'], has_lanes=local['lanes'] is not None)
            elif line == self.line['pv_pass']:
                self._event('pv_selected16_finite_pass', head=c['head'], token=c['token'], key=c['key'], col=c['col'])
        elif code is self.codes['tick'] and line == self.line['memory_accept']:
            q = self.owner.request
            self._event('memory_write_accepted' if q.write else 'memory_read_accepted',
                        tag=q.tag, address=q.address, write=q.write, mask=q.mask, data=q.data)
        elif code is self.codes['tick'] and line == self.line['memory_match']:
            q, r = local['q'], local['r']
            self._event('write_response' if q.write else 'read_response', tag=r.tag, address=q.address,
                        error=r.error, nbytes=r.nbytes, data=r.data, ack_bytes=self.owner.ack_bytes)
        elif code is self.codes['tick'] and line == self.line['write_ack']:
            q, r = local['q'], local['r']
            self._event('write_ack', tag=r.tag, address=q.address, error=r.error, nbytes=r.nbytes, ack_bytes=self.owner.ack_bytes)
        elif code is self.codes['_write'] and line in (self.line['store_check'], self.line['store_pass']):
            self._event('store_finite_check' if line == self.line['store_check'] else 'store_finite_pass', address=local['address'], words=tuple(local['words']))

    def _packed(self, frame, event, arg):
        client = frame.f_locals.get('self')
        require(getattr(client, 'owner', None) is self.owner and
                client is self.owner.matrix_client.packed, 'wrong packed-client instance')
        if frame.f_code is self.codes['packed_commit'] and event == 'return' and client.state == 'retire':
            self._event('packed_scores_committed', tag=client.tag, count=client.committed, fifo_object=id(client.borrowed))
        elif frame.f_code is self.codes['packed_tick'] and event == 'return' and isinstance(arg, dict):
            for key in ('packed_start_fire', 'packed_step_fire', 'packed_borrow_fire', 'service_result_fire', 'service_done_fire', 'packed_completion_fire'):
                if arg.get(key):
                    self._event(key, tag=client.tag, index=client.index, count=client.count, state=client.state,
                                fifo_object=id(arg['packed_result']) if key == 'packed_borrow_fire' else None)

    def _tick(self, frame, edge):
        if edge['job_fire'] and not self.started:
            self._start()
        if edge['response_fire']:
            require(self.terminal is None and self.started == 1, 'duplicate/unowned accepted terminal')
            self.terminal = asdict(edge['response'])
            self.retirement = dict(state=self.owner.state, poison=self.owner.poison,
                same_services=(self.owner.matrix is self.services[0] and self.owner.scalar is self.services[1]),
                same_job=self.owner.job is self.job_object and asdict(self.owner.job) == self.job, ack_bytes=self.owner.ack_bytes,
                matrix_released=self.owner.matrix.owner is None, matrix_reset_required=edge['reset_required'],
                client_retired=self.owner.matrix_client is None, memory_pending=self.owner.memory_pending,
                scalar_released=self.owner.scalar.client is None)
            self._event('owner_terminal_accepted', **self.terminal)
            # Do not clear global trace or unregister a shared dispatcher here.
            self.disarmed = True

    def _service(self, frame, event, arg):
        local, name, matrix = frame.f_locals, self.service_codes[frame.f_code], self.services[0]
        require(local.get('self') is matrix, 'wrong Matrix service instance in observed operation')
        if 'owner' in local:
            require(local['owner'] is self.owner, 'wrong owner passed to observed Matrix service')
        meta = dict(epoch=matrix.epoch, owner_object=id(self.owner), matrix_object=id(matrix),
                    owner_tag=matrix.owner_tag, mode=matrix.mode, ticket=self.last_ticket)
        if event == 'call':
            self._event('matrix_call_' + name, **meta)
            return
        if event != 'return':
            return
        meta['accepted'] = arg if type(arg) is bool else None
        if name in ('accept_group', 'accept_step'):
            obj = local['group' if name == 'accept_group' else 'step']
            meta.update(asdict(obj))
            meta['request_object'] = id(obj)
            meta['rc'] = local.get('rc')
        elif name in ('retire_result', 'retire_done'):
            obj = local['result' if name == 'retire_result' else 'done']
            meta.update({k: getattr(obj, k) for k in ('ticket', 'epoch', 'error')})
            meta['result_object' if name == 'retire_result' else 'done_object'] = id(obj)
            if name == 'retire_result':
                meta.update(context=obj.context, last=obj.last)
            else:
                meta['tag'] = obj.tag
        elif name == 'retire_legacy_reply':
            meta.update(ticket=local['ticket'], epoch=local['epoch'])
        self._event('matrix_' + name, **meta)
        if name == 'accept_group' and arg is True:
            require(self.service_group is None and self.service_pending_result is None, 'Matrix group with outstanding debt')
            self.service_group = dict(group=local['group'], index=0, epoch=matrix.epoch)
            self.event_counts['accepted_matrix_groups'] += 1
        elif name == 'accept_step' and arg is True:
            state, step = self.service_group, local['step']
            require(state is not None and self.service_pending_result is None and matrix.group is state['group'] and
                    matrix.epoch == state['epoch'] and step.index == state['index'], 'accepted Matrix step identity/order/debt')
            state['index'] += 1
            self.event_counts['accepted_matrix_steps'] += 1
            if local['rc'] == 1:
                require(matrix.result is not None, 'emitted Matrix result absent')
                self.service_pending_result = (id(matrix.result), matrix.result.ticket, matrix.result.epoch)
                self._event('matrix_result_produced', result_object=id(matrix.result), context=matrix.result.context,
                            ticket=matrix.result.ticket, epoch=matrix.result.epoch, last=matrix.result.last, error=matrix.result.error)
        elif name == 'retire_result':
            result = local['result']
            require(self.service_pending_result == (id(result), result.ticket, result.epoch), 'FIFO result instance/ticket/epoch changed')
            self.service_pending_result = None
        elif name == 'retire_done':
            state, done = self.service_group, local['done']
            require(state is not None and self.service_pending_result is None and done.epoch == state['epoch'] and
                    done.tag == state['group'].tag and state['index'] == state['group'].steps,
                    'Done before exact group steps/result or wrong epoch/tag')
            self.service_group = None
        elif name == 'release':
            require(matrix.owner is None and self.service_group is None and self.service_pending_result is None,
                    'Matrix owner released with outstanding debt')
            self.service_release_seen = True

    def _legacy(self, frame, event, arg):
        client = frame.f_locals.get('self')
        require(self.owner.matrix_client is not None and client is self.owner.matrix_client.legacy and
                client.owner is self.owner and client.service is self.services[0], 'wrong legacy client instance')
        if event == 'return' and isinstance(arg, dict):
            for key in ('request_fire', 'service_result_fire', 'service_done_fire', 'result_fire'):
                if arg.get(key):
                    self._event('legacy_' + key, tag=client.tag, index=client.index, state=client.state,
                                epoch=client.epoch, pending=client._request_pending, tracks_reply=client._tracks_reply)

    def _trace(self, frame, event, arg):
        code = frame.f_code
        closing_tick = (code is self.codes['tick'] and event == 'return' and
                        self.identity_tick_frame == id(frame))
        if code not in self.all_codes:
            return None
        if code is self.scalar_code and (frame.f_back is None or frame.f_back.f_code is not self.exp_code):
            return None
        if self.disarmed or (self.stream is not None and self.stream.failed):
            if closing_tick:
                self.identity_tick_frame = None
            return self._callback
        try:
            # Contract op-evidence-boundary-v1: these normal callbacks have
            # no scalar field/event consumer. Keep instance/thread checks, but
            # do not inspect unrelated ABI/profile metadata at these two
            # no-evidence boundaries. Exceptions retain the original path.
            if (code is self.codes['_op'] and event in ('call', 'return') and
                    (frame.f_back is None or frame.f_back.f_code is not self.codes['_attention'])):
                require(threading.get_ident() == self.thread, 'observation thread changed')
                require(frame.f_locals.get('self') is self.owner,
                        'wrong owner instance reached pinned observed method')
                return self._callback
            # This local listener filter does not alter shared line delivery.
            # Off-hook locals/ownership sampling is explicitly weaker than the
            # prior tick policy; all evidence hooks and exception paths remain.
            if (event == 'line' and code in self.evidence_lines and
                    frame.f_lineno not in self.evidence_lines[code] and
                    self.identity_tick_frame is not None and self.error is None):
                require(threading.get_ident() == self.thread, 'observation thread changed')
                require(frame.f_locals.get('self') is self.owner,
                        'wrong owner instance reached pinned observed method')
                require(code is not self.codes['tick'] or self.identity_tick_frame == id(frame),
                        'unmatched observed owner tick frame')
                cursor = frame
                for _ in range(128):
                    if cursor is None or id(cursor) == self.identity_tick_frame:
                        break
                    cursor = cursor.f_back
                require(cursor is not None and id(cursor) == self.identity_tick_frame,
                        'observed callback outside active owner tick frame')
                return self._callback
            self._integrity(frame, event, code)
            if event == 'exception':
                # StopIteration is generator control, not an operation fault.
                if arg[0] not in (StopIteration, GeneratorExit):
                    self._event('observed_exception', function=code.co_name,
                                exception_type=arg[0].__name__, detail=str(arg[1])[:512])
            if code in self.service_codes:
                self._service(frame, event, arg)
            elif code is self.ticket_code:
                require(frame.f_locals.get('self') is self.services[0], 'wrong inherited ticket getter instance')
                if event == 'return':
                    require(type(arg) is int and arg >= 0, 'ticket getter invalid return')
                    self.last_ticket = arg
            elif code is self.exp_code:
                require(frame.f_locals.get('scalar') is self.services[1] and frame.f_locals.get('client') is self.owner,
                        'wrong exp caller/service binding')
                if event == 'call':
                    require(self.exp_nodes is None, 'nested/reentered exp graph')
                    context = self._context(frame)
                    self.exp_nodes = []
                    self.exp_coord = (context['head'], context['token'], len(context['probabilities']))
                elif event == 'return' and type(arg) is int:
                    expected = 1 if (frame.f_locals['a'] & 0x7fffffff) >= 0x42a00000 else 17
                    require(self.exp_nodes is not None and len(self.exp_nodes) == expected, 'missing/extra actual exp primitive')
                    self.stream.emit_exp_nodes(self.owner.clock, *self.exp_coord, tuple(self.exp_nodes), arg)
                    self.event_counts['exp_nodes'] += 1
                    self.event_counts['exp_actual_primitives'] += expected
                    self.exp_nodes, self.exp_coord = None, None
            elif code is self.scalar_code:
                require(frame.f_locals.get('self') is self.services[1] and frame.f_locals.get('client') is self.owner,
                        'wrong exp ScalarService/client instance')
                if event == 'return' and type(arg) is int:
                    local = frame.f_locals
                    require(self.exp_nodes is not None and len(self.exp_nodes) < 17 and local['policy'] == 'vector',
                            'exp primitive outside bounded vector graph')
                    index = len(self.exp_nodes)
                    operation = 'mul' if index == 0 or index == 16 or index % 2 == 0 else 'add'
                    require(local['operation'] == operation, 'actual exp primitive order drift')
                    self.exp_nodes.append((0 if operation == 'mul' else 1, local['a'], local['b'], arg))
            elif code is self.legacy_code:
                self._legacy(frame, event, arg)
            elif code in (self.codes['packed_tick'], self.codes['packed_commit']):
                self._packed(frame, event, arg)
            else:
                require(frame.f_locals.get('self') is self.owner, 'wrong owner instance reached pinned observed method')
                if event == 'call' and code is self.codes['_attention'] and not self.started:
                    self._start()
                if event == 'line':
                    self._line(frame)
                elif event == 'return' and code is self.codes['_op'] and type(arg) is int:
                    self._scalar(frame, arg)
                elif event == 'return' and code is self.codes['tick'] and isinstance(arg, dict):
                    self._tick(frame, arg)
                elif event == 'call' and code is self.codes['_fault']:
                    self._event('owner_fault', status=frame.f_locals['status'], detail=frame.f_locals['detail'])
                elif event == 'call' and code is self.codes['_finish']:
                    client = self.owner.matrix_client
                    self._event('owner_finish_called', status=frame.f_locals.get('status'), ack_bytes=self.owner.ack_bytes,
                        expected_write_bytes=self.owner.job.write_bytes, memory_pending=self.owner.memory_pending,
                        packed_state=None if client is None else client.packed.state,
                        legacy_state=None if client is None else client.legacy.state,
                        matrix_group_open=self.owner.matrix.group is not None,
                        matrix_result_present=self.owner.matrix.result is not None,
                        matrix_cached_done_present=vars(self.owner.matrix).get('_done') is not None)
        except Exception as error:
            # Preserve original returns/exceptions. First failure prevents any
            # completeness claim; no reference values repair missing records.
            self.error = self.error or str(error)
        finally:
            if closing_tick:
                self.identity_tick_frame = None
        return self._callback
    def _coverage(self):
        m = self.job['m']
        for name, field in self.fields.items():
            shape = field['shape']
            stride = 1
            for width in shape[3:]:
                stride *= width
            for index, actual in enumerate(field['frequency']):
                if name in ('normalizer', 'pv_final_raw', 'pv_bf16'):
                    expected = 1
                else:
                    key, token = (index // stride) % m, (index // stride // m) % m
                    expected = int(key <= token)
                if actual != expected or (not expected and field['words'][index] != SENTINEL):
                    return False
        return True

    def _repeats(self):
        m = self.job['m']
        for name in ('probability_fp32', 'probability_bf16'):
            f = self.fields[name]
            for h in range(12):
                for t in range(m):
                    for k in range(m):
                        start = ((h * m + t) * m + k) * 8
                        expected = int(k <= t)
                        if any(f['frequency'][start + use] != expected for use in range(8)):
                            return False
                        if expected and any(f['words'][start + use] != f['words'][start] for use in range(1, 8)):
                            return False
                        if not expected and any(f['words'][start + use] != SENTINEL for use in range(8)):
                            return False
        return True

    def _fences(self):
        m = self.job['m']
        causal = 12 * m * (m + 1) // 2
        expected = {k: 8 * causal for k in ('pv_probability_fp32_use', 'pv_bf16_input', 'pv_selected16_finite_check', 'pv_selected16_finite_pass')}
        expected['pv_normalize'] = causal
        expected.update({k: causal for k in ('qk_selected16_finite_check', 'qk_selected16_finite_pass', 'score_finite_commit')})
        expected.update({k: 96 * m for k in ('store_finite_check', 'store_finite_pass', 'memory_write_accepted', 'write_ack', 'write_response')})
        expected.update(owner_finish_called=1, owner_terminal_accepted=1, job_accepted=1, matrix_release=1, exp_nodes=causal)
        # All query heads read8 beats once; K and V each read8 beats per causal pair.
        expected.update(memory_read_accepted=96 * m + 16 * causal, read_response=96 * m + 16 * causal)
        groups = 12 * sum((t + 16) // 16 for t in range(m))
        pv_steps = 8 * causal
        expected.update(accepted_matrix_steps=groups * 8 + pv_steps,
                        accepted_matrix_groups=groups + 96 * m,
                        matrix_retire_result=groups + pv_steps,
                        matrix_retire_done=groups + 96 * m,
                        matrix_retire_legacy_reply=pv_steps)
        return (all(self.event_counts[k] == count for k, count in expected.items()) and
                self.lease is None and self.completed_groups == groups and self.pending_memory is None and
                self.fold_coord is None and self.service_group is None and self.service_pending_result is None and
                self.service_release_seen and self.exp_nodes is None and self.stream_seal is not None and
                self.pending_normalization is None and self.normalization_reuse_count == 7 * causal and self._repeats())

    def _field_chunks(self, name):
        field = self.fields[name]['words']
        for start in range(0, len(field), 16384):
            chunk = array('I', field[start:start + 16384])
            if sys.byteorder != 'little':
                chunk.byteswap()
            yield chunk.tobytes()

    def field_words(self, name):
        """Read-only export; returns complete original field, no reference filling.

        Main runner needs pv_bf16 (<=786432 B). The largest optional field is
        pv_key_raw (<=100663296 B); save/report themselves use <=64KiB chunks.
        """
        require(name in self.fields, 'unknown observed field')
        return b''.join(self._field_chunks(name))

    def _field_report(self, name):
        f, digest = self.fields[name], hashlib.sha256()
        for raw in self._field_chunks(name):
            digest.update(raw)
        return dict(shape=f['shape'], observed_words=sum(f['frequency']), total_words=len(f['words']),
                    raw_sha256=digest.hexdigest(), frequency_sha256=sha(f['frequency']))

    def report(self):
        require(self.closed and not self.active, 'close observer before reporting')
        if self.dispatcher is not None and self.dispatcher.failed is not None:
            self.error = self.error or 'wholeblock dispatcher failed'
        complete = self.error is None and self.started == 1 and self.terminal is not None
        if complete:
            r = self.retirement
            complete = (self.terminal['status'] is None and self.terminal['tag'] == self.job['tag']
                and self.terminal['write_bytes'] == self.job['write_bytes'] == self.job['m'] * 1536 * 4
                and r['same_services'] and r['same_job'] and r['state'] == 'idle' and not r['poison']
                and r['matrix_released'] and not r['matrix_reset_required'] and r['client_retired']
                and not r['memory_pending'] and r['scalar_released'] and self._coverage() and self._fences())
        return dict(schema='fixed93-fullblock-attention-pv-reuse-observation-v1', complete_observation=bool(complete),
            status='COMPLETE_ATTENTION_OBSERVATION_NOT_FULLBLOCK_ACCEPTANCE' if complete else 'INCOMPLETE',
            source_preparation_only=True, control_only=False, numerical_acceptance=False, native_acceptance=False, fullblock_acceptance=False,
            hardware_simulation=False, historical_results_inherited=False,
            source_manifest_sha256=self.closure_sha256, reviewed_manifest_sha256=REVIEWED_MANIFEST_SHA256,
            candidate_identity=CANDIDATE_IDENTITY, candidate_review_status='SOURCE_PREPARED_REVIEW_SEPARATE',
            integration_status='SOURCE_BOUND_PV_REUSE_FULLBLOCK_CANDIDATE',
            predecessor_reviewed_manifest_sha256=PREDECESSOR_REVIEWED_MANIFEST_SHA256,
            source_sha256=self.sources, selected_source_sha256=SELECTED, instrumentation_sha256=self.instrumentation,
            python=sys.version, loaded_functions_checked=self.loaded_checked, observer_error=self.error,
            job=self.job, terminal=self.terminal, accepted_retirement=self.retirement,
            fields={name: self._field_report(name) for name in self.fields},
            event_counts=dict(self.event_counts),
            event_count=0 if self.stream is None else self.stream.count,
            event_payload_sha256=None if self.stream is None else self.stream.digest.hexdigest(),
            event_codec_seal=None if self.stream_seal is None else asdict(self.stream_seal),
            event_codec_source_sha256=CODEC_PINS, event_file='attention-events.lec1',
            exp_node_schema='one typed u32le event per causal exp: actual17 nodes, or actual first1 plus explicit cutoff absence',
            trace_api='CPython source-bound actual locals/returns, same-thread dispatcher',
            normalization_evaluations_per_causal_key=1, probability_use_repeats=8,
            normalization_reuses_per_causal_key=7, observed_normalization_reuses=self.normalization_reuse_count,
            probability_fp32_source='each actual _matrix_step a[0] before BF16 conversion',
            scalar_schedule_changed=True, both_probability_domains_repeats_verified=bool(complete),
            pv_finite_boundary='every returned selected16 key packet',
            field_storage_bytes=0 if self.job is None else field_storage_bytes(self.job['m']),
            history_state='fixed counters + one fold + one packed lease + one memory debt + one Matrix group/result + one pending normalization',
            owner_scope='exact Fixed93AttentionOwner/ProfiledMatrixService/OfficialMatrixService/MatrixService/ScalarService',
            native_file_sha256=self.trace_limits['native_library_sha256'],
            matrix_binary_provenance_verified_by_observer=False,
            unobserved_domains=['expanded4096 Matrix bank per issue', 'SiLU nested17 exp nodes and preBF16 multiply'],
            scope_note='Attention actual arrays and complete streamed accepted schedule, not wholeblock/RTL/numeric admission')

    def save(self, destination):
        require(Path(destination).resolve() == self.destination, 'save destination must match stream destination')
        require(not self.saved, 'save is single-use; refusing overwrite')
        report = self.report()
        for name, field in self.fields.items():
            with (self.destination / (name + '.u32le')).open('xb') as target:
                for chunk in self._field_chunks(name):
                    target.write(chunk)
            with (self.destination / (name + '.presence')).open('xb') as target:
                target.write(field['frequency'])
        with (self.destination / 'summary.json').open('x') as target:
            target.write(json.dumps(report, indent=2) + '\n')
        self.saved = True
        return report

    def legacy_adapter(self):
        require(self.report()['complete_observation'] and self._repeats(),
                'legacy projection requires full fields, coverage/fences, and all8 actual Matrix operands in both probability domains, not eight normalization evaluations')
        return _LegacyProjection(self)


class _LegacyProjection:
    """Bounded, immutable export ONLY; not an alternate observer/computation."""
    def __init__(self, capture):
        m = capture.job['m']
        self._raw = {}
        fields = {}
        aliases = {'scores_bf16': 'score_bf16', 'softmax_fp32': 'probability_fp32',
                   'prob_bf16': 'probability_bf16', 'pv_bf16': 'pv_bf16'}
        for alias, original in aliases.items():
            f = capture.fields[original]
            if original.startswith('probability_'):
                words = array('I', (f['words'][i] for i in range(0, len(f['words']), 8)))
                frequency = bytes(f['frequency'][i] for i in range(0, len(f['frequency']), 8))
                shape = (12, m, m)
                if sys.byteorder != 'little':
                    words.byteswap()
                raw = words.tobytes()
            else:
                raw, frequency, shape = capture.field_words(original), bytes(f['frequency']), f['shape']
            self._raw[alias] = raw
            fields[alias] = types.MappingProxyType(dict(shape=shape, observed=frequency))
        self._raw, self.fields = types.MappingProxyType(self._raw), types.MappingProxyType(fields)

    def _bytes(self, name):
        return self._raw[name]
