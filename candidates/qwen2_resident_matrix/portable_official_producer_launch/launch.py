"""Fresh hosted M16 reference preparation; no Public or M128 execution.

Source preparation only until the exact launcher, source lock, package lock and
workflow have passed review. The caller must also enforce TERM at 890 seconds
and KILL ten seconds later. All payload and detailed logs remain private.
"""
import argparse
import hashlib
import importlib.util
import importlib.machinery
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import signal
import stat
import sys
import time

HERE = Path(__file__).resolve().parent
PREFIX = 'candidates/qwen2_resident_matrix/'
CONSUMER = PREFIX + 'portable_consumer_qualification/'
PRODUCER = PREFIX + 'portable_official_producer/'
OWN = PREFIX + 'portable_official_producer_launch/'
PROFILE = 'qwen2-fresh-same-host-m16-producer-qualified-v1'
CLAIMS = dict(actual_chain_executed=False, full_public_admission=False,
    full_29_node_acceptance=False, rtl_execution=False,
    hardware_recipe_acceptance=False, old_pass_inherited=False)
SIGNALS = {signal.SIGALRM, signal.SIGTERM, signal.SIGINT}
WORK_SECONDS, CLEANUP_SECONDS, TOTAL_SECONDS = 890, 899, 900
EXEC = 'import os,sys\nos.execv(sys.argv[1],sys.argv[1:])\n'


def need(value, reason):
    if not value:
        raise ValueError('fresh producer launcher: ' + reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(value, length=64):
    return type(value) is str and len(value)==length and all(c in '0123456789abcdef' for c in value)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw, limit=2*1024*1024):
    need(type(raw) is bytes and len(raw)<=limit, 'JSON size')
    def pairs(items):
        value={}
        for key,item in items:
            need(key not in value, 'duplicate JSON key')
            value[key]=item
        return value
    def invalid(_):
        raise ValueError('fresh producer launcher: nonfinite JSON')
    value=json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    encoded(value)
    return value


def safe(path, limit=2*1024*1024):
    path=Path(path).absolute()
    need(all(not p.is_symlink() for p in (path,*path.parents)), 'symlink path')
    before=path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit, 'file type/alias/size')
    with path.open('rb') as stream:
        opened=os.fstat(stream.fileno())
        need((opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino), 'open race')
        raw=stream.read(limit+1)
        after=os.fstat(stream.fileno())
    fields=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
    need(fields(before)==fields(after) and len(raw)==before.st_size, 'file drift')
    return raw


def record(root, item):
    need(type(item) is dict and set(item)=={'path','bytes','sha256'}, 'artifact record')
    name=item['path']
    need(type(name) is str and '\\' not in name and not PurePosixPath(name).is_absolute()
         and all(p not in ('','.','..') for p in name.split('/')), 'relative record path')
    need(type(item['bytes']) is int and 0<=item['bytes']<=188043264 and digest(item['sha256']), 'record identity')
    path=Path(root)/name
    raw=safe(path,188043264)
    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'], 'artifact hash')
    return path


def write_new(path,value):
    raw=encoded(value);need(len(raw)<=2*1024*1024,'receipt bound')
    with Path(path).open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    directory=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)
    return sha(raw)


def host():
    need(os.uname().sysname=='Linux' and os.uname().machine=='x86_64','host family')
    with Path('/proc/sys/kernel/random/boot_id').open('rb') as stream:
        boot=stream.read(129).strip()
    need(len(boot)==36,'boot identity')
    return dict(host_sha256=sha(os.uname().nodename.encode()),boot_sha256=sha(boot),machine='x86_64',system='Linux')


def resource_observation(out):
    raw=Path('/proc/meminfo').read_text();need(len(raw)<65536,'memory observation bound')
    available=[int(line.split()[1])*1024 for line in raw.splitlines() if line.startswith('MemAvailable:')]
    need(len(available)==1,'memory observation')
    disk=os.statvfs(Path(out).parent)
    return dict(cpu_affinity=len(os.sched_getaffinity(0)),available_memory_bytes=available[0],
        available_disk_bytes=disk.f_bavail*disk.f_frsize)


