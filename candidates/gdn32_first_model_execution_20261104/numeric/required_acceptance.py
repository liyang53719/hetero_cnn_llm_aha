"""Full M128 exact-reference acceptance, invoked only by the actual evidence chain.
No tolerance, rounding, route override, model arithmetic, or final RTL qualification.
Pure functions are testable with fixtures; fixture results are never DUT evidence.
"""
import re
SCHEMA='FULL_M128_EXACT_REFERENCE_ACCEPTANCE_V1'
LAYER='CHISEL_EMITTED_SV_NUMERICAL_BACKEND'
HEX=re.compile(r'^[0-9a-f]{64}$')
OUTPUTS=(
 {'y':128*1536*4,'cache_k':128*2*128*4,'cache_v':128*2*128*4,'resident_gate':128*8960*4,'resident_up':128*8960*4},
 {'output':128*1024*2,'history_out':6144*4*2,'state_out':16*128*128*4},
 {'output':128*1024*2,'cache':2*128*2*256*2},
 {'output':128*2048*2,'history_out':8192*4*2,'state_out':32*128*128*4},
 {'output':128*2048*2,'cache':2*128*2*256*2})
EXECUTION=('actual_popen_verified','pre_post_frozen_identity_verified','official_full128_reference_verified','unique_clean_terminal','all_declared_observations_complete','final_acknowledged_writes_verified')

def evaluate(row, *, outer_verified=False):
    missing=[]; failed=[]; checked=[]
    profile=row.get('profile')
    if type(profile) is not int or not 0<=profile<5:
        return dict(schema=SCHEMA,status='INCOMPLETE',numerical_pass=False,missing=['valid_profile'],failed=[],checked=[])
    if row.get('complete_block_tokens')!=128:missing.append('complete_block_tokens_128')
    if row.get('exit_code')!=0:missing.append('native_dut_exit_zero')
    evidence=row.get('execution_evidence',{})
    for key in EXECUTION:
        if evidence.get(key) is not True:missing.append(key)
    if row.get('error_class'):missing.append('consumer_finished_without_exception')
    def comparison(name,record,size,finite=False):
        if not isinstance(record,dict):missing.append(name);return
        if record.get('bytes')!=size or not all(isinstance(record.get(k),str) and HEX.fullmatch(record[k]) for k in ('actual_sha256','expected_layout_sha256')):
            missing.append(name+':full_size_and_hashes');return
        count=record.get('byte_mismatches')
        if type(count) is not int or not 0<=count<=size:missing.append(name+':comparison_count');return
        if finite:
            for key in ('actual_nonfinite_elements','reference_nonfinite_elements'):
                value=record.get(key)
                if type(value) is not int or value<0:missing.append(name+':'+key)
                elif value:failed.append(name+':'+key)
        checked.append(name)
        if count:failed.append(name+':exact_reference_mismatch')
        elif record['actual_sha256']!=record['expected_layout_sha256']:failed.append(name+':contradictory_zero_mismatch_hash')
    comparisons=row.get('comparisons',{})
    for name,size in OUTPUTS[profile].items():comparison(name,comparisons.get(name),size,True)
    def probability_domain(name, diagnostic, elements):
        counts=diagnostic.get('actual_value_counts') if isinstance(diagnostic,dict) else None
        if not isinstance(counts,dict):missing.append(name+':actual_probability_domain_counts');return
        for key in ('nan','positive_infinity','negative_infinity','negative_finite','negative_zero','above_one_finite'):
            count=counts.get(key)
            if type(count) is not int or not 0<=count<=elements:missing.append(name+':domain_count_'+key)
            elif count and key in ('nan','positive_infinity','negative_infinity','negative_finite'):failed.append(name+':probability_domain_violation_'+key)
            elif count and key=='above_one_finite':missing.append(name+':above_one_requires_existing_rounding_chain_diagnosis')
        # Negative zero is retained and counted, not classified as < 0.
    router=row.get('router',{})
    if profile in (3,4):
        for name,size,finite in [('ids',8192,False),('normalized_bf16_weights',2048,True),('bf16_dense_logits',65536,True)]:
            comparison('router.'+name,router.get(name),size,finite)
        raw=router.get('raw_probability_diagnostics',{})
        if raw.get('status')!='COMPARED_DIAGNOSTIC_ONLY' or raw.get('shape')!=[128,256] or raw.get('dtype')!='FP32_LE' or raw.get('coverage')!='EXACT_ONCE_32768':missing.append('raw_fp32_selection_scores')
        full=raw.get('full_probabilities',{})
        if not isinstance(full,dict) or full.get('elements')!=32768 or full.get('bytes')!=131072 or not all(isinstance(full.get(k),str) and HEX.fullmatch(full[k]) for k in ('actual_sha256','reference_sha256')):missing.append('raw_fp32_selection_scores_full_size_hashes')
        probability_domain('router.input_probabilities',full,32768)
        selected=raw.get('actual_selected_output',{})
        if selected.get('status')!='COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY' or selected.get('shape')!=[128,8] or selected.get('score_bytes')!=4096 or selected.get('id_bytes')!=4096 or selected.get('coverage')!='EXACT_ONCE_1024':missing.append('raw_fp32_selected_topk_scores')
        else:
            # Real selector must return the exact bits it accepted for that ID.
            # This is an internal transport contract, NOT Torch softmax equality.
            consistency=selected.get('input_output_score_consistency',{})
            probability_domain('router.selected_probabilities',consistency,1024)
            mismatch=consistency.get('element_mismatches')
            if consistency.get('elements')!=1024 or consistency.get('bytes')!=4096 or type(mismatch) is not int or not 0<=mismatch<=1024:missing.append('selector_input_output_consistency')
            elif mismatch:failed.append('selector_input_output_score_corruption')
            if not all(isinstance(selected.get(k),str) and HEX.fullmatch(selected[k]) for k in ('score_sha256','id_sha256')):missing.append('selector_output_score_and_id_hashes')
            elif selected['score_sha256']!=consistency.get('actual_sha256'):failed.append('selector_output_score_hash_contradiction')
            byte_count=consistency.get('byte_mismatches')
            valid_hashes=all(isinstance(consistency.get(k),str) and HEX.fullmatch(consistency[k]) for k in ('actual_sha256','reference_sha256'))
            if type(byte_count) is not int or not 0<=byte_count<=4096 or not valid_hashes:missing.append('selector_input_output_exact_bit_evidence')
            elif byte_count or consistency['actual_sha256']!=consistency['reference_sha256']:failed.append('selector_input_output_exact_bits_corruption')
            ids=selected.get('selected_vs_route_id_mismatches')
            if type(ids) is not int or not 0<=ids<=1024:missing.append('selector_route_id_consistency')
            elif ids:failed.append('selector_route_id_corruption')
    if not outer_verified:missing.append('verified_outer_cleanup_and_log_eof')
    status='FAIL_EXACT_REFERENCE' if failed else ('INCOMPLETE' if missing else 'PASS_FULL128_EXACT_REFERENCE')
    return dict(schema=SCHEMA,status=status,numerical_pass=status=='PASS_FULL128_EXACT_REFERENCE',profile=profile,tokens=128,layer=LAYER,final_rtl_executed=False,missing=missing,failed=failed,checked=checked,
      arithmetic_policy='EXACT_REFERENCE_ONLY_NO_NEW_TOLERANCE',raw_moe_fp32_arithmetic='DIAGNOSTIC_NOT_AN_ADDED_BITWISE_CONTRACT',
      route_policy='ORIGINAL_TORCH_TOPK_NO_SMALL_ID_OVERRIDE',route_divergence_requires_diagnosis=any(x.startswith('router.ids:') for x in failed),tie_policy_decision_needed='UNDETERMINED_UNTIL_ACTUAL_TIE_DIVERGENCE_PROVEN' if any(x.startswith('router.ids:') for x in failed) else False)

