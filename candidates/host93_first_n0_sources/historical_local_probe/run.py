"""Four fixed local phases for the original historical N0 reference; no DUT route."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import argparse, hashlib, json, math, os, signal, stat, time, types
from pathlib import Path
HERE=Path(__file__).absolute().parent
PREFIX='candidates/host93_first_n0_sources/historical_local_probe/'
BASE='candidates/host93_ci_recovery/'
REFERENCE='candidates/host93_first_n0_sources/reference/'
RUNTIME=PREFIX+'historical_runtime.py'
PINS_BYTES=5509
PINS_SHA='51eb30938b089b674d754bdbb7dacae19882d17ac615060097b69de3c588e003'
MIB=1024**2;GIB=1024**3
STAGES=('n0_wheels_acquire','n0_runtime_install','n0_raw2_readonly','n0_original_reference')
EVIDENCE=('summary.json','source_hashes.json','stage_exits.json')
BOUNDARIES=('NONE','SOURCE','PATH','DEADLINE','PHASE_ORDER','PHASE_BUDGET','RUNTIME_PREPARE','RUNTIME_TREE','RAW2_RECEIPT','REFERENCE_RECEIPT','REFERENCE_RSS','REFERENCE_OUTPUT','RAW2_CHANGED','SOURCE_CHANGED','NATIVE')
EXCEPTIONS=('NONE','ValueError','TimeoutError','OSError','MemoryError','KeyboardInterrupt','SystemExit','OTHER')
STATUS=('INCOMPLETE','LOCAL_REFERENCE_EXACT_ONLY')
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
    return (load(repo,pins,BASE+'run.py'),load(repo,pins,BASE+'first_n0/pipeline.py'),load(repo,pins,BASE+'ci_support_v3.py'),load(repo,pins,REFERENCE+'n0_reference.py'))

def natural(row,code):
    return row['exit_code']==code and type(row['exit_code']) is int and row['waitid_code']==1 and row['waitid_status']==code and row['receipt_timed_out'] is False and row['cleanup_confirmed'] is True and row['kill_attempted'] is True and row['kill_result'] in ('SIGNAL_SENT_BEFORE_REAP','GROUP_ALREADY_ABSENT') and row['final_reap_signal'] is None and row['native_record_status']==('PASS' if code==0 else 'FAIL')

def allowed_markers(repo,pins,name):
    if name in (STAGES[0],STAGES[2]):return load(repo,pins,PREFIX+'stage_entry.py').SAFE_MARKERS
    if name==STAGES[3]:
        C=load(repo,pins,REFERENCE+'n0_reference.py')
        return {'NOT_COMPLETED:'+x for x in C.CODES}|{'REFERENCE_MISMATCH:HASH_MISMATCH'}
    return set()

def safe_failure(repo,pins,name,p,A):
    result=A.empty_diagnostics('READ_ERROR')
    try:raw=read(p,65536)
    except BaseException:return result
    try:
        allowed=allowed_markers(repo,pins,name);lines=[s for s in raw.decode('ascii',errors='replace').splitlines() if s in allowed]
        result.update(context_state='AVAILABLE',merged_log_tail='\n'.join(lines[-4:]) if lines else 'PRIVATE_PHASE_FAILED:NO_FIXED_STATUS_MARKER')
    except BaseException:result.update(context_state='SANITIZER_ERROR',merged_log_tail='')
    return result

REF_STAGES=('SOURCE','RAW2','RUNTIME_IDENTITY','RUNTIME_IMPORT','OFFICIAL_N0','POSTFLIGHT','COMPLETE')
def validate_reference(value,C):
    need(type(value) is dict and set(value)=={'status','code','stage','python_profile','expected_capability','observed_capability','native_exact_reported','fp32le_exact_reported','worker_accepted'})
    need(value['status'] in ('NOT_COMPLETED','REFERENCE_MISMATCH','PASS_FROZEN_N0_EXACT') and value['stage'] in REF_STAGES and value['python_profile']=='historical' and value['expected_capability']=='AVX512' and value['observed_capability'] in ('DEFAULT','AVX2','AVX512','OTHER','UNKNOWN'))
    need(all(type(value[k]) is bool for k in ('native_exact_reported','fp32le_exact_reported','worker_accepted')))
    passed=value['status']=='PASS_FROZEN_N0_EXACT'
    need((value['code'] is None if passed else value['code'] in C.CODES) and value['worker_accepted']==passed and (value['stage']=='COMPLETE')==passed)
    if passed:need(value['observed_capability']=='AVX512' and value['native_exact_reported'] and value['fp32le_exact_reported'])
    if value['status']=='REFERENCE_MISMATCH':need(value['code']=='HASH_MISMATCH' and value['stage']=='POSTFLIGHT' and not(value['native_exact_reported'] and value['fp32le_exact_reported']))
    return True

def project_receipt(report,refpins,C):
    need(type(report) is dict and type(report.get('schema')) is int and report['schema']==1 and report.get('scope')=='FROZEN_M128_N0_REFERENCE_ONLY' and report.get('rtl_executed') is False and report.get('fullblock_executed') is False)
    need(type(report.get('reference_accepted')) is bool)
    runtime=report.get('observed_runtime');observed='UNKNOWN'
    if runtime is not None:
        need(type(runtime) is dict)
        if 'capability' in runtime:
            v=runtime['capability'];observed=v if type(v) is str and v in ('DEFAULT','AVX2','AVX512') else 'OTHER'
    output=report.get('output');native=False;fp32=False
    if output is not None:
        need(type(output) is dict and set(output)=={'native','fp32le','native_exact','fp32le_exact','accepted'})
        need(all(type(output[k]) is bool for k in ('native_exact','fp32le_exact','accepted')))
        native=output['native_exact'];fp32=output['fp32le_exact']
        need(output['accepted']==(native and fp32))
        if native:need(output['native']=={'bytes':C.BF16_BYTES,'sha256':C.BF16_SHA256})
        if fp32:need(output['fp32le']=={'bytes':C.F32_BYTES,'sha256':C.F32_SHA256})
    result={'status':report.get('status'),'code':report.get('code'),'stage':report.get('stage'),'python_profile':'historical','expected_capability':'AVX512','observed_capability':observed,'native_exact_reported':native,'fp32le_exact_reported':fp32,'worker_accepted':report['reference_accepted']}
    validate_reference(result,C)
    if result['worker_accepted']:
        need(report.get('python_profile')=='historical' and report.get('source_identities')==refpins['sources'] and report.get('input_identities')==refpins['raw2'] and report.get('runtime_requirements')==refpins['runtime_requirements'])
        before=report.get('runtime_before');after=report.get('runtime_after')
        expected={k:{a:v[a] for a in ('bytes','sha256')} for k,v in refpins['runtime_native_files'].items() if k!='python'}
        expected['python']={k:refpins['python_profiles']['historical'][k] for k in ('bytes','sha256')}
        need(before==after==expected)
    return result

def validate(objects,repo,pins,A,C):
    need(type(objects) is dict and set(objects)==set(EVIDENCE));s,h,e=(objects[n] for n in EVIDENCE)
    need(type(s) is dict and set(s)=={'schema','status','seconds','contract_failure','observation_state','reference','sampled_rss','scope'})
    need(s['schema']=='n0-historical-local-summary-v1' and s['status'] in STATUS and finite(s['seconds']) and s['seconds']<=720)
    need(s['scope']=={'local_reference_qualified':s['status']=='LOCAL_REFERENCE_EXACT_ONLY','baseline_adopted':False,'dut_executed':False,'fullblock_executed':False})
    need(all(type(x) is bool for x in s['scope'].values()))
    f=s['contract_failure'];need(type(f) is dict and set(f)=={'boundary','exception_type'} and f['boundary'] in BOUNDARIES and f['exception_type'] in EXCEPTIONS and (f['boundary']=='NONE')==(f['exception_type']=='NONE'))
    need(type(h) is dict and set(h)=={'schema','files'} and h['schema']=='n0-historical-local-sources-v1' and h['files']==pins)
    need(type(e) is dict and set(e)=={'schema','stages'} and e['schema']=='n0-historical-local-stage-exits-v1' and type(e['stages']) is list and len(e['stages'])<=4)
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
        validate_reference(s['reference'],C);need(len(rows)==4 and all(natural(r,0) and r['status']=='EXIT0_CLEANED' for r in rows[:3]))
    else:need(s['reference'] is None)
    if len(rows)<4:need(state=='NOT_COLLECTED' and s['sampled_rss'] is None)
    rss=s['sampled_rss']
    if rss is not None:need(type(rss) is dict and set(rss)=={'sampled_leader_max_kib','limit_kib','os_hard_limit','includes_descendants'} and type(rss['sampled_leader_max_kib']) is int and 0<=rss['sampled_leader_max_kib']<=1572864 and rss['limit_kib']==1572864 and rss['os_hard_limit'] is False and rss['includes_descendants'] is False and len(rows)==4)
    b=f['boundary'];clean=lambda:all(r['status']=='EXIT0_CLEANED' and natural(r,0) for r in rows)
    if b=='NATIVE':need(bool(rows) and rows[-1]['status']=='FAILED')
    if b=='RUNTIME_PREPARE':need(len(rows) in (0,1) and clean())
    if b=='RUNTIME_TREE':need(len(rows)==2 and clean())
    if b=='RAW2_RECEIPT':need(len(rows)==3 and clean())
    if b in ('REFERENCE_RECEIPT','REFERENCE_RSS','REFERENCE_OUTPUT','RAW2_CHANGED'):need(len(rows)==4 and clean())
    if b in ('REFERENCE_RSS','REFERENCE_OUTPUT','RAW2_CHANGED'):need(state=='AVAILABLE')
    if b=='SOURCE_CHANGED':need(len(rows)==4 and clean() and state=='AVAILABLE' and s['reference']['status']=='PASS_FROZEN_N0_EXACT')
    if b in ('PHASE_ORDER','PHASE_BUDGET','DEADLINE'):need(clean())
    if b in ('SOURCE','PATH'):need(not rows)
    if s['status']=='LOCAL_REFERENCE_EXACT_ONLY':need(state=='AVAILABLE' and s['reference']['status']=='PASS_FROZEN_N0_EXACT' and all(r['status']=='EXIT0_CLEANED' and natural(r,0) for r in rows) and len(rows)==4 and rss is not None and f['boundary']=='NONE')
    else:need(f['boundary']!='NONE')
    return True

def save(p,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();need(len(raw)<=131072)
    with p.open('xb') as f:need(f.write(raw)==len(raw))

def execute(repo,out,deadline,embedding,gamma):
    started=time.monotonic();need(type(deadline) is float and math.isfinite(deadline) and started<deadline<=started+600)
    repo=plain(repo);out=plain(out);need(repo.is_dir() and out.parent.is_dir() and not os.path.lexists(out) and not out.is_relative_to(repo) and not repo.is_relative_to(out))
    pins=source_map(repo);A,P,S,C=modules(repo,pins);S.deadline_ready();base,plan,_=S.fixed_support(repo)
    stop=deadline-5;need(stop>started);oldmask=os.umask(0o077);olda=signal.signal(signal.SIGALRM,S.interrupted);oldt=signal.signal(signal.SIGTERM,S.interrupted);signal.setitimer(signal.ITIMER_REAL,stop-time.monotonic());owner={'handler':S.interrupted,'deadline':stop}
    rows=[];boundary='PATH';error=None;state='NOT_COLLECTED';reference=None;rss=None;status='INCOMPLETE'
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
        phase(STAGES[0],P.argv(repo,pins,PREFIX+'stage_entry.py',['--stage','wheels','--repo',repo,'--out',out/'wheels','--deadline',min(wheel_stop,time.monotonic()+180),'--execute']),P.native_environment(out,True),P.limits(180,165,120,512*MIB,256*MIB),wheel_stop)
        boundary='RUNTIME_PREPARE';command=runtime.install_argv(repo/REFERENCE,out/'wheels',out/'runtime')
        phase(STAGES[1],command,P.native_environment(out),P.limits(120,100,90,2*GIB,GIB),wheel_stop)
        boundary='RUNTIME_TREE';runtime.observe_installed_tree(out/'runtime',out/'wheels')
        phase(STAGES[2],P.argv(repo,pins,PREFIX+'stage_entry.py',['--stage','raw2','--repo',repo,'--out',out/'raw2','--embedding',embedding,'--gamma',gamma,'--deadline',min(stop,time.monotonic()+30),'--execute']),P.native_environment(out),P.limits(30,10,10,256*MIB,4*MIB),stop)
        boundary='RAW2_RECEIPT';entry=load(repo,pins,PREFIX+'stage_entry.py');raw2=entry.raw2_receipt(repo,embedding,gamma);need(decode(read(out/'raw2'/'RECEIPT.json',16384))==raw2)
        child_error=None
        try:phase(STAGES[3],P.argv(repo,pins,REFERENCE+'n0_reference.py',['--repo',repo,'--embedding',embedding,'--gamma',gamma,'--runtime-root',out/'runtime','--python',Path(sys.executable).resolve(),'--python-profile','historical','--out',out/'reference','--pins',repo/REFERENCE/'PINS.json','--shared-stop',min(stop,time.monotonic()+120),'--execute']),P.native_environment(out,numeric=True),P.limits(120,100,90,8*GIB,4*MIB),stop)
        except BaseException as e:child_error=e
        if len(rows)!=4:
            if child_error is not None:raise child_error
            boundary='PHASE_ORDER';need(False)
        try:
            boundary='REFERENCE_RECEIPT';state='READ_ERROR';raw=read(out/'reference'/'RECEIPT.json',65536);state='SANITIZER_ERROR';refpins=C.load_pins(repo/REFERENCE/'PINS.json');reference=project_receipt(decode(raw),refpins,C);state='AVAILABLE'
            boundary='REFERENCE_RSS';rss=P.rss_observation(out/'phases'/STAGES[3])
        except BaseException:
            reference=None if state!='AVAILABLE' else reference
            if child_error is not None:boundary='NATIVE';raise child_error
            raise
        if child_error is not None:boundary='NATIVE';raise child_error
        boundary='REFERENCE_RECEIPT';need(reference['status']=='PASS_FROZEN_N0_EXACT' and natural(rows[-1],0))
        boundary='REFERENCE_OUTPUT';read(out/'reference'/'n0.f32le',C.F32_BYTES,{'bytes':C.F32_BYTES,'sha256':C.F32_SHA256})
        boundary='RAW2_CHANGED';need(entry.raw2_receipt(repo,embedding,gamma)==raw2)
        boundary='SOURCE_CHANGED';need(source_map(repo)==pins)
        status='LOCAL_REFERENCE_EXACT_ONLY'
    except BaseException as e:error=e
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,olda);signal.signal(signal.SIGTERM,oldt);os.umask(oldmask)
    if error is not None:
        if status=='LOCAL_REFERENCE_EXACT_ONLY':status='INCOMPLETE'
        kind=type(error).__name__;kind=kind if kind in EXCEPTIONS else 'OTHER'
    else:kind='NONE';boundary='NONE'
    summary={'schema':'n0-historical-local-summary-v1','status':status,'seconds':round(time.monotonic()-started,6),'contract_failure':{'boundary':boundary,'exception_type':kind},'observation_state':state,'reference':reference,'sampled_rss':rss,'scope':{'local_reference_qualified':status=='LOCAL_REFERENCE_EXACT_ONLY','baseline_adopted':False,'dut_executed':False,'fullblock_executed':False}}
    objects={'summary.json':summary,'source_hashes.json':{'schema':'n0-historical-local-sources-v1','files':pins},'stage_exits.json':{'schema':'n0-historical-local-stage-exits-v1','stages':rows}}
    validate(objects,repo,pins,A,C);evidence=out/'evidence';evidence.mkdir(mode=0o700)
    for name,value in objects.items():save(evidence/name,value)
    print(json.dumps({'status':status,'stages':len(rows)},sort_keys=True));return 0 if error is None else 1

def verify(out,repo):
    pins=source_map(repo);A,P,S,C=modules(repo,pins);objects={n:decode(read(plain(out)/'evidence'/n,131072)) for n in EVIDENCE};validate(objects,repo,pins,A,C);print('SAFE_DIAGNOSTIC_EVIDENCE_ONLY');return 0

def main(argv=None):
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--repo',type=Path,default=HERE.parents[2]);ap.add_argument('--out',type=Path);ap.add_argument('--deadline',type=float);ap.add_argument('--embedding',type=Path);ap.add_argument('--gamma',type=Path);ap.add_argument('--execute',action='store_true');ap.add_argument('--verify-evidence',action='store_true');a=ap.parse_args(argv)
    if a.verify_evidence:need(not a.execute and a.out is not None);return verify(a.out,a.repo)
    if not a.execute:source_map(a.repo);print('N0_HISTORICAL_LOCAL_SOURCE_ONLY');return 0
    need(a.out is not None and a.deadline is not None and a.embedding is not None and a.gamma is not None);return execute(a.repo,a.out,a.deadline,a.embedding,a.gamma)
if __name__=='__main__':raise SystemExit(main())
