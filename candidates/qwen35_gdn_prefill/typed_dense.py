"""Packed-BF16 Dense transport over the unchanged single-chunk Down owner.

No arithmetic oracle or reference output is accepted here. Accepted physical
reads feed the original owner banks; its packets feed the caller's ONE existing
MatrixService. Only actual output data, write ACKs and the accepted terminal
publish a readable span. Software ticks are not hardware cycles.
"""
from collections import Counter, deque
import ctypes as C
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct

from ..qwen2_resident_matrix.transposed_down import model as down
from ..qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService


FULL_MASK = (1 << 64) - 1
GUARD = bytes.fromhex('c3a5965a') * 16


def require(ok, why):
    if not ok:
        raise ValueError('typed Dense: ' + why)


def library_from_environment(repo, environ=None):
    """Validate an explicitly supplied existing library; never build or search.

    The CI path is the original three-source shared-recipe receipt. The
    four-source official-BF16 combined library is also usable for its unchanged
    base td_* symbols. This does not select any official-BF16 numeric policy.
    """
    from scripts import build_shared_matrix_recipe as shared
    env = os.environ if environ is None else environ
    require(bool(env.get('MATRIX_SERVICE_LIBRARY')) and bool(env.get('MATRIX_SERVICE_COMPILE_RECEIPT')),
            'explicit MATRIX_SERVICE_LIBRARY and MATRIX_SERVICE_COMPILE_RECEIPT required')
    repo = Path(repo).resolve(strict=True)
    library = Path(env['MATRIX_SERVICE_LIBRARY']).resolve(strict=True)
    receipt = Path(env['MATRIX_SERVICE_COMPILE_RECEIPT']).resolve(strict=True)
    require(library.is_file() and receipt.is_file(), 'regular library and receipt files required')
    r = json.loads(receipt.read_text())
    if r.get('status') == 'PASS_HOST_BUILD_ONLY':
        selected = shared.validate(repo, library, receipt)
    else:
        require(r.get('schema') == 1 and r.get('status') == 'PASS' and r.get('returncode') == 0 and
                r.get('policy') == 'official_bf16_dense_silu_v1' and r.get('hardware_simulation') is False,
                'unsupported combined library receipt')
        require(r.get('library') == str(library) and shared.sha(library) == r.get('library_sha256'),
                'combined library path/hash identity')
        extra = 'candidates/qwen2_resident_matrix/official_bf16/silu_recipe.cpp'
        sources = (*shared.SOURCES, extra)
        require(r.get('source_sha256') == {name: shared.sha(repo / name) for name in sources},
                'combined library exact source closure/hash')
        compiler = Path(r['compiler']['path']).resolve(strict=True)
        require(shared.sha(compiler) == r['compiler']['sha256'], 'combined compiler identity')
        expected = [str(compiler), *shared.FLAGS, str(repo / shared.SOURCES[0]),
                    str(repo / extra), '-o', str(library)]
        require(r.get('argv') == expected, 'combined strict compile argv')
        selected = library
    with selected.open('rb') as stream:
        require(stream.read(4) == b'\x7fELF', 'actual existing ELF library required')
    return selected


@dataclass
class Region:
    base: int
    extent: int
    storage: bytearray
    readonly: bool
    published: bool
    written: set
    acknowledged: set

    def raw(self):
        self.check()
        return bytes(self.storage[64:-64])

    def check(self):
        require(self.storage[:64] == GUARD and self.storage[-64:] == GUARD,
                'physical region guard changed')


