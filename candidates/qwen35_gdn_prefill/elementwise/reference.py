"""Independent NumPy pointwise recipe and opt-in original Torch diagnostics.

No owner or scalar implementation is imported or called. Fixed arithmetic is
array FP32 with one RNE per node; SiLU rounds to BF16 before the up product.
Native diagnostics evaluate the unchanged official AST pointwise expressions
at full production width. They are not the complete decoder or MLP projections,
and introduce no acceptance threshold. The complete block gate belongs to the
fullblock native audit, separately from fixed-recipe bitwise agreement.
"""
import ast
import ctypes
import hashlib
import math
import os
from pathlib import Path
import platform
import subprocess
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnElementwiseOwner.scala'
OWNER_SHA = '01b394526f75b9732c3e605652c64f3968851aca97258a3a640bc056de1f2fe3'
SCALAR_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala'
SCALAR_SHA = '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5'
SOURCE = 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'
SOURCE_SHA = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
TRANSFORMERS_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'


def require(ok, detail):
    if not ok:
        raise ValueError('independent Elementwise reference: ' + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _operation(op):
    if isinstance(op, int) and not isinstance(op, bool) and op in (0, 1):
        return int(op)
    require(type(op) is str and op in ('Add', 'SiluMul'), 'only Add=0 and SiluMul=1 operations')
    return ('Add', 'SiluMul').index(op)


def _inputs(a_raw, b_raw, rows, op, row_width, test_geometry):
    op = _operation(op)
    production_width = (1024, 3584)[op]
    width = production_width if row_width is None else row_width
    require(type(rows) is int and 1 <= rows <= 128 and type(test_geometry) is bool and
            type(width) is int and 0 < width <= production_width and width % 32 == 0 and
            (width == production_width or test_geometry),
            'M1..128 / full production width or explicit reduced 32-element test geometry')
    require(all(type(raw) is bytes and len(raw) == rows * width * 2 for raw in (a_raw, b_raw)),
            'complete BF16 input shapes')
    arrays = tuple(_float(np.frombuffer(raw, '<u2').reshape(rows, width)) for raw in (a_raw, b_raw))
    require(all(np.isfinite(x).all() for x in arrays), 'nonfinite BF16 input')
    return (*arrays, op, width)


def _float(bits):
    return (np.asarray(bits, dtype='<u2').astype('<u4') << 16).view('<f4')


def _bf16(values):
    require(np.isfinite(values).all(), 'nonfinite FP32 conversion input')
    raw = np.asarray(values, dtype='<f4').view('<u4')
    rounded = ((raw + np.uint32(0x7fff) + ((raw >> 16) & 1)) >> 16).astype('<u2')
    require(np.isfinite(_float(rounded)).all(), 'BF16 conversion overflow')
    return rounded


def _environment():
    libc = ctypes.CDLL(None)
    libc.fegetround.restype = ctypes.c_int
    require(libc.fegetround() == 0, 'FE_TONEAREST required')
    tiny = np.array([1, 0x00800000, 0x80000000], dtype='<u4').view('<f4')
    with np.errstate(all='ignore'):
        require(int(np.add(tiny[0], tiny[0], dtype=np.float32).view('<u4')) == 2 and
                int(np.multiply(tiny[1], np.float32(.5), dtype=np.float32).view('<u4')) == 0x00400000 and
                int(np.add(tiny[2], tiny[2], dtype=np.float32).view('<u4')) == 0x80000000,
                'gradual underflow and signed zero required')


def _node(operation, left, right, *, legacy=False):
    a, b = np.broadcast_arrays(np.asarray(left, dtype=np.float32), np.asarray(right, dtype=np.float32))
    require(np.isfinite(a).all() and np.isfinite(b).all(), 'nonfinite public FP32 operand')
    with np.errstate(all='ignore'):
        out = {'mul': np.multiply, 'add': np.add, 'div': np.divide}[operation](a, b, dtype=np.float32)
    require(np.isfinite(out).all(), 'public FP32 invalid/div0/overflow')
    if legacy:
        tiny = ((out.view('<u4') & 0x7f800000) == 0) & (a != 0) & (b != 0)
        for av, bv, rv in zip(a[tiny], b[tiny], out[tiny]):
            an, ad = float(av).as_integer_ratio()
            bn, bd = float(bv).as_integer_ratio()
            rn, rd = float(rv).as_integer_ratio()
            exact = ((an * bd + bn * ad) * rd == rn * ad * bd if operation == 'add' else
                     an * bn * rd == rn * ad * bd if operation == 'mul' else
                     an * bd * rd == rn * ad * bn)
            require(exact, 'legacy public ' + operation + ' rejects inexact underflow')
    return out


def _exp_negative(values):
    """Independent degree-7 recipe, each of 9 mul + 8 add separately rounded."""
    magnitude = np.abs(np.asarray(values, dtype=np.float32))
    coefficients = np.array([math.pow(-math.log(2), i) / math.factorial(i)
                             for i in range(8)], dtype=np.float32)
    with np.errstate(all='ignore'):
        scaled = np.multiply(magnitude, np.float32(1 / math.log(2)), dtype=np.float32)
        active = magnitude < np.float32(80)
        z = np.where(active, scaled, np.float32(0))
        k = z.astype(np.int32)
        fraction = np.add(z, -k.astype(np.float32), dtype=np.float32)
        accumulator = np.full_like(z, coefficients[7])
        for coefficient in coefficients[6::-1]:
            product = np.multiply(accumulator, fraction, dtype=np.float32)
            accumulator = np.add(product, coefficient, dtype=np.float32)
        scale = ((127 - k).astype('<u4') << 23).view('<f4')
        result = np.multiply(accumulator, scale, dtype=np.float32)
    return np.where(active, result, np.float32(0))


def _sources(root):
    root = Path(root)
    original = subprocess.run(['git', 'show', 'HEAD:' + OWNER_SOURCE], cwd=root,
                              capture_output=True, check=True, timeout=10).stdout
    require(sha(original) == OWNER_SHA, 'committed owner source drift')
    hashes = {'HEAD:' + OWNER_SOURCE: OWNER_SHA, SCALAR_SOURCE: SCALAR_SHA, SOURCE: SOURCE_SHA}
    for name in (SCALAR_SOURCE, SOURCE):
        require(sha((root / name).read_bytes()) == hashes[name], 'source drift: ' + name)
    return hashes


def fixed_elementwise(a_raw, b_raw, rows, op, row_width=None, *, test_geometry=False, root=ROOT):
    """Return (packed BF16 bytes, identity); exact recipe, not native acceptance."""
    a, b, op, width = _inputs(a_raw, b_raw, rows, op, row_width, test_geometry)
    _environment()
    sources = _sources(root)
    if op == 0:
        result = _node('add', a, b, legacy=True)
    else:
        require(not np.any(a <= np.float32(-80)), 'Unsupported negative SiLU <= -80')
        exponential = _exp_negative(a)
        denominator = _node('add', np.float32(1), exponential, legacy=True)
        inverse = _node('div', np.float32(1), denominator, legacy=True)
        sigmoid = _node('mul', inverse, np.where(np.signbit(a), exponential, np.float32(1)))
        activated = _bf16(_node('mul', sigmoid, a))
        result = _node('mul', _float(activated), b)
    raw = _bf16(result).tobytes()
    return raw, dict(scope='INDEPENDENT_NUMPY_FIXED_ELEMENTWISE_RECIPE',
        operation=('Add', 'SiluMul')[op], shape=[rows, width], test_geometry=test_geometry,
        production_geometry=width == (1024, 3584)[op], arbitrary_tail_supported=False,
        source_sha256=sources, implementation_sha256=sha(Path(__file__).read_bytes()),
        numpy=np.__version__, input_sha256=[sha(a_raw), sha(b_raw)], output_sha256=sha(raw),
        arithmetic='BF16_Add' if op == 0 else 'FP32_SiLU_BF16_boundary_FP32_product_BF16_boundary',
        reference_only=True, scalar_or_owner_called=False, native_acceptance=False,
        native_numeric_diagnostics_executed=False, full_official_block_executed=False,
        state_committed=False, history_committed=False, generation_advanced=False,
        rtl_executed=False, hardware_cycles=None)


def _official_expressions(source):
    """Compile unchanged original expressions, with projection outputs supplied.

    SiLU keeps the entire original multiply AST. Only its gate_proj/up_proj
    receivers return the already supplied tensors; no linear is simulated.
    """
    require(sha(source) == SOURCE_SHA, 'pinned official source hash changed')
    classes = {node.name: node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)}
    mlp = next(n for n in classes['Qwen3_5MLP'].body if isinstance(n, ast.FunctionDef) and n.name == 'forward')
    call = next(n.value for n in mlp.body if isinstance(n, ast.Assign))
    require(ast.unparse(call) == 'self.down_proj(self.act_fn(self.gate_proj(x)) * self.up_proj(x))',
            'official MLP expression changed')
    decoder = classes['Qwen3_5DecoderLayer']
    residuals = [n.value for n in ast.walk(decoder) if isinstance(n, ast.Assign) and
                 isinstance(n.value, ast.BinOp) and ast.unparse(n.value) == 'residual + hidden_states']
    require(len(residuals) == 2, 'official residual expressions changed')
    return (compile(ast.Expression(residuals[0]), SOURCE, 'eval'),
            compile(ast.Expression(call.args[0]), SOURCE, 'eval'))


