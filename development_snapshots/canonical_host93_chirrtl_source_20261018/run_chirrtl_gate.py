"""New Host93 CHIRRTL-only gate; fixed completed CLASS inputs and existing supervisor."""
import argparse,hashlib,json,signal,sys,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
PLAN_SHA='e6f0245132f9bd292ccd4bc60789db9d205f9aab4f29a1c7f234869285d03a21'
CALIBRATION_REL='development_snapshots/canonical_host93_observation_source_20261018/calibration'
CALIBRATION_SHA='ade8c397292fb92226e8e83d5e461112b2b4021d60e793493ad54e830c61448a'
CALIBRATION_BYTES=17327
PROJECTION_SHA='091e5d8e5588ee40576de366998e06be4357a2714a23d6be247015f79ddbf9e1'
PHASE='unarmed'


def require(ok,why):
    if not ok:raise ValueError(why)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def clean(path):
    path=Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path,*path.parents)),'unsafe path')
    return path


def fixed(path,size,sha):
    path=clean(path);require(path.is_file() and path.stat().st_size==size<=2*1024*1024,'fixed input size')
    with path.open('rb') as stream:raw=stream.read(size+1)
    require(len(raw)==size and digest(raw)==sha,'fixed input SHA')
    return raw


def load_gate(repo):
    path=clean(repo)/CALIBRATION_REL/'run_class_gate.py'
    raw=fixed(path,CALIBRATION_BYTES,CALIBRATION_SHA)
    module=types.ModuleType('fixed_calibration_source_for_CHIRRTL');module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def load_plan():
    path=HERE/'EMIT_PLAN.json';require(path.stat().st_size<=2*1024*1024,'emit plan cap')
    raw=path.read_bytes();require(digest(raw)==PLAN_SHA,'emit plan SHA')
    return json.loads(raw)


def inventory(root,expected):
    entries=list(root.rglob('*'));require(not any(p.is_symlink() for p in entries),'snapshot symlink')
    directories={str(q) for name in expected for q in Path(name).parents if str(q)!='.'}
    require({p.relative_to(root).as_posix() for p in entries if p.is_dir()}==directories,'exact snapshot directories')
    require(all(p.is_file() or p.is_dir() for p in entries),'nonregular snapshot entry')
    files=[p for p in entries if p.is_file()]
    require({p.relative_to(root).as_posix() for p in files}==set(expected),'exact snapshot inventory')
    return files


def command(java,classes,jars,jplan,structure):
    cp=':'.join([str(classes)]+[str(jars/x['relative_destination']) for x in sorted(jplan['artifacts'],key=lambda x:x['relative_destination'])])
    return [str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',cp,
            'heteronpu.continuous.EmitCanonicalHost93',str(structure)]


def arm(stop,phase):
    global PHASE
    PHASE=phase;remaining=stop-time.monotonic();require(remaining>0,'shared CHIRRTL budget exhausted')
    signal.setitimer(signal.ITIMER_REAL,remaining)


def expired(_signal,_frame):raise TimeoutError('CHIRRTL '+PHASE+' deadline')


def validate_binding(plan):
    review=plan['class_actual_review_manifest_sha256']
    require(type(review) is str and len(review)==64 and all(c in '0123456789abcdef' for c in review),'CLASS actual review is PENDING or invalid')
    require(plan['class_actual_review_state']=='CLOSED_CLASS_ONLY','actual CLASS review not closed')
    require(plan['class_count']==562 and len(plan['classes'])==562,'new exact562 closure')
    require(sum(x['bytes'] for x in plan['classes'].values())==plan['class_bytes']==9653495,'class aggregate identity')
    require(plan['emit_entry']=='heteronpu.continuous.EmitCanonicalHost93','fixed new emitter')


