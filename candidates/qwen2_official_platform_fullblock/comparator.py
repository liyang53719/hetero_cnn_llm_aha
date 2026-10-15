"""New post-seal cache object contract; all original numerical comparisons retained.

The old result and its cross-oracle exact-copy failures remain honest diagnostics.
Only this new result recomputes acceptance with final same-run sealed KV bytes.
"""
import hashlib
import json
from pathlib import Path
from candidates.qwen2_live_fullblock_model_m128 import compare as old
from candidates.qwen2_cold_cache_contract_candidate import compare as cache
CONTRACT='sealed-same-live-cold-cache-v1'
REFERENCE_CONTRACT='official-ast-ci-aten-avx2-reference-v1'
GROUPS=(('producer_comparisons',{'n0','qr','q','kr','k','v'}),
        ('attention_comparisons',{'scores','logits','prob','pv','att'}),
        ('tail_comparisons',set(old.TAIL)))


def need(ok,message):
    if not ok:raise ValueError(message)


def same_live(report):
    first=report['same_live_identity_initial']
    need(first==report['same_live_identity_at_pc12']==report['same_live_identity_final'],'same live chain required')
    return hashlib.sha256(json.dumps(first,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def checked_cache(report,actual,reference,payloads):
    need(report['actual_outputs_sealed'] is True and report['whole_block_terminal'] is True and
        report['finalfence'] is True and report['execution']['host']['launch_result']['completed']==21,
        'sealed whole-chain comparison only')
    need(report['numerical_policy']['operator']==cache.LIMITS and
        report['numerical_policy']['block']=={'max_abs':0.05,'mean_abs':0.01},'unchanged original error gates')
    identity=same_live(report)
    live={role:actual[name].tobytes() for role,name in (('k','k'),('v','v'),('cache','kv'))}
    sealed=report['sealed_actual_outputs']
    expected={role:sealed[name]['sha256'] for role,name in (('k','k'),('v','v'),('cache','kv'))}
    for role,name in (('k','k'),('v','v'),('cache','kv')):
        need(sealed[name]['bytes']==len(live[role]),'complete final sealed extent')
    producers={r['name']:r for r in report['producers']}
    append=report['kv_append'];job=append['job']
    need(job['kind']=='KvAppend' and job['tag']&0xffff==9 and job['write_bytes']==262144 and
        job['a']==producers['k']['job']['dst'] and job['b']==producers['v']['job']['dst'], 'typed same-chain pc9 binding')
    need(append['bytes']==262144 and append['exact_copy'] is True and append['coverage_64b_beats']==4096 and
        append['physical_counter_delta']['write_ack_bytes']==262144 and
        append['sha256']==expected['cache'] and append['k_sha256']==expected['k'] and
        append['v_sha256']==expected['v'],'final readback must equal the actual admitted pc9 output')
    receipts={}
    for role in ('k','v','cache'):
        if role=='cache':
            ack=append['physical_counter_delta']['write_ack_bytes'];beats=append['coverage_64b_beats'];terminal=report['whole_block_terminal']
        else:
            producer=producers[role]
            need(producer['sha256']==expected[role] and producer['finite'] is True and
                producer['public_completion_retired'] is True,'same sealed producer')
            ack=producer['ack_bytes'];beats=ack//64;terminal=producer['owner_terminal']
        receipts[role]=dict(role=role,run='ci01',live_identity=identity,layout=cache.LAYOUTS[role],
            bytes=len(live[role]),sha256=expected[role],sealed=report['actual_outputs_sealed'],
            terminal=terminal,ack_bytes=ack,ack_64b_beats=beats,
            origin='SEALED_ACTUAL_KV_PHYSICAL_READBACK' if role=='cache' else 'SEALED_ACTUAL_PRODUCER')
    return cache.compare(payloads=live,receipts=receipts,expected_run='ci01',expected_live_identity=identity,
        expected_artifacts=expected,official={name:payloads[name] for name in ('k','v')},
        official_commitments={name:reference['outputs'][name]['sha256'] for name in ('k','v')})


def accepted(result,copy_result,cache_numeric):
    return (all(result[field][name]['official_numeric_pass'] is True for field,names in GROUPS for name in names) and
        result['official_kv_comparison']['official_numeric_pass'] is True and
        result['softmax_probability_sum']['passed'] is True and
        all(row['official_numeric_pass'] is True for row in cache_numeric.values()) and
        copy_result['same_live_exact_copy'] is True)


def official(out,report,capture,actual,silu,reference,payloads,native,np):
    from . import gates
    need(Path(out)==gates.OUTPUT_ROOT/'ci01','single admitted live run namespace')
    # Run the original comparator unchanged, including its diagnostic failures.
    result=old.official(out,report,capture,actual,silu,reference,payloads,native,np)
    legacy_pass=result['official_observed_node_pass']
    corrected=checked_cache(report,actual,reference,payloads)
    need(corrected['official_kv_exact_copy']==result['official_kv_comparison']['official_kv_exact_copy'],
        'original and corrected official exact diagnostics must agree')
    cache_numeric={}
    # Authority remains the exact original native metric implementation, including
    # its FP64 reduction order and uint32 bit-exact semantics. Pure helper metrics
    # (when present) are never numerical acceptance authority.
    raw=actual['kv'].tobytes()
    for name,offset in (('cache_k',0),('cache_v',131072)):
        spec=reference['outputs'][name]
        token=np.frombuffer(payloads[name],dtype='<f4').reshape(spec['shape']).transpose(0,2,1,3).copy().tobytes()
        a=np.frombuffer(raw[offset:offset+131072],dtype='<f4');b=np.frombuffer(token,dtype='<f4')
        need(np.isfinite(a).all() and np.isfinite(b).all(),'finite complete physical cache subspan')
        metrics=native.compare(a,b);verdict=native.stage_verdict(name,metrics,'bf16',report['numerical_policy'])
        need(type(verdict['passed']) is bool,'existing cache BF16 operator policy')
        cache_numeric[name]=dict(metrics=metrics,verdict=verdict,official_numeric_pass=verdict['passed'],
            finite=True,observed_elements=int(a.size),origin='final sealed physical KV subspan')
    passed=accepted(result,corrected,cache_numeric)
    result.update(cache_contract=CONTRACT,reference_contract=REFERENCE_CONTRACT,
        same_run_cache_comparison=corrected,same_run_cache_original_comparisons=cache_numeric,
        legacy_cross_oracle_contract_pass=legacy_pass,
        official_observed_node_pass=passed,fullblock_pass=passed,
        fullblock_pass_scope='fresh public21 software; original BF16 gates plus sealed same-run physical KV exact copy')
    return result
