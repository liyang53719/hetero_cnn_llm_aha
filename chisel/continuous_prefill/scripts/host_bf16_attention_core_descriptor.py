"""Experimental Host BF16 attention-core v2 descriptors and strict preflight.

Twelve public commands retain the actual seven QKV -> Norm -> RoPE commands,
then append, QK, softmax, PV and a terminal core fence. They represent nine
owner jobs: seven producers, KV append, and one fused QK/softmax/PV owner.
Score/probability roots reserve BF16 rectangles but are internal-only: no DDR
materialization or standalone publication is implied. This module serializes
and checks the contract; it does not claim numeric or RTL execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from math import prod
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from heteronpu.abi_validation import bit, enum_value, uint
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import (
    DescriptorRecord, MatrixAux, NULL_INDEX, RecordType, SfuProgram,
    TensorDType, validate_descriptor_chain,
)
from heteronpu.gemmini_descriptor_v2 import (
    tensor_base_record, shape4_record, stride3_record, matrix_op_record,
)
from host_bf16_qkv_descriptor import parse_host_qkv_descriptor
from host_bf16_qk_rope_descriptor import (
    build_host_qkv_rope_commands, parse_host_qk_rope_descriptor,
)

CHAIN_COMMANDS, CHAIN_RECORDS, OWNER_JOBS = 12, 172, 9
ATTENTION_VERSION, ATTENTION_RECIPE = 2, 0xA1
DENSE_MATRIX_AUX = 0x004000040020FFFFFF


class AttentionOperation(IntEnum):
    APPEND = 0
    QK = 1
    SOFTMAX = 2
    PV = 3
    FENCE = 4


_ENVELOPES = {
    AttentionOperation.APPEND: (Opcode.KV_APPEND, Engine.KV),
    AttentionOperation.QK: (Opcode.MATRIX_QK, Engine.MATRIX),
    AttentionOperation.SOFTMAX: (Opcode.SFU_SOFTMAX, Engine.SFU_CGRA),
    AttentionOperation.PV: (Opcode.MATRIX_PV, Engine.MATRIX),
    AttentionOperation.FENCE: (Opcode.SFU_VECTOR, Engine.SFU_CGRA),
}


def _disjoint(spans):
    """Check complete physical allocations, including inactive guards."""
    for index, (address, size) in enumerate(spans):
        uint(address, 56, 'DDR address')
        if address % 64 or size <= 0 or address + size > 1 << 56:
            raise ValueError('unaligned or overflowing full DDR allocation')
        if any(address < other + length and other < address + size
               for other, length in spans[:index]):
            raise ValueError('full physical attention allocations overlap')


@dataclass(frozen=True)
class AttentionContext:
    capacity: int
    expected_length: int
    query_start: int
    expected_generation: int
    cold: bool

    def __post_init__(self):
        for name, width in (('capacity', 9), ('expected_length', 9),
                            ('query_start', 9), ('expected_generation', 32)):
            object.__setattr__(self, name, uint(getattr(self, name), width, name))
        object.__setattr__(self, 'cold', bit(self.cold, 'cold'))
        if not 1 <= self.capacity <= 256 or self.expected_length != self.query_start:
            raise ValueError('capacity or absolute queryStart/expectedLength mismatch')
        if self.expected_length >= self.capacity or self.expected_generation == 0xFFFFFFFF:
            raise ValueError('cache length or next generation exceeds capacity')
        if self.cold:
            if self.expected_length or self.expected_generation:
                raise ValueError('cold cache requires expected length and generation zero')
        elif not self.expected_length or not self.expected_generation:
            raise ValueError('carried cache requires positive expected length and generation')

    def payload(self):
        self.__post_init__()
        return (ATTENTION_VERSION | self.capacity << 8 | self.expected_length << 17 |
                self.query_start << 26 | self.expected_generation << 35 |
                int(self.cold) << 67 | 1 << 68)

    def to_record(self):
        return DescriptorRecord(RecordType.ATTENTION_CONTEXT, 0, 0, NULL_INDEX, self.payload())

    @classmethod
    def from_record(cls, record):
        record.__post_init__()
        p = record.payload
        if record.record_type != RecordType.ATTENTION_CONTEXT or record.next_index != NULL_INDEX:
            raise ValueError('attention context must terminate the policy chain')
        if p & 255 != ATTENTION_VERSION or p >> 69 or (p >> 68) & 1 != 1:
            raise ValueError('unsupported context version, causal bit or reserved bits')
        return cls((p >> 8) & 511, (p >> 17) & 511, (p >> 26) & 511,
                   (p >> 35) & 0xFFFFFFFF, bool((p >> 67) & 1))


@dataclass(frozen=True)
class AttentionTensor:
    address: int
    shape: tuple[int, ...]

    def __post_init__(self):
        object.__setattr__(self, 'address', uint(self.address, 56, 'tensor address'))
        if not isinstance(self.shape, (tuple, list)) or len(self.shape) not in (2, 3):
            raise ValueError('attention tensor requires rank2 or rank3')
        shape = tuple(uint(v, 18, 'shape dimension') for v in self.shape)
        if not all(shape):
            raise ValueError('attention tensor dimensions must be positive')
        object.__setattr__(self, 'shape', shape)
        _disjoint((self.span,))

    @property
    def payload_bytes(self): return prod(self.shape) * 2

    @property
    def span(self): return self.address, (self.payload_bytes + 63) // 64 * 64

    @property
    def strides(self):
        return ((self.shape[1], 1, 1) if len(self.shape) == 2 else
                (self.shape[1] * self.shape[2], self.shape[2], 1))


@dataclass(frozen=True)
class HostAttentionCommandBinding:
    operation: AttentionOperation
    token_base: int
    token_count: int
    context: AttentionContext
    src0: AttentionTensor
    src1: AttentionTensor | None
    dst: AttentionTensor

    def __post_init__(self):
        object.__setattr__(self, 'operation', enum_value(self.operation, AttentionOperation, 'operation'))
        object.__setattr__(self, 'token_base', uint(self.token_base, 32, 'token_base'))
        object.__setattr__(self, 'token_count', uint(self.token_count, 8, 'token_count'))
        if not 1 <= self.token_count <= 128 or self.token_base + self.token_count > 128:
            raise ValueError('invalid attention active token window')
        if type(self.context) is not AttentionContext:
            raise ValueError('invalid attention context type')
        self.context.__post_init__()
        if self.total_keys > self.context.capacity:
            raise ValueError('active append exceeds cache capacity')
        tensors = tuple(v for v in (self.src0, self.src1, self.dst) if v is not None)
        for tensor in tensors:
            if type(tensor) is not AttentionTensor:
                raise ValueError('invalid attention tensor type')
            tensor.__post_init__()
        _disjoint(tuple(t.span for t in tensors))
        if self.operation == AttentionOperation.SOFTMAX:
            if self.src1 is not None or self.src0.shape != self.rectangle or self.dst.shape != self.rectangle:
                raise ValueError('softmax requires score/NONE/probability rectangles')
            return
        if self.src1 is None:
            raise ValueError('attention operation requires three tensor roots')
        if self.operation == AttentionOperation.APPEND:
            rows = self.src0.shape[0]
            expected = ((rows, 512), (rows, 512), self.cache_shape)
        elif self.operation == AttentionOperation.QK:
            rows = self.src0.shape[0]
            expected = ((rows, 2048), self.cache_shape, self.rectangle)
        elif self.operation == AttentionOperation.PV:
            rows = self.dst.shape[0]
            expected = (self.rectangle, self.cache_shape, (rows, 2048))
        else:
            rows = self.src1.shape[0]
            expected = (self.cache_shape, (rows, 2048), (rows, 2048))
        if not 1 <= rows <= 128 or self.token_base + self.token_count > rows:
            raise ValueError('active token window exceeds full rows')
        if tuple(t.shape for t in tensors) != expected:
            raise ValueError('attention tensor role, rank or geometry mismatch')

    @property
    def total_keys(self): return self.context.expected_length + self.token_count

    @property
    def rectangle(self): return (8, self.token_count, self.total_keys)

    @property
    def cache_shape(self): return (2, self.context.capacity, 512)

    @property
    def recipe(self):
        return 0 if self.operation in (AttentionOperation.APPEND, AttentionOperation.FENCE) else ATTENTION_RECIPE

    @property
    def policy_payload(self):
        return (ATTENTION_VERSION | int(self.operation) << 8 | self.token_base << 12 |
                self.token_count << 44 | self.recipe << 52)

    @property
    def record_count(self): return (11, 13, 9, 13, 12)[self.operation]


@dataclass(frozen=True)
class HostAttentionCoreBinding:
    rows: int
    token_base: int
    token_count: int
    capacity: int
    expected_length: int
    query_start: int
    expected_generation: int
    cold: bool
    q_ddr: int
    k_ddr: int
    v_ddr: int
    cache_ddr: int
    score_ddr: int
    probability_ddr: int
    output_ddr: int

    def __post_init__(self):
        for name, width in (('rows', 8), ('token_base', 32), ('token_count', 8),
                            ('capacity', 9), ('expected_length', 9), ('query_start', 9),
                            ('expected_generation', 32)):
            object.__setattr__(self, name, uint(getattr(self, name), width, name))
        for name in ('q_ddr', 'k_ddr', 'v_ddr', 'cache_ddr', 'score_ddr', 'probability_ddr', 'output_ddr'):
            object.__setattr__(self, name, uint(getattr(self, name), 56, name))
        object.__setattr__(self, 'cold', bit(self.cold, 'cold'))
        if not 1 <= self.rows <= 128 or not 1 <= self.token_count <= 128 or self.token_base + self.token_count > self.rows:
            raise ValueError('invalid full tensor or active token window')
        self.context.__post_init__()
        if self.total_keys > self.capacity:
            raise ValueError('active append exceeds cache capacity')
        _disjoint(self.spans)

    @property
    def context(self):
        return AttentionContext(self.capacity, self.expected_length, self.query_start,
                                self.expected_generation, self.cold)

    @property
    def total_keys(self): return self.expected_length + self.token_count

    @property
    def cache_v_ddr(self): return self.cache_ddr + self.capacity * 1024

    @property
    def tensors(self):
        return (
            AttentionTensor(self.q_ddr, (self.rows, 2048)),
            AttentionTensor(self.k_ddr, (self.rows, 512)),
            AttentionTensor(self.v_ddr, (self.rows, 512)),
            AttentionTensor(self.cache_ddr, (2, self.capacity, 512)),
            AttentionTensor(self.score_ddr, (8, self.token_count, self.total_keys)),
            AttentionTensor(self.probability_ddr, (8, self.token_count, self.total_keys)),
            AttentionTensor(self.output_ddr, (self.rows, 2048)),
        )

    @property
    def spans(self): return tuple(t.span for t in self.tensors)

    @property
    def reservations(self):
        """Logical RW regions; score/probability storage stays owner-internal."""
        return tuple(dict(name=name, address=tensor.address, bytes=tensor.span[1],
                          payloadBytes=tensor.payload_bytes, read=True, write=True,
                          internalOnly=name in ('scores', 'probabilities'))
                     for name, tensor in zip(('cache', 'scores', 'probabilities', 'context'), self.tensors[3:]))

    def command_binding(self, operation):
        operation = enum_value(operation, AttentionOperation, 'operation')
        q, k, v, cache, scores, probabilities, output = self.tensors
        roots = ((k, v, cache), (q, cache, scores), (scores, None, probabilities),
                 (probabilities, cache, output), (cache, q, output))[operation]
        return HostAttentionCommandBinding(operation, self.token_base, self.token_count, self.context, *roots)

    @property
    def jobs(self):
        """The two additional real owners; QK/softmax/PV share one owner."""
        return (
            dict(owner='append', tokens=self.token_count, capacity=self.capacity,
                 expectedLength=self.expected_length, expectedGeneration=self.expected_generation,
                 expectedCacheLength=self.expected_length, cacheLength=self.expected_length,
                 queryStart=self.query_start, currentGeneration=self.expected_generation,
                 cold=self.cold, k=self.k_ddr + self.token_base * 1024,
                 v=self.v_ddr + self.token_base * 1024, cache=self.cache_ddr,
                 cacheV=self.cache_v_ddr, activationBf16=True, weightBf16=True, outputBf16=True,
                 writeBytes=self.token_count * 2048),
            dict(owner='attention', queryCount=self.token_count, totalKeys=self.total_keys,
                 queryStart=self.query_start, expectedCacheLength=self.expected_length,
                 cacheLength=self.total_keys, expectedGeneration=self.expected_generation,
                 currentGeneration=self.expected_generation, cold=self.cold,
                 capacity=self.capacity, headDim=256, queryHeads=8, kvHeads=2,
                 q=self.q_ddr + self.token_base * 4096, cacheK=self.cache_ddr,
                 cacheV=self.cache_v_ddr, dst=self.output_ddr + self.token_base * 4096,
                 activationBf16=True, weightBf16=True, outputBf16=True,
                 writeBytes=self.token_count * 4096),
        )


def _envelope(first_index, count, event_wait, event_signal):
    uint(first_index, 24, 'first_index')
    uint(event_wait, 16, 'event_wait'); uint(event_signal, 16, 'event_signal')
    if first_index + count > NULL_INDEX:
        raise ValueError('descriptor index aperture exhausted')
    if event_wait >= 256 or not 0 < event_signal < 256 or event_wait == event_signal:
        raise ValueError('unsupported Host completion event')


def _tensor(records, root, tensor, tail=NULL_INDEX):
    records[root] = tensor_base_record(tensor.address, dtype=TensorDType.BF16,
                                      rank=len(tensor.shape), next_index=root + 1)
    records[root + 1] = shape4_record(tensor.shape + (1,) * (4 - len(tensor.shape)), next_index=root + 2)
    records[root + 2] = stride3_record(tensor.strides, next_index=tail)


def _program_records(binding):
    op = binding.operation
    if op in (AttentionOperation.QK, AttentionOperation.PV):
        n, k = ((binding.total_keys, 256) if op == AttentionOperation.QK else (256, binding.total_keys))
        return [matrix_op_record(m=binding.token_count, n=n, k=k, dataflow=0,
                                 transpose_b=op == AttentionOperation.QK), MatrixAux().to_record()]
    if op in (AttentionOperation.SOFTMAX, AttentionOperation.FENCE):
        return [SfuProgram(_ENVELOPES[op][0], 1 if op == AttentionOperation.SOFTMAX else 2).to_record()]
    return []


def build_host_attention_core_descriptor(binding, *, first_index=0, event_wait=0, event_signal=1):
    if type(binding) is not HostAttentionCommandBinding:
        raise ValueError('expected an attention command binding')
    binding.__post_init__()
    _envelope(first_index, binding.record_count, event_wait, event_signal)
    records, programs = {}, _program_records(binding)
    policy_index = first_index + 3 + len(programs)
    src1 = policy_index + 2 if binding.src1 is not None else NULL_INDEX
    dst = policy_index + 2 + (3 if binding.src1 is not None else 0)
    _tensor(records, first_index, binding.src0, first_index + 3)
    if binding.src1 is not None:
        _tensor(records, src1, binding.src1)
    _tensor(records, dst, binding.dst)
    for offset, record in enumerate(programs, start=3):
        records[first_index + offset] = DescriptorRecord(record.record_type, 0, 0, first_index + offset + 1, record.payload)
    records[policy_index] = DescriptorRecord(RecordType.ATTENTION_POLICY, 0, 0, policy_index + 1, binding.policy_payload)
    records[policy_index + 1] = binding.context.to_record()
    opcode, engine = _ENVELOPES[binding.operation]
    return Command128(opcode, engine, event_wait=event_wait, event_signal=event_signal,
                      src0=first_index, src1=src1, dst=dst), records


def _parse_tensor(chain):
    if [r.record_type for _, r in chain[:3]] != [1, 2, 3]:
        raise ValueError('attention tensor requires a base/shape/stride prefix')
    base, shape, stride = (r.payload for _, r in chain[:3])
    rank = (base >> 60) & 15
    if rank not in (2, 3) or (base >> 48) & 0xFFF != 0x050:
        raise ValueError('native contiguous BF16 rank2/rank3 tensor required')
    dims = tuple((shape >> (18 * index)) & 0x3FFFF for index in range(4))
    if dims[rank:] != (1,) * (4 - rank):
        raise ValueError('unused shape dimensions must be one')
    tensor = AttentionTensor((base & ((1 << 48) - 1)) | (base >> 64) << 48, dims[:rank])
    if stride != sum(value << (24 * index) for index, value in enumerate(tensor.strides)):
        raise ValueError('invalid contiguous element strides')
    return tensor


def parse_host_attention_core_descriptor(command, records):
    if isinstance(command, int): command = Command128.unpack(command)
    command.__post_init__()
    matches = [op for op, envelope in _ENVELOPES.items() if envelope == (command.opcode, command.engine)]
    if command.flags or len(matches) != 1:
        raise ValueError('unsupported attention command envelope')
    op = matches[0]
    _envelope(0, 1, command.event_wait, command.event_signal)
    if (command.src1 == NULL_INDEX) != (op == AttentionOperation.SOFTMAX):
        raise ValueError('only softmax requires a NULL src1')
    chains = [validate_descriptor_chain(root, records) if root != NULL_INDEX else ()
              for root in (command.src0, command.src1, command.dst)]
    extra_types = ([0x10, 0x12] if op in (AttentionOperation.QK, AttentionOperation.PV) else
                   [0x20] if op in (AttentionOperation.SOFTMAX, AttentionOperation.FENCE) else [])
    expected_types = [1, 2, 3] + extra_types + [0x24, 0x26]
    if [r.record_type for _, r in chains[0]] != expected_types:
        raise ValueError('invalid attention source program/policy/context chain')
    if any(chain and [r.record_type for _, r in chain] != [1, 2, 3] for chain in chains[1:]):
        raise ValueError('non-A tensor tails must terminate after stride')
    indices = [index for chain in chains for index, _ in chain]
    if len(indices) != len(set(indices)):
        raise ValueError('attention descriptor chains must have distinct records')
    policy = chains[0][-2][1].payload
    recipe = 0 if op in (AttentionOperation.APPEND, AttentionOperation.FENCE) else ATTENTION_RECIPE
    if policy & 255 != ATTENTION_VERSION or (policy >> 8) & 15 != int(op) or (policy >> 52) & 255 != recipe or policy >> 60:
        raise ValueError('unsupported attention policy version/operation/recipe/reserved bits')
    result = HostAttentionCommandBinding(op, (policy >> 12) & 0xFFFFFFFF, (policy >> 44) & 255,
                                        AttentionContext.from_record(chains[0][-1][1]),
                                        *(_parse_tensor(chain) if chain else None for chain in chains))
    if len(indices) != result.record_count:
        raise ValueError('attention descriptor record inventory mismatch')
    if [r.payload for _, r in chains[0][3:-2]] != [r.payload for r in _program_records(result)]:
        raise ValueError('unsupported Matrix/SFU BF16 numerical policy')
    return result


def _validate_bindings(projections, norms, ropes, core):
    if type(core) is not HostAttentionCoreBinding:
        raise ValueError('expected an attention-core binding')
    core.__post_init__()
    commands, records = build_host_qkv_rope_commands(projections, norms, ropes)
    if (core.rows, core.token_base, core.token_count) != (projections[0].rows, projections[0].token_base, projections[0].token_count):
        raise ValueError('core window must match actual producer window')
    if (core.q_ddr, core.k_ddr, core.v_ddr) != (ropes[0].output_ddr, ropes[1].output_ddr, projections[2].output_ddr):
        raise ValueError('core must consume actual Q RoPE, K RoPE and V projection outputs')
    if core.query_start != ropes[0].position_base or core.query_start != ropes[1].position_base:
        raise ValueError('queryStart and expectedLength must equal the RoPE absolute position')
    external = ((projections[0].spans[0],) + tuple(p.spans[1] for p in projections) +
                tuple(n.input_spans[1] for n in norms) + (ropes[0].input_spans[1],))
    produced = tuple(p.spans[2] for p in projections) + tuple(span for b in (*norms, *ropes) for span in b.output_spans)
    # Q/K/V are deliberate producer-consumer edges and appear once in produced.
    _disjoint(external + produced + core.spans[3:])
    return commands, records


def build_host_attention_core_commands(projections, norms, ropes, core):
    """Build the actual 12-command topology, with strict events 0 -> ... -> 12."""
    commands, records = _validate_bindings(projections, norms, ropes, core)
    for op in AttentionOperation:
        command, extra = build_host_attention_core_descriptor(core.command_binding(op), first_index=len(records),
                                                             event_wait=len(commands), event_signal=len(commands) + 1)
        commands.append(command); records.update(extra)
    if len(commands) != CHAIN_COMMANDS or len(records) != CHAIN_RECORDS:
        raise ValueError('attention chain inventory drift')
    return commands, records


def validate_host_attention_core_commands(commands, records):
    """Parse an untrusted full stream and validate topology across all producers."""
    if len(commands) != CHAIN_COMMANDS:
        raise ValueError('expected exactly twelve attention commands')
    commands = [Command128.unpack(c) if isinstance(c, int) else c for c in commands]
    for index, command in enumerate(commands):
        command.__post_init__()
        if (command.event_wait, command.event_signal) != (index, index + 1):
            raise ValueError('attention commands must carry strict sequential event dependencies')
    projections = tuple(parse_host_qkv_descriptor(c, records) for c in commands[:3])
    norms = tuple(parse_host_qk_rope_descriptor(c, records) for c in commands[3:5])
    ropes = tuple(parse_host_qk_rope_descriptor(c, records) for c in commands[5:7])
    steps = tuple(parse_host_attention_core_descriptor(c, records) for c in commands[7:])
    if tuple(s.operation for s in steps) != tuple(AttentionOperation):
        raise ValueError('append/QK/softmax/PV/fence phase ordering mismatch')
    append, qk, softmax, pv, fence = steps
    ctx = append.context
    core = HostAttentionCoreBinding(append.src0.shape[0], append.token_base, append.token_count,
                                   ctx.capacity, ctx.expected_length, ctx.query_start, ctx.expected_generation, ctx.cold,
                                   qk.src0.address, append.src0.address, append.src1.address, append.dst.address,
                                   qk.dst.address, softmax.dst.address, pv.dst.address)
    _validate_bindings(projections, norms, ropes, core)
    if steps != tuple(core.command_binding(op) for op in AttentionOperation):
        raise ValueError('attention phases disagree on context, tensor rectangles or actual bindings')
    used = []
    for command in commands:
        for root in (command.src0, command.src1, command.dst):
            if root != NULL_INDEX:
                used.extend(i for i, _ in validate_descriptor_chain(root, records))
    # The Q Norm gate prefix is a fourth root in its auxiliary record.
    q_norm_chain = validate_descriptor_chain(commands[3].src0, records)
    gate_root = q_norm_chain[-1][1].payload & 0xFFFFFF
    used.extend(i for i, _ in validate_descriptor_chain(gate_root, records))
    if len(used) != CHAIN_RECORDS or len(set(used)) != CHAIN_RECORDS:
        raise ValueError('full stream requires 172 distinct descriptor records')
    return core


def validate_carried_attention_launch(previous, current):
    """Validate the committed cache/context, allowing expired scratch reuse.

    A successful preceding fence ends the lifetime of its Q/K/V and virtual
    score/probability scratch. Cache and the latest context stay protected until
    a later accepted fence replaces that checkpoint. No memory is initialized
    or copied here; the caller must establish the actual preceding commit.
    """
    previous.__post_init__(); current.__post_init__()
    if current.cold or (current.cache_ddr, current.capacity) != (previous.cache_ddr, previous.capacity):
        raise ValueError('carried launch must reuse exactly the previous cache allocation')
    if current.expected_length != previous.total_keys or current.expected_generation != previous.expected_generation + 1:
        raise ValueError('carried launch must use the committed length and next generation')
    # Current cache is the exact shared allocation checked above. Everything
    # else must avoid it and the previous committed context, matching Host.
    _disjoint((previous.spans[3], previous.spans[-1]) + current.spans[:3] + current.spans[4:])
    return current


def validate_carried_attention_commands(previous_commands, previous_records, current_commands, current_records):
    """Check full streams, including persistent parameter identity across fences.

    The caller must supply the actually committed preceding stream; serialization
    cannot establish that its owners succeeded or its terminal fence committed.
    """
    previous = validate_host_attention_core_commands(previous_commands, previous_records)
    current = validate_host_attention_core_commands(current_commands, current_records)
    validate_carried_attention_launch(previous, current)

    def inventory(commands, records, core):
        projections = tuple(parse_host_qkv_descriptor(c, records) for c in commands[:3])
        norms = tuple(parse_host_qk_rope_descriptor(c, records) for c in commands[3:5])
        ropes = tuple(parse_host_qk_rope_descriptor(c, records) for c in commands[5:7])
        parameters = tuple(p.spans[1] for p in projections) + tuple(n.input_spans[1] for n in norms) + (ropes[0].input_spans[1],)
        outputs = (tuple(p.spans[2] for p in projections) +
                   tuple(span for binding in (*norms, *ropes) for span in binding.output_spans) + core.spans[4:])
        return parameters, projections[0].spans[0], outputs

    old_parameters, _, _ = inventory(previous_commands, previous_records, previous)
    new_parameters, new_hidden, new_outputs = inventory(current_commands, current_records, current)
    if old_parameters != new_parameters:
        raise ValueError('carried launch must preserve full Wq/Wk/Wv/gammaQ/gammaK/trig identities')
    # Per-stream checks protect the unchanged typed parameters. Scratch from
    # the preceding committed launch may be reused; its context remains live.
    _disjoint((previous.spans[-1], new_hidden) + new_outputs)
    return current
