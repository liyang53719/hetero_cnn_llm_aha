#!/usr/bin/env python3
"""Pinned, complete Qwen2 L0 eager forward versus independent NumPy stages.

This executes one genuine checkpoint layer, not the full model, logits, an RTL
simulation, or a hardware-recipe oracle. BF16 stage acceptance uses the existing
numerical_contract v0. FP32 is explicitly a diagnostic with no invented budget.
"""
from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import platform
import resource
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('config/upstream/weight_headers/qwen2_1p5b')
MODEL_REVISION = 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
FORWARD_REVISION = '9fe3f585bb4ea29f209dc705d269fbe292e1128f'
SOURCE_HASHES = {
    'modeling_qwen2.py': 'f1c7a117ced20ee632e4c17d09982863304d6e30bb44f0ccdebd4b27dde259ad',
    'configuration_qwen2.py': '71aa00c48b4b586e283033afe11ce9df8c3e9bbc51613e11cd0617b103c5582b',
    'config.json': 'a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136',
}
EXPORT_TOKEN_MAJOR = {'q', 'k'}
REQUIRED_STAGES = {
    'x', 'n0', 'qr', 'kr', 'v', 'q', 'k', 'cache_k', 'cache_v',
    'repeat_k', 'repeat_v', 'scores', 'logits', 'prob', 'pv', 'att',
    'o', 'r', 'n1', 'gate', 'up', 'silu', 'act', 'down', 'y',
    'cos', 'sin', 'mask', 'softmax_fp32',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def digest_array(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def bf16(value: np.ndarray) -> np.ndarray:
    """IEEE round-to-nearest, ties-to-even, materialized as decoded FP32."""
    value = np.asarray(value, dtype=np.float32)
    if not np.isfinite(value).all():
        raise ValueError('nonfinite BF16 input')
    bits = value.view(np.uint32)
    rounded = ((bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) & np.uint32(0xffff0000)).view(np.float32)
    if not np.isfinite(rounded).all():
        raise ValueError('BF16 conversion overflow')
    return rounded


def causal_mask(tokens: int, past: int, mode: str) -> np.ndarray:
    if tokens <= 0 or past < 0 or mode not in ('bf16', 'fp32'):
        raise ValueError('invalid mask dimensions or mode')
    lowest = np.array([0xff7f0000 if mode == 'bf16' else 0xff7fffff], dtype=np.uint32).view(np.float32)[0]
    query = past + np.arange(tokens)
    key = np.arange(past + tokens)
    return np.where(key[None, :] > query[:, None], lowest, np.float32(0))[None, None].astype(np.float32)


def compare(actual: np.ndarray, reference: np.ndarray) -> dict:
    a, r = np.asarray(actual, dtype=np.float32), np.asarray(reference, dtype=np.float32)
    if a.shape != r.shape or a.size == 0:
        raise ValueError('shape mismatch or empty stage')
    if not np.isfinite(a).all() or not np.isfinite(r).all():
        raise ValueError('nonfinite stage')
    av, rv = a.astype(np.float64).reshape(-1), r.astype(np.float64).reshape(-1)
    error = av - rv
    rn, an, en = float(np.linalg.norm(rv)), float(np.linalg.norm(av)), float(np.linalg.norm(error))
    maximum, scale = float(np.max(np.abs(error))), float(np.max(np.abs(rv)))
    different = np.flatnonzero(a.reshape(-1).view(np.uint32) != r.reshape(-1).view(np.uint32))
    return {
        'shape': list(a.shape), 'elements': int(a.size),
        'max_abs': maximum, 'mean_abs': float(np.mean(np.abs(error))),
        'relative_l2': en / rn if rn else (0.0 if en == 0 else None),
        'cosine': float(np.dot(av, rv) / (an * rn)) if an and rn else float(an == rn),
        'normalized_max_abs': maximum / scale if scale else (0.0 if maximum == 0 else None),
        'different_elements': int(different.size), 'bit_exact': different.size == 0,
        'first_difference_flat': int(different[0]) if different.size else None,
        'actual_f32_sha256': digest_array(a), 'reference_f32_sha256': digest_array(r),
        'finite': True,
    }


def load_policy(root: Path) -> dict:
    import re
    path = root / 'spec/numerical_contract.md'
    content = path.read_text()
    policy = {'source': str(path.relative_to(root)), 'sha256': sha(path)}
    for key, title in [('operator', 'BF16 single operator'), ('block', 'BF16 one Transformer block')]:
        match = re.search(re.escape(title) + r':\s+max_abs <= ([0-9.eE+-]+)\s+mean_abs <= ([0-9.eE+-]+)', content)
        if not match:
            raise ValueError('missing existing numerical contract: ' + key)
        policy[key] = {'max_abs': float(match[1]), 'mean_abs': float(match[2])}
    policy['scope'] = 'Existing BF16 v0 operator/block budget; not an FP32, logits, or model-quality contract'
    return policy


def stage_verdict(name: str, metrics: dict, mode: str, policy: dict) -> dict:
    if name == 'mask':
        return {'contract': 'exact_causal_mask', 'passed': metrics['bit_exact']}
    if mode == 'fp32' or name == 'softmax_fp32':
        return {'contract': None, 'passed': None, 'status': 'DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE'}
    limit = policy['block' if name == 'y' else 'operator']
    return {'contract': 'spec/numerical_contract.md:' + ('block' if name == 'y' else 'operator'),
            'limits': limit, 'passed': metrics['max_abs'] <= limit['max_abs'] and metrics['mean_abs'] <= limit['mean_abs']}


def independent_forward(weights: dict, x: np.ndarray, config: dict, mode: str,
                        cache: tuple[np.ndarray, np.ndarray] | None = None) -> tuple[dict, tuple]:
    """No official helper, torch operation, or native intermediate feeds this path."""
    if mode not in ('bf16', 'fp32'):
        raise ValueError('unknown arithmetic mode')
    round_output = bf16 if mode == 'bf16' else lambda value: np.asarray(value, dtype=np.float32)
    stages = {'x': np.array(x, dtype=np.float32, copy=True)}
    batch, tokens, hidden = x.shape
    heads, kvheads = int(config['num_attention_heads']), int(config['num_key_value_heads'])
    dim, groups = hidden // heads, heads // kvheads
    past = 0 if cache is None else cache[0].shape[-2]
    if batch != 1 or hidden != int(config['hidden_size']) or dim % 2:
        raise ValueError('unsupported input shape')

    def keep(name, value):
        value = np.asarray(value, dtype=np.float32)
        stages[name] = value
        return value

    def norm(value, name):
        variance = np.mean(np.square(value, dtype=np.float32), axis=-1, keepdims=True, dtype=np.float32)
        inverse = np.reciprocal(np.sqrt(variance + np.float32(config['rms_norm_eps']), dtype=np.float32))
        return round_output(round_output(value * inverse) * weights[name + '.weight'])

    def linear(value, name, bias=False):
        output = np.matmul(value, weights[name + '.weight'].T, dtype=np.float32)
        if bias:
            output = output + weights[name + '.bias']
        return round_output(output)

    n0 = keep('n0', norm(x, 'input_layernorm'))
    qr = keep('qr', linear(n0, 'self_attn.q_proj', True))
    kr = keep('kr', linear(n0, 'self_attn.k_proj', True))
    v = keep('v', linear(n0, 'self_attn.v_proj', True))
    qh = qr.reshape(batch, tokens, heads, dim).transpose(0, 2, 1, 3)
    kh = kr.reshape(batch, tokens, kvheads, dim).transpose(0, 2, 1, 3)
    vh = v.reshape(batch, tokens, kvheads, dim).transpose(0, 2, 1, 3)
    inverse = np.reciprocal(np.power(np.float32(config['rope_theta']), np.arange(0, dim, 2, dtype=np.float32) / np.float32(dim), dtype=np.float32))
    angles = np.outer(np.arange(past + tokens, dtype=np.float32), inverse)
    angles = np.concatenate((angles, angles), axis=-1)
    cosine = keep('cos', round_output(np.cos(angles, dtype=np.float32)))
    sine = keep('sin', round_output(np.sin(angles, dtype=np.float32)))
    c, s = cosine[None, None, past:], sine[None, None, past:]

    def rotate(value):
        swapped = np.concatenate((-value[..., dim // 2:], value[..., :dim // 2]), axis=-1)
        return round_output(round_output(value * c) + round_output(swapped * s))

    q, k = keep('q', rotate(qh)), keep('k', rotate(kh))
    cache_k = keep('cache_k', k.copy() if cache is None else np.concatenate((cache[0], k), axis=-2))
    cache_v = keep('cache_v', vh.copy() if cache is None else np.concatenate((cache[1], vh), axis=-2))
    repeated_k = keep('repeat_k', np.repeat(cache_k, groups, axis=1))
    repeated_v = keep('repeat_v', np.repeat(cache_v, groups, axis=1))
    scores = keep('scores', round_output(round_output(np.matmul(q, repeated_k.swapaxes(-1, -2), dtype=np.float32)) / math.sqrt(dim)))
    mask = keep('mask', causal_mask(tokens, past, mode))
    logits = keep('logits', round_output(scores + mask))
    exp = np.exp(logits - np.max(logits, axis=-1, keepdims=True), dtype=np.float32)
    softmax_fp32 = keep('softmax_fp32', exp / np.sum(exp, axis=-1, keepdims=True, dtype=np.float32))
    prob = keep('prob', round_output(softmax_fp32))
    pv = keep('pv', round_output(np.matmul(prob, repeated_v, dtype=np.float32)))
    att = keep('att', pv.transpose(0, 2, 1, 3).reshape(batch, tokens, hidden))
    o = keep('o', linear(att, 'self_attn.o_proj'))
    r = keep('r', round_output(x + o))
    n1 = keep('n1', norm(r, 'post_attention_layernorm'))
    gate = keep('gate', linear(n1, 'mlp.gate_proj'))
    up = keep('up', linear(n1, 'mlp.up_proj'))
    silu = keep('silu', round_output(gate / (np.float32(1) + np.exp(-gate, dtype=np.float32))))
    act = keep('act', round_output(silu * up))
    down = keep('down', linear(act, 'mlp.down_proj'))
    keep('y', round_output(r + down))
    if set(stages) != REQUIRED_STAGES:
        raise ValueError('independent stage coverage mismatch')
    for name, value in stages.items():
        if not np.isfinite(value).all():
            raise ValueError('nonfinite independent ' + name)
    return stages, (cache_k, cache_v)


def attention_observers(module) -> dict:
    """Find assignment boundaries in the frozen function; never rewrite it."""
    tree = ast.parse(Path(inspect.getsourcefile(module)).read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Qwen2Attention')
    forward = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'forward')
    targets = {}
    for node in ast.walk(forward):
        if not isinstance(node, ast.Assign):
            continue
        expression = ast.unparse(node.value)
        captures = None
        if expression.startswith('self.rotary_emb('):
            captures = {'cos': 'cos', 'sin': 'sin'}
        elif expression.startswith('apply_rotary_pos_emb('):
            captures = {'q': 'query_states', 'k': 'key_states'}
        elif expression.startswith('past_key_value.update('):
            captures = {'cache_k': 'key_states', 'cache_v': 'value_states'}
        elif expression.startswith('repeat_kv(key_states,'):
            captures = {'repeat_k': 'key_states'}
        elif expression.startswith('repeat_kv(value_states,'):
            captures = {'repeat_v': 'value_states'}
        elif expression.startswith('torch.matmul(query_states,'):
            captures = {'scores': 'attn_weights'}
        elif expression == 'attn_weights + attention_mask':
            captures = {'logits': 'attn_weights'}
        elif expression.startswith('nn.functional.softmax('):
            captures = {'prob': 'attn_weights'}
        elif expression.startswith('torch.matmul(attn_weights,'):
            captures = {'pv': 'attn_output'}
        if captures:
            targets[node.lineno] = (node.end_lineno, captures)
    if len(targets) != 9:
        raise ValueError('frozen attention observation boundary mismatch')
    return targets


def torch_storage_equal(actual, reference) -> bool:
    import torch
    return (actual.shape == reference.shape and actual.dtype == reference.dtype and
            torch.equal(actual.contiguous().view(torch.uint8), reference.contiguous().view(torch.uint8)))


def native_forward(module, layer, x, mode: str, cache=None) -> tuple[dict, object]:
    import torch
    from transformers.modeling_attn_mask_utils import _prepare_4d_causal_attention_mask
    native = {'x': x.detach().clone()}
    past = 0 if cache is None else cache.get_seq_length(0)
    if cache is None:
        cache = module.DynamicCache()
    mask = _prepare_4d_causal_attention_mask(None, x.shape[:2], x, past)
    # M>=2 in production. The tiny tests also retain an explicit causal mask.
    if mask is None:
        mask = torch.zeros((1, 1, x.shape[1], past + x.shape[1]), dtype=x.dtype)
    native['mask'] = mask.detach().clone()
    positions = torch.arange(past, past + x.shape[1], dtype=torch.long).unsqueeze(0)
    handles = []

    def save(name):
        return lambda _module, _args, value: native.__setitem__(name, value.detach().clone())

    for name, submodule in {
        'n0': layer.input_layernorm, 'qr': layer.self_attn.q_proj,
        'kr': layer.self_attn.k_proj, 'v': layer.self_attn.v_proj,
        'o': layer.self_attn.o_proj, 'n1': layer.post_attention_layernorm,
        'gate': layer.mlp.gate_proj, 'up': layer.mlp.up_proj,
        'silu': layer.mlp.act_fn, 'down': layer.mlp.down_proj,
    }.items():
        handles.append(submodule.register_forward_hook(save(name)))
    for name, submodule in {'att': layer.self_attn.o_proj, 'r': layer.post_attention_layernorm, 'act': layer.mlp.down_proj}.items():
        handles.append(submodule.register_forward_pre_hook(lambda _module, args, key=name: native.__setitem__(key, args[0].detach().clone())))
    boundaries = attention_observers(module)
    target_code = layer.self_attn.forward.__func__.__code__
    softmax_code = torch.nn.functional.softmax.__code__
    pending = None

    def trace(frame, event, arg):
        nonlocal pending
        if frame.f_code is softmax_code:
            if event == 'return':
                native['softmax_fp32'] = arg.detach().clone()
            return trace
        if frame.f_code is not target_code:
            return None
        if event in ('line', 'return'):
            if pending is not None and (event == 'return' or frame.f_lineno > pending[0]):
                for name, local in pending[1].items():
                    native[name] = frame.f_locals[local].detach().clone()
                pending = None
            if event == 'line' and frame.f_lineno in boundaries:
                pending = boundaries[frame.f_lineno]
        return trace

    old_trace = sys.gettrace()
    if old_trace is not None:
        raise ValueError('refuse to replace an existing Python tracer')
    try:
        sys.settrace(trace)
        with torch.inference_mode():
            result = layer(x, attention_mask=mask, position_ids=positions,
                           past_key_value=cache, output_attentions=True, use_cache=True)
        native['y'] = result[0].detach().clone()
    finally:
        sys.settrace(old_trace)
        for handle in handles:
            handle.remove()
    if set(native) != REQUIRED_STAGES:
        raise ValueError('native stage coverage mismatch: ' + repr(sorted(REQUIRED_STAGES - set(native))))
    for name, value in native.items():
        if not bool(torch.isfinite(value).all()):
            raise ValueError('nonfinite official ' + name)
    return native, cache


def runtime_identity(root: Path) -> tuple[object, dict]:
    import torch
    import transformers
    from transformers.models.qwen2 import modeling_qwen2 as module
    from transformers.models.qwen2 import configuration_qwen2
    if transformers.__version__ != '4.40.1':
        raise ValueError('requires exactly Transformers 4.40.1')
    installed = {'modeling_qwen2.py': Path(module.__file__), 'configuration_qwen2.py': Path(configuration_qwen2.__file__)}
    for name, expected in SOURCE_HASHES.items():
        if sha(root / SOURCE / name) != expected:
            raise ValueError('pinned source hash mismatch: ' + name)
        if name in installed and sha(installed[name]) != expected:
            raise ValueError('installed source differs from frozen official source: ' + name)
    return module, {
        'python': platform.python_version(), 'torch': torch.__version__, 'numpy': np.__version__,
        'transformers': transformers.__version__, 'device': 'cpu', 'attention': 'eager',
        'model_revision': MODEL_REVISION, 'forward_revision': FORWARD_REVISION,
        'source_sha256': SOURCE_HASHES, 'installed_sources_verified_exact': True,
        'torch_build': torch.__config__.show(), 'numpy_build': str(np.__config__.CONFIG),
        'cache_utils_sha256': sha(Path(transformers.__file__).parent / 'cache_utils.py'),
        'mask_utils_sha256': sha(Path(transformers.__file__).parent / 'modeling_attn_mask_utils.py'),
        'activations_sha256': sha(Path(transformers.__file__).parent / 'activations.py'),
        'runner_sha256': sha(Path(__file__)),
    }


def export_value(value: np.ndarray, name: str) -> np.ndarray:
    if name in EXPORT_TOKEN_MAJOR:
        b, h, m, d = value.shape
        value = value.transpose(0, 2, 1, 3).reshape(b, m, h * d)
    return np.ascontiguousarray(value, dtype='<f4')


def expected_shapes(config: dict, tokens: int, past: int) -> dict:
    hidden, intermediate = int(config['hidden_size']), int(config['intermediate_size'])
    heads, kvheads = int(config['num_attention_heads']), int(config['num_key_value_heads'])
    dim, total = hidden // heads, tokens + past
    shapes = {name: [1, tokens, hidden] for name in ('x', 'n0', 'qr', 'att', 'o', 'r', 'n1', 'down', 'y')}
    shapes.update({name: [1, tokens, kvheads * dim] for name in ('kr', 'v')})
    shapes.update({name: [1, tokens, intermediate] for name in ('gate', 'up', 'silu', 'act')})
    shapes.update({name: [1, heads, tokens, total] for name in ('scores', 'logits', 'prob', 'softmax_fp32')})
    shapes.update({name: [1, kvheads, total, dim] for name in ('cache_k', 'cache_v')})
    shapes.update({name: [1, heads, total, dim] for name in ('repeat_k', 'repeat_v')})
    shapes.update({'q': [1, heads, tokens, dim], 'k': [1, kvheads, tokens, dim],
                   'pv': [1, heads, tokens, dim], 'mask': [1, 1, tokens, total],
                   'cos': [total, dim], 'sin': [total, dim]})
    return shapes


def audit_semantics(stages: dict, previous: dict | None, config: dict, mode: str) -> dict:
    tokens, hidden = stages['x'].shape[1:]
    kvheads, heads = int(config['num_key_value_heads']), int(config['num_attention_heads'])
    past = stages['cache_k'].shape[-2] - tokens
    rounded = bf16 if mode == 'bf16' else lambda value: value.astype(np.float32)
    exact = lambda a, b: a.shape == b.shape and np.array_equal(a.view(np.uint32), b.view(np.uint32))
    mask = causal_mask(tokens, past, mode)
    checks = {
        'mask_exact': exact(stages['mask'], mask),
        'cache_append_k_exact': exact(stages['cache_k'][..., -tokens:, :], stages['k']),
        'cache_append_v_exact': exact(stages['cache_v'][..., -tokens:, :], stages['v'].reshape(1, tokens, kvheads, -1).transpose(0, 2, 1, 3)),
        'future_probability_zero': bool(np.all(stages['prob'][np.broadcast_to(mask != 0, stages['prob'].shape)] == 0)),
        'fp32_probability_sum_within_2e_5': bool(np.all(np.abs(stages['softmax_fp32'].sum(axis=-1, dtype=np.float32) - 1) <= 2e-5)),
        'probability_materialization_exact': exact(stages['prob'], rounded(stages['softmax_fp32'])),
        'gqa_k_exact': exact(stages['repeat_k'], np.repeat(stages['cache_k'], heads // kvheads, axis=1)),
        'gqa_v_exact': exact(stages['repeat_v'], np.repeat(stages['cache_v'], heads // kvheads, axis=1)),
        'attention_layout_exact': exact(stages['att'], stages['pv'].transpose(0, 2, 1, 3).reshape(1, tokens, hidden)),
        'attention_residual_exact': exact(stages['r'], rounded(stages['x'] + stages['o'])),
        'activation_product_exact': exact(stages['act'], rounded(stages['silu'] * stages['up'])),
        'final_residual_exact': exact(stages['y'], rounded(stages['r'] + stages['down'])),
    }
    if previous is not None:
        checks['cache_prefix_k_unchanged'] = exact(stages['cache_k'][..., :past, :], previous['cache_k'])
        checks['cache_prefix_v_unchanged'] = exact(stages['cache_v'][..., :past, :], previous['cache_v'])
    return checks


def validate_small_gate(path: Path, identity: dict, payload_sha: str, policy: dict,
                        config: dict, embeddings: np.ndarray, carried: bool, threads: int) -> None:
    """Revalidate full M16 evidence, not a self-asserted PASS string."""
    try:
        report = json.loads(path.read_text())
        required = {
            'schema_version': 1, 'tokens': 16, 'carried': carried, 'layer': 0,
            'status': 'PASS_BF16_STAGE_BUDGET', 'model_id': 'Qwen/Qwen2-1.5B-Instruct',
            'identity': identity, 'payload_manifest_sha256': payload_sha,
            'policy': policy, 'torch_threads': threads,
            'blas_environment': {key: os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS')},
            'official_framework_forward': True, 'rtl_execution': False,
        }
        for key, expected in required.items():
            if key not in report or type(report[key]) is not type(expected) or report[key] != expected:
                raise ValueError('M16 binding mismatch: ' + key)
        if set(report['modes']) != {'bf16', 'fp32'}:
            raise ValueError('M16 mode inventory mismatch')
        evidence_root = path.resolve().parent
        for mode in ('bf16', 'fp32'):
            phases = report['modes'][mode]['phases']
            if len(phases) != (2 if carried else 1):
                raise ValueError('M16 phase inventory mismatch')
            previous = {'native': None, 'independent': None}
            for phase, receipt in enumerate(phases):
                ids = list(range(phase * 16, (phase + 1) * 16))
                expected_status = 'PASS_BF16_STAGE_BUDGET' if mode == 'bf16' else 'DIAGNOSTIC_FP32'
                if (receipt['phase'] != phase or receipt['past_tokens'] != phase * 16 or
                    receipt['token_ids'] != ids or receipt['position_ids'] != ids or
                    receipt['failed_stages'] != [] or receipt['status'] != expected_status or
                    receipt['all_semantics_exact'] is not True or not all(v is True for v in receipt['semantics'].values())):
                    raise ValueError('M16 phase binding mismatch')
                if set(receipt['stages']) != REQUIRED_STAGES:
                    raise ValueError('M16 stage inventory mismatch')
                loaded = {'native': {}, 'independent': {}}
                shapes = expected_shapes(config, 16, phase * 16)
                for name in sorted(REQUIRED_STAGES):
                    entry = receipt['stages'][name]
                    if entry['shape'] != shapes[name]:
                        raise ValueError('M16 tensor shape mismatch: ' + name)
                    for kind in ('native', 'independent'):
                        relative = f'{mode}/phase_{phase}/{kind}_{name}.f32le'
                        tensor_path = evidence_root / relative
                        if (entry[kind + '_file'] != relative or tensor_path.is_symlink() or
                            not tensor_path.resolve().is_relative_to(evidence_root)):
                            raise ValueError('M16 tensor path mismatch')
                        if tensor_path.stat().st_size != math.prod(shapes[name]) * 4 or sha(tensor_path) != entry[kind + '_file_sha256']:
                            raise ValueError('M16 tensor bytes/hash mismatch: ' + name)
                        array = np.fromfile(tensor_path, dtype='<f4')
                        if name in EXPORT_TOKEN_MAJOR:
                            b, h, m, d = shapes[name]
                            exported_shape = [b, m, h * d]
                            array = array.reshape(b, m, h, d).transpose(0, 2, 1, 3).copy()
                        else:
                            exported_shape = shapes[name]
                            array = array.reshape(shapes[name])
                        if entry[kind + '_export_shape'] != exported_shape:
                            raise ValueError('M16 export shape mismatch')
                        loaded[kind][name] = array
                    metrics = compare(loaded['native'][name], loaded['independent'][name])
                    for key, value in metrics.items():
                        if entry.get(key) != value:
                            raise ValueError('M16 recomputed metric mismatch: ' + name + ':' + key)
                    verdict = stage_verdict(name, metrics, mode, policy)
                    if verdict['passed'] is False or any(entry.get(key) != value for key, value in verdict.items()):
                        raise ValueError('M16 recomputed stage failure: ' + name)
                    array = loaded['native'][name]
                    is_bf16 = mode == 'bf16' and name != 'softmax_fp32'
                    if is_bf16 and np.any(array.view(np.uint32) & 0xffff):
                        raise ValueError('M16 BF16 storage mismatch')
                    expected_dtype = 'torch.bfloat16' if is_bf16 else 'torch.float32'
                    stored = (array.view(np.uint32) >> 16).astype('<u2') if is_bf16 else array
                    if entry['actual_storage_dtype'] != expected_dtype or digest_array(stored) != entry['actual_storage_sha256']:
                        raise ValueError('M16 original storage digest mismatch')
                for kind in ('native', 'independent'):
                    if not np.array_equal(loaded[kind]['x'].view(np.uint32), embeddings[ids][None].view(np.uint32)):
                        raise ValueError('M16 input does not match current checkpoint embeddings')
                    if not all(audit_semantics(loaded[kind], previous[kind], config, mode).values()):
                        raise ValueError('M16 recomputed semantic failure: ' + kind)
                    previous[kind] = loaded[kind]
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        raise ValueError('incomplete or invalid M16 evidence: ' + str(error)) from error


def run_gate(root: Path, payload_dir: Path, output_dir: Path, tokens: int = 16,
             carried: bool = False, threads: int = 4, small_gate: Path | None = None) -> dict:
    import torch
    sys.path.insert(0, str(root / 'src'))
    sys.path.insert(0, str(root / 'scripts'))
    from qwen2_layer0_payload import load_payload
    if tokens not in (16, 128) or not 1 <= threads <= 8:
        raise ValueError('only M16 or M128 and 1..8 CPU threads are supported')
    if output_dir.exists():
        raise ValueError('refuse to overwrite gate output')
    # Scope is bounded to 47M layer parameters, 256 embedding rows, at most 256 KV
    # positions and 12*128*256 attention values. Never instantiate Qwen2Model.
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    torch.set_default_dtype(torch.float32)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    module, identity = runtime_identity(root)
    config_dict = json.loads((root / SOURCE / 'config.json').read_text())
    config = module.Qwen2Config(**config_dict)
    config._attn_implementation = 'eager'
    policy = load_policy(root)
    manifest, payload = load_payload(root, payload_dir)
    records = {entry['local_name']: entry for entry in manifest['tensors']}
    weights = {}
    for name, data in payload.items():
        values = (np.frombuffer(data, dtype='<u2').astype(np.uint32) << 16).view(np.float32)
        weights[name] = values.reshape(records[name]['shape'])
    embeddings = weights.pop('embed_tokens.rows_0_255')
    expected = {'input_layernorm.weight', 'post_attention_layernorm.weight'}
    for name in ('q_proj', 'k_proj', 'v_proj', 'o_proj'):
        expected.add('self_attn.' + name + '.weight')
        if name != 'o_proj':
            expected.add('self_attn.' + name + '.bias')
    expected |= {'mlp.' + name + '.weight' for name in ('gate_proj', 'up_proj', 'down_proj')}
    if set(weights) != expected or embeddings.shape != (256, config.hidden_size):
        raise ValueError('payload does not contain the exact complete L0 plus embeddings')
    del payload
    if tokens == 128:
        if small_gate is None:
            raise ValueError('M128 requires a completed valid --small-gate M16 RESULT.json')
        validate_small_gate(small_gate, identity, sha(payload_dir / 'manifest.json'), policy,
                            config_dict, embeddings, carried, threads)
    output_dir.mkdir(parents=True)
    result = {
        'schema_version': 1, 'status': 'RUNNING', 'model_id': 'Qwen/Qwen2-1.5B-Instruct',
        'layer': 0, 'tokens': tokens, 'carried': carried, 'identity': identity,
        'policy': policy, 'torch_threads': threads, 'blas_environment': {key: os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS')}, 'm16_gate_sha256': sha(small_gate) if small_gate else None,
        'payload_manifest_sha256': sha(payload_dir / 'manifest.json'),
        'manifest_whole_checkpoint_hash_verified': False,
        'input': 'genuine checkpoint embedding rows for explicit sequential token IDs, no tokenizer/template',
        'arithmetic': {
            'bf16': 'Official eager CPU BF16. Independent NumPy FP32 primitives with explicit ties-even BF16 after each materialized producer; RMS reduction and softmax FP32; RMS normalized value rounded before gamma; each RoPE product rounded before addition; both residuals BF16.',
            'fp32': 'Official eager CPU FP32 and independently evaluated NumPy FP32 equations from the same BF16 checkpoint values; diagnostic only, no approved FP32 tolerance.',
            'rope': 'split-half full 128-dimensional RoPE; FP32 initial frequency/table computation then cast to activation dtype; absolute cache positions',
            'mask': 'exact lower triangular additive mask, finite dtype minimum; no padding or sliding window',
            'cache': 'each path appends and carries its own computed post-RoPE K and raw V; no cache or intermediate substitution',
            'softmax': 'stable FP32 softmax then activation dtype, no dropout in eval',
        },
        'resource_budget': {'maximum_query_tokens': 128, 'maximum_key_tokens': 256, 'maximum_torch_threads': 8, 'full_model_loaded': False},
        'modes': {}, 'official_framework_forward': True, 'rtl_execution': False,
        'hardware_recipe_acceptance': False, 'logits': False, 'full_model_quality': False,
    }
    started = time.monotonic()
    for mode, dtype in [('bf16', torch.bfloat16), ('fp32', torch.float32)]:
        mode_started = time.monotonic()
        layer = module.Qwen2DecoderLayer(config, layer_idx=0)
        layer.load_state_dict({name: torch.from_numpy(value).to(dtype) for name, value in weights.items()}, strict=True, assign=True)
        layer = layer.to(dtype=dtype).eval()
        native_cache = None
        independent_cache = None
        phases = []
        for phase in range(2 if carried else 1):
            phase_started = time.monotonic()
            ids = list(range(phase * tokens, (phase + 1) * tokens))
            x = embeddings[ids][None].copy()
            xt = torch.from_numpy(x).to(dtype)
            previous_native = None if native_cache is None else (native_cache.key_cache[0].clone(), native_cache.value_cache[0].clone())
            previous_independent = None if independent_cache is None else tuple(value.copy() for value in independent_cache)
            native, native_cache = native_forward(module, layer, xt, mode, native_cache)
            independent, independent_cache = independent_forward(weights, x, config_dict, mode, independent_cache)
            stage_results = {}
            destination = output_dir / mode / ('phase_' + str(phase))
            destination.mkdir(parents=True)
            for name in sorted(REQUIRED_STAGES):
                n = native[name].float().numpy()
                i = independent[name]
                metrics = compare(n, i)
                metrics.update(stage_verdict(name, metrics, mode, policy))
                metrics['actual_storage_dtype'] = str(native[name].dtype)
                metrics['actual_storage_sha256'] = hashlib.sha256(native[name].contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()
                for prefix, value in [('native', n), ('independent', i)]:
                    exported = export_value(value, name)
                    filename = prefix + '_' + name + '.f32le'
                    exported.tofile(destination / filename)
                    metrics[prefix + '_file'] = str((destination / filename).relative_to(output_dir))
                    metrics[prefix + '_export_shape'] = list(exported.shape)
                    metrics[prefix + '_file_sha256'] = sha(destination / filename)
                stage_results[name] = metrics
            # Exact semantic/cache invariants within each path, independent of all
            # native-versus-NumPy approximate floating-point metrics.
            nk, nv = native_cache.key_cache[0], native_cache.value_cache[0]
            semantic = {
                'mask_exact': stage_results['mask']['bit_exact'],
                'native_fp32_probability_sum_within_2e_5': bool(torch.all(torch.abs(native['softmax_fp32'].sum(dim=-1) - 1) <= 2e-5)),
                'independent_fp32_probability_sum_within_2e_5': bool(np.all(np.abs(independent['softmax_fp32'].sum(axis=-1, dtype=np.float32) - 1) <= 2e-5)),
                'native_cache_append_k_exact': torch_storage_equal(nk[..., -tokens:, :], native['k']),
                'native_cache_append_v_exact': torch_storage_equal(nv[..., -tokens:, :], native['v'].view(1, tokens, config.num_key_value_heads, -1).transpose(1, 2)),
                'independent_cache_append_k_exact': np.array_equal(independent_cache[0][..., -tokens:, :].view(np.uint32), independent['k'].view(np.uint32)),
                'independent_cache_append_v_exact': np.array_equal(independent_cache[1][..., -tokens:, :].view(np.uint32), independent['v'].reshape(1, tokens, config.num_key_value_heads, -1).transpose(0, 2, 1, 3).view(np.uint32)),
                'native_future_probability_zero': bool(torch.all(native['prob'].masked_select(native['mask'] != 0) == 0)),
                'independent_future_probability_zero': bool(np.all(independent['prob'][np.broadcast_to(independent['mask'] != 0, independent['prob'].shape)] == 0)),
            }
            if previous_native is not None:
                semantic['native_cache_prefix_unchanged'] = all(torch_storage_equal(old, now[..., :phase * tokens, :]) for old, now in zip(previous_native, (nk, nv)))
                semantic['independent_cache_prefix_unchanged'] = all(np.array_equal(old.view(np.uint32), now[..., :phase * tokens, :].view(np.uint32)) for old, now in zip(previous_independent, independent_cache))
            failed = [name for name, value in stage_results.items() if value['passed'] is False]
            phases.append({
                'phase': phase, 'past_tokens': phase * tokens, 'token_ids': ids,
                'position_ids': ids, 'stages': stage_results,
                'failed_stages': failed, 'semantics': semantic,
                'all_semantics_exact': all(semantic.values()),
                'status': ('PASS_BF16_STAGE_BUDGET' if not failed and all(semantic.values()) else 'FAIL_BF16_STAGE_BUDGET') if mode == 'bf16' else ('DIAGNOSTIC_FP32' if all(semantic.values()) else 'FAIL_FP32_SEMANTICS'),
                'seconds': time.monotonic() - phase_started,
            })
            del native, independent
        result['modes'][mode] = {'phases': phases, 'seconds': time.monotonic() - mode_started}
        del layer, native_cache, independent_cache
        gc.collect()
    passed = all(phase['status'] == 'PASS_BF16_STAGE_BUDGET' for phase in result['modes']['bf16']['phases'])
    passed = passed and all(phase['all_semantics_exact'] for phase in result['modes']['fp32']['phases'])
    result['status'] = 'PASS_BF16_STAGE_BUDGET' if passed else 'FAIL_BF16_STAGE_BUDGET'
    result['seconds'] = time.monotonic() - started
    result['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (output_dir / 'RESULT.json').write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--payload', type=Path, default=ROOT / 'work/qwen2_layer0_payload_20261011')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tokens', type=int, choices=(16, 128), default=16)
    parser.add_argument('--carried', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--small-gate', type=Path)
    args = parser.parse_args()
    result = run_gate(args.root.resolve(), args.payload.resolve(), args.out.resolve(), args.tokens, args.carried, args.threads, args.small_gate)
    print(json.dumps({'status': result['status'], 'tokens': result['tokens'], 'seconds': result['seconds'], 'peak_rss_kib': result['peak_rss_kib'], 'result': str(args.out / 'RESULT.json')}, sort_keys=True))
    return 0 if result['status'] == 'PASS_BF16_STAGE_BUDGET' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, ImportError) as error:
        print('ERROR ' + str(error), file=sys.stderr)
        raise SystemExit(2)
