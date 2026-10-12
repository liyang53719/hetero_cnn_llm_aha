"""Independent numeric oracles at the FP32[M,6400] prepared boundary.

The fixed oracle uses NumPy FP32 nodes, original ExpNegative, and true chunk64
forward solves. It never imports the candidate owner, Vector16, or PrepScalar.
The conditional native oracle executes the pinned original chunk suffix after
input preparation, on all 16 heads. It is not an official whole-layer run.
Only fixed byte equality is an acceptance gate; native metrics are diagnostic.
"""
from __future__ import annotations

import ast
import copy
import ctypes
import hashlib
import math
import os
from pathlib import Path
import platform

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'
SOURCE_SHA = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'
SOURCE_HASHES = {
    SOURCE: SOURCE_SHA,
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala':
        '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
    'integration/gemmini/EmitHeteroFP32Alu.scala':
        '83fb6b55fe4362b58ddf740f7bfccd16f86779bda68e2e6e879052749cad88b1',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/ElementwiseMemoryEngine.scala':
        'cb8a338051cce94dda613603df892bd0f43b6ea62423ad1f9d28b24f98b73845',
}
CHUNK, HEADS, WIDTH, CORE = 64, 16, 128, 6400

# This explicit binding replaces only the source's preparation prefix. Inputs
# are already [1,H,M,D] FP32, normalized/scaled, with original BF16 V/beta bits.
# Initial dtype is the ORIGINAL function-entry query dtype, before preparation.
NATIVE_BINDING = '''initial_dtype = torch.bfloat16
batch_size = 1
sequence_length = query.shape[2]
k_head_dim = 128
num_v_heads = 16
v_head_dim = 128
recurrent_state_shape = (batch_size, num_v_heads, k_head_dim, v_head_dim)
padded_output_shape = (batch_size, num_v_heads, -1, v_head_dim)
decay = g
'''


