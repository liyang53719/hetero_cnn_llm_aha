from pathlib import Path
import json,hashlib,sys,time,os
import numpy as np
os.environ.setdefault('HF_HOME',str(Path(__file__).resolve().parents[3]/'work/hf-cache'))
import torch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
ACT=ROOT/'work/qwen2_official_public21_20261012/actual_m128_02';OUT=ROOT/'work/qwen2_official_public21_20261012/q_projection_attribution';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ACT/'summary.json')=='25b947ff774412685d9691de0a06f1a1cf489388557db357013bf7911c11681a'
r=json.loads((ACT/'summary.json').read_text());snapshot=Path(r['snapshot'])
assert sha(snapshot)==r['snapshot_sha256']=='5b9247588ddddcada1e669034c3e8e0a17ffb39c6c6aef3ffd1bb5e49c6924ab', 'actual snapshot drift'
s=json.loads(snapshot.read_text());ref=s['reference'];inventory={x['path']:x for x in ref['artifacts']}
assert sha(ROOT/'scripts/qwen2_layer0_model_gate.py')==s['source_sha256']['scripts/qwen2_layer0_model_gate.py'], 'official source identity checker drift'
from scripts.qwen2_layer0_model_gate import runtime_identity
torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.set_default_dtype(torch.float32);torch.use_deterministic_algorithms(True);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False;torch.set_float32_matmul_precision('highest')
module,identity=runtime_identity(ROOT);assert identity==ref['official_reference_identity']
consumed={}
def read(path,expected):
 assert sha(path)==expected,str(path);consumed[str(path.relative_to(ROOT))]=expected;return np.fromfile(path,dtype='<f4')
def actual(name,width):return read(ACT/('actual_'+name+'.f32le'),r['sealed_actual_outputs'][name]['sha256']).reshape(1,128,width)
def native(name,shape):
 rel='references/official_self_cache/'+name+'.f32le';entry=inventory[rel]
 return read(Path(ref['directory'])/'cold'/rel,entry['sha256']).reshape(shape)
def operand(a):return torch.from_numpy(a.copy()).to(torch.bfloat16).transpose(1,2)
q=operand(actual('q',1536).reshape(1,128,12,128));k=operand(actual('k',256).reshape(1,128,2,128));qo=operand(native('q',(1,12,128,128)).transpose(0,2,1,3));ko=operand(native('k',(1,2,128,128)).transpose(0,2,1,3))
ref_scores=native('scores',(1,12,128,128));shape=r['observation']['fields']['scores_bf16']['shape'];entry=r['observation']['fields']['scores_bf16'];actual_scores=read(ACT/'attention_observation/scores_bf16.u32le',entry['raw_sha256']).reshape((1,*shape));mask_path=ACT/'attention_observation/scores_bf16.presence';assert sha(mask_path)==entry['presence_sha256'];present=np.fromfile(mask_path,dtype=np.uint8).reshape((1,*shape)).astype(bool);assert int(present.sum())==99072
outputs={};layouts={};start=time.monotonic()
with torch.inference_mode():
 for label,qvalue,kvalue in [('official_operands',qo,ko),('actual_operands',q,k)]:
  kt=module.repeat_kv(kvalue,6).transpose(2,3);layouts[label]={n:dict(shape=list(t.shape),stride=list(t.stride()),storage_offset=t.storage_offset(),dtype=str(t.dtype),logical_bf16_sha256=hashlib.sha256(t.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()) for n,t in [('q',qvalue),('key_transposed',kt)]}
  outputs[label]=(torch.matmul(qvalue,kt)/(128**0.5)).float().numpy()
assert np.array_equal(outputs['official_operands'].view('<u4'),ref_scores.view('<u4')),'full-shape native replay differs from frozen reference'
def metrics(a,b):
 dif=np.abs(a.astype('float64')-b.astype('float64'));where=np.argwhere(present&(a.view('<u4')!=b.view('<u4')));return dict(causal_elements=int(present.sum()),different_elements=len(where),max_abs=float(dif[present].max()),mean_abs=float(dif[present].mean()),coordinates=where.tolist(),greater_than_original_abs_max=int(np.count_nonzero(present&(dif>0.03125))))
result=dict(status='CONDITIONAL_FULL_SHAPE_OPERATOR_DIAGNOSTIC_ONLY',actual_summary_sha256=sha(ACT/'summary.json'),script_sha256=sha(Path(__file__)),consumed_sha256=consumed,identity=identity,threads=torch.get_num_threads(),interop_threads=torch.get_num_interop_threads(),deterministic=torch.are_deterministic_algorithms_enabled(),mkldnn_enabled=torch.backends.mkldnn.enabled,autocast_enabled=torch.is_autocast_enabled('cpu'),layouts=layouts,original_stride_receipt_available=False,stride_reconstructed_from_frozen_source=True,official_full_scores_replayed_bit_exact=True,actual_vs_native_same_actual_operands=metrics(actual_scores,outputs['actual_operands']),native_actual_vs_official_operands=metrics(outputs['actual_operands'],ref_scores),actual_vs_official=metrics(actual_scores,ref_scores),elapsed_seconds=time.monotonic()-start,future_positions_remain_unobserved=True,full_block_reexecuted=False,thresholds_changed=False,native_acceptance=False)
for label,array in outputs.items():
 path=OUT/(label+'_scores.f32le');array.tofile(path);result[label+'_scores_sha256']=sha(path)
(OUT/'CONDITIONAL_QK.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('consumed_sha256','identity','layouts')}))
