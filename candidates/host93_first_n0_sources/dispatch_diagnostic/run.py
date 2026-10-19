"""Four fixed phases for an independent N0 dispatch diagnostic; never a DUT route."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import argparse, hashlib, json, math, os, signal, stat, time, types
from pathlib import Path
HERE=Path(__file__).absolute().parent
PREFIX='candidates/host93_first_n0_sources/dispatch_diagnostic/'
BASE='candidates/host93_ci_recovery/'
REFERENCE='candidates/host93_first_n0_sources/reference/'
RUNTIME='candidates/host93_first_n0_sources/runtime/runtime_wheel_gate.py'
PINS_BYTES=5868
PINS_SHA='45342749d1cdd561ae7733d64a13008566477f2bf42471a6fab1342c83a591d6'
MIB=1024**2;GIB=1024**3
STAGES=('n0_wheels_acquire','n0_runtime_install','n0_raw2_acquire','n0_dispatch_candidate')
EVIDENCE=('summary.json','source_hashes.json','stage_exits.json')
BOUNDARIES=('NONE','SOURCE','PATH','DEADLINE','PHASE_ORDER','PHASE_BUDGET','RUNTIME_PREPARE','RUNTIME_TREE','RAW2_RECEIPT','CANDIDATE_RECEIPT','CANDIDATE_RSS','SOURCE_CHANGED','NATIVE')
EXCEPTIONS=('NONE','ValueError','TimeoutError','OSError','MemoryError','KeyboardInterrupt','SystemExit','OTHER')
STATUS=('INCOMPLETE','CANDIDATE_EXACT_MATCH_ONLY','CANDIDATE_HASH_MISMATCH_ONLY')
class Rejected(ValueError):pass
def need(ok):
    if not ok:raise Rejected('FIXED_CONTRACT')
def finite(x):return type(x) in (int,float) and math.isfinite(x) and x>=0

def plain(p):
    p=Path(p);need(p.is_absolute() and '..' not in p.parts and all(not x.is_symlink() for x in (p,*p.parents)));return p

def read(p,cap,pin=None):
    p=plain(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and 0<=a.st_size<=cap);raw=f.read(cap+1);z=os.fstat(f.fileno())
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    need(len(raw)==a.st_size and stamp(a)==stamp(z)==stamp(p.stat(follow_symlinks=False)))
    if pin is not None:need(identity(raw)==pin)
    return raw

def identity(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:need(k not in d);d[k]=v
        return d
    def invalid(_):raise Rejected('JSON_NONFINITE')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
def load(repo,pins,name):
    p=pins[name];raw=read(repo/name,p['bytes'],p);m=types.ModuleType('_diagnostic_'+p['sha256'][:16]);m.__file__=str(repo/name);sys.modules[m.__name__]=m;exec(compile(raw,m.__file__,'exec',dont_inherit=True),m.__dict__);return m

def source_map(repo):
    doc=decode(read(HERE/'SOURCE_PINS.json',PINS_BYTES,{'bytes':PINS_BYTES,'sha256':PINS_SHA}));need(type(doc) is dict and set(doc)=={'schema','files'} and doc['schema']==1)
    pins=doc['files'];need(type(pins) is dict and 1<=len(pins)<=80)
    for name,p in pins.items():
        need(type(name) is str and not name.startswith('/') and '..' not in name.split('/') and type(p) is dict and set(p)=={'bytes','sha256'})
        read(repo/name,p['bytes'],p)
    pins=dict(pins);pins[PREFIX+'run.py']=identity(read(HERE/'run.py',65536));return pins

def modules(repo,pins):
    return (load(repo,pins,BASE+'run.py'),load(repo,pins,BASE+'first_n0/pipeline.py'),load(repo,pins,BASE+'ci_support_v3.py'),load(repo,pins,PREFIX+'n0_dispatch_candidate.py'))

def natural(row,code):
    return row['exit_code']==code and type(row['exit_code']) is int and row['waitid_code']==1 and row['waitid_status']==code and row['receipt_timed_out'] is False and row['cleanup_confirmed'] is True and row['kill_attempted'] is True and row['kill_result'] in ('SIGNAL_SENT_BEFORE_REAP','GROUP_ALREADY_ABSENT') and row['final_reap_signal'] is None and row['native_record_status']==('PASS' if code==0 else 'FAIL')

def safe_failure(repo,pins,name,p,A):
    result=A.empty_diagnostics('READ_ERROR')
    try:raw=read(p,65536)
    except BaseException:return result
    try:
        if name=='n0_wheels_acquire':allowed=load(repo,pins,BASE+'first_n0/pipeline.py').fixed_markers(repo,pins,name)
        elif name=='n0_raw2_acquire':allowed=load(repo,pins,PREFIX+'raw2_adapter.py').SAFE_MARKERS
        elif name=='n0_dispatch_candidate':allowed=load(repo,pins,PREFIX+'n0_dispatch_candidate.py').SAFE_MARKERS
        else:allowed=set()
        lines=[s for s in raw.decode('ascii',errors='replace').splitlines() if s in allowed]
        result.update(context_state='AVAILABLE',merged_log_tail='\n'.join(lines[-4:]) if lines else 'PRIVATE_PHASE_FAILED:NO_FIXED_STATUS_MARKER')
    except BaseException:result.update(context_state='SANITIZER_ERROR',merged_log_tail='')
    return result

def allowed_markers(repo,pins,name):
    if name=='n0_wheels_acquire':return load(repo,pins,BASE+'first_n0/pipeline.py').fixed_markers(repo,pins,name)
    if name=='n0_raw2_acquire':return load(repo,pins,PREFIX+'raw2_adapter.py').SAFE_MARKERS
    if name=='n0_dispatch_candidate':return load(repo,pins,PREFIX+'n0_dispatch_candidate.py').SAFE_MARKERS
    return set()

def validate(objects,repo,pins,A,C):
    need(type(objects) is dict and set(objects)==set(EVIDENCE));s,h,e=(objects[n] for n in EVIDENCE)
    need(type(s) is dict and set(s)=={'schema','status','seconds','contract_failure','observation_state','candidate','sampled_rss','scope'})
    need(s['schema']=='n0-dispatch-summary-v1' and s['status'] in STATUS and finite(s['seconds']) and s['seconds']<=720)
    need(s['scope']=={'baseline_adopted':False,'reference_accepted':False,'dut_executed':False,'fullblock_executed':False})
    need(all(type(x) is bool for x in s['scope'].values()))
    f=s['contract_failure'];need(type(f) is dict and set(f)=={'boundary','exception_type'} and f['boundary'] in BOUNDARIES and f['exception_type'] in EXCEPTIONS and (f['boundary']=='NONE')==(f['exception_type']=='NONE'))
    need(type(h) is dict and set(h)=={'schema','files'} and h['schema']=='n0-dispatch-sources-v1' and h['files']==pins)
    need(type(e) is dict and set(e)=={'schema','stages'} and e['schema']=='n0-dispatch-stage-exits-v1' and type(e['stages']) is list and len(e['stages'])<=4)
    rows=e['stages'];need([r.get('name') for r in rows]==list(STAGES[:len(rows)]))
    for i,r in enumerate(rows):
        need(set(r)==set(A.OBSERVATION_KEYS)|{'name','status','seconds','diagnostics'});A.validate_observation(r)
        need(r['status'] in ('EXIT0_CLEANED','FAILED') and finite(r['seconds']) and r['seconds']<=600)
        if r['status']=='EXIT0_CLEANED':need(natural(r,0) and r['failure_boundary']=='NONE' and r['failure_code']=='NONE' and r['diagnostics']==A.empty_diagnostics())
        else:
            need(i==len(rows)-1)
            d=r['diagnostics'];need(d['observations']==[] and d['truncated'] is False)
            if d['context_state']=='AVAILABLE':need(0<len(d['merged_log_tail'].splitlines())<=4 and all(x in allowed_markers(repo,pins,r['name'])|{'PRIVATE_PHASE_FAILED:NO_FIXED_STATUS_MARKER'} for x in d['merged_log_tail'].splitlines()))
    state=s['observation_state'];need(state in ('NOT_COLLECTED','AVAILABLE','READ_ERROR','SANITIZER_ERROR'))
    if state=='AVAILABLE':
        C.validate_public_observation(s['candidate']);need(len(rows)==4 and all(natural(r,0) and r['status']=='EXIT0_CLEANED' for r in rows[:3]))
        need(natural(rows[-1],0 if s['candidate']['status']=='CANDIDATE_EXACT_MATCH' else 1))
    else:need(s['candidate'] is None)
    if len(rows)<4:need(state=='NOT_COLLECTED' and s['sampled_rss'] is None)
    rss=s['sampled_rss']
    if rss is not None:need(type(rss) is dict and set(rss)=={'sampled_leader_max_kib','limit_kib','os_hard_limit','includes_descendants'} and type(rss['sampled_leader_max_kib']) is int and 0<=rss['sampled_leader_max_kib']<=1572864 and rss['limit_kib']==1572864 and rss['os_hard_limit'] is False and rss['includes_descendants'] is False and len(rows)==4)
    b=f['boundary'];clean=lambda:all(r['status']=='EXIT0_CLEANED' and natural(r,0) for r in rows)
    if b=='NATIVE':need(bool(rows) and rows[-1]['status']=='FAILED')
    if b=='RUNTIME_PREPARE':need(len(rows) in (0,1) and clean())
    if b=='RUNTIME_TREE':need(len(rows)==2 and clean())
    if b=='RAW2_RECEIPT':need(len(rows)==3 and clean())
    if b in ('CANDIDATE_RECEIPT','CANDIDATE_RSS'):need(len(rows)==4 and all(r['status']=='EXIT0_CLEANED' for r in rows[:3]))
    if b=='CANDIDATE_RSS':need(state=='AVAILABLE')
    if b=='SOURCE_CHANGED':need(len(rows)==4 and clean() and state=='AVAILABLE' and s['candidate']['status']=='CANDIDATE_EXACT_MATCH')
    if b in ('PHASE_ORDER','PHASE_BUDGET','DEADLINE'):need(clean())
    if b in ('SOURCE','PATH'):need(not rows)
    if s['status']=='CANDIDATE_EXACT_MATCH_ONLY':need(state=='AVAILABLE' and s['candidate']['status']=='CANDIDATE_EXACT_MATCH' and all(r['status']=='EXIT0_CLEANED' for r in rows) and len(rows)==4 and rss is not None and f['boundary']=='NONE')
    elif s['status']=='CANDIDATE_HASH_MISMATCH_ONLY':need(state=='AVAILABLE' and s['candidate']['status']=='CANDIDATE_HASH_MISMATCH' and rows[-1]['status']=='FAILED' and natural(rows[-1],1) and rss is not None and f['boundary']=='NATIVE')
    else:need(f['boundary']!='NONE')
    return True

def save(p,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();need(len(raw)<=131072)
    with p.open('xb') as f:need(f.write(raw)==len(raw))

def execute(repo,out,deadline):
    started=time.monotonic();need(os.environ.get('GITHUB_ACTIONS')=='true' and type(deadline) is float and math.isfinite(deadline) and started<deadline<=started+600)
    repo=plain(repo);out=plain(out);need(repo.is_dir() and out.parent.is_dir() and not os.path.lexists(out) and not out.is_relative_to(repo) and not repo.is_relative_to(out))
    pins=source_map(repo);A,P,S,C=modules(repo,pins);S.deadline_ready();base,plan,_=S.fixed_support(repo)
    stop=deadline-5;need(stop>started);oldmask=os.umask(0o077);olda=signal.signal(signal.SIGALRM,S.interrupted);oldt=signal.signal(signal.SIGTERM,S.interrupted);signal.setitimer(signal.ITIMER_REAL,stop-time.monotonic());owner={'handler':S.interrupted,'deadline':stop}
    rows=[];boundary='PATH';error=None;state='NOT_COLLECTED';candidate=None;rss=None;status='INCOMPLETE'
    try:
        out.mkdir(mode=0o700)
        for x in ('home','tmp','phases'):(out/x).mkdir(mode=0o700)
        def phase(name,command,environment,bound,phase_stop):
            nonlocal boundary
            boundary='PHASE_ORDER';need(name==STAGES[len(rows)]);boundary='DEADLINE';need(time.monotonic()<stop-15)
            boundary='PHASE_BUDGET';bound=P.cap_deadline(bound,min(stop,phase_stop));row={'name':name,'status':'FAILED','seconds':0.0,'diagnostics':A.empty_diagnostics(),**S.diagnostic_defaults()};rows.append(row);began=time.monotonic();diag={}
            print(json.dumps({'phase':name,'status':'START'},sort_keys=True),flush=True);boundary='NATIVE'
            try:
                rec,raw,usage=S.run_phase(base,plan,name,command,out,out/'phases'/name,environment,bound,stop,owner,diagnostics=diag);row.update(diag);row.update(status='EXIT0_CLEANED');return rec
            except BaseException:
                row.update(diag);row['diagnostics']=safe_failure(repo,pins,name,out/'phases'/name/'native.log',A);raise
            finally:row['seconds']=round(time.monotonic()-began,6);print(json.dumps({'phase':name,'status':row['status'],'seconds':row['seconds']},sort_keys=True),flush=True)
        boundary='RUNTIME_PREPARE';runtime=load(repo,pins,RUNTIME);runtime.source_preflight(repo/REFERENCE);runtime.require_current_python();wheel_stop=min(stop,time.monotonic()+300)
        phase(STAGES[0],P.argv(repo,pins,BASE+'first_n0/stage_entry.py',['--stage','wheels','--repo',repo,'--out',out/'wheels','--deadline',min(wheel_stop,time.monotonic()+180),'--execute']),P.native_environment(out,True),P.limits(180,165,120,512*MIB,256*MIB),wheel_stop)
        boundary='RUNTIME_PREPARE';command=runtime.install_argv(repo/REFERENCE,out/'wheels',out/'runtime')
        phase(STAGES[1],command,P.native_environment(out),P.limits(120,100,90,2*GIB,GIB),wheel_stop)
        boundary='RUNTIME_TREE';runtime.observe_installed_tree(out/'runtime',out/'wheels')
        phase(STAGES[2],P.argv(repo,pins,PREFIX+'raw2_adapter.py',['--repo',repo,'--out',out/'raw2','--deadline',min(stop,time.monotonic()+180),'--execute']),P.native_environment(out,True),P.limits(180,165,90,512*MIB,4*MIB),stop)
        boundary='RAW2_RECEIPT';raw2=load(repo,pins,PREFIX+'raw2_adapter.py');raw2.verify_receipt(out/'raw2')
        child_error=None
        try:phase(STAGES[3],P.argv(repo,pins,PREFIX+'n0_dispatch_candidate.py',['--repo',repo,'--embedding',out/'raw2'/'tensors'/'embed_tokens.rows_0_255.bin','--gamma',out/'raw2'/'tensors'/'input_layernorm.weight.bin','--runtime-root',out/'runtime','--python',Path(sys.executable).resolve(),'--python-profile','ci31214','--out',out/'candidate','--pins',repo/REFERENCE/'PINS.json','--shared-stop',min(stop,time.monotonic()+120),'--execute']),P.native_environment(out,numeric=True),P.limits(120,100,90,8*GIB,4*MIB),stop)
        except BaseException as e:child_error=e
        if len(rows)!=4:
            if child_error is not None:raise child_error
            boundary='PHASE_ORDER';need(False)
        try:
            boundary='CANDIDATE_RECEIPT';state='READ_ERROR';raw=read(out/'candidate'/'PUBLIC_OBSERVATION.json',16384);state='SANITIZER_ERROR';candidate=decode(raw);C.validate_public_observation(candidate)
            need(natural(rows[-1],0 if candidate['status']=='CANDIDATE_EXACT_MATCH' else 1));state='AVAILABLE'
            boundary='CANDIDATE_RSS';rss=P.rss_observation(out/'phases'/STAGES[3])
        except BaseException:
            candidate=None if state!='AVAILABLE' else candidate
            if child_error is not None:raise child_error
            raise
        if child_error is not None:
            boundary='NATIVE'
            if candidate['status']=='CANDIDATE_HASH_MISMATCH':status='CANDIDATE_HASH_MISMATCH_ONLY'
            raise child_error
        boundary='CANDIDATE_RECEIPT';need(candidate['status']=='CANDIDATE_EXACT_MATCH')
        boundary='SOURCE_CHANGED';need(source_map(repo)==pins)
        status='CANDIDATE_EXACT_MATCH_ONLY'
    except BaseException as e:error=e
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,olda);signal.signal(signal.SIGTERM,oldt);os.umask(oldmask)
    if error is not None:
        if status=='CANDIDATE_EXACT_MATCH_ONLY':status='INCOMPLETE'
        kind=type(error).__name__;kind=kind if kind in EXCEPTIONS else 'OTHER'
    else:kind='NONE';boundary='NONE'
    summary={'schema':'n0-dispatch-summary-v1','status':status,'seconds':round(time.monotonic()-started,6),'contract_failure':{'boundary':boundary,'exception_type':kind},'observation_state':state,'candidate':candidate,'sampled_rss':rss,'scope':{'baseline_adopted':False,'reference_accepted':False,'dut_executed':False,'fullblock_executed':False}}
    objects={'summary.json':summary,'source_hashes.json':{'schema':'n0-dispatch-sources-v1','files':pins},'stage_exits.json':{'schema':'n0-dispatch-stage-exits-v1','stages':rows}}
    validate(objects,repo,pins,A,C);evidence=out/'evidence';evidence.mkdir(mode=0o700)
    for name,value in objects.items():save(evidence/name,value)
    print(json.dumps({'status':status,'stages':len(rows)},sort_keys=True));return 0 if error is None else 1

def verify(out,repo):
    pins=source_map(repo);A,P,S,C=modules(repo,pins);objects={n:decode(read(plain(out)/'evidence'/n,131072)) for n in EVIDENCE};validate(objects,repo,pins,A,C);print('SAFE_DIAGNOSTIC_EVIDENCE_ONLY');return 0

def main(argv=None):
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--repo',type=Path,default=HERE.parents[2]);ap.add_argument('--out',type=Path);ap.add_argument('--deadline',type=float);ap.add_argument('--execute',action='store_true');ap.add_argument('--verify-evidence',action='store_true');a=ap.parse_args(argv)
    if a.verify_evidence:need(not a.execute and a.out is not None);return verify(a.out,a.repo)
    if not a.execute:source_map(a.repo);print('N0_DISPATCH_SOURCE_ONLY');return 0
    need(a.out is not None and a.deadline is not None);return execute(a.repo,a.out,a.deadline)
if __name__=='__main__':raise SystemExit(main())
