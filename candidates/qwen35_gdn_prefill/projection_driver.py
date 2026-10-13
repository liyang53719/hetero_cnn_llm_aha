"""Actual typed partials -> shared Vector16 Add -> packed BF16 ACKs.

All arithmetic uses the caller's one MatrixService and one Vector16. The
resident partials and sum occupy the owner's existing three A-bank tile slots.
No reference output, detached reduction arithmetic, second bank or ALU exists.
"""
from collections import Counter, deque
import ctypes as C
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct

from . import typed_dense as t
from .projection_owner import (GdnProjectionOwner, GdnReductionCoordinator,
    GdnReductionRequest, GdnKWindowRequest, Job, down, drain)
from .chunk.vector import Vector16, VectorArithmeticFault
from ..qwen2_resident_matrix.ffn_attention.matrix_service import MatrixValue
from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile
from ..qwen2_resident_matrix.dense_block_reduce.public_coordinator import Services
from ..qwen2_resident_matrix.dense_block_reduce.sum_tiles import (
    TileSumController, SumResponse, shared_loan_edge, owner_tile_edge)

require = t.require
GDN_PROJECTION_PROFILE = ReductionProfile(
    'torch210cpu_gdn_k1024_two_k512_pair_reverse_fp32_sum_bf16',
    ((0, 512), (512, 1024)), True,
    '8b98184ea237efc0e2599fdaa223e0c04e3a9dee4b07dc091a0867389448bb7e')
ROLES = {'qkv': (1024, 6144), 'z': (1024, 2048), 'ab': (1024, 32)}
ATTENTION_FAMILY = 'attention_l3_v1'
ATTENTION_PROJECTION_PROFILE = ReductionProfile(
    'torch210cpu_default_l3_k1024_two_k512_pair_reverse_fp32_sum_bf16',
    ((0, 512), (512, 1024)), True,
    'e4f616563bfc94978a528ee012bad498841156dae8809054d0d9cc5c0422ef5d')
ATTENTION_ROLES = {'packed_q_gate': (1024, 4096), 'k': (1024, 512), 'v': (1024, 512)}

# Execution definitions and the unchanged files which select their dynamic
# authority are frozen separately. The latter are import scaffolding only:
# their checkpoint readers/reference/numeric drivers are never called here.
EXECUTION_SOURCE_FILES = tuple('candidates/' + name for name in (
    'qwen35_gdn_prefill/projection_owner.py', 'qwen35_gdn_prefill/projection_driver.py',
    'qwen35_attention_prefill/projection_profile.json',
    'qwen35_gdn_prefill/typed_dense.py',
    'qwen35_gdn_prefill/rms_owner.py', 'qwen35_gdn_prefill/chunk/vector.py',
    'qwen35_gdn_prefill/chunk/vector16.cpp',
    'qwen2_resident_matrix/ffn_attention/matrix_service.py',
    'qwen2_resident_matrix/transposed_down/model.py',
    'qwen2_resident_matrix/ffn_tiles/model.py', 'qwen2_resident_matrix/ffn_window/model.py',
    'qwen2_resident_matrix/ffn_drain/model.py',
    'qwen2_resident_matrix/dense_block_reduce/k_window_model.py',
    'qwen2_resident_matrix/dense_block_reduce/dense_drain.py',
    'qwen2_resident_matrix/dense_block_reduce/public_coordinator.py',
    'qwen2_resident_matrix/dense_block_reduce/profile.py',
    'qwen2_resident_matrix/dense_block_reduce/sum_tiles.py',
    # shared_loan_edge imports Request only. No VectorLoanModel/add_lane runs.
    'qwen2_resident_matrix/dense_block_reduce/vector_add_model.py'))
AUTHORITY_IMPORT_SOURCE_FILES = tuple('candidates/qwen2_resident_matrix/' + name for name in (
    'ffn_public/execute_numeric.py', 'ffn_public/model.py', 'ffn_public/prefix_arithmetic.py',
    'ffn_fullgroup/check_numeric.py', 'ffn_fullgroup/down_driver.py', 'ffn_group/model.py',
    'ffn_drain/check_numeric.py', 'ffn_tiles/check_numeric.py', 'ffn_window/check_numeric.py'))
SOURCE_FILES = EXECUTION_SOURCE_FILES + AUTHORITY_IMPORT_SOURCE_FILES
VALIDATION_SOURCE_FILES = ('candidates/qwen35_gdn_prefill/test_projection_driver.py',)


