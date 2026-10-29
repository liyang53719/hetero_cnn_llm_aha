"""R7-only serial frontend. stage callback owns locks/caps/receipts and fail-closed exit.
No shell/make recipe execution. No compiler/archive/link or numerical qualification.
"""
from pathlib import Path
import hashlib,json,os,shlex,sys
PREFIXES=('Vbf16_context_lane_cluster16_rev8b_b_candidate_d','Vqwen2_matrix_command_endpoint_0','VTransposedDenseDownOwner','VHostBlockTopV4')
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def completed(receipt):
 need(receipt.get('native_exit')==0 and not receipt.get('errors') and receipt.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','native stage incomplete or cleanup not proven')

def audit_plan(obj):
 obj=Path(obj).resolve();found={p.name for p in obj.glob('*__hierMkArgs.f')};need(found=={x+'__hierMkArgs.f' for x in PREFIXES},'exact R7 four stages required')
 need(not any(p.suffix in ('.cpp','.h','.sv','.a','.o') for p in obj.rglob('*') if p.is_file()),'plan-only unexpectedly generated child files')
 records=[]
 for prefix in PREFIXES:
  p=obj/(prefix+'__hierMkArgs.f');need(not p.is_symlink(),'args symlink');tokens=shlex.split(p.read_text());need('--cc' in tokens and not any(x in tokens for x in ('--build','--binary')),'frontend only')
  need(tokens.count('-Mdir')==1 and tokens.count('--prefix')==1,'one Mdir/prefix');target=Path(tokens[tokens.index('-Mdir')+1]);expected=obj if prefix=='VHostBlockTopV4' else obj/prefix;need(target==expected,'owned native Mdir');need(tokens[tokens.index('--prefix')+1]==prefix,'native prefix drift')
  if prefix!='VHostBlockTopV4':need('--hierarchical-child' in tokens,'native child required')
  else:need('--hierarchical' not in tokens,'Host must not respawn scanner')
  records.append({'prefix':prefix,'args':str(p),'args_sha256':sha(p)})
 return records

def run_frontend_serial(stage,argv,python,verilator,out):
 """stage(name, argv, seconds, rss, env_override, extra_watch_roots, extra_pins).
 stage must require native0 + no errors + complete cleanup BEFORE returning,
 use global disk/deadline gates, and pin extra_pins under the same lock.
 """
 out=Path(out).resolve();obj=out/'frontend/obj';argv=list(argv)
 need(argv[0]==verilator and '--hierarchical' in argv,'reviewed hierarchical initial argv')
 need(argv[argv.index('--Mdir')+1]==str(obj),'expected owned obj')
 for flag in ('--build-jobs','--verilate-jobs','--threads'):need(argv.count(flag)==1 and argv[argv.index(flag)+1]=='1','serial options')
 # Freeze freshly emitted SV/FMA and other concrete argv files before any scan.
 concrete_pins={}
 for token in argv[1:]:
  p=Path(token)
  if p.is_absolute() and p.is_file():
   need(not p.is_symlink(),'concrete input symlink');concrete_pins[str(p)]=sha(p)
 plan_receipt=stage('frontend',argv,seconds=180,rss=7,env_override={'MAKEFLAGS':'-n'},extra_watch_roots=[],extra_pins=concrete_pins);completed(plan_receipt)
 records=audit_plan(obj);manifest=out/'frontend/SERIAL_NATIVE_PLAN.json';manifest.write_text(json.dumps({'scope':'R7_NATIVE_PLAN_CODEGEN_ONLY','stages':records},indent=2)+'\n')
 helper=Path(__file__).resolve();pins={**concrete_pins,str(helper):sha(helper),str(manifest):sha(manifest),**{x['args']:x['args_sha256'] for x in records}}
 receipts=[]
 for row in records:
  prefix=row['prefix'];args=row['args'];need(sha(args)==row['args_sha256'],'plan drift')
  command=[python,str(helper),'--native-exec',str(out/'frontend'),verilator,args,row['args_sha256']]
  receipt=stage('frontend_native_'+prefix,command,seconds=1800,rss=12,env_override={'MAKEFLAGS':'-j1'},extra_watch_roots=[str(out/'frontend')],extra_pins=pins)
  completed(receipt);receipts.append({'prefix':prefix,'receipt':receipt})
  # Host needs exact wrappers from completed preceding children. Pin each before next stage.
  if prefix!='VHostBlockTopV4':
   wrappers=list((obj/prefix).glob('*.sv'));need(len(wrappers)==1,'exactly one native child wrapper');pins[str(wrappers[0])]=sha(wrappers[0])
 need((obj/'VHostBlockTopV4.h').is_file(),'Host header missing')
 need(any(obj.glob('VHostBlockTopV4*.cpp')),'Host cpp missing')
 result={'scope':'FRONTEND_CODEGEN_ONLY_NO_BINARY_NO_NUMERICS','plan_manifest_sha256':sha(manifest),'stages':receipts,'scanner_exited_before_children':True};(out/'SERIAL_FRONTEND_RESULT.json').write_text(json.dumps(result,indent=2)+'\n');return result

def native_exec(args):
 need(len(args)==5 and args[0]=='--native-exec','internal native worker arguments')
 root=Path(args[1]).resolve();tool=Path(args[2]);f=Path(args[3]).resolve();digest=args[4]
 need(root.name=='frontend' and f.parent==root/'obj' and f.name in {x+'__hierMkArgs.f' for x in PREFIXES},'owned native plan')
 need(not f.is_symlink() and sha(f)==digest,'native plan hash drift');need(tool.is_absolute() and tool.is_file(),'pinned tool required')
 os.chdir(root);os.execve(str(tool),[str(tool),'-f',str(f)],dict(os.environ))
if __name__=='__main__':native_exec(sys.argv[1:])
