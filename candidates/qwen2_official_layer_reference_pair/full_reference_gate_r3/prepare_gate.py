"""Metadata-only proposal preparation. Never import ML or read tensor payloads."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import GATE_FILES, LIMITS, file_id, need, read_checked, write_new, loopback_probe_policy


def prepare(base_path, base_sha, config_path, helper_provenance):
    here = Path(__file__).resolve().parent
    root = here.parent
    base = read_checked(base_path, base_sha)
    need(base['action'] == 'single_official_normal_import_only', 'wrong baseline closure')
    need(base['execution_started'] is False, 'baseline config must predate all execution')
    previous = Path(base['gate_directory'])
    # Consume only the frozen closure, never any prior run, approval, or claim.
    for name in ('gate_common.py', 'prepare_gate.py', 'worker.py', 'run_gate.py'):
        old = previous / name
        need(file_id(old) == base['file_manifest'][str(old)], 'frozen baseline source drift')
        del base['file_manifest'][str(old)]
    audit_path = root / 'input_audit/INPUT_AUDIT.json'
    source_audit_path = root / 'source_audit/SOURCE_AUDIT.json'
    capture_dir = root / 'capture_pair_r3'
    pins_path = capture_dir / 'pins.json'
    pins = json.loads(pins_path.read_text())
    audit = json.loads(audit_path.read_text())
    source = json.loads(source_audit_path.read_text())
    need(len(audit['raw13']) == 13, 'exact raw13 metadata required')
    raw_roots = {str(Path(x['path']).parent) for x in audit['raw13']}
    need(len(raw_roots) == 1, 'single original raw13 root required')
    raw_root = raw_roots.pop()
    raw_manifest = {}
    for expected, current in zip(pins['raw13'], audit['raw13']):
        need({k: current[k] for k in expected} == expected, 'capture and input audit pins differ')
        path = Path(current['path'])
        need(str(path) == str(Path(raw_root) / (expected['local_name'] + '.bin')), 'raw13 path substitution')
        # stat only. Raw tensor bytes are neither read nor rehashed here.
        need(path.stat().st_size == expected['bytes'], 'raw13 stat size changed')
        raw_manifest[str(path)] = {k: expected[k] for k in ('bytes', 'sha256')}
    config_path = Path(config_path).resolve(strict=True)
    config_id = file_id(config_path)  # Plain JSON metadata, not tensor payload.
    need(config_id['sha256'] == pins['config_sha256'], 'original source-B config identity mismatch')
    config_data = json.loads(config_path.read_text())
    need(config_data['max_position_embeddings'] == 32768 and config_data['rope_theta'] == 1e6
         and config_data['use_sliding_window'] is False, 'original config profile required')
    source_manifest_path = capture_dir / 'SOURCE_MANIFEST.json'
    source_manifest = json.loads(source_manifest_path.read_text())
    need(source_manifest['status'] == 'PAIR_SOURCE_PREPARED_NOT_EXECUTED', 'paired capture source not frozen')
    need(source_manifest['predecessor_capture_sha256'] == '4fe8428c8ae2a1d96a900b0fc26e9a34cb98663f037c029595a5e51d4fc9bfc4', 'wrong frozen capture predecessor')
    expected_capture = source_manifest['files']
    need(set(expected_capture) == {'capture_pair.py', 'pins.json'}, 'exact paired source and original pins required')
    for name, identity in expected_capture.items():
        need(file_id(capture_dir / name) == identity, 'frozen capture drift')
    history = source['upstream']['runtime_requirements']
    profile = {'cpu_capability': history['capability'], 'torch_build_sha256': history['torch_build_sha256'],
               'torch_git_version': history['torch_commit'], 'intraop_threads': 4, 'interop_threads': 1,
               'deterministic_algorithms': True, 'python_major_minor': [3, 12]}
    meta = [audit_path, source_audit_path, pins_path, capture_dir / 'capture_pair.py', source_manifest_path, Path(base_path),
            config_path, Path(helper_provenance)]
    revision = here / 'REVISION_PROVENANCE.json'
    need(revision.is_file(), 'explicit predecessor and scope-change provenance required')
    meta.append(revision)
    helper = json.loads(Path(helper_provenance).read_text())
    need(helper['status'] == 'EXACT_SOURCE_COPY_FROM_FROZEN_R2', 'network helper not frozen')
    for path, identity in helper['upstream_files'].items():
        need(file_id(path) == identity, 'r2 frozen helper provenance drift')
        meta.append(Path(path))
    for path in meta:
        base['file_manifest'][str(path.resolve())] = file_id(path)
    for name in GATE_FILES:
        base['file_manifest'][str(here / name)] = file_id(here / name)
    base['file_manifest'].update(raw_manifest)
    base.update({
        'schema': 1, 'status': 'PREPARED_NOT_EXECUTED_NOT_APPROVED',
        'action': 'single_official_m16_full_layer_reference_pair',
        'gate_directory': str(here), 'capture_directory': str(capture_dir),
        'capture_sources': {str(capture_dir / n): v for n, v in expected_capture.items()},
        'input_config': {'path': str(config_path), **config_id},
        'raw_root': raw_root, 'raw_input_manifest': raw_manifest,
        'capture_profile': source_manifest['capture_profile'],
        'raw13': audit['raw13'], 'limits': LIMITS, 'reviewed_runtime_profile': profile,
        'loopback_probe': loopback_probe_policy(base['target']),
        'network_helper_provenance': helper,
        'output_contract': pins['fields'], 'comparison_gates': pins['comparison_gates'],
        'predecessor_config': {'path': str(Path(base_path).resolve()), **file_id(base_path)},
        'preparation_scope': 'Metadata-only: reused runtime closure is NOT revalidated; raw13 historical expected hashes are NOT fresh evidence. Future launcher must rehash source/runtime/input pre/post.',
        'scope': {'normal_import_only': False, 'instantiate_config': True, 'instantiate_layer': True,
                  'model_forward': 'two complete Qwen2DecoderLayer.forward calls on one identical instance: baseline then observed',
                  'layer_instances': 1, 'forward_calls': 2, 'same_input_objects': True,
                  'baseline_y_prob_native_bytes_exact': True, 'input_parameter_buffer_state_unchanged': True,
                  'all29_baseline_intermediate_noninterference_claimed': False,
                  'full_causal_lm_or_model_forward': False, 'raw13_only': True,
                  'geometry': 'cold M16', 'max_position_embeddings': 32768,
                  'diagnostic_rotary256': False, 'matrix_or_dut': False, 'rtl': False, 'M128': False,
                  'provider_inputs': False, 'legacy_output_inputs': False, 'download': False,
                  'network': False, 'single_exact_dependency_loopback_probe': True,
                  'full_live_code_identity_claimed': False, 'old_reference_pass_inherited': False},
        'execution_started': False,
        'expected_output_hashes': None,
        'output_hash_policy': 'A fresh oracle has no prior expected output hashes. Newly observed hashes bind results only, never prove correctness against a prior oracle.'})
    need(base['loopback_probe']['function']['file_sha256'] == base['file_manifest'][base['loopback_probe']['function']['filename']]['sha256'], 'loopback source not in closure')
    return base


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-config', required=True)
    p.add_argument('--base-config-sha256', required=True)
    p.add_argument('--original-config', required=True)
    p.add_argument('--helper-provenance', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    config = prepare(a.base_config, a.base_config_sha256, a.original_config, a.helper_provenance)
    identity = write_new(a.output, config)
    print(json.dumps({'status': config['status'], 'identity': identity, 'payload_read': False,
                      'model_import_executed': False, 'reference_executed': False}, sort_keys=True))

if __name__ == '__main__':
    main()
