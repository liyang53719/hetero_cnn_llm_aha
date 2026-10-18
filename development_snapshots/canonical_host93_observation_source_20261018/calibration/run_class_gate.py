"""One new Host93 CLASS calibration: fixed inputs, flushed progress, leader metrics."""
import argparse,ast,hashlib,json,os,resource,signal,subprocess,sys,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
PLAN_SHA='04392af34006c55a086cd0da3f550a956db81e0483943be959d9458de1675fe7'
FUNCTIONS=('require','save','group_state','observe_exit','bounded')


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def clean(path):
    path=Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path,*path.parents)),'unsafe path')
    return path


def fixed(path,pin):
    path=clean(path)
    require(path.is_file() and path.stat().st_size==pin['bytes']<=2*1024*1024,'fixed source size')
    with path.open('rb') as handle:raw=handle.read(pin['bytes']+1)
    require(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],'fixed source SHA')
    return raw


def load_plan():
    raw=(HERE/'CLASS_GATE_PLAN.json').read_bytes()
    require(sha(raw)==PLAN_SHA,'class gate plan drift')
    return json.loads(raw)


def project_supervisor(raw):
    nodes=ast.parse(raw);lines=raw.splitlines(keepends=True)
    parts={n.name:b''.join(lines[n.lineno-1:n.end_lineno]) for n in nodes.body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS}
    require(tuple(parts)==FUNCTIONS,'published function selection')
    before=parts['bounded'].decode();after=before
    edits=[('resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))','resource.setrlimit(resource.RLIMIT_FSIZE, (48 * 1024 * 1024, 48 * 1024 * 1024))'),
           ('        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))','        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n        allowed = os.sched_getaffinity(0)\n        require(bool(allowed), "empty inherited CPU affinity")\n        os.sched_setaffinity(0, {min(allowed)})'),
           ('        finally:\n            if child is not None:','        finally:\n            signal.setitimer(signal.ITIMER_REAL, 0)\n            if child is not None:'),
           ("if record['log_bytes'] > 65536:","if record['log_bytes'] > 2 * 1024 * 1024:")]
    for old,new in edits:
        require(after.count(old)==1,'fixed supervisor edit anchor');after=after.replace(old,new,1)
    reverse=after
    for old,new in reversed(edits):
        require(reverse.count(new)==1,'reverse supervisor anchor');reverse=reverse.replace(new,old,1)
    require(reverse==before,'supervisor reverse projection')
    old_timeout = 'isinstance(error, subprocess.TimeoutExpired)'
    new_timeout = 'isinstance(error, (subprocess.TimeoutExpired, TimeoutError))'
    require(after.count(old_timeout)==1,'timeout classifier anchor')
    after=after.replace(old_timeout,new_timeout,1)
    parts['bounded']=after.encode()
    observe_before=parts['observe_exit'].decode()
    anchor='        if event is not None:\n'
    require(observe_before.count(anchor)==1,'WNOWAIT sample insertion anchor')
    insert="        require(event is None or event.si_pid == child.pid, 'sample WNOWAIT anchor mismatch')\n        sample_leader(child)\n"
    observe_after=observe_before.replace(anchor,insert+anchor,1)
    require(observe_after.replace(insert,'',1)==observe_before,'sample projection reverse')
    parts['observe_exit']=observe_after.encode()
    return b'\n\n'.join(parts[name] for name in FUNCTIONS)+b'\n'


def supervisor(raw, sample_path=None):
    sample_state={'path':sample_path,'identity':None,'count':0,'next':None,'start':None}
    namespace={'__builtins__':__builtins__,'os':os,'resource':resource,'signal':signal,
               'subprocess':subprocess,'time':time,'json':json,'AS_LIMIT':4*1024*1024*1024,
               'sample_leader':lambda child:sample_leader(child,sample_state)}
    exec(compile(raw,'fixed_published_class_WNOWAIT','exec',dont_inherit=True),namespace)
    return namespace


def proc_bytes(pid,leaf):
    require(type(pid) is int and pid>0 and leaf in ('stat','status'),'fixed leader proc input')
    with open('/proc/'+str(pid)+'/'+leaf,'rb') as handle:raw=handle.read(65537)
    require(len(raw)<=65536,'leader proc file bound')
    return raw


