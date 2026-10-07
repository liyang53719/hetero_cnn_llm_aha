import hashlib, json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
P=ROOT/'work/rope_rounding_ablation/verified_final'
r=json.loads((P/'result.json').read_text())
checks=0

def check(value,label):
 global checks
 if not value: raise RuntimeError(label)
 checks+=1

for source,digest in r['source_sha256'].items():check(hashlib.sha256((ROOT/source).read_bytes()).hexdigest()==digest,source)
for name,record in r['artifacts'].items():check(hashlib.sha256((P/name).read_bytes()).hexdigest()==record['sha256'],name)
summary={}
for name in ('local','remote'):
 t=np.load(P/(name+'_traces.npy'));c=np.load(P/(name+'_independent_c.npy'));check(np.array_equal(t,c),'all C nodes '+name)
 with np.load(ROOT/'tests/fixtures/rope_rounding'/(name+'.npz')) as f:
  check(np.array_equal(t[:,0,12:14],f['hardware_comb'][:,:2]),'hardware '+name)
  check(np.array_equal(t[:,3,8:12],f['native_products']),'products '+name)
  check(np.array_equal(t[:,3,16:18],f['native_outputs']),'native '+name)
  summary[name]={}
  for i,v in enumerate(r['variants']):
   for j,g in enumerate(r['corpora'][name]['metrics'][v]):
    sl=slice(g['start'],g['start']+g['pairs']);a=t[sl,i,16:18];b=f['native_outputs'][sl];err=np.abs(a.view(np.float32).astype(np.float64)-b.view(np.float32).astype(np.float64));m=g['terminal_BF16_vs_frozen_native']
    check(m['bit_different']==int(np.count_nonzero(a!=b)),name+v+' bits')
    check(m['max_abs_error']==err.max() and m['mean_abs_error']==err.mean(),name+v+' error')
    check(m['mismatches_over_max']==int(np.count_nonzero(err>0.03125)),name+v+' over')
    comparisons={'terminal_BF16_vs_frozen_native':(a,b,True),
      'terminal_BF16_vs_hardware_projection':(a,t[sl,0,16:18],True),
      'sum_FP32_vs_frozen_actual_hardware':(t[sl,i,12:14],f['hardware_comb'][sl,:2],False),
      'selected_products_vs_frozen_native':(t[sl,i,8:12],f['native_products'][sl],False)}
    for metric,(actual,expected,is_bf16) in comparisons.items():
     mm=g[metric];af=actual.view(np.float32).astype(np.float64);bf=expected.view(np.float32).astype(np.float64);er=np.abs(af-bf)
     def order(words):
      mag=(words & 0x7fffffff).astype(np.int64)
      if is_bf16:mag=mag//65536
      return np.where(words & 0x80000000,-mag,mag)
     distance=np.abs(order(actual)-order(expected))
     bins=[('0',0,0),('1',1,1),('2_to_4',2,4),('5_to_16',5,16),('17_to_256',17,256),('257_to_65536',257,65536),('over_65536',65537,2**32)]
     expected_metrics={'elements':actual.size,'max_abs_error':float(er.max()),'mean_abs_error':float(er.mean()),'mismatches_over_max':int(np.count_nonzero(er>0.03125)),
      'bit_different':int(np.count_nonzero(actual!=expected)),'numerically_different':int(np.count_nonzero(af!=bf)),
      'pass':bool(er.max()<=0.03125 and er.mean()<=0.005),'max_ulp':int(distance.max()),'mean_ulp':float(distance.mean()),
      'ulp_histogram':{key:int(((distance>=low)&(distance<=high)).sum()) for key,low,high in bins},
      'ulp_quantiles':{str(q):float(np.quantile(distance,q)) for q in (0.5,0.9,0.99,1)},
      'abs_error_quantiles':{str(q):float(np.quantile(er,q)) for q in (0.5,0.9,0.99,1)},
      'signed_zero_only_differences':int(np.count_nonzero((actual!=expected)&(af==bf))),
      'actual_above_expected':int(np.count_nonzero(af>bf)),'actual_below_expected':int(np.count_nonzero(af<bf))}
     for field,value in expected_metrics.items():check(mm[field]==value,name+v+metric+field)
    w=g['max_abs_witness'];pair=w['flat_pair_index'];lane=w['lane'];check(w['candidate_hex']==f'{t[pair,i,16+lane]:08x}' and w['frozen_native_hex']==f'{f["native_outputs"][pair,lane]:08x}' and w['abs_error']==err.max(),name+v+' witness')
    if j==0:summary[name][v]={k:m[k] for k in ('bit_different','max_abs_error','mismatches_over_max','pass')}
check(np.array_equal(np.load(P/'synthetic_traces.npy'),np.load(P/'synthetic_independent_c.npy')),'synthetic all C nodes')
result={'status':'PASS','checks':checks,'summary':summary}
Path(__file__).with_name('final_report_checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
