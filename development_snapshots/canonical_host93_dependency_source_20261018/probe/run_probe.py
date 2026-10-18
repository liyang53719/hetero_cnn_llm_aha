"""One fixed tool version or synthetic resource-generation probe per fresh process."""
import argparse,ast,hashlib,json,os,resource,signal,stat,subprocess,sys,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
PLAN_SHA='066eccb969acb634215179e3235c52f16141d2b5fc7320b0304b7b20747bf223'
GATE_PIN={'bytes': 8657, 'sha256': 'e0c6e0b4e31834880fbabca809fea4e4b7de48c612bf75cb6705b1094762f07e'}
SUPERVISOR_PIN={'bytes':16693,'sha256':'2eda970f0841b8aebffad451c44a414ed5effe6fbb51a3c04900eeec881b65d2'}
SUPERVISOR_PATH='development_snapshots/canonical_runtime_ram_source_20261018/run_behavior.py'
FUNCTIONS=('require','save','group_state','observe_exit','bounded')
TOOLS=('autoconf','autom4te','m4','flex','bison')


def require(ok,why):
    if not ok:raise ValueError(why)


def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def clean(path):
    p=Path(path).absolute();require('..' not in p.parts and all(not x.is_symlink() for x in (p,*p.parents)),'safe nonsymlink path');return p


def checked(path,expected):
    path=clean(path);s=path.lstat();require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size==expected['bytes']<=4*1024*1024,'fixed source/data size and type')
    raw=path.read_bytes();require(pin(raw)==expected,'fixed same-buffer hash');return raw


def load(raw,path,expected):
    require(pin(raw)==expected,'source before compile pin');m=types.ModuleType('fixed_probe_dependency');m.__file__=str(path);exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m


def project(raw):
    require(pin(raw)==SUPERVISOR_PIN,'fixed supervisor raw bytes')
    lines=raw.splitlines(keepends=True);selected={n.name:b''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS}
    require(tuple(selected)==FUNCTIONS,'fixed five published functions');before=selected['bounded'].decode();after=before
    edits=[("env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})",'env=CHILD_ENV)'),('        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))','        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n        allowed = os.sched_getaffinity(0)\n        require(bool(allowed), "empty inherited CPU affinity")\n        os.sched_setaffinity(0, {min(allowed)})'),('        finally:\n            if child is not None:','        finally:\n            signal.setitimer(signal.ITIMER_REAL, 0)\n            if child is not None:')]
    for old,new in edits:require(after.count(old)==1,'exact projection anchor');after=after.replace(old,new,1)
    restored=after
    for old,new in reversed(edits):require(restored.count(new)==1,'reverse projection anchor');restored=restored.replace(new,old,1)
    require(restored==before,'exact supervisor reverse projection');selected['bounded']=after.encode()
    return b'\n\n'.join(selected[n] for n in FUNCTIONS)+b'\n'


def configure(repo,gate,worker):
    raw=(HERE/'PROBE_PLAN.json').read_bytes();require(hashlib.sha256(raw).hexdigest()==PLAN_SHA,'fixed plan raw pin');p=json.loads(raw)
    definitions=checked(HERE/'MODE_DEFINITIONS.json',p['mode_definitions']);modes=json.loads(definitions)['modes']
    require(set(modes)=={x+'-'+s for x in TOOLS for s in ('version','micro')},'fixed ten modes')
    g=load(checked(gate/'run_stage.py',GATE_PIN),gate/'run_stage.py',GATE_PIN);worker_raw,m,pins=g.preflight(worker)
    source=checked(repo/SUPERVISOR_PATH,SUPERVISOR_PIN);projected=project(source)
    return p,modes,g,m,pins,projected,worker_raw


def usage():
    r=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'user_cpu_seconds':r.ru_utime,'system_cpu_seconds':r.ru_stime,'maxrss_kib':r.ru_maxrss,'major_faults':r.ru_majflt,'minor_faults':r.ru_minflt,'voluntary_context_switches':r.ru_nvcsw,'involuntary_context_switches':r.ru_nivcsw}


def write(path,raw,mode=0o600):
    require(len(raw)<=4*1024*1024,'single output cap');fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:require(stream.write(raw)==len(raw),'complete write')


