#!/usr/bin/env python3
"""Independent FP32-RNE input/post RMSNorm recipe and pinned real captures.

Fixtures contain original BF16 weights and stay in ignored work directories.
Native same-input measurements are diagnostics, never an invented tolerance.
"""
from pathlib import Path
import argparse
import hashlib
import inspect
import json
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


def recipe(hidden, weight):
    """Every arithmetic node rounds to FP32; only the final output is BF16."""
    require(hidden.dtype == weight.dtype == np.dtype('<u2'), 'original BF16 storage required')
    require(hidden.ndim >= 2 and weight.ndim == 1 and hidden.shape[-1] == weight.size, 'width geometry')
    width = weight.size
    require(32 <= width <= 65535 and width & (width - 1) == 0, 'power-of-two width required')
    x, w = fp(hidden), fp(weight)
    require(np.isfinite(x).all() and np.isfinite(w).all(), 'nonfinite input')
    stages = {}

    def keep(name, value):
        require(np.isfinite(value).all(), 'nonfinite ' + name)
        stages[name] = value
        return value

    with np.errstate(over='ignore', invalid='ignore', under='ignore', divide='ignore'):
        squares = keep('squares', np.multiply(x, x, dtype=np.float32))
        total = np.zeros(x.shape[:-1] + (1,), dtype='<f4')
        for lane in range(width):
            total = np.add(total, squares[..., lane:lane + 1], dtype=np.float32)
            require(np.isfinite(total).all(), 'nonfinite ascending sum')
        mean = keep('mean', np.multiply(total, np.float32(1 / width), dtype=np.float32))
        variance = keep('variance', np.add(mean, np.float32(1e-6), dtype=np.float32))
        root = keep('root', np.sqrt(variance, dtype=np.float32))
        inverse = keep('inverse_rms', np.divide(np.float32(1), root, dtype=np.float32))
        normalized = keep('normalized_fp32', np.multiply(x, inverse, dtype=np.float32))
        offset_weight = keep('one_plus_weight', np.add(np.float32(1), w, dtype=np.float32))
        weighted = keep('weighted_fp32', np.multiply(normalized, offset_weight, dtype=np.float32))
        output = bf16(weighted)
        require(np.isfinite(fp(output)).all(), 'nonfinite BF16 result')
    return output, stages


def diagnostics(actual, official):
    require(actual.shape == official.shape and actual.size > 0, 'comparison shape')
    require(actual.dtype == official.dtype == np.dtype('<u2'), 'comparison BF16 storage')
    require(np.isfinite(fp(actual)).all() and np.isfinite(fp(official)).all(), 'nonfinite comparison')
    a, b = actual.astype(np.int32), official.astype(np.int32)
    ordered = lambda v: np.where(v & 0x8000, 0x8000 - (v & 0x7fff), 0x8000 + v)
    ulp = np.abs(ordered(a) - ordered(b))
    delta = np.abs(fp(actual).astype(np.float64) - fp(official).astype(np.float64))
    relative = np.divide(delta, np.abs(fp(official)), out=np.zeros_like(delta), where=fp(official) != 0)
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(a != b)),
                numeric_mismatches=int(np.count_nonzero(ulp)),
                signed_zero_only_mismatches=int(np.count_nonzero((a != b) & (ulp == 0))),
                max_bf16_ulp=int(ulp.max()), max_abs=float(delta.max()),
                max_relative_nonzero_reference=float(relative.max()),
                nonzero_vs_reference_zero=int(np.count_nonzero((delta != 0) & (fp(official) == 0))),
                official_acceptance='UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')


