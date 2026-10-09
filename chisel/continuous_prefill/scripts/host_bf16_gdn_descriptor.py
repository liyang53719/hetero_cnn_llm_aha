"""Public, default-off Host GDN Dense-QKV and Conv4 command bindings."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from heteronpu.abi_validation import uint, bit
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import (DescriptorRecord, RecordType, MatrixAux, SfuProgram,
    NULL_INDEX, TensorDType, validate_descriptor_chain)
from heteronpu.gemmini_descriptor_v2 import tensor_base_record, shape4_record, stride3_record, matrix_op_record

CHANNELS, TAPS, HIDDEN = 6144, 4, 1024
DENSE_RECORDS, CONV_RECORDS = 12, 18


def _ranges(spans):
    for i, (a, size) in enumerate(spans):
        uint(a, 56, 'DDR address')
        if a % 64 or a + size > 1 << 56:
            raise ValueError('unaligned or overflowing DDR span')
        if any(a < b + n and b < a + size for b, n in spans[:i]):
            raise ValueError('physical tensor alias')


@dataclass(frozen=True)
class HostGdnDenseBinding:
    tokens: int
    activation_ddr: int
    weight_ddr: int
    output_ddr: int

    def __post_init__(self):
        uint(self.tokens, 8, 'tokens')
        if not 1 <= self.tokens <= 128: raise ValueError('tokens outside 1..128')
        _ranges(self.spans)

    @property
    def spans(self):
        return ((self.activation_ddr, self.tokens * HIDDEN * 2),
                (self.weight_ddr, HIDDEN * CHANNELS * 2),
                (self.output_ddr, self.tokens * CHANNELS * 2))


@dataclass(frozen=True)
class HostGdnConvBinding:
    tokens: int
    activation_ddr: int
    weight_ddr: int
    output_ddr: int
    history_input_ddr: int
    history_output_ddr: int
    cold: bool
    expected_generation: int = 0
    context: int = 0

    def __post_init__(self):
        uint(self.tokens, 8, 'tokens'); uint(self.expected_generation, 32, 'generation')
        bit(self.cold, 'cold'); uint(self.context, 8, 'context')
        if not 1 <= self.tokens <= 128 or self.context != 0 or self.expected_generation == 0xffffffff:
            raise ValueError('unsupported tokens/context')
        if self.cold and self.expected_generation != 0:
            raise ValueError('cold command requires generation zero')
        _ranges(self.spans)

    @property
    def spans(self):
        return ((self.activation_ddr, self.tokens * CHANNELS * 2),
                (self.weight_ddr, CHANNELS * TAPS * 2),
                (self.output_ddr, self.tokens * CHANNELS * 2),
                (self.history_input_ddr, CHANNELS * TAPS * 2),
                (self.history_output_ddr, CHANNELS * TAPS * 2))


def _envelope(first_index, count, event_wait, event_signal):
    uint(first_index, 24, 'first_index'); uint(event_wait, 16, 'event_wait'); uint(event_signal, 16, 'event_signal')
    if first_index + count > NULL_INDEX or event_wait >= 256 or not 0 < event_signal < 256 or event_wait == event_signal:
        raise ValueError('unsupported descriptor aperture or event')


def _tensor(records, root, address, rows, columns, tail=NULL_INDEX):
    records[root] = tensor_base_record(address, dtype=TensorDType.BF16, rank=2, next_index=root + 1)
    records[root + 1] = shape4_record((rows, columns, 1, 1), next_index=root + 2)
    records[root + 2] = stride3_record((columns, 1, 1), next_index=tail)


def build_host_gdn_descriptor(binding, *, first_index=0, event_wait=0, event_signal=1):
    binding.__post_init__()
    dense = type(binding) is HostGdnDenseBinding
    if not dense and type(binding) is not HostGdnConvBinding: raise ValueError('unsupported GDN binding')
    _envelope(first_index, DENSE_RECORDS if dense else CONV_RECORDS, event_wait, event_signal)
    i, r = first_index, {}
    _tensor(r, i, binding.activation_ddr, binding.tokens, HIDDEN if dense else CHANNELS, i + 3)
    _tensor(r, i + 6, binding.weight_ddr, HIDDEN if dense else CHANNELS, CHANNELS if dense else TAPS)
    _tensor(r, i + 9, binding.output_ddr, binding.tokens, CHANNELS)
    if dense:
        r[i + 3] = matrix_op_record(m=binding.tokens, n=CHANNELS, k=HIDDEN, dataflow=0, next_index=i + 4)
        r[i + 4] = MatrixAux().to_record(next_index=i + 5)
        r[i + 5] = DescriptorRecord(RecordType.GDN_POLICY, 0, 0, NULL_INDEX, 0x201)
    else:
        _tensor(r, i + 12, binding.history_input_ddr, CHANNELS, TAPS)
        _tensor(r, i + 15, binding.history_output_ddr, CHANNELS, TAPS)
        r[i + 3] = SfuProgram(0x30, 2, vector_lanes=1).to_record(next_index=i + 4)
        payload = 0x101 | binding.context << 16 | int(binding.cold) << 24 | binding.expected_generation << 32
        r[i + 4] = DescriptorRecord(RecordType.GDN_POLICY, 0, 0, i + 5, payload)
        r[i + 5] = DescriptorRecord(RecordType.GDN_STATE_ROOTS, 0, 0, NULL_INDEX, (i + 12) | (i + 15) << 24)
    command = Command128(Opcode.MATRIX_GEMM if dense else Opcode.SFU_VECTOR, Engine.MATRIX if dense else Engine.SFU_CGRA,
                         event_wait=event_wait, event_signal=event_signal, src0=i, src1=i + 6, dst=i + 9)
    return command, r


def parse_host_gdn_descriptor(command, records):
    if isinstance(command, int): command = Command128.unpack(command)
    dense = command.opcode == Opcode.MATRIX_GEMM and command.engine == Engine.MATRIX
    conv = command.opcode == Opcode.SFU_VECTOR and command.engine == Engine.SFU_CGRA
    if command.flags or not (dense or conv): raise ValueError('unsupported GDN command envelope')
    _envelope(0, 1, command.event_wait, command.event_signal)
    roots = [command.src0, command.src1, command.dst]
    chains = [validate_descriptor_chain(root, records) for root in roots]
    types = [1, 2, 3, 0x10, 0x12, 0x21] if dense else [1, 2, 3, 0x20, 0x21, 0x22]
    if [int(r.record_type) for _, r in chains[0]] != types:
        raise ValueError('invalid source policy chain')
    if not dense:
        state = chains[0][5][1].payload
        if state >> 48: raise ValueError('reserved state-root payload')
        roots += [state & 0xffffff, (state >> 24) & 0xffffff]
        chains += [validate_descriptor_chain(root, records) for root in roots[3:]]
    indices = [i for chain in chains for i, _ in chain]
    count = DENSE_RECORDS if dense else CONV_RECORDS
    if len(indices) != count or len(set(indices)) != count:
        raise ValueError('GDN prefix and policy indices must be distinct')
    addresses, shapes = [], []
    for slot, chain in enumerate(chains):
        if slot and [int(r.record_type) for _, r in chain] != [1, 2, 3]: raise ValueError('non-A tail must be NULL')
        if any(r.subtype or r.flags for _, r in chain): raise ValueError('reserved common header')
        base, shape, stride = [r.payload for _, r in chain[:3]]
        if (base >> 48) & 0xffff != 0x2050: raise ValueError('native BF16 rank2 required')
        addresses.append((base & ((1 << 48) - 1)) | (base >> 64) << 48)
        dims = tuple((shape >> (18 * i)) & 0x3ffff for i in range(4))
        if dims[2:] != (1, 1) or stride != dims[1] | 1 << 24 | 1 << 48: raise ValueError('contiguous shape/stride required')
        shapes.append(dims[:2])
    if dense:
        if chains[0][5][1].payload != 0x201: raise ValueError('Dense policy must be exactly 0x201')
        result = HostGdnDenseBinding(shapes[0][0], *addresses)
        if shapes != [(result.tokens, HIDDEN), (HIDDEN, CHANNELS), (result.tokens, CHANNELS)]: raise ValueError('Dense geometry')
        if chains[0][3][1].payload != result.tokens | CHANNELS << 16 | HIDDEN << 32 or chains[0][4][1].payload != MatrixAux().payload():
            raise ValueError('Dense Matrix policy')
    else:
        policy = chains[0][4][1].payload
        if policy & 0xffff != 0x101 or (policy >> 25) & 0x7f or policy >> 64: raise ValueError('Conv policy reserved/version/operation')
        result = HostGdnConvBinding(shapes[0][0], *addresses, bool((policy >> 24) & 1), (policy >> 32) & 0xffffffff, (policy >> 16) & 255)
        if shapes != [(result.tokens, CHANNELS), (CHANNELS, TAPS), (result.tokens, CHANNELS), (CHANNELS, TAPS), (CHANNELS, TAPS)]:
            raise ValueError('Conv geometry')
        if chains[0][3][1].payload != SfuProgram(0x30, 2, vector_lanes=1).payload(): raise ValueError('Conv SFU policy')
    return result


def build_gdn_commands(bindings):
    """Validate a real Dense0→cold Conv0→Dense1→carried Conv1 dependency chain."""
    if len(bindings) != 4 or [type(b) for b in bindings] != [HostGdnDenseBinding, HostGdnConvBinding] * 2:
        raise ValueError('expected four alternating Dense/Conv commands')
    d0, c0, d1, c1 = bindings
    if any(b.tokens != 1 for b in bindings) or not c0.cold or c1.cold or c0.expected_generation != 0 or c1.expected_generation != 1:
        raise ValueError('expected consecutive M1 cold/carried generations 0/1')
    if c0.activation_ddr != d0.output_ddr or c1.activation_ddr != d1.output_ddr or c1.history_input_ddr != c0.history_output_ddr:
        raise ValueError('broken actual DMA dependency')
    if d0.weight_ddr != d1.weight_ddr or c0.weight_ddr != c1.weight_ddr:
        raise ValueError('same checkpoint weights required')
    spans = [*d0.spans[:2], d1.spans[0], c0.spans[1], c0.spans[3], d0.spans[2], c0.spans[2], c0.spans[4], d1.spans[2], c1.spans[2], c1.spans[4]]
    _ranges(spans)
    commands, records = [], {}
    for pc, binding in enumerate(bindings):
        command, chain = build_host_gdn_descriptor(binding, first_index=len(records), event_wait=pc, event_signal=pc + 1)
        commands.append(command); records.update(chain)
    return commands, records
