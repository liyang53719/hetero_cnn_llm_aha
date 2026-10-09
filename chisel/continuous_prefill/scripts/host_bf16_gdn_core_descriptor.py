"""Public, default-off GDN core v2 Command128 bindings.

This module describes one M1 transaction. It uses the public typed-descriptor
constructors and does not load weights, compute reference tensors, issue DMA,
or restore a checkpoint. Hardware must acknowledge every producer write before
its consumer runs and atomically publish both states only at the final fence.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from heteronpu.abi_validation import bit, enum_value, uint
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import (
    DescriptorRecord, MatrixAux, NULL_INDEX, RecordType, SfuProgram,
    TensorDType, validate_descriptor_chain,
)
from heteronpu.gemmini_descriptor_v2 import (
    matrix_op_record, shape4_record, stride3_record, tensor_base_record,
)

HIDDEN, CHANNELS, VALUE_CHANNELS, HEADS, HEAD_DIM, TAPS = 1024, 6144, 2048, 16, 128, 4
PREP_ELEMENTS = 6400
POLICY_VERSION = 2
ALIGNMENT_BYTES = 64


class GdnCoreOperation(IntEnum):
    CONV4 = 1
    DENSE = 2
    INPUT_PREP = 3
    RECURRENT = 4
    GATED_NORM = 5
    FENCE = 6


@dataclass(frozen=True)
class HostGdnCoreTensor:
    """A contiguous native rank-2 tensor in 64-byte-aligned flat DDR.

    The final burst is part of the allocation, including dt_bias's 32 bytes of
    padding. Access direction is defined by the command role, not tensor_base.
    """

    address: int
    dtype: TensorDType
    shape: tuple[int, int]

    def __post_init__(self) -> None:
        address = uint(self.address, 56, "DDR address")
        dtype = enum_value(self.dtype, TensorDType, "dtype")
        if dtype not in (TensorDType.BF16, TensorDType.FP32):
            raise ValueError("GDN core requires native BF16 or FP32")
        if not isinstance(self.shape, (tuple, list)) or len(self.shape) != 2:
            raise ValueError("GDN core tensor requires rank-2 shape")
        shape = tuple(uint(n, 18, "shape dimension") for n in self.shape)
        if not all(shape):
            raise ValueError("GDN core tensor dimensions must be nonzero")
        object.__setattr__(self, "address", address)
        object.__setattr__(self, "dtype", dtype)
        object.__setattr__(self, "shape", shape)
        if address % ALIGNMENT_BYTES or address + self.span_bytes > 1 << 56:
            raise ValueError("unaligned or overflowing DDR span")

    @property
    def logical_bytes(self) -> int:
        return self.shape[0] * self.shape[1] * (2 if self.dtype == TensorDType.BF16 else 4)

    @property
    def span_bytes(self) -> int:
        return (self.logical_bytes + ALIGNMENT_BYTES - 1) // ALIGNMENT_BYTES * ALIGNMENT_BYTES


def _overlap(left: HostGdnCoreTensor, right: HostGdnCoreTensor) -> bool:
    return (left.address < right.address + right.span_bytes and
            right.address < left.address + left.span_bytes)


@dataclass(frozen=True)
class HostGdnCoreBinding:
    """Typed A/B/D roots and operation-specific auxiliary roots.

    CONV4 aux0/aux1 are history input/output. INPUT_PREP aux0/aux1 are
    A_log/dt_bias. RECURRENT aux0 is state output. GATED_NORM aux0 is the
    original FP32 gamma (no 1+ transform). FENCE has no auxiliary roots and
    reads A/B/D as staged history, staged state, and this transaction's norm.
    """

    operation: GdnCoreOperation
    a: HostGdnCoreTensor
    b: HostGdnCoreTensor
    d: HostGdnCoreTensor
    aux0: HostGdnCoreTensor | None = None
    aux1: HostGdnCoreTensor | None = None
    cold: bool = True
    expected_generation: int = 0
    recurrent_mode: bool | None = None

    def __post_init__(self) -> None:
        operation = enum_value(self.operation, GdnCoreOperation, "operation")
        cold = bit(self.cold, "cold")
        mode = not cold if self.recurrent_mode is None else bit(self.recurrent_mode, "recurrent_mode")
        generation = uint(self.expected_generation, 32, "expected_generation")
        if mode != (not cold):
            raise ValueError("M1 recurrent_mode must equal not cold")
        if generation == 0xFFFFFFFF or (cold != (generation == 0)):
            raise ValueError("cold requires generation zero, carried requires nonzero; generation wrap is unsupported")
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "cold", cold)
        object.__setattr__(self, "expected_generation", generation)
        object.__setattr__(self, "recurrent_mode", mode)
        tensors = (self.a, self.b, self.d, self.aux0, self.aux1)
        for tensor in tensors:
            if tensor is not None:
                if not isinstance(tensor, HostGdnCoreTensor):
                    raise ValueError("roots must be HostGdnCoreTensor values")
                tensor.__post_init__()
        if any(tensor is None for tensor in tensors[:3]):
            raise ValueError("A, B and D tensor roots are required")
        bf, fp = TensorDType.BF16, TensorDType.FP32
        if operation == GdnCoreOperation.DENSE:
            n = self.d.shape[1]
            if n not in (CHANNELS, VALUE_CHANNELS, 2 * HEADS):
                raise ValueError("Dense supports only QKV, Z and packed AB widths")
            geometry = ((bf, (1, HIDDEN)), (bf, (HIDDEN, n)), (bf, (1, n)), None, None)
        elif operation == GdnCoreOperation.CONV4:
            geometry = ((bf, (1, CHANNELS)), (bf, (CHANNELS, TAPS)),
                        (bf, (1, CHANNELS)), (bf, (CHANNELS, TAPS)), (bf, (CHANNELS, TAPS)))
        elif operation == GdnCoreOperation.INPUT_PREP:
            geometry = ((bf, (1, CHANNELS)), (bf, (1, 2 * HEADS)),
                        (fp, (1, PREP_ELEMENTS)), (fp, (1, HEADS)), (bf, (1, HEADS)))
        elif operation == GdnCoreOperation.RECURRENT:
            geometry = ((fp, (1, PREP_ELEMENTS)), (fp, (VALUE_CHANNELS, HEAD_DIM)),
                        (bf, (1, VALUE_CHANNELS)), (fp, (VALUE_CHANNELS, HEAD_DIM)), None)
        elif operation == GdnCoreOperation.GATED_NORM:
            geometry = ((bf, (1, VALUE_CHANNELS)), (bf, (1, VALUE_CHANNELS)),
                        (bf, (1, VALUE_CHANNELS)), (fp, (1, HEAD_DIM)), None)
        else:
            geometry = ((bf, (CHANNELS, TAPS)), (fp, (VALUE_CHANNELS, HEAD_DIM)),
                        (bf, (1, VALUE_CHANNELS)), None, None)
        for slot, (tensor, expected) in enumerate(zip(tensors, geometry)):
            actual = None if tensor is None else (tensor.dtype, tensor.shape)
            if actual != expected:
                raise ValueError(f"{operation.name} root {slot} geometry/dtype or optional-root mismatch")
        present = tuple(tensor for tensor in tensors if tensor is not None)
        for index, tensor in enumerate(present):
            if any(_overlap(tensor, other) for other in present[:index]):
                raise ValueError("physical tensor alias within GDN core command")

    @property
    def policy_payload(self) -> int:
        return (POLICY_VERSION | int(self.operation) << 8 | int(self.cold) << 24 |
                int(self.recurrent_mode) << 25 | self.expected_generation << 32)

    @property
    def record_count(self) -> int:
        if self.operation == GdnCoreOperation.DENSE:
            return 12
        if self.operation == GdnCoreOperation.FENCE:
            return 11
        return 12 + 3 * (int(self.aux0 is not None) + int(self.aux1 is not None))


def _envelope(first_index: int, count: int, event_wait: int, event_signal: int) -> None:
    first_index = uint(first_index, 24, "first_index")
    event_wait = uint(event_wait, 16, "event_wait")
    event_signal = uint(event_signal, 16, "event_signal")
    if first_index + count > NULL_INDEX:
        raise ValueError("descriptor allocation crosses null index")
    if event_wait >= 256 or not 0 < event_signal < 256 or event_wait == event_signal:
        raise ValueError("Host GDN requires distinct 8-bit wait/signal events and nonzero signal")


def _program(operation: GdnCoreOperation) -> SfuProgram:
    return SfuProgram(0x30, 2, input_dtype=(TensorDType.FP32 if operation == GdnCoreOperation.RECURRENT
                                          else TensorDType.BF16),
                      output_dtype=(TensorDType.FP32 if operation == GdnCoreOperation.INPUT_PREP
                                    else TensorDType.BF16), vector_lanes=1)


def _tensor_records(records: dict[int, DescriptorRecord], root: int,
                    tensor: HostGdnCoreTensor, tail: int = NULL_INDEX) -> None:
    records[root] = tensor_base_record(tensor.address, dtype=tensor.dtype, rank=2, next_index=root + 1)
    records[root + 1] = shape4_record((*tensor.shape, 1, 1), next_index=root + 2)
    records[root + 2] = stride3_record((tensor.shape[1], 1, 1), next_index=tail)


def build_host_gdn_core_descriptor(binding: HostGdnCoreBinding, *, first_index: int = 0,
                                   event_wait: int = 0, event_signal: int = 1
                                   ) -> tuple[Command128, dict[int, DescriptorRecord]]:
    """Build a canonical public descriptor chain for one operation."""
    if not isinstance(binding, HostGdnCoreBinding):
        raise ValueError("binding must be HostGdnCoreBinding")
    binding.__post_init__()
    _envelope(first_index, binding.record_count, event_wait, event_signal)
    i, records = first_index, {}
    dense = binding.operation == GdnCoreOperation.DENSE
    fence = binding.operation == GdnCoreOperation.FENCE
    b_root, d_root = (i + 5, i + 8) if fence else (i + 6, i + 9)
    _tensor_records(records, i, binding.a, i + 3)
    _tensor_records(records, b_root, binding.b)
    _tensor_records(records, d_root, binding.d)
    if dense:
        records[i + 3] = matrix_op_record(m=1, n=binding.d.shape[1], k=HIDDEN,
                                          dataflow=0, next_index=i + 4)
        records[i + 4] = MatrixAux().to_record(next_index=i + 5)
        records[i + 5] = DescriptorRecord(RecordType.GDN_POLICY, 0, 0, NULL_INDEX, binding.policy_payload)
    else:
        records[i + 3] = _program(binding.operation).to_record(next_index=i + 4)
        records[i + 4] = DescriptorRecord(RecordType.GDN_POLICY, 0, 0,
                                         NULL_INDEX if fence else i + 5, binding.policy_payload)
        if not fence:
            roots = []
            for offset, tensor in ((12, binding.aux0), (15, binding.aux1)):
                roots.append(NULL_INDEX if tensor is None else i + offset)
                if tensor is not None:
                    _tensor_records(records, i + offset, tensor)
            root_type = (RecordType.GDN_STATE_ROOTS if binding.operation == GdnCoreOperation.CONV4
                         else RecordType.GDN_AUX_ROOTS)
            records[i + 5] = DescriptorRecord(root_type, 0, 0, NULL_INDEX, roots[0] | roots[1] << 24)
    command = Command128(Opcode.MATRIX_GEMM if dense else Opcode.SFU_VECTOR,
                         Engine.MATRIX if dense else Engine.SFU_CGRA,
                         event_wait=event_wait, event_signal=event_signal,
                         src0=i, src1=b_root, dst=d_root)
    return command, records


def _parse_tensor(chain: tuple) -> HostGdnCoreTensor:
    if [record.record_type for _, record in chain[:3]] != [RecordType.TENSOR_BASE, RecordType.SHAPE4, RecordType.STRIDE3]:
        raise ValueError("tensor requires BASE -> SHAPE4 -> STRIDE3 prefix")
    base, shape, stride = (record.payload for _, record in chain[:3])
    address = (base & ((1 << 48) - 1)) | (base >> 64) << 48
    dtype = (base >> 52) & 0xF
    if base != tensor_base_record(address, dtype=dtype, rank=2).payload:
        raise ValueError("native flat rank-2 tensor_base required")
    dimensions = tuple((shape >> (18 * index)) & 0x3FFFF for index in range(4))
    if dimensions[2:] != (1, 1) or stride != stride3_record((dimensions[1], 1, 1)).payload:
        raise ValueError("native contiguous shape/stride required")
    return HostGdnCoreTensor(address, dtype, dimensions[:2])


def _decode_descriptor(command: Command128 | int, records: Mapping[int, DescriptorRecord | int]
                       ) -> tuple[Command128, HostGdnCoreBinding, tuple[int, ...]]:
    if not isinstance(command, Command128):
        command = Command128.unpack(command)
    command.__post_init__()
    if command.flags or command.opcode not in (Opcode.MATRIX_GEMM, Opcode.SFU_VECTOR):
        raise ValueError("unsupported GDN core command envelope")
    _envelope(0, 1, command.event_wait, command.event_signal)
    roots = (command.src0, command.src1, command.dst)
    chains = [validate_descriptor_chain(root, records) for root in roots]
    dense = command.opcode == Opcode.MATRIX_GEMM
    policy_slot = 5 if dense else 4
    if len(chains[0]) <= policy_slot or chains[0][policy_slot][1].record_type != RecordType.GDN_POLICY:
        raise ValueError("missing GDN core policy")
    policy = chains[0][policy_slot][1].payload
    allowed = 0xFFFF | (3 << 24) | (0xFFFFFFFF << 32)
    if policy & ~allowed or policy & 0xFF != POLICY_VERSION:
        raise ValueError("GDN core policy version/reserved bits")
    operation = enum_value((policy >> 8) & 0xFF, GdnCoreOperation, "operation")
    if dense != (operation == GdnCoreOperation.DENSE):
        raise ValueError("GDN operation and opcode mismatch")
    expected_types = [1, 2, 3, 0x10, 0x12, 0x21] if dense else [1, 2, 3, 0x20, 0x21]
    if not dense and operation != GdnCoreOperation.FENCE:
        expected_types.append(0x22 if operation == GdnCoreOperation.CONV4 else 0x23)
    if [record.record_type for _, record in chains[0]] != expected_types:
        raise ValueError("invalid GDN core A policy chain")
    aux_tensors = [None, None]
    if not dense and operation != GdnCoreOperation.FENCE:
        payload = chains[0][-1][1].payload
        if payload >> 48:
            raise ValueError("reserved auxiliary-root payload")
        for slot in range(2):
            root = (payload >> (24 * slot)) & NULL_INDEX
            if root != NULL_INDEX:
                chain = validate_descriptor_chain(root, records)
                chains.append(chain)
                aux_tensors[slot] = _parse_tensor(chain)
    for chain in chains[1:]:
        if [record.record_type for _, record in chain] != [1, 2, 3]:
            raise ValueError("non-A tensor chain must end after STRIDE3")
    indices = tuple(index for chain in chains for index, _ in chain)
    if len(indices) != len(set(indices)):
        raise ValueError("GDN core descriptor indices overlap")
    binding = HostGdnCoreBinding(operation, *(_parse_tensor(chain) for chain in chains[:3]),
                                *aux_tensors, cold=bool((policy >> 24) & 1),
                                recurrent_mode=bool((policy >> 25) & 1),
                                expected_generation=(policy >> 32) & 0xFFFFFFFF)
    if len(indices) != binding.record_count:
        raise ValueError("unexpected GDN core record count")
    if dense:
        expected_matrix = matrix_op_record(m=1, n=binding.d.shape[1], k=HIDDEN, dataflow=0).payload
        if (chains[0][3][1].payload != expected_matrix or
                chains[0][4][1].payload != MatrixAux().payload()):
            raise ValueError("unsupported Dense matrix policy")
    elif chains[0][3][1].payload != _program(operation).payload():
        raise ValueError("unsupported GDN core SFU program")
    return command, binding, indices


def parse_host_gdn_core_descriptor(command: Command128 | int,
                                   records: Mapping[int, DescriptorRecord | int]) -> HostGdnCoreBinding:
    """Reject malformed chains, reserved fields, type/shape mismatches and aliases."""
    return _decode_descriptor(command, records)[1]


def validate_host_gdn_core_transaction(bindings: Sequence[HostGdnCoreBinding]) -> None:
    """Validate true producers and physical resources for one eight-command M1 token.

    All resource allocations stay reserved through the fence, preserving
    external sources and old committed state if a command fails. This version
    does not recycle earlier producer buffers inside the transaction. Fence
    references do not create new writes. Different read-only sources are also
    distinct resources and may not overlap, even across different commands.
    """
    if len(bindings) != 8 or any(not isinstance(binding, HostGdnCoreBinding) for binding in bindings):
        raise ValueError("GDN core transaction requires eight bindings")
    for binding in bindings:
        binding.__post_init__()
    expected = [GdnCoreOperation.DENSE] * 3 + [GdnCoreOperation.CONV4, GdnCoreOperation.INPUT_PREP,
                GdnCoreOperation.RECURRENT, GdnCoreOperation.GATED_NORM, GdnCoreOperation.FENCE]
    if [binding.operation for binding in bindings] != expected:
        raise ValueError("expected Dense QKV/Z/AB -> Conv -> Prep -> Recurrent -> Norm -> Fence")
    qkv, z, ab, conv, prep, rec, norm, fence = bindings
    if [binding.d.shape[1] for binding in bindings[:3]] != [CHANNELS, VALUE_CHANNELS, 2 * HEADS]:
        raise ValueError("Dense producers must be QKV, Z and packed AB in order")
    state = (qkv.cold, qkv.expected_generation, qkv.recurrent_mode)
    if any((binding.cold, binding.expected_generation, binding.recurrent_mode) != state for binding in bindings):
        raise ValueError("cold/generation/recurrent_mode must match across the transaction")
    # One resource has one immutable typed address and one actual producer.
    resources = (
        ("hidden", 0, 7, (qkv.a, z.a, ab.a)),
        ("qkv_weight", 0, 7, (qkv.b,)), ("z_weight", 0, 7, (z.b,)),
        ("ab_weight", 0, 7, (ab.b,)), ("conv_weight", 0, 7, (conv.b,)),
        ("history_in", 0, 7, (conv.aux0,)), ("state_in", 0, 7, (rec.b,)),
        ("A_log", 0, 7, (prep.aux0,)), ("dt_bias", 0, 7, (prep.aux1,)),
        ("norm_weight", 0, 7, (norm.aux0,)),
        ("qkv", 0, 7, (qkv.d, conv.a)), ("z", 1, 7, (z.d, norm.b)),
        ("ab", 2, 7, (ab.d, prep.b)), ("conv", 3, 7, (conv.d, prep.a)),
        ("history_out", 3, 7, (conv.aux1, fence.a)),
        ("prep", 4, 7, (prep.d, rec.a)), ("core", 5, 7, (rec.d, norm.a)),
        ("state_out", 5, 7, (rec.aux0, fence.b)), ("norm", 6, 7, (norm.d, fence.d)),
    )
    for index, (name, birth, last_use, uses) in enumerate(resources):
        if any(tensor != uses[0] for tensor in uses[1:]):
            raise ValueError(f"broken actual producer/source binding for {name}")
        for other_name, other_birth, other_last, other_uses in resources[:index]:
            if max(birth, other_birth) <= min(last_use, other_last) and _overlap(uses[0], other_uses[0]):
                raise ValueError(f"live physical tensor alias: {name} overlaps {other_name}")


def build_host_gdn_core_commands(bindings: Sequence[HostGdnCoreBinding], *, first_index: int = 0,
                                 event_wait: int = 0, first_signal: int = 1
                                 ) -> tuple[list[Command128], dict[int, DescriptorRecord]]:
    """Build the complete validated eight-command producer/consumer sequence."""
    validate_host_gdn_core_transaction(bindings)
    first_signal = uint(first_signal, 8, "first_signal")
    _envelope(first_index, sum(binding.record_count for binding in bindings), event_wait, first_signal)
    signals = range(first_signal, first_signal + len(bindings))
    if signals[-1] >= 256 or event_wait in signals:
        raise ValueError("transaction events overflow or depend on their own future signal")
    commands, records = [], {}
    for binding, signal in zip(bindings, signals):
        command, added = build_host_gdn_core_descriptor(binding, first_index=first_index + len(records),
                                                        event_wait=event_wait, event_signal=signal)
        commands.append(command)
        records.update(added)
        event_wait = signal
    return commands, records


def validate_host_gdn_core_continuation(previous: Sequence[HostGdnCoreBinding],
                                        current: Sequence[HostGdnCoreBinding]) -> None:
    """Check a carried transaction after the previous fence completed successfully.

    This does not establish that a fence was acknowledged: callers must obtain
    that fact from Host completion. Temporary allocations may be reused on a
    new launch. The latest committed history/state remain reserved, and the
    current transaction's normal alias checks protect them until its fence.
    This is continuation of a live context, not checkpoint restore after reset.
    """
    validate_host_gdn_core_transaction(previous)
    validate_host_gdn_core_transaction(current)
    if current[0].cold or current[0].expected_generation != previous[0].expected_generation + 1:
        raise ValueError("carried transaction requires the previous committed generation plus one")
    if current[3].aux0 != previous[7].a or current[5].b != previous[7].b:
        raise ValueError("carried history/state must match the previous fence bindings")
    for index, field in ((0, "b"), (1, "b"), (2, "b"), (3, "b"),
                         (4, "aux0"), (4, "aux1"), (6, "aux0")):
        if getattr(previous[index], field) != getattr(current[index], field):
            raise ValueError("carried transaction must retain the same checkpoint weight bindings")


def parse_host_gdn_core_commands(commands: Sequence[Command128 | int],
                                 records: Mapping[int, DescriptorRecord | int]) -> tuple[HostGdnCoreBinding, ...]:
    """Validate a complete command table, including real addresses and event order."""
    if len(commands) != 8:
        raise ValueError("GDN core transaction requires eight commands")
    decoded = [_decode_descriptor(command, records) for command in commands]
    unpacked = [entry[0] for entry in decoded]
    indices = tuple(index for _, _, used in decoded for index in used)
    if len(indices) != len(set(indices)):
        raise ValueError("descriptor indices must be distinct across the transaction")
    signals = [command.event_signal for command in unpacked]
    if (len(set(signals)) != len(signals) or unpacked[0].event_wait in signals or
            any(current.event_wait != previous.event_signal for previous, current in zip(unpacked, unpacked[1:]))):
        raise ValueError("broken GDN core event dependency chain")
    bindings = tuple(entry[1] for entry in decoded)
    validate_host_gdn_core_transaction(bindings)
    return bindings
