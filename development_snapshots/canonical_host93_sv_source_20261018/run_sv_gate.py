"""Fixed same-FIR single-SV generation; no SV semantic checker or Host execution."""
import argparse,hashlib,json,os,signal,stat,sys,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
PLAN_SHA='c8da8a818821ece4d276f1c2ba64f1e14c511487dfbaa304a5255d3e03d02d34'
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
    path=clean(path);require(type(size) is int and path.is_file() and path.stat().st_size==size<=2*1024*1024,'fixed input size')
    with path.open('rb') as stream:raw=stream.read(size+1)
    require(len(raw)==size and digest(raw)==sha,'fixed input SHA')
    return raw


def load_gate(repo):
    path=clean(repo)/CALIBRATION_REL/'run_class_gate.py'
    raw=fixed(path,CALIBRATION_BYTES,CALIBRATION_SHA)
    module=types.ModuleType('fixed_calibration_source_for_SV');module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def load_plan():
    path=clean(HERE/'SV_PLAN.json');require(path.is_file() and path.stat().st_size<=2*1024*1024,'SV plan cap')
    raw=path.read_bytes();require(digest(raw)==PLAN_SHA,'SV plan SHA')
    return json.loads(raw)


def native_projection(projected):
    require(digest(projected)==PROJECTION_SHA,'unchanged reviewed supervisor projection')
    old=b'resource.setrlimit(resource.RLIMIT_FSIZE, (48 * 1024 * 1024, 48 * 1024 * 1024))'
    new=b'resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024 * 1024, 128 * 1024 * 1024))'
    require(projected.count(old)==1,'native FSIZE projection anchor')
    raw=projected.replace(old,new,1)
    require(raw.replace(new,old,1)==projected,'native FSIZE reverse projection')
    return raw


def native_supervisor(g,raw,sample_path):
    # Same five reviewed lifecycle functions and exact calibration sampler.
    # No JVM runtime limit is inherited: the native namespace supplies 2 GiB.
    sample_state={'path':sample_path,'identity':None,'count':0,'next':None,'start':None}
    namespace={'__builtins__':__builtins__,'os':g.os,'resource':g.resource,'signal':g.signal,
               'subprocess':g.subprocess,'time':g.time,'json':g.json,'AS_LIMIT':2*1024*1024*1024,
               'sample_leader':lambda child:g.sample_leader(child,sample_state)}
    exec(compile(raw,'fixed_published_native_SV_WNOWAIT','exec',dont_inherit=True),namespace)
    return namespace