def aggregate(records):
    by_id={};duplicate=False
    for r in records:
        i=r.get('profile')
        if type(i) is not int or not 0<=i<5 or i in by_id:duplicate=True
        else:by_id[i]=r
    missing=[i for i in range(5) if i not in by_id]
    identities=[r.get('common_artifact_identity') for r in records]
    identity_ok=bool(identities) and all(isinstance(x,dict) and x==identities[0] for x in identities)
    if identity_ok:
        x=identities[0]
        identity_ok=x.get('layer')==LAYER and x.get('matrix_macs')==4096 and x.get('vector_lanes')==32 and all(isinstance(x.get(k),str) and HEX.fullmatch(x[k]) for k in ('artifact_manifest_sha256','binary_sha256','sv_sha256','source_manifest_sha256','driver_sha256'))
    checks=[r.get('qualification',{}) for r in records]
    failures=any(q.get('status')=='FAIL_EXACT_REFERENCE' for q in checks)
    passed=not missing and not duplicate and len(records)==5 and identity_ok and all(q.get('schema')==SCHEMA and q.get('profile')==r['profile'] and q.get('tokens')==128 and q.get('layer')==LAYER and q.get('final_rtl_executed') is False and q.get('status')=='PASS_FULL128_EXACT_REFERENCE' and q.get('numerical_pass') is True and r.get('numerical_pass') is True and q.get('missing')==[] and q.get('failed')==[] for r,q in zip(records,checks))
    status='PASS_FIVE_FULL128_EXACT_REFERENCE' if passed else ('FAIL_EXACT_REFERENCE' if failures else 'INCOMPLETE')
    return dict(schema='FIVE_FULL_M128_EXACT_REFERENCE_ACCEPTANCE_V1',status=status,numerical_pass=passed,missing_profiles=missing,duplicate_or_invalid_profiles=duplicate,same_common_hardware_artifact=identity_ok,layer=LAYER,final_rtl_executed=False,utilization_qualification='UNMEASURED')
