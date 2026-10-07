"""One-time archival extraction; requires original pinned historical NPZ files.

This reads and slices native arrays; it never executes a model or computes
replacement expected activations. Normal tests load frozen fixtures directly.
"""
from pathlib import Path
import hashlib,json,shutil
import numpy as np
root=Path(__file__).resolve().parents[3];dest=root/'tests/fixtures/qk_norm256'
def check(path,expected):
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    if h!=expected: raise ValueError(f'untrusted historical source {path}: {h}')
    return {'file':path.name,'bytes':path.stat().st_size,'sha256':h}
prior=json.loads((root/'tests/fixtures/rope_rounding/provenance.json').read_text())
fixed_reports={'local':'fece52d072ea997675a59865ed1e5ffb48ac28e41b7ae3e8e32552f8e9d0fda1','remote':'d04f72678b8347bcf872f5a33c5948a0fc66e14a4f98d1a60d0976a611523d25'}
fixed_arrays={'local':'836ce634c677f5b171c69c525a8d5cf6d018b30414f06427c236c8c08803bff7','remote':'81f51be898714b17602eaa63e51d945c7a7552cf0e0e25648fbe863948f4fe48'}
for name in ('local','remote'):
 if prior[name]['original_audit_report']['sha256']!=fixed_reports[name] or prior[name]['original_audit_arrays']['sha256']!=fixed_arrays[name]: raise ValueError('independently pinned source authority drift')
manifest=root/'work/qwen35_layer3_payload/manifest.json';check(manifest,'31d12acb34c7c0c4ad031a93a1ef46203ec21e193865728ada407dbbe014cd66')
weight_hashes={'q':'6fbc460e96b527aa6b54ab345195d141716dd4e34094baec92c65344f8bac298','k':'424ead8a89f71d4e83858da7f28335665c4d61a8797b121cfaa26a56d1f5ea6a'}
weights=[];weight_info=[]
for role in ['q','k']:
 p=manifest.parent/f'self_attn.{role}_norm.weight.bin';weight_info.append(check(p,weight_hashes[role]));weights.append(np.fromfile(p,dtype='<u2').astype(np.uint32)<<16)
weights=np.array(weights,dtype='<u4')
meta={'schema_version':1,'policy':193,'head_dim':256,'epsilon_word':0x358637bd,'roles':['q','k'],'phases':['cold_m128','carried_m128'],'model_id':prior['local']['model_id'],'revision':prior['local']['revision'],'framework_revision':prior['local']['framework_revision'],'layer_id':3,'payload_manifest':check(manifest,'31d12acb34c7c0c4ad031a93a1ef46203ec21e193865728ada407dbbe014cd66'),'weights':weight_info,'arithmetic_recomputed_when_freezing':False,'corpora':{}}
shutil.copyfile(manifest,dest/'payload_manifest.json')
for name,rel in [('local','work/bf16_recovery/final_saved'),('remote','work/rope_rounding_ablation/remote_native/bf16')]:
 d=root/rel; old=prior[name];report=check(d/'result.json',old['original_audit_report']['sha256']);arrays=check(d/'all_bf16_producers.npz',old['original_audit_arrays']['sha256']);r=json.loads((d/'result.json').read_text())
 if any(r[k]!=meta[k] for k in ['model_id','revision','layer_id']):raise ValueError('weight identity mismatch')
 for idx,key in [(8,'self_attn.q_proj|aten.linear.default|0'),(16,'self_attn.q_norm|cast_bf16|0'),(17,'self_attn.k_proj|aten.linear.default|0'),(25,'self_attn.k_norm|cast_bf16|0')]:
  if r['producer_sequence'][idx]['key']!=key:raise ValueError('producer sequence drift')
 shutil.copyfile(d/'result.json',dest/(name+'_original_report.json'))
 z=np.load(d/'all_bf16_producers.npz',allow_pickle=False);inputs=[];native=[];gate=[];phase=[];token=[];head=[];roles=[];gi=[];groups=[];gate_start=0;row_start=0
 for phase_id,case in enumerate(meta['phases']):
  for role_id,(role,proj,norm,H) in enumerate([('q',8,16,8),('k',17,25,2)]):
   pk=f'{case}_native_producer_{proj:02d}';nk=f'{case}_native_producer_{norm:02d}';p=z[pk];n=z[nk]
   if p.dtype!=np.float32 or n.dtype!=np.float32 or p.shape!=(1,128,H*(512 if role=='q' else 256)) or n.shape!=(1,128,H,256): raise ValueError('historical dtype/shape drift')
   p=p.view(np.uint32).reshape(128,H,-1);n=n.view(np.uint32).reshape(-1,256)
   if np.any(p&65535) or np.any(n&65535):raise ValueError('non-BF16 historical words')
   inputs.append(p[:,:,:256].reshape(-1,256));native.append(n)
   phase.extend([phase_id]*(128*H));token.extend(np.repeat(np.arange(128),H));head.extend(np.tile(np.arange(H),128));roles.extend([role_id]*(128*H))
   if role=='q':gate.append(p[:,:,256:].reshape(-1,256));gi.extend(range(gate_start,gate_start+128*H));gate_start+=128*H
   else:gi.extend([-1]*(128*H))
   groups.append({'phase':case,'role':role,'start':row_start,'heads':128*H,'input_key':pk,'native_key':nk,'input_mapping':'reshape(1,128,8,512)[...,0:256]' if role=='q' else 'reshape(1,128,2,256)','gate_mapping':'reshape(1,128,8,512)[...,256:512]' if role=='q' else None});row_start+=128*H
 data={'input_bf16_u32':np.concatenate(inputs).astype('<u4'),'native_bf16_u32':np.concatenate(native).astype('<u4'),'gate_bf16_u32':np.concatenate(gate).astype('<u4'),'weight_bf16_u32':weights,'phase':np.array(phase,dtype=np.uint8),'token':np.array(token,dtype=np.uint8),'head':np.array(head,dtype=np.uint8),'role':np.array(roles,dtype=np.uint8),'gate_index':np.array(gi,dtype='<i4')}
 np.savez_compressed(dest/(name+'.npz'),**data)
 record={'bundle':{'file':name+'.npz','bytes':(dest/(name+'.npz')).stat().st_size,'sha256':hashlib.sha256((dest/(name+'.npz')).read_bytes()).hexdigest()},'historical_payload_manifest_sha256':r['payload_manifest_sha256'],'original_audit_report':report,'original_audit_arrays':arrays,'groups':groups,'array_sha256':{k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in data.items()},'historical_native_audit_status':r['status'],'historical_native_failed_comparisons':old['historical_native_failed_comparisons'],'environment':old['environment']}
 meta['corpora'][name]=record
(dest/'provenance.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps({name:meta['corpora'][name]['bundle'] for name in meta['corpora']},indent=2));print('provenance',hashlib.sha256((dest/'provenance.json').read_bytes()).hexdigest())
