"""Public Command128, default-off Host Q/K/V PROJECTION_ONLY descriptors.

The three roles fan out from one normalized activation. Completion events order
execution; they do not create a Q-to-K or K-to-V tensor dependency.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from heteronpu.abi_validation import uint
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import DescriptorRecord, MatrixAux, NULL_INDEX, TensorDType, validate_descriptor_chain
from heteronpu.gemmini_descriptor_v2 import tensor_base_record, shape4_record, stride3_record, matrix_op_record

ROLES = ('q', 'k', 'v')
COLUMNS = (4096, 512, 512)
RECORDS_PER_COMMAND = 21


@dataclass(frozen=True)
class HostQkvBinding:
    role: int
    rows: int
    token_base: int
    token_count: int
    activation_ddr: int
    weight_ddr: int
    output_ddr: int

    def __post_init__(self):
        for name, width in (('role', 2), ('rows', 8), ('token_base', 32), ('token_count', 8),
                            ('activation_ddr', 56), ('weight_ddr', 56), ('output_ddr', 56)):
            object.__setattr__(self, name, uint(getattr(self, name), width, name))
        if self.role > 2 or not 1 <= self.rows <= 128 or not 1 <= self.token_count <= 128 or self.token_base + self.token_count > self.rows:
            raise ValueError('invalid projection role/full tensor/token window')
        spans = self.spans
        for address, size in spans:
            if address % 64 or address + size > 1 << 56:
                raise ValueError('unaligned or overflowing full DDR tensor')
        out, size = spans[2]
        if any(address < out + size and out < address + length for address, length in spans[:2]):
            raise ValueError('output overlaps full input tensor')

    @property
    def n(self):
        return COLUMNS[self.role]

    @property
    def spans(self):
        return ((self.activation_ddr, self.rows * 2048),
                (self.weight_ddr, 1024 * self.n * 2),
                (self.output_ddr, self.rows * self.n * 2))

    @property
    def job(self):
        return dict(m=self.token_count, n=self.n, k=1024,
                    a=self.activation_ddr + self.token_base * 2048, b=self.weight_ddr,
                    dst=self.output_ddr + self.token_base * self.n * 2,
                    writeBytes=self.token_count * self.n * 2,
                    activationBf16=True, weightBf16=True, outputBf16=True)


def validate_qkv_bindings(bindings):
    """Reject physical aliases across the complete fan-out, including guards.

    This stricter fixture preflight is independent of Host's active-publication
    check. All three D allocations and every W must be physically distinct.
    """
    if len(bindings) != 3 or [b.role for b in bindings] != [0, 1, 2]:
        raise ValueError('expected exactly Q, K, V in order')
    a = bindings[0]
    if any((b.rows, b.token_base, b.token_count, b.activation_ddr) !=
           (a.rows, a.token_base, a.token_count, a.activation_ddr) for b in bindings):
        raise ValueError('Q/K/V must fan out from the same activation window')
    spans = [a.spans[0]] + [b.spans[1] for b in bindings] + [b.spans[2] for b in bindings]
    for index, (address, size) in enumerate(spans):
        for other, length in spans[:index]:
            if address < other + length and other < address + size:
                raise ValueError('physical QKV tensor alias')
    return tuple(bindings)


def build_host_qkv_descriptor(binding: HostQkvBinding, *, first_index=0, event_wait=0, event_signal=1):
    binding.__post_init__()
    first_index = uint(first_index, 24, 'first_index')
    event_wait = uint(event_wait, 16, 'event_wait')
    event_signal = uint(event_signal, 16, 'event_signal')
    if first_index + RECORDS_PER_COMMAND > NULL_INDEX:
        raise ValueError('descriptor index aperture exhausted')
    if event_wait >= 256 or not 0 < event_signal < 256 or event_signal == event_wait:
        raise ValueError('unsupported Host completion event')
    records = {}
    for slot, offset in enumerate((0, 15, 18)):
        root = first_index + offset
        rows, cols = ((binding.rows, 1024), (1024, binding.n), (binding.rows, binding.n))[slot]
        address = (binding.activation_ddr, binding.weight_ddr, binding.output_ddr)[slot]
        records[root] = tensor_base_record(address, dtype=TensorDType.BF16, rank=2, next_index=root + 1)
        records[root + 1] = shape4_record((rows, cols, 1, 1), next_index=root + 2)
        records[root + 2] = stride3_record((cols, 1, 1), next_index=root + 3 if slot == 0 else NULL_INDEX)
    records[first_index + 3] = matrix_op_record(m=binding.rows, n=binding.n, k=1024, dataflow=0, next_index=first_index + 4)
    records[first_index + 4] = MatrixAux().to_record(next_index=first_index + 5)
    policy = 2 | binding.role << 8 | 3 << 10 | binding.token_base << 12 | binding.token_count << 44
    records[first_index + 5] = DescriptorRecord(0x1a, 0, 0, first_index + 6, policy)
    for kind in range(9):
        index = first_index + 6 + kind
        records[index] = DescriptorRecord(0x1b, 0, 0, index + 1 if kind < 8 else NULL_INDEX, kind << 56)
    command = Command128(Opcode.MATRIX_GEMM, Engine.MATRIX, event_wait=event_wait, event_signal=event_signal,
                         src0=first_index, src1=first_index + 15, dst=first_index + 18)
    return command, records


def parse_host_qkv_descriptor(command, records):
    if isinstance(command, int):
        command = Command128.unpack(command)
    if command.opcode != Opcode.MATRIX_GEMM or command.engine != Engine.MATRIX or command.flags:
        raise ValueError('unsupported public command envelope')
    if command.event_wait >= 256 or not 0 < command.event_signal < 256 or command.event_signal == command.event_wait:
        raise ValueError('unsupported Host completion event')
    chains = [validate_descriptor_chain(root, records) for root in (command.src0, command.src1, command.dst)]
    indices = [i for chain in chains for i, _ in chain]
    if len(indices) != RECORDS_PER_COMMAND or len(set(indices)) != RECORDS_PER_COMMAND:
        raise ValueError('chains must have 21 distinct records')
    addresses, shapes = [], []
    for slot, chain in enumerate(chains):
        expected = [1, 2, 3] + ([0x10, 0x12, 0x1a] + [0x1b] * 9 if slot == 0 else [])
        if [int(r.record_type) for _, r in chain] != expected or any(r.subtype or r.flags for _, r in chain):
            raise ValueError('record order or reserved common header')
        base, shape, stride = [r.payload for _, r in chain[:3]]
        if (base >> 48) & 0xffff != 0x2050:
            raise ValueError('not native contiguous BF16 rank2')
        addresses.append((base & ((1 << 48) - 1)) | (base >> 64) << 48)
        dims = tuple((shape >> (18 * i)) & 0x3ffff for i in range(4))
        if dims[2:] != (1, 1) or stride != dims[1] | 1 << 24 | 1 << 48:
            raise ValueError('invalid shape or element stride')
        shapes.append(dims[:2])
    policy = chains[0][5][1].payload
    if policy & 0xff != 2 or (policy >> 8) & 3 > 2 or (policy >> 10) & 3 != 3 or policy >> 52:
        raise ValueError('unsupported projection owner-managed version/mode/norm policy')
    for kind, (_, record) in enumerate(chains[0][6:]):
        if record.payload != kind << 56:
            raise ValueError('owner-managed zero address sentinel required')
    result = HostQkvBinding((policy >> 8) & 3, shapes[0][0], (policy >> 12) & 0xffffffff, (policy >> 44) & 0xff, *addresses)
    if shapes != [(result.rows, 1024), (1024, result.n), (result.rows, result.n)]:
        raise ValueError('role/shape mismatch')
    if chains[0][3][1].payload != result.rows | result.n << 16 | 1024 << 32 or chains[0][4][1].payload != MatrixAux().payload():
        raise ValueError('unsupported Matrix policy')
    return result


def build_qkv_commands(bindings):
    bindings = validate_qkv_bindings(bindings)
    commands, records = [], {}
    for index, binding in enumerate(bindings):
        command, chain = build_host_qkv_descriptor(binding, first_index=len(records), event_wait=index, event_signal=index + 1)
        commands.append(command)
        records.update(chain)
    return commands, records
