"""Reuse-only worker. Invoked solely by one-use supervised launch.py."""
import argparse,ctypes,hashlib,json,os,resource,signal,struct,sys,time,types
from pathlib import Path
from importlib.machinery import ModuleSpec
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from harness import need,digest,load_exact,run_owner,compare_original,compare_arms
from admission import validate_review
from stage_clock import Stages
from selective_binding import compare_three
from stability import CANONICAL, ORDERS, canonical_arms
from artifacts import persist_words, persist_fields
from runtime_closure import verify_graph
from module_inventory import collect_modules,persist_and_validate


def check_manifest(config):
    need(config['commit']=='e8375f64d861c45fea3fbd6d445e5c213ff895a6','published owner binding')
    need(config['profile']=='real_attention_m2_rotated_identity_stability_v1' and config['rows']==2,'profile')
    need(config['arms']==list(CANONICAL) and config['arm_orders']==[list(x) for x in ORDERS],'exact cyclic stability orders')
    need(config['source_manifest_sha256']==digest(config['source_manifest']),'complete current source manifest')
    source=json.loads(Path(config['source_manifest']).read_text())
    root=Path(config['source_root'])
    need({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}==set(source['source_files']),'complete current source closure')
    for rel,pin in source['source_files'].items():
        need(config['files'][str(root/rel)]==pin,'current source pin differs')
    need(all(config[k] in config['files'] for k in ('committed_source_witness','committed_source_manifest')),'same committed witness pins')
    for name,pin in config['files'].items():
        p=Path(name);need(p.is_absolute() and p.resolve()==p and p.is_file(),'unaliased pinned input')
        need(p.stat().st_size==pin['bytes'] and digest(p)==pin['sha256'],'file drift '+name)
    need(config['elf'] in config['files'],'ELF pin')
    need(str(Path(sys.executable).resolve()) in config['files'],'interpreter pin')
    need(set(config['inputs'])=={'qr','kr','v'},'only declared component inputs')
    need(all(v['path'] in config['files'] for v in config['inputs'].values()),'input pins')
    graph=config['runtime_graph']
    need(hashlib.sha256((json.dumps(graph,indent=2)+'\n').encode()).hexdigest()==config['runtime_graph_sha256'],'runtime graph identity')
    verify_graph(graph,config['files'])
    need(config['git_environment']['GIT_DIR']==str(Path(config['git_environment']['GIT_DIR']).resolve()),'real Git path')


def process_identity():
    fields=Path('/proc/self/stat').read_text().split(') ',1)[1].split()
    return dict(pid=os.getpid(),ppid=os.getppid(),pgid=os.getpgrp(),start_ticks=int(fields[19]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())


class Isolation:
    def __init__(self,config):self.config=config;self.terminal=False;self.integrity=False;self.loads=[]
    def audit(self,event,args):
        if event=='ctypes.dlopen':
            need(args[0] in (None,self.config['elf']),'unapproved native load');self.loads.append(args[0])
        if event=='subprocess.Popen':
            executable,argv,cwd,env=args
            need(executable in ('git','/usr/bin/git') and os.environ.get('PATH')=='/usr/bin:/bin' and argv in (['git','show','HEAD:chisel/continuous_prefill/tests/qwen2_block.cpp'],['git','rev-parse','HEAD']),'only original read-only Git source queries')
        if event.startswith('socket.') or event in ('os.system','os.exec','os.spawn'):raise ValueError('network/process outside profile')
        if event=='import' and args[0].split('.')[0] in ('torch','transformers'):raise ValueError('official oracle import forbidden')
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(os.fsdecode(args[0]));mode=args[1];flags=args[2]
            if path.suffix=='.pyc' and not flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):raise PermissionError('source-only import cache policy')
            # Prevent reading any reference data except the three explicitly
            # declared operator inputs, even after terminal comparison.
            if path.suffix in ('.f32le','.bf16le','.npz','.bin'):
                need(str(path) in {x['path'] for x in self.config['inputs'].values()} or (self.terminal and self.integrity and str(path) in self.config['files']), 'reference/weight payload outside component input boundary')
            if not self.terminal and str(path) in ({self.config['oracle_harness'],*(spec['path'] for spec in self.config['reference_sources'].values())}-{self.config['exact_helper'],self.config['buffer_source']}):
                raise ValueError('independent reference before DUT terminal')


