"""Independent Conv4/SiLU references, run only after actual outputs are sealed.

The array recipe never imports or calls the Conv owner or its shared scalar.
The native reference executes the exact pinned official fallback function AST,
with the original BF16 dtype and full [1, channels, sequence] convolution shape.
Neither reference is a model of memory ACKs, cache publication, or RTL timing.
"""
from __future__ import annotations

import ast
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'
SOURCE_SHA = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'
OWNER_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnConv4Owner.scala'
OWNER_SHA = '99b7e4a4cbf2df234fc831cd1a85d44b032f981221f57fde504f3f5aebe6a28a'
SCALAR_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala'
SCALAR_SHA = '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5'
GATE_SOURCE = 'chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json'
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
TRANSFORMERS_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'


def require(condition, detail):
    if not condition:
        raise ValueError('independent Conv reference: ' + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _inputs(qkv_raw, weight_raw, rows, channels, history_raw):
    require(type(rows) is int and 1 <= rows <= 128 and type(channels) is int and
            0 < channels <= 65535 and channels % 32 == 0, 'M1..128 / 32-channel geometry')
    for name, raw, size in (('QKV', qkv_raw, rows * channels * 2),
                            ('weight', weight_raw, channels * 8)):
        require(type(raw) is bytes and len(raw) == size, 'complete raw BF16 ' + name + ' shape')
    require(history_raw is None or type(history_raw) is bytes and len(history_raw) == channels * 8,
            'complete raw BF16 history shape')
    x = np.frombuffer(qkv_raw, '<u2').reshape(rows, channels)
    weight = np.frombuffer(weight_raw, '<u2').reshape(channels, 4)
    history = (np.zeros((channels, 4), dtype='<u2') if history_raw is None else
               np.frombuffer(history_raw, '<u2').reshape(channels, 4))
    require(np.isfinite(_float(x)).all() and np.isfinite(_float(weight)).all() and
            np.isfinite(_float(history[:, 1:])).all(), 'nonfinite consumed BF16 input')
    return x, weight, history


def _float(bits):
    return (bits.astype('<u4') << 16).view('<f4')


def _bf16(values):
    require(np.isfinite(values).all(), 'nonfinite FP32 conversion input')
    u = np.asarray(values, dtype='<f4').view('<u4')
    bits = ((u + np.uint32(0x7fff) + ((u >> 16) & 1)) >> 16).astype('<u2')
    require(np.isfinite(_float(bits)).all(), 'BF16 conversion overflow')
    return bits


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
    """One FP32 rounding per node; legacy public ops reject tiny inexact.

    The rare tiny candidates are checked with integer ratios, independently of
    the scalar implementation. Exp's internal nodes deliberately ignore flags.
    """
    a, b = np.broadcast_arrays(np.asarray(left, dtype=np.float32),
                               np.asarray(right, dtype=np.float32))
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
    """Degree-7 source recipe: 9 mul + 8 add, each independently FP32 RNE.

    The >=80 branch still evaluates expScale and then selects +0, as in the
    source; its internal flags are not public Mul/op6 flags. No numpy.exp call.
    """
    magnitude = np.abs(np.asarray(values, dtype=np.float32))
    coefficients = np.array([math.pow(-math.log(2), i) / math.factorial(i)
                             for i in range(8)], dtype=np.float32)
    with np.errstate(all='ignore'):
        scaled = np.multiply(magnitude, np.float32(1 / math.log(2)), dtype=np.float32)
        active = magnitude < np.float32(80)
        # Inactive lanes must not cast expScale's allowed overflow to integer.
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


def _history(x, history):
    # Retain raw QKV bytes, including signed zero; never conv or SiLU values.
    return np.concatenate((history.T, x), axis=0)[-4:].T.copy().astype('<u2').tobytes()


def _identity(qkv_raw, weight_raw, rows, channels, history_raw):
    return dict(rows=rows, channels=channels, cold=history_raw is None,
                qkv_sha256=sha(qkv_raw), weight_sha256=sha(weight_raw),
                history_in_sha256=None if history_raw is None else sha(history_raw),
                history_layout='channel_major_oldest_to_newest_raw_BF16',
                reference_only=True, rtl_executed=False, hardware_cycles=None,
                history_committed=False, generation_advanced=False,
                full_official_block_executed=False)


def fixed_conv(qkv_raw, weight_raw, rows, channels=6144, history_raw=None, *, root=ROOT):
    """Return ({conv, silu, history}: BF16 bytes, identity) for fixed arithmetic.

    Accepted domain matches the owner: finite consumed BF16 values, finite
    public FP32 results, finite BF16 boundaries, conv > -80, and no inexact
    underflow in legacy public Add/Div/Mul. Mul6 accepts finite underflow.
    """
    x, weight, history = _inputs(qkv_raw, weight_raw, rows, channels, history_raw)
    _environment()
    source_hashes = {OWNER_SOURCE: OWNER_SHA, SCALAR_SOURCE: SCALAR_SHA}
    for path, expected in source_hashes.items():
        require(sha((Path(root) / path).read_bytes()) == expected, 'fixed source drift: ' + path)
    samples = _float(np.concatenate((history.T, x), axis=0))
    weights = _float(weight)
    total = np.zeros((rows, channels), dtype=np.float32)
    for tap in range(4):
        product = _node('mul', samples[tap + 1:tap + 1 + rows], weights[:, tap])
        total = _node('add', total, product, legacy=True)
    conv = _bf16(total)
    convolved = _float(conv)
    require(not np.any(convolved <= np.float32(-80)), 'unsupported negative conv <= -80')
    probability = _exp_negative(convolved)
    denominator = _node('add', np.float32(1), probability, legacy=True)
    inverse = _node('div', np.float32(1), denominator, legacy=True)
    selected = np.where(np.signbit(convolved), probability, np.float32(1))
    signed = _node('mul', inverse, selected, legacy=True)
    activated = _node('mul', signed, convolved, legacy=True)
    raw = dict(conv=conv.tobytes(), silu=_bf16(activated).tobytes(), history=_history(x, history))
    identity = _identity(qkv_raw, weight_raw, rows, channels, history_raw)
    identity.update(scope='INDEPENDENT_NUMPY_FIXED_CONV4_SILU_RECIPE',
        source_sha256=source_hashes, implementation_sha256=sha(Path(__file__).read_bytes()),
        numpy=np.__version__, arithmetic='4_mul6_4_add0_conv_BF16_17_exp_nodes_sigmoid_terminal_BF16',
        exp_internal_nodes=dict(mul=9, add=8, saturated_branch_mul=1),
        scalar_or_owner_called=False, output_sha256={name: sha(data) for name, data in raw.items()})
    return raw, identity


def original_conv_functions(source, torch):
    """Compile unchanged official AST nodes; the hub decorator alone is identity."""
    require(sha(source) == SOURCE_SHA, 'pinned official source hash changed')
    names = ('causal_conv1d_fn', 'causal_conv1d_update')
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    require(len(functions) == 2 and {node.name for node in functions} == set(names),
            'official Conv function set changed')
    for node in functions:
        require([ast.unparse(d) for d in node.decorator_list] ==
                [f"use_kernel_func_from_hub_with_fallback('{node.name}', 'causal_conv1d')"],
                'official Conv dispatch changed')
    namespace = dict(torch=torch, nn=torch.nn, F=torch.nn.functional,
                     ACT2FN={'silu': torch.nn.functional.silu},
                     use_kernel_func_from_hub_with_fallback=lambda *args: lambda fn: fn)
    exec(compile(ast.Module(body=functions, type_ignores=[]), SOURCE, 'exec'), namespace)
    return {name: namespace[name] for name in names}


def native_conv(qkv_raw, weight_raw, rows, channels=6144, history_raw=None, *, root=ROOT):
    """Return original fullshape official BF16 Conv/SiLU and raw history bytes.

    Cold uses [1,C,M] without prepended zeros. Warm uses the explicit prefill
    cache transformation [four raw history samples, M new samples], calls the
    original fn on [1,C,M+4], then selects the last M outputs. It never replaces
    a prefill call with repeated M1 calls or causal_conv1d_update.
    """
    x, weight, history = _inputs(qkv_raw, weight_raw, rows, channels, history_raw)
    require(os.environ.get('ATEN_CPU_CAPABILITY') == 'default',
            'set ATEN_CPU_CAPABILITY=default before importing Torch')
    import torch
    require(torch.__version__.split('+')[0] == '2.10.0', 'frozen Torch 2.10.0 required')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    capability = torch.backends.cpu.get_cpu_capability()
    require(capability in ('NO AVX', 'DEFAULT'), 'frozen Torch DEFAULT CPU backend required')
    source = (Path(root) / SOURCE).read_bytes()
    functions = original_conv_functions(source, torch)
    hidden = torch.frombuffer(bytearray(qkv_raw), dtype=torch.bfloat16).reshape(1, rows, channels).transpose(1, 2)
    weights = torch.frombuffer(bytearray(weight_raw), dtype=torch.bfloat16).reshape(channels, 4)
    if history_raw is not None:
        state = torch.frombuffer(bytearray(history_raw), dtype=torch.bfloat16).reshape(1, channels, 4)
        hidden = torch.cat((state, hidden), dim=-1)
    require(list(hidden.shape) == [1, channels, rows + (4 if history_raw is not None else 0)],
            'native fullshape changed')
    with torch.inference_mode():
        # Both parameter choices are supported by the unchanged official fn.
        conv = functions['causal_conv1d_fn'](hidden, weights, bias=None, activation=None)
        silu = functions['causal_conv1d_fn'](hidden, weights, bias=None, activation='silu')
        if history_raw is not None:
            conv, silu = conv[:, :, -rows:], silu[:, :, -rows:]
    require(torch.isfinite(conv).all().item() and torch.isfinite(silu).all().item(),
            'nonfinite official Conv output')
    def raw_tensor(value):
        return value.transpose(1, 2).contiguous().view(torch.int16).numpy().astype('<i2', copy=False).tobytes()
    raw = dict(conv=raw_tensor(conv), silu=raw_tensor(silu), history=_history(x, history))
    identity = _identity(qkv_raw, weight_raw, rows, channels, history_raw)
    identity.update(scope='PINNED_OFFICIAL_FULLSHAPE_CONV_FALLBACK_OPERATIONS_ONLY',
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        official_source_sha256=sha(source), optional_hub_decorator='identity_no_external_kernel',
        operator='causal_conv1d_fn', update_operator_called=False,
        conv_boundary='original_function_activation_None', activation='torch.nn.functional.silu',
        input_shape=list(hidden.shape), weight_shape=[channels, 4],
        history_mode='cold_without_cache' if history_raw is None else 'explicit_warm_prefill_prepend4_fn_tailM',
        backend=dict(torch=torch.__version__, torch_git=torch.version.git_version,
                     cpu_capability=capability, requested_cpu_capability=os.environ['ATEN_CPU_CAPABILITY'],
                     machine=platform.machine(), threads=torch.get_num_threads(),
                     deterministic=True, autocast=False, float32_matmul_precision='highest',
                     mkldnn_enabled=torch.backends.mkldnn.enabled, configuration=torch.__config__.show()),
        output_sha256={name: sha(data) for name, data in raw.items()})
    return raw, identity


def compare_bf16(actual, expected):
    require(type(actual) is bytes and type(expected) is bytes and len(actual) == len(expected)
            and len(actual) > 0 and len(actual) % 2 == 0, 'same complete BF16 comparison shape')
    a, b = np.frombuffer(actual, '<u2'), np.frombuffer(expected, '<u2')
    fa, fb = _float(a), _float(b)
    require(np.isfinite(fa).all() and np.isfinite(fb).all(), 'nonfinite BF16 comparison')
    def ordered(bits):
        value = bits.astype(np.int32)
        return np.where(value & 0x8000, 0x8000 - (value & 0x7fff), 0x8000 + value)
    ulp = np.abs(ordered(a) - ordered(b))
    delta = np.abs(fa.astype(np.float64) - fb.astype(np.float64))
    different = a != b
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(different)),
                numerical_mismatches=int(np.count_nonzero(ulp)), max_bf16_ulp=int(ulp.max()),
                max_abs=float(delta.max()), mean_abs=float(delta.mean()),
                signed_zero_only_mismatches=int(np.count_nonzero(different & (ulp == 0))),
                first_bit_mismatch=int(np.flatnonzero(different)[0]) if different.any() else None,
                actual_sha256=sha(actual), expected_sha256=sha(expected))


