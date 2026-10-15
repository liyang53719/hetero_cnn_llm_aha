"""Allowlisted local software aggregate; no payloads, identifiers or output hash.

Explicit collect reads only fixed RESULT/LAUNCH JSON and source-only closure.
This is a projection of current guarded receipts, not another numerical test or
an independent review. Reference arithmetic in an earlier bootstrap is outside
these receipts; its execution is not inferred. No uploading is performed.
"""
import json
import math
import os
from pathlib import Path
import re
import stat
from . import closure

ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = Path('/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
RESULT = 'work/qwen2_official_platform_fullblock_numeric/ci01/RESULT.json'
LAUNCH = 'work/qwen2_official_platform_fullblock_numeric/ci01.LAUNCH.json'
PASS = 'PASS_M128_OFFICIAL_OBSERVED_FULLBLOCK_PUBLIC21'
MAX_JSON_BYTES = 256 * 1024 * 1024
MAX_INTEGER = 2**53 - 1
STAGE_MAP = {
    'dependency_setup':'DEPENDENCY_SETUP', 'source_and_input_hashes':'SOURCE_VALIDATION',
    'native_artifact_validation':'NATIVE_VALIDATION', 'tool_hashes_and_fresh_setup':'FRESH_SETUP',
    'pc8_hold_and_kv_append':'CACHE_APPEND', 'attention_observer_setup':'ATTENTION_SETUP',
    'attention':'ATTENTION_EXECUTION', 'attention_writeback_and_pc12_hold':'ATTENTION_WRITEBACK',
    'pc12_release':'TAIL_EXECUTION', 'pc13_Dense':'TAIL_EXECUTION', 'pc14_Add':'TAIL_EXECUTION',
    'pc15_Norm':'TAIL_EXECUTION', 'pc16_18_resident_ffn':'TAIL_EXECUTION',
    'pc19_down':'TAIL_EXECUTION', 'pc20_residual':'TAIL_EXECUTION',
    'launch_result_hold_retire':'LAUNCH_RETIRE', 'whole_launch_output_seal':'OUTPUT_SEAL',
    'post_seal_official_comparison':'OFFICIAL_COMPARISON',
    'final_source_input_reference_tool_hashes':'FINAL_IDENTITY_CHECK',
    'final_receipt_write':'RECEIPT_WRITE',
    **{f'prefix_pc{i}_{name}':'PREFIX_EXECUTION' for i,name in
       enumerate(('n0','qraw','qr','q','kraw','kr','k','vraw','v'))}}
STAGES = frozenset(('UNKNOWN','AGGREGATION','SUPERVISOR',*STAGE_MAP.values()))
EXCEPTIONS = frozenset(('UNKNOWN','ValueError','RuntimeError','TimeoutError','BudgetExceeded',
    'MemoryError','OSError','FileNotFoundError','PermissionError','JSONDecodeError',
    'AssertionError','KeyError','TypeError','KeyboardInterrupt'))
DEBTS = frozenset(('matrix_owned','scalar_owned','dma_pending','owner_pending','owner_fifo',
    'owner_read','owner_a_hold','owner_a_rmw','accepted_write','tile_lease','tile_busy','a_lease',
    'reduction_active','reset_required','prefix_not_idle','attention_not_idle',
    'attention_memory_pending','attention_abort_pending','attention_client_live',
    'attention_matrix_request','matrix_c_state','matrix_group','matrix_result','matrix_done',
    'dense_bridge','dense_bridge_results','window_bridge','window_bridge_results',
    'ordinary_job','ordinary_terminal','coordinator_not_idle','coordinator_poison',
    'resident_silu_busy','workspace_read','workspace_seed','workspace_invalidated','workspace_unfinished'))
IDENTITIES = frozenset(('execution','host','physical','metadata','owner','a_banks','b_banks',
    'tile_banks','prefix_owner','attention_owner','matrix','scalar','accumulator_address',
    'act_data','workspace','workspace_data','physical_buffers'))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(same(a[k],b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x,y) for x,y in zip(a,b))
    return a == b


def integer(value, maximum=MAX_INTEGER):
    return value if type(value) is int and 0 <= value <= maximum else None


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) and 0 <= value <= MAX_INTEGER else None


