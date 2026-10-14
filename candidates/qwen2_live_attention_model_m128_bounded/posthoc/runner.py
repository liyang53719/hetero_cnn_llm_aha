#!/usr/bin/env python3
"""Append a comparison receipt for sealed v2 bytes; never resume/reexecute DUT."""
import argparse
import json
from pathlib import Path
import resource
import signal
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_live_attention_model_m128_bounded.posthoc import validation as v
from candidates.qwen2_live_attention_model_m128_bounded.posthoc.audit import ImportGuard, ReadOnlyGate


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def identity(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=v.sha(path))


def verify_records(records):
    actual = {name: identity(spec['path']) for name, spec in records.items()}
    for name, spec in records.items():
        v.require(all(actual[name][key] == spec[key] for key in ('bytes', 'sha256')), 'identity drift: ' + name)
    return actual


def verify_inventory(run, review):
    expected = review['all_original_run_files']
    v.require({str(p.relative_to(run)) for p in run.rglob('*') if p.is_file()} == set(expected), 'original run inventory changed')
    for name, spec in expected.items():
        got = identity(run / name)
        v.require(got['bytes'] == spec['bytes'] and got['sha256'] == spec['sha256'], 'original run file drift: ' + name)
    return expected


def verify_input_identity(original, review):
    result = {}
    for name, expected in (('inputs', original['input_identity_before']),
                           ('raw_inputs', original['input_validation']['raw_tensors'])):
        got = verify_records(review[name])
        v.require(set(got) == set(expected), 'input identity role set drift')
        for role, spec in expected.items():
            v.require(all(got[role][k] == spec[k] for k in ('bytes', 'sha256')), 'original input/raw bytes drift: ' + role)
        result[name] = got
    result['evidence'] = verify_records(review['evidence'])
    v.require({n: s['sha256'] for n, s in result['evidence'].items()} == original['evidence_sha256_before'], 'original evidence drift')
    return result


