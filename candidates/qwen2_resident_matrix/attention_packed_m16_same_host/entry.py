"""Runnable full M16 child API; no execute CLI and no authority from JSON alone.

The external supervisor owns process-group creation, absolute deadline signals,
fresh Git worktree, same-job consumer qualification, observed exit, cleanup and
parent receipts. It invokes run() once in a clean isolated child after approval.
"""
from pathlib import Path
import time
from . import admission as A, contract as C


def configure_backend():
    """One-time original thread/determinism policy in the clean consumer child."""
    import torch
    torch.set_num_threads(4)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    C.need(torch.get_num_threads() == 4 and torch.get_num_interop_threads() == 1 and
           torch.are_deterministic_algorithms_enabled(), 'original backend settings required')


def run(workspace, *, manifest, manifest_sha256, run_context):
    sources = C.authorize_run(run_context)
    workspace = Path(workspace).absolute()
    C.need('..' not in workspace.parts and not workspace.exists() and not workspace.is_symlink(),
           'new single-attempt full-M16 output required')
    C.safe(workspace.parent, directory=True)
    value = A.read_manifest(manifest, manifest_sha256)
    C.need(value['producer_receipt']['sha256'] == run_context['producer_receipt_sha256'],
           'external parent producer qualification differs')
    producer = C.read_json(value['producer_manifest']['path'], value['producer_manifest']['sha256'])
    C.need(producer['attempt_nonce'] == run_context['attempt_nonce'], 'external attempt nonce differs')
    A.verify(manifest, manifest_sha256, rows=16, enable_raw_kv=True)
    workspace.mkdir(mode=0o700)
    from ..dense_block_reduce import check_public_numeric as original
    snapshot_path, snapshot = original.prepare(workspace/'snapshot', value['library']['receipt']['path'],
        None, None, rows=16, enable_raw_kv=True, fresh_profile=True, fresh_manifest=str(manifest),
        fresh_manifest_sha256=manifest_sha256, enable_packed=True)
    snapshot_sha256 = C.sha(snapshot_path.read_bytes())
    C.need(time.monotonic()+C.NUMERIC_SECONDS <= run_context['work_deadline'],
           'full numerical budget unavailable after admission')
    result = original.run(workspace/'actual', snapshot_path, snapshot_sha256,
        wall_budget=C.NUMERIC_SECONDS, enable_raw_kv=True, fresh_profile=True, enable_packed=True,
        run_context=run_context)
    from . import terminal_validator
    summary = workspace/'actual/summary.json'
    raw = summary.read_bytes()
    C.need(C.encoded(result) == C.encoded(C.read_json(summary, C.sha(raw), limit=4*1024*1024)),
           'returned/disk full-M16 result differs')
    validation = terminal_validator.validate_terminal(summary, C.sha(raw), sources,
                                                      snapshot_path, snapshot_sha256)
    C.need(C.snapshot() == sources and C.sha(snapshot_path.read_bytes()) == snapshot_sha256,
           'postflight source/snapshot drift')
    A.verify(manifest, manifest_sha256, rows=16, enable_raw_kv=True)
    C.need(time.monotonic() < run_context['work_deadline'], 'full-M16 postflight missed deadline')
    output = dict(schema=1, profile=C.PROFILE, status='VALIDATED_FRESH_M16_CHILD_RESULT',
        attempt_nonce=run_context['attempt_nonce'], producer_receipt_sha256=run_context['producer_receipt_sha256'],
        source_manifest_sha256=C.sha(C.encoded(sources)), summary_sha256=C.sha(raw),
        snapshot_sha256=snapshot_sha256, validation=validation,
        parent_must_authenticate_exit_and_cleanup=True, full_29_node_acceptance=False,
        rtl_execution=False, hardware_recipe_acceptance=False, old_pass_inherited=False)
    with (workspace/'CHILD_RESULT.json').open('xb') as stream:
        stream.write(C.encoded(output))
    return output