def require(condition, detail):
    if not condition:
        raise ValueError('independent GDN chunk reference: ' + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _sources(root):
    for name, digest in SOURCE_HASHES.items():
        require(sha((Path(root) / name).read_bytes()) == digest, 'source drift: ' + name)
    return dict(SOURCE_HASHES)


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


def _node(operation, left, right, *, allow_gradual_underflow=False):
    """One separate FP32 RNE operation, including retained Vector fault policy.

    Float64 represents an exact product of two finite FP32 numbers. A sum whose
    rounded result is tiny is also exact in Float64. This detects inexact
    underflow after rounding without relying on NumPy's process exception flags.
    """
    require(operation in ('add', 'mul'), 'only separate Add/Mul nodes')
    a, b = np.broadcast_arrays(np.asarray(left, dtype=np.float32),
                               np.asarray(right, dtype=np.float32))
    require(np.isfinite(a).all() and np.isfinite(b).all(), 'nonfinite FP32 operand')
    op = np.add if operation == 'add' else np.multiply
    with np.errstate(all='ignore'):
        result = op(a, b, dtype=np.float32)
    require(np.isfinite(result).all(), 'FP32 invalid/overflow')
    tiny = (result.view('<u4') & 0x7f800000) == 0
    if np.any(tiny) and not allow_gradual_underflow:
        exact = op(a[tiny].astype(np.float64), b[tiny].astype(np.float64))
        require(np.all(exact == result[tiny].astype(np.float64)),
                'retained Vector policy rejects inexact underflow')
    return result


def _exp_negative(values):
    """Original degree-7 exp(-abs(x)), abs >= 80 gives +0.

    The source standalone ExpNegative opcode ignores internal exception flags.
    It is deliberately independent of _node's Vector underflow fault policy.
    Upper-triangle masking happens before this function is called.
    """
    x = np.asarray(values, dtype=np.float32)
    require(np.isfinite(x).all() and np.all(x <= 0), 'exp requires finite nonpositive input')
    magnitude = np.abs(x)
    active = magnitude < np.float32(80)
    coefficients = np.array([(-math.log(2)) ** i / math.factorial(i)
                             for i in range(8)], dtype=np.float32)
    with np.errstate(all='ignore'):
        scaled = np.multiply(magnitude, np.float32(1 / math.log(2)), dtype=np.float32)
        z = np.where(active, scaled, np.float32(0))
        exponent = z.astype(np.int32)
        fraction = np.add(z, -exponent.astype(np.float32), dtype=np.float32)
        total = np.full_like(z, coefficients[7])
        for coefficient in coefficients[6::-1]:
            product = np.multiply(total, fraction, dtype=np.float32)
            total = np.add(product, coefficient, dtype=np.float32)
        scale = ((127 - exponent).astype('<u4') << 23).view('<f4')
        result = np.multiply(total, scale, dtype=np.float32)
    return np.where(active, result, np.float32(0))


def _matmul(a, b, node=_node):
    require(a.ndim == b.ndim == 2 and a.shape[1] == b.shape[0], 'matrix geometry')
    total = np.zeros((a.shape[0], b.shape[1]), dtype=np.float32)
    for index in range(a.shape[1]):
        product = node('mul', a[:, index:index + 1], b[index:index + 1, :])
        total = node('add', total, product)
    return total


def _solve(lower, rhs, node=_node):
    """Ascending forward substitution with implicit unit diagonal."""
    require(lower.shape == (CHUNK, CHUNK) and rhs.shape[0] == CHUNK, 'solve geometry')
    result = np.zeros_like(rhs, dtype=np.float32)
    for row in range(CHUNK):
        total = np.zeros(rhs.shape[1], dtype=np.float32)
        for index in range(row):
            total = node('add', total, node('mul', lower[row, index], result[index]))
        result[row] = node('add', rhs[row], -total)
    return result


def _inputs(raw, rows, initial_state, heads, key_dim, value_dim):
    require(type(rows) is int and 1 <= rows <= 128, 'M1..128 geometry')
    require(type(heads) is int and 1 <= heads <= HEADS and
            type(key_dim) is int and 1 <= key_dim <= WIDTH and
            type(value_dim) is int and 1 <= value_dim <= WIDTH, 'head/dimension geometry')
    require(type(raw) is bytes and len(raw) == rows * CORE * 4, 'complete FP32[M,6400] input')
    data = np.frombuffer(raw, '<f4').reshape(rows, CORE)
    q, k, v = (data[:, start:start + 2048].reshape(rows, HEADS, WIDTH)[:, :heads, :dim]
               for start, dim in ((0, key_dim), (2048, key_dim), (4096, value_dim)))
    gates = data[:, 6144:].reshape(rows, HEADS, 16)[:, :heads]
    g, beta = gates[..., 0], gates[..., 1]
    require(all(np.isfinite(x).all() for x in (q, k, v, gates)), 'nonfinite consumed input')
    require(np.all(g <= 0) and np.all(beta >= 0) and np.all(beta <= 1), 'gate domain')
    require(np.all(gates[..., 2:].view('<u4') == 0), 'gate padding must be positive zero')
    require(np.all((v.view('<u4') & 0xffff) == 0) and np.all((beta.view('<u4') & 0xffff) == 0),
            'V and beta must be BF16-widened FP32')
    shape = (heads, key_dim, value_dim)
    if initial_state is None:
        state = np.zeros(shape, dtype=np.float32)
    else:
        require(type(initial_state) is bytes and len(initial_state) == math.prod(shape) * 4,
                'complete FP32 initial state')
        state = np.frombuffer(initial_state, '<f4').reshape(shape).copy()
        require(np.isfinite(state).all(), 'nonfinite initial state')
    return q, k, v, g, beta, state


def _bf16(values):
    require(np.isfinite(values).all(), 'nonfinite terminal output')
    bits = np.asarray(values, dtype='<f4').view('<u4')
    result = ((bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) >> 16).astype('<u2')
    require(np.all((result & 0x7f80) != 0x7f80), 'BF16 terminal overflow')
    return result.tobytes()


def _identity(raw, rows, initial_state, heads, key_dim, value_dim, output, state, sources):
    return dict(rows=rows, heads=heads, key_dim=key_dim, value_dim=value_dim,
        input_shape=[rows, CORE], output_shape=[rows, heads, value_dim],
        state_shape=[heads, key_dim, value_dim], chunk_size=CHUNK, chunks=(rows + 63) // 64,
        pad_size=(-rows) % CHUNK, input_sha256=sha(raw),
        initial_state_sha256=None if initial_state is None else sha(initial_state),
        output_sha256=sha(output), state_sha256=sha(state), source_sha256=sources,
        implementation_sha256=sha(Path(__file__).read_bytes()),
        input_layout='Q2048_K2048_V2048_gate16x16_FP32; gate={g,beta,14_positive_zero}',
        input_scope='supplied_prepared_boundary; Q_already_L2_and_scaled; K_already_L2',
        output_dtype='BF16_RNE', state_dtype='FP32', reference_only=True,
        scalar_or_owner_called=False, vector_called=False, rtl_executed=False,
        full_official_block_executed=False, hardware_cycles=None,
        official_stage_acceptance='UNASSIGNED; native comparisons diagnostic only',
        complete_gdn_final_gate='REQUIRED_DOWNSTREAM_UNCHANGED; not evaluated here')


def fixed_chunk(raw, rows, initial_state=None, *, heads=HEADS, key_dim=WIDTH,
                value_dim=WIDTH, root=ROOT, exception_policy="legacy_vector_fatal_underflow"):
    """Return (BF16 output bytes, FP32 state bytes, identity).

    Geometry arguments select the leading prepared heads/lanes, for independent
    small tests or isolated boundaries. M65..128 always executes two complete
    padded chunk64 transforms. Initial and final state never narrow to BF16.
    """
    require(exception_policy in ('legacy_vector_fatal_underflow', 'ieee_rne_finite_gradual_underflow'), 'explicit supported exception policy')
    def node(op, a, b):
        return _node(op, a, b, allow_gradual_underflow=exception_policy == 'ieee_rne_finite_gradual_underflow')
    def mm(a, b):
        return _matmul(a, b, node)
    def solve(a, b):
        return _solve(a, b, node)
    q, k, v, g, beta, states = _inputs(raw, rows, initial_state, heads, key_dim, value_dim)
    _environment()
    sources = _sources(root)
    output = np.zeros((rows, heads, value_dim), dtype=np.float32)
    exp_calls = saturated = 0
    max_magnitude = 0

    def exp(values):
        nonlocal exp_calls, saturated, max_magnitude
        x = np.asarray(values, dtype=np.float32)
        magnitude = np.abs(x)
        exp_calls += int(x.size)
        saturated += int(np.count_nonzero(magnitude >= 80))
        max_magnitude = max(max_magnitude, int(magnitude.view('<u4').max()))
        return _exp_negative(x)

    for head in range(heads):
        state = states[head]
        for start in range(0, rows, CHUNK):
            count = min(CHUNK, rows - start)
            cq, ck, cv = (np.zeros((CHUNK, dim), dtype=np.float32)
                          for dim in (key_dim, key_dim, value_dim))
            cq[:count], ck[:count], cv[:count] = q[start:start + count, head], k[start:start + count, head], v[start:start + count, head]
            cg, cb = (np.zeros(CHUNK, dtype=np.float32) for _ in range(2))
            cg[:count], cb[:count] = g[start:start + count, head], beta[start:start + count, head]
            cumulative = np.empty(CHUNK, dtype=np.float32)
            total = np.float32(0)
            for row in range(CHUNK):
                total = node('add', total, cg[row])
                cumulative[row] = total
            chunk_decay = exp(total)
            exp_g = exp(cumulative)
            exp_end = exp(node('add', total, -cumulative))
            pair = np.zeros((CHUNK, CHUNK), dtype=np.float32)
            for row in range(CHUNK):
                pair[row, :row + 1] = exp(node('add', cumulative[row], -cumulative[:row + 1]))
            kb = node('mul', ck, cb[:, None])
            vb = node('mul', cv, cb[:, None])
            kbg = node('mul', kb, exp_g[:, None])
            qg = node('mul', cq, exp_g[:, None])
            ke = node('mul', ck, exp_end[:, None])
            lower = node('mul', mm(kb, ck.T), pair)
            intra = node('mul', mm(cq, ck.T), pair)
            solved_v, solved_k = solve(lower, vb), solve(lower, kbg)
            vnew = node('add', solved_v, -mm(solved_k, state))
            inter = mm(qg, state)
            out = node('add', inter, mm(intra, vnew))
            state = node('add', node('mul', state, chunk_decay), mm(ke.T, vnew))
            output[start:start + count, head] = out[:count]
        states[head] = state
    output_raw, state_raw = _bf16(output), states.astype('<f4', copy=False).tobytes()
    identity = _identity(raw, rows, initial_state, heads, key_dim, value_dim, output_raw, state_raw, sources)
    identity.update(scope='INDEPENDENT_NUMPY_TRUE_CHUNK64_FIXED_RECIPE', numpy=np.__version__,
        arithmetic='separate_FP32_RNE_Mul_Add; ascending_K_from_positive_zero; unit_diagonal_forward_solve',
        vector_underflow_policy=exception_policy,
        exp_policy='original_degree7_ExpNegative_abs_ge_80_positive_zero_saturation',
        exp_stats=dict(calls=exp_calls, saturated_abs_ge_80=saturated, max_abs_input_word=max_magnitude),
        synthetic_geometry=(heads, key_dim, value_dim) != (HEADS, WIDTH, WIDTH),
        bitwise_required=True, native_acceptance=False)
    return output_raw, state_raw, identity


def _native_ast(source):
    """Replace only preparation with explicit bindings; retain the whole suffix."""
    require(sha(source) == SOURCE_SHA, 'pinned official source hash changed')
    tree = ast.parse(source)
    original = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and
                    n.name == 'torch_chunk_gated_delta_rule')
    stop = next(i for i, n in enumerate(original.body) if isinstance(n, ast.Assign) and
                ast.unparse(n) == 'query = query * scaling')
    suffix = original.body[stop + 1:]
    require(ast.unparse(suffix[0]) == 'pad_size = (chunk_size - sequence_length % chunk_size) % chunk_size',
            'native prepared boundary changed')
    function = copy.deepcopy(original)
    function.decorator_list = []
    function.body = ast.parse(NATIVE_BINDING).body + copy.deepcopy(suffix)
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    dump = lambda nodes: ast.dump(ast.Module(body=nodes, type_ignores=[])).encode()
    identity = dict(original_function_ast_sha256=sha(ast.dump(original).encode()),
        removed_preparation_ast_sha256=sha(dump(original.body[:stop + 1])),
        unchanged_suffix_ast_sha256=sha(dump(suffix)),
        explicit_binding_ast_sha256=sha(dump(ast.parse(NATIVE_BINDING).body)),
        executable_ast_sha256=sha(ast.dump(module).encode()),
        modifications=['remove_hub_decorator', 'replace_preparation_prefix_with_explicit_stage_bindings'],
        suffix_unchanged=True, entry='immediately_after_query_equals_query_times_scaling',
        original_initial_dtype='BF16', export_branch=False)
    return module, identity


