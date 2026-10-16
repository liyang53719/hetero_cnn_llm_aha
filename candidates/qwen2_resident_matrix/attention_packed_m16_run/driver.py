"""One same-PID child: source composition, genuine Git, clean exec, original run."""
# Popen inherits the parent's temporary ownership-protection mask across exec.
import signal
signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT})
import hashlib,importlib,json,math,os,shutil,subprocess,sys,time
from pathlib import Path
OWN=Path(__file__).resolve().parent
sys.path.insert(0,str(OWN))
import launch as L

def compact(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def command(args,cwd,stop,ceiling=10):
 if args[0]=='git':args=['git','-c','protocol.allow=never','-c','protocol.file.allow=always',*args[1:]]
 remaining=min(ceiling,stop-time.monotonic());L.need(remaining>0,'source command budget')
 return subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=remaining).stdout

def progress(context,context_sha,phase):
 L.need(phase in L.PHASES,'fixed phase')
 value=dict(schema=1,phase=phase,ordinal=L.PHASES.index(phase),pid=os.getpid(),elapsed_seconds=round(time.monotonic()-context['started'],6),context_sha256=context_sha)
 target=Path(context['workspace'])/'control/progress.json'
 if target.exists():
  _,old=L.bounded_json(target)
  L.need(old['pid']==os.getpid() and old['context_sha256']==context_sha and old['ordinal']<=value['ordinal'] and old['elapsed_seconds']<=value['elapsed_seconds'],'monotonic same-writer phase')
 L.atomic(target,value)

def read_context(path,expected):
 raw,value=L.bounded_json(path);L.need(L.digest(raw)==expected,'immutable invocation context')
 keys={'schema','profile','source_root','origin','preparation_workspace','compile_receipt','compile_origin','workspace','python','contract_sha256','started','work_deadline','outer_deadline','parent_pid'}
 L.need(set(value)==keys and type(value['schema']) is int and value['schema']==1 and value['profile']==L.PROFILE,'context schema')
 L.need(type(value['parent_pid']) is int and value['parent_pid']==os.getppid(),'same supervising parent')
 L.need(all(type(value[k]) in (int,float) and math.isfinite(value[k]) and value[k]>0 for k in ('started','work_deadline','outer_deadline')),'finite typed context time')
 L.need(value['work_deadline']==value['started']+924 and value['outer_deadline']==value['started']+930 and value['started']<=time.monotonic()<value['work_deadline'],'same original deadlines')
 L.need(sys.flags.optimize==0 and sys.implementation.name=='cpython' and list(sys.version_info[:3])==[3,12,14],'normal pinned Python required')
 return value

def prepare(context,context_path,context_sha):
 source=Path(context['source_root']);work=Path(context['workspace']);stop=context['work_deadline']
 contract,pins=L.load_contract(context['contract_sha256'],source)
 L.runtime_python(Path(context['origin']),sys.executable,contract)
 progress(context,context_sha,'compose')
 sys.path.insert(0,str(source))
 prep=importlib.import_module('candidates.qwen2_resident_matrix.attention_packed_m16_host_job.prepare')
 L.need(Path(prep.__file__).resolve()==source/(L.REPAIR+'prepare.py'),'exact preparation import')
 overlay=prep.compose(work/'overlay')
 runtime_sources=dict(pins['sources'],**pins['own'],**pins['generated'])
 runtime_sources[L.PREFIX+'pins.json']=contract['runtime_entry_pins_sha256']
 L.verify_map(overlay,runtime_sources)
 entry_raw,installed=L.bounded_json(overlay/(L.PREFIX+'pins.json'))
 L.need(L.digest(entry_raw)==contract['runtime_entry_pins_sha256'],'repaired installed entry identity')
 installed_map=dict(installed['sources'],**installed['own'],**installed['generated']);installed_map[L.PREFIX+'pins.json']=L.digest(entry_raw)
 L.need(L.same(installed_map,runtime_sources),'generated entry map differs from independently pinned repair')
 files={str(p.relative_to(overlay)) for p in overlay.rglob('*') if p.is_file()}
 L.need(files==set(runtime_sources),'exact composition file inventory')
 progress(context,context_sha,'git_clone')
 base=L.safe(Path(context['origin'])/'source',True);runtime=work/'source'
 head=command(['git','rev-parse','HEAD'],base,stop).decode().strip()
 L.need(head==contract['origin_commit'],'original genuine Git HEAD')
 L.need(not command(['git','status','--porcelain','--untracked-files=all'],base,stop),'clean immutable original checkout')
 command(['git','clone','--no-hardlinks','--no-checkout',str(base),str(runtime)],work,stop,15)
 command(['git','checkout','--detach',head],runtime,stop)
 for name in runtime_sources:
  destination=runtime/name;destination.parent.mkdir(parents=True,exist_ok=True)
  L.need(not destination.is_symlink(),'no source overlay symlink')
  destination.write_bytes((overlay/name).read_bytes())
 L.verify_map(runtime,runtime_sources)
 L.need(command(['git','rev-parse','HEAD'],runtime,stop).decode().strip()==head,'cloned Git HEAD')
 cpp='chisel/continuous_prefill/tests/qwen2_block.cpp'
 committed=command(['git','show','HEAD:'+cpp],runtime,stop)
 L.need(committed==(runtime/cpp).read_bytes(),'authentic committed scalar arithmetic')
 changed=command(['git','status','--porcelain','--untracked-files=all'],runtime,stop).decode().splitlines()
 L.need(all(line[3:] in runtime_sources for line in changed),'no unrelated Git changes')
 proof=dict(schema=1,pid=os.getpid(),context_sha256=context_sha,work_deadline=stop,git_head=head,committed_cpp_sha256=L.digest(committed),runtime_sources=runtime_sources,source_manifest_sha256=L.digest(compact(runtime_sources)))
 L.atomic(work/'control/SOURCE_PROOF.json',proof)
 progress(context,context_sha,'reexec')
 # A genuine exec clears all source-preparation imports; it preserves PID,
 # process group and the original context/deadline, never starting a new budget.
 os.chdir(runtime)
 signal.setitimer(signal.ITIMER_REAL,0)
 os.execv(context['python'],[context['python'],'-I','-B',str(L.HERE/'driver.py'),'run',str(context_path),context_sha])

