#!/usr/bin/env python3
"""Fresh official-BF16 public21 execution, followed by pinned native comparison.

This is the existing physical transaction software model, not Chisel or RTL.
Saved v2 arithmetic/native tensors are comparison-only and cannot feed owners.
Every actual tensor is sealed before their access. Historical FAILs and all
original operator/block limits remain intact; missing future scores stay absent.
"""
import argparse
import ctypes as C
import importlib
import json
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import check_fullgraph_numeric as old
from . import execution as policy
from . import reference_layout

base = old.base
require, sha, encoded, file_sha = base.require, base.sha, base.encoded, base.file_sha
IMPORTED_SOURCE_SHA256 = file_sha(Path(__file__))
PREFIX = 'candidates/qwen2_resident_matrix/official_bf16/'
NEW_SOURCES = tuple(PREFIX + p for p in ('owners.py', 'dense_silu.py', 'silu_recipe.cpp',
                    'execution.py', 'observation.py', 'check_numeric.py', 'reference_layout.py', 'observation_monitoring.py')) + (
    'scripts/observe_qwen2_attention_model.py', 'scripts/qwen2_layer0_model_gate.py',
    'spec/numerical_contract.md')
REFERENCE_PINS = {
    16: ('68299c6687734408bf4ac03eae5efe149ed4042113f919eff4c379e78a8558a2',
         '5f2a709fc932ba5cbf436847010c4154d4e7c68ecc1d90f2c82db3b6785ed3f9'),
    128: ('99d551a40ca38af3d196015cf2dbb6e4ea80bdfec1f33f7c0d5cbb58a9131ac0',
          'ae99b4ce2aceebcbbd9c83b1cbf2ab64605314ae60dfbf5423258db6469d2ab9'),
}
TABLE_SHA = '5edc3314874c1cf4a7dc9cb54f2c824b18272048f70abcf9021f021308589045'
# These two historical Python files differ from the current files. Their
# exact old bytes were not recovered; do not reduce the difference to a
# claimed report-order-only change. M16 archived Q/K also uses token-major
# reference exports, verified separately against original native metadata.
# Reuse additionally requires current generation to reproduce the exact saved
# numerical C++ bytes. No historical Python test PASS is inherited.
HISTORICAL_PYTHON_VERSIONS = {
    'scripts/qwen2_rms_rope_prefill_candidate.py': (
        '818325c08e80e4b1167334ebe24a774238606614ca87eb3d5c83b8216e90bca4',
        '41aea07ba09fc5c11f6aafbe14e83ebdba6e843a3cf47080a954a1032b6461e9'),
    'tests/test_qwen2_rms_rope_prefill_candidate.py': (
        'ad6221f564df8591fd60952898e6d53be2638acb148941281ebb1ca403f33893',
        '02c2c8cedc98b317ece7593fbd968d89424f65d7352deacb5e42a28ee5fed2ce'),
}


def source_hashes():
    result = old.source_hashes()
    result.update({p: file_sha(ROOT / p) for p in NEW_SOURCES})
    return result


def runtime():
    require(file_sha(Path(__file__)) == IMPORTED_SOURCE_SHA256 and
            file_sha(Path(policy.__file__)) == policy.IMPORTED_SOURCE_SHA256,
            'loaded official runner/dispatch source identity differs from disk')
    modules = old.runtime()
    before = source_hashes()
    with base.frozen_exec(before):
        dense = importlib.import_module('candidates.qwen2_resident_matrix.official_bf16.dense_silu')
        observer = importlib.import_module('candidates.qwen2_resident_matrix.official_bf16.observation_monitoring')
        native = importlib.import_module('scripts.qwen2_layer0_model_gate')
    require(before == source_hashes(), 'official execution source changed during import')
    return modules, dense, observer, native


