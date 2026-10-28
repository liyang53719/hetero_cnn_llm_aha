"""Reconstruct input-only P1/P2 affine byte maps. No arithmetic or DUT execution."""
import argparse,hashlib,json,sys,math
from pathlib import Path
import numpy as np

def need(v,s):
 if not v: raise ValueError(s)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def aligned(n):return (n+63)&~63

def run(a):
 root=a.root.resolve();base=root/'hetero_verified_recovery_20261028T2035/candidates/five_profile_byte_provider';sys.path.insert(0,str(base));import emit_cold128_programs as emitter
 out=a.output.resolve();out.mkdir(exist_ok=False);report=[]
 for profile,layer in [(1,0),(2,3)]:
  d=out/f'profile{profile}';d.mkdir();b,_=emitter.common(profile);cb,db,m=b.finish();old=root/f'environment_recovery_20261028T2032/programs/profile{profile}';om=json.loads((old/'manifest.json').read_text())
  need(cb==(old/'commands.bin').read_bytes() and db==(old/'descriptors.bin').read_bytes(),'regenerated command bytes differ')
  need(all(m[k]==om[k] for k in ('launch','tensors','schedule','tokens')),'regenerated geometry differs')
  need((m['launch']['commands'],m['launch']['descriptors'])==({1:(17,219),2:(22,261)}[profile]),'program counts')
  m['sha256']={'commands':hashlib.sha256(cb).hexdigest(),'descriptors':hashlib.sha256(db).hexdigest()};m['input_identity']='NEW_EXTERNAL_BOUNDARY_T2307';save(d/'manifest.json',m)
  (d/'commands.bin').write_bytes(cb+bytes(aligned(len(cb))-len(cb)));(d/'descriptors.bin').write_bytes(db+bytes(aligned(len(db))-len(db)))
  ref=root/f'full_block_P{profile}_20261028T2307/reference';result=json.loads((ref/'RESULT.json').read_text());need(result['complete_block_tokens']==128 and result['profile']['profile']==profile,'reference input contract')
  views=['AFFINE_BYTES_V1']; specs={};probes=[];logical={};native={};allocs=[]
  def source(tail):
   name=f'model.language_model.layers.{layer}.'+tail;rr=root/'five_profile_payload_recovery_20261028T2258';r=json.loads((rr/'qwen3_5_0p8b'/(name+'.receipt.json')).read_text());p=rr/r['file']
   need(r['name']==name and r['revision']=='2fc06364715b967f1860aea9cf38778875588b17','native identity');need(sha(p)==r['actual_sha256']==r['expected_sha256'] and p.stat().st_size==r['bytes'],'native hash')
   need(math.prod(r['shape'])*{'BF16':2,'F32':4}[r['dtype']]==r['bytes'],'native shape')
   native[name]={k:r[k] for k in ('name','revision','shape','dtype','bytes','actual_sha256')}
   return p,r
  def row(name,t,p,shape,dst,src,word,offset=0,source_offset=0):
   zero=p is None;views.append('\t'.join(map(str,['map',name,t['address']+offset,t['address'],aligned(t['bytes']),len(shape),','.join(map(str,shape)),','.join(map(str,dst)),'-' if zero else p,source_offset,','.join(map(str,src)),0 if zero else word,word,'zero' if zero else 'identity',0 if zero else p.stat().st_size,'-' if zero else sha(p)])))
  def bind(name,kind,tails=None,input_name=None):
   t=m['tensors'][name];word=2 if t['dtype']==5 else 4;size=t['bytes'];dims=t['dims'];sources=[]
   if kind=='zero':expected=bytes(size);row(name,t,None,[size],[1],[0],1)
   elif input_name:
    rec=result['tensor_records'][input_name];need(rec['file'].startswith('input_only/'),'no reference output');p=ref/rec['file'];need(sha(p)==rec['sha256'] and p.stat().st_size==size,'input hash/size');expected=p.read_bytes();row(name,t,p,[size],[1],[1],1);sources=[{'file':rec['file'],'sha256':rec['sha256'],'bytes':size}]
   else:
    arrays=[]
    for tail in tails:
     p,r=source(tail);need(r['dtype']==('BF16' if word==2 else 'F32'),'dtype mismatch');sources.append(native[r['name']]);arrays.append(np.fromfile(p,dtype='<u2' if word==2 else '<u4').reshape(r['shape']))
     if kind=='flat':need(r['bytes']==size,'flat size');row(name,t,p,[size],[1],[1],1)
     elif kind=='transpose':
      K,N=dims;need(r['shape']==[N,K],'transpose shape');row(name,t,p,[K,N],[N*word,word],[word,K*word],word)
     elif kind=='concat_transpose':
      K,N=dims;need(r['shape']==[16,K] and N==32,'AB dimensions');part=len(arrays)-1;row(name,t,p,[K,16],[N*word,word],[word,K*word],word,part*16*word)
    if kind=='flat':expected=arrays[0].tobytes()
    elif kind=='transpose':expected=arrays[0].T.copy().tobytes()
    else:expected=np.concatenate([ar.T for ar in arrays],axis=1).tobytes()
   need(len(expected)==size,'logical size');padding=aligned(size)-size
   if padding:row(name+'_bus_padding',t,None,[padding],[1],[0],1,size)
   payload=expected+bytes(padding);logical[name]={'address':t['address'],'logical_bytes':size,'allocation_bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
   specs[name]={'mapping':kind,'logical_dims':dims,'dtype':t['dtype'],'sources':sources}
   # Independent NumPy materialization checks row/column and concat boundaries, unaligned/end accesses.
   offsets={0,1,31,32,63,max(0,size-65),size-1,size}
   if len(dims)==2:offsets.update({dims[1]*word-1,dims[1]*word,min(size-1,(dims[0]//2)*dims[1]*word+word)})
   for off in sorted(offsets):
    if off<len(payload):probes.append((t['address']+off,payload[off:min(len(payload),off+65)].hex()))
  common={'input_gamma':'input_layernorm.weight','post_gamma':'post_attention_layernorm.weight'}
  bind('input','flat',input_name='hidden_storage')
  for n,tail in common.items():bind(n,'flat',[tail])
  for n in ('gate','up','down'):bind(n+'_weight','transpose',['mlp.'+n+'_proj.weight'])
  if profile==1:
   for n,tail in {'qkv':'in_proj_qkv','z':'in_proj_z','o':'out_proj'}.items():bind(n+'_weight','transpose',['linear_attn.'+tail+'.weight'])
   bind('ab_weight','concat_transpose',['linear_attn.in_proj_a.weight','linear_attn.in_proj_b.weight'])
   for n,tail in {'conv_weight':'conv1d.weight','a_log':'A_log','dt_bias':'dt_bias','gated_gamma':'norm.weight'}.items():bind(n,'flat',['linear_attn.'+tail])
   for n in ('history_in','state_in'):bind(n,'zero')
  else:
   for n in ('q','k','v','o'):bind(n+'_weight','transpose',['self_attn.'+n+'_proj.weight'])
   for n in ('q','k'):bind(n+'_gamma','flat',['self_attn.'+n+'_norm.weight'])
   bind('trig','flat',input_name='rope_packed')
  need(set(specs)=={n for n,t in m['tensors'].items() if t['readonly']},'RO coverage')
  l=m['launch'];config=['HOST_COMPILED_INPUT_V2','\t'.join(map(str,['launch']+[l[k] for k in ('version','profileId','epoch','commandBase','commandLimit','commands','descriptorBase','descriptorLimit','descriptors')]))]
  for i,r in enumerate(l['regions']):config.append('\t'.join(map(str,['region',i,r['base'],r['limit'],int(r['read']),int(r['write'])])))
  for name,stem in [('commands','command'),('descriptors','descriptor')]:
   p=d/(name+'.bin');t={'address':l[stem+'Base'],'bytes':p.stat().st_size};allocs.append((name,t['address'],t['bytes'],t['bytes'],'ro'));row(name,t,p,[t['bytes']],[1],[1],1);probes.append((t['address'],p.read_bytes()[:65].hex()))
  for name,t in m['tensors'].items():allocs.append((name,t['address'],aligned(t['bytes']),aligned(t['bytes']),'virtual' if t['virtual'] else 'ro' if t['readonly'] else 'rw'))
  r=l['regions'][3];allocs.append(('dense_transport_scratch',r['base'],r['limit']-r['base'],r['limit']-r['base'],'rw'))
  for allocation in sorted(allocs,key=lambda x:x[1]):config.append('\t'.join(map(str,['allocation',*allocation])))
  for s in m['schedule']:
   for n in s['outputs']:
    t=m['tensors'][n]
    if not t['virtual']:config.append('\t'.join(map(str,['observe',s['pc'],n,t['address'],aligned(t['bytes']),t['dtype']])))
  (d/'views.tsv').write_text('\n'.join(views)+'\n');config.append('views\t'+str(d/'views.tsv'));(d/'runtime.tsv').write_text('\n'.join(config)+'\n');(d/'PRIVATE_PROBES.tsv').write_text('\n'.join(f'{p}\t{h}' for p,h in probes)+'\n')
  save(d/'source_spec.json',{'profile':profile,'status':'NEW_INPUT_ONLY_BYTE_MAPPING_NOT_DUT','bindings':specs,'native_sources':native,'input_reference_result_sha256':sha(ref/'RESULT.json'),'program_geometry_matches_regenerated_original':True,'numeric_pass':False})
  save(d/'LOGICAL_HASHES.json',logical);report.append({'profile':profile,'commands':l['commands'],'descriptors':l['descriptors'],'native_sources':len(native),'logical_ro_bytes':sum(x['logical_bytes'] for x in logical.values()),'probe_records':len(probes),'source_spec_sha256':sha(d/'source_spec.json'),'runtime_sha256':sha(d/'runtime.tsv'),'views_sha256':sha(d/'views.tsv')})
 save(out/'SUMMARY.json',{'status':'RECONSTRUCTED_PENDING_CPP_PROBES_NOT_DUT','profiles':report,'numeric_pass':False});print(json.dumps(report))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path.cwd());p.add_argument('--output',type=Path,required=True);run(p.parse_args())