def proc_stat(raw, pid):
    text=raw.decode('ascii');prefix,tail=text.rsplit(') ',1)
    require(prefix.split(' (',1)[0]==str(pid),'leader stat PID mismatch')
    fields=tail.split();require(len(fields)>=22,'leader stat shape')
    values={key:int(fields[index]) for key,index in (('user_ticks',11),('system_ticks',12),('starttime_ticks',19),('rss_pages',21))}
    require(all(v>=0 for v in values.values()),'negative proc metric')
    return dict(pid=pid,state=fields[0],**values)


def sample_leader(child,state):
    now=time.monotonic()
    if state['next'] is not None and now<state['next']:return
    require(state['path'] is not None,'sample sink required')
    require(state['count']<340,'leader sample row cap exceeded')
    first=proc_stat(proc_bytes(child.pid,'stat'),child.pid)
    identity=(child.pid,first['starttime_ticks'])
    if state['identity'] is None:state['identity']=identity;state['start']=now
    require(identity==state['identity'],'original leader PID/starttime changed')
    status=proc_bytes(child.pid,'status').decode('ascii')
    second=proc_stat(proc_bytes(child.pid,'stat'),child.pid)
    require((second['pid'],second['starttime_ticks'])==state['identity'],'leader identity changed across status read')
    memory={key:None for key in ('VmRSS','VmHWM')}
    for line in status.splitlines():
        key,separator,value=line.partition(':')
        if key in memory:
            fields=value.split();require(separator==':' and len(fields)==2 and fields[1]=='kB','proc memory unit')
            require(memory[key] is None,'duplicate memory metric');memory[key]=int(fields[0]);require(memory[key]>=0,'negative memory metric')
    hz=os.sysconf('SC_CLK_TCK');require(type(hz) is int and hz>0,'clock ticks')
    row=dict(second,sample_number=state['count']+1,elapsed_from_first_sample_seconds=now-state['start'],
             user_cpu_seconds=second['user_ticks']/hz,system_cpu_seconds=second['system_ticks']/hz,
             clock_ticks_per_second=hz,vmrss_kib=memory['VmRSS'],vmhwm_kib=memory['VmHWM'],
             scope='original unreaped leader PID process counters; excludes descendant processes')
    raw=(json.dumps(row,sort_keys=True)+'\n').encode('ascii');require(len(raw)<=2048,'leader sample line cap')
    mode='xb' if state['count']==0 else 'ab'
    with state['path'].open(mode) as stream:stream.write(raw);stream.flush()
    state['count']+=1;state['next']=now+1


def usage():
    r=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'user_cpu_seconds':r.ru_utime,'system_cpu_seconds':r.ru_stime,
            'maxrss_kib':r.ru_maxrss,'major_faults':r.ru_majflt,'minor_faults':r.ru_minflt,
            'voluntary_context_switches':r.ru_nvcsw,'involuntary_context_switches':r.ru_nivcsw}


def configuration(repo):
    plan=load_plan();repo=clean(repo);buffers={}
    for label,pin in plan['project_files'].items():
        buffers[label]=fixed(repo/pin['repository_path'],{k:pin[k] for k in ('bytes','sha256')})
    sources=json.loads(buffers['source_plan']);jars=json.loads(buffers['jar_plan']);deps=json.loads(buffers['dependency_pins'])
    require(len(sources['expected93'])==93 and sources['source_count']==93 and sources['bench_sources']==[],'new93 exact closure')
    require(len(jars['artifacts'])==87 and {p['relative_destination']:p['sha256'] for p in jars['artifacts']}==deps['jars'],'exact87 closure')
    return plan,sources,jars,deps,project_supervisor(buffers['supervisor'])


def verified_file(path,expected_sha,cap,target=None,known_size=None):
    path=clean(path);require(path.is_file() and path.stat().st_size<=cap,'regular input cap')
    h=hashlib.sha256();count=0
    destination=None
    try:
        if target is not None:
            target.parent.mkdir(parents=True,exist_ok=True);destination=target.open('xb')
        with path.open('rb') as source:
            while True:
                raw=source.read(min(65536,cap-count+1))
                if not raw:break
                count+=len(raw);require(count<=cap,'input grew over cap');h.update(raw)
                if destination is not None:destination.write(raw)
    finally:
        if destination is not None:destination.close()
    require(h.hexdigest()==expected_sha and known_size in (None,count),'actual input identity')
    return count