def native_elementwise(a_raw, b_raw, rows, op, *, root=ROOT):
    """Opt-in original Torch BF16 expression at [1,M,1024/3584], no threshold.

    This function is never invoked by lightweight tests. No owner, Dense,
    checkpoint, or complete official block is executed here.
    """
    _, _, op, width = _inputs(a_raw, b_raw, rows, op, None, False)
    require(os.environ.get('ATEN_CPU_CAPABILITY') == 'default',
            'set ATEN_CPU_CAPABILITY=default before importing Torch')
    import torch
    require(torch.__version__.split('+')[0] == '2.10.0', 'frozen Torch 2.10.0 required')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    capability = torch.backends.cpu.get_cpu_capability()
    require(capability in ('NO AVX', 'DEFAULT'), 'frozen Torch DEFAULT CPU backend required')
    expressions = _official_expressions((Path(root) / SOURCE).read_bytes())
    a, b = (torch.frombuffer(bytearray(raw), dtype=torch.bfloat16).reshape(1, rows, width)
            for raw in (a_raw, b_raw))
    receiver = SimpleNamespace(gate_proj=lambda _: a, up_proj=lambda _: b, act_fn=torch.nn.functional.silu)
    with torch.inference_mode():
        output = eval(expressions[op], {'__builtins__': {}},
                      dict(residual=a, hidden_states=b, self=receiver, x=None))
    require(list(output.shape) == [1, rows, width] and output.dtype == torch.bfloat16 and
            torch.isfinite(output).all().item(), 'nonfinite or changed official pointwise result')
    raw = output.contiguous().view(torch.uint16).numpy().astype('<u2').tobytes()
    return raw, dict(scope='ORIGINAL_TORCH_POINTWISE_EXPRESSION_DIAGNOSTIC',
        operation=('Add', 'SiluMul')[op], shape=[1, rows, width], official_source_sha256=SOURCE_SHA,
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        torch=torch.__version__, torch_git=torch.version.git_version, cpu_capability=capability,
        machine=platform.machine(), threads=torch.get_num_threads(), deterministic=True,
        autocast=False, input_sha256=[sha(a_raw), sha(b_raw)], output_sha256=sha(raw),
        native_numeric_diagnostics_executed=True, native_acceptance=False, acceptance_threshold=None,
        full_official_block_executed=False, projections_executed=False, scalar_or_owner_called=False,
        history_committed=False, state_committed=False, generation_advanced=False, rtl_executed=False)