class SharedVector16Loan:
    """One held loan response around the provided existing Vector16 resource.

The host call completes synchronously; its actual result stays held until the
tile consumer accepts it. Abort discards only that already-completed response.
There is no NumPy arithmetic, lane allocation, or invented hardware latency.
"""
    def __init__(self, vector):
        require(type(vector) is Vector16 and vector.client is None, 'drained existing Vector16 required')
        self.vector = vector
        self.result = None
        self.poison = False
        self.fault = None
        self.calls = self.retirements = 0
        self.resource = (id(vector), vector.resource_address)

    def ports(self, *, abort=False):
        return dict(request_ready=self.result is None and self.vector.client is None and
                    not self.poison and not abort,
                    result=self.result if not self.poison and not abort else None,
                    drained=self.result is None and self.vector.client is not self,
                    reset_required=self.poison)

    def tick(self, *, request=None, result_ready=False, abort=False, coordinated_reset=False):
        require(self.resource == (id(self.vector), self.vector.resource_address), 'Vector16 resource replaced')
        p = self.ports(abort=abort)
        request_fire = request is not None and p['request_ready']
        result_fire = p['result'] is not None and result_ready
        if coordinated_reset:
            require(p['drained'], 'coordinated reset before actual Vector loan drain')
            self.poison = False
            return dict(p, request_fire=False, result_fire=False)
        if request_fire:
            require(request.binary_add is True and len(request.gate) == len(request.up) == 16,
                    'GDN loan requires exactly sixteen actual FP32 Add lanes')
            require(self.vector.acquire(self), 'existing Vector16 loan acquisition rejected')
            try:
                words = tuple(self.vector.op(self, 'add', request.gate, request.up))
                self.result = SumResponse(words)
            except VectorArithmeticFault as exc:
                self.fault = exc.diagnostic
                self.result = SumResponse((0,) * 16, True)
            self.calls += 1
        if result_fire or abort and self.result is not None:
            if result_fire:
                self.retirements += 1
                self.poison |= self.result.error
            self.result = None
            self.vector.release(self)
        self.poison |= bool(abort)
        return dict(p, request_fire=request_fire, result_fire=result_fire)


