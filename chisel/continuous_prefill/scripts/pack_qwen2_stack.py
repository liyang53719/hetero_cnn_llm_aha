#!/usr/bin/env python3
"""Pack official Qwen2 safetensors into immutable, bounded-memory stack arenas.

No reference intermediate is written. Q/K split-half RoPE coordinates are
permuted into the adjacent-pair convention of the Chisel block. The manifest
states this conversion explicitly. GGUF is deliberately not guessed here.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, struct
from pathlib import Path
from typing import Any
import numpy as np


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


class SafeCheckpoint:
    """Header validation plus read-only mappings, never torch.load/pickle."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config = json.loads((root / 'config.json').read_text())
        index = root / 'model.safetensors.index.json'
        self.files: dict[str, tuple[Path, int, dict[str, Any]]] = {}
        paths = sorted(set(json.loads(index.read_text())['weight_map'].values())) if index.exists() else ['model.safetensors']
        for name in paths:
            path = (root / name).resolve()
            require(path.is_relative_to(self.root), 'checkpoint path escapes root')
            size = path.stat().st_size
            with path.open('rb') as f:
                raw = f.read(8)
                require(len(raw) == 8, 'short safetensors prefix')
                length = struct.unpack('<Q', raw)[0]
                require(2 <= length <= min(64 << 20, size - 8), 'invalid safetensors header length')
                header = json.loads(f.read(length))
            spans = []
            for tensor, spec in header.items():
                if tensor == '__metadata__':
                    continue
                require(tensor not in self.files, 'duplicate tensor: ' + tensor)
                dtype = spec['dtype']; shape = spec['shape']; lo, hi = spec['data_offsets']
                require(dtype in ('BF16', 'F16', 'F32'), 'unsupported safetensor dtype ' + dtype)
                require(shape and all(type(x) is int and x > 0 for x in shape), 'invalid tensor shape')
                require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= size - 8 - length, 'invalid data offsets')
                require(hi - lo == math.prod(shape) * (4 if dtype == 'F32' else 2), 'tensor byte count mismatch')
                spans.append((lo, hi)); self.files[tensor] = (path, 8 + length + lo, spec)
            spans.sort()
            require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), 'overlapping tensor file ranges')

    def tensor(self, name: str, shape: tuple[int, ...] | None = None) -> np.memmap:
        require(name in self.files, 'missing tensor: ' + name)
        path, offset, spec = self.files[name]
        if shape is not None:
            require(tuple(spec['shape']) == shape, 'shape mismatch: ' + name)
        dtype = {'BF16': '<u2', 'F16': '<f2', 'F32': '<f4'}[spec['dtype']]
        return np.memmap(path, dtype=dtype, mode='r', offset=offset, shape=tuple(spec['shape']))

    def fp32(self, name: str, selected: Any = slice(None)) -> np.ndarray:
        source = self.tensor(name)[selected]
        if self.files[name][2]['dtype'] == 'BF16':
            value = (np.asarray(source, dtype='<u4') << 16).view('<f4')
        else:
            value = np.asarray(source, dtype='<f4')
        require(bool(np.isfinite(value).all()), 'nonfinite source: ' + name)
        return value


def read_layout(path: Path) -> dict[str, int]:
    text = path.read_text()
    values = {k: int(v) for k, v in re.findall(r'\b([A-Z][A-Z0-9_]*)\s*=\s*(\d+)(?:ULL)?', text)}
    required = ['H', 'F', 'HEADS', 'KVHEADS', 'HD', 'MAX_TOKENS', 'STACK_LAYERS', 'STACK_WEIGHT_BYTES', 'STACK_ROPE_BYTES', 'STACK_HIDDEN_BYTES', 'STACK_SCRATCH_BYTES', 'OFF_COS', 'OFF_SIN', 'OFF_X', 'OFF_Y', 'WRITABLE_START']
    require(all(k in values for k in required), 'not a generated stack layout')
    require(values['STACK_WEIGHT_BYTES'] == values['OFF_COS'], 'weight layout mismatch')
    return values