def compare_bf16(actual, expected):
    """Diagnostics only: signed-zero differences stay visible; no invented gate."""
    require(type(actual) is bytes and type(expected) is bytes and len(actual) == len(expected)
            and len(actual) > 0 and len(actual) % 2 == 0, 'same complete BF16 comparison shape')
    a, b = np.frombuffer(actual, '<u2'), np.frombuffer(expected, '<u2')
    fa, fb = _float(a), _float(b)
    require(np.isfinite(fa).all() and np.isfinite(fb).all(), 'nonfinite BF16 comparison')
    def ordered(bits):
        values = bits.astype(np.int32)
        return np.where(values & 0x8000, 0x8000 - (values & 0x7fff), 0x8000 + values)
    ulp = np.abs(ordered(a) - ordered(b))
    delta = np.abs(fa.astype(np.float64) - fb.astype(np.float64))
    different = a != b
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(different)),
                numerical_mismatches=int(np.count_nonzero(ulp)), max_bf16_ulp=int(ulp.max()),
                max_abs=float(delta.max()), mean_abs=float(delta.mean()),
                signed_zero_only_mismatches=int(np.count_nonzero(different & (ulp == 0))),
                first_bit_mismatch=int(np.flatnonzero(different)[0]) if different.any() else None,
                actual_sha256=sha(actual), expected_sha256=sha(expected), acceptance_threshold=None)
