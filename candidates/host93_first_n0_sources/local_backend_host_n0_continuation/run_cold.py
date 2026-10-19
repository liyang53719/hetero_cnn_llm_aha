"""Finite source-only cold tests. All native/network operations are forbidden."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before source reads')
import argparse,hashlib,json,os,resource,signal,stat,types
from pathlib import Path
ROOT=Path(__file__).absolute().parent
PINS={'accepted_toolchain.py':(4312,'8719c513afec5bf48565bdb1dc27e70bdf150560828de7fc08936bc33c550dcd'),'cached_flex_header.py':(3269,'afaf98d6137562790b0664293acf465859288549e30d87f197879cb334979403'),'local_toolchain_adapter.py':(8776,'5b21cf3d8969873b3d751f52d64dc7e9528edc0a7d68ce3b91d88f65c8ca3896')}
PINS['continuation_entry.py']=(17111, 'e8b45d2563b6079058663f98f22275d093ca808e0187f55476f16d224ab54675')
PINS['source_entry.py']=(8437, 'be54ecc74488a2dce76318d2a86b73f52427a9a8364480662c800fe40b22c6dc')
PINS.update({'test_accepted_cold.py': (6366, 'f995500d16aa8a468bd6390c3ceb1be5fb8d36696f1cf76527fe2e1b13406c27'), 'test_continuation_cold.py': (14082, '4181960901b28ce945d2a9f37541320c61fa258e607b23ed14394cd9fb715321'), 'test_entry_cold.py': (4702, '80003fb32b45ccd8181f85165a05d090010ab25c5f52e3ac8cdfa1a681476bf4'), 'test_fault_cold.py': (5788, '7621afbdc3d344438f0d826f4c7820b75b6d7f0655ce068e431a3bfa28652f59'), 'test_header_cold.py': (7564, 'dc11b11d30859ccdda244b2ef4fb80f83adfac5e791b02432e565f2341dced8e'), 'test_stage_cold.py': (3743, '1a819b03f8a87486a7d52efa6700cda4ad28c38753513da5d0a5ab656914ac0b')})
def need(ok,why):
    if not ok:raise ValueError(why)
def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def read(path,expected):
    path=Path(path);size,digest=expected
    need(path.is_absolute() and '..' not in path.parts,'absolute finite source')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        f=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(f);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==size,'single-link finite source')
            chunks=[];count=0
            while count<=size:
                data=os.read(f,min(65536,size+1-count))
                if not data:break
                chunks.append(data);count+=len(data)
            raw=b''.join(chunks);stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            need(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest and stamp(before)==stamp(os.fstat(f))==stamp(os.stat(path.name,dir_fd=fd,follow_symlinks=False)),'fixed source same-buffer identity')
            return raw
        finally:os.close(f)
    finally:os.close(fd)
def loaded(path,key):
    raw=read(path,PINS[key]);m=types.ModuleType('_cold_'+key.replace('.','_'));m.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m
def audit(event,args):
    if event.startswith(('subprocess.','socket.')) or event in ('os.system','os.fork','os.forkpty','os.exec','os.posix_spawn','pty.spawn','urllib.Request'):
        raise RuntimeError('cold tests forbid native and network execution')
sys.addaudithook(audit)
resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(40,40));signal.alarm(60)
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--repo',type=Path,required=True);p.add_argument('--caller-source',type=Path,required=True);p.add_argument('--consumer-source',type=Path,required=True);args=p.parse_args();REPO=args.repo;CONSUMER_SOURCE=args.consumer_source
accepted=loaded(ROOT/'accepted_toolchain.py','accepted_toolchain.py');header=loaded(ROOT/'cached_flex_header.py','cached_flex_header.py');adapter=loaded(args.caller_source/'local_toolchain_adapter.py','local_toolchain_adapter.py')
continuation=loaded(ROOT/'continuation_entry.py','continuation_entry.py');entry=loaded(ROOT/'source_entry.py','source_entry.py')
CI_RAW=read(REPO/adapter.CI,(adapter.CI_PIN['bytes'],adapter.CI_PIN['sha256']))
def make_ci():
    c=types.ModuleType('_synthetic_ci');c.__file__=str(REPO/adapter.CI)
    exec(compile(CI_RAW,c.__file__,'exec',dont_inherit=True),c.__dict__);return c
TEST_RESULTS=[]
for name in ('test_accepted_cold.py','test_header_cold.py','test_continuation_cold.py','test_stage_cold.py','test_entry_cold.py','test_fault_cold.py'):
    raw=read(ROOT/name,PINS[name]);namespace=dict(globals(),__name__='_cold_'+name,__file__=str(ROOT/name))
    exec(compile(raw,str(ROOT/name),'exec',dont_inherit=True),namespace)
print(json.dumps({'status':'PASS_FINITE_BACKEND_HOST_N0_COLD_ONLY','tests':sum(row['tests'] for row in TEST_RESULTS),'modules':TEST_RESULTS,'optimized':sys.flags.optimize,'native_started':False,'network_started':False,'actual_execution_authorized':False},sort_keys=True))