def reference_spec(rows):
    require(rows in REFERENCE_PINS, 'official integration M16/M128 only')
    directory = ROOT / ('work/qwen2_rms_rope_prefill_v2_m%d_20261011' % rows)
    top_path, cold_path = directory / 'RESULT.json', directory / 'cold/RESULT.json'
    require((file_sha(top_path), file_sha(cold_path)) == REFERENCE_PINS[rows],
            'reviewed arithmetic/native archive metadata changed')
    top, cold = json.loads(top_path.read_text()), json.loads(cold_path.read_text())
    require(top['tokens'] == cold['tokens'] == rows and cold['past_tokens'] == 0 and
            top['phase_result_sha256']['cold'] == REFERENCE_PINS[rows][1] and
            top['payload_manifest_sha256'] == base.PINS[base.PAYLOAD] and
            cold['inputs']['token_ids'] == cold['inputs']['position_ids'] == list(range(rows)) and
            cold['inputs']['intermediate_preloads'] == 0,
            'reference workload/raw-payload identity differs')
    python_versions = {}
    for relative, digest in top['source_files'].items():
        current = file_sha(ROOT / relative)
        if current != digest:
            require(HISTORICAL_PYTHON_VERSIONS.get(relative) == (digest,current),
                    'reviewed oracle source drift: ' + relative)
            python_versions[relative] = dict(historical_sha256=digest,current_sha256=current,
                historical_python_bytes_recovered=False, historical_test_pass_inherited=False)
    for filename, key in (('candidate.cpp', 'cpp_sha256'), ('candidate', 'binary_sha256'),
                          ('block_layout.h', 'header_sha256')):
        require(file_sha(directory / 'build' / filename) == top['build'][key],
                'reviewed oracle build identity drift')
    from scripts import qwen2_rms_rope_prefill_candidate as generator
    regenerated, _ = generator.candidate_source()
    require(regenerated.encode() == (directory/'build/candidate.cpp').read_bytes() and
            sha(regenerated.encode()) == top['build']['cpp_sha256'],
            'current guarded generator does not reproduce archived numerical C++')
    require(file_sha(directory / 'rope_full.f32le') == TABLE_SHA and
            cold['inputs']['rope_table_sha256'] == TABLE_SHA,
            'reviewed readonly FP32 trig table drift')
    return dict(directory=str(directory), top_sha256=REFERENCE_PINS[rows][0],
        cold_sha256=REFERENCE_PINS[rows][1], inputs=cold['inputs'], build=top['build'],
        source_files=top['source_files'], threshold_policy=top['threshold_policy'],
        official_reference_identity=top['official_reference_identity'],
        artifacts=cold['artifacts'], tensors=cold['tensors'],
        historical_python_version_differences=python_versions,
        archived_numerical_cpp_reproduced_exactly=True,
        prior_failures={k:v['failed_stages'] for k,v in cold['evaluation']['methods'].items()},
        oracle_execution_reused=True, native_execution_reused=True, old_pass_inherited=False)


def load_inputs(spec, rows, reference):
    import numpy as np
    inputs = old.load_inputs(spec, rows)
    table = Path(reference['directory']) / 'rope_full.f32le'
    require(file_sha(table) == TABLE_SHA, 'readonly table changed')
    raw = np.frombuffer(table.read_bytes(), dtype='<f4')
    require(raw.size == 192 + 5 * 16384, 'reviewed table layout')
    tables = np.zeros((2, 1024, 64), dtype='<f4')
    for i, source in enumerate((1, 2)):
        tables[i, :rows] = raw[192 + source * 16384:192 + (source + 1) * 16384].reshape(256, 64)[:rows]
    inputs['rope'] = tables.tobytes()
    require(sha(inputs['x']) == reference['inputs']['input_x_sha256'], 'actual/reference raw x differs')
    return inputs