def valid_sha(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def validate_binding(plan):
    tool=plan['firtool']
    require(tool['actual_review_state']=='CLOSED_FIXED_FIRTOOL_MEMBER_ONLY','firtool actual review PENDING or not closed')
    require(type(tool['bytes']) is int and 0<tool['bytes']<=32*1024*1024,'actual firtool member bytes PENDING or invalid')
    require(tool['sha256']=='7f52d2a3782d09736895f66e7eb0e5cc4b3b1b18aa1ad0d04fca4cd6e42cd2ee','fixed firtool SHA')
    require(tool['relative_binary']=='artifacts/firtool' and tool['version']=='1.62.1','fixed acquired member')
    for name in ('attempt_path','review_path'):
        require(type(tool[name]) is str and tool[name].startswith('/'),'actual firtool path PENDING')
    require(set(tool['attempt_files'])=={'RESULT.json','artifacts/MEMBER.json','artifacts/ACQUISITION.json'},'fixed acquisition receipt set')
    require(set(tool['review_files'])=={'MANIFEST.json','SUMMARY.json'},'fixed acquisition review set')
    for pin in list(tool['attempt_files'].values())+list(tool['review_files'].values()):
        require(set(pin)=={'bytes','sha256'} and type(pin['bytes']) is int and 0<pin['bytes']<=2*1024*1024 and valid_sha(pin['sha256']),'actual firtool receipt pin PENDING')
    claims=tool['review_summary_claims']
    require(type(claims) is dict and claims.get('outer_exit')==0 and claims.get('binary_executed') is False and type(claims.get('verdict')) is str and claims['verdict'].startswith('PASS_'),'actual firtool review claims PENDING')
    require(plan['structure_review']['state']=='CLOSED_CHIRRTL_STATIC_STRUCTURE_ONLY','CHIRRTL review closure')


def verify_receipts(plan,attempt,tool_review,structure_review):
    tool=plan['firtool'];loaded={}
    for root,pins,label in ((attempt,tool['attempt_files'],'attempt'),(tool_review,tool['review_files'],'tool_review'),(structure_review,plan['structure_review']['files'],'structure_review')):
        for name,pin in pins.items():loaded[label+'/'+name]=json.loads(fixed(root/name,pin['bytes'],pin['sha256']))
    member=loaded['attempt/artifacts/MEMBER.json'];acquired=loaded['attempt/RESULT.json']
    require(member['status']=='MEMBER_BYTES_PREPARED_PENDING_OUTER_EXIT0' and member['terminal_success'] is False,'member nonterminal evidence')
    require(member['member_name']==tool['member_name'] and member['extracted_member_count']==1 and member['binary_relative_destination']=='firtool','single allowlist member identity')
    require(member['binary_sha256']==tool['sha256'] and member['binary_bytes']==tool['bytes'] and member['binary_mode_octal']=='0600','new actual member bytes')
    require(member['archive_sha256']==tool['archive_sha256'] and member['archive_receipt_sha256']==tool['attempt_files']['artifacts/ACQUISITION.json']['sha256'],'new acquisition lineage')
    require(acquired['member']==member and acquired['terminal_success'] is False and acquired['child_cleanup_confirmed'] is True,'acquisition final evidence binding')
    for value in (member,acquired):
        require(value['binary_executed'] is False and value['installed'] is False,'binary was not installed or executed by acquisition')
    summary=loaded['tool_review/SUMMARY.json']
    require(all(summary.get(k)==v for k,v in tool['review_summary_claims'].items()),'fixed actual acquisition acceptance')
    require(loaded['tool_review/MANIFEST.json']['files']['SUMMARY.json']==tool['review_files']['SUMMARY.json'],'review summary membership')
    summary=loaded['structure_review/SUMMARY.json'];structure=summary['structure']
    require(summary['verdict']=='PASS_ACTUAL_SAME_FIR_CHIRRTL_STATIC_STRUCTURE_ONLY' and summary['accepted_by_combining_saved_outer0_time_and_independent_review'] is True and summary['outer_exit']==0,'same FIR structure accepted')
    require(summary['runtime_or_functional_qualification'] is False and structure['host_port_count']==83 and structure['metadata_direct_request_response_routes']==8,'CHIRRTL scope')
    require(loaded['structure_review/FIR_CURRENT_IDENTITY.json']['identity']=={k:plan['fir'][k] for k in ('bytes','sha256')},'review same FIR identity')
    require(loaded['structure_review/MANIFEST.json']['files']['SUMMARY.json']==plan['structure_review']['files']['SUMMARY.json'],'CHIRRTL summary membership')


def inventory(root,expected):
    root=clean(root);require(root.is_dir(),'inventory root directory');files=[];directories=set();entries=0;total=0;pending=[root]
    while pending:
        folder=pending.pop()
        with os.scandir(folder) as scan:
            for entry in scan:
                entries+=1;require(entries<=64,'finite inventory entry cap')
                path=Path(entry.path);mode=entry.stat(follow_symlinks=False).st_mode
                require(not entry.is_symlink(),'inventory symlink')
                if stat.S_ISDIR(mode):directories.add(path.relative_to(root).as_posix());pending.append(path)
                else:
                    require(stat.S_ISREG(mode),'nonregular inventory entry');files.append(path)
                    require(len(files)<=32,'finite inventory file cap');size=entry.stat(follow_symlinks=False).st_size
                    require(size<=128*1024*1024,'inventory per-file hard-policy boundary');total+=size
                    require(total<=256*1024*1024,'tree postflight soft acceptance cap')
    expected=set(expected);wanted_dirs={str(q) for name in expected for q in Path(name).parents if str(q)!='.'}
    require(directories==wanted_dirs,'exact inventory directories')
    require({p.relative_to(root).as_posix() for p in files}==expected,'exact finite inventory files')
    return files


def file_identity(path):
    path=clean(path);size=path.stat().st_size;require(path.is_file() and 0<=size<=128*1024*1024,'bounded output hash input')
    count=0;h=hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            raw=stream.read(min(65536,size-count+1))
            if not raw:break
            count+=len(raw);require(count<=size,'output grew while hashing');h.update(raw)
    require(count==size==path.stat().st_size,'output size changed while hashing')
    return {'bytes':count,'sha256':h.hexdigest()}


def command(binary,fir,rtl):
    return [str(binary),'-format=fir',str(fir),'-o',str(rtl/'HostBlockCollection.sv'),
            '-warn-on-unprocessed-annotations','-output-annotation-file',str(rtl/'circt.anno.json'),
            '--preserve-values=all','-disable-all-randomization','--verbose-pass-executions']


def arm(stop,phase):
    global PHASE
    PHASE=phase;remaining=stop-time.monotonic();require(remaining>0,'shared SV budget exhausted')
    signal.setitimer(signal.ITIMER_REAL,remaining)


def expired(_signal,_frame):raise TimeoutError('SV '+PHASE+' deadline')


def execute(args,entry):
    stop=entry+180;pre_stop=entry+10;work_latest=entry+160
    require(sys.platform=='linux','Linux WNOWAIT and RSS units required')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing timer refused')
    previous=signal.signal(signal.SIGALRM,expired);created=False;runner=None
    try:
        arm(pre_stop,'preflight10s')
        plan=load_plan();validate_binding(plan);g=load_gate(args.repo)
        projected=native_projection(g.configuration(args.repo)[4])
        fir=clean(args.fir);attempt=clean(args.firtool_attempt);tool_review=clean(args.firtool_review);structure_review=clean(args.structure_review);output=clean(args.output)
        require(str(fir)==plan['fir']['origin_path'] and str(attempt)==plan['firtool']['attempt_path'] and str(tool_review)==plan['firtool']['review_path'] and str(structure_review)==plan['structure_review']['path'],'explicit original actual paths required')
        binary=clean(attempt/plan['firtool']['relative_binary']);tool=plan['firtool']
        require(output.parent.is_dir() and not output.exists(),'fresh output required')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (clean(args.repo),fir.parent,attempt,tool_review,structure_review,HERE)),'disjoint output')
        verify_receipts(plan,attempt,tool_review,structure_review)
        require((binary.stat().st_mode&0o7777)==0o600,'actual acquired binary must remain0600')
        g.verified_file(fir,plan['fir']['sha256'],plan['fir']['bytes'],known_size=plan['fir']['bytes'])
        g.verified_file(binary,tool['sha256'],tool['bytes'],known_size=tool['bytes'])
        before=g.usage();require(before['user_cpu_seconds']==0 and before['system_cpu_seconds']==0 and before['maxrss_kib']==0,'dedicated process has previous child usage')
        output.mkdir(mode=0o700);created=True
        runner=native_supervisor(g,projected,output/'leader_samples.jsonl')
        frozen_fir=output/'inputs/HostBlockCollection.fir';frozen_tool=output/'tool/firtool';rtl=output/'rtl';rtl.mkdir()
        g.verified_file(fir,plan['fir']['sha256'],plan['fir']['bytes'],frozen_fir,plan['fir']['bytes'])
        g.verified_file(binary,tool['sha256'],tool['bytes'],frozen_tool,tool['bytes'])
        for path,pin in ((frozen_fir,plan['fir']),(frozen_tool,tool)):
            g.verified_file(path,pin['sha256'],pin['bytes'],known_size=pin['bytes'])
        frozen_tool.chmod(0o700);require((frozen_tool.stat().st_mode&0o7777)==0o700,'private snapshot execute mode')
        argv=command(frozen_tool,frozen_fir,rtl)
        runner['save'](output/'INPUTS.json',{'status':'PREPARED_NOT_GENERATED','argv':argv,'sv_plan_sha256':PLAN_SHA,
            'fir':{k:plan['fir'][k] for k in ('bytes','sha256')},'firtool':{k:tool[k] for k in ('bytes','sha256')},
            'firtool_actual_review_manifest_sha256':tool['review_files']['MANIFEST.json']['sha256'],
            'structure_actual_review_manifest_sha256':plan['structure_review']['files']['MANIFEST.json']['sha256'],
            'base_supervisor_projection_sha256':PROJECTION_SHA,'native_supervisor_projection_sha256':digest(projected),
            'budgets':plan['budgets'],'original_binary_mode':'0600','fresh_snapshot_binary_mode':'0700'})
        require(time.monotonic()<pre_stop,'preflight10s exhausted')
        tool_stop=min(work_latest,time.monotonic()+150);arm(tool_stop,'firtool_work150s')
        failure=None;record=None
        try:record,_=runner['bounded']('firtool',argv,output,output,tool_stop-time.monotonic(),150)
        except BaseException as error:failure=error
        after=g.usage();arm(stop,'postflight180s')
        runner['save'](output/'CHILD_USAGE.json',{'status':'OBSERVATION_ONLY_NOT_SV_PASS','before':before,'after':after,
            'maxrss_is_cumulative_peak_not_difference':True,'linux_maxrss_unit':'KiB','failure_type':None if failure is None else type(failure).__name__,
            'scope':'one reaped native child including preexec; not pass-specific','cleanup_receipt':'firtool.json'})
        if failure is not None:raise failure
        require(record['cleanup_confirmed'] is True,'native cleanup required')
        rtl_expected={'HostBlockCollection.sv'}
        if (rtl/'circt.anno.json').exists():rtl_expected.add('circt.anno.json')
        inventory(rtl,rtl_expected)
        require((rtl/'HostBlockCollection.sv').stat().st_size>0,'nonempty generated single SV required')
        if 'circt.anno.json' in rtl_expected:require((rtl/'circt.anno.json').stat().st_size<=32*1024*1024,'annotation file soft cap')
        for path,pin in ((fir,plan['fir']),(frozen_fir,plan['fir']),(binary,tool),(frozen_tool,tool)):
            g.verified_file(path,pin['sha256'],pin['bytes'],known_size=pin['bytes'])
        require((binary.stat().st_mode&0o7777)==0o600 and (frozen_tool.stat().st_mode&0o7777)==0o700,'binary modes preserved')
        verify_receipts(plan,attempt,tool_review,structure_review)
        expected={'INPUTS.json','CHILD_USAGE.json','firtool.json','firtool.log','leader_samples.jsonl','inputs/HostBlockCollection.fir','tool/firtool'}|{'rtl/'+name for name in rtl_expected}
        outputs={p.relative_to(output).as_posix():file_identity(p) for p in sorted(inventory(output,expected))}
        require(outputs['firtool.log']['bytes']<=2*1024*1024,'postflight log soft cap')
        for name,pin in (('inputs/HostBlockCollection.fir',plan['fir']),('tool/firtool',tool)):
            require(outputs[name]=={k:pin[k] for k in ('bytes','sha256')},'final snapshot inventory identity')
        runner['save'](output/'OUTPUT_INVENTORY.json',outputs)
        result={'status':'SV_EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,'execution_top':'HostBlockTop','emission_root':'HostBlockCollection',
            'sv_static_structure_qualification':'INCOMPLETE_REQUIRES_SAME_SV_HOST83_RESOURCE8_TAP_REVIEW','fir':outputs['inputs/HostBlockCollection.fir'],
            'sv':outputs['rtl/HostBlockCollection.sv'],'annotation':outputs.get('rtl/circt.anno.json'),
            'output_inventory_sha256':file_identity(output/'OUTPUT_INVENTORY.json')['sha256'],
            'inventory_hash_excludes_self_and_final_receipt':['OUTPUT_INVENTORY.json','RESULT.json'],
            'final_exact_path_count':len(expected)+2,'cleanup_confirmed':record['cleanup_confirmed'],'entry_to_postflight_seconds':time.monotonic()-entry,
            'rtl_generated':True,'firtool_executed':True,'host_executed':False,'numerical_qualification':False,'historical95_identity_inherited':False,
            'limits_boundary':'AS/CPU/FSIZE/affinity are child hard limits; tree256MiB/log2MiB/annotation32MiB are postflight soft acceptance checks',
            'acceptance_requires':'independent actual outer exit0, elapsed<=180, exact postflight inventory and independent SV-generation-only review; same-SV static structure remains INCOMPLETE'}
        runner['save'](output/'RESULT.json',result)
        inventory(output,expected|{'OUTPUT_INVENTORY.json','RESULT.json'})
        require(time.monotonic()<stop,'final SV receipt deadline')
        return result
    except BaseException as error:
        if created and runner is not None:
            try:
                arm(stop,'failure_record180s');runner['save'](output/'FAILURE.json',{'status':'FAILED_SV_ATTEMPT','error_type':type(error).__name__})
            except BaseException:pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def main():
    entry=time.monotonic();p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True)
    paths=('fir','firtool-attempt','firtool-review','structure-review','output')
    for name in paths:p.add_argument('--'+name,type=Path)
    p.add_argument('--execute-reviewed-sv',action='store_true');args=p.parse_args()
    if args.execute_reviewed_sv:
        require(all(getattr(args,k.replace('-','_')) is not None for k in paths),'explicit actual paths required')
        result=execute(args,entry)
    else:
        require(all(getattr(args,k.replace('-','_')) is None for k in paths),'source-only preflight takes repository only')
        plan=load_plan();g=load_gate(args.repo);projected=native_projection(g.configuration(args.repo)[4])
        result={'status':'SV_SOURCE_PREFLIGHT_ONLY','firtool_actual_review_state':plan['firtool']['actual_review_state'],
                'native_supervisor_projection_sha256':digest(projected),'firtool_started':False,'rtl_generated':False}
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
