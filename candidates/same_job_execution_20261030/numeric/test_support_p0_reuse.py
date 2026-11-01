"""Portable metadata-only sparse fixture. No real weights or old job references."""
import importlib.util,json
from pathlib import Path
HERE=Path(__file__).parent
CORE=HERE/'p0_provider_data_reuse.py'if (HERE/'p0_provider_data_reuse.py').exists()else HERE/'source/p0_provider_data_reuse.py'
FIXTURES=HERE/'fixtures/p0_reuse'if (HERE/'fixtures/p0_reuse').exists()else HERE/'fixture_data'
sp=importlib.util.spec_from_file_location('reuse_core',CORE);core=importlib.util.module_from_spec(sp);sp.loader.exec_module(core)
def build_fixture(root):
 root=Path(root).resolve();repo=root/'repo';old=root/'oldprovider';(old/'input_only').mkdir(parents=True);(old/'program').mkdir();rawroot=root/'raw/qwen2_1p5b';rawroot.mkdir(parents=True);refroot=root/'ref';refroot.mkdir();(refroot/'input_only').mkdir()
 def put(p,d):
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2)+'\n');return core.makepin(p)
 def sparse(p,size,h='0'*64):
  p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('wb')as f:f.truncate(size)
  return dict(path=str(p),bytes=size,sha256=h)
 sources={};program={}
 for k,(rel,h)in core.SOURCE_CONTRACT.items():
  p=repo/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((FIXTURES/('source_'+k)).read_bytes());sources[k]=core.makepin(p)
 for k,fn in core.PROGRAM.items():
  p=old/'program'/fn;fixture=FIXTURES/('program_'+k+('.hex'if k in ('commands','descriptors')else''));data=bytes.fromhex(fixture.read_text(encoding='ascii'))if k in ('commands','descriptors')else fixture.read_bytes();p.write_bytes(data);program[k]=core.makepin(p)
  core.need(program[k]['sha256']==core.PROGRAM_PINS[k],'fixture original program bytes')
 inputs={};raws={};provenance=[];retainedweights=[]
 for n,(suffix,shape)in (core.MATRIX|core.VECTORS).items():
  count=1
  for v in shape:count*=v
  name='model.layers.0.'+suffix;rp=sparse(rawroot/(name+'.bin'),count*2);receipt=put(rawroot/(name+'.receipt.json'),dict(name=name,revision=core.REV,dtype='BF16',shape=shape,bytes=count*2,actual_sha256=rp['sha256']))
  raws[n]=dict(data=rp,receipt=receipt);retainedweights.append(dict(file=rp,receipt=receipt))
  inp=sparse(old/'input_only'/(n+'.bin'),count*(2 if n in core.MATRIX else 4));inputs[n]=inp
  provenance.append(dict(name=n,mapping='native BF16LE transpose [N,K] to [K,N]'if n in core.MATRIX else'exact BF16 bit expansion into FP32 storage',source=dict(name=name,sha256=rp['sha256'],shape=shape,revision=core.REV),bytes=inp['bytes'],sha256=inp['sha256']))
 hidden=sparse(refroot/'input_only/hidden_storage.bin',786432);rope=sparse(root/'rope.bin',524288,'4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815')
 for n,row in [('x',hidden),('rope',rope)]:
  inputs[n]=sparse(old/'input_only'/(n+'.bin'),row['bytes'],row['sha256']);provenance.append(dict(name=n,mapping='synthetic expectation only',source={},bytes=row['bytes'],sha256=row['sha256']))
 ref=put(refroot/'RESULT.json',dict(complete_block_tokens=128,hardware_executed=False,exact_baseline_observer_output_equal=True,router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',tensor_records={'hidden_storage':dict(file='input_only/hidden_storage.bin',bytes=hidden['bytes'],sha256=hidden['sha256'])}))
 retained=put(root/'retained.json',dict(weights=retainedweights,references={'0':{'result':ref}}));artifact=put(root/'artifact.json',dict(synthetic=True));context=dict(repo=str(repo),artifact_manifest=artifact,retained_materials=retained)
 prior=put(root/'prior.json',dict(artifact_manifest=artifact,repo=str(repo),job_root=str(root/'job')));phase=put(root/'phase.json',dict(argv=['python',sources['rebuild']['path'],'--repo',str(repo),'--payload',str(rawroot.parent),'--reference',str(root/'job/materials/numeric/profile0/material/reference'),'--rope',rope['path'],'--rope-sha256',rope['sha256'],'--output',str(old)],pins={sources['rebuild']['path']:sources['rebuild']['sha256']}));receipt=put(root/'closed.json',dict(argv=['python','locked_phase.py','--phase',phase['path'],'--sha256',phase['sha256']],native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','direct_leader_reaped':True,'direct_exit_code':0,'no_nonleader_identities_at_barrier':True,'no_post_reap_signals':True,'empty_complete_scans':2},reader_join_barrier={'complete':True,'alive':False,'reader_finally_done':True},log_capture={'pipe_eof_observed':True,'gzip_finalized':True,'capture_cap_hit':False}))
 sm=put(old/'source_manifest.json',dict(status='INPUT_ONLY_NOT_DUT',sources=provenance));ss=put(old/'source_spec.json',dict(metadata_sha256=program['manifest']['sha256'],provider_manifest_sha256=sm['sha256'],provenance_sha256=sm['sha256']));res=put(old/'RESULT.json',dict(status='P0_NEW_INPUT_ONLY_PROVIDER_STREAMS_VERIFIED_NOT_CHISEL_OR_RTL',full_block_numeric_pass=False,manifest_sha256=program['manifest']['sha256'],source_spec_sha256=ss['sha256'],logical_ro={n:{k:v[k]for k in ('bytes','sha256')}for n,v in inputs.items()}))
 d=dict(schema='P0_DATA_REUSE_BINDING_V1',scope='PURE_INPUT_DATA_ONLY_NO_DUT_OR_RUNTIME_PASS',profile=0,tokens=128,context=context,prior_controller_binding=prior,provider_root=str(old),closed_stage=dict(receipt=receipt,phase=phase),metadata=dict(source_manifest=sm,source_spec=ss,provider_result=res),program=program,inputs=inputs,raw_weights=raws,source_contract=sources,rope=rope,reference_result=ref,numerical_pass=False)
 evidence=root/'evidence';evidence.mkdir();originals={'prior':prior,'phase':phase,'receipt':receipt,'rope':rope};copies={}
 for key,row in originals.items():
  dest=evidence/(key+('.bin'if key=='rope'else'.json'));dest.write_bytes(Path(row['path']).read_bytes());copies[key]=dict(row,path=str(dest))
 d.update(evidence_root=str(evidence),evidence_origins=originals,prior_controller_binding=copies['prior'],closed_stage={'phase':copies['phase'],'receipt':copies['receipt']},rope=copies['rope'])
 row=put(root/'reuse.json',d)
 return dict(document=d,pin=row,context=context,root=root,save=lambda:put(root/'reuse.json',d))
