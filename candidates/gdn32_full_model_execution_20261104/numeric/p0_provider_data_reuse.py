"""P0 pure immutable byte reuse. No DUT/runtime PASS, alias creation or data write."""
import argparse,hashlib,json,os,stat,mmap
from pathlib import Path
REV='ba1cf1846d7df0a0591d6c00649f57e798519da8'
MATRIX={'wq':('self_attn.q_proj.weight',[1536,1536]),'wk':('self_attn.k_proj.weight',[256,1536]),'wv':('self_attn.v_proj.weight',[256,1536]),'wo':('self_attn.o_proj.weight',[1536,1536]),'wg':('mlp.gate_proj.weight',[8960,1536]),'wu':('mlp.up_proj.weight',[8960,1536]),'wd':('mlp.down_proj.weight',[1536,8960])}
VECTORS={'gamma0':('input_layernorm.weight',[1536]),'gamma1':('post_attention_layernorm.weight',[1536]),'bq':('self_attn.q_proj.bias',[1536]),'bk':('self_attn.k_proj.bias',[256]),'bv':('self_attn.v_proj.bias',[256])}
PROGRAM={'manifest':'manifest.json','commands':'host_commands.bin','descriptors':'host_descriptors.bin'}
METADATA={'source_manifest':'source_manifest.json','source_spec':'source_spec.json','provider_result':'RESULT.json'}
SOURCE_CONTRACT={'rebuild': ('candidates/p0_newboundary_input_provider_20261028/rebuild.py', '400732c713e4df4f14220b11cb0b6adb5bd6218c64a4d7a0a35934594143d1aa'), 'emit': ('candidates/p0_newboundary_input_provider_20261028/emit_tsv.py', 'fe08d00c8a06a15c2fb734e1b637e09f96fe651a6cfb5d05fc8b5b0b3c323ec6'), 'pack': ('chisel/continuous_prefill/scripts/pack_owner_block_fixture.py', '3efc7bb21b66bd16f757b8aac99c779ad3efe9289115e6ea7d5628a4ff6c2154'), 'convert': ('chisel/continuous_prefill/scripts/pack_owner_bf16_weights.py', '17347fccdf73f54692b4e1c8047a26154f55348f06dca87c5c2db7def515c692'), 'config': ('config/upstream/weight_headers/qwen2_1p5b/config.json', 'a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136'), 'reconstruct': ('candidates/five_profile_input_recovery_20261028/reconstruct_plan.py', '466c267f7a0c6eaaefc41705112196b6c4f29a037da03b692237f89b95b7baee')}
PROGRAM_PINS={'manifest': '4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163', 'commands': '618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4', 'descriptors': '1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02'}
def need(v,m):
 if not v:raise ValueError(m)
def digest(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(path):
 p=Path(path);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in (p,*p.parents)),'canonical no-symlink path')
 s=p.lstat();need(stat.S_ISREG(s.st_mode),'regular file');return p,s
def check(row,cap=2<<20,content=True):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'},'exact pin')
 p,s=regular(row['path']);need(type(row['bytes'])is int and 0<row['bytes']<=cap and s.st_size==row['bytes'],'pin size')
 h=row['sha256'];need(type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'hex pin')
 if content:need(digest(p)==h,'pin hash')
 return p
