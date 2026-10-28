"""NEW P0 input-only byte provider; no reference output or arithmetic execution."""
import argparse,json,hashlib,importlib.util,sys,shutil,os
from pathlib import Path
import numpy as np

def need(x,s):
 if not x:raise ValueError(s)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n');return sha(p)
def mod(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def run(a):
 pin_package=(a.pin_package or (a.repo/'candidates/five_profile_input_recovery_20261028')).resolve()
 sys.path.insert(0,str(pin_package));from reconstruct_plan import verified_plan,same
 pinned={x['name']:x for x in verified_plan()['specs'] if x['model']=='qwen2_1p5b'}
 repo=a.repo.resolve();out=a.output.resolve();need(not out.exists(),'new output required');out.mkdir();data=out/'input_only';data.mkdir();providers=[];files={};provenance=[]
 def emit(name,b,mapping,source):
  p=data/(name+'.bin');p.write_bytes(b);d=sha(p);files[d]=str(p);providers.append({'name':name,'sha256':d,'bytes':len(b)});provenance.append({'name':name,'mapping':mapping,'source':source,'sha256':d,'bytes':len(b)})
 matrix={'wq':'self_attn.q_proj.weight','wk':'self_attn.k_proj.weight','wv':'self_attn.v_proj.weight','wo':'self_attn.o_proj.weight','wg':'mlp.gate_proj.weight','wu':'mlp.up_proj.weight','wd':'mlp.down_proj.weight'}
 vectors={'gamma0':'input_layernorm.weight','gamma1':'post_attention_layernorm.weight','bq':'self_attn.q_proj.bias','bk':'self_attn.k_proj.bias','bv':'self_attn.v_proj.bias'}
 for name,tail in {**matrix,**vectors}.items():
  official='model.layers.0.'+tail;r=json.loads((a.payload/'qwen2_1p5b'/(official+'.receipt.json')).read_text());p=a.payload/r['file'];need(all(same(r.get(k),v) for k,v in pinned[official].items()),'fixed acquisition plan drift');need(p.resolve().is_relative_to(a.payload.resolve()),'weight path escape');need(r['name']==official and r['revision']=='ba1cf1846d7df0a0591d6c00649f57e798519da8','official identity');need(p.stat().st_size==r['bytes'] and sha(p)==r['actual_sha256'],'weight hash/size');need(r['dtype']=='BF16','native weight dtype')
  ar=np.fromfile(p,dtype='<u2').reshape(r['shape'])
  if name in matrix:b=ar.T.copy().tobytes();mapping='native BF16LE transpose [N,K] to [K,N]'
  else:b=(ar.astype('<u4')<<16).tobytes();mapping='exact BF16 bit expansion into FP32 storage'
  emit(name,b,mapping,{'name':official,'sha256':r['actual_sha256'],'shape':r['shape'],'revision':r['revision']})
 result=json.loads((a.reference/'RESULT.json').read_text());h=result['tensor_records']['hidden_storage'];need(h['file']=='input_only/hidden_storage.bin','input-only hidden');p=a.reference/h['file'];need(sha(p)==h['sha256'],'hidden hash');emit('x',p.read_bytes(),'NEW external boundary FP32 storage',{'sha256':h['sha256'],'file':'input_only/hidden_storage.bin'})
 # Extended official input-only rotary table is separately pinned by caller.
 need(sha(a.rope)==a.rope_sha256 and a.rope.stat().st_size==2*1024*64*4,'official extended rope pin/shape');emit('rope',a.rope.read_bytes(),'official FP32 cosine/sine first-half tables [2,1024,64]',{'sha256':a.rope_sha256})
 scripts=repo/'chisel/continuous_prefill/scripts';pack=mod('pack',scripts/'pack_owner_block_fixture.py');conv=mod('conv',scripts/'pack_owner_bf16_weights.py');pack.pack(dict(H=1536,F=8960,HEADS=12,KVHEADS=2,HD=128,MAX_TOKENS=1024),128,out/'original_metadata');conv.convert(out/'original_metadata',out/'program')
 mp=out/'program/manifest.json';need(sha(mp)=='c5fcd45a4cee53b084a0915753186b06540342bb0620a783f528fefb83b9b561','original corrected ABI pin');m=json.loads(mp.read_text());m['scope']['synthetic_weights']=False;m['input_identity']='NEW_EXTERNAL_BOUNDARY_FRESH_OFFICIAL_WEIGHTS';save(mp,m)
 need(set(x['name'] for x in providers)=={n for n,t in m['tensors'].items() if t['readonly']},'RO inventory')
 pm=out/'source_manifest.json';ps=save(pm,{'status':'INPUT_ONLY_NOT_DUT','sources':provenance});files[ps]=str(pm)
 spec={'metadata_sha256':sha(mp),'provider_manifest_sha256':ps,'provider_manifest_path':'source_manifest.json','provenance_sha256':ps,'provenance_path':'source_manifest.json','providers':providers,'matrix_names':list(matrix)}
 sp=out/'source_spec.json';ss=save(sp,spec);files[ss]=str(sp);files[sha(mp)]=str(mp)
 src=repo/'candidates/recovered_execution_fixes/provider_candidate';dest=out/'provider';shutil.copytree(src,dest);rp=dest/'qwen2/payloads.py';text=rp.read_text().replace('34dea02dab7dd10d34ae0e3969202bbb91f10d1f7966f308eb01e4d4e803ee6e',ss).replace('a3e04946be19d274181ed5839b3047e19a4b450f5421ab3d748774e0312e9522',sha(mp)).replace('c5fcd45a4cee53b084a0915753186b06540342bb0620a783f528fefb83b9b561',sha(mp)).replace('legacy source metadata binding changed','NEW source metadata binding changed');rp.write_text(text)
 save(out/'local_inputs.json',{'files':files});os.environ['BYTE_PROVIDER_INPUTS']=str(out/'local_inputs.json');sys.path.insert(0,str(dest));reader=mod('fresh_p0',rp);readers,report=reader.build_readers(mp);logical={};checks=0
 try:
  for n,r in readers.items():
   expected=(data/(n+'.bin')).read_bytes();need(r.size==len(expected),'reader size');d=hashlib.sha256()
   for off in range(0,r.size,1048576):d.update(r.read(off,min(1048576,r.size-off)))
   need(d.hexdigest()==hashlib.sha256(expected).hexdigest(),'full stream hash')
   for off in sorted({0,1,63,max(0,r.size-65),r.size-1,r.size}):
    z=min(65,r.size-off);need(r.read(off,z)==expected[off:off+z],'unaligned boundary');checks+=1
   logical[n]={'sha256':d.hexdigest(),'bytes':r.size}
   for off,z in [(-1,1),(r.size,1),(0,r.size+1)]:
    try:r.read(off,z)
    except ValueError:checks+=1
    else:raise ValueError('reader accepted invalid boundary')
  from memory_provider import MemoryProvider,MemoryAccessError
  metadata=[]
  for label,base,limit,fn in [('commands','commandBase','commandLimit','host_commands.bin'),('descriptors','descriptorBase','descriptorLimit','host_descriptors.bin')]:
   b=(out/'program'/fn).read_bytes();need(len(b)==m[limit]-m[base],'metadata extent');metadata.append((label,m[base],b))
  mem=MemoryProvider(m,readers,metadata,rw_alias_groups=[('kv','cache_k','cache_v')])
  for start,end,name,ro,r in mem.regions:
   if ro:
    need(mem.read(start,min(65,end-start))==r.read(0,min(65,end-start)),'mapped reader')
    try:mem.write(start,b'X')
    except MemoryAccessError:checks+=1
    else:raise ValueError('RO write accepted')
   else:
    try:mem.read(start,1)
    except MemoryAccessError:checks+=1
    else:raise ValueError('RW reference preload')
  need(not mem.pages and not mem.valid,'transport tests populated RW')
 finally:
  for r in readers.values():r.close()
 save(out/'RESULT.json',{'status':'P0_NEW_INPUT_ONLY_PROVIDER_STREAMS_VERIFIED_NOT_CHISEL_OR_RTL','logical_ro':logical,'boundary_checks':checks,'manifest_sha256':sha(mp),'source_spec_sha256':ss,'provider_source_sha256':sha(rp),'full_block_numeric_pass':False})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pin-package',type=Path);p.add_argument('--repo',type=Path,required=True);p.add_argument('--payload',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--rope',type=Path,required=True);p.add_argument('--rope-sha256',required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
