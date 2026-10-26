"""One test-only attempt; pinned retained-leader cleanup on every spawned path."""
from pathlib import Path
import hashlib,json,os,re,resource,signal,subprocess,sys,time,types
HERE=Path(__file__).resolve().parent
HELPER=Path(os.environ['STRICT_CLEANUP_HELPER']).resolve()
HELPER_SHA='30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
SIGNALS={signal.SIGALRM,signal.SIGTERM,signal.SIGINT,signal.SIGHUP}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,message):
 if not ok:raise RuntimeError(message)
def load_cleanup():
 raw=HELPER.read_bytes();need(hashlib.sha256(raw).hexdigest()==HELPER_SHA,'cleanup helper drift')
 mod=types.ModuleType('admitted_cleanup');mod.__file__=str(HELPER);mod._ADMITTED_SOURCE_SHA256=HELPER_SHA
 exec(compile(raw,str(HELPER),'exec'),mod.__dict__);return mod

def owned_run(argv,run,env,cpu,absolute_stop,*,monitor_fault_for_test=False):
 """Retain direct leader even on success. Unit fault flag is never CLI-controlled."""
 strict=load_cleanup();work_stop=absolute_stop-30;cleanup_stop=absolute_stop-15
 owner=None;log=None;report={'worker_started':False,'cleanup_complete':False,'errors':[],
  'absolute_stop':absolute_stop,'work_stop':work_stop,'cleanup_stop':cleanup_stop,'helper_sha256':HELPER_SHA,
  'sampled_peak_rss_bytes':0,'sampled_peak_cpu_seconds':0,'sampled_peak_output_bytes':0}
 old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);old_handlers={s:signal.getsignal(s) for s in SIGNALS}
 def stop(signum,frame):raise RuntimeError('supervisor signal '+str(signum))
 def fail(error):report['errors'].append(type(error).__name__+': '+str(error))
 def child_limits():
  os.sched_setaffinity(0,{cpu});resource.setrlimit(resource.RLIMIT_CPU,(300,300));resource.setrlimit(resource.RLIMIT_FSIZE,(10*1024**2,)*2)
  for s in SIGNALS:signal.signal(s,signal.SIG_DFL)
  signal.pthread_sigmask(signal.SIG_UNBLOCK,SIGNALS)
 def sample():
  strict._verify_leader(owner,api,leader,boot)
  names=os.listdir('/proc');need(len(names)<=100000,'bounded process scan')
  rss=cpu_seconds=0;leader_seen=False
  for name in names:
   if not name.isascii() or not name.isdecimal():continue
   try:raw=(Path('/proc')/name/'stat').read_bytes()
   except FileNotFoundError:continue
   row=strict.parse_stat(raw)
   if row['group']!=owner['process'].pid:continue
   need(row['session']==leader['session'] and row['start']>=leader['start'],'ambiguous original group')
   fields=raw[raw.rindex(b')')+1:].split()
   rss+=max(0,int(fields[21]))*os.sysconf('SC_PAGE_SIZE')
   cpu_seconds+=sum(int(fields[i]) for i in (11,12,13,14))/os.sysconf('SC_CLK_TCK')
   leader_seen|=row['pid']==leader['pid'] and row['start']==leader['start']
  need(leader_seen,'retained leader missing')
  size=sum(p.stat().st_size for p in run.rglob('*') if p.is_file()) # Any OSError takes the same finally cleanup.
  report['sampled_peak_rss_bytes']=max(report['sampled_peak_rss_bytes'],rss)
  report['sampled_peak_cpu_seconds']=max(report['sampled_peak_cpu_seconds'],cpu_seconds)
  report['sampled_peak_output_bytes']=max(report['sampled_peak_output_bytes'],size)
  need(rss<=1024**3,'sampled owned group RSS cap');need(cpu_seconds<=300,'sampled aggregate CPU cap')
  need(size<=10*1024**2,'sampled total output cap');need(time.monotonic()<work_stop,'original work deadline')
 try:
  for s in SIGNALS:signal.signal(s,stop)
  need(time.monotonic()<work_stop,'original prelaunch deadline')
  signal.setitimer(signal.ITIMER_REAL,work_stop-time.monotonic())
  log=(run/'test.log').open('xb')
  p=subprocess.Popen(argv,cwd=run,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
      start_new_session=True,preexec_fn=child_limits)
  # Signals remain blocked until the owning handle and exact identity exist.
  owner={'process':p,'identity':None};report['worker_started']=True
  api=strict._Linux();boot=api.boot();leader,_=strict._verify_leader(owner,api,None,boot)
  report['owner_identity']=dict(owner['identity'])
  (run/'WORKER_STARTED.json').write_text(json.dumps({'owner_identity':owner['identity'],'session':leader['session'],'boot_id':boot,'absolute_stop':absolute_stop,'cleanup_stop':cleanup_stop})+'\n')
  signal.pthread_sigmask(signal.SIG_SETMASK,old_mask-SIGNALS)
  if monitor_fault_for_test:raise OSError('injected post-Popen monitor error')
  while True:
   sample()
   exited=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
   if exited is not None:
    report['observed_exit_code']=exited.si_status if exited.si_code==os.CLD_EXITED else -exited.si_status
    break
   time.sleep(.05)
 except BaseException as error:fail(error)
 finally:
  # Protect the one original cleanup interval; never reset deadline on error.
  signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);signal.setitimer(signal.ITIMER_REAL,0)
  for s in SIGNALS:
   if s in signal.sigpending():signal.sigtimedwait({s},0)
  try:
   if owner is not None:
    try:
     proof=strict.cleanup_owned(owner,cleanup_stop)
     strict.validate_cleanup_proof(proof,owner=owner,stop=cleanup_stop)
     report.update(cleanup_complete=True,cleanup_proof=proof,exit_code=proof['direct_exit_code'])
    except BaseException as error:fail(error)
    report['cleanup_observation']=owner.get('strict_cleanup_observation')
   else:report['cleanup_not_required_no_process_started']=True
  finally:
   try:
    if log is not None:log.flush();log.close()
   except BaseException as error:fail(error)
   # Restore state after protected cleanup; success still requires exact proof.
   signal.setitimer(signal.ITIMER_REAL,0)
   for s in SIGNALS:
    if s in signal.sigpending():signal.sigtimedwait({s},0)
   for s,handler in old_handlers.items():signal.signal(s,handler)
   signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
 return report

