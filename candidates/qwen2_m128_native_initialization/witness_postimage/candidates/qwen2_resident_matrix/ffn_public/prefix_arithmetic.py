"""Strict FP32 primitives for the original Qwen2 v0 prefix recipe.

This is a serialized *software* resource, not an extra hardware ALU, SFU,
Matrix instance, simulator, or latency estimate. The owner retains the source
algorithm and calls one primitive per source rounding node. NumPy scalar ufuncs
execute FP32 add/mul/div/sqrt without contraction; bf() is the pinned C++ RNE
helper, including its nonfinite behavior. There is no reference-output API.
"""
from collections import Counter
import ctypes
import hashlib
from pathlib import Path
import struct

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SCALA_DIR = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
# V3 active runtime guard: reviewed f16 default-disabled borrower/loan path.
# Physical Matrix, arithmetic, and modeled protocol are unchanged.
# Historical source_pins/receipts remain frozen; no old result is inherited.
SOURCE_HASHES = {
    'Qwen2Block.scala': '9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4',
    'QwenOwnerProtocol.scala': '7f2b4a623b61b6e68478b2310d441ed04ccde1cd5490cb22205113f907b7974d',
    'HostBlockCommands.scala': '68749c376fffeaed47a2b2965ec7e3af594b5409c7cd08d31c16535d75073757',
    'ElementwiseMemoryEngine.scala': 'cb8a338051cce94dda613603df892bd0f43b6ea62423ad1f9d28b24f98b73845',
    'Protocol.scala': '5c94def481dede0195f989608c1827ded32f2d83c752617945695f7d82f64783',
    'BlockWritebackFence.scala': '70e0303640904dd4044d6f5f61231b9766816da68cc71dbd58aa464a00a11054',
    'BlockFloat.scala': '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
}
ALU_SOURCE = 'integration/gemmini/EmitHeteroFP32Alu.scala'
ALU_SHA256 = '83fb6b55fe4362b58ddf740f7bfccd16f86779bda68e2e6e879052749cad88b1'
NATIVE_ACCEPTANCE = 'UNCHANGED_FAIL_POLICY_PENDING'


def source_identity(root=ROOT, *, enable_h2048_rms_borrower=False,
                    external_elementwise_loan=False, committed_source_witness=None,
                    committed_source_manifest=None):
    """Use the existing extraction guard; refuse drift in either arithmetic or IO."""
    if enable_h2048_rms_borrower is not False or external_elementwise_loan is not False:
        raise ValueError('source review requires the original default-disabled borrower/loan profile')
    from scripts.qwen2_block_recipe_model import extract_sources
    root = Path(root)
    if committed_source_witness is None and committed_source_manifest is None:
        _, _, recipe = extract_sources(root)
    else:
        _, _, recipe = extract_sources(root, committed_source_witness=committed_source_witness,
                                       committed_source_manifest=committed_source_manifest)
    found = {}
    for name, expected in SOURCE_HASHES.items():
        relative = SCALA_DIR + name
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('prefix source changed; explicit review required: ' + relative)
        found[relative] = actual
    actual = hashlib.sha256((root / ALU_SOURCE).read_bytes()).hexdigest()
    if actual != ALU_SHA256:
        raise ValueError('prefix ALU source changed; explicit review required')
    found[ALU_SOURCE] = actual
    return dict(recipe=recipe, control_source_sha256=found,
                source_version='qwen2-prefix-source-guard-v3',
                source_base_commit='f16df50adfb0f1f4bc668c517a2e29accffe6753',
                source_commit=None, historical_results_inherited=False,
                borrower_enabled=False, elementwise_loan_enabled=False,
                numerical_policy='default-v0-original-ordered-recipe',
                native_acceptance=NATIVE_ACCEPTANCE,
                hardware_simulation=False, model_ticks_are_hardware_cycles=False)


