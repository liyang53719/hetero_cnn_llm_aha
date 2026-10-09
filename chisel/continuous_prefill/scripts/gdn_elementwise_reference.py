#!/usr/bin/env python3
"""BF16 residual/SiLU×up shared-Scalar recipe and one pinned official capture.

The recipe is compared bit-for-bit; differences from official native operators
are diagnostics with no new acceptance threshold. Generated payload stays local.
"""
from pathlib import Path
import argparse
import hashlib
import inspect
import json
import math
import numpy as np


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bf16(x):
    u = np.asarray(x, dtype='<f4').view('<u4')
    return ((u + 0x7fff + ((u >> 16) & 1)) >> 16).astype('<u2')


def fp(x):
    return (np.asarray(x, dtype='<u2').astype('<u4') << 16).view('<f4')


def finite(x, label):
    require(np.isfinite(x).all(), f'nonfinite {label}')
    return x


def recipe(op, a, b):
    """op is 'add' or 'silu_mul'. Every operation rounds independently to FP32.

    SiLU has an explicit BF16 intermediate because official act_fn(gate_proj(x))
    produces BF16 before its tensor multiplication by the BF16 up projection.
    Unsupported negative gates are legal SiLU inputs, but not this exp recipe.
    """
    require(op in ('add', 'silu_mul'), 'unsupported operation')
    require(a.shape == b.shape and a.size > 0, 'nonempty equal geometry required')
    require(a.dtype == b.dtype == np.dtype('<u2'), 'BF16 storage required')
    x, y = finite(fp(a), 'a'), finite(fp(b), 'b')
    f = np.float32
    if op == 'add':
        out = bf16(finite(np.add(x, y, dtype=np.float32), 'sum'))
        finite(fp(out), 'rounded sum')
        return out, {}
    require(np.all(x > -80), 'legal negative SiLU gate outside supported shared exp domain')
    # Keep the large-positive branch from overflowing the range-reduction cast.
    magnitude = np.where(np.abs(x) >= 80, f(0), np.abs(x))
    t = np.multiply(magnitude, f(1 / math.log(2)), dtype=np.float32)
    k = t.astype(np.int32)
    fraction = np.subtract(t, k.astype(np.float32), dtype=np.float32)
    coeff = [f((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    h = np.full(x.shape, coeff[7], dtype='<f4')
    for i in range(6, -1, -1):
        h = np.add(np.multiply(h, fraction, dtype=np.float32), coeff[i], dtype=np.float32)
    scale = ((127 - k).astype('<u4') << 23).view('<f4')
    e = np.where(np.abs(x) >= 80, f(0), np.multiply(h, scale, dtype=np.float32)).astype('<f4')
    inv = np.divide(f(1), np.add(f(1), e, dtype=np.float32), dtype=np.float32)
    sig = np.multiply(inv, np.where(np.signbit(x), e, f(1)), dtype=np.float32)
    activation_f32 = finite(np.multiply(sig, x, dtype=np.float32), 'SiLU')
    activation_bf16 = bf16(activation_f32)
    finite(fp(activation_bf16), 'rounded SiLU')
    out = bf16(finite(np.multiply(fp(activation_bf16), y, dtype=np.float32), 'product'))
    finite(fp(out), 'rounded product')
    return out, dict(silu_f32=activation_f32, silu_bf16=activation_bf16)


def diagnostics(actual, official):
    require(actual.shape == official.shape, 'comparison shape')
    a, b = actual.astype(np.int32), official.astype(np.int32)
    ordered = lambda v: np.where(v & 0x8000, 0x8000 - (v & 0x7fff), 0x8000 + v)
    ulp = np.abs(ordered(a) - ordered(b))
    delta = np.abs(fp(actual).astype(np.float64) - fp(official).astype(np.float64))
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(a != b)),
                numeric_mismatches=int(np.count_nonzero(ulp)), max_bf16_ulp=int(ulp.max()),
                max_abs=float(delta.max()), official_acceptance='UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')


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
    captures = {}
    handles = []
    def hook(name):
        def capture(module, args, result):
            require(args[0].dtype == result.dtype == torch.bfloat16, f'{name} BF16 boundary drift')
            captures[name] = (args[0].detach().clone(), result.detach().clone())
        return capture
    for name, module in [('input', layer.input_layernorm), ('post', layer.post_attention_layernorm),
                         ('o', layer.linear_attn.out_proj), ('gate', layer.mlp.gate_proj),
                         ('up', layer.mlp.up_proj), ('silu', layer.mlp.act_fn), ('down', layer.mlp.down_proj)]:
        handles.append(module.register_forward_hook(hook(name)))
    embeddings = torch.frombuffer(bytearray(embedding), dtype=torch.bfloat16).reshape(256, 1024)
    token_ids = token_fixture(root)['token_ids'][:2]
    cache = DynamicCache(config=cfg)
    output.mkdir(parents=True)
    report = dict(schema_version=1, scope='ISOLATED_ELEMENTWISE_AND_RMS_CAPTURE_NOT_FULL_BLOCK_ACCEPTANCE',
                  model_id=manifest['model_id'], revision=manifest['revision'], hidden_width=1024, ffn_width=3584,
                  official_source_sha256=sha(source.read_bytes()), config_sha256=sha(cfg_raw),
                  embedding_sha256=sha(embedding), token_ids=token_ids, source_parameter_dtypes=dtypes,
                  cases={}, files={}, recipe_acceptance='EXACT_BITS',
                  official_acceptance='DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')
    def bf_tensor(value):
        require(value.dtype == torch.bfloat16, 'capture dtype drift')
        return value.contiguous().view(torch.int16).numpy().view('<u2').copy()
    def save(name, data):
        raw_data = data if isinstance(data, bytes) else data.tobytes()
        (output / name).write_bytes(raw_data)
        report['files'][name] = dict(bytes=len(raw_data), sha256=sha(raw_data))
    for name in ('input', 'post'):
        weight = f'{name}_attention_layernorm.weight' if name == 'post' else 'input_layernorm.weight'
        require(tensors[weight].dtype == torch.bfloat16, 'RMS original BF16 weight required')
        save(f'{name}_weight.bf16le', raw[weight])
    with torch.inference_mode():
        for label, token_id in zip(('cold1', 'carried1'), token_ids, strict=True):
            captures.clear()
            hidden = embeddings[token_id].reshape(1, 1, 1024)
            native_output = layer(hidden, position_embeddings=None,
                                  attention_mask=torch.ones((1, 1), dtype=torch.bool), past_key_values=cache)
            require(cache.layers[0].recurrent_states[0].dtype == torch.float32, 'recurrent state dtype drift')
            require(set(captures) == {'input', 'post', 'o', 'gate', 'up', 'silu', 'down'}, 'missing hooks')
            for name in ('input', 'post'):
                for kind, tensor in zip(('hidden', 'official'), captures[name], strict=True):
                    save(f'{name}_{label}_{kind}.bf16le', bf_tensor(tensor))
            stages = [('residual1', 'add', hidden, captures['o'][1], captures['post'][0]),
                      ('silu_mul', 'silu_mul', captures['gate'][1], captures['up'][1], captures['down'][0]),
                      ('residual2', 'add', captures['post'][0], captures['down'][1], native_output)]
            report['cases'][label] = {}
            for name, op, ta, tb, ty in stages:
                a, b, native = map(bf_tensor, (ta, tb, ty))
                expected, intermediate = recipe(op, a, b)
                for kind, value in [('a', a), ('b', b), ('recipe', expected), ('official', native)]:
                    save(f'{label}_{name}_{kind}.bf16le', value)
                report['cases'][label][name] = diagnostics(expected, native)
                if op == 'silu_mul':
                    official_silu = bf_tensor(captures['silu'][1])
                    save(f'{label}_silu_official.bf16le', official_silu)
                    save(f'{label}_silu_recipe.bf16le', intermediate['silu_bf16'])
                    report['cases'][label]['silu_boundary'] = diagnostics(intermediate['silu_bf16'], official_silu)
                    report['cases'][label]['gate_min'] = float(fp(a).min())
                    report['cases'][label]['gate_max'] = float(fp(a).max())
    for handle in handles:
        handle.remove()
    report['generator_sha256'] = sha(Path(__file__).read_bytes())
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    print(json.dumps(generate(args.root, args.output), indent=2))