def adjacent_rope_permutation(heads: int, dim: int) -> np.ndarray:
    require(heads > 0 and dim > 0 and dim % 2 == 0, 'invalid RoPE dimensions')
    pairs = np.stack((np.arange(dim // 2), np.arange(dim // 2) + dim // 2), axis=1).reshape(-1)
    return np.concatenate([pairs + head * dim for head in range(heads)])


def validate_qwen2(config: dict[str, Any], l: dict[str, int], layers: list[int]) -> None:
    require(config.get('model_type') == 'qwen2', 'only official Qwen2 supported')
    for key, expected in [('hidden_size', l['H']), ('intermediate_size', l['F']), ('num_attention_heads', l['HEADS']), ('num_key_value_heads', l['KVHEADS'])]:
        require(config.get(key) == expected, 'configuration mismatch: ' + key)
    require(l['H'] == 1536 and l['F'] == 8960 and l['HEADS'] == 12 and l['KVHEADS'] == 2 and l['HD'] == 128, 'not the real Qwen2-1.5B layout')
    require(config.get('num_hidden_layers') == 28 and config.get('vocab_size') == 151936, 'unexpected Qwen2 layer/vocabulary count')
    require(float(config.get('rms_norm_eps', 0)) == 1e-6, 'hardware RMS epsilon contract mismatch')
    require(config.get('hidden_act') == 'silu' and not config.get('rope_scaling') and not config.get('use_sliding_window', False), 'unsupported activation/RoPE/window recipe')
    require(layers == list(range(len(layers))) and len(layers) == l['STACK_LAYERS'] and len(layers) <= 28, 'stack must be a contiguous prefix starting at layer zero')


def pack(checkpoint: SafeCheckpoint, l: dict[str, int], layers: list[int], token_ids: list[int], out: Path, revision: str) -> dict[str, Any]:
    validate_qwen2(checkpoint.config, l, layers)
    require(re.fullmatch(r'[0-9a-f]{40}', revision) is not None, 'exact upstream revision required')
    require(token_ids and len(token_ids) <= l['MAX_TOKENS'] and all(type(i) is int and 0 <= i < checkpoint.config['vocab_size'] for i in token_ids), 'invalid token IDs')
    require(not out.exists(), 'refuse to overwrite an earlier run')
    out.mkdir(parents=True)
    wbytes = l['STACK_WEIGHT_BYTES']; rope = wbytes * len(layers)
    ha = rope + l['STACK_ROPE_BYTES']; hb = ha + l['STACK_HIDDEN_BYTES']; scratch = hb + l['STACK_HIDDEN_BYTES']; total = scratch + l['STACK_SCRATCH_BYTES']
    arena = out / 'arena.bin'
    with arena.open('wb') as f:
        f.truncate(total)
    dst = np.memmap(arena, dtype='<f4', mode='r+', shape=(total // 4,))
    for begin in range(0, total // 4, 1 << 18):
        dst[begin:begin + (1 << 18)] = np.nan
    h, f, kh, d = l['H'], l['F'], l['KVHEADS'], l['HD']
    matrix_specs = [('wq', 'self_attn.q_proj.weight', h, h, l['HEADS']), ('wk', 'self_attn.k_proj.weight', h, kh*d, kh), ('wv', 'self_attn.v_proj.weight', h, kh*d, 0), ('wo', 'self_attn.o_proj.weight', h, h, 0), ('wg', 'mlp.gate_proj.weight', h, f, 0), ('wu', 'mlp.up_proj.weight', h, f, 0), ('wd', 'mlp.down_proj.weight', f, h, 0)]
    used: set[Path] = set(); tensors = []
    for slot, layer in enumerate(layers):
        prefix = f'model.layers.{layer}.'
        for target, suffix, k, n, heads in matrix_specs:
            name = prefix + suffix; checkpoint.tensor(name, (n, k)); used.add(checkpoint.files[name][0])
            base = (slot*wbytes + l['OFF_' + target.upper()]) // 4
            view = dst[base:base+k*n].reshape(k, n)
            perm = adjacent_rope_permutation(heads, d) if heads else None
            for kb in range(0, k, 64):
                block = checkpoint.fp32(name, (slice(None), slice(kb, min(k, kb+64))))
                view[kb:kb+block.shape[1], :] = (block[perm] if perm is not None else block).T
            tensors.append({'source': name, 'destination': target, 'layer': layer, 'conversion': 'HF_NK_to_device_KN' + ('_split_half_to_adjacent_QK' if heads else '')})
        for target, suffix, n, heads in [('gamma0', 'input_layernorm.weight', h, 0), ('gamma1', 'post_attention_layernorm.weight', h, 0), ('bq', 'self_attn.q_proj.bias', h, l['HEADS']), ('bk', 'self_attn.k_proj.bias', kh*d, kh), ('bv', 'self_attn.v_proj.bias', kh*d, 0)]:
            name = prefix + suffix; checkpoint.tensor(name, (n,)); used.add(checkpoint.files[name][0]); value = checkpoint.fp32(name)
            if heads:
                value = value[adjacent_rope_permutation(heads, d)]
            offset = (slot*wbytes + l['OFF_' + target.upper()]) // 4; dst[offset:offset+n] = value
            tensors.append({'source': name, 'destination': target, 'layer': layer, 'conversion': 'expand_to_FP32' + ('_split_half_to_adjacent_QK' if heads else '')})
    theta = float(checkpoint.config['rope_theta']); require(math.isfinite(theta) and theta > 0, 'invalid theta')
    inv = 1.0 / (np.float32(theta) ** (np.arange(0, d, 2, dtype=np.float32) / d))
    phase = np.arange(l['MAX_TOKENS'], dtype=np.float32)[:, None] * inv[None, :]
    for target, value in [('COS', np.cos(phase)), ('SIN', np.sin(phase))]:
        start = (rope + l['OFF_' + target] - l['OFF_COS']) // 4
        dst[start:start+value.size] = value.reshape(-1)
    embedding = 'model.embed_tokens.weight'; checkpoint.tensor(embedding, (checkpoint.config['vocab_size'], h)); used.add(checkpoint.files[embedding][0])
    for i, token in enumerate(token_ids):
        dst[ha//4+i*h:ha//4+(i+1)*h] = checkpoint.fp32(embedding, token)
    dst.flush(); del dst
    token_path = out / 'tokens.json'; token_path.write_text(json.dumps(token_ids) + '\n')
    manifest = {'schema': 1, 'model_id': 'Qwen/Qwen2-1.5B', 'upstream_revision': revision, 'upstream_revision_asserted_by_caller': True, 'layers': layers, 'tokens': len(token_ids), 'official_forward_validated': False, 'rtl_validated': False, 'reference_intermediates_in_arena': False, 'weights_storage': 'FP32_expansion_of_official_safetensors', 'matrix_recipe': 'BF16_RNE_operands_FP32_FMA_sequential_K', 'rope_coordinates': 'adjacent_QK_permutation_from_HF_split_half', 'rms_epsilon': 1e-6, 'rope_theta': theta, 'rope_table_recipe': 'FP32_inverse_frequency_and_phase_numpy_fp32_sin_cos', 'layout': l, 'regions': {'weights': [0, rope], 'rope': [rope, ha], 'hiddenA': [ha, hb], 'hiddenB': [hb, scratch], 'scratch': [scratch, total]}, 'arena': {'file': arena.name, 'bytes': total, 'sha256': digest(arena)}, 'token_ids_sha256': digest(token_path), 'config_sha256': digest(checkpoint.root/'config.json'), 'source_files': {str(p.relative_to(checkpoint.root)): digest(p) for p in sorted(used)}, 'tensor_conversions': tensors}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', type=Path, required=True); p.add_argument('--layout', type=Path, required=True)
    p.add_argument('--token-ids', type=Path, required=True); p.add_argument('--revision', required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); layout = read_layout(a.layout)
    result = pack(SafeCheckpoint(a.checkpoint), layout, list(range(layout['STACK_LAYERS'])), json.loads(a.token_ids.read_text()), a.out, a.revision)
    print(json.dumps({'status': 'PACKED_NOT_RTL_VALIDATED', 'arena': result['arena'], 'layers': result['layers'], 'tokens': result['tokens']}))

if __name__ == '__main__':
    main()
