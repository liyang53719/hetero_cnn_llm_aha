"""One serialized host Matrix resource and the source-bound legacy adapter.

This is a handshake model, not an RTL simulator or hardware-cycle estimate.
MatrixService owns no arithmetic array: both modes call matrix_numeric.cpp's
sole inherited accum[5][16][256]. Results are immutable output snapshots.

Dense integration: configure/reset the CDLL once, create MatrixService(lib),
acquire the actual owner, and pass dense_library(owner) to the existing driver.
After its REAL accepted result, seed ACK, and MatrixDone edges, call the
adapter's retire_result/retire_seed_ack/retire_done respectively. td_step return
does not retire anything. Multiple groups may use the same acquired owner.
Only after the actual terminal response is accepted call retire_owner_response
and release. Missing fences prevent switching modes. Dense callbacks are bound
to the current synchronous driver and its already-validated accepted receipts;
optional ticket/epoch assertions do not constitute an asynchronous transport.
"""
from collections import Counter, deque
from collections.abc import Sequence
import ctypes as C
from dataclasses import dataclass, replace
import hashlib
import operator
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[3]
# V3 active runtime guard: reviewed f16 default-disabled borrower/loan path.
# Physical Matrix, arithmetic, and modeled protocol are unchanged.
# Historical source_pins/receipts remain frozen; no old result is inherited.
SOURCE_HASHES = {
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp':
        'bdd7513bd788c03ac92be1d7c2f3553d3d7e0723ce1ac2892e93dcef58782ef1',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala':
        'dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala':
        '9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4',
    'rtl/integration/qwen2_matrix_command_endpoint.sv':
        '057ce15d3b9fd5153c8873498f9cf1b3f17d7eea64e8928c1208496b3d0bd53a',
    'rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv':
        '541d4a717df08ef65e0ac047c1f83e06b1e3e1bead6553bd97ada24a32a30d59',
    'rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv':
        '0d3bbeee52db023598ebc457420cd2ed8063051363b5c89699730b7f0cbfe6bc',
    'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv':
        'a4c37b485f1e7eeed3012372024e8e7207bc33af6ff97bc307a5572aced6890e',
}


class MatrixProtocolError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise MatrixProtocolError(message)


def source_identity(root=ROOT, *, enable_h2048_rms_borrower=False,
                    external_elementwise_loan=False):
    if enable_h2048_rms_borrower is not False or external_elementwise_loan is not False:
        raise ValueError('source review requires the original default-disabled borrower/loan profile')
    for name, digest in SOURCE_HASHES.items():
        require(hashlib.sha256((Path(root) / name).read_bytes()).hexdigest() == digest,
                'Matrix source changed: ' + name)
    return dict(source_sha256=dict(SOURCE_HASHES),
                source_version='qwen2-matrix-source-guard-v3',
                source_base_commit='f16df50adfb0f1f4bc668c517a2e29accffe6753',
                source_commit=None, historical_results_inherited=False,
                borrower_enabled=False, elementwise_loan_enabled=False, hardware_simulation=False,
                model_ticks_are_hardware_cycles=False, accumulator_banks=5,
                accumulator_rows=16, accumulator_columns=256)


def configure_library(library):
    """Set ABI declarations only. Reset belongs to the coordinated caller."""
    u, q, p16, p32 = C.c_uint, C.c_uint64, C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
    signatures = {
        'td_reset': [], 'td_group': [u] * 3, 'td_seed_begin': [u],
        'td_seed_beat': [u, u, p32], 'td_seed_commit': [u],
        'td_step': [u] * 6 + [p16, p16, p32],
        'td_reference': [p32, p16, p32, u],
        'matrix_guard_enable': [], 'matrix_acquire': [u, q],
        'matrix_owner_reply_retire': [u, q], 'matrix_release': [u, q],
        'matrix_abort': [], 'matrix_done_ready': [],
        'matrix_result_retire': [q, u, u], 'matrix_done_retire': [q, u, u],
        'matrix_seed_ack': [q, u, u], 'matrix_legacy_reply_retire': [q],
        'matrix_normal_group': [u] * 4,
        'matrix_normal_group_v1': [u] * 5,
        'matrix_normal_step': [u] * 6 + [p16, p16, p32],
    }
    for name, args in signatures.items():
        fn = getattr(library, name)
        fn.argtypes, fn.restype = args, C.c_int
    for name in ('matrix_ticket', 'matrix_dense_fmas', 'matrix_normal_fmas'):
        fn = getattr(library, name)
        fn.argtypes, fn.restype = [], q
    for name in ('matrix_state', 'matrix_accumulator_bytes'):
        fn = getattr(library, name)
        fn.argtypes, fn.restype = [], u
    library.matrix_accumulator_address.argtypes = []
    library.matrix_accumulator_address.restype = C.c_size_t
    return library


