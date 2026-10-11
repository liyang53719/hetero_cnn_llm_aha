from pathlib import Path
import importlib.util,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent;T=16
BASE=ROOT/'work/qwen2_block_recipe_m16_release_20261011';NATIVE=ROOT/'work/qwen2_layer0_model_gate_cold_m16_20261011';stages=OUT/'stages'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load(ROOT/'scripts/qwen2_block_recipe_model.py','r');n=load(ROOT/'scripts/qwen2_layer0_model_gate.py','n')
receipt=r.validate_recipe_receipt(ROOT,BASE);native=r.validate_native_receipt(ROOT,NATIVE,receipt)
original=json.loads((OUT/'RESULT.json').read_text())
for e in original['comparisons']['native']:
 name=e['name'];path=stages/(f'phase_{r.STAGE_NAMES.index(name)}_{name}_recipe.f32le' if name in r.STAGE_NAMES else name+'.f32le')
 if r.file_sha(path)!=e['sha256']:raise ValueError('original candidate output hash changed')
actual={}
for i,name in enumerate(r.STAGE_NAMES):
 shape=native['modes']['bf16']['phases'][0]['stages'][name]['native_export_shape']
 a=np.fromfile(stages/f'phase_{i}_{name}_recipe.f32le',dtype='<f4').reshape(shape)
 if name in ('q','k'):
  heads=12 if name=='q' else 2;a=a.reshape(1,T,heads,128).transpose(0,2,1,3).copy()
 actual[name]=a
for name in ['scores','logits','softmax_fp32','prob','silu']:
 shape=native['modes']['bf16']['phases'][0]['stages'][name]['shape']
 actual[name]=np.fromfile(stages/f'{name}.f32le',dtype='<f4').reshape(shape)
actual['cache_k']=actual['k'].copy();actual['cache_v']=actual['v'].reshape(1,T,2,128).transpose(0,2,1,3).copy()
actual['repeat_k']=np.repeat(actual['cache_k'],6,axis=1);actual['repeat_v']=np.repeat(actual['cache_v'],6,axis=1)
actual['pv']=actual['att'].reshape(1,T,12,128).transpose(0,2,1,3).copy()
actual['mask']=n.causal_mask(T,0,'bf16');actual['x']=np.fromfile(BASE/'input_x.f32le',dtype='<f4').reshape(1,T,1536)
layout=json.loads((BASE/'generated/layout.json').read_text());regions={x['name']:x for x in layout['regions']}
arena=np.memmap(BASE/'readonly_arena.f32le',dtype='<f4',mode='r')
for name in ['cos','sin']:
 off=regions[name]['offset']//4;a=n.bf16(arena[off:off+T*64].reshape(T,64).copy());actual[name]=np.concatenate((a,a),axis=1)
assert set(actual)==n.REQUIRED_STAGES
for name,a in actual.items():n.export_value(a,name).tofile(stages/f'candidate_{name}.f32le')
policy=n.load_policy(ROOT);comparisons={}
for kind in ('native','independent'):
 results=[]
 for name in sorted(n.REQUIRED_STAGES):
  entry=native['modes']['bf16']['phases'][0]['stages'][name]
  ref=np.fromfile(NATIVE/entry[kind+'_file'],dtype='<f4').reshape(entry[kind+'_export_shape'])
  a=n.export_value(actual[name],name);metrics=n.compare(a,ref);verdict=n.stage_verdict(name,metrics,'bf16',policy)
  delta=np.abs(a.astype(np.float64)-ref.astype(np.float64));ix=np.unravel_index(np.argmax(delta),delta.shape)
  results.append(dict(name=name,metrics=metrics,verdict=verdict,max_abs_coordinate=list(map(int,ix)),candidate_at_max=float(a[ix]),reference_at_max=float(ref[ix]),candidate_sha256=r.file_sha(stages/f'candidate_{name}.f32le')))
 comparisons[kind]=results
config=json.loads((ROOT/n.SOURCE/'config.json').read_text());semantics=n.audit_semantics(actual,None,config,'bf16')
row_error=float(np.max(np.abs(actual['softmax_fp32'].sum(axis=-1,dtype=np.float32)-1)))
result=dict(status='CANDIDATE_ONLY_NOT_IMPLEMENTED',tokens=T,comparisons=comparisons,semantics=semantics,
 softmax_fp32=dict(reference='official BF16 eager forward internal FP32 softmax, not official FP32-mode attention',elementwise_tolerance=None,max_row_sum_error=row_error,row_sum_limit=2e-5,passed_existing_row_sum_contract=row_error<=2e-5),
 candidate_result_sha256=r.file_sha(OUT/'RESULT.json'),candidate_cpp_sha256=r.file_sha(OUT/'candidate.cpp'),candidate_binary_sha256=r.file_sha(OUT/'candidate'),
 derived_nodes=['x','cos','sin','mask','cache_k','cache_v','repeat_k','repeat_v','pv'],derived_nodes_source='own computed candidate stages or immutable readonly input/constants; no native intermediate injection',
 native_result_sha256=r.file_sha(NATIVE/'RESULT.json'),canonical_result_sha256=r.file_sha(BASE/'RESULT.json'),rtl_executed=False)
(OUT/'FULL_NODE_CHECK.json').write_text(json.dumps(result,indent=2)+'\n')
for kind,entries in comparisons.items():print(kind,'failed',[(e['name'],e['metrics']['max_abs']) for e in entries if e['verdict']['passed'] is False])
print('M16_node_count',len(actual),'row_error',row_error,'semantics',semantics)
