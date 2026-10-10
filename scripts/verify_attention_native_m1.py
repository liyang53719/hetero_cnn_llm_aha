#!/usr/bin/env python3
"""Explicit, reference-only native M1 audit; importing this file runs no model.

Consumes retained raw block-reference bytes, never selected M128 native gold.
The default action checks availability and identities only. --execute-official
runs the pinned installed official layer; it downloads nothing and runs no RTL.
Reports never award native RTL acceptance, even when every comparison passes.
Offline receipts and their caller-supplied hashes establish file relationships
only. Their DUT/CI authority claims are not authenticated here. Even optional
"actual" dumps remain receipt_hashed_claim_only, hardware_authority_verified
is always false, and this script has no authority-upgrade path. Direct hardware
evidence would require the existing complete live/CI authentication workflow.

Receipt identities are deliberately separate: reference_receipt_file_sha256
hashes the saved indented JSON bytes; reference_receipt_sha256 hashes the live
canonical sorted compact JSON plus newline. Only the canonical identity is
compared with result.block_reference_receipt_sha256. The two CLI pins are
--receipt-file-sha256 and the optional --canonical-receipt-sha256.

Retention TODO for a FUTURE authorized run (never retroactively the old pass):
save the small plan from --retention-plan as a CI artifact, not in Git. It
contains exact raw rows, trig, actual outputs and explicit prior/final KV,
plus an identity/size/SHA256/privacy manifest. Keep downloadable weights out.
Reacquire pinned weights locally and reconstruct a receipt-bound reference
bundle beside this retained pack. Do not substitute a fresh capture if the
original raw-input hashes cannot be reproduced. Optional internal producer
dumps need actual driver instrumentation and execution-receipt hashes; merely
writing canonical expectations under an actual filename is not valid evidence.

The present threads workflow has a fresh canonical bundle before its bounded
prefix windows, but does not execute the full two-token actual block. A future
reference-only invocation immediately after fresh_fixture can close the M1
reference gap with canonical prior KV only. It cannot establish actual/native
block acceptance. No workflow is changed or launched by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.qwen35_bf16_reference import producer_compare, softmax_invariants

CONTRACT = 'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json'
CONTRACT_SHA = '13b52da81746346f62c6a2f28cc1d6fa565989bd71d834dd4951ee2056355d97'
PAYLOAD_PIN = 'config/upstream/qwen3_5_0p8b/layer3_payload_pin.json'
PAYLOAD_PIN_SHA = 'ab9735a92f3b3377737288621019bccd855a5696bd4d02b2d8257cbf24a5b0ac'
CONFIG_SOURCE_SHA = '2f26c4bb911772d42a5f16e82bdea4b9ba1ac07872df527ec228622d35f3c30e'
PHASES = ('cold0', 'carried1')
SOURCES = ('cold0', 'cold1')
DENSE = {'q': (1024, 4096), 'k': (1024, 512), 'v': (1024, 512),
         'o': (2048, 1024), 'ffn_gate': (1024, 3584),
         'ffn_up': (1024, 3584), 'down': (3584, 1024)}
PARAMETERS = {'input_norm': 'input_layernorm.weight',
              'post_norm': 'post_attention_layernorm.weight',
              'q_gamma': 'self_attn.q_norm.weight', 'k_gamma': 'self_attn.k_norm.weight',
              **{r: 'self_attn.' + r + '_proj.weight' for r in ('q', 'k', 'v', 'o')},
              'ffn_gate': 'mlp.gate_proj.weight', 'ffn_up': 'mlp.up_proj.weight',
              'down': 'mlp.down_proj.weight'}
TERMINALS = {'input_norm': 7, 'q': 8, 'k': 17, 'v': 26, 'norm_q': 16,
             'norm_k': 25, 'context': 38, 'sigmoid_mul': 40, 'o': 41,
             'residual1': 42, 'post_norm': 50, 'ffn_gate': 51, 'ffn_up': 53,
             'silu_mul': 54, 'down': 55, 'residual2': 56}
STORED_WIDTHS = dict(input_norm=1024, q=4096, k=512, v=512, norm_q=2048,
    gate=2048, norm_k=512, rope_q=2048, rope_k=512, cache_k=512,
    cache_v=512, context=2048, sigmoid_mul=2048, o=1024, residual1=1024,
    post_norm=1024, ffn_gate=3584, ffn_up=3584, silu_mul=3584,
    down=1024, residual2=1024)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, expected, size=None):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'missing retained nonsymlink bytes: ' + str(path))
    raw = path.read_bytes()
    require(digest(raw) == expected, 'evidence hash mismatch: ' + str(path))
    require(size is None or len(raw) == size, 'evidence size mismatch: ' + str(path))
    return raw


def fresh_report_path(path):
    """Admit a fresh file strictly inside ignored work before model execution."""
    require(path is not None, 'fresh report path beneath work required')
    path = Path(path).absolute()
    require(not path.exists() and not any(p.is_symlink() for p in (path, *path.parents)),
            'fresh nonsymlink report path required')
    require('..' not in path.parts, 'report path traversal')
    work_root = ROOT / 'work'
    require(path != work_root and path.is_relative_to(work_root),
            'report must be a proper descendant of ignored work')
    require(all(not p.exists() or p.is_dir() for p in path.parents),
            'report ancestors must be directories')
    return path


def bf16(raw, shape):
    require(len(raw) == int(np.prod(shape)) * 2, 'BF16 shape/size mismatch')
    value = (np.frombuffer(raw, dtype='<u2').astype('<u4') << 16).view('<f4').reshape(shape)
    require(np.isfinite(value).all(), 'nonfinite BF16 input')
    return value.copy()


def array_sha(value):
    return digest(np.asarray(value, dtype='<f4').tobytes())


def same_bits(a, b):
    return a.shape == b.shape and np.array_equal(a.view('<u4'), b.view('<u4'))


def producer_shape(index, position):
    require(position in (0, 1) and index in range(57), 'only exact two-M1 producer geometry supported')
    if index in (5, 48): return (1024,)
    if index in (14, 23): return (256,)
    if index in (1, 2, 3, 44, 45, 46): return (1, 1, 1)
    if index in (10, 11, 12): return (1, 1, 8, 1)
    if index in (19, 20, 21): return (1, 1, 2, 1)
    if index in (9, 13, 15, 16): return (1, 1, 8, 256)
    if index in (18, 22, 24, 25): return (1, 1, 2, 256)
    if index in (27, 28, 29): return (1, 8, 1, 64)
    if index in (30, 31, 32): return (1, 2, 1, 64)
    if 33 <= index <= 37: return (1, 8, 1, position + 1)
    if index == 38: return (1, 8, 1, 256)
    return (1, 1, 4096 if index == 8 else 512 if index in (17, 26)
            else 2048 if index in (39, 40) else 3584 if 51 <= index <= 54 else 1024)


def contract():
    value = json.loads(checked(ROOT / CONTRACT, CONTRACT_SHA))
    require(value['thresholds'] == {'operator': {'max_abs': .03125, 'mean_abs': .005},
                                    'block': {'max_abs': .05, 'mean_abs': .01}}, 'frozen limits drift')
    return value


def retention_plan():
    records = [dict(path='input/' + phase + '_hidden.bf16le', bytes=2048,
                    purpose='exact original raw layer3 input') for phase in SOURCES]
    records.append(dict(path='input/trig_first_two_rows.bf16le', bytes=256,
                        purpose='original positions0/1 cosine32,sine32 rows'))
    for phase in PHASES:
        records.extend(dict(path=phase + '/actual_' + name + '.bf16le', bytes=2 * width,
                            purpose='actual acknowledged output; cache files hold current append only')
                       for name, width in STORED_WIDTHS.items())
    for name, size in [('prior_carried1', 1024), ('final_carried1', 2048)]:
        records.extend(dict(path='cache/' + name + '_' + role + '.bf16le', bytes=size,
                            purpose='explicit actual KV prefix/full-state snapshot') for role in ('k', 'v'))
    optional = [dict(path=phase + f'/actual_producer_{i:02d}.f32le', bytes=int(np.prod(producer_shape(i, pos))) * 4,
                     purpose='actual internal GQA boundary, never synthesized from expectations')
                for pos, phase in enumerate(PHASES) for i in range(33, 38)]
    return dict(schema='ATTENTION_M1_FUTURE_RETENTION_PLAN_V1', status='TODO_NOT_CAPTURED',
        raw_files=records, raw_bytes=sum(v['bytes'] for v in records), optional_gqa_files=optional,
        optional_gqa_bytes=sum(v['bytes'] for v in optional), downloadable_weights_included=False,
        required_manifest_fields=['original_commit', 'run_id', 'job_id', 'binary_sha256', 'rtl_sha256',
            'official_capture_manifest_sha256', 'reference_receipt_sha256',
            'reference_receipt_file_sha256', 'CPU_variant',
            'input_sha256', 'launch_positions', 'cache_lengths_before_after',
            'file_path_bytes_sha256_dtype_shape_layout', 'privacy_description'],
        privacy_description='Model-derived activation, KV and output tensors from this fixed artificial-token fixture; keep in authorized CI artifacts, never Git; no downloadable model weights.',
        no_original_pass_revalidation_without_original_matching_bytes=True,
        native_full_block_acceptance=False)


def validated_weight_words(files):
    """Check all original parameter bytes even during default no-model inspection."""
    c = contract()
    manifest = json.loads(checked(ROOT / PAYLOAD_PIN, PAYLOAD_PIN_SHA))
    require((manifest['model_id'], manifest['revision'], manifest['layer_id']) ==
            (c['model_id'], c['revision'], 3), 'original payload model/layer pin mismatch')
    pins = {v['local_name']: v for v in manifest['tensors']}
    require(len(manifest['tensors']) == len(pins) == 11 and set(pins) == set(PARAMETERS.values()),
            'all eleven pinned layer parameters required')
    weights = {}
    for role, name in PARAMETERS.items():
        raw = files['input/weight_' + role + '.bf16le']
        shape = DENSE.get(role, (256,) if role.endswith('gamma') else (1024,))
        require(len(raw) == int(np.prod(shape)) * 2 and pins[name]['dtype'] == 'BF16', 'parameter size/dtype mismatch')
        words = np.frombuffer(raw, dtype='<u2').reshape(shape)
        original = np.ascontiguousarray(words.T) if role in DENSE else words
        require(list(original.shape) == pins[name]['shape'] and digest(original.tobytes()) == pins[name]['sha256'],
                'original model parameter pin mismatch')
        weights[name] = original
    return weights


def validate_native_failure_claims(receipt):
    """Consistency only: embedded historical evidence remains unauthenticated here."""
    failures, evidence = receipt['original_native_full_block_failures'], receipt['original_capture_evidence']
    limits = contract()['thresholds']
    require(set(failures) == {'baseline', 'avx2'}, 'both historical CPU variants required')
    for variant, claim in failures.items():
        require(claim['gate_pass'] is False and evidence['native_full_block_gate_pass'][variant] is False and
                claim['status'] == evidence['native_full_block_status'][variant] == 'BLOCKED_BF16_PRODUCER_GATE',
                'historical failure status drift')
        require(claim['report_sha256'] == evidence['native_audit_report_sha256'][variant] and
                len(claim['failed_producers']) == evidence['native_full_block_failed_comparisons'][variant],
                'historical failure report/count drift')
        require(len({(r['case'], r['producer']) for r in claim['failed_producers']}) == len(claim['failed_producers']),
                'duplicate historical failure record')
        for row in claim['failed_producers']:
            threshold = limits['block' if row['producer'] == 'output' else 'operator']
            require(row['case'] in ('cold_m128', 'carried_m128') and row['pass'] is False and
                    (row['max_abs_limit'], row['mean_abs_limit']) == (threshold['max_abs'], threshold['mean_abs']) and
                    (row['max_abs_error'] > row['max_abs_limit'] or row['mean_abs_error'] > row['mean_abs_limit']),
                    'historical failure/threshold record drift')
    original = receipt['original_native_report']; variant = receipt['variant']
    require(original['thresholds'] == limits and original['failed_producers'] == failures[variant]['failed_producers'] and
            original['gate_pass'] is False and original['status'] == failures[variant]['status'],
            'embedded original native report differs from preserved failures')


def read_reference_receipt(path, file_sha, canonical_sha=None):
    """Bind saved file bytes and live canonical content as distinct identities."""
    scripts = ROOT / 'chisel/continuous_prefill/scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from host_bf16_attention_block_live_gate import encoded
    raw = checked(path, file_sha)
    receipt = json.loads(raw)
    identities = dict(reference_receipt_file_sha256=digest(raw),
                      reference_receipt_sha256=digest(encoded(receipt)))
    require(canonical_sha is None or identities['reference_receipt_sha256'] == canonical_sha,
            'canonical reference receipt identity mismatch')
    return receipt, identities


def load_bundle(directory, receipt_file_sha, canonical_receipt_sha=None):
    """Hash-bound existing source bundle; not a live-authority or RTL issuer."""
    scripts = ROOT / 'chisel/continuous_prefill/scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import host_bf16_attention_block_fixture as fixture
    import host_bf16_attention_block_reference as reference
    directory = Path(directory)
    receipt, identities = read_reference_receipt(directory / 'reference_receipt.json',
                                                receipt_file_sha, canonical_receipt_sha)
    c = contract()
    require(receipt['launch_counts'] == [1, 1] and receipt['variant'] in ('baseline', 'avx2'),
            'expected adjacent two-M1 reference bundle')
    require(receipt['model_revision'] == c['revision'], 'original model revision required')
    require(receipt['schema'] == reference.contract_schema() and
            receipt['original_native_thresholds'] == c['thresholds'], 'producer/threshold drift')
    require(receipt['source_sha256_before'] == receipt['source_sha256_after'] == reference.source_identity(),
            'complete original reference source closure required')
    # Reuse existing source-only admission for exact inventories, predecessor
    # schema, raw-hidden/trig identities, positions and canonical cache hashes.
    # It checks files/metadata, without issuing a live or hardware authority.
    files = fixture.validate_reference_receipt(directory, receipt)
    validated_weight_words(files)
    validate_native_failure_claims(receipt)
    nodes = {}
    for position, phase in enumerate(SOURCES):
        case = receipt['cases'][phase]
        require((case['source_phase'], case['source_token'], case['token_count'], case['absolute_position']) ==
                ('cold', position, 1, position), 'M128/carried source substitution rejected')
        nodes[phase] = {}
        for i, definition in enumerate(c['producer_sequence']):
            raw = files[f'reference/{phase}/producer_{i:02d}.f32le']
            require(len(raw) == int(np.prod(producer_shape(i, position))) * 4, 'producer shape mismatch')
            value = np.frombuffer(raw, dtype='<f4').reshape(producer_shape(i, position)).copy()
            require(np.isfinite(value).all(), 'nonfinite producer')
            if definition['storage_dtype'] == 'bfloat16':
                require(not np.any(value.view('<u4') & 65535), 'unrounded BF16 producer')
            nodes[phase][i] = value
        for role, current in [('k', 'rope_k'), ('v', 'v')]:
            cache = files[f'reference/{phase}/cache_{role}.bf16le']
            require(len(cache) == (position + 1) * 1024 and
                    cache[position * 1024:] == files[f'reference/{phase}/{current}.bf16le'],
                    'canonical cache current append differs from predecessor')
            if position:
                require(cache[:1024] == files[f'reference/cold0/cache_{role}.bf16le'], 'canonical cache prefix changed')
    return dict(receipt=receipt, **identities, files=files, nodes=nodes)


def cache_array(raw, tokens):
    return bf16(raw, (tokens, 2, 256)).transpose(1, 0, 2)[None].copy()


def stage_metrics(candidate, native, *, block=False):
    return producer_compare(candidate, native, block=block)


def load_actual(directory, result_path, result_sha, bundle):
    """Check claimed-output file relationships; never authenticate DUT authority."""
    result = json.loads(checked(result_path, result_sha))
    require(result['actual_dut_identity_verified'] is True and result['same_dut_launches'] == 2 and
            result['resets_between_launches'] == 0, 'receipt must claim the expected two-launch scope')
    require(result['input_sha256'] == {name: record['sha256'] for name, record in bundle['receipt']['inputs'].items()},
            'actual and reference raw input identities differ')
    require(result['block_reference_receipt_sha256'] == bundle['reference_receipt_sha256'],
            'result/canonical reference receipt mismatch')
    require(result['mode'] == 'pass' and result['status'] == 'PASS_PRODUCTION_HOST_ATTENTION_BLOCK_PAIR_FROZEN_RECIPE',
            'receipt must describe the complete successful M1 pair')
    require(len(result['runs']) == 2 and all(
        (row['phase'], row['status'], row['checkpoint_accepted'], row['inferred_committed_length'], row['inferred_committed_generation']) ==
        (phase, 0, True, index + 1, index + 1)
        for index, (phase, row) in enumerate(zip(PHASES, result['runs']))), 'receipt launch/commit metadata mismatch')
    require(result['full_block_artifact_consistency'] is True and result['full_block_m1_executed'] is True and
            result['live_authorities_verified'] is True, 'receipt scope/authority claim fields required')
    require(set(result['actual_sha256']) == set(PHASES), 'actual phase inventory drift')
    files = {}
    for phase in PHASES:
        require(set(result['actual_sha256'][phase]) == set(STORED_WIDTHS), 'actual terminal inventory drift')
        for name, pin in result['actual_sha256'][phase].items():
            require(Path(name).name == name, 'invalid actual terminal path')
            relative = phase + '/actual_' + name + '.bf16le'
            require(result['execution_identity']['files_sha256'].get(relative) == pin,
                    'actual terminal and physical execution identity differ')
            files[phase + '/' + name] = checked(Path(directory) / relative, pin, 2 * STORED_WIDTHS[name])
        require(files[phase + '/cache_k'] == files[phase + '/rope_k'] and
                files[phase + '/cache_v'] == files[phase + '/v'], 'actual append differs from its actual producer')
        # The caller's receipt hash binds optional files, but cannot prove they
        # came from RTL. Adding a file/hash never upgrades hardware authority.
        for i in range(57):
            name = phase + f'/actual_producer_{i:02d}.f32le'
            if name in result['execution_identity']['files_sha256']:
                files[name] = checked(Path(directory) / name, result['execution_identity']['files_sha256'][name],
                                      int(np.prod(producer_shape(i, PHASES.index(phase)))) * 4)
                value = np.frombuffer(files[name], dtype='<f4')
                require(np.isfinite(value).all(), 'nonfinite actual producer dump')
                if contract()['producer_sequence'][i]['storage_dtype'] == 'bfloat16':
                    require(not np.any(value.view('<u4') & 65535), 'actual producer BF16 boundary mismatch')
    return dict(files=files, receipt_sha256=result_sha, result=result,
                evidence_status='receipt_hashed_claim_only', hardware_authority_verified=False)


class OfficialM1:
    """Only explicit construction imports Torch/Transformers and instantiates a layer."""
    def __init__(self, bundle):
        import torch
        import transformers.activations as activation_source
        import transformers.cache_utils as cache_source
        from transformers.cache_utils import DynamicCache
        from transformers.models.qwen3_5 import modeling_qwen3_5 as official
        from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig
        from torch.utils._python_dispatch import TorchDispatchMode
        c = contract()
        variant = bundle['receipt']['variant']
        requested, capability = ('default', 'DEFAULT') if variant == 'baseline' else ('avx2', 'AVX2')
        require(os.environ.get('ATEN_CPU_CAPABILITY') == requested and
                torch.backends.cpu.get_cpu_capability() == capability, 'explicit matching CPU dispatch required')
        require(torch.__version__ == c['torch_version'] + '+cpu' and np.__version__ == c['numpy_version'] and
                torch.version.cuda is None and not torch.is_autocast_enabled('cpu'), 'unsupported official runtime')
        for module, pin in [(official, c['official_modeling_sha256']),
                (cache_source, 'abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b'),
                (activation_source, '5b20c0a3625edc0001a98f09ce3c6b5baa1100e1d7ad8dee649e4d45c8468665')]:
            checked(Path(inspect.getfile(module)), pin)
        checked(Path(inspect.getfile(Qwen3_5TextConfig)), CONFIG_SOURCE_SHA)
        package = json.loads(importlib.metadata.distribution('transformers').read_text('direct_url.json') or '{}')
        require(package.get('url') == 'https://github.com/huggingface/transformers/archive/' + c['framework_revision'] + '.zip' and
                package.get('archive_info', {}).get('hashes', {}).get('sha256') ==
                '15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d', 'framework package identity drift')
        config = Qwen3_5TextConfig.from_dict(json.loads(checked(
            ROOT / 'config/upstream/qwen3_5_0p8b/config.json', c['config_sha256']))['text_config'])
        config._attn_implementation = 'eager'
        torch.set_num_threads(2)
        torch.use_deterministic_algorithms(True)
        torch.set_float32_matmul_precision('highest')
        torch.set_flush_denormal(False)
        layer = official.Qwen3_5DecoderLayer(config, layer_idx=3).to(dtype=torch.bfloat16).eval()
        weights = {}
        for name, original in validated_weight_words(bundle['files']).items():
            weights[name] = torch.from_numpy(bf16(original.tobytes(), original.shape)).to(torch.bfloat16)
        loaded = layer.load_state_dict(weights, strict=True)
        require(not loaded.missing_keys and not loaded.unexpected_keys, 'incomplete layer weights')
        self.torch, self.official, self.config, self.layer = torch, official, config, layer
        self.cache_type, self.dispatch_type = DynamicCache, TorchDispatchMode
        self.rotary = official.Qwen3_5TextRotaryEmbedding(config)
        self.definitions = c['producer_sequence']
        self.metadata = dict(torch_version=torch.__version__, torch_cpu_capability=capability,
                             torch_git_version=torch.version.git_version, torch_threads=torch.get_num_threads(),
                             numpy_version=np.__version__, framework_revision=c['framework_revision'],
                             modeling_sha256=c['official_modeling_sha256'])

    def _tensor(self, value):
        return self.torch.from_numpy(np.asarray(value, dtype='<f4').copy()).to(self.torch.bfloat16)

    def _trace(self, call, *, conditioned=False):
        torch = self.torch
        definitions = self.definitions[33:39] if conditioned else self.definitions
        selected = {v['key'].split('|')[1] for v in self.definitions} - {'cast_bf16'}
        stack, rows, handles = (['self_attn'] if conditioned else []), [], []
        counts = {('self_attn', 'aten.mul.Tensor'): 4, ('self_attn', 'aten.add.Tensor'): 2} if conditioned else {}
        class Trace(self.dispatch_type):
            def __torch_dispatch__(mode, func, types, args=(), kwargs=None):
                op = str(func)
                value = func(*args, **(kwargs or {}))
                if op in ('aten.to.dtype', 'aten.type_as.default') and value.dtype == torch.bfloat16 and args[0].dtype == torch.float32:
                    op = 'cast_bf16'
                if op in selected or op == 'cast_bf16':
                    require(stack, 'unscoped official producer')
                    key = (stack[-1], op); count = counts.get(key, 0); counts[key] = count + 1
                    rows.append(dict(key=f'{key[0]}|{op}|{count}', dtype=str(value.dtype).removeprefix('torch.'),
                                     value=value.detach().float().cpu().numpy().copy()))
                return value
        if not conditioned:
            for name, module in self.layer.named_modules():
                def before(mod, args, n=name): stack.append(n)
                def after(mod, args, result): stack.pop()
                handles.extend((module.register_forward_pre_hook(before), module.register_forward_hook(after)))
        try:
            with torch.inference_mode(), Trace():
                result = call()
        finally:
            for handle in handles: handle.remove()
        require(stack == (['self_attn'] if conditioned else []), 'unbalanced native trace')
        require(len(rows) == len(definitions) and all(r['key'] == d['key'] and r['dtype'] == d['storage_dtype']
                for r, d in zip(rows, definitions)), 'M1 official producer sequence unsupported')
        return result, {i + (33 if conditioned else 0): row['value'] for i, row in enumerate(rows)}

    def forward(self, hidden, position, prior):
        require(hidden.shape == (1, 1, 1024) and position in (0, 1), 'true M1 input required')
        require(all(v.shape == (1, 2, position, 256) for v in prior), 'explicit exact prior-cache geometry required')
        torch = self.torch; x = self._tensor(hidden); cache = self.cache_type(config=self.config)
        if position:
            cache.update(self._tensor(prior[0]), self._tensor(prior[1]), 3)
        positions = torch.tensor([[[position]]] * 3)
        trig = self.rotary(x, positions)
        mask = torch.zeros((1, 1, 1, position + 1), dtype=torch.bfloat16)
        result, nodes = self._trace(lambda: self.layer(x, position_embeddings=trig, attention_mask=mask, past_key_values=cache))
        for i, value in nodes.items():
            require(value.shape == producer_shape(i, position), 'native M1 producer geometry drift')
        current = tuple(v.float().detach().numpy().copy() for v in (cache.layers[3].keys, cache.layers[3].values))
        require(all(same_bits(v[:, :, :position], p) for v, p in zip(current, prior)), 'official cache rewrote prior prefix')
        return dict(nodes=nodes, cache=current, output=result.float().detach().numpy().copy(),
                    trig=[v.float().detach().numpy().copy() for v in trig])

    def conditioned_gqa(self, query, key, value):
        position = key.shape[2] - 1
        require(query.shape == (1, 8, 1, 256) and key.shape == value.shape == (1, 2, position + 1, 256)
                and position in (0, 1), 'conditioned GQA shape drift')
        torch = self.torch
        q, k, v = self._tensor(query), self._tensor(key), self._tensor(value)
        mask = torch.zeros((1, 1, 1, position + 1), dtype=torch.bfloat16)
        _, nodes = self._trace(lambda: self.official.eager_attention_forward(self.layer.self_attn,
            q, k, v, mask, scaling=1 / 16, dropout=0.0), conditioned=True)
        return nodes


def audit(bundle, engine, actual=None):
    """Model adapter is injected so carry/acceptance logic can be tested without a model."""
    result = dict(status='REFERENCE_ONLY_M1_DIAGNOSTIC', native_full_block_acceptance=False,
        numerical_rtl_executed=False, native_context_acceptance=False, overall_pass=False,
        hardware_authority_verified=False, hardware_authority_upgrade_supported=False,
        supplied_output_evidence_status='receipt_hashed_claim_only' if actual else 'not_supplied',
        source_sha256=digest(Path(__file__).read_bytes()), cross_host_input_identity_claimed=False,
        reference_receipt_sha256=bundle['reference_receipt_sha256'],
        reference_receipt_file_sha256=bundle['reference_receipt_file_sha256'], runtime=engine.metadata,
        original_native_full_block_failures=bundle['receipt']['original_native_full_block_failures'],
        original_native_failure_evidence_status='receipt_claimed_historical_evidence_not_independently_authenticated',
        modes={}, conditioned_gqa={})
    empty = tuple(np.empty((1, 2, 0, 256), dtype='<f4') for _ in range(2))
    modes = ['official_own_cache', 'canonical_prior_cache'] + (['receipt_claimed_prior_cache'] if actual else [])
    for mode in modes:
        prior = empty; rows = []
        for position, (host, source) in enumerate(zip(PHASES, SOURCES)):
            if position and mode != 'official_own_cache':
                prior = tuple(cache_array(actual['files']['cold0/cache_' + role] if mode == 'receipt_claimed_prior_cache'
                        else bundle['files']['reference/cold0/cache_' + role + '.bf16le'], 1) for role in ('k', 'v'))
            hidden = bf16(bundle['files']['input/' + source + '_hidden.bf16le'], (1, 1, 1024))
            native = engine.forward(hidden, position, tuple(v.copy() for v in prior))
            trig = bf16(bundle['files']['input/trig.bf16le'][position * 128:(position + 1) * 128], (64,))
            trig_expected = [np.concatenate((v, v)).reshape(1, 1, 64) for v in (trig[:32], trig[32:])]
            require(all(same_bits(a, b) for a, b in zip(trig_expected, native['trig'])),
                    'native M1 trig differs from supplied original trig; same-input comparison rejected')
            comparisons = {str(i): stage_metrics(bundle['nodes'][source][i], native['nodes'][i]) for i in range(57)}
            row = dict(host_phase=host, absolute_position=position, query_tokens=1,
                raw_hidden_sha256=digest(bundle['files']['input/' + source + '_hidden.bf16le']),
                prior_cache_decoded_fp32_sha256=[array_sha(v) for v in prior],
                prior_origin='empty' if position == 0 else mode,
                comparison_origin='canonical_expected_not_actual_rtl', producer_comparisons=comparisons,
                original_trig_bit_identity=all(same_bits(a, b) for a, b in zip(trig_expected, native['trig'])),
                trig_comparisons=[stage_metrics(a, b) for a, b in zip(trig_expected, native['trig'])],
                output_comparison=stage_metrics(bundle['nodes'][source][56], native['output'], block=True),
                softmax_invariants=softmax_invariants(native['nodes'][36], np.zeros((1, 1, 1, position + 1), dtype='<f4')))
            if actual:
                row['supplied_output_evidence_status'] = 'receipt_hashed_claim_only'
                row['hardware_authority_verified'] = False
                row['receipt_hashed_terminal_comparisons'] = {name: stage_metrics(
                    bf16(actual['files'][host + '/' + name], producer_shape(i, position)), native['nodes'][i])
                    for name, i in TERMINALS.items()}
                row['receipt_hashed_output_comparison'] = stage_metrics(
                    bf16(actual['files'][host + '/residual2'], (1, 1, 1024)), native['output'], block=True)
            rows.append(row); prior = native['cache']
        result['modes'][mode] = dict(meaning='independent official two-M1 cache trajectory' if mode == 'official_own_cache'
            else ('conditional official decoder: supplied append-derived prior cache, hardware provenance unverified; official current K/V'
                  if mode == 'receipt_claimed_prior_cache' else
                  'conditional official decoder: canonical prior cache, official current K/V; not independent official cache trajectory'), cases=rows)
    for position, (host, source) in enumerate(zip(PHASES, SOURCES)):
        canonical = tuple(cache_array(bundle['files'][f'reference/{source}/cache_{role}.bf16le'], position + 1) for role in ('k', 'v'))
        canonical_q = bf16(bundle['files'][f'reference/{source}/rope_q.bf16le'], (1, 8, 1, 256))
        if actual:
            kv = tuple(cache_array(b''.join(actual['files'][phase + '/cache_' + role] for phase in PHASES[:position + 1]), position + 1) for role in ('k', 'v'))
            query = bf16(actual['files'][host + '/rope_q'], (1, 8, 1, 256))
        else:
            query, kv = canonical_q, canonical
        native = engine.conditioned_gqa(query, *kv)
        identity = same_bits(query, canonical_q) and all(same_bits(a, b) for a, b in zip(kv, canonical))
        stages = {}
        for i in range(33, 39):
            dump = host + f'/actual_producer_{i:02d}.f32le'
            if actual and dump in actual['files']:
                candidate = np.frombuffer(actual['files'][dump], dtype='<f4').reshape(producer_shape(i, position))
                origin, file_kind = 'receipt_hashed_claim_only', 'claimed_stage_dump'
            elif actual and i == 38:
                candidate = bf16(actual['files'][host + '/context'], producer_shape(i, position))
                origin, file_kind = 'receipt_hashed_claim_only', 'claimed_terminal_file'
            elif identity:
                candidate, origin, file_kind = bundle['nodes'][source][i], 'canonical_expected_only', 'expected_producer_file'
            else:
                stages[str(i)] = dict(status='MISSING_ACTUAL_STAGE_AND_CANONICAL_PREDECESSORS_DIFFER'); continue
            stages[str(i)] = dict(origin=origin, file_kind=file_kind, hardware_authority_verified=False,
                                  comparison=stage_metrics(candidate, native[i]))
        result['conditioned_gqa'][host] = dict(operand_origin='receipt_hashed_claim_only' if actual else 'canonical_expected',
            hardware_authority_verified=False, actual_predecessor_identity_established=False,
            conditioned_native_operands_exact_to_supplied_files=True,
            actual_dut_internal_qk_operands_directly_observed=False,
            canonical_predecessor_bit_identity=identity, query_sha256=array_sha(query),
            cache_sha256=[array_sha(v) for v in kv], stages=stages,
            meaning='pinned official eager attention with exactly supplied Q/K/V; isolates GQA from upstream decoder differences')
    result['future_retention_todo'] = retention_plan()
    if actual:
        result['receipt_hashed_claim_evidence'] = dict(receipt_sha256=actual.get('receipt_sha256'),
            hardware_authority_verified=False,
            claimed_identity={key: actual.get('result', {}).get(key) for key in ('binary_sha256', 'rtl_sha256', 'input_sha256')})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path)
    p.add_argument('--receipt-file-sha256', help='SHA256 of saved reference_receipt.json file bytes')
    p.add_argument('--canonical-receipt-sha256', help='optional live canonical JSON identity, distinct from file SHA256')
    p.add_argument('--retention-plan', action='store_true')
    p.add_argument('--actual', type=Path)
    p.add_argument('--actual-result', type=Path)
    p.add_argument('--actual-result-sha256')
    p.add_argument('--execute-official', action='store_true')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.retention_plan:
        require(not a.execute_official, 'retention plan cannot execute a model')
        print(json.dumps(retention_plan(), indent=2)); return
    require(a.bundle is not None and a.receipt_file_sha256 is not None, 'retained bundle and receipt file hash required')
    require(all(v is None for v in (a.actual, a.actual_result, a.actual_result_sha256)) or
            all(v is not None for v in (a.actual, a.actual_result, a.actual_result_sha256)), 'all actual-evidence arguments required together')
    bundle = load_bundle(a.bundle, a.receipt_file_sha256, a.canonical_receipt_sha256)
    actual = load_actual(a.actual, a.actual_result, a.actual_result_sha256, bundle) if a.actual else None
    if not a.execute_official:
        print(json.dumps(dict(status='RETAINED_BYTES_VERIFIED_NO_MODEL_EXECUTED',
                              reference_receipt_file_sha256=bundle['reference_receipt_file_sha256'],
                              reference_receipt_sha256=bundle['reference_receipt_sha256'],
                              receipt_claim_file_hashes_verified=actual is not None,
                              hardware_authority_verified=False, native_full_block_acceptance=False), indent=2)); return
    output = fresh_report_path(a.output)
    result = audit(bundle, OfficialM1(bundle), actual)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(status=result['status'], native_full_block_acceptance=False, report_sha256=digest(output.read_bytes())), indent=2))


if __name__ == '__main__':
    main()
