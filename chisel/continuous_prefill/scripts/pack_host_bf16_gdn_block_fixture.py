#!/usr/bin/env python3
"""Source-bound full layer0 GDN block: two raw embedding inputs, one live DUT.

Reference/native arrays are comparator files only. All consumers, including
RMSNorm, residuals and FFN, must read preceding physical ACK outputs.
"""
from __future__ import annotations
import argparse
import copy
import inspect
import importlib.metadata
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import weakref
import numpy as np

from pack_host_bf16_gdn_core_fixture import (ROOT, HEADS, WIDTH, HIDDEN, CHANNELS,
    HISTORY_BYTES, STATE_BYTES, MODEL_REVISION, FRAMEWORK_REVISION, require, sha,
    canonical_chain, _native_capture, _conditioned_conv, frozen_operator_metrics,
    fp32_diagnostics, bf16_diagnostics, _sources as core_sources)
from host_bf16_qkv_reference import _tool_file, _verify_tools, _source_identity
from gdn_dense_reference import compile_reference, project_and_crosscheck
from gdn_rmsnorm_reference import recipe as rms_recipe
from gdn_elementwise_reference import recipe as elementwise_recipe
from heteronpu.qwen35_numpy_reference import compare as compare_fp32
from heteronpu.matrix_norm_rope_candidate import compare_native
from host_bf16_gdn_block_descriptor import (HostGdnBlockTensor as Tensor,
    HostGdnBlockBinding as Binding, GdnBlockOperation as Op, TensorDType as DType,
    build_host_gdn_block_commands, parse_host_gdn_block_commands,
    validate_host_gdn_block_continuation)

FFN = 3584
KINDS = ('input_norm', 'qkv', 'z', 'ab', 'conv', 'prep', 'recurrent', 'norm',
         'o', 'residual1', 'post_norm', 'gate', 'up', 'silu_mul', 'down', 'residual2', 'fence')
DENSE_SHAPES = {'qkv': (1024, 6144), 'z': (1024, 2048), 'ab': (1024, 32),
                'o': (2048, 1024), 'gate': (1024, 3584), 'up': (1024, 3584), 'down': (3584, 1024)}