def prepare(out, compile_receipt, rows=16, epoch=7):
    out = Path(out).resolve()
    require(not out.exists(), 'fresh official snapshot required')
    modules, dense, _, native = runtime()
    helper, _, fixtures, *_ = modules
    sources, inputs_spec = source_hashes(), old.input_spec()[0]
    ref = reference_spec(rows)
    built = dense.verify_library(compile_receipt)
    fixture = fixtures.make_qwen2_21_fixture(rows, epoch)
    inputs = load_inputs(inputs_spec, rows, ref)
    require(set(inputs) == {n for n,a in fixture.allocations.items() if a.readonly} and
            all(len(v) == fixture.allocations[n].storage_bytes for n,v in inputs.items()),
            'official readonly provider does not match public typed allocations')
    require(native.load_policy(ROOT) == ref['threshold_policy'], 'original numerical thresholds changed')
    receipt = Path(compile_receipt).resolve()
    library = Path(built['library']).resolve()
    snapshot = dict(schema=1, status='PREPARED_OFFICIAL_PUBLIC21_NOT_EXECUTED',
        policy=policy.POLICY, rows=rows, epoch=epoch, source_sha256=sources,
        source_manifest_sha256=sha(encoded(sources)), input_spec=inputs_spec,
        loaded_inputs=base.identities(inputs), reference=ref,
        binaries=dict(compile_receipt=str(receipt), compile_sha256=file_sha(receipt),
                      library=str(library), library_sha256=file_sha(library)),
        metadata=helper.metadata_identity(fixture), host_tools=helper.host_tool_identity(),
        prelaunch_intermediate_payloads=[], old_pass_inherited=False)
    require(source_hashes() == sources, 'official source changed during preparation')
    out.mkdir(parents=True)
    for relative, digest in sources.items():
        raw = (ROOT / relative).read_bytes()
        require(sha(raw) == digest, 'source changed while snapshotting')
        target = out / 'frozen_sources' / relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    for name in ('command', 'descriptor'):
        table = getattr(fixture.config, name)
        (out / (name + '_table.bin')).write_bytes(fixture.memory.mappings[table.base])
    path = out / 'SNAPSHOT.json'; path.write_bytes(encoded(snapshot))
    return path, snapshot


def verify_snapshot(path, digest):
    path = Path(path).resolve()
    require(file_sha(path) == digest, 'official snapshot hash differs')
    s = json.loads(path.read_text())
    _, dense, _, _ = runtime()
    require(s['status'] == 'PREPARED_OFFICIAL_PUBLIC21_NOT_EXECUTED' and s['policy'] == policy.POLICY
            and source_hashes() == s['source_sha256'] and
            s['source_manifest_sha256'] == sha(encoded(s['source_sha256'])), 'official source/policy drift')
    for name, expected in s['source_sha256'].items():
        require(file_sha(path.parent / 'frozen_sources' / name) == expected, 'frozen source drift: ' + name)
    b = s['binaries']
    require(file_sha(b['compile_receipt']) == b['compile_sha256'] and
            dense.verify_library(b['compile_receipt'])['library'] == b['library'] and
            file_sha(b['library']) == b['library_sha256'], 'official arithmetic build drift')
    require(reference_spec(s['rows']) == s['reference'] and old.input_spec()[0] == s['input_spec'],
            'official/reference source or raw input provenance drift')
    return s


