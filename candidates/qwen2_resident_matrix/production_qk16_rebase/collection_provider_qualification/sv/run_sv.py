"""One approved fixed CHIRRTL to SystemVerilog conversion, no linkage or simulation."""
import argparse,json,hashlib,signal,time
from pathlib import Path
import owned_compile
from check_sv import check,need
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(a):
 start=time.monotonic();stop=start+180
 need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'preexisting alarm')
 def alarm(sig,frame):raise TimeoutError('absolute deadline')
 old=signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,10)
 try:
  need(a.execute,'explicit --execute required');need(not a.out.exists() and not a.out.is_symlink(),'fresh out')
  own=json.loads((HERE/'ARTIFACT_HASHES.json').read_text());pins=json.loads((HERE/'INPUT_PINS.json').read_text())
  need(a.ir.is_file() and not a.ir.is_symlink() and a.receipt.is_file() and not a.receipt.is_symlink(),'regular input')
  ir=a.ir.resolve(strict=True);receipt0=a.receipt.resolve(strict=True);tool=a.firtool.resolve(strict=True);out=a.out.resolve()
  def preflight():
   need(all(sha(HERE/n)==h for n,h in own.items()),'runner identity');need(sha(ir)==pins['ir_sha256'] and ir.stat().st_size==pins['ir_bytes'],'IR identity')
   need(sha(receipt0)==pins['receipt_sha256'],'prior receipt identity');r=json.loads(receipt0.read_text());need(r['status']=='PASS_COLLECTION_NAMESPACE_BENCH_SUBTREE_CHIRRTL_ONLY','prior stage status')
   need(r['structure']['sha256']==sha(ir),'IR receipt binding');need(sha(tool)==pins['firtool_sha256'],'tool identity');need(sha(HERE/'strict_cleanup.py')==owned_compile.HELPER_SHA,'helper')
  preflight();out.mkdir();sv=out/'ProductionQk16KernelCollection.sv'
  cmd=[str(tool),'-format=fir',str(ir),'-o',str(sv),'-warn-on-unprocessed-annotations','-output-annotation-file',str(out/'circt.anno.json'),'--preserve-values=all','-disable-all-randomization','--verbose-pass-executions']
  r={'status':'NOT_COMPLETED','scope':'COMMON_NAMESPACE_BENCH_AND_FMA_SV_ONLY','budget_seconds':180,'tool_budget_seconds':150,'input_ir_sha256':pins['ir_sha256'],'prior_receipt_sha256':pins['receipt_sha256'],'rtl':True,'linked':False,'numerical':False}
  signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));(out/'argv.json').write_text(json.dumps(cmd,indent=2)+'\n');(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
  with (out/'firtool.log').open('wb') as log:
   signal.setitimer(signal.ITIMER_REAL,0)
   try:result=owned_compile.execute(cmd,cwd=out,log=log,cleanup_helper=HERE/'strict_cleanup.py',absolute_stop=stop,stage_stop=min(stop-5,time.monotonic()+150),cleanup_seconds=5)
   finally:signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
  r['stage']=result;(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
  need(result['exit_code']==0 and result['error'] is None and result['cleanup_complete'],'firtool failure')
  preflight();r['sv']=check(sv)
  need(all(x.is_file() and not x.is_symlink() for x in out.iterdir()),'flat regular output only')
  allowed={'ProductionQk16KernelCollection.sv','circt.anno.json','argv.json','receipt.json','firtool.log','native_limits.json'}
  need({x.name for x in out.iterdir()}<=allowed,'output file allowlist')
  need(sorted(str(x.relative_to(out)) for x in out.rglob('*') if x.suffix in ['.sv','.v'])==['ProductionQk16KernelCollection.sv'],'exact one recursive generated SV')
  limits=out/'native_limits.json';need(limits.is_file() and not limits.is_symlink() and limits.stat().st_size<=1024,'limits audit')
  r['native_limits']=json.loads(limits.read_text());need(r['native_limits']=={'as_limit':[2147483648,2147483648],'file_limit':[134217728,134217728],'affinity_count':1},'actual child limits')
  need(not any(p.suffix in ['.cpp','.so','.o'] for p in out.rglob('*')),'unexpected native output')
  r.update(status='PASS_COLLECTION_SV_GENERATION_INVENTORY_ONLY',elapsed_seconds=time.monotonic()-start)
  temp=out/'receipt.pending.json';temp.write_text(json.dumps(r,indent=2)+'\n');need(time.monotonic()<stop,'total deadline');temp.replace(out/'receipt.json')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in ['ir','receipt','firtool','out']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--execute',action='store_true');run(p.parse_args())
