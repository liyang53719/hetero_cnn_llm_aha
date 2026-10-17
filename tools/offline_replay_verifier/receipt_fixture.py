"""Synthetic safe receipts for offline schema tests; no numerical claim."""
import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
FREEZE=HERE.parent/'same_host_m128_replay_identity_20261017_freeze_cded2ae5'


def build(V,manifest=None):
    full,pins=V.load_sources(FREEZE)
    ci=dict(commit=V.COMMIT,run_id=V.RUN_ID,run_attempt='1')
    nonce='a'*64;qualification='b'*64;prerequisite='c'*64
    def common(rows):return dict(schema=1,profile=V.PROFILE.replace('m128','m16') if rows==16 else V.PROFILE,ci=ci.copy(),claims=dict(V.CLAIMS,**({'full_m128_acceptance':False} if rows==16 else {})))
    resources=dict(available_disk_bytes=20*1024**3,available_memory_bytes=8*1024**3,cpu_affinity=4)
    summary=dict(common(128),status='PASS_FRESH_SAME_HOST_M128_ASSIGNED27',phase='complete',elapsed_seconds=1000.0,failure_kind=None,owned_groups_cleanup_complete=True,resources_before_setup=resources.copy(),full_m16_prerequisite_pass=True,producer128_qualified=True,full_m128_assigned27_pass=True,replay_identity_ready=True,replay_identity_sha256='0'*64,replay_identity_failure=None,producer_failure_observation=None,full_m128_failure_diagnostic=None)
    a16=dict(common(16),status='PASS_FRESH_SAME_HOST_M16_ASSIGNED27',phase='complete',elapsed_seconds=100.0,failure_kind=None,owned_groups_cleanup_complete=True,resources_before_setup=resources.copy(),resources_after_setup=resources.copy(),producer_qualified=True,full_m16_assigned27_pass=True,full_m16_failure_diagnostic=None)
    h=dict(common(128),inputs=pins[128]['inputs'],composed_sources_template=pins[128]['composed_sources'],dynamic_source_contract=True)
    events=[dict(phase=phase,pid=100+i,status='PASS',observed_exit_code=0,final_exit_code=0,owned_group_cleanup_complete=True,timing_diagnostic=dict(schema=1,diagnostic_only=True,acceptance=False,scope='PARENT_RUSAGE_CHILDREN_DELTA',status='AVAILABLE',reason=None,wall_seconds=1.0,reaped_children_user_cpu_seconds=0.5,reaped_children_system_cpu_seconds=0.1)) for i,phase in enumerate(V.PHASES)]
    journal=dict(schema=1,profile=V.PROFILE,ci=ci.copy(),stages=events,m16_stage_exits_sha256='d'*64)
    producer=dict(common(128),status='PASS_FRESH_M128_PRODUCER',attempt_nonce=nonce,producer_manifest_sha256='e'*64,producer_qualification_sha256=qualification,verifier_receipt_sha256='f'*64,m16_prerequisite_sha256=prerequisite,owned_groups_cleanup_complete=True,stages=copy.deepcopy(events[:2]))
    values={'summary.json':summary,'source_hashes.json':h,'m16_attempt_summary.json':a16,'producer_summary.json':producer,'stage_exits.json':journal}
    for rows in (16,128):
        sources,_=V.compose(pins,rows)
        validation=dict(schema=1,status=f'VALIDATED_FRESH_SAME_HOST_M{rows}_OBSERVED_GATES_ONLY',assigned_official_gates=27,official_observed_stages=28,capture_fields=10,diagnostic_fp32_stages=1,owner_jobs=17,public_completions=21,rows=rows,source_files=len(sources),source_manifest_sha256=V.sha(V.encoded(sources)),execution_authenticated_by_this_validator=False,fixed_arithmetic_pass=True,observed_official_gates_pass=True,full_29_node_acceptance=False,hardware_acceptance=False,rtl_acceptance=False,summary_sha256=hashlib.sha256(f'synthetic summary {rows}'.encode()).hexdigest(),snapshot_sha256=hashlib.sha256(f'synthetic snapshot {rows}'.encode()).hexdigest())
        f=dict(common(rows),status=f'PASS_FRESH_SAME_HOST_M{rows}_ASSIGNED27',attempt_nonce=nonce,producer_receipt_sha256=qualification if rows==128 else '1'*64,child_result_sha256='0'*64,child_pid=105 if rows==128 else 99,child_exit_code=0,owned_group_cleanup_complete=True,elapsed_seconds=80.0,validation=validation)
        if rows==128:f['m16_prerequisite_sha256']=prerequisite
        f['child_result_sha256']=V.sha(V.encoded(V.child_result(rows,f)));values[f'full_m{rows}_summary.json']=f
    if manifest is None:
        # Deliberately minimal fixture for receipt-only unit tests. It is not
        # accepted by the full identity validator or CLI.
        manifest={'identity':{},'identity_sha256':V.sha(V.encoded({})),'provenance':{}}
    else:manifest=copy.deepcopy(manifest)
    p=manifest['provenance'];p.update(ci=ci.copy(),raw_source_map_sha256=V.sha(V.encoded(h['inputs'])),qualification_sha256=qualification,m16_prerequisite_sha256=prerequisite,producer_manifest_sha256={'16':'2'*64,'128':producer['producer_manifest_sha256']},verifier_receipt_sha256=producer['verifier_receipt_sha256'],m128_child_result_sha256=values['full_m128_summary.json']['child_result_sha256'],driver_sha256={str(rows):full[V.BASE+('portable_official_producer/' if rows==16 else 'portable_official_producer_m128/')+'driver.py'] for rows in (16,128)},emitter_sha256=full[V.BASE+'portable_same_host_m128_launch/replay_identity.py'],wheel_lock_sha256=full[V.BASE+'portable_official_producer_launch/wheel-lock.json'])
    for rows in (16,128):
        f=values[f'full_m{rows}_summary.json'];p.update({f'm{rows}_composed_source_map_sha256':f['validation']['source_manifest_sha256'],f'm{rows}_summary_sha256':f['validation']['summary_sha256'],f'm{rows}_snapshot_sha256':f['validation']['snapshot_sha256'],f'm{rows}_full_receipt_sha256':V.sha(V.encoded(f))})
    values['replay_identity.json']=manifest
    summary['replay_identity_sha256']=V.sha(V.encoded(manifest))
    return values,pins,full


def raws(V,values):return {n:V.encoded(v) for n,v in values.items()}


def archive(raws):
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,body in raws.items():z.writestr(name,body)
    return target.getvalue()
