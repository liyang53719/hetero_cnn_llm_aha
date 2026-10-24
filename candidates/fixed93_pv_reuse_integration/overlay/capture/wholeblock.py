"""SOURCE-ONLY wholeblock observer bridge; never imports or calls DUT arithmetic.

Construction requires independently reviewed parent admission. This module is not
run admission. Frames and existing return buffers are observed, never executed a
second time or written back. A poisoned capture cannot produce a successful seal.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import fields, is_dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
import threading
import types

CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'
ANCHORS = json.loads(Path(__file__).with_name('anchors.json').read_text())
LIMIT_FIELDS = {'contexts','bank_bytes','max_chunk','max_metadata','max_record','max_records','max_output','max_raw'}
TRACE_FIELDS = {'codec','max_trace_call_bytes','max_semantic_bytes','max_listener_count',
                'max_loaded_codes','max_trace_objects','max_exception_frames'}
# Counts are successful source-bound accepts, never predictions used as events.
REQUIRED_COUNTS = {'silu_vectors':71680, 'dense_steps':1462272,
                   'normal_steps':847872, 'normal_emits':799488,
                   'normal_groups':19200, 'public_completions':21,
                   'public_requests':17, 'public_launch_results':1,
                   'physical_publications':17, 'physical_terminals':17}
SCHEDULE_DOMAINS = ('public_host_accepts','prefix_and_attention_memory_handshakes',
    'dense_driver_accepts','resident_ffn_coordinator_accepts','matrix_group_step_emit_retire',
    'physical_read_write_ack_publication','workspace_version_read_seed_write_ack',
    'complete_existing_capped_trace_payloads','silu_single_delegate_six_phase_returns')
CACHE_DOMAINS = ('physical_kv_append_reads_writes_acks_publication',
    'attention_accepted_q_cache_k_cache_v_read_addresses_and_return_bytes',
    'workspace_accepted_versions_reads_seeds_and_acks')
LINE_ANCHORS = frozenset(('silu_execute','owner_attention','owner_matrix_step','owner_write','owner_tick'))
SUPPORT_ANCHORS = LINE_ANCHORS - {'silu_execute'} | {'jsonable','scalar_op','exp_negative'}


class CaptureError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise CaptureError(message)


def file_identity(path):
    path = Path(path)
    need(path.is_absolute() and path.is_file() and not path.is_symlink(), 'regular absolute source required')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def typename(value):
    cls = type(value)
    return cls.__module__ + '.' + cls.__qualname__


class TraceDispatcher:
    """One thread, one exact trace callback, fixed admitted CodeType universe.

    Listener return values are ignored. No DUT exception/return is replaced.
    Listener failures latch poison; the parent must check observer.check() at
    its existing safe boundaries. Uncaught DUT exceptions remain uncaught.
    """
    def __init__(self, codes, *, max_listeners, on_error, line_codes=(),
                 scalar_code=None, exp_code=None, max_exception_frames=64):
        self.codes = frozenset(codes)
        need(self.codes and all(type(c) is types.CodeType for c in self.codes), 'exact admitted code set required')
        self.max_listeners = max_listeners
        self.on_error = on_error
        self.line_codes = frozenset(line_codes)
        need(self.line_codes <= self.codes, 'unadmitted line-code domain')
        need((scalar_code is None and exp_code is None) or
             (scalar_code in self.codes and exp_code in self.codes), 'exact scalar/exp code pair')
        self.scalar_code, self.exp_code = scalar_code, exp_code
        self.scalar_instance = None
        self.max_exception_frames = max_exception_frames
        self._resume_lines = set()
        self.thread = threading.get_ident()
        self.callback = self._dispatch
        self._listeners = {}
        self._next = 0
        self.active = False
        self.failed = None

    def bind_scalar(self, instance):
        need(not self.active and self.scalar_code is not None and
             self.scalar_instance is None and instance is not None, 'one pretrace scalar binding required')
        self.scalar_instance = instance

    def register(self, callback, codes):
        need(threading.get_ident() == self.thread, 'cross-thread listener registration')
        need(callable(callback) and len(self._listeners) < self.max_listeners, 'listener capacity/callable')
        codes = frozenset(codes)
        need(codes and codes <= self.codes, 'listener supplied unadmitted code')
        if self.active:
            need(sys.gettrace() is self.callback, 'trace callback replaced')
        self._next += 1
        self._listeners[self._next] = (callback, codes)
        return self._next

    def unregister(self, token):
        need(threading.get_ident() == self.thread and token in self._listeners, 'unknown/cross-thread listener')
        if self.active:
            need(sys.gettrace() is self.callback, 'trace callback replaced')
        del self._listeners[token]

    def start(self):
        need(not self.active and self.failed is None, 'dispatcher already active/failed')
        need(threading.get_ident() == self.thread and threading.active_count() == 1, 'single-thread execution required')
        need(sys.gettrace() is None and threading.gettrace() is None, 'pre-existing trace cannot be replaced')
        need(self.scalar_code is None or self.scalar_instance is not None, 'scalar instance not bound')
        self.active = True
        sys.settrace(self.callback)

    def _dispatch(self, frame, event, arg):
        if frame.f_code not in self.codes:
            return None
        if self.failed is not None:
            return self.callback
        try:
            need(threading.get_ident() == self.thread, 'foreign traced thread')
            if event=='call':
                frame.f_trace_lines = frame.f_code in self.line_codes
                if frame.f_code is self.scalar_code:
                    # Guard every real scalar global call, including legal
                    # prefix clients. Never restrict client to Attention here.
                    need(frame.f_locals.get('self') is self.scalar_instance,
                         'wrong shared ScalarService instance')
            elif event=='exception' and frame.f_code not in self.line_codes:
                need(len(self._resume_lines)<self.max_exception_frames,
                     'handled-exception resume-frame cap')
                self._resume_lines.add(id(frame))
                frame.f_trace_lines = True
            # Registration is bounded; snapshot prevents mutation during iteration.
            for listener, codes in tuple(self._listeners.values()):
                if frame.f_code in codes:
                    listener(frame, event, arg)
            if event=='call' and frame.f_code is self.scalar_code and (
                    frame.f_back is None or frame.f_back.f_code is not self.exp_code):
                # Listener saw the original global call once. Non-exp scalar
                # arithmetic gets no local return/line tracing.
                return None
            if event=='line' and id(frame) in self._resume_lines:
                self._resume_lines.remove(id(frame))
                frame.f_trace_lines = False
            elif event=='return':
                self._resume_lines.discard(id(frame))
        except BaseException as error:
            # Do not inject an observer exception into a live arithmetic frame.
            # Store bounded text only, not exception/traceback/frame references.
            self.failed = type(error).__name__ + ': ' + str(error)[:512]
            self.on_error(self.failed)
        return self.callback

    def stop(self):
        if not self.active:
            return
        need(threading.get_ident() == self.thread, 'cross-thread trace stop')
        need(sys.gettrace() is self.callback, 'foreign trace must not be cleared')
        sys.settrace(None)
        self.active = False


class _PublicTrace:
    """Original event JSON schema, with uncapped durable opaque-byte retention."""
    def __init__(self, capture):
        self.capture = capture
        self.digest = hashlib.sha256()
        self.total = self.records = self.saved = 0
        self.truncated = False
        self.cap = None
        self.stream = None

    def write(self, raw):
        need(type(raw) is bytes, 'trace expects original immutable bytes')
        self.digest.update(raw)
        self.total += len(raw)
        self.records += 1
        try:
            self.capture._raw('public_trace', raw, {'trace_index':0,'write_index':self.records})
            self.saved += len(raw)
        except BaseException as error:
            self.capture._poison(type(error).__name__ + ': ' + str(error)[:512])
        return len(raw)

    def event(self, value):
        # Deliberately matches the frozen CappedTrace.event serialization.
        self.write((json.dumps(value, default=self.capture.jsonable, sort_keys=True,
                               separators=(',', ':')) + '\n').encode())

    def report(self):
        return dict(sha256=self.digest.hexdigest(), records=self.records,
                    total_bytes_hashed=self.total, persisted_prefix_bytes=self.saved,
                    prefix_cap_bytes=None, lossless=self.capture.failure is None,
                    poisoned=self.capture.failure is not None)

    def close(self):
        # Old runner closes x.trace before combined evidence sealing and in finally.
        # Actual stream ownership belongs solely to WholeblockObservation.close.
        return None


class WholeblockObservation:
    def __init__(self, out, *, admission, trace_limits):
        need(type(admission) is dict and type(trace_limits) is dict, 'explicit parent admission and budgets required')
        need(set(trace_limits) == TRACE_FIELDS, 'all new trace bounds must be explicit')
        for key in TRACE_FIELDS - {'codec'}:
            need(type(trace_limits[key]) is int and 1 <= trace_limits[key] <= 1048576, 'invalid trace bound '+key)
        need(trace_limits['max_listener_count'] <= 8 and trace_limits['max_loaded_codes'] <= 512 and
             trace_limits['max_trace_objects'] <= 1024 and trace_limits['max_exception_frames'] <= 1024,
             'hard observer state cap')
        need(type(trace_limits['codec']) is dict and set(trace_limits['codec']) == LIMIT_FIELDS,
             'all eight new codec limits required; inherited defaults forbidden')
        self.limits = dict(trace_limits)
        self.admission = admission
        self.failure = None
        self._closed = self._sealed = self._bound = False
        self._stream = 0
        self.counts = Counter()
        self._exceptions = set()
        self._trace_objects = {}
        # Exact accepted Dense emit bytes: two original in-flight results plus
        # one just-retired byte packet, needed by an outer driver's same-tick
        # pre-edge snapshot after its nested retirement. No DUT FIFO is added.
        self._dense_payloads = []
        self._dense_retired = None
        # Fixed operand byte dictionary, not a model transaction/cache.
        # slot 0: 16 u16 a words (32 B); slot 1: 256 u16 b words (512 B).
        self._operand_slots = [None, None]
        self._semantic_operands = None
        self._silu_calls = self._silu_returns = 0
        self._silu_gate_max_abs = self._silu_cutoff = self._silu_nonfinite = 0
        self._silu_active = None
        self._last_silu = -1
        self.out = Path(out).absolute()
        need(self.out.is_dir() and not self.out.is_symlink(), 'existing fresh output directory required')
        self._validate_admission()
        self.by_code = {d['code']:key for key,d in self.descriptors.items() if key in ANCHORS}
        need(len(self.by_code) == len(ANCHORS), 'aliased required source functions')
        codec = admission['codec']
        limits = codec['Limits'](**trace_limits['codec']).validate()
        # Require a no-compression upper bound independent of data or zlib ratios.
        worst = 52 + limits.max_raw + limits.max_records * (88 + limits.max_metadata) + 146
        need(limits.max_output >= worst, 'codec max_output below explicit worst-case byte reservation')
        self.worst_case_bytes = worst
        self.path = self.out/'wholeblock_events.lec1'
        self.sink = self.path.open('xb')
        try:
            self.writer = codec['Writer'](self.sink,limits,byte_order='little')
        except BaseException:
            self.sink.close()
            raise
        self.jsonable = admission['jsonable']
        self.public_trace = _PublicTrace(self)
        self.trace_dispatcher = TraceDispatcher((d['code'] for d in self.descriptors.values()),
            max_listeners=trace_limits['max_listener_count'],on_error=self._poison,
            line_codes=(self.descriptors[k]['code'] for k in LINE_ANCHORS),
            scalar_code=self.descriptors['scalar_op']['code'],
            exp_code=self.descriptors['exp_negative']['code'],
            max_exception_frames=trace_limits['max_exception_frames'])
        self._token = self.trace_dispatcher.register(self._observe,self.by_code)

    def _validate_admission(self):
        a = self.admission
        need(a.get('source_verified') is True and a.get('native_verified') is True and
             type(a.get('native_identity')) is dict and a['native_identity'],
             'parent source closure and loaded-native verification required')
        roots = a.get('source_roots')
        need(type(roots) is list and roots and len(roots) <= 8, 'exact source roots required')
        self.roots = tuple(Path(p).resolve() for p in roots)
        sources = a.get('sources')
        need(type(sources) is dict and sources and len(sources) <= 4096, 'source hash closure required')
        self.sources = dict(sources)
        for path,digest in self.sources.items():
            p=Path(path)
            need(p.is_absolute() and any(p.is_relative_to(root) for root in self.roots), 'source outside admitted roots')
            need(file_identity(p)==digest, 'source digest mismatch: '+str(path))
        self.descriptors = dict(a.get('loaded_codes',{}))
        need(set(ANCHORS) <= self.descriptors.keys() and
             len(self.descriptors) <= self.limits['max_loaded_codes'], 'missing/excess loaded-code descriptors')
        for key,d in self.descriptors.items():
            need(type(d) is dict and {'code','function','path','sha256','qualname','firstlineno'} <= d.keys(), 'incomplete loaded descriptor')
            c=d['code']; fn=d['function']; path=Path(d['path'])
            need(type(c) is types.CodeType and type(fn) is types.FunctionType and fn.__code__ is c,
                 'loaded callable/code identity')
            need(str(path) in self.sources and self.sources[str(path)] == d['sha256'] and
                 Path(c.co_filename).resolve() == path.resolve() and c.co_qualname == d['qualname'] and
                 c.co_firstlineno == d['firstlineno'], 'loaded source descriptor drift: '+key)
            if key in ANCHORS:
                expected=ANCHORS[key]
                need(str(path).endswith('/'+expected['relative_path']) and
                     d['sha256']==expected['sha256'] and d['qualname']==expected['qualname'] and
                     d['firstlineno']==expected['firstlineno'], 'wrong exact source anchor: '+key)
        need(a.get('jsonable') is self.descriptors['jsonable']['function'], 'original trace JSON converter required')
        types_map=a.get('identity_types')
        need(type(types_map) is dict and set(types_map)=={'x','physical','memory','silu','library'} and
             all(isinstance(v,type) for v in types_map.values()), 'exact admitted classes required')
        payload_types=a.get('matrix_payload_types')
        need(type(payload_types) is dict and set(payload_types)=={'normal_result','dense_result','matrix_value'} and
             all(isinstance(v,type) for v in payload_types.values()), 'exact admitted Matrix payload classes required')
        normal_globals=self.descriptors['matrix_accept_step']['function'].__globals__
        ordinary_globals=self.descriptors['public_ordinary_edge']['function'].__globals__
        silu_globals=self.descriptors['silu_execute']['function'].__globals__
        reduce_globals=self.descriptors['reduce_tick']['function'].__globals__
        need(payload_types['normal_result'] is normal_globals.get('MatrixResult') and
             payload_types['matrix_value'] is normal_globals.get('MatrixValue') and
             payload_types['dense_result'] is ordinary_globals['numeric'].model.MatrixResult and
             payload_types['dense_result'] is silu_globals['model'].MatrixResult and
             payload_types['dense_result'] is reduce_globals.get('MatrixResult'),
             'Matrix payload class is not the source-selected loaded identity')
        layouts={'normal_result':('context','value','last','error','ticket','epoch'),
                 'dense_result':('context','value','last','error'), 'matrix_value':('raw',)}
        for key,cls in payload_types.items():
            module=sys.modules.get(cls.__module__)
            path=Path(module.__file__).resolve() if module is not None else None
            need(path is not None and str(path) in self.sources and
                 getattr(module,cls.__name__,None) is cls and is_dataclass(cls) and
                 tuple(f.name for f in fields(cls))==layouts[key], 'Matrix payload class source/schema drift')
        self._matrix_payload_types=dict(payload_types)
        operand_types=a.get('operand_payload_types')
        need(type(operand_types) is dict and set(operand_types)=={
            'dense_step','window_step','normal_step','legacy_request','packed_request'} and
            all(isinstance(v,type) for v in operand_types.values()), 'exact admitted operand classes required')
        owner_globals=self.descriptors['owner_attention']['function'].__globals__
        matrix_owner_globals=self.descriptors['owner_matrix_step']['function'].__globals__
        window_globals=reduce_globals['DenseReductionOwner']._operand_response.__globals__
        need(operand_types['dense_step'] is ordinary_globals['numeric'].model.Step and
             operand_types['dense_step'] is silu_globals['model'].Step and
             operand_types['window_step'] is window_globals['KWindowStep'] and
             operand_types['normal_step'] is normal_globals['NormalStep'] and
             operand_types['legacy_request'] is normal_globals['LegacyRequest'] and
             operand_types['legacy_request'] is matrix_owner_globals['LegacyRequest'] and
             operand_types['packed_request'] is owner_globals['PackedQkRequest'],
             'operand class is not the source-selected loaded identity')
        layouts={
            'dense_step':('k','context','clear','last','finish','emit','a','b'),
            'window_step':('k','context','clear','last','finish','emit','a','b',
                           'logical_k','job_tag','identity','block_id'),
            'normal_step':('index','a','b','clear','last','context','finish','emit'),
            'legacy_request':('opcode','a','b','clear','last','steps','slice_mask'),
            'packed_request':('index','active_keys','a','b')}
        for key,cls in operand_types.items():
            module=sys.modules.get(cls.__module__)
            path=Path(module.__file__).resolve() if module is not None else None
            need(path is not None and str(path) in self.sources and
                 getattr(module,cls.__name__,None) is cls and is_dataclass(cls) and
                 tuple(f.name for f in fields(cls))==layouts[key], 'operand class source/schema drift')
        need(len(set(operand_types.values()))==5,'operand source classes unexpectedly aliased')
        self._operand_type_domains={cls:key for key,cls in operand_types.items()}
        codec=a.get('codec')
        need(type(codec) is dict and {'Writer','Limits','source_sha256'} <= codec.keys(), 'reviewed codec types and pins required')
        pins=codec['source_sha256']
        need(type(pins) is dict and len(pins)==3, 'exact final codec writer/format/decoder pins required')
        trusted=Path(__file__).with_name('CODEC_PINS.json')
        expected=json.loads(trusted.read_text())
        need({Path(k).name:v for k,v in pins.items()}==expected, 'codec is not reviewed r3 source')
        for path,digest in pins.items():
            need(file_identity(path)==digest, 'codec source drift')
        for typ,name in ((codec['Writer'],'writer.py'),(codec['Limits'],'format.py')):
            module=sys.modules.get(typ.__module__)
            need(module is not None and Path(module.__file__).resolve() in
                 {Path(p).resolve() for p in pins if Path(p).name==name}, 'unbound codec loaded type')

    def bind(self, x, physical, memory, silu, library):
        need(not self._bound and not self.trace_dispatcher.active, 'one pretrace binding required')
        self.objects=dict(x=x,physical=physical,memory=memory,silu=silu,library=library)
        for key,obj in self.objects.items():
            need(type(obj) is self.admission['identity_types'][key], 'wrong exact admitted '+key+' class')
        need(x.trace is self.public_trace and x.host.pc == x.host.completed == x.host.jobs == 0,
             'fresh pc0 public execution with this trace required')
        need(x.frontend.memory.physical_memory is physical and memory.physical_memory is physical and
             memory.workspace.physical_memory is physical and x.attention_owner.matrix is x.matrix_service and
             x.attention_owner.scalar is x.prefix_owner.scalar and x.matrix_service.lib is library,
             'detached launch/memory/service/library')
        need(silu.rows==128 and silu.calls==0 and silu.selected.sf_entrypoint=='sf_vector_bf16_v1',
             'fresh exact M128 BF16 SiLU selection')
        need(physical.pending is None and x.owner.state==x.prefix_owner.state==x.attention_owner.state=='idle',
             'fresh owner states required')
        self.fixed=self._identities()
        self.initial_counts=dict(physical.counts)
        self.trace_dispatcher.bind_scalar(x.prefix_owner.scalar)
        self._bound=True
        return self

    def _identities(self):
        o=self.objects; x=o['x']; p=o['physical']; m=o['memory']
        fixed=[x,x.host,x.frontend,x.frontend.memory,x.frontend.port,x.owner,x.owner.a_banks,
               x.owner.b_banks,x.owner.tiles,x.owner.tiles.banks,x.prefix_owner,x.attention_owner,
               x.prefix_owner.scalar,x.matrix_service,o['library'],o['silu'],o['silu'].selected,p,
               p.fixture,p.regions,m,m.act,m.act.data,m.workspace,m.workspace.data]
        fixed.extend(p.regions[k] for k in sorted(p.regions))
        fixed.extend(p.regions[k].get('data') for k in sorted(p.regions))
        fixed.extend(p.regions[k].get('provider') for k in sorted(p.regions))
        return tuple(id(v) for v in fixed)

    def _poison(self,message):
        if self.failure is None:
            self.failure=str(message)[:1024]

    def check(self):
        need(self.failure is None and self.trace_dispatcher.failed is None, 'capture poisoned: '+str(self.failure))
        need(not self._closed, 'capture is closed')
        if self._bound:
            need(self._identities()==self.fixed, 'same-live object/buffer/provider replaced')
        if self.trace_dispatcher.active:
            need(sys.gettrace() is self.trace_dispatcher.callback and threading.active_count()==1,
                 'trace replacement or multiple threads')
        for d in self.descriptors.values():
            need(d['function'].__code__ is d['code'], 'loaded function code replaced')

    def __enter__(self):
        need(self._bound, 'bind exact fresh objects before context entry')
        self.check()
        self.trace_dispatcher.start()
        return self

    def __exit__(self,kind,value,traceback):
        if kind is not None:
            self._poison('executing body exception: '+kind.__name__)
        try:
            self.trace_dispatcher.stop()
        except BaseException as error:
            self._poison(type(error).__name__+': '+str(error)[:512])
            if kind is None:
                raise
        return False

    def _raw(self,kind,raw,metadata):
        need(self.failure is None and not self._sealed, 'cannot write failed/sealed capture')
        need(type(raw) is bytes and len(raw)<=self.limits['max_trace_call_bytes'], 'raw observation extent cap')
        from .token_encoder import encode_record, WIRE_MAX_CHUNK
        need(self.writer.limits.max_chunk==WIRE_MAX_CHUNK, 'explicit token envelope chunk admission required')
        meta=dict(metadata,domain=kind)
        envelope,outer=encode_record(raw,meta)
        # One envelope per unchanged logical record. Retain r3's original
        # bounded values-fragment fallback; the codec hard chunk cap is 65536.
        if len(envelope)<=self.writer.limits.max_chunk:
            self.writer.event(envelope,outer)
        else:
            self._stream+=1; sid=self._stream
            self.writer.begin_values(sid,len(envelope),outer)
            step=self.writer.limits.max_chunk
            for offset in range(0,len(envelope),step):
                self.writer.value_chunk(sid,offset,envelope[offset:offset+step],outer)
            self.writer.end_values(sid,outer)
        self.counts['records_'+kind]+=1

    def _dense_payload_bytes(self,value):
        """Inspect immutable actual bank bytes only; never invoke a DUT method."""
        if type(value) is self._matrix_payload_types['matrix_value']:
            raw=object.__getattribute__(value,'raw')
            need(type(raw) is bytes and len(raw)==16384,'MatrixValue raw bank extent')
            return raw
        need(type(value) is tuple and len(value)==16 and
             all(type(row) is tuple and len(row)==256 and
                 all(type(word) is int and 0<=word<1<<32 for word in row) for row in value),
             'Dense result bank must be an exact bounded u32 tuple')
        return b''.join(struct.pack('<256I',*row) for row in value)

    def _dense_payload_entry(self,result,live_only=False):
        need(type(result) is self._matrix_payload_types['dense_result'],'wrong Dense result container')
        raw=self._dense_payload_bytes(object.__getattribute__(result,'value'))
        context=object.__getattribute__(result,'context')
        epoch=self.objects['x'].matrix_service.epoch
        entries=list(self._dense_payloads)
        if not live_only and self._dense_retired is not None:
            entries.append(self._dense_retired)
        matches=[entry for entry in entries if entry['raw']==raw and
                 entry['context']==context and entry['service_epoch']==epoch]
        need(matches,'Dense result has no exact retained actual dense_emit bytes')
        # This is a byte-content reference, not a transaction identity claim.
        # Equal bytes/coordinates may resolve to the first still-live emit;
        # every occurrence retains its original complete transaction fields.
        return matches[0]

    def _retire_dense_payload(self,result):
        entry=self._dense_payload_entry(result,live_only=True)
        self._dense_payloads.remove(entry)
        # Retain until the next retirement. A driver return may still contain
        # the retired immutable packet after nested retire -> emit -> return.
        # This one-entry byte dictionary is not outstanding transaction debt.
        self._dense_retired=entry

    def _matrix_payload(self,result):
        value=object.__getattribute__(result,'value')
        reference={'actual_object_reference':id(value),'type':typename(value)}
        if type(result) is self._matrix_payload_types['normal_result']:
            need(type(value) is self._matrix_payload_types['matrix_value'],
                 'normal result must use the exact source-selected MatrixValue')
            raw=object.__getattribute__(value,'raw')
            need(type(raw) is bytes and len(raw)==16384,'normal MatrixValue raw extent')
            reference['selected_observation']={
                'domain':'attention_selected_result_fields','result_object':id(result),
                'ticket':object.__getattribute__(result,'ticket'),
                'epoch':object.__getattribute__(result,'epoch'),
                'context':object.__getattribute__(result,'context'),
                'complete_physical_bank':False}
        else:
            entry=self._dense_payload_entry(result)
            reference['payload_reference']={key:entry[key] for key in
                ('emit_index','step_index','context','service_epoch')}
            reference['payload_reference'].update(stream='wholeblock_events.lec1',
                domain='dense_emit',byte_offset=0,byte_length=16384)
        return reference

    def _operand_value(self,value,field,source_domain,depth,budget):
        """Two fixed typed leaves only; equality means bytes, not transactions."""
        slot,words=(0,16) if field=='a' else (1,256)
        need(field in ('a','b') and type(value) is tuple and len(value)==words and
             all(type(word) is int and 0<=word<1<<16 for word in value), 'operand typed word extent')
        # Charge the same tuple + word visits/depth as the old expansion.
        budget[0]-=words+1
        need(budget[0]>=0 and depth+2<=10,'operand exceeds original semantic shape bound')
        need(self._semantic_operands is not None,'operand outside one semantic event')
        raw=struct.pack('<'+str(words)+'H',*value)
        current=self._semantic_operands.get(slot)
        if current is not None:
            need(current['raw']==raw,'one semantic event has conflicting operand bytes for one slot')
        else:
            previous=self._operand_slots[slot]
            if previous is not None and previous['raw']==raw:
                current=previous
            else:
                generation=1 if previous is None else previous['generation']+1
                need(generation<1<<64,'operand generation width')
                current=dict(raw=raw,generation=generation,source_domain=source_domain)
            self._semantic_operands[slot]=current
        return {'operand_ref':{'slot':slot,'generation':current['generation']}}

    def _value(self,value,*,depth=0,budget=None,name=''):
        # Only the exact source-selected MatrixResult container's bank field
        # uses a payload reference. A field merely named "value" is not opaque.
        if budget is None:budget=[8192]
        budget[0]-=1
        need(budget[0]>=0 and depth<=10,'semantic shape exceeds bounded schema')
        if value is None or type(value) in (bool,int):return value
        if type(value) is str:
            need(len(value)<=512,'semantic string cap');return value
        if type(value) is bytes:
            need(len(value)<=4096,'semantic bytes require explicit raw stream')
            return {'bytes_hex':value.hex(),'bytes':len(value)}
        if type(value) in (tuple,list):
            need(len(value)<=512,'semantic sequence cap')
            return [self._value(v,depth=depth+1,budget=budget) for v in value]
        if type(value) is dict:
            need(len(value)<=96 and all(type(k) is int or (type(k) is str and len(k)<=64) for k in value),
                 'semantic mapping cap')
            if any(type(k) is int for k in value):
                return {'typed_mapping':[[k,self._value(v,depth=depth+1,budget=budget)] for k,v in value.items()]}
            return {k:self._value(v,depth=depth+1,budget=budget,name=k) for k,v in value.items()}
        if is_dataclass(value) and not isinstance(value,type):
            fs=fields(value);need(len(fs)<=48,'semantic dataclass cap')
            payload_types=getattr(self,'_matrix_payload_types',{})
            matrix_result=type(value) in (payload_types.get('normal_result'),payload_types.get('dense_result'))
            operand_source=getattr(self,'_operand_type_domains',{}).get(type(value))
            return {'actual_object_reference':id(value),'type':typename(value),'fields':{
                f.name:(self._matrix_payload(value) if matrix_result and f.name=='value' else
                        self._operand_value(object.__getattribute__(value,f.name),f.name,operand_source,depth,budget)
                        if operand_source is not None and f.name in ('a','b') else
                        self._value(object.__getattribute__(value,f.name),depth=depth+1,budget=budget,name=f.name)) for f in fs}}
        if type(value) is types.SimpleNamespace:
            return self._value(vars(value),depth=depth+1,budget=budget)
        need(name!='value','unsupported non-Matrix value must not become an opaque reference')
        return {'actual_object_reference':id(value),'type':typename(value),'payload':'NOT_EXPANDED'}

    def _event(self,key,frame,values):
        need(self._semantic_operands is None,'reentrant semantic event')
        self._semantic_operands={}
        try:
            raw=json.dumps(self._value(values),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            need(len(raw)<=self.limits['max_semantic_bytes'],'semantic event byte cap')
            # Commit definitions only after the entire semantic tree has passed
            # its size and one-generation-per-slot checks. Each definition is
            # immediately before the semantic record that first references it.
            for slot,entry in sorted(self._semantic_operands.items()):
                if entry is not self._operand_slots[slot]:
                    self._raw('operand_definition',entry['raw'],dict(schema='step-u16-dict-v1',
                        slot=slot,generation=entry['generation'],source_domain=entry['source_domain'],
                        event_index=self.counts['semantic_events'],anchor=key))
                    self._operand_slots[slot]=entry
            self._raw('semantic',raw,{'anchor':key,'line':frame.f_lineno,'event_index':self.counts['semantic_events']})
        finally:
            self._semantic_operands=None
        self.counts['semantic_events']+=1
        self.counts['anchor_'+key]+=1

    def _belongs(self,key,L):
        self_obj=L.get('self');o=self.objects;x=o['x']
        if key.startswith('physical_'):return self_obj is o['physical']
        if key.startswith('workspace_'):return self_obj is o['memory'].workspace
        if key.startswith('public_'):return self_obj is x
        if key.startswith('matrix_'):return self_obj is x.matrix_service
        if key.startswith('dense_') or key=='official_dense_step':
            return getattr(self_obj,'service',None) is x.matrix_service and getattr(self_obj,'owner',None) is x.owner
        if key=='reduce_tick':return getattr(self_obj,'x',None) is x and self_obj is x.reduction
        if key=='coupled_tick':return getattr(self_obj,'owner',None) is x.owner and self_obj is x.coupled
        if key=='silu_vector':return self_obj is o['silu']
        if key=='silu_execute':return L.get('lib') is o['silu'] and L.get('h') is x.coupled
        return True

    def _observe(self,frame,event,arg):
        key=self.by_code[frame.f_code]
        if key in SUPPORT_ANCHORS:return
        L=frame.f_locals
        if key in ('capped_write','capped_records_write'):
            if event=='call':
                obj=L['self']; ident=id(obj)
                if ident not in self._trace_objects:
                    need(len(self._trace_objects)<self.limits['max_trace_objects'],'trace object cap')
                    # Retain bounded object refs so Python id reuse cannot merge streams.
                    self._trace_objects[ident]=(obj,len(self._trace_objects)+1)
                self._raw('existing_capped_trace',L['raw'],{'trace_index':self._trace_objects[ident][1],
                    'write_index':obj.records+1,'source_line':frame.f_lineno,'anchor':key})
            return
        if not self._belongs(key,L):
            raise CaptureError('wrong fixed instance at '+key)
        fid=id(frame)
        if event=='exception':
            need(len(self._exceptions)<self.limits['max_exception_frames'],'exception frame cap')
            self._exceptions.add(fid)
            self._event(key,frame,{'exception_type':arg[0].__name__,'exception':str(arg[1])[:512]})
            return
        if event=='line':
            self._exceptions.discard(fid)
            if key=='silu_execute' and frame.f_lineno==396:
                self._capture_silu(frame,L)
            return
        if event=='call':
            if key=='silu_vector':
                need(self._silu_active is None,'overlapping SiLU call')
                self._silu_active=id(frame);self._silu_calls+=1
            return
        if event!='return':return
        if fid in self._exceptions:
            self._exceptions.discard(fid)
            self._poison('uncaught observed source exception at '+key)
            return
        if key=='silu_vector':
            need(self._silu_active==id(frame) and arg==0,'SiLU return identity/status')
            self._silu_active=None;self._silu_returns+=1
            return
        if key=='silu_execute':return
        if key.startswith('public_') or key in ('reduce_tick','coupled_tick'):
            edges=[arg] if type(arg) is dict else list(arg) if type(arg) is tuple else []
            if key=='reduce_tick':edges=[L['oe'],L['ce'],L['se']]
            accepted=[e for e in edges if type(e) is dict and any(v for k,v in e.items() if k.endswith('_fire'))]
            if not accepted:return
            inputs={k:L[k] for k in ('inputs','args','abort','start','silu_accept','silu_complete','group_result_ready') if k in L}
            self._event(key,frame,{'accepted_edges':accepted,'inputs':inputs})
            if key=='public__host_edge':
                for signal,count in (('completion_fire','public_completions'),('request_fire','public_requests'),('result_fire','public_launch_results')):
                    self.counts[count]+=bool(arg.get(signal))
            return
        if key=='physical_read_bytes64':
            need(type(arg) is bytes and len(arg)==64,'physical read returned non64B')
            self._raw('physical_read64',arg,{'address':L['address'],'region':L['name']})
            self.counts['physical_read_bytes']+=64
            return
        if key.startswith('physical_') or key.startswith('workspace_'):
            names=('kind','value','command','job','result','address','words','request','ack','chunk_index','n_base','contexts','sequence','reservation','reason','name','chunk','context','index')
            values={n:L[n] for n in names if n in L}
            if key=='workspace_accept_read':values['returned_words']=arg
            if 'write_event' in key:
                self.counts[key+'_'+L['kind']]+=1
            if key=='physical_publish':self.counts['physical_publications']+=1
            if key=='physical_terminal':self.counts['physical_terminals']+=1
            self._event(key,frame,values)
            return
        if key.startswith('matrix_'):
            if key in ('matrix_acquire','matrix_accept_group','matrix_accept_step') and arg is not True:return
            values={n:L[n] for n in ('owner','mode','tag','group','step','result','done','ticket','epoch','rc') if n in L}
            values['service_epoch']=L['self'].epoch
            self._event(key,frame,values)
            if key=='matrix_accept_step':
                self.counts['normal_steps']+=1
                self.counts['normal_emits']+=L.get('rc')==1
            if key=='matrix_accept_group':self.counts['normal_groups']+=1
            return
        if key.startswith('dense_') or key=='official_dense_step':
            values={n:L[n] for n in ('start','end','contexts','k','context','clear','last','finish','emit','result','ack','done','ticket','epoch','index') if n in L}
            values['return']=arg
            values['adapter_reference']=id(L['self'])
            values['service_epoch']=L['self'].service.epoch
            if key in ('dense_td_step','official_dense_step'):
                # These are mutually exclusive actual delegate bodies: profiled
                # QKV invokes base; official tail bypasses base and calls ELF once.
                need(type(arg) is int and arg>=0,'negative Dense delegate result')
                for name,n in (('a',16),('b',256)):
                    need(len(L[name])==n,'Dense operand vector shape')
                raw=struct.pack('<272H',*(int(v) for v in L['a']),*(int(v) for v in L['b']))
                self._raw('dense_operands',raw,{'anchor':key,'step_index':self.counts['dense_steps'],
                    'k':L['k'],'context':L['context'],'output_reference':id(L['output'])})
                self.counts['dense_steps']+=1
                if arg==1:
                    need(len(L['output'])==4096,'Dense emitted result extent')
                    need(len(self._dense_payloads)<2,'Dense in-flight payload queue exceeds source bound')
                    raw=struct.pack('<4096I',*(int(v) for v in L['output']))
                    entry=dict(raw=raw,emit_index=self.counts['dense_emits'],
                        step_index=self.counts['dense_steps']-1,context=L['context'],
                        service_epoch=L['self'].service.epoch)
                    self._raw('dense_emit',raw,dict(anchor=key,output_reference=id(L['output']),
                        **{k:v for k,v in entry.items() if k!='raw'}))
                    self._dense_payloads.append(entry)
                    self.counts['dense_emits']+=1
            elif key=='dense_td_seed_beat':
                values['actual_seed_words']=[int(v) for v in L['words']]
            self._event(key,frame,values)
            if key=='dense_retire_result':
                self._retire_dense_payload(L['result'])

    def _capture_silu(self,frame,L):
        q=L['q']; index=L['index']; ng=L['ng']
        expected=self.counts['silu_vectors']
        need((q.rows,q.cols)==(128,160) and ng%160==0 and 0<=ng<8960 and
             index==expected%1280 and ng//160==expected//1280 and
             self._silu_calls==self._silu_returns==expected+1 and self._silu_active is None,
             'SiLU omitted/repeated/reordered coordinate/delegate')
        need(expected<71680 and len(L['values'])==len(L['flags'])==96 and len(L['errors'])==16,
             'SiLU vector/phase extent')
        gate=tuple(int(v) for v in L['operands'][0]);up=tuple(int(v) for v in L['operands'][1])
        output=tuple(int(v) for v in L['operands'][2])
        need(len(gate)==len(up)==len(output)==16 and gate==tuple(L['g']) and up==tuple(L['u']),
             'SiLU exact accepted tile operand identity')
        for word in gate:
            absword=word&0x7fffffff
            self._silu_gate_max_abs=max(self._silu_gate_max_abs,absword)
            self._silu_nonfinite+=absword>=0x7f800000
            self._silu_cutoff+=absword>=0x42a00000
        values=tuple(int(v) for v in L['values']); flags=tuple(int(v) for v in L['flags']); errors=tuple(int(v) for v in L['errors'])
        raw=struct.pack('<256I',*(gate+up+output+values+flags+errors))
        self._raw('silu_six_phases',raw,{'vector':expected,'window':ng//160,'ng':ng,
            'row_group':index//160,'column':ng+index%160,'phase_count':6,'lanes':16,
            'gate_words':16,'up_words':16,'output_words':16,'phase_words':96,'flag_words':96,'error_words':16})
        self.counts['silu_vectors']+=1

    def seal(self, report):
        self.check()
        need(self._bound and not self._sealed and self.trace_dispatcher.active,'seal inside live complete capture')
        x=self.objects['x'];p=self.objects['physical'];m=self.objects['memory']
        need(type(report) is dict and x.launch_result is not None and
             x.launch_result.get('status') is None and x.launch_result.get('completed')==21 and
             x.launch_result.get('jobs')==17 and [v['pc'] for v in x.completions]==list(range(21)),
             'whole public21 actual terminal required, not pc12 checkpoint')
        need(x.host.state=='idle' and p.pending is None and m.workspace.finished and
             x.matrix_service.owner is None and x.prefix_owner.scalar.client is None and
             x.owner.state==x.prefix_owner.state==x.attention_owner.state=='idle' and
             x.owner.lease is None and not x.owner.tiles.leased and x.owner.tiles.idle,
             'live terminal debt/lease fence')
        need(not self._exceptions and self._silu_active is None and not self._dense_payloads,
             'open exception, SiLU frame or Dense result payload')
        for key,count in REQUIRED_COUNTS.items():
            need(self.counts[key]==count,'accepted count mismatch '+key+': '+str(self.counts[key]))
        need(self._silu_calls==self._silu_returns==71680 and self.objects['silu'].calls==71680,'SiLU single-delegate count mismatch')
        need(self.counts['physical_read_bytes']==p.counts['read_bytes']-self.initial_counts.get('read_bytes',0)-
             self.counts['anchor_workspace_accept_read']*64,'actual physical/workspace read coverage mismatch')
        for kind,counter in (('command','write_commands'),('data','write_data_bytes'),('ack','write_acks')):
            actual=self.counts['physical_write_event_'+kind]+self.counts['workspace_write_event_'+kind]
            expected=p.counts[counter]-self.initial_counts.get(counter,0)
            need(actual*(64 if kind=='data' else 1)==expected,'accepted physical/workspace '+kind+' coverage mismatch')
        for path,digest in self.sources.items():need(file_identity(path)==digest,'terminal source drift')
        for path,digest in self.admission['codec']['source_sha256'].items():need(file_identity(path)==digest,'terminal codec drift')
        sealed=self.writer.finish()
        self.sink.flush()
        self._sealed=True
        digest=file_identity(self.path)
        return {'evidence_contract':CONTRACT,'source_bound':True,
            'complete_declared_schedule':True,'complete_declared_cache':True,
            'covered_schedule_domains':list(SCHEDULE_DOMAINS),'covered_cache_domains':list(CACHE_DOMAINS),
            'complete_algorithm_arrays':False,'algorithm_array_authority':'integration and sibling artifact seals, not this bridge',
            'lossless_streams_sealed':True,'six_actual_silu_phases_complete':True,
            'native_silu_inner_exp_observed':False,'native_silu_pre_bf16_product_observed':False,
            'silu_gate_cutoff_reachability':{'actual_gate_words':71680*16,'maximum_absolute_word':self._silu_gate_max_abs,
                'abs_ge_80_count':self._silu_cutoff,'nonfinite_count':self._silu_nonfinite,
                'historical_values_used_as_input':False},
            'counts':dict(self.counts),'silu_delegate_calls':self._silu_calls,
            'trace_object_count':len(self._trace_objects),'trace_limits':self.limits,'worst_case_bytes':self.worst_case_bytes,
            'codec_seal':vars(sealed),'artifacts':{'wholeblock_events.lec1':{'path':str(self.path),
                'bytes':self.path.stat().st_size,'sha256':digest}},
            'all_hardware_cycles':False,'all_dense4096_bank_snapshots':False,
            'all_internal_scalar_nodes':False,'observed_values_are_expected_inputs':False,
            'uncovered_domains':['native SiLU internal 17 exp nodes','native SiLU pre-BF16 product',
                'unexported native internal arithmetic','all hardware cycles','physical bank snapshot after every Dense step']}

    def close(self):
        if self._closed:return
        if self.trace_dispatcher.active:self.trace_dispatcher.stop()
        self.sink.close()
        self._closed=True
