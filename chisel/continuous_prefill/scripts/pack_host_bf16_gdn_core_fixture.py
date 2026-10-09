#!/usr/bin/env python3
"""Source-bound two-token Host GDN core fixture, never a complete GDN block.

The only activation boundary is real embedding rows 19/92 followed by pinned
official inputNorm. QKV/Z/AB, Conv, InputPrep, recurrence and gated norm are DUT
work. Canonical/native arrays are comparator files, never physical DDR inputs.
Generation is deliberately opt-in; importing this module does no model work.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import weakref

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from pack_host_bf16_gdn_fixture import (MODEL_REVISION, FRAMEWORK_REVISION,
    bf16, fp, conv_recipe, ulp_metric, require, sha)
from host_bf16_qkv_reference import _compile_matrix, _project_and_crosscheck, _tool_file
from gdn_input_prep_reference import recipe as input_prep_recipe
from gdn_gated_norm_reference import recipe as gated_norm_recipe, diagnostics as bf16_diagnostics
from heteronpu.qwen35_gdn_recurrent_fp32 import recurrent_step
from heteronpu.matrix_norm_rope_candidate import compare_native

HEADS, WIDTH, HIDDEN, CHANNELS = 16, 128, 1024, 6144
HISTORY_BYTES, STATE_BYTES, PREP_BYTES = 49152, 1048576, 25600
KINDS = ('qkv', 'z', 'ab', 'conv', 'prep', 'recurrent', 'norm', 'fence')
ACTUAL_DENSE_MACS = 2 * HIDDEN * (CHANNELS + HEADS * WIDTH + 2 * HEADS)
REFERENCE_FMA_STEPS = 2 * HIDDEN * (CHANNELS + HEADS * WIDTH + 256)


def canonical_chain(projected, conv_weight, a_log, dt_bias, gamma, *, token,
                    history=None, state=None):
    """Compose only already-tested stage recipes; independent carried state."""
    require(type(token) is int and token in (0, 1), 'cold0/carried1 only')
    require(set(projected) == {'qkv', 'z', 'ab'}, 'three actual projection roles')
    require(projected['qkv'].shape == (1, CHANNELS), 'QKV width')
    require(projected['z'].shape == (1, HEADS * WIDTH), 'Z width')
    require(projected['ab'].shape == (1, 2 * HEADS), 'AB width')
    require((history is None) == (token == 0) and (state is None) == (token == 0),
            'carried reference requires its own preceding two states')
    past = np.zeros((CHANNELS, 4), dtype='<u2') if history is None else history
    conv, activated, new_history = conv_recipe(projected['qkv'], conv_weight, past, token == 0)
    query, key, value = activated.reshape(3, HEADS, WIDTH)
    ab = projected['ab'].reshape(2, HEADS)
    q, k, v, gates = input_prep_recipe(query, key, value, ab[0], ab[1], a_log,
                                       dt_bias, recurrent_mode=bool(token))
    prepared = np.concatenate([q.reshape(-1), k.reshape(-1), v.reshape(-1), gates.reshape(-1)]).astype('<f4')
    require(prepared.nbytes == PREP_BYTES, 'FP32[1,6400] packed prep layout')
    core, new_state, core32 = recurrent_step(q, k, v, gates[:, :2], state)
    gated, stages = gated_norm_recipe(core, projected['z'].reshape(HEADS, WIDTH), gamma)
    return dict(conv=activated, conv_before_silu=conv, history=new_history, prep=prepared,
                recurrent=core, state=new_state, recurrent_fp32=core32, norm=gated,
                normalized=stages['normalized'])


def fp32_diagnostics(actual, native):
    """Numerical facts only; there is no inherited whole-block tolerance."""
    a, b = [np.asarray(x, dtype='<f4').reshape(-1) for x in (actual, native)]
    require(a.shape == b.shape and a.size and np.isfinite(a).all() and np.isfinite(b).all(),
            'finite native FP32 comparison')
    delta = np.abs(a.astype(np.float64) - b.astype(np.float64))
    relative = np.divide(delta, np.abs(b), out=np.zeros_like(delta), where=b != 0)
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(a.view('<u4') != b.view('<u4'))),
                max_abs=float(delta.max()), mean_abs=float(delta.mean()),
                max_relative_nonzero_reference=float(relative.max()),
                nonzero_vs_reference_zero=int(np.count_nonzero((delta != 0) & (b == 0))),
                official_acceptance='UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')


def frozen_operator_metrics(canonical, native, conditioned):
    """Retain v1's separately frozen Dense/Conv/SiLU acceptance unchanged."""
    result = []
    for token in range(2):
        a, b, same = canonical[token], native[token], conditioned[token]
        comparisons = {role: compare_native(a[role].reshape(-1), b[role].reshape(-1)) for role in ('qkv', 'z', 'ab')}
        comparisons['end_to_end_conv'] = compare_native(a['conv_before_silu'].reshape(-1), b['conv_before_silu'].reshape(-1))
        comparisons['end_to_end_silu'] = compare_native(a['conv'].reshape(-1), b['conv'].reshape(-1))
        comparisons['conv_same_canonical_input'] = ulp_metric(a['conv_before_silu'].reshape(-1), same['conv_before_silu'].reshape(-1))
        comparisons['silu_same_canonical_input'] = ulp_metric(a['conv'].reshape(-1), same['conv'].reshape(-1))
        passed = all(x.get('pass', x.get('pass_')) for x in comparisons.values())
        result.append(dict(token=token, comparisons=comparisons, passed=passed,
                           contract='chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json'))
    return result


