"""Independent InputPrep array recipe and pinned fullshape native diagnostics.

This reference never imports or calls PrepScalar, InputPrepOwner or their
arithmetic helpers. The candidate prepares independent tokens, M1..128; the
pinned Chisel owner supports M1 only. No recurrence, Chisel or RTL is run.
Only bit-exact fixed arithmetic has an acceptance gate here. Native InputPrep
has no approved standalone threshold; final GDN acceptance remains downstream.
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
import re
import subprocess
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'
SOURCE_SHA = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'
OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnInputPrepOwner.scala'
OWNER_SHA = '86fa350cd87bc140b762db2deb5650c25e3b30bae4fb12cef7fe407e6b4faffe'
SCALAR_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala'
SCALAR_SHA = '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5'
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
TRANSFORMERS_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'
HEADS, WIDTH, VECTOR, CONV, CORE = 16, 128, 2048, 6144, 6400


def require(condition, detail):
    if not condition:
        raise ValueError('independent InputPrep reference: ' + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _float(bits):
    return (np.asarray(bits, dtype='<u2').astype('<u4') << 16).view('<f4')


def _inputs(conv_raw, ab_raw, alog_raw, dtbias_raw, rows):
    require(type(rows) is int and 1 <= rows <= 128, 'M1..128 geometry')
    for name, raw, size in (('Conv', conv_raw, rows * CONV * 2),
                            ('AB', ab_raw, rows * 32 * 2),
                            ('A_log', alog_raw, 64), ('dt_bias', dtbias_raw, 64)):
        require(type(raw) is bytes and len(raw) == size, 'complete raw ' + name + ' shape')
    conv = _float(np.frombuffer(conv_raw, '<u2').reshape(rows, 3, HEADS, WIDTH))
    ab = _float(np.frombuffer(ab_raw, '<u2').reshape(rows, 2, HEADS))
    alog = np.frombuffer(alog_raw, '<f4')
    # The second 32 bytes are physical padding and never parameter values.
    bias = _float(np.frombuffer(dtbias_raw, '<u2')[:HEADS])
    require(all(np.isfinite(x).all() for x in (conv, ab, alog, bias)),
            'nonfinite consumed input')
    return conv, ab, alog, bias


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


def _node(operation, left, right=0, *, legacy=False):
    """Exactly one FP32 rounding; public Add/Div/Sqrt reject tiny inexact."""
    a, b = np.broadcast_arrays(np.asarray(left, dtype=np.float32),
                               np.asarray(right, dtype=np.float32))
    require(np.isfinite(a).all() and np.isfinite(b).all(), 'nonfinite FP32 operand')
    with np.errstate(all='ignore'):
        out = (np.sqrt(a, dtype=np.float32) if operation == 'sqrt' else
               {'mul': np.multiply, 'add': np.add, 'div': np.divide}[operation](a, b, dtype=np.float32))
    require(np.isfinite(out).all(), 'FP32 invalid/div0/overflow')
    if legacy:
        tiny = (out.view('<u4') & 0x7f800000) == 0
        for av, bv, rv in zip(a[tiny], b[tiny], out[tiny]):
            an, ad = float(av).as_integer_ratio()
            bn, bd = float(bv).as_integer_ratio()
            rn, rd = float(rv).as_integer_ratio()
            exact = ((an * bd + bn * ad) * rd == rn * ad * bd if operation == 'add' else
                     an * bd * rd == rn * ad * bn if operation == 'div' else
                     rn * rn * ad == an * rd * rd)
            require(exact, 'legacy public ' + operation + ' rejects inexact underflow')
    return out


def _exp_negative(values, *, severe_checks=False):
    """Source degree-7 exp(-abs(x)); >=80 saturates after expScale.

    The standalone opcode ignores internal flags. Softplus uses the same
    arithmetic with severe checks and accepts finite inexact underflow.
    Constants are independently derived, never imported from the scalar.
    """
    magnitude = np.abs(np.asarray(values, dtype=np.float32))
    require(np.isfinite(magnitude).all(), 'nonfinite exp input')
    active = magnitude < np.float32(80)
    coefficients = np.array([math.pow(-math.log(2), i) / math.factorial(i)
                             for i in range(8)], dtype=np.float32)
    def op(name, left, right):
        if severe_checks:
            return _node(name, left, right)
        return {'mul': np.multiply, 'add': np.add}[name](left, right, dtype=np.float32)
    with np.errstate(all='ignore'):
        scaled = op('mul', magnitude, np.float32(1 / math.log(2)))
        z = np.where(active, scaled, np.float32(0))
        k = z.astype(np.int32)
        fraction = op('add', z, -k.astype(np.float32))
        accumulator = np.full_like(z, coefficients[7])
        for coefficient in coefficients[6::-1]:
            accumulator = op('add', op('mul', accumulator, fraction), coefficient)
        scale = ((127 - k).astype('<u4') << 23).view('<f4')
        result = op('mul', accumulator, scale)
    return np.where(active, result, np.float32(0))


def _softplus(values):
    x = np.asarray(values, dtype=np.float32)
    require(np.isfinite(x).all() and np.all(x > np.float32(-80)), 'Softplus source domain x > -80')
    bypass = x > np.float32(20)
    active = np.where(bypass, np.float32(0), x)
    exponential = _exp_negative(active, severe_checks=True)
    y = _node('div', exponential, _node('add', np.float32(2), exponential))
    square = _node('mul', y, y)
    coefficients = [np.float32(1 / (2 * i + 1)) for i in range(8)]
    horner = np.full_like(x, coefficients[7])
    for coefficient in coefficients[6::-1]:
        horner = _node('add', _node('mul', horner, square), coefficient)
    logarithm = _node('mul', _node('mul', np.float32(2), y), horner)
    base = np.where(np.signbit(active), np.float32(0), active)
    return np.where(bypass, x, _node('add', base, logarithm))


def _identity(conv_raw, ab_raw, alog_raw, dtbias_raw, rows):
    return dict(rows=rows, heads=HEADS, head_width=WIDTH, input_conv_shape=[rows, CONV],
                input_ab_shape=[rows, 32], output_shape=[rows, CORE],
                conv_sha256=sha(conv_raw), ab_sha256=sha(ab_raw),
                a_log_sha256=sha(alog_raw), dt_bias_sha256=sha(dtbias_raw),
                layout='FP32[M,6400]=Q2048_K2048_V2048_gates256; gate64B={g,beta,14_positive_zero}',
                a_log_dtype='original_FP32', ab_dtype='BF16', dt_bias_dtype='BF16_first16_of64B',
                source_tokens=1, candidate_tokens=rows, model_not_Chisel_tokens128=True,
                reference_only=True, scalar_or_owner_called=False,
                token_independent=True, recurrence_implemented=False,
                full_official_block_executed=False, rtl_executed=False, hardware_cycles=None,
                history_committed=False, state_committed=False, generation_advanced=False,
                official_stage_acceptance='UNASSIGNED; native comparisons are diagnostic only')


def fixed_prep(conv_raw, ab_raw, alog_raw, dtbias_raw, rows, *, root=ROOT):
    """Return raw FP32[M,6400] bytes and the independent fixed-recipe identity."""
    conv, ab, alog, bias = _inputs(conv_raw, ab_raw, alog_raw, dtbias_raw, rows)
    _environment()
    committed = subprocess.run(['git', 'show', 'HEAD:' + OWNER_SOURCE], cwd=Path(root),
                               check=True, capture_output=True, timeout=10).stdout
    require(sha(committed) == OWNER_SHA, 'committed M1 InputPrep source drift')
    require(sha((Path(root) / SCALAR_SOURCE).read_bytes()) == SCALAR_SHA, 'shared scalar source drift')
    qk = conv[:, :2]
    total = np.zeros((rows, 2, HEADS), dtype=np.float32)
    for lane in range(WIDTH):
        square = _node('mul', qk[..., lane], qk[..., lane])
        total = _node('add', total, square, legacy=True)
    variance = _node('add', total, np.float32(1e-6), legacy=True)
    inverse = _node('div', np.float32(1), _node('sqrt', variance, legacy=True), legacy=True)
    normalized = _node('mul', qk, inverse[..., None])
    query = _node('mul', normalized[:, 0], np.float32(1 / math.sqrt(WIDTH)))
    a, b = ab[:, 0], ab[:, 1]
    require(np.all(np.abs(alog) < np.float32(80)) and np.all(b > np.float32(-80)),
            'source A_log abs < 80 and beta input b > -80 required')
    positive = _softplus(_node('add', a, bias, legacy=True))
    require(not np.signbit(positive).any(), 'negative Softplus result')
    exponential = _exp_negative(alog)
    # Branch selection is real: do not evaluate unselected reciprocals.
    positive_log = ~np.signbit(alog)
    exponential[positive_log] = _node('div', np.float32(1), exponential[positive_log], legacy=True)
    g = _node('mul', -exponential, positive)
    require(np.all(g <= np.float32(0)) and np.all(g > np.float32(-80)), 'source gate -80 < g <= 0')
    exponential = _exp_negative(b)
    denominator = _node('add', np.float32(1), exponential, legacy=True)
    reciprocal = _node('div', np.float32(1), denominator, legacy=True)
    beta = _node('mul', reciprocal, np.where(np.signbit(b), exponential, np.float32(1)))
    require(not np.signbit(beta).any() and np.all(beta <= np.float32(1)), 'source beta in [0,1]')
    bits = beta.view('<u4')
    beta = ((bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) & np.uint32(0xffff0000)).view('<f4')
    output = np.zeros((rows, CORE), dtype='<f4')
    output[:, :VECTOR] = query.reshape(rows, VECTOR)
    output[:, VECTOR:2 * VECTOR] = normalized[:, 1].reshape(rows, VECTOR)
    output[:, 2 * VECTOR:CONV] = conv[:, 2].reshape(rows, VECTOR)
    gates = output[:, CONV:].reshape(rows, HEADS, 16)
    gates[..., 0], gates[..., 1] = g, beta
    raw = output.tobytes()
    identity = _identity(conv_raw, ab_raw, alog_raw, dtbias_raw, rows)
    identity.update(scope='INDEPENDENT_NUMPY_FIXED_INPUT_PREP_RECIPE', numpy=np.__version__,
                    source_sha256={'HEAD:' + OWNER_SOURCE: OWNER_SHA, SCALAR_SOURCE: SCALAR_SHA},
                    implementation_sha256=sha(Path(__file__).read_bytes()),
                    arithmetic='ascending128_square_add_eps_sqrt_reciprocal_Qmultiply_1_over_sqrt128',
                    softplus='opcode7_threshold20_e_over_2_plus_e_8_odd_terms_separate_FP32_nodes',
                    beta='source_exp_reciprocal_sigmoid_then_BF16_RNE_then_FP32_widen',
                    output_sha256=sha(raw))
    return raw, identity


def _official_ast(source, torch):
    """Execute unchanged l2norm, gate assignments and chunk preparation prefix."""
    require(sha(source) == SOURCE_SHA, 'pinned official source hash changed')
    tree = ast.parse(source)
    norm = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'l2norm')
    chunk = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and
                 node.name == 'torch_chunk_gated_delta_rule')
    prefix = copy.deepcopy(chunk)
    stop = next(i for i, node in enumerate(prefix.body) if isinstance(node, ast.Assign) and
                ast.unparse(node) == 'query = query * scaling')
    prefix.body = prefix.body[:stop + 1]
    prefix.body += [ast.Return(value=ast.Tuple(elts=[ast.Name(id=x, ctx=ast.Load())
                        for x in ('query', 'key', 'value', 'g', 'beta')], ctx=ast.Load()))]
    # Return transformed decay, not the original pre-transpose argument g.
    prefix.body[-1].value.elts[3].id = 'decay'
    prefix.decorator_list = []
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Qwen3_5GatedDeltaNet')
    forward = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'forward')
    gates = [node for node in forward.body if isinstance(node, ast.Assign) and
             len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('beta', 'g')]
    require([ast.unparse(node) for node in gates] == ['beta = b.sigmoid()',
            'g = -self.A_log.float().exp() * F.softplus(a.float() + self.dt_bias)'],
            'official gate expressions changed')
    namespace = dict(torch=torch, F=torch.nn.functional)
    module = ast.fix_missing_locations(ast.Module(body=[norm, prefix], type_ignores=[]))
    exec(compile(module, SOURCE, 'exec'), namespace)
    gate_code = compile(ast.Module(body=gates, type_ignores=[]), SOURCE, 'exec')
    identity = dict(l2norm_ast_sha256=sha(ast.dump(norm).encode()),
                    gate_ast_sha256=sha(ast.dump(ast.Module(body=gates, type_ignores=[])).encode()),
                    chunk_prefix_ast_sha256=sha(ast.dump(ast.Module(body=chunk.body[:stop + 1], type_ignores=[])).encode()))
    return namespace, gate_code, identity


def native_prep(conv_raw, ab_raw, alog_raw, dtbias_raw, rows, *, root=ROOT):
    """Fullshape official operations on supplied Conv/AB boundaries, diagnostic.

    The full [1,M,16,128] tensors follow the original chunk path: transpose
    (1,2), cast to contiguous FP32, l2norm, then multiply Q by 128**-0.5.
    Beta sigmoid executes in BF16 before the chunk FP32 conversion. This does
    not run the remainder of chunk GDN or establish standalone acceptance.
    """
    _inputs(conv_raw, ab_raw, alog_raw, dtbias_raw, rows)
    require(os.environ.get('ATEN_CPU_CAPABILITY') == 'default',
            'set ATEN_CPU_CAPABILITY=default before importing Torch')
    import torch
    require(torch.__version__.split('+')[0] == '2.10.0', 'frozen Torch 2.10.0 required')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    capability = torch.backends.cpu.get_cpu_capability()
    require(capability in ('NO AVX', 'DEFAULT'), 'frozen Torch DEFAULT CPU backend required')
    _environment()
    source = (Path(root) / SOURCE).read_bytes()
    namespace, gate_code, ast_identity = _official_ast(source, torch)
    mixed = torch.frombuffer(bytearray(conv_raw), dtype=torch.bfloat16).reshape(1, rows, CONV)
    query, key, value = [x.reshape(1, rows, HEADS, WIDTH) for x in torch.split(mixed, [VECTOR] * 3, dim=-1)]
    ab = torch.frombuffer(bytearray(ab_raw), dtype=torch.bfloat16).reshape(1, rows, 32)
    alog = torch.frombuffer(bytearray(alog_raw), dtype=torch.float32)
    bias = torch.frombuffer(bytearray(dtbias_raw[:32]), dtype=torch.bfloat16)
    with torch.inference_mode():
        namespace.update(a=ab[..., :HEADS], b=ab[..., HEADS:], self=SimpleNamespace(A_log=alog, dt_bias=bias))
        exec(gate_code, namespace)
        q, k, v, g, beta = namespace['torch_chunk_gated_delta_rule'](
            query, key, value, namespace['g'], namespace['beta'], use_qk_l2norm_in_kernel=True)
        require(all(list(x.shape) == [1, HEADS, rows, WIDTH] for x in (q, k, v)) and
                all(list(x.shape) == [1, HEADS, rows] for x in (g, beta)), 'native fullshape changed')
        require(all(torch.isfinite(x).all().item() for x in (q, k, v, g, beta)), 'nonfinite native output')
        output = torch.zeros((rows, CORE), dtype=torch.float32)
        for index, x in enumerate((q, k, v)):
            output[:, index * VECTOR:(index + 1) * VECTOR] = x.transpose(1, 2).reshape(rows, VECTOR)
        gates = output[:, CONV:].reshape(rows, HEADS, 16)
        gates[..., 0] = g.transpose(1, 2).reshape(rows, HEADS)
        gates[..., 1] = beta.transpose(1, 2).reshape(rows, HEADS)
    raw = output.numpy().astype('<f4', copy=False).tobytes()
    identity = _identity(conv_raw, ab_raw, alog_raw, dtbias_raw, rows)
    identity.update(scope='PINNED_OFFICIAL_FULLSHAPE_INPUT_PREP_OPERATIONS_ONLY',
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        official_source_sha256=sha(source), original_ast=ast_identity,
        qkv_before_chunk_shape=[1, rows, HEADS, WIDTH], chunk_qkv_shape=[1, HEADS, rows, WIDTH],
        qkv_layout='transpose(1,2).to(float32,memory_format=contiguous_format)_then_l2norm_then_Q_scale',
        beta_boundary='BF16_sigmoid_before_FP32_widen', g_boundary='FP32_Alog_exp_times_softplus_a_float_plus_BF16_bias',
        backend=dict(torch=torch.__version__, torch_git=torch.version.git_version,
                     cpu_capability=capability, requested_cpu_capability=os.environ['ATEN_CPU_CAPABILITY'],
                     machine=platform.machine(), threads=torch.get_num_threads(), deterministic=True,
                     autocast=False, float32_matmul_precision='highest',
                     mkldnn_enabled=torch.backends.mkldnn.enabled, configuration=torch.__config__.show()),
        output_sha256=sha(raw))
    return raw, identity


def compare_fp32(actual, expected):
    require(type(actual) is bytes and type(expected) is bytes and len(actual) == len(expected) and
            len(actual) > 0 and len(actual) % 4 == 0, 'same complete FP32 comparison shape')
    a, b = np.frombuffer(actual, '<u4'), np.frombuffer(expected, '<u4')
    fa, fb = a.view('<f4'), b.view('<f4')
    finite = np.isfinite(fa) & np.isfinite(fb)
    def ordered(bits):
        value = bits.astype(np.int64)
        return np.where(value & 0x80000000, 0x80000000 - (value & 0x7fffffff), 0x80000000 + value)
    ulp = np.abs(ordered(a) - ordered(b))
    different = a != b
    delta = np.abs(fa[finite].astype(np.float64) - fb[finite].astype(np.float64))
    all_finite = bool(finite.all())
    return dict(elements=int(a.size), bit_mismatches=int(different.sum()),
                max_abs=float(delta.max()) if all_finite else None,
                mean_abs=float(delta.mean()) if all_finite else None,
                max_fp32_ulp=int(ulp.max()) if all_finite else None,
                actual_nonfinite=int((~np.isfinite(fa)).sum()), expected_nonfinite=int((~np.isfinite(fb)).sum()),
                nonfinite=not all_finite, numerical_mismatches=int(np.count_nonzero(ulp[finite])),
                signed_zero_only_mismatches=int(np.count_nonzero(different & (ulp == 0) & finite)),
                first_bit_mismatch=int(np.flatnonzero(different)[0]) if different.any() else None,
                actual_sha256=sha(actual), expected_sha256=sha(expected))


def _roles(raw, rows):
    require(type(raw) is bytes and len(raw) == rows * CORE * 4, 'complete FP32 core output')
    x = np.frombuffer(raw, '<u4').reshape(rows, CORE)
    gates = x[:, CONV:].reshape(rows, HEADS, 16)
    arrays = dict(query=x[:, :VECTOR], key=x[:, VECTOR:2 * VECTOR], value=x[:, 2 * VECTOR:CONV],
                  g=gates[..., 0], beta=gates[..., 1], gate_padding=gates[..., 2:])
    return {name: np.ascontiguousarray(value).tobytes() for name, value in arrays.items()}


def compare_roles(actual, expected, rows):
    a, b = _roles(actual, rows), _roles(expected, rows)
    return {name: compare_fp32(a[name], b[name]) for name in a}


def verify_outputs(conv_raw, ab_raw, alog_raw, dtbias_raw, rows, actual_raw, *,
                   official_conv=None, official_ab=None, output, phase, root=ROOT):
    """Persist byte artifacts; passed means fixed arithmetic conformance only.

    Same-input native and optional pure-official-input native comparisons are
    explicitly diagnostics. They carry no pass result or numeric threshold.
    The existing complete-GDN final gate must still be evaluated downstream.
    """
    require(isinstance(phase, str) and re.fullmatch(r'[A-Za-z0-9_-]+', phase) is not None,
            'safe nonempty phase label')
    require((official_conv is None) == (official_ab is None), 'official Conv and AB must be provided together')
    _roles(actual_raw, rows)
    fixed, fixed_identity = fixed_prep(conv_raw, ab_raw, alog_raw, dtbias_raw, rows, root=root)
    same, same_identity = native_prep(conv_raw, ab_raw, alog_raw, dtbias_raw, rows, root=root)
    roles = compare_roles(actual_raw, fixed, rows)
    fixed_report = dict(passed=actual_raw == fixed, bitwise_required=True, roles=roles, identity=fixed_identity)
    padding = np.frombuffer(_roles(actual_raw, rows)['gate_padding'], '<u4')
    fixed_report['all_gate_padding_positive_zero'] = bool(np.all(padding == 0))
    def diagnostic(raw, identity):
        return dict(status='DIAGNOSTIC_ONLY_NO_APPROVED_INPUT_PREP_THRESHOLD',
                    passed=None, thresholds=None, roles=compare_roles(actual_raw, raw, rows), identity=identity)
    report = dict(passed=fixed_report['passed'], passed_scope='fixed_arithmetic_bitwise_conformance_only',
        scope='INPUT_PREP_MODEL_NOT_CHISEL_TOKENS128', model_not_Chisel_tokens128=True,
        fixed=fixed_report, native_sameinput=diagnostic(same, same_identity),
        native_official_inputs=None, official_stage_acceptance='UNASSIGNED',
        complete_gdn_final_gate='REQUIRED_DOWNSTREAM_UNCHANGED; not evaluated by this stage',
        full_official_block_executed=False, rtl_executed=False)
    values = dict(actual=actual_raw, fixed=fixed, native_sameinput=same)
    if official_conv is not None:
        official, identity = native_prep(official_conv, official_ab, alog_raw, dtbias_raw, rows, root=root)
        values['native_official_inputs'] = official
        report['native_official_inputs'] = diagnostic(official, identity)
    output = Path(output)
    paths = {name: output / f'{phase}.prep_{name}.f32le' for name in values}
    require(all(not path.exists() for path in paths.values()), 'refuse to overwrite comparison artifacts')
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, raw in values.items():
        paths[name].write_bytes(raw)
        require(paths[name].read_bytes() == raw, 'comparison artifact write mismatch')
        artifacts[name] = dict(path=str(paths[name]), bytes=len(raw), sha256=sha(raw))
    report['artifacts'] = artifacts
    return report
