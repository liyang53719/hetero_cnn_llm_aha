"""Pure synthetic sampler/real-dispatcher and exact diagnostic-scope controls.
No DUT import, model library, native call, old capture, runtime hash, or job.
"""
import argparse
import ast
import builtins
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import threading
import time
import types

HERE=Path(__file__).resolve().parent


def need(ok,msg):
    if not ok:raise AssertionError(msg)


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);args=p.parse_args()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(256<<20,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(10,)*2)
    start=time.monotonic();denied=[];cases=[]
    def audit(event,args):
        if event.startswith(('ctypes.','socket.','subprocess.')) or event in ('os.system','os.fork','os.posix_spawn'):
            denied.append(event);raise RuntimeError('forbidden pure synthetic action')
        if event=='import' and args[0].split('.')[0] in ('numpy','torch','candidates','integration','observation'):
            denied.append(event);raise RuntimeError('forbidden DUT import')
    sys.addaudithook(audit)
    manifest=json.loads((HERE/'SOURCE_MANIFEST.json').read_bytes())
    def load(name):
        raw=(HERE/(name+'.py')).read_bytes();pin=manifest['files'][name+'.py']
        need(pin==dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),'exact source bytes')
        m=types.ModuleType(name);m.__file__=str(HERE/(name+'.py'));sys.modules[name]=m
        exec(compile(raw,m.__file__,'exec',dont_inherit=True),vars(m));return m
    def check(name,fn):fn();cases.append(name)
    def rejects(fn,typ=RuntimeError):
        try:fn()
        except typ:return
        raise AssertionError('required rejection')
    sampler=load('loop_sampler');a=load('m2_authority');gate=load('m2_supervision_gate')
    # Use original full-compile class CodeType, not a rewritten dispatcher.
    base=Path(args.base);bm=json.loads((base/'SOURCE_MANIFEST.json').read_bytes())
    path=HERE/'cached_wholeblock.py';raw=path.read_bytes()
    need(manifest['files']['cached_wholeblock.py']==dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),'dispatcher pin')
    whole=compile(raw,str(path),'exec',dont_inherit=True)
    code=next(c for c in whole.co_consts if type(c) is types.CodeType and c.co_name=='TraceDispatcher')
    namespace=dict(__name__='synthetic_original_dispatcher',need=need,sys=sys,threading=threading,types=types)
    Dispatcher=builtins.__build_class__(types.FunctionType(code,namespace),'TraceDispatcher')
    def leaf():
        v=1
        for i in range(12000):v=(v+i)&65535
        return v
    marker=ValueError('synthetic original exception')
    def op(value):
        if value<0:raise marker
        return value+1
    def experiment(sample):
        first=[];second=[];errors=[]
        def one(frame,event,arg):
            first.append((event,arg if event=='return' else type(arg[1]).__name__ if event=='exception' else None))
            leaf()
        def two(frame,event,arg):second.append((event,frame.f_code.co_name))
        d=Dispatcher([op.__code__],max_listeners=2,on_error=errors.append)
        d.register(one,[op.__code__]);d.register(two,[op.__code__]);d.start()
        s=sampler.LoopSampler() if sample else None
        before_trace=sys.gettrace()
        if s:s.start()
        try:
            values=[op(i) for i in range(180)]
            try:op(-1)
            except ValueError as e:need(e is marker,'original exception identity')
        finally:
            if s:s.stop()
            need(sys.gettrace() is before_trace,'sampler changed dispatcher')
            d.stop()
        need(not errors and not d._resume_lines,'original dispatcher poison/resume clean')
        return first,second,values,s
    normal=experiment(False);sampled=experiment(True);report=sampled[3].report()
    check('real original dispatcher two-subscriber events and values unchanged',lambda:need(normal[:3]==sampled[:3],'events/values drift'))
    check('SIGPROF sees real callback internals',lambda:need(any(c['qualname'].endswith('leaf') for c in report['code_table']),'no callback sample'))
    check('naturally stopped bounded sampler',lambda:need(report['status'] in ('PASS_BOUNDED_MAIN_LOOP_SAMPLING','INCOMPLETE_SAMPLING') and report['restored'] and not report['active'],'sampler incomplete'))
    check('sample accounting complete',lambda:need(sum(x['count'] for x in report['stacks'])==report['samples'],'accounting'))
    check('second stop refused',lambda:rejects(sampled[3].stop))
    check('second start refused',lambda:rejects(sampled[3].start))
    check('report before stop refused',lambda:rejects(sampler.LoopSampler().report))
    original=signal.getsignal(signal.SIGPROF)
    def old_prof(*_):return None
    signal.signal(signal.SIGPROF,old_prof)
    try:
        signal.setitimer(signal.ITIMER_PROF,1,1)
        check('active PROF rejected without overwrite',lambda:rejects(sampler.LoopSampler().start))
        need(signal.getitimer(signal.ITIMER_PROF)[1]==1 and signal.getsignal(signal.SIGPROF) is old_prof,'active prior profiler altered')
        signal.setitimer(signal.ITIMER_PROF,0)
        mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGPROF})
        try:
            check('blocked PROF rejected without unblocking',lambda:rejects(sampler.LoopSampler().start))
            os.kill(os.getpid(),signal.SIGPROF)
            check('pending PROF preserved on refused start',lambda:need(signal.SIGPROF in signal.sigpending(),'pending vanished'))
            signal.sigtimedwait({signal.SIGPROF},0)
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,mask)
        s=sampler.LoopSampler();s.start()
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGPROF});os.kill(os.getpid(),signal.SIGPROF)
        s.stop()
        check('own pending PROF drained before handler/mask restore',lambda:need(s.pending_drained==1 and s.restored and signal.getsignal(signal.SIGPROF) is old_prof,'pending drain'))
    finally:
        signal.setitimer(signal.ITIMER_PROF,0);signal.signal(signal.SIGPROF,original)
    # Inject the exact startup window: timer installed, PROF still blocked,
    # our pending signal exists, then independent wall timeout interrupts.
    before_handler=signal.getsignal(signal.SIGPROF)
    before_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    set_timer=signal.setitimer; timeout_start=TimeoutError('start-abort wall timeout')
    def interrupted_install(which,delay,interval=0):
        result=set_timer(which,delay,interval)
        if which==signal.ITIMER_PROF and delay:
            os.kill(os.getpid(),signal.SIGPROF)
            raise timeout_start
        return result
    signal.setitimer=interrupted_install
    try:
        aborted=sampler.LoopSampler()
        try:aborted.start()
        except TimeoutError as e:need(e is timeout_start,'start timeout replaced')
        else:raise AssertionError('start timeout absent')
        check('interrupted startup drains PROF before restoring old handler',lambda:need(
            aborted.pending_drained==1 and not aborted.active and
            signal.getsignal(signal.SIGPROF) is before_handler and
            signal.getitimer(signal.ITIMER_PROF)==(0.0,0.0) and
            signal.SIGPROF not in signal.sigpending() and
            signal.pthread_sigmask(signal.SIG_BLOCK,set())==before_mask,'start-abort cleanup'))
    finally:signal.setitimer=set_timer
    # An undrainable synthetic PROF must remain blocked with our harmless
    # handler, never replace an already-propagating original exception.
    s=sampler.LoopSampler();s.start()
    real_pending,real_wait=signal.sigpending,signal.sigtimedwait
    signal.sigpending=lambda:{signal.SIGPROF}
    signal.sigtimedwait=lambda *_:None
    failure=ValueError('original loop exception survives cleanup failure')
    try:
        try:
            try:raise failure
            finally:s.stop()
        except ValueError as e:need(e is failure,'cleanup replaced original exception')
        check('undrainable pending PROF stays safe and cannot PASS',lambda:need(
            not s.restored and not s.stopped and not s.active and s.cleanup_error and
            signal.getsignal(signal.SIGPROF) is s.callback and
            signal.SIGPROF in signal.pthread_sigmask(signal.SIG_BLOCK,set()),'unsafe failed cleanup'))
        rejects(s.report)
    finally:
        signal.sigpending,signal.sigtimedwait=real_pending,real_wait
        if signal.SIGPROF in signal.sigpending():signal.sigtimedwait({signal.SIGPROF},0)
        signal.signal(signal.SIGPROF,s.old_handler)
        signal.pthread_sigmask(signal.SIG_SETMASK,s.old_mask)
    # The sampler must never restart/extend the existing independent wall timer.
    old_alarm=signal.getsignal(signal.SIGALRM)
    def alarm(*_):raise TimeoutError('unchanged wall deadline')
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,2)
    try:
        before=signal.getitimer(signal.ITIMER_REAL)[0]
        s=sampler.LoopSampler();s.start()
        try:
            until=time.process_time()+.035
            while time.process_time()<until:pass
        finally:s.stop()
        after=signal.getitimer(signal.ITIMER_REAL)[0]
        check('SIGALRM handler unchanged and deadline decreases',lambda:need(signal.getsignal(signal.SIGALRM) is alarm and 0<after<before,'wall timer modified'))
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_alarm)
    # No catch in sample handler: emulate a wall interrupt arriving at its clock
    # read and prove the exact exception object propagates through finally.
    timeout=TimeoutError('nested SIGALRM identity');s=sampler.LoopSampler();s.active=True
    original_clock=sampler.time.process_time_ns
    def raise_timeout():raise timeout
    sampler.time.process_time_ns=raise_timeout
    try:
        try:s._sample(signal.SIGPROF,sys._getframe())
        except TimeoutError as e:need(e is timeout and not s.busy,'timeout swallowed/replaced')
        else:raise AssertionError('timeout absent')
        cases.append('nested wall-timeout object propagates; handler busy reset')
    finally:sampler.time.process_time_ns=original_clock
    # Direct synthetic frames only for exact caps; no real signal or model.
    frame=types.SimpleNamespace(f_code=op.__code__,f_lineno=1,f_back=None)
    s=sampler.LoopSampler();s.active=True;s.samples=sampler.MAX_SAMPLES;s._sample(signal.SIGPROF,frame)
    check('sample cap bounds all stored stacks',lambda:need(s.overflow_samples==1 and not s.stacks,'sample cap'))
    s=sampler.LoopSampler();s.active=True;s.stacks={i:1 for i in range(sampler.MAX_STACKS)};s._sample(signal.SIGPROF,frame)
    check('distinct-stack cap rejects new stack',lambda:need(s.overflow_stacks==1 and len(s.stacks)==sampler.MAX_STACKS,'stack cap'))
    s=sampler.LoopSampler();s.active=True;s.codes=set(range(sampler.MAX_CODES));s._sample(signal.SIGPROF,frame)
    check('distinct-code cap rejects new code',lambda:need(s.overflow_codes==1 and not s.stacks,'code cap'))
    deep=frame
    for _ in range(60):deep=types.SimpleNamespace(f_code=op.__code__,f_lineno=1,f_back=deep)
    s=sampler.LoopSampler();s.active=True;s._sample(signal.SIGPROF,deep)
    check('stack depth bounded and disclosed',lambda:need(s.truncated_stacks==1 and len(next(iter(s.stacks)))==48,'depth cap'))
    s=sampler.LoopSampler();s.active=True;s.busy=True;s._sample(signal.SIGPROF,frame)
    check('reentrant sample bounded and disclosed',lambda:need(s.reentrant_dropped==1 and not s.stacks,'reentrance'))
    policy=gate.sampling_policy(manifest)
    check('policy exact current source and numeric caps',lambda:need(policy['max_codes']==sampler.MAX_CODES and policy['hz']==sampler.HZ and policy['max_samples']==sampler.MAX_SAMPLES and policy['max_stacks']==sampler.MAX_STACKS and policy['max_depth']==sampler.MAX_DEPTH,'policy differs'))
    budget=json.loads((HERE/'BUDGET.json').read_bytes());gate.validate_budget(budget)
    check('old budget schema rejected',lambda:rejects(lambda:gate.validate_budget(dict(budget,schema='fixed93-success-m2-calibration-budget-v1')),ValueError))
    check('old arm rejected before any authority read',lambda:rejects(lambda:a.admit(arm='old',base='',out='',admission='',admission_sha='',manifest_sha=''),ValueError))
    check('old authority is not new diagnostic schema',lambda:need('fixed93-success-m2-calibration-admission-v1' not in (HERE/'m2_authority.py').read_text(),'old authority retained'))
    check('parent has exactly one new child and only postseal historical comparison',lambda:need("for arm in ('new',):" in (HERE/'run_pair.py').read_text() and "expected_variants=('new','new')" in (HERE/'run_pair.py').read_text(),'parent arm/diff scope'))
    quality=load('sampling_report')
    report_copy=dict(report)
    check('real bounded report classified independently',lambda:need(quality.classify(report_copy) in ('COMPLETE_BOUNDED_SAMPLES','PARTIAL'),'quality'))
    # Valid minimal synthetic report, not a model/stream fixture.
    clean=dict(schema='fixed93-main-loop-sigprof-report-v1',diagnostic_only=True,speed_measurement=False,
        restored=True,active=False,status='PASS_BOUNDED_MAIN_LOOP_SAMPLING',hz=100,max_samples=12000,
        max_stacks=4096,max_depth=48,max_codes=2048,samples=1,unique_stacks=1,pending_drained=0,
        stacks=[{'stack':[[0,1]],'count':1}],code_table=[{'id':0}],
        overflow_samples=0,overflow_stacks=0,overflow_codes=0,truncated_stacks=0,reentrant_dropped=0)
    check('clean diagnostic quality only',lambda:need(quality.classify(clean)=='COMPLETE_BOUNDED_SAMPLES','clean quality'))
    for key in ('reentrant_dropped','truncated_stacks','overflow_samples'):
        value=dict(clean,**{key:1},status='INCOMPLETE_SAMPLING')
        check('nonfatal reported auxiliary loss '+key,lambda x=value:need(quality.classify(x)=='PARTIAL','partial failed'))
    for key in ('overflow_stacks','overflow_codes'):
        value=dict(clean,**{key:1},samples=2,status='INCOMPLETE_SAMPLING')
        check('nonfatal bounded store loss '+key,lambda x=value:need(quality.classify(x)=='PARTIAL','partial failed'))
    empty=dict(clean,samples=0,unique_stacks=0,stacks=[],code_table=[],status='INCOMPLETE_SAMPLING')
    check('zero samples auxiliary PARTIAL not model failure',lambda:need(quality.classify(empty)=='PARTIAL','empty'))
    for key,value in (('restored',False),('active',True),('samples',True),('reentrant_dropped',-1),('max_depth',49),('samples',2)):
        check('unsafe or malformed diagnostic still hard fails '+key+str(value),lambda k=key,v=value:rejects(lambda:quality.classify(dict(clean,**{k:v})),ValueError))
    policy=gate.sampling_policy(manifest);original=a.checked
    for key,value in (('quality_partial_blocks_main_evidence',True),('unsafe_restore_blocks_main_evidence',False),
                      ('preserve_sigalrm',False),('preserve_trace_dispatcher',False),('hz',True),('max_profile_bytes',8388608),('region','whole_run')):
        a.checked=lambda *x,raw=json.dumps(dict(policy,**{key:value})).encode(),**kw:raw
        try:check('sampling policy rejects '+key,lambda:rejects(lambda:a.sampling_policy(manifest),ValueError))
        finally:a.checked=original
    # Every helper except run_one remains exact, including fixture/run_loop/seal.
    predecessor=Path(manifest['predecessor']['path'])
    before=(predecessor/'success_driver.py').read_text();after=(HERE/'success_driver.py').read_text()
    def defs(raw):return {n.name:n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
    bd,ad=defs(before),defs(after)
    need(bd.keys()==ad.keys(),'driver function set drift')
    for name in bd.keys()-{'run_one'}:
        need(ast.get_source_segment(before,bd[name])==ast.get_source_segment(after,ad[name]),'driver helper drift '+name)
    def main_report(tree):
        return next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and
                    any(isinstance(t,ast.Name) and t.id=='report' for t in n.targets) and
                    isinstance(n.value,ast.Call) and any(k.arg=='status' for k in n.value.keywords))
    check('M2_CASE assignment exactly preserves historical semantic schema',lambda:need(
        ast.dump(main_report(bd['run_one']))==ast.dump(main_report(ad['run_one'])),'main report schema drift'))
    check('historical decoder remains byte-identical',lambda:need(
        (HERE/'parent/decode_diff.py').read_bytes()==(predecessor/'parent/decode_diff.py').read_bytes(),'decoder widened'))
    check('only run_one diagnostic wrapper among driver helpers',lambda:need('sampling[\'diagnostic_quality\'] = classify(sampling)' in after and
          "need(sampling['status']" not in after,'auxiliary status still blocks main evidence'))

    need(not denied and 'ctypes' not in sys.modules,'forbidden action attempted')
    print(json.dumps(dict(status='PASS_SINGLE_ARM_DIAGNOSTIC_SYNTHETIC_ONLY',cases=cases,case_count=len(cases),
        wall_seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        real_dispatcher_samples=report['samples'],real_dispatcher_unique_stacks=report['unique_stacks'],
        native_executed=False,model_executed=False,actual_M2_executed=False,denied_attempts=denied),sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
