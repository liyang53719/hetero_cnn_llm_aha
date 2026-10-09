"""Public default-off full GDN block v3 Command128 contract.

Tensor-free serializer/parser; no numerical oracle, payload loading, DMA, or
implicit checkpoint restoration. Runtime completion proves actual ACKs.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum

# Reuse the existing typed ABI constructors/parser, including padded spans.
from host_bf16_gdn_core_descriptor import (
    HostGdnCoreTensor as HostGdnBlockTensor, TensorDType, DescriptorRecord,
    RecordType, NULL_INDEX, Command128, Engine, Opcode, MatrixAux,
    matrix_op_record, validate_descriptor_chain, bit, enum_value, uint,
    _tensor_records, _parse_tensor, _overlap, _envelope, _program,
    HIDDEN, CHANNELS, VALUE_CHANNELS, HEADS, HEAD_DIM, TAPS, PREP_ELEMENTS,
)

POLICY_VERSION = 3
FFN = 3584
DENSE_GEOMETRY = ((1024, 6144), (1024, 2048), (1024, 32), (2048, 1024),
                  (1024, 3584), (1024, 3584), (3584, 1024))

class GdnBlockOperation(IntEnum):
    CONV4 = 1
    DENSE = 2
    INPUT_PREP = 3
    RECURRENT = 4
    GATED_NORM = 5
    FENCE = 6
    # 7 remains reserved for an explicit future restore protocol.
    RMS_NORM = 8
    ELEMENTWISE = 9

NO_AUX_OPERATIONS = (GdnBlockOperation.FENCE, GdnBlockOperation.RMS_NORM,
                     GdnBlockOperation.ELEMENTWISE)
BLOCK_SEQUENCE = ((8, 0), (2, 0), (2, 1), (2, 2), (1, 0), (3, 0), (4, 0),
                  (5, 0), (2, 3), (9, 0), (8, 1), (2, 4), (2, 5), (9, 1),
                  (2, 6), (9, 2), (6, 0))
PARAMETER_BINDINGS = ((0, "b"), (1, "b"), (2, "b"), (3, "b"), (4, "b"),
                      (5, "aux0"), (5, "aux1"), (7, "aux0"), (8, "b"),
                      (10, "b"), (11, "b"), (12, "b"), (14, "b"))

@dataclass(frozen=True)
class HostGdnBlockBinding:
    """Typed A/B/D roots and operation-specific auxiliary roots.

    CONV4 aux0/aux1 are history input/output. INPUT_PREP aux0/aux1 are
    A_log/dt_bias. RECURRENT aux0 is state output. GATED_NORM aux0 is the
    original FP32 gamma (no 1+ transform). FENCE has no auxiliary roots and
    reads A/B/D as staged history, staged state, and this transaction's residual2.
    """

    operation: GdnBlockOperation
    a: HostGdnBlockTensor
    b: HostGdnBlockTensor
    d: HostGdnBlockTensor
    aux0: HostGdnBlockTensor | None = None
    aux1: HostGdnBlockTensor | None = None
    role: int = 0
    cold: bool = True
    expected_generation: int = 0
    recurrent_mode: bool | None = None

    def __post_init__(self) -> None:
        operation = enum_value(self.operation, GdnBlockOperation, "operation")
        role = uint(self.role, 3, "role")
        role_limit = {GdnBlockOperation.DENSE: 6, GdnBlockOperation.RMS_NORM: 1,
                      GdnBlockOperation.ELEMENTWISE: 2}.get(operation, 0)
        if role > role_limit:
            raise ValueError("unsupported GDN block operation role")
        object.__setattr__(self, "role", role)
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
                if not isinstance(tensor, HostGdnBlockTensor):
                    raise ValueError("roots must be HostGdnBlockTensor values")
                tensor.__post_init__()
        if any(tensor is None for tensor in tensors[:3]):
            raise ValueError("A, B and D tensor roots are required")
        bf, fp = TensorDType.BF16, TensorDType.FP32
        if operation == GdnBlockOperation.DENSE:
            k, n = DENSE_GEOMETRY[role]
            geometry = ((bf, (1, k)), (bf, (k, n)), (bf, (1, n)), None, None)
        elif operation == GdnBlockOperation.RMS_NORM:
            geometry = ((bf, (1, HIDDEN)),) * 3 + (None, None)
        elif operation == GdnBlockOperation.ELEMENTWISE:
            n = FFN if role == 1 else HIDDEN
            geometry = ((bf, (1, n)),) * 3 + (None, None)
        elif operation == GdnBlockOperation.CONV4:
            geometry = ((bf, (1, CHANNELS)), (bf, (CHANNELS, TAPS)),
                        (bf, (1, CHANNELS)), (bf, (CHANNELS, TAPS)), (bf, (CHANNELS, TAPS)))
        elif operation == GdnBlockOperation.INPUT_PREP:
            geometry = ((bf, (1, CHANNELS)), (bf, (1, 2 * HEADS)),
                        (fp, (1, PREP_ELEMENTS)), (fp, (1, HEADS)), (bf, (1, HEADS)))
        elif operation == GdnBlockOperation.RECURRENT:
            geometry = ((fp, (1, PREP_ELEMENTS)), (fp, (VALUE_CHANNELS, HEAD_DIM)),
                        (bf, (1, VALUE_CHANNELS)), (fp, (VALUE_CHANNELS, HEAD_DIM)), None)
        elif operation == GdnBlockOperation.GATED_NORM:
            geometry = ((bf, (1, VALUE_CHANNELS)), (bf, (1, VALUE_CHANNELS)),
                        (bf, (1, VALUE_CHANNELS)), (fp, (1, HEAD_DIM)), None)
        else:
            geometry = ((bf, (CHANNELS, TAPS)), (fp, (VALUE_CHANNELS, HEAD_DIM)),
                        (bf, (1, HIDDEN)), None, None)
        for slot, (tensor, expected) in enumerate(zip(tensors, geometry)):
            actual = None if tensor is None else (tensor.dtype, tensor.shape)
            if actual != expected:
                raise ValueError(f"{operation.name} root {slot} geometry/dtype or optional-root mismatch")
        present = tuple(tensor for tensor in tensors if tensor is not None)
        for index, tensor in enumerate(present):
            if any(_overlap(tensor, other) for other in present[:index]):
                raise ValueError("physical tensor alias within GDN block command")

    @property
    def policy_payload(self) -> int:
        return (POLICY_VERSION | int(self.operation) << 8 | int(self.cold) << 24 |
                int(self.recurrent_mode) << 25 | self.role << 26 | self.expected_generation << 32)

    @property
    def record_count(self) -> int:
        if self.operation == GdnBlockOperation.DENSE:
            return 12
        if self.operation in NO_AUX_OPERATIONS:
            return 11
        return 12 + 3 * (int(self.aux0 is not None) + int(self.aux1 is not None))


def build_host_gdn_block_descriptor(binding: HostGdnBlockBinding, *, first_index: int = 0,
                                   event_wait: int = 0, event_signal: int = 1
                                   ) -> tuple[Command128, dict[int, DescriptorRecord]]:
    """Build a canonical public descriptor chain for one operation."""
    if not isinstance(binding, HostGdnBlockBinding):
        raise ValueError("binding must be HostGdnBlockBinding")
    binding.__post_init__()
    _envelope(first_index, binding.record_count, event_wait, event_signal)
    i, records = first_index, {}
    dense = binding.operation == GdnBlockOperation.DENSE
    no_aux = binding.operation in NO_AUX_OPERATIONS
    b_root, d_root = (i + 5, i + 8) if no_aux else (i + 6, i + 9)
    _tensor_records(records, i, binding.a, i + 3)
    _tensor_records(records, b_root, binding.b)
    _tensor_records(records, d_root, binding.d)
    if dense:
        records[i + 3] = matrix_op_record(m=1, n=binding.d.shape[1], k=binding.a.shape[1],
                                          dataflow=0, next_index=i + 4)
        records[i + 4] = MatrixAux().to_record(next_index=i + 5)
        records[i + 5] = DescriptorRecord(RecordType.GDN_POLICY, 0, 0, NULL_INDEX, binding.policy_payload)
    else:
        records[i + 3] = _program(binding.operation).to_record(next_index=i + 4)
        records[i + 4] = DescriptorRecord(RecordType.GDN_POLICY, 0, 0,
                                         NULL_INDEX if no_aux else i + 5, binding.policy_payload)
        if not no_aux:
            roots = []
            for offset, tensor in ((12, binding.aux0), (15, binding.aux1)):
                roots.append(NULL_INDEX if tensor is None else i + offset)
                if tensor is not None:
                    _tensor_records(records, i + offset, tensor)
            root_type = (RecordType.GDN_STATE_ROOTS if binding.operation == GdnBlockOperation.CONV4
                         else RecordType.GDN_AUX_ROOTS)
            records[i + 5] = DescriptorRecord(root_type, 0, 0, NULL_INDEX, roots[0] | roots[1] << 24)
    command = Command128(Opcode.MATRIX_GEMM if dense else Opcode.SFU_VECTOR,
                         Engine.MATRIX if dense else Engine.SFU_CGRA,
                         event_wait=event_wait, event_signal=event_signal,
                         src0=i, src1=b_root, dst=d_root)
    return command, records


def _decode_descriptor(command: Command128 | int, records: Mapping[int, DescriptorRecord | int]
                       ) -> tuple[Command128, HostGdnBlockBinding, tuple[int, ...]]:
    if not isinstance(command, Command128):
        command = Command128.unpack(command)
    command.__post_init__()
    if command.flags or command.opcode not in (Opcode.MATRIX_GEMM, Opcode.SFU_VECTOR):
        raise ValueError("unsupported GDN block command envelope")
    _envelope(0, 1, command.event_wait, command.event_signal)
    roots = (command.src0, command.src1, command.dst)
    chains = [validate_descriptor_chain(root, records) for root in roots]
    dense = command.opcode == Opcode.MATRIX_GEMM
    policy_slot = 5 if dense else 4
    if len(chains[0]) <= policy_slot or chains[0][policy_slot][1].record_type != RecordType.GDN_POLICY:
        raise ValueError("missing GDN block policy")
    policy = chains[0][policy_slot][1].payload
    allowed = 0xFFFF | (31 << 24) | (0xFFFFFFFF << 32)
    if policy & ~allowed or policy & 0xFF != POLICY_VERSION:
        raise ValueError("GDN block policy version/reserved bits")
    operation = enum_value((policy >> 8) & 0xFF, GdnBlockOperation, "operation")
    if dense != (operation == GdnBlockOperation.DENSE):
        raise ValueError("GDN operation and opcode mismatch")
    expected_types = [1, 2, 3, 0x10, 0x12, 0x21] if dense else [1, 2, 3, 0x20, 0x21]
    if not dense and operation not in NO_AUX_OPERATIONS:
        expected_types.append(0x22 if operation == GdnBlockOperation.CONV4 else 0x23)
    if [record.record_type for _, record in chains[0]] != expected_types:
        raise ValueError("invalid GDN block A policy chain")
    aux_tensors = [None, None]
    if not dense and operation not in NO_AUX_OPERATIONS:
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
        raise ValueError("GDN block descriptor indices overlap")
    binding = HostGdnBlockBinding(operation, *(_parse_tensor(chain) for chain in chains[:3]),
                                *aux_tensors, role=(policy >> 26) & 7, cold=bool((policy >> 24) & 1),
                                recurrent_mode=bool((policy >> 25) & 1),
                                expected_generation=(policy >> 32) & 0xFFFFFFFF)
    if len(indices) != binding.record_count:
        raise ValueError("unexpected GDN block record count")
    if dense:
        expected_matrix = matrix_op_record(m=1, n=binding.d.shape[1], k=binding.a.shape[1], dataflow=0).payload
        if (chains[0][3][1].payload != expected_matrix or
                chains[0][4][1].payload != MatrixAux().payload()):
            raise ValueError("unsupported Dense matrix policy")
    elif chains[0][3][1].payload != _program(operation).payload():
        raise ValueError("unsupported GDN block SFU program")
    return command, binding, indices

def parse_host_gdn_block_descriptor(command: Command128 | int,
                                   records: Mapping[int, DescriptorRecord | int]) -> HostGdnBlockBinding:
    """Reject malformed chains, reserved fields, type/shape mismatches and aliases."""
    return _decode_descriptor(command, records)[1]


def validate_host_gdn_block_transaction(bindings: Sequence[HostGdnBlockBinding]) -> None:
    """Validate all actual producers and disjoint live physical resources.

    All source/output allocations remain reserved through the final Fence.
    This verifies addresses and declarations, never owner ACKs or payloads.
    """
    if len(bindings) != 17 or any(not isinstance(b, HostGdnBlockBinding) for b in bindings):
        raise ValueError("GDN block transaction requires 17 bindings")
    for binding in bindings:
        binding.__post_init__()
    if tuple((int(b.operation), b.role) for b in bindings) != BLOCK_SEQUENCE:
        raise ValueError("expected all 17 GDN block operations and explicit roles in order")
    inp, qkv, z, ab, conv, prep, rec, norm, out, r1, post, gate, up, silu, down, r2, fence = bindings
    context = (inp.cold, inp.expected_generation, inp.recurrent_mode)
    if any((b.cold, b.expected_generation, b.recurrent_mode) != context for b in bindings):
        raise ValueError("cold/generation/recurrent_mode must match across the transaction")
    resources = (
        ("raw_hidden", (inp.a, r1.a)),
        ("input_gamma", (inp.b,)), ("post_gamma", (post.b,)),
        ("qkv_weight", (qkv.b,)), ("z_weight", (z.b,)), ("ab_weight", (ab.b,)),
        ("conv_weight", (conv.b,)), ("A_log", (prep.aux0,)), ("dt_bias", (prep.aux1,)),
        ("gated_gamma", (norm.aux0,)), ("o_weight", (out.b,)),
        ("gate_weight", (gate.b,)), ("up_weight", (up.b,)), ("down_weight", (down.b,)),
        ("old_history", (conv.aux0,)), ("old_state", (rec.b,)),
        ("input_norm", (inp.d, qkv.a, z.a, ab.a)),
        ("qkv", (qkv.d, conv.a)), ("z", (z.d, norm.b)), ("ab", (ab.d, prep.b)),
        ("conv", (conv.d, prep.a)), ("prep", (prep.d, rec.a)), ("core", (rec.d, norm.a)),
        ("gated_norm", (norm.d, out.a)), ("o", (out.d, r1.b)),
        ("residual1", (r1.d, post.a, r2.a)), ("post_norm", (post.d, gate.a, up.a)),
        ("gate", (gate.d, silu.a)), ("up", (up.d, silu.b)),
        ("silu_mul", (silu.d, down.a)), ("down", (down.d, r2.b)),
        ("residual2", (r2.d, fence.d)),
        ("staged_history", (conv.aux1, fence.a)), ("staged_state", (rec.aux0, fence.b)),
    )
    for index, (name, uses) in enumerate(resources):
        if any(t != uses[0] for t in uses[1:]):
            raise ValueError(f"broken actual producer/source binding for {name}")
        for other_name, other_uses in resources[:index]:
            if _overlap(uses[0], other_uses[0]):
                raise ValueError(f"live physical tensor alias: {name} overlaps {other_name}")

def build_host_gdn_block_commands(bindings: Sequence[HostGdnBlockBinding], *, first_index: int = 0,
                                 event_wait: int = 0, first_signal: int = 1
                                 ) -> tuple[list[Command128], dict[int, DescriptorRecord]]:
    """Build the complete validated 17-command producer/consumer sequence."""
    validate_host_gdn_block_transaction(bindings)
    if uint(event_wait, 16, "event_wait") != 0:
        raise ValueError("a complete Host launch must begin at event zero")
    first_signal = uint(first_signal, 8, "first_signal")
    _envelope(first_index, sum(binding.record_count for binding in bindings), event_wait, first_signal)
    signals = range(first_signal, first_signal + len(bindings))
    if signals[-1] >= 256 or event_wait in signals:
        raise ValueError("transaction events overflow or depend on their own future signal")
    commands, records = [], {}
    for binding, signal in zip(bindings, signals):
        command, added = build_host_gdn_block_descriptor(binding, first_index=first_index + len(records),
                                                        event_wait=event_wait, event_signal=signal)
        commands.append(command)
        records.update(added)
        event_wait = signal
    return commands, records

def validate_host_gdn_block_continuation(previous: Sequence[HostGdnBlockBinding],
                                        current: Sequence[HostGdnBlockBinding]) -> None:
    """Check a carried transaction after the previous fence completed successfully.

    This does not establish that a fence was acknowledged: callers must obtain
    that fact from Host completion. Temporary allocations may be reused on a
    new launch. The latest committed history/state remain reserved, and the
    current transaction's normal alias checks protect them until its fence.
    This is continuation of a live context, not checkpoint restore after reset.
    """
    validate_host_gdn_block_transaction(previous)
    validate_host_gdn_block_transaction(current)
    if current[0].cold or current[0].expected_generation != previous[0].expected_generation + 1:
        raise ValueError("carried transaction requires the previous committed generation plus one")
    if current[4].aux0 != previous[16].a or current[6].b != previous[16].b:
        raise ValueError("carried history/state must match the previous fence bindings")
    for index, field in PARAMETER_BINDINGS:
        if getattr(previous[index], field) != getattr(current[index], field):
            raise ValueError("carried transaction must retain the same checkpoint weight bindings")

def parse_host_gdn_block_commands(commands: Sequence[Command128 | int],
                                 records: Mapping[int, DescriptorRecord | int]) -> tuple[HostGdnBlockBinding, ...]:
    """Validate a complete command table, including real addresses and event order."""
    if len(commands) != 17:
        raise ValueError("GDN block transaction requires 17 commands")
    decoded = [_decode_descriptor(command, records) for command in commands]
    unpacked = [entry[0] for entry in decoded]
    indices = tuple(index for _, _, used in decoded for index in used)
    if len(indices) != len(set(indices)):
        raise ValueError("descriptor indices must be distinct across the transaction")
    signals = [command.event_signal for command in unpacked]
    if (unpacked[0].event_wait != 0 or len(set(signals)) != len(signals) or unpacked[0].event_wait in signals or
            any(current.event_wait != previous.event_signal for previous, current in zip(unpacked, unpacked[1:]))):
        raise ValueError("broken GDN block event dependency chain")
    bindings = tuple(entry[1] for entry in decoded)
    validate_host_gdn_block_transaction(bindings)
    return bindings
