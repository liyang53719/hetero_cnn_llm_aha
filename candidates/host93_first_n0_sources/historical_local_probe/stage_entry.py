"""Two explicit local-probe entries: fixed11 wheels or existing fixed raw2 read."""
import argparse,hashlib,json,math,os,stat,sys,time,types
from pathlib import Path
PREFIX='candidates/host93_first_n0_sources/historical_local_probe/'
REFERENCE='candidates/host93_first_n0_sources/reference/'
RUNTIME_PIN=(16640,'80a664a451ca8f587321c6da04d15ca8377cb56f8ac00c42dd1c68290f1e4222')
PINS_PIN=(6364,'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8')
CODES=frozenset(('FLAGS','PATH','SOURCE','DEADLINE','RAW2','OUTPUT','RESOURCE','UNEXPECTED','SOURCE_IDENTITY','FILESYSTEM','PYTHON_IDENTITY','EXECUTION_DISABLED','NETWORK','REDIRECT','RESPONSE','WHEEL_SIZE','WHEEL_HASH','WHEEL_SET','TREE_LIMIT','OBSERVATION'))
SAFE_MARKERS=frozenset('LOCAL_PROBE_FAILED:'+s+':'+c for s in ('SOURCE','WHEELS','RAW2') for c in CODES)
class Rejected(ValueError):pass
class Parser(argparse.ArgumentParser):
 def error(self,message):raise Rejected('FLAGS')
def need(ok,code):
 if not ok:raise Rejected(code)
def checked(path,pin,code='SOURCE'):
 p=Path(path);need(p.is_absolute() and '..' not in p.parts and all(not x.is_symlink() for x in (p,*p.parents)),'PATH')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_size==pin[0],code);raw=f.read(pin[0]+1);z=os.fstat(f.fileno())
 stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 need(len(raw)==pin[0] and hashlib.sha256(raw).hexdigest()==pin[1] and stamp(a)==stamp(z)==stamp(p.stat(follow_symlinks=False)),code);return raw
def load_runtime(repo):
 p=repo/PREFIX/'historical_runtime.py';raw=checked(p,RUNTIME_PIN);m=types.ModuleType('_historical_runtime');m.__file__=str(p);sys.modules[m.__name__]=m;exec(compile(raw,str(p),'exec',dont_inherit=True),m.__dict__);return m
def raw2_receipt(repo,embedding,gamma):
 pins=json.loads(checked(repo/REFERENCE/'PINS.json',PINS_PIN));rows={}
 for role,p in (('embedding',embedding),('gamma',gamma)):
  pin=pins['raw2'][role];checked(p,(pin['bytes'],pin['sha256']),'RAW2');rows[role]={k:pin[k] for k in ('bytes','sha256')}
 return {'schema':1,'status':'LOCAL_RAW2_IDENTITY_ONLY','origin':'EXISTING_PINNED_RAW2_READ_ONLY','inputs':rows,'network_acquired_here':False,'reference_executed':False,'dut_executed':False}
def main(argv=None):
 stage='SOURCE';runtime=None
 try:
  need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'FLAGS')
  ap=Parser(allow_abbrev=False);ap.add_argument('--stage',choices=('wheels','raw2'));ap.add_argument('--repo',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--embedding',type=Path);ap.add_argument('--gamma',type=Path);ap.add_argument('--deadline',type=float);ap.add_argument('--execute',action='store_true');a=ap.parse_args(argv)
  if not a.execute:print('LOCAL_PROBE_SOURCE_ONLY');return 0
  need(a.stage is not None and a.repo is not None and a.out is not None and a.deadline is not None,'FLAGS');need(math.isfinite(a.deadline) and time.monotonic()<a.deadline-5,'DEADLINE')
  if a.stage=='wheels':
   need(a.embedding is None and a.gamma is None,'FLAGS');stage='WHEELS';runtime=load_runtime(a.repo);runtime.require_current_python();runtime.acquire_wheels(a.repo/REFERENCE,a.out,execute=True,deadline=a.deadline-5)
  else:
   stage='RAW2';need(a.embedding is not None and a.gamma is not None,'FLAGS');receipt=raw2_receipt(a.repo,a.embedding,a.gamma);p=a.out
   need(p.is_absolute() and '..' not in p.parts and all(not x.is_symlink() for x in (p,*p.parents)) and p.parent.is_dir() and not os.path.lexists(p),'PATH');p.mkdir(mode=0o700)
   raw=(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode()
   with (p/'RECEIPT.json').open('xb') as f:need(f.write(raw)==len(raw),'OUTPUT')
  need(time.monotonic()<a.deadline-5,'DEADLINE');print('LOCAL_PROBE_OK:'+a.stage.upper());return 0
 except (TimeoutError,MemoryError):code='RESOURCE'
 except Rejected as e:code=str(e) if str(e) in CODES else 'UNEXPECTED'
 except BaseException as e:code=str(e) if runtime is not None and isinstance(e,runtime.GateError) and str(e) in CODES else 'UNEXPECTED'
 print('LOCAL_PROBE_FAILED:'+stage+':'+code);return 1
if __name__=='__main__':raise SystemExit(main())
