"""Explicit Softplus7 option on the caller's ONE shared ConvScalar service.

This maps BlockFloat.scala's enableSoftplus path, with separate FP32 RNE at
every node. Its internal operations accept finite underflow, but invalid,
division by zero, overflow and nonfinite results fail. No log/SFU, exp oracle,
second scalar instance, or change to any existing public opcode is introduced.
"""
from collections import Counter

import numpy as np

from ..conv.scalar import ConvScalar, EXP_COEFFICIENTS, LOG2_RECIPROCAL
from ..conv.scalar import OPCODES as CONV_OPCODES
from ..rms_owner import ArithmeticFault, finite, require, value, word


OPCODES = dict(CONV_OPCODES, softplus=7)
SOFT_COEFFICIENTS = (0x3f800000, 0x3eaaaaab, 0x3e4ccccd, 0x3e124925,
                     0x3de38e39, 0x3dba2e8c, 0x3d9d89d9, 0x3d888889)


class PrepScalar(ConvScalar):
    """Pass this same instance to RMS, Conv, prep and subsequent owners.

    Like the source, Softplus7 is disabled unless explicitly enabled. Public
    request counts and compound-internal node counts remain separate.
    """
    def __init__(self, *, enable_softplus=False):
        require(type(enable_softplus) is bool, 'explicit Softplus enable flag')
        super().__init__()
        self.enable_softplus = enable_softplus
        self.soft_internal_calls = Counter()

    def _soft_node(self, operation, a, b):
        self.soft_internal_calls[operation] += 1
        with np.errstate(all='ignore'):
            fn = {'add': np.add, 'mul': np.multiply, 'div': np.divide}[operation]
            bits = word(fn(value(a), value(b), dtype=np.float32))
        if not finite(bits):
            raise ArithmeticFault('Softplus internal invalid/div0/overflow/nonfinite result')
        return bits

    def op(self, client, operation, a, b=0):
        if operation != 'softplus':
            return super().op(client, operation, a, b)
        require(self.client is client, 'arithmetic without exclusive scalar ownership')
        require(all(type(v) is int and 0 <= v < 1 << 32 for v in (a, b)), 'FP32 raw-word domain')
        self.calls[operation] += 1
        if not self.enable_softplus or not finite(a) or not finite(b):
            raise ArithmeticFault('Softplus7 disabled or nonfinite scalar input')
        magnitude = a & 0x7fffffff
        if a >> 31 and magnitude >= 0x42a00000:
            raise ArithmeticFault('Softplus source domain rejects x <= -80')
        if not a >> 31 and a > 0x41a00000:  # source x > 20, not >= 20
            return a

        # expScale/Floor/Fraction/Mul/Add/Finish; Softplus checks each node's
        # severe flags, unlike the standalone ExpNegative opcode's policy.
        z = self._soft_node('mul', magnitude, LOG2_RECIPROCAL)
        k = int(value(z))
        fraction = self._soft_node('add', z, word(float(k)) ^ 0x80000000)
        exponential = EXP_COEFFICIENTS[7]
        for coefficient in reversed(EXP_COEFFICIENTS[:7]):
            product = self._soft_node('mul', exponential, fraction)
            exponential = self._soft_node('add', product, coefficient)
        exponential = self._soft_node('mul', exponential, (127 - k) << 23)

        denominator = self._soft_node('add', word(2), exponential)
        y = self._soft_node('div', exponential, denominator)
        square = self._soft_node('mul', y, y)
        horner = SOFT_COEFFICIENTS[7]
        for coefficient in reversed(SOFT_COEFFICIENTS[:7]):
            product = self._soft_node('mul', horner, square)
            horner = self._soft_node('add', product, coefficient)
        doubled = self._soft_node('mul', word(2), y)
        logarithm = self._soft_node('mul', doubled, horner)
        return self._soft_node('add', 0 if a >> 31 else a, logarithm)