class TypedProjectionDriver:
    # Explicit implementation hooks retain the original exact types by default.
    # A derived internal owner must supply its own validated request, sum and
    # coordinator; these are not selectable public command fields.
    OWNER_TYPE = GdnProjectionOwner
    WINDOW_REQUEST_TYPE = GdnKWindowRequest

    def _validate_family(self, job, role, profile, family):
        require(type(family) is str and family in ('gdn', ATTENTION_FAMILY),
                'explicit supported projection family required')
        if family == 'gdn':
            require(role in ROLES or role == 'synthetic' and profile not in
                    (GDN_PROJECTION_PROFILE, ATTENTION_PROJECTION_PROFILE),
                    'explicit production GDN role or nonproduction synthetic profile required')
            if role in ROLES:
                require((job.k, job.n) == ROLES[role], 'production GDN projection full shape mismatch')
                require(profile == GDN_PROJECTION_PROFILE, 'production GDN projection policy/profile mismatch')
        else:
            require(role in ATTENTION_ROLES, 'explicit production L3 projection role required')
            require((job.k, job.n) == ATTENTION_ROLES[role], 'production L3 projection full shape mismatch')
            require(profile == ATTENTION_PROJECTION_PROFILE, 'production L3 projection policy/profile mismatch')
            parameters = Path(__file__).resolve().parents[1] / 'qwen35_attention_prefill/projection_profile.json'
            canonical = json.dumps(json.loads(parameters.read_text()), sort_keys=True,
                                   separators=(',', ':'), ensure_ascii=True).encode()
            require(hashlib.sha256(canonical).hexdigest() == profile.source_sha256,
                    'production L3 projection parameter identity drift')

    def _make_call(self, typed_job, profile):
        return GdnReductionRequest(typed_job, typed_job.tag or 1, profile.ranges, profile.pair_reverse)

    def _make_sum(self, owner):
        return TileSumController(owner.tiles, bank_tick=lambda **p: owner_tile_edge(owner, **p))

    def _make_coordinator(self):
        return GdnReductionCoordinator()

    def __init__(self, owner, matrix_service, memory, job, *, vector, role,
                 profile=GDN_PROJECTION_PROFILE, family='gdn'):
        require(type(owner) is self.OWNER_TYPE, 'exact selected projection owner required')
        require(type(matrix_service) is t.MatrixService and type(memory) is t.TypedMemory,
                'same base MatrixService and typed physical byte map required')
        require(type(job) in (t.down.Job, down.Job, Job), 'supported complete original Dense Job authority')
        require(type(profile) is ReductionProfile, 'explicit immutable reduction profile required')
        profile.validate(job.k)
        self._validate_family(job, role, profile, family)
        typed_job = Job(**vars(job))
        self.call = self._make_call(typed_job, profile)
        self.call.validate()
        require(type(owner.workspace) is down.PrefixWorkspace, 'explicit bounded workspace identity required')
        owner.workspace.validate(typed_job)
        require(owner.state == 'idle' and not owner.error and not owner.drain_poison and
                owner.tiles.idle and not owner.tiles.leased and not owner.tiles.poison and
                owner.lease is None, 'drained unpoisoned projection owner required')
        require(memory.pending is None and matrix_service.owner is None and not matrix_service.reset_required,
                'physical Matrix/DMA must be drained before projection admission')
        self.a = memory.exact(job.a, job.m * job.k * 2, readable=True)
        self.b = memory.exact(job.b, job.k * job.n * 2, readable=True)
        self.output = memory.exact(job.dst, job.write_bytes, readable=False)
        self.owner, self.matrix, self.memory, self.job = owner, matrix_service, memory, job
        self.family, self.role, self.profile = family, role, profile
        self.binding_identity = self._binding_identity()
        self.loan = SharedVector16Loan(vector)
        self.sum = self._make_sum(owner)
        self.coordinator = self._make_coordinator()
        self.pending_read = self.pending_ack = self.bridge = None
        self.results = deque()
        self.response = None
        self._terminal_report = None
        self.aborted = self.abort_sent = False
        self.numeric_fault = None
        self.counts = Counter()
        self.partials, self.drains, self.groups = [], [], []
        self.input_hashes = tuple(hashlib.sha256(r.raw()).hexdigest() for r in (self.a, self.b))
        self.bank_identity = self._identity()
        self.epoch = self.matrix.epoch
        self.fma_before = int(self.matrix.lib.matrix_dense_fmas())
        self.vector_calls_before = vector.calls['add']
        self.vector_lanes_before = vector.lane_ops['add']
        self.fences_before = (owner.a_fences, owner.k_a_fences)
        e = self.coordinator.tick(request=self.call, services=self.services())
        require(e['request_fire'] and not self.coordinator.poison, 'typed projection admission failed')

    def _identity(self):
        return (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks),
                id(self.owner.tiles), id(self.owner.tiles.banks), id(self.matrix),
                self.matrix.resource_address, id(self.loan.vector), self.loan.vector.resource_address,
                id(self.owner.workspace))

    def _binding_identity(self):
        return (self.family, self.role, self.profile, tuple(sorted(vars(self.job).items())))

    def services(self):
        o = self.owner
        return Services(window_busy=o.window_request is not None and o.state not in ('idle', 'locked'),
            drain_busy=o.drain_request is not None and o.state not in ('idle', 'locked'),
            tiles_drained=o.tiles.idle, tiles_leased=o.tiles.leased,
            vector_drained=self.loan.ports()['drained'], sum_busy=self.sum.busy,
            lease_valid=o.lease is not None, matrix_drained=self.matrix.owner is None,
            dma_drained=self.pending_read is None and self.pending_ack is None and self.memory.pending is None,
            window_reset=bool(o.error), drain_reset=bool(o.drain_poison), sum_reset=self.sum.poison,
            vector_reset=self.loan.poison, tiles_reset=o.tiles.poison,
            backend_reset=self.matrix.reset_required or self.numeric_fault is not None)

    def tick(self, *, read_ready=True, read_response_ready=True, step_ready=True,
             result_ready=True, done_ready=True, write_ready=True, data_ready=True,
             ack_ready=True, response_ready=True, abort=False, ack_error=False):
        require(self.response is None, 'projection invocation already retired')
        require(self.binding_identity == self._binding_identity(),
                'accepted projection family/role/profile/job binding changed')
        require(self.bank_identity == self._identity() and self.owner.tiles.banks is self.owner.a_banks and
                self.matrix.epoch == self.epoch, 'physical projection resources/epoch replaced')
        o, c = self.owner, self.coordinator
        reset_edge = bool(abort or self.numeric_fault) and not self.aborted
        self.aborted |= reset_edge
        svc, op = self.services(), o.ports()
        cp = c.ports(svc, abort=self.aborted)
        if cp['backend_abort'] and self.matrix.owner is o and not self.abort_sent:
            self.matrix.abort(o)
            self.abort_sent = True
            self.counts['matrix_aborts'] += 1
        args = dict(abort=cp['backend_abort'], invalidate_lease=cp['invalidate_lease'],
                    window_result_ready=cp['window_result_ready'], drain_result_ready=cp['drain_result_ready'])
        se, oe = {}, {}
        if c.state in ('sumIssue', 'sumWait') or self.sum.busy:
            se = shared_loan_edge(self.sum, self.loan, start=cp['sum_request'],
                abort=cp['backend_abort'], bank_ready=cp['sum_bank_granted'])
        else:
            if cp['window_request'] is not None and op['window_ready']:
                require(self.bridge is None and self.matrix.acquire(o, 'dense', self.job.tag),
                        'same serialized Matrix acquisition rejected')
                self.bridge = self.matrix.dense_library(o)
                self.abort_sent = False
                args['window'] = cp['window_request']
            if cp['drain_request'] is not None:
                args['drain'] = cp['drain_request']
            backend_fault = self.matrix.reset_required or self.numeric_fault is not None
            args.update(read_command_ready=read_ready and not backend_fault,
                group_ready=not backend_fault and not self.abort_sent,
                step_ready=step_ready and not backend_fault and not self.abort_sent and
                    not (op.get('step') is not None and op['step'].last and len(self.results) >= 2),
                write_command_ready=write_ready, write_data_ready=data_ready)
            if self.pending_read is not None and read_response_ready:
                args['read_beat'] = self.pending_read
            if self.results and result_ready:
                args['result'] = self.results[0]
            if (op['matrix_done_ready'] and done_ready and not self.results and self.bridge is not None and
                    self.matrix.lib.matrix_done_ready()):
                args['matrix_done'] = down.MatrixDone(self.job.tag, bool(o.error or self.matrix.reset_required))
            if self.pending_ack is not None and ack_ready:
                a = self.pending_ack
                args['write_ack'] = down.WriteAck(a.tag, bool(ack_error), a.nbytes)
            oe = o.tick(**args)
        ce = c.tick(services=svc, abort=self.aborted,
            window_ready=bool(oe.get('window_fire')), drain_ready=bool(oe.get('drain_fire')),
            sum_ready=bool(se.get('start_fire')), window_result=op.get('window_result'),
            drain_result=op.get('drain_result'), sum_complete=bool(se.get('complete')),
            result_ready=response_ready and not reset_edge)
        for key in ('window_fire', 'window_result_fire', 'drain_fire', 'drain_result_fire'):
            require(bool(ce[key]) == bool(oe.get(key)), 'projection endpoint handshake ' + key)
        require(ce['sum_fire'] == bool(se.get('start_fire')), 'shared Vector sum handshake')
        if oe.get('read_fire'):
            self.pending_read = None
        if oe.get('read_command_fire'):
            cmd = oe['read_command']
            require(self.pending_read is None and cmd.beats == 1, 'one existing physical read beat')
            r = self.memory._resolve(cmd.address)
            require((cmd.kind, id(r)) in (('a', id(self.a)), ('b', id(self.b))), 'read escaped full A/W allocation')
            self.pending_read = down.ReadBeat(cmd.tag, struct.unpack('<32H', self.memory.read64(cmd.address)), True)
            self.counts[cmd.kind + '_read_beats'] += 1
        if oe.get('result_fire'):
            self.bridge.retire_result(self.results.popleft())
        if oe.get('group_fire'):
            q = o.window_request
            require(type(q) is self.WINDOW_REQUEST_TYPE and q.job == self.call.job and
                    (q.k_begin, q.k_end) == self.profile.ranges[q.block_id - 1] and
                    q.pair_reverse == self.profile.pair_reverse, 'immutable GDN role/profile binding changed')
            require(self.bridge.td_group(0, q.k_end - q.k_begin, q.cols // 32) == 0,
                    'actual independent partial Matrix group rejected')
            self.groups.append((q.ng, q.cols, q.k_begin, q.k_end))
        if oe.get('step_fire'):
            s, q = oe['step'], o.window_request
            require((s.job_tag, s.identity, s.block_id, s.logical_k) ==
                    (q.job.tag, q.identity, q.block_id, q.k_begin + (s.k ^ int(q.pair_reverse))),
                    'accepted local ordinal/logical K/profile identity mismatch')
            aa, bb, out = (C.c_uint16 * 16)(*s.a), (C.c_uint16 * 256)(*s.b), (C.c_uint32 * 4096)()
            rc = self.bridge.td_step(s.k, s.context, s.clear, s.last, s.finish, s.emit, aa, bb, out)
            if rc < 0:
                self.numeric_fault = dict(rc=rc, k=s.k, block_id=q.block_id, context=s.context)
            else:
                require(rc == int(s.last), 'actual Matrix result timing mismatch')
                if rc:
                    self.results.append(down.MatrixResult(s.context, MatrixValue(bytes(out))))
        require(len(self.results) <= 2, 'existing Matrix result queue capacity exceeded')
        if oe.get('matrix_done_fire'):
            self.bridge.retire_done(args['matrix_done'])
        if ce['window_result_fire']:
            self.partials.append(asdict(op['window_result']))
            self.matrix.retire_owner_response(o)
            self.matrix.release(o)
            self.bridge = None
        if oe.get('write_command_fire'):
            require(self.memory._resolve(oe['write_command'].address) is self.output, 'write outside real BF16 D')
            self.memory.begin_write(oe['write_command'])
        if oe.get('write_data_fire'):
            b = oe['write_data']
            self.memory.write_data(b.words, b.last, mask=b.mask)
            self.counts['write_data_bytes'] += 64
            if b.last:
                cmd = self.memory.pending[0]
                self.pending_ack = down.WriteAck(cmd.tag, False, cmd.beats * 64)
        if oe.get('write_ack_fire'):
            self.memory.acknowledge(args['write_ack'])
            self.counts['ack_bytes'] += 0 if args['write_ack'].error else args['write_ack'].nbytes
            self.pending_ack = None
        if ce['drain_result_fire']:
            self.drains.append(asdict(op['drain_result']))
        require(not oe.get('seed_begin_fire') and not oe.get('seed_beat_fire'),
                'independent FP32 partials cannot seed accumulators')
        if ce['result_fire']:
            r = ce['result']
            failed = r.status or ('Protocol' if ce['reset_required'] or self.services().error else None)
            require(self.pending_read is None and self.pending_ack is None and self.memory.pending is None and
                    not self.results and self.bridge is None and self.matrix.owner is None and
                    self.loan.ports()['drained'] and not self.sum.busy and o.tiles.idle and
                    o.read_active is None and o.a_hold is None and o.a_rmw_pending is None and
                    o.pending is None and not o.fifo and o.accepted_write is None,
                    'projection terminal before accepted physical obligations drain')
            require(self.input_hashes == tuple(hashlib.sha256(x.raw()).hexdigest() for x in (self.a, self.b)),
                    'original projection inputs changed')
            self.response = (r.tag, failed, r.write_bytes)
            if failed is None:
                require(o.lease is None and not o.tiles.leased, 'projection success before all leases released')
                self.memory.publish(self.job.dst, self.response)
        self.counts['ticks'] += 1
        for key in ('read_command_fire', 'read_fire', 'step_fire', 'result_fire', 'matrix_done_fire',
                    'write_command_fire', 'write_data_fire', 'write_ack_fire'):
            self.counts[key] += bool(oe.get(key))
        ce['owner'] = oe
        ce['sum'] = se
        if self.response is not None:
            self._terminal_report = self._report()
        return ce

    def report(self):
        return deepcopy(self._terminal_report) if self._terminal_report is not None else self._report()

    def _report(self):
        return dict(scope=('GDN_TWO_PARTIAL_PACKED_BF16_SOFTWARE_OWNER' if self.family == 'gdn' else
                           'L3_TWO_PARTIAL_PACKED_BF16_SOFTWARE_OWNER'), family=self.family,
            complete=self.response is not None,
            response=self.response, role=self.role, profile=asdict(self.profile), counts=dict(self.counts),
            groups=list(self.groups), partials=list(self.partials), drains=list(self.drains),
            shared_vector=dict(self.sum.counts), vector_add_calls=self.loan.vector.calls['add'] - self.vector_calls_before,
            vector_add_lanes=self.loan.vector.lane_ops['add'] - self.vector_lanes_before,
            vector_fault=self.loan.fault, numeric_fault=self.numeric_fault,
            input_sha256=list(self.input_hashes), output_sha256=hashlib.sha256(self.output.raw()).hexdigest(),
            output_published=self.output.published,
            executed_fmas=int(self.matrix.lib.matrix_dense_fmas()) - self.fma_before,
            same_owner_and_banks=True, same_vector16=True,
            a_load_fences=self.owner.k_a_fences - self.fences_before[1],
            hardware_cycles=None, rtl_executed=False, native_acceptance=False)
