"""New Host93 CLASS-only candidate: fresh exact inputs, one fixed Scala compiler."""
import argparse,ast,hashlib,json,os,resource,signal,subprocess,sys,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
PLAN_SHA='3673beb1187d1830c1a43e00e27816e97aff129d571767f3e3ac7f6f9c65c3a9'
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
    parts['bounded']=after.encode()
    return b'\n\n'.join(parts[name] for name in FUNCTIONS)+b'\n'


def supervisor(raw):
    namespace={'__builtins__':__builtins__,'os':os,'resource':resource,'signal':signal,
               'subprocess':subprocess,'time':time,'json':json,'AS_LIMIT':4*1024*1024*1024}
    exec(compile(raw,'fixed_published_class_WNOWAIT','exec',dont_inherit=True),namespace)
    return namespace


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
            '-Xplugin:'+str(plugin),'-language:reflectiveCalls','-d',str(classes)]+[str(source/name) for name in sorted(expected)]


def arm(stop):
    remaining=stop-time.monotonic();require(remaining>0,'absolute CLASS budget exhausted')
    signal.setitimer(signal.ITIMER_REAL,remaining)


def expired(_signal,_frame):raise TimeoutError('absolute150s CLASS deadline')


def execute(args,entry):
    stop=entry+150;preflight_stop=entry+20;work_stop=entry+140
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'inherited timer refused')
    previous=signal.signal(signal.SIGALRM,expired);runner=None;created=False
    try:
        arm(preflight_stop)
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
        runner=supervisor(projected)
        argv=command(java,cache,classes,source,sources['expected93'],jars)
        runner['save'](output/'INPUTS.json',{'status':'PREPARED_NOT_COMPILED','source_receipt_sha256':receipt_sha,'source_sha256':sources['expected93'],'source_bytes':source_bytes,'jar_bytes':jar_bytes,'jar_count':87,'argv':argv,'gate_plan_sha256':PLAN_SHA,'supervisor_projection_sha256':sha(projected)})
        require(time.monotonic()<preflight_stop,'20s preflight start budget exhausted')
        compile_stop=min(work_stop,time.monotonic()+120);arm(compile_stop)
        failure=None;record=None
        try:record,_=runner['bounded']('compile',argv,output,output,compile_stop-time.monotonic(),120)
        except BaseException as error:failure=error
        arm(stop)
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
        result={'status':'CLASS_EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,'class_count':len(identity),'class_bytes':total,'classes_sha256':identity,'entry_to_postflight_seconds':time.monotonic()-entry,'cleanup_confirmed':record['cleanup_confirmed'],'source_count':93,'jar_count':87,'hardware_elaborated':False,'rtl_generated':False,'host_executed':False,'historical95_identity_inherited':False,'acceptance_requires':'independent actual outer exit0, elapsed<=150, and source/CLASS review'}
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