def run(out, reviewed_manifest):
    started = time.monotonic(); closure = v.sources(); p = v.pins()
    v.require(v.manifest(closure) == reviewed_manifest, 'new independently reviewed posthoc manifest required')
    out = Path(out).absolute()
    v.require(out.parent == v.OUTPUT_ROOT and out.resolve() == out and not out.exists(), 'fresh isolated posthoc output required')
    original, parent = v.load_receipts()
    review_path = v.ROOT / p['independent_seal_review']['path']
    v.require(v.sha(review_path) == p['independent_seal_review']['sha256'], 'independent seal review drift')
    review = json.loads(review_path.read_text())
    v.require(review['source_manifest_sha256'] == p['execution_source_manifest_sha256'] and
              review['original_result']['sha256'] == p['result_sha256'] and not review['posthoc_numeric_comparison_executed'],
              'seal review identity')
    # Import only comparison functions and NumPy. No runtime(), Torch, owner,
    # ScalarService, Matrix service, observer execution, or DUT C library is created.
    sys.addaudithook(ImportGuard(out).audit)
    verify_records(original['tools_before'])
    import numpy as np
    from scripts import qwen2_layer0_model_gate as native
    from candidates.qwen2_live_attention_model_m128 import gates as original_gates, compare
    v.require(not any(n == 'torch' or n.startswith('torch.') for n in sys.modules), 'Torch already loaded')
    out.mkdir(); gate = ReadOnlyGate(out, original, review); sys.addaudithook(gate.audit)
    report = dict(schema=1, status='STARTED_POSTHOC_ONLY', original_execution_status=original['status'],
        original_execution_result_sha256=p['result_sha256'], original_acceptance_sealed=False,
        original_execution_manifest=p['execution_source_manifest_sha256'], posthoc_source_manifest=v.manifest(closure),
        input_payloads_read_for_identity=True, model_inputs_used_as_operands=False,
        dut_reexecuted=False, torch_imported=False, dut_native_library_loaded=False,
        comparison_numpy_runtime_imported=True, compile_executed=False,
        fullblock_pass=False, whole_block_terminal=False, att_published=False, pc12_completion_held=True,
        comparison_completed=False, posthoc_numeric_pass=False, finalfence=False,
        hash_timing='All final/current identities below are appended posthoc checks, not original in-run final hashes')
    stage = 'identity_and_seal_verification'
    def timeout(signum, frame): raise TimeoutError('posthoc comparison wall budget exceeded')
    previous = {s: signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM)}
    signal.signal(signal.SIGALRM, timeout)
    signal.signal(signal.SIGTERM, timeout)
    signal.setitimer(signal.ITIMER_REAL, max(.001, 60 - (time.monotonic() - started)))
    try:
        save(out / 'RESULT.json', report)
        run_path = v.ROOT / p['run_path']; data = v.ROOT / p['data_path']; reference = v.ROOT / p['reference_path']
        report['original_inventory_before'] = verify_inventory(run_path, review)
        report['sealed_artifacts'] = v.verify_artifacts(run_path, original)
        report['tools_before_posthoc'] = verify_records(original['tools_before'])
        v.require(Path(sys.executable).resolve() == Path(original['tools_before']['python']['path']) and
                  Path(np.__file__).resolve() == Path(original['tools_before']['numpy_init']['path']) and
                  Path(np._core._multiarray_umath.__file__).resolve() == Path(original['tools_before']['numpy_multiarray']['path']),
                  'current comparison runtime differs from v2 runtime')
        report['native_artifacts_before_posthoc'] = verify_records(original['native_artifact_reuse']['artifact_identity_before'])
        report['inputs_before_posthoc'] = verify_input_identity(original, review)
        original_gates.validate_reference_metadata(data, reference)
        capture = v.FrozenCapture(run_path, original)
        v.require(np.frombuffer(capture._bytes('pv_bf16'), '<u4').reshape(12, 128, 128).transpose(1, 0, 2).copy().tobytes() ==
                  (run_path / 'att.f32le').read_bytes(), 'sealed PV to Attention layout drift')
        v.require(not gate.reference_reads, 'oracle read before all seal/identity checks')
        report['seal_and_identity_verified_before_oracle'] = True
        stage = 'original_postseal_official_comparison'; gate.opened = True
        reference_metadata, payloads = original_gates.validate_references(data, reference)
        context = dict(original, numerical_policy=native.load_policy(v.ROOT))
        comparisons = compare.official(run_path, context, capture, reference_metadata, payloads, native, np)
        report['numerical_policy'] = context['numerical_policy']; report['comparisons'] = comparisons
        stage = 'post_comparison_identity_recheck'
        v.require(v.sources() == closure, 'posthoc/source closure drift')
        v.load_receipts()
        report['original_inventory_after'] = verify_inventory(run_path, review)
        report['tools_after_posthoc'] = verify_records(original['tools_before'])
        report['native_artifacts_after_posthoc'] = verify_records(original['native_artifact_reuse']['artifact_identity_before'])
        report['inputs_after_posthoc'] = verify_input_identity(original, review)
        v.require(report['inputs_before_posthoc'] == report['inputs_after_posthoc'], 'posthoc input/evidence drift')
        original_gates.validate_reference_metadata(data, reference)
        v.require(all(v.sha(reference / (n + '.f32le')) == reference_metadata['outputs'][n]['sha256'] for n in payloads), 'oracle payload drift')
        v.require(v.sha(review_path) == p['independent_seal_review']['sha256'], 'seal review changed')
        report.update(status='POSTHOC_OFFICIAL_COMPARISON_PASS_PC12_HELD' if comparisons['official_observed_node_pass'] else
                      'POSTHOC_OFFICIAL_COMPARISON_FAIL_PC12_HELD', comparison_completed=True,
                      posthoc_numeric_pass=comparisons['official_observed_node_pass'], original_failed_receipt_unchanged=True,
                      reference_reads=gate.reference_reads, runtime_identity_reads=gate.runtime_reads,
                      seconds=time.monotonic() - started, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save(out / 'RESULT.json', report)
        v.require(time.monotonic() - started < 60, 'posthoc final receipt exceeded inner wall deadline')
        return report
    except BaseException as error:
        report.update(status='FAILED_POSTHOC_ONLY', stage=stage, error=repr(error), traceback=traceback.format_exc(),
                      comparison_completed=False, posthoc_numeric_pass=False, reference_reads=gate.reference_reads,
                      runtime_identity_reads=gate.runtime_reads, seconds=time.monotonic() - started)
        save(out / 'RESULT.json', report)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for signum, handler in previous.items(): signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual-comparison', action='store_true'); parser.add_argument('--out')
    parser.add_argument('--reviewed-source-manifest')
    a = parser.parse_args(argv)
    if not a.actual_comparison:
        v.require(a.out is None and a.reviewed_source_manifest is None, 'comparison arguments require explicit flag')
        print(json.dumps(dict(status='NOT_EXECUTED', comparison=False, dut_execution=False,
                              source_manifest_sha256=v.manifest(v.sources())))); return 0
    v.require(a.out is not None and a.reviewed_source_manifest is not None, 'fresh out and independent review required')
    result = run(a.out, a.reviewed_source_manifest)
    print(json.dumps({k: result[k] for k in ('status', 'posthoc_numeric_pass', 'seconds')}))
    return 0 if result['posthoc_numeric_pass'] else 1


if __name__ == '__main__': raise SystemExit(main())