def import_path_guard(root,sources):
    """Reject implicit package code and cache alternatives to pinned source."""
    need(sys.dont_write_bytecode and sys.pycache_prefix is None,'source-only import mode')
    for name in sources:
        path=Path(root)/name
        if path.suffix!='.py': continue
        need(not path.with_suffix('.pyc').exists() and
             not any((path.parent/'__pycache__').glob(path.stem+'.*.pyc')),'source bytecode cache')
        for suffix in importlib.machinery.EXTENSION_SUFFIXES:
            need(not path.with_name(path.stem+suffix).exists(),'source extension shadow')
        for parent in path.parents:
            if parent==Path(root): break
            initializer=parent/'__init__.py'
            need(not initializer.with_suffix('.pyc').exists() and
                 not any((parent/'__pycache__').glob('__init__.*.pyc')),'package bytecode cache')
            if initializer.exists():
                need(initializer.relative_to(root).as_posix() in sources,'unpinned package initializer')


def load_contract(root):
    need(Path(root).resolve()/OWN==HERE,'single launcher source root')
    value=strict(safe(HERE/'launch-contract.json'))
    need(type(value) is dict and set(value)=={'schema','profile','sources','packages','minimum_resources','budgets'},'contract keys')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE,'contract profile')
    need(encoded(value['budgets'])==encoded(dict(work=890,cleanup=899,total=900,tiny=150,install=300)),'fixed budgets')
    need(type(value['sources']) is dict and value['sources'],'source map')
    for name,expected in value['sources'].items():
        need(type(name) is str and '\\' not in name and not Path(name).is_absolute()
             and all(p not in ('','.','..') for p in name.split('/')) and digest(expected),'source identity')
        need(sha(safe(Path(root)/name,8*1024*1024))==expected,'source drift: '+name)
    need(type(value['packages']) is dict and set(value['packages'])=={'bootstrap','runtime','lock'},'package paths')
    need(value['packages']==dict(bootstrap=OWN+'requirements-bootstrap.lock',runtime=OWN+'requirements-runtime.lock',lock=OWN+'wheel-lock.json'),'fixed package paths')
    need(all(name in value['sources'] for name in value['packages'].values()),'package source closure')
    minimum=dict(cpu_affinity=4,available_memory_bytes=6*1024**3,available_disk_bytes=4*1024**3)
    need(encoded(value['minimum_resources'])==encoded(minimum),'fixed minimum resources')
    for name in ('launch.py','package_validation.py','installed_inventory.py','verify_producer.py'):
        need(value['sources'].get(OWN+name)==sha(safe(HERE/name)), 'loaded launcher source: '+name)
    for name in ('driver.py','owned_commands.py','source-lock.json','gate.py'):
        need(PRODUCER+name in value['sources'],'producer source required')
    import_path_guard(root,value['sources'])
    producer_lock=strict(safe(Path(root)/PRODUCER/'source-lock.json'))
    need(type(producer_lock) is dict and set(producer_lock)=={'schema','sources'} and
         type(producer_lock['schema']) is int and producer_lock['schema']==1 and
         type(producer_lock['sources']) is dict and producer_lock['sources'],'producer lock closure')
    need(all(value['sources'].get(k)==v for k,v in producer_lock['sources'].items()),'complete producer preflight closure')
    need(CONSUMER+'input-contract.json' in value['sources'],'fresh tiny contract pin')
    tiny=strict(safe(Path(root)/CONSUMER/'input-contract.json'))
    for role in ('source_sha256','payload_sha256'):
        need(type(tiny.get(role)) is dict and tiny[role] and
             all(value['sources'].get(k)==v for k,v in tiny[role].items()),'complete tiny preflight closure')
    return value


def load_checked(name,path,expected):
    """Execute the checked source buffer, never a timestamp-valid .pyc cache."""
    raw=safe(path,8*1024*1024)
    need(sha(raw)==expected,'imported source identity')
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def packages(root,contract):
    path=Path(root)/OWN/'package_validation.py'
    module=load_checked('fresh_package_validator',path,contract['sources'][OWN+'package_validation.py'])
    lock=module.validate_lock(strict(safe(root/contract['packages']['lock'])))
    for role in ('bootstrap','runtime'):
        module.validate_requirements(safe(root/contract['packages'][role]),lock,role)
    return module,lock