def execute(args,entry):
    stop=entry+90;pre_stop=entry+20;work_latest=entry+80
    require(sys.platform=='linux','Linux WNOWAIT and RSS units required')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing timer refused')
    previous=signal.signal(signal.SIGALRM,expired);created=False;runner=None
    try:
        arm(pre_stop,'preflight20s')
        plan=load_plan();validate_binding(plan);g=load_gate(args.repo)
        _,sources,jplan,deps,projected=g.configuration(args.repo)
        require(digest(projected)==PROJECTION_SHA,'unchanged reviewed supervisor projection')
        require(digest(json.dumps({n:v['sha256'] for n,v in plan['classes'].items()},sort_keys=True,separators=(',',':')).encode())==plan['classes_map_sha256'],'fixed class map identity')
        origin=clean(args.class_attempt);java=clean(args.java);output=clean(args.output)
        require(output.parent.is_dir() and not output.exists(),'fresh output required')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (clean(args.repo),origin,HERE,java.parent.parent)),'disjoint output')
        for name in ('RESULT.json','INPUTS.json'):
            pin=plan['class_receipts'][name];raw=fixed(origin/name,pin['bytes'],pin['sha256'])
            if name=='RESULT.json':
                r=json.loads(raw);require(r['classes_sha256']=={n:v['sha256'] for n,v in plan['classes'].items()} and r['source_count']==93 and r['jar_count']==87,'CLASS receipt closure')
            else:require(json.loads(raw)['source_sha256']==sources['expected93'],'CLASS actual source identity')
        g.verified_file(java,deps['java_sha256'],1024*1024);g.verified_file(java.parent.parent/'release',deps['java_release_sha256'],1024*1024)
        inventory(origin/'classes',plan['classes'])
        inventory(origin/'dependencies',{x['relative_destination'] for x in jplan['artifacts']})
        before=g.usage();require(before['user_cpu_seconds']==0 and before['system_cpu_seconds']==0 and before['maxrss_kib']==0,'dedicated process has previous child usage')
        output.mkdir(mode=0o700);created=True
        classes=output/'classes';jars=output/'dependencies';structure=output/'structure'
        for name,pin in sorted(plan['classes'].items()):g.verified_file(origin/'classes'/name,pin['sha256'],pin['bytes'],classes/name,pin['bytes'])
        jarbytes=sum(g.verified_file(origin/'dependencies'/x['relative_destination'],x['sha256'],x['max_transfer_bytes']-1,jars/x['relative_destination'],x['known_size_bytes']) for x in jplan['artifacts'])
        require(jarbytes==61870159,'exact87 aggregate bytes')
        runner=g.supervisor(projected,output/'leader_samples.jsonl');argv=command(java,classes,jars,jplan,structure)
        runner['save'](output/'INPUTS.json',{'status':'PREPARED_NOT_EMITTED','argv':argv,'emit_plan_sha256':PLAN_SHA,
            'class_review_manifest_sha256':plan['class_actual_review_manifest_sha256'],'class_count':562,'class_bytes':9653495,
            'classes_map_sha256':plan['classes_map_sha256'],'jar_count':87,'jar_bytes':jarbytes,'supervisor_projection_sha256':PROJECTION_SHA})
        require(time.monotonic()<pre_stop,'preflight20s exhausted')
        emit_stop=min(work_latest,time.monotonic()+60);arm(emit_stop,'emit_work60s')
        failure=None;record=None
        try:record,log=runner['bounded']('emit',argv,output,output,emit_stop-time.monotonic(),60)
        except BaseException as error:failure=error
        after=g.usage();arm(stop,'postflight90s')
        runner['save'](output/'CHILD_USAGE.json',{'status':'OBSERVATION_ONLY_NOT_CHIRRTL_PASS','before':before,'after':after,
            'maxrss_is_cumulative_peak_not_difference':True,'linux_maxrss_unit':'KiB','failure_type':None if failure is None else type(failure).__name__,
            'scope':'one reaped child including preexec and entire JVM; not phase-specific','cleanup_receipt':'emit.json'})
        if failure is not None:raise failure
        require(log.count(b'CANONICAL_HOST93_CHIRRTL_BEGIN ')==1 and log.count(b'CANONICAL_HOST93_CHIRRTL_WRITTEN ')==1,'exact emitter markers')
        files=inventory(structure,{'HostBlockCollection.fir'})
        require(sum(p.stat().st_size for p in files)<=64*1024*1024,'generated structure tree soft cap')
        fir=structure/'HostBlockCollection.fir';require(fir.stat().st_size<=48*1024*1024,'single FIR cap')
        for tree in (origin/'classes',classes):
            inventory(tree,plan['classes'])
            for name,pin in plan['classes'].items():g.verified_file(tree/name,pin['sha256'],pin['bytes'],known_size=pin['bytes'])
        for tree in (origin/'dependencies',jars):
            inventory(tree,{x['relative_destination'] for x in jplan['artifacts']})
            for x in jplan['artifacts']:g.verified_file(tree/x['relative_destination'],x['sha256'],x['max_transfer_bytes']-1,known_size=x['known_size_bytes'])
        for name in ('RESULT.json','INPUTS.json'):
            pin=plan['class_receipts'][name];fixed(origin/name,pin['bytes'],pin['sha256'])
        g.verified_file(java,deps['java_sha256'],1024*1024);g.verified_file(java.parent.parent/'release',deps['java_release_sha256'],1024*1024)
        expected={'INPUTS.json','CHILD_USAGE.json','emit.json','emit.log','leader_samples.jsonl','structure/HostBlockCollection.fir'}
        expected|={'classes/'+n for n in plan['classes']}
        expected|={'dependencies/'+x['relative_destination'] for x in jplan['artifacts']}
        allfiles=inventory(output,expected)
        outputs={}
        for path in sorted(allfiles):
            raw=path.read_bytes();outputs[path.relative_to(output).as_posix()]={'bytes':len(raw),'sha256':digest(raw)}
        require(outputs['structure/HostBlockCollection.fir']['bytes']<=48*1024*1024,'inventoried FIR cap')
        require(all(outputs['classes/'+n]==pin for n,pin in plan['classes'].items()),'final class inventory identity')
        require(all(outputs['dependencies/'+x['relative_destination']]['sha256']==x['sha256'] for x in jplan['artifacts']),'final JAR inventory identity')
        runner['save'](output/'OUTPUT_INVENTORY.json',outputs)
        inventory_sha=digest((output/'OUTPUT_INVENTORY.json').read_bytes())
        result={'status':'CHIRRTL_EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,'execution_top':'HostBlockTop',
            'emission_root':'HostBlockCollection','structure_qualification':'INCOMPLETE_REQUIRES_SAME_FIR_READ_ONLY_REVIEW','classes_count':562,'jar_count':87,
            'fir':outputs['structure/HostBlockCollection.fir'],'output_inventory_sha256':inventory_sha,
            'cleanup_confirmed':record['cleanup_confirmed'],'entry_to_postflight_seconds':time.monotonic()-entry,
            'rtl_generated':False,'firtool_executed':False,'host_executed':False,'numerical_qualification':False,
            'historical95_identity_inherited':False,'acceptance_requires':'independent actual outer exit0, elapsed<=90, exact postflight and independent CHIRRTL-only review'}
        runner['save'](output/'RESULT.json',result);require(time.monotonic()<stop,'final CHIRRTL receipt deadline')
        return result
    except BaseException as error:
        if created and runner is not None:
            try:
                arm(stop,'failure_record90s');runner['save'](output/'FAILURE.json',{'status':'FAILED_CHIRRTL_ATTEMPT','error_type':type(error).__name__})
            except BaseException:pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def main():
    entry=time.monotonic();p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True)
    for name in ('class-attempt','java','output'):p.add_argument('--'+name,type=Path)
    p.add_argument('--execute-reviewed-chirrtl',action='store_true');args=p.parse_args()
    if args.execute_reviewed_chirrtl:
        require(all(getattr(args,k) is not None for k in ('class_attempt','java','output')),'explicit actual paths required')
        result=execute(args,entry)
    else:
        require(all(getattr(args,k) is None for k in ('class_attempt','java','output')),'source-only preflight takes repository only')
        plan=load_plan();g=load_gate(args.repo);projected=g.configuration(args.repo)[4]
        require(digest(projected)==PROJECTION_SHA,'supervisor projection')
        result={'status':'CHIRRTL_SOURCE_PREFLIGHT_ONLY','class_actual_review_state':plan['class_actual_review_state'],'java_started':False,'rtl_generated':False}
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