def native_prepared_chunk(raw, rows, initial_state=None, *, heads=HEADS,
                          key_dim=WIDTH, value_dim=WIDTH, root=ROOT):
    """Pinned Torch conditional diagnostic, complete original 16-head suffix.

    No normalization, inverse scaling, or second scaling is applied to prepared
    inputs. g retains upstream's FP32 transposed stride; Q/K/V and widened beta
    retain their original contiguous head-major preparation layout. Native exp,
    matmul and solve_triangular run exactly as written in the original suffix.
    """
    require((heads, key_dim, value_dim) == (HEADS, WIDTH, WIDTH),
            'native requires original complete 16-head 128x128 geometry')
    q, k, v, g, beta, states = _inputs(raw, rows, initial_state, heads, key_dim, value_dim)
    sources = _sources(root)
    require(os.environ.get('ATEN_CPU_CAPABILITY') == 'default',
            'set ATEN_CPU_CAPABILITY=default before importing Torch')
    import torch
    require(torch.__version__.split('+')[0] == '2.10.0', 'frozen Torch 2.10.0 required')
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    capability = torch.backends.cpu.get_cpu_capability()
    require(capability in ('NO AVX', 'DEFAULT'), 'frozen Torch DEFAULT CPU backend required')
    require(not torch.is_autocast_enabled('cpu'), 'native requires CPU autocast disabled')
    _environment()
    module, ast_identity = _native_ast((Path(root) / SOURCE).read_bytes())
    namespace = dict(torch=torch, F=torch.nn.functional, is_torchdynamo_exporting=lambda: False)
    exec(compile(module, SOURCE + ':prepared_chunk_suffix', 'exec'), namespace)

    def head_contiguous(array):
        shape = (1, HEADS, rows, WIDTH) if array.ndim == 3 else (1, HEADS, rows)
        tensor = torch.empty(shape, dtype=torch.float32, device='cpu')
        tensor.copy_(torch.from_numpy(array.copy()).unsqueeze(0).transpose(1, 2))
        return tensor

    query, key, value, native_beta = [head_contiguous(x) for x in (q, k, v, beta)]
    decay = torch.from_numpy(g.copy()).unsqueeze(0).transpose(1, 2)
    native_state = None if initial_state is None else torch.from_numpy(states).unsqueeze(0)
    tensors = dict(query=query, key=key, value=value, beta=native_beta, g=decay)
    layout = {name: dict(shape=list(x.shape), stride=list(x.stride()), dtype=str(x.dtype),
                         contiguous=x.is_contiguous()) for name, x in tensors.items()}
    require(list(decay.stride()) == [HEADS * rows, 1, HEADS], 'original FP32 decay stride')
    with torch.inference_mode():
        output, state = namespace['torch_chunk_gated_delta_rule'](
            query, key, value, decay, native_beta, chunk_size=CHUNK,
            initial_state=native_state, output_final_state=True, use_qk_l2norm_in_kernel=False)
    require(list(output.shape) == [1, rows, HEADS, WIDTH] and output.dtype == torch.bfloat16 and
            list(state.shape) == [1, HEADS, WIDTH, WIDTH] and state.dtype == torch.float32,
            'native terminal shapes/dtypes changed')
    require(torch.isfinite(output).all().item() and torch.isfinite(state).all().item(),
            'native nonfinite terminal result')
    output_raw = output.contiguous().view(torch.uint16).numpy().astype('<u2', copy=False).tobytes()
    state_raw = state.contiguous().numpy().astype('<f4', copy=False).tobytes()
    identity = _identity(raw, rows, initial_state, heads, key_dim, value_dim, output_raw, state_raw, sources)
    identity.update(scope='PINNED_OFFICIAL_FULLSHAPE_CHUNK_SUFFIX_ON_PREPARED_INPUTS',
        native_acceptance=False, original_ast=ast_identity, prepared_input_layout=layout,
        initial_dtype_binding='BF16_original_function_entry_before_preparation',
        query_transform='none_already_normalized_and_scaled',
        backend=dict(torch=torch.__version__, torch_git=torch.version.git_version,
            cpu_capability=capability, requested_cpu_capability=os.environ['ATEN_CPU_CAPABILITY'],
            machine=platform.machine(), threads=torch.get_num_threads(),
            interop_threads=torch.get_num_interop_threads(), deterministic=True, autocast=False,
            float32_matmul_precision='highest', mkldnn_enabled=torch.backends.mkldnn.enabled,
            configuration=torch.__config__.show()))
    return output_raw, state_raw, identity