def helper(root,contract):
    """Load only exact published sources, bypassing any bytecode/module cache."""
    directory=Path(root)/CONSUMER
    old=sys.modules.get('contract')
    need(old is None or Path(old.__file__).resolve()==directory/'contract.py','foreign contract import')
    checked=load_checked('contract',directory/'contract.py',contract['sources'][CONSUMER+'contract.py'])
    sys.modules['contract']=checked
    module=load_checked('fresh_owned_control',directory/'run_ci.py',contract['sources'][CONSUMER+'run_ci.py'])
    need(module.c is checked and Path(module.c.__file__).resolve()==directory/'contract.py','loaded helper contract')
    return module


def remaining(deadline):
    value=deadline-time.monotonic()
    if value<=0: raise TimeoutError('absolute preparation deadline')
    return value


def interrupted(signum,frame):
    raise TimeoutError('preparation deadline or cancellation')


def arm(deadline):
    for signum in SIGNALS: signal.signal(signum,interrupted)
    signal.setitimer(signal.ITIMER_REAL,max(0.000001,remaining(deadline)))


def finish_owned(control,owner,stop,*,cancel):
    """Give the producer time to reap any independently owned compiler child."""
    control.protect_cleanup()
    if owner['process'] is None: return False
    if cancel:
        process=owner['process']
        os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        current=control.process_identity(process.pid)
        if owner['identity'] is None: owner['identity']=current
        need(current==owner['identity'] and current['ppid']==os.getpid()
             and current['group']==process.pid!=os.getpgrp(),'owned cancellation group')
        try: os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: control.observe_exit(process.pid,max(time.monotonic(),stop-2))
        except TimeoutError: pass
    control.cleanup_owned(owner,stop)
    return True


def stage(control,argv,*,cwd,env,log,cap,work_stop,cleanup_stop,journal=None,name='control'):
    """Retain exits and cleanup even when the actual child fails or is cancelled."""
    owner={'process':None,'identity':None}
    stop=min(work_stop,time.monotonic()+cap)
    failure=None;code=None;cleaned=False;cleanup_failed=False
    entry=dict(phase=name,pid=None,observed_exit_code=None,final_exit_code=None,
               owned_group_cleanup_complete=False,status='NOT_STARTED')
    if journal is not None: journal.append(entry)
    try:
        arm(stop)
        with Path(log).open('xb') as stream:
            control.spawn_owned(owner,['-I','-B','-c',EXEC,*map(str,argv)],cwd=cwd,stdout=stream,env=env)
            entry.update(pid=owner['process'].pid,status='RUNNING')
            code=control.observe_exit(owner['process'].pid,stop)
            entry['observed_exit_code']=code
            need(type(code) is int and code==0,'phase child nonzero exit')
    except BaseException as error:
        failure=error
    finally:
        try:
            cleaned=finish_owned(control,owner,min(cleanup_stop,stop+9),cancel=failure is not None)
        except BaseException as cleanup_error:
            cleanup_failed=True
            if failure is None: failure=cleanup_error
        process=owner['process']
        if process is not None:
            entry['pid']=process.pid
            if type(process.returncode) is int:
                entry['final_exit_code']=process.returncode if process.returncode>=0 else 128-process.returncode
        entry['owned_group_cleanup_complete']=cleaned
        entry['status']='CLEANUP_FAILED' if cleanup_failed else ('TIMEOUT' if isinstance(failure,TimeoutError) else 'FAILED' if failure is not None else 'PASS')
    if failure is not None: raise failure
    need(cleaned,'owned phase cleanup')
    arm(work_stop)
    return dict(pid=owner['process'].pid,exit_code=code,owned_group_cleanup_complete=cleaned)