class TypedMemory:
    """One physical byte map, suitable for sharing with the input RMS owner.

    RMS can use the same begin_write/write_data/acknowledge/publish operations.
    add_readonly is for authenticated raw input/parameters only. Intermediate
    producers must allocate_output and publish their real accepted writes.
    """
    def __init__(self):
        self.regions = {}
        self.pending = None

    def _add(self, base, extent, raw=None):
        require(type(base) is int and type(extent) is int and base >= 0 and
                base % 64 == extent % 64 == 0 and extent > 0 and base + extent <= 1 << 56,
                'aligned nonempty physical span')
        require(all(base + extent <= r.base or r.base + r.extent <= base
                    for r in self.regions.values()), 'physical allocation alias')
        readonly = raw is not None
        require(not readonly or type(raw) is bytes and len(raw) == extent, 'readonly byte extent')
        value = raw if readonly else bytes.fromhex('c3a5965a') * (extent // 4)
        r = Region(base, extent, bytearray(GUARD + value + GUARD), readonly, readonly, set(), set())
        self.regions[base] = r
        return r

    def add_readonly(self, base, raw):
        return self._add(base, len(raw), raw)

    def allocate_output(self, base, extent):
        return self._add(base, extent)

    def exact(self, base, extent, *, readable):
        r = self.regions.get(base)
        require(r is not None and r.extent == extent, 'complete physical span identity')
        r.check()
        if readable:
            require(r.published and (r.readonly or r.acknowledged == set(range(0, extent, 64))),
                    'source has no complete accepted producer ACK/terminal')
        else:
            require(not r.readonly and not r.published and not r.written and not r.acknowledged,
                    'destination must be fresh unpublished staging')
        return r

    def _resolve(self, address, size=64):
        require(type(address) is int and address % 64 == 0 and size > 0 and size % 64 == 0,
                'physical access alignment')
        matches = [r for r in self.regions.values() if r.base <= address and address + size <= r.base + r.extent]
        require(len(matches) == 1, 'physical access outside one allocation')
        return matches[0]

    def read64(self, address):
        r = self._resolve(address)
        require(r.published, 'read before producer terminal')
        r.check()
        offset = address - r.base + 64
        return bytes(r.storage[offset:offset + 64])

    def begin_write(self, command):
        require(self.pending is None and type(command.beats) is int and 1 <= command.beats <= 16,
                'overlapping or invalid write descriptor')
        require(command.address // 1024 == (command.address + command.beats * 64 - 1) // 1024,
                'write crosses original 1KiB boundary')
        r = self._resolve(command.address, command.beats * 64)
        require(not r.readonly and not r.published, 'write to readonly/published allocation')
        offsets = tuple(command.address - r.base + i * 64 for i in range(command.beats))
        require(not any(i in r.written for i in offsets), 'duplicate physical write')
        self.pending = [command, r, offsets, 0]

    def write_data(self, words, last, *, mask=FULL_MASK):
        require(self.pending is not None and mask == FULL_MASK, 'full 64-byte output mask required')
        command, r, offsets, index = self.pending
        require(index < command.beats and type(last) is bool and last == (index + 1 == command.beats),
                'write LAST/count mismatch')
        require(len(words) == 32 and all(type(w) is int and 0 <= w < 65536 for w in words),
                'packed BF16 output requires 32 uint16 per 64B beat')
        offset = offsets[index]
        r.storage[64 + offset:128 + offset] = struct.pack('<32H', *words)
        r.written.add(offset)
        self.pending[3] += 1

    def acknowledge(self, ack):
        require(self.pending is not None, 'unsolicited write ACK')
        command, r, offsets, count = self.pending
        require(count == command.beats, 'ACK before final data beat')
        require(ack.tag == command.tag and ack.nbytes == command.beats * 64,
                'write ACK identity/explicit byte count')
        if not ack.error:
            r.acknowledged.update(offsets)
        self.pending = None

    def publish(self, base, response):
        r = self.regions[base]
        require(self.pending is None and response[1] is None and response[2] == r.extent,
                'publication before successful owner terminal')
        require(not r.readonly and not r.published and
                r.written == r.acknowledged == set(range(0, r.extent, 64)),
                'incomplete actual data/ACK coverage')
        r.check()
        r.published = True

    def publish_many(self, bases, response):
        """Atomically expose all spans of one accepted successful terminal.

        Validate every span, including guards and complete real ACK coverage,
        before changing any visibility. The driver owns terminal handshake
        and tag validation; this byte map enforces the aggregate byte fence.
        """
        require(type(bases) is tuple and bases and all(type(b) is int for b in bases)
                and len(set(bases)) == len(bases), 'distinct explicit output spans required')
        require(type(response) is tuple and len(response) == 3 and
                response[1] is None and type(response[2]) is int and self.pending is None,
                'multi-span publication before successful owner terminal')
        require(all(b in self.regions for b in bases), 'unknown publication span')
        regions = tuple(self.regions[b] for b in bases)
        require(response[2] == sum(r.extent for r in regions),
                'aggregate terminal byte count does not cover output spans')
        for r in regions:
            require(not r.readonly and not r.published and
                    r.written == r.acknowledged == set(range(0, r.extent, 64)),
                    'incomplete actual multi-span data/ACK coverage')
            r.check()
        for r in regions:
            r.published = True


def dense_wire_authority(owner, job):
    """Select only the two explicit owner implementations, never duck typing.

    The reduction hierarchy imports a hash-checked copy of the original Down
    module. Its seeded wire dataclasses have that exact Python identity even
    though the source and physical bank geometry are identical. Ordinary and
    seeded jobs keep using the original public Job and unchanged arithmetic.
    """
    require(type(job) is down.Job, 'original complete Down Job required')
    if type(owner) is down.DenseOwnerModel:
        return down
    from .projection_owner import GdnProjectionOwner, down as projection_down
    require(type(owner) is GdnProjectionOwner, 'unsupported Dense owner authority')
    return projection_down


class TypedDenseDriver:
    """One actual single-K-chunk invocation; reuse owner/service between jobs.

    abort uses the original owner's public local_reset drain input and the real
    Matrix abort. It leaves both poisoned until the caller coordinates reset.
    A failed invocation never publishes its staging output.
    """
    def __init__(self, owner, matrix_service, memory, job):
        self.wire = dense_wire_authority(owner, job)
        require(type(matrix_service) is MatrixService and type(memory) is TypedMemory,
                'base shared MatrixService and typed physical byte map required')
        job.validate()
        require(all(type(v) is bool and v for v in
                    (job.activation_bf16, job.weight_bf16, job.output_bf16)) and
                job.write_bytes == job.m * job.n * 2, 'BF16 A/W/D and exact 2B output extent')
        require(owner.workspace is not None, 'explicit bounded workspace identity required')
        owner.workspace.validate(job)
        require(job.k <= owner.workspace.split_k and owner.state == 'idle' and not owner.error,
                'single chunk and drained, unpoisoned owner required')
        require(memory.pending is None and matrix_service.owner is None and not matrix_service.reset_required,
                'transport/Matrix must be drained before admission')
        self.a = memory.exact(job.a, job.m * job.k * 2, readable=True)
        self.b = memory.exact(job.b, job.k * job.n * 2, readable=True)
        self.output = memory.exact(job.dst, job.write_bytes, readable=False)
        self.owner, self.matrix, self.memory, self.job = owner, matrix_service, memory, job
        self.input_hashes = tuple(hashlib.sha256(r.raw()).hexdigest() for r in (self.a, self.b))
        self.bank_identity = (id(owner.a_banks), id(owner.b_banks), matrix_service.resource_address)
        self.pending_read = self.pending_ack = None
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

    def tick(self, *, read_ready=True, read_response_ready=True, step_ready=True,
             result_ready=True, done_ready=True, write_ready=True, data_ready=True,
             ack_ready=True, response_ready=True, abort=False, ack_error=False):
        require(self.response is None, 'invocation already retired')
        require(self.bank_identity == (id(self.owner.a_banks), id(self.owner.b_banks),
                                     self.matrix.resource_address), 'physical resources replaced')
        o = self.owner
        owner_poison = bool(o.ports().get('reset_required', False))
        reset_edge = bool(abort or self.numeric_fault or owner_poison) and not self.aborted
        self.aborted |= reset_edge
        if (reset_edge or o.error) and not self.abort_sent:
            self.matrix.abort(o)
            self.abort_sent = True
        p = o.ports()
        inputs = dict(read_command_ready=read_ready, group_ready=not self.abort_sent,
            step_ready=step_ready and not self.abort_sent and
                not (p['step'] is not None and p['step'].last and len(self.results) >= 2),
            write_command_ready=write_ready, write_data_ready=data_ready,
            # The owner exposes PRE-edge ports. A first abort/fault must not
            # consume a held success before local_reset changes its terminal.
            response_ready=response_ready and not reset_edge, local_reset=reset_edge)
        if self.pending_read is not None and read_response_ready:
            inputs['read_beat'] = self.pending_read
        if self.results and result_ready:
            inputs['result'] = self.results[0]
        if self.pending_ack is not None and ack_ready:
            a = self.pending_ack
            inputs['write_ack'] = self.wire.WriteAck(a.tag, bool(ack_error), a.nbytes)
        done = None
        if p['matrix_done_ready'] and done_ready and not self.results and self.matrix.lib.matrix_done_ready():
            done = self.wire.MatrixDone(self.job.tag, self.matrix.reset_required)
            inputs['matrix_done'] = done
        e = o.tick(**inputs)
        self.counts['ticks'] += 1
        if e['read_fire']:
            self.pending_read = None
            self.counts['read_responses'] += 1
        if e['read_command_fire']:
            require(self.pending_read is None, 'more than one accepted read')
            command = e['read_command']
            r = self.memory._resolve(command.address)
            require((command.kind, id(r)) in (('a', id(self.a)), ('b', id(self.b))) and command.beats == 1,
                    'owner read escaped actual A/W allocation')
            words = struct.unpack('<32H', self.memory.read64(command.address))
            self.pending_read = self.wire.ReadBeat(command.tag, words, True)
            self.counts[command.kind + '_read_beats'] += 1
        if e['result_fire']:
            value = self.results.popleft()
            self.bridge.retire_result(value)
            self.counts['results'] += 1
        if e['group_fire']:
            require(e['group'] == (self.job.tag, 0x20, 255, True) and o.chunk_start == 0 and
                    o.chunk_end == self.job.k, 'original single-chunk Matrix contract')
            require(self.bridge.td_group(0, self.job.k, o.contexts) == 0, 'actual Matrix group rejected')
            self.groups.append((o.n_base, o.contexts))
        if e['step_fire']:
            step = e['step']
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
            require(self.memory._resolve(e['write_command'].address) is self.output,
                    'write outside exact 2B destination')
            self.memory.begin_write(e['write_command'])
            self.counts['write_commands'] += 1
        if e['write_data_fire']:
            beat = e['write_data']
            self.memory.write_data(beat.words, beat.last, mask=FULL_MASK)
            self.counts['write_data_bytes'] += 64
            if beat.last:
                command = self.memory.pending[0]
                self.pending_ack = self.wire.WriteAck(command.tag, False, command.beats * 64)
        if e['write_ack_fire']:
            self.memory.acknowledge(inputs['write_ack'])
            self.pending_ack = None
            self.counts['ack_bytes'] += 0 if inputs['write_ack'].error else inputs['write_ack'].nbytes
        if done is not None and p['matrix_done_ready']:
            self.bridge.retire_done(done)
            self.counts['done'] += 1
        require(not e['seed_begin_fire'] and not e['seed_beat_fire'] and o.prefix_bytes == 0,
                'single chunk used prefix or seed')
        if e['response_fire']:
            require(self.pending_read is None and self.pending_ack is None and not self.results and
                    self.memory.pending is None, 'terminal before transport drain')
            require(self.input_hashes == tuple(hashlib.sha256(r.raw()).hexdigest() for r in (self.a, self.b)),
                    'input/weight changed during actual execution')
            raw_response = e['response']
            # This adapter is the public consumer. A sideband poison raised
            # on this same edge cannot publish a held internal success.
            failed = raw_response[1] or ('Protocol' if o.ports().get('reset_required', False) else None)
            response = (raw_response[0], failed, raw_response[2])
            if response[1] is None:
                require(self.groups == [(n, min(5, (self.job.n - n) // 32))
                                        for n in range(0, self.job.n, 160)] and
                        self.counts['steps'] == self.job.k * (self.job.n // 32) and
                        self.counts['a_read_beats'] == self.job.m * self.job.k // 32 and
                        self.counts['b_read_beats'] == self.job.k * self.job.n // 32,
                        'incomplete actual Dense windows/reads/steps')
            self.matrix.retire_owner_response(o)
            self.matrix.release(o)
            if response[1] is None:
                self.memory.publish(self.job.dst, response)
            self.executed_fmas = int(self.matrix.lib.matrix_dense_fmas()) - self.fma_before
            self.response = response
        return e

    def report(self):
        return dict(scope='SINGLE_CHUNK_PACKED_BF16_DENSE_SOFTWARE_MODEL',
            complete=self.response is not None, response=self.response, counts=dict(self.counts),
            groups=list(self.groups), input_sha256=list(self.input_hashes),
            output_sha256=hashlib.sha256(self.output.raw()).hexdigest(),
            output_published=self.output.published, numeric_fault=self.numeric_fault,
            executed_fmas=(self.executed_fmas if self.response is not None else
                           int(self.matrix.lib.matrix_dense_fmas()) - self.fma_before),
            hardware_cycles=None, rtl_executed=False, native_acceptance=False)
