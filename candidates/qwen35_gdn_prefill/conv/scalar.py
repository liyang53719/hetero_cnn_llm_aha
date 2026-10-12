"""GDN op1/op4 extension of the one caller-owned FP32 scalar service.

No second arithmetic resource or instance is allocated. ExpNegative reproduces
BlockFloat's separately rounded nodes, including its ignored internal flags;
that policy is neither public legacy Mul nor public MulIeeeRne opcode 6.
"""
from collections import Counter

import numpy as np

from ..rms_owner import SharedScalar, ArithmeticFault, finite, value, word, require


OPCODES = {'add': 0, 'mul': 1, 'div': 2, 'sqrt': 3,
           'exp_negative': 4, 'mul_ieee_rne': 6}
EXP_COEFFICIENTS = (0x3f800000, 0xbf317218, 0x3e75fdf0, 0xbd635847,
                    0x3c1d955b, 0xbaaec3ff, 0x39218489, 0xb77fe5fe)
LOG2_RECIPROCAL = 0x3fb8aa3b


class ConvScalar(SharedScalar):
    """One shared service; the caller also passes this instance to other owners.

    Existing Add/Div/Sqrt/op6 calls retain their original implementation and
    counters. Legacy Mul rejects inexact underflow; opcode 6 accepts it.
    ExpNegative's internal primitive counts are separate from public requests.
    """
    def __init__(self):
        super().__init__()
        self.internal_calls = Counter()

    def _exp_node(self, operation, a, b):
        self.internal_calls[operation] += 1
        with np.errstate(all='ignore'):
            fn = np.add if operation == 'add' else np.multiply
            return word(fn(value(a), value(b), dtype=np.float32))

    def op(self, client, operation, a, b=0):
        if operation not in ('mul', 'exp_negative'):
            return super().op(client, operation, a, b)
        require(self.client is client, 'arithmetic without exclusive scalar ownership')
        require(all(type(v) is int and 0 <= v < 1 << 32 for v in (a, b)), 'FP32 raw-word domain')
        self.calls[operation] += 1
        if not finite(a) or not finite(b):
            raise ArithmeticFault('nonfinite scalar input')
        if operation == 'mul':
            with np.errstate(all='ignore'):
                bits = word(np.multiply(value(a), value(b), dtype=np.float32))
            if not finite(bits):
                raise ArithmeticFault('legacy Mul invalid/overflow/nonfinite result')
            if bits & 0x7f800000 == 0:
                an, ad = float(value(a)).as_integer_ratio()
                bn, bd = float(value(b)).as_integer_ratio()
                rn, rd = float(value(bits)).as_integer_ratio()
                if an * bn * rd != rn * ad * bd:
                    raise ArithmeticFault('legacy Mul rejects inexact underflow')
            return bits
        magnitude = a & 0x7fffffff
        # Source expScale still executes before the >=80 zero selection.
        z = self._exp_node('mul', magnitude, LOG2_RECIPROCAL)
        if magnitude >= 0x42a00000:
            return 0
        k = int(value(z))
        fraction = self._exp_node('add', z, word(float(k)) ^ 0x80000000)
        accumulator = EXP_COEFFICIENTS[7]
        for coefficient in reversed(EXP_COEFFICIENTS[:7]):
            product = self._exp_node('mul', accumulator, fraction)
            accumulator = self._exp_node('add', product, coefficient)
        return self._exp_node('mul', accumulator, (127 - k) << 23)
