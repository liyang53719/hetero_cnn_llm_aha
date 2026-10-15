"""Aggregate-only publication projection; no arrays, hashes, paths, or shapes."""
import argparse
import json
import math
from pathlib import Path
from candidates.qwen2_qk_aten_reduction_candidate import model
OUT=model.ROOT/'work/qwen2_qk_aten_reduction_candidate/local01'
METRIC_KEYS=('max_abs','mean_abs','count','different','bit_diff_count')
def count(value,maximum=1<<31):
    model.need(type(value) is int and 0<=value<=maximum,'nonnegative exact bounded integer required')
    return value

def number(value):
    model.need(type(value) in (int,float),'plain numeric metric required')
    model.need(0<=value<=6.805646932770577e38 and math.isfinite(value),'finite bounded metric required')
    return value

def aggregate_metrics(m):
    model.need(type(m) is dict and set(m)==set(METRIC_KEYS),'exact metric schema required')
    out={k:number(m[k]) for k in ('max_abs','mean_abs')}
    out.update({k:count(m[k]) for k in ('count','different','bit_diff_count')})
    model.need(out['count']>0 and out['different']<=out['bit_diff_count']<=out['count'],'metric counts inconsistent')
    model.need(out['mean_abs']<=out['max_abs'],'metric means inconsistent')
    model.need((out['different']==0)==(out['max_abs']==0),'zero difference/max inconsistent')
    model.need(out['max_abs']!=0 or out['mean_abs']==0,'zero metrics inconsistent')
    return out

def verdict(value):
    model.need(type(value) is bool,'exact boolean verdict required')
    return 'PASS' if value else 'FAIL'

def fixed_count(value,expected):
    model.need(count(value)==expected,'fixed count differs')
    return value
def sanitize(report):
    model.need(type(report) is dict and type(report.get('public')) is dict,'report schema')
    original=report['public'];prefix={}
    for n in ('n0','qr','kr','q','k'):
        item=original['prefix'][n]
        fixed_count(item['metrics']['count'],32768 if n in ('kr','k') else 196608)
        prefix[n]={'metrics':aggregate_metrics(item['metrics']),
          'verdict':verdict(item['verdict']['passed'])}
    attention={}
    for n in ('scores','prob_bounded'):
        item=original['attention'][n];fixed_count(item['metrics']['count'],99072 if n=='scores' else 1796)
        attention[n]={'metrics':aggregate_metrics(item['metrics']),
          'verdict':verdict(item['verdict']['passed'])}
    for n in ('same_scores_scalar_vs_official_bounded','candidate_scores_official_softmax_all_causal'):
        fixed_count(original['attention'][n]['count'],1796 if n=='same_scores_scalar_vs_official_bounded' else 99072)
        attention[n]=aggregate_metrics(original['attention'][n])
    return {'status':'COMPLETE_QK_CANDIDATE_LOCAL_DIAGNOSTIC','prefix':prefix,'attention':attention,
      'projection_fmas':fixed_count(original['projection_fmas'],352321536),'projection_adds':fixed_count(original['projection_adds'],14680064),
      'peak_partial_words':fixed_count(original['peak_partial_words'],4096),'original_qk_native_fmas':fixed_count(original['original_qk_native_fmas'],405798912),
      'selected_probability_rows':fixed_count(original['selected_probability_rows'],16),
      'selected_probability_positions':fixed_count(original['selected_probability_positions'],1796),
      'qk_coverage':'ALL_CAUSAL','current_probability_coverage':'BOUNDED_SELECTED_ROWS',
      'candidate_source':'INDEPENDENT_RAW_INPUT_MODEL','bias_rope':'UNCHANGED_OWNER_MEMORY_ACK_EXECUTION',
      'hardware_mapping':'NOT_IMPLEMENTED','hardware_performance':'NO_GO',
      'rtl':'NOT_EXECUTED','fullblock':'NOT_EXECUTED','ci':'NOT_EXECUTED','gate_policy':'UNCHANGED',
      'platform_identity':'LOCAL_PINNED_PROFILE_NOT_CI_EQUIVALENCE'}
def run(execute=False):
    if not execute:return {'status':'NOT_EXECUTED'}
    path=OUT.parent/'repair01/SAFE_PUBLIC_V2.json';model.need(not path.exists(),'fresh safe projection')
    original=OUT/'RESULT.json';identity=model.sha(original);result=sanitize(json.loads(original.read_text()))
    model.need(model.sha(original)==identity,'original receipt changed')
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,sort_keys=True));return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args();run(a.execute)
