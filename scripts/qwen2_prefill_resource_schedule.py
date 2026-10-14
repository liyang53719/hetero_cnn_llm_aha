#!/usr/bin/env python3
"""Shared-resource reservation scaffold, NOT a hardware cycle predictor.

The baseline serializes work. Repeated macros preserve their ordered bodies;
they are not an expanded Chisel FSM. Default timing is entirely unbound.
Explicit synthetic timings only exercise this scheduler and its lifetimes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ATT = _module('qwen2_rectangular_attention_model')
BOUND = _module('qwen2_prefill_traffic_bound')
SFU = _module('qwen2_shared_sfu_schedule')
EXTRA_PINS = {
    'scripts/qwen2_shared_sfu_schedule.py': '724e3a4894a42d40972c215c2984fb12da34baf59140baa173451f1a28335dab',
    'scripts/qwen2_rectangular_attention_model.py': '8fdcffce9908d1a273bb5bc2011d62f952b20eb5c83fb2258dc06f0f04208f29',
    'scripts/qwen2_prefill_traffic_bound.py': '6b16326c9218039e154b5ed7e979194258d89ff1c6b702309481384d8334b2c1',
    'scripts/import_llama_qwen2_graph.py': '07a7edfa3f0c08876fddd47c909b2a340fb6fd175ec46f99c2754f748bb2ea6e',
    'chisel/p0_safety/src/main/scala/heteronpu/p0/LocalSramConfig.scala': '6d8167530ae045ca038f644a93238731d6f2b645a01cf856d1ab111387de0464',
    'chisel/p0_safety/src/main/scala/heteronpu/p0/SharedL2Fabric.scala': '10372482417b8802fcf494e10af6a8d202e1dc5bb39d1a637d27da259efa30c5',
    ATT.BASE+'BlockWritebackFence.scala': '70e0303640904dd4044d6f5f61231b9766816da68cc71dbd58aa464a00a11054',
    ATT.BASE+'Record128Reader.scala': '4b7f33a150dcf3abf15e4ba54b2d1fbdc846d49f966dd7b3bb810ec05f1a9afb',
    ATT.BASE+'TypedTensorReader.scala': 'a0641c72360e608238879f3c12f5882a8999ccac3c46d510beff6b0ffb0a1c3c',
}
SOURCE_PINS = {**BOUND.SOURCE_PINS, **BOUND.HOST_SOURCE_PINS, **ATT.SOURCE_PINS,
               **SFU.SOURCE_PINS, **EXTRA_PINS}
A_BANKS = tuple(f'A.bank{i}' for i in range(16))
B_BANKS = tuple(f'B.bank{i}' for i in range(16))
CORE_BANKS = tuple(f'core.group{i}' for i in range(4))
ELEM_BANKS = tuple(f'elementwise.group{i}' for i in range(4))
RESOURCES = frozenset(A_BANKS+B_BANKS+CORE_BANKS+ELEM_BANKS+(
    'idma', 'matrix', 'scalar', 'core_vector16', 'elementwise_vector16', 'silu16', 'host_control'))
CAPACITIES = dict(A_bytes=704512, B_bytes=81920, core_bytes=573440,
                  elementwise_bytes=12288, contexts=5, metadata=8,
                  matrix_results=2, dense_final_values=1, partial_slots=5, captured_rows=16,
                  core_vectors=7, silu_inputs=1, silu_outputs=1,
                  idma_transaction=1, dense_scratch_lease=1)
DENSE_MAPPINGS = ('current', 'resident_m128_nc3')


def mapping_capacities(mapping='current'):
    if mapping not in DENSE_MAPPINGS:
        raise ReservationError('unknown Dense mapping')
    capacities = dict(CAPACITIES)
    if mapping == 'resident_m128_nc3':
        capacities.update(A_bytes=524288, B_bytes=262144)
    if capacities['A_bytes']+capacities['B_bytes'] != 768*1024:
        raise ReservationError('Dense SRAM total changed')
    return capacities
TIMING_KEYS = (
    'owner_switch', 'command_admission', 'control', 'bank_word', 'fabric_beat',
    'read_64b_service', 'read_64b_commit', 'write_64b_service', 'write_64b_ack',
    'matrix_issue', 'matrix_return_wait', 'matrix_group',
    'scalar_add', 'scalar_mul', 'scalar_div', 'scalar_sqrt', 'scalar_exp',
    'core_vector', 'elementwise_vector', 'silu_group', 'terminal_fence',
)
V0_SILU_AUDIT = 'reports/execution/QWEN2_SFU_TIMING_20261011/V0_SAVED_GATE_AUDIT.json'
V0_SILU_AUDIT_SHA256 = '14b65f7fe70416739ca2b5cebffdd5a4bb388077708c579b30aa1f40df247ebf'

# Exact compatibility review for the original Qwen2 Host only. At f16df50,
# HostBlockTop omits enableH2048RmsBorrower; its false default keeps the
# original ElementwiseMemoryEngine and leaves both new exclusivity wires false.
# Dense geometry, core arithmetic/ACK paths, and ScheduledSiluOwner are unchanged.
# The frozen census and producer identities below are NOT rewritten or rerun.
V0_HOST_SOURCE_REVIEW = {
    ATT.BASE+'Qwen2Block.scala': {
        'historical_sha256': '1152cb11e145c27f271b0170913194bd66ce2930008a75e3a580d5660e410a43',
        'current_sha256': '9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4'},
    ATT.BASE+'QwenOwnerProtocol.scala': {
        'historical_sha256': 'c8d6cfd95901bc9f2cae3f248d542cb532b1b66aec1be98942a9a7533d3ca542',
        'current_sha256': '7f2b4a623b61b6e68478b2310d441ed04ccde1cd5490cb22205113f907b7974d'},
}


def _current_v0_hardware_pins(root, historical_pins):
    current = {}
    for path, historical in historical_pins.items():
        review = V0_HOST_SOURCE_REVIEW.get(path)
        if review is not None and historical != review['historical_sha256']:
            raise ValueError('saved branch audit reviewed historical source changed: '+path)
        expected = review['current_sha256'] if review is not None else historical
        if hashlib.sha256((Path(root)/path).read_bytes()).hexdigest() != expected:
            raise ValueError('saved branch audit hardware source changed: '+path)
        current[path] = expected
    return current


def timing_profile(synthetic=False):
    values = dict.fromkeys(TIMING_KEYS)
    if synthetic:
        values.update(dict.fromkeys(TIMING_KEYS, 1))
        values.update(owner_switch=2, command_admission=7, read_64b_service=2,
                      read_64b_commit=3, write_64b_ack=5, matrix_return_wait=6,
                      scalar_add=3, scalar_mul=3, scalar_div=9, scalar_sqrt=9,
                      scalar_exp=20, silu_group=64)
    return dict(name='synthetic_serial_scenario' if synthetic else 'unbound',
                synthetic=synthetic, parameters=values,
                meaning='Per-macro service assumptions, including unknown waits; not measured RTL timings')


def op(label, resources=(), costs=None, metrics=None):
    return dict(event='op', label=label, resources=tuple(resources), costs=costs or {}, metrics=metrics or {})


def acquire(name, pool, amount):
    return dict(event='acquire', name=name, pool=pool, amount=amount)


def release(name):
    return dict(event='release', name=name)


def repeat(count, body, label):
    return dict(event='repeat', count=count, body=list(body), label=label)


def read_span(size, banks=(), local_words=0, metric='external_read_bytes'):
    """Bounded stream macro: commits before use; never allocates size registers.

    Service/commit cost is charged per 64 B, conservatively. Actual burst
    coalescing, root alignment and backend FSM transitions are not expanded.
    """
    if size % 64:
        raise ValueError('only complete 64 B spans are modeled')
    return op('read_span_then_commit', ('idma',)+tuple(banks),
              dict(read_64b_service=size//64, read_64b_commit=size//64, bank_word=local_words),
              {metric:size, 'external_read_bytes':size} if metric != 'external_read_bytes'
              else {metric:size})


def write_span(size, tag='write'):
    if size % 64:
        raise ValueError('only complete 64 B stores are modeled')
    return [dict(event='write', tag=tag, bytes=size), dict(event='ack', tag=tag)]


def scalar(kind, count=1):
    return op('scalar_'+kind, ('scalar',), {'scalar_'+kind:count}, {'scalar_'+kind+'_requests':count})


def vector(count=1, elementwise=False):
    resource = 'elementwise_vector16' if elementwise else 'core_vector16'
    cost = 'elementwise_vector' if elementwise else 'core_vector'
    return op(resource, (resource,), {cost:count}, {cost+'_requests':count})


class ReservationError(ValueError):
    pass


class ReservationBook:
    """Exclusive intervals. All overlap is disabled in the initial baseline."""
    def __init__(self):
        self.now = 0
        self.free_at = dict.fromkeys(RESOURCES, 0)
        self.samples = []

    def reserve(self, resources, duration, start=None, label=''):
        # Simultaneously owned ports are a set, not a bus transaction order.
        # Keep the evidence stable when a caller passes RESOURCES (frozenset).
        resources = tuple(sorted(resources))
        if any(r not in self.free_at for r in resources):
            raise ReservationError('unknown physical resource')
        if type(duration) is not int or duration < 0:
            raise ReservationError('invalid duration')
        start = self.now if start is None else start
        if any(self.free_at[r] > start for r in resources):
            raise ReservationError('resource double reservation')
        if start < self.now:
            raise ReservationError('overlap has no approved port/buffer schedule')
        end = start+duration
        for r in resources:
            self.free_at[r] = end
        self.now = end
        if len(self.samples) < 24:
            self.samples.append(dict(label=label, start=start, end=end, resources=list(resources)))


class Scheduler:
    """Validate successful-path model lifetimes, not hardware deadlock freedom."""
    def __init__(self, profile=None, dense_mapping='current'):
        self.profile = profile or timing_profile()
        self.capacities = mapping_capacities(dense_mapping)
        params = self.profile['parameters']
        if set(params) != set(TIMING_KEYS):
            raise ReservationError('timing parameters must explicitly cover every timing key')
        if any(v is not None and (type(v) is not int or v < 1) for v in params.values()):
            raise ReservationError('timing values must be positive integers or unbound')
        self.bound = all(v is not None for v in params.values())
        if self.bound and not self.profile.get('synthetic'):
            raise ReservationError('this scaffold only permits explicit synthetic timing execution')
        self.book = ReservationBook()
        self.allocations, self.pending = {}, {}
        self.usage, self.peaks, self.metrics, self.costs = Counter(), Counter(), Counter(), Counter()
        self.owner = None
        self.published = {'x'}
        self.completed = []
        self.stage_metrics = {}
        self.terminal_seen = False
        self.dense_prefixes, self.dense_inflight, self.dense_final_tiles = {}, {}, set()
        self.dense_c_addresses = {}
        self.resident_shape = None
        self.seed_ready = set()
        self.dense_depths = {}
        self.dense_captured = None
        self.dense_sink_complete = False
        self.dense_output_pending = {}
        self.prefix_store_committed = self.prefix_output_committed = 0

    def _snapshot(self):
        return (dict(self.allocations), dict(self.pending), dict(self.usage),
                self.owner, frozenset(self.published), tuple(self.completed),
                dict(self.dense_prefixes),dict(self.dense_inflight),frozenset(self.dense_final_tiles),
                dict(self.dense_c_addresses),self.resident_shape,frozenset(self.seed_ready),dict(self.dense_depths),
                self.dense_captured,self.dense_sink_complete,dict(self.dense_output_pending))

    def _run_op(self, event, multiplier):
        resources = event['resources']
        label=event['label']
        if label=='resident_Dense_capture_existing_finalValue':
            ctx=event['dense_context']
            if (self.dense_depths.get(ctx)!=256 or ctx not in self.seed_ready or
                self.dense_captured is not None or 'dense_final' not in self.allocations or
                'dense_result' not in self.allocations):
                raise ReservationError('Dense capture before completed context or without output buffers')
            self.dense_captured=ctx
            self.dense_sink_complete=False
        if label=='candidate_FP32_prefix_store_before_context_reuse':
            ctx=event['dense_context']
            if (self.dense_captured!=ctx or self.dense_depths.get(ctx)!=256 or
                'dense_final' not in self.allocations or self.dense_sink_complete or
                self.dense_inflight[ctx][1]+256==self.resident_shape['k']):
                raise ReservationError('Dense snapshot store before captured context or on final K')
            self.dense_sink_complete=True
        if label=='candidate_FP32_seed_restore_before_compute':
            if (not self.dense_inflight or any(kb==0 for _,kb in self.dense_inflight.values()) or
                self.seed_ready or event['metrics'].get('dense_partial_restore_bytes')!=len(self.dense_inflight)*16384):
                raise ReservationError('seed restore lacks exactly the pending nonzero-K contexts')
            self.seed_ready=set(self.dense_inflight)
        if label in ('resident_Dense_increasing_K_prefix','resident_Dense_last_K_of_chunk'):
            if not self.dense_inflight or self.seed_ready!=set(self.dense_inflight):
                raise ReservationError('Dense compute before exact FP32 seed restore')
            if label=='resident_Dense_increasing_K_prefix' and len(self.dense_inflight)!=self.usage['contexts']:
                raise ReservationError('Dense prefix compute lacks a physical context identity')
            if label=='resident_Dense_increasing_K_prefix':
                if any(self.dense_depths[c]!=0 for c in self.dense_inflight) or event['metrics']['dense_wide_issues']!=255*len(self.dense_inflight):
                    raise ReservationError('Dense increasing-K operation repeated or incomplete')
                self.dense_depths={c:255 for c in self.dense_inflight}
            else:
                ctx=event['dense_context']
                if self.dense_depths.get(ctx)!=255 or event['metrics']['dense_wide_issues']!=1:
                    raise ReservationError('Dense final K missing its exact context prefix')
                self.dense_depths[ctx]=256
        if self.pending and 'idma' in resources and event['label'] not in ('write_data_not_committed','write_ACK'):
            raise ReservationError('IDMA reused before outstanding write ACK')
        if not set(resources) <= RESOURCES:
            raise ReservationError('unknown physical resource')
        costs = event['costs']
        if any(k not in TIMING_KEYS or type(v) is not int or v < 0 for k,v in costs.items()):
            raise ReservationError('invalid operation cost')
        for k,v in costs.items(): self.costs[k] += v*multiplier
        for k,v in event['metrics'].items(): self.metrics[k] += v*multiplier
        if self.bound:
            duration = sum(v*self.profile['parameters'][k] for k,v in costs.items())
            self.book.reserve(resources, duration, label=event['label'])

    def execute(self, event, multiplier=1):
        if self.terminal_seen:
            raise ReservationError('work after terminal fence')
        kind = event['event']
        if kind == 'op':
            self._run_op(event, multiplier)
        elif kind == 'acquire':
            name, pool, amount = event['name'], event['pool'], event['amount']
            if name in self.allocations or pool not in self.capacities or type(amount) is not int or amount <= 0:
                raise ReservationError('invalid or duplicate allocation')
            if self.usage[pool]+amount > self.capacities[pool]:
                raise ReservationError('buffer/context capacity exceeded: '+pool)
            self.allocations[name] = (pool, amount, self.owner)
            self.usage[pool] += amount
            self.peaks[pool] = max(self.peaks[pool], self.usage[pool])
        elif kind == 'release':
            name = event['name']
            if name=='resident_C' and (self.dense_prefixes or self.dense_inflight or self.dense_c_addresses):
                raise ReservationError('C lease release before all prefixes become final')
            if name=='dense_contexts' and self.dense_inflight:
                raise ReservationError('physical contexts reused before prefix drain')
            if name=='dense_final' and self.dense_captured is not None:
                raise ReservationError('Dense finalValue release before its sink commit')
            if name.startswith('idma:') or self.pending:
                raise ReservationError('write must retain IDMA ownership until its ACK')
            if name in self.allocations:
                pool = self.allocations[name][0]
                if pool in ('contexts','A_bytes','B_bytes') and (self.usage['metadata'] or self.usage['matrix_results']):
                    raise ReservationError('buffer/context release before Matrix drain')
                if pool == 'dense_scratch_lease' and (self.usage['A_bytes'] or self.usage['B_bytes']):
                    raise ReservationError('scratch lease release while bank buffers are live')
            self._release(name)
        elif kind == 'write':
            tag, size = event['tag'], event['bytes']
            if self.resident_shape:
                ctx=event.get('dense_context')
                if (ctx is None or ctx!=self.dense_captured or self.dense_depths.get(ctx)!=256 or
                    'dense_final' not in self.allocations or self.dense_sink_complete or size!=16384 or
                    self.dense_inflight[ctx][1]+256!=self.resident_shape['k']):
                    raise ReservationError('Dense output write before final captured context')
                self.dense_output_pending[tag]=ctx
            if tag in self.pending or not self.owner or size <= 0 or size % 64:
                raise ReservationError('invalid write or missing owner')
            self.execute(acquire('idma:'+tag, 'idma_transaction', 1))
            self.pending[tag] = size
            self._run_op(op('write_data_not_committed', ('idma',),
                            {'write_64b_service':size//64}, {'external_write_bytes':size}), multiplier)
        elif kind == 'ack':
            tag = event['tag']
            if tag not in self.pending:
                raise ReservationError('ACK has no outstanding write')
            size = self.pending.pop(tag)
            if self.resident_shape:
                ctx=self.dense_output_pending.pop(tag,None)
                if ctx is None or ctx!=event.get('dense_context') or ctx!=self.dense_captured:
                    raise ReservationError('Dense ACK context does not match captured output')
                self.dense_sink_complete=True
            self._run_op(op('write_ACK', ('idma',), {'write_64b_ack':size//64},
                            {'acknowledged_write_bytes':size}), multiplier)
            self._release('idma:'+tag)
        elif kind == 'owner_begin':
            if (self.owner or self.pending or self.allocations or self.dense_prefixes or
                self.dense_inflight or self.dense_c_addresses or self.resident_shape):
                raise ReservationError('owner switch before previous resources drained')
            if not set(event['requires']) <= self.published:
                raise ReservationError('consumer before committed producer')
            self.owner = event['name']
            self.dense_final_tiles.clear()
            self.prefix_store_committed=self.metrics['dense_partial_store_bytes']
            self.prefix_output_committed=self.metrics['acknowledged_write_bytes']
            self.stage_metrics[self.owner] = Counter(self.metrics)
            self._run_op(op('opaque_host_admission', ('host_control','idma'),
                            {'command_admission':len(event['public_stages']), 'owner_switch':1}), multiplier)
        elif kind == 'owner_end':
            if (self.owner != event['name'] or self.pending or self.allocations or
                self.dense_prefixes or self.dense_inflight or self.dense_c_addresses or self.resident_shape):
                raise ReservationError('owner completion before final ACK/buffer drain')
            self.published.update(event['produces'])
            self.completed.append(self.owner)
            self.stage_metrics[self.owner] = dict(self.metrics-self.stage_metrics[self.owner])
            self.owner = None
            self.dense_final_tiles.clear()
        elif kind == 'dense_residency_begin':
            if self.resident_shape or not self.owner:
                raise ReservationError('resident Dense shape already live or missing owner')
            self.resident_shape=resident_dense_plan(event['tokens'],event['k'],event['n'])
        elif kind == 'dense_residency_end':
            if (not self.resident_shape or self.dense_prefixes or self.dense_inflight or
                self.dense_c_addresses or self.seed_ready):
                raise ReservationError('resident Dense ends before prefix drain')
            expected={(mb,nb) for mb in range(0,128,16) for nb in range(0,self.resident_shape['n'],256)}
            if self.dense_final_tiles!=expected:
                raise ReservationError('resident Dense final tile coverage is incomplete')
            self.resident_shape=None
        elif kind == 'dense_prefix_begin':
            key=(event['m_base'],event['nbase']);ctx=event['context'];kb=event['kbase']
            address=event['c_word_address']
            shape=self.resident_shape
            if (not shape or any(type(v) is not int for v in (*key,ctx,kb)) or
                key[0] not in range(0,128,16) or key[1] not in range(0,shape['n'],256) or
                kb not in range(0,shape['k'],256)):
                raise ReservationError('Dense logical tile range or selected shape mismatch')
            expected_address=shape['a_operand_bf16_bytes']//512+((key[1]//256)%shape['n_tiles_retained'])*256+key[0]//16*32
            a_end=self.allocations.get('resident_A',(None,0))[1]//512
            c_end=a_end+self.allocations.get('resident_C',(None,0))[1]//512
            if (not self.owner or 'resident_C' not in self.allocations or
                ctx not in range(self.usage['contexts']) or ctx in self.dense_inflight or
                any(v[0]==key for v in self.dense_inflight.values()) or
                key in self.dense_final_tiles or
                self.dense_prefixes.get(key,0)!=kb or (kb==0 and key in self.dense_prefixes)):
                raise ReservationError('Dense prefix restore/order/context mismatch')
            if (type(address) is not int or address!=expected_address or address%32 or address<a_end or address+32>c_end or
                any(other!=key and address<start+32 and start<address+32
                    for start,other in self.dense_c_addresses.items()) or
                (kb and self.dense_c_addresses.get(address)!=key)):
                raise ReservationError('Dense C physical bank span alias or prefix address mismatch')
            self.dense_c_addresses[address]=key
            self.dense_inflight[ctx]=(key,kb)
            self.dense_depths[ctx]=0
            if kb==0:self.seed_ready.add(ctx)
        elif kind == 'dense_prefix_commit':
            ctx=event['context'];kb=event['kbase'];key=(event['m_base'],event['nbase'])
            if self.pending or self.dense_inflight.get(ctx)!=(key,kb):
                raise ReservationError('Dense prefix commit before ACK or without matching restore')
            if self.dense_depths.get(ctx)!=256:
                raise ReservationError('Dense prefix commit before all increasing-K FMA steps')
            if self.dense_captured!=ctx or not self.dense_sink_complete:
                raise ReservationError('Dense prefix commit without its captured sink completion')
            end=kb+256
            if (not self.resident_shape or event['total_k']!=self.resident_shape['k'] or
                end>event['total_k'] or bool(event['final'])!=(end==event['total_k'])):
                raise ReservationError('Dense prefix has wrong terminal K')
            del self.dense_inflight[ctx]
            del self.dense_depths[ctx]
            if ctx not in self.seed_ready:
                raise ReservationError('Dense prefix commit without completed seed')
            self.seed_ready.remove(ctx)
            self.dense_captured=None
            self.dense_sink_complete=False
            if event['final']:
                if self.metrics['acknowledged_write_bytes']-self.prefix_output_committed != 16384:
                    raise ReservationError('final Dense tile lacks its complete output ACK')
                self.prefix_output_committed=self.metrics['acknowledged_write_bytes']
                self.dense_prefixes.pop(key,None)
                self.dense_final_tiles.add(key)
                address=next(a for a,v in self.dense_c_addresses.items() if v==key)
                del self.dense_c_addresses[address]
            else:
                if self.metrics['dense_partial_store_bytes']-self.prefix_store_committed != 16384:
                    raise ReservationError('Dense prefix lacks its complete FP32 snapshot store')
                self.prefix_store_committed=self.metrics['dense_partial_store_bytes']
                self.dense_prefixes[key]=end
        elif kind == 'repeat':
            count = event['count']
            if type(count) is not int or count < 0:
                raise ReservationError('invalid macro repetition')
            if not count: return
            before, time = self._snapshot(), self.book.now
            for child in event['body']:
                self.execute(child, multiplier*count)
            if self._snapshot() != before:
                raise ReservationError('repeated body leaks or changes live ownership')
            # The first iteration proves identical entry/exit ownership. The
            # rest repeat the same ordered body, not read-all/compute-all/store-all.
            if self.bound and count > 1:
                self.book.reserve(RESOURCES, (self.book.now-time)*(count-1), label='repeat:'+event['label'])
        elif kind == 'block_done':
            if self.owner or self.pending or self.allocations or 'y' not in self.published:
                raise ReservationError('block completion before terminal write ACK')
            self._run_op(op('terminal_host_fence', ('host_control',), {'terminal_fence':1}), multiplier)
            self.terminal_seen = True
        else:
            raise ReservationError('unknown event: '+kind)

    def _release(self, name):
        if name not in self.allocations:
            raise ReservationError('release of unowned buffer')
        pool, amount, _ = self.allocations.pop(name)
        self.usage[pool] -= amount
        if not self.usage[pool]: del self.usage[pool]

    def run(self, events, require_terminal=False):
        for event in events: self.execute(event)
        if (self.owner or self.pending or self.allocations or self.dense_prefixes or
            self.dense_inflight or self.dense_c_addresses or self.resident_shape or self.seed_ready):
            raise ReservationError('unfinished model ownership / missing ACK')
        if require_terminal and not self.terminal_seen:
            raise ReservationError('missing terminal Host fence')
        expected = sum(v*self.profile['parameters'][k] for k,v in self.costs.items()) if self.bound else None
        if self.bound and self.book.now != expected:
            raise ReservationError('repeated timing accounting is inconsistent')
        return dict(completed_owners=self.completed, metrics=dict(self.metrics),
                    stage_metrics=self.stage_metrics, peak_owned=dict(self.peaks),
                    timing_work_units=dict(self.costs),
                    synthetic_scheduled_cycles=self.book.now if self.bound else None,
                    sample_reservations=self.book.samples,
                    successful_path_ownership_closed=True)


def dense_groups(tokens, k, n):
    rows_per_group = max(t for t in range(1,6) if k <= 1376*16//t)*16
    for row_base in range(0, tokens, rows_per_group):
        rows = min(rows_per_group, tokens-row_base)
        mt = (rows+15)//16
        available_n = 5 if mt == 1 else 2 if mt == 2 else 1
        nbase = 0
        while nbase < n:
            full = (n-nbase)//256
            nt = min(full, available_n) if full else 1
            columns = min(256, n-nbase)
            yield dict(row_base=row_base, rows=rows, m_tiles=mt, n_contexts=nt,
                       contexts=mt*nt, nbase=nbase, columns=columns, k=k,
                       a_words_per_bank=mt*k//16, b_words_per_bank=80,
                       b_payload_words_per_bank=nt*16,
                       b_high_water_words_per_half=15*5+nt)
            nbase += nt*256


def dense_events(tokens, k, n):
    yield acquire('scratch', 'dense_scratch_lease', 1)
    previous_row = None
    for g in dense_groups(tokens,k,n):
        if g['a_words_per_bank']>1376 or g['b_words_per_bank']>80:
            raise ReservationError('Dense active tile exceeds its physical bank half/depth')
        if previous_row != g['row_base']:
            if previous_row is not None: yield release('dense_A')
            yield acquire('dense_A','A_bytes',g['rows']*k*2)
            yield read_span(g['rows']*k*4,A_BANKS,g['rows']*k//16)
            previous_row = g['row_base']
        yield acquire('dense_contexts','contexts',g['contexts'])
        yield op('Dense_group_start',('matrix',),{'matrix_group':1})
        # Existing addresses use halfBase + depthWithin16*5 + ctxN. Even nt=1
        # spans words 0..75, not 16 contiguous words. Reserve the entire real
        # 80-word half (40 KiB); payload/DDR bytes remain nt*16 useful words.
        weight_bytes = 16*g['n_contexts']*g['columns']*2
        weight_reserved_bytes = 16*80*32
        def compute(depths, context_count, useful):
            steps = depths*context_count
            return [acquire('dense_pending','metadata',1),
                    op('Dense_ordered_steps_serial_returns',('matrix',)+A_BANKS+B_BANKS,
                       dict(bank_word=steps*32,matrix_issue=steps,matrix_return_wait=steps),
                       dict(dense_wide_issues=steps,useful_macs=useful,
                            executed_macs=steps*16*((g['columns']+31)//32)*32)),
                    release('dense_pending')]
        normal = [acquire('weight_slot','B_bytes',weight_reserved_bytes),
                  read_span(weight_bytes,B_BANKS,weight_bytes//32,'dense_weight_read_bytes'),
                  *compute(16,g['contexts'],16*g['rows']*g['n_contexts']*g['columns']),
                  release('weight_slot')]
        yield repeat(k//16-1, normal, 'Dense_K16_chunks; increasing K; conservative no ping-pong overlap')
        yield acquire('weight_slot','B_bytes',weight_reserved_bytes)
        yield read_span(weight_bytes,B_BANKS,weight_bytes//32,'dense_weight_read_bytes')
        yield from compute(15,g['contexts'],15*g['rows']*g['n_contexts']*g['columns'])
        # Return/store/ACK each final context before issuing the next final K.
        # This avoids inventing space for five simultaneous wide results.
        for ctx in range(g['contexts']):
            cm = ctx//g['n_contexts']
            rows = min(16,g['rows']-cm*16)
            yield from compute(1,1,rows*g['columns'])
            yield acquire('dense_result','matrix_results',1)
            yield acquire('dense_final','dense_final_values',1)
            yield op('Dense_result_capture_into_existing_finalValue',(),{'control':1})
            yield release('dense_result')
            yield from write_span(rows*g['columns']*4)
            yield release('dense_final')
        yield release('weight_slot')
        yield op('Dense_group_done',('matrix',),{'matrix_group':1})
        yield release('dense_contexts')
    yield release('dense_A')
    yield release('scratch')


def resident_dense_plan(tokens, k, n):
    """Capacity/traffic contract of an unimplemented KC256 Dense mapping.

    External A/D remain FP32; A SRAM holds the SAME existing RNE BF16 operands.
    Each C snapshot is the original FP32 accumulator after an increasing-K
    prefix. A seeded continuation, not independently summed K blocks, is needed.
    """
    if tokens != 128 or (k, n) not in [(a,b) for _,a,b in BOUND.MATRICES]:
        raise ReservationError('resident candidate supports only the seven cold M128 Dense shapes')
    kc, ntile = 256, 256
    nt = n//ntile
    slots = 3 if k == 8960 else 1
    full_a = k == 1536
    a_bytes = tokens*(k if full_a else kc)*2
    c_bytes = tokens*ntile*4*slots
    b_bytes = 2*kc*ntile*2
    if a_bytes+c_bytes > 524288 or b_bytes > 262144:
        raise ReservationError('resident candidate exceeds a physical bank partition')
    groups = (nt+slots-1)//slots
    external_a = tokens*k*4*(1 if full_a else groups)
    partial = tokens*n*4*(k//kc-1)
    return dict(tokens=tokens,k=k,n=n,k_chunk=kc,n_tile=ntile,
        n_tiles_retained=slots,n_groups=groups,full_a_resident=full_a,
        a_operand_bf16_bytes=a_bytes,c_snapshot_fp32_bytes=c_bytes,
        b_ping_pong_reserved_bytes=b_bytes,
        a_c_words_per_bank=(a_bytes+c_bytes)//512,b_words_per_bank=b_bytes//512,
        a_c_objects=[dict(name='A_operand',start_word=0,end_word=a_bytes//512)]+
                   [dict(name='C'+str(i),start_word=a_bytes//512+i*256,
                         end_word=a_bytes//512+(i+1)*256) for i in range(slots)],
        b_objects=[dict(name='B0',start_word=0,end_word=256),dict(name='B1',start_word=256,end_word=512)],
        m_tiles=8,physical_context_groups=[5,3],physical_context_limit=5,
        external_a_fp32_read_bytes=external_a,external_weight_bf16_read_bytes=k*n*2,
        external_d_fp32_write_bytes=tokens*n*4,
        partial_restore_bytes=partial,partial_store_bytes=partial,
        matrix_wide_issues=tokens*k*n//4096,useful_macs=tokens*k*n,
        candidate_only=True,accumulator_seed_interface_implemented=False,
        physical_sram_repartition_implemented=False)


def resident_dense_tiles(tokens, k, n):
    """Concrete tile-prefix order for independently checking the event loops."""
    p=resident_dense_plan(tokens,k,n)
    for ng in range(0,n,p['n_tiles_retained']*256):
        for kb in range(0,k,256):
            for nb in range(ng,min(n,ng+p['n_tiles_retained']*256),256):
                for mb,count in ((0,5),(80,3)):
                    yield dict(n_group=ng,kbase=kb,nbase=nb,m_base=mb,contexts=count,
                               rows=16*count,depths=256,columns=256,
                               restore=kb!=0,final=kb+256==k)


def resident_dense_events(tokens, k, n):
    p=resident_dense_plan(tokens,k,n)
    yield dict(event='dense_residency_begin',tokens=tokens,k=k,n=n)
    yield acquire('scratch','dense_scratch_lease',1)
    yield acquire('resident_B_halves','B_bytes',p['b_ping_pong_reserved_bytes'])
    if p['full_a_resident']:
        yield acquire('resident_A','A_bytes',p['a_operand_bf16_bytes'])
        yield read_span(tokens*k*4,A_BANKS,tokens*k*2//32,'dense_activation_read_bytes')
    for ng in range(0,n,p['n_tiles_retained']*256):
        live_nt=min(p['n_tiles_retained'],(n-ng)//256)
        yield acquire('resident_C','A_bytes',tokens*256*4*live_nt)
        for kb in range(0,k,256):
            if not p['full_a_resident']:
                yield acquire('resident_A','A_bytes',tokens*256*2)
                yield read_span(tokens*256*4,A_BANKS,tokens*256*2//32,'dense_activation_read_bytes')
            for nb in range(ng,ng+live_nt*256,256):
                # Both physical B halves stay reserved. This conservative
                # serial scenario fills one half; it claims no prefetch overlap.
                yield read_span(256*256*2,B_BANKS,256*256*2//32,'dense_weight_read_bytes')
                for mb,ct in ((0,5),(80,3)):
                    yield acquire('dense_contexts','contexts',ct)
                    yield op('resident_Dense_group_start',('matrix',),{'matrix_group':1})
                    for ctx in range(ct):
                        yield dict(event='dense_prefix_begin',m_base=mb+ctx*16,nbase=nb,
                                   kbase=kb,context=ctx,
                                   c_word_address=p['a_operand_bf16_bytes']//512+
                                     ((nb-ng)//256)*256+(mb//16+ctx)*32)
                    if kb:
                        # A/C SRAM and accumulator write port are exclusively
                        # reserved while restoring. Hardware seed route is absent.
                        size=ct*16*256*4
                        yield op('candidate_FP32_seed_restore_before_compute',A_BANKS+('matrix',),
                                 dict(bank_word=size//32,fabric_beat=size//64,control=ct),
                                 dict(dense_partial_restore_bytes=size,dense_seed_contexts=ct))
                    yield acquire('dense_pending','metadata',1)
                    steps=255*ct
                    yield op('resident_Dense_increasing_K_prefix',('matrix',)+A_BANKS+B_BANKS,
                             dict(bank_word=steps*32,matrix_issue=steps,matrix_return_wait=steps),
                             dict(dense_wide_issues=steps,useful_macs=steps*4096,executed_macs=steps*4096))
                    yield release('dense_pending')
                    # Drain each context's last K before emitting the next one:
                    # one existing finalValue and one result FIFO entry suffice.
                    for ctx in range(ct):
                        yield acquire('dense_pending','metadata',1)
                        yield dict(op('resident_Dense_last_K_of_chunk',('matrix',)+A_BANKS+B_BANKS,
                                 dict(bank_word=32,matrix_issue=1,matrix_return_wait=1),
                                 dict(dense_wide_issues=1,useful_macs=4096,executed_macs=4096)),dense_context=ctx)
                        yield release('dense_pending')
                        yield acquire('dense_result','matrix_results',1)
                        yield acquire('dense_final','dense_final_values',1)
                        yield dict(op('resident_Dense_capture_existing_finalValue',(),{'control':1}),dense_context=ctx)
                        yield release('dense_result')
                        if kb+256==k:
                            for transfer in write_span(16*256*4):
                                yield dict(transfer,dense_context=ctx)
                        else:
                            yield dict(op('candidate_FP32_prefix_store_before_context_reuse',A_BANKS,
                                     dict(bank_word=16*256*4//32,fabric_beat=16*256*4//64),
                                     dict(dense_partial_store_bytes=16*256*4)),dense_context=ctx)
                        yield dict(event='dense_prefix_commit',m_base=mb+ctx*16,nbase=nb,
                                   kbase=kb,context=ctx,total_k=k,final=kb+256==k)
                        yield release('dense_final')
                    yield op('resident_Dense_group_drained',('matrix',),{'matrix_group':1})
                    yield release('dense_contexts')
            if not p['full_a_resident']: yield release('resident_A')
        yield release('resident_C')
    if p['full_a_resident']: yield release('resident_A')
    yield release('resident_B_halves')
    yield release('scratch')
    yield dict(event='dense_residency_end')


def norm_events(tokens):
    load_chunk = [read_span(64), op('norm_row_store',CORE_BANKS,{'fabric_beat':1}),
                  vector(), scalar('add',16)]
    emit_chunk = [op('norm_row_read',CORE_BANKS,{'fabric_beat':1}),read_span(64),
                  vector(2),*write_span(64)]
    row = [acquire('norm_row','core_bytes',1536*4),acquire('norm_registers','core_vectors',3),
           repeat(96,load_chunk,'Norm input chunks: read/store/square/16 ordered adds'),
           scalar('mul'),scalar('add'),scalar('sqrt'),scalar('div'),
           repeat(96,emit_chunk,'Norm gamma/read/scale/product/store/ACK'),
           release('norm_registers'),release('norm_row')]
    yield repeat(tokens,row,'Norm token rows')


def bias_events(tokens, width):
    yield acquire('bias_registers','core_vectors',2)
    yield repeat(tokens*width//16,[read_span(64),read_span(64),vector(),*write_span(64)],
                 'Bias input/bias/add/write/ACK per sixteen elements')
    yield release('bias_registers')


def rope_events(tokens, heads):
    yield acquire('rope_registers','core_vectors',7)
    yield repeat(tokens*heads*4,[read_span(64),read_span(64),read_span(64),read_span(64),
                 vector(5),*write_span(64,'even'),vector(),*write_span(64,'odd')],
                 'RoPE four operands, five separate ALU ops, even ACK, final add, odd ACK')
    yield release('rope_registers')


def elementwise_events(elements, copy=False):
    # Canonical full tiles; all public M128/M1024 sizes are multiples of 1024.
    for base in range(0,elements,1024):
        size = min(1024,elements-base)
        beats = size//16
        yield acquire('elementwise_tile','elementwise_bytes',3*size*4)
        load = [read_span(64),op('elementwise_store_input',ELEM_BANKS,{'fabric_beat':1})]
        yield repeat(beats,load,'elementwise load A')
        if not copy: yield repeat(beats,load,'elementwise load B')
        compute = [op('elementwise_read_A',ELEM_BANKS,{'fabric_beat':1})]
        if not copy: compute.append(op('elementwise_read_B',ELEM_BANKS,{'fabric_beat':1}))
        compute.append(op('copy_mux',(),{'control':1}) if copy else vector(elementwise=True))
        compute.append(op('elementwise_store_C',ELEM_BANKS,{'fabric_beat':1}))
        yield repeat(beats,compute,'elementwise ordered tile compute')
        yield repeat(beats,[op('elementwise_read_C',ELEM_BANKS,{'fabric_beat':1}),*write_span(64)],
                     'elementwise output and ACK')
        yield release('elementwise_tile')


def silu_events(tokens):
    body = [acquire('silu_input','silu_inputs',1),read_span(64),read_span(64),
            op('existing_silu16_six_phase_wrapper',('silu16',),{'silu_group':1},
               {'silu_vector_groups':1,'silu_lane_primitive_groups':6}),
            release('silu_input'),acquire('silu_output','silu_outputs',1),
            *write_span(64),release('silu_output')]
    yield repeat(tokens*8960//16,body,'SiLU gate/up/read, existing wrapper, store, ACK; no overlap')


def kv_append_events(tokens):
    for half in ('K','V'):
        yield op('KV_copy_'+half+'_half',(),{'control':1})
        yield from elementwise_events(tokens*256,True)


def attention_events(tokens, contexts):
    """Translate the published Attention iterator, retaining its causal lifetimes."""
    layout = ATT.scratch_layout(tokens,contexts)
    seen_contexts, captured = set(), []
    for e in ATT.iter_events(tokens,contexts):
        kind = e['event']
        if kind == 'owner_acquire':
            yield acquire('scratch','dense_scratch_lease',1)
            yield acquire('attention_A','A_bytes',layout['used_a_bytes'])
            yield acquire('attention_B','B_bytes',layout['used_b_bytes'])
        elif kind in ('load_kv','load_q'):
            yield read_span(e['external_fp32_bytes'],A_BANKS,e['scratch_bf16_bytes']//32)
        elif kind == 'group_start':
            seen_contexts = set()
            yield op('Attention_group_start',('matrix',),{'matrix_group':1})
        elif kind == 'operand_gather':
            words = (e.get('q_bank_word_reads',0)+e.get('k_bank_word_reads',0)
                     +e.get('probability_bank_word_reads',0)+e.get('v_bank_word_reads',0))
            yield op('Attention_serial_A_bank_gather',A_BANKS,{'bank_word':words},
                     {'attention_A_bank_read_bytes':words*32})
        elif kind == 'matrix_issue':
            ctx = e['context']
            if ctx not in seen_contexts:
                seen_contexts.add(ctx)
                yield acquire('ctx:'+str(ctx),'contexts',1)
            yield acquire('pending:'+str(ctx),'metadata',1)
            yield op(e['phase']+'_issue',('matrix',),{'matrix_issue':1},
                     {'attention_wide_issues':1,'useful_macs':e['useful_macs'],
                      'executed_macs':e['executed_macs']})
        elif kind == 'matrix_return':
            yield op('Attention_return_and_relevant_finite_check',('matrix',),{'matrix_return_wait':1})
            yield release('pending:'+str(e['context']))
            if e['emit']: yield acquire('returned','matrix_results',1)
        elif kind == 'partial_store':
            yield acquire('partial:'+str(e['slot']),'partial_slots',1)
            yield op('partial_C_store',B_BANKS,{'bank_word':e['bytes']//32})
            yield release('returned')
        elif kind == 'ordered_stripe_add':
            n = e['fp32_adds']
            words = 3 if e['initial_positive_zero'] else 4
            yield op('per_pair_partial_read_score_read_scalar_add_RMW',A_BANKS+B_BANKS+('scalar',),
                     {'bank_word':n*words,'scalar_add':n},{'scalar_add_requests':n})
        elif kind == 'partial_release':
            yield release('partial:'+str(e['slot']))
        elif kind == 'scale_and_softmax':
            p = e['useful_pairs']
            yield op('per_row_ascending_scale_max_exp_sum_reciprocal_probability',A_BANKS+('scalar',),
                     dict(bank_word=9*p,scalar_mul=2*p,scalar_add=2*p,scalar_exp=p,scalar_div=e['rows']),
                     dict(scalar_mul_requests=2*p,scalar_add_requests=2*p,
                          scalar_exp_requests=p,scalar_div_requests=e['rows']))
        elif kind == 'capture_final_row':
            for row in e['rows']:
                name = 'capture:'+str(row)
                captured.append(name)
                yield acquire(name,'captured_rows',1)
            yield op('PV_causal_row_final_capture',B_BANKS,{'bank_word':e['bytes']//32})
            yield release('returned')
        elif kind == 'group_done':
            yield op('Attention_group_done',('matrix',),{'matrix_group':1})
            for ctx in sorted(seen_contexts): yield release('ctx:'+str(ctx))
        elif kind == 'output_write':
            yield op('PV_capture_read_for_write',B_BANKS,{'bank_word':e['bytes']//32})
            yield dict(event='write',tag='attention_output',bytes=e['bytes'])
        elif kind == 'output_ack':
            yield dict(event='ack',tag='attention_output')
            for name in captured: yield release(name)
            captured = []
        elif kind == 'owner_release':
            yield release('attention_B')
            yield release('attention_A')
            yield release('scratch')
        else:
            raise ReservationError('unmapped Attention event: '+kind)


def stages(tokens, contexts=1, dense_mapping='current'):
    dims = {name:(k,n) for name,k,n in BOUND.MATRICES}
    mapping_capacities(dense_mapping)
    if dense_mapping!='current' and tokens!=128:
        raise ReservationError('resident candidate is M128 only; M1024 Attention A exceeds its partition')
    def dense(name):
        function=dense_events if dense_mapping=='current' else resident_dense_events
        return function(tokens,*dims[name])
    yield ('input_norm',['input_norm'],['x'],['n0'],norm_events(tokens))
    yield ('q',['q'],['n0'],['q_projected'],dense('q'))
    yield ('q_bias',['q_bias'],['q_projected'],['q_biased'],bias_events(tokens,1536))
    yield ('q_rope',['q_rope'],['q_biased'],['q_rotated'],rope_events(tokens,12))
    yield ('k',['k'],['n0'],['k_projected'],dense('k'))
    yield ('k_bias',['k_bias'],['k_projected'],['k_biased'],bias_events(tokens,256))
    yield ('k_rope',['k_rope'],['k_biased'],['k_rotated'],rope_events(tokens,2))
    yield ('v',['v'],['n0'],['v_projected'],dense('v'))
    yield ('v_bias',['v_bias'],['v_projected'],['v_biased'],bias_events(tokens,256))
    yield ('kv_append',['kv_append'],['k_rotated','v_biased'],['kv_cache'],kv_append_events(tokens))
    yield ('attention',['qk','softmax','pv'],['q_rotated','kv_cache'],['att'],attention_events(tokens,contexts))
    yield ('o',['oproj'],['att'],['o'],dense('o'))
    yield ('attn_residual',['attn_residual'],['o','x'],['r'],elementwise_events(tokens*1536))
    yield ('post_norm',['post_norm'],['r'],['n1'],norm_events(tokens))
    yield ('gate',['gate'],['n1'],['gate'],dense('gate'))
    yield ('up',['up'],['n1'],['up'],dense('up'))
    yield ('silu',['silu_mul'],['gate','up'],['act'],silu_events(tokens))
    yield ('down',['down'],['act'],['down'],dense('down'))
    yield ('residual',['residual'],['down','r'],['y'],elementwise_events(tokens*1536))


def iter_events(tokens,contexts=1,dense_mapping='current'):
    ATT._tokens(tokens)
    ATT.scratch_layout(tokens,contexts)
    capacities=mapping_capacities(dense_mapping)
    layout=ATT.scratch_layout(tokens,contexts)
    if layout['used_a_bytes']>capacities['A_bytes'] or layout['used_b_bytes']>capacities['B_bytes']:
        raise ReservationError('Attention address high-water exceeds selected Dense SRAM partition')
    for name, public, requires, produces, body in stages(tokens,contexts,dense_mapping):
        yield dict(event='owner_begin',name=name,public_stages=public,requires=requires)
        yield from body
        yield dict(event='owner_end',name=name,produces=produces)
    yield dict(event='block_done')


def resource_issue_floors(result, useful_macs):
    """One-cycle service floors, never substitute for unbound macro timings.

    Per owner, independent resources may overlap ideally (max). Across owners,
    this explicit serialized model cannot overlap (sum). Counts do not price
    seed/control, real SFU latency, bank access, DDR delay or pipeline draining.
    """
    rows=[]
    def floors(metrics):
        external=metrics.get('external_read_bytes',0)+metrics.get('external_write_bytes',0)
        return dict(idma_64b_read_write=(external+63)//64,
            matrix_issues=metrics.get('dense_wide_issues',0)+metrics.get('attention_wide_issues',0),
            scalar_requests=sum(v for k,v in metrics.items() if k.startswith('scalar_') and k.endswith('_requests')),
            core_vector_requests=metrics.get('core_vector_requests',0),
            elementwise_requests=metrics.get('elementwise_vector_requests',0),
            silu_primitive_issues=metrics.get('silu_lane_primitive_groups',0))
    for owner in result['completed_owners']:
        counts=floors(result['stage_metrics'][owner])
        rows.append(dict(owner=owner,resource_cycle_floors=counts,cycles_lower_bound=max(counts.values())))
    total=sum(row['cycles_lower_bound'] for row in rows)
    return dict(status='SOURCE_COUNT_CONDITIONAL_LOWER_BOUNDS_NOT_PREDICTION',
        primitive_service_cycles_assumed_at_least=1,
        independent_resource_floors=floors(result['metrics']),
        serial_owner_floors=rows,serial_owners_cycles_lower_bound=total,
        useful_utilization_upper_bound=useful_macs/(4096*total),
        useful_macs=useful_macs,fixed_matrix_macs_per_cycle=4096,
        primitive_latency_binding_applied=False,
        assumptions=['Successful path of the selected software event graph; hardware routing not demonstrated.',
                     '64B maximum external service per cycle, one IDMA transaction shared by reads/writes.',
                     'Within-owner resource overlap is idealized only for a lower bound; owners remain serialized.',
                     'No count is a full-cycle estimate; command bytes, bank waits, seed arbitration, flags and drain add unresolved costs.'])


def report(root,tokens=128,contexts=1,profile=None,dense_mapping='current'):
    if type(tokens) is not int or tokens not in (128,1024):
        raise ValueError('public reports support M128/M1024 cold prefill only')
    for name,expected in SOURCE_PINS.items():
        path = Path(root)/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('source changed; re-audit resource model: '+name)
    profile = profile or timing_profile()
    capacities=mapping_capacities(dense_mapping)
    result = Scheduler(profile,dense_mapping).run(iter_events(tokens,contexts,dense_mapping),require_terminal=True)
    bound = BOUND.calculate(tokens)
    if result['metrics']['useful_macs'] != bound['total_useful_macs']:
        raise ReservationError('full-DAG useful MAC coverage mismatch')
    resident = None if dense_mapping=='current' else [dict(name=name,**resident_dense_plan(tokens,k,n))
                                                     for name,k,n in BOUND.MATRICES]
    weight_bytes=bound['weight_ingress_bytes'] if resident is None else sum(p['external_weight_bf16_read_bytes'] for p in resident)
    if result['metrics']['dense_weight_read_bytes'] != weight_bytes:
        raise ReservationError('Dense weight-read schedule mismatch')
    return dict(schema_version=2,status='SYNTHETIC_RESOURCE_SCENARIO' if profile['synthetic'] else 'UNBOUND_RESOURCE_RESERVATION_MODEL',
                workload=bound['workload'],source_sha256=SOURCE_PINS,
                policy='Explicit Dense mapping plus candidate rectangular Attention; serialized successful-path software scenario; no hardware or numerical policy changes',
                dense_mapping=dense_mapping,resident_dense_phases=resident,
                dense_schedule_geometry=bound['dense_phases'] if resident is None else resident,
                dense_weight_bank_layout=(dict(
                    address_rule='halfBase + depthWithin16*5 + ctxN',
                    physical_half_bases_words=[0,80],reserved_words_per_bank_per_live_half=80,
                    reserved_bytes_per_live_half=40960,
                    payload_words_per_bank='16*nContexts',
                    high_water_span_words_per_half='15*5+nContexts',
                    live_halves_in_serial_baseline=1) if resident is None else dict(
                    candidate_only=True,a_c_words_per_bank=1024,b_words_per_bank=512,
                    b_half_bases_words=[0,256],reserved_words_per_bank_per_live_half=256,
                    reserved_bytes_per_live_half=131072,both_halves_reserved=True,
                    prefetch_overlap_credited=False,current_hardware_layout_changed=False)),
                attention_schedule=dict(qk_contexts=contexts,pv_contexts=1,
                                        source_iterator='qwen2_rectangular_attention_model.iter_events',
                                        candidate_routing_not_implemented=True,
                                        allocated_a_bytes=capacities['A_bytes'],allocated_b_bytes=capacities['B_bytes'],
                                        used_a_bytes=ATT.scratch_layout(tokens,contexts)['used_a_bytes'],
                                        used_b_bytes=ATT.scratch_layout(tokens,contexts)['used_b_bytes']),
                stages=[dict(owner=n,public_stages=p,requires=r,produces=o) for n,p,r,o,_ in stages(tokens,contexts,dense_mapping)],
                resources=dict(exclusive_ports=sorted(RESOURCES),capacities=capacities,
                               dense_bank_word_bytes=32,core_and_elementwise_bank_word_bytes=16,
                               shared_l2_banks_per_arbitration_group=4,idma_max_live_transactions=1,
                               owner_routing_slots=1,existing_accumulator_bytes=81920,
                               existing_matrix_result_fifo_bytes=32768,existing_dense_final_value_bytes=16384,
                               matrix_macs=4096,scalar_cores=1,core_vector_alu_lanes=16,
                               elementwise_alu_lanes=16,silu_scalar_lanes=16,
                               silu_variants_are_alternatives=True,overlap_enabled=False),
                timing_profile=profile,
                traffic_scope='Modeled tensor/parameter transfers only; descriptor/command/policy bytes remain unresolved',
                unresolved_traffic=dict(command_tensor_policy_metadata_bytes=None),
                unbound_timing_parameters=[k for k,v in profile['parameters'].items() if v is None],
                known_sfu_source_lower_bounds=dict(
                    version='v1_loose_wrapper_bounds_preserved',
                    scalar_add_mul_request_ii_at_least=3,
                    scalar_exp_saturated_request_ii_at_least=3,
                    scalar_exp_nonsaturated_request_ii_at_least=20,
                    scalar_div_fsm_request_ii_at_least=4,
                    scalar_div_actual_latency_and_ii=None,
                    silu16_all_saturated_group_ii_at_least=21,
                    silu16_any_nonsaturated_group_ii_at_least=38,
                    silu16_edge_span_formula='21*N+17*L-1; L groups have any lane abs(gate)<80',
                    real_gate_branch_population_not_loaded=True,
                    generic_sfu_or_multi_context_rewrite_included=False),
                known_sfu_source_timing=SFU.timing_binding(root),
                source_timing_application='Primitive and wrapper formulas only; not substituted for owner-level macro timing. Branch populations and calc/resume, memory/ACK costs remain unbound in this full-DAG report.',
                reservation_result=result,
                resource_issue_floors=resource_issue_floors(result,bound['total_useful_macs']),
                predicted_full_block_cycles=None,rtl_measured_cycles=None,rtl_measured_utilization=None,
                scope=dict(numerical_execution=False,rtl_execution=False,hardware_deadlock_proof=False,
                           hardware_acceptance=False,credible_full_cycle_prediction=False),
                omitted_or_abstracted=[
                    'The resident_m128_nc3 option requires unimplemented SRAM repartition, exact FP32 accumulator seed/partial routes and arbitration; no additional port/context or cross-owner forwarding is credited.',
                    'This is an ordered macro/resource model, not a Chisel FSM execution trace or a lowering implementation.',
                    'Host command/tensor/policy fetch byte counts and exact decoding are opaque admission work with unbound cost; only 21-stage ordering is explicit.',
                    'DDR root alignment, individual AXI bursts/legalization, backpressure, read commit and B ACK timing remain unknown; per-64B synthetic charges are assumptions.',
                    'Dense K16 repeats, Norm row/chunk loops, elementwise tiles and SiLU groups retain ordered bodies but internal request/response FSM cycles are not expanded.',
                    'Attention scratch lease/gather/capture routing is the published pre-RTL candidate, not current Host hardware.',
                    'All bank reads/writes conflict conservatively; actual independent-bank or Dense ping-pong/SiLU memory overlap is not credited.',
                    'Matrix feedback, input-dependent SFU branch populations, owner control/overlap and final Host fence remain unbound; separately pinned primitive/wrapper formulas do not complete those macro costs.',
                    'Only successful finite work is scheduled; arithmetic values, flags, faults, retries, cancellation and fault-drain behavior are not simulated.',
                    'Original Matrix finite checks and Scalar underflow/error policy remain required; no new vectorized Attention/SFU route is assumed.',
                ])


def observed_silu_host_bound(root=ROOT, *, enable_h2048_rms_borrower=False,
                             external_elementwise_loan=False):
    """Refine the ORIGINAL Host bound with one frozen software-input census.

    This is deliberately separate from the rectangular candidate calendar.
    The gate audit remains historical evidence at its exact hash; it is not
    rebound to a later Python model implementation or claimed as RTL input.
    """
    if enable_h2048_rms_borrower is not False or external_elementwise_loan is not False:
        raise ValueError('saved v0 review requires the original default-disabled borrower/loan profile')
    root=Path(root)
    audit_path=root/V0_SILU_AUDIT
    raw=audit_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=V0_SILU_AUDIT_SHA256:
        raise ValueError('saved v0 SiLU branch evidence changed')
    audit=json.loads(raw)
    host=BOUND.host_schedule_report(root,128)
    binding=SFU.timing_binding(root)
    # Source facts about physical arithmetic/owners must remain current. The
    # historical software producer/model identities are retained separately.
    hardware_pins={k:v for k,v in audit['source_sha256'].items()
                   if not k.startswith('scripts/')}
    hardware_pins.update(audit['receipt']['source_identity']['source_sha256'])
    historical_hardware_pins = dict(hardware_pins)
    hardware_pins = _current_v0_hardware_pins(root, historical_hardware_pins)
    historical_upstream=audit['source_timing_binding']['upstream']
    current_upstream=binding['upstream']
    if (historical_upstream['commit']!=current_upstream['commit'] or
        any(current_upstream['source_sha256'].get(p)!=h
            for p,h in historical_upstream['source_sha256'].items())):
        raise ValueError('saved branch audit upstream timing identity changed')
    groups=audit['gate']['groups']
    assert groups==128*8960//16 and audit['gate']['elements']==groups*16
    assert audit['gate']['all_nonsaturated'] and audit['d25_lane_requests']==0
    assert audit['d26_lane_requests']==groups*16 and audit['wrapper_d26_groups']==groups
    span=45*groups+17*groups+groups-1
    assert span==audit['wrapper_arithmetic_edge_span']
    old=host['issue_counts']['silu_16_lane_primitive_issue_cycles']
    remaining=host['non_dense_cycles_lower_bound']-old
    current_total=host['current_dense_cycles_lower_bound']+remaining+span
    ideal_total=host['ideal_dense_cycles_lower_bound']+remaining+span
    macs=host['useful_macs']
    return dict(schema_version=1,status='CONDITIONAL_SAVED_INPUT_HOST_BOUND_NOT_PREDICTION',
        profile='original Host mapping / cold M128 / successful path / observed v0 gate branches / divider options0',
        source_sha256={**host['source_sha256'],**hardware_pins},
        evidence=dict(path=V0_SILU_AUDIT,sha256=V0_SILU_AUDIT_SHA256,
                      original_source_model_sha256=audit['source_sha256']['scripts/qwen2_shared_sfu_schedule.py'],
                      gate=audit['gate'],producer_status=audit['receipt']['status'],
                      source_review=dict(commit='f16df50adfb0f1f4bc668c517a2e29accffe6753',
                          profile='original Qwen2 Host; enableH2048RmsBorrower=false; externalElementwiseLoan=false',
                          h2048_borrower_included=False, current_host_reexecuted=False,
                          current_rtl_measured=False, proof='scoped source review, not a new execution',
                          historical_hardware_sha256=historical_hardware_pins,
                          current_hardware_sha256=hardware_pins,
                          reviewed_identity_pairs=V0_HOST_SOURCE_REVIEW)),
        workload=host['workload'],fixed_matrix_macs_per_cycle=4096,useful_macs=macs,
        formula_version='host_bound_v2_replace_only_silu_issue_floor',
        previous=dict(formula_version='host_bound_v1_one_cycle_per_nonoverlapping_request',
                      cycles_lower_bound=host['whole_block_cycles_lower_bound'],
                      utilization_upper_bound=host['useful_utilization_upper_bound']),
        terms=dict(removed_old_silu_floor=old,new_silu_arithmetic_edge_span=span,
                   unchanged_other_non_dense_lower_bound=remaining,
                   current_dense_lower_bound=host['current_dense_cycles_lower_bound'],
                   ideal_dense_lower_bound=host['ideal_dense_cycles_lower_bound']),
        whole_block_cycles_lower_bound=current_total,
        useful_utilization_upper_bound=macs/(4096*current_total),
        ideal_dense_whole_block_cycles_lower_bound=ideal_total,
        ideal_dense_useful_utilization_upper_bound=macs/(4096*ideal_total),
        assumptions=[
            'The actual SFU input has the saved software-producer branch population; actual Host production of these gates is not demonstrated.',
            'All original numeric/error gates permit full successful execution; current model producer remains NOT_ACCEPTED.',
            'Original owners serialize; SiLU internal memory overlap cannot overlap another owner.',
            'Only the old six-primitive issue floor is replaced; do not add it, exp microsteps or divider service again.',
            'The new internal request-to-result edge span omits first/last owner transitions, memory and ACK; it is a conservative lower bound, not an exact owner duration.',
            'Applies only to this cold M128 and current mapping; no carried, M1024 or candidate-routing generalization.'],
        predicted_full_block_cycles=None,rtl_measured_cycles=None,rtl_measured_utilization=None,
        scope=dict(actual_host_gate_production=False,numerical_acceptance=False,
                   candidate_mapping=False,rtl_execution=False,cycle_prediction=False))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tokens',type=int,choices=(128,1024),default=128)
    p.add_argument('--contexts',type=int,choices=(1,5),default=1)
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--synthetic-profile',action='store_true')
    p.add_argument('--observed-silu-host-bound',action='store_true')
    p.add_argument('--dense-mapping',choices=DENSE_MAPPINGS,default='current')
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    if args.observed_silu_host_bound:
        if args.synthetic_profile or args.tokens!=128 or args.contexts!=1 or args.dense_mapping!='current':
            p.error('saved-input Host bound requires cold M128, original context profile and no synthetic timings')
        result=observed_silu_host_bound(args.root)
    else:
        result=report(args.root,args.tokens,args.contexts,timing_profile(args.synthetic_profile),args.dense_mapping)
    encoded=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        with args.out.open('x') as stream: stream.write(encoded)
    else: print(encoded,end='')


if __name__ == '__main__': main()
