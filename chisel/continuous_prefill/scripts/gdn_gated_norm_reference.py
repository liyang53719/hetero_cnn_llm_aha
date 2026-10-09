#!/usr/bin/env python3
"""Frozen shared-Scalar gated-norm recipe and bounded official layer0 capture.

Generated data are local-only test inputs/expectations. This script does not
assign a new tolerance or grant official acceptance from a diagnostic metric.
"""
from pathlib import Path
import argparse
import hashlib
import inspect
import json
import math
import numpy as np


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bf16(x):
    u = np.asarray(x, dtype='<f4').view('<u4')
    return ((u + 0x7fff + ((u >> 16) & 1)) >> 16).astype('<u2')


def fp(x):
    return (np.asarray(x, dtype='<u2').astype('<u4') << 16).view('<f4')


def recipe(core, gate, weight):
    """FP32 rounded stages; ascending 128-element sum; explicit BF16 boundary."""
    require(core.shape == gate.shape and core.shape[-1] == 128, 'head geometry')
    require(core.dtype == gate.dtype == np.dtype('<u2'), 'BF16 storage required')
    require(weight.dtype == np.dtype('<f4') and weight.shape == (128,), 'original FP32 gamma required')
    x, z = fp(core), fp(gate)
    require(np.isfinite(x).all() and np.isfinite(z).all() and np.isfinite(weight).all(), 'nonfinite input')
    require(np.all(z > -80), 'negative gate outside shared exp domain')
    f = np.float32
    squares = np.multiply(x, x, dtype=np.float32)
    acc = np.zeros(core.shape[:-1] + (1,), dtype='<f4')
    for lane in range(128):
        acc = np.add(acc, squares[..., lane:lane + 1], dtype=np.float32)
    mean = np.multiply(acc, f(1 / 128), dtype=np.float32)
    variance = np.add(mean, f(1e-6), dtype=np.float32)
    inverse = np.divide(f(1), np.sqrt(variance, dtype=np.float32), dtype=np.float32)
    normalized = bf16(np.multiply(x, inverse, dtype=np.float32))
    weighted = np.multiply(weight, fp(normalized), dtype=np.float32)
    t = np.multiply(np.abs(z), f(1 / math.log(2)), dtype=np.float32)
    # Positive large gates use the documented shared-service saturation branch.
    safe_t = np.where(np.abs(z) >= 80, f(0), t)
    k = safe_t.astype(np.int32)
    fraction = np.subtract(safe_t, k.astype(np.float32), dtype=np.float32)
    coefficients = [f((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    h = np.full(z.shape, coefficients[7], dtype='<f4')
    for i in range(6, -1, -1):
        h = np.add(np.multiply(h, fraction, dtype=np.float32), coefficients[i], dtype=np.float32)
    scale = ((127 - k).astype('<u4') << 23).view('<f4')
    exponential = np.where(np.abs(z) >= 80, f(0), np.multiply(h, scale, dtype=np.float32)).astype('<f4')
    inv = np.divide(f(1), np.add(f(1), exponential, dtype=np.float32), dtype=np.float32)
    sigmoid = np.multiply(inv, np.where(np.signbit(z), exponential, f(1)), dtype=np.float32)
    silu = np.multiply(sigmoid, z, dtype=np.float32)
    output = bf16(np.multiply(weighted, silu, dtype=np.float32))
    require(np.isfinite(fp(output)).all(), 'nonfinite result')
    return output, dict(normalized=normalized, inverse_rms=inverse, weighted=weighted, silu=silu)


def diagnostics(actual, official):
    require(actual.shape == official.shape, 'comparison shape')
    a, b = actual.astype(np.int32), official.astype(np.int32)
    ordered = lambda v: np.where(v & 0x8000, 0x8000 - (v & 0x7fff), 0x8000 + v)
    ulp = np.abs(ordered(a) - ordered(b))
    delta = np.abs(fp(actual).astype(np.float64) - fp(official).astype(np.float64))
    relative = np.divide(delta, np.abs(fp(official)), out=np.zeros_like(delta), where=fp(official) != 0)
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(a != b)),
                numeric_mismatches=int(np.count_nonzero(ulp)), max_bf16_ulp=int(ulp.max()),
                max_abs=float(delta.max()), max_relative_nonzero_reference=float(relative.max()),
                nonzero_vs_reference_zero=int(np.count_nonzero((delta != 0) & (fp(official) == 0))),
                official_acceptance='UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')


def generate(root, output):
    from heteronpu.pinned_gdn_payload import load_payload, F32_NAMES
    from heteronpu.pinned_prefix_payload import selection, payload_pin, token_fixture
    import torch
    from transformers import DynamicCache, Qwen3_5TextConfig
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    require(not output.exists(), 'output must be fresh')
    profile = json.loads((root / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    source = Path(inspect.getfile(official))
    require(sha(source.read_bytes()) == profile['transformers_source']['sha256'], 'official source drift')
    cfg_raw = (root / 'config/upstream/qwen3_5_0p8b/config.json').read_bytes()
    require(sha(cfg_raw) == profile['config_sha256'], 'configuration drift')
    cfg = Qwen3_5TextConfig.from_dict(json.loads(cfg_raw)['text_config'])
    manifest, raw = load_payload(root, root / 'work/qwen35_layer0_payload')
    _, specs = selection(root)
    pin = payload_pin(root, specs)
    embedding = (root / 'work/qwen35_prefix_payload/embed_tokens.rows_0_255.bin').read_bytes()
    require(sha(embedding) == pin['embed_tokens.rows_0_255'], 'embedding payload drift')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    layer = official.Qwen3_5DecoderLayer(cfg, layer_idx=0).eval()
    tensors = {r['local_name']: torch.frombuffer(bytearray(raw[r['local_name']]),
               dtype=torch.float32 if r['local_name'] in F32_NAMES else torch.bfloat16).reshape(r['shape'])
               for r in manifest['tensors']}
    result = layer.load_state_dict(tensors, strict=True, assign=True)
    require(not result.missing_keys and not result.unexpected_keys, 'incomplete 14-tensor load')
    dtypes = {k: str(v.dtype) for k, v in layer.named_parameters()}
    require(dtypes == {k: str(v.dtype) for k, v in tensors.items()}, 'parameter dtype drift')
    require(layer.linear_attn.norm.weight.dtype == torch.float32, 'gated gamma must stay FP32')
    captures = []
    def capture(module, args, result):
        require(args[0].dtype == args[1].dtype == result.dtype == torch.bfloat16, 'gated norm producer dtype drift')
        captures.append(tuple(v.detach().clone() for v in (*args, result)))
    handle = layer.linear_attn.norm.register_forward_hook(capture)
    embeddings = torch.frombuffer(bytearray(embedding), dtype=torch.bfloat16).reshape(256, 1024)
    token_ids = token_fixture(root)['token_ids'][:2]
    cache = DynamicCache(config=cfg)
    with torch.inference_mode():
        for token_id in token_ids:
            layer(embeddings[token_id].reshape(1, 1, 1024), position_embeddings=None,
                  attention_mask=torch.ones((1, 1), dtype=torch.bool), past_key_values=cache)
            require(cache.layers[0].recurrent_states[0].dtype == torch.float32, 'recurrent state dtype drift')
    handle.remove()
    require(len(captures) == 2, 'missing cold/carried official norm captures')
    output.mkdir(parents=True)
    report = dict(schema_version=1, scope='ISOLATED_GATED_NORM_OWNER_NOT_FULL_BLOCK',
                  model_id=manifest['model_id'], revision=manifest['revision'], heads=16, width=128,
                  official_source_sha256=sha(source.read_bytes()), embedding_sha256=sha(embedding),
                  token_ids=token_ids, source_parameter_dtypes=dtypes, cases={}, files={},
                  producer='pinned real embedding -> official layer0 cold1 then carried1; norm forward hook',
                  recipe_acceptance='EXACT_BITS', official_acceptance='DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')
    def save(name, value):
        data = value if isinstance(value, bytes) else value.tobytes()
        (output / name).write_bytes(data)
        report['files'][name] = dict(bytes=len(data), sha256=sha(data))
    save('weight.f32le', raw['linear_attn.norm.weight'])
    gamma = np.frombuffer(raw['linear_attn.norm.weight'], dtype='<f4')
    for label, capture_values in zip(('cold1', 'carried1'), captures, strict=True):
        core, gate, native = [v.contiguous().view(torch.int16).numpy().view('<u2').copy() for v in capture_values]
        require(core.shape == gate.shape == native.shape == (16, 128), 'official head shape drift')
        expected, stages = recipe(core, gate, gamma)
        for kind, value in (('core', core), ('gate', gate), ('official', native), ('recipe', expected)):
            save(f'{label}_{kind}.bf16le', value)
        report['cases'][label] = dict(all_heads=diagnostics(expected, native),
                                     head0=diagnostics(expected[:1], native[:1]),
                                     core_min=float(fp(core).min()), core_max=float(fp(core).max()),
                                     gate_min=float(fp(gate).min()), gate_max=float(fp(gate).max()))
    report['generator_sha256'] = sha(Path(__file__).read_bytes())
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    print(json.dumps(generate(args.root, args.output), indent=2))