def obj(value):
    return value if type(value) is dict else {}


def _pairs(items):
    result = {}
    for key,value in items:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('nonfinite JSON')


def _read(relative):
    path = ROOT / relative
    need(path.resolve() == path and not any(p.is_symlink() for p in (path,*path.parents)),
         'receipt alias')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_JSON_BYTES, 'receipt bounds')
        raw = stream.read(MAX_JSON_BYTES+1)
        after = os.fstat(stream.fileno())
    keys = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
    end = path.stat()
    need(len(raw) <= MAX_JSON_BYTES and all(getattr(before,k)==getattr(after,k)==getattr(end,k) for k in keys),
         'receipt changed while reading')
    result = json.loads(raw,object_pairs_hook=_pairs,parse_constant=_constant)
    need(type(result) is dict, 'receipt object required')
    return result


def _same_live(report):
    records = [report.get(k) for k in ('same_live_identity_initial','same_live_identity_at_pc12','same_live_identity_final')]
    first = records[0]
    if type(first) is not dict or set(first) != IDENTITIES:
        return False
    buffers = first['physical_buffers']
    if type(buffers) is not dict or not buffers or not all(integer(v) and type(k) is str for k,v in buffers.items()):
        return False
    return all(integer(v) for k,v in first.items() if k != 'physical_buffers') and all(same(first,r) for r in records[1:])


def _debts(report):
    value = report.get('backend_debts')
    return type(value) is dict and set(value) == DEBTS and all(v is None or v is False or type(v) is int and v == 0 for v in value.values())


def _counts(host):
    terminal = obj(host.get('launch_result'));accepted = obj(host.get('accepted'))
    completions = host.get('completions')
    return (terminal.get('status', 'missing') is None and
        integer(terminal.get('completed')) == 21 and integer(terminal.get('jobs')) == 17 and
        integer(accepted.get('completion_fire')) == 21 and integer(accepted.get('request_fire')) == 17 and
        integer(accepted.get('owner_result_fire')) == 17 and integer(accepted.get('result_fire')) == 1 and
        type(completions) is list and len(completions) == 21 and
        all(type(c) is dict and type(c.get('pc')) is int and c['pc'] == i and c.get('status','missing') is None
            for i,c in enumerate(completions)) and same(host.get('events'),list(range(22))) and
        host.get('reset_required') is False and host.get('same_owner_and_banks') is True)


