#!/usr/bin/env python3
"""Root-review candidate, single attempt; no runtime network isolation asserted. No retry. Compile spec, run Treadle."""
import hashlib, json, os, pathlib, resource, signal, stat, subprocess, sys, time
HERE=pathlib.Path(__file__).resolve().parent

def need(ok, why):
    if not ok: raise RuntimeError(why)
def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        before=os.fstat(f.fileno())
        while b:=f.read(1024*1024):h.update(b)
        after=os.fstat(f.fileno())
    need((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Input changed while hashing')
    return {'bytes':after.st_size,'sha256':h.hexdigest()}
def verify(plan):
    found={}
    for path,pin in plan['inputs'].items():
        p=pathlib.Path(path);need(str(p.resolve(strict=True))==pin.get('resolved',str(p)), 'Input resolution changed: '+path)
        need(p.is_file(),'Not regular input'); row=digest(p)
        need(all(row[k]==pin[k] for k in row),'Input digest mismatch: '+path);found[path]=row
    root=pathlib.Path(plan['original_classes'])
    need(sorted(str(p) for p in root.rglob('*') if p.is_file())==plan['original_class_paths'],'Original class closure drift')
    return found

def inventory(root):
    files={}; total=0
    for p in root.rglob('*'):
        s=p.lstat(); need(not stat.S_ISLNK(s.st_mode),'Output symlink')
        if stat.S_ISDIR(s.st_mode):continue
        need(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'Nonordinary output')
        need(s.st_size<=16*1024**2,'Single output file cap')
        total+=s.st_size;need(total<=64*1024**2 and len(files)<4096,'Output aggregate cap')
        files[str(p.relative_to(root))]={'bytes':s.st_size}
    return files

def dump(root,name,data):
    with (root/name).open('x') as f:json.dump(data,f,indent=2,sort_keys=True)

def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU,(180,180))
    resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})

def group_absent(pgid):
    try: os.killpg(pgid,0); return False
    except ProcessLookupError: return True

def terminal_caps(root, log, elapsed):
    need(elapsed<=180,'Terminal phase wall cap')
    need(log.stat().st_size<=2*1024**2,'Terminal log cap')
    inventory(root)

def terminated(signum, frame):
    raise RuntimeError('Supervisor termination signal '+str(signum))

def phase(plan,name,argv):
    signal.signal(signal.SIGTERM,terminated)
    signal.signal(signal.SIGINT,terminated)
    root=pathlib.Path(plan['output']); start=time.monotonic(); p=None; observed=None; failure=None; quiescent=False; code=None; elapsed=None
    with (root/(name+'.log')).open('xb') as log:
        try:
            p=subprocess.Popen(argv,cwd=root,env=plan['environment'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=child_limits)
            while True:
                observed=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if observed:
                    elapsed=time.monotonic()-start
                    terminal_caps(root,root/(name+'.log'),elapsed)
                    break
                need(time.monotonic()-start<180,'Phase wall timeout')
                inventory(root)
                need(log.tell()<=2*1024**2,'Log cap')
                time.sleep(.1)
        except BaseException as e:failure=repr(e)
        finally:
            # Complete bounded cleanup despite repeated cancellation signals.
            signal.signal(signal.SIGTERM,signal.SIG_IGN)
            signal.signal(signal.SIGINT,signal.SIG_IGN)
            if p is not None:
                # Leader remains unreaped until group termination, preventing PID reuse.
                try:
                    stop=time.monotonic()+5
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    code=p.wait(timeout=max(.001,stop-time.monotonic()))
                    while not group_absent(p.pid) and time.monotonic()<stop:time.sleep(.05)
                    quiescent=group_absent(p.pid)
                    need(quiescent,'Process group quiescence not confirmed')
                    terminal_caps(root,root/(name+'.log'),elapsed if elapsed is not None else time.monotonic()-start)
                except BaseException as e:failure=(failure or '')+' cleanup/post-exit: '+repr(e)
    signal.signal(signal.SIGTERM,terminated)
    signal.signal(signal.SIGINT,terminated)
    record={'process_group_absent':quiescent,'exit_code':code,'seconds':time.monotonic()-start,'failure':failure,'natural_exit':bool(observed and observed.si_code==os.CLD_EXITED and observed.si_status==0),'leader_reaped':p is not None and p.returncode is not None}
    dump(root,name+'_receipt.json',record)
    need(failure is None and quiescent and code==0 and record['natural_exit'],name+' failed: '+str(record))

def admission():
    pins=json.loads((HERE/'REVIEW_PINS.json').read_text())
    for name in ['run_lane.py','PLAN.json']:
        need(digest(HERE/name)==pins[name],'Reviewed source/plan pin mismatch')
    plan=json.loads((HERE/'PLAN.json').read_text())
    need(plan['execution_authorized'] is True,'Execution not authorized')
    need(plan.get('backend_reviewed') is True and plan.get('backend_evidence_sha256'),'Backend review missing')
    evidence=pathlib.Path(plan['backend_evidence_path'])
    need(digest(evidence)['sha256']==plan['backend_evidence_sha256'],'Backend evidence pin mismatch')
    return plan

def main():
    need(len(sys.argv)==1,'No variable runtime arguments')
    plan=admission()
    need(plan['scope']=='singlelane_spec_only','Fixed scope')
    before=verify(plan)  # Admission is read-only; missing jars do not create output.
    root=pathlib.Path(plan['output']);root.mkdir(mode=0o700,exist_ok=False)
    os.umask(0o077)
    result={'status':'FAILED','backend':'explicit Treadle','RTL_generated':None}
    try:
        for sub in ['classes','tmp','home']: (root/sub).mkdir()
        dump(root,'BEFORE.json',before)
        phase(plan,'compile',plan['compile_argv'])
        phase(plan,'test',plan['test_argv'])
        log=(root/'test.log').read_text(errors='replace')
        need('All tests passed.' in log and 'Tests: succeeded 5, failed 0' in log,'Expected five-test ScalaTest pass missing')
        result['status']='PASS'
    except BaseException as e:result['error']=repr(e)
    finally:
        try:dump(root,'AFTER.json',verify(plan));result['inputs_unchanged']=True
        except BaseException as e:result['inputs_unchanged']=False;result['status']='FAILED';result['postflight_error']=repr(e)
        try:
            files=inventory(root)
            result['generated_RTL_files']=[p for p in files if pathlib.Path(p).suffix.lower() in ['.v','.sv']]
            result['generated_IR_files']=[p for p in files if pathlib.Path(p).suffix.lower() in ['.fir','.mlir']]
            result['RTL_generated']=bool(result['generated_RTL_files'])
            result['RTL_claim_scope']='Retained artifacts in isolated owned output; not proof that no transient RTL was generated.'
            dump(root,'OUTPUT_INVENTORY.json',files)
        except BaseException as e:
            result['status']='FAILED';result['inventory_error']=repr(e);result['RTL_generated']=None
        try:dump(root,'RESULT.json',result)
        except BaseException as e:result['status']='FAILED';result['receipt_error']=repr(e)
    print(json.dumps(result));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