def manifest_postflight(root,workspace,nonce,ci,source_map):
    raw=safe(workspace/'PRODUCER_M16.json')
    value=strict(raw)
    path=Path(root)/PRODUCER/'driver.py'
    validator=load_checked('fresh_producer_cold_validator',path,source_map[PRODUCER+'driver.py'])
    validator.validate_manifest(value)
    need(value.get('profile')=='qwen2-official-bf16-consumer-host-v1' and
         value.get('status')=='COMPLETE_FRESH_M16_REFERENCE_OUTPUTS','producer completion')
    need(type(value.get('schema')) is int and value['schema']==1 and type(value.get('rows')) is int
         and value['rows']==16 and type(value.get('past_tokens')) is int and value['past_tokens']==0,'producer geometry')
    need(value.get('attempt_nonce')==nonce and encoded(value.get('ci'))==encoded(ci),'producer attempt')
    need(encoded(value.get('host'))==encoded(host()),'same producer host/boot')
    need(value.get('original_small_gate_revalidated') is True and encoded(value.get('claims'))==encoded(CLAIMS),'original gate and scope')
    sources=value.get('source_sha256')
    lock=strict(safe(Path(root)/PRODUCER/'source-lock.json'))
    need(type(lock) is dict and set(lock)=={'schema','sources'} and type(lock['schema']) is int and lock['schema']==1,'producer source lock')
    need(type(sources) is dict and sources and encoded(sources)==encoded(lock['sources']) and
         all(source_map.get(k)==v for k,v in sources.items()),'exact producer source closure')
    need(sha(encoded(sources))==value.get('source_manifest_sha256'),'producer source digest')
    need(value.get('driver_sha256')==source_map[PRODUCER+'driver.py'] and
         value.get('source_lock_sha256')==source_map[PRODUCER+'source-lock.json'],'producer loaded source')
    seen={}
    def walk(node):
        if type(node) is dict:
            if set(node)=={'path','bytes','sha256'}:
                path=record(workspace,node);info=path.stat();key=(info.st_dev,info.st_ino)
                need(key not in seen or seen[key]==node['path'],'cross-record alias')
                seen[key]=node['path']
            else:
                for child in node.values(): walk(child)
        elif type(node) is list:
            for child in node: walk(child)
    for field in ('payload','readonly','sequential','reduced','native','libraries'): walk(value[field])
    need(len(value['payload']['tensors'])==13 and sum(x['bytes'] for x in value['payload']['tensors'].values())==94382080,'official payload inventory')
    need(all(len(value[r]['outputs'])==22 for r in ('sequential','reduced')),'two reference inventories')
    need(sum(len(stages) for methods in value['native']['outputs'].values() for stages in methods.values())==116,'native export inventory')
    need(safe(workspace/'PRODUCER_M16.json')==raw,'producer manifest drift')
    return value,sha(raw)