def run(context,context_sha):
 work=Path(context['workspace']);runtime=work/'source'
 L.need(Path.cwd()==runtime,'installed runtime cwd required')
 contract,_=L.load_contract(context['contract_sha256'],Path(context['source_root']))
 L.runtime_python(Path(context['origin']),sys.executable,contract)
 _,proof=L.bounded_json(work/'control/SOURCE_PROOF.json')
 L.need(proof['pid']==os.getpid() and proof['context_sha256']==context_sha and proof['work_deadline']==context['work_deadline'],'same-PID context after exec')
 L.verify_map(runtime,proof['runtime_sources']);sys.path.insert(0,str(runtime))
 from candidates.qwen2_resident_matrix.attention_packed_m16_entry import admission,contract as linked
 from candidates.qwen2_resident_matrix.raw_kv_public_fresh import setup
 sources=linked.snapshot();L.need(sources==proof['runtime_sources'] and L.digest(compact(sources))==proof['source_manifest_sha256'],'installed complete source closure')
 linked.git_context()
 progress(context,context_sha,'admission')
 torch,identity=setup.backend_identity()
 torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 manifest,manifest_sha,admitted=admission.seal_manifest(work/'INPUTS.json',origin=context['origin'],preparation_workspace=context['preparation_workspace'],compile_receipt=context['compile_receipt'],compile_origin=context['compile_origin'])
 progress(context,context_sha,'snapshot')
 from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as entry
 snapshot_path,snapshot=entry.prepare(work/'snapshot',context['compile_receipt'],None,None,rows=16,enable_raw_kv=True,fresh_profile=True,fresh_manifest=str(manifest),fresh_manifest_sha256=manifest_sha,enable_packed=True)
 snapshot_sha=L.sha_file(snapshot_path)
 run_context=dict(profile=linked.PROFILE,attempt=1,pid=os.getpid(),started=context['started'],work_deadline=context['work_deadline'],outer_deadline=context['outer_deadline'],source_manifest_sha256=proof['source_manifest_sha256'])
 progress(context,context_sha,'numeric')
 result=entry.run(work/'actual',snapshot_path,snapshot_sha,wall_budget=900,enable_raw_kv=True,fresh_profile=True,enable_packed=True,run_context=run_context)
 progress(context,context_sha,'postflight')
 report_raw,report_on_disk=L.bounded_json(work/'actual/summary.json')
 L.need(L.same(result,report_on_disk),'returned report differs from same-byte disk summary')
 import terminal_validator as terminal
 public=terminal.validate_terminal(work/'actual/summary.json',L.digest(report_raw),sources,snapshot_path,snapshot_sha)
 L.need(linked.snapshot()==sources and linked.git_context()['commit']==proof['git_head'],'postflight full source/Git identity')
 L.need(L.sha_file(snapshot_path)==snapshot_sha,'postflight snapshot changed')
 admission.verify(manifest,manifest_sha,rows=16,enable_raw_kv=True)
 L.load_contract(context['contract_sha256'],Path(context['source_root']))
 complete=dict(schema=1,status='VALIDATED_M16_CHILD_COMPLETE',pid=os.getpid(),context_sha256=context_sha,source_manifest_sha256=proof['source_manifest_sha256'],result_sha256=public['summary_sha256'],snapshot_sha256=snapshot_sha,public=public)
 L.atomic(work/'control/CHILD_COMPLETE.json',complete)
 progress(context,context_sha,'complete')

def main():
 L.need(len(sys.argv)==4 and sys.argv[1] in ('prepare','run'),'exact child invocation')
 phase,path,context_sha=sys.argv[1:];context_path=L.safe(path);context=read_context(context_path,context_sha)
 with L.deadline(context['work_deadline']):
  if phase=='prepare':prepare(context,context_path,context_sha)
  else:run(context,context_sha)
if __name__=='__main__':main()
