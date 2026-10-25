"""One separately authorized reference-only validation of immutable terminal arms.
The reference receives only original qr/kr/v words; saved DUT word files are not
opened or decoded until capture_reference has returned successfully.
"""
import argparse,hashlib,json,os,resource,struct,sys
from array import array
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from admission import validate_review
from artifacts import persist_fields,persist_words
from boundary import Boundary,verify_pins,load_bound,audit_runtime
from durable import Stages,atomic_json,sync_files
from policy import LIMITS,PROFILE
from primitives import need,digest,compare_fields
from reference_capture import capture_reference
STAGES=OUT=None

def terminal_gate(config):
    envelope=json.loads(Path(config['sealed_envelope']).read_text())
    review=json.loads(Path(config['saved_pair_review']).read_text())
    need(envelope['original_state']=='FAILED_RETAINED' and envelope['reference_completed'] is False,'immutable failed origin')
    need(review['status']=='PASS_INDEPENDENT_RETAINED_TWO_ARM_EVIDENCE_NOT_REFERENCE_OR_RUN_SUCCESS' and review['recovery']['rerun_DUT_required'] is False and review['recovery']['saved_operands_and_two_arms_sufficient_for_separate_terminal_only_reference'] is True,'reviewed terminal evidence')
    root=Path(config['original_attempt']);pair=root/'pair'
    need({str(p.resolve()) for p in root.rglob('*') if p.is_file()}==set(envelope['artifacts']),'complete immutable original artifact set')
    need({str(root/rel):pin for rel,pin in review['artifact_pins'].items()}==envelope['artifacts'],'independent artifact seal agrees')
    for i in range(2):
        evidence=json.loads((pair/f'artifacts/ARM_{i}_EVIDENCE.json').read_text())
        need(evidence['actual_terminal_verified'] is True and evidence['errors']==[] and evidence['capture_error'] is evidence['service_error'] is None,'both actual clean terminals')
        need(evidence['terminal']['completed']==3 and evidence['terminal']['jobs']==1 and evidence['terminal']['status'] is None,'public3 terminal')
        need(evidence['capture_report']['terminal']==dict(clean=True,same_services=True,state='idle'),'clean owner release')
        summary=json.loads((pair/f'audits/RUNTIME_ARM_{i}_TERMINAL/SUMMARY.json').read_text())
        need(summary==dict(status='PASS_EXACT_RUNTIME_IDENTITIES',phase=f'ARM_{i}_TERMINAL',errors=[]),'original terminal audit')
    need(not (pair/'RESULT.json').exists() and not list((pair/'artifacts').glob('REFERENCE*')),'do not invent or reuse prior reference')
    return dict(status='BOTH_SAVED_PUBLIC3_TERMINALS_ADMITTED',original_attempt_state='FAILED_RETAINED',reference_values_loaded=False)

def input_words(config):
    arrays=[]
    for role,width in (('qr',1536),('kr',256),('v',256)):
        spec=config['inputs'][role];prefix=config['input_prefixes'][role]
        need(digest(spec['path'])==spec['sha256'],'frozen input identity')
        with Path(spec['path']).open('rb') as f:raw=f.read(16*width*4)
        need(len(raw)==prefix['bytes'] and hashlib.sha256(raw).hexdigest()==prefix['sha256'],'exact M16 input prefix')
        arrays.append(struct.unpack('<%dI'%(16*width),raw))
    return tuple(arrays)

