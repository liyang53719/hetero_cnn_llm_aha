"""Actual L3 RMS/Qgate/K/V -> Q/K Norm256 -> Q/K partial64 RoPE.

This is a software transport composition of the original projection prefix
and memory-fed owners. It owns no arithmetic resource, calls no forward
reference, and does not model an attention block or an actual KV cache.
All allocations must exist before the original prefix is constructed.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass

from ..projection_driver import (
    L3ProjectionCoordinator, L3ProjectionPlan, ORDER as PREFIX_ORDER, sha,
)
from .driver import TypedNormRopeDriver
from .owner import QkNorm256Job, QkNorm256Owner, PartialRope64Job, PartialRope64Owner, source_identity, POLICY, TORCH_DEFAULT256_POLICY
from .scalar import NormRopeScalar
from ...qwen35_gdn_prefill.typed_dense import GUARD


ORDER = (*PREFIX_ORDER, 'q_norm', 'k_norm', 'q_rope', 'k_rope')
SCOPE = 'QWEN35_L3_NORM_ROPE_TYPED_SOFTWARE_COORDINATOR'


def require(ok, why):
    if not ok:
        raise ValueError('typed L3 Norm/RoPE chain: ' + why)


def _fields(value):
    return tuple(vars(value).items()) if hasattr(value, '__dict__') else value


@dataclass(frozen=True)
class L3NormRopePlan:
    projection: L3ProjectionPlan
    q_norm_weight: int
    k_norm_weight: int
    q_norm: int
    k_norm: int
    gate: int
    q_rope: int
    k_rope: int
    trig: int
    position_base: int
    trig_tokens: int
    norm_policy: int = POLICY

    def validate(self):
        require(type(self.projection) is L3ProjectionPlan, 'original immutable projection plan required')
        self.projection.validate()
        require(type(self.norm_policy) is int and self.norm_policy in (POLICY, TORCH_DEFAULT256_POLICY),
                'explicit C1/C2 Norm policy required')
        require(self.projection.tag_base <= (1 << 32) - len(ORDER), 'eight distinct UInt32 owner tags required')
        for name in ('q_norm_weight', 'k_norm_weight', 'q_norm', 'k_norm', 'gate', 'q_rope', 'k_rope', 'trig'):
            value = getattr(self, name)
            require(type(value) is int and 0 <= value < 1 << 56 and value % 64 == 0,
                    name + ' must be an aligned 56-bit address')
        require(type(self.position_base) is int and 0 <= self.position_base < 1 << 32 and
                type(self.trig_tokens) is int and 0 < self.trig_tokens < 1 << 32 and
                self.position_base + self.projection.tokens <= self.trig_tokens,
                'absolute trig position range')

    @property
    def tokens(self):
        return self.projection.tokens


@dataclass(frozen=True)
class L3NormRopeResult:
    tag: int
    status: str | None
    tokens: int
    q_rope: int | None
    k_rope: int | None
    v: int | None
    gate: int | None
    acknowledged_write_bytes: int
    failed_role: str | None = None


class L3NormRopeCoordinator:
    """One genuine prefix and the same scalar/memory through eight commands.

    Construction and start do not accept precomputed intermediates. Each next
    owner starts only after the preceding real terminal has been accepted and
    all output bytes acknowledged. The last K RoPE terminal is also the chain
    terminal: backpressure keeps that destination unpublished. Accepted older
    stages remain published on later failure; only complete chain validity is
    withheld. Abort/reset retires transport, retains poison and never launches
    another stage. Resetting owners is an explicit caller operation afterward.
    """
    def __init__(self, *, prefix, norm_owner, rope_owner, plan):
        require(type(prefix) is L3ProjectionCoordinator and type(plan) is L3NormRopePlan,
                'genuine original prefix and immutable complete plan required')
        plan.validate()
        require(prefix.plan is plan.projection and not prefix.started and prefix.response is None and
                prefix.active is None and not prefix.commands and not prefix.receipts,
                'prefix must be the same unstarted original plan invocation')
        require(type(norm_owner) is QkNorm256Owner and type(rope_owner) is PartialRope64Owner and
                isinstance(prefix.scalar, NormRopeScalar) and
                norm_owner.scalar is rope_owner.scalar is prefix.scalar is prefix.rms.scalar,
                'same existing NormRopeScalar across RMS, Norm and RoPE required')
        self.prefix, self.norm, self.rope, self.plan = prefix, norm_owner, rope_owner, plan
        self.memory, self.scalar = prefix.memory, prefix.scalar
        self.matrix, self.vector, self.dense = prefix.matrix, prefix.vector, prefix.dense
        t, p, tag = plan.tokens, plan.projection, plan.projection.tag_base
        self.jobs = (*prefix.jobs,
            QkNorm256Job(tag + 4, p.packed_q_gate, plan.q_norm_weight, plan.q_norm, t, 0, plan.gate, policy=plan.norm_policy),
            QkNorm256Job(tag + 5, p.k, plan.k_norm_weight, plan.k_norm, t, 1, policy=plan.norm_policy),
            PartialRope64Job(tag + 6, plan.q_norm, plan.trig, plan.q_rope, t, 8,
                             plan.position_base, plan.trig_tokens),
            PartialRope64Job(tag + 7, plan.k_norm, plan.trig, plan.k_rope, t, 2,
                             plan.position_base, plan.trig_tokens))
        for job in self.jobs:
            job.validate()
        self._original_spans = ((plan.q_norm_weight, 512), (plan.k_norm_weight, 512),
                                (plan.trig, plan.trig_tokens * 128))
        self._output_spans = tuple(span for job in self.jobs[4:] for span in job.output_spans)
        spans = (*prefix._input_spans, *prefix._output_spans, *self._original_spans, *self._output_spans)
        require(all(type(base) is int and base >= 0 and base % 64 == extent % 64 == 0 and
                    extent > 0 and base + extent <= 1 << 56 for base, extent in spans),
                'complete aligned physical span overflows 56-bit range')
        require(all(base + extent <= other or other + size <= base
                    for i, (base, extent) in enumerate(spans) for other, size in spans[:i]),
                'complete live input/parameter/output span alias')
        workspace = prefix.dense.workspace
        require(all(workspace.base + workspace.extent <= base or base + extent <= workspace.base
                    for base, extent in spans), 'workspace overlaps live Norm/RoPE allocation')
        prefix._check_resources()
        for base, extent in self._original_spans:
            require(self.memory.exact(base, extent, readable=True).readonly,
                    'only original prelaunch readonly norm weights and trig admitted')
        self._fresh_outputs()
        self._source_hashes = {**prefix.source_hashes, **{base: sha(self.memory.regions[base].raw())
                                                     for base, _ in self._original_spans}}
        self._producer_hashes = {}
        self.started = self.aborted = self.locked = False
        self.response = self._terminal_report = None
        self._active = self._active_binding = None
        self._index, self.ticks, self._prefix_count = 4, 0, 0
        self.commands, self.receipts = [], {}
        self._commands, self._receipts, self._prefix_result = [], {}, None
        self._prefix_result_fields = None
        self._scalar_baseline = self.scalar.calls.copy()
        self.identity = source_identity(policy=plan.norm_policy)
        self._identity = deepcopy(self.identity)
        self._binding = self._resource_identity()
        self._require_drained()

    @property
    def active(self):
        return self.prefix.active if self._prefix_result is None else self._active

    @property
    def role(self):
        return (self.prefix.role if self._prefix_result is None or self._prefix_result.status is not None
                else ORDER[min(self._index, 7)])

    def _resource_identity(self):
        return (id(self.prefix), id(self.norm), id(self.rope), id(self.memory), id(self.scalar),
                id(self.norm.scalar), id(self.rope.scalar), id(self.matrix), id(self.vector), id(self.dense),
                id(getattr(self.norm, 'observer', None)), id(getattr(self.rope, 'observer', None)),
                id(self.plan), _fields(self.plan),
                id(self.plan.projection), id(self.jobs),
                tuple((id(job), _fields(job)) for job in self.jobs),
                self.prefix._resource_identity())

    def _check_resources(self):
        require(self._resource_identity() == self._binding and self.identity == self._identity,
                'resource, scalar, plan or complete job binding changed')
        self.prefix._check_resources()
        require(self.prefix.response is self._prefix_result and
                _fields(self._prefix_result) == self._prefix_result_fields and
                len(self.prefix.commands) == self._prefix_count and
                self.prefix.commands == self._commands[:self._prefix_count] and
                set(self.prefix.receipts) == set(PREFIX_ORDER[:self._prefix_count]),
                'original prefix terminal/command provenance changed')
        require(self.commands == self._commands and set(self.receipts) == set(self._receipts),
                'accepted command or receipt history changed')
        for role, (receipt, fields) in self._receipts.items():
            require(self.receipts[role] is receipt and _fields(receipt) == fields,
                    'accepted previous receipt identity changed')
            if role in PREFIX_ORDER:
                require(self.prefix.receipts.get(role) is receipt,
                        'original prefix receipt provenance changed')
        for base, region, storage, extent, readonly in self.prefix.allocations:
            require(type(region.base) is int and type(region.extent) is int and
                    type(region.readonly) is bool and len(region.storage) == extent + 128,
                    'physical allocation geometry changed')
            region.check()
        if self._active is not None:
            require(self._active_binding == self._driver_binding(), 'active Norm/RoPE binding changed')

    def _driver_binding(self):
        d = self._active
        return (id(d), id(d.owner), id(d.memory), id(d.job), id(d.owner.job),
                id(d.owner.scalar), id(d.inputs), id(d.outputs),
                tuple(id(r) for r in (*d.inputs, *d.outputs)))

    def _fresh_outputs(self):
        for base, extent in self._output_spans:
            require(self.memory.exact(base, extent, readable=False).raw() == GUARD * (extent // 64),
                    'extra destination lost prelaunch sentinels')

    def _check_bytes(self):
        self.prefix._check_bytes()
        for base, digest in {**self._source_hashes, **self._producer_hashes}.items():
            require(sha(self.memory.regions[base].raw()) == digest,
                    'original source or accepted producer bytes changed')
        for role in self._receipts:
            if self._commands[ORDER.index(role)]['terminal_status'] is not None:
                continue
            index = ORDER.index(role)
            spans = (((getattr(self.plan.projection, role), self.jobs[index].write_bytes),)
                     if index < 4 else self.jobs[index].output_spans)
            for base, extent in spans:
                r = self.memory.exact(base, extent, readable=True)
                require(not r.readonly and r.written == r.acknowledged == set(range(0, extent, 64)),
                        'accepted producer publication/data/ACK coverage changed')

    def _require_drained(self, *, success=True):
        self.prefix._require_drained(success=success)
        require(self.norm.request is None and self.rope.request is None and self.memory.pending is None and
                self.scalar.client is None, 'Norm/RoPE terminal before physical obligations drained')
        if success:
            require(self.norm.ports()['job_ready'] and self.rope.ports()['job_ready'],
                    'unpoisoned idle Norm/RoPE owners required')

    def start(self):
        self._check_resources()
        require(not self.started, 'fixed complete chain invocation cannot be relaunched')
        self._require_drained()
        self._check_bytes()
        self._fresh_outputs()
        self.started = True
        self.prefix.start()

    def _record(self, role, receipt, command, spans):
        self.receipts[role] = receipt
        self._receipts[role] = (receipt, _fields(receipt))
        self.commands.append(deepcopy(command))
        self._commands.append(deepcopy(command))
        if command['terminal_status'] is None:
            for base, extent in spans:
                region = self.memory.exact(base, extent, readable=True)
                require(not region.readonly and region.written == region.acknowledged == set(range(0, extent, 64)),
                        'stage advance before actual data/ACK/publication')
                self._producer_hashes[base] = sha(region.raw())

    def _launch(self):
        self._check_resources()
        self._check_bytes()
        self._require_drained()
        require(not self.aborted and self._prefix_result is not None and self._prefix_result.status is None and
                self._prefix_count == 4 and len(self.commands) == self._index < 8,
                'actual prefix/previous accepted terminal required before next stage')
        prior = self._receipts.get(ORDER[self._index - 1])
        require(prior is not None and self._commands[-1]['terminal_status'] is None and
                self._commands[-1]['terminal_accepted'], 'genuine accepted previous success required')
        job = self.jobs[self._index]
        owner = self.norm if self._index < 6 else self.rope
        self._active = TypedNormRopeDriver(owner, self.memory, job)
        self._active_binding = self._driver_binding()

    def _finish(self, failure=None):
        self._require_drained(success=failure is None)
        self._check_bytes()
        self.locked = failure is not None
        p = self.plan
        self.response = L3NormRopeResult(p.projection.tag_base, failure, p.tokens,
            None if failure else p.q_rope, None if failure else p.k_rope,
            None if failure else p.projection.v, None if failure else p.gate,
            sum(c['acknowledged_write_bytes'] for c in self.commands),
            (self._prefix_result.failed_role if self._prefix_result is not None and
             self._prefix_result.status is not None else self.role) if failure else None)
        self._terminal_report = self._report()

    def tick(self, *, read_ready=True, read_response_ready=True, step_ready=True,
             result_ready=True, done_ready=True, write_ready=True, data_ready=True,
             ack_ready=True, response_ready=True, memory_ready=True,
             memory_response_ready=True, abort=False, reset=False,
             read_error=False, ack_error=False):
        require(self.started and self.response is None, 'no active complete chain invocation')
        controls = locals().copy()
        controls.pop('self')
        require(all(type(v) is bool for v in controls.values()), 'boolean transport controls required')
        self._check_resources()
        self.ticks += 1
        self.aborted |= abort or reset
        if self._prefix_result is None:
            event = self.prefix.tick(**controls)
            if len(self.prefix.commands) > self._prefix_count:
                require(len(self.prefix.commands) == self._prefix_count + 1, 'multiple prefix terminals in one tick')
                index = self._prefix_count
                role = ORDER[index]
                command = self.prefix.commands[-1]
                require(command['role'] == role and command['terminal_accepted'] and
                        command['job'] == asdict(self.jobs[index]), 'original accepted prefix command identity')
                self._record(role, self.prefix.receipts[role], command,
                             ((getattr(self.plan.projection, role), self.jobs[index].write_bytes),))
                self._prefix_count += 1
            if self.prefix.response is not None:
                self._prefix_result = self.prefix.response
                self._prefix_result_fields = _fields(self._prefix_result)
                if self._prefix_result.status is not None:
                    self._finish(self._prefix_result.status)
                else:
                    require(self._prefix_count == 4, 'prefix success without four genuine accepted terminals')
                    self._check_bytes()
            event['chain_terminal_fire'] = self.response is not None
            return event
        if self._active is None:
            if self.aborted:
                if response_ready:
                    self._finish('Aborted')
                return dict(chain_terminal_fire=self.response is not None)
            self._launch()
        driver = self._active
        request = driver.owner.request
        writing = request is not None and request.write
        event = driver.tick(memory_ready=memory_ready and (write_ready and data_ready if writing else read_ready),
            memory_response_ready=memory_response_ready and (ack_ready if writing else read_response_ready),
            response_ready=response_ready, abort=self.aborted, read_error=read_error, ack_error=ack_error)
        if driver.response is not None:
            result, report = driver.response, driver.report()
            counts = report['counts']
            require(result.tag == driver.job.tag and
                    (result.status is not None or result.write_bytes == driver.job.write_bytes),
                    'accepted Norm/RoPE terminal tag/full byte identity')
            command = dict(role=ORDER[self._index], job=asdict(driver.job), terminal_status=result.status,
                terminal_accepted=True, software_ticks=counts.get('ticks', 0),
                read_bytes=counts.get('read_bytes', 0), write_data_bytes=counts.get('write_bytes', 0),
                acknowledged_write_bytes=counts.get('ack_bytes', 0), executed_fmas=0,
                vector_add_calls=0, vector_add_lanes=0,
                scalar_calls=dict(report['owner']['scalar_calls']), owner_report=report)
            self._record(ORDER[self._index], result, command, driver.job.output_spans)
            self._active = self._active_binding = None
            if result.status is not None or self.aborted:
                self._finish(result.status or 'Aborted')
            else:
                self._index += 1
                if self._index == len(ORDER):
                    self._finish()
        event['chain_terminal_fire'] = self.response is not None
        return event

    def _report(self):
        scalar_calls = dict(self.scalar.calls - self._scalar_baseline)
        success = self.response is not None and self.response.status is None
        return dict(scope=SCOPE, plan=asdict(self.plan), complete=self.response is not None,
            response=None if self.response is None else asdict(self.response),
            full_chain_terminal_accepted=self.response is not None, full_chain_success=success,
            complete_l3_norm_rope_valid=success, reset_required=self.locked,
            commands=deepcopy(self.commands), actual_owner_commands=len(self.commands),
            software_ticks=self.ticks, scalar_calls=scalar_calls, scalar_request_count=sum(scalar_calls.values()),
            acknowledged_write_bytes=sum(c['acknowledged_write_bytes'] for c in self.commands),
            executed_fmas=sum(c['executed_fmas'] for c in self.commands),
            vector_add_calls=sum(c['vector_add_calls'] for c in self.commands),
            vector_add_lanes=sum(c['vector_add_lanes'] for c in self.commands),
            same_memory_owner_matrix_vector_scalar=True,
            original_inputs_sha256={**self.prefix.source_hashes, **self._source_hashes},
            actual_producer_sha256=dict(self._producer_hashes), identity=deepcopy(self.identity),
            source_initialization='original_hidden_weights_and_trig_only_before_launch',
            public_command128_executed=False, chisel_executed=False, rtl_executed=False,
            hardware_cycles=None, hardware_mac_utilization=None, native_acceptance=False,
            full_block_executed=False, actual_kv_cache_executed=False,
            not_executed=['attention', 'attention_output', 'residual', 'ffn', 'actual_kv_cache'])

    def report(self):
        return deepcopy(self._terminal_report) if self._terminal_report is not None else self._report()
