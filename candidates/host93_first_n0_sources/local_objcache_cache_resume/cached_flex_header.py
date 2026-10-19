"""One fixed cached FlexLexer header; original compile probe is projected unchanged."""
import sys
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import hashlib,json,os
from pathlib import Path
PHASE='local_flex_header_cached'
SIZE=6893
SHA='ee9859d6b3027ed565f98f42744e438ab31b2cd2e9f797ddf870029ca2021686'
def need(ok,message):
    if not ok:raise ValueError(message)
def expected(source):
    return {'schema':'LOCAL_FIXED_CACHED_FLEX_HEADER_V1','source':str(source),'header':{'bytes':SIZE,'sha256':SHA,'mode':'0o600'},'network_started':False,'native_qualification_inherited':False}
def stage(raw,source,destination):
    need(type(raw) is bytes and len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==SHA,'fixed cached header bytes')
    source,destination=Path(source),Path(destination)
    need(source.is_absolute() and destination.is_absolute() and '..' not in source.parts+destination.parts and not os.path.lexists(destination),'fresh absolute header destination')
    destination.mkdir(mode=0o700);(destination/'include').mkdir(mode=0o700)
    for relative,data in (('include/FlexLexer.h',raw),('RECEIPT.json',(json.dumps(expected(source),sort_keys=True,indent=2)+'\n').encode())):
        fd=os.open(destination/relative,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:need(os.write(fd,data)==len(data),'complete cached header write')
        finally:os.close(fd)
def bind(g,adapter,component,source,self_raw):
    source=Path(source)
    need(type(self_raw) is bytes and self_raw==g.checked(Path(__file__),g.pin(self_raw),65536),'same-buffer header helper')
    raw=g.checked(Path(component.__file__),adapter.CI_PIN)
    def argv(repo,destination,buffers):
        header=component.initial_read(source,SIZE,SHA)
        code=('import sys\n'
              'def guard(event,args):\n'
              ' if event.startswith(("socket.","subprocess.")) or event in ("urllib.Request","os.system","os.fork","os.forkpty","os.exec","os.posix_spawn","pty.spawn"):raise RuntimeError("data-only cached header")\n'
              'sys.addaudithook(guard)\nraw='+repr(self_raw)+'\nns={"__name__":"fixed_cached_header","__file__":'+repr(str(Path(__file__)))+'}\n'
              'exec(compile(raw,ns["__file__"],"exec",dont_inherit=True),ns)\n'
              'ns["stage"]('+repr(header)+','+repr(str(source))+','+repr(str(destination))+')\n')
        return ['/usr/bin/python3','-I','-S','-B','-c',code]
    component.__dict__['local_header_argv']=argv
    component.__dict__['expected_cached_header_receipt']=lambda:expected(source)
    component.__dict__['LOCAL_HEADER_LIMITS']=component.limits(60,40,512,4,8,65536)
    replacements=((b"'flex_header_acquire',\n        header_acquisition_argv(repo, destination, buffers), work, env, HEADER_LIMITS, destination)",b"'local_flex_header_cached',\n        local_header_argv(repo, destination, buffers), work, env, LOCAL_HEADER_LIMITS, destination)"),(b'receipt == expected_header_receipt()',b'receipt == expected_cached_header_receipt()'),(b"'acquisition_usage': acquired['usage']",b"'cached_stage_usage': acquired['usage']"))
    _,proof=adapter.exact_function(g,raw,'qualify_flex_header',component.__dict__,replacements)
    return proof