@dataclass(frozen=True)
class NormalGroup:
    opcode: int
    steps: int
    tag: int
    slice_mask: int = 1
    profile: int = 0  # 0 legacy Qwen2; 1 existing rectangular GQA stream


@dataclass(frozen=True)
class NormalStep:
    index: int
    a: tuple
    b: tuple
    clear: bool
    last: bool
    context: int = 0
    finish: bool = False
    emit: bool = True


@dataclass(frozen=True, slots=True, eq=False)
class _MatrixRow(Sequence):
    _raw: bytes
    _offset: int
    __hash__ = None

    def __len__(self):
        return 256

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(256)))
        index = operator.index(index)
        if index < 0:
            index += 256
        if not 0 <= index < 256:
            raise IndexError('Matrix column outside 16x256 result')
        return struct.unpack_from('<I', self._raw, self._offset + index * 4)[0]

    def __iter__(self):
        return iter(struct.unpack_from('<256I', self._raw, self._offset))

    def __eq__(self, other):
        if isinstance(other, _MatrixRow):
            return self._raw[self._offset:self._offset+1024] == other._raw[other._offset:other._offset+1024]
        if not isinstance(other, Sequence):
            return NotImplemented
        return len(other) == 256 and all(a == b for a, b in zip(self, other))


@dataclass(frozen=True, slots=True, eq=False)
class MatrixValue(Sequence):
    """Immutable complete 16x256 FP32-bit snapshot with lazy integer access.

    Owns all 16384 output bytes, including every special bit pattern and zero
    inactive slice. It never aliases the mutable C accumulator/output buffer.
    Indexing returns the original unsigned words; .raw and .sha256 cover the
    entire result. Only requested words become Python integers.
    """
    raw: bytes
    __hash__ = None

    def __post_init__(self):
        require(isinstance(self.raw, (bytes, bytearray, memoryview)) and len(self.raw) == 16384,
                'Matrix value requires the complete 16x256 FP32-byte payload')
        object.__setattr__(self, 'raw', bytes(self.raw))

    def __len__(self):
        return 16

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self[i] for i in range(*index.indices(16)))
        index = operator.index(index)
        if index < 0:
            index += 16
        if not 0 <= index < 16:
            raise IndexError('Matrix row outside 16x256 result')
        return _MatrixRow(self.raw, index * 1024)

    def __iter__(self):
        return (_MatrixRow(self.raw, row * 1024) for row in range(16))

    def __bytes__(self):
        return self.raw

    @property
    def sha256(self):
        return hashlib.sha256(self.raw).hexdigest()

    def __eq__(self, other):
        if isinstance(other, MatrixValue):
            return self.raw == other.raw
        if not isinstance(other, Sequence):
            return NotImplemented
        return len(other) == 16 and all(a == b for a, b in zip(self, other))


@dataclass(frozen=True)
class MatrixResult:
    context: int
    value: MatrixValue
    last: bool
    error: bool
    ticket: int
    epoch: int


@dataclass(frozen=True)
class MatrixDone:
    tag: int
    error: bool
    ticket: int
    epoch: int


