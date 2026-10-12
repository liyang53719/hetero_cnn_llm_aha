"""Raw Add0/Mul1 flags on the caller's one shared scalar service.

The integer primitives model separate binary32 RNE operations and HardFloat
tininess. No reference trace, result array, or second scalar instance is used.
Inherited Div2/Sqrt3/MulIeeeRne6 remain available to the input RMS owner.
ExpNegative4 reuses the same source-bound degree7 service for GQA softmax;
its internal primitive counts remain separate from accepted public requests.
"""
from dataclasses import dataclass

from heteronpu.rope_bf16_candidate import add_rne, mul_rne
from ...qwen35_gdn_prefill.rms_owner import ArithmeticFault, finite, require
from ...qwen35_gdn_prefill.conv.scalar import ConvScalar


OPCODES = {'add': 0, 'mul': 1, 'div': 2, 'sqrt': 3, 'exp_negative': 4, 'mul_ieee_rne': 6}
FATAL_FLAGS = 0x1E


@dataclass(frozen=True)
class RawScalarResult:
    bits: int
    flags: int
    error: bool = False
    flags_valid: bool = True


class NormRopeScalar(ConvScalar):
    """Inject this same instance into RMS, Norm256, partial64 RoPE and GQA.

    raw_op exposes the original flags even on a fatal result; op retains the
    existing exception-based API. Both routes count exactly one public call.
    """
    def raw_op(self, client, operation, a, b=0):
        require(self.client is client, 'arithmetic without exclusive scalar ownership')
        require(operation in ('add', 'mul'), 'raw flags require existing Add0/Mul1')
        require(all(type(v) is int and 0 <= v < 1 << 32 for v in (a, b)), 'FP32 raw-word domain')
        self.calls[operation] += 1
        bits, flags = (add_rne if operation == 'add' else mul_rne)(a, b)
        error = bool(flags & FATAL_FLAGS) or not all(finite(v) for v in (a, b, bits))
        return RawScalarResult(bits, flags, error)

    def op(self, client, operation, a, b=0):
        if operation not in ('add', 'mul'):
            return super().op(client, operation, a, b)
        result = self.raw_op(client, operation, a, b)
        if result.error:
            raise ArithmeticFault('legacy Add0/Mul1 fatal raw flags/nonfinite result')
        return result.bits
