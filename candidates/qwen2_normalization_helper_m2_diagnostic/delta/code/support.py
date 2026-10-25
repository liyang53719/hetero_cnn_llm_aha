"""Runtime identity helpers, no model construction during import."""
import ctypes,hashlib,json,os,sys,time,types
from pathlib import Path
from importlib.machinery import ModuleSpec
from module_inventory import collect_modules,persist_and_validate

def need(ok,msg):
    if not ok:raise ValueError(msg)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(1<<20):h.update(block)
    return h.hexdigest()
def process_identity():
    fields=Path('/proc/self/stat').read_text().split(') ',1)[1].split()
    return dict(pid=os.getpid(),ppid=os.getppid(),pgid=os.getpgrp(),start_ticks=int(fields[19]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
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

def check_manifest(config, *, include_reference=True):
    from runtime_closure import verify_graph
    source=json.loads(Path(config['source_manifest']).read_text());root=Path(config['source_root'])
    need(digest(config['source_manifest'])==config['source_manifest_sha256'],'source manifest identity')
    need({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}==set(source['source_files']),'complete source tree')
    for rel,p in source['source_files'].items():need(config['files'][str(root/rel)]==p,'source pin')
    for name,p in config['files'].items():
        if not include_reference and name in config['reference_artifacts']:continue
        path=Path(name);need(path.is_absolute() and path.resolve()==path and path.is_file() and path.stat().st_size==p['bytes'] and digest(path)==p['sha256'],'pinned file drift '+name)
    verify_graph(config['runtime_graph'],config['files'])
    need(set(config['inputs'])=={'qr','kr','v'},'only actual frozen qr/kr/v')

def audit_runtime(config,out,phase):
    import binding,runtime_observer
    directory=Path(out)/('RUNTIME_'+phase);directory.mkdir()
    raw=Path('/proc/self/maps').read_text();(directory/'MAPS_RAW.txt').write_text(raw)
    snapshot=dict(sys.modules);synthetic={}
    name='_qualified_runtime_observer'
    if name in snapshot:synthetic[name]=dict(kind='namespace_package',module=snapshot[name],paths=[config['observer_root']],allowed_children=['monitor','capture'],creator_source=str(Path(runtime_observer.__file__).resolve()),creator_function=runtime_observer.load_observer)
    name=binding.PACKAGE
    if name in snapshot:synthetic[name]=dict(kind='namespace_package',module=snapshot[name],paths=[config['bridge_root']],allowed_children=list(binding.MODULES),creator_source=str(Path(binding.__file__).resolve()),creator_function=binding.create_bridge_namespace)
    report=collect_modules(snapshot,config['files'],namespaces=config['namespace_packages'],synthetic=synthetic,registered_objects=config['registered_module_objects'])
    errors=[]
    try:persist_and_validate(report,directory/'MODULE_AUDIT.json')
    except Exception as error:errors.append(dict(kind='modules',detail=str(error)))
    try:verify_maps(config,directory,raw)
    except Exception as error:errors.append(dict(kind='maps',detail=str(error)))
    (directory/'SUMMARY.json').write_text(json.dumps(dict(status='FAIL' if errors else 'PASS_EXACT_RUNTIME_IDENTITIES',phase=phase,errors=errors),indent=2)+'\n')
    need(not errors,'complete runtime audit failed; ledgers retained')