def saved_fields(config,index):
    directory=Path(config['original_attempt'])/'pair/artifacts'
    metadata=json.loads((directory/f'CAPTURE_{index}_FIELDS.json').read_text());fields={}
    evidence=json.loads((directory/f'ARM_{index}_EVIDENCE.json').read_text())
    need(metadata==evidence['fields'],'archived field metadata link')
    names={'dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16'}
    need(set(metadata)==names,'exact ten archived fields')
    for name,row in metadata.items():
        raw=(directory/row['file']).read_bytes();presence=(directory/row['presence_file']).read_bytes()
        need(hashlib.sha256(raw).hexdigest()==row['sha256'] and hashlib.sha256(presence).hexdigest()==row['presence_sha256'],'archived field identity')
        shape=(12,16,16,16) if name=='dot_parts' else (12,16,3) if name=='normalizer' else (12,16,128) if name in ('pv_raw','pv_bf16') else (12,16,16)
        count=1
        for dimension in shape:count*=dimension
        need(tuple(row['shape'])==shape and len(raw)==row['bytes']==4*count and len(presence)==len(row['frequency'])==count,'archived M16 shape/extent')
        frequency=row['frequency'];need(all(type(v) is int and 0<=v<65536 for v in frequency),'u16 frequency')
        words=struct.unpack('<%dI'%count,raw);report=evidence['capture_report']['fields'][name]
        need(hashlib.sha256(struct.pack('<%dH'%count,*frequency)).hexdigest()==report['frequency_sha256'] and list(shape)==report['shape'] and row['sha256']==report['raw_sha256'] and row['presence_sha256']==report['presence_sha256'],'archived field report binding')
        for j in range(count):
            causal=True if name in ('normalizer','pv_raw','pv_bf16') else ((j//16)%16<=(j//256)%16 if name=='dot_parts' else j%16<=(j//16)%16)
            expected=(8 if name in ('prob_bf16','softmax_fp32') else 1) if causal else 0
            need(presence[j]==int(causal) and frequency[j]==expected and (causal or words[j]==0xa5963cc3),'archived causal presence/frequency/sentinel')
        need(report['observed_words']==report['writes']==sum(presence) and report['identical_repeats']==sum(frequency)-sum(presence),'archived event accounting')
        fields[name]=dict(shape=shape,words=words,observed=presence,frequency=array('H',frequency))
    return fields

def compare_completed_reference(config,reference):
    expected=struct.pack('<24576I',*reference['output'])
    directory=Path(config['original_attempt'])/'pair/artifacts'
    for i in range(2):
        need((directory/f'OUTPUT_{i}.u32le').read_bytes()==expected,'independent recipe output mismatch')
        fields=saved_fields(config,i);compare_fields(fields,reference['fields'])
        scores=fields['scores_bf16']['words']
        need(tuple(scores[(h*16+t)*16+k] for t in range(16) for h in range(12) for k in range(t+1))==reference['scores'],'independent recipe score mismatch')
    return dict(status='PASS_TWO_ARCHIVED_ARMS_AGAINST_INDEPENDENT_ATTENTION_RECIPE',output_sha256=hashlib.sha256(expected).hexdigest(),ten_fields_bit_exact=True,original_attempt_state='FAILED_RETAINED')

def main():
    global STAGES,OUT
    p=argparse.ArgumentParser()
    for n in ('config','sha','review','review-sha','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--m',type=int,choices=(16,),required=True);a=p.parse_args()
    need(os.environ.get('ORDERED_NATIVE_PARENT')==str(os.getppid()),'reviewed supervisor required')
    need(digest(a.config)==a.sha,'exact config')
    config,review=validate_review(a.config,a.review,a.review_sha,HERE)
    need(config['profile']==PROFILE and config['reference_only'] is True,'reference-only profile')
    need(len(os.sched_getaffinity(0))==1 and resource.getrlimit(resource.RLIMIT_AS)[0]==LIMITS['address_space_bytes'],'caps')
    OUT=Path(a.out)
    for name in ('streams','artifacts','audits','metadata'):(OUT/name).mkdir()
    STAGES=Stages(OUT/'metadata/stages');STAGES.mark('PREFLIGHT_ENTER')
    verify_pins(config);gate=terminal_gate(config)
    atomic_json(OUT/'metadata/TERMINAL_ADMISSION.json',gate);STAGES.mark('SEALED_TERMINALS_ADMITTED',gate)
    guard=Boundary(config,OUT);sys.addaudithook(guard.audit)
    inputs=input_words(config)
    STAGES.mark('BEFORE_REFERENCE_IMPORT',dict(input_sources_only=['qr','kr','v'],dut_values_loaded=False))
    saved=list(sys.argv);sys.argv=[config['oracle_harness'],'--source-root',config['raw_root']]
    try:module=load_bound(config['oracle_harness'],'_terminal_only_existing_recipe',config)
    finally:sys.argv[:]=saved
    base=load_bound(config['buffer_source'],'_terminal_only_existing_fields',config)
    audit_runtime(config,OUT/'audits','BEFORE_RECIPE')
    STAGES.mark('BEFORE_RECIPE',dict(dut_values_loaded=False,terminal_gate=True))
    reference=capture_reference(module,16,inputs,base.PackedFields,config['reference_sources'],terminal_gate=True)
    STAGES.mark('RECIPE_COMPLETE',dict(status=reference['report']['status'],output_words=len(reference['output']),fields=len(reference['fields'])))
    # Enable archived DUT reads only after the independent recipe has completed.
    guard.reference_complete=True
    persist_words(OUT/'artifacts','REFERENCE_OUTPUT',reference['output']);persist_words(OUT/'artifacts','REFERENCE_SCORES',reference['scores'])
    persist_fields(OUT/'artifacts','REFERENCE',reference['fields']);atomic_json(OUT/'metadata/REFERENCE_REPORT.json',reference['report'])
    sync_files(OUT/'artifacts');STAGES.mark('REFERENCE_ARTIFACTS_SAVED')
    comparison=compare_completed_reference(config,reference)
    atomic_json(OUT/'metadata/COMPARISON.json',comparison);STAGES.mark('COMPARISON_COMPLETE',comparison)
    guard.integrity=True
    try:verify_pins(config);terminal_gate(config)
    finally:guard.integrity=False
    audit_runtime(config,OUT/'audits','POSTFLIGHT');STAGES.mark('POSTFLIGHT_COMPLETE')
    atomic_json(OUT/'RESULT.json',dict(status='PASS_POSTTERMINAL_REFERENCE_REVALIDATION_ONLY',rows=16,profile=PROFILE,
        original_attempt_state='FAILED_RETAINED',original_attempt=config['original_attempt'],DUT_reexecuted=False,
        reference_after_both_component_terminals=True,reference_values_from_frozen_inputs_only=True,
        shared_exact_primitives_disclosed=True,official_full_layer_executed=False,official_m16_pair_used_as_acceptance=False,
        fullblock=False,performance_adopted=False,hardware_cycles=False,comparison=comparison,stages=STAGES.rows))

if __name__=='__main__':
    try:main()
    except BaseException as error:
        if STAGES is not None:
            try:STAGES.mark('FAILED_RETAINED',dict(type=type(error).__name__,detail=str(error)))
            except BaseException:pass
        raise