def word(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def value(bits):
    return np.float32(struct.unpack('<f', struct.pack('<I', bits))[0])


def finite(bits):
    return bits & 0x7f800000 != 0x7f800000


def bf(bits):
    if not finite(bits):
        return bits
    return ((bits + 0x7fff + ((bits >> 16) & 1)) & 0xffffffff) & 0xffff0000


class ArithmeticFault(Exception):
    """Original BlockScalarFloat fatal policy, never a changed FP32 recipe."""


def tiny_inexact(operation, a, b, result):
    """Exact rational comparison only when the rounded result is tiny.

    HardFloat uses tininess_afterRounding: UF requires both a tiny rounded
    result and inexact rounding. Integer cross-products avoid host FTZ flags,
    float64 division rounding, and accidental rejection of exact subnormals.
    """
    if result & 0x7f800000:
        return False
    an, ad = float(value(a)).as_integer_ratio()
    bn, bd = float(value(b)).as_integer_ratio()
    rn, rd = float(value(result)).as_integer_ratio()
    if operation == 'add':
        return (an * bd + bn * ad) * rd != rn * ad * bd
    if operation == 'mul':
        return an * bn * rd != rn * ad * bd
    if operation == 'div':
        return an * bd * rd != rn * ad * bn
    if operation == 'sqrt':
        return rn * rn * ad != an * rd * rd
    return False


class ScalarService:
    """One shared exclusive software arithmetic service across serial owners.

    The claim is resource serialization, not correspondence between Python
    arrays and allocated physical SRAM banks. Counters are observed software
    primitive calls and carry no hardware throughput or clock implication.
    """
    def __init__(self, *, committed_source_witness=None, committed_source_manifest=None):
        if committed_source_witness is None and committed_source_manifest is None:
            self.identity = source_identity()
        else:
            self.identity = source_identity(committed_source_witness=committed_source_witness,
                                            committed_source_manifest=committed_source_manifest)
        self.client = None
        self.calls = Counter()
        self._check_environment()

    @staticmethod
    def _check_environment():
        libc = ctypes.CDLL(None)
        libc.fegetround.restype = ctypes.c_int
        if libc.fegetround() != 0:
            raise ValueError('prefix FP32 arithmetic requires FE_TONEAREST')
        with np.errstate(all='ignore'):
            probes = (
                (word(np.add(value(1), value(1), dtype=np.float32)), 2),
                (word(np.multiply(value(1), value(0x3f800000), dtype=np.float32)), 1),
                (word(np.multiply(value(0x00800000), value(0x3f000000), dtype=np.float32)), 0x00400000),
                (word(np.add(value(0x80000000), value(0x80000000), dtype=np.float32)), 0x80000000),
                (word(np.add(value(0x80000000), value(0), dtype=np.float32)), 0),
            )
        if any(actual != expected for actual, expected in probes):
            raise ValueError('prefix FP32 signed-zero/gradual-underflow probes failed')

    def acquire(self, client):
        if self.client is not None:
            return False
        self.client = client
        return True

    def release(self, client):
        if self.client is not client:
            raise ValueError('scalar resource released by a different owner')
        self.client = None

    def op(self, client, operation, a, b=0, *, policy='vector'):
        """Preserve each source path's policy while sharing software execution.

        legacy_scalar is BlockScalarFloat Add/Mul/Div/Sqrt: nonfinite inputs,
        invalid/div0/overflow and inexact underflow are fatal; inexact alone
        and exact subnormals are accepted. vector is Qwen2Block's vout path,
        where exceptionFlags are not connected and finite stores are checked
        by the owner. It is not the new MulIeeeRne scalar opcode.
        """
        if self.client is not client:
            raise ValueError('scalar operation without exclusive ownership')
        if policy not in ('vector', 'legacy_scalar'):
            raise ValueError('unsupported original arithmetic policy')
        self.calls[operation] += 1
        if operation == 'bf':
            return bf(a)
        if policy == 'legacy_scalar' and (not finite(a) or not finite(b)):
            raise ArithmeticFault('BlockScalarFloat rejects nonfinite input')
        with np.errstate(all='ignore'):
            x, y = value(a), value(b)
            if operation == 'add':
                result = np.add(x, y, dtype=np.float32)
            elif operation == 'mul':
                result = np.multiply(x, y, dtype=np.float32)
            elif operation == 'div':
                result = np.divide(x, y, dtype=np.float32)
            elif operation == 'sqrt':
                result = np.sqrt(x, dtype=np.float32)
            else:
                raise ValueError('unsupported scalar operation ' + str(operation))
        bits = word(result)
        if policy == 'legacy_scalar':
            if not finite(bits):
                raise ArithmeticFault('BlockScalarFloat invalid/div0/overflow/nonfinite result')
            if tiny_inexact(operation, a, b, bits):
                raise ArithmeticFault('BlockScalarFloat rejects inexact underflow')
        return bits