class MatrixService:
    MODES = {'dense': 1, 'normal': 2}

    def __init__(self, library):
        self.identity = source_identity()
        self.lib = configure_library(library)
        require(self.lib.matrix_guard_enable() == 0,
                'enable guard after initial td_reset and before any arithmetic')
        self.resource_address = self.lib.matrix_accumulator_address()
        require(self.lib.matrix_accumulator_bytes() == 5 * 16 * 256 * 4,
                'unexpected physical accumulator allocation')
        self.owner = self.mode = self.owner_tag = None
        self.epoch = 0
        self.counts = Counter()
        self.group = self.result = self._done = None
        self._dense = None
        self._owner_retired = False

    @property
    def ticket(self):
        return int(self.lib.matrix_ticket())

    @property
    def reset_required(self):
        return bool(self.lib.matrix_state() & 256)

    def _check_owner(self, owner, mode=None):
        require(self.owner is owner and self.owner is not None and
                (mode is None or self.mode == mode), 'Matrix owner/resource mismatch')
        require(self.resource_address == self.lib.matrix_accumulator_address(),
                'Matrix accumulator resource changed')

    def _check_event(self, ticket=None, epoch=None):
        require(ticket is None or ticket == self.ticket, 'late Matrix group event')
        require(epoch is None or epoch == self.epoch, 'late Matrix reset epoch')

    def acquire(self, owner, mode, tag):
        require(mode in self.MODES and type(tag) is int and 0 <= tag < 1 << 32,
                'Matrix acquisition mode/tag')
        if owner is None or self.owner is not None:
            return False
        if self.lib.matrix_acquire(self.MODES[mode], tag) != 0:
            return False
        self.owner, self.mode, self.owner_tag = owner, mode, tag
        self._owner_retired = False
        self.counts['owner_acquires'] += 1
        return True

    def retire_owner_response(self, owner):
        """Call only on the actual accepted owner terminal, after all ACKs."""
        self._check_owner(owner)
        require(self.lib.matrix_owner_reply_retire(self.MODES[self.mode], self.owner_tag) == 0,
                'owner response before result/done/seed/reply retirement')
        self._owner_retired = True
        self.counts['owner_responses'] += 1

    def release(self, owner):
        self._check_owner(owner)
        require(self._owner_retired and
                self.lib.matrix_release(self.MODES[self.mode], self.owner_tag) == 0,
                'Matrix release before actual owner response')
        self.owner = self.mode = self.owner_tag = self._dense = None
        self.counts['owner_releases'] += 1

    def reset(self):
        """Coordinated owner/service reset. Existing clients must also reset.

        This deliberately invalidates in-flight work; it never makes a late
        reply admissible. Callers must reset their DMA/owner model separately.
        """
        require(self.lib.td_reset() == 0, 'Matrix reset rounding environment')
        self.epoch += 1
        self.owner = self.mode = self.owner_tag = self._dense = None
        self.group = self.result = self._done = None
        self._owner_retired = False
        self.counts.clear()

    def abort(self, owner):
        self._check_owner(owner)
        require(self.lib.matrix_abort() == 0, 'Matrix abort without ownership')
        self.counts['aborts'] += 1
        # A previously exposed output stays stable through backpressure.

    @property
    def done(self):
        if self._done is None and self.group is not None and self.lib.matrix_done_ready():
            self._done = MatrixDone(self.group.tag, self.reset_required, self.ticket, self.epoch)
        return self._done

    def ports(self):
        state = self.lib.matrix_state()
        ready = self.mode == 'normal' and not self.reset_required
        return dict(group_ready=ready and not (state & (4 | 8 | 32 | 64)),
                    step_ready=ready and bool(state & 4) and not (state & (8 | 16 | 32)),
                    result=self.result, done=self.done, reset_required=self.reset_required)

    def accept_group(self, owner, group):
        self._check_owner(owner, 'normal')
        if not self.ports()['group_ready']:
            return False
        require(isinstance(group, NormalGroup) and all(type(x) is int and 0 <= x < 1 << 32
                for x in (group.opcode, group.steps, group.tag, group.slice_mask, group.profile)),
                'normal Matrix group fields')
        rc = (self.lib.matrix_normal_group(group.opcode, group.steps, group.tag, group.slice_mask)
              if group.profile == 0 else self.lib.matrix_normal_group_v1(
                  group.opcode, group.steps, group.tag, group.slice_mask, group.profile))
        require(rc in (0, -1), 'normal group admission disagrees with ready')
        self.group, self._done = group, None
        self.counts['normal_groups'] += 1
        return True

    def accept_step(self, owner, step):
        self._check_owner(owner, 'normal')
        if not self.ports()['step_ready']:
            return False
        require(isinstance(step, NormalStep) and len(step.a) == 16 and len(step.b) == 256 and
                all(type(x) is int and 0 <= x < 65536 for x in (*step.a, *step.b)),
                'normal Matrix BF16 packet widths')
        require(all(type(x) is int and 0 <= x < 1 << 32 for x in (step.index, step.context)),
                'normal Matrix step index/context')
        a, b, output = (C.c_uint16 * 16)(*step.a), (C.c_uint16 * 256)(*step.b), (C.c_uint32 * 4096)()
        rc = self.lib.matrix_normal_step(step.index, step.context, step.clear, step.last,
                                        step.finish, step.emit, a, b, output)
        require(rc in ((0, 1, -1) if self.group.profile == 1 else (1, -1)),
                'normal accepted step disagrees with ready')
        self.counts['normal_steps'] += 1
        if rc == 1:
            value = MatrixValue(bytes(output))
            self.result = MatrixResult(0, value, step.last, False, self.ticket, self.epoch)
        return True

    def retire_result(self, owner, result):
        self._check_owner(owner, 'normal')
        self._check_event(result.ticket, result.epoch)
        require(self.result is result, 'result payload changed or was not held by this service')
        require(self.lib.matrix_result_retire(result.ticket, result.context, result.last) == 0,
                'unexpected Matrix result retirement')
        self.result = None
        self.counts['normal_results'] += 1

    def retire_done(self, owner, done):
        self._check_owner(owner)
        self._check_event(done.ticket, done.epoch)
        require(self.lib.matrix_done_ready(), 'MatrixDone before accepted result retirement')
        require(self.lib.matrix_done_retire(done.ticket, done.tag, done.error) == 0,
                'unexpected MatrixDone retirement')
        self.group = self._done = None
        self.counts[self.mode + '_done'] += 1

    def retire_legacy_reply(self, owner, ticket, epoch):
        self._check_owner(owner, 'normal')
        self._check_event(ticket, epoch)
        require(self.lib.matrix_legacy_reply_retire(ticket) == 0,
                'legacy reply before service result and final matching done')
        self.counts['legacy_replies'] += 1

    def dense_library(self, owner):
        self._check_owner(owner, 'dense')
        if self._dense is None:
            self._dense = DenseLibraryAdapter(self, owner)
        return self._dense

    def report(self):
        return dict(counters=dict(self.counts), dense_fma_calls=int(self.lib.matrix_dense_fmas()),
                    normal_fma_calls=int(self.lib.matrix_normal_fmas()),
                    counter_provenance='Actual C++ std::fma calls; no shape-derived or hardware-cycle totals.',
                    reset_required=self.reset_required, same_accumulator_resource=True,
                    accumulator_bytes=int(self.lib.matrix_accumulator_bytes()),
                    hardware_simulation=False, model_ticks_are_hardware_cycles=False)


