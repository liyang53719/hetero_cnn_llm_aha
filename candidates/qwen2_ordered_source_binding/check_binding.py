"""Normal module loading/binding only; pinned dependency initialization is allowed.

Never construct services, invoke task arithmetic, load Matrix ELF, or read data.
"""
import argparse,hashlib,importlib,importlib.util,json,os,sys,types
from pathlib import Path

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    c=json.loads(a.config.read_text());out=a.output.resolve();out.mkdir(exist_ok=False)
    source=Path(c['source_root']).resolve();observer=Path(c['observer_root']).resolve();buffer=Path(c['buffer_source']).resolve()
    source_pins=c['source_files'];runtime=c['runtime_files'];extras=c['extra_files'];verified={};events=[]
    def check(path,pin):
        path=Path(path);need(path.stat().st_size==pin['bytes'] and sha(path)==pin['sha256'],'pinned file drift '+path.name);verified[str(path.resolve())]=pin['sha256']
    for rel,pin in source_pins.items():check(source/rel,pin)
    for path,pin in extras.items():check(path,pin)
    allowed={**runtime,**{str(source/rel):pin for rel,pin in source_pins.items()},**extras}
    def audit(event,args):
        if event in ('subprocess.Popen','os.system','os.fork','os.posix_spawn'):raise ValueError('process execution forbidden')
        if event=='ctypes.dlopen':
            need(args[0] is None,'explicit library loading forbidden');events.append('ctypes.dlopen(None) dependency initialization')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve()
            flags=args[2] if len(args)>2 else 0
            if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
                need(path.is_relative_to(out),'write outside new output');return
            if os.fsdecode(args[0])=='/proc/self/maps' or path.is_relative_to(out):return
            if path.suffix=='.pyc':raise PermissionError('source-only import; bytecode cache not admitted')
            need(str(path) in allowed,'unapproved read '+path.name)
            if str(path) not in verified:check(path,allowed[str(path)])
        if event=='import' and len(args)>1 and args[1]:
            path=Path(args[1]).resolve()
            need(str(path) in allowed,'unapproved extension '+path.name)
            if str(path) not in verified:check(path,allowed[str(path)])
    # Reentrant audit file hashing is bounded because mark precedes hash reads.
    checking=set()
    def guarded(event,args):
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            key=str(Path(os.fsdecode(args[0])).resolve())
            if key in checking:return
            checking.add(key)
            try:audit(event,args)
            finally:checking.remove(key)
        else:audit(event,args)
    def profile(frame,event,arg):
        if event=='call' and str(frame.f_code.co_filename).startswith(str(source)):
            n=frame.f_code.co_name
            need(n not in {'configure_library','__init__','td_reset','tick','run','op','_op','_matrix_step'},'task-level execution forbidden '+n)
    sys.addaudithook(guarded);sys.setprofile(profile)
    sys.path.insert(0,c['numpy_root']);sys.path.insert(0,str(source))
    names=['ffn_attention.attention_owner','production_qk16_model.schedule','production_qk16_model.ordered_work','attention_packed_owner.client']
    modules={name:importlib.import_module('candidates.qwen2_resident_matrix.'+name) for name in names}
    base=load('_normal_pinned_buffer',buffer)
    package=types.ModuleType('_normal_pinned_observer');package.__path__=[str(observer)];sys.modules[package.__name__]=package
    monitor=importlib.import_module(package.__name__+'.monitor')
    root=source/'candidates/qwen2_resident_matrix'
    spec={
        'run':('production_qk16_model.schedule','ProductionQk16Schedule','run'),
        'work':('production_qk16_model.ordered_work','OrderedFoldAdapter','tick'),
        'consume':('production_qk16_model.ordered_work','OrderedFoldWork','consume'),
        'matrix':('ffn_attention.attention_owner','AttentionOwner','_matrix_step'),
        'op':('ffn_attention.attention_owner','AttentionOwner','_op'),
        'tick':('ffn_attention.attention_owner','AttentionOwner','tick'),
        'client':('attention_packed_owner.client','PackedClient','tick')}
    bound=[]
    for role,(module,cls,name) in spec.items():
        path=root/(module.replace('.','/')+'.py');m=modules[module];need(Path(m.__file__).resolve()==path,'module path drift')
        method=getattr(getattr(m,cls),name);monitor.bind(method,path,monitor.PINS['roles'][role],cls,name,False);bound.append(role)
    for name in ('__init__','_put','_bytes','field_summary'):
        monitor.bind(getattr(base.PackedFields,name),buffer,monitor.PINS['buffer_sha256'],'PackedFields',name,False);bound.append('buffer.'+name)
    # Negative checks never replace original sources or execute altered methods.
    method=modules['production_qk16_model.schedule'].ProductionQk16Schedule.run;path=root/'production_qk16_model/schedule.py';digest=monitor.PINS['roles']['run'];negative=[]
    def rejected(name,fn):
        try:fn()
        except ValueError:negative.append(name)
        else:raise ValueError('negative accepted '+name)
    rejected('wrong_digest',lambda:monitor.bind(method,path,'0'*64,'ProductionQk16Schedule','run',False))
    same=out/'same_source.py';same.write_bytes(path.read_bytes())
    rejected('same_bytes_wrong_path',lambda:monitor.bind(method,same,digest,'ProductionQk16Schedule','run',False))
    changed=out/'changed_source.py';changed.write_bytes(path.read_bytes()+b'\n')
    rejected('one_byte_source_change',lambda:monitor.bind(method,changed,digest,'ProductionQk16Schedule','run',False))
    def replacement():return None
    rejected('replacement_method',lambda:monitor.bind(replacement,path,digest,'ProductionQk16Schedule','run',False))
    (out/'BINDING_STAGE.json').write_text(json.dumps({'bound':bound,'negative_rejections':negative,'source_files_verified':len(source_pins),'verified_reads':verified},indent=2)+'\n')
    # The ledger is written before validation, including unknown mappings on failure.
    maps=Path('/proc/self/maps').read_text();(out/'MAPS.txt').write_text(maps)
    mapping=[]
    for line in maps.splitlines():
        parts=line.split(None,5)
        if len(parts)==6 and parts[5].startswith('/'):
            stat=Path(parts[5]).stat();major,minor=(int(x,16) for x in parts[3].split(':'))
            need((os.major(stat.st_dev),os.minor(stat.st_dev),stat.st_ino)==(major,minor,int(parts[4])),'mapped inode/device differs')
    for name in sorted({line.split(None,5)[5] for line in maps.splitlines() if len(line.split(None,5))==6 and line.split(None,5)[5].startswith('/')}):
        pth=Path(name).resolve();need(str(pth) in allowed,'unapproved mapped file '+pth.name);check(pth,allowed[str(pth)])
        mapping.append(dict(name=pth.name,sha256=verified[str(pth)],bytes=pth.stat().st_size))
    imports=[]
    for name,module in sorted(sys.modules.items()):
        filename=getattr(module,'__file__',None)
        if not filename:continue
        pth=Path(filename).resolve()
        need(str(pth) in allowed,'unapproved already-loaded module '+name)
        check(pth,allowed[str(pth)]);imports.append(dict(module=name,sha256=verified[str(pth)],name=pth.name))
    for rel,pin in source_pins.items():check(source/rel,pin)
    for path,pin in extras.items():check(path,pin)
    report=dict(status='PASS_NORMAL_MODULE_LOAD_AND_CODE_BINDING_ONLY',bound=bound,negative_rejections=negative,source_files_verified=len(source_pins),imports=imports,mappings=mapping,dependency_initialization_events=events,allowed_dependency_self_tests=['NumPy float32 ones(2).dot','NumPy ones((20,20)) matrix-multiply BLAS FPE self-check'],task_services_constructed=False,task_jobs=0,matrix_elf_loaded=False,task_tensor_reads=0,numerical_or_observer_nonintrusion_qualification=False,rtl=False)
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
    try:main()
    except Exception as error:
        sys.setprofile(None)
        if '--output' in sys.argv:
            out=Path(sys.argv[sys.argv.index('--output')+1])
            if out.is_dir():
                (out/'MAPS_ON_FAILURE.txt').write_text(Path('/proc/self/maps').read_text())
                (out/'FAILURE.json').write_text(json.dumps({'status':'FAIL','error':type(error).__name__+': '+str(error)},indent=2)+'\n')
        raise