def from_capture(root, capture, output):
    """Reuse a verified combined official capture without loading the model again."""
    require(not output.exists(), 'output must be fresh')
    require((root / 'work').resolve() in output.resolve().parents, 'fixtures must remain inside ignored work')
    capture_raw = (capture / 'manifest.json').read_bytes()
    source = json.loads(capture_raw)
    profile = json.loads((root / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    require(source['model_id'] == 'Qwen/Qwen3.5-0.8B' and
            source['revision'] == '2fc06364715b967f1860aea9cf38778875588b17', 'capture model/revision drift')
    require(source['official_source_sha256'] == profile['transformers_source']['sha256'], 'capture source drift')
    require(source['token_ids'] == [19, 92], 'capture tokens drift')
    pin = json.loads((root / 'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json').read_text())
    pins = {r['local_name']: r for r in pin['tensors']}
    data = {}
    for name, metadata in source['files'].items():
        require(Path(name).name == name, 'capture filename must be a basename')
        raw = (capture / name).read_bytes()
        require(len(raw) == metadata['bytes'] and sha(raw) == metadata['sha256'], 'capture file drift: ' + name)
        data[name] = raw
    report = dict(schema_version=1, scope='ISOLATED_INPUT_POST_RMSNORM_OWNER_NOT_FULL_BLOCK',
                  model_id=source['model_id'], revision=source['revision'], width=1024,
                  official_source_sha256=source['official_source_sha256'], token_ids=source['token_ids'],
                  source_parameter_dtypes=source['source_parameter_dtypes'],
                  capture_manifest_sha256=sha(capture_raw), files={}, cases={},
                  recipe_acceptance='EXACT_BITS', official_acceptance='DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN',
                  generator_sha256=sha(Path(__file__).read_bytes()))
    for name, local_name in (('input', 'input_layernorm.weight'), ('post', 'post_attention_layernorm.weight')):
        filename = f'{name}_weight.bf16le'
        require(pins[local_name]['dtype'] == 'BF16' and pins[local_name]['shape'] == [1024] and
                sha(data[filename]) == pins[local_name]['sha256'], 'original BF16 weight pin drift')
        require(source['source_parameter_dtypes'][local_name] == 'torch.bfloat16', 'captured parameter dtype drift')
        weight = np.frombuffer(data[filename], dtype='<u2')
        for label in ('cold1', 'carried1'):
            key = f'{name}_{label}'
            hidden = np.frombuffer(data[f'{key}_hidden.bf16le'], dtype='<u2').reshape(1, 1, 1024)
            native = np.frombuffer(data[f'{key}_official.bf16le'], dtype='<u2').reshape(1, 1, 1024)
            expected, _ = recipe(hidden, weight)
            data[f'{key}_recipe.bf16le'] = expected.tobytes()
            report['cases'][key] = diagnostics(expected, native)
    output.mkdir(parents=True)
    for name in ('input', 'post'):
        names = [f'{name}_weight.bf16le'] + [f'{name}_{label}_{kind}.bf16le'
                for label in ('cold1', 'carried1') for kind in ('hidden', 'official', 'recipe')]
        for filename in names:
            (output / filename).write_bytes(data[filename])
            report['files'][filename] = dict(bytes=len(data[filename]), sha256=sha(data[filename]))
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def generate(root, output):
    from heteronpu.pinned_gdn_payload import load_payload, F32_NAMES
    from heteronpu.pinned_prefix_payload import selection, payload_pin, token_fixture
    import torch
    from transformers import DynamicCache, Qwen3_5TextConfig
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    require(not output.exists(), 'output must be fresh')
    # Captures include original weights, so reject destinations outside ignored work.
    require((root / 'work').resolve() in output.resolve().parents, 'fixtures must remain inside ignored work')
    profile = json.loads((root / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    source = Path(inspect.getfile(official))
    require(sha(source.read_bytes()) == profile['transformers_source']['sha256'], 'official source drift')
    cfg_raw = (root / 'config/upstream/qwen3_5_0p8b/config.json').read_bytes()
    require(sha(cfg_raw) == profile['config_sha256'], 'configuration drift')
    cfg = Qwen3_5TextConfig.from_dict(json.loads(cfg_raw)['text_config'])
    require(cfg.hidden_size == 1024 and cfg.rms_norm_eps == 1e-6, 'RMSNorm geometry/epsilon drift')
    manifest, raw = load_payload(root, root / 'work/qwen35_layer0_payload')
    pinned = json.loads((root / 'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json').read_text())
    by_name = {r['local_name']: r for r in pinned['tensors']}
    for name in ('input_layernorm.weight', 'post_attention_layernorm.weight'):
        require(by_name[name]['dtype'] == 'BF16' and by_name[name]['shape'] == [1024], 'original weight dtype/shape')
        require(sha(raw[name]) == by_name[name]['sha256'], 'original weight bytes drift')
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
    captures = {name: [] for name in ('input', 'post')}

    def capture(name):
        def hook(module, args, result):
            require(args[0].dtype == result.dtype == module.weight.dtype == torch.bfloat16, 'RMSNorm dtype drift')
            captures[name].append((args[0].detach().clone(), result.detach().clone()))
        return hook

    handles = [layer.input_layernorm.register_forward_hook(capture('input')),
               layer.post_attention_layernorm.register_forward_hook(capture('post'))]
    embeddings = torch.frombuffer(bytearray(embedding), dtype=torch.bfloat16).reshape(256, 1024)
    token_ids = token_fixture(root)['token_ids'][:2]
    require(token_ids == [19, 92], 'cold/carried token fixture drift')
    cache = DynamicCache(config=cfg)
    with torch.inference_mode():
        for token_id in token_ids:
            layer(embeddings[token_id].reshape(1, 1, 1024), position_embeddings=None,
                  attention_mask=torch.ones((1, 1), dtype=torch.bool), past_key_values=cache)
            require(cache.layers[0].recurrent_states[0].dtype == torch.float32, 'recurrent state dtype drift')
    for handle in handles:
        handle.remove()
    require(all(len(v) == 2 for v in captures.values()), 'missing cold/carried RMSNorm captures')
    output.mkdir(parents=True)
    report = dict(schema_version=1, scope='ISOLATED_INPUT_POST_RMSNORM_OWNER_NOT_FULL_BLOCK',
                  model_id=manifest['model_id'], revision=manifest['revision'], width=1024,
                  official_source_sha256=sha(source.read_bytes()), embedding_sha256=sha(embedding),
                  token_ids=token_ids, source_parameter_dtypes=dtypes, cases={}, files={},
                  producer='pinned real embeddings 19,92 -> official layer0 cold1,carried1; input/post RMSNorm hooks',
                  recipe_nodes=['BF16->FP32', 'FP32 square', 'ascending FP32 sum from +0', 'FP32 * (1/1024)',
                                'FP32 + epsilon', 'FP32 sqrt', 'FP32 reciprocal', 'FP32 x*inverse',
                                'FP32 1+BF16_weight.float', 'FP32 normalized*offset_weight', 'BF16 RNE'],
                  recipe_acceptance='EXACT_BITS', official_acceptance='DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')

    def save(name, value):
        data = value if isinstance(value, bytes) else value.tobytes()
        (output / name).write_bytes(data)
        report['files'][name] = dict(bytes=len(data), sha256=sha(data))

    for name, local_name in (('input', 'input_layernorm.weight'), ('post', 'post_attention_layernorm.weight')):
        save(f'{name}_weight.bf16le', raw[local_name])
        weight = np.frombuffer(raw[local_name], dtype='<u2')
        for label, values in zip(('cold1', 'carried1'), captures[name], strict=True):
            hidden, native = [v.contiguous().view(torch.int16).numpy().view('<u2').copy() for v in values]
            require(hidden.shape == native.shape == (1, 1, 1024), 'official hidden shape drift')
            expected, _ = recipe(hidden, weight)
            key = f'{name}_{label}'
            for kind, value in (('hidden', hidden), ('official', native), ('recipe', expected)):
                save(f'{key}_{kind}.bf16le', value)
            report['cases'][key] = diagnostics(expected, native)
    report['generator_sha256'] = sha(Path(__file__).read_bytes())
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--capture', type=Path, help='reuse combined official capture instead of running model')
    args = parser.parse_args()
    report = from_capture(args.root, args.capture, args.output) if args.capture else generate(args.root, args.output)
    print(json.dumps(report, indent=2))
