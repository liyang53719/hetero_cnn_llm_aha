from pathlib import Path
from fractions import Fraction
import json,hashlib,struct,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
assert hashlib.sha256((ROOT/'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py').read_bytes()).hexdigest()=='daf80d7d6273e9818e63aa030be8ec1ead07324ddcafc82ef8d165ed55065d4e', 'independent integer RNE helper drift'
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import exact,rn,ref_add,ref_bf
ACT=ROOT/'work/qwen2_official_public21_20261012/actual_m128_02';OUT=ROOT/'work/qwen2_official_public21_20261012/q_projection_attribution';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((ACT/'summary.json').read_text());assert sha(ACT/'summary.json')=='25b947ff774412685d9691de0a06f1a1cf489388557db357013bf7911c11681a'
previous_path=ROOT/'reports/execution/QWEN2_BF16_ERROR_ATTRIBUTION_20261011/ATTRIBUTION.json';previous=json.loads(previous_path.read_text());assert sha(previous_path)=='2e5991c9efb31e980c8ef9199717b6c7a0e4d58b91f3bcfd5faa4086d2c3519a'
consumed={}
def read(path,digest):
 assert sha(path)==digest,str(path);consumed[str(path.relative_to(ROOT))]=digest;return path.read_bytes()
def actual(name,shape):
 rec=r['sealed_actual_outputs'][name];raw=read(ACT/('actual_'+name+'.f32le'),rec['sha256']);assert len(raw)==rec['bytes'];return np.frombuffer(raw,dtype='<u4').reshape(shape)
def oldfile(path):return read(ROOT/path,previous['consumed_files'][path]['sha256'])
n0=actual('n0',(128,1536));qraw=actual('qraw',(128,1536));qr=actual('qr',(128,1536));q=actual('q',(128,12,128));k=actual('k',(128,2,128))
w=np.frombuffer(oldfile('work/qwen2_layer0_payload_20261011/self_attn.q_proj.weight.bin'),dtype='<u2').reshape(1536,1536).astype('uint32')<<16
bias=np.frombuffer(oldfile('work/qwen2_layer0_payload_20261011/self_attn.q_proj.bias.bin'),dtype='<u2').astype('uint32')<<16
reference=np.frombuffer(oldfile('work/qwen2_rms_rope_prefill_v2_m128_20261011/cold/references/official_self_cache/qr.f32le'),dtype='<u4').reshape(128,1536)
assert read(ACT/'actual_n0.f32le',r['sealed_actual_outputs']['n0']['sha256'])==oldfile('work/qwen2_rms_rope_prefill_v2_m128_20261011/cold/references/official_self_cache/n0.f32le')
indices=np.argwhere(qr!=reference);assert len(indices)==40
rows=[];start=time.monotonic()
for token,col in indices:
 products=[exact(int(x))*exact(int(y)) for x,y in zip(n0[token],w[col])]
 total=sum(products,Fraction());seq=0
 for product in products:seq=rn(exact(seq)+product)
 assert seq==int(qraw[token,col]);assert ref_bf(ref_add(seq,int(bias[col])))==int(qr[token,col])
 exact_fused=ref_bf(rn(total+exact(int(bias[col]))));exact_dot_then_bias=ref_bf(ref_add(rn(total),int(bias[col])))
 rows.append(dict(token=int(token),output_channel=int(col),actual_qraw_hex=hex(seq),actual_qr_hex=hex(int(qr[token,col])),official_qr_hex=hex(int(reference[token,col])),exact_dot_then_fp32_bias_bf16_hex=hex(exact_dot_then_bias),exact_fused_dot_bias_bf16_hex=hex(exact_fused),exact_fused_matches_official=bool(exact_fused==reference[token,col]),exact_dot_then_bias_matches_official=bool(exact_dot_then_bias==reference[token,col])))
fields=r['observation']['fields'];ix=(9,102,2);observed={}
for name in ('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16'):
 rec=fields[name];raw=read(ACT/'attention_observation'/(name+'.u32le'),rec['raw_sha256']);values=np.frombuffer(raw,dtype='<u4').reshape(rec['shape']);value=values[ix];observed[name]=[hex(int(x)) for x in value] if isinstance(value,np.ndarray) else dict(hex=hex(int(value)),value=struct.unpack('<f',struct.pack('<I',int(value)))[0])
result=dict(status='READ_ONLY_SELECTED_PROJECTION_ATTRIBUTION_NOT_ACCEPTANCE',actual_summary_sha256=sha(ACT/'summary.json'),previous_attribution_sha256=sha(previous_path),script_sha256=sha(Path(__file__)),independent_rne_source_sha256=sha(ROOT/'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py'),consumed_sha256=consumed,scope='All 40 actual-vs-official QR bit differences; 1536 products each. Exact rational calculations are diagnostic only and propose no hardware precision/resource change. No native forward or complete chain rerun.',actual_n0_official_bit_exact=True,sequential_fp32_recipe_matches_all_40_raw_actual=True,rows=rows,exact_fused_matches=sum(x['exact_fused_matches_official'] for x in rows),exact_dot_then_bias_matches=sum(x['exact_dot_then_bias_matches_official'] for x in rows),worst_causal_score_coordinate=list(ix),actual_observed_worst=observed,seconds=time.monotonic()-start)
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('rows','consumed_sha256')}))