def _comparison(report, require_pass=True):
    groups = (
        ('producer_comparisons', {'n0','qr','q','kr','k','v'}, {'qraw','kraw','vraw'}),
        ('attention_comparisons', {'scores','logits','prob','pv','att'}, {'softmax_fp32'}),
        ('tail_comparisons', {'o','r','n1','gate','up','silu','act','down','y'}, set()))
    for field,accepted,diagnostic in groups:
        group=report.get(field)
        if type(group) is not dict or set(group) != accepted | diagnostic:
            return False
        if not all((obj(group[n]).get('official_numeric_pass') is True if require_pass else
                    type(obj(group[n]).get('official_numeric_pass')) is bool) for n in accepted):
            return False
        if not all('official_numeric_pass' in obj(group[n]) and group[n]['official_numeric_pass'] is None for n in diagnostic):
            return False
    # Exact-copy and numerical policy are separate, explicitly versioned gates.
    legacy = report.get('cold_cache_comparisons')
    copy=obj(report.get('same_run_cache_comparison'))
    numeric=report.get('same_run_cache_original_comparisons')
    if (report.get('cache_contract')!='sealed-same-live-cold-cache-v1' or
        report.get('reference_contract')!='official-ast-ci-aten-avx2-reference-v1' or
        type(legacy) is not dict or set(legacy)!={'cache_k','cache_v'} or
        not all(type(obj(v).get('exact_cold_alias')) is bool for v in legacy.values()) or
        type(obj(report.get('official_kv_comparison')).get('official_kv_exact_copy')) is not bool or
        type(report.get('legacy_cross_oracle_contract_pass')) is not bool or
        set(copy)!={'scope','same_live_exact_copy','official_kv_exact_copy','numerical_acceptance_claimed',
                    'whole_block_acceptance_claimed','historical_run_upgraded'} or
        copy.get('scope')!='COLD_CACHE_IDENTITY_AND_COPY_ONLY' or copy.get('same_live_exact_copy') is not True or
        any(copy.get(k) is not False for k in ('numerical_acceptance_claimed','whole_block_acceptance_claimed','historical_run_upgraded')) or
        copy.get('official_kv_exact_copy') is not report['official_kv_comparison']['official_kv_exact_copy'] or
        type(numeric) is not dict or set(numeric)!={'cache_k','cache_v'}):return False
    for row in numeric.values():
        verdict=obj(obj(row).get('verdict'));metrics=obj(obj(row).get('metrics'))
        if (obj(row).get('finite') is not True or integer(obj(row).get('observed_elements'))!=32768 or
            obj(row).get('origin')!='final sealed physical KV subspan' or
            verdict.get('contract')!='spec/numerical_contract.md:operator' or
            not same(verdict.get('limits'),dict(max_abs=0.03125,mean_abs=0.005)) or
            type(obj(row).get('official_numeric_pass')) is not bool or
            verdict.get('passed') is not row['official_numeric_pass'] or
            number(metrics.get('max_abs')) is None or number(metrics.get('mean_abs')) is None or
            (metrics['max_abs']<=0.03125 and metrics['mean_abs']<=0.005) is not verdict['passed'] or
            (require_pass and row['official_numeric_pass'] is not True)):return False
    for item in (obj(report.get('official_kv_comparison')).get('official_numeric_pass'),
                 obj(report.get('softmax_probability_sum')).get('passed')):
        if (item is not True if require_pass else type(item) is not bool):return False
    return True


def _source_records(report):
    before=report.get('source_sha256_before');after=report.get('source_sha256_after')
    return type(before) is dict and bool(before) and all(type(k) is str and type(v) is str and
        re.fullmatch('[0-9a-f]{64}',v) for k,v in before.items()) and same(before,after)


def _empty(source_digest):
    return dict(schema=1, scope='Qwen2_M128_PUBLIC21_SOFTWARE', status='INCOMPLETE',
        reference_contract='official-ast-ci-aten-avx2-reference-v1',cache_contract='sealed-same-live-cold-cache-v1',
        source_digest=source_digest, failure_stage='UNKNOWN', exception_class='UNKNOWN',
        public_completions=None, owner_jobs=None, accepted_launch_results=None,
        host_wall_seconds=None, host_cpu_seconds=None, supervisor_wall_seconds=None,
        peak_rss_bytes=None, sampled_group_rss_bytes=None, output_bytes=None, log_bytes=None,
        useful_macs=None, executed_macs=None, efficiency_kind='SOFTWARE_OPERATION_EFFICIENCY',
        software_operation_efficiency=None, hardware_cycles=None, hardware_utilization=None,
        hardware_duty=None, reference_arithmetic_executed=None, official_reference_comparison_executed=False,
        dut_software_executed=None, rtl_executed=None, full_29_node_acceptance=False,
        full_official_forward_executed=False, same_live_guards_passed=False, debt_guards_passed=False)


