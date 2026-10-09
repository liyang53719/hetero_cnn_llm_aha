"""Default-off M1 Qwen3.5 Attention block: public Command128/typed records.

The existing QKV v2, QK/RoPE v1 and attention-core v2 producers are unchanged.
ATTENTION_POLICY (0x24) v3 extends only the eleven surrounding block commands.
No model payload, reference arithmetic, DMA, restore or ACK is synthesized here.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum

from host_bf16_attention_core_descriptor import (
    AttentionContext, AttentionTensor, AttentionOperation, HostAttentionCoreBinding,
    Command128, Engine, Opcode, DescriptorRecord, RecordType, NULL_INDEX,
    MatrixAux, SfuProgram, matrix_op_record, validate_descriptor_chain,
    enum_value, uint, _disjoint, _envelope, _tensor, _parse_tensor,
    _validate_bindings, build_host_attention_core_descriptor,
    parse_host_attention_core_descriptor,
)
from host_bf16_qkv_descriptor import build_host_qkv_descriptor, parse_host_qkv_descriptor
from host_bf16_qk_rope_descriptor import build_host_qk_rope_descriptor, parse_host_qk_rope_descriptor

POLICY_VERSION = 3
CHAIN_COMMANDS, CHAIN_RECORDS, OWNER_JOBS = 22, 296, 19
DENSE_GEOMETRY = ((2048, 1024), (1024, 3584), (1024, 3584), (3584, 1024))


class AttentionBlockOperation(IntEnum):
    FENCE = 4
    RMS_NORM = 5
    DENSE = 6
    ELEMENTWISE = 7


# Eleven v3 additions, interleaved with eleven unchanged producer/core commands.
BLOCK_SEQUENCE = ((5, 0), (7, 0), (6, 0), (7, 1), (5, 1),
                  (6, 1), (6, 2), (7, 2), (6, 3), (7, 3), (4, 0))
BLOCK_COMMAND_INDICES = (0, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)


@dataclass(frozen=True)
class HostAttentionBlockBinding:
    """Elementwise role0 is BF16(sigmoid(A)) * B: A=Q gate, B=context."""
    operation: AttentionBlockOperation
    role: int
    context: AttentionContext
    a: AttentionTensor
    b: AttentionTensor
    d: AttentionTensor

    def __post_init__(self):
        op = enum_value(self.operation, AttentionBlockOperation, 'block operation')
        role = uint(self.role, 3, 'block role')
        object.__setattr__(self, 'operation', op)
        object.__setattr__(self, 'role', role)
        if type(self.context) is not AttentionContext:
            raise ValueError('block requires explicit attention context')
        self.context.__post_init__()
        limit = {op.FENCE: 0, op.RMS_NORM: 1, op.DENSE: 3, op.ELEMENTWISE: 3}[op]
        if role > limit:
            raise ValueError('unsupported block operation role')
        for t in (self.a, self.b, self.d):
            if type(t) is not AttentionTensor:
                raise ValueError('native BF16 AttentionTensor required')
            t.__post_init__()
        if op == op.DENSE:
            k, n = DENSE_GEOMETRY[role]
            expected = ((1, k), (k, n), (1, n))
        elif op == op.FENCE:
            expected = ((2, self.context.capacity, 512), (1, 1024), (1, 1024))
        else:
            n = (2048 if role == 0 else 3584 if role == 2 else 1024) if op == op.ELEMENTWISE else 1024
            expected = ((1, n),) * 3
        if tuple(t.shape for t in (self.a, self.b, self.d)) != expected:
            raise ValueError('block tensor geometry/role mismatch; only M1 is admitted')
        _disjoint(tuple(t.span for t in (self.a, self.b, self.d)))

    @property
    def policy_payload(self):
        # Payload coordinates: version 7:0, op 11:8, base 43:12=0,
        # count 51:44=1, recipe 59:52=0, role 62:60, reserved 71:63=0.
        return POLICY_VERSION | int(self.operation) << 8 | 1 << 44 | self.role << 60

    @property
    def record_count(self): return 13 if self.operation == self.operation.DENSE else 12

    @property
    def job(self):
        if self.operation == self.operation.FENCE:
            return None
        kind = {self.operation.DENSE: 1, self.operation.RMS_NORM: 11,
                self.operation.ELEMENTWISE: 13}[self.operation]
        result = dict(kind=kind, m=1, n=self.d.shape[1], k=self.a.shape[1],
                      a=self.a.address, b=self.b.address, dst=self.d.address,
                      activationBf16=True, weightBf16=True, outputBf16=True,
                      writeBytes=self.d.payload_bytes)
        if self.operation == self.operation.ELEMENTWISE:
            result['gdnElementwiseOp'] = (2, 0, 1, 0)[self.role]
        return result


def _programs(binding):
    if binding.operation == AttentionBlockOperation.DENSE:
        return (matrix_op_record(m=1, n=binding.d.shape[1], k=binding.a.shape[1], dataflow=0),
                MatrixAux().to_record())
    return (SfuProgram(Opcode.SFU_VECTOR, 2).to_record(),)


def build_host_attention_block_descriptor(binding, *, first_index=0, event_wait=0, event_signal=1):
    if type(binding) is not HostAttentionBlockBinding:
        raise ValueError('expected HostAttentionBlockBinding')
    binding.__post_init__()
    _envelope(first_index, binding.record_count, event_wait, event_signal)
    programs = _programs(binding)
    policy_index = first_index + 3 + len(programs)
    b_root, d_root = policy_index + 2, policy_index + 5
    records = {}
    _tensor(records, first_index, binding.a, first_index + 3)
    _tensor(records, b_root, binding.b)
    _tensor(records, d_root, binding.d)
    for offset, record in enumerate(programs, 3):
        records[first_index + offset] = DescriptorRecord(record.record_type, 0, 0, first_index + offset + 1, record.payload)
    records[policy_index] = DescriptorRecord(RecordType.ATTENTION_POLICY, 0, 0, policy_index + 1, binding.policy_payload)
    records[policy_index + 1] = binding.context.to_record()
    dense = binding.operation == AttentionBlockOperation.DENSE
    return Command128(Opcode.MATRIX_GEMM if dense else Opcode.SFU_VECTOR,
                      Engine.MATRIX if dense else Engine.SFU_CGRA,
                      event_wait=event_wait, event_signal=event_signal,
                      src0=first_index, src1=b_root, dst=d_root), records


def parse_host_attention_block_descriptor(command, records):
    if isinstance(command, int): command = Command128.unpack(command)
    command.__post_init__()
    dense = command.opcode == Opcode.MATRIX_GEMM
    if command.flags or (command.opcode, command.engine) != ((Opcode.MATRIX_GEMM, Engine.MATRIX) if dense else (Opcode.SFU_VECTOR, Engine.SFU_CGRA)):
        raise ValueError('unsupported block command envelope')
    _envelope(0, 1, command.event_wait, command.event_signal)
    chains = [validate_descriptor_chain(root, records) for root in (command.src0, command.src1, command.dst)]
    types = [1, 2, 3] + ([0x10, 0x12] if dense else [0x20]) + [0x24, 0x26]
    if [r.record_type for _, r in chains[0]] != types:
        raise ValueError('invalid block A program/policy/context chain')
    if any([r.record_type for _, r in c] != [1, 2, 3] for c in chains[1:]):
        raise ValueError('non-A block tensor chain must terminate after stride')
    indices = [i for c in chains for i, _ in c]
    if len(indices) != len(set(indices)):
        raise ValueError('block descriptor records overlap')
    p = chains[0][-2][1].payload
    op = enum_value((p >> 8) & 15, AttentionBlockOperation, 'block operation')
    result = HostAttentionBlockBinding(op, (p >> 60) & 7,
                                      AttentionContext.from_record(chains[0][-1][1]),
                                      *(_parse_tensor(c) for c in chains))
    if p != result.policy_payload or dense != (op == op.DENSE):
        raise ValueError('unsupported block policy version/window/role/recipe/reserved bits')
    if [r.payload for _, r in chains[0][3:-2]] != [r.payload for r in _programs(result)]:
        raise ValueError('unsupported block numeric Matrix/SFU policy')
    if len(indices) != result.record_count:
        raise ValueError('block record inventory mismatch')
    return result


def _resources(projections, norms, ropes, core, block):
    inp, gate, out, r1, post, fg, fu, silu, down, r2, fence = block
    def tensor(address, shape): return AttentionTensor(address, shape)
    parameters = tuple(tensor(p.weight_ddr, (1024, p.n)) for p in projections) + tuple(
        tensor(n.weight_ddr, (1, 256)) for n in norms) + (tensor(ropes[0].trig_ddr, (ropes[0].trig_tokens, 64)),
        inp.b, out.b, post.b, fg.b, fu.b, down.b)
    qkv = tuple(tensor(p.output_ddr, (1, p.n)) for p in projections)
    normalized = tuple(tensor(n.output_ddr, (1, n.n)) for n in norms)
    qgate = tensor(norms[0].gate_output_ddr, (1, 2048))
    rotated = tuple(tensor(r.output_ddr, (1, r.n)) for r in ropes)
    produced = (inp.d,) + qkv + normalized + (qgate,) + rotated + core.tensors[4:] + tuple(b.d for b in block[1:-1])
    return parameters, inp.a, produced, core.tensors[3]


def validate_host_attention_block_bindings(projections, norms, ropes, core, block):
    """Check all physical allocations and exact producer roles before serializing."""
    _validate_bindings(projections, norms, ropes, core)
    if (core.rows, core.token_base, core.token_count) != (1, 0, 1):
        raise ValueError('Attention block v3 supports only rows=1, tokenBase=0, tokenCount=1')
    if len(block) != 11 or any(type(b) is not HostAttentionBlockBinding for b in block):
        raise ValueError('full block requires eleven explicit v3 surrounding bindings')
    for b in block: b.__post_init__()
    if tuple((int(b.operation), b.role) for b in block) != BLOCK_SEQUENCE:
        raise ValueError('invalid full block operation/role order')
    if any(b.context != core.context for b in block):
        raise ValueError('all block commands must carry the identical core context')
    inp, gate, out, r1, post, fg, fu, silu, down, r2, fence = block
    edges = (
        ('actual input RMS', inp.d, AttentionTensor(projections[0].activation_ddr, (1, 1024))),
        ('context', gate.b, core.tensors[-1]),
        ('Q gate', gate.a, AttentionTensor(norms[0].gate_output_ddr, (1, 2048))),
        ('sigmoid multiply', gate.d, out.a), ('raw hidden', inp.a, r1.a),
        ('O', out.d, r1.b), ('residual1/post', r1.d, post.a),
        ('residual1/final', r1.d, r2.a), ('post/gate', post.d, fg.a),
        ('post/up', post.d, fu.a), ('FFN gate', fg.d, silu.a),
        ('FFN up', fu.d, silu.b), ('SiLU multiply', silu.d, down.a),
        ('down', down.d, r2.b), ('final residual', r2.d, fence.d),
        ('fence cache', core.tensors[3], fence.a), ('fence raw hidden', inp.a, fence.b),
    )
    for name, producer, consumer in edges:
        if producer != consumer:
            raise ValueError(f'broken actual producer/source binding: {name}')
    parameters, hidden, produced, cache = _resources(projections, norms, ropes, core, block)
    _disjoint(tuple(t.span for t in (hidden,) + parameters + produced + (cache,)))
    return tuple(block)


def build_host_attention_block_commands(projections, norms, ropes, core, block):
    """Serialize exactly 22 commands; the old core fence is intentionally absent."""
    validate_host_attention_block_bindings(projections, norms, ropes, core, block)
    work = [(build_host_attention_block_descriptor, block[0])]
    work += [(build_host_qkv_descriptor, b) for b in projections]
    work += [(build_host_qk_rope_descriptor, b) for b in (*norms, *ropes)]
    work += [(build_host_attention_core_descriptor, core.command_binding(op)) for op in tuple(AttentionOperation)[:4]]
    work += [(build_host_attention_block_descriptor, b) for b in block[1:]]
    commands, records = [], {}
    for builder, binding in work:
        cmd, extra = builder(binding, first_index=len(records), event_wait=len(commands), event_signal=len(commands) + 1)
        commands.append(cmd); records.update(extra)
    if (len(commands), len(records)) != (CHAIN_COMMANDS, CHAIN_RECORDS):
        raise ValueError('full block command/record inventory drift')
    return commands, records


def validate_host_attention_block_commands(commands, records):
    """Parse an untrusted stream and validate public wire, geometry and topology."""
    if len(commands) != CHAIN_COMMANDS:
        raise ValueError('expected exactly 22 block commands')
    commands = [Command128.unpack(c) if isinstance(c, int) else c for c in commands]
    for i, c in enumerate(commands):
        c.__post_init__()
        if (c.event_wait, c.event_signal) != (i, i + 1):
            raise ValueError('block events must be strictly sequential 0 through 22')
    projections = tuple(parse_host_qkv_descriptor(c, records) for c in commands[1:4])
    norms = tuple(parse_host_qk_rope_descriptor(c, records) for c in commands[4:6])
    ropes = tuple(parse_host_qk_rope_descriptor(c, records) for c in commands[6:8])
    steps = tuple(parse_host_attention_core_descriptor(c, records) for c in commands[8:12])
    if tuple(b.operation for b in steps) != tuple(AttentionOperation)[:4]:
        raise ValueError('append/QK/softmax/PV order mismatch')
    append, qk, soft, pv = steps
    ctx = append.context
    core = HostAttentionCoreBinding(append.src0.shape[0], append.token_base, append.token_count,
        ctx.capacity, ctx.expected_length, ctx.query_start, ctx.expected_generation, ctx.cold,
        qk.src0.address, append.src0.address, append.src1.address, append.dst.address,
        qk.dst.address, soft.dst.address, pv.dst.address)
    if steps != tuple(core.command_binding(op) for op in tuple(AttentionOperation)[:4]):
        raise ValueError('attention stages disagree on context or actual tensor bindings')
    block = tuple(parse_host_attention_block_descriptor(commands[i], records) for i in BLOCK_COMMAND_INDICES)
    validate_host_attention_block_bindings(projections, norms, ropes, core, block)
    used = []
    for c in commands:
        for root in (c.src0, c.src1, c.dst):
            if root != NULL_INDEX:
                used.extend(i for i, _ in validate_descriptor_chain(root, records))
    gate_root = validate_descriptor_chain(commands[4].src0, records)[-1][1].payload & NULL_INDEX
    used.extend(i for i, _ in validate_descriptor_chain(gate_root, records))
    if len(used) != CHAIN_RECORDS or len(set(used)) != CHAIN_RECORDS:
        raise ValueError('full block requires 296 distinct descriptor records')
    return projections, norms, ropes, core, block


def validate_carried_attention_block_commands(previous_commands, previous_records, current_commands, current_records):
    """Protect committed cache, FINAL output and twelve parameter identities.

    The caller must establish that previous command 22 actually committed.
    An append/PV/other producer ACK is insufficient. No reset/restore is implied.
    """
    previous = validate_host_attention_block_commands(previous_commands, previous_records)
    current = validate_host_attention_block_commands(current_commands, current_records)
    old_core, new_core = previous[3], current[3]
    old_params, _, _, old_cache = _resources(*previous)
    new_params, hidden, produced, new_cache = _resources(*current)
    if new_core.cold or new_cache != old_cache:
        raise ValueError('carried block must reuse exactly the committed cache allocation')
    if (new_core.expected_length, new_core.expected_generation) != (old_core.total_keys, old_core.expected_generation + 1):
        raise ValueError('carried block must use committed length/generation')
    if old_params != new_params:
        raise ValueError('carried block must preserve all eleven weight and trig identities')
    old_final = previous[4][-1].d
    _disjoint(tuple(t.span for t in (old_cache, old_final, hidden) + new_params + produced))
    return current
