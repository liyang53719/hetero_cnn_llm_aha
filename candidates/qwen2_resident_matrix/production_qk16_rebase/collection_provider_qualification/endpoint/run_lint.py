"""Fixed real provider Verilator lint only. No C++ generation/build/simulation."""
import argparse,hashlib,json,signal,time
from pathlib import Path
import owned_compile
P=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,s):
 if not ok:raise ValueError(s)
def run(a):
 start=time.monotonic();stop=start+210
 need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'preexisting alarm')
 def alarm(s,f):raise TimeoutError('absolute deadline')
 old=signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,15)
 try:
  need(a.execute,'explicit execute required');need(not a.out.exists() and not a.out.is_symlink(),'fresh out')
  root=a.workspace.resolve(strict=True);out=a.out.resolve();pins=json.loads((P/'INPUT_PINS.json').read_text());own=json.loads((P/'ARTIFACT_HASHES.json').read_text());c=json.loads((P/'COMPOSITION.json').read_text())
  tool=root/'production_qkv_native_tools_v10_20261017/usr/bin/verilator_bin'
  def preflight():
   need(all(sha(P/n)==h for n,h in own.items()),'runner drift')
   for n,h in pins.items():
    f=root/n;need(f.is_file() and not f.is_symlink() and sha(f)==h,'input/tool/header drift '+n)
   for prefix in ['idma_source_export_attempt_v8_20261017/source/idma_export/','production_qkv_native_tools_v10_20261017/usr/share/verilator/']:
    actual={str(f.relative_to(root)) for f in (root/prefix).rglob('*') if f.is_file()}
    need(actual=={n for n in pins if n.startswith(prefix)},'provider/tool full file inventory')
   need(len(c['sources_ordered'])==14 and c['source_count']==14,'fixed source inventory')
   for d in c['include_directories_ordered']:need((root/d).is_dir() and not (root/d).is_symlink(),'include dir')
   r=json.loads((root/'production_qk16_kernel_collection_sv_attempt_v2_20261017/receipt.json').read_text());need(r['status']=='PASS_COLLECTION_SV_GENERATION_INVENTORY_ONLY','B1 prior status')
   need(r['sv']['sha256']==c['sources_ordered'][-1]['sha256'],'SV receipt binding')
  preflight();out.mkdir()
  cmd=[str(tool),'--lint-only','--top-module','qwen2_matrix_command_endpoint',"-GENABLE_ACCUMULATOR_SEED=1'b1", '--timescale','1ns/1ps','--threads','1','--no-std','--relative-includes','--Mdir',str(out/'obj_dir')]
  cmd+=['+define+'+n for n in c['initial_defines']]
  cmd+=['+incdir+'+str(root/n) for n in c['include_directories_ordered']]
  cmd+=[str(root/r['path']) for r in c['sources_ordered']]
  r=dict(status='NOT_COMPLETED',scope='ONE_REAL_SEED_ENDPOINT_COMPONENT_LINT_ONLY',total_budget_seconds=210,tool_budget_seconds=180,top='qwen2_matrix_command_endpoint',source_count=14,endpoint_lane_configuration=512,full_bench_qualified=False,simulation=False,numerical=False,stages=[])
  signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));(out/'argv.json').write_text(json.dumps(cmd,indent=2)+'\n');(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
  with (out/'lint.log').open('wb') as log:
   signal.setitimer(signal.ITIMER_REAL,0)
   try:result=owned_compile.execute(cmd,cwd=out,log=log,cleanup_helper=P/'strict_cleanup.py',absolute_stop=stop,stage_stop=min(stop-10,time.monotonic()+180),cleanup_seconds=10)
   finally:signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
  r['stages'].append(result);(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
  preflight();r['postflight_complete']=True
  limits=json.loads((out/'native_limits.json').read_text());need(limits==dict(as_limit=[4294967296,4294967296],file_limit=[16777216,16777216],affinity_count=1),'limits drift');r['native_limits']=limits
  need(not any(f.suffix in ['.cpp','.o','.so','.a'] for f in out.rglob('*')),'unexpected native build output')
  r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name!='receipt.json'}
  r['elapsed_seconds']=time.monotonic()-start
  r['status']='PASS_ENDPOINT_COMPONENT_LINT_ONLY' if result['exit_code']==0 and result['error'] is None and result['cleanup_complete'] else 'FAIL_ENDPOINT_COMPONENT_LINT'
  temp=out/'receipt.pending.json';temp.write_text(json.dumps(r,indent=2)+'\n');need(time.monotonic()<stop,'absolute deadline');temp.replace(out/'receipt.json')
  need(r['status']=='PASS_ENDPOINT_COMPONENT_LINT_ONLY','lint failure; retain diagnostics')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true');run(p.parse_args())