def exact_sources(root,expected):
    entries=list(root.rglob('*'))
    require(not any(p.is_symlink() for p in entries),'source symlink')
    require({p.relative_to(root).as_posix() for p in entries if p.is_file()}==set(expected),'exact93 source inventory')
    require(sum(p.stat().st_size for p in entries if p.is_file())<=32*1024*1024,'source aggregate cap before snapshot')


def source_receipt(assembled,sources):
    path=clean(assembled/'SOURCE_RECEIPT.json');require(path.is_file() and path.stat().st_size<=65536,'source receipt cap')
    raw=path.read_bytes();receipt=json.loads(raw)
    require(receipt['status']=='PASS_NEW_DERIVED_HOST93_SOURCE_ONLY' and receipt['source_count']==93 and receipt['source_sha256']==sources['expected93'],'source receipt exact93')
    require(receipt['recipe_sha256']==load_plan()['project_files']['source_plan']['sha256'],'source recipe identity')
    for name in ('historical95_identity_inherited','compiler_started','elaboration_started','rtl_generated','hardware_executed'):
        require(receipt[name] is False,'source receipt unearned stage')
    return sha(raw)


def command(java,cache,classes,source,expected,jars):
    cp=':'.join(str(cache/p['relative_destination']) for p in sorted(jars['artifacts'],key=lambda p:p['relative_destination']))
    plugin=cache/'org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
    return [str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,
            '-Xplugin:'+str(plugin),'-language:reflectiveCalls','-verbose','-d',str(classes)]+[str(source/name) for name in sorted(expected)]


DEADLINE_PHASE='unarmed'


def arm(stop, phase='postflight'):
    global DEADLINE_PHASE
    DEADLINE_PHASE=phase
    remaining=stop-time.monotonic();require(remaining>0,'absolute CLASS budget exhausted')
    signal.setitimer(signal.ITIMER_REAL,remaining)


def expired(_signal,_frame):raise TimeoutError('CLASS '+DEADLINE_PHASE+' deadline')


