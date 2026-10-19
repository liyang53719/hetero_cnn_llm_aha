import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require Python -I -S -B before source read')
import argparse,hashlib,json,os,resource,signal,stat,types
from pathlib import Path
ROOT=Path(__file__).absolute().parent
BOOTSTRAP='candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py'
PINS={'bootstrap.py': (25509, 'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'), 'binding_observer.py': (11781, '62a7f5b4f9250f66e5c62ed9d8b6a486642e135e5e934fc505ae2dfadc850904'), 'local_mount_profile.py': (7087, 'cdbe1030e3bf2a9b2222836f7f594b4800c4315dfb31a4438a8b76c07cd18c8f'), 'local_toolchain_adapter.py': (8776, '5b21cf3d8969873b3d751f52d64dc7e9528edc0a7d68ce3b91d88f65c8ca3896'), 'preset_package_stage.py': (4415, '364647f02226c68a9ba5bbb23b907b19554a72c811af982fd136cebca6c066cf'), 'ci_support_v3.py': (16348, '653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1'), 'SUPPORT_PINS.json': (806, 'c2fd4d03c0dc30226a22992e5cd4d347659409d7625505404bd9b714a20105d2')}
def need(ok):
    if not ok:raise ValueError('fixed same-buffer observer entry rejected')
def read(path,pin):
    size,digest=pin;need(path.is_absolute() and '..' not in path.parts)
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        f=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(f);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==size)
            data=[];count=0
            while count<=size:
                raw=os.read(f,min(65536,size+1-count))
                if not raw:break
                data.append(raw);count+=len(raw)
            raw=b''.join(data);stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            need(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest and stamp(before)==stamp(os.fstat(f))==stamp(os.stat(path.name,dir_fd=fd,follow_symlinks=False)))
            return raw
        finally:os.close(f)
    finally:os.close(fd)
def loaded(path,key):
    raw=read(path,PINS[key]);m=types.ModuleType('_fixed_'+key.replace('.','_'));m.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m
import math,time
p=argparse.ArgumentParser(allow_abbrev=False)
for name in ('repo','binding-source','caller-source','binding','profile','package-root','qualification-root'):p.add_argument('--'+name,type=Path,required=True)
for name in ('binding','profile'):
    p.add_argument('--'+name+'-bytes',type=int,required=True);p.add_argument('--'+name+'-sha',required=True)
p.add_argument('--execute-fixed-qualification',action='store_true')
p.add_argument('--child',choices=('accept','stage','prepare'));p.add_argument('--deadline',type=float)
a=p.parse_args()
need(a.execute_fixed_qualification and type(ENTRY_BYTES) is bytes and len(ENTRY_BYTES)<=32768)
def audit(event,args):
    if event.startswith('socket.') or event=='urllib.Request':raise RuntimeError('network forbidden in fixed preset qualification')
    if a.child and (event.startswith('subprocess.') or event in ('os.system','os.fork','os.forkpty','os.exec','os.posix_spawn','pty.spawn')):raise RuntimeError('native forbidden in data-only child')
