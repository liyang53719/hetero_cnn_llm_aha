"""Original providers from already verified shared weights + full128 references.
No acquisition, framework/reference forward, hardware build, or DUT execution.
Caller owns V2 lease through each strict-supervisor cleanup and post-tree check.
"""
import hashlib,importlib.util,json,os,pathlib,sys
P=pathlib.Path

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def checked(v):
 p=P(v['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink() and p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'pinned input drift');return p
def save(p,v):
 with P(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def copy_reference(row,out,profile):
 src=checked(row);r=json.loads(src.read_text())
 need(r['profile']['profile']==profile and r['complete_block_tokens']==128 and r['exact_baseline_observer_output_equal'] is True and r['hardware_executed'] is False,'full original independent reference')
 need(r['router_policy']=='UNMODIFIED_OFFICIAL_TORCH_TOPK','unchanged routing reference')
 target=out/'reference';target.mkdir();total=src.stat().st_size
 for v in r['tensor_records'].values():
  rel=P(v['file']);need(not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] in ('input_only','reference_only'),'segregated reference file')
  p=checked(dict(v,path=str(src.parent/rel)));total+=p.stat().st_size;need(total<=128<<20,'reference retained bound')
  dest=target/rel
  if dest.exists():need(sha(dest)==v['sha256'],'duplicate tensor identity');continue
  dest.parent.mkdir(parents=True,exist_ok=True)
  # Owned immutable byte copy, not an alias into an unowned historical tree.
  with p.open('rb') as f,dest.open('xb') as g:
   while chunk:=f.read(1<<20):g.write(chunk)
  need(sha(dest)==v['sha256'],'copied reference drift')
 with (target/'RESULT.json').open('xb') as f:f.write(src.read_bytes())
 need(sha(target/'RESULT.json')==row['sha256'],'original reference receipt preserved')
 return target

def prepare(repo,materializer,out,profile,wrapper,payload,reference,stage,source_pins):
 """stage(name,argv) MUST be strict supervised and require complete cleanup/EOF.
 This function is called inside the parent's runtime lease, not in another session.
 All source files are explicitly admitted by source_pins before import/exec.
 """
 repo=P(repo).resolve();materializer=P(materializer).resolve();out=P(out).resolve();payload=P(payload).resolve()
 need(profile in range(5) and out.is_dir(),'supervised initialized selected profile output')
 for p,h in source_pins.items():need(sha(p)==h,'source pin drift')
 def source(p):
  p=P(p).resolve();need(str(p) in source_pins and sha(p)==source_pins[str(p)],'provider executable source pin');return str(p)
 source(materializer/'prepare.py')
 init=json.loads((out/'INITIALIZED.json').read_text());need(init==dict(profile=profile,reference=reference),'same initialized original reference')
 ref=out/'reference';need(sha(ref/'RESULT.json')==reference['sha256'],'frozen initialized reference')
 refs=out/'references';refs.mkdir();(refs/f'profile{profile}').symlink_to(ref,target_is_directory=True)
 argv_prefix=[str(wrapper)]
 if profile==0:
  table=out/'rope';stage('p0_rope',argv_prefix+[source(materializer/'generate_p0_rope.py'),'--config',str(repo/'config/upstream/weight_headers/qwen2_1p5b/config.json'),'--reference',str(ref),'--output',str(table)])
  rope=table/'rope_fp32.bin';need(sha(rope)=='4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815','original RoPE identity')
  base=repo/'candidates/p0_newboundary_input_provider_20261028'
  stage('p0_provider',argv_prefix+[source(base/'rebuild.py'),'--repo',str(repo),'--payload',str(payload),'--reference',str(ref),'--rope',str(rope),'--rope-sha256',sha(rope),'--output',str(out/'p0_provider')])
  stage('p0_transport',argv_prefix+[source(base/'emit_tsv.py'),'--payload',str(payload),'--provider',str(out/'p0_provider'),'--output',str(out/'p0_transport')])
  d=out/'p0_transport';receipt=out/'p0_provider/RESULT.json'
 elif profile in (1,2):
  stage('p12_provider',argv_prefix+[source(materializer/'provider_p12.py'),'--profile',str(profile),'--repo',str(repo),'--programs',str(out/'programs'),'--payload',str(payload),'--reference-root',str(refs),'--acquisition-metadata',str(repo/'candidates/five_profile_input_recovery_20261028'),'--output',str(out/'p12_provider')])
  d=out/'p12_provider'/f'profile{profile}';receipt=d/'source_spec.json'
 else:
  inputs=out/'input_only';i=inputs/f'P{profile}';i.mkdir(parents=True);(i/'hidden.storage.bin').symlink_to(ref/'input_only/hidden_storage.bin')
  argv=argv_prefix+[source(materializer/'provider_p34.py'),'--repo',str(repo),'--programs',str(out/'programs'),'--payload',str(payload),'--inputs',str(inputs),'--output',str(out/'p34_provider'),'--profiles',str(profile)]
  if profile==4:argv+=['--reference-result',str(ref/'RESULT.json'),'--reference-result-sha256',sha(ref/'RESULT.json')]
  stage('p34_provider',argv);d=out/'p34_provider'/f'profile{profile}';receipt=d/'source_spec.json'
 save(out/'runtime_bundle.json',dict(schema='SINGLE_PROFILE_RUNTIME_BUNDLE_V1',status='FROZEN_ORIGINAL_REFERENCE_AND_PROVIDER_NOT_DUT',profiles=[dict(id=profile,runtime=pin(d/'runtime.tsv'),views=pin(d/'views.tsv'),reference_result=pin(ref/'RESULT.json'),provider_receipt=pin(receipt))],limits=dict(address_space_bytes=12*1024**3,cpu_seconds=18000,wall_seconds=20000,file_bytes=64*1024**2,max_active_cycles=1000000000),hardware_executed=False,raw_payloads_upload_allowed=False))
 for p,h in source_pins.items():need(sha(p)==h,'post provider source drift')
 return out/'runtime_bundle.json'


def initialize(repo,materializer,out,profile,reference):
 repo=P(repo).resolve();materializer=P(materializer).resolve();out=P(out).resolve()
 need(not out.exists() and profile in range(5),'fresh supervised material initialization');out.mkdir()
 copy_reference(reference,out,profile)
 spec=importlib.util.spec_from_file_location('unchanged_original_materializer',materializer/'prepare.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.sources(repo);m.programs(repo,out/'programs',profile)
 save(out/'INITIALIZED.json',dict(profile=profile,reference=reference))

if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--initialize-binding',type=P,required=True);a.add_argument('--sha256',required=True);v=a.parse_args()
 need(sha(v.initialize_binding)==v.sha256,'admitted initialization binding');b=json.loads(v.initialize_binding.read_text())
 initialize(b['repo'],b['materializer'],b['output'],b['profile'],b['reference'])
