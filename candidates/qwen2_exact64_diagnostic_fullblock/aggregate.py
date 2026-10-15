"""Allowlisted local software aggregate; no payloads, identifiers or output hash.

Explicit collect reads fixed RESULT/LAUNCH/POSTSEAL JSON and source-only closure.
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
from . import closure, accounting, retention

ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = Path('/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
RESULT = 'work/qwen2_exact64_diagnostic_fullblock_numeric/ci01/RESULT.json'
LAUNCH = 'work/qwen2_exact64_diagnostic_fullblock_numeric/ci01.LAUNCH.json'
PASS = 'PASS_DIAGNOSTIC_SOFTWARE_OWNER'
FAIL = 'FAIL_DIAGNOSTIC_SOFTWARE_OWNER'
POSTSEAL = 'work/qwen2_exact64_diagnostic_gate_probe/ci01/RESULT.json'
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
    return value if type(value) in (int,float) and 0 <= value <= MAX_INTEGER and math.isfinite(value) else None


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


# Public diagnostic identities are source constants, never receipt keys or text.
# The old 120 gates are retained, with formal flags required to stay false.
# Acceptance below is independently derived for this diagnostic-only contract.
# Each direct entry is (group, gate, receipt, fixed path, required value).
_MISSING = object()
_SOURCE_DIGEST = object()
DIRECT_GATES = (
    ('SCHEMA','REPORT','report',('schema',),1),
    ('SCHEMA','LAUNCH','launch',('schema',),1),
    ('LAUNCH','STATUS','launch',('status',),'PASS'),
    ('LAUNCH','RETURN_CODE','launch',('returncode',),0),
    ('LAUNCH','CLEANUP_COMPLETE','launch',('cleanup_incomplete',),False),
    ('LAUNCH','NO_FAILURE_KIND','launch',('failure_kind',),None),
    ('LAUNCH','ACCEPTANCE_SEALED','launch',('acceptance_sealed',),False),
    ('LAUNCH','FULLBLOCK_PASS','launch',('fullblock_pass',),False),
    ('LAUNCH','FINAL_RESULT_ACCEPTED','launch',('accepted_final_launch_result',),True),
    ('LAUNCH','CHILD_STATUS','launch',('child_status',),PASS),
    ('LAUNCH','NO_OLD_PASS','launch',('old_pass_inherited',),False),
    ('LAUNCH','NO_AUTOMATIC_RETRY','launch',('automatic_retry',),False),
    ('REPORT','STATUS','report',('status',),PASS),
    ('REPORT','ACCEPTANCE_SEALED','report',('acceptance_sealed',),False),
    ('REPORT','OBSERVED_NODE_PASS','report',('official_observed_node_pass',),True),
    ('REPORT','FULLBLOCK_PASS','report',('fullblock_pass',),False),
    ('REPORT','WHOLE_BLOCK_TERMINAL','report',('whole_block_terminal',),True),
    ('REPORT','FINALFENCE','report',('finalfence',),True),
    ('REPORT','OUTPUTS_SEALED','report',('actual_outputs_sealed',),True),
    ('REPORT','NO_OLD_PASS','report',('old_pass_inherited',),False),
    ('REPORT','NO_HISTORICAL_APPROVAL','report',('historical_approval_inherited',),False),
    ('SOURCE','REPORT_MANIFEST','report',('reviewed_source_manifest',),_SOURCE_DIGEST),
    ('SOURCE','LAUNCH_MANIFEST','launch',('reviewed_source_manifest',),_SOURCE_DIGEST),
    ('HOST','TERMINAL_STATUS','report',('execution','host','launch_result','status'),None),
    ('HOST','COMPLETIONS_COUNT','report',('execution','host','launch_result','completed'),21),
    ('HOST','OWNER_JOBS','report',('execution','host','launch_result','jobs'),17),
    ('HOST','ACCEPTED_COMPLETIONS','report',('execution','host','accepted','completion_fire'),21),
    ('HOST','ACCEPTED_REQUESTS','report',('execution','host','accepted','request_fire'),17),
    ('HOST','ACCEPTED_OWNER_RESULTS','report',('execution','host','accepted','owner_result_fire'),17),
    ('HOST','ACCEPTED_LAUNCH_RESULTS','report',('execution','host','accepted','result_fire'),1),
    ('HOST','RESET_CLEAR','report',('execution','host','reset_required'),False),
    ('HOST','SAME_OWNER_AND_BANKS','report',('execution','host','same_owner_and_banks'),True),
    ('EXECUTION','STATUS','report',('execution','status'),'PUBLIC21_PC0_20_SOFTWARE_EXECUTED'),
    ('EXECUTION','SAME_OWNER_AND_BANKS','report',('execution','same_owner_and_banks'),True),
    ('EXECUTION','SAME_MEMORY_AND_SERVICES','report',('execution','same_physical_memory_and_services'),True),
    ('EXECUTION','FULL_BLOCK','report',('execution','full_block_executed'),True),
    ('EXECUTION','SOFTWARE_MODEL','report',('execution','full_block_software_model_executed'),True),
    ('SCOPE','REPORT_NO_RTL','report',('rtl_executed',),False),
    ('SCOPE','EXECUTION_NO_RTL','report',('execution','rtl_executed'),False),
    ('SCOPE','NO_REFERENCE_ARITHMETIC','report',('execution','reference_arithmetic_executed'),False),
    ('SCOPE','NO_FULL29_ACCEPTANCE','report',('full_29_node_acceptance',),False),
    ('SCOPE','NO_FULL_OFFICIAL_FORWARD','report',('full_official_forward_executed',),False),
    ('SCOPE','NO_HARDWARE_CYCLES','report',('hardware_cycles',),None),
    ('SCOPE','NO_HARDWARE_UTILIZATION','report',('hardware_utilization',),None),
    ('SCOPE','NO_MODEL_TICKS_AS_CYCLES','report',('model_ticks_are_hardware_cycles',),False),
    ('MACS','USEFUL','summary',('useful_macs',),6014828544),
    ('MACS','EXECUTED','summary',('executed_macs',),6598164480),
    ('COMPARISON','CACHE_CONTRACT','report',('cache_contract',),'sealed-same-live-cold-cache-v1'),
    ('COMPARISON','REFERENCE_CONTRACT','report',('reference_contract',),'official-ast-ci-aten-avx2-reference-v1'),
    ('COMPARISON','COPY_SCOPE','report',('same_run_cache_comparison','scope'),'COLD_CACHE_IDENTITY_AND_COPY_ONLY'),
    ('COMPARISON','SAME_LIVE_EXACT_COPY','report',('same_run_cache_comparison','same_live_exact_copy'),True),
    ('COMPARISON','NO_COPY_NUMERICAL_CLAIM','report',('same_run_cache_comparison','numerical_acceptance_claimed'),False),
    ('COMPARISON','NO_COPY_WHOLE_BLOCK_CLAIM','report',('same_run_cache_comparison','whole_block_acceptance_claimed'),False),
    ('COMPARISON','NO_COPY_HISTORY_UPGRADE','report',('same_run_cache_comparison','historical_run_upgraded'),False),
)
# Fixed group/node order is part of the strict projection schema. Raw Q/K/V and
# softmax_fp32 are diagnostic-only in the original policy, never accepted nodes.
NODE_SPECS = tuple(
    ((name.upper() if group=='CACHE' else group+'_'+name.upper()),(field,name),'official_numeric_pass',('metrics',))
    for group,field,names in (
        ('PRODUCER','producer_comparisons',('n0','qr','q','kr','k','v')),
        ('ATTENTION','attention_comparisons',('scores','logits','prob','pv','att')),
        ('TAIL','tail_comparisons',('o','r','n1','gate','up','silu','act','down','y')),
        ('CACHE','same_run_cache_original_comparisons',('cache_k','cache_v')))
    for name in names) + (
        ('OFFICIAL_KV',('official_kv_comparison',),'official_numeric_pass',('metrics',)),
        ('SOFTMAX_SUM',('softmax_probability_sum',),'passed',()))
RESOURCE_GATES = (
    ('HOST_WALL','host_wall_seconds',3300),
    ('HOST_CPU','host_cpu_seconds',None),
    ('SUPERVISOR_WALL','supervisor_wall_seconds',3330),
    ('PEAK_RSS','peak_rss_bytes',3221225472),
    ('SAMPLED_GROUP_RSS','sampled_group_rss_bytes',3221225472),
    ('OUTPUT_BYTES','output_bytes',1073741824),
    ('LOG_BYTES','log_bytes',16777216))
DIAGNOSTIC_GROUPS = ('SCHEMA','LAUNCH','REPORT','SOURCE','HOST','LIVE','COMPARISON',
                     'NUMERIC','EXECUTION','SCOPE','MACS','RESOURCES')
EXTRA_GATES = {
    'SOURCE':('UNCHANGED_RECORDS',),
    'HOST':('COMPLETION_SEQUENCE','EVENT_SEQUENCE'),
    'LIVE':('IDENTITY_CHAIN','DEBTS_CLEAR'),
    'COMPARISON':('PRODUCER_STRUCTURE','ATTENTION_STRUCTURE','TAIL_STRUCTURE',
        'PRODUCER_DIAGNOSTIC_ONLY','ATTENTION_DIAGNOSTIC_ONLY','LEGACY_CACHE_STRUCTURE',
        'LEGACY_CACHE_ALIAS_TYPES','OFFICIAL_KV_COPY_TYPE','LEGACY_CROSS_ORACLE_FLAG_TYPE',
        'COPY_STRUCTURE','OFFICIAL_COPY_AGREEMENT','CACHE_NUMERIC_STRUCTURE',
        *(name+'_'+gate for name in ('CACHE_K','CACHE_V') for gate in
          ('FINITE','ELEMENT_COUNT','ORIGIN','VERDICT_CONTRACT','LIMITS','VERDICT_AGREEMENT',
           'METRICS_VALID','POLICY_AGREEMENT'))),
    'NUMERIC':tuple(spec[0] for spec in NODE_SPECS),
    'MACS':('OBSERVED_USEFUL','OBSERVED_EXECUTED'),
    'RESOURCES':tuple(spec[0] for spec in RESOURCE_GATES)}
DIAGNOSTIC_GATES = {group:tuple(row[1] for row in DIRECT_GATES if row[0]==group)+EXTRA_GATES.get(group,())
                    for group in DIAGNOSTIC_GROUPS}


# These schemas are immutable public enums, not discovered receipt strings.
ORIGINAL_GATE_SCHEMA = dict(DIAGNOSTIC_GATES)
ORIGINAL_DIRECT_GATES = DIRECT_GATES
DIAGNOSTIC_IDENTITIES = frozenset(('projection','kernel','partial','n0_row','weights',
    'original_a_payload','resident_scratch','resident_storage'))
DIAGNOSTIC_DEBTS = frozenset(('exact64_active','exact64_not_idle','exact64_poison','exact64_request',
    'exact64_result','exact64_kernel_not_idle','shared_a_guard_lease','shared_a_route_active',
    'shared_a_route_fault','shared_a_owner','shared_a_pending','shared_a_hold','shared_a_valid_lines',
    'attention_local_pending','attention_local_request','attention_deferred_finish'))
POSTSEAL_STAGES = ('LOCAL_GATE_ERROR','PROPAGATED_GATE_ERROR','UPSTREAM_N1_ERROR')
POSTSEAL_LIMITS = dict(inner_seconds=120,outer_seconds=122,cpu_seconds=120,
    rss_bytes=2147483648,file_bytes=33554432,output_bytes=67108864)
NEW_DIRECT_GATES = tuple(
    ('DIAGNOSTIC_SCOPE',receipt.upper()+'_'+gate,receipt,(field,),expected)
    for receipt in ('report','launch') for gate,field,expected in (
        ('SCOPE','scope','DIAGNOSTIC_SOFTWARE_OWNER'),('PERFORMANCE','performance','NO_GO'),
        ('HARDWARE_MAPPING','hardware_mapping','NOT_IMPLEMENTED'),
        ('NO_CHISEL_PASS','chisel_full_prefill_pass',False),
        ('NUMERIC_PASS','diagnostic_numeric_pass',True),
        ('SEALED','diagnostic_acceptance_sealed',True))) + (
    ('DIAGNOSTIC_SCOPE','NO_CURRENT_CHISEL_MODEL','report',('model_corresponds_to_current_chisel',),False),
    ('DIAGNOSTIC_SCOPE','NO_EDA','report',('eda_executed',),False),
    ('RETENTION','VERIFIED_BEFORE_SEAL','report',('local_retention_verified_before_seal',),True),
    ('RETENTION','VERIFIED_AFTER_COMPARISON','report',('local_retention_verified_after_comparison',),True))
DIRECT_GATES += NEW_DIRECT_GATES
NEW_GATES = {
    'DIAGNOSTIC_SCOPE': tuple(r[1] for r in NEW_DIRECT_GATES if r[0]=='DIAGNOSTIC_SCOPE'),
    'DIAGNOSTIC_LIVE': ('IDENTITY_CHAIN','PC12_DEBTS_CLEAR','FINAL_DEBTS_CLEAR','PUBLIC_SHARED_A_ROUTE'),
    'DIAGNOSTIC_ACCOUNTING': ('EXACT64_OWNER_TERMINALS','EXACT64_SEPARATE_TOTALS','ORIGINAL_V_TOTALS',
        'MATRIX_ACTUAL_COUNTS','TAIL_ACTUAL_COUNTS','WHOLE_FMA_RECONCILIATION','NO_INVENTED_MATRIX_WORK'),
    'RETENTION': ('VERIFIED_BEFORE_SEAL','VERIFIED_AFTER_COMPARISON','COMPLETE_PRIVATE_INVENTORY'),
    'POSTSEAL': ('SEALED_MAIN_ELIGIBLE','RECEIPT_CONTRACT','CONTROL_BIT_EXACT','TWO_OFFICIAL_CALLS',
        'SAME_ACTUAL_SEAL','SAME_FRESH_REFERENCE','SAME_RUNTIME','SOURCE_BINDING',
        'NATIVE_COMPARISON_CONTRACT','RESOURCES')}
DIAGNOSTIC_GROUPS += tuple(NEW_GATES)
DIAGNOSTIC_GATES.update(NEW_GATES)


def _diagnostic_identity(report):
    before=report.get('diagnostic_identity_initial');after=report.get('diagnostic_identity_final')
    if type(before) is not dict or set(before)!=DIAGNOSTIC_IDENTITIES or not same(before,after):return False
    payload=before['original_a_payload']
    return (type(payload) is list and len(payload)==2 and all(integer(v) and v>0 for v in payload) and
        all(integer(v) and v>0 for k,v in before.items() if k!='original_a_payload'))


def _diagnostic_debts(report,field):
    value=report.get(field)
    return type(value) is dict and set(value)==DIAGNOSTIC_DEBTS and all(v is False for v in value.values())


def _checked(fn):
    # Receipt corruption is a failed fixed boolean, never an exception payload.
    try:return bool(fn())
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,AttributeError):return False


def _exact64_owners(report):
    records=report['exact64_projections']
    need(type(records) is list and len(records)==2,'two original owners')
    for r,(pc,width) in zip(records,((1,1536),(4,256))):
        job=r['job'];terminal=r['terminal'];counts=r['kernel_delta'];delta=r['matrix_counter_delta']
        need(integer(job.get('tag')) is not None and job['tag']&65535==pc and
            all(type(job.get(k)) is int for k in ('m','n','k')),'canonical original job')
        need(type(counts) is dict and set(counts)=={'fmas','adds','tiles_started'} and
            all(integer(v) is not None for v in counts.values()),'actual independent kernel counters')
        need(type(delta) is dict and all(type(k) is str and integer(v) is not None for k,v in delta.items()),'actual matrix deltas')
        need(all(delta.get(k)==1 and type(delta.get(k)) is int for k in ('owner_acquires','owner_responses','owner_releases')) and
            all(v==0 for k,v in delta.items() if k not in ('owner_acquires','owner_responses','owner_releases')),
            'only serialized Matrix reservation, never Matrix arithmetic')
        for field in ('actual_dense_fma_calls_delta','actual_normal_fma_calls_delta','partial_bytes','tiles_output_acked'):
            need(integer(r.get(field)) is not None,'canonical actual owner counts')
        need(all(integer(terminal.get(k)) is not None for k in ('useful_macs','executed_macs','write_bytes')),
            'canonical actual Host terminal')
        need(type(r['memory']) is dict and all(integer(v) is not None for v in r['memory'].values()),'actual accepted memory')
        fence=r['final_ack_fence']
        need(type(fence['held_ticks']) is int and integer(fence.get('final_ack_tick')) is not None and
            integer(fence.get('terminal_tick')) is not None and fence['terminal_tick']>fence['final_ack_tick'],
            'actual final ACK ordering')
        driver=r['driver_counts'];accepted=r['accepted'];reads=128*(96+width//64*3072);writes=128*width//16
        need(all(integer(driver.get(k))==v for k,v in dict(job_fire=1,response_fire=1,
            memory_fire=reads+writes,memory_response_fire=reads+writes,final_ack_stall=5).items()),
            'original Host and owner handshake counts')
        need(all(integer(accepted.get(k))==v for k,v in dict(read_requests=reads,read_responses=reads,
            write_requests=writes,write_acks=writes,responses=reads+writes,owner_results=1).items()),
            'exact64 accepted response and ACK coverage')
        need(r.get('same_owner_and_banks') is True and r.get('model_ticks_are_hardware_cycles') is False and
            r.get('hardware_cycles','missing') is None and r.get('status','missing') is None and
            integer(r.get('write_bytes'))==128*width*4,'diagnostic owner terminal scope')
    return same(accounting.exact64_totals(records),accounting.EXACT_EXPECTED)


def _shared_a(report):
    row=report['shared_a_route'];publication=row['publication'];events=row['loan_events']
    return (row.get('active') is False and row.get('fault','missing') is None and
        row.get('shared_payload_identity_unchanged') is True and row.get('same_dense_tile_attention_banks') is True and
        row.get('payload_bytearray_allocated') is False and row.get('production_public_checkpoint_executed') is True and
        row.get('authority')=='ACTUAL_PUBLIC_PC9_HANDSHAKES' and row.get('scope')=='DIAGNOSTIC_SOFTWARE_OWNER' and
        row.get('performance')=='NO_GO' and row.get('hardware')=='NOT_IMPLEMENTED' and
        row.get('rtl_executed') is False and row.get('model_edges_are_hardware_cycles') is False and
        integer(events.get('loans'))==1 and integer(events.get('releases'))==1 and
        integer(events.get('edges')) is not None and events['edges']>0 and
        all(integer(events.get(k,0))==0 for k in ('faults','route_faults','faulted_terminal_lease_retained')) and
        publication.get('authority')=='ACTUAL_PUBLIC_PC9_HANDSHAKES' and
        publication.get('validation')=='FULL_ENTRY_AND_RELEASE_CONSTANT_SIZE_CONTINUATION' and
        publication.get('original_physical_write_guard') is True and
        integer(publication['counts'].get('full_checks')) is not None and publication['counts']['full_checks']>=2 and
        integer(publication['counts'].get('fast_checks')) is not None and publication['counts']['fast_checks']>=2)


def _matrix_counts(report):
    expected=accounting.WHOLE_EXPECTED;matrix=report['matrix'];counts=matrix['counters']
    return (integer(counts.get('dense_steps'))==expected['dense_steps'] and
        integer(counts.get('normal_steps'))==expected['normal_steps'] and
        integer(matrix.get('dense_fma_calls'))==expected['dense_fma'] and
        integer(matrix.get('normal_fma_calls'))==expected['normal_fma'] and
        integer(report['statistics'].get('full_fixed_array_issued_cell_opportunities'))==expected['opportunities'])


def _tail_counts(report):
    row=report['whole_schedule_prediction_and_observation']
    return (same(row['predicted'],accounting.WHOLE_EXPECTED) and all(integer(row['observed_tail'].get(k))==v
        for k,v in dict(dense_steps=1363968,dense_groups=162,dense_results=800,
            owner_acquires=114,owner_releases=114,dense_seed_acks=144).items()))


def _reconciled(report):
    matrix=report['matrix'];terminal=report['execution']['host']['launch_result'];whole=report['whole_schedule_prediction_and_observation']
    exact=report['observed_exact64_qk_totals']
    return (same(exact,accounting.EXACT_EXPECTED) and same(whole['exact64_software'],exact) and
        all(integer(matrix.get(k)) is not None for k in ('dense_fma_calls','normal_fma_calls')) and
        matrix['dense_fma_calls']+matrix['normal_fma_calls']+exact['fmas']==integer(terminal.get('executed_macs')))


def _no_fake_matrix(report):
    row=report['whole_schedule_prediction_and_observation']
    return (integer(row.get('exact64_matrix_stream_steps'))==0 and row.get('exact64_tree_adds_are_macs') is False and
        row.get('full_fixed_array_opportunities_scope')=='ORIGINAL_MATRIX_EVENTS_ONLY' and
        row.get('performance')=='NO_GO' and row.get('hardware_mapping')=='NOT_IMPLEMENTED' and
        row.get('scope')=='DIAGNOSTIC_SOFTWARE_OWNER' and row.get('hardware_cycles','missing') is None and
        row.get('hardware_utilization','missing') is None)


def _retained(report):
    row=report['local_retention'];inventory=row['inventory'];sealed=report['sealed_actual_outputs']
    expected={'actual_'+n+'.f32le' for n in retention.ACTUAL_NAMES|{'silu'}}|{'attention_observation/summary.json'}|{
        'attention_observation/'+n+suffix for n in retention.ATTENTION_NAMES for suffix in ('.u32le','.presence','.count.u16le')}
    if (type(row.get('schema')) is not int or row['schema']!=1 or
        row.get('status')!='LOCAL_ACTUALS_RETAINED_BEFORE_ORACLE' or row.get('scope')!='DIAGNOSTIC_SOFTWARE_OWNER' or
        row.get('local_only') is not True or row.get('upload_authorized') is not False or
        row.get('oracle_payloads_read') is not False or row.get('reference_operands_in_execution') is not False or
        not same(row.get('propagation_inputs_retained'),['v','att','o','r','n1','gate','up']) or
        type(inventory) is not dict or set(inventory)!=expected or len(inventory)!=51 or
        type(sealed) is not dict or set(sealed)!=retention.ACTUAL_NAMES|{'silu'}):return False
    for spec in inventory.values():
        if (type(spec) is not dict or set(spec)!={'bytes','sha256'} or
            integer(spec['bytes']) is None or spec['bytes']==0 or type(spec['sha256']) is not str or
            re.fullmatch('[0-9a-f]{64}',spec['sha256']) is None):return False
    return all(same(inventory['actual_'+n+'.f32le'],spec) for n,spec in sealed.items())


def _terminal_contract(report,launch):
    numeric=report.get('diagnostic_numeric_pass')
    return (type(numeric) is bool and _comparison(report,require_pass=False) and
        all(report.get(k) is numeric for k in ('official_observed_node_pass','diagnostic_acceptance_sealed')) and
        report.get('status')==(PASS if numeric else FAIL) and launch.get('child_status')==report.get('status') and
        launch.get('status')==('PASS' if numeric else 'FAILED') and
        integer(launch.get('returncode'))==(0 if numeric else 1) and
        all(launch.get(k) is numeric for k in ('diagnostic_numeric_pass','diagnostic_acceptance_sealed')) and
        numeric is _comparison(report))


def _postseal_contract(postseal,report):
    return (type(postseal.get('schema')) is int and postseal['schema']==1 and
        postseal.get('status')=='POSTSEAL_GATE_DIAGNOSTIC_COMPLETE' and
        postseal.get('scope')=='POSTSEAL_GATE_ERROR_ISOLATION_ONLY' and
        postseal.get('performance')=='NO_GO' and postseal.get('hardware_mapping')=='NOT_IMPLEMENTED' and
        postseal.get('fullblock_pass') is False and postseal.get('local_only') is True and
        postseal.get('upload_authorized') is False and
        type(postseal.get('original_diagnostic_numeric_pass')) is bool and
        postseal['original_diagnostic_numeric_pass'] is report.get('diagnostic_numeric_pass') and
        same(postseal.get('comparison_order'),list(POSTSEAL_STAGES)))


def _postseal_comparisons(postseal):
    rows=postseal['comparisons']
    if type(rows) is not dict or set(rows)!=set(POSTSEAL_STAGES):return False
    if postseal.get('native_metric_authority')!='scripts/qwen2_layer0_model_gate.py:compare/stage_verdict':return False
    if not same(obj(postseal.get('original_numerical_policy')).get('operator'),dict(max_abs=0.03125,mean_abs=0.005)):return False
    for row in rows.values():
        if type(row) is not dict or set(row)!={'metrics','verdict','official_numeric_pass'}:return False
        verdict=obj(row.get('verdict'));metrics=obj(row.get('metrics'));flag=row['official_numeric_pass']
        maximum=number(metrics.get('max_abs'));mean=number(metrics.get('mean_abs'))
        if (type(flag) is not bool or verdict.get('passed') is not flag or
            verdict.get('contract')!='spec/numerical_contract.md:operator' or
            not same(verdict.get('limits'),dict(max_abs=0.03125,mean_abs=0.005)) or
            maximum is None or mean is None or (maximum<=0.03125 and mean<=0.005) is not flag):return False
    return True


def _postseal_resources(postseal):
    return (same(postseal.get('resource_limits'),POSTSEAL_LIMITS) and
        number(postseal.get('host_wall_seconds')) is not None and postseal['host_wall_seconds']<=120 and
        number(postseal.get('host_cpu_seconds')) is not None and postseal['host_cpu_seconds']<=120 and
        integer(postseal.get('peak_rss_bytes')) is not None and postseal['peak_rss_bytes']<=2147483648)


def _extend_diagnostics(summary,report,launch,postseal,source_digest):
    result=summary['acceptance_diagnostics'];gates=result['gates']
    checks={
        'DIAGNOSTIC_LIVE':(
            ('IDENTITY_CHAIN',('diagnostic_identity_initial','diagnostic_identity_final'),lambda:_diagnostic_identity(report)),
            ('PC12_DEBTS_CLEAR',('diagnostic_debts_at_pc12',),lambda:_diagnostic_debts(report,'diagnostic_debts_at_pc12')),
            ('FINAL_DEBTS_CLEAR',('diagnostic_backend_debts',),lambda:_diagnostic_debts(report,'diagnostic_backend_debts')),
            ('PUBLIC_SHARED_A_ROUTE',('shared_a_route',),lambda:_shared_a(report))),
        'DIAGNOSTIC_ACCOUNTING':(
            ('EXACT64_OWNER_TERMINALS',('exact64_projections',),lambda:_exact64_owners(report)),
            ('EXACT64_SEPARATE_TOTALS',('observed_exact64_qk_totals',),lambda:same(report['observed_exact64_qk_totals'],accounting.EXACT_EXPECTED)),
            ('ORIGINAL_V_TOTALS',('observed_v_totals',),lambda:same(report['observed_v_totals'],accounting.V_EXPECTED)),
            ('MATRIX_ACTUAL_COUNTS',('matrix','statistics'),lambda:_matrix_counts(report)),
            ('TAIL_ACTUAL_COUNTS',('whole_schedule_prediction_and_observation',),lambda:_tail_counts(report)),
            ('WHOLE_FMA_RECONCILIATION',('matrix','execution','observed_exact64_qk_totals','whole_schedule_prediction_and_observation'),lambda:_reconciled(report)),
            ('NO_INVENTED_MATRIX_WORK',('whole_schedule_prediction_and_observation',),lambda:_no_fake_matrix(report))),
        'RETENTION':(('COMPLETE_PRIVATE_INVENTORY',('local_retention','sealed_actual_outputs'),lambda:_retained(report)),)}
    for group,rows in checks.items():
        for gate,fields,check in rows:gates[group][gate]=_checked(check) if all(k in report for k in fields) else None
    # A complete, coherent numerical rejection is eligible for error isolation.
    # Ignore only positive numerical acceptance gates, never structural evidence.
    numeric_only={('LAUNCH',k) for k in ('STATUS','RETURN_CODE','CHILD_STATUS')}|{
        ('REPORT',k) for k in ('STATUS','OBSERVED_NODE_PASS')}|{
        ('DIAGNOSTIC_SCOPE',k) for k in ('REPORT_NUMERIC_PASS','REPORT_SEALED','LAUNCH_NUMERIC_PASS','LAUNCH_SEALED')}
    structural=all(value is True for group,rows in gates.items() if group not in ('NUMERIC','POSTSEAL')
        for gate,value in rows.items() if (group,gate) not in numeric_only)
    p=obj(postseal);post=gates['POSTSEAL']
    post['SEALED_MAIN_ELIGIBLE']=structural and _terminal_contract(report,launch) if report and launch else None
    post['RECEIPT_CONTRACT']=_checked(lambda:_postseal_contract(p,report)) if p else None
    for gate,field,expected in (('CONTROL_BIT_EXACT','control_bit_exact',True),
        ('TWO_OFFICIAL_CALLS','official_gate_invocations',2),('SAME_ACTUAL_SEAL','same_actual_seal_verified',True),
        ('SAME_FRESH_REFERENCE','same_fresh_reference_verified',True),('SAME_RUNTIME','same_runtime_verified',True),
        ('SOURCE_BINDING','source_closure_sha256',source_digest)):
        post[gate]=_expected(_field(p,(field,)),expected)
    post['NATIVE_COMPARISON_CONTRACT']=_checked(lambda:_postseal_comparisons(p)) if 'comparisons' in p else None
    post['RESOURCES']=_checked(lambda:_postseal_resources(p)) if p else None
    # A bit-exact official control is mandatory before exposing isolation values.
    if all(value is True for value in post.values()):
        for node in result['postseal_nodes']:
            row=p['comparisons'][node['stage']];metrics=row['metrics']
            node.update(official_numeric_pass=row['official_numeric_pass'],max_abs=number(metrics['max_abs']),
                mean_abs=number(metrics['mean_abs']))
    result['failure_stages']=[group for group in DIAGNOSTIC_GROUPS if any(
        value is not True for value in gates[group].values())]


def _field(value, path):
    for key in path:
        if type(value) is not dict or key not in value:
            return _MISSING
        value=value[key]
    return value


def _expected(value, expected):
    # null means missing/invalid evidence; false means a present gate failed.
    # Explicit-null requirements have no other valid value and do not echo it.
    if value is _MISSING:
        return None
    if expected is None:
        return value is None
    if type(value) is not type(expected):
        return None
    return value==expected


def _boolean(value):
    return value if type(value) is bool else None


def _keys(value, expected):
    return set(value)==set(expected) if type(value) is dict else None


def _all_known(values):
    values=tuple(values)
    return False if False in values else None if None in values else True


def _diagnostic_empty():
    return dict(schema=1,
        gates={group:{gate:None for gate in DIAGNOSTIC_GATES[group]} for group in DIAGNOSTIC_GROUPS},
        nodes=[dict(stage=spec[0],official_numeric_pass=None,max_abs=None,mean_abs=None) for spec in NODE_SPECS],
        postseal_nodes=[dict(stage=stage,official_numeric_pass=None,max_abs=None,mean_abs=None) for stage in POSTSEAL_STAGES],
        failure_stages=list(DIAGNOSTIC_GROUPS))


def _acceptance_diagnostics(report, launch, summary, source_digest):
    """Read already-computed receipts; never recompute metrics or set acceptance.

    Every original conjunct has its corresponding fixed gate below. Compound private
    identity/source/debt checks yield only their existing boolean, never records.
    Resource gates combine the original presence and budget predicates. Node
    metrics are optional evidence, not additional or replacement acceptance gates.
    """
    result=_diagnostic_empty();gates=result['gates']
    receipts=dict(report=report,launch=launch,summary=summary)
    for group,gate,receipt,path,expected in DIRECT_GATES:
        gates[group][gate]=_expected(_field(receipts[receipt],path),
            source_digest if expected is _SOURCE_DIGEST else expected)
    gates['SOURCE']['UNCHANGED_RECORDS']=(_source_records(report) if all(k in report for k in
        ('source_sha256_before','source_sha256_after')) else None)
    gates['LIVE']['IDENTITY_CHAIN']=(bool(_same_live(report)) if all(k in report for k in
        ('same_live_identity_initial','same_live_identity_at_pc12','same_live_identity_final')) else None)
    gates['LIVE']['DEBTS_CLEAR']=_debts(report) if 'backend_debts' in report else None
    host=obj(obj(report.get('execution')).get('host'));completions=host.get('completions')
    gates['HOST']['COMPLETION_SEQUENCE']=(len(completions)==21 and all(
        type(c) is dict and type(c.get('pc')) is int and c['pc']==i and c.get('status','missing') is None
        for i,c in enumerate(completions)) if type(completions) is list else None)
    gates['HOST']['EVENT_SEQUENCE']=(same(host['events'],list(range(22))) if 'events' in host else None)
    comparison=gates['COMPARISON']
    for group,field,names,diagnostic in (
        ('PRODUCER','producer_comparisons',('n0','qr','q','kr','k','v'),('qraw','kraw','vraw')),
        ('ATTENTION','attention_comparisons',('scores','logits','prob','pv','att'),('softmax_fp32',)),
        ('TAIL','tail_comparisons',('o','r','n1','gate','up','silu','act','down','y'),())):
        comparison[group+'_STRUCTURE']=_keys(report.get(field),(*names,*diagnostic))
        if diagnostic:
            comparison[group+'_DIAGNOSTIC_ONLY']=_all_known(_expected(
                _field(report,(field,name,'official_numeric_pass')),None) for name in diagnostic)
    legacy=report.get('cold_cache_comparisons');copy=obj(report.get('same_run_cache_comparison'))
    numeric=report.get('same_run_cache_original_comparisons')
    comparison['LEGACY_CACHE_STRUCTURE']=_keys(legacy,('cache_k','cache_v'))
    comparison['LEGACY_CACHE_ALIAS_TYPES']=_all_known(
        True if type(_field(legacy,(name,'exact_cold_alias'))) is bool else None for name in ('cache_k','cache_v'))
    official=_field(report,('official_kv_comparison','official_kv_exact_copy'))
    comparison['OFFICIAL_KV_COPY_TYPE']=True if type(official) is bool else None
    comparison['LEGACY_CROSS_ORACLE_FLAG_TYPE']=(True if type(report.get('legacy_cross_oracle_contract_pass')) is bool else None)
    comparison['COPY_STRUCTURE']=_keys(report.get('same_run_cache_comparison'),
        ('scope','same_live_exact_copy','official_kv_exact_copy','numerical_acceptance_claimed',
         'whole_block_acceptance_claimed','historical_run_upgraded'))
    comparison['OFFICIAL_COPY_AGREEMENT']=(copy.get('official_kv_exact_copy') is official
        if type(official) is bool and type(copy.get('official_kv_exact_copy')) is bool else None)
    comparison['CACHE_NUMERIC_STRUCTURE']=_keys(numeric,('cache_k','cache_v'))
    for name in ('cache_k','cache_v'):
        row=obj(obj(numeric).get(name));verdict=obj(row.get('verdict'));metrics=obj(row.get('metrics'))
        prefix=name.upper()+'_'
        for gate,value,expected in (
            ('FINITE',_field(row,('finite',)),True),
            ('ELEMENT_COUNT',_field(row,('observed_elements',)),32768),
            ('ORIGIN',_field(row,('origin',)),'final sealed physical KV subspan'),
            ('VERDICT_CONTRACT',_field(verdict,('contract',)),'spec/numerical_contract.md:operator')):
            comparison[prefix+gate]=_expected(value,expected)
        comparison[prefix+'LIMITS']=(same(verdict['limits'],dict(max_abs=0.03125,mean_abs=0.005))
            if 'limits' in verdict else None)
        official_pass=_boolean(row.get('official_numeric_pass'));verdict_pass=_boolean(verdict.get('passed'))
        comparison[prefix+'VERDICT_AGREEMENT']=(official_pass is verdict_pass
            if official_pass is not None and verdict_pass is not None else None)
        maximum=number(metrics.get('max_abs'));mean=number(metrics.get('mean_abs'))
        comparison[prefix+'METRICS_VALID']=True if maximum is not None and mean is not None else None
        # Identical existing receipt-consistency check in _comparison(), not a
        # new numerical calculation, tolerance, comparator or acceptance source.
        comparison[prefix+'POLICY_AGREEMENT']=((maximum<=0.03125 and mean<=0.005) is verdict_pass
            if maximum is not None and mean is not None and verdict_pass is not None else None)
    for node,(stage,path,flag,metric_path) in zip(result['nodes'],NODE_SPECS):
        row=_field(report,path);metrics=_field(row,metric_path)
        node['official_numeric_pass']=_boolean(_field(row,(flag,)))
        node['max_abs']=number(_field(metrics,('max_abs',)))
        # The existing softmax sum receipt has no mean; never invent one.
        node['mean_abs']=None if stage=='SOFTMAX_SUM' else number(_field(metrics,('mean_abs',)))
        gates['NUMERIC'][stage]=node['official_numeric_pass']
    for gate,field in (('OBSERVED_USEFUL','useful_macs'),('OBSERVED_EXECUTED','executed_macs')):
        observed=integer(_field(report,('whole_schedule_prediction_and_observation','actual_'+field)))
        gates['MACS'][gate]=(observed==summary[field] if observed is not None and summary[field] is not None else None)
    for gate,field,limit in RESOURCE_GATES:
        value=summary[field]
        gates['RESOURCES'][gate]=None if value is None else limit is None or value<=limit
    result['failure_stages']=[group for group in DIAGNOSTIC_GROUPS if any(
        value is not True for value in gates[group].values())]
    return result


def _validate_diagnostics(value):
    need(type(value) is dict and set(value)=={'schema','gates','nodes','postseal_nodes','failure_stages'}, 'exact diagnostic keys')
    need(type(value['schema']) is int and value['schema']==1, 'diagnostic schema')
    gates=value['gates']
    need(type(gates) is dict and set(gates)==set(DIAGNOSTIC_GROUPS), 'fixed diagnostic groups')
    for group in DIAGNOSTIC_GROUPS:
        need(type(gates[group]) is dict and set(gates[group])==set(DIAGNOSTIC_GATES[group]), 'fixed diagnostic gates')
        need(all(v is None or type(v) is bool for v in gates[group].values()), 'boolean diagnostic gates')
    nodes=value['nodes']
    need(type(nodes) is list and len(nodes)==len(NODE_SPECS), 'fixed diagnostic nodes')
    for node,spec in zip(nodes,NODE_SPECS):
        need(type(node) is dict and set(node)=={'stage','official_numeric_pass','max_abs','mean_abs'}, 'exact diagnostic node keys')
        need(type(node['stage']) is str and node['stage']==spec[0], 'fixed diagnostic stage')
        need(node['official_numeric_pass'] is None or type(node['official_numeric_pass']) is bool, 'boolean node pass')
        need(node['official_numeric_pass'] is gates['NUMERIC'][spec[0]], 'node gate consistency')
        for key in ('max_abs','mean_abs'):
            need(node[key] is None or number(node[key]) is not None, 'finite diagnostic metric')
        need(spec[0]!='SOFTMAX_SUM' or node['mean_abs'] is None, 'no invented softmax mean')
    post=value['postseal_nodes']
    need(type(post) is list and len(post)==3, 'fixed postseal nodes')
    valid=all(v is True for v in gates['POSTSEAL'].values())
    for node,stage in zip(post,POSTSEAL_STAGES):
        need(type(node) is dict and set(node)=={'stage','official_numeric_pass','max_abs','mean_abs'} and node['stage']==stage, 'fixed postseal stage')
        need(node['official_numeric_pass'] is None or type(node['official_numeric_pass']) is bool, 'safe postseal verdict')
        for key in ('max_abs','mean_abs'):need(node[key] is None or number(node[key]) is not None, 'safe postseal metric')
        need(valid or all(node[k] is None for k in ('official_numeric_pass','max_abs','mean_abs')), 'invalid isolation is not evidence')
        if valid:
            need(type(node['official_numeric_pass']) is bool and all(number(node[k]) is not None for k in ('max_abs','mean_abs')), 'complete valid isolation evidence')
            need((node['max_abs']<=0.03125 and node['mean_abs']<=0.005) is node['official_numeric_pass'], 'native isolation policy consistency')
    expected=[group for group in DIAGNOSTIC_GROUPS if any(v is not True for v in gates[group].values())]
    need(same(value['failure_stages'],expected), 'fixed diagnostic failure stages')


def _empty(source_digest):
    return dict(schema=1, scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
        fullblock_pass=False,acceptance_sealed=False,chisel_full_prefill_pass=False,
        model_corresponds_to_current_chisel=False,diagnostic_numeric_pass=False,
        diagnostic_acceptance_sealed=False,postseal_valid=False, status='INCOMPLETE',
        reference_contract='official-ast-ci-aten-avx2-reference-v1',cache_contract='sealed-same-live-cold-cache-v1',
        source_digest=source_digest, failure_stage='UNKNOWN', exception_class='UNKNOWN',
        public_completions=None, owner_jobs=None, accepted_launch_results=None,
        host_wall_seconds=None, host_cpu_seconds=None, supervisor_wall_seconds=None,
        peak_rss_bytes=None, sampled_group_rss_bytes=None, output_bytes=None, log_bytes=None,
        useful_macs=None, executed_macs=None, efficiency_kind='SOFTWARE_OPERATION_EFFICIENCY',
        software_operation_efficiency=None, hardware_cycles=None, hardware_utilization=None,
        hardware_duty=None, reference_arithmetic_executed=None, official_reference_comparison_executed=False,
        dut_software_executed=None, rtl_executed=None, full_29_node_acceptance=False,
        full_official_forward_executed=False, same_live_guards_passed=False, debt_guards_passed=False,
        acceptance_diagnostics=_diagnostic_empty())


def summarize(report, launch, *, source_digest, postseal=None):
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
    result['acceptance_diagnostics']=_acceptance_diagnostics(report,launch,result,source_digest)
    _extend_diagnostics(result,report,launch,postseal,source_digest)
    diagnostics=result['acceptance_diagnostics']
    main_pass=all(v is True for group,rows in diagnostics['gates'].items()
                  if group!='POSTSEAL' for v in rows.values())
    result['diagnostic_numeric_pass']=main_pass
    result['postseal_valid']=all(v is True for v in diagnostics['gates']['POSTSEAL'].values())
    passed=main_pass
    result['diagnostic_acceptance_sealed']=passed
    if passed:
        result.update(status=PASS,failure_stage=None,exception_class=None)
    else:
        if launch.get('status') in ('FAILED','PASS') or report.get('status') in ('FAILED',PASS,FAIL):
            result['status']=FAIL
        stage=report.get('failure_stage')
        result['failure_stage']=STAGE_MAP.get(stage,'UNKNOWN') if type(stage) is str else 'UNKNOWN'
        error=report.get('original_error_type')
        result['exception_class']=error if type(error) is str and error in EXCEPTIONS else 'UNKNOWN'
    validate_summary(result)
    return result


def validate_summary(value):
    need(type(value) is dict and set(value)==set(_empty('0'*64)), 'exact safe summary keys')
    need(type(value['schema']) is int and value['schema']==1 and value['scope']=='DIAGNOSTIC_SOFTWARE_OWNER', 'summary schema/scope')
    need(value['status'] in (PASS,FAIL,'INCOMPLETE'), 'summary status')
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
    need(value['performance']=='NO_GO' and value['hardware_mapping']=='NOT_IMPLEMENTED', 'fixed diagnostic scope')
    for key in ('fullblock_pass','acceptance_sealed','chisel_full_prefill_pass','model_corresponds_to_current_chisel'):
        need(value[key] is False, 'no formal or current Chisel acceptance')
    for key in ('diagnostic_numeric_pass','diagnostic_acceptance_sealed','postseal_valid'):
        need(type(value[key]) is bool, 'diagnostic boolean')
    _validate_diagnostics(value['acceptance_diagnostics'])
    gates=value['acceptance_diagnostics']['gates']
    main_pass=all(v is True for group,rows in gates.items() if group!='POSTSEAL' for v in rows.values())
    postseal_valid=all(v is True for v in gates['POSTSEAL'].values())
    need(value['diagnostic_numeric_pass'] is main_pass, 'main diagnostic gate consistency')
    need(value['postseal_valid'] is postseal_valid, 'postseal gate consistency')
    need(value['diagnostic_acceptance_sealed'] is value['diagnostic_numeric_pass'], 'sealed diagnostic consistency')
    need((value['status']==PASS) is value['diagnostic_acceptance_sealed'], 'diagnostic status consistency')


def collect(*, source_digest=None, execute=False):
    need(type(execute) is bool, 'execute must be boolean')
    if not execute:
        return dict(status='NOT_EXECUTED', numeric_execution_allowed=False)
    need(type(source_digest) is str and re.fullmatch('[0-9a-f]{64}',source_digest), 'externally supplied source digest')
    need(ROOT==CI_ROOT and ROOT.resolve()==ROOT, 'fixed CI aggregate root')
    need(closure.digest(ROOT)==source_digest, 'source closure drift')
    records=[];errors=[]
    for relative in (RESULT,LAUNCH,POSTSEAL):
        try:records.append(_read(relative))
        except (OSError,ValueError,UnicodeError) as error:
            records.append({});errors.append(type(error).__name__)
    result=summarize(*records[:2],source_digest=source_digest,postseal=records[2])
    if errors and not result['diagnostic_numeric_pass']:
        result.update(status=FAIL if records[1].get('status') in ('FAILED','PASS') or
                      records[0].get('status') in ('FAILED',FAIL,PASS) else 'INCOMPLETE',
                      failure_stage='AGGREGATION',
                      exception_class=errors[0] if errors[0] in EXCEPTIONS else 'UNKNOWN')
    need(closure.digest(ROOT)==source_digest, 'source closure changed during aggregate')
    validate_summary(result)
    return result