def save(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();require(len(raw)<=512*1024,'report cap');write(path,raw)


def arm(deadline):
    remaining=deadline-time.monotonic();require(remaining>0,'probe absolute deadline exhausted');signal.setitimer(signal.ITIMER_REAL,remaining)


def expired(_signal,_frame):raise TimeoutError('probe shared pre/work/total deadline')


def stage_identity(p,g,m,pins,outer,review):
    actual=p['actual_staging'];require(isinstance(actual,dict),'ACTUAL_STAGING_REVIEW_PENDING')
    checked(review/'MANIFEST.json',actual['review_manifest']);summary=json.loads(checked(review/'SUMMARY.json',actual['review_summary']))
    require(summary['verdict']==actual['review_verdict'],'fixed staging review verdict')
    report=checked(Path(m.OUTPUT_ROOT)/'STAGING_REPORT.json',actual['staging_report'])
    receipt=json.loads(checked(outer/'RESULT.json',actual['outer_result']))
    require(receipt['status']=='STAGED_DEPENDENCY_DATA_PENDING_OUTER_EXIT0_AND_REVIEW' and receipt['terminal_success'] is False and receipt['package_tools_executed'] is False,'original stage receipt scope')
    g.postflight(m,pins,actual['stage_summary'])
    return pin(report)


def data_members(pins):
    expected={x['path']:{'bytes':x['bytes'],'sha256':x['sha256']} for pkg in pins['packages'] for x in pkg['selected']}
    expected['relocation/autom4te.cfg']=pins['derived_cfg'];require(len(expected)==68,'fixed68 data members');return expected


def copy_tools(root,stage,expected):
    root.mkdir(mode=0o700)
    for name,identity in sorted(expected.items()):
        target=root/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        mode=0o700 if name in {'usr/bin/'+x for x in TOOLS} else 0o600
        write(target,checked(stage/name,identity),mode)
    verify_copies(root,expected)


def verify_copies(root,expected):
    files=[]
    for parent,dirs,names in os.walk(root,followlinks=False):
        for name in dirs:require(not (Path(parent)/name).is_symlink(),'no copied link')
        files.extend((Path(parent)/name).relative_to(root).as_posix() for name in names)
    require(set(files)==set(expected) and len(files)==68,'exact copied68 tree')
    for name,identity in expected.items():
        path=root/name;checked(path,identity);require(stat.S_IMODE(path.stat().st_mode)==(0o700 if name in {'usr/bin/'+x for x in TOOLS} else 0o600),'copy execute allowlist')


def environment(output,stage):
    bindir=output/'tools/usr/bin';share=stage/'usr/share'
    return {'PATH':str(bindir)+':/usr/bin:/bin','LC_ALL':'C','HOME':str(output/'home'),'TMPDIR':str(output/'tmp'),'AUTOM4TE':str(bindir/'autom4te'),'M4':str(bindir/'m4'),'autom4te_perllibdir':str(share/'autoconf'),'AC_MACRODIR':str(share/'autoconf'),'trailer_m4':str(share/'autoconf/autoconf/trailer.m4'),'AUTOM4TE_CFG':str(stage/'relocation/autom4te.cfg'),'BISON_PKGDATADIR':str(share/'bison')}


def inventory(root):
    files={};directories=[];total=0
    for parent,dirs,names in os.walk(root,followlinks=False):
        require(len(files)+len(names)<=200 and len(directories)+len(dirs)<=64,'finite probe inventory')
        for name in dirs:
            path=Path(parent)/name;require(path.is_dir() and not path.is_symlink(),'no output directory links');directories.append(path.relative_to(root).as_posix())
        for name in names:
            path=Path(parent)/name;meta=path.lstat();require(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1 and meta.st_size<=4*1024*1024,'regular bounded probe output');raw=path.read_bytes();total+=len(raw);require(total<=8*1024*1024,'probe tree8MiB soft acceptance');files[path.relative_to(root).as_posix()]={**pin(raw),'mode':oct(stat.S_IMODE(meta.st_mode))}
    return {'files':files,'directories':sorted(directories),'bytes':total}


def check_probe(mode,definition,work,log):
    require(len(log)<=65536,'log64KiB')
    for marker in definition['expected_log_contains']:require(marker.encode() in log,'fixed tool version/output marker absent')
    if definition['expected_log_exact'] is not None:require(log==definition['expected_log_exact'].encode(),'exact synthetic stdout')
    for relative,spec in definition['generated_files'].items():
        require('/' not in relative and relative not in ('.','..'),'fixed generated basename');path=work/relative;meta=path.lstat();require(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1 and meta.st_size<=4*1024*1024,'fixed generated regular data')
        raw=path.read_bytes()
        for marker in spec['contains']:require(marker.encode() in raw,'synthetic generated marker absent')


def execute(args,entry):
    stop=entry+20;pre_stop=entry+4;latest_work=entry+14;created=False
    require(sys.platform=='linux','Linux getrusage units');require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked SIGALRM');require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'existing timer')
    signal.signal(signal.SIGALRM,expired);arm(pre_stop)
    try:
        p,modes,g,m,pins,projected,worker_raw=configure(clean(args.repo),clean(args.staging_gate),clean(args.worker_source));require(args.mode in modes,'fixed mode');require(isinstance(p['actual_staging'],dict),'ACTUAL_STAGING_REVIEW_PENDING')
        stage=clean(m.OUTPUT_ROOT);outer=clean(args.stage_outer);review=clean(args.stage_review);output=clean(args.output)
        require(output.parent.is_dir() and not output.exists(),'fresh output')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in [stage,outer,review,clean(args.repo),clean(args.staging_gate),clean(args.worker_source),HERE]),'disjoint probe output')
        stage_identity(p,g,m,pins,outer,review);before=usage();require(before['user_cpu_seconds']==before['system_cpu_seconds']==before['maxrss_kib']==0,'dedicated no-prior-child process')
        output.mkdir(mode=0o700);created=True
        for name in ('work','home','tmp'):(output/name).mkdir(mode=0o700)
        expected=data_members(pins);copy_tools(output/'tools',stage,expected);definition=modes[args.mode]
        for name,text in definition['fixture_files'].items():
            require('/' not in name and name not in ('.','..'),'fixed synthetic basename');write(output/'work'/name,text.encode())
        env=environment(output,stage);command=[str(output/'tools/usr/bin'/definition['tool'])]+definition['argv_tail']
        ns={'__builtins__':__builtins__,'os':os,'resource':resource,'signal':signal,'subprocess':subprocess,'time':time,'json':json,'AS_LIMIT':512*1024*1024,'CHILD_ENV':env};exec(compile(projected,'fixed_WNOWAIT_tool_probe','exec',dont_inherit=True),ns)
        save(output/'STARTED.json',{'status':'STARTED_NOT_QUALIFIED','mode':args.mode,'argv':command,'environment':env,'supervisor_projection':pin(projected),'plan_sha256':PLAN_SHA,'child_max_work_seconds':10,'total_seconds':20,'rusage_children_before':before})
        require(time.monotonic()<pre_stop,'probe preflight4s');work_stop=min(latest_work,time.monotonic()+10);arm(work_stop);failure=None;record=None;log=None
        try:record,log=ns['bounded']('probe',command,output/'work',output,work_stop-time.monotonic(),10)
        except BaseException as error:failure=error
        after=usage();arm(stop);save(output/'CHILD_USAGE.json',{'before':before,'after':after,'scope':'unique direct child including preexec; OS accumulated reaped child/descendant usage, not tool-phase attribution','maxrss_is_cumulative_peak_not_difference':True,'failure_type':None if failure is None else type(failure).__name__})
        if failure is not None:raise failure
        check_probe(args.mode,definition,output/'work',log);verify_copies(output/'tools',expected);stage_identity(p,g,m,pins,outer,review)
        p2,modes2,g2,m2,pins2,projected2,raw2=configure(clean(args.repo),clean(args.staging_gate),clean(args.worker_source));require(p2==p and modes2==modes and pins2==pins and projected2==projected and raw2==worker_raw,'original sources/plans unchanged')
        result={'status':'TOOL_PROBE_EVIDENCE_PENDING_OUTER_EXIT0_AND_REVIEW','terminal_success':False,'mode':args.mode,'child_cleanup_confirmed':record['cleanup_confirmed'],'child_exit':record['exit_code'],'original_staged_data_and_review_unchanged':True,'tool_copies_unchanged':True,'synthetic_generator_or_version_only':True,'generated_script_or_C_executed':False,'production_source_compiled':False,'elapsed_seconds':time.monotonic()-entry,'qualification_scope':'fixed version marker or tiny output generation under explicit environment only; internal consumer tracing/native build/hierarchy/DPI are unproven'}
        save(output/'RESULT.json',result)
        observed=inventory(output);observed['inventory_excludes_only_its_own_file']='OUTPUT_INVENTORY.json'
        require(observed['bytes']+len((json.dumps(observed,sort_keys=True,indent=2)+'\n').encode())<=8*1024*1024 and len(observed['files'])+1<=200,'inventory included in aggregate bound')
        save(output/'OUTPUT_INVENTORY.json',observed)
        require(time.monotonic()<stop,'post-save same20 deadline');print(json.dumps(result,sort_keys=True))
    except BaseException as error:
        if created and time.monotonic()<stop:
            try:save(output/'FAILURE.json',{'status':'INCOMPLETE_PROBE_PRESERVED','terminal_success':False,'error_type':type(error).__name__})
            except BaseException as save_error:error.add_note('failure receipt '+type(save_error).__name__)
        raise
    # Keep shared alarm armed through interpreter exit; bounded owns private group cleanup.


def main():
    entry=time.monotonic();p=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','staging-gate','worker-source'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('stage-outer','stage-review','output'):p.add_argument('--'+name,type=Path)
    p.add_argument('--mode');p.add_argument('--execute-reviewed-probe',action='store_true');args=p.parse_args()
    if args.execute_reviewed_probe:
        require(all(x is not None for x in (args.stage_outer,args.stage_review,args.output,args.mode)),'actual probe arguments');execute(args,entry)
    else:
        require(all(x is None for x in (args.stage_outer,args.stage_review,args.output,args.mode)),'source-only no actual arguments');plan,modes,*_=configure(clean(args.repo),clean(args.staging_gate),clean(args.worker_source));print(json.dumps({'status':'SOURCE_ONLY_NO_STAGED_DATA_READ_OR_NATIVE','actual_staging_review':'BOUND' if isinstance(plan['actual_staging'],dict) else 'PENDING','modes':sorted(modes)},sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use -I -S -B');main()
