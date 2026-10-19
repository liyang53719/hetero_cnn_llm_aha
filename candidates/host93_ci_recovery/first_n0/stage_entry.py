"""Two fixed explicit acquisition entries; all data/tracebacks remain private."""
import argparse,hashlib,json,math,os,stat,sys,time,types
from pathlib import Path
RAW_PATH='development_snapshots/canonical_raw_acquisition_source_20261018/acquire_raw.py'
RAW_PIN=(17991,'4cff91b1a5e76a6a1701426fd1e6cb1f8db32ee8b7e762bb17575364b12d932a')
RUNTIME_PATH='candidates/host93_first_n0_sources/runtime/runtime_wheel_gate.py'
RUNTIME_PIN=(16625,'736ab1d718ffb3fd100fb4e4bb92857fbae0b80bb1fd195c064f36833032050d')
REFERENCE_PATH='candidates/host93_first_n0_sources/reference'
RAW_RULES={'--execute requires --output': 'RAW_RULE_001', 'HTTP error or redirect limit; no retry': 'RAW_RULE_002', 'ambiguous transport framing': 'RAW_RULE_003', 'assembled tensor SHA mismatch': 'RAW_RULE_004', 'assembled tensor too long': 'RAW_RULE_005', 'bundle identity drift': 'RAW_RULE_006', 'cache symlink refused': 'RAW_RULE_007', 'cannot inspect signal mask': 'RAW_RULE_008', 'deadline/timer conflict': 'RAW_RULE_009', 'duplicate JSON key': 'RAW_RULE_010', 'fixed acquisition budget drift': 'RAW_RULE_011', 'fixed acquisition plan hash drift': 'RAW_RULE_012', 'helper definitions drift': 'RAW_RULE_013', 'historical work tree refused': 'RAW_RULE_014', 'inherited SIGALRM block defeats shared deadline': 'RAW_RULE_015', 'input changed length': 'RAW_RULE_016', 'input grew beyond bound': 'RAW_RULE_017', 'input size drift': 'RAW_RULE_018', 'insufficient remaining disk': 'RAW_RULE_019', 'missing or duplicate range header': 'RAW_RULE_020', 'need at least 512 MiB free disk': 'RAW_RULE_021', 'nonregular cache refused': 'RAW_RULE_022', 'nonregular or oversized input': 'RAW_RULE_023', 'output disk budget exceeded': 'RAW_RULE_024', 'output must be a new directory under an existing parent': 'RAW_RULE_025', 'output must be outside repository': 'RAW_RULE_026', 'platform API evidence hash drift': 'RAW_RULE_027', 'platform metadata evidence identity drift': 'RAW_RULE_028', 'raw pin identity drift': 'RAW_RULE_029', 'refuse output overwrite': 'RAW_RULE_030', 'request plan drift': 'RAW_RULE_031', 'retained cache budget drift': 'RAW_RULE_032', 'segment count drift': 'RAW_RULE_033', 'segment destination already exists': 'RAW_RULE_034', 'segment geometry drift': 'RAW_RULE_035', 'shard count drift': 'RAW_RULE_036', 'shard identity drift': 'RAW_RULE_037', 'shared wall deadline exceeded': 'RAW_RULE_038', 'source Git blob drift': 'RAW_RULE_039', 'source path escape': 'RAW_RULE_040', 'symlink path refused': 'RAW_RULE_041', 'tensor destination already exists': 'RAW_RULE_042', 'tensor dtype/size drift': 'RAW_RULE_043', 'tensor hash drift': 'RAW_RULE_044', 'tensor plan drift': 'RAW_RULE_045', 'tensor size drift': 'RAW_RULE_046', 'tensor too long': 'RAW_RULE_047', 'unapproved redirect URL': 'RAW_RULE_048'}

class Rejected(ValueError):pass
class Parser(argparse.ArgumentParser):
 def error(self,message):raise Rejected('FLAGS')
def need(ok,code):
 if not ok:raise Rejected(code)
def module(path,pin):
 need(path.is_absolute() and '..' not in path.parts and all(not x.is_symlink() for x in (path,*path.parents)),'PATH')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());raw=f.read(pin[0]+1);z=os.fstat(f.fileno())
 ident=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 need(stat.S_ISREG(a.st_mode) and a.st_size==pin[0] and len(raw)==pin[0] and hashlib.sha256(raw).hexdigest()==pin[1] and ident(a)==ident(z)==ident(path.stat(follow_symlinks=False)),'SOURCE')
 m=types.ModuleType('_fixed_'+pin[1][:12]);m.__file__=str(path);sys.modules[m.__name__]=m;exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m

def main(argv=None):
 stage='SOURCE';code='UNEXPECTED';raw_module=None;runtime=None
 try:
  need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'FLAGS')
  ap=Parser(prog='n0-acquisition',allow_abbrev=False)
  ap.add_argument('--stage',choices=('wheels','raw'));ap.add_argument('--repo');ap.add_argument('--out');ap.add_argument('--deadline',type=float);ap.add_argument('--execute',action='store_true')
  a=ap.parse_args(argv)
  if not a.execute:print('N0_ACQUISITION_SOURCE_ONLY');return 0
  need(all(v is not None for v in (a.stage,a.repo,a.out,a.deadline)),'FLAGS')
  need(math.isfinite(a.deadline) and time.monotonic()<a.deadline-5,'DEADLINE');repo=Path(a.repo);out=Path(a.out)
  if a.stage=='wheels':
   stage='WHEELS';runtime=module(repo/RUNTIME_PATH,RUNTIME_PIN)
   runtime.require_current_python();runtime.acquire_wheels(repo/REFERENCE_PATH,out,execute=True,deadline=a.deadline-5)
  else:
   stage='RAW_SOURCE';raw_module=module(repo/RAW_PATH,RAW_PIN)
   plan,helpers,shard=raw_module.check_sources(repo,repo/Path(RAW_PATH).parent/'ACQUISITION_PLAN.json')
   stage='RAW_OUTPUT';output=raw_module.prepare_output(repo,out)
   stage='RAW_ACQUIRE';raw_module.collect_fixed(plan,helpers,shard,output,raw_module.strict_opener(a.deadline-5))
  need(time.monotonic()<a.deadline-5,'DEADLINE');print('N0_ACQUISITION_OK:'+a.stage.upper());return 0
 except (TimeoutError,MemoryError):code='RESOURCE'
 except Rejected as error:code=str(error) if str(error) in ('FLAGS','PATH','SOURCE','DEADLINE') else 'UNEXPECTED'
 except BaseException as error:
  if raw_module is not None and isinstance(error,raw_module.Refused):code=RAW_RULES.get(str(error),'UNMAPPED_RAW')
  elif runtime is not None and isinstance(error,runtime.GateError):code=str(error) if str(error) in runtime.CODES else 'UNEXPECTED'
  else:code='UNEXPECTED'
 print('N0_ACQUISITION_FAILED:'+stage+':'+code);return 1
if __name__=='__main__':raise SystemExit(main())