def prerequisite(path, digest, snapshot):
    require(path and digest and file_sha(path) == digest, 'M128 needs the exact new M16 integration receipt')
    r = json.loads(Path(path).read_text())
    postprocessed = r['status'] == 'PASS_RECOMPARISON_OF_SEALED_M16'
    if postprocessed:
        from . import recompare_m16
        require(r['postprocessor_sha256'] == file_sha(Path(recompare_m16.__file__)) and
                r['original_result_sha256'] == recompare_m16.ORIGINAL_RESULT_SHA and
                r['original_snapshot_sha256'] == recompare_m16.ORIGINAL_SNAPSHOT_SHA and
                r['arithmetic_and_physical_driver_sources_unchanged'] and
                r['functional_run_ast_unchanged_except_readonly_transport'] and
                not r['actual_execution_repeated'] and not r['reference_forward_repeated'],
                'M16 comparison-only correction provenance differs')
    require((r['status'] == 'PASS_BF16_DATAFLOW_NATIVE_GATE_REPORTED' or postprocessed) and r['rows'] == 16 and
            r['source_sha256'] == r['source_sha256_after'] == snapshot['source_sha256'] and
            r['binaries'] == snapshot['binaries'] and r['policy'] == policy.POLICY and
            r['input_spec'] == snapshot['input_spec'] and r['comparison']['fixed_arithmetic_pass'],
            'M16 implementation/input/terminal prerequisite differs')
    h = r['execution']['host']
    require(h['launch_result']['status'] is None and h['launch_result']['completed'] == 21 and
            h['launch_result']['jobs'] == h['accepted']['owner_result_fire'] == 17 and
            h['accepted']['result_fire'] == 1 and not h['reset_required'], 'M16 public terminal incomplete')
    return dict(path=str(Path(path).resolve()), sha256=digest,
                native_acceptance_inherited=False, readonly_instrumentation_revalidated=postprocessed,
                rationale='same arithmetic/physical-driver implementation and accepted dataflow; diagnostic-source changes explicit')


def _reference_bytes(ref, relative):
    entries = [e for e in ref['artifacts'] if e['path'] == relative]
    require(len(entries) == 1, 'reference file missing/duplicate in frozen inventory: ' + relative)
    entry = entries[0]
    raw = (Path(ref['directory']) / 'cold' / relative).read_bytes()
    require(len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], 'reference artifact drift: ' + relative)
    return raw