ACTUAL_DENSE_MACS = 2 * sum(k * n for k, n in DENSE_SHAPES.values())
REFERENCE_FMA_STEPS = 2 * sum(k * ((n+255)//256)*256 for k, n in DENSE_SHAPES.values())
EXPECTED_ACK_BYTES = 2388096
NATIVE_GATE_SOURCES = ['spec/numerical_contract.md', 'src/heteronpu/qwen35_numpy_reference.py',
                       'scripts/prepare_gdn_recurrent_fixture.py']


def _sources():
    sources = core_sources()
    sources.update(_source_identity())
    paths = [Path(__file__), Path(__file__).with_name('host_bf16_gdn_block_descriptor.py'),
             Path(__file__).with_name('host_bf16_gdn_block_execution.py'),
             Path(__file__).with_name('gdn_dense_reference.py'), Path(__file__).with_name('gdn_dense_reference.c'),
             Path(__file__).with_name('gdn_rmsnorm_reference.py'), Path(__file__).with_name('gdn_elementwise_reference.py'),
             ROOT / 'chisel/continuous_prefill/tests/host_bf16_gdn_block.cpp',
             ROOT / 'chisel/continuous_prefill/config/host_bf16_gdn_block_descriptor_contract.json']
    paths.extend(ROOT / p for p in NATIVE_GATE_SOURCES)
    sources.update({str(p.resolve().relative_to(ROOT)): sha(p.read_bytes()) for p in paths})
    return sources


_ISSUED = weakref.WeakKeyDictionary()
class GdnBlockFixtureSession:
    """Only this invocation's pinned producers can issue fixture authority."""
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
        for name, record in files.items():
            candidate = path / name
            require(candidate.stat().st_size == record['bytes'] and sha(candidate.read_bytes()) == record['sha256'],
                    'source-bound bytes changed: ' + name)
        require(json.loads((path / 'manifest.json').read_text()) == manifest, 'manifest changed')
        require(_tool_file(path / 'c_matrix') == manifest['tools']['executable'], 'reference executable changed')
        _verify_tools(manifest['tools'])
        require(all(sha(Path(name).read_bytes()) == digest for name, digest in manifest['installed_source_sha256'].items()),
                'installed official producer/cache/config source changed')
        return copy.deepcopy(manifest)


def build_layout():
    """Seventeen public v3 commands; no expected/native tensor in input DDR."""
    base, cursor = 0x120000000, 0x120010000
    inputs, launches, tensors = [], [], {}
    def allocate(size):
        nonlocal cursor
        address = cursor
        cursor += ((size + 63)//64)*64 + 4096
        return address
    bf, f32 = DType.BF16, DType.FP32
    def tensor(dtype, shape):
        return Tensor(allocate(shape[0]*shape[1]*(2 if dtype == bf else 4)), dtype, shape)
    def input_tensor(name, dtype, shape, filename):
        value = tensor(dtype, shape)
        inputs.append(dict(name=name, address=value.address, bytes=value.span_bytes, file=filename))
        tensors[name] = value
        return value
    for token in range(2):
        input_tensor(f'hidden{token}', bf, (1, HIDDEN), f'hidden{token}.bf16le')
    input_tensor('weight_input_norm', bf, (1, HIDDEN), 'weight_input_norm.bf16le')
    for role in ('qkv', 'z', 'ab'):
        input_tensor('weight_'+role, bf, DENSE_SHAPES[role], 'weight_'+role+'.bf16le')
    input_tensor('weight_conv', bf, (CHANNELS, 4), 'weight_conv.bf16le')
    input_tensor('a_log', f32, (1, HEADS), 'a_log.f32le')
    input_tensor('dt_bias', bf, (1, HEADS), 'dt_bias.bf16le')
    input_tensor('weight_norm', f32, (1, WIDTH), 'weight_norm.f32le')
    input_tensor('weight_o', bf, DENSE_SHAPES['o'], 'weight_o.bf16le')
    input_tensor('weight_post_norm', bf, (1, HIDDEN), 'weight_post_norm.bf16le')
    for role in ('gate', 'up', 'down'):
        input_tensor('weight_'+role, bf, DENSE_SHAPES[role], 'weight_'+role+'.bf16le')
    history_in = input_tensor('initial_history', bf, (CHANNELS, 4), 'initial_history.bf16le')
    state_in = input_tensor('initial_state', f32, (HEADS*WIDTH, WIDTH), 'initial_state.f32le')
    scratch = cursor
    cursor += 4096
    producers, previous = {}, None
    for token in range(2):
        outputs = {}
        for kind in KINDS[:-1]:
            width = {'qkv': CHANNELS, 'z': HEADS*WIDTH, 'ab': 2*HEADS, 'conv': CHANNELS,
                     'prep': 6400, 'recurrent': HEADS*WIDTH, 'norm': HEADS*WIDTH,
                     'gate': FFN, 'up': FFN, 'silu_mul': FFN}.get(kind, HIDDEN)
            outputs[kind] = tensor(f32 if kind == 'prep' else bf, (1, width))
            if kind == 'conv': outputs['history'] = tensor(bf, (CHANNELS, 4))
            if kind == 'recurrent': outputs['state'] = tensor(f32, (HEADS*WIDTH, WIDTH))
        opt = dict(cold=token == 0, expected_generation=token, recurrent_mode=bool(token))
        hidden = tensors[f'hidden{token}']
        bindings = [Binding(Op.RMS_NORM, hidden, tensors['weight_input_norm'], outputs['input_norm'], role=0, **opt)]
        bindings += [Binding(Op.DENSE, outputs['input_norm'], tensors['weight_'+role], outputs[role], role=i, **opt)
                     for i, role in enumerate(('qkv', 'z', 'ab'))]
        bindings += [Binding(Op.CONV4, outputs['qkv'], tensors['weight_conv'], outputs['conv'], history_in, outputs['history'], **opt),
                     Binding(Op.INPUT_PREP, outputs['conv'], outputs['ab'], outputs['prep'], tensors['a_log'], tensors['dt_bias'], **opt),
                     Binding(Op.RECURRENT, outputs['prep'], state_in, outputs['recurrent'], outputs['state'], **opt),
                     Binding(Op.GATED_NORM, outputs['recurrent'], outputs['z'], outputs['norm'], tensors['weight_norm'], **opt),
                     Binding(Op.DENSE, outputs['norm'], tensors['weight_o'], outputs['o'], role=3, **opt),
                     Binding(Op.ELEMENTWISE, hidden, outputs['o'], outputs['residual1'], role=0, **opt),
                     Binding(Op.RMS_NORM, outputs['residual1'], tensors['weight_post_norm'], outputs['post_norm'], role=1, **opt),
                     Binding(Op.DENSE, outputs['post_norm'], tensors['weight_gate'], outputs['gate'], role=4, **opt),
                     Binding(Op.DENSE, outputs['post_norm'], tensors['weight_up'], outputs['up'], role=5, **opt),
                     Binding(Op.ELEMENTWISE, outputs['gate'], outputs['up'], outputs['silu_mul'], role=1, **opt),
                     Binding(Op.DENSE, outputs['silu_mul'], tensors['weight_down'], outputs['down'], role=6, **opt),
                     Binding(Op.ELEMENTWISE, outputs['residual1'], outputs['down'], outputs['residual2'], role=2, **opt),
                     Binding(Op.FENCE, outputs['history'], outputs['state'], outputs['residual2'], **opt)]
        commands, records = build_host_gdn_block_commands(bindings)
        require(tuple(parse_host_gdn_block_commands(commands, records)) == tuple(bindings), 'public helper round-trip')
        if previous is not None: validate_host_gdn_block_continuation(previous, bindings)
        previous = bindings
        launch = dict(token=token, epoch=9+token, command_base=base+token*8192,
                      command_limit=base+token*8192+((len(commands)*16+63)//64)*64, commands=len(commands),
                      descriptor_base=base+token*8192+4096,
                      descriptor_limit=base+token*8192+4096+((len(records)*16+63)//64)*64,
                      descriptor_records=len(records), operations=[],
                      packed_commands=[f'{c.pack():032x}' for c in commands],
                      packed_descriptors=[f'{records[i].pack():032x}' for i in range(len(records))])
        for pc, (kind, binding, command) in enumerate(zip(KINDS, bindings, commands, strict=True)):
            names = [] if kind == 'fence' else [kind]
            if kind == 'conv': names.append('history')
            if kind == 'recurrent': names.append('state')
            reads = [binding.a, binding.b]
            if kind == 'conv': reads.append(binding.aux0)
            if kind == 'prep': reads += [binding.aux0, binding.aux1]
            if kind == 'norm': reads.append(binding.aux0)
            if kind == 'fence': reads.append(binding.d)
            read_spans = [dict(address=t.address, bytes=t.span_bytes, producer=producers.get(t.address, -1)) for t in reads]
            writes = []
            for name in names:
                value = outputs[name]
                extension = 'bf16le' if value.dtype == bf else 'f32le'
                writes.append(dict(name=name, address=value.address, bytes=value.span_bytes,
                                   element_bytes=2 if value.dtype == bf else 4,
                                   expected=f'expected_{name}{token}.{extension}', native=f'native_{name}{token}.{extension}'))
                producers[value.address] = token*len(KINDS)+pc
            launch['operations'].append(dict(kind=kind, records=binding.record_count, engine=int(command.engine),
                event_wait=command.event_wait, event_signal=command.event_signal, destination_root=command.dst,
                reads=read_spans, writes=writes))
        launches.append(launch)
        history_in, state_in = outputs['history'], outputs['state']
    actual = sum(s['bytes'] for l in launches for o in l['operations'] for s in o['writes'])
    require(actual == EXPECTED_ACK_BYTES, 'full-block write footprint drift')
    return dict(base=base, limit=cursor, metadata_limit=base+0x4000, scratch=scratch,
                inputs=inputs, launches=launches, actual_write_bytes=actual)


def _write_launch(layout, write):
    lines = ['HOST_GDN_BLOCK_V3', ' '.join(map(str, [layout['base'], layout['limit'],
             layout['metadata_limit'], layout['scratch'], len(layout['inputs']), 2]))]
    for entry in layout['inputs']: lines.append(f"{entry['address']} {entry['bytes']} {entry['file']}")
    for launch in layout['launches']:
        token = launch['token']
        for kind, start, end in [('commands', 'command_base', 'command_limit'), ('descriptors', 'descriptor_base', 'descriptor_limit')]:
            packed = b''.join(int(v, 16).to_bytes(16, 'little') for v in launch['packed_'+kind])
            packed += bytes(launch[end]-launch[start]-len(packed))
            write(f'host_{kind}{token}.bin', packed)
        lines.append(' '.join(map(str, [token, launch['epoch'], launch['command_base'], launch['command_limit'],
                     launch['commands'], launch['descriptor_base'], launch['descriptor_limit'], launch['descriptor_records']])))
        for pc, op in enumerate(launch['operations']):
            lines.append(' '.join(map(str, [pc, KINDS.index(op['kind']), op['records'], op['engine'], op['event_wait'],
                         op['event_signal'], op['destination_root'], len(op['reads']), len(op['writes'])])))
            for read in op['reads']: lines.append(' '.join(map(str, [read['address'], read['bytes'], read['producer']])))
            for span in op['writes']:
                lines.append(' '.join(map(str, [span['address'], span['bytes'], span['element_bytes'], span['name'], span['expected'], span['native']])))
    write('launch.txt', ('\n'.join(lines)+'\n').encode())


def native_full_block_metrics(canonical, native):
    """Frozen block/output and per-node gates, plus original FP32 state audit.

    The existing strict FP32 state audit remains a real gate, even when failure
    originates upstream. Canonical recipe equality cannot override any failure.
    """
    reports = []
    for token in range(2):
        checks = {}
        for name in KINDS[:-1]:
            a, b = canonical[token][name], native[token][name]
            if name == 'prep':
                continue  # Packed prep has no existing aggregate operator gate.
            metric = compare_native(a.reshape(-1), b.reshape(-1))
            if name == 'residual2':
                metric['thresholds'] = {'max_abs': .05, 'mean_abs': .01}
                metric['pass'] = metric['max_abs'] <= .05 and metric['mean_abs'] <= .01
            checks[name] = metric
        checks['history'] = compare_native(canonical[token]['history'].reshape(-1), native[token]['history'].reshape(-1))
        checks['state'] = compare_fp32(canonical[token]['state'], native[token]['state'])
        checks['state']['pass'] = checks['state']['mismatches'] == 0
        reports.append(dict(token=token, checks=checks, passed=all(v['pass'] for v in checks.values()),
                            threshold_sources=NATIVE_GATE_SOURCES))
    return reports


def generate_fixture(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT/'work') and output != ROOT/'work' and not output.exists(), 'fresh ignored work output required')
    sources_before = _sources()
    import torch
    import transformers.cache_utils as cache_source
    from transformers import Qwen3_5TextConfig
    from transformers.models.qwen3_5 import modeling_qwen3_5 as official
    from heteronpu.pinned_gdn_payload import load_payload as load_gdn
    from heteronpu.pinned_prefix_payload import load_payload as load_prefix, token_fixture
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True); torch.set_float32_matmul_precision('highest')
    profile = json.loads((ROOT/'config/model_profiles/qwen3_5_0p8b.json').read_text())
    source_file = Path(inspect.getfile(official))
    require(sha(source_file.read_bytes()) == profile['transformers_source']['sha256'], 'pinned official source drift')
    config_file = Path(inspect.getfile(Qwen3_5TextConfig))
    cache_file = Path(inspect.getfile(cache_source))
    require(config_file.read_bytes() == (ROOT/'config/upstream/qwen3_5_0p8b/configuration_qwen3_5.py').read_bytes(), 'installed official configuration source drift')
    require(sha(cache_file.read_bytes()) == 'abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b', 'installed official cache source drift')
    direct_url = json.loads(importlib.metadata.distribution('transformers').read_text('direct_url.json') or '{}')
    require(direct_url.get('url') == 'https://github.com/huggingface/transformers/archive/'+FRAMEWORK_REVISION+'.zip' and
            direct_url.get('archive_info', {}).get('hashes', {}).get('sha256') == '15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d', 'pinned Transformers archive drift')
    installed_sources = {str(p.resolve()): sha(p.read_bytes()) for p in (source_file, config_file, cache_file)}
    config_raw = (ROOT/'config/upstream/qwen3_5_0p8b/config.json').read_bytes()
    require(sha(config_raw) == profile['config_sha256'], 'pinned config drift')
    config = json.loads(config_raw)['text_config']
    require((config['hidden_size'], config['intermediate_size'], config['linear_num_key_heads'],
             config['linear_num_value_heads'], config['linear_key_head_dim'], config['linear_value_head_dim'],
             config['mamba_ssm_dtype']) == (1024, 3584, 16, 16, 128, 128, 'float32'), 'block geometry drift')
    manifest, raw = load_gdn(ROOT, ROOT/'work/qwen35_layer0_payload')
    prefix_manifest, prefix = load_prefix(ROOT, ROOT/'work/qwen35_prefix_payload')
    require(manifest['revision'] == prefix_manifest['revision'] == MODEL_REVISION, 'checkpoint drift')
    tokens = token_fixture(ROOT)['token_ids'][:2]; require(tokens == [19, 92], 'token drift')
    started = time.monotonic()
    embedding_raw = prefix['embed_tokens.rows_0_255']; embedding_sha = sha(embedding_raw)
    native = _native_capture(raw, manifest, embedding_raw, tokens, config, official, torch, full_block=True)
    hidden = np.frombuffer(embedding_raw, '<u2').reshape(256, HIDDEN)[tokens].copy()
    del prefix, embedding_raw
    weights = {}
    for role, (k, n) in DENSE_SHAPES.items():
        if role == 'ab':
            weights[role] = np.ascontiguousarray(np.concatenate([np.frombuffer(raw[f'linear_attn.in_proj_{r}.weight'], '<u2').reshape(HEADS, HIDDEN).T for r in ('a', 'b')], axis=1))
        else:
            name = f'linear_attn.in_proj_{role}.weight' if role in ('qkv', 'z') else 'linear_attn.out_proj.weight' if role == 'o' else f'mlp.{role}_proj.weight'
            weights[role] = np.ascontiguousarray(np.frombuffer(raw[name], '<u2').reshape(n, k).T)
    conv_weight = np.frombuffer(raw['linear_attn.conv1d.weight'], '<u2').reshape(CHANNELS, 4)
    a_log = np.frombuffer(raw['linear_attn.A_log'], '<f4'); bias = np.frombuffer(raw['linear_attn.dt_bias'], '<u2')
    gamma = np.frombuffer(raw['linear_attn.norm.weight'], '<f4')
    input_weight = np.frombuffer(raw['input_layernorm.weight'], '<u2')
    post_weight = np.frombuffer(raw['post_attention_layernorm.weight'], '<u2')
    output.mkdir(parents=True)
    executable, tools = compile_reference(output)
    files, receipts, canonical = {}, [], []
    def write(name, value):
        data = value if isinstance(value, bytes) else np.ascontiguousarray(value).tobytes()
        files[name] = dict(bytes=len(data), sha256=sha(data)); (output/name).write_bytes(data)
    history = state = None
    with tempfile.TemporaryDirectory(prefix='.block_reference_', dir=output) as tmp:
        def project(role, activation, token):
            weight, parts = weights[role], []
            k, n = weight.shape
            for column in range(0, n, 256):
                valid = min(256, n-column); selected = np.zeros((k, 256), '<u2')
                selected[:, :valid] = weight[:, column:column+valid]
                values, receipt = project_and_crosscheck(activation.reshape(-1), selected, executable, Path(tmp))
                receipts.append(dict(token=token, role=role, k=k, column=column, valid_columns=valid,
                    activation_sha256=sha(activation.tobytes()), original_weight_slice_sha256=sha(np.ascontiguousarray(weight[:, column:column+valid]).tobytes()),
                    padded_oracle_weight_sha256=sha(selected.tobytes()), c_reference=receipt))
                result = np.frombuffer(values['bf16'], '<u2'); require(np.all(result[valid:] == 0), 'nonzero padded oracle column')
                parts.append(result[:valid].copy())
                print(f'GDN_BLOCK_REFERENCE token={token} role={role} k={k} column={column} valid={valid} elapsed={time.monotonic()-started:.1f}', flush=True)
            return np.concatenate(parts).reshape(1, n)
        for token in range(2):
            values = {'input_norm': rms_recipe(hidden[token].reshape(1, -1), input_weight)[0]}
            projected = {role: project(role, values['input_norm'], token) for role in ('qkv', 'z', 'ab')}
            values.update(projected)
            values.update(canonical_chain(projected, conv_weight, a_log, bias, gamma, token=token, history=history, state=state))
            history, state = values['history'], values['state']
            values['o'] = project('o', values['norm'], token)
            values['residual1'] = elementwise_recipe('add', hidden[token].reshape(1, -1), values['o'])[0]
            values['post_norm'] = rms_recipe(values['residual1'], post_weight)[0]
            for role in ('gate', 'up'): values[role] = project(role, values['post_norm'], token)
            values['silu_mul'] = elementwise_recipe('silu_mul', values['gate'], values['up'])[0]
            values['down'] = project('down', values['silu_mul'], token)
            values['residual2'] = elementwise_recipe('add', values['residual1'], values['down'])[0]
            canonical.append(values)
    require(len(receipts) == 138 and sum(r['c_reference']['matrix_accumulator_steps'] for r in receipts) == REFERENCE_FMA_STEPS,
            'bounded independent integer/C reference coverage')
    require(sum(r['valid_columns']*r['k'] for r in receipts) == ACTUAL_DENSE_MACS, 'actual full-block Dense coverage')
    conditioned = _conditioned_conv(canonical, native, conv_weight, official, torch)
    fixed_metrics = frozen_operator_metrics(canonical, native, conditioned)
    block_metrics = native_full_block_metrics(canonical, native)
    native_metrics = []
    for token in range(2):
        comparisons = {}; write(f'hidden{token}.bf16le', hidden[token])
        for kind in KINDS[:-1] + ('history', 'state'):
            extension = 'f32le' if kind in ('prep', 'state') else 'bf16le'
            a, b = canonical[token][kind], native[token][kind]
            write(f'expected_{kind}{token}.{extension}', a); write(f'native_{kind}{token}.{extension}', b)
            comparisons[kind] = fp32_diagnostics(a, b) if extension == 'f32le' else bf16_diagnostics(a.reshape(-1), b.reshape(-1))
            if kind in block_metrics[token]['checks']:
                comparisons[kind]['official_acceptance'] = ('FROZEN_FP32_STATE_ABS_REL' if kind == 'state' else
                    'FROZEN_BF16_BLOCK_OUTPUT' if kind == 'residual2' else 'FROZEN_BF16_OPERATOR')
                comparisons[kind]['frozen_gate'] = block_metrics[token]['checks'][kind]
        for label in ('conv', 'conv_before_silu'):
            write(f'conditioned_{label}{token}.bf16le', conditioned[token][label])
        for prefix, source in [('expected', canonical), ('native', native)]:
            write(f'{prefix}_conv_before_silu{token}.bf16le', source[token]['conv_before_silu'])
        write(f'expected_recurrent_fp32{token}.f32le', canonical[token]['recurrent_fp32'])
        native_metrics.append(dict(token=token, token_id=tokens[token], official_path=native[token]['official_path'],
                                  source='independent original official full-layer forward and private cold/carried cache', stages=comparisons))
    for role, weight in weights.items(): write('weight_'+role+'.bf16le', weight)
    for name, value in [('weight_input_norm.bf16le', input_weight), ('weight_post_norm.bf16le', post_weight),
                        ('weight_conv.bf16le', conv_weight), ('a_log.f32le', a_log), ('dt_bias.bf16le', bias.tobytes()+bytes(32)),
                        ('weight_norm.f32le', gamma), ('initial_history.bf16le', bytes(HISTORY_BYTES)), ('initial_state.f32le', bytes(STATE_BYTES))]: write(name, value)
    layout = build_layout(); _write_launch(layout, write)
    operator_pass = all(x['passed'] for x in fixed_metrics)
    block_pass = operator_pass and all(x['passed'] for x in block_metrics)
    require(_sources() == sources_before, 'producer sources changed during reference generation')
    _verify_tools(tools)
    report = dict(schema_version=3, status='SOURCE_AUTHENTICATED_HOST_GDN_BLOCK_TWO_TOKEN_FIXTURE',
        scope='FULL_LAYER0_GDN_BLOCK_RAW_HIDDEN_TO_RESIDUAL2_AND_BOTH_STATES',
        input_boundary='original real embedding rows19/92; all layer0 operators execute on DUT',
        token_ids=tokens, tokens_per_launch=1, launches=2, commands_per_launch=17, heads=HEADS, head_width=WIDTH,
        model_id=manifest['model_id'], model_revision=MODEL_REVISION, framework_revision=FRAMEWORK_REVISION,
        framework_source_sha256=sha(source_file.read_bytes()), embedding_rows_sha256=embedding_sha,
        source_sha256=sources_before, installed_source_sha256=installed_sources, transformers_direct_url=direct_url, tools=tools,
        layer0_all14_weight_sha256={r['local_name']: r['sha256'] for r in manifest['tensors']},
        source_payload_manifest_sha256={name: sha((ROOT/'work'/name/'manifest.json').read_bytes()) for name in ('qwen35_layer0_payload','qwen35_prefix_payload')},
        original_parameter_dtypes={r['local_name']: r['dtype'] for r in manifest['tensors']},
        reference_head_jobs=len(receipts), reference_padded_fma_steps=REFERENCE_FMA_STEPS,
        actual_useful_dense_macs=ACTUAL_DENSE_MACS, heads_reference=receipts,
        canonical_acceptance='EXACT_BITS_EVERY_STAGE_AND_BOTH_STATES', native_metrics=native_metrics,
        frozen_operator_metrics=fixed_metrics, native_operator_gate_pass=operator_pass,
        native_full_block_metrics=block_metrics, native_full_block_gate_pass=block_pass,
        native_full_block_status='PASS' if block_pass else 'FAIL', native_core_gate_pass=None,
        native_gate_threshold_sources=NATIVE_GATE_SOURCES,
        full_block_supported=True, input_norm_dut=True, o_projection_dut=True, residual_dut=True, ffn_dut=True,
        rtl_executed=False, fault_restore_supported=False, generations=[0,1,2],
        persistent_publish='last residual2 ACK then fence atomically publishes both actual state roots',
        intermediate_ddr_initialization='sentinel only; actual ACK writes are sole consumer source',
        state_layout='original FP32[16,128,128]; never BF16', norm_weight='original FP32[128], no 1+weight',
        layout=layout, files=files, torch_version=torch.__version__, numpy_version=np.__version__, python_version=sys.version,
        reference_elapsed_seconds=time.monotonic()-started, max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    (output/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    session = object.__new__(GdnBlockFixtureSession); _ISSUED[session] = (output, copy.deepcopy(files), report)
    session.verify(output)
    return session


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('output', type=Path)
    args = parser.parse_args(); session = generate_fixture(args.output); manifest = session.verify(args.output)
    print(json.dumps({k: manifest[k] for k in ('status','scope','actual_useful_dense_macs','reference_padded_fma_steps','native_full_block_status','max_rss_kib')}, indent=2))
