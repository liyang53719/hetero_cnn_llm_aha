"""Control-only tests: synthetic prefix events and tiny processes, no EDA/model."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('attention_threads_diagnostic', ROOT/'tools/attention_threads/run_diagnostic.py')
diag = importlib.util.module_from_spec(spec); spec.loader.exec_module(diag)


def prefix(tmp_path, cycles=80, matrix=True):
    tmp_path.mkdir(exist_ok=True)
    events = []
    for cycle in range(1, cycles+1):
        event = dict.fromkeys(diag.EVENT_INTS, 0)
        event.update(cycle=cycle, pre_reset=int(cycle <= 6), pre_running=int(cycle > 36),
                     end_running=int(cycle > 36), pre_ar_valid=int(cycle == 37), pre_ar_ready=1,
                     pre_r_valid=int(cycle == 37), pre_r_ready=1, end_idma_read_beats=int(cycle >= 37),
                     pre_w_payload_le_hex='', pre_r_payload_le_hex='00'*64 if cycle == 37 else '')
        if matrix:
            if 40 <= cycle <= 71:
                event.update(pre_w_valid=1, pre_w_ready=1, pre_w_payload_le_hex='00'*64)
            if cycle in (72, 73):
                event.update(pre_b_valid=1, pre_b_ready=1)
            if cycle >= 72:
                beats = 16 if cycle == 72 else 32
                event.update(end_write_acks=beats, end_ack_bytes=beats*64, end_physical_bytes=beats*64)
            if cycle == 77:
                event.update(pre_completion_valid=1, pre_completion_ready=1, pre_completion_word=(3 << 29) | (1 << 40))
            if cycle >= 77:
                event.update(end_completions=1, end_successful=1, end_pc=1)
            if cycle >= 78:
                event.update(pre_pc=1, end_pc=1, end_pipeline_issues=cycle-77)
        events.append(event)
    raw = ('\n'.join(json.dumps(value) for value in [diag.HEADER, *events])+'\n').encode()
    (tmp_path/'prefix_events.jsonl').write_bytes(raw)
    deterministic = dict(cycles=cycles, reset_cycles=6, active_cycles=cycles-36, ar_handshakes=1,
                         aw_handshakes=0, w_handshakes=32 if matrix else 0, r_handshakes=1, b_handshakes=2 if matrix else 0,
                         memory_bytes=16, memory_fnv1a64='0'*16,
                         terminal_event={key: value for key, value in events[-1].items() if key not in diag.PAYLOAD_KEYS})
    report = dict(schema='HOST_ATTENTION_BLOCK_PREFIX_V1', status='BOUNDED_DIAGNOSTIC_PREFIX',
                  numerical_acceptance=False, prefix_reached=True, cycles=cycles, cycle_limit=cycles,
                  constructor_cycles=36, step_elapsed_ns=100, timing_scope=diag.TIMING_SCOPE,
                  event_file='prefix_events.jsonl', event_bytes=len(raw), prefix_fnv1a64='0'*16,
                  prefix_hash_is_noncryptographic=True, memory_hash_is_noncryptographic=True,
                  sha256_input='exact prefix_events.jsonl bytes; no timings or output paths', deterministic=deterministic)
    (tmp_path/'prefix.json').write_text(json.dumps(report))
    return report, events


def change_report(path, key, value):
    report = json.loads((path/'prefix.json').read_text()); report[key] = value
    (path/'prefix.json').write_text(json.dumps(report))


def rewrite_events(path, events):
    raw = ('\n'.join(json.dumps(value) for value in [diag.HEADER, *events])+'\n').encode()
    (path/'prefix_events.jsonl').write_bytes(raw)
    change_report(path, 'event_bytes', len(raw))


def test_exact_frozen_header_and_builder():
    assert diag.sha(ROOT/diag.PREFIX_HEADER) == diag.HEADER_SHA256
    assert diag.sha(ROOT/diag.BUILD_SCRIPT) == diag.BUILDER_SHA256
    import re
    text = (ROOT/diag.PREFIX_HEADER).read_text()
    fields = set(re.findall(r'field\(pre_,"([^"]+)"', text))
    fields.discard('pre_')  # Macro string-concatenation prefix, not a complete field.
    fields.update(re.findall(r'PREFIX_(?:BUS|PORT|OWNER)\("([^"]+)"', text))
    fields.update('pre_'+channel+'_'+field for channel in ('ar', 'aw', 'w', 'r', 'b') for field in ('valid', 'ready'))
    fields.update('pre_'+channel+'_'+field for channel in ('ar', 'aw') for field in ('address', 'id', 'len', 'size', 'burst'))
    assert fields == diag.EVENT_INTS


def test_prefix_streams_actual_activity_without_completed_macs(tmp_path):
    prefix(tmp_path)
    result = diag.read_prefix(tmp_path, 80)
    assert result['activity']['matrix_activity_proven']
    assert result['activity']['first_matrix_issue_cycle'] == 78
    assert result['activity']['matrix_pipeline_issue_delta'] == 3
    assert result['activity']['norm_completion_before_matrix']
    assert result['activity']['norm_acked_bytes'] == 2048
    assert result['activity']['useful_macs_delta'] == result['activity']['executed_macs_delta'] == 0
    assert 'pre_r_payload_le_hex' not in json.dumps(result)
    assert result['event_sha256'] == diag.sha(tmp_path/'prefix_events.jsonl')


@pytest.mark.parametrize('key,value', [('numerical_acceptance', True), ('cycle_limit', 39),
    ('constructor_cycles', 35), ('step_elapsed_ns', True), ('step_elapsed_ns', 0),
    ('event_bytes', 1), ('timing_scope', 'eval only'), ('event_file', '../events'), ('extra', 'payload')])
def test_report_rejections(tmp_path, key, value):
    prefix(tmp_path); change_report(tmp_path, key, value)
    with pytest.raises(ValueError): diag.read_prefix(tmp_path, 80)


@pytest.mark.parametrize('mutation', ['missing', 'order', 'excess', 'bool', 'payload', 'unknown', 'reset', 'terminal', 'negative'])
def test_event_rejections(tmp_path, mutation):
    _, events = prefix(tmp_path)
    if mutation == 'missing': events.pop()
    elif mutation == 'order': events[1]['cycle'] = 1
    elif mutation == 'excess': events.append(events[-1])
    elif mutation == 'bool': events[2]['cycle'] = True
    elif mutation == 'payload': events[36]['pre_r_payload_le_hex'] = 'ff'
    elif mutation == 'unknown': events[2]['future_tensor'] = 'payload'
    elif mutation == 'reset': events[38]['end_reset_required'] = 1
    elif mutation == 'terminal': events[-1]['end_rng'] = 1
    elif mutation == 'negative': events[38]['end_pipeline_issues'] = -1
    rewrite_events(tmp_path, events)
    with pytest.raises(ValueError): diag.read_prefix(tmp_path, 80)


def test_byte_bound_checked_before_event_read(tmp_path, monkeypatch):
    prefix(tmp_path); monkeypatch.setattr(diag, 'EVENT_MAX_BYTES', 10)
    with pytest.raises(ValueError, match='byte bound'): diag.read_prefix(tmp_path, 80)


def test_duplicate_json_and_symlink_rejected(tmp_path):
    prefix(tmp_path)
    report = tmp_path/'prefix.json'
    report.write_text(report.read_text().replace('"schema":', '"schema":"bad", "schema":', 1))
    with pytest.raises(ValueError, match='duplicate'): diag.read_prefix(tmp_path, 80)
    report.unlink(); report.symlink_to(tmp_path/'prefix_events.jsonl')
    with pytest.raises(ValueError, match='nonsymlink'): diag.read_prefix(tmp_path, 80)


def rows(tmp_path, matrix=True):
    prefix(tmp_path, matrix=matrix)
    result = diag.read_prefix(tmp_path, 80)
    return [dict(variant=variant, status='COMPLETE', log_sha256='abc',
                 prefix=dict(result, step_elapsed_ns=200 if variant == 'baseline' else 100)) for variant in diag.ORDER]


def test_abba_ratio_is_whole_prefix_only(tmp_path):
    result = diag.compare_window(rows(tmp_path), 65536)
    assert result['status'] == 'COMPLETE_PREFIX_EQUIVALENCE_ONLY'
    assert result['baseline_over_threads2_mean_step'] == 2
    assert result['isolated_matrix_timing'] is result['isolated_eval_timing'] is result['numerical_acceptance'] is False


def test_no_matrix_or_timeout_is_pending(tmp_path):
    value = rows(tmp_path, matrix=False)
    assert diag.compare_window(value, 65536)['status'] == 'PENDING'
    value[1] = dict(variant='threads2', status='PENDING_TIMEOUT')
    result = diag.compare_window(value, 65536)
    assert result['status'] == 'PENDING' and result['ratios_available'] is False


def test_abba_missing_order_or_drift_rejects(tmp_path):
    value = rows(tmp_path)
    with pytest.raises(ValueError, match='order'): diag.compare_window(value[:3], 65536)
    value[1]['prefix']['event_sha256'] = 'changed'
    with pytest.raises(ValueError, match='mismatch'): diag.compare_window(value, 65536)


def fake_cgroup(tmp_path, quota='200000 100000', v1=False):
    proc = tmp_path/'proc'; (proc/'self').mkdir(parents=True)
    (proc/'self/status').write_text('Name:\ttest\nCpus_allowed_list:\t2-5\n')
    mount = tmp_path/'sys/fs/cgroup'; leaf = mount/'job'; leaf.mkdir(parents=True)
    if v1:
        (proc/'self/cgroup').write_text('5:cpu,cpuacct,cpuset:/job\n')
        (proc/'self/mountinfo').write_text('31 22 0:22 / /sys/fs/cgroup rw - cgroup cgroup rw,cpu,cpuacct,cpuset\n')
        (mount/'cpu.cfs_quota_us').write_text('200000'); (mount/'cpu.cfs_period_us').write_text('100000')
        (leaf/'cpu.cfs_quota_us').write_text('-1'); (leaf/'cpu.cfs_period_us').write_text('100000')
        (leaf/'cpuset.effective_cpus').write_text('3-5')
    else:
        (proc/'self/cgroup').write_text('0::/job\n')
        (proc/'self/mountinfo').write_text('31 22 0:22 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n')
        (mount/'cpu.max').write_text(quota); (leaf/'cpu.max').write_text('max 100000')
        (leaf/'cpuset.cpus.effective').write_text('3-5')
    (mount/'cpu.stat').write_text('usage_usec 100\nnr_throttled 2\nthrottled_usec 12\n')
    return proc


def inventory(argv, **kwargs):
    return '4\n' if argv == ['nproc'] else 'CPU(s): 4\n'


@pytest.mark.parametrize('v1', [False, True])
def test_cpu_admission_counts_ancestor_quotas_and_cpuset(tmp_path, v1):
    proc = fake_cgroup(tmp_path, v1=v1)
    value = diag.resource_snapshot(proc, tmp_path, {2, 3, 4, 5}, inventory)
    assert value['effective_cpu_count'] == 2
    assert value['selected_affinity'] == [3, 4]
    assert value['permitted_cpus'] == [3, 4, 5]


def test_fractional_quota_blocks_build_admission(tmp_path):
    proc = fake_cgroup(tmp_path, quota='150000 100000')
    value = diag.resource_snapshot(proc, tmp_path, {2, 3, 4, 5}, inventory)
    assert value['effective_cpu_count'] == 1.5
    assert value['selected_affinity'] == []


def test_missing_controller_fails_closed(tmp_path):
    proc = fake_cgroup(tmp_path)
    (tmp_path/'sys/fs/cgroup/cpu.max').unlink(); (tmp_path/'sys/fs/cgroup/job/cpu.max').unlink()
    with pytest.raises(ValueError, match='incomplete'): diag.resource_snapshot(proc, tmp_path, {2, 3, 4, 5}, inventory)


def test_cpu_runtime_usage_and_throttling(tmp_path):
    proc = fake_cgroup(tmp_path)
    before = diag.resource_snapshot(proc, tmp_path, {2, 3, 4, 5}, inventory)
    (tmp_path/'sys/fs/cgroup/cpu.stat').write_text('usage_usec 600\nnr_throttled 3\nthrottled_usec 22\n')
    after = diag.resource_snapshot(proc, tmp_path, {2, 3, 4, 5}, inventory)
    value = diag.cpu_delta(before, after, 2, SimpleNamespace(ru_utime=1, ru_stime=1), SimpleNamespace(ru_utime=4, ru_stime=2))
    assert value['mean_cpu_cores'] == 2
    assert next(iter(value['cgroup_delta'].values()))['throttled_usec'] == 10
    diag.same_admission(before, after)
    after['quota_cpu_limits'] = [1]
    with pytest.raises(ValueError, match='drift'): diag.same_admission(before, after)


def test_recipe_only_adds_threads_two(tmp_path):
    raw = (ROOT/diag.BUILD_SCRIPT).read_bytes()
    result = diag.candidate_recipe(raw, ROOT, tmp_path)
    start = 'python3 "$P/scripts/prepare_idma_export.py"'
    body = raw.decode().split(start, 1)[1].split('python3 "$P/scripts/host_bf16_v_toolchain.py" after', 1)[0]
    candidate = result[result.index(start):]
    record_start = candidate.index('python3 - "$OUT/verilator_argv.json"')
    record_end = candidate.index('\nPY_THREADS_ARGV\n', record_start)+len('\nPY_THREADS_ARGV\n')
    candidate = candidate[:record_start]+candidate[record_end:]
    assert candidate.replace('verilator --threads 2 ', 'verilator ', 1) == start+body
    assert 'scala.tools.nsc.Main' not in result and 'EmitHost' not in result
    assert '--threads-dpi' not in result and 'build_ready' not in result
    assert 'MAKEFLAGS=-n' in result and '-j1 hier_verilation' in result
    assert 'OPT_FAST=-O2 OPT_SLOW=-O0' in result
    with pytest.raises(ValueError, match='identity drift'): diag.candidate_recipe(raw+b'\n', ROOT, tmp_path)


def two_cpus():
    values = sorted(os.sched_getaffinity(0))[:2]
    if len(values) < 2: pytest.skip('tiny process affinity test requires two allowed CPUs')
    return values


def logged_worker(tmp_path, program, timeout):
    cpus = two_cpus()
    worker = tmp_path/'worker.py'
    worker.write_text(
        'import importlib.util,json,sys\n'
        'from pathlib import Path\n'
        'spec=importlib.util.spec_from_file_location("diag",'+repr(str(ROOT/'tools/attention_threads/run_diagnostic.py'))+')\n'
        'diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)\n'
        'result,_,_=diag.run_logged([sys.executable,"-c",'+repr(program)+'],Path('+repr(str(tmp_path/'process.log'))+'),'
        'cwd=Path('+repr(str(tmp_path))+'),timeout='+repr(timeout)+',affinity='+repr(cpus)+')\n'
        'Path('+repr(str(tmp_path/'result.json'))+').write_text(json.dumps(result))\n')
    process = subprocess.Popen([sys.executable,str(worker)],start_new_session=True)
    try:
        assert process.wait(timeout=8) == 0
    finally:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=2)
    return json.loads((tmp_path/'result.json').read_text()), cpus


def test_tiny_process_affinity_and_nonzero_exit(tmp_path):
    result, cpus = logged_worker(tmp_path, 'import os; print(sorted(os.sched_getaffinity(0))); raise SystemExit(7)', 2)
    assert result['returncode'] == 7 and not result['timed_out']
    assert json.loads((tmp_path/'process.log').read_text()) == cpus
    assert result['process_group_cleaned']


def test_timeout_kills_process_group_and_preserves_log(tmp_path):
    program = ('import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
               'print(p.pid,flush=True); time.sleep(30)')
    started = time.monotonic()
    result, _ = logged_worker(tmp_path, program, .2)
    assert result['timed_out'] and time.monotonic()-started < 6
    child = int((tmp_path/'process.log').read_text())
    stat = Path('/proc')/str(child)/'stat'
    assert not stat.exists() or stat.read_text().split()[2] == 'Z'


def test_frozen_supervisor_cleans_descendants_after_worker_sigkill(tmp_path):
    # Execute the exact existing supervisor definitions without importing any
    # numerical factories. This is still a real process tree and real SIGKILL.
    import ast
    source = (ROOT/'chisel/continuous_prefill/scripts/run_host_bf16_attention_core_fresh_gate.py').read_text()
    tree = ast.parse(source)
    names = {'SupervisorInterrupted','_signal_group','_terminate_group','supervise_process'}
    tree.body = [node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names]
    scope = dict(signal=signal,os=os,time=time,subprocess=subprocess,ROOT=tmp_path,
                 GROUP_TERMINATION_GRACE_SECONDS=.2,require=diag.require)
    exec(compile(tree,'frozen_supervisor','exec'),scope)
    cpus = two_cpus(); worker = tmp_path/'killed_worker.py'
    child_program = ('import os,signal,subprocess,sys,time; '
        'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
        'print(os.getpid(),p.pid,flush=True); os.kill(os.getppid(),signal.SIGKILL); time.sleep(30)')
    worker.write_text(
        'import importlib.util,sys\nfrom pathlib import Path\n'
        'spec=importlib.util.spec_from_file_location("diag",'+repr(str(ROOT/'tools/attention_threads/run_diagnostic.py'))+')\n'
        'diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)\n'
        'diag.run_logged([sys.executable,"-c",'+repr(child_program)+'],Path('+repr(str(tmp_path/'orphans.log'))+'),'
        'cwd=Path('+repr(str(tmp_path))+'),timeout=20,affinity='+repr(cpus)+')\n')
    outcome = scope['supervise_process']([sys.executable,str(worker)],timeout_seconds=5,grace_seconds=.2)
    assert outcome['worker_returncode'] == -signal.SIGKILL
    assert outcome['cleanup']['direct_child_reaped']
    for pid in map(int,(tmp_path/'orphans.log').read_text().split()):
        stat = Path('/proc')/str(pid)/'stat'
        assert not stat.exists() or stat.read_text().split()[2] == 'Z'


def test_candidate_rejection_before_build(tmp_path):
    with pytest.raises(ValueError, match='bounded candidate'):
        diag.build_candidate(ROOT, tmp_path/'baseline', tmp_path/'candidate', timeout=6301,
                             affinity=[0, 1], launch=lambda *a, **kw: pytest.fail('build must not run'))


def test_supervisor_failure_never_preserves_success(tmp_path):
    diag.write_compact(tmp_path, {'status':'COMPLETE_PREFIX_DIAGNOSTIC_ONLY', 'numerical_acceptance': True}, {})
    outcome = dict(returncode=1, forced_shutdown=True, reason='timeout')
    assert diag.finalize_supervision(tmp_path, outcome) == 1
    summary = json.loads((tmp_path/'compact/summary.json').read_text())
    assert summary['status'] == 'FAILED_DIAGNOSTIC'
    assert summary['numerical_acceptance'] is summary['overall_pass'] is False
    assert summary['compact_artifact_upload_allowlist'] == list(diag.COMPACT_FILES)
    assert summary['artifact_upload_allowlist'] == diag.upload_allowlists()['artifact_upload_allowlist']


def test_missing_supervisor_evidence_fails_closed(tmp_path):
    assert diag.finalize_supervision(tmp_path, dict(returncode=0, forced_shutdown=False)) == 1


def test_worker_resource_rejection_never_builds_or_captures(tmp_path, monkeypatch):
    out = tmp_path/'out'
    args = SimpleNamespace(expected_sha256='a'*64, baseline_run_id='38015586840')
    monkeypatch.setattr(diag, 'checked_paths', lambda a: (ROOT, out, 'b'*40))
    frozen = SimpleNamespace(total_budget=lambda seconds: __import__('contextlib').nullcontext())
    monkeypatch.setattr(diag, 'imports', lambda source: (frozen, None))
    monkeypatch.setattr(diag, 'resource_snapshot', lambda: {'effective_cpu_count': 1.5})
    monkeypatch.setattr(diag, 'build_candidate', lambda *a, **kw: pytest.fail('candidate build prohibited'))
    monkeypatch.setattr(diag, 'fresh_fixture', lambda *a, **kw: pytest.fail('fresh capture prohibited'))
    monkeypatch.setenv('GITHUB_SHA', 'b'*40)
    assert diag.run_worker(args) == 0
    summary = json.loads((out/'compact/summary.json').read_text())
    assert summary['status'] == 'NOT_RUN' and summary['candidate_builds'] == 0


def test_factory_uses_original_live_authorities_once(tmp_path):
    calls = []
    def reference(name, receipt):
        return SimpleNamespace(receipt_sha256=name, verify=lambda **kw: receipt)
    session = SimpleNamespace(fresh=True, manifest_sha256='capture',
        evidence=lambda: dict(fresh_official_executions=2, reused_official_executions=0),
        verify=lambda: {'source_sha256': {}})
    projected = reference('projection', dict(requested_windows=[['cold',0],['carried',1]], head_jobs=24,
        matrix_accumulator_steps=10485760, native_operator_gate_pass=True, source_sha256={}))
    attended = reference('attention', dict(original_operator_gate_pass=True, source_sha256={}))
    block = reference('block', dict(source_sha256_after={}))
    def call(name, result):
        def invoke(*args, **kwargs): calls.append((name, args, kwargs)); return result
        return invoke
    frozen = SimpleNamespace(rebuild_session=call('capture', session),
        _native_failure_evidence=lambda value: {'still_failed':True},
        merge_sources=lambda dst, src: dst.update(src), WINDOWS=(('cold',0),('carried',1)),
        generate_projection_references=call('projection',projected),
        generate_attention_references=call('attention',attended), generate_block_reference=call('block',block),
        pack_fixture=call('pack',dict(live_authorities_verified=True, source_sha256={}, input_sha256={'raw':'hash'})))
    args = SimpleNamespace(payload_layer0='l0',payload_layer3='l3',payload_extra='extra')
    summary, hashes = {}, dict(source_sha256={})
    stages = []
    inventory = SimpleNamespace(admit=lambda stage, actual, hashes: stages.append((stage, actual)),
                                require_complete=lambda hashes: None)
    authorities, admitted = diag.fresh_fixture(frozen, args, tmp_path, summary, hashes, inventory)
    assert [call[0] for call in calls] == ['capture','projection','attention','block','pack']
    assert calls[1][2]['variants'] == calls[2][2]['variants'] == ('baseline',)
    assert calls[-1][2] == authorities and authorities['session'] is session
    assert hashes['input_sha256'] == {'raw':'hash'} and summary['native_full_block_failures']['still_failed']
    assert stages == [(stage, {}) for stage in diag.SOURCE_STAGES]


@pytest.mark.parametrize('field,value', [('pre_completion_valid', 0), ('end_ack_bytes', 1984),
    ('end_physical_bytes', 1984), ('end_write_acks', 31), ('end_successful', 0), ('pre_completion_word', 0)])
def test_matrix_requires_actual_norm_publication(tmp_path, field, value):
    _, events = prefix(tmp_path)
    events[76][field] = value
    rewrite_events(tmp_path, events)
    with pytest.raises(ValueError, match='Norm|Matrix'): diag.read_prefix(tmp_path, 80)


def test_norm_smoke_rejects_unexpected_matrix_scope(tmp_path):
    with pytest.raises(ValueError, match='Norm scope'): diag.compare_window(rows(tmp_path), 4096)


def test_candidate_build_mock_records_new_identity_without_baseline_receipt(tmp_path, monkeypatch):
    baseline = tmp_path/'baseline'; (baseline/'generated').mkdir(parents=True)
    (baseline/'generated/HostBlockTop.sv').write_text('immutable fake RTL')
    (baseline/'generated/SCOPE.json').write_text('{}')
    monkeypatch.setattr(diag, 'RTL_SHA256', diag.sha(baseline/'generated/HostBlockTop.sv'))
    candidate = tmp_path/'candidate'
    invocations = []
    def launch(argv, log, **kwargs):
        invocations.append((argv, kwargs)); Path(log).write_text('mock build')
        (candidate/'obj').mkdir(); binary = candidate/'obj/VHostBlockTop'
        binary.write_bytes(b'\x7fELFmock candidate'); binary.chmod(0o755)
        (candidate/'obj/VHostBlockTop.cpp').write_text('unsigned VHostBlockTop::threads() const { return 2; }')
        (candidate/'verilator_argv.json').write_text('["verilator", "--threads", "2"]')
        (candidate/'bounded_build').mkdir()
        (candidate/'bounded_build/01.log').write_text('g++ -O2 -ffp-contract=off -fno-fast-math -c host_bf16_attention_block.cpp\n')
        (candidate/'bounded_build/result.json').write_text('{"status":"PASS","jobs":1,"generated_inputs_unchanged":true}')
        return dict(timed_out=False, returncode=0), None, None
    receipt = diag.build_candidate(ROOT, baseline, candidate, timeout=1, affinity=[1,2], launch=launch)
    assert len(invocations) == 1 and invocations[0][1]['affinity'] == [1,2]
    assert receipt['threads'] == 2 and receipt['numerical_acceptance'] is False
    assert receipt['verilator_argv'] == ['verilator','--threads','2']
    assert receipt['rtl_sha256'] == diag.sha(baseline/'generated/HostBlockTop.sv')
    assert not (candidate/'build_ready.json').exists()


def test_compiler_policy_drift_rejected(tmp_path):
    (tmp_path/'bounded_build').mkdir()
    (tmp_path/'bounded_build/01.log').write_text('g++ -O3 -ffast-math -c host_bf16_attention_block.cpp\n')
    with pytest.raises(ValueError, match='compiler flags'): diag.compiler_evidence(tmp_path)


def test_selected_tool_drift_rejected(tmp_path, monkeypatch):
    (tmp_path/'toolchain.json').write_text('{"tools":{"cxx":"expected"}}')
    real_import = diag.importlib.import_module
    def imported(name):
        if name == 'host_bf16_v_toolchain': return SimpleNamespace(tool_identity=lambda: {'cxx':'wrong'})
        if name == 'real2_ci': return SimpleNamespace(verilator_backend_identity=lambda *args: pytest.fail('must reject earlier'))
        return real_import(name)
    monkeypatch.setattr(diag.importlib, 'import_module', imported)
    with pytest.raises(ValueError, match='differs'): diag.selected_tools(tmp_path)


def test_candidate_identity_detects_elf_and_argv_drift(tmp_path):
    names = ['candidate_identity.json','build_threads2.sh','verilator_argv.json','obj/VHostBlockTop',
             'obj/VHostBlockTop.cpp','generated/HostBlockTop.sv','generated/SCOPE.json','idma_identity.json','idma.f']
    for name in names:
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(name)
    before = diag.candidate_identity(tmp_path)
    (tmp_path/'obj/VHostBlockTop').write_text('changed')
    after = diag.candidate_identity(tmp_path)
    assert before['obj/VHostBlockTop'] != after['obj/VHostBlockTop']
    (tmp_path/'build_ready.json').write_text('{}')
    with pytest.raises(ValueError, match='forbidden'): diag.candidate_identity(tmp_path)


def test_original_native_failure_survives_reference_failure(tmp_path):
    session = SimpleNamespace(fresh=True, manifest_sha256='capture',
        evidence=lambda: dict(fresh_official_executions=2, reused_official_executions=0),
        verify=lambda: {'source_sha256': {}})
    def projection(*args, **kwargs): raise ValueError('original native operator gate failed')
    frozen = SimpleNamespace(rebuild_session=lambda *args: session,
        _native_failure_evidence=lambda value: {'unchanged_failure':True},
        merge_sources=lambda dst, src: dst.update(src), WINDOWS=(), generate_projection_references=projection)
    args = SimpleNamespace(payload_layer0='l0',payload_layer3='l3',payload_extra='extra')
    summary, hashes = {}, dict(source_sha256={})
    inventory = SimpleNamespace(admit=lambda *args: None)
    with pytest.raises(ValueError, match='original native'):
        diag.fresh_fixture(frozen, args, tmp_path, summary, hashes, inventory)
    assert summary['native_full_block_failures'] == {'unchanged_failure':True}


@pytest.mark.parametrize('timeout_index', [None, 5])
def test_worker_mocked_end_to_end_abba_and_pending(tmp_path, monkeypatch, timeout_index):
    import contextlib
    out = tmp_path/'out'; archive = tmp_path/'archive'; archive.write_bytes(b'fake trusted package')
    args = SimpleNamespace(expected_sha256=diag.sha(archive), baseline_run_id='38015586840', archive=archive)
    calls = []; admission = dict(effective_cpu_count=2, selected_affinity=[0,1], sched_getaffinity=[0,1],
        cpus_allowed_list='0-1', permitted_cpus=[0,1], quota_cpu_limits=[2], cgroups=[])
    build_sources, stage_sources = source_shape()
    full_sources = diag.source_union(build_sources, *stage_sources.values())
    admitted = dict(live_authorities_verified=True, input_sha256={}, source_sha256=stage_sources['fixture'])
    session = SimpleNamespace(evidence=lambda: dict(fresh_official_executions=2,reused_official_executions=0))
    identity = {'generated/HostBlockTop.sv':diag.RTL_SHA256, 'obj/VHostBlockTop':'baseline ELF'}
    build_identity_calls = []
    def verify_checkout(pin, sources):
        diag.require(pin == diag.PIN and all(full_sources.get(name) == digest for name, digest in sources.items()),
                     'source differs from immutable test checkout')
    def build_identity(build, required):
        actual = json.loads((build/'sources.sha256.json').read_text())
        # Model the production authority's required-source subset check, and
        # strengthen this diagnostic test to require the entire build closure.
        diag.require(required and all(actual.get(name) == digest for name, digest in required.items()),
                     'built/live source closure mismatch')
        diag.require(required == actual == build_sources, 'full immutable build source map required')
        build_identity_calls.append(dict(required))
        return dict(identity)
    frozen = SimpleNamespace(total_budget=lambda seconds: contextlib.nullcontext(),
        merge_sources=lambda dst,src: dst.update(src), verify_checkout=verify_checkout,
        build_identity=build_identity, verify_all_build_sources=lambda *a: None,
        admit_fixture=lambda *a,**kw: admitted, _native_failure_evidence=lambda value:{'failed':True})
    def restore(*args):
        calls.append('restore'); baseline=out/'baseline'; baseline.mkdir()
        (baseline/'sources.sha256.json').write_text(json.dumps(build_sources)); (baseline/'idma_identity.json').write_text('{}')
        return {'restored':True}
    def build(*args, **kwargs):
        calls.append('build'); candidate=out/'threads2'; candidate.mkdir()
        (candidate/'idma_identity.json').write_text('{}')
        return dict(binary_sha256='candidate ELF')
    def fresh(frozen, args, output, summary, hashes, inventory):
        calls.append('fresh')
        for stage in diag.SOURCE_STAGES:
            inventory.admit(stage, stage_sources[stage], hashes)
        return dict(session=session), admitted
    count = 0
    def launch(argv, log, **kwargs):
        nonlocal count
        calls.append(('prefix',argv[-1],Path(argv[0]).parent.parent.name)); count += 1
        Path(log).write_text('same visible log')
        timed_out = count == timeout_index
        result = dict(returncode=None if timed_out else 0, timed_out=timed_out,elapsed_seconds=1)
        return result, SimpleNamespace(ru_utime=0,ru_stime=0), SimpleNamespace(ru_utime=1,ru_stime=.1)
    def read(output, cycles):
        return dict(event_sha256='events',event_bytes=12,deterministic_sha256='deterministic',terminal_event_sha256='terminal',
                    step_elapsed_ns=100,activity=dict(matrix_activity_proven=cycles==65536,pcs_seen=[0] if cycles==4096 else [0,1],
                                                     final_pipeline_issues=0 if cycles==4096 else 3))
    monkeypatch.setattr(diag,'checked_paths',lambda a:(ROOT,out,'b'*40))
    monkeypatch.setattr(diag,'imports',lambda s:(frozen,SimpleNamespace(prepare_compiler_jars=lambda *a:{},restore=restore)))
    monkeypatch.setattr(diag,'source_stage_snapshots',lambda *args:stage_sources)
    monkeypatch.setattr(diag,'resource_snapshot',lambda:dict(admission))
    monkeypatch.setattr(diag,'build_candidate',build); monkeypatch.setattr(diag,'fresh_fixture',fresh)
    monkeypatch.setattr(diag,'selected_tools',lambda p:{})
    monkeypatch.setattr(diag,'candidate_identity',lambda p:{'elf':'new'})
    monkeypatch.setattr(diag,'git',lambda p,*a:'' if a[0]=='status' else 'b'*40)
    monkeypatch.setattr(diag,'read_prefix',read); monkeypatch.setattr(diag,'run_logged',launch)
    monkeypatch.setenv('GITHUB_SHA','b'*40); monkeypatch.setenv('OFFLINE_TOOLS',str(tmp_path/'runtime'))
    assert diag.run_worker(args) == 0
    assert calls[:3] == ['restore','build','fresh']
    assert len(calls) == 11
    assert [value[2] for value in calls[3:]] == ['baseline','threads2','threads2','baseline']*2
    assert [value[1] for value in calls[3:]] == ['--diagnostic-prefix=4096']*4+['--diagnostic-prefix=65536']*4
    summary = json.loads((out/'compact/summary.json').read_text())
    assert summary['status'] == ('PENDING' if timeout_index else 'COMPLETE_PREFIX_DIAGNOSTIC_ONLY')
    assert summary['native_full_block_failures'] == {'failed':True}
    assert summary['numerical_acceptance'] is summary['overall_pass'] is False
    assert summary['candidate_builds'] == 1 and summary['source_tool_identity_verified'] is True
    hashes = json.loads((out/'compact/source_input_hashes.json').read_text())
    assert len(hashes['source_sha256']) == 658 and len(hashes['build_source_sha256']) == 655
    assert all(len(required) == 655 for required in build_identity_calls)
    assert len(build_identity_calls) >= 9


def source_shape():
    """The real failure shape: 655 immutable build sources plus 3 capture-only sources."""
    build = {'sources/source_'+str(index)+'.py': diag.object_sha(index) for index in range(655)}
    extra = {name: diag.object_sha(name) for name in sorted(diag.REFERENCE_ONLY_PATHS)}
    names = list(build)
    stages = dict(capture={names[0]:build[names[0]], **extra},
                  projection={name:build[name] for name in names[1:12]},
                  attention={name:build[name] for name in names[8:25]},
                  block={name:build[name] for name in names[:40]}, fixture=dict(build))
    return build, stages


def source_inventory():
    build, stages = source_shape()
    full = diag.source_union(build, *stages.values())
    verified = []
    def verify(pin, actual):
        diag.require(pin == diag.PIN and actual == full, 'complete frozen source union differs')
        verified.append(dict(actual))
    frozen = SimpleNamespace(verify_checkout=verify, merge_sources=lambda dst, src: dst.update(src))
    hashes = dict(source_sha256={})
    inventory = diag.SourceInventory(frozen, build, stages, hashes)
    return inventory, hashes, build, stages, verified


def test_source_inventory_real_655_plus_3_shape_preserves_every_source():
    inventory, hashes, build, stages, verified = source_inventory()
    assert len(hashes['source_sha256']) == 655 and hashes['reference_source_sha256'] == {}
    for index, stage in enumerate(diag.SOURCE_STAGES):
        inventory.admit(stage, stages[stage], hashes)
        assert hashes['source_sha256'] == diag.source_union(build, *(stages[key] for key in diag.SOURCE_STAGES[:index+1]))
        inventory.verify(hashes, dict(build))
    inventory.require_complete(hashes)
    assert len(hashes['source_sha256']) == 658
    assert hashes['build_source_sha256'] == dict(inventory.build) == build
    assert set(hashes['source_sha256'])-set(build) == diag.REFERENCE_ONLY_PATHS
    assert all(value == diag.source_union(build, *stages.values()) for value in verified)
    with pytest.raises(TypeError): inventory.build['extra.py'] = 'a'*64
    # Caller mutations cannot change either immutable snapshot.
    build.pop(next(iter(build))); stages['capture'].clear()
    inventory.verify(hashes)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'drift'])
def test_each_reference_stage_rejects_incomplete_extra_or_changed_receipt(mutation):
    for rejected in diag.SOURCE_STAGES:
        inventory, hashes, _, stages, _ = source_inventory()
        for stage in diag.SOURCE_STAGES:
            actual = dict(stages[stage])
            if stage == rejected:
                if mutation == 'missing': actual.pop(next(iter(actual)))
                elif mutation == 'extra': actual['unlisted.py'] = 'c'*64
                else: actual[next(iter(actual))] = 'd'*64
                with pytest.raises(ValueError, match='source inventory|nonempty'):
                    inventory.admit(stage, actual, hashes)
                break
            inventory.admit(stage, actual, hashes)


@pytest.mark.parametrize('field', ['source_sha256', 'build_source_sha256', 'reference_source_sha256'])
@pytest.mark.parametrize('mutation', ['missing', 'extra', 'drift'])
def test_aggregate_and_partition_tampering_rejected(field, mutation):
    inventory, hashes, _, stages, _ = source_inventory()
    for stage in diag.SOURCE_STAGES: inventory.admit(stage, stages[stage], hashes)
    if mutation == 'missing': hashes[field].pop(next(iter(hashes[field])))
    elif mutation == 'extra': hashes[field]['unknown.py'] = 'a'*64
    else: hashes[field][next(iter(hashes[field]))] = 'a'*64
    with pytest.raises(ValueError, match='union inventory drift'): inventory.verify(hashes)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'drift'])
def test_original_build_inventory_drift_rejected(mutation):
    inventory, hashes, build, _, _ = source_inventory()
    if mutation == 'missing': build.pop(next(iter(build)))
    elif mutation == 'extra': build['extra.py'] = 'b'*64
    else: build[next(iter(build))] = 'b'*64
    with pytest.raises(ValueError, match='build source inventory drift'): inventory.verify(hashes, build)


def test_stage_omission_reordering_or_hash_conflict_rejected():
    inventory, hashes, _, stages, _ = source_inventory()
    with pytest.raises(ValueError, match='incomplete'): inventory.require_complete(hashes)
    with pytest.raises(ValueError, match='order'): inventory.admit('projection', stages['projection'], hashes)
    build, stages = source_shape()
    stages['projection'][next(iter(build))] = 'e'*64
    with pytest.raises(ValueError, match='conflict'):
        diag.SourceInventory(SimpleNamespace(), build, stages, dict(source_sha256={}))


def test_finalizer_logs_both_complete_compact_receipts(tmp_path, capsys):
    build, stages = source_shape()
    summary = dict(status='COMPLETE_PREFIX_DIAGNOSTIC_ONLY', windows={'test': {'hash':'a'*64}})
    hashes = dict(source_sha256=diag.source_union(build, *stages.values()), candidate_identity={'obj/VHostBlockTop':'b'*64})
    diag.write_compact(tmp_path, summary, hashes)
    assert diag.finalize_supervision(tmp_path, dict(returncode=0, forced_shutdown=False)) == 0
    printed = capsys.readouterr().out
    for name in diag.COMPACT_FILES:
        begin, end = 'BEGIN_ATTENTION_THREADS_COMPACT '+name+'\n', 'END_ATTENTION_THREADS_COMPACT '+name+'\n'
        assert printed.count(begin) == printed.count(end) == 1
        raw = printed.split(begin, 1)[1].split(end, 1)[0]
        assert raw == (tmp_path/name).read_text()
        assert json.loads(raw) == json.loads((tmp_path/name).read_text())


def test_candidate_workflow_upload_is_exactly_nine_identity_files():
    import yaml
    value = yaml.safe_load((ROOT/'.github/workflows/attention-threads-diagnostic.yml').read_text())
    steps = [step for job in value['jobs'].values() for step in job['steps']
             if step.get('name') == 'Preserve only the built candidate and its checked identity files']
    assert len(steps) == 1
    step = steps[0]
    assert step['uses'] == 'actions/upload-artifact@v4'
    paths = step['with']['path'].strip().splitlines()
    expected = ['work/attention_threads_result/threads2/'+name for name in diag.CANDIDATE_FILES]
    assert len(paths) == 9 and set(paths) == set(expected)
    assert all('*' not in path and '..' not in Path(path).parts for path in paths)
    allowlists = diag.upload_allowlists()
    assert set(allowlists['artifact_upload_allowlist']) == set(diag.COMPACT_FILES) | {'threads2/'+name for name in diag.CANDIDATE_FILES}


@pytest.mark.parametrize('mutation', [None, 'missing', 'extra', 'git_drift', 'file_drift', 'wrong_module'])
def test_reference_snapshot_preflight_binds_all_extra_sources_to_frozen_git(tmp_path, monkeypatch, mutation):
    build, stages = source_shape()
    modules = {}
    paths = dict(capture=('heteronpu.qk_norm256_materialization', 'src/heteronpu/qk_norm256_materialization.py'),
        projection=('host_bf16_qkv_reference', 'chisel/continuous_prefill/scripts/host_bf16_qkv_reference.py'),
        attention=('host_bf16_qk_rope_reference', 'chisel/continuous_prefill/scripts/host_bf16_qk_rope_reference.py'),
        block=('host_bf16_attention_block_reference', 'chisel/continuous_prefill/scripts/host_bf16_attention_block_reference.py'),
        fixture=('host_bf16_attention_block_fixture', 'chisel/continuous_prefill/scripts/host_bf16_attention_block_fixture.py'))
    for stage, (name, relative) in paths.items():
        modules[name] = SimpleNamespace(__file__=str(tmp_path/relative),
            _source_identity=lambda stage=stage: stages[stage], source_identity=lambda stage=stage: stages[stage])
    capture = modules[paths['capture'][0]]
    capture._contract = lambda root: {}
    capture._source_hashes = lambda root, contract: stages['capture']
    originals = {name: json.dumps(name, separators=(',', ':')).encode() for name in diag.REFERENCE_ONLY_PATHS}
    for name, raw in originals.items():
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    if mutation == 'missing': stages['capture'].pop(next(iter(originals)))
    elif mutation == 'extra': stages['capture']['scripts/unexpected_reference.py'] = 'a'*64
    elif mutation == 'file_drift': (tmp_path/next(iter(originals))).write_bytes(b'changed')
    elif mutation == 'wrong_module': capture.__file__ = str(tmp_path/'wrong.py')
    git_reads = []
    def git_blob(argv, **kwargs):
        assert argv[:4] == ['git','-C',str(tmp_path),'show'] and argv[4].startswith(diag.PIN+':')
        name = argv[4].split(':',1)[1]; git_reads.append(name)
        return b'drifted Git bytes' if mutation == 'git_drift' else originals[name]
    monkeypatch.setattr(diag.importlib, 'import_module', lambda name: modules[name])
    monkeypatch.setattr(diag.subprocess, 'check_output', git_blob)
    if mutation is None:
        assert diag.source_stage_snapshots(tmp_path, build) == stages
        assert set(git_reads) == diag.REFERENCE_ONLY_PATHS
    else:
        with pytest.raises(ValueError): diag.source_stage_snapshots(tmp_path, build)