def load_library(config,out):
    binary=Path(config['elf']);need(digest(binary)==config['files'][str(binary)]['sha256'],'ELF before load')
    lib=ctypes.CDLL(str(binary));(Path(out)/'MAPS_AFTER_CDLL.txt').write_text(Path('/proc/self/maps').read_text());need(Path(lib._name).resolve()==binary,'CDLL identity')
    class DlInfo(ctypes.Structure):
        _fields_=[('name',ctypes.c_char_p),('base',ctypes.c_void_p),('symbol',ctypes.c_char_p),('address',ctypes.c_void_p)]
    system=ctypes.CDLL(None);system.dladdr.argtypes=[ctypes.c_void_p,ctypes.POINTER(DlInfo)];system.dladdr.restype=ctypes.c_int
    info=DlInfo();need(system.dladdr(ctypes.cast(lib.matrix_normal_step,ctypes.c_void_p),ctypes.byref(info))!=0,'resolved symbol')
    need(Path(os.fsdecode(info.name)).resolve()==binary,'symbol ELF identity')
    st=binary.stat();found=False;math=[]
    for line in Path('/proc/self/maps').read_text().splitlines():
        parts=line.split(maxsplit=5)
        if len(parts)!=6:continue
        path=parts[5]
        if path==str(binary):
            need(int(parts[4])==st.st_ino,'mapped ELF inode');found=True
        if path.startswith('/') and Path(path).name.startswith(('libc.so','libm.so','libstdc++','libgcc_s')):
            need(path in config['files'],'unbound math runtime');need(digest(path)==config['files'][path]['sha256'],'math runtime drift');math.append(path)
    need(found and any(Path(p).name.startswith('libm.so') for p in math),'ELF and math mappings')
    return lib,dict(elf_sha256=digest(binary),inode=st.st_ino,device=st.st_dev,math_runtime=sorted(set(math)))