def compare(snapshot, actual, inputs, capture, silu, native):
    """Use sealed actual values, retaining absence masks on unexecuted nodes."""
    import numpy as np
    ref, rows = snapshot['reference'], snapshot['rows']
    fields, fixed, native_results = {}, {}, {}
    for name, width in old.STAGE_WIDTHS.items():
        value = np.frombuffer(actual[name].tobytes(), dtype='<f4').reshape(1, rows, width)
        fields[name] = value
        reference = _reference_bytes(ref, 'raw_stages/phase_%d_%s_recipe.f32le' %
                                     (list(old.STAGE_WIDTHS).index(name), name))
        expected = np.frombuffer(reference, dtype='<f4').reshape(value.shape)
        fixed[name] = native.compare(value, expected)
    fields['q'] = fields['q'].reshape(1, rows, 12, 128).transpose(0,2,1,3)
    fields['k'] = fields['k'].reshape(1, rows, 2, 128).transpose(0,2,1,3)
    kv = np.frombuffer(actual['kv'].tobytes(), dtype='<f4').reshape(2, rows, 2, 128)
    fields['cache_k'], fields['cache_v'] = (kv[i].transpose(1,0,2)[None] for i in range(2))
    fields['repeat_k'] = np.repeat(fields['cache_k'], 6, axis=1)
    fields['repeat_v'] = np.repeat(fields['cache_v'], 6, axis=1)
    fields['x'] = np.frombuffer(inputs['x'], dtype='<f4').reshape(1, rows, 1536)
    trig = np.frombuffer(inputs['rope'], dtype='<f4').reshape(2, 1024, 64)
    for i,name in enumerate(('cos', 'sin')):
        part = native.bf16(trig[i,:rows]); fields[name] = np.concatenate((part,part),axis=1)
    fields['silu'] = np.frombuffer(silu, dtype='<f4').reshape(1, rows, 8960)
    masks = {}
    for name, observation in (('scores','scores_bf16'), ('logits','scores_bf16'),
                              ('softmax_fp32','softmax_fp32'), ('prob','prob_bf16'), ('pv','pv_bf16')):
        f = capture.fields[observation]
        fields[name] = np.frombuffer(capture._bytes(observation), dtype='<f4').reshape((1,*f['shape']))
        masks[name] = np.frombuffer(bytes(f['observed']), dtype=np.uint8).reshape(fields[name].shape).astype(bool)
    # The implicit causal mask is protocol behavior, not an actual computed
    # tensor. Future score/logit/probability positions never gain observations.
    methods = ('official_self_cache', 'independent_self_cache')
    limits = native.load_policy(ROOT)
    for method in methods:
        results, failures = {}, []
        for name, value in fields.items():
            raw = _reference_bytes(ref, 'references/%s/%s.f32le' % (method,name))
            expected = reference_layout.read_native_reference(raw, rows=rows, method=method, name=name, shape=value.shape)
            mask = masks.get(name)
            a, b = (value[mask], expected[mask]) if mask is not None else (value, expected)
            metrics = native.compare(a, b)
            verdict = native.stage_verdict(name, metrics, 'bf16', limits)
            results[name] = dict(metrics=metrics, verdict=verdict, original_shape=list(value.shape),
                coverage='actual_causal_positions_only' if mask is not None and not bool(mask.all()) else 'complete',
                observed_elements=int(a.size), unobserved_elements=int(value.size-a.size))
            if verdict['passed'] is False: failures.append(name)
        native_results[method] = dict(stages=results, failed_stages=failures,
            numerical_status='FAIL' if failures else 'PASS_OBSERVED_ONLY')
    observed_fixed = {}
    for name in ('scores', 'logits', 'softmax_fp32', 'prob', 'pv', 'silu'):
        entries = [e for e in ref['tensors'] if e['name'] == name]
        require(len(entries) == 1, 'fixed reference tensor inventory')
        raw = _reference_bytes(ref, 'tensors/' + entries[0]['path'])
        expected = np.frombuffer(raw, dtype='<f4').reshape(fields[name].shape)
        mask = masks.get(name)
        a,b = (fields[name][mask],expected[mask]) if mask is not None else (fields[name],expected)
        observed_fixed[name] = native.compare(a,b)
    return dict(whole_outputs=fixed, actual_observed_nodes=observed_fixed,
        fixed_arithmetic_pass=all(v['bit_exact'] for v in (*fixed.values(),*observed_fixed.values())),
        methods=native_results, thresholds=limits, historical_diagnostic_failures=ref['prior_failures'],
        full_29_node_acceptance=False, missing_nodes=['explicit_mask_tensor'],
        partially_observed_nodes=['scores','logits','prob','softmax_fp32'],
        future_score_materialization=False, new_official_forward_executed=False,
        reference_layout=dict(qk_storage='token_major' if rows==16 else 'head_major',
            native_result_sha256=reference_layout.NATIVE_RESULT_SHA256[rows],
            producer_sha256=reference_layout.PRODUCER_SHA256),
        reference_reuse='exact frozen same-raw-input cold references; original FAILs preserved')


def retain_failed_run(out, physical, capture):
    """Copy bounded actual diagnostics; never publish, resume, or access goldens.

    A later FFN/Down error may coexist with an accepted Attention terminal.
    Preserve that original record and its INCOMPLETE classification unchanged;
    copying it does not claim a successful block or retroactively publish data.
    Only already-published ordinary physical outputs are copied. Partially
    written act/workspace and virtual reservations are explicitly omitted.
    """
    root = Path(out) / 'failure_capture'
    require(not root.exists(), 'fresh failure capture required')
    root.mkdir()
    result = dict(status='FAILED_RUN_DIAGNOSTICS_ONLY', whole_block_pass=False,
                  native_acceptance=False, resumable_checkpoint=False, outputs={}, omitted=[])
    errors = []
    if physical is not None:
        before = physical.report()
        for name, region in physical.regions.items():
            if region['readonly']:
                continue
            if (not region['published'] or region['virtual'] or
                    region.get('workspace_transport') is not None):
                result['omitted'].append(name)
                continue
            try:
                record = before['outputs'][name]
                require(region['terminal'] and record['written_bytes'] == record['ack_bytes'] == region['extent'],
                        'published diagnostic lacks complete terminal/ACK: ' + name)
                raw = physical.raw(region['base'], region['extent'])
                require(len(raw) == record['bytes'] and sha(raw) == record['sha256'],
                        'published diagnostic hash changed: ' + name)
                target = root / (name + '.f32le')
                target.write_bytes(raw)
                result['outputs'][name] = dict(record, path=target.name,
                    base=region['base'], dtype=region['dtype'])
            except Exception as error:
                errors.append(name + ': ' + str(error))
        require(physical.report() == before, 'diagnostic preservation changed physical memory/counters')
    if capture is not None and capture.closed and not capture.active:
        try:
            result['attention'] = capture.save(root / 'attention_observation')
        except Exception as error:
            errors.append('attention: ' + str(error))
    result['errors'] = errors
    (root / 'summary.json').write_bytes(encoded(result))
    return dict(path=str(root), summary_sha256=file_sha(root / 'summary.json'), **result)


