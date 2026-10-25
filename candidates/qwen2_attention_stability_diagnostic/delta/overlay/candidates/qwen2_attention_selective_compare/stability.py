"""Fixed-order metadata and read-only cross-round control checks, not arithmetic."""
import hashlib,json
from pathlib import Path
from runtime_observer import canonical_events
CANONICAL=('off','original','selective_identity_r1')
ORDERS=(CANONICAL,CANONICAL[1:]+CANONICAL[:1],CANONICAL[2:]+CANONICAL[:2])
LIMITS=dict(cpu_seconds=60,address_space_bytes=1<<30,wall_seconds=90,cpus=1,child_cpu_seconds=18,child_wall_seconds=27,cleanup_cpu_reserve=2,cleanup_wall_reserve=3,fresh_processes=3)
def need(ok,message):
    if not ok:raise ValueError(message)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical_arms(arms,execution_order):
    need(tuple(execution_order) in ORDERS and [a['observer_variant'] for a in arms]==list(execution_order),'exact physical execution order')
    need(len(arms)==3 and all(a['terminal_acked'] and a['resources_released'] for a in arms),'three physical terminals before canonical comparison')
    by_variant={a['observer_variant']:a for a in arms}
    return [by_variant[v] for v in CANONICAL]
def field_signature(directory,filename):
    fields=json.loads((directory/filename).read_text());out={}
    for name,row in fields.items():
        data=directory/row['file'];presence=directory/row['presence_file']
        need(data.stat().st_size==row['bytes'] and digest(data)==row['sha256'],'captured field hash drift')
        need(digest(presence)==row['presence_sha256'],'captured presence hash drift')
        out[name]=(row['shape'],row['sha256'],row['presence_sha256'],row['frequency'])
    need(len(out)==10,'ten captured fields required')
    return out
def summarize_experiment(directories):
    need(len(directories)==3,'exact three fresh process trios')
    baseline=None;field_baseline=None;reference_baseline=None;rounds=[];births=set()
    keys=('counts','service_counts','scalar_calls','native_fmas','edges','owner_clock','held_checks','work_events','lane_calls','owner_counts')
    for order_index,value in enumerate(directories):
        d=Path(value);result=json.loads((d/'RESULT.json').read_text());order=ORDERS[order_index]
        need(result['status']=='PASS_REAL_ATTENTION_M2_ROTATED_IDENTITY_TRIO_DIAGNOSTIC_ONLY' and result['m']==2,'round must pass actual reference/control')
        need(result['order_index']==order_index and result['execution_order']==list(order) and result['canonical_reporting_order']==list(CANONICAL),'round identity/order mismatch')
        need(result['reference_after_all_three_terminals'] is True,'reference terminal gate receipt')
        canonical_arms(result['arms'],order)
        identity=result['identity'];birth=(identity['boot_id'],identity['pid'],identity['start_ticks']);need(birth not in births,'fresh worker process required');births.add(birth)
        reference=(digest(d/'REFERENCE_OUTPUT.u32le'),digest(d/'REFERENCE_SCORES.u32le'),field_signature(d,'REFERENCE_FIELDS.json'))
        if reference_baseline is None:reference_baseline=reference
        else:need(reference==reference_baseline,'cross-round independent reference changed')
        costs={};artifact_hashes={}
        need(len(result['arm_artifacts'])==3,'all physical artifact links')
        for i,(variant,arm,link) in enumerate(zip(order,result['arms'],result['arm_artifacts'])):
            expected=dict(variant=variant,execution_index=i,output='OUTPUT_'+str(i)+'.u32le',scores='SCORES_'+str(i)+'.u32le',writes='WRITES_'+str(i)+'.json',service_events='SERVICE_EVENTS_'+str(i)+'.json',capture_fields=None if variant=='off' else 'CAPTURE_'+str(i)+'_FIELDS.json')
            need(link==expected,'physical artifact index/variant mismatch')
            hashes={key:digest(d/link[key]) for key in ('output','scores','writes','service_events')};artifact_hashes[variant]=hashes
            need((hashes['output'],hashes['scores'])==reference[:2],'persisted output/score differs from own reference')
            events=json.loads((d/link['service_events']).read_text())
            controls=({key:arm[key] for key in keys},hashes['output'],hashes['scores'],hashes['writes'],canonical_events(events))
            if baseline is None:baseline=controls
            else:need(controls==baseline,'cross-round numeric/control/service mismatch')
            if variant!='off':
                need(arm['capture_error'] is None and arm['capture_report'] is not None,'capture acceptance')
                signature=field_signature(d,link['capture_fields'])
                need({k:v[:3] for k,v in signature.items()}=={k:v[:3] for k,v in reference[2].items()},'persisted fields differ from own reference')
                if field_baseline is None:field_baseline=signature
                else:need(signature==field_baseline,'cross-round capture/frequency mismatch')
            need(arm['service_trace_error'] is None,'service trace acceptance')
            stages=[s for s in arm['stages'] if s['stage']=='actual_owner_job_through_terminal_ack_and_monitor_exit']
            need(len(stages)==1 and stages[0]['cpu_ns']>0 and stages[0]['wall_ns']>0,'exact clean owner timing stage')
            costs[variant]={key:stages[0][key] for key in ('cpu_ns','wall_ns')}
        ratio=costs['selective_identity_r1']['cpu_ns']/costs['original']['cpu_ns']
        rounds.append(dict(order_index=order_index,execution_order=list(order),identity=identity,result_sha256=digest(d/'RESULT.json'),artifact_hashes=artifact_hashes,costs=costs,identity_over_original_cpu_ratio=ratio))
    spread={v:{metric:dict(samples=[r['costs'][v][metric] for r in rounds],minimum=min(r['costs'][v][metric] for r in rounds),maximum=max(r['costs'][v][metric] for r in rounds),median=sorted(r['costs'][v][metric] for r in rounds)[1]) for metric in ('cpu_ns','wall_ns')} for v in CANONICAL}
    return dict(status='PASS_THREE_FRESH_ROTATED_M2_CONTROL_REFERENCE_ONLY',rounds=rounds,spread=spread,identity_cpu_lower_in_all_three=all(r['identity_over_original_cpu_ratio']<1 for r in rounds),raw_traces_rewritten=False,only_comparison_ticket_normalization=True,performance_adopted=False,small_sample_not_statistical_proof=True,hardware_claim=False)
