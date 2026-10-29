"""P3/P4 full-expert input-only affine mappings. Never runs a DUT or forward."""
import argparse,hashlib,json,sys,math,importlib.util,os
from pathlib import Path

def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def align(n):return (n+63)&~63

def run(a):
 deps=json.loads(Path(__file__).with_name('P34_DEPENDENCIES.json').read_text())
 for root,rows in deps.items():
  for rel,pin in rows.items():
   if root=='programs' and not any(rel.startswith(f'profile{p}/') for p in a.profiles):continue
   p=getattr(a,root)/rel;need(p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256'],'dependency drift '+rel)
 base=a.repo/'candidates/five_profile_byte_provider';sys.path.insert(0,str(base));import emit_cold128_programs as emitter
 metadata=a.repo/'candidates/five_profile_input_recovery_20261028'
 spec=importlib.util.spec_from_file_location('plan',metadata/'reconstruct_plan.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 plan=mod.verified_plan(metadata);expected={t['name']:t for t in plan['specs'] if t['model']=='qwen3_5_35b_a3b'}
 a.output.mkdir(exist_ok=False);summary=[]
 for profile,layer in [(p,{3:0,4:3}[p]) for p in a.profiles]:
  d=a.output/f'profile{profile}';d.mkdir();b,_=emitter.common(profile);cb,db,m=b.finish();old=a.programs/f'profile{profile}';om=json.loads((old/'manifest.json').read_text())
  need(cb==(old/'commands.bin').read_bytes() and db==(old/'descriptors.bin').read_bytes(),'program bytes drift')
  need(all(m[k]==om[k] for k in ('launch','tensors','schedule','tokens')),'program geometry drift');l=m['launch'];need((l['commands'],l['descriptors'])=={3:(13,199),4:(18,241)}[profile],'counts')
  m['sha256']={'commands':hashlib.sha256(cb).hexdigest(),'descriptors':hashlib.sha256(db).hexdigest()};save(d/'manifest.json',m);(d/'commands.bin').write_bytes(cb+bytes(align(len(cb))-len(cb)));(d/'descriptors.bin').write_bytes(db+bytes(align(len(db))-len(db)))
  views=['AFFINE_BYTES_V1'];native={};bindings={};probes=[];pins={};files={}
  def source(tail):
   name=f'model.language_model.layers.{layer}.'+tail
   if name in files:return files[name]
   r=json.loads((a.payload/'qwen3_5_35b_a3b'/(name+'.receipt.json')).read_text());t=expected[name]
   need(all(r.get(k)==v for k,v in t.items()),'receipt differs from pinned header plan: '+name)
   rel=Path(r['file']);need(not rel.is_absolute() and '..' not in rel.parts,'unsafe source path');p=(a.payload/rel).resolve();need(p.is_relative_to(a.payload.resolve()),'source escape');need(p.stat().st_size==t['bytes'] and sha(p)==r['actual_sha256'] and r['actual_sha256'] in t['allowed_sha256'],'native size/hash')
   pins[p]=r['actual_sha256'];native[name]={**t,'file':str(rel),'actual_sha256':r['actual_sha256']};files[name]=(p,r);return p,r
  def row(name,t,p,shape,dst,src,word,offset=0,so=0):
   zero=p is None
   views.append('\t'.join(map(str,['map',name,t['address']+offset,t['address'],align(t['bytes']),len(shape),','.join(map(str,shape)),','.join(map(str,dst)),'-' if zero else p,so,','.join(map(str,src)),0 if zero else word,word,'zero' if zero else 'identity',0 if zero else p.stat().st_size,'-' if zero else pins.setdefault(p,sha(p)) if p not in pins else pins[p]])))
  def bind(name,kind,tails=(),input_path=None):
   t=m['tensors'][name];dims=t['dims'];size=t['bytes'];word={5:2,7:4}[t['dtype']];ss=[]
   for tail in tails:ss.append(source(tail))
   if input_path:
    p=input_path.resolve();need(p.stat().st_size==size,'input size');pins[p]=sha(p);ss=[(p,{'shape':dims,'dtype':'BF16','bytes':size})]
   for p,r in ss:need(r['dtype']==('BF16' if word==2 else 'F32'),'dtype')
   if kind=='zero':row(name,t,None,[size],[1],[0],1)
   elif kind=='flat':need(ss[0][1]['bytes']==size,'flat size');row(name,t,ss[0][0],[size],[1],[1],1)
   elif kind=='transpose':
    K,N=dims;need(ss[0][1]['shape']==[N,K],'transpose shape');row(name,t,ss[0][0],dims,[N*word,word],[word,K*word],word)
   elif kind=='ab':
    K,N=dims;need(N==64 and all(r['shape']==[32,K] for p,r in ss),'AB shape')
    for part,(p,r) in enumerate(ss):row(name,t,p,[K,32],[N*word,word],[word,K*word],word,part*32*word)
   elif kind in ('expert_gate','expert_up'):
    need(dims==[256,2048,512] and ss[0][1]['shape']==[256,1024,2048],'full expert gate_up shape');row(name,t,ss[0][0],dims,[2048*512*2,512*2,2],[1024*2048*2,2,2048*2],2,so=512*2048*2 if kind=='expert_up' else 0)
   elif kind=='expert_down':
    need(dims==[256,512,2048] and ss[0][1]['shape']==[256,2048,512],'full expert down shape');row(name,t,ss[0][0],dims,[512*2048*2,2048*2,2],[2048*512*2,2,512*2],2)
   elif kind=='gate_pad':
    need(dims==[2048,32] and ss[0][1]['shape']==[1,2048],'shared gate padded shape');row(name,t,ss[0][0],[2048,1],[64,2],[2,2],2);row(name+'_zeros',t,None,[2048,62],[64,1],[0,0],1,2)
   else:raise ValueError(kind)
   if align(size)>size:row(name+'_padding',t,None,[align(size)-size],[1],[0],1,size)
   # Independent raw source indexing by logical coordinates (not affine stride interpreter).
   handles=[p.open('rb') for p,r in ss]
   def byte(off):
    if off>=size or kind=='zero':return 0
    elem,within=divmod(off,word);which=0
    if kind=='flat':at=off
    elif kind=='transpose':k,n=divmod(elem,dims[1]);at=(n*dims[0]+k)*word+within
    elif kind=='ab':k,n=divmod(elem,64);which,n=divmod(n,32);at=(n*2048+k)*word+within
    elif kind in ('expert_gate','expert_up'):
     e,rem=divmod(elem,2048*512);k,n=divmod(rem,512);at=((e*1024+n+(512 if kind=='expert_up' else 0))*2048+k)*2+within
    elif kind=='expert_down':e,rem=divmod(elem,512*2048);k,n=divmod(rem,2048);at=((e*2048+n)*512+k)*2+within
    else:
     k,n=divmod(elem,32)
     if n:return 0
     at=k*2+within
    handles[which].seek(at);raw=handles[which].read(1);need(len(raw)==1,'probe raw source bounds');return raw[0]
   offsets={0,1,31,63,max(0,size-65),size-1,size}
   if len(dims)>1:offsets.update((dims[-1]*word-1,dims[-1]*word,size//2))
   if len(dims)==3:
    span=math.prod(dims[1:])*word
    for e in range(256):offsets.update((e*span,min(size-1,(e+1)*span-1),e*span+span//2))
   for off in sorted(offsets):
    if off<align(size):probes.append((t['address']+off,bytes(byte(j) for j in range(off,min(align(size),off+65))).hex()))
   for f in handles:f.close()
   bindings[name]={'kind':kind,'logical_dims':dims,'bytes':size,'dtype':t['dtype'],'sources':[{'path':str(p),'sha256':pins[p]} for p,r in ss]}
  hidden=a.inputs/f'P{profile}/hidden.storage.bin';need(sha(hidden)=='c32e36dd356244838b17f8aebd8a0e647c5a09198365ad32c6f7996adef237bb','hidden identity');bind('input','flat',input_path=hidden)
  for n,tail in {'input_gamma':'input_layernorm.weight','post_gamma':'post_attention_layernorm.weight'}.items():bind(n,'flat',[tail])
  if profile==3:
   for n,tail in {'qkv':'in_proj_qkv','z':'in_proj_z','o':'out_proj'}.items():bind(n+'_weight','transpose',['linear_attn.'+tail+'.weight'])
   bind('ab_weight','ab',['linear_attn.in_proj_a.weight','linear_attn.in_proj_b.weight'])
   for n,tail in {'conv_weight':'conv1d.weight','a_log':'A_log','dt_bias':'dt_bias','gated_gamma':'norm.weight'}.items():bind(n,'flat',['linear_attn.'+tail])
   for n in ('history_in','state_in'):bind(n,'zero')
  else:
   for n in ('q','k','v','o'):bind(n+'_weight','transpose',['self_attn.'+n+'_proj.weight'])
   for n in ('q','k'):bind(n+'_gamma','flat',['self_attn.'+n+'_norm.weight'])
   need(a.reference_result is not None and a.reference_result_sha256 is not None,'P4 independent actual RESULT pin required')
   need(sha(a.reference_result)==a.reference_result_sha256,'P4 RESULT hash mismatch');ref=json.loads(a.reference_result.read_text());rp=ref['profile']
   need(ref['status']=='CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY' and ref['complete_block_tokens']==128 and rp['profile']==4 and rp['layer']==3,'P4 official input provenance')
   need(rp['framework_revision']=='42ca97014c85d71a88ad60d55f08cb9fb4d26e2c' and rp['source_sha256']=='ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30' and rp['checkpoint_revision']=='62704185bd97ad488cfc404e7caea797396b74dc','P4 official source pins')
   need(ref['runtime_source_pins_sha256']=='79078825f230ffecf33fff9b838d40b155217b025accf26e961927a25a475743','P4 helper pins');rr=ref['tensor_records']['rope_packed']
   need(rr['file']=='input_only/rope_packed.bin' and rr['shape']==[1,128,64] and rr['dtype']=='torch.bfloat16' and rr['bytes']==16384,'P4 rope input-only contract');rope=a.reference_result.parent/rr['file'];need(sha(rope)==rr['sha256'],'P4 official input-only RoPE hash mismatch');bind('trig','flat',input_path=rope)
   bindings['trig']['independent_result_sha256']=a.reference_result_sha256
  for role,kind,tail in [(0,'transpose','gate.weight'),(1,'expert_gate','experts.gate_up_proj'),(2,'expert_up','experts.gate_up_proj'),(3,'expert_down','experts.down_proj'),(4,'transpose','shared_expert.gate_proj.weight'),(5,'transpose','shared_expert.up_proj.weight'),(6,'transpose','shared_expert.down_proj.weight'),(7,'transpose','shared_expert_gate.weight')]:bind(f'moe_weight_{role}',kind,['mlp.'+tail])
  bind('moe_shared_gate_padded','gate_pad',['mlp.shared_expert_gate.weight'])
  need(len(native)=={3:18,4:15}[profile] and set(native)=={n for n in expected if n.startswith(f'model.language_model.layers.{layer}.')},'complete native inventory');need(set(bindings)=={n for n,t in m['tensors'].items() if t['readonly']},'full RO coverage')
  config=['HOST_COMPILED_INPUT_V2','\t'.join(map(str,['launch']+[l[k] for k in ('version','profileId','epoch','commandBase','commandLimit','commands','descriptorBase','descriptorLimit','descriptors')]))];allocs=[]
  for i,r in enumerate(l['regions']):config.append('\t'.join(map(str,['region',i,r['base'],r['limit'],int(r['read']),int(r['write'])])))
  for name,stem in [('commands','command'),('descriptors','descriptor')]:
   p=d/(name+'.bin');t={'address':l[stem+'Base'],'bytes':p.stat().st_size};allocs.append((name,t['address'],t['bytes'],t['bytes'],'ro'));row(name,t,p,[t['bytes']],[1],[1],1);probes.append((t['address'],p.read_bytes()[:65].hex()))
  for name,t in m['tensors'].items():allocs.append((name,t['address'],align(t['bytes']),align(t['bytes']),'virtual' if t['virtual'] else 'ro' if t['readonly'] else 'rw'))
  r=l['regions'][3];allocs.append(('dense_transport_scratch',r['base'],r['limit']-r['base'],r['limit']-r['base'],'rw'))
  for al in sorted(allocs,key=lambda x:x[1]):config.append('\t'.join(map(str,['allocation',*al])))
  for s in m['schedule']:
   for n in s['outputs']:
    t=m['tensors'][n]
    if not t['virtual']:config.append('\t'.join(map(str,['observe',s['pc'],n,t['address'],align(t['bytes']),t['dtype']])))
  (d/'views.tsv').write_text('\n'.join(views)+'\n');config.append('views\t'+str(d/'views.tsv'));(d/'runtime.tsv').write_text('\n'.join(config)+'\n');(d/'PRIVATE_PROBES.tsv').write_text('\n'.join(f'{p}\t{h}' for p,h in probes)+'\n')
  save(d/'source_spec.json',{'status':'NEW_FULL_EXPERT_INPUT_MAPPING_NOT_DUT','profile':profile,'native':native,'bindings':bindings,'numeric_pass':False,'all_experts':256,'reference_outputs_injected':False})
  summary.append({'profile':profile,'native_count':len(native),'RO_bytes':sum(x['bytes'] for x in bindings.values()),'probe_records':len(probes),'commands':l['commands'],'descriptors':l['descriptors'],'source_spec_sha256':sha(d/'source_spec.json')});save(a.output/'SUMMARY.json',{'status':'PENDING_CPP_TRANSPORT_QUALIFICATION','profiles':summary,'dut_executed':False});print(json.dumps(summary[-1]),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for flag in ('repo','programs','payload','inputs','output'):p.add_argument('--'+flag,type=lambda s:Path(s).resolve(),required=True)
 p.add_argument('--reference-result',type=Path);p.add_argument('--reference-result-sha256');p.add_argument('--profiles',type=int,nargs='+',choices=[3,4],default=[3,4]);run(p.parse_args())