def run(out, path, digest, *, wall_budget=1200, m16=None, m16_sha256=None):
    out, path = Path(out).resolve(), Path(path).resolve()
    require(not out.exists() and 0 < wall_budget <= 1800, 'fresh bounded official model run required')
    s = verify_snapshot(path, digest)
    modules, dense, observation, native = runtime()
    helper, original_execution, fixtures, public, prefix, _, scalar, suffix, physical_adapter, matrix, _, _ = modules
    prior = prerequisite(m16,m16_sha256,s) if s['rows'] == 128 else None
    require(helper.host_tool_identity() == s['host_tools'], 'execution host tool drift')
    out.mkdir(parents=True)
    started, cpu = time.monotonic(), time.process_time(); deadline = started + wall_budget
    report = dict(status='PINNED_NOT_EXECUTED', policy=policy.POLICY, rows=s['rows'],
        source_sha256=s['source_sha256'], input_spec=s['input_spec'], binaries=s['binaries'],
        snapshot=str(path), snapshot_sha256=digest, m16_prerequisite=prior,
        rtl_executed=False, scala_executed=False, hardware_cycles=None,
        prelaunch_intermediate_payloads=[], old_pass_inherited=False,
        native_acceptance='PENDING_OBSERVED_NODE_GATES')
    def save(): (out / 'summary.json').write_bytes(encoded(report))
    try:
        with base.frozen_exec(s['source_sha256']) as observed, policy.reference_gate(s['input_spec']) as gate:
            f = fixtures.make_qwen2_21_fixture(s['rows'],s['epoch'])
            require(helper.metadata_identity(f) == s['metadata'], 'public metadata changed')
            inputs = load_inputs(s['input_spec'],s['rows'],s['reference'])
            require(base.identities(inputs) == s['loaded_inputs'], 'raw input identity changed')
            physical = prefix.PhysicalMemory(f,{n:base.bytes_provider(v) for n,v in inputs.items()})
            memory = physical_adapter.FullGraphMemory(physical)
            n, region = original_execution.numeric, f.config.regions[3]
            owner = n.model.FfnDrainOwnerModel(n.model.PrefixWorkspace(region.base,
                region.limit-region.base,s['epoch']+1,2560),enable_ffn_window=True,
                enable_ffn_tiles=True,enable_ffn_drain=True)
            library = matrix.configure_library(C.CDLL(s['binaries']['library']))
            selected = dense.selected_library(library)
            require(library.td_reset() == selected.sf_reset() == 0, 'initial arithmetic reset failed')
            service, shared_scalar = dense.OfficialMatrixService(library), scalar.ScalarService()
            x = policy.OfficialPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),
                owner,n.CappedTrace(),deadline,fixture=f,
                host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
                prefix_owner=policy.OfficialPrefixOwner(shared_scalar),
                attention_owner=policy.OfficialAttentionOwner(service,shared_scalar),matrix_service=service)
            silu = policy.ObservedSiluLibrary(selected,s['rows'])
            guarded = gate.library(silu)
            # Construct before any arithmetic: fresh loaded-bytecode validation
            # covers both new owner classes and the actual shared services.
            capture = observation.OfficialAttentionMonitoringObservation(x.attention_owner,source_sha256=s['source_sha256'])
            report.update(loaded_inputs=base.identities(inputs),metadata=s['metadata']); save()
            report['prefix_execution'] = prefix.execute_public_prefix(x,physical,guarded,out)
            report['status'] = 'ACTUAL_PREFIX_COMPLETE'; save()
            report['prefix_host_wall_seconds'] = time.monotonic() - started
            with capture:
                actual, report['execution'] = suffix.execute_public_suffix(x,physical,guarded,out,memory=memory)
            report['whole_terminal_host_wall_seconds'] = time.monotonic() - started
            require(x.launch_result and x.launch_result['completed'] == 21 and
                    x.counts['result_fire'] == 1 and not x.reset_required(), 'whole public terminal missing')
            report['observation'] = capture.save(out/'attention_observation')
            require(report['observation']['status'].startswith('COMPLETE_'), 'actual Attention observation incomplete')
            import numpy as np
            pv = np.frombuffer(capture._bytes('pv_bf16'),dtype='<u4').reshape(12,s['rows'],128)
            require(pv.transpose(1,0,2).copy().tobytes() == actual['att'].tobytes(),
                    'observed BF16 PV differs from actual ACKed physical attention output')
            silu_bytes = silu.seal(actual['act'].tobytes())
            (out/'actual_silu.f32le').write_bytes(silu_bytes)
            report['sealed_actual_outputs'] = {name:dict(bytes=len(v)*4,sha256=sha(v.tobytes()))
                                               for name,v in actual.items()}
            report['sealed_silu_sha256'] = sha(silu_bytes)
            report['status'] = 'WHOLE_TERMINAL_ACTUAL_OUTPUTS_SEALED'; save()
            gate.opened = True
            report['comparison'] = compare(s,actual,inputs,capture,silu_bytes,native)
            require(report['comparison']['fixed_arithmetic_pass'], 'actual chain differs from frozen BF16 arithmetic')
            require(source_hashes() == s['source_sha256'] and base.identities(inputs) == s['loaded_inputs'],
                    'post-execution source/input drift')
            report.update(status='PASS_BF16_DATAFLOW_NATIVE_GATE_REPORTED',
                source_sha256_after=source_hashes(), executed_imports_observed=sorted(observed),
                native_acceptance='FAIL_OR_INCOMPLETE_OBSERVED_NODE_GATE',
                host_wall_seconds=time.monotonic()-started, host_cpu_seconds=time.process_time()-cpu,
                host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            save(); return report
    except Exception as error:
        report.update(status='FAILED',error=str(error),host_wall_seconds=time.monotonic()-started)
        if 'x' in locals(): report['failed_host'] = x.report()
        if 'physical' in locals(): report['failed_memory'] = physical.report()
        try:
            report['failure_capture'] = retain_failed_run(out, locals().get('physical'), locals().get('capture'))
        except Exception as preservation_error:
            report['failure_capture_error'] = str(preservation_error)
        save(); raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--rows',type=int,choices=(16,128),default=16);p.add_argument('--compile-receipt',type=Path)
    p.add_argument('--snapshot',type=Path);p.add_argument('--expected-snapshot-sha256')
    p.add_argument('--wall-budget',type=int,default=1200)
    p.add_argument('--m16-prerequisite',type=Path);p.add_argument('--m16-sha256')
    a=p.parse_args()
    if a.prepare_only:
        path,s=prepare(a.out,a.compile_receipt,a.rows)
        print(json.dumps(dict(status=s['status'],path=str(path),sha256=file_sha(path))),flush=True)
    else:
        r=run(a.out,a.snapshot,a.expected_snapshot_sha256,wall_budget=a.wall_budget,
              m16=a.m16_prerequisite,m16_sha256=a.m16_sha256)
        print(json.dumps({k:r[k] for k in ('status','rows','host_wall_seconds')}),flush=True)


if __name__ == '__main__': main()