def _conditioned_conv(canonical, native, conv_weight, official, torch):
    """Existing v1 official same-input Conv diagnostics; never DUT feedback."""
    import torch.nn.functional as F
    tensor = lambda a: torch.frombuffer(bytearray(np.ascontiguousarray(a).tobytes()), dtype=torch.bfloat16)
    words = lambda t: t.detach().contiguous().view(torch.int16).numpy().view('<u2').copy()
    weight = tensor(conv_weight).reshape(CHANNELS, 4)
    result = []
    with torch.inference_mode():
        for token in range(2):
            rows = {}
            for label, source in [('canonical', canonical), ('native', native)]:
                x = tensor(source[token]['qkv']).reshape(1, 1, CHANNELS).transpose(1, 2)
                past = np.zeros((CHANNELS, 4), '<u2') if token == 0 else source[token-1]['history']
                state = tensor(past).reshape(1, CHANNELS, 4)
                before = F.conv1d(torch.cat([state, x], dim=-1), weight.unsqueeze(1), groups=CHANNELS)[:, :, -1:]
                activated = (official.causal_conv1d_fn(x, weight, activation='silu') if token == 0 else
                             official.causal_conv1d_update(x, state, weight, activation='silu'))
                captured = dict(conv_before_silu=words(before).reshape(-1), conv=words(activated).reshape(-1))
                if label == 'native':
                    require(np.array_equal(captured['conv'], native[token]['conv'].reshape(-1)), 'official Conv producer capture drift')
                    native[token]['conv_before_silu'] = captured['conv_before_silu']
                else:
                    rows = captured
            result.append(rows)
    return result


def _sources():
    paths = [Path(__file__).resolve(),
             Path(__file__).with_name('pack_host_bf16_gdn_fixture.py'),
             Path(__file__).with_name('host_bf16_gdn_core_descriptor.py'),
             Path(__file__).with_name('host_bf16_gdn_core_execution.py'),
             Path(__file__).with_name('host_bf16_qkv_reference.py'),
             Path(__file__).with_name('gdn_input_prep_reference.py'),
             Path(__file__).with_name('gdn_gated_norm_reference.py'),
             ROOT / 'src/heteronpu/qwen35_gdn_recurrent_fp32.py',
             ROOT / 'src/heteronpu/matrix_norm_rope_candidate.py',
             ROOT / 'src/heteronpu/rope_bf16_candidate.py',
             ROOT / 'src/heteronpu/pinned_gdn_payload.py',
             ROOT / 'src/heteronpu/pinned_prefix_payload.py',
             ROOT / 'scripts/matrix_norm_rope_reference.c',
             ROOT / 'config/model_profiles/qwen3_5_0p8b.json',
             ROOT / 'chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/config.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py',
             ROOT / 'config/upstream/qwen3_5_0p8b/prefix_token_fixture.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/prefix_payload_pin.json',
             ROOT / 'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json',
             ROOT / 'chisel/continuous_prefill/tests/host_bf16_gdn_core.cpp']
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


