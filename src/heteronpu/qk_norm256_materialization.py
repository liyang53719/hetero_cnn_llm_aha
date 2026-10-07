"""Fresh official Q/K captures, distinct from the optional historical corpora.

Trust begins with executing the pinned producer in two fresh subprocesses. The
returned manifest digest is an in-process receipt, not a digest to read from an
untrusted manifest or accept as a command-line override. Reproducibility here
means pinned inputs, source and runtime plus deterministic extraction, not
historical byte identity or backend-independent native arithmetic.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import numpy as np

from .model_geometry import require
from . import qk_norm256_candidate as oracle

CONTRACT = 'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json'
CONTRACT_SHA256 = '13b52da81746346f62c6a2f28cc1d6fa565989bd71d834dd4951ee2056355d97'
AUDIT_SOURCES = {
    'scripts/run_qwen35_bf16_audit.py': '13119e753f6003090d6b2582b545f42985a9fef3e84c585bde48a8bac17250eb',
    'src/heteronpu/qwen35_bf16_reference.py': 'f6a8f9cea441552baf099de174247b47f4c1004fee5b3e5790dfa010083665b9',
}
MATERIALIZER_SOURCES = (
    'scripts/rebuild_qk_norm256_corpora.py',
    'src/heteronpu/qk_norm256_materialization.py',
    'src/heteronpu/qk_norm256_candidate.py',
    'src/heteronpu/rope_bf16_candidate.py',
)
VARIANTS = {'baseline': ('default', 'DEFAULT'), 'avx2': ('avx2', 'AVX2')}
PHASES = ('cold_m128', 'carried_m128')
WEIGHTS = ('self_attn.q_norm.weight', 'self_attn.k_norm.weight')
ARCHIVE_SHA256 = '15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d'
TORCH_GIT_VERSION = '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0'
OFFICIAL_SOURCES = {
    'modeling': 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18',
    'cache': 'abdcb0ae88aa5b924ef7d76879db680e9af8f3ec1dafbba7ce446ecb521a944b',
    'activations': '5b20c0a3625edc0001a98f09ce3c6b5baa1100e1d7ad8dee649e4d45c8468665',
    'configuration': '2f26c4bb911772d42a5f16e82bdea4b9ba1ac07872df527ec228622d35f3c30e',
}
PROVENANCE_KIND = 'fresh_pinned_official_prefix_and_layer3_cpu_dispatch_v1'


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), 'expected JSON object')
    return value


def _record(path: Path) -> dict:
    raw = path.read_bytes()
    return {'file': path.name, 'bytes': len(raw), 'sha256': _sha(raw)}


def _verify_file(path: Path, record: dict) -> None:
    require(record == _record(path), 'materialized file name/size/hash drift: ' + path.name)


def _contract(root: Path) -> dict:
    require(_sha((root / CONTRACT).read_bytes()) == CONTRACT_SHA256, 'pinned BF16 contract drift')
    contract = _read_json(root / CONTRACT)
    for name, digest in {**AUDIT_SOURCES, **contract['fresh_prefix_source_sha256']}.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root.resolve()) and _sha(path.read_bytes()) == digest,
                'pinned producer source drift: ' + name)
    return contract


def _source_hashes(root: Path, contract: dict) -> dict:
    names = (CONTRACT, *AUDIT_SOURCES, *contract['fresh_prefix_source_sha256'], *MATERIALIZER_SOURCES)
    return {name: _sha((root / name).read_bytes()) for name in names}


def _location(root: Path, output: Path, *, fresh: bool = False) -> tuple[Path, Path]:
    root, output = Path(root).resolve(), Path(output).resolve()
    require(root == Path(__file__).resolve().parents[2], 'materializer root/import identity drift')
    require(Path(oracle.__file__).resolve() == root / 'src/heteronpu/qk_norm256_candidate.py',
            'oracle import identity drift')
    require(sys.byteorder == 'little', 'only little-endian CPU extraction supported')
    require(output.is_relative_to(root / 'work') and output != root / 'work',
            'materialized corpus must live under ignored work/')
    if fresh:
        require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
                'output must be fresh or empty; old evidence cannot survive a failed rebuild')
    return root, output


def _validate_report(report: dict, contract: dict, variant: str) -> None:
    require(variant in VARIANTS, 'unknown CPU variant')
    for key in ('model_id', 'revision', 'framework_revision', 'layer_id', 'batch', 'query_tokens'):
        require(report[key] == contract[key] and type(report[key]) is type(contract[key]),
                'native model/geometry identity drift: ' + key)
    require(report['contract_sha256'] == CONTRACT_SHA256, 'native contract identity drift')
    require(report['producer_sequence'] == contract['producer_sequence'], 'native producer sequence drift')
    require(report['thresholds'] == contract['thresholds'], 'native threshold drift')
    require(report['cases'] == list(PHASES), 'cold/carried native cases drift')
    require(report['audit_collection_complete'] is True
            and report['upstream_admission'] == 'fresh_pinned_prefix_executed_in_process',
            'native report must come from a fresh official prefix execution')
    require(type(report['gate_pass']) is bool, 'native audit gate type drift')
    expected_status = 'PASS_SOURCE_NATIVE_BF16_DIAGNOSTIC_ONLY' if report['gate_pass'] else 'BLOCKED_BF16_PRODUCER_GATE'
    require(report['status'] == expected_status, 'native audit status drift')
    require(len(report['comparisons']) == 126 and all(type(r['pass']) is bool for r in report['comparisons']),
            'native comparison inventory drift')
    failed = [r for r in report['comparisons'] if not r['pass']]
    require(report['failed_producers'] == failed and len(report['softmax_invariants']) == 4
            and all(type(r['pass']) is bool for r in report['softmax_invariants'])
            and report['gate_pass'] is (not failed and all(r['pass'] for r in report['softmax_invariants'])),
            'native numerical audit result drift')
    expected_replay = [{'case': case, 'producer': name, 'bit_identical_to_original_prefix': True}
                       for case in PHASES for name in ('output', 'key', 'value')]
    require(report['native_replay'] == expected_replay, 'native official prefix replay drift')
    require(report['runner_source_sha256'] == {**AUDIT_SOURCES, **contract['fresh_prefix_source_sha256']},
            'native source binding drift')
    env = report['environment']
    require(env['torch'] == contract['torch_version'] + '+cpu' and env['numpy'] == contract['numpy_version'],
            'native runtime version drift')
    require(env['torch_git_version'] == TORCH_GIT_VERSION, 'native Torch build identity drift')
    require(env['torch_cpu_capability'] == VARIANTS[variant][1], 'actual CPU dispatch mismatch')
    require(type(env['torch_threads']) is int and env['torch_threads'] == 2, 'native thread count drift')
    require(env['official_source_sha256'] == OFFICIAL_SOURCES, 'installed official source identity drift')
    url = env['transformers_direct_url']
    require(url.get('url') == 'https://github.com/huggingface/transformers/archive/' + contract['framework_revision'] + '.zip'
            and url.get('archive_info', {}).get('hashes', {}).get('sha256') == ARCHIVE_SHA256,
            'framework archive identity drift')


def _validate_prefix(report: dict, native: dict, contract: dict, payloads: dict) -> None:
    for key in ('model_id', 'revision', 'framework_revision', 'batch', 'query_tokens'):
        require(report[key] == contract[key], 'prefix identity drift: ' + key)
    require(report['status'] == 'PASS_REAL_EMBEDDING_OFFICIAL_PREFIX_CHAIN_U00_2_OPEN'
            and report['official_TextModel_prefix_executed'] is True
            and report['upstream_activation_provenance_verified_for_layers_0_to_3'] is True,
            'official prefix verification missing')
    require(len(report['comparisons']) == 32 and all(r['mismatches'] == 0 for r in report['comparisons']),
            'official prefix mathematical audit failed')
    require(report['arrays'] == native['upstream_arrays'], 'native/prefix array link drift')
    require(report['runner_source_sha256'] == contract['upstream_runner_source_sha256'],
            'prefix source binding drift')
    for name in ('layer0', 'layer3', 'additional_prefix'):
        require(report['payload_manifests'][name]['sha256'] == payloads[name]['sha256'], 'prefix weight receipt drift')
    require(native['payload_manifest_sha256'] == payloads['layer3']['sha256'], 'native weight receipt drift')


def _bf16_words(value: np.ndarray, shape: tuple, name: str) -> np.ndarray:
    require(isinstance(value, np.ndarray) and value.dtype == np.dtype('<f4') and value.shape == shape,
            'native producer dtype/shape drift: ' + name)
    words = np.ascontiguousarray(value).view('<u4')
    require(np.isfinite(value).all() and not np.any(words & 0xFFFF), 'invalid native BF16 producer: ' + name)
    return words


def _extract(producers, raw_weights: dict) -> dict:
    """Pure bit extraction. Never run or approximate a norm to make its target."""
    inputs, native, gates, phases, tokens, heads, roles, gate_indices = ([] for _ in range(8))
    gate_start = 0
    for phase, case in enumerate(PHASES):
        def words(index, shape):
            name = f'{case}_native_producer_{index:02d}'
            return _bf16_words(producers[name], shape, name)
        projected_q = words(8, (1, 128, 4096)).reshape(128, 8, 512)
        q_native = words(16, (1, 128, 8, 256)).reshape(1024, 256)
        k_input = words(17, (1, 128, 512)).reshape(256, 256)
        k_native = words(25, (1, 128, 2, 256)).reshape(256, 256)
        gates.append(projected_q[..., 256:].reshape(1024, 256))
        for role, count, x, y in ((0, 8, projected_q[..., :256].reshape(1024, 256), q_native),
                                  (1, 2, k_input, k_native)):
            size = 128 * count
            inputs.append(x); native.append(y)
            phases.append(np.full(size, phase, dtype='u1'))
            roles.append(np.full(size, role, dtype='u1'))
            tokens.append(np.repeat(np.arange(128, dtype='u1'), count))
            heads.append(np.tile(np.arange(count, dtype='u1'), 128))
            gate_indices.append(np.arange(gate_start, gate_start + size, dtype='<i4') if role == 0
                                else np.full(size, -1, dtype='<i4'))
            if role == 0:
                gate_start += size
    require(set(raw_weights) == set(WEIGHTS), 'Q/K weight inventory drift')
    weight_words = []
    for role, name in enumerate(WEIGHTS):
        raw = raw_weights[name]
        require(isinstance(raw, bytes) and len(raw) == 512 and _sha(raw) == oracle.WEIGHT_SHA256[role],
                'pinned Q/K weight bytes drift')
        weight_words.append(np.frombuffer(raw, dtype='<u2').astype('<u4') << 16)
    data = {'input_bf16_u32': np.concatenate(inputs), 'native_bf16_u32': np.concatenate(native),
            'gate_bf16_u32': np.concatenate(gates), 'weight_bf16_u32': np.stack(weight_words),
            'phase': np.concatenate(phases), 'token': np.concatenate(tokens), 'head': np.concatenate(heads),
            'role': np.concatenate(roles), 'gate_index': np.concatenate(gate_indices)}
    oracle._validate_arrays(data, {'array_sha256': _array_hashes(data)})
    return data


def _array_hashes(data: dict) -> dict:
    return {name: _sha(value.tobytes()) for name, value in data.items()}


def _save_deterministic(path: Path, data: dict) -> None:
    """Stable names, ordering, metadata, NPY encoding and deflate settings."""
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(data):
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, data[name], allow_pickle=False)
            entry = zipfile.ZipInfo(name + '.npy', date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, buffer.getvalue(), compresslevel=9)


def _payload_inputs(root: Path, payload0: Path, payload3: Path, payload_extra: Path) -> tuple[dict, dict]:
    from . import pinned_block_payload, pinned_gdn_payload, pinned_prefix_payload
    inputs = {'layer0': (pinned_gdn_payload, payload0), 'layer3': (pinned_block_payload, payload3),
              'additional_prefix': (pinned_prefix_payload, payload_extra)}
    records, weights = {}, {}
    for name, (module, directory) in inputs.items():
        _, raw = module.load_payload(root, directory)
        records[name] = _record(directory / 'manifest.json')
        if name == 'layer3':
            weights = {key: raw[key] for key in WEIGHTS}
    return records, weights


def _execute_variant(root: Path, payload0: Path, payload3: Path, payload_extra: Path,
                     output: Path, variant: str) -> None:
    env = os.environ.copy()
    env['ATEN_CPU_CAPABILITY'] = VARIANTS[variant][0]
    # A fresh isolated interpreter prevents an already imported Torch runtime or
    # external PYTHONPATH from bypassing the requested CPU dispatch/source.
    command = [sys.executable, '-I', str(root / 'scripts/rebuild_qk_norm256_corpora.py'),
               '--root', str(root), '--payload-layer0', str(payload0), '--payload-layer3', str(payload3),
               '--payload-extra', str(payload_extra), '--output', str(output / variant), '--_variant', variant]
    with (output / (variant + '.log')).open('w') as log:
        subprocess.run(command, env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)


def run_variant(root: Path, payload0: Path, payload3: Path, payload_extra: Path,
                output: Path, variant: str) -> None:
    """Internal subprocess entry. It never creates a trusted corpus manifest."""
    root, output = _location(root, output, fresh=True)
    contract = _contract(root)
    require(variant in VARIANTS and os.environ.get('ATEN_CPU_CAPABILITY') == VARIANTS[variant][0],
            'requested CPU dispatch environment mismatch')
    import torch
    require(torch.backends.cpu.get_cpu_capability() == VARIANTS[variant][1], 'actual CPU dispatch mismatch')
    require(torch.__version__ == contract['torch_version'] + '+cpu' and torch.version.cuda is None
            and np.__version__ == contract['numpy_version'], 'unsupported official execution runtime')
    spec = importlib.util.spec_from_file_location('pinned_qk_native_audit', root / 'scripts/run_qwen35_bf16_audit.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    report = audit.run(root, payload3, output / 'prefix', output / 'native',
                       rebuild_layer0=payload0, rebuild_extra=payload_extra)
    _validate_report(report, contract, variant)


def rebuild(root: Path, payload0: Path, payload3: Path, payload_extra: Path,
            output: Path) -> tuple[dict, str]:
    """Execute both official captures, return verified corpora and trusted digest.

    The caller must retain the returned digest for subsequent checks in the
    same invocation. No existing manifest, report, or corpus is admitted here.
    ``corpora[name]`` is ``(read_only_arrays, provenance)`` for baseline/avx2.
    """
    root, output = _location(root, output, fresh=True)
    payload0, payload3, payload_extra = (Path(p).resolve() for p in (payload0, payload3, payload_extra))
    contract = _contract(root)
    sources = _source_hashes(root, contract)
    payloads, weights = _payload_inputs(root, payload0, payload3, payload_extra)
    output.mkdir(parents=True, exist_ok=True)
    origins = {}
    for variant, (requested, actual) in VARIANTS.items():
        _execute_variant(root, payload0, payload3, payload_extra, output, variant)
        native_dir, prefix_dir = output / variant / 'native', output / variant / 'prefix'
        report, prefix = _read_json(native_dir / 'result.json'), _read_json(prefix_dir / 'result.json')
        _validate_report(report, contract, variant)
        _validate_prefix(prefix, report, contract, payloads)
        require(report['upstream_report_sha256'] == _sha((prefix_dir / 'result.json').read_bytes()),
                'native/prefix report link drift')
        _verify_file(native_dir / 'all_bf16_producers.npz', report['arrays'])
        _verify_file(prefix_dir / 'prefix_activations_and_states.npz', prefix['arrays'])
        with np.load(native_dir / 'all_bf16_producers.npz', allow_pickle=False) as producers:
            data = _extract(producers, weights)
        bundle = output / (variant + '.npz')
        _save_deterministic(bundle, data)
        origins[variant] = {'bundle': _record(bundle), 'array_sha256': _array_hashes(data),
            'requested_aten_cpu_capability': requested, 'actual_torch_cpu_capability': actual,
            'fresh_audit_report': _record(native_dir / 'result.json'), 'fresh_audit_arrays': report['arrays'],
            'fresh_prefix_report': _record(prefix_dir / 'result.json'), 'fresh_prefix_arrays': prefix['arrays'],
            'native_audit_status': report['status'], 'native_audit_gate_pass': report['gate_pass'],
            'native_failed_comparisons': len(report['failed_producers']), 'environment': report['environment'],
            'heads': 2560, 'q_heads': 2048, 'k_heads': 512}
    require(_source_hashes(root, _contract(root)) == sources, 'source changed during materialization')
    # Reverify receipt/weight bytes after both subprocesses, including layer0 and
    # prefix payloads. A changed input must never acquire a successful manifest.
    require(_payload_inputs(root, payload0, payload3, payload_extra) == (payloads, weights),
            'payload changed during materialization')
    manifest = {'schema_version': 1, 'provenance_kind': PROVENANCE_KIND,
        'model_id': contract['model_id'], 'revision': contract['revision'],
        'framework_revision': contract['framework_revision'], 'layer_id': 3,
        'policy': oracle.POLICY, 'head_dim': oracle.HEAD_DIM, 'epsilon_word': oracle.EPSILON,
        'phases': list(PHASES), 'contract_sha256': CONTRACT_SHA256, 'source_sha256': sources,
        'payload_manifests': payloads, 'weights_sha256': dict(zip(WEIGHTS, oracle.WEIGHT_SHA256)),
        'official_executions': 2, 'heads_total': 5120, 'historical_byte_identity_claimed': False,
        'unique_input_count_claimed': False, 'arithmetic_recomputed_during_extraction': False,
        'scope': 'same-input Q/K component; fixed artificial token IDs; native full-block gate remains separate',
        'cross_variant_input_arrays_identical': origins['baseline']['array_sha256']['input_bf16_u32'] == origins['avx2']['array_sha256']['input_bf16_u32'],
        'cross_variant_native_arrays_identical': origins['baseline']['array_sha256']['native_bf16_u32'] == origins['avx2']['array_sha256']['native_bf16_u32'],
        'corpora': origins}
    path = output / 'provenance.json'
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    digest = _sha(path.read_bytes())
    return load_materialized(root, output, trusted_manifest_sha256=digest), digest


def load_materialized(root: Path, output: Path, *, trusted_manifest_sha256: str) -> dict:
    """Fail closed against the digest retained from ``rebuild`` in this process.

    Callers must not obtain this trust anchor from a CLI, the saved manifest,
    or arbitrary third-party content. Saved historical captures use the separate
    code-pinned ``qk_norm256_candidate.load_corpus`` API instead.
    """
    root, output = _location(root, output)
    raw = (output / 'provenance.json').read_bytes()
    require(isinstance(trusted_manifest_sha256, str) and len(trusted_manifest_sha256) == 64
            and _sha(raw) == trusted_manifest_sha256, 'untrusted materialized manifest digest')
    manifest = json.loads(raw)
    contract = _contract(root)
    require(manifest['schema_version'] == 1 and manifest['provenance_kind'] == PROVENANCE_KIND,
            'fresh provenance schema drift')
    for key in ('model_id', 'revision', 'framework_revision', 'layer_id'):
        require(manifest[key] == contract[key], 'materialized model identity drift')
    require((manifest['policy'], manifest['head_dim'], manifest['epsilon_word']) ==
            (oracle.POLICY, oracle.HEAD_DIM, oracle.EPSILON), 'materialized arithmetic contract drift')
    require(manifest['contract_sha256'] == CONTRACT_SHA256 and manifest['phases'] == list(PHASES),
            'materialized producer contract drift')
    require(manifest['source_sha256'] == _source_hashes(root, contract), 'materializer source binding drift')
    require(manifest['weights_sha256'] == dict(zip(WEIGHTS, oracle.WEIGHT_SHA256)), 'materialized weight pin drift')
    require(manifest['official_executions'] == 2 and manifest['heads_total'] == 5120
            and manifest['historical_byte_identity_claimed'] is False
            and manifest['unique_input_count_claimed'] is False
            and manifest['arithmetic_recomputed_during_extraction'] is False,
            'materialized evidence scope drift')
    require(set(manifest['corpora']) == set(VARIANTS), 'CPU corpus inventory drift')
    corpora = {}
    for variant, (requested, actual) in VARIANTS.items():
        origin = manifest['corpora'][variant]
        require(origin['requested_aten_cpu_capability'] == requested and origin['actual_torch_cpu_capability'] == actual,
                'corpus CPU dispatch identity drift')
        native_dir, prefix_dir = output / variant / 'native', output / variant / 'prefix'
        for path, record in ((native_dir / 'result.json', origin['fresh_audit_report']),
                             (native_dir / 'all_bf16_producers.npz', origin['fresh_audit_arrays']),
                             (prefix_dir / 'result.json', origin['fresh_prefix_report']),
                             (prefix_dir / 'prefix_activations_and_states.npz', origin['fresh_prefix_arrays']),
                             (output / (variant + '.npz'), origin['bundle'])):
            require(path.resolve().is_relative_to(output), 'materialized file path escape')
            _verify_file(path, record)
        report, prefix = _read_json(native_dir / 'result.json'), _read_json(prefix_dir / 'result.json')
        _validate_report(report, contract, variant)
        _validate_prefix(prefix, report, contract, manifest['payload_manifests'])
        require(report['upstream_report_sha256'] == origin['fresh_prefix_report']['sha256']
                and report['arrays'] == origin['fresh_audit_arrays']
                and prefix['arrays'] == origin['fresh_prefix_arrays'], 'fresh report/array binding drift')
        require(origin['environment'] == report['environment'] and origin['native_audit_status'] == report['status']
                and origin['native_audit_gate_pass'] is report['gate_pass']
                and origin['native_failed_comparisons'] == len(report['failed_producers']), 'native audit evidence drift')
        require((origin['heads'], origin['q_heads'], origin['k_heads']) == (2560, 2048, 512), 'corpus head count drift')
        with np.load(output / (variant + '.npz'), allow_pickle=False) as bundle:
            require(len(bundle.files) == len(set(bundle.files)), 'duplicate corpus array names')
            data = {name: bundle[name] for name in bundle.files}
        oracle._validate_arrays(data, origin)
        weights = {name: (data['weight_bf16_u32'][i] >> 16).astype('<u2').tobytes()
                   for i, name in enumerate(WEIGHTS)}
        with np.load(native_dir / 'all_bf16_producers.npz', allow_pickle=False) as producers:
            extracted = _extract(producers, weights)
        require(all(np.array_equal(data[name], extracted[name]) for name in data), 'native extraction binding drift')
        for array in data.values():
            array.flags.writeable = False
        corpora[variant] = (data, {**origin, 'model_id': manifest['model_id'], 'revision': manifest['revision'],
            'framework_revision': manifest['framework_revision'], 'layer_id': 3, 'policy': oracle.POLICY,
            'provenance_kind': PROVENANCE_KIND, 'provenance_sha256': trusted_manifest_sha256,
            'historical_byte_identity_claimed': False, 'unique_input_count_claimed': False})
    for field, array in (('cross_variant_input_arrays_identical', 'input_bf16_u32'),
                         ('cross_variant_native_arrays_identical', 'native_bf16_u32')):
        require(manifest[field] is bool(np.array_equal(corpora['baseline'][0][array], corpora['avx2'][0][array])),
                'cross-variant identity disclosure drift')
    return corpora