def execute(args,entry):
    stop=entry+330;preflight_stop=entry+20;work_stop=entry+320
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'inherited timer refused')
    previous=signal.signal(signal.SIGALRM,expired);runner=None;created=False
    try:
        arm(preflight_stop,'preflight20s')
        plan,sources,jars,deps,projected=configuration(args.repo)
        assembled=clean(args.assembled_source);jar_root=clean(args.jar_artifacts);java=clean(args.java);output=clean(args.output)
        require(output.parent.is_dir() and not output.exists(),'fresh output required')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (clean(args.repo),assembled,jar_root,HERE)),'disjoint class output')
        receipt_sha=source_receipt(assembled,sources);exact_sources(assembled/'scala',sources['expected93'])
        verified_file(java,deps['java_sha256'],1024*1024)
        verified_file(java.parent.parent/'release',deps['java_release_sha256'],1024*1024)
        output.mkdir(mode=0o700);created=True
        source=output/'scala';cache=output/'dependencies';classes=output/'classes';classes.mkdir()
        source_bytes=sum(verified_file(assembled/'scala'/name,digest,2*1024*1024,source/name) for name,digest in sorted(sources['expected93'].items()))
        require(source_bytes<=32*1024*1024,'source aggregate cap')
        jar_bytes=sum(verified_file(jar_root/p['relative_destination'],p['sha256'],p['max_transfer_bytes']-1,cache/p['relative_destination'],p['known_size_bytes']) for p in jars['artifacts'])
        require(jar_bytes<=512*1024*1024,'jar aggregate cap')
        before=usage();require(before['user_cpu_seconds']==0 and before['system_cpu_seconds']==0 and before['maxrss_kib']==0,'dedicated process must have no prior child usage')
        runner=supervisor(projected,output/'leader_samples.jsonl')
        argv=command(java,cache,classes,source,sources['expected93'],jars)
        runner['save'](output/'INPUTS.json',{'status':'PREPARED_NOT_COMPILED','source_receipt_sha256':receipt_sha,'source_sha256':sources['expected93'],'source_bytes':source_bytes,'jar_bytes':jar_bytes,'jar_count':87,'argv':argv,'gate_plan_sha256':PLAN_SHA,'supervisor_projection_sha256':sha(projected)})
        require(time.monotonic()<preflight_stop,'20s preflight start budget exhausted')
        compile_stop=min(work_stop,time.monotonic()+300);arm(compile_stop,'compile_work300s')
        failure=None;record=None
        try:record,_=runner['bounded']('compile',argv,output,output,compile_stop-time.monotonic(),300)
        except BaseException as error:failure=error
        after=usage()  # Unique child scope after original WNOWAIT cleanup/reap.
        arm(stop,'postflight330s')
        runner['save'](output/'CHILD_USAGE.json',{'status':'OBSERVATION_ONLY_NOT_CLASS_PASS','before':before,'after':after,
            'maxrss_is_cumulative_peak_not_difference':True,'linux_maxrss_unit':'KiB',
            'scope':'only reaped child including preexec and entire JVM; not compiler phase-specific',
            'failure_type':None if failure is None else type(failure).__name__,'cleanup_receipt':'compile.json'})
        if failure is not None:raise failure
        # New snapshot bytes, rather than live originals, were the compiler's only CP/source.
        exact_sources(source,sources['expected93'])
        for name,digest in sources['expected93'].items():verified_file(source/name,digest,2*1024*1024)
        for p in jars['artifacts']:verified_file(cache/p['relative_destination'],p['sha256'],p['max_transfer_bytes']-1,known_size=p['known_size_bytes'])
        verified_file(java,deps['java_sha256'],1024*1024);verified_file(java.parent.parent/'release',deps['java_release_sha256'],1024*1024)
        entries=list(classes.rglob('*'));require(not any(p.is_symlink() for p in entries),'class symlink')
        files=[p for p in entries if p.is_file()]
        require(bool(files) and all(p.suffix=='.class' for p in files),'only fresh classes')
        total=sum(p.stat().st_size for p in files);require(total<=64*1024*1024,'class tree acceptance cap')
        identity={p.relative_to(classes).as_posix():sha(p.read_bytes()) for p in sorted(files)}
        expected_emitter='heteronpu/continuous/EmitCanonicalHost93$.class'
        require(expected_emitter in identity,'new Host93 emitter class absent')
        result={'status':'CLASS_EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,'class_count':len(identity),'class_bytes':total,'classes_sha256':identity,'entry_to_postflight_seconds':time.monotonic()-entry,'cleanup_confirmed':record['cleanup_confirmed'],'source_count':93,'jar_count':87,'hardware_elaborated':False,'rtl_generated':False,'host_executed':False,'historical95_identity_inherited':False,'acceptance_requires':'independent actual outer exit0, elapsed<=330, and source/CLASS review'}
        require(time.monotonic()<stop,'class final deadline')
        runner['save'](output/'RESULT.json',result)
        require(time.monotonic()<stop,'class final receipt deadline')
        return {key:value for key,value in result.items() if key!='classes_sha256'}
    except BaseException as error:
        if created and runner is not None:
            try:
                arm(stop);runner['save'](output/'FAILURE.json',{'status':'FAILED_CLASS_ATTEMPT','error_type':type(error).__name__})
            except BaseException:pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def main():
    entry=time.monotonic();parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--assembled-source',type=Path)
    parser.add_argument('--jar-artifacts',type=Path)
    parser.add_argument('--java',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--execute-reviewed-class',action='store_true')
    args=parser.parse_args()
    if args.execute_reviewed_class:
        require(all(getattr(args,key) is not None for key in ('assembled_source','jar_artifacts','java','output')),'explicit CLASS inputs/output required')
        result=execute(args,entry)
    else:
        require(all(getattr(args,key) is None for key in ('assembled_source','jar_artifacts','java','output')),'SOURCE preflight uses repository only')
        plan,sources,jars,deps,projected=configuration(args.repo)
        result={'status':'CLASS_SOURCE_PREFLIGHT_ONLY','source_count':93,'jar_count':87,'java_started':False,'supervisor_projection_sha256':sha(projected)}
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
