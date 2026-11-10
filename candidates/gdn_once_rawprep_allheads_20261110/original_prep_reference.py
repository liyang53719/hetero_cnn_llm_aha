#!/usr/bin/env python3
"""Frozen FP32 input-preparation recipe; no torch and no injected recurrent state.

Inputs are explicitly BF16 Conv output and BF16 A/B projection *boundaries*.
This oracle does not imply those producers have been executed in hardware.
A_log retains original FP32, while checkpoint dt_bias is BF16, per frozen pin.
Only M1 is supported. Cold chunk and carried decode scaling differ explicitly.
"""
from __future__ import annotations
import math
import numpy as np

F = np.float32


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bf16(x):
    u = np.asarray(x, dtype='<f4').view('<u4')
    return ((u + 0x7fff + ((u >> 16) & 1)) >> 16).astype('<u2')


def fp(x):
    return (np.asarray(x, dtype='<u2').astype('<u4') << 16).view('<f4')


def add(a, b): return np.add(a, b, dtype=np.float32)
def mul(a, b): return np.multiply(a, b, dtype=np.float32)
def div(a, b): return np.divide(a, b, dtype=np.float32)


def exp_negative(x):
    """Published shared ExpNegative: degree7 exp(-abs(x)), saturation at80."""
    x = np.asarray(x, dtype='<f4')
    require(np.isfinite(x).all(), 'nonfinite exp input')
    safe_magnitude = np.where(np.abs(x) >= 80, F(0), np.abs(x))
    t = mul(safe_magnitude, F(1 / math.log(2)))
    k = t.astype(np.int32)
    fraction = np.subtract(t, k.astype(np.float32), dtype=np.float32)
    coefficients = [F((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    h = np.full(x.shape, coefficients[7], dtype='<f4')
    for i in range(6, -1, -1):
        h = add(mul(h, fraction), coefficients[i])
    scale = ((127 - k).astype('<u4') << 23).view('<f4')
    return np.where(np.abs(x) >= 80, F(0), mul(h, scale)).astype('<f4')


def softplus(x):
    """Shared opcode7 recipe: threshold20; log1p via odd atanh through15.

    The series variable is e/(2+e), e=exp(-abs(x)), hence at most1/3.
    Separate FP32 rounding at every operation is part of the recipe.
    Negative x<=-80 fail closed, matching the shared exp domain limit.
    """
    x = np.asarray(x, dtype='<f4')
    require(np.isfinite(x).all() and np.all(x > -80), 'softplus domain')
    # Threshold is a real control branch in hardware; do not evaluate huge x.
    active_x = np.where(x > F(20), F(0), x)
    e = exp_negative(active_x)
    y = div(e, add(F(2), e))
    square = mul(y, y)
    h = np.full(x.shape, F(1 / 15), dtype='<f4')
    for denominator in (13, 11, 9, 7, 5, 3, 1):
        h = add(mul(h, square), F(1 / denominator))
    log1p = mul(mul(F(2), y), h)
    return np.where(x > F(20), x, add(np.maximum(x, F(0)), log1p)).astype('<f4')


def recipe(query, key, value, a, b, a_log, dt_bias, *, recurrent_mode):
    """Return FP32 Q/K/V and padded FP32[H,16] gates from raw BF16 words."""
    require(type(recurrent_mode) is bool, 'explicit chunk/decode mode required')
    require(query.dtype == key.dtype == value.dtype == a.dtype == b.dtype == dt_bias.dtype == np.dtype('<u2'), 'raw BF16 storage required')
    require(a_log.dtype == np.dtype('<f4'), 'original FP32 A_log required')
    require(query.ndim == 2 and query.shape[1] == 128 and key.shape == value.shape == query.shape, 'M1 [heads,128] geometry required')
    heads = query.shape[0]
    require(1 <= heads <= 16 and a.shape == b.shape == a_log.shape == dt_bias.shape == (heads,), 'head geometry')
    q, k, v, a, b, bias = [fp(x) for x in (query, key, value, a, b, dt_bias)]
    require(all(np.isfinite(x).all() for x in (q, k, v, a, b, bias, a_log)), 'nonfinite input')
    require(np.all(np.abs(a_log) < 80) and np.all(b > -80), 'exp input domain')

    def norm(x):
        acc = np.zeros((heads, 1), dtype='<f4')
        for lane in range(128):
            acc = add(acc, mul(x[:, lane:lane + 1], x[:, lane:lane + 1]))
        inverse = div(F(1), np.sqrt(add(acc, F(1e-6)), dtype=np.float32))
        return mul(x, inverse)

    normalized_query, normalized_key = norm(q), norm(k)
    scaled_query = div(normalized_query, F(math.sqrt(128))) if recurrent_mode else mul(normalized_query, F(1 / math.sqrt(128)))
    soft = softplus(add(a, bias))
    e = exp_negative(a_log)
    a_exp = np.where(np.signbit(a_log), e, div(F(1), e)).astype('<f4')
    decay = mul(np.negative(a_exp, dtype=np.float32), soft)
    e = exp_negative(b)
    inverse = div(F(1), add(F(1), e))
    beta = fp(bf16(mul(inverse, np.where(np.signbit(b), e, F(1)))))
    require(np.all(decay <= 0) and np.all(decay > -80), 'recurrent log-decay domain')
    require(all(np.isfinite(x).all() for x in (scaled_query, normalized_key, v, decay, beta)), 'nonfinite output')
    gates = np.zeros((heads, 16), dtype='<f4')
    gates[:, 0], gates[:, 1] = decay, beta
    return scaled_query, normalized_key, v, gates


def generate(root, source, output, heads=2):
    """Two real heads x two M1 tokens. Comparator files are never DUT feedback."""
    import ctypes
    import hashlib
    import inspect
    import json
    from pathlib import Path
    import torch
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from heteronpu.pinned_gdn_payload import load_payload
    from heteronpu.matrix_norm_rope_candidate import fma_rne
    from heteronpu.qwen35_numpy_reference import compare
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    require(not output.exists(), 'fresh output required')
    require(heads in (1, 2), 'bounded one/two-head fixture only')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    profile = json.loads((root / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    source_file = Path(inspect.getfile(official))
    require(sha(source_file.read_bytes()) == profile['transformers_source']['sha256'], 'official source drift')
    cfg_bytes = (root / 'config/upstream/qwen3_5_0p8b/config.json').read_bytes()
    require(sha(cfg_bytes) == profile['config_sha256'], 'config drift')
    cfg = json.loads(cfg_bytes)['text_config']
    require(tuple(cfg[k] for k in ('linear_num_key_heads', 'linear_num_value_heads', 'linear_key_head_dim', 'linear_value_head_dim')) == (16, 16, 128, 128), 'geometry drift')
    manifest, raw = load_payload(root, root / 'work/qwen35_layer0_payload')
    producer_manifest = json.loads((source / 'manifest.json').read_text())
    require(producer_manifest['model_revision'] == profile['revision'], 'source model drift')
    for name, rec in producer_manifest['files'].items():
        data = (source / name).read_bytes()
        require(len(data) == rec['bytes'] and sha(data) == rec['sha256'], 'source corruption: ' + name)
    specs = {x['local_name']: x for x in manifest['tensors']}
    require(specs['linear_attn.A_log']['dtype'] == 'F32' and specs['linear_attn.dt_bias']['dtype'] == 'BF16', 'parameter dtype drift')
    alog = np.frombuffer(raw['linear_attn.A_log'], dtype='<f4')[:heads].copy()
    bias = np.frombuffer(raw['linear_attn.dt_bias'], dtype='<u2')[:heads].copy()
    weight = {role: np.frombuffer(raw[f'linear_attn.in_proj_{role}.weight'], dtype='<u2').reshape(16, 1024)[:heads] for role in ('a', 'b')}
    fmaf = ctypes.CDLL('libm.so.6').fmaf
    fmaf.argtypes = (ctypes.c_float, ctypes.c_float, ctypes.c_float)
    fmaf.restype = ctypes.c_float
    output.mkdir(parents=True)
    files, diagnostics = {}, []
    def save(name, array):
        data = np.ascontiguousarray(array).tobytes(); (output / name).write_bytes(data)
        files[name] = {'bytes': len(data), 'sha256': sha(data)}
    save('a_log.f32le', alog); save('dt_bias.bf16le', bias)
    fma_steps = 0
    for token in range(2):
        activation = np.fromfile(source / f'activation{token}.bf16le', dtype='<u2')
        conv = np.fromfile(source / f'expected_output{token}.bf16le', dtype='<u2').reshape(3, 16, 128)[:, :heads].copy()
        q, k, v = conv
        projected, native_projected = {}, {}
        for role in ('a', 'b'):
            accumulators = []
            for head in range(heads):
                acc, native_acc = 0, F(0)
                for lane in range(1024):
                    aa, bb = int(activation[lane]) << 16, int(weight[role][head, lane]) << 16
                    acc, _flags = fma_rne(aa, bb, acc)
                    af, bf = np.array([aa, bb], dtype='<u4').view('<f4')
                    native_acc = F(fmaf(float(af), float(bf), float(native_acc)))
                    require(int(np.asarray(native_acc).view('<u4')) == acc, 'independent integer/C fmaf mismatch')
                    fma_steps += 1
                accumulators.append(acc)
            projected[role] = bf16(np.array(accumulators, dtype='<u4').view('<f4'))
            xt = torch.from_numpy(fp(activation).copy()).to(torch.bfloat16)
            wt = torch.from_numpy(fp(weight[role]).copy()).to(torch.bfloat16)
            native_projected[role] = torch.nn.functional.linear(xt, wt)
            save(f'{role}{token}.bf16le', projected[role])
        actual = recipe(q, k, v, projected['a'], projected['b'], alog, bias, recurrent_mode=bool(token))
        qt, kt, vt = [torch.from_numpy(fp(x).copy()) for x in (q, k, v)]
        qn = official.l2norm(qt, eps=1e-6)
        official_q = qn / (128 ** .5) if token else qn * (128 ** -.5)
        official_k = official.l2norm(kt, eps=1e-6)
        at, bt = [torch.from_numpy(fp(projected[x]).copy()).to(torch.bfloat16) for x in ('a', 'b')]
        logt = torch.from_numpy(alog.copy()); biast = torch.from_numpy(fp(bias).copy()).to(torch.bfloat16)
        official_g = -logt.float().exp() * torch.nn.functional.softplus(at.float() + biast)
        official_beta = bt.sigmoid().float()
        gates = np.zeros((heads, 16), dtype='<f4'); gates[:, 0] = official_g.numpy(); gates[:, 1] = official_beta.numpy()
        comparisons = {}
        for label, input_words, result, expected in zip(('query', 'key', 'value'), (q, k, v), actual[:3], (official_q.numpy(), official_k.numpy(), vt.numpy())):
            save(f'{label}{token}.bf16le', input_words)
            save(f'expected_{label}{token}.f32le', result)
            save(f'official_{label}{token}.f32le', expected)
            comparisons[label] = compare(result, expected)
            comparisons[label]['raw_bit_mismatches'] = int(np.count_nonzero(result.view('<u4') != expected.view('<u4')))
        save(f'expected_gates{token}.f32le', actual[3]); save(f'official_gates{token}.f32le', gates)
        for index, label in enumerate(('g', 'beta')):
            comparisons[label] = compare(actual[3][:, index], gates[:, index])
            comparisons[label]['raw_bit_mismatches'] = int(np.count_nonzero(actual[3][:, index].view('<u4') != gates[:, index].view('<u4')))
        diagnostics.append({'case': 'cold_chunk_m1' if token == 0 else 'carried_decode_m1', 'same_boundary_official': comparisons,
                            'projection_official_max_abs': {role: float(np.max(np.abs(fp(projected[role]) - native_projected[role].float().numpy()))) for role in ('a', 'b')},
                            'a': fp(projected['a']).tolist(), 'b': fp(projected['b']).tolist(), 'a_log': alog.tolist(), 'dt_bias': fp(bias).tolist()})
    passed = all(x['mismatches'] == 0 for case in diagnostics for x in case['same_boundary_official'].values())
    report = {'status': 'INPUT_PREP_REFERENCE_DIAGNOSTIC_ONLY',
              'within_diagnostic_tolerance': passed,
              'official_stage_acceptance': 'UNASSIGNED; existing full-output comparison defaults are diagnostics here, not a new stage gate',
              'scope': 'isolated actual-checkpoint input prep; Conv and A/B are stage input boundaries, no Host/full-block claim',
              'model_revision': profile['revision'], 'official_source_sha256': sha(source_file.read_bytes()), 'config_sha256': sha(cfg_bytes),
              'all14_weight_sha256': {k: v['sha256'] for k, v in specs.items()},
              'source_manifest_sha256': sha((source / 'manifest.json').read_bytes()), 'source': str(source),
              'source_code_sha256': sha(Path(__file__).read_bytes()), 'heads': heads, 'tokens_per_command': 1,
              'independent_projection_integer_c_fmaf_steps': fma_steps, 'same_boundary_diagnostic_tolerance': {'atol': 1e-4, 'rtol': 1e-4, 'source': 'qwen35_numpy_reference.compare defaults; not an independent stage acceptance threshold'},
              'checks': diagnostics, 'files': files, 'full_block_supported': False, 'rtl_executed': False}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'scope', 'checks', 'independent_projection_integer_c_fmaf_steps')}, indent=2))
    return 0


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / 'src'))
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--heads', type=int, default=2)
    args = parser.parse_args()
    raise SystemExit(generate(root, args.source, args.output, args.heads))