def main():
 need(sys.argv[1:]==['--test-only'],'explicit --test-only required')
 cpu=int(os.environ['HETERO_CPU']);need(cpu in os.sched_getaffinity(0),'assigned CPU unavailable')
 run=Path(os.environ['VERIFIED_OBSERVED_TEST_RUN_ROOT']).resolve();start=time.monotonic();absolute_stop=start+360
 plan=json.loads((run/'PLAN.json').read_bytes());compiled=json.loads((run/'BASE_COMPILE_RESULT.json').read_bytes())
 observed=json.loads((run/'OBSERVED_COMPILE_RESULT.json').read_bytes())
 need(observed.get('stage')=='compile_observation_spec_only' and observed.get('qualified') is True and observed.get('exit_code')==0 and observed.get('cleanup_complete') is True and not observed.get('errors'),'qualified observation-class compile required')
 need(len(compiled)==1 and compiled[0]['stage']=='compile' and compiled[0]['exit_code']==0 and compiled[0]['stop_reason'] is None,'qualified compile required')
 classes=json.loads((run/'COMPILED_CLASSES.json').read_bytes());golden=Path(os.environ['OFFICIAL_SYNTHETIC_GOLDEN']).resolve()
 def current_classes():return {str(p.relative_to(run/'classes')):sha(p) for p in sorted((run/'classes').rglob('*.class'))}
 def unchanged():return {'sources':all(sha(p)==v for p,v in plan['sources'].items()),'jars':all(sha(p)==v for p,v in plan['jars'].items()),'classes':classes==current_classes(),'golden':sha(golden)==plan['golden_sha256']}
 need(all(unchanged().values()),'preflight source/tool/classes/golden drift')
 need(not(run/'test.log').exists() and not(run/'TEST_PLAN.json').exists(),'only one attempt; retain originals')
 argv=plan['commands']['test'];need('-Xmx512m' in argv and '-XX:ActiveProcessorCount=1' in argv,'fixed JVM caps')
 caps={**plan['caps'],'assigned_cpu':cpu,'total_wall_seconds':360,'work_reserve_for_cleanup_seconds':30,'final_postflight_reserve_seconds':15}
 (run/'TEST_PLAN.json').write_text(json.dumps({'argv':argv,'caps':caps,'runner_sha256':sha(__file__),'cleanup_sha256':HELPER_SHA,'source_plan_sha256':sha(run/'PLAN.json'),'compiled_classes_manifest_sha256':sha(run/'COMPILED_CLASSES.json'),'golden_sha256':sha(golden),'expected_tests':5,'scope':'Independent observed successor: unchanged DUT/Golden/stimuli, original complete five cases, bounded traces and fixture-specific progress guard; old CPU120 failure retained. Not complete4096/35B block; nonfinite/overflow gaps remain.'},indent=2)+'\n')
 report=owned_run(argv,run,{**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MOE_GOLDEN':str(golden)},cpu,absolute_stop)
 # Postflight uses the remaining part of the same original boundary, not a retry.
 old_handler=signal.getsignal(signal.SIGALRM)
 def expired(signum,frame):raise RuntimeError('original total deadline during postflight')
 try:
  need(time.monotonic()<absolute_stop,'original total deadline before postflight')
  signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,absolute_stop-time.monotonic())
  report['unchanged']=unchanged();report['log_sha256']=sha(run/'test.log')
  clean=re.sub(r'\x1b\[[0-9;]*m','',(run/'test.log').read_text())
  report['exact_five_tests_passed']=('Total number of tests run: 5' in clean and 'Tests: succeeded 5, failed 0, canceled 0, ignored 0, pending 0' in clean and 'All tests passed.' in clean)
  need(time.monotonic()<absolute_stop,'original total deadline after postflight')
 except BaseException as error:report['errors'].append(type(error).__name__+': '+str(error))
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
 report['wall_seconds']=time.monotonic()-start
 report['qualified']=not report['errors'] and report.get('exit_code')==0 and report['cleanup_complete'] and report.get('exact_five_tests_passed') is True and all(report.get('unchanged',{'unknown':False}).values())
 (run/'TEST_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['qualified','exit_code','wall_seconds','sampled_peak_rss_bytes','sampled_peak_cpu_seconds','cleanup_complete','exact_five_tests_passed','errors']}),flush=True)
 raise SystemExit(0 if report['qualified'] else 1)
if __name__=='__main__':main()
