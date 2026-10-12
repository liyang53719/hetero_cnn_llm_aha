"""Original BlockScalarFloat ExpNegative on the existing scalar resource.

Every mul/add below is a separate FP32 rounding node. This helper allocates
no ALU/SFU and accepts no reference tensor. Source identity is checked by the
shared ScalarService (BlockFloat.scala and the original qwen2_block.cpp).
Internal exp flags are deliberately ignored, as in the original scalar FSM;
the enclosing Attention Add/Mul/Div still use legacy_scalar's fatal UF policy.
"""
from ..ffn_public.prefix_arithmetic import ArithmeticFault, finite, value, word


# F32.lit(pow(-log(2), i) / i!), i=0..7, from BlockFloat.scala's ROM.
EXP_COEFFICIENTS = (0x3f800000, 0xbf317218, 0x3e75fdf0, 0xbd635847,
                    0x3c1d955b, 0xbaaec3ff, 0x39218489, 0xb77fe5fe)
LOG2_RECIPROCAL = 0x3fb8aa3b


def exp_negative(scalar, client, a, b=0):
    """Return exp(-abs(a)) using only the caller's acquired ScalarService.

    b is unused by ExpNegative but validated by the source request admission.
    FP32-to-integer truncation is exact here: the cutoff bounds z below 116.
    At/above 80, the source expScale ALU still runs, then selects literal zero.
    Primitive counts therefore include that actual software mul call.
    """
    if scalar.client is not client:
        raise ValueError('ExpNegative without exclusive scalar ownership')
    if any(type(x) is not int or not 0 <= x < 1 << 32 for x in (a, b)):
        raise ValueError('ExpNegative requires FP32 words')
    if not finite(a) or not finite(b):
        raise ArithmeticFault('BlockScalarFloat rejects nonfinite ExpNegative input')
    magnitude = a & 0x7fffffff
    z = scalar.op(client, 'mul', magnitude, LOG2_RECIPROCAL, policy='vector')
    if magnitude >= 0x42a00000:
        return 0
    k = int(value(z))
    fraction = scalar.op(client, 'add', z, word(float(k)) ^ 0x80000000,
                         policy='vector')
    accumulator = EXP_COEFFICIENTS[7]
    for index in range(6, -1, -1):
        product = scalar.op(client, 'mul', accumulator, fraction, policy='vector')
        accumulator = scalar.op(client, 'add', product, EXP_COEFFICIENTS[index],
                                policy='vector')
    return scalar.op(client, 'mul', accumulator, (127 - k) << 23, policy='vector')