def compare_bytes(actual, expected, *, dtype):
    """Bit/ULP and numerical diagnostics, with no assigned native threshold."""
    require(dtype in ('bf16', 'fp32'), 'comparison dtype')
    size = 2 if dtype == 'bf16' else 4
    require(type(actual) is bytes and type(expected) is bytes and len(actual) == len(expected) and
            len(actual) > 0 and len(actual) % size == 0, 'same complete comparison geometry')
    a, b = (np.frombuffer(raw, '<u2' if size == 2 else '<u4') for raw in (actual, expected))
    fa, fb = (((x.astype('<u4') << 16).view('<f4') if size == 2 else x.view('<f4')) for x in (a, b))
    finite = np.isfinite(fa) & np.isfinite(fb)
    sign = 1 << (size * 8 - 1)
    def ordered(x):
        x = x.astype(np.int64)
        return np.where(x & sign, sign - (x & (sign - 1)), sign + x)
    ulp = np.abs(ordered(a) - ordered(b))
    differing = a != b
    result = dict(dtype=dtype, elements=int(a.size), bit_mismatches=int(differing.sum()),
        numerical_mismatches=int(np.count_nonzero(ulp[finite])),
        signed_zero_only_mismatches=int(np.count_nonzero(differing & (ulp == 0) & finite)),
        nonfinite=not bool(finite.all()), actual_nonfinite=int((~np.isfinite(fa)).sum()),
        expected_nonfinite=int((~np.isfinite(fb)).sum()),
        first_bit_mismatch=int(np.flatnonzero(differing)[0]) if differing.any() else None,
        actual_sha256=sha(actual), expected_sha256=sha(expected),
        max_abs=None, mean_abs=None, max_ulp=None, relative_l2=None, cosine=None)
    if finite.all():
        av, bv = fa.astype(np.float64), fb.astype(np.float64)
        delta = av - bv
        an, bn, dn = (float(np.linalg.norm(x)) for x in (av, bv, delta))
        result.update(max_abs=float(np.abs(delta).max()), mean_abs=float(np.abs(delta).mean()),
            max_ulp=int(ulp.max()), relative_l2=dn / bn if bn else (0. if dn == 0 else None),
            cosine=float(np.dot(av, bv) / (an * bn)) if an and bn else (1. if an == bn else 0.))
    return result


def compare_outputs(actual_output, actual_state, expected_output, expected_state, *, native=False):
    """Compare complete supplied output/state; native never acquires a pass gate."""
    output = compare_bytes(actual_output, expected_output, dtype='bf16')
    state = compare_bytes(actual_state, expected_state, dtype='fp32')
    return dict(status='DIAGNOSTIC_ONLY_NO_APPROVED_CHUNK_THRESHOLD' if native else 'FIXED_BITWISE_CONFORMANCE',
        passed=None if native else (actual_output == expected_output and actual_state == expected_state and
                                    not output['nonfinite'] and not state['nonfinite']),
        thresholds=None, bitwise_required=not native,
        output=output, state=state)
