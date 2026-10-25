"""Existing runtime/isolation helper definitions with explicit M16/source namespace deltas."""
import ctypes,hashlib,json,os,struct,sys,time,types
from pathlib import Path
from importlib.machinery import ModuleSpec
from primitives import need,digest
from runtime_closure import verify_graph
from module_inventory import collect_modules,persist_and_validate
HERE=Path(__file__).resolve().parent
def check_manifest(config):
    need(config['commit']=='e8375f64d861c45fea3fbd6d445e5c213ff895a6','published owner binding')
    need(config['profile']=='production_attention_m16_public3_stream_pair_r2' and config['rows']==16,'profile')
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
    errors=[];mapped=[];report=None;qualification=None
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
        import binding
        name=binding.PACKAGE
        if name in snapshot:
            synthetic[name]=dict(kind='namespace_package',module=snapshot[name],paths=[config['production_root']],allowed_children=list(binding.MODULES),creator_source=str(HERE/'binding.py'),creator_function=binding.create_production_namespace)
        dependency=binding.DEPENDENCY
        need(dependency is not None,'production dependency initialization context missing')
        namespaces,repetitions=dependency['policy'].namespace_registration(snapshot,config['namespace_packages'])
        report=collect_modules(snapshot,config['files'],namespaces=namespaces,synthetic=synthetic,registered_objects=config['registered_module_objects'])
        # Preserve the immutable original failure ledger; qualification is separate.
        (directory/'MODULE_AUDIT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        qualification=dependency['policy'].qualify_namespace_repetitions(report,repetitions,snapshot)
        (directory/'NAMESPACE_QUALIFICATION.json').write_text(json.dumps(qualification,indent=2,sort_keys=True)+'\n')
    except Exception as error:errors.append(dict(audit='modules',type=type(error).__name__,detail=str(error)))
    try:mapped=verify_maps(config,directory,raw_maps)
    except Exception as error:errors.append(dict(audit='maps',type=type(error).__name__,detail=str(error)))
    try:
        need(report is not None and qualification is not None,'complete original module ledger required')
        dependency=binding.DEPENDENCY
        initialization=dependency['initialization']
        safe_raw=dependency['safe'].snapshot(snapshot,(*initialization.NAMES,'yaml','yaml.cyaml','yaml._yaml'))
        (directory/'DEPENDENCY_OBJECTS_RAW.json').write_text(json.dumps(safe_raw,indent=2,sort_keys=True)+'\n')
        need(all(not row['errors'] for row in safe_raw),'dependency raw object errors')
        maps=json.loads((directory/'MAP_AUDIT.json').read_text())
        need(not maps['failures'] and any(r['path']==config['elf'] and r['match'] for r in maps['mappings']),
             'complete exact maps including Matrix required')
        dep=initialization.qualify(snapshot,dependency['native_before'],dependency['native_events'],
            config['yaml_root'],config['yaml_extension_sha256'],maps,report)
        remaining=qualification['remaining_failures']
        need({r['name'] for r in remaining}==set(initialization.NAMES) and
             all(r['code']=='unregistered_no_file_module' for r in remaining),'unknown module identity failure')
        (directory/'DEPENDENCY_QUALIFICATION.json').write_text(json.dumps(dep,indent=2,sort_keys=True)+'\n')
    except Exception as error:errors.append(dict(audit='dependency_qualification',type=type(error).__name__,detail=str(error)))
    (directory/'SUMMARY.json').write_text(json.dumps(dict(status='FAIL' if errors else 'PASS_EXACT_RUNTIME_IDENTITIES',phase=phase,errors=errors),indent=2)+'\n')
    emit(out,'RUNTIME_AUDIT_'+phase,dict(errors=errors,module_count=len(snapshot),mapped_files=len(mapped)))
    need(not errors,'runtime identity audit failed; complete module/maps evidence preserved')
    return mapped
