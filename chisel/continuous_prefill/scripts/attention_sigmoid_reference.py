"""Independent integer/rational reference for the existing shared-scalar recipe.

No Torch, NumPy, RTL callbacks, or native floating-point arithmetic is used for
expected bits. Every primitive is rounded explicitly to IEEE FP32 RNE; the
sigmoid and final product have separate BF16 RNE boundaries. This checks the
frozen recipe, not official-model numerical acceptance or a full attention block.
"""
from fractions import Fraction
from pathlib import Path
import hashlib
import json

ONE = 0x3F800000
INV_LN2 = 0x3FB8AA3B
COEFFICIENTS = (0x3F800000, 0xBF317218, 0x3E75FDF0, 0xBD635847,
                0x3C1D955B, 0xBAAEC3FF, 0x39218489, 0xB77FE5FE)
SOURCE_SHA256 = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'


def finite(bits):
    return bits & 0x7F800000 != 0x7F800000


def power2(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def rational(bits):
    if not finite(bits):
        raise ValueError('nonfinite input')
    exponent = (bits >> 23) & 255
    significand = (bits & 0x7FFFFF) | (0x800000 if exponent else 0)
    value = significand * power2((exponent - 127 if exponent else -126) - 23)
    return -value if bits >> 31 else value


def nearest_even(value):
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + (2 * remainder > value.denominator or
                       (2 * remainder == value.denominator and quotient & 1))


def rounded_f32(value, zero_sign=0):
    if not value:
        return zero_sign << 31
    sign = 0x80000000 if value < 0 else 0
    value = abs(value)
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < power2(exponent):
        exponent -= 1
    if exponent < -126:
        return sign | nearest_even(value / power2(-149))
    significand = nearest_even(value / power2(exponent - 23))
    if significand == 0x1000000:
        significand >>= 1
        exponent += 1
    if exponent > 127:
        return sign | 0x7F800000
    return sign | ((exponent + 127) << 23) | (significand & 0x7FFFFF)


def add(a, b):
    return rounded_f32(rational(a) + rational(b), (a & b) >> 31)


def multiply(a, b):
    return rounded_f32(rational(a) * rational(b), (a ^ b) >> 31)


def divide(a, b):
    if not rational(b):
        raise ValueError('divide by zero')
    return rounded_f32(rational(a) / rational(b), (a ^ b) >> 31)


def bf16(bits):
    return ((bits + 0x7FFF + ((bits >> 16) & 1)) >> 16) & 0xFFFF


def exp_negative(gate):
    magnitude = gate & 0x7FFFFFFF
    if magnitude >= 0x42A00000:
        return 0
    scaled = multiply(magnitude, INV_LN2)
    k = int(rational(scaled))
    fraction = add(scaled, rounded_f32(Fraction(-k)))
    h = COEFFICIENTS[7]
    for coefficient in reversed(COEFFICIENTS[:7]):
        h = add(multiply(h, fraction), coefficient)
    return multiply(h, (127 - k) << 23)


def lane(gate_bf16, context_bf16):
    if not 0 <= gate_bf16 <= 0xFFFF or not 0 <= context_bf16 <= 0xFFFF:
        raise ValueError('BF16 storage required')
    gate, context = gate_bf16 << 16, context_bf16 << 16
    if not finite(gate) or not finite(context):
        raise ValueError('nonfinite gate/context')
    if gate >> 31 and gate & 0x7FFFFFFF >= 0x42A00000:
        raise ValueError('Unsupported: legal negative gate <= -80')
    steps = []

    def step(op, a, b, result):
        if not finite(result):
            raise ValueError('nonfinite arithmetic')
        steps.append(dict(op=op, a=a, b=b, result=result))
        return result

    e = step(4, gate, 0, exp_negative(gate))
    den = step(0, ONE, e, add(ONE, e))
    inv = step(2, ONE, den, divide(ONE, den))
    branch = e if gate >> 31 else ONE
    sigmoid = step(6, inv, branch, multiply(inv, branch))
    sigmoid_bf16 = bf16(sigmoid)
    product = step(6, sigmoid_bf16 << 16, context,
                   multiply(sigmoid_bf16 << 16, context))
    out = bf16(product)
    if not finite(out << 16):
        raise ValueError('nonfinite BF16 product')
    return dict(gate=gate_bf16, context=context_bf16, sigmoid=sigmoid_bf16,
                output=out, steps=steps)


def vectors():
    gates = [bf16(rounded_f32(Fraction((i % 19) - 9, 3))) for i in range(70)]
    contexts = [bf16(rounded_f32(Fraction((i % 13) - 6, 4))) for i in range(70)]
    special = [(0, 0x3F80), (0x8000, 0x8000), (1, 1), (0x8001, 0x8001),
               (0xC29F, 0x3F80), (0x42A0, 0x4000), (0x7F7F, 0xBF80),
               (0x3F80, 0x7F7F), (0xBF80, 0), (0, 3), (0x8000, 0x8003)]
    for index, (gate, context) in enumerate(special):
        gates[index], contexts[index] = gate, context
    return [lane(g, c) for g, c in zip(gates, contexts)]


def manifest():
    return dict(schema=1, scope='ISOLATED_OWNER_FROZEN_RECIPE_ONLY',
                official_source_sha256=SOURCE_SHA256, attention_width=2048,
                input_a='preserved BF16 gate', input_b='BF16 attention context',
                recipe_acceptance='EXACT_BITS', official_acceptance='UNASSIGNED',
                scalar_sequence=[4, 0, 2, 6, 6], values=vectors())


def main(argv=None):
    """Generate reproducible synthetic tests outside the tracked source tree."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    destination = args.output
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise ValueError('new absolute output path required')
    root = Path(__file__).resolve().parents[3]
    resolved = destination.resolve()
    if not resolved.is_relative_to(root / 'work') or resolved == root / 'work':
        raise ValueError('ignored work output required')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest(), indent=2) + '\n')
    print(json.dumps(dict(path=str(destination), values=70,
                         sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
