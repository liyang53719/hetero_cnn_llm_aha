"""Cold exact callbacks using the existing integer-rational FP32 reference.

Only named definitions are loaded; no NumPy, native library or RTL is loaded.
These are software reference callbacks, never an implemented physical ALU.
"""
import ast
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def check_sources():
    pins = json.loads((HERE / 'source_pins.json').read_text())
    for path, expected in pins['sources'].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError('frozen source drift: ' + path)
    return pins


def definitions(path, names, namespace):
    body = []
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            body.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in names for t in node.targets):
            body.append(node)
    if len(body) != len(names):
        raise ValueError('original reference definitions missing')
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


check_sources()
_reference = definitions(ROOT / 'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py',
    ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf'), {'Fraction': Fraction})
exact, rn, ref_add, ref_mul, ref_div, ref_bf = (
    _reference[x] for x in ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf'))
_recipe = definitions(ROOT / 'candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py',
    ('EXP_COEFFICIENTS', 'LOG2_RECIPROCAL'), {})
COEFFICIENTS = _recipe['EXP_COEFFICIENTS']
LOG2_RECIPROCAL = _recipe['LOG2_RECIPROCAL']


def finite(bits):
    return bits & 0x7f800000 != 0x7f800000


def word(bits):
    if type(bits) is not int or not 0 <= bits < 1 << 32:
        raise ValueError('canonical FP32 word required')
    return bits


@dataclass(frozen=True)
class Primitive:
    bits: int
    flags: int

    def __post_init__(self):
        word(self.bits)
        if type(self.flags) is not int or not 0 <= self.flags < 32:
            raise ValueError('canonical HardFloat-position flags required')


def precision24_tiny(number):
    """HardFloat after-rounding tininess before exponent-range clamping.

    Unlike checking only the final exponent, this includes a tiny precision24
    value that later rounds to the minimum normal at the subnormal boundary.
    """
    number = abs(number)
    if not number:
        return False
    n, d = number.numerator, number.denominator
    e = n.bit_length() - d.bit_length()
    if number < Fraction(2) ** e:
        e -= 1
    shift = 23 - e
    n <<= max(shift, 0)
    d <<= max(-shift, 0)
    q, r = divmod(n, d)
    q += 2 * r > d or (2 * r == d and q & 1)
    if q == 1 << 24:
        e += 1
    return e < -126


def primitive(operation, a, b):
    """Separate FP32 RNE nodes; finite input callback, including overflow bits."""
    word(a); word(b)
    if not finite(a) or not finite(b):
        raise ValueError('source admission must reject nonfinite operands first')
    x, y = exact(a), exact(b)
    if operation == 'add':
        mathematical, bits = x + y, ref_add(a, b)
    elif operation == 'mul':
        mathematical, bits = x * y, ref_mul(a, b)
    elif operation == 'div':
        if not y:
            return Primitive(0x7fc00000, 16) if not x else Primitive(
                ((a ^ b) & 0x80000000) | 0x7f800000, 8)
        mathematical, bits = x / y, ref_div(a, b)
    else:
        raise ValueError('unsupported arithmetic node')
    if not finite(bits):
        return Primitive(bits, 5)
    inexact = exact(bits) != mathematical
    flags = int(inexact) | (2 if inexact and precision24_tiny(mathematical) else 0)
    return Primitive(bits, flags)
