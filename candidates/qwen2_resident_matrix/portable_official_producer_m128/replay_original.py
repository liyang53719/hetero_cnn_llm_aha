"""Exact geometry-only adaptation of the original native array validator.

Executed with the exact original generated runner globals by verify.replay_arrays.
All six row/phase geometry literals become128. The BF16 storage shift stays16.
No numerical library is imported or numerical work executed on import.
"""
from __future__ import annotations

def validate_m128_gate(path: Path, identity: dict, payload_sha: str, policy: dict,
                        config: dict, embeddings: np.ndarray, carried: bool, threads: int) -> None:
    """Revalidate full M128 evidence, not a self-asserted PASS string."""
    try:
        report = json.loads(path.read_text())
        required = {
            'schema_version': 1, 'tokens': 128, 'carried': carried, 'layer': 0,
            'status': 'PASS_BF16_STAGE_BUDGET', 'model_id': 'Qwen/Qwen2-1.5B-Instruct',
            'identity': identity, 'payload_manifest_sha256': payload_sha,
            'policy': policy, 'torch_threads': threads,
            'blas_environment': {key: os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS')},
            'official_framework_forward': True, 'rtl_execution': False,
        }
        for key, expected in required.items():
            if key not in report or type(report[key]) is not type(expected) or report[key] != expected:
                raise ValueError('M128 binding mismatch: ' + key)
        if set(report['modes']) != {'bf16', 'fp32'}:
            raise ValueError('M128 mode inventory mismatch')
        evidence_root = path.resolve().parent
        for mode in ('bf16', 'fp32'):
            phases = report['modes'][mode]['phases']
            if len(phases) != (2 if carried else 1):
                raise ValueError('M128 phase inventory mismatch')
            previous = {'native': None, 'independent': None}
            for phase, receipt in enumerate(phases):
                ids = list(range(phase * 128, (phase + 1) * 128))
                expected_status = 'PASS_BF16_STAGE_BUDGET' if mode == 'bf16' else 'DIAGNOSTIC_FP32'
                if (receipt['phase'] != phase or receipt['past_tokens'] != phase * 128 or
                    receipt['token_ids'] != ids or receipt['position_ids'] != ids or
                    receipt['failed_stages'] != [] or receipt['status'] != expected_status or
                    receipt['all_semantics_exact'] is not True or not all(v is True for v in receipt['semantics'].values())):
                    raise ValueError('M128 phase binding mismatch')
                if set(receipt['stages']) != REQUIRED_STAGES:
                    raise ValueError('M128 stage inventory mismatch')
                loaded = {'native': {}, 'independent': {}}
                shapes = expected_shapes(config, 128, phase * 128)
                for name in sorted(REQUIRED_STAGES):
                    entry = receipt['stages'][name]
                    if entry['shape'] != shapes[name]:
                        raise ValueError('M128 tensor shape mismatch: ' + name)
                    for kind in ('native', 'independent'):
                        relative = f'{mode}/phase_{phase}/{kind}_{name}.f32le'
                        tensor_path = evidence_root / relative
                        if (entry[kind + '_file'] != relative or tensor_path.is_symlink() or
                            not tensor_path.resolve().is_relative_to(evidence_root)):
                            raise ValueError('M128 tensor path mismatch')
                        if tensor_path.stat().st_size != math.prod(shapes[name]) * 4 or sha(tensor_path) != entry[kind + '_file_sha256']:
                            raise ValueError('M128 tensor bytes/hash mismatch: ' + name)
                        array = np.fromfile(tensor_path, dtype='<f4')
                        if name in EXPORT_TOKEN_MAJOR:
                            b, h, m, d = shapes[name]
                            exported_shape = [b, m, h * d]
                            array = array.reshape(b, m, h, d).transpose(0, 2, 1, 3).copy()
                        else:
                            exported_shape = shapes[name]
                            array = array.reshape(shapes[name])
                        if entry[kind + '_export_shape'] != exported_shape:
                            raise ValueError('M128 export shape mismatch')
                        loaded[kind][name] = array
                    metrics = compare(loaded['native'][name], loaded['independent'][name])
                    for key, value in metrics.items():
                        if entry.get(key) != value:
                            raise ValueError('M128 recomputed metric mismatch: ' + name + ':' + key)
                    verdict = stage_verdict(name, metrics, mode, policy)
                    if verdict['passed'] is False or any(entry.get(key) != value for key, value in verdict.items()):
                        raise ValueError('M128 recomputed stage failure: ' + name)
                    array = loaded['native'][name]
                    is_bf16 = mode == 'bf16' and name != 'softmax_fp32'
                    if is_bf16 and np.any(array.view(np.uint32) & 0xffff):
                        raise ValueError('M128 BF16 storage mismatch')
                    expected_dtype = 'torch.bfloat16' if is_bf16 else 'torch.float32'
                    stored = (array.view(np.uint32) >> 16).astype('<u2') if is_bf16 else array
                    if entry['actual_storage_dtype'] != expected_dtype or digest_array(stored) != entry['actual_storage_sha256']:
                        raise ValueError('M128 original storage digest mismatch')
                for kind in ('native', 'independent'):
                    if not np.array_equal(loaded[kind]['x'].view(np.uint32), embeddings[ids][None].view(np.uint32)):
                        raise ValueError('M128 input does not match current checkpoint embeddings')
                    if not all(audit_semantics(loaded[kind], previous[kind], config, mode).values()):
                        raise ValueError('M128 recomputed semantic failure: ' + kind)
                    previous[kind] = loaded[kind]
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        raise ValueError('incomplete or invalid M128 evidence: ' + str(error)) from error