def load(row):return json.loads(check(row).read_text())
def makepin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=digest(p))
FIRST_FAULT_MODE='P0_FIRST_FAULT_DIAGNOSTIC'
FIRST_FAULT_SCHEMA='P0_DATA_REUSE_FIRST_FAULT_BINDING_V1'
def first_fault_relation(d,b,artifact,prior):
 """Pure reviewed data lineage, never live execution or historical ABI admission."""
 import types
 need(b.get('execution_mode')==FIRST_FAULT_MODE,'explicit first fault data reuse')
 repo=Path(b['repo']);catalog=load(b['source_pins']);need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','reviewed current catalog')
 rows=catalog['files'];need(len({r['path']for r in rows})==len(rows),'unique current source paths')
 pins={}
 for row in rows:
  rel=Path(row['path']);need(not rel.is_absolute()and '..'not in rel.parts,'relative catalog source')
  pins[str(repo/rel)]=row['sha256']
 def source(name):
  rel='candidates/gdn32_full_model_execution_20261104/numeric/'+name+'.py';p=repo/rel;matches=[r for r in rows if r['path']==rel]
  need(len(matches)==1,'unique required source role');row=matches[0];check(dict(path=str(p),bytes=row['bytes'],sha256=row['sha256']),1<<20)
  m=types.ModuleType('reuse_'+name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
 candidate=source('candidate_admission');review=candidate.verify_review(b['model_candidate_review'],b['artifact_manifest'],artifact['artifact_identity'],repo=str(repo),current_source_pins_pin=b['source_pins'])
 ctx=dict(b,execution_context='CLOUD_EXECUTOR_V1',full_block_budget=None,pins=pins)
 document=source('p0_first_fault_contract');document.verify_document(ctx,review)
 probe=source('first_fault_driver_contract').verify_probe(review,b['artifact_manifest'],str(repo),b['source_pins'])
 doc=load(review['first_fault_diagnostic']);history=load(doc['basis']['historical_stage_binding'])
 need(prior['artifact_manifest']==history['artifact_manifest']and prior['artifact_manifest']!=b['artifact_manifest'],'exact historical provider artifact, not new identity')
 need(prior['retained_materials']==b['retained_materials'],'same complete retained data inventory')
 old=load(prior['artifact_manifest']);need(old['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'and artifact['schema']=='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1','explicit original and diagnostic artifacts')
 for item in (old,artifact):
  need(item['profiles']==list(range(5))and item['matrix_macs']==4096,'unchanged complete hardware resource contract')
  need(item['common']['sv']['sha256']=='3d148277114ff5d968d0e200f4ab117839a3b6c0c0d33e5388e6e5268d42d029','exact original raw SV')
 need(old['common']['sv']==artifact['common']['sv'],'identical raw SV path/size/digest')
 driver=old['common']['driver'];need(driver['path']=='driver.cpp'and driver['bytes']==27317 and driver['sha256']=='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61','original stimulus driver')
 check(dict(driver,path=str(Path(prior['artifact_manifest']['path']).parent/'driver.cpp')),1<<20)
 for key,target in(('manifest','program_manifest'),('commands','commands'),('descriptors','descriptors')):
  need(all(d['program'][key][field]==doc['stimulus'][target][field]for field in('bytes','sha256')),'same full original P0 program bytes')
 roots={str(Path(prior['artifact_manifest']['path']).parent),str(Path(b['model_candidate_review']['path']).parent),*review['roots'],*probe['roots'],*document.document_roots(ctx,review)}
 return sorted(roots)

def verify_metadata(reuse_pin,b):
 d=load(reuse_pin)
 need(set(d)=={'schema','scope','profile','tokens','context','prior_controller_binding','provider_root','closed_stage','metadata','program','inputs','raw_weights','source_contract','rope','reference_result','numerical_pass','evidence_root','evidence_origins'},'exact reuse schema fields')
 first_fault=d['schema']==FIRST_FAULT_SCHEMA
 need((first_fault or d['schema']=='P0_DATA_REUSE_BINDING_V1')and d['scope']=='PURE_INPUT_DATA_ONLY_NO_DUT_OR_RUNTIME_PASS'and d['profile']==0 and d['tokens']==128 and d['numerical_pass']is False,'data-only P0 contract')
 fields={'repo','artifact_manifest','retained_materials'}
 if first_fault:fields|={'execution_mode','model_candidate_review','source_pins'}
 need(set(d['context'])==fields,'context domain')
 need(all(d['context'][k]==b[k]for k in d['context']),'current context mismatch')
 evidence=Path(d['evidence_root']);need(evidence.is_absolute()and evidence==evidence.resolve()and evidence.is_dir()and all(not q.is_symlink()for q in (evidence,*evidence.parents)),'canonical evidence root')
 copies={'prior':d['prior_controller_binding'],'phase':d['closed_stage']['phase'],'receipt':d['closed_stage']['receipt'],'rope':d['rope']}
 need(set(d['evidence_origins'])==set(copies),'exact evidence origins')
 for key,row in copies.items():
  origin=d['evidence_origins'][key];need(type(origin)is dict and set(origin)=={'path','bytes','sha256'},'origin pin shape')
  op=Path(origin['path']);need(op.is_absolute()and '..'not in op.parts,'absolute provenance path')
  need(origin['bytes']==row['bytes']and origin['sha256']==row['sha256'],'copy exact original bytes')
  need(Path(row['path'])==evidence/(key+('.bin'if key=='rope'else'.json')),'exact copied evidence path')
 need({p.name for p in evidence.iterdir()}=={'prior.json','phase.json','receipt.json','rope.bin'},'finite evidence inventory')
 artifact=load(b['artifact_manifest']);prior=load(d['prior_controller_binding'])
 additional_roots=first_fault_relation(d,b,artifact,prior)if first_fault else []
 if not first_fault:need(prior['artifact_manifest']==b['artifact_manifest'],'same artifact bytes for retained P0 data')
 retained=load(b['retained_materials']);need(retained['references']['0']['result']==d['reference_result'],'same admitted original software reference')
 ref=load(d['reference_result']);need(ref['complete_block_tokens']==128 and ref['hardware_executed']is False and ref['exact_baseline_observer_output_equal']is True and ref['router_policy']=='UNMODIFIED_OFFICIAL_TORCH_TOPK','reference domain')
 root=Path(d['provider_root']);need(root.is_absolute()and root==root.resolve()and root.is_dir()and all(not q.is_symlink()for q in (root,*root.parents)),'provider root')
 need(set(d['source_contract'])==set(SOURCE_CONTRACT),'complete fixed source contract')
 for name,(rel,h)in SOURCE_CONTRACT.items():
  p=check(d['source_contract'][name]);need(p==Path(b['repo'])/rel and d['source_contract'][name]['sha256']==h,'current original source/config pin')
 need(set(d['closed_stage'])=={'receipt','phase'},'closed stage domain');r=load(d['closed_stage']['receipt']);phase=load(d['closed_stage']['phase'])
 need(type(r['native_exit'])is int and r['native_exit']==0 and r['errors']==[] and r['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and r['log_capture']['pipe_eof_observed']is True and r['log_capture']['gzip_finalized']is True,'old provider strict closure only')
 cp=r['cleanup_proof'];bar=r['reader_join_barrier']
 need(bar=={'complete':True,'alive':False,'reader_finally_done':True}and all(type(x)is bool for x in bar.values()),'complete reader join')
 need(cp['direct_leader_reaped']is True and type(cp['direct_exit_code'])is int and cp['direct_exit_code']==0 and cp['no_nonleader_identities_at_barrier']is True and cp['no_post_reap_signals']is True and cp['empty_complete_scans']>=2 and r['log_capture']['capture_cap_hit']is False,'strict closed owner proof')
 av=r['argv'];need(av[-4:]==['--phase',d['evidence_origins']['phase']['path'],'--sha256',d['evidence_origins']['phase']['sha256']],'closed actual phase binding')
 args=phase['argv'];oldrepo=Path(prior['repo']);oldjob=Path(prior['job_root']);oldrebuild=str(oldrepo/SOURCE_CONTRACT['rebuild'][0]);payloads={str(Path(v['data']['path']).parent.parent)for v in d['raw_weights'].values()}
 need(len(payloads)==1,'single original payload root');payload=next(iter(payloads));refpath=str(oldjob/'materials/numeric/profile0/material/reference')
 need(len(args)==14 and args[1:]==[oldrebuild,'--repo',str(oldrepo),'--payload',payload,'--reference',refpath,'--rope',d['evidence_origins']['rope']['path'],'--rope-sha256',d['rope']['sha256'],'--output',str(root)],'exact closed original provider argv')
 need(phase['pins'].get(oldrebuild)==SOURCE_CONTRACT['rebuild'][1],'closed original converter identity')
 need(set(d['metadata'])==set(METADATA)and set(d['program'])==set(PROGRAM),'exact metadata/program inventory')
 docs={}
 for k,fn in METADATA.items():
  p=check(d['metadata'][k]);need(p==root/fn,'old metadata path');docs[k]=json.loads(p.read_text())
 for k,fn in PROGRAM.items():
  p=check(d['program'][k]);need(p==root/'program'/fn and d['program'][k]['sha256']==PROGRAM_PINS[k],'fixed original program bytes')
 m=load(d['program']['manifest']);spec=docs['source_spec'];old=docs['provider_result']
 need(old['status']=='P0_NEW_INPUT_ONLY_PROVIDER_STREAMS_VERIFIED_NOT_CHISEL_OR_RTL'and old['full_block_numeric_pass']is False,'only input provider result permitted')
 need(old['manifest_sha256']==d['program']['manifest']['sha256']and old['source_spec_sha256']==d['metadata']['source_spec']['sha256'],'old provider metadata joins')
 need(spec['metadata_sha256']==d['program']['manifest']['sha256']and spec['provider_manifest_sha256']==d['metadata']['source_manifest']['sha256']and spec['provenance_sha256']==d['metadata']['source_manifest']['sha256'],'source/provenance joins')
 sources=docs['source_manifest']['sources'];need(len(sources)==14,'fourteen pure inputs');sources={v['name']:v for v in sources};names=set(MATRIX)|set(VECTORS)|{'x','rope'}
 need(set(sources)==set(d['inputs'])==set(old['logical_ro'])==names,'no output/DUT data in inventory')
 need({n for n,t in m['tensors'].items()if t['readonly']}==names,'same readonly program inventory')
 inputroot=root/'input_only';need(inputroot.is_dir()and not inputroot.is_symlink(),'pure input root')
 need({p.name for p in inputroot.iterdir()}=={n+'.bin'for n in names},'no extra file in input root')
 need(set(d['raw_weights'])==set(MATRIX)|set(VECTORS),'exact twelve raw sources')
 for n in names:
  p=check(d['inputs'][n],128<<20,False);need(p==inputroot/(n+'.bin'),'exact input path')
  src=sources[n];need({k:src[k]for k in ('bytes','sha256')}=={k:d['inputs'][n][k]for k in ('bytes','sha256')}==old['logical_ro'][n],'input byte joins')
  if n in MATRIX or n in VECTORS:
   suffix,shape=(MATRIX|VECTORS)[n];official='model.layers.0.'+suffix;rw=d['raw_weights'][n];need(set(rw)=={'data','receipt'},'raw pins');rp=check(rw['data'],128<<20,False);rr=load(rw['receipt'])
   need(rr['name']==official and rr['revision']==REV and rr['dtype']=='BF16'and rr['shape']==shape,'fixed original weight contract')
   need(rw['data']['sha256']==rr['actual_sha256']==src['source']['sha256']and rw['data']['bytes']==rr['bytes'],'raw byte joins')
   need(src['source']==dict(name=official,sha256=rr['actual_sha256'],shape=shape,revision=REV),'source mapping provenance')
   expected_mapping='native BF16LE transpose [N,K] to [K,N]'if n in MATRIX else'exact BF16 bit expansion into FP32 storage'
   need(src['mapping']==expected_mapping,'exact transform policy')
   count=1
   for q in shape:count*=q
   need(rw['data']['bytes']==count*2 and d['inputs'][n]['bytes']==count*(2 if n in MATRIX else 4),'shape bytes')
   # Bind retained official raw inventory without following any new caller root.
   matches=[v for v in retained['weights']if v.get('file')==rw['data']and v.get('receipt')==rw['receipt']]
   need(len(matches)==1,'admitted retained raw source')
  elif n=='x':
   h=ref['tensor_records']['hidden_storage'];need(h['file']=='input_only/hidden_storage.bin'and h['sha256']==d['inputs'][n]['sha256']and d['inputs'][n]['bytes']==786432,'same FP32 hidden input')
  else:
   check(d['rope'],1<<20,False);need(d['rope']['sha256']==d['inputs'][n]['sha256']=='4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815'and d['inputs'][n]['bytes']==d['rope']['bytes']==524288,'exact original rope')
 result=dict(watch_scope='PURE_PROVIDER_AND_FINITE_EVIDENCE_V1',roots=[str(root),str(evidence),*additional_roots],provider_root=str(root),evidence_root=str(evidence),input_root=str(inputroot),inputs=d['inputs'],program=d['program'],metadata=d['metadata'],artifact_manifest_sha256=b['artifact_manifest']['sha256'],reuse_binding_sha256=reuse_pin['sha256'],source_contract_pins=d['source_contract'],reference_result_sha256=d['reference_result']['sha256'],rope_sha256=d['rope']['sha256'])
 if first_fault:result.update(watch_scope='PURE_PROVIDER_FINITE_EVIDENCE_AND_DIAGNOSTIC_AUTHORITY_V1',authority_roots=additional_roots)
 return result

def compare_mapping(raw,logical,shape,transpose):
 """Full independent bytes comparison, bounded 32-row chunks; no writes."""
 import numpy as np
 with Path(raw).open('rb')as f,Path(logical).open('rb')as g:
  before=os.fstat(f.fileno());gbefore=os.fstat(g.fileno())
  with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)as mm:
   ar=np.ndarray(tuple(shape),dtype='<u2',buffer=mm)
   if transpose:
    for lo in range(0,shape[1],32):
     expected=ar[:,lo:lo+32].T.copy().tobytes();need(g.read(len(expected))==expected,'full transpose bytes')
   else:
    for lo in range(0,shape[0],4096):
     expected=(ar[lo:lo+4096].astype('<u4')<<16).tobytes();need(g.read(len(expected))==expected,'full FP32 expansion bytes')
   del ar
  need(g.read(1)==b'','logical trailing bytes')
  ident=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  need(ident(before)==ident(os.fstat(f.fileno()))and ident(gbefore)==ident(os.fstat(g.fileno())),'mapping source changed')

def materialize(binding_path,binding_sha,output):
 bp,_=regular(str(binding_path));rp=dict(path=str(bp),bytes=bp.stat().st_size,sha256=binding_sha);d=load(rp);v=verify_metadata(rp,d['context'])
 for row in d['inputs'].values():check(row,128<<20,True)
 for n,(_,shape)in (MATRIX|VECTORS).items():
  raw=check(d['raw_weights'][n]['data'],128<<20,True);compare_mapping(raw,d['inputs'][n]['path'],shape,n in MATRIX)
 ref=load(d['reference_result']);h=ref['tensor_records']['hidden_storage'];check(dict(path=str(Path(d['reference_result']['path']).parent/h['file']),bytes=h['bytes'],sha256=h['sha256']),2<<20,True);check(d['rope'],1<<20,True)
 out=Path(output);need(out.is_absolute()and not out.exists()and not out.is_symlink()and out==out.resolve()and all(not q.is_symlink()for q in out.parents),'fresh canonical destination');need(not out.is_relative_to(Path(d['provider_root'])),'must not write original provider');out.mkdir();(out/'program').mkdir()
 for k,fn in PROGRAM.items():
  with (out/'program'/fn).open('xb')as f:f.write(check(d['program'][k]).read_bytes())
 for k in ('source_manifest','source_spec'):
  with (out/METADATA[k]).open('xb')as f:f.write(check(d['metadata'][k]).read_bytes())
 freshprogram={k:makepin(out/'program'/fn)for k,fn in PROGRAM.items()}
 freshmetadata={k:makepin(out/METADATA[k])for k in ('source_manifest','source_spec')}
 result=dict(schema='P0_REUSED_INPUT_DATA_MATERIALIZATION_V1',status='PURE_INPUT_BYTES_REVALIDATED_NOT_DUT',reuse_binding_sha256=binding_sha,artifact_manifest_sha256=v['artifact_manifest_sha256'],input_root=v['input_root'],input_pins=v['inputs'],program_pins=freshprogram,metadata_pins=freshmetadata,full_transform_verified=True,full_block_numeric_pass=False)
 with (out/'RESULT.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
 return result

def verify_materialized(binding_path,binding_sha,newprovider):
 bp,_=regular(str(binding_path));rp=dict(path=str(bp),bytes=bp.stat().st_size,sha256=binding_sha);d=load(rp);v=verify_metadata(rp,d['context']);out=Path(newprovider);need(out.is_absolute()and out==out.resolve()and out.is_dir()and all(not q.is_symlink()for q in (out,*out.parents)),'canonical materialized provider');p=out/'RESULT.json';regular(str(p));need(p.stat().st_size<2<<20,'bounded material receipt');r=json.loads(p.read_text())
 need(set(r)=={'schema','status','reuse_binding_sha256','artifact_manifest_sha256','input_root','input_pins','program_pins','metadata_pins','full_transform_verified','full_block_numeric_pass'},'exact new data receipt fields')
 need(set(r['program_pins'])==set(PROGRAM)and set(r['metadata_pins'])=={'source_manifest','source_spec'},'exact fresh metadata inventory')
 need(r['schema']=='P0_REUSED_INPUT_DATA_MATERIALIZATION_V1'and r['status']=='PURE_INPUT_BYTES_REVALIDATED_NOT_DUT'and r['full_transform_verified']is True and r['full_block_numeric_pass']is False,'new data-only receipt')
 need(r['reuse_binding_sha256']==binding_sha and r['artifact_manifest_sha256']==v['artifact_manifest_sha256']and r['input_root']==v['input_root']and r['input_pins']==v['inputs'],'same admitted data binding')
 for k,fn in PROGRAM.items():need(check(r['program_pins'][k])==out/'program'/fn and r['program_pins'][k]['sha256']==d['program'][k]['sha256'],'fresh program exact bytes')
 for k in ('source_manifest','source_spec'):need(check(r['metadata_pins'][k])==out/METADATA[k]and r['metadata_pins'][k]['sha256']==d['metadata'][k]['sha256'],'fresh provenance exact bytes')
 for row in v['inputs'].values():check(row,128<<20,True)
 return v['input_root']

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--binding',required=True,type=Path);p.add_argument('--sha256',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args();materialize(a.binding,a.sha256,a.output)
