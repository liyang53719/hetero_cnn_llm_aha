"""Nineteen actual L3 owners on one preallocated, shared physical byte map.

This is a typed SOFTWARE coordinator. It creates no arithmetic service, bank,
reference tensor or substitute producer. KV staging becomes internally readable
at its real terminal; only the final real Add can advance the external fence.
Allocate every phase, cache reservation and workspace before constructing the
original projection prefix. A fresh phase may rebind the same Dense workspace
only after the entire preceding phase has retired.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields

from .norm_rope.coordinator import L3NormRopeCoordinator, L3NormRopePlan, ORDER as PREFIX_ORDER
from .norm_rope.owner import TORCH_DEFAULT256_POLICY
from .projection_driver import sha
from .kv_cache.owner import CAPACITY, TOKEN_BYTES, KvCacheJob, KvCacheOwner, disjoint, same_coverage
from .kv_cache.driver import TypedKvCacheDriver
from .kv_cache.fence import KvBlockFence
from .gqa.owner import Bf16CausalGqaJob, Bf16CausalGqaOwner, QkOrder
from .gqa.driver import TypedBf16CausalGqaDriver
from ..qwen35_gdn_prefill import typed_dense as d, rms_owner as rms
from ..qwen35_gdn_prefill.dense_prefix import TypedSeededDenseDriver
from ..qwen35_gdn_prefill.elementwise.model import ElementwiseJob, ElementwiseOp, ElementwiseOwner, TypedElementwiseDriver, LEGACY_PROFILE


ORDER = (*PREFIX_ORDER, 'kv_append', 'gqa', 'sigmoid_mul', 'o', 'attention_residual',
         'post_norm', 'gate', 'up', 'silu_mul', 'down', 'output')
SCOPE = 'QWEN35_L3_FULL_BLOCK_TYPED_SOFTWARE_COORDINATOR'
WORKSPACE_BYTES = 1024 // 32 * 16384
DENSE_SHAPES = {'o': (2048, 1024), 'gate': (1024, 3584),
                'up': (1024, 3584), 'down': (3584, 1024)}


def require(ok, why):
    if not ok:
        raise ValueError('typed L3 full block: ' + why)


def _fields(value):
    if value is None or type(value) is tuple:
        return value
    return tuple((f.name, type(getattr(value, f.name)), getattr(value, f.name)) for f in fields(value))


def _status(result):
    return result[1] if type(result) is tuple else result.status


@dataclass(frozen=True)
class L3FullBlockPlan:
    norm_rope: L3NormRopePlan
    o_weight: int
    post_norm_weight: int
    gate_weight: int
    up_weight: int
    down_weight: int
    staging_k: int
    context: int
    gated_context: int
    o: int
    attention_residual: int
    post_norm: int
    gate: int
    up: int
    silu_mul: int
    down: int
    output: int
    expected_generation: int
    capacity: int = CAPACITY

    @property
    def tokens(self):
        return self.norm_rope.tokens

    @property
    def staging_v(self):
        return self.staging_k + self.capacity * TOKEN_BYTES

    def validate(self):
        require(type(self.norm_rope) is L3NormRopePlan, 'original immutable Norm/RoPE plan required')
        self.norm_rope.validate()
        require(self.norm_rope.norm_policy == TORCH_DEFAULT256_POLICY,
                'explicit C2 Torch default256 normalization required')
        require(self.norm_rope.projection.tag_base <= (1 << 32) - len(ORDER),
                'nineteen distinct UInt32 owner tags required')
        require(type(self.expected_generation) is int and 0 <= self.expected_generation < (1 << 64) - 1,
                'exact expected fence generation required')
        require(type(self.capacity) is int and self.capacity == CAPACITY, 'source KV capacity256 required')
        for f in fields(self):
            if f.name in ('norm_rope', 'expected_generation', 'capacity'):
                continue
            value = getattr(self, f.name)
            require(type(value) is int and 0 <= value < 1 << 56 and value % 64 == 0,
                    f.name + ' must be an aligned 56-bit physical address')


@dataclass(frozen=True)
class L3FullBlockResult:
    tag: int
    status: str | None
    tokens: int
    generation: int
    output: int | None
    k_root: int
    v_root: int
    valid_tokens: int
    acknowledged_write_bytes: int
    failed_role: str | None = None


class L3FullBlockCoordinator:
    """Compose the unchanged eight-stage prefix and eleven actual tail jobs.

    Initialization launches no owner and performs no DMA. Every tail input is
    an accepted, ACKed producer allocation, except original hidden in the first
    residual Add and prelaunch readonly weights. Reset means abort and drain;
    recovering poisoned owners is an explicit caller operation after retirement.
    """
    def __init__(self, *, prefix, kv_owner, gqa_owner, elementwise_owner, fence, plan):
        require(type(prefix) is L3NormRopeCoordinator and type(plan) is L3FullBlockPlan,
                'genuine unstarted Norm/RoPE coordinator and immutable full plan required')
        plan.validate()
        require(prefix.plan is plan.norm_rope and not prefix.started and prefix.active is None and
                prefix.response is None and not prefix.commands and not prefix.receipts,
                'same unstarted eight-stage prefix invocation required')
        require(type(kv_owner) is KvCacheOwner and type(gqa_owner) is Bf16CausalGqaOwner and
                type(elementwise_owner) is ElementwiseOwner and type(fence) is KvBlockFence,
                'actual caller-owned KV, GQA, elementwise and fence resources required')
        require(fence.memory is prefix.memory and gqa_owner.matrix is prefix.matrix and
                gqa_owner.scalar is elementwise_owner.scalar is prefix.scalar,
                'same caller Matrix, scalar and physical memory required')
        require(elementwise_owner.enable_attention_sigmoid_mul is True and
                elementwise_owner._parameters() == (1024, 3584, False, 2048, True, LEGACY_PROFILE),
                'production elementwise geometry with explicit attention SigmoidMul opt-in required')
        require(plan.expected_generation == fence.state.generation,
                'plan does not match current committed fence generation')
        self.prefix, self.kv, self.gqa, self.elementwise = prefix, kv_owner, gqa_owner, elementwise_owner
        self.fence, self.plan = fence, plan
        self.memory, self.scalar, self.matrix = prefix.memory, prefix.scalar, prefix.matrix
        self.vector, self.dense, self.rms = prefix.vector, prefix.dense, prefix.prefix.rms
        self._before = fence.state
        self._before_fields = _fields(self._before)
        p, n, t = plan.norm_rope.projection, plan.norm_rope, plan.tokens
        tag, state = p.tag_base, self._before
        kv = KvCacheJob(tag + 8, state.k_root, state.v_root, state.valid_tokens,
            n.k_rope, p.v, plan.staging_k, t, plan.expected_generation, state.generation, plan.capacity)
        tail = [kv,
            Bf16CausalGqaJob(tag + 9, n.q_rope, plan.staging_k, plan.context, t,
                state.valid_tokens, kv.valid_tokens, plan.capacity, qk_policy=QkOrder.PairHighFirst),
            ElementwiseJob(tag + 10, n.gate, plan.context, plan.gated_context, t,
                           ElementwiseOp.SigmoidMul, 2048)]
        for index, role in enumerate(ORDER[11:], 11):
            if role in DENSE_SHAPES:
                k, width = DENSE_SHAPES[role]
                source = {'o': plan.gated_context, 'gate': plan.post_norm,
                          'up': plan.post_norm, 'down': plan.silu_mul}[role]
                tail.append(d.down.Job(m=t, k=k, n=width, tag=tag + index, a=source,
                    b=getattr(plan, role + '_weight'), dst=getattr(plan, role),
                    activation_bf16=True, weight_bf16=True, output_bf16=True, write_bytes=t * width * 2))
            elif role == 'post_norm':
                tail.append(rms.RmsJob(tag + index, plan.attention_residual, plan.post_norm_weight,
                                      plan.post_norm, t, prefix.prefix.rms_policy))
            else:
                a, b, op, width = {
                    'attention_residual': (p.hidden, plan.o, ElementwiseOp.Add, 1024),
                    'silu_mul': (plan.gate, plan.up, ElementwiseOp.SiluMul, 3584),
                    'output': (plan.attention_residual, plan.down, ElementwiseOp.Add, 1024)}[role]
                tail.append(ElementwiseJob(tag + index, a, b, getattr(plan, role), t, op, width))
        self.jobs = (*prefix.jobs, *tail)
        for job in tail:
            if type(job) is ElementwiseJob:
                elementwise_owner._validate_job(job)
            else:
                job.validate()
            if type(job) is d.down.Job:
                self.dense.workspace.validate(job)
        fence.validate_job(kv)
        workspace = self.dense.workspace
        require(workspace.extent == WORKSPACE_BYTES and workspace.split_k == 2560,
                'fixed complete 524288-byte Down workspace with split2560 required')
        self._original_spans = ((plan.post_norm_weight, 2048),
            *((getattr(plan, role + '_weight'), k * width * 2)
              for role, (k, width) in DENSE_SHAPES.items()))
        self._output_spans = (*kv.output_spans,
            (plan.context, t * 4096), (plan.gated_context, t * 4096),
            (plan.o, t * 2048), (plan.attention_residual, t * 2048), (plan.post_norm, t * 2048),
            (plan.gate, t * 7168), (plan.up, t * 7168), (plan.silu_mul, t * 7168),
            (plan.down, t * 2048), (plan.output, t * 2048))
        spans = (*prefix.prefix._input_spans, *prefix.prefix._output_spans,
                 *prefix._original_spans, *prefix._output_spans,
                 *self._original_spans, *self._output_spans, (workspace.base, workspace.extent))
        require(all(type(base) is int and base >= 0 and base % 64 == extent % 64 == 0 and
                    extent > 0 and base + extent <= 1 << 56 for base, extent in spans),
                'complete aligned physical span overflows 56-bit range')
        require(all(disjoint(span, prior) for i, span in enumerate(spans) for prior in spans[:i]),
                'complete live input/parameter/output/workspace span alias')
        # Check the entire map, including preallocated later phases, against
        # unused cache capacity. TypedMemory itself sees only the valid planes.
        reservations = [(plan.staging_k, 2 * plan.capacity * TOKEN_BYTES, kv.output_spans)]
        if state.valid_tokens:
            reservations.append((state.k_root, 2 * state.capacity * TOKEN_BYTES,
                                 ((state.k_root, state.valid_tokens * TOKEN_BYTES),
                                  (state.v_root, state.valid_tokens * TOKEN_BYTES))))
        for base, extent, allowed in reservations:
            require(all((region.base, region.extent) in allowed or
                        disjoint((base, extent), (region.base, region.extent))
                        for region in self.memory.regions.values()),
                    'allocation occupies reserved KV capacity, including unused holes')
        for base, extent in self._original_spans:
            require(self.memory.exact(base, extent, readable=True).readonly,
                    'tail parameters require original prelaunch readonly storage')
        self._fresh_outputs()
        workspace_region = self.memory.exact(workspace.base, workspace.extent, readable=False)
        require(workspace_region.raw() == d.GUARD * (workspace.extent // 64),
                'fresh phase workspace lost initial sentinels')
        prefix._check_resources()
        self._source_hashes = {base: sha(self.memory.regions[base].raw()) for base, _ in self._original_spans}
        self._producer_hashes = {}
        self.started = self.aborted = self.locked = False
        self.response = self._terminal_report = None
        self._active = self._active_binding = None
        self._index, self.ticks, self._prefix_count = 8, 0, 0
        self.commands, self.receipts = [], {}
        self._commands, self._receipts = [], {}
        self._prefix_result = self._prefix_result_fields = self._kv_receipt = None
        self._scalar_baseline = self.scalar.calls.copy()
        self._binding = self._resource_identity()
        self._require_drained()

    @property
    def active(self):
        return self.prefix.active if self._prefix_result is None else self._active

    @property
    def role(self):
        return self.prefix.role if self._prefix_result is None else ORDER[min(self._index, 18)]

    def _resource_identity(self):
        return (id(self.prefix), self.prefix._resource_identity(), id(self.kv), id(self.gqa),
                id(self.elementwise), id(self.fence), id(self.fence.memory), id(self.memory),
                id(self.matrix), id(self.scalar), id(self.vector), id(self.dense), id(self.rms), id(self.rms.observer),
                id(self.gqa.matrix), id(self.gqa.scalar), id(self.gqa.observer),
                id(self.elementwise.scalar), self.elementwise._parameters(),
                id(self.elementwise.sigmoid_observer), id(self.elementwise.silu_observer), id(self.plan), _fields(self.plan),
                id(self.jobs), tuple((id(job), _fields(job)) for job in self.jobs))

    def _driver_binding(self):
        driver = self._active
        return (id(driver), id(driver.owner), id(driver.memory), id(driver.job),
                id(driver.owner.job), id(getattr(driver, 'output', None)),
                id(getattr(driver, 'inputs', None)), id(getattr(driver, 'outputs', None)))

    def _check_resources(self):
        require(self._resource_identity() == self._binding, 'resource, immutable plan/job or owner binding changed')
        self.prefix._check_resources()
        require(self.fence.state is self._before and _fields(self._before) == self._before_fields,
                'committed roots/generation changed during block')
        require(self.prefix.response is self._prefix_result and
                _fields(self._prefix_result) == self._prefix_result_fields and
                len(self.prefix.commands) == self._prefix_count and
                self.prefix.commands == self._commands[:self._prefix_count],
                'original prefix terminal/command provenance changed')
        require(self.commands == self._commands and set(self.receipts) == set(self._receipts),
                'accepted command or receipt history changed')
        for role, (receipt, values) in self._receipts.items():
            require(self.receipts[role] is receipt and _fields(receipt) == values,
                    'accepted receipt identity changed')
            if role in PREFIX_ORDER:
                require(self.prefix.receipts.get(role) is receipt, 'original prefix receipt provenance changed')
        if self._active is not None:
            require(self._driver_binding() == self._active_binding, 'active driver binding changed')
        require(self.fence.pending_receipt is self._kv_receipt,
                'pending KV receipt identity changed')

    def _fresh_outputs(self):
        for base, extent in self._output_spans:
            require(self.memory.exact(base, extent, readable=False).raw() == d.GUARD * (extent // 64),
                    'tail destination lost prelaunch sentinels')

    def _check_bytes(self):
        self.prefix._check_bytes()
        for base, digest in {**self._source_hashes, **self._producer_hashes}.items():
            require(sha(self.memory.regions[base].raw()) == digest,
                    'original tail parameter or accepted producer bytes changed')
        for base in self._producer_hashes:
            region = self.memory.regions[base]
            require(region.published is True and not region.readonly and
                    same_coverage(region.written, frozenset(range(0, region.extent, 64))) and
                    same_coverage(region.acknowledged, frozenset(range(0, region.extent, 64))),
                    'accepted producer publication/data/ACK coverage changed')

    def _require_drained(self, *, success=True, final_held=False):
        self.prefix._require_drained(success=success)
        require(self.kv.request is None and self.gqa.request is None and self.elementwise.request is None,
                'tail terminal before transport drained')
        if success:
            require(self.kv.ports()['job_ready'] and self.gqa.ports()['job_ready'] and
                    (final_held or self.elementwise.ports()['job_ready']), 'unpoisoned idle tail owners required')

    def start(self):
        self._check_resources()
        require(not self.started, 'fixed complete fullblock invocation cannot be relaunched')
        self._require_drained()
        self._check_bytes()
        self._fresh_outputs()
        self.started = True
        self.prefix.start()

    def _record(self, role, result, command, spans):
        self.receipts[role] = result
        self._receipts[role] = (result, _fields(result))
        self.commands.append(deepcopy(command))
        self._commands.append(deepcopy(command))
        if command['terminal_status'] is None:
            for base, extent in spans:
                region = self.memory.exact(base, extent, readable=True)
                require(not region.readonly and
                        same_coverage(region.written, frozenset(range(0, extent, 64))) and
                        same_coverage(region.acknowledged, frozenset(range(0, extent, 64))),
                        'stage advance before actual data/ACK/publication')
                self._producer_hashes[base] = sha(region.raw())

    def _launch(self):
        self._check_resources()
        self._check_bytes()
        self._require_drained()
        require(not self.aborted and self._prefix_result is not None and self._prefix_result.status is None and
                len(self.commands) == self._index < len(ORDER) and self._prefix_count == 8 and
                self._commands[-1]['terminal_status'] is None and self._commands[-1]['terminal_accepted'],
                'actual accepted previous success required before next stage')
        job, role = self.jobs[self._index], self.role
        if role == 'kv_append':
            self._active = TypedKvCacheDriver(self.kv, self.memory, job, self.fence)
        elif role == 'gqa':
            require(self._kv_receipt is not None, 'GQA requires actual pending KV staging receipt')
            self._active = TypedBf16CausalGqaDriver(self.gqa, self.memory, job)
        elif role in DENSE_SHAPES:
            source = self.memory.exact(job.a, job.m * job.k * 2, readable=True)
            require(not source.readonly, 'Dense tail source must be an actual accepted producer')
            driver = TypedSeededDenseDriver if role == 'down' else d.TypedDenseDriver
            self._active = driver(self.dense, self.matrix, self.memory, job)
        elif role == 'post_norm':
            require(not self.memory.exact(job.input, job.write_bytes, readable=True).readonly,
                    'postnorm source must be actual residual producer')
            self._active = rms.TypedRmsDriver(self.rms, self.memory, job)
        else:
            self._active = TypedElementwiseDriver(self.elementwise, self.memory, job)
        self._active_binding = self._driver_binding()

    def _finish(self, failure=None, *, prevalidated=False):
        if not prevalidated:
            self._require_drained(success=failure is None)
            self._check_bytes()
        if failure is not None and self._kv_receipt is not None:
            self.fence.discard_pending(self._kv_receipt)
        self.locked = failure is not None
        state = self.fence.state
        self.response = L3FullBlockResult(self.plan.norm_rope.projection.tag_base, failure,
            self.plan.tokens, state.generation, None if failure else self.plan.output,
            state.k_root, state.v_root, state.valid_tokens,
            sum(c['acknowledged_write_bytes'] for c in self.commands),
            (self._prefix_result.failed_role if self._prefix_result is not None and
             self._prefix_result.status is not None else self.role) if failure else None)
        self._terminal_report = self._report()

    def tick(self, *, read_ready=True, read_response_ready=True, step_ready=True,
             result_ready=True, done_ready=True, write_ready=True, data_ready=True,
             ack_ready=True, response_ready=True, memory_ready=True,
             memory_response_ready=True, abort=False, reset=False, read_error=False,
             ack_error=False, matrix_group_ready=True, scalar_ready=True,
             seed_begin_ready=True, seed_beat_ready=True, seed_ack_ready=True, seed_ack_error=False):
        require(self.started and self.response is None, 'no active fullblock invocation')
        controls = locals().copy()
        controls.pop('self')
        require(all(type(v) is bool for v in controls.values()), 'boolean transport controls required')
        self._check_resources()
        self.ticks += 1
        self.aborted |= abort or reset
        if self._prefix_result is None:
            forwarded = {k: v for k, v in controls.items() if k not in (
                'matrix_group_ready', 'scalar_ready', 'seed_begin_ready', 'seed_beat_ready',
                'seed_ack_ready', 'seed_ack_error')}
            event = self.prefix.tick(**forwarded)
            if len(self.prefix.commands) > self._prefix_count:
                require(len(self.prefix.commands) == self._prefix_count + 1,
                        'multiple prefix terminals in one tick')
                index = self._prefix_count
                command, role = self.prefix.commands[-1], ORDER[index]
                require(command['role'] == role and command['terminal_accepted'] and
                        command['job'] == asdict(self.jobs[index]), 'original accepted prefix command identity')
                self._record(role, self.prefix.receipts[role], command, ())
                self._prefix_count += 1
            if self.prefix.response is not None:
                self._prefix_result = self.prefix.response
                self._prefix_result_fields = _fields(self._prefix_result)
                if self._prefix_result.status is not None:
                    self._finish(self._prefix_result.status)
                else:
                    require(self._prefix_count == 8, 'prefix success requires eight genuine accepted terminals')
            event['fullblock_terminal_fire'] = self.response is not None
            return event
        if self._active is None:
            if self.aborted:
                if response_ready:
                    self._finish('Aborted')
                return dict(fullblock_terminal_fire=self.response is not None)
            self._launch()
        driver, role = self._active, self.role
        final_accept = False
        if role == 'output' and response_ready and not self.aborted and self.elementwise.ports()['response'] is not None:
            held = driver.preflight_response()
            if held.status is None:
                # Full-chain checks, including all earlier bytes and roots,
                # precede the final real response edge and external commit.
                self._check_resources()
                self._check_bytes()
                self._require_drained(final_held=True)
                prepared = self.fence.prepare_final_owner(self._kv_receipt, driver, expected_job=self.jobs[-1])
                event = self.fence.accept_final_owner(prepared)
                final_accept = True
        if not final_accept:
            if role in DENSE_SHAPES:
                require(not read_error, 'Dense read-error injection is unsupported by shared transport')
                kwargs = dict(read_ready=read_ready and memory_ready,
                    read_response_ready=read_response_ready and memory_response_ready,
                    step_ready=step_ready, result_ready=result_ready, done_ready=done_ready,
                    write_ready=write_ready and memory_ready, data_ready=data_ready and memory_ready,
                    ack_ready=ack_ready and memory_response_ready, response_ready=response_ready,
                    abort=self.aborted, ack_error=ack_error)
                if role == 'down':
                    kwargs.update(seed_begin_ready=seed_begin_ready, seed_beat_ready=seed_beat_ready,
                                  seed_ack_ready=seed_ack_ready, seed_ack_error=seed_ack_error)
            else:
                request = driver.owner.request
                writing = request is not None and request.write
                kwargs = dict(memory_ready=memory_ready and (write_ready and data_ready if writing else read_ready),
                    memory_response_ready=memory_response_ready and (ack_ready if writing else read_response_ready),
                    response_ready=response_ready, abort=self.aborted, read_error=read_error, ack_error=ack_error)
                if role == 'gqa':
                    kwargs.update(matrix_group_ready=matrix_group_ready, matrix_step_ready=step_ready,
                        matrix_result_ready=result_ready, matrix_done_ready=done_ready, scalar_ready=scalar_ready)
            event = driver.tick(**kwargs)
        if driver.response is not None:
            result, report = driver.response, driver.report()
            failure = _status(result)
            counts = report['counts']
            command = dict(role=role, tag=driver.job.tag, job=asdict(driver.job), terminal_status=failure,
                terminal_accepted=True, software_ticks=counts.get('ticks', 0),
                read_bytes=counts.get('read_bytes', 64 * (counts.get('a_read_beats', 0) + counts.get('b_read_beats', 0))),
                write_data_bytes=counts.get('write_bytes', counts.get('write_data_bytes', 0)),
                acknowledged_write_bytes=(report['owner']['acknowledged_write_bytes'] if role == 'post_norm'
                                           else counts.get('ack_bytes', 0)),
                executed_fmas=report.get('executed_fmas', 0), vector_add_calls=0, vector_add_lanes=0,
                owner_report=report)
            if role == 'kv_append':
                self._kv_receipt = driver.receipt
            spans = self.jobs[self._index].output_spans if role in ('kv_append', 'gqa') else (
                ((driver.job.dst if role in DENSE_SHAPES else driver.job.output), driver.job.write_bytes),)
            if final_accept:
                # Publication and root promotion have already happened together.
                # Record only diagnostics here; no post-accept proof requirement.
                self.receipts[role] = result
                self._receipts[role] = (result, _fields(result))
                self.commands.append(deepcopy(command))
                self._commands.append(deepcopy(command))
                self._producer_hashes[self.plan.output] = sha(driver.output.raw())
            else:
                self._record(role, result, command, spans)
            self._active = self._active_binding = None
            if failure is not None or self.aborted:
                self._finish(failure or 'Aborted')
            else:
                self._index += 1
                if self._index == len(ORDER):
                    self._finish(prevalidated=final_accept)
        event['fullblock_terminal_fire'] = self.response is not None
        return event

    def _report(self):
        success = self.response is not None and self.response.status is None
        scalar_calls = dict(self.scalar.calls - self._scalar_baseline)
        return dict(scope=SCOPE, plan=asdict(self.plan), complete=self.response is not None,
            response=None if self.response is None else asdict(self.response),
            full_chain_terminal_accepted=self.response is not None, full_chain_success=success,
            complete_l3_block_valid=success, reset_required=self.locked,
            commands=deepcopy(self.commands), actual_owner_commands=len(self.commands),
            software_ticks=self.ticks, scalar_calls=scalar_calls, scalar_request_count=sum(scalar_calls.values()),
            acknowledged_write_bytes=sum(c['acknowledged_write_bytes'] for c in self.commands),
            dense_projection_executed_fmas=sum(c['executed_fmas'] for c in self.commands),
            executed_fmas=None,
            executed_fmas_scope='full total unassigned here; GQA service counters must be included separately',
            vector_add_calls=sum(c['vector_add_calls'] for c in self.commands),
            vector_add_lanes=sum(c['vector_add_lanes'] for c in self.commands),
            same_memory_owner_matrix_vector_scalar=True,
            original_inputs_sha256={**self.prefix._source_hashes, **self._source_hashes},
            actual_producer_sha256={**self.prefix._producer_hashes, **self._producer_hashes},
            committed_before=asdict(self._before), committed_after=asdict(self.fence.state),
            cache_commit_proof='real_final_TypedElementwiseDriver_Add',
            norm_policy=self.plan.norm_rope.norm_policy, qk_policy=QkOrder.PairHighFirst.value,
            source_initialization='original_hidden_weights_and_trig_only_before_launch',
            public_command128_executed=False, chisel_executed=False, rtl_executed=False,
            hardware_cycles=None, hardware_mac_utilization=None, native_acceptance=False,
            full_block_executed=success, actual_kv_cache_executed='kv_append' in self.receipts,
            not_executed=[] if success else ['complete_l3_block'])

    def report(self):
        return deepcopy(self._terminal_report) if self._terminal_report is not None else self._report()