sys.addaudithook(audit)
resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(40,40))
resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024**2,4*1024**2))
started=time.monotonic()
if a.deadline is not None:need(math.isfinite(a.deadline) and started<a.deadline<=started+6600)
stop=min(started+480,a.deadline) if a.deadline is not None else started+480
def expired(*args):raise TimeoutError('fixed qualification shared deadline exhausted')
signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,max(0.001,stop-time.monotonic()))
# Select one already-allowed CPU, never expand affinity.
allowed=os.sched_getaffinity(0);need(bool(allowed));os.sched_setaffinity(0,{min(allowed)});need(len(os.sched_getaffinity(0))==1)
g=loaded(a.repo/BOOTSTRAP,'bootstrap.py');o=loaded(a.binding_source/'binding_observer.py','binding_observer.py');l=loaded(a.binding_source/'local_mount_profile.py','local_mount_profile.py')
adapter=loaded(a.caller_source/'local_toolchain_adapter.py','local_toolchain_adapter.py');preset=loaded(ROOT/'preset_package_stage.py','preset_package_stage.py')
bpin={'bytes':a.binding_bytes,'sha256':a.binding_sha};ppin={'bytes':a.profile_bytes,'sha256':a.profile_sha}
braw=read(a.binding,(a.binding_bytes,a.binding_sha));praw=read(a.profile,(a.profile_bytes,a.profile_sha))
b,profile=adapter.checked_inputs(g,o,l,a.repo,braw,bpin,praw,ppin)
q=g.clean(a.qualification_root);dep=g.paths(b)['work'];source=g.clean(a.package_root)
for root in (a.repo,dep,source):need(not q.is_relative_to(root) and not root.is_relative_to(q))
receipt_pin={'bytes':2151,'sha256':'20fbc58f77aa477b7f54c827859b81b089414fb0b93a6df6daf33e9af6fa26a6'}
s=g.load_sources(a.repo);fs=s['fs']
def write(name,value):
    raw=o.canonical(value);need(len(raw)<=256*1024)
    fd=os.open(q/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:need(os.write(fd,raw)==len(raw))
    finally:os.close(fd)
    need(g.checked(q/name,g.pin(raw),256*1024)==raw)
    return g.pin(raw)
def prior(name):
    # These exact files and their pins were written by the same parent run;
    # the child receives their pin map embedded into its checked entry globals.
    need(type(PRIOR_PINS) is dict and name in PRIOR_PINS)
    return g.decode(g.checked(q/name,PRIOR_PINS[name],256*1024))
def exited(phase,name):
    need(type(phase) is dict and set(phase)=={'name','record'} and phase['name']==name)
    need(type(phase['record']['exit_code']) is int and phase['record']['exit_code']==0 and phase['record']['cleanup_confirmed'] is True)
def parent_run():
    need(not os.path.lexists(q) and not os.path.lexists(dep))
    fs.fresh_directory(q)
    for name in ('home','tmp','evidence'):fs.fresh_directory(q/name)
    support_file=a.repo/'candidates/host93_ci_recovery/ci_support_v3.py'
    read(a.repo/'candidates/host93_ci_recovery/SUPPORT_PINS.json',PINS['SUPPORT_PINS.json'])
    supervisor=loaded(support_file,'ci_support_v3.py');support,base,pins=supervisor.fixed_support(a.repo)
    owner={'handler':expired,'deadline':stop};records=[];prior_pins={}
    def callback(name,argv,cwd,environment,limits):
        need(time.monotonic()<stop and len(records)<13)
        record,raw,usage=supervisor.run_phase(support,base,name,argv,cwd,q/'evidence'/name,environment,limits,stop,owner)
        need(type(record['exit_code']) is int and record['exit_code']==0 and record['cleanup_confirmed'] is True)
        records.append({'name':name,'record':record,'usage':usage})
        return {'record':record,'raw_log':raw,'usage':usage}
    env=g.child_environment(b);env['HOME']=str(q/'home');env['TMPDIR']=str(q/'tmp')
    common=['--repo',str(a.repo),'--binding-source',str(a.binding_source),'--caller-source',str(a.caller_source),
            '--binding',str(a.binding),'--binding-bytes',str(a.binding_bytes),'--binding-sha',a.binding_sha,
            '--profile',str(a.profile),'--profile-bytes',str(a.profile_bytes),'--profile-sha',a.profile_sha,
            '--package-root',str(source),'--qualification-root',str(q),'--execute-fixed-qualification','--deadline',repr(stop)]
    for kind,name in (('accept',preset.PHASE),('stage','local_dependencies_stage_preset'),('prepare','local_dependencies_prepare_private')):
        # Child compiles exactly these already-verified entry bytes; prior pin
        # map is data embedded by this parent, not a path-imported helper.
        code='import sys\nraw='+repr(ENTRY_BYTES)+'\nns={"__name__":"__main__","__file__":'+repr(str(Path(__file__).absolute()))+',"ENTRY_BYTES":raw,"PRIOR_PINS":'+repr(prior_pins)+'}\nexec(compile(raw,ns["__file__"],"exec",dont_inherit=True),ns)\n'
        command=['/usr/bin/python3','-I','-S','-B','-c',code]+common+['--child',kind]
        g.system_identities(s,b)
        found=callback(name,command,q,env,g.STAGE_LIMITS)
        value=g.decode(found['raw_log']);prior_pins[kind+'_result.json']=write(kind+'_result.json',value)
        prior_pins[kind+'_phase.json']=write(kind+'_phase.json',{'name':name,'record':found['record']})
    stage_result=g.decode(g.checked(q/'stage_result.json',prior_pins['stage_result.json'],65536))['stage_result']
    component,projection=adapter.bind(g,o,l,a.repo,braw,bpin,praw,ppin,stage_result)
    _,_,buffers=component.load_sources(a.repo)
    qualification=component.qualify_tools(support,component.host_identities(support),buffers,q,callback,component.environment(q))
    component.unchanged_tools(support,component.host_identities(support))
    need(len(records)==13 and time.monotonic()<stop)
    result={'status':'PASS_FIXED_FIVE_TOOL_VERSION_AND_GENERATION_ONLY','qualification':qualification,'records':records,
            'binding':bpin,'profile':ppin,'stage_result':stage_result,'caller_projection':projection,
            'seconds':time.monotonic()-started,'shared_seconds_cap':480,'cpu_affinity_count':1,
            'download_cleanup_inherited':False,'backend_build_started':False,'host_started':False,'network_started':False}
    result_pin=write('RESULT.json',result);return {'status':result['status'],'result':result_pin,'phases':13}

if a.child:
    need(len(os.sched_getaffinity(0))==1 and q.is_dir())
    if a.child=='accept':
        result=preset.accept(g,a.repo,braw,bpin,source,receipt_pin)
    elif a.child=='stage':
        record=prior('accept_phase.json');exited(record,preset.PHASE)
        raw=g.checked(q/'accept_result.json',PRIOR_PINS['accept_result.json'],65536)
        stage_result,proof=preset.stage(g,adapter,a.repo,braw,bpin,record,receipt_pin,raw,PRIOR_PINS['accept_result.json'])
        result={'stage_result':stage_result,'projection':proof}
    else:
        record=prior('stage_phase.json');exited(record,'local_dependencies_stage_preset')
        stage_result=prior('stage_result.json')['stage_result']
        prepared,proof=adapter.prepare(g,o,l,a.repo,braw,bpin,praw,ppin,stage_result)
        result={'prepared':prepared,'projection':proof}
    output=o.canonical(result);need(len(output)<=65536);print(output.decode(),end='')
else:
    print(json.dumps(parent_run(),sort_keys=True))
signal.setitimer(signal.ITIMER_REAL,0)