class DenseLibraryAdapter:
    """td_* ABI facade, plus explicit callbacks from the existing driver.

    Result payloads remain in that driver's bounded return queue. This facade
    keeps only their hashes/metadata, verifying the actual retired output.
    Seed ACK and done callbacks are never inferred from numerical function
    returns. Calls are synchronous with the current driver's accepted edges;
    that driver must validate each complete SeedRequest sequence/generation.
    Optional ticket/epoch arguments are extra assertions, not async admission.
    """
    def __init__(self, service, owner):
        self.service, self.owner = service, owner
        self.pending = deque()
        self.epoch = service.epoch

    @property
    def ticket(self):
        return self.service.ticket

    def _check(self):
        self.service._check_owner(self.owner, 'dense')
        self.service._check_event(epoch=self.epoch)
        require(self.service._dense is self, 'stale Dense bridge from a prior owner acquisition')

    def __getattr__(self, name):
        require(name not in ('td_reset', 'matrix_guard_enable', 'matrix_acquire',
                            'matrix_owner_reply_retire', 'matrix_release'),
                'Dense facade cannot reset or bypass service ownership')
        return getattr(self.service.lib, name)

    def td_seed_begin(self, context):
        self._check()
        return self.service.lib.td_seed_begin(context)

    def td_seed_beat(self, context, index, words):
        self._check()
        return self.service.lib.td_seed_beat(context, index, words)

    def td_seed_commit(self, context):
        self._check()
        return self.service.lib.td_seed_commit(context)

    def td_group(self, start, end, contexts):
        self._check()
        rc = self.service.lib.td_group(start, end, contexts)
        if rc == 0:
            require(not self.pending, 'Dense group with unretired results')
            self.service.counts['dense_groups'] += 1
        return rc

    def td_step(self, k, context, clear, last, finish, emit, a, b, output):
        self._check()
        rc = self.service.lib.td_step(k, context, clear, last, finish, emit, a, b, output)
        if rc >= 0:
            self.service.counts['dense_steps'] += 1
        if rc == 1:
            digest = hashlib.sha256(C.string_at(output, 4096 * 4)).digest()
            self.pending.append((self.ticket, context, bool(last), digest))
        return rc

    def retire_result(self, result, *, ticket=None, epoch=None):
        self._check()
        self.service._check_event(ticket, epoch)
        require(bool(self.pending), 'unsolicited Dense result')
        expected_ticket, context, last, digest = self.pending[0]
        require(result.context == context and getattr(result, 'last', True) == last and
                not getattr(result, 'error', False), 'Dense result metadata mismatch')
        raw = b''.join(struct.pack('<256I', *row) for row in result.value)
        require(len(result.value) == 16 and hashlib.sha256(raw).digest() == digest,
                'Dense result payload changed while held')
        require(self.service.lib.matrix_result_retire(expected_ticket, context, last) == 0,
                'Dense result retirement mismatch')
        self.pending.popleft()
        self.service.counts['dense_results'] += 1

    def retire_seed_ack(self, ack, *, ticket=None, epoch=None):
        self._check()
        self.service._check_event(ticket, epoch)
        require(ack.request.tag == self.service.owner_tag, 'Dense seed ACK owner tag')
        require(self.service.lib.matrix_seed_ack(self.ticket, ack.request.context, ack.error) == 0,
                'Dense seed ACK without complete owned restore')
        self.service.counts['dense_seed_acks'] += 1

    def retire_done(self, done, *, ticket=None, epoch=None):
        self._check()
        self.service._check_event(ticket, epoch)
        require(not self.pending, 'Dense done before held results retire')
        self.service.retire_done(self.owner,
            MatrixDone(done.tag, done.error, self.ticket, self.epoch))