def emit(out,stage,details):
    record=dict(stage=stage,monotonic=time.monotonic(),details=details)
    with (Path(out)/'STAGES.jsonl').open('a') as stream:
        stream.write(json.dumps(record,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())


def verify_maps(config,out,maps_text=None):
    # Persist the complete snapshot BEFORE any per-mapping check can fail.
    raw=Path('/proc/self/maps').read_text() if maps_text is None else maps_text
    with (Path(out)/'MAPS_BEFORE_AUDIT.txt').open('x') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    rows=[];mapped=[]
    for line in raw.splitlines():
        parts=line.split(maxsplit=5)
        if len(parts)!=6 or not parts[5].startswith('/'):continue
        path=Path(parts[5]);row=dict(path=str(path),mapped_inode=parts[4],mapped_device=parts[3],elf=None)
        if str(path) not in config.get('mapping_allowlist',()):
            row.update(match=False,error='mapping not in exact reviewed runtime mapping allowlist; contents not read');rows.append(row);continue
        try:
            with path.open('rb') as stream:magic=stream.read(4)
            row['elf']=magic==b'\x7fELF'
            mapped.append(str(path));actual=digest(path);pin=config['files'].get(str(path));st=path.stat()
            row.update(sha256=actual,bytes=st.st_size,pinned=pin is not None)
            row['match']=pin is not None and actual==pin['sha256'] and st.st_size==pin['bytes'] and int(parts[4])==st.st_ino and tuple(int(v,16) for v in parts[3].split(':'))==(os.major(st.st_dev),os.minor(st.st_dev))
        except (OSError,ValueError) as error:row.update(match=False,error=str(error))
        rows.append(row)
    failures=[r for r in rows if not r.get('match',False)]
    report=dict(status='FAIL_UNKNOWN_OR_CHANGED_MAPPING' if failures else 'PASS_PINNED_ELF_MAPPINGS',mappings=rows,failures=failures)
    (Path(out)/'MAP_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n')
    need(not failures,'actual ELF mapping audit failed; full evidence preserved')
    return sorted(set(mapped))


def audit_runtime(config,out,phase):
    """Save both raw inventories before any validation; report all differences."""
    directory=Path(out)/('RUNTIME_'+phase);directory.mkdir()
    raw_maps=Path('/proc/self/maps').read_text()
    (directory/'MAPS_RAW.txt').write_text(raw_maps)
    snapshot=dict(sys.modules);raw=[]
    def safe(value):
        return value if value is None or type(value) in (str,int,bool) else {'unexpected_type':type(value).__name__}
    for name,module in snapshot.items():
        row={'name':safe(name)}
        try:
            fields=vars(module) if type(module) is types.ModuleType else {}
            spec=fields.get('__spec__');spec_fields=vars(spec) if type(spec) is ModuleSpec else {}
            row.update(module_name=safe(fields.get('__name__')),file=safe(fields.get('__file__')),origin=safe(spec_fields.get('origin')),loader=type(spec_fields.get('loader')).__name__,object_aliases=[safe(n) for n,m in snapshot.items() if m is module])
            if type(module) is not types.ModuleType:row['unexpected_module_type']=type(module).__name__
            if spec is not None and type(spec) is not ModuleSpec:row['unexpected_spec_type']=type(spec).__name__
        except Exception as error:row['collection_error']=type(error).__name__+': '+str(error)
        raw.append(row)
    (directory/'MODULES_RAW.json').write_text(json.dumps(raw,indent=2)+'\n')
    errors=[];mapped=[]
    try:
        import runtime_observer
        synthetic={}
        name='_qualified_runtime_observer'
        if name in snapshot:
            synthetic[name]=dict(kind='namespace_package',module=snapshot[name],paths=[config['observer_root']],allowed_children=['monitor','capture'],creator_source=str(HERE/'runtime_observer.py'),creator_function=runtime_observer.load_observer)
        import selective_binding
        name=selective_binding.PACKAGE
        if name in snapshot:
            synthetic[name]=dict(kind='namespace_package',module=snapshot[name],paths=[config['selective_root']],allowed_children=list(selective_binding.MODULES),creator_source=str(HERE/'selective_binding.py'),creator_function=selective_binding.create_candidate_namespace)
        report=collect_modules(snapshot,config['files'],namespaces=config['namespace_packages'],synthetic=synthetic,registered_objects=config['registered_module_objects'])
        persist_and_validate(report,directory/'MODULE_AUDIT.json')
    except Exception as error:errors.append(dict(audit='modules',type=type(error).__name__,detail=str(error)))
    try:mapped=verify_maps(config,directory,raw_maps)
    except Exception as error:errors.append(dict(audit='maps',type=type(error).__name__,detail=str(error)))
    (directory/'SUMMARY.json').write_text(json.dumps(dict(status='FAIL' if errors else 'PASS_EXACT_RUNTIME_IDENTITIES',phase=phase,errors=errors),indent=2)+'\n')
    emit(out,'RUNTIME_AUDIT_'+phase,dict(errors=errors,module_count=len(snapshot),mapped_files=len(mapped)))
    need(not errors,'runtime identity audit failed; complete module/maps evidence preserved')
    return mapped


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--review',required=True);p.add_argument('--review-sha',required=True);p.add_argument('--sha',required=True);p.add_argument('--m',type=int,choices=(2,),required=True);p.add_argument('--out',required=True);p.add_argument('--order-index',type=int,choices=(0,1,2),required=True);a=p.parse_args()
    stages=Stages()
    need(os.environ.get('ORDERED_NATIVE_PARENT')==str(os.getppid()),'supervised worker required')
    need(digest(a.config)==a.sha,'config identity');config,review=validate_review(a.config,a.review,a.review_sha,HERE);check_manifest(config)
    need(len(os.sched_getaffinity(0))==1 and resource.getrlimit(resource.RLIMIT_AS)[0]==1<<30,'resource caps')
    need(not any(k.startswith('LD_') for k in os.environ),'loader override')
    global RUN_OUT
    out=Path(a.out);RUN_OUT=out;global RUN_CONFIG
    RUN_CONFIG=config;identity=process_identity();(out/'IDENTITY.json').write_text(json.dumps(identity,indent=2)+'\n')
    for k,v in config['git_environment'].items():os.environ[k]=v
    sys.path[:0]=[config['source_root'],config['numpy_root']]
    # No DUT or reference classes have executed at this point.
    guard=Isolation(config);sys.addaudithook(guard.audit)
    stages.mark('config_source_runtime_pins_and_isolation_setup')
    inputs=[]
    for name,width in [('qr',1536),('kr',256),('v',256)]:
        pin=config['inputs'][name];need(digest(pin['path'])==pin['sha256'],'input recheck')
        with open(pin['path'],'rb') as f:raw=f.read(a.m*width*4)
        need(len(raw)==a.m*width*4,'input prefix size');inputs.append(struct.unpack('<%dI'%(a.m*width),raw))
    stages.mark('input_prefix_hash_and_read')
    emit(out,'INPUTS_VERIFIED',dict(m=a.m,input_sha256={n:p['sha256'] for n,p in config['inputs'].items()}))
    exact=load_exact(config['exact_helper']);lib,loaded=load_library(config,out)
    emit(out,'NATIVE_LOADED',loaded)
    audit_runtime(config,out,'AFTER_NATIVE_LOAD')
    stages.mark('exact_primitives_native_load_and_initial_runtime_audit')
    arms=[]
    execution_order=config['arm_orders'][a.order_index]
    for index,variant in enumerate(execution_order):
        observe=variant!='off'
        emit(out,'ARM_START',dict(ordered=True,observer=observe,variant=variant,index=index))
        arm=run_owner(lib,inputs,a.m,True,exact,config,variant=variant);arms.append(arm)
        summary={k:v for k,v in arm.items() if k not in ('output','scores','writes','service_events','capture_fields')}
        summary.update(ordered=True,observer=observe,service_event_count=len(arm['service_events'] or ()),service_events_sha256=hashlib.sha256(json.dumps(arm['service_events'],sort_keys=True).encode()).hexdigest(),writes_sha256=hashlib.sha256(json.dumps(arm['writes']).encode()).hexdigest(),output_sha256=hashlib.sha256(struct.pack('<%dI'%len(arm['output']),*arm['output'])).hexdigest(),scores_sha256=hashlib.sha256(struct.pack('<%dI'%len(arm['scores']),*arm['scores'])).hexdigest())
        (out/('SERVICE_EVENTS_'+str(index)+'.json')).write_text(json.dumps(arm['service_events'],indent=2)+'\n')
        # Actual per-arm bytes are retained only after that arm terminal ACK.
        persist_words(out,'OUTPUT_'+str(index),arm['output'])
        persist_words(out,'SCORES_'+str(index),arm['scores'])
        (out/('WRITES_'+str(index)+'.json')).write_text(json.dumps(arm['writes'])+'\n')
        if observe:
            persist_fields(out,'CAPTURE_'+str(index),arm['capture_fields'])
            (out/('CAPTURE_REPORT_'+str(index)+'.json')).write_text(json.dumps(arm['capture_report'],indent=2)+'\n')
        emit(out,'ARM_TERMINAL_ACKED',summary)
        audit_runtime(config,out,'ARM_'+str(index)+'_TERMINAL')
    # No oracle execute/read before all three original client terminal ACKs.
    stages.mark('three_arms_including_between_arm_audits')
    from harness import compare_fields
    control_arms=canonical_arms(arms,execution_order)
    control=compare_three(control_arms,compare_arms,compare_fields)
    emit(out,'OBSERVER_OFF_ON_CONTROL_EQUAL',control)
    guard.terminal=True
    emit(out,'REFERENCE_COMPARE_START',{})
    comparison=compare_original(config,a.m,inputs,control_arms,reference_out=out)
    # The selective arm is compared transitively to the original independent
    # reference through exact output/score equality and all ten captured fields.
    compare_fields(control_arms[1]['capture_fields'],control_arms[2]['capture_fields'])
    stages.mark('terminal_only_original_reference_compare')
    emit(out,'REFERENCE_COMPARE_PASS',comparison)
    guard.integrity=True
    try:check_manifest(config)
    finally:guard.integrity=False
    loaded['all_mapped_elf_files']=audit_runtime(config,out,'POSTFLIGHT')
    emit(out,'POSTFLIGHT_MAPS_PASS',dict(mapped_elf_count=len(loaded['all_mapped_elf_files'])))
    stages.mark('final_source_runtime_postflight')
    summaries=[]
    for arm in arms:
        summaries.append({k:v for k,v in arm.items() if k not in ('output','scores','writes','service_events','capture_fields')})
    report=dict(status='PASS_REAL_ATTENTION_M2_ROTATED_IDENTITY_TRIO_DIAGNOSTIC_ONLY',m=a.m,order_index=a.order_index,execution_order=execution_order,canonical_reporting_order=list(CANONICAL),arm_artifacts=[dict(variant=v,execution_index=i,output='OUTPUT_'+str(i)+'.u32le',scores='SCORES_'+str(i)+'.u32le',writes='WRITES_'+str(i)+'.json',service_events='SERVICE_EVENTS_'+str(i)+'.json',capture_fields=None if v=='off' else 'CAPTURE_'+str(i)+'_FIELDS.json') for i,v in enumerate(execution_order)],identity=identity,loaded=loaded,arms=summaries,observer_control=control,capture=control_arms[1]['capture_report'],comparison=comparison,inputs_reverified=True,fullblock=False,rtl=False,hardware_cycles=False,stage_costs=stages.rows,reference_after_all_three_terminals=True,total_process_cpu_ns=time.process_time_ns())
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
    RUN_OUT=None;RUN_CONFIG=None
    try:main()
    except BaseException as error:
        if RUN_OUT is not None:
            emit(RUN_OUT,'FAILED_RETAINED',dict(error_type=type(error).__name__,detail=str(error)))
            (RUN_OUT/'MAPS_ON_FAILURE.txt').write_text(Path('/proc/self/maps').read_text())
            if RUN_CONFIG is not None:
                try:audit_runtime(RUN_CONFIG,RUN_OUT,'FAILURE')
                except BaseException as audit_error:
                    (RUN_OUT/'FAILURE_AUDIT_ERROR.json').write_text(json.dumps(dict(type=type(audit_error).__name__,detail=str(audit_error)),indent=2)+'\n')
        raise
