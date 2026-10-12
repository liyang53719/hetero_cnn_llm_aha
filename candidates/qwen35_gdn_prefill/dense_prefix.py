"""Two-chunk packed-BF16 Dense transport using the existing Down/Matrix owner.

The first sweep writes all 4096 FP32 cells of each physical context to private
DDR. Its actual ACKed bytes, in the original seed permutation, restore the
same five accumulator banks before ascending-K continuation. Only final D is
BF16 RNE. This adapter has one prefix version and deliberately rejects a third
chunk; it is not a general multi-version prefix store or an arithmetic model.

The caller allocates the entire PrefixWorkspace in the shared TypedMemory.
It stays unpublished, including after success. A new invocation needs fresh
staging; this driver never resets or replaces the owner, banks, or service.
"""
from collections import Counter, deque
import ctypes as C
import hashlib
import struct

from .typed_dense import FULL_MASK, MatrixService, TypedMemory, down, require, dense_wire_authority


class TypedSeededDenseDriver:
    """Exactly two K chunks, including K3584 with the original split of 2560.

    Tick readiness controls are transport stalls, not hardware cycles. A local
    abort drains accepted reads, writes, results, seed ACKs, and MatrixDone and
    leaves both owners locked until an external coordinated reset.
    """
    def __init__(self, owner, matrix_service, memory, job):
        self.wire = dense_wire_authority(owner, job)
        require(type(matrix_service) is MatrixService and type(memory) is TypedMemory,
                'base shared MatrixService and typed physical byte map required')
        job.validate()
        require(all(type(v) is bool and v for v in
                    (job.activation_bf16, job.weight_bf16, job.output_bf16)) and
                job.write_bytes == job.m * job.n * 2, 'BF16 A/W/D and exact 2B output extent')
        workspace = owner.workspace
        require(type(workspace) is self.wire.PrefixWorkspace, 'explicit bounded workspace identity required')
        workspace.validate(job)
        require(workspace.split_k < job.k <= 2 * workspace.split_k,
                'exactly two K chunks required')
        require(owner.state == 'idle' and not owner.error,
                'drained, unpoisoned owner required')
        require(memory.pending is None and matrix_service.owner is None and not matrix_service.reset_required,
                'transport/Matrix must be drained before admission')
        self.a = memory.exact(job.a, job.m * job.k * 2, readable=True)
        self.b = memory.exact(job.b, job.k * job.n * 2, readable=True)
        self.output = memory.exact(job.dst, job.write_bytes, readable=False)
        self.prefix = memory.exact(workspace.base, workspace.extent, readable=False)
        self.prefix_extent = job.n // 32 * 16384
        self.prefix_offsets = frozenset(range(0, self.prefix_extent, 64))
        self.owner, self.matrix, self.memory, self.job = owner, matrix_service, memory, job
        self.workspace = workspace
        self.input_hashes = tuple(hashlib.sha256(r.raw()).hexdigest() for r in (self.a, self.b))
        self.bank_identity = (id(owner.a_banks), id(owner.b_banks), matrix_service.resource_address)
        self.epoch = matrix_service.epoch
        # Only this invocation may restore its one committed prefix version.
        self.prefix_version = (job.tag, workspace.generation, self.epoch, 1, workspace.split_k)
        self._prefix_written = {}
        self._prefix_receipts = {}
        self._prefix_reads = set()
        self._prefix_seeds = set()
        self.pending_read = self.pending_ack = self.pending_seed_ack = None
        self._pending_prefix_read = None
        self.active_seed = None
        self.results = deque()
        self.response = None
        self.aborted = self.abort_sent = False
        self.numeric_fault = None
        self.counts = Counter()
        self.groups = []
        self.fma_before = int(matrix_service.lib.matrix_dense_fmas())
        self.executed_fmas = None
        require(self.matrix.acquire(owner, 'dense', job.tag), 'shared Matrix acquisition rejected')
        self.bridge = self.matrix.dense_library(owner)
        self.owner.tick(job=job)
        require(owner.error is None, 'validated owner admission failed')

    def _check_identity(self):
        require(self.bank_identity == (id(self.owner.a_banks), id(self.owner.b_banks),
                                      self.matrix.lib.matrix_accumulator_address()) and
                self.matrix.resource_address == self.bank_identity[2] and
                self.matrix.epoch == self.epoch and self.owner.workspace is self.workspace,
                'physical resources/workspace/epoch replaced')
        require(all(self.memory.regions.get(r.base) is r for r in
                    (self.a, self.b, self.output, self.prefix)), 'physical allocation replaced')
        require(not self.prefix.published, 'private prefix must never be published')

    def _prefix_bytes(self, command):
        """Read only the accepted, current owned prefix descriptor, never D."""
        self._check_identity()
        o = self.owner
        require(command.kind == 'prefix' and command.beats == 1 and
                o.read_active is not None and o.read_active[0] == command,
                'prefix read requires its exact accepted descriptor')
        require(o.chunk_index == 1 and o.prefix_valid and
                o.committed_prefix_end == self.workspace.split_k and o.completed_prefix_sweeps == 1 and
                self.prefix.written == self.prefix.acknowledged == self.prefix_offsets and
                set(self._prefix_receipts) == self.prefix_offsets,
                'prefix read before complete ACKed prior sweep')
        require(self.memory._resolve(command.address) is self.prefix,
                'prefix read escaped exact workspace allocation')
        expected = self.workspace.base + (o.n_base // 32 + o.seed_context) * 16384 + self.wire.prefix_ddr_beat(o.seed_index) * 64
        require(command.address == expected, 'prefix read address/order mismatch')
        offset = command.address - self.prefix.base
        require(offset in self.prefix_offsets, 'prefix read outside live physical contexts')
        self.prefix.check()
        raw = bytes(self.prefix.storage[64 + offset:128 + offset])
        require(self._prefix_receipts[offset] == (self.prefix_version, hashlib.sha256(raw).digest()),
                'stale or changed ACKed prefix version')
        return raw

    def _check_seed_request(self, request):
        o = self.owner
        require(o.chunk_index == 1 and request == self.wire.SeedRequest(
                    self.job.tag, o.group_sequence, self.workspace.generation, o.seed_context) and
                request.context < o.contexts, 'seed request identity/context mismatch')

    def tick(self, *, read_ready=True, read_response_ready=True, step_ready=True,
             result_ready=True, done_ready=True, write_ready=True, data_ready=True,
             ack_ready=True, response_ready=True, seed_begin_ready=True,
             seed_beat_ready=True, seed_ack_ready=True, abort=False,
             ack_error=False, seed_ack_error=False):
        require(self.response is None, 'invocation already retired')
        self._check_identity()
        o = self.owner
        owner_poison = bool(o.ports().get('reset_required', False))
        reset_edge = bool(abort or self.numeric_fault or owner_poison) and not self.aborted
        self.aborted |= reset_edge
        if (reset_edge or o.error) and not self.abort_sent:
            self.matrix.abort(o)
            self.abort_sent = True
        # An accepted, even partially loaded, seed owns an ACK obligation.
        # Abort retires it as an error through the real facade, not by reset.
        if self.abort_sent and self.active_seed is not None:
            self.pending_seed_ack = self.wire.SeedAck(self.active_seed, True)
        p = o.ports()
        chunk, start, end = o.chunk_index, o.chunk_start, o.chunk_end
        n_base, contexts = o.n_base, getattr(o, 'contexts', 0)
        inputs = dict(read_command_ready=read_ready, group_ready=not self.abort_sent,
            step_ready=step_ready and not self.abort_sent and
                not (p['step'] is not None and p['step'].last and len(self.results) >= 2),
            write_command_ready=write_ready, write_data_ready=data_ready,
            # The owner exposes PRE-edge ports. A first abort/fault must not
            # consume a held success before local_reset changes its terminal.
            response_ready=response_ready and not reset_edge, local_reset=reset_edge,
            seed_begin_ready=seed_begin_ready and not self.abort_sent,
            seed_beat_ready=seed_beat_ready and not self.abort_sent)
        if self.pending_read is not None and read_response_ready:
            if self._pending_prefix_read is not None and not (self.abort_sent or o.error):
                command, raw = self._pending_prefix_read
                require(self._prefix_bytes(command) == raw, 'prefix bytes changed while read response held')
            inputs['read_beat'] = self.pending_read
        if self.results and result_ready:
            inputs['result'] = self.results[0]
        if self.pending_ack is not None and ack_ready:
            a = self.pending_ack
            inputs['write_ack'] = self.wire.WriteAck(a.tag, bool(ack_error), a.nbytes)
        if self.pending_seed_ack is not None and seed_ack_ready and p['seed_ack_ready']:
            ack = self.pending_seed_ack
            inputs['seed_ack'] = self.wire.SeedAck(ack.request, bool(ack.error or seed_ack_error))
        done = None
        if (p['matrix_done_ready'] and done_ready and not self.results and
                self.active_seed is None and self.pending_seed_ack is None and
                self.matrix.lib.matrix_done_ready()):
            done = self.wire.MatrixDone(self.job.tag, self.matrix.reset_required)
            inputs['matrix_done'] = done
        e = o.tick(**inputs)
        self.counts['ticks'] += 1
        if e['read_fire']:
            if self._pending_prefix_read is not None:
                command, _ = self._pending_prefix_read
                offset = command.address - self.prefix.base
                require(offset not in self._prefix_reads, 'duplicate prefix version read')
                self._prefix_reads.add(offset)
                self._pending_prefix_read = None
            self.pending_read = None
            self.counts['read_responses'] += 1
        if e['read_command_fire']:
            require(self.pending_read is None, 'more than one accepted read')
            command = e['read_command']
            require(command.beats == 1, 'original one-beat physical read required')
            if command.kind == 'prefix':
                raw = self._prefix_bytes(command)
                self._pending_prefix_read = (command, raw)
                words = struct.unpack('<16I', raw)
            else:
                r = self.memory._resolve(command.address)
                require((command.kind, id(r)) in (('a', id(self.a)), ('b', id(self.b))),
                        'owner read escaped actual A/W allocation')
                words = struct.unpack('<32H', self.memory.read64(command.address))
            self.pending_read = self.wire.ReadBeat(command.tag, words, True)
            self.counts[command.kind + '_read_beats'] += 1
        if e['result_fire']:
            value = self.results.popleft()
            self.bridge.retire_result(value)
            self.counts['results'] += 1
        if e['group_fire']:
            expected = [(c, n, min(5, (self.job.n - n) // 32), lo, hi)
                        for c, lo, hi in ((0, 0, self.workspace.split_k),
                                          (1, self.workspace.split_k, self.job.k))
                        for n in range(0, self.job.n, 160)]
            observed = (chunk, n_base, contexts, start, end)
            require(e['group'] == (self.job.tag, 0x20, 255, True) and
                    len(self.groups) < len(expected) and observed == expected[len(self.groups)] and
                    self.counts['done'] == len(self.groups), 'original chunk-major Matrix group contract')
            require(self.bridge.td_group(start, end, contexts) == 0, 'actual Matrix group rejected')
            self.groups.append(observed)
        if e['seed_begin_fire']:
            request = e['seed_begin']
            self._check_seed_request(request)
            require(self.active_seed is None and self.pending_seed_ack is None,
                    'overlapping seed restore')
            require(self.bridge.td_seed_begin(request.context) == 0, 'actual Matrix seed reservation rejected')
            self.active_seed = request
            self.counts['seed_begins'] += 1
        if e['seed_beat_fire']:
            beat = e['seed_beat']
            require(beat.request == self.active_seed and not beat.error,
                    'seed beat owner/identity/error')
            offset = (n_base // 32 + beat.request.context) * 16384 + self.wire.prefix_ddr_beat(beat.index) * 64
            raw = struct.pack('<16I', *beat.words)
            require(offset in self._prefix_reads and offset not in self._prefix_seeds and
                    self._prefix_receipts.get(offset) == (self.prefix_version, hashlib.sha256(raw).digest()),
                    'seed is not the exact accepted ACKed prefix reread')
            require(beat.last == (beat.index == 255), 'seed LAST/index mismatch')
            rc = self.bridge.td_seed_beat(beat.request.context, beat.index, (C.c_uint32 * 16)(*beat.words))
            if rc != 0:
                self.numeric_fault = 'actual Matrix seed beat returned ' + str(rc)
            else:
                self._prefix_seeds.add(offset)
                self.counts['seed_beats'] += 1
                if beat.last:
                    rc = self.bridge.td_seed_commit(beat.request.context)
                    if rc != 0:
                        self.numeric_fault = 'actual Matrix seed commit returned ' + str(rc)
                    else:
                        self.pending_seed_ack = self.wire.SeedAck(beat.request)
        if e['seed_ack_fire']:
            ack = inputs['seed_ack']
            require(ack.request == self.active_seed, 'seed ACK changed owned request')
            self.bridge.retire_seed_ack(ack)
            self.active_seed = self.pending_seed_ack = None
            self.counts['seed_acks'] += 1
            self.counts['seed_errors'] += int(ack.error)
        if e['step_fire']:
            step = e['step']
            require(start <= step.k < end and step.clear == (step.k == 0), 'global K/clear semantics')
            require(chunk == 0 or (self.active_seed is None and
                    self.counts['seed_acks'] == n_base // 32 + contexts), 'step before actual seed ACK retirement')
            aa, bb = (C.c_uint16 * 16)(*step.a), (C.c_uint16 * 256)(*step.b)
            output = (C.c_uint32 * 4096)()
            rc = self.bridge.td_step(step.k, step.context, step.clear, step.last,
                                    step.finish, step.emit, aa, bb, output)
            self.counts['steps'] += 1
            if rc < 0:
                self.numeric_fault = 'actual Matrix step returned ' + str(rc)
            else:
                require(rc in (0, 1) and bool(rc) == step.last, 'Matrix result timing mismatch')
                if rc == 1:
                    value = tuple(tuple(int(output[r * 256 + c]) for c in range(256)) for r in range(16))
                    self.results.append(self.wire.MatrixResult(step.context, value))
                    self.counts['peak_results'] = max(self.counts['peak_results'], len(self.results))
        if e['write_command_fire']:
            command = e['write_command']
            r = self.memory._resolve(command.address, command.beats * 64)
            require(r is (self.prefix if chunk == 0 else self.output),
                    'write outside owned prefix/final destination')
            if r is self.prefix:
                require(command.beats == 1 and command.address - r.base in self.prefix_offsets,
                        'prefix write outside full physical context extent')
            self.memory.begin_write(command)
            self.counts['write_commands'] += 1
        if e['write_data_fire']:
            beat = e['write_data']
            is_prefix = self.memory.pending[1] is self.prefix
            # TypedMemory is a byte map with a uint16 bus ABI. Repack every
            # FP32 bit; applying BF16 conversion here would destroy the seed.
            words = struct.unpack('<32H', struct.pack('<16I', *beat.words)) if is_prefix else beat.words
            if is_prefix:
                _, _, offsets, index = self.memory.pending
                offset = offsets[index]
                require(offset not in self._prefix_written, 'duplicate prefix data version')
                self._prefix_written[offset] = hashlib.sha256(struct.pack('<32H', *words)).digest()
            self.memory.write_data(words, beat.last, mask=FULL_MASK)
            self.counts['prefix_write_data_bytes' if is_prefix else 'write_data_bytes'] += 64
            if beat.last:
                command = self.memory.pending[0]
                self.pending_ack = self.wire.WriteAck(command.tag, False, command.beats * 64)
        if e['write_ack_fire']:
            command, region, offsets, _ = self.memory.pending
            ack = inputs['write_ack']
            self.memory.acknowledge(ack)
            self.pending_ack = None
            if region is self.prefix and not ack.error:
                for offset in offsets:
                    require(offset not in self._prefix_receipts, 'duplicate prefix version ACK')
                    raw = bytes(region.storage[64 + offset:128 + offset])
                    digest = hashlib.sha256(raw).digest()
                    require(self._prefix_written.get(offset) == digest, 'prefix bytes changed before write ACK')
                    self._prefix_receipts[offset] = (self.prefix_version, digest)
            self.counts['prefix_ack_bytes' if region is self.prefix else 'ack_bytes'] += 0 if ack.error else ack.nbytes
        if done is not None and p['matrix_done_ready']:
            self.bridge.retire_done(done)
            self.counts['done'] += 1
        if e['response_fire']:
            require(self.pending_read is None and self.pending_ack is None and not self.results and
                    self.memory.pending is None and self.active_seed is None and self.pending_seed_ack is None,
                    'terminal before transport/seed drain')
            require(self.input_hashes == tuple(hashlib.sha256(r.raw()).hexdigest() for r in (self.a, self.b)),
                    'input/weight changed during actual execution')
            raw_response = e['response']
            failed = raw_response[1] or ('Protocol' if o.ports().get('reset_required', False) else None)
            response = (raw_response[0], failed, raw_response[2])
            if response[1] is None:
                total_contexts = self.job.n // 32
                require(self.counts['steps'] == self.job.k * total_contexts and
                        self.counts['a_read_beats'] == self.job.m * self.job.k // 32 and
                        self.counts['b_read_beats'] == self.job.k * self.job.n // 32 and
                        self.counts['prefix_read_beats'] == self.counts['seed_beats'] == self.prefix_extent // 64 and
                        self.counts['seed_acks'] == total_contexts and self.counts['seed_errors'] == 0 and
                        self.counts['results'] == 2 * total_contexts and
                        self.counts['done'] == len(self.groups) == 2 * ((total_contexts + 4) // 5) and
                        self.counts['prefix_ack_bytes'] == o.prefix_bytes == self.prefix_extent and
                        self._prefix_reads == self._prefix_seeds == self.prefix_offsets,
                        'incomplete actual Dense windows/reads/steps/prefix/seed retirement')
            # Publication is downstream of both accepted owner response and
            # actual service release; no pending seed/result/done may escape.
            self.matrix.retire_owner_response(o)
            self.matrix.release(o)
            if response[1] is None:
                self.memory.publish(self.job.dst, response)
            self.executed_fmas = int(self.matrix.lib.matrix_dense_fmas()) - self.fma_before
            self.response = response
        return e

    def report(self):
        return dict(scope='TWO_CHUNK_PACKED_BF16_DENSE_SOFTWARE_MODEL',
            complete=self.response is not None, response=self.response, counts=dict(self.counts),
            groups=list(self.groups), input_sha256=list(self.input_hashes),
            output_sha256=hashlib.sha256(self.output.raw()).hexdigest(),
            output_published=self.output.published, prefix_published=self.prefix.published,
            prefix_version=self.prefix_version, prefix_extent=self.prefix_extent,
            prefix_bytes=self.counts['prefix_ack_bytes'],
            numeric_fault=self.numeric_fault,
            executed_fmas=(self.executed_fmas if self.response is not None else
                           int(self.matrix.lib.matrix_dense_fmas()) - self.fma_before),
            hardware_cycles=None, rtl_executed=False, native_acceptance=False)