def verify_outputs(qkv_raw, weight_raw, rows, actual_silu, actual_history, *, official_qkv,
                   output, phase, actual_conv=None, channels=6144, root=ROOT):
    """Three separate cold-window gates, without claiming observed pre-SiLU.

    Actual SiLU/history and observed Conv, when supplied, must match the fixed
    recipe bitwise. Same-input native Conv/SiLU limits are the original <=1
    BF16 ULP; the full prefix comparison uses max .03125 / mean .005.
    No tolerance is added or relaxed; missing Conv observations stay explicit.
    """
    require(isinstance(phase, str) and re.fullmatch(r'[A-Za-z0-9_-]+', phase) is not None,
            'safe nonempty phase label')
    _inputs(qkv_raw, weight_raw, rows, channels, None)
    require(type(actual_silu) is bytes and len(actual_silu) == rows * channels * 2 and
            type(actual_history) is bytes and len(actual_history) == channels * 8,
            'complete actual SiLU/history shapes')
    require(actual_conv is None or type(actual_conv) is bytes and
            len(actual_conv) == rows * channels * 2, 'complete actual pre-SiLU Conv shape')
    contract_raw = (Path(root) / GATE_SOURCE).read_bytes()
    thresholds = json.loads(contract_raw)['native_thresholds']
    wanted = dict(conv_same_canonical_input_max_bf16_ulp=1, silu_same_canonical_input_max_bf16_ulp=1,
                  end_to_end_max_abs=0.03125, end_to_end_mean_abs=0.005)
    require(all(thresholds.get(key) == value for key, value in wanted.items()),
            'original Conv native thresholds changed')
    fixed, fixed_identity = fixed_conv(qkv_raw, weight_raw, rows, channels, root=root)
    same, same_identity = native_conv(qkv_raw, weight_raw, rows, channels, root=root)
    official, official_identity = native_conv(official_qkv, weight_raw, rows, channels, root=root)
    fixed_silu = compare_bf16(actual_silu, fixed['silu'])
    fixed_history = compare_bf16(actual_history, fixed['history'])
    same_silu = compare_bf16(actual_silu, same['silu'])
    end_silu = compare_bf16(actual_silu, official['silu'])
    fixed_report = dict(passed=actual_silu == fixed['silu'] and actual_history == fixed['history'],
                        silu=fixed_silu, raw_history=fixed_history, identity=fixed_identity)
    same_report = dict(passed=same_silu['max_bf16_ulp'] <= 1, silu=same_silu,
                       max_bf16_ulp=1, identity=same_identity,
                       conv=dict(status='missing_actual_pre_silu', passed=None, max_bf16_ulp=1),
                       fixed_reference_conv_diagnostic=compare_bf16(fixed['conv'], same['conv']))
    actual = dict(silu=actual_silu, history=actual_history)
    if actual_conv is not None:
        fixed_report['conv'] = compare_bf16(actual_conv, fixed['conv'])
        fixed_report['passed'] &= actual_conv == fixed['conv']
        same_conv = compare_bf16(actual_conv, same['conv'])
        same_report['conv'] = dict(status='observed_actual_pre_silu', comparison=same_conv,
                                   passed=same_conv['max_bf16_ulp'] <= 1, max_bf16_ulp=1)
        same_report['passed'] &= same_report['conv']['passed']
        actual['conv'] = actual_conv
    end_report = dict(passed=end_silu['max_abs'] <= 0.03125 and end_silu['mean_abs'] <= 0.005,
                      silu=end_silu, thresholds=dict(max_abs=0.03125, mean_abs=0.005),
                      identity=official_identity)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for family, values in (('actual', actual),
                           ('fixed', fixed), ('native_sameinput', same), ('native_endtoend', official)):
        for name, data in values.items():
            path = output / f'{phase}.conv_{family}_{name}.bf16le'
            require(not path.exists(), 'refuse to overwrite comparison artifact: ' + str(path))
            path.write_bytes(data)
            require(path.read_bytes() == data, 'comparison artifact write mismatch')
            artifacts[f'{family}_{name}'] = dict(path=str(path), bytes=len(data), sha256=sha(data))
    return dict(passed=fixed_report['passed'] and same_report['passed'] and end_report['passed'],
                scope='COLD_PREFILL_ACTUAL_CONV_SILU_RAW_HISTORY_THREE_SEPARATE_GATES',
                missing_actual_pre_silu=actual_conv is None,
                actual_conv_gate_complete=actual_conv is not None,
                conv_gate_complete=actual_conv is not None,
                fixed=fixed_report, native_sameinput=same_report, endtoend=end_report,
                gate_source=GATE_SOURCE, gate_source_sha256=sha(contract_raw),
                artifacts=artifacts, history_committed=False, rtl_executed=False)
