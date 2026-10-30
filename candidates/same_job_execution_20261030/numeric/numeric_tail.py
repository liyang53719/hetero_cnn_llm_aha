"""Actual same-job build -> ABI -> original providers -> existing comparisons.
Source-only candidate. Requires independently reviewed owning-job binding; no
acquisition/build defaults, no API artifact, no upload, no numerical PASS claim.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,signal,sys,time
import live_budget
import dut_evidence
import provider_from_frozen as material
P=pathlib.Path;D=P(__file__).resolve().parent

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):
 with P(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def module(name,path,pins):
 need(pins.get(str(path))==sha(path),'admitted module');spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def complete(r):
 return (r.get('cleanup_proof') or {}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and (r.get('log_capture') or {}).get('pipe_eof_observed')is True and (r.get('log_capture') or {}).get('gzip_finalized')is True

def require_cleanup(r,marker):
 if not complete(r):
  save(marker,dict(status='HOLD_PARENT_LEASE_NO_CONTINUATION'))
  while True:signal.pause()

def weights(b,i):
 model=('qwen2_1p5b','qwen3_5_0p8b','qwen3_5_0p8b','qwen3_5_35b_a3b','qwen3_5_35b_a3b')[i]
 layer=3 if i in (2,4) else 0
 need(len(b['weights'])==70,'one complete shared70 inventory')
 rows=[r for r in b['weights']if r['model']==model and f'.layers.{layer}.'in r['name']]
 need(len(rows)==(12,14,11,18,15)[i],'full block/all experts')
 for r in rows:
  p=material.checked(r['pin']);need(p.is_relative_to(P(b['payload'])),'owning shared payload')

def validate(b):
 need(b['schema']=='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1','explicit samejob tail')
 need(b['profiles']==list(range(5)) and b['tokens']==128 and b['matrix_macs']==4096 and b['vector_lanes']==32,'five fixed full profiles')
 need(b['upload_payloads']is False and b['final_rtl_replay']is False,'local generated Chisel test backend only')
 need(set(b['references'])==set(map(str,range(5))),'five independently frozen reference receipts')
 need(set(b['calibration_seconds'])==set(map(str,range(5))),'all five budgeted before any execution')
 need(all(type(n)is int and 0<n<=20000 for n in b['calibration_seconds'].values()),'explicit bounded same-stimulus calibration')
 need(b['job_started_monotonic']<=time.monotonic(),'owning job start clock, not reset after build')
 need(sum(b['calibration_seconds'].values())+b['reserved_material_seconds']+b['reserved_cleanup_seconds']+b['reserved_parent_seconds'] <= 21000-(time.monotonic()-b['job_started_monotonic']),'whole five round exceeds remaining job')
 need(b['reserved_material_seconds']>=7*b['provider_wall_seconds']+11*120 and b['reserved_cleanup_seconds']>=23*60+5*30 and b['reserved_parent_seconds']>0,'all seven provider/five connect/ABI and twenty-three cleanup plus DUT/parent reservations')
 need(b['tree_cap']==12_081_306_272,'unchanged aggregate tree cap')
 for k in ('rss_bytes','address_space_bytes','phase_extra_bytes','provider_wall_seconds'):
  need(type(b[k])is int and b[k]>0,'explicit reviewed resource bound '+k)
 need(b['rss_bytes']<=12*1024**3 and 12*1024**3<=b['address_space_bytes']<=16*1024**3,'runner resource maxima')

CACHE_NAMES=('HOME','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR','TMPDIR')
def owned_environment(base,root):
 allowed={'PATH','LANG','LC_ALL','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'}
 need(set(base)<=allowed,'no inherited credentials/loader/python/cache variables')
 root=P(root);need(not root.exists() and not root.is_symlink(),'fresh watched phase cache root');root.mkdir()
 e=dict(base,PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 for name in CACHE_NAMES:
  p=root/name.lower();p.mkdir();e[name]=str(p)
 return e

def run(b,binding_path,binding_sha):
 validate(b);pins=dict(b['pins']);pins[str(binding_path)]=binding_sha
 need(not {r['pin']['path']for r in b['weights']} & set(pins),'large payload uses streaming pins, not supervisor read_bytes')
 for p,h in pins.items():need(sha(p)==h,'source pin drift')
 for name in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):
  path=str(P(b['supervisor_dir'])/name);need(pins.get(path)==sha(path),'exact published supervisor closure')
 for name in ('numeric_tail.py','provider_from_frozen.py','locked_phase.py','live_budget.py','consumer_owned.py','dut_evidence.py','runtime_abi_owned.py','connect_owned.py','CONNECTION_OWNED_SOURCE_PINS.json'):
  need(pins.get(str(D/name))==sha(D/name),'controller source pin')
 out=P(b['output']);roots=live_budget.roots_checked(b['owned_roots'])
 for role in ('repo','owner_root','payload'):
  need(any(P(b[role]).resolve().is_relative_to(r)for r in roots),'unwatched required material '+role)
 need(any(P(b['build_result']['path']).resolve().is_relative_to(r)for r in roots),'unwatched build tree')
 need(not out.exists() and out.is_relative_to(P(b['owner_root'])),'fresh output inside runtime owner');out.mkdir();(out/'runs').mkdir();(out/'phases').mkdir();(out/'cache_roots').mkdir()
 save(out/'REGISTERED_FIVE.json',dict(profiles=b['profiles'],tokens=128,calibration_seconds=b['calibration_seconds'],scope='CHISEL_EMITTED_SV_SIMULATION_NOT_FINAL_RTL',numeric_pass=False))
 sys.path.insert(0,b['supervisor_dir']);import supervise_multiroot as supervisor
 owner=module('admitted_runtime_owner',P(b['owner_module']),pins)
 owner_doc,_=owner.verify(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root'])
 need(owner_doc['schema']=='SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3'and owner_doc['identity']==dict(run_id=b['run_id'],source_commit=b['source_commit'],launch_commit=b['launch_commit']),'fresh CI owner exact same run/source/launch, never historical V2 receipt')
 build=material.checked(b['build_result']);br=json.loads(build.read_text());manifest=material.checked(br['artifact']['manifest']);frozen=json.loads(manifest.read_text());common=frozen['common'];root=manifest.parent
 # Original proof checks actual owning run + source/launch, not invented API proof.
 proof=module('same_job_proof',D/'local_build_proof.py',pins)
 proof.verify(build,b['build_result']['sha256'],manifest,sha(manifest),frozen,b['run_id'],b['launch_commit'],b['source_commit'])
 allstage=[];dut_records=[]
 def stage(name,argv,seconds=None,accepted=(0,),lease_out=None):
  seconds=seconds or b['provider_wall_seconds'];phase=out/'phases'/(name+'.json');run_dir=out/'runs'/name
  cache_root=out/'cache_roots'/name;e=owned_environment(b['environment'],cache_root)
  body=dict(argv=list(map(str,argv)),pins=pins,owned_roots=b['owned_roots'],extra_bytes=b['phase_extra_bytes'],seconds=seconds,job_started=b['job_started_monotonic'],write_file_bytes=128<<20,environment=e,cache_root=str(cache_root),admission_output=str(run_dir/'LIVE_ADMISSION.json'))
  save(phase,body);localpins=dict(pins);localpins[str(phase)]=sha(phase)
  caps=dict(wall_seconds=seconds+30,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=512<<20,log_bytes=64<<20,raw_log_bytes=128<<20,max_entries=100000,per_process_as_bytes=b['address_space_bytes'],per_process_cpu_seconds=18000 if name.endswith('_dut') else seconds+30,rss_bytes=b['rss_bytes'],cpu_seconds=seconds+30,extra_watch_roots=b['owned_roots'],min_free_disk_bytes=1_500_000_000,watch_tree_bytes=b['tree_cap'])
  r=supervisor.execute([b['python'],'-B',str(D/'locked_phase.py'),'--phase',str(phase),'--sha256',sha(phase)],str(run_dir),b['lock'],caps,e,localpins,resource_gate={'min_available_memory':b['rss_bytes']+(1<<30),'min_disk_free':8<<30})
  require_cleanup(r,out/('OWNERSHIP_INCOMPLETE_'+name+'.json'))
  allstage.append(dict(name=name,native_exit=r['native_exit'],receipt_sha256=sha(run_dir/'RESULT.json')))
  need(r['native_exit']in accepted and not r['errors'],'stage failed; no retry '+name)
  return r
 stable_cache=out/'execution_cache';owned_environment({},stable_cache)
 env_manifest=out/'EXECUTION_ENVIRONMENT.json'
 save(env_manifest,dict(schema='OWNED_EXECUTION_ENVIRONMENT_V1',identity=dict(run_id=b['run_id'],source_commit=b['source_commit'],launch_commit=b['launch_commit']),owner_root=b['owner_root'],watched_roots=[b['owner_root']],cache_root=str(stable_cache),cache_paths={k:str(stable_cache/k.lower())for k in CACHE_NAMES}))
 pins[str(env_manifest)]=sha(env_manifest)
 env_args=['--owned-environment',str(env_manifest),'--owned-environment-sha256',sha(env_manifest)]
 abi=out/'STARTUP_ABI.json';tool=frozen['tool_manifest'];binary=common['binary']
 stage('startup_abi',[b['python'],'-B',str(D/'runtime_abi_owned.py'),'--binary',str(root/binary['path']),'--binary-sha256',binary['sha256'],'--tool-manifest',str(root/tool['path']),'--tool-manifest-sha256',tool['sha256'],'--output',str(abi),'--execute-reviewed-loader-list','--expected-run-id',str(b['run_id']),'--expected-source-commit',b['source_commit'],'--expected-launch-commit',b['launch_commit'],*env_args],120)
 identity_args=['--artifact-manifest',str(manifest),'--artifact-manifest-sha256',sha(manifest),'--local-build-result',str(build),'--local-build-result-sha256',b['build_result']['sha256'],'--expected-run-id',str(b['run_id']),'--expected-launch-commit',b['launch_commit'],'--expected-source-commit',b['source_commit'],'--local-runtime-abi',str(abi),'--local-runtime-abi-sha256',sha(abi),*env_args]
 for i in b['profiles']:
  lease_root=out/f'profile{i}';lease_root.mkdir();profile=lease_root/'material'
  with owner.lease(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root'],i,lease_root) as selected:
   weights(b,i)
   runtime=selected[('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')[i]]
   ref_path=material.checked(b['references'][str(i)]);need(ref_path.is_relative_to(P(b['owner_root'])),'reference belongs to owning job')
   ref_doc=json.loads(ref_path.read_text());need(ref_doc['runtime_receipt_sha256']==runtime['receipt']['sha256']and ref_doc['runtime_source_pins_sha256']==runtime['sidecar']['sha256'],'reference matches actual selected installed runtime/sidecar')
   def provider_stage(label,argv):return stage(f'p{i}_{label}',argv,lease_out=lease_root)
   initialization=out/'phases'/f'p{i}_initialize_input.json'
   save(initialization,dict(repo=b['repo'],materializer=b['materializer'],output=str(profile),profile=i,reference=b['references'][str(i)]))
   stage(f'p{i}_initialize',[b['python'],'-B',str(D/'provider_from_frozen.py'),'--initialize-binding',str(initialization),'--sha256',sha(initialization)],120,lease_out=lease_root)
   material.prepare(b['repo'],b['materializer'],profile,i,runtime['wrapper'],b['payload'],b['references'][str(i)],provider_stage,pins)
   stage(f'p{i}_connect',[b['python'],'-B',str(D/'connect_owned.py'),'--existing-output',str(profile),'--profile',str(i),*identity_args],120,lease_out=lease_root)
   generated=json.loads((profile/'CONSUMER_ARGV.json').read_text())['consumer_argv'];need(generated[1]==str(D/'consumer_owned.py'),'explicit owned consumer handoff')
   generated[1]=str(D/'consumer_owned.py');generated+=['--calibration-wall-seconds',str(b['calibration_seconds'][str(i)])]
   dut_outer=stage(f'p{i}_dut',generated,b['calibration_seconds'][str(i)]+30,accepted=(2,),lease_out=lease_root)
   bundle=profile/'runtime_bundle.v3.json';bundle_doc=json.loads(bundle.read_text());runtime_sha=bundle_doc['profiles'][0]['runtime']['sha256']
   diagnostic=dut_evidence.verify(profile/'dut_result',i,sha(manifest),sha(bundle),binary['sha256'],runtime_sha,material.pin(out/'runs'/f'p{i}_dut'/'RESULT.json'));dut_records.append(diagnostic)
   save(out/f'PROFILE_{i}_DIAGNOSTIC.json',diagnostic)
   weights(b,i)
 save(out/'RESULT.json',dict(status='INCOMPLETE_DIAGNOSTIC_ONLY',scope='CHISEL_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL',stages=allstage,profiles=b['profiles'],actual_dut_reports=dut_records,numerical_pass=False,moe_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',uploaded_payloads=False))

def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);v=a.parse_args();need(sha(v.binding)==v.binding_sha256,'independently reviewed binding');run(json.loads(v.binding.read_text()),v.binding.resolve(),v.binding_sha256)
if __name__=='__main__':main()
