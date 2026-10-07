"""Portable extraction/admission tests; these do not claim official native runs.

Synthetic producer arrays exist only in temporary ignored directories. Real
CPU executions are exercised by the opt-in rebuild path with verified payloads.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pytest

from heteronpu.model_geometry import require
from heteronpu import qk_norm256_candidate as oracle
from heteronpu import qk_norm256_materialization as m

ROOT = Path(__file__).resolve().parents[1]


def synthetic_producers():
    arrays = {}
    for phase, case in enumerate(m.PHASES):
        for index, shape in ((8, (1, 128, 4096)), (16, (1, 128, 8, 256)),
                             (17, (1, 128, 512)), (25, (1, 128, 2, 256))):
            bits = ((np.arange(np.prod(shape), dtype='<u4') % 127) << 16) | np.uint32(0x3F000000 + phase * 0x00800000)
            arrays[f'{case}_native_producer_{index:02d}'] = bits.reshape(shape).view('<f4')
    return arrays


@pytest.fixture
def weights(monkeypatch):
    raw = {name: bytes([role, 0x3F]) * 256 for role, name in enumerate(m.WEIGHTS)}
    monkeypatch.setattr(oracle, 'WEIGHT_SHA256', tuple(hashlib.sha256(raw[name]).hexdigest() for name in m.WEIGHTS))
    return raw


def native_report(contract, variant, payloads, prefix_report, prefix_path, arrays_path):
    report = {key: copy.deepcopy(contract[key]) for key in
              ('model_id', 'revision', 'framework_revision', 'layer_id', 'batch', 'query_tokens', 'producer_sequence', 'thresholds')}
    comparisons = [{'pass': True} for _ in range(126)]
    # Keep an actual collection-level diagnostic failure in the synthetic test
    # report. Corpus admission must not rewrite full-block numerical acceptance.
    comparisons[-1] = {'pass': False, 'producer': 'synthetic_full_block_test'}
    report.update(contract_sha256=m.CONTRACT_SHA256, cases=list(m.PHASES),
        audit_collection_complete=True, upstream_admission='fresh_pinned_prefix_executed_in_process',
        gate_pass=False, status='BLOCKED_BF16_PRODUCER_GATE', comparisons=comparisons,
        failed_producers=[comparisons[-1]], softmax_invariants=[{'pass': True} for _ in range(4)],
        native_replay=[{'case': case, 'producer': name, 'bit_identical_to_original_prefix': True}
                       for case in m.PHASES for name in ('output', 'key', 'value')],
        runner_source_sha256={**m.AUDIT_SOURCES, **contract['fresh_prefix_source_sha256']},
        upstream_arrays=prefix_report['arrays'], upstream_report_sha256=m._sha(prefix_path.read_bytes()),
        payload_manifest_sha256=payloads['layer3']['sha256'], arrays=m._record(arrays_path),
        environment={'torch': contract['torch_version'] + '+cpu', 'numpy': contract['numpy_version'],
            'torch_git_version': m.TORCH_GIT_VERSION, 'torch_threads': 2,
            'torch_cpu_capability': m.VARIANTS[variant][1], 'official_source_sha256': m.OFFICIAL_SOURCES,
            'transformers_direct_url': {'url': 'https://github.com/huggingface/transformers/archive/' + contract['framework_revision'] + '.zip',
                'archive_info': {'hashes': {'sha256': m.ARCHIVE_SHA256}}}})
    return report


@pytest.fixture
def mocked_materialization(monkeypatch, weights):
    """Exercise the entire writer/reader with an explicitly fake subprocess."""
    payloads = {name: {'file': 'manifest.json', 'bytes': 4, 'sha256': m._sha(name.encode())}
                for name in ('layer0', 'layer3', 'additional_prefix')}
    contract = m._contract(ROOT)
    monkeypatch.setattr(m, '_payload_inputs', lambda *args: (copy.deepcopy(payloads), weights))
    calls = []

    def execute(root, payload0, payload3, payload_extra, output, variant):
        calls.append(variant)
        native, prefix = output / variant / 'native', output / variant / 'prefix'
        native.mkdir(parents=True); prefix.mkdir(parents=True)
        arrays_path = native / 'all_bf16_producers.npz'
        m._save_deterministic(arrays_path, synthetic_producers())
        prefix_arrays = prefix / 'prefix_activations_and_states.npz'
        m._save_deterministic(prefix_arrays, {'explicitly_synthetic_test': np.zeros(1, dtype='<f4')})
        prefix_report = {key: contract[key] for key in ('model_id', 'revision', 'framework_revision', 'batch', 'query_tokens')}
        prefix_report.update(status='PASS_REAL_EMBEDDING_OFFICIAL_PREFIX_CHAIN_U00_2_OPEN',
            official_TextModel_prefix_executed=True, upstream_activation_provenance_verified_for_layers_0_to_3=True,
            comparisons=[{'mismatches': 0}] * 32, arrays=m._record(prefix_arrays),
            runner_source_sha256=contract['upstream_runner_source_sha256'], payload_manifests=payloads)
        prefix_path = prefix / 'result.json'
        prefix_path.write_text(json.dumps(prefix_report))
        report = native_report(contract, variant, payloads, prefix_report, prefix_path, arrays_path)
        (native / 'result.json').write_text(json.dumps(report))
    monkeypatch.setattr(m, '_execute_variant', execute)
    (ROOT / 'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='test_qk_materialization_', dir=ROOT / 'work') as directory:
        output = Path(directory) / 'fresh'
        corpora, digest = m.rebuild(ROOT, Path('unused0'), Path('unused3'), Path('unused_extra'), output)
        yield output, corpora, digest, calls


def test_deterministic_native_extraction_layout_and_archive(tmp_path, weights):
    producers = synthetic_producers()
    first, second = m._extract(producers, weights), m._extract(producers, weights)
    require(set(first) == set(second), 'array inventory changed')
    for name in first:
        require(np.array_equal(first[name], second[name]), 'extraction is not deterministic')
    for phase, case in enumerate(m.PHASES):
        start = phase * 1280
        q = producers[case + '_native_producer_08'].view('<u4').reshape(128, 8, 512)
        require(np.array_equal(first['input_bf16_u32'][start:start + 1024], q[..., :256].reshape(1024, 256)), 'Q extraction changed')
        require(np.array_equal(first['gate_bf16_u32'][phase * 1024:(phase + 1) * 1024], q[..., 256:].reshape(1024, 256)), 'gate extraction changed')
        require(np.array_equal(first['input_bf16_u32'][start + 1024:start + 1280],
                               producers[case + '_native_producer_17'].view('<u4').reshape(256, 256)), 'K extraction changed')
    for name, data in (('one.npz', first), ('two.npz', second)):
        m._save_deterministic(tmp_path / name, data)
    require((tmp_path / 'one.npz').read_bytes() == (tmp_path / 'two.npz').read_bytes(), 'archive metadata is not deterministic')


@pytest.mark.parametrize('bad', ['shape', 'dtype', 'low_bits', 'nonfinite', 'weight'])
def test_extraction_rejects_invalid_producer_or_weight(bad, weights):
    producers = synthetic_producers()
    key = 'cold_m128_native_producer_08'
    if bad == 'shape': producers[key] = producers[key].reshape(128, 4096)
    elif bad == 'dtype': producers[key] = producers[key].astype(np.float64)
    elif bad == 'low_bits': producers[key].view('<u4').flat[0] |= 1
    elif bad == 'nonfinite': producers[key].flat[0] = np.inf
    else: weights[m.WEIGHTS[0]] = b'bad'
    with pytest.raises(ValueError):
        m._extract(producers, weights)


def test_fresh_writer_reader_receipt_and_scope(mocked_materialization):
    output, corpora, digest, calls = mocked_materialization
    require(calls == ['baseline', 'avx2'], 'two distinct subprocess invocations missing')
    require(set(corpora) == {'baseline', 'avx2'} and len(digest) == 64, 'API drift')
    require(sum(len(data['role']) for data, origin in corpora.values()) == 5120, 'head count drift')
    for data, origin in corpora.values():
        require(origin['provenance_sha256'] == digest and origin['native_audit_gate_pass'] is False,
                'receipt or separate full-block rejection lost')
        require(not any(arr.flags.writeable for arr in data.values()), 'corpus arrays must be read-only')
    manifest = m._read_json(output / 'provenance.json')
    require(manifest['historical_byte_identity_claimed'] is False and manifest['unique_input_count_claimed'] is False,
            'historical or unique-input overclaim')
    require(manifest['cross_variant_input_arrays_identical'] is True, 'identical variant data must be disclosed')
    loaded = m.load_materialized(ROOT, output, trusted_manifest_sha256=digest)
    require(np.array_equal(loaded['baseline'][0]['input_bf16_u32'], corpora['baseline'][0]['input_bf16_u32']), 'recheck drift')
    with pytest.raises(ValueError, match='fresh or empty'):
        m.rebuild(ROOT, Path('unused'), Path('unused'), Path('unused'), output)


@pytest.mark.parametrize('target', ['provenance.json', 'baseline.npz', 'baseline/native/result.json',
                                    'baseline/native/all_bf16_producers.npz', 'baseline/prefix/result.json',
                                    'baseline/prefix/prefix_activations_and_states.npz'])
def test_tampering_rejected_before_admission(mocked_materialization, target):
    output, corpora, digest, calls = mocked_materialization
    path = output / target
    data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
    with pytest.raises(ValueError, match='digest|hash'):
        m.load_materialized(ROOT, output, trusted_manifest_sha256=digest)


def test_wrong_or_self_certified_manifest_has_no_default_authority(mocked_materialization):
    output, corpora, digest, calls = mocked_materialization
    with pytest.raises(TypeError):
        m.load_materialized(ROOT, output)
    with pytest.raises(ValueError, match='untrusted'):
        m.load_materialized(ROOT, output, trusted_manifest_sha256='0' * 64)
    report = m._read_json(output / 'provenance.json')
    report['manifest_sha256'] = digest
    (output / 'provenance.json').write_text(json.dumps(report))
    with pytest.raises(ValueError, match='untrusted'):
        m.load_materialized(ROOT, output, trusted_manifest_sha256=digest)


def test_source_binding_rechecked(mocked_materialization, monkeypatch):
    output, corpora, digest, calls = mocked_materialization
    original = m._source_hashes
    def changed(root, contract):
        sources = original(root, contract)
        sources['src/heteronpu/qk_norm256_materialization.py'] = '0' * 64
        return sources
    monkeypatch.setattr(m, '_source_hashes', changed)
    with pytest.raises(ValueError, match='source binding'):
        m.load_materialized(ROOT, output, trusted_manifest_sha256=digest)


@pytest.mark.parametrize('field,value', [
    ('model_id', 'other/model'), ('revision', '0' * 40), ('framework_revision', '0' * 40),
    ('environment.torch', '2.9.0+cpu'), ('environment.numpy', '2.2.0'),
    ('environment.torch_git_version', '0' * 40), ('environment.torch_cpu_capability', 'AVX512'),
    ('environment.torch_threads', 1), ('upstream_admission', 'immutable_saved_prefix_report_digest'),
    ('producer_sequence', []), ('runner_source_sha256', {}), ('gate_pass', True),
])
def test_model_runtime_cpu_and_source_report_mismatch(mocked_materialization, field, value):
    output, corpora, digest, calls = mocked_materialization
    report = m._read_json(output / 'baseline/native/result.json')
    target = report
    keys = field.split('.')
    for key in keys[:-1]: target = target[key]
    target[keys[-1]] = value
    with pytest.raises(ValueError):
        m._validate_report(report, m._contract(ROOT), 'baseline')


def test_bundle_cannot_detach_from_native_extraction(mocked_materialization):
    output, corpora, digest, calls = mocked_materialization
    # Even a test-authorized refreshed receipt cannot admit a bundle whose
    # arrays and per-array hashes agree with each other but not its producer.
    manifest = m._read_json(output / 'provenance.json')
    data = {key: value.copy() for key, value in corpora['baseline'][0].items()}
    data['native_bf16_u32'][0, 0] ^= 0x00010000
    m._save_deterministic(output / 'baseline.npz', data)
    manifest['corpora']['baseline']['bundle'] = m._record(output / 'baseline.npz')
    manifest['corpora']['baseline']['array_sha256'] = m._array_hashes(data)
    path = output / 'provenance.json'; path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='native extraction binding'):
        m.load_materialized(ROOT, output, trusted_manifest_sha256=m._sha(path.read_bytes()))


def test_failure_leaves_no_success_manifest(monkeypatch, weights):
    monkeypatch.setattr(m, '_payload_inputs', lambda *args: ({}, weights))
    def failed(*args): raise subprocess.CalledProcessError(3, 'synthetic_failure')
    monkeypatch.setattr(m, '_execute_variant', failed)
    with tempfile.TemporaryDirectory(dir=ROOT / 'work') as directory:
        output = Path(directory) / 'failed'
        with pytest.raises(subprocess.CalledProcessError):
            m.rebuild(ROOT, Path('unused'), Path('unused'), Path('unused'), output)
        require(not (output / 'provenance.json').exists(), 'failed rebuild wrote an authority manifest')


def test_output_must_be_ignored_work_and_not_symlink_escape(tmp_path):
    with pytest.raises(ValueError, match='ignored work'):
        m.rebuild(ROOT, tmp_path, tmp_path, tmp_path, tmp_path / 'output')
    with tempfile.TemporaryDirectory(dir=ROOT / 'work') as directory:
        link = Path(directory) / 'outside'; link.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError, match='ignored work'):
            m.rebuild(ROOT, tmp_path, tmp_path, tmp_path, link / 'output')


def test_fresh_subprocess_dispatch_is_explicit(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: seen.append((args, kwargs)))
    monkeypatch.setenv('ATEN_CPU_CAPABILITY', 'avx512')
    for variant in m.VARIANTS:
        m._execute_variant(ROOT, tmp_path, tmp_path, tmp_path, tmp_path, variant)
    require(len(seen) == 2, 'subprocess count drift')
    for (args, kwargs), variant in zip(seen, m.VARIANTS, strict=True):
        require(args[0][:2] == [sys.executable, '-I'], 'fresh isolated Python required')
        require(kwargs['env']['ATEN_CPU_CAPABILITY'] == m.VARIANTS[variant][0], 'inherited dispatch override leaked')
        require(args[0][-2:] == ['--_variant', variant] and kwargs['check'] is True, 'worker invocation drift')


def test_cli_rejects_untrusted_manifest_override(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/rebuild_qk_norm256_corpora.py'),
        '--payload-layer0', str(tmp_path), '--payload-layer3', str(tmp_path), '--payload-extra', str(tmp_path),
        '--output', str(tmp_path), '--trusted-manifest-sha256', '0' * 64], capture_output=True, text=True)
    require(result.returncode == 2 and 'unrecognized arguments' in result.stderr, 'CLI admitted self-certified trust')


def test_security_validation_survives_optimization(mocked_materialization):
    output, corpora, digest, calls = mocked_materialization
    code = f'''from pathlib import Path
from heteronpu.qk_norm256_materialization import load_materialized
try:
    load_materialized(Path({str(ROOT)!r}), Path({str(output)!r}), trusted_manifest_sha256='0' * 64)
except ValueError as exc:
    if 'untrusted' not in str(exc): raise
else:
    raise RuntimeError('optimized security check vanished')
'''
    env = os.environ.copy(); env['PYTHONPATH'] = str(ROOT / 'src')
    subprocess.run([sys.executable, '-O', '-c', code], env=env, check=True)
