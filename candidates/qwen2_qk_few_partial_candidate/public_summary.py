"""Strict aggregate-only projection; added after the numerical execution."""
import argparse
import json
from candidates.qwen2_qk_few_partial_candidate import model
from candidates.qwen2_qk_aten_reduction_candidate.public_summary import aggregate_metrics,fixed_count
CASES=('REAL_BASELINE','SIGN_FLIP_SEED','CHANNEL_PERMUTE_SEED')
STAGES=('n0','qr','kr','q','k')
BOUNDARIES=('ZERO_SIGN','CANCELLATION','REFILL_BOUNDARIES','BIAS_BF16_MIDPOINT')

def enum(value,expected):
    model.need(type(value) is str and value==expected,'fixed enum required')
    return expected

def stage(value,count):
    model.need(type(value) is dict and set(value)=={'metrics','verdict'},'stage schema')
    metrics=aggregate_metrics(value['metrics']);fixed_count(metrics['count'],count)
    verdict='PASS' if metrics['max_abs']<=0.03125 and metrics['mean_abs']<=0.005 else 'FAIL'
    enum(value['verdict'],verdict)
    return {'metrics':metrics,'verdict':verdict}

def sanitize(report):
    model.need(type(report) is dict and type(report.get('public')) is dict,'report schema')
    p=report['public'];enum(p['status'],'SIX_CASE_SCREEN_COMPLETE')
    fixed_count(p['completed_cases'],6);fixed_count(p['registered_cases'],6)
    for name,value in [('gate_policy','UNCHANGED'),('selection','NO_POSTHOC_GRAPH_OR_SEED_SELECTION'),
                       ('rtl','NOT_EXECUTED'),('fullblock','NOT_EXECUTED'),('ci','NOT_EXECUTED'),
                       ('hardware_mapping','CONDITIONAL_NOT_IMPLEMENTED')]:enum(p[name],value)
    model.need(type(p['cases']) is list and len(p['cases'])==6,'all registered cases required')
    results=[]
    for original,(case,P) in zip(p['cases'],((c,P) for c in CASES for P in (2,4))):
        model.need(type(original) is dict,'case schema')
        enum(original['case'],case);fixed_count(original['partials'],P)
        model.need(type(original['prefix']) is dict and set(original['prefix'])==set(STAGES),'prefix schema')
        prefix={n:stage(original['prefix'][n],32768 if n in ('kr','k') else 196608) for n in STAGES}
        scores=stage(original['scores'],99072);probability=stage(original['probability'],99072)
        failed=[n for n in STAGES if prefix[n]['verdict']=='FAIL']
        failed += [n for n,v in [('scores',scores),('probability',probability)] if v['verdict']=='FAIL']
        model.need(type(original['failed_stages']) is list and original['failed_stages']==failed,'failed stages inconsistent')
        status='COMPLETE_NUMERIC_FAIL' if failed else 'COMPLETE_NUMERIC_PASS';enum(original['status'],status)
        results.append({'case':case,'partials':P,'status':status,'prefix':prefix,'scores':scores,'probability':probability,
          'failed_stages':failed,'probability_positions':fixed_count(original['probability_positions'],99072),
          'projection_fmas':fixed_count(original['projection_fmas'],352321536),
          'projection_adds':fixed_count(original['projection_adds'],229376*P),
          'qk_native_fmas':fixed_count(original['qk_native_fmas'],405798912)})
    model.need(type(p['boundaries']) is list and len(p['boundaries'])==8,'boundary schema')
    for original,(P,name) in zip(p['boundaries'],((P,n) for P in (2,4) for n in BOUNDARIES)):
        model.need(type(original) is dict,'boundary item schema')
        fixed_count(original['partials'],P);enum(original['case'],name);enum(original['status'],'PASS')
        fixed_count(original['fmas'],393216)
    # Only validated metrics/counts and fixed enums cross this boundary.
    return {'status':'SIX_CASE_SCREEN_COMPLETE','cases':results,'registered_cases':6,'completed_cases':6,
       'boundary_checks_passed':8,'probability_positions':594432,
       'graph_acceptance':'NEITHER_GRAPH_PASSES_ALL_REGISTERED_CASES' if all(any(r['partials']==P and r['status']=='COMPLETE_NUMERIC_FAIL' for r in results) for P in (2,4)) else 'REFER_TO_ALL_CASES',
       'qk_coverage':'ALL_CAUSAL','probability_coverage':'ALL_CAUSAL_ORIGINAL_SCALAR',
       'selection':'NO_POSTHOC_GRAPH_OR_SEED_SELECTION','gate_policy':'UNCHANGED',
       'candidate_source':'INDEPENDENT_RAW_INPUT_MODEL','bias_rope':'UNCHANGED_OWNER_MEMORY_ACK_EXECUTION',
       'hardware_mapping':'CONDITIONAL_NOT_IMPLEMENTED','hardware_performance':'NOT_ESTABLISHED',
       'rtl':'NOT_EXECUTED','fullblock':'NOT_EXECUTED','ci':'NOT_EXECUTED',
       'platform_identity':'LOCAL_PINNED_PROFILE_NOT_CI_EQUIVALENCE'}

def run(execute=False):
    if not execute:return {'status':'NOT_EXECUTED'}
    root=model.ROOT/'work/qwen2_qk_few_partial_candidate/local01'
    path=root/'RESULT.json';before=model.sha(path);out=sanitize(json.loads(path.read_text()))
    model.need(model.sha(path)==before,'original result drift')
    destination=root.parent/'SAFE_PUBLIC.json';model.need(not destination.exists(),'fresh safe projection')
    destination.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
    print(json.dumps(run(a.execute),sort_keys=True))
