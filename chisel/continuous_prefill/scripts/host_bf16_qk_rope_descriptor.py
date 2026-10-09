"""Public Host BF16 QK Norm256 / partial64 RoPE descriptors and strict preflight.

Ordinary SFU_RMSNORM(0x32)/SFU_ROPE(0x34), engine3, flags0. A's tensor prefix
continues SFU_PROGRAM(0x20) -> ATTENTION_POLICY(0x24) -> ATTENTION_AUX(0x25).
Policy payload: version[7:0]=1, role[9:8]=Q0/K1, mode[11:10]=Norm0/RoPE1,
tokenBase[43:12], tokenCount[51:44], recipe[59:52]=C1/B1, reserved[71:60]=0.
Aux payload: gateRoot[23:0] (Q Norm only; otherwise NULL), positionBase[55:24]
(Norm requires zero), reserved[71:56]=0. positionBase is the absolute position
of the FIRST ACTIVE token, never positionBase+tokenBase. All tensor strides
are ELEMENT strides and rank2 trailing shape dimensions are both one.

Q Norm has 15 distinct records; all other SFU commands have 12. The optional
7-command helper combines the existing 63-record QKV projection with 51 SFU
records, including a separate contiguous Q gate output. No numeric execution
or Host permission/publication completion is implied by serialization.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from heteronpu.abi_validation import uint
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import (
    DescriptorRecord, RecordType, SfuProgram, NULL_INDEX, TensorDType,
    validate_descriptor_chain,
)
from heteronpu.gemmini_descriptor_v2 import tensor_base_record, shape4_record, stride3_record
from host_bf16_qkv_descriptor import build_qkv_commands, validate_qkv_bindings

NORM_Q_RECORDS, OTHER_SFU_RECORDS, CHAIN_RECORDS = 15, 12, 114


def _window(value):
    for name, width in (('role', 2), ('rows', 8), ('token_base', 32), ('token_count', 8)):
        object.__setattr__(value, name, uint(getattr(value, name), width, name))
    if value.role > 1 or not 1 <= value.rows <= 128 or not 1 <= value.token_count <= 128 or value.token_base + value.token_count > value.rows:
        raise ValueError('invalid Q/K role, full tensor or active token window')


def _spans(inputs, outputs):
    for address, size in inputs + outputs:
        uint(address, 56, 'DDR address')
        if address % 64 or address + size > 1 << 56:
            raise ValueError('unaligned or overflowing full DDR tensor')
    for index, (address, size) in enumerate(outputs):
        if any(address < other + length and other < address + size
               for other, length in inputs + outputs[:index]):
            raise ValueError('output overlaps full input or other output tensor')


@dataclass(frozen=True)
class HostQkNormBinding:
    role: int
    rows: int
    token_base: int
    token_count: int
    input_ddr: int
    weight_ddr: int
    output_ddr: int
    gate_output_ddr: int = 0

    def __post_init__(self):
        _window(self)
        uint(self.gate_output_ddr, 56, 'gate_output_ddr')
        if self.role == 1 and self.gate_output_ddr:
            raise ValueError('K Norm must not bind a gate output')
        _spans(self.input_spans, self.output_spans)

    @property
    def n(self): return 2048 if self.role == 0 else 512

    @property
    def input_columns(self): return 4096 if self.role == 0 else 512

    @property
    def record_count(self): return NORM_Q_RECORDS if self.role == 0 else OTHER_SFU_RECORDS

    @property
    def input_spans(self):
        return ((self.input_ddr, self.rows * self.input_columns * 2), (self.weight_ddr, 512))

    @property
    def output_spans(self):
        return ((self.output_ddr, self.rows * self.n * 2),) + (
            ((self.gate_output_ddr, self.rows * self.n * 2),) if self.role == 0 else ())

    @property
    def job(self):
        return dict(tokens=self.token_count, role=self.role, headDim=256, policy=0xC1,
                    epsilon=0x358637BD, input=self.input_ddr + self.token_base * self.input_columns * 2,
                    weight=self.weight_ddr, output=self.output_ddr + self.token_base * self.n * 2,
                    gateOutput=self.gate_output_ddr + self.token_base * self.n * 2 if self.role == 0 else 0,
                    writeBytes=self.token_count * self.n * 2 * (2 if self.role == 0 else 1))


@dataclass(frozen=True)
class HostPartialRopeBinding:
    role: int
    rows: int
    token_base: int
    token_count: int
    input_ddr: int
    trig_ddr: int
    output_ddr: int
    trig_tokens: int
    position_base: int = 0

    def __post_init__(self):
        _window(self)
        object.__setattr__(self, 'trig_tokens', uint(self.trig_tokens, 18, 'trig_tokens'))
        object.__setattr__(self, 'position_base', uint(self.position_base, 32, 'position_base'))
        if self.trig_tokens == 0 or self.position_base + self.token_count > self.trig_tokens:
            raise ValueError('absolute active positions exceed trig table')
        _spans(self.input_spans, self.output_spans)

    @property
    def n(self): return 2048 if self.role == 0 else 512

    @property
    def record_count(self): return OTHER_SFU_RECORDS

    @property
    def input_spans(self):
        return ((self.input_ddr, self.rows * self.n * 2), (self.trig_ddr, self.trig_tokens * 128))

    @property
    def output_spans(self): return ((self.output_ddr, self.rows * self.n * 2),)

    @property
    def job(self):
        return dict(tokens=self.token_count, heads=8 if self.role == 0 else 2,
                    headDim=256, rotaryDim=64, policy=0xB1,
                    input=self.input_ddr + self.token_base * self.n * 2,
                    trig=self.trig_ddr, output=self.output_ddr + self.token_base * self.n * 2,
                    positionBase=self.position_base, trigTokens=self.trig_tokens,
                    writeBytes=self.token_count * self.n * 2)


def _envelope(first_index, count, event_wait, event_signal):
    uint(first_index, 24, 'first_index')
    uint(event_wait, 16, 'event_wait'); uint(event_signal, 16, 'event_signal')
    if first_index + count > NULL_INDEX:
        raise ValueError('descriptor index aperture exhausted')
    if event_wait >= 256 or not 0 < event_signal < 256 or event_wait == event_signal:
        raise ValueError('unsupported Host completion event')


def _tensor(records, root, address, rows, columns, tail=NULL_INDEX):
    records[root] = tensor_base_record(address, dtype=TensorDType.BF16, rank=2, next_index=root + 1)
    records[root + 1] = shape4_record((rows, columns, 1, 1), next_index=root + 2)
    records[root + 2] = stride3_record((columns, 1, 1), next_index=tail)


def build_host_qk_rope_descriptor(binding, *, first_index=0, event_wait=0, event_signal=1):
    if type(binding) not in (HostQkNormBinding, HostPartialRopeBinding):
        raise ValueError('unsupported attention binding type')
    binding.__post_init__()
    _envelope(first_index, binding.record_count, event_wait, event_signal)
    norm = type(binding) is HostQkNormBinding
    opcode = Opcode.SFU_RMSNORM if norm else Opcode.SFU_ROPE
    i, records = first_index, {}
    _tensor(records, i, binding.input_ddr, binding.rows, binding.input_columns if norm else binding.n, i + 3)
    _tensor(records, i + 6, binding.weight_ddr if norm else binding.trig_ddr,
            1 if norm else binding.trig_tokens, 256 if norm else 64)
    _tensor(records, i + 9, binding.output_ddr, binding.rows, binding.n)
    gate_root = i + 12 if norm and binding.role == 0 else NULL_INDEX
    if gate_root != NULL_INDEX:
        _tensor(records, gate_root, binding.gate_output_ddr, binding.rows, binding.n)
    records[i + 3] = SfuProgram(opcode, 2).to_record(next_index=i + 4)
    policy = (1 | binding.role << 8 | int(not norm) << 10 | binding.token_base << 12 |
              binding.token_count << 44 | (0xC1 if norm else 0xB1) << 52)
    records[i + 4] = DescriptorRecord(RecordType.ATTENTION_POLICY, 0, 0, i + 5, policy)
    aux = gate_root | (0 if norm else binding.position_base) << 24
    records[i + 5] = DescriptorRecord(RecordType.ATTENTION_AUX, 0, 0, NULL_INDEX, aux)
    return Command128(opcode, Engine.SFU_CGRA, event_wait=event_wait, event_signal=event_signal,
                      src0=i, src1=i + 6, dst=i + 9), records


def parse_host_qk_rope_descriptor(command, records):
    if isinstance(command, int): command = Command128.unpack(command)
    command.__post_init__()
    if command.flags or command.engine != Engine.SFU_CGRA or command.opcode not in (Opcode.SFU_RMSNORM, Opcode.SFU_ROPE):
        raise ValueError('unsupported attention command envelope')
    _envelope(0, 1, command.event_wait, command.event_signal)
    chains = [validate_descriptor_chain(root, records) for root in (command.src0, command.src1, command.dst)]
    if [int(r.record_type) for _, r in chains[0]] != [1, 2, 3, 0x20, 0x24, 0x25]:
        raise ValueError('invalid attention source policy chain')
    norm = command.opcode == Opcode.SFU_RMSNORM
    policy, aux = chains[0][4][1].payload, chains[0][5][1].payload
    role, mode = (policy >> 8) & 3, (policy >> 10) & 3
    if policy & 255 != 1 or role > 1 or mode != int(not norm) or (policy >> 52) & 255 != (0xC1 if norm else 0xB1) or policy >> 60:
        raise ValueError('unsupported attention version/role/mode/recipe/reserved bits')
    gate_root, position = aux & 0xFFFFFF, (aux >> 24) & 0xFFFFFFFF
    if aux >> 56 or (norm and position != 0):
        raise ValueError('attention auxiliary reserved bits or Norm position')
    if norm and role == 0:
        if gate_root == NULL_INDEX: raise ValueError('Q Norm requires gate tensor root')
        chains.append(validate_descriptor_chain(gate_root, records))
    elif gate_root != NULL_INDEX:
        raise ValueError('only Q Norm may bind a gate tensor root')
    indices = [index for chain in chains for index, _ in chain]
    count = NORM_Q_RECORDS if norm and role == 0 else OTHER_SFU_RECORDS
    if len(indices) != count or len(set(indices)) != count:
        raise ValueError('attention prefixes/policy chains must be distinct and exact length')
    addresses, shapes = [], []
    for slot, chain in enumerate(chains):
        if slot and [int(r.record_type) for _, r in chain] != [1, 2, 3]:
            raise ValueError('non-A tensor tail must be NULL')
        base, shape, stride = (record.payload for _, record in chain[:3])
        if (base >> 48) & 0xFFFF != 0x2050:
            raise ValueError('native contiguous BF16 rank2 required')
        dims = tuple((shape >> (18 * index)) & 0x3FFFF for index in range(4))
        if dims[2:] != (1, 1) or stride != (dims[1] | 1 << 24 | 1 << 48):
            raise ValueError('invalid shape or element stride')
        addresses.append((base & ((1 << 48) - 1)) | (base >> 64) << 48)
        shapes.append(dims[:2])
    common = (role, shapes[0][0], (policy >> 12) & 0xFFFFFFFF, (policy >> 44) & 255, *addresses[:3])
    result = (HostQkNormBinding(*common, gate_output_ddr=addresses[3] if role == 0 else 0) if norm else
              HostPartialRopeBinding(*common, trig_tokens=shapes[1][0], position_base=position))
    expected = ([(result.rows, result.input_columns), (1, 256), (result.rows, result.n)] +
                ([(result.rows, result.n)] if role == 0 else []) if norm else
                [(result.rows, result.n), (result.trig_tokens, 64), (result.rows, result.n)])
    if shapes != expected:
        raise ValueError('attention tensor role/geometry mismatch')
    if chains[0][3][1].payload != SfuProgram(command.opcode, 2).payload():
        raise ValueError('unsupported BF16 SFU program')
    return result


def build_host_qkv_rope_commands(projections, norms, ropes):
    """Seven real dependencies, 114 records, events 0->1->...->7.

    Performs full-allocation cross-command alias checks. Permission regions,
    producer liveness and dual-output publication remain hardware checks.
    """
    projections = validate_qkv_bindings(projections)
    if len(norms) != 2 or len(ropes) != 2 or [type(v) for v in norms] != [HostQkNormBinding] * 2 or [type(v) for v in ropes] != [HostPartialRopeBinding] * 2:
        raise ValueError('expected exactly Q Norm, K Norm, Q RoPE, K RoPE')
    for role, (norm, rope) in enumerate(zip(norms, ropes)):
        norm.__post_init__(); rope.__post_init__()
        p = projections[role]
        window = (p.rows, p.token_base, p.token_count)
        if norm.role != role or rope.role != role or any((b.rows, b.token_base, b.token_count) != window for b in (norm, rope)):
            raise ValueError('attention role/window does not match projection')
        if norm.input_ddr != p.output_ddr or rope.input_ddr != norm.output_ddr:
            raise ValueError('attention inputs must be actual preceding outputs')
    if (ropes[0].trig_ddr, ropes[0].trig_tokens, ropes[0].position_base) != (ropes[1].trig_ddr, ropes[1].trig_tokens, ropes[1].position_base):
        raise ValueError('Q/K RoPE must use the same absolute position table/window')
    external = (projections[0].spans[0],) + tuple(p.spans[1] for p in projections) + tuple(n.input_spans[1] for n in norms) + (ropes[0].input_spans[1],)
    outputs = tuple(p.spans[2] for p in projections) + tuple(span for b in (*norms, *ropes) for span in b.output_spans)
    _spans(external, outputs)
    commands, records = build_qkv_commands(projections)
    for binding in (*norms, *ropes):
        index = len(commands)
        command, chain = build_host_qk_rope_descriptor(binding, first_index=len(records), event_wait=index, event_signal=index + 1)
        commands.append(command); records.update(chain)
    if len(records) != CHAIN_RECORDS or sum(b.job['writeBytes'] for b in (*projections, *norms, *ropes)) != projections[0].token_count * 24576:
        raise ValueError('seven-command descriptor/write byte inventory drift')
    return commands, records
