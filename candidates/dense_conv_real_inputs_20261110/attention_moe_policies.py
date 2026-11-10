"""Exact payload-only encoders for common cold M128 runtime policies.

Return (kind8, payload72); caller links records with next24 and adds the
unchanged Record128 envelope. Metadata encoding is not hardware execution or
numerical verification. Does not generate weights, routing IDs or references.
Source: HostBlockCommandsV4.scala 878-995,1473-1485,1581-1584;
HostMoeWeightScanV4.scala HostMoeWeightRecordV4 and versionOK.
"""
NULL = 0xffffff
MATRIX_AUX = 0x004000040020ffffff
ATTENTION_ENVELOPES = {0: (0x41, 0), 1: (0x23, 0), 2: (0x33, 1), 3: (0x24, 2)}
MOE_SHAPES = ((2048, 256), (256, 2048, 512), (256, 2048, 512),
              (256, 512, 2048), (2048, 512), (2048, 512),
              (512, 2048), (2048, 1))
MOE_PADDED_SHARED_GATE_SHAPE = (2048, 32)

def _int(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in [{low}, {high}]')
    return value

def _root(value):
    return _int(value, 0, NULL - 1, 'non-null tensor root')

def _program(opcode, inputs=2):
    return (0x20, opcode | inputs << 16 | 1 << 24 | 5 << 32 | 5 << 36 | 16 << 40)

def cold_context():
    """v2 C128, expected length/query start/generation=0, cold+required."""
    return (0x26, 2 | 128 << 8 | 1 << 67 | 1 << 68)

def qknorm(role, gate_root=None, recipe=0xC1):
    """Q role0 requires separate writable Q-gate tensor; K role1 has none.

    Source supports C1/C2 at runtime. Caller selects the pinned arithmetic
    recipe, not a precision optimization. Cold base0/count128 only.
    """
    _int(role, 0, 1, 'Q/K role')
    if type(recipe) is not int or recipe not in (0xC1, 0xC2):
        raise ValueError('runtime QKNorm recipe must be C1 or C2')
    if role == 0:
        gate = _root(gate_root)
    else:
        if gate_root not in (None, NULL):
            raise ValueError('K normalization must not encode Q gate')
        gate = NULL
    return [_program(0x32), (0x24, 1 | role << 8 | 128 << 44 | recipe << 52), (0x25, gate)]

def rope(role, absolute_position=0):
    """Cold Q/K RoPE B1. Trig input is [>=128,64], BF16."""
    _int(role, 0, 1, 'Q/K role')
    _int(absolute_position, 0, 0, 'cold absolute position')
    return [_program(0x34), (0x24, 1 | role << 8 | 1 << 10 | 128 << 44 | 0xB1 << 52), (0x25, NULL)]

def attention_core(op):
    """Append0/QK1/Softmax2/PV3; terminal fence uses separate v3 helper.

    QK+Softmax+PV must be consecutive commands in checked fusion order.
    Their virtual score/probability allocations are DUT scratch, not inputs.
    """
    _int(op, 0, 3, 'attention op')
    prefix = []
    if op in (1, 3):
        n, k = (128, 256) if op == 1 else (256, 128)
        prefix = [(0x10, 128 | n << 16 | k << 32 | int(op == 1) << 59), (0x12, MATRIX_AUX)]
    elif op == 2:
        prefix = [_program(0x33, 1)]
    return prefix + [(0x24, 2 | op << 8 | 128 << 44 | (0xA1 << 52 if op else 0)), cold_context()]

def attention_output(role):
    """v3 op7: role0 sigmoid(Qgate)*context; role1 original hidden+O."""
    _int(role, 0, 1, 'attention output role')
    return [_program(0x30), (0x24, 3 | 7 << 8 | 128 << 44 | role << 60), cold_context()]

def attention_fence():
    """v3 terminal publication fence; operands KV, original hidden, final R2.

    Requires real completed block receipts/provenance and drained owners.
    Emitting this descriptor alone does not publish any successful result.
    """
    return [_program(0x30), (0x24, 3 | 4 << 8 | 128 << 44), cold_context()]

def moe_manifest_payload(role, tensor_root, padded_shared_gate_root=None):
    """One of eight ascending roles; parent links chain with terminal role7.

    Role7 v2 logical [2048,1] plus distinct physical [2048,32] layout1.
    Materializer must put the logical column in physical column0 and zero
    columns1..31. Metadata does not verify these bytes or authorize aliases.
    """
    _int(role, 0, 7, 'MoE role')
    logical = _root(tensor_root)
    if role == 7:
        physical = _root(padded_shared_gate_root)
        if physical == logical:
            raise ValueError('logical and physical shared-gate roots must differ')
        return (0x60, 2 | role << 8 | logical << 11 | physical << 35 | 1 << 59)
    if padded_shared_gate_root is not None:
        raise ValueError('only role7 has a physical padded tensor')
    return (0x60, 1 | role << 8 | logical << 11)
