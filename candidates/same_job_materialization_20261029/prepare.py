#!/usr/bin/env python3
"""Fresh job-local inputs/references/providers, reusing original pinned sources.
Never runs/elaborates hardware. Do not upload generated payloads or private probes.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,signal,subprocess,sys,time
P=pathlib.Path
HERE=P(__file__).resolve().parent
C='candidates/'
REF=C+'independent_reference_runtime_binding_20261028T2300/'
P0=C+'p0_newboundary_input_provider_20261028/'
P12=C+'p1_p2_provider_reconstruction_20261028T2322/portable_v2/'
P34=C+'p3_p4_provider_reconstruction_20261028T2344/'
ACQ=C+'five_profile_input_recovery_20261028'
MODEL=['qwen2_1p5b','qwen3_5_0p8b','qwen3_5_0p8b','qwen3_5_35b_a3b','qwen3_5_35b_a3b']
RUNTIME=['qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b']

def need(v,msg):
 if not v:raise ValueError(msg)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):
 with P(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def pin(p):
 p=P(p).resolve();need(p.is_file(),'pin file missing '+str(p));return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def verify_pin(v,root=None):
 p=P(v['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink(),'regular absolute pin')
 if root is not None:need(p.resolve().is_relative_to(root.resolve()),'job-local path required')
 need(p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'pin drift '+str(p));return p

def sources(repo):
 rows=json.loads((HERE/'REPO_DEPENDENCIES.json').read_text())
 for rel,v in rows.items():
  p=repo/rel;need(p.is_file() and p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'source dependency '+rel)
 return rows

def run(argv,out,label,wall=1800):
 argv=list(map(str,argv));log=out/(label+'.log');start=time.monotonic();child=None
 try:
  with log.open('xb') as f:
   child=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   while True:
    status=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
    if status is not None:break
    need(time.monotonic()-start<wall,'wall deadline '+label)
    need(log.stat().st_size<=64*1024*1024,'log cap '+label)
    time.sleep(.25)
   code=status.si_status if status.si_code==os.CLD_EXITED else -status.si_status
   need(code==0,'step failed '+label+' exit='+str(code))
 finally:
  if child is not None:
   # Never reap leader before group cleanup. Escaped sessions require outer supervisor.
   try:os.killpg(child.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   child.wait()
  save(out/(label+'.process.json'),dict(argv=argv,seconds=time.monotonic()-start,exit_code=None if child is None else child.returncode,scope='PROCESS_ONLY_NOT_NUMERICAL_PASS'))

def programs(repo,out,profile):
 """Call the original Builder, and require exact original PROGRAM_PINS bytes."""
 base=repo/C/'five_profile_byte_provider';sys.path.insert(0,str(base))
 spec=importlib.util.spec_from_file_location('original_program_emitter',base/'emit_cold128_programs.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 pins=json.loads((base/'PROGRAM_PINS.json').read_text())['profiles'];out.mkdir()
 for profile in ([] if profile==0 else [profile]):
  b,blocked=m.common(profile);cb,db,meta=b.finish();meta['blocker']=blocked;meta['complete_program_emitted']=blocked is None
  need(blocked is None,'original program incomplete')
  meta['sha256']={'commands':hashlib.sha256(cb).hexdigest(),'descriptors':hashlib.sha256(db).hexdigest()}
  data={'commands.bin':cb,'descriptors.bin':db,'manifest.json':(json.dumps(meta,indent=2)+'\n').encode()}
  d=out/f'profile{profile}';d.mkdir()
  for name,value in data.items():
   row=pins[profile]['files'][name];need(len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256'],'original program byte identity')
   (d/name).write_bytes(value)

def reference_command(repo,out,rt,profile,payload):
 r=rt[RUNTIME[profile]];run_dir=out/'reference_runs'/f'profile{profile}'
 runner=repo/C/('independent_reference_p0_cache_arm_20261028T2313' if profile==0 else 'independent_block_reference_prepare_v3_20261028T2312')/'run_reference.py'
 return [sys.executable,HERE/'bounded_reference_owned.py','--site',r['site'],'--sidecar',r['sidecar']['path'],'--sidecar-sha',r['sidecar']['sha256'],'--run-dir',run_dir,'--rss-gib','3','--cpu-seconds','1200','--wall-seconds','1800','--',r['wrapper'],runner,'--profile',str(profile),'--payload',payload,'--config',repo/'config/upstream/weight_headers'/MODEL[profile]/'config.json','--runtime-receipt',r['receipt']['path'],'--runtime-receipt-sha256',r['receipt']['sha256'],'--runtime-source-pins',r['sidecar']['path'],'--runtime-source-pins-sha256',r['sidecar']['sha256'],'--output',run_dir/'reference','--execute-reviewed']

def materialize(repo,out,runtimes,i):
 from acquire_profile import selected_plan
 runtime_document=json.loads(runtimes.read_text());rt=runtime_document['entries'];need(set(rt)=={RUNTIME[i]} and runtime_document['profile']==i and runtime_document['selected_runtime']==RUNTIME[i],'only selected runtime allowed')
 r=rt[RUNTIME[i]];need(runtime_document['provider_python']==r['wrapper'],'selected provider runtime')
 for k in ('wrapper','site'):need(P(r[k]).is_absolute() and P(r[k]).resolve().is_relative_to(out.resolve()),'runtime outside job OUT')
 verify_pin(r['receipt'],out);verify_pin(r['sidecar'],out)
 payload=out/'payload';plan=selected_plan(repo,i)
 run([sys.executable,HERE/'acquire_profile.py','--repo',repo,'--profile',i,'--output',payload,'--execute'],out,'01_acquire',3600)
 summary=json.loads((payload/'SUMMARY.json').read_text());need(summary['profile']==i and summary['tensors']==len(plan['specs']) and summary['tensor_bytes']==sum(t['bytes'] for t in plan['specs']),'complete selected native tensor inventory')
 programs(repo,out/'programs',i);(out/'reference_runs').mkdir();refs=out/'references';refs.mkdir()
 run(reference_command(repo,out,rt,i,payload),out,f'02_reference_{i}',1900)
 source=out/'reference_runs'/f'profile{i}'/'reference';refs.joinpath(f'profile{i}').symlink_to(source,target_is_directory=True)
 result=json.loads((source/'RESULT.json').read_text());need(result['complete_block_tokens']==128 and result['profile']['profile']==i and result['exact_baseline_observer_output_equal'] is True,'full original reference')
 py=r['wrapper'] # selected locked NumPy, not software DUT arithmetic
 if i==0:
  rope_run=out/'rope_run'
  run([sys.executable,HERE/'bounded_reference_owned.py','--site',r['site'],'--sidecar',r['sidecar']['path'],'--sidecar-sha',r['sidecar']['sha256'],'--run-dir',rope_run,'--rss-gib','1','--cpu-seconds','120','--wall-seconds','120','--',py,HERE/'generate_p0_rope.py','--config',repo/'config/upstream/weight_headers/qwen2_1p5b/config.json','--reference',source,'--output',rope_run/'table'],out,'03_p0_rope',150)
  rope=rope_run/'table/rope_fp32.bin';need(sha(rope)=='4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815','original RoPE identity')
  run([py,repo/P0/'rebuild.py','--repo',repo,'--payload',payload,'--reference',source,'--rope',rope,'--rope-sha256',sha(rope),'--output',out/'p0_provider'],out,'04_p0_provider')
  run([py,repo/P0/'emit_tsv.py','--payload',payload,'--provider',out/'p0_provider','--output',out/'p0_transport'],out,'05_p0_tsv');d=out/'p0_transport';receipt=out/'p0_provider/RESULT.json'
 elif i in (1,2):
  run([py,HERE/'provider_p12.py','--profile',i,'--repo',repo,'--programs',out/'programs','--payload',payload,'--reference-root',refs,'--acquisition-metadata',repo/ACQ,'--output',out/'p12_provider'],out,'06_p12_provider');d=out/'p12_provider'/f'profile{i}';receipt=d/'source_spec.json'
 else:
  inputs=out/'input_only';d=inputs/f'P{i}';d.mkdir(parents=True)
  (d/'hidden.storage.bin').symlink_to((source/'input_only/hidden_storage.bin').resolve())
  argv=[py,HERE/'provider_p34.py','--repo',repo,'--programs',out/'programs','--payload',payload,'--inputs',inputs,'--output',out/'p34_provider','--profiles',i]
  if i==4:argv+=['--reference-result',source/'RESULT.json','--reference-result-sha256',sha(source/'RESULT.json')]
  run(argv,out,'07_p34_provider');d=out/'p34_provider'/f'profile{i}';receipt=d/'source_spec.json'
 profile=dict(id=i,runtime=pin(d/'runtime.tsv'),views=pin(d/'views.tsv'),reference_result=pin(source/'RESULT.json'),provider_receipt=pin(receipt))
 for k in ('runtime','views','reference_result','provider_receipt'):verify_pin(profile[k],out)
 save(out/'runtime_bundle.json',dict(schema='SINGLE_PROFILE_RUNTIME_BUNDLE_V1',status='FRESH_SELECTED_REFERENCE_AND_PROVIDER_NOT_DUT',profiles=[profile],limits=dict(address_space_bytes=12*1024**3,cpu_seconds=18000,wall_seconds=20000,file_bytes=64*1024**2,max_active_cycles=1000000000),hardware_executed=False,raw_payloads_upload_allowed=False))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=P,required=True);ap.add_argument('--output',type=P,required=True);ap.add_argument('--profile',type=int,choices=range(5),required=True);ap.add_argument('--check-sources',action='store_true');import connect_bundle;connect_bundle.add_arguments(ap);a=ap.parse_args();repo=a.repo.resolve();out=a.output.resolve();sources(repo)
 if a.check_sources:print('SOURCE_PINS_ONLY_NO_EXECUTION');return
 connect_bundle.preflight(a)
 need(not out.exists(),'fresh job output only');out.mkdir(parents=True)
 run([sys.executable,repo/C/'ci_single_profile_runtime_20261029/prepare_runtimes.py','--repo',repo,'--output',out/'runtimes','--profile',a.profile,'--execute-reviewed'],out,'00_runtimes',3600)
 materialize(repo,out,out/'runtimes/RUNTIMES.json',a.profile)
 connect_bundle.connect(a,out)
if __name__=='__main__':main()