@dataclass(frozen=True)
class LegacyRequest:
    opcode: int
    a: tuple
    b: tuple
    clear: bool
    last: bool
    steps: int
    slice_mask: int = 1


@dataclass(frozen=True)
class LegacyResult:
    value: object  # None on error-done-without-result; never a fabricated tensor.
    error: bool
    ticket: int
    epoch: int


class LegacyMatrixClient:
    """MatrixPipeline.scala LegacyMatrixStreamClient's serial state machine.

    tick returns PRE-edge ports plus request_fire/result_fire. service_result_ready
    and service_done_ready can hold the internal handshakes independently. The
    owner sees the final result only after Matrix result AND matching done have
    retired. On abort, error done without a result is drained in wait_result.
    The caller acquires/releases the same service for the complete owner job.
    """
    def __init__(self, service, owner):
        service._check_owner(owner, 'normal')
        self.service, self.owner, self.epoch = service, owner, service.epoch
        self.state, self.active, self.poison = 'idle', False, False
        self.tag, self.index = 0, 0
        self.request = self.response = self.group = None
        self._tracks_reply = False
        self._request_pending = False
        self.aborting = False

    @property
    def drained(self):
        return (not self.active and not self._request_pending and self.response is None and
                not (self.service.lib.matrix_state() & (4 | 8 | 32 | 64)))

    def ports(self):
        return dict(request_ready=self.state == 'idle' and not self.poison and
                    not self.service.reset_required and self.epoch == self.service.epoch,
                    result=self.response if self.state == 'reply' else None,
                    reset_required=self.poison or self.service.reset_required,
                    drained=self.drained)

    def _abort_edge(self, p, result_ready, service_result_ready, service_done_ready):
        """Drain accepted obligations even between requests or before issue.

        An already exposed owner reply remains byte-stable. An unexposed reply
        becomes an error only after all service outputs/done have retired. No
        response is invented when an abort lands between accepted requests.
        """
        self.poison = True
        result, done = self.service.result, self.service.done
        if self.state == 'reply' and result_ready:
            if self._tracks_reply:
                self.service.retire_legacy_reply(self.owner, self.response.ticket, self.response.epoch)
            p['result_fire'] = True
            self.response = None
            self._request_pending = self._tracks_reply = False
            self.state = 'draining'
        if result is not None and service_result_ready:
            self.service.retire_result(self.owner, result)
            if self._request_pending and self.state != 'reply':
                self.response = LegacyResult(result.value, True, result.ticket, result.epoch)
            p['service_result_fire'] = True
        if done is not None and service_done_ready:
            self.service.retire_done(self.owner, done)
            self.active = False
            p['service_done_fire'] = True
        # Check service group/result obligations, but a pending legacy reply is
        # specifically what the next owner-facing handshake must retire.
        if not (self.service.lib.matrix_state() & (4 | 8)):
            self.active = False
            if self._request_pending:
                if self.state != 'reply':
                    self.response = LegacyResult(
                        self.response.value if self.response is not None else None,
                        True, self.service.ticket, self.epoch)
                    self.state = 'reply'
            else:
                self.state = 'locked'
        self.service.counts['legacy_model_ticks'] += 1
        return p

    def tick(self, *, request=None, result_ready=False, service_result_ready=True,
             service_done_ready=True, abort=False, done_override=None):
        self.service._check_owner(self.owner, 'normal')
        self.service._check_event(epoch=self.epoch)
        p = self.ports()
        p.update(request_fire=False, result_fire=False, service_result_fire=False, service_done_fire=False)
        if abort:
            self.service.abort(self.owner)
            self.aborting = True
        if self.aborting:
            return self._abort_edge(p, result_ready, service_result_ready, service_done_ready)
        if self.state == 'idle' and request is not None and p['request_ready']:
            require(isinstance(request, LegacyRequest), 'legacy request type')
            # Copy tuples so producer mutation cannot change an accepted packet.
            self.request = replace(request, a=tuple(request.a), b=tuple(request.b))
            self._request_pending = True
            p['request_fire'] = True
            if bool(request.clear) == self.active:
                self.service.abort(self.owner);self.poison = True
                self.aborting = True
                self._tracks_reply = False;self.state = 'draining'
            elif request.clear:
                self.tag = (self.tag + 1) & 0xffffffff
                self.group = NormalGroup(request.opcode, request.steps, self.tag, request.slice_mask)
                self.index = 0;self.state = 'begin'
            else:
                require((request.opcode, request.steps, request.slice_mask) ==
                        (self.group.opcode, self.group.steps, self.group.slice_mask),
                        'legacy opcode/shape changed within active group')
                self.state = 'issue'
        elif self.state == 'begin':
            if self.service.accept_group(self.owner, self.group):
                self.active = True
                self.state = 'wait_result' if self.service.reset_required else 'issue'
                self._tracks_reply = False
        elif self.state == 'issue':
            r = self.request
            if self.service.accept_step(self.owner,
                    NormalStep(self.index, r.a, r.b, r.clear, r.last, finish=r.last)):
                self.index += 1;self._tracks_reply = True;self.state = 'wait_result'
        elif self.state == 'wait_result':
            result, done = self.service.result, self.service.done
            if result is not None and service_result_ready:
                self.service.retire_result(self.owner, result)
                self.response = LegacyResult(result.value, result.error, result.ticket, result.epoch)
                self.poison |= result.error
                self.state = 'wait_done' if self.request.last or result.error or self.service.reset_required else 'reply'
                p['service_result_fire'] = True
            elif result is None and done is not None and done.error and service_done_ready:
                done = done_override if done_override is not None else done
                self.service.retire_done(self.owner, done)
                self.active = False;self.poison = True
                self.response = LegacyResult(None, True, done.ticket, done.epoch)
                self.state = 'reply';p['service_done_fire'] = True
        elif self.state == 'wait_done':
            done = self.service.done
            if done is not None and service_done_ready:
                done = done_override if done_override is not None else done
                self.service.retire_done(self.owner, done)
                self.active = False
                self.poison |= done.error or done.tag != self.tag or self.service.reset_required
                self.response = replace(self.response, error=self.response.error or self.poison)
                self.state = 'reply';p['service_done_fire'] = True
        elif self.state == 'reply' and result_ready:
            if self._tracks_reply:
                self.service.retire_legacy_reply(self.owner, self.response.ticket, self.response.epoch)
            p['result_fire'] = True
            self.response = None
            self._request_pending = self._tracks_reply = False
            self.state = 'locked' if self.poison or self.service.reset_required else 'idle'
        self.service.counts['legacy_model_ticks'] += 1
        return p