def summarize(report, launch, *, source_digest):
    """Pure receipt projection; collect() additionally binds current source bytes."""
    need(type(report) is dict and type(launch) is dict, 'receipt objects required')
    need(type(source_digest) is str and re.fullmatch('[0-9a-f]{64}',source_digest), 'source digest required')
    result=_empty(source_digest)
    execution=obj(report.get('execution'));host=obj(execution.get('host'));terminal=obj(host.get('launch_result'))
    accepted=obj(host.get('accepted'))
    for target,origin in (('public_completions','completed'),('owner_jobs','jobs')):
        result[target]=integer(terminal.get(origin))
    result['accepted_launch_results']=integer(accepted.get('result_fire'))
    for name in ('host_wall_seconds','host_cpu_seconds'):
        result[name]=number(report.get(name))
    result['supervisor_wall_seconds']=number(launch.get('elapsed_seconds'))
    rss=integer(report.get('peak_rss_kib'), MAX_INTEGER//1024)
    result['peak_rss_bytes']=rss*1024 if rss is not None else None
    for target,origin in (('sampled_group_rss_bytes','peak_sampled_process_group_rss_bytes'),
                          ('output_bytes','final_output_bytes'),('log_bytes','final_log_bytes')):
        result[target]=integer(launch.get(origin))
    useful=integer(terminal.get('useful_macs'));executed=integer(terminal.get('executed_macs'))
    if useful is not None and executed is not None and useful <= executed:
        result.update(useful_macs=useful,executed_macs=executed,
            software_operation_efficiency=useful/executed if executed else None)
    if execution.get('reference_arithmetic_executed') is False:
        result['reference_arithmetic_executed']=False
    if execution.get('full_block_software_model_executed') is True:
        result['dut_software_executed']=True
    if report.get('rtl_executed') is False and execution.get('rtl_executed') is False:
        result['rtl_executed']=False
    result['same_live_guards_passed']=bool(_same_live(report))
    result['debt_guards_passed']=_debts(report)
    result['official_reference_comparison_executed']=bool(_comparison(report, require_pass=False))
    required_resource=('host_wall_seconds','host_cpu_seconds','supervisor_wall_seconds','peak_rss_bytes',
                       'sampled_group_rss_bytes','output_bytes','log_bytes')
    observed=obj(report.get('whole_schedule_prediction_and_observation'))
    passed=(type(report.get('schema')) is int and report['schema']==1 and
        type(launch.get('schema')) is int and launch['schema']==1 and launch.get('status')=='PASS' and
        integer(launch.get('returncode'))==0 and launch.get('cleanup_incomplete') is False and
        'failure_kind' in launch and launch['failure_kind'] is None and
        all(launch.get(k) is True for k in ('acceptance_sealed','fullblock_pass','accepted_final_launch_result')) and
        launch.get('child_status')==PASS and report.get('status')==PASS and
        all(report.get(k) is True for k in ('acceptance_sealed','official_observed_node_pass','fullblock_pass',
                                           'whole_block_terminal','finalfence','actual_outputs_sealed')) and
        report.get('old_pass_inherited') is False and launch.get('old_pass_inherited') is False and
        launch.get('automatic_retry') is False and report.get('historical_approval_inherited') is False and
        report.get('reviewed_source_manifest')==launch.get('reviewed_source_manifest')==source_digest and
        _source_records(report) and _counts(host) and result['same_live_guards_passed'] and
        result['debt_guards_passed'] and _comparison(report) and
        execution.get('status')=='PUBLIC21_PC0_20_SOFTWARE_EXECUTED' and
        all(execution.get(k) is True for k in ('same_owner_and_banks','same_physical_memory_and_services',
                                               'full_block_executed','full_block_software_model_executed')) and
        result['rtl_executed'] is False and result['reference_arithmetic_executed'] is False and
        report.get('full_29_node_acceptance') is False and report.get('full_official_forward_executed') is False and
        report.get('hardware_cycles','missing') is None and report.get('hardware_utilization','missing') is None and
        report.get('model_ticks_are_hardware_cycles') is False and
        result['useful_macs']==6014828544 and result['executed_macs']==6598164480 and
        integer(observed.get('actual_useful_macs'))==result['useful_macs'] and
        integer(observed.get('actual_executed_macs'))==result['executed_macs'] and
        all(result[k] is not None for k in required_resource) and
        result['host_wall_seconds']<=3300 and result['supervisor_wall_seconds']<=3330 and
        result['peak_rss_bytes']<=3221225472 and result['sampled_group_rss_bytes']<=3221225472 and
        result['output_bytes']<=1073741824 and result['log_bytes']<=16777216)
    if passed:
        result.update(status='PASS_OFFICIAL_OBSERVED',failure_stage=None,exception_class=None)
    else:
        if launch.get('status') in ('FAILED','PASS') or report.get('status') in ('FAILED',PASS,'FAIL_M128_OFFICIAL_OBSERVED_CONTRACT'):
            result['status']='FAILED'
        stage=report.get('failure_stage')
        result['failure_stage']=STAGE_MAP.get(stage,'UNKNOWN') if type(stage) is str else 'UNKNOWN'
        error=report.get('original_error_type')
        result['exception_class']=error if type(error) is str and error in EXCEPTIONS else 'UNKNOWN'
    validate_summary(result)
    return result


def validate_summary(value):
    need(type(value) is dict and set(value)==set(_empty('0'*64)), 'exact safe summary keys')
    need(type(value['schema']) is int and value['schema']==1 and value['scope']=='Qwen2_M128_PUBLIC21_SOFTWARE', 'summary schema/scope')
    need(value['status'] in ('PASS_OFFICIAL_OBSERVED','FAILED','INCOMPLETE'), 'summary status')
    need(value['reference_contract']=='official-ast-ci-aten-avx2-reference-v1' and
         value['cache_contract']=='sealed-same-live-cold-cache-v1','fixed public policy enums')
    need(type(value['source_digest']) is str and re.fullmatch('[0-9a-f]{64}',value['source_digest']), 'source-only digest')
    need(value['failure_stage'] is None or type(value['failure_stage']) is str and value['failure_stage'] in STAGES, 'safe stage')
    need(value['exception_class'] is None or type(value['exception_class']) is str and value['exception_class'] in EXCEPTIONS, 'safe exception')
    for key in ('public_completions','owner_jobs','accepted_launch_results','peak_rss_bytes','sampled_group_rss_bytes',
                'output_bytes','log_bytes','useful_macs','executed_macs'):
        need(value[key] is None or integer(value[key]) is not None, 'safe count')
    for key in ('host_wall_seconds','host_cpu_seconds','supervisor_wall_seconds'):
        need(value[key] is None or number(value[key]) is not None, 'safe duration')
    ratio=value['software_operation_efficiency']
    need(ratio is None or type(ratio) in (int,float) and math.isfinite(ratio) and 0<=ratio<=1, 'safe software ratio')
    need(value['efficiency_kind']=='SOFTWARE_OPERATION_EFFICIENCY' and
         all(value[k] is None for k in ('hardware_cycles','hardware_utilization','hardware_duty')), 'no hardware evidence')
    for key in ('reference_arithmetic_executed','dut_software_executed','rtl_executed'):
        need(value[key] is None or type(value[key]) is bool, 'safe execution flag')
    for key in ('official_reference_comparison_executed','full_29_node_acceptance','full_official_forward_executed',
                'same_live_guards_passed','debt_guards_passed'):
        need(type(value[key]) is bool, 'safe guard flag')
    need(value['full_29_node_acceptance'] is False and value['full_official_forward_executed'] is False, 'fixed partial scope')


def collect(*, source_digest=None, execute=False):
    need(type(execute) is bool, 'execute must be boolean')
    if not execute:
        return dict(status='NOT_EXECUTED', numeric_execution_allowed=False)
    need(type(source_digest) is str and re.fullmatch('[0-9a-f]{64}',source_digest), 'externally supplied source digest')
    need(ROOT==CI_ROOT and ROOT.resolve()==ROOT, 'fixed CI aggregate root')
    need(closure.digest(ROOT)==source_digest, 'source closure drift')
    records=[];errors=[]
    for relative in (RESULT,LAUNCH):
        try:records.append(_read(relative))
        except (OSError,ValueError,UnicodeError) as error:
            records.append({});errors.append(type(error).__name__)
    result=summarize(*records,source_digest=source_digest)
    if errors:
        result.update(status='FAILED' if records[1].get('status')=='FAILED' or
                      records[0].get('status') in ('FAILED','FAIL_M128_OFFICIAL_OBSERVED_CONTRACT') else 'INCOMPLETE',
                      failure_stage='AGGREGATION',
                      exception_class=errors[0] if errors[0] in EXCEPTIONS else 'UNKNOWN')
    need(closure.digest(ROOT)==source_digest, 'source closure changed during aggregate')
    validate_summary(result)
    return result