_ISSUED = weakref.WeakKeyDictionary()


class GdnCoreFixtureSession:
    """Live authority from this invocation; persisted hashes cannot issue one."""
    __slots__ = ('__weakref__',)

    def __init__(self):
        raise TypeError('use generate_fixture')

    def verify(self, directory):
        require(self in _ISSUED, 'unissued source authority')
        original, files, manifest = _ISSUED[self]
        path = Path(directory)
        require(not path.is_symlink() and path.resolve() == original, 'different source directory')
        require(_sources() == manifest['source_sha256'], 'producer source changed')
        require({p.name for p in path.iterdir()} == set(files) | {'manifest.json', 'c_matrix'}, 'fixture inventory changed')
        require(all(p.is_file() and not p.is_symlink() for p in path.iterdir()), 'fixture symlink/nonfile')
        for name, raw in files.items():
            require((path / name).read_bytes() == raw, 'source-bound bytes changed: ' + name)
        require(json.loads((path / 'manifest.json').read_text()) == manifest, 'manifest changed')
        require(_tool_file(path / 'c_matrix') == manifest['tools']['executable'], 'reference executable changed')
        return copy.deepcopy(manifest)


def build_layout():
    """Public-helper serialized, disjoint physical DDR for two real launches."""
    from host_bf16_gdn_core_descriptor import (HostGdnCoreTensor as Tensor,
        HostGdnCoreBinding as Binding, GdnCoreOperation as Op, TensorDType as DType,
        build_host_gdn_core_commands, parse_host_gdn_core_commands,
        validate_host_gdn_core_continuation)
    base, cursor = 0x120000000, 0x120010000
    inputs, launches, tensors = [], [], {}
    def allocate(size):
        nonlocal cursor
        address = cursor
        cursor += ((size + 63) // 64) * 64 + 4096
        return address
    def input_tensor(name, dtype, shape, filename):
        size = shape[0] * shape[1] * (2 if dtype == DType.BF16 else 4)
        tensor = Tensor(allocate(size), dtype, shape)
        inputs.append(dict(name=name, address=tensor.address, bytes=tensor.span_bytes, file=filename))
        tensors[name] = tensor
        return tensor
    bf, f32 = DType.BF16, DType.FP32
    for token in range(2):
        input_tensor(f'activation{token}', bf, (1, HIDDEN), f'activation{token}.bf16le')
    for role, columns in [('qkv', CHANNELS), ('z', HEADS * WIDTH), ('ab', 2 * HEADS)]:
        input_tensor('weight_' + role, bf, (HIDDEN, columns), f'weight_{role}.bf16le')
    input_tensor('weight_conv', bf, (CHANNELS, 4), 'weight_conv.bf16le')
    input_tensor('a_log', f32, (1, HEADS), 'a_log.f32le')
    input_tensor('dt_bias', bf, (1, HEADS), 'dt_bias.bf16le')
    input_tensor('weight_norm', f32, (1, WIDTH), 'weight_norm.f32le')
    history_in = input_tensor('initial_history', bf, (CHANNELS, 4), 'initial_history.bf16le')
    state_in = input_tensor('initial_state', f32, (HEADS * WIDTH, WIDTH), 'initial_state.f32le')
    scratch = cursor
    cursor += 4096
    producers, previous = {}, None
    for token in range(2):
        outputs = {}
        for kind, dtype, shape in [('qkv', bf, (1, CHANNELS)), ('z', bf, (1, HEADS * WIDTH)),
                                  ('ab', bf, (1, 2 * HEADS)), ('conv', bf, (1, CHANNELS)),
                                  ('history', bf, (CHANNELS, 4)), ('prep', f32, (1, 6400)),
                                  ('recurrent', bf, (1, HEADS * WIDTH)),
                                  ('state', f32, (HEADS * WIDTH, WIDTH)), ('norm', bf, (1, HEADS * WIDTH))]:
            outputs[kind] = Tensor(allocate(shape[0] * shape[1] * (2 if dtype == bf else 4)), dtype, shape)
        options = dict(cold=token == 0, expected_generation=token, recurrent_mode=bool(token))
        bindings = [Binding(Op.DENSE, tensors[f'activation{token}'], tensors['weight_' + role], outputs[role], **options)
                    for role in ('qkv', 'z', 'ab')]
        bindings.extend([
            Binding(Op.CONV4, outputs['qkv'], tensors['weight_conv'], outputs['conv'], history_in, outputs['history'], **options),
            Binding(Op.INPUT_PREP, outputs['conv'], outputs['ab'], outputs['prep'], tensors['a_log'], tensors['dt_bias'], **options),
            Binding(Op.RECURRENT, outputs['prep'], state_in, outputs['recurrent'], outputs['state'], **options),
            Binding(Op.GATED_NORM, outputs['recurrent'], outputs['z'], outputs['norm'], tensors['weight_norm'], **options),
            Binding(Op.FENCE, outputs['history'], outputs['state'], outputs['norm'], **options)])
        commands, records = build_host_gdn_core_commands(bindings)
        require(tuple(parse_host_gdn_core_commands(commands, records)) == tuple(bindings), 'public helper round-trip')
        if previous is not None:
            validate_host_gdn_core_continuation(previous, bindings)
        previous = bindings
        launch = dict(token=token, epoch=9 + token, command_base=base + token * 8192,
                      command_limit=base + token * 8192 + 128, commands=8,
                      descriptor_base=base + token * 8192 + 4096,
                      descriptor_limit=base + token * 8192 + 4096 + ((len(records) * 16 + 63) // 64) * 64,
                      descriptor_records=len(records), operations=[],
                      packed_commands=[f'{c.pack():032x}' for c in commands],
                      packed_descriptors=[f'{records[i].pack():032x}' for i in range(len(records))])
        for pc, (kind, binding, command) in enumerate(zip(KINDS, bindings, commands, strict=True)):
            write_names = [] if kind == 'fence' else [kind]
            if kind == 'conv':
                write_names.append('history')
            if kind == 'recurrent':
                write_names.append('state')
            read_tensors = [binding.a, binding.b]
            if kind == 'conv': read_tensors.append(binding.aux0)
            if kind == 'prep': read_tensors.extend([binding.aux0, binding.aux1])
            if kind == 'norm': read_tensors.append(binding.aux0)
            if kind == 'fence': read_tensors.append(binding.d)
            reads = [dict(address=t.address, bytes=t.span_bytes, producer=producers.get(t.address, -1)) for t in read_tensors]
            writes = []
            for name in write_names:
                tensor = outputs[name]
                extension = 'bf16le' if tensor.dtype == bf else 'f32le'
                writes.append(dict(name=name, address=tensor.address, bytes=tensor.span_bytes,
                                   element_bytes=2 if tensor.dtype == bf else 4,
                                   expected=f'expected_{name}{token}.{extension}', native=f'native_{name}{token}.{extension}'))
                producers[tensor.address] = token * 8 + pc
            launch['operations'].append(dict(kind=kind, records=binding.record_count, engine=int(command.engine),
                                              event_wait=command.event_wait, event_signal=command.event_signal,
                                              destination_root=command.dst, reads=reads, writes=writes))
        launches.append(launch)
        history_in, state_in = outputs['history'], outputs['state']
    return dict(base=base, limit=cursor, metadata_limit=base + 0x4000, scratch=scratch,
                inputs=inputs, launches=launches,
                actual_write_bytes=sum(w['bytes'] for l in launches for o in l['operations'] for w in o['writes']))


def _write_launch(layout, write):
    lines = ['HOST_GDN_CORE_V2', ' '.join(map(str, [layout['base'], layout['limit'],
             layout['metadata_limit'], layout['scratch'], len(layout['inputs']), 2]))]
    for entry in layout['inputs']:
        lines.append(f"{entry['address']} {entry['bytes']} {entry['file']}")
    for launch in layout['launches']:
        token = launch['token']
        commands = b''.join(int(v, 16).to_bytes(16, 'little') for v in launch['packed_commands'])
        descriptors = b''.join(int(v, 16).to_bytes(16, 'little') for v in launch['packed_descriptors'])
        descriptors += bytes(-len(descriptors) % 64)
        write(f'host_commands{token}.bin', commands)
        write(f'host_descriptors{token}.bin', descriptors)
        lines.append(' '.join(map(str, [token, launch['epoch'], launch['command_base'], launch['command_limit'],
                     launch['commands'], launch['descriptor_base'], launch['descriptor_limit'], launch['descriptor_records']])))
        for pc, op in enumerate(launch['operations']):
            lines.append(' '.join(map(str, [pc, KINDS.index(op['kind']), op['records'], op['engine'], op['event_wait'],
                         op['event_signal'], op['destination_root'], len(op['reads']), len(op['writes'])])))
            for read in op['reads']:
                lines.append(' '.join(map(str, [read['address'], read['bytes'], read['producer']])))
            for span in op['writes']:
                lines.append(' '.join(map(str, [span['address'], span['bytes'], span['element_bytes'],
                             span['name'], span['expected'], span['native']])))
    write('launch.txt', ('\n'.join(lines) + '\n').encode())


def _native_capture(raw, manifest, embedding_bytes, tokens, config, official, torch):
    """Unmodified official layer, its own cache; hooks record actual producers."""
    from transformers import DynamicCache, Qwen3_5TextConfig
    from heteronpu.pinned_gdn_payload import F32_NAMES
    cfg = Qwen3_5TextConfig.from_dict(config)
    layer = official.Qwen3_5DecoderLayer(cfg, layer_idx=0).eval()
    tensors = {r['local_name']: torch.frombuffer(bytearray(raw[r['local_name']]),
               dtype=torch.float32 if r['local_name'] in F32_NAMES else torch.bfloat16).reshape(r['shape'])
               for r in manifest['tensors']}
    loaded = layer.load_state_dict(tensors, strict=True, assign=True)
    require(not loaded.missing_keys and not loaded.unexpected_keys, 'all14 parameter load')
    require({k: v.dtype for k, v in layer.named_parameters()} == {k: v.dtype for k, v in tensors.items()},
            'original mixed parameter dtype changed')
    captures, handles = [], []
    current = {}
    def words(t):
        require(t.dtype == torch.bfloat16, 'native BF16 producer dtype')
        return t.detach().contiguous().view(torch.int16).numpy().view('<u2').copy()
    def hook(label):
        def capture(_module, _args, result):
            current[label] = words(result).reshape(-1)
        return capture
    for label, module in [('activation', layer.input_layernorm), ('qkv', layer.linear_attn.in_proj_qkv),
                          ('z', layer.linear_attn.in_proj_z), ('a', layer.linear_attn.in_proj_a),
                          ('b', layer.linear_attn.in_proj_b)]:
        handles.append(module.register_forward_hook(hook(label)))
    def norm_hook(_module, args, result):
        current['recurrent'] = words(args[0]).reshape(HEADS, WIDTH)
        current['norm'] = words(result).reshape(HEADS, WIDTH)
    handles.append(layer.linear_attn.norm.register_forward_hook(norm_hook))
    originals = {name: getattr(official, name) for name in
                 ('torch_chunk_gated_delta_rule', 'torch_recurrent_gated_delta_rule')}
    def wrap(name):
        original = originals[name]
        def capture(query, key, value, *args, **kwargs):
            require(not args and kwargs.get('use_qk_l2norm_in_kernel') is True, 'native recurrent call changed')
            current['conv'] = np.concatenate([words(x).reshape(-1) for x in (query, key, value)])
            q = official.l2norm(query.float(), dim=-1, eps=1e-6)
            q = q / (WIDTH ** .5) if name == 'torch_recurrent_gated_delta_rule' else q * (WIDTH ** -.5)
            k = official.l2norm(key.float(), dim=-1, eps=1e-6)
            gates = np.zeros((HEADS, 16), dtype='<f4')
            gates[:, 0] = kwargs['g'].float().numpy().reshape(HEADS)
            gates[:, 1] = kwargs['beta'].float().numpy().reshape(HEADS)
            current['prep'] = np.concatenate([q.numpy().reshape(-1), k.numpy().reshape(-1),
                                              value.float().numpy().reshape(-1), gates.reshape(-1)]).astype('<f4')
            current['official_path'] = name
            return original(query, key, value, **kwargs)
        return capture
    cache = DynamicCache(config=cfg)
    embedding = torch.frombuffer(bytearray(embedding_bytes), dtype=torch.bfloat16).reshape(256, HIDDEN)
    try:
        for name in originals:
            setattr(official, name, wrap(name))
        with torch.inference_mode():
            for token, token_id in enumerate(tokens):
                current = {}
                layer(embedding[token_id].reshape(1, 1, HIDDEN), position_embeddings=None,
                      attention_mask=torch.ones((1, 1), dtype=torch.bool), past_key_values=cache)
                current['ab'] = np.concatenate([current.pop('a'), current.pop('b')])
                current['history'] = words(cache.layers[0].conv_states[0]).reshape(CHANNELS, 4)
                state = cache.layers[0].recurrent_states[0]
                require(state.dtype == torch.float32, 'native state changed from FP32')
                current['state'] = state.detach().numpy().copy().reshape(HEADS, WIDTH, WIDTH)
                require(current['official_path'] == list(originals)[token], 'cold/carry native producer path')
                captures.append(current)
    finally:
        for name, original in originals.items():
            setattr(official, name, original)
        for handle in handles:
            handle.remove()
    return captures


def generate_fixture(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / 'work') and output != ROOT / 'work' and not output.exists(),
            'fresh ignored work output required')
    import torch
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from heteronpu.pinned_gdn_payload import load_payload as load_gdn
    from heteronpu.pinned_prefix_payload import load_payload as load_prefix, token_fixture
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    profile = json.loads((ROOT / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    source_file = Path(inspect.getfile(official))
    require(sha(source_file.read_bytes()) == profile['transformers_source']['sha256'], 'pinned official source drift')
    config_raw = (ROOT / 'config/upstream/qwen3_5_0p8b/config.json').read_bytes()
    require(sha(config_raw) == profile['config_sha256'], 'pinned config drift')
    config = json.loads(config_raw)['text_config']
    require((config['linear_num_key_heads'], config['linear_num_value_heads'], config['linear_key_head_dim'],
             config['linear_value_head_dim'], config['mamba_ssm_dtype']) == (16, 16, 128, 128, 'float32'), 'core geometry drift')
    manifest, raw = load_gdn(ROOT, ROOT / 'work/qwen35_layer0_payload')
    prefix_manifest, prefix = load_prefix(ROOT, ROOT / 'work/qwen35_prefix_payload')
    require(manifest['revision'] == prefix_manifest['revision'] == MODEL_REVISION, 'checkpoint drift')
    tokens = token_fixture(ROOT)['token_ids'][:2]
    require(tokens == [19, 92], 'real token source drift')
    started = time.monotonic()
    native = _native_capture(raw, manifest, prefix['embed_tokens.rows_0_255'], tokens, config, official, torch)
    embedding_sha = sha(prefix['embed_tokens.rows_0_255'])
    del prefix
    weights = {role: np.ascontiguousarray(np.frombuffer(raw[f'linear_attn.in_proj_{role}.weight'], dtype='<u2')
               .reshape(columns, HIDDEN).T) for role, columns in [('qkv', CHANNELS), ('z', HEADS * WIDTH)]}
    weights['ab'] = np.ascontiguousarray(np.concatenate([np.frombuffer(raw[f'linear_attn.in_proj_{role}.weight'], dtype='<u2')
                    .reshape(HEADS, HIDDEN).T for role in ('a', 'b')], axis=1))
    conv_weight = np.frombuffer(raw['linear_attn.conv1d.weight'], dtype='<u2').reshape(CHANNELS, 4)
    a_log = np.frombuffer(raw['linear_attn.A_log'], dtype='<f4')
    bias = np.frombuffer(raw['linear_attn.dt_bias'], dtype='<u2')
    gamma = np.frombuffer(raw['linear_attn.norm.weight'], dtype='<f4')
    output.mkdir(parents=True)
    executable, tools = _compile_matrix(output)
    files, receipts, canonical = {}, [], []
    def write(name, value):
        value = value if isinstance(value, bytes) else np.ascontiguousarray(value).tobytes()
        files[name] = value
        (output / name).write_bytes(value)
    history = state = None
    with tempfile.TemporaryDirectory(prefix='.core_reference_', dir=output) as tmp:
        for token in range(2):
            projected = {}
            for role, weight in weights.items():
                parts = []
                for column in range(0, weight.shape[1], 256):
                    valid = min(256, weight.shape[1] - column)
                    selected = np.zeros((HIDDEN, 256), dtype='<u2')
                    selected[:, :valid] = weight[:, column:column + valid]
                    values, receipt = _project_and_crosscheck(native[token]['activation'], selected, executable, Path(tmp))
                    receipts.append(dict(token=token, role=role, column=column, valid_columns=valid,
                                         activation_sha256=sha(native[token]['activation'].tobytes()),
                                         original_weight_slice_sha256=sha(np.ascontiguousarray(weight[:, column:column + valid]).tobytes()),
                                         padded_oracle_weight_sha256=sha(selected.tobytes()), c_reference=receipt))
                    result = np.frombuffer(values['bf16'], dtype='<u2')
                    require(np.all(result[valid:] == 0), 'nonzero padded oracle column')
                    parts.append(result[:valid].copy())
                    print(f'GDN_CORE_REFERENCE token={token} role={role} column={column} valid={valid} elapsed={time.monotonic()-started:.1f}', flush=True)
                projected[role] = np.concatenate(parts).reshape(1, -1)
            stages = canonical_chain(projected, conv_weight, a_log, bias, gamma,
                                     token=token, history=history, state=state)
            history, state = stages['history'], stages['state']
            canonical.append({**projected, **stages})
    require(len(receipts) == 66 and sum(r['c_reference']['matrix_accumulator_steps'] for r in receipts) == REFERENCE_FMA_STEPS,
            'bounded padded integer/C reference coverage')
    require(sum(r['valid_columns'] * HIDDEN for r in receipts) == ACTUAL_DENSE_MACS,
            'actual N6144/N2048/N32 Dense coverage')
    conditioned = _conditioned_conv(canonical, native, conv_weight, official, torch)
    fixed_metrics = frozen_operator_metrics(canonical, native, conditioned)
    native_metrics = []
    for token in range(2):
        comparisons = {}
        write(f'activation{token}.bf16le', native[token]['activation'])
        for kind in ('qkv', 'z', 'ab', 'conv', 'history', 'prep', 'recurrent', 'state', 'norm'):
            dtype = 'f32le' if kind in ('prep', 'state') else 'bf16le'
            a, b = canonical[token][kind], native[token][kind]
            write(f'expected_{kind}{token}.{dtype}', a)
            write(f'native_{kind}{token}.{dtype}', b)
            comparisons[kind] = fp32_diagnostics(a, b) if dtype == 'f32le' else bf16_diagnostics(a.reshape(-1), b.reshape(-1))
        write(f'expected_conv_before_silu{token}.bf16le', canonical[token]['conv_before_silu'])
        write(f'native_conv_before_silu{token}.bf16le', native[token]['conv_before_silu'])
        for label in ('conv', 'conv_before_silu'):
            write(f'conditioned_{label}{token}.bf16le', conditioned[token][label])
        write(f'expected_recurrent_fp32{token}.f32le', canonical[token]['recurrent_fp32'])
        native_metrics.append(dict(token=token, token_id=tokens[token], official_path=native[token]['official_path'],
                                   source='independent official full-layer producer and its own cold/carried cache', stages=comparisons))
    for role, weight in weights.items():
        write(f'weight_{role}.bf16le', weight)
    write('weight_conv.bf16le', conv_weight)
    write('a_log.f32le', a_log)
    write('dt_bias.bf16le', bias.tobytes() + bytes(32))
    write('weight_norm.f32le', gamma)
    write('initial_history.bf16le', bytes(HISTORY_BYTES))
    write('initial_state.f32le', bytes(STATE_BYTES))
    layout = build_layout()
    _write_launch(layout, write)
    report = dict(schema_version=2, status='SOURCE_AUTHENTICATED_HOST_GDN_CORE_TWO_TOKEN_FIXTURE',
                  scope='DENSE_QKV_Z_AB_CONV4_INPUT_PREP_FP32_RECURRENT_GATED_NORM_FENCE_ONLY',
                  input_boundary='real embedding rows19/92 -> official inputNorm; inputNorm is external, not DUT',
                  token_ids=tokens, tokens_per_launch=1, launches=2, commands_per_launch=8,
                  heads=HEADS, head_width=WIDTH, model_id=manifest['model_id'], model_revision=MODEL_REVISION,
                  framework_revision=FRAMEWORK_REVISION, framework_source_sha256=sha(source_file.read_bytes()),
                  embedding_rows_sha256=embedding_sha, source_sha256=_sources(), tools=tools,
                  layer0_all14_weight_sha256={r['local_name']: r['sha256'] for r in manifest['tensors']},
                  source_payload_manifest_sha256={name: sha((ROOT / 'work' / name / 'manifest.json').read_bytes())
                                                  for name in ('qwen35_layer0_payload', 'qwen35_prefix_payload')},
                  original_parameter_dtypes={r['local_name']: r['dtype'] for r in manifest['tensors']},
                  reference_head_jobs=len(receipts), reference_padded_fma_steps=REFERENCE_FMA_STEPS,
                  actual_useful_dense_macs=ACTUAL_DENSE_MACS, heads_reference=receipts,
                  ab_layout='K-major original [A16,B16]; N32 DUT, N256 zero-padded oracle only',
                  prep_layout='FP32[1,6400]: Q2048,K2048,V2048,16x16 gates; gates columns0=g,1=beta',
                  state_layout='original FP32[16,128,128]; never BF16',
                  norm_weight='original FP32[128], no 1+weight',
                  canonical_acceptance='EXACT_BITS_EVERY_STAGE_AND_BOTH_STATES',
                  native_metrics=native_metrics, native_core_gate_pass=None,
                  frozen_operator_metrics=fixed_metrics,
                  native_operator_gate_pass=all(x['passed'] for x in fixed_metrics),
                  official_stage_acceptance='UNASSIGNED_DIAGNOSTIC_ONLY; no whole-block tolerance inheritance',
                  native_full_block_gate_pass=None, native_full_block_status='NOT_ESTABLISHED_BY_CORE_FIXTURE',
                  full_block_supported=False, input_norm_dut=False, o_projection_dut=False,
                  residual_dut=False, ffn_dut=False, rtl_executed=False,
                  generations=[0, 1, 2], persistent_publish='fence commits both actual ACK state roots atomically',
                  intermediate_ddr_initialization='sentinel only; actual ACK writes are the sole consumer source',
                  layout=layout, files={name: dict(bytes=len(raw), sha256=sha(raw)) for name, raw in files.items()},
                  torch_version=torch.__version__, numpy_version=np.__version__, python_version=sys.version,
                  reference_elapsed_seconds=time.monotonic()-started,
                  max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    session = object.__new__(GdnCoreFixtureSession)
    _ISSUED[session] = (output, files, report)
    session.verify(output)
    return session


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    session = generate_fixture(args.output)
    manifest = session.verify(args.output)
    print(json.dumps({k: manifest[k] for k in ('status', 'scope', 'actual_useful_dense_macs',
                                             'reference_padded_fma_steps', 'max_rss_kib')}, indent=2))