def validate_verifier(value,producer,manifest_sha,context_sha,nonce,ci):
    expected=dict(schema=1,profile='qwen2-fresh-parent-native-verification-v1',status='PASS_ORIGINAL_M16_NATIVE_GATES',
        attempt_nonce=nonce,ci=ci,producer_manifest_sha256=manifest_sha,parent_context_sha256=context_sha,
        source_manifest_sha256=producer['source_manifest_sha256'],
        runtime_identity_sha256=sha(encoded(producer['runtime_identity'])),host_sha256=sha(encoded(producer['host'])),
        native_exports=116,original_array_gate_revalidated=True,new_forward_executed=False,claims=CLAIMS)
    need(encoded(value)==encoded(expected),'owned independent original native validation')
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    started=time.monotonic();work_stop=started+WORK_SECONDS;cleanup_stop=started+CLEANUP_SECONDS;receipt_stop=started+TOTAL_SECONDS
    need(sys.version_info[:3]==(3,12,15) and not sys.flags.optimize and sys.flags.isolated,'exact isolated normal interpreter')
    root=args.root.resolve(strict=True);out=args.out.absolute()
    need('..' not in out.parts and out==out.resolve(strict=False) and not out.exists() and not out.is_symlink() and all(not p.is_symlink() for p in out.parents),'fresh owned output')
    need(not out.is_relative_to(root) and not root.is_relative_to(out),'source and output must be disjoint')
    contract=load_contract(root);control=helper(root,contract)
    package_validator,wheel_lock=packages(root,contract)
    tiny_contract=control.c.validate(root,root/CONSUMER)
    ci=dict(commit=control.c.admit(os.environ,out),run_id=os.environ.get('GITHUB_RUN_ID'),run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'))
    need(type(ci['run_id']) is str and ci['run_id'].isascii() and ci['run_id'].isdecimal() and int(ci['run_id'])>0 and ci['run_attempt']=='1','first CI identity')
    loader=control.c.loader(os.environ,sys.executable)
    need(not any(k in os.environ for k in ('ATEN_CPU_CAPABILITY','ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','ONEDNN_CPU_ISA_HINTS','DNNL_CPU_ISA_HINTS','MKL_ENABLE_INSTRUCTIONS','OPENBLAS_CORETYPE','NPY_DISABLE_CPU_FEATURES','NPY_ENABLE_CPU_FEATURES')),'no ISA overrides')
    resources=resource_observation(out)
    need(set(resources)==set(contract['minimum_resources']) and all(type(v) is int and v>=contract['minimum_resources'][k] for k,v in resources.items()),'observed resource minimum')
    out.mkdir(mode=0o700)  # Exclusive ownership: nothing below runs for a replay.
    nonce=secrets.token_hex(32)
    failure=None;phase='provision';producer_started=False;terminal=None;journal=[]
    package_reports={}
    try:
        arm(work_stop)
        (out/'evidence').mkdir()
        write_new(out/'LAUNCH_LOCK.json',dict(schema=1,profile=PROFILE,attempt_nonce=nonce,pid=os.getpid(),host=host(),ci=ci,started=started,work_deadline=work_stop,outer_deadline=receipt_stop))
        for name in ('home','tmp'): (out/name).mkdir()
        env=control.clean_environment(out,loader);env['GITHUB_RUN_ID']=ci['run_id']
        # Every command including git is owned, retained, bounded, and reaped.
        stage(control,['/usr/bin/git','rev-parse','HEAD'],cwd=root,env=env,log=out/'head.log',cap=5,
            work_stop=work_stop,cleanup_stop=cleanup_stop,journal=journal,name='checkout_identity')
        need(safe(out/'head.log',128).decode('ascii').strip()==ci['commit'],'actual checkout equals triggering commit')
        stage(control,[sys.executable,'-I','-B','-m','venv',out/'venv'],cwd=root,env=env,log=out/'venv.log',cap=30,
            work_stop=work_stop,cleanup_stop=cleanup_stop,journal=journal,name='private_venv')
        python=out/'venv/bin/python'
        install_stop=min(work_stop,time.monotonic()+300)
        pip_env=dict(env,PIP_CONFIG_FILE=os.devnull)
        for role in ('bootstrap','runtime'):
            report=out/('pip-'+role+'-report.json')
            stage(control,[python,'-I','-B','-m','pip','--isolated','install','--require-hashes','--no-deps','--only-binary=:all:',
                '--disable-pip-version-check','--no-cache-dir','--no-input','--no-index','--force-reinstall','--report',report,
                '-r',root/contract['packages'][role]],cwd=root,env=pip_env,log=out/('pip-'+role+'.log'),cap=remaining(install_stop),
                work_stop=install_stop,cleanup_stop=cleanup_stop,journal=journal,name='pip_'+role)
            report_raw=safe(report,8*1024*1024)
            package_validator.validate_report(strict(report_raw,8*1024*1024),wheel_lock,role)
            package_reports[role]=sha(report_raw)
        stage(control,[python,'-I','-B',root/OWN/'installed_inventory.py',out/'installed.json'],cwd=root,env=env,
            log=out/'installed.log',cap=remaining(install_stop),work_stop=install_stop,cleanup_stop=cleanup_stop,journal=journal,name='installed_inventory')
        installed_raw=safe(out/'installed.json')
        package_validator.validate_inventory(strict(installed_raw),wheel_lock)
        package_reports['installed_inventory']=sha(installed_raw)
        phase='fixed_cases';tiny=out/'tiny';tiny.mkdir()
        tiny_run=stage(control,[python,'-I','-B',root/CONSUMER/'worker.py','all',root,tiny],cwd=root,env=env,
            log=out/'tiny.log',cap=150,work_stop=work_stop,cleanup_stop=cleanup_stop,journal=journal,name='fresh_fixed_cases')
        tiny_contract=control.c.validate(root,root/CONSUMER)
        tiny_raw=safe(tiny/'result.json');tiny_result=control.c.result(strict(tiny_raw),ci['commit'],tiny_contract)
        phase='producer';producer_started=True
        producer_env=dict(env,OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
        workspace=out/'producer'
        deadline_ns=int(work_stop*1e9)
        context=dict(schema=1,profile='qwen2-fresh-same-host-producer-context-v1',parent_pid=os.getpid(),
            root=str(root),workspace=str(workspace),created_ns=time.monotonic_ns(),deadline_ns=deadline_ns,
            attempt_nonce=nonce,ci=ci,host=host(),driver_sha256=contract['sources'][PRODUCER+'driver.py'],
            source_lock_sha256=contract['sources'][PRODUCER+'source-lock.json'],tiny_result_sha256=sha(tiny_raw))
        context_path=out/'PRODUCER_CONTEXT.json';context_sha=write_new(context_path,context)
        producer_run=stage(control,[python,'-I','-B',root/PRODUCER/'driver.py','--root',root,'--workspace',workspace,
            '--deadline-ns',str(deadline_ns),'--attempt-nonce',nonce,'--commit',ci['commit'],'--run-id',ci['run_id'],'--run-attempt','1',
            '--context',context_path,'--context-sha256',context_sha],
            cwd=root,env=producer_env,log=out/'producer.log',cap=remaining(work_stop),work_stop=work_stop,cleanup_stop=cleanup_stop,journal=journal,name='fresh_producer')
        phase='postflight'
        value,manifest_sha=manifest_postflight(root,workspace,nonce,ci,contract['sources'])
        phase='original_native_verification'
        stage(control,[python,'-I','-B',root/OWN/'verify_producer.py','--root',root,'--workspace',workspace,
            '--context',context_path,'--context-sha256',context_sha,'--manifest-sha256',manifest_sha,
            '--out',out/'VERIFIED_PRODUCER.json'],cwd=root,env=producer_env,log=out/'verify-producer.log',
            cap=remaining(work_stop),work_stop=work_stop,cleanup_stop=cleanup_stop,journal=journal,name='original_native_verification')
        verifier_raw=safe(out/'VERIFIED_PRODUCER.json')
        validate_verifier(strict(verifier_raw),value,manifest_sha,context_sha,nonce,ci)
        _,after_manifest_sha=manifest_postflight(root,workspace,nonce,ci,contract['sources'])
        need(after_manifest_sha==manifest_sha,'verified producer manifest drift')
        load_contract(root)
        need(sha(safe(context_path))==context_sha,'parent context drift')
        need(safe(tiny/'result.json')==tiny_raw,'fresh tiny result drift')
        terminal=dict(schema=1,profile=PROFILE,status='PASS_FRESH_M16_PRODUCER',attempt_nonce=nonce,
            producer_manifest_sha256=manifest_sha,producer_source_manifest_sha256=value['source_manifest_sha256'],
            host_sha256=sha(encoded(value['host'])),runtime_identity_sha256=sha(encoded(value['runtime_identity'])),
            ci=ci,child_pid=producer_run['pid'],child_exit_code=producer_run['exit_code'],owned_group_cleanup_complete=True,
            producer_native_gate_validated=True,fresh_tiny_result_sha256=sha(tiny_raw),
            fresh_tiny_source_manifest_sha256=sha(encoded({**tiny_contract['source_sha256'],**tiny_contract['generated_sha256']})),claims=CLAIMS)
    except BaseException as error:
        failure=error
    finally:
        control.protect_cleanup()
        try:
            control.arm_receipt_deadline(receipt_stop)
            remaining(receipt_stop)
            elapsed=time.monotonic()-started
            if failure is None:
                terminal['elapsed_seconds']=elapsed
                write_new(out/'QUALIFICATION.json',terminal)
            write_new(out/'evidence/summary.json',dict(schema=1,profile=PROFILE,
                status='PASS_FRESH_M16_PRODUCER' if failure is None else 'FAILED_PREPARATION',phase=phase,
                producer_started=producer_started,observed_complete=terminal is not None and failure is None,
                stages=journal,package_report_sha256=package_reports,
                failure_kind=None if failure is None else type(failure).__name__,
                owned_groups_cleanup_complete=any(x['pid'] is not None for x in journal) and all(x['owned_group_cleanup_complete'] for x in journal if x['pid'] is not None),
                attempt_nonce=nonce,ci=ci,elapsed_seconds=elapsed,resources=resources,claims=CLAIMS))
        except BaseException as receipt_error:
            if failure is None: failure=receipt_error
        finally: control.protect_cleanup()
    if failure is not None: raise failure
    return 0


if __name__=='__main__':
    raise SystemExit(main())
