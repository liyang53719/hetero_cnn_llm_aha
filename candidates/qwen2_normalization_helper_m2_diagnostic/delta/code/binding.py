"""Normal source loading: exactly one model root and one complete lease profile."""
import hashlib,importlib,importlib.util,json,os,sys,types
from pathlib import Path
from contextlib import contextmanager
from support import need,digest
PACKAGE='_normalization_bridge'
MODULES=('bridge','service_trace','registry')
def load_file(path,name,config):
    path=Path(path);need(name not in sys.modules and digest(path)==config['files'][str(path)]['sha256'],'fresh pinned helper '+name)
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    need(Path(module.__file__).resolve()==path and digest(path)==config['files'][str(path)]['sha256'],'normal source helper identity')
    return module

def create_bridge_namespace(config):
    need(PACKAGE not in sys.modules and not any(n.startswith(PACKAGE+'.') for n in sys.modules),'fresh bridge namespace')
    module=types.ModuleType(PACKAGE);module.__path__=[config['bridge_root']];sys.modules[PACKAGE]=module
    return module

def prepare(config,guard):
    gate=load_file(config['project_code_gate_source'],'_production_existing_project_code_gate',config)
    guard.source_verifier_code=gate.verify_sources.__code__
    root,files=gate.verify_sources(config['source_root'],config['source_manifest'],config['source_manifest_sha256'])
    need(not gate.project_inventory(root,files,sys.modules),'no preloaded model namespace')
    create_bridge_namespace(config)
    bridge_files={name+'.py':config['files'][str(Path(config['bridge_root'])/(name+'.py'))] for name in MODULES}
    with gate.ProjectCodeGate(Path(config['bridge_root']),bridge_files) as bridge_gate:
        modules={name:importlib.import_module(PACKAGE+'.'+name) for name in MODULES}
    runtime_path=Path(config['observer_runtime_root'])/'runtime_observer.py'
    with gate.ProjectCodeGate(runtime_path.parent,{'runtime_observer.py':config['files'][str(runtime_path)]}) as runtime_gate:
        runtime=load_file(runtime_path,'runtime_observer',config)
    return gate,root,files,modules,runtime,dict(bridge_exec_events=bridge_gate.events,runtime_exec_events=runtime_gate.events)

@contextmanager
def model_gate(gate,root,files,config,receipt):
    observer_root=Path(config['observer_root'])
    observer_files={name:config['files'][str(observer_root/name)] for name in ('monitor.py','capture.py','SOURCE_PINS.json')}
    with gate.ProjectCodeGate(root,files) as active, gate.ProjectCodeGate(observer_root,observer_files) as observed:
        yield
    receipt['observer_exec_events']=observed.events
    need({v['relative'] for v in observed.events}=={'monitor.py','capture.py'},'complete normal observer source execution')
    receipt['model_exec_events']=active.events
    receipt['model_inventory']=gate.project_inventory(root,files,sys.modules)
    executed={row['relative'] for row in active.events}
    need(all(v['relative'] in executed for v in receipt['model_inventory'].values()),'every actual model module source-exec attested')
    gate.verify_sources(config['source_root'],config['source_manifest'],config['source_manifest_sha256'])

class Isolation:
    def __init__(self,config,out,baseline=None):
        self.config=config;self.out=Path(out);self.baseline=None if baseline is None else Path(baseline)
        self.source_verifier_code=None;self.terminal=False;self.all_terminals=False;self.reference_qualified=False;self.integrity=False;self.loads=[];self.handoff_files=set()
    def metadata_hash_read(self,path,mode,flags):
        header=Path(self.config['source_root'])/'config/upstream/weight_headers/qwen2_1p5b/model.safetensors.header.bin'
        if path!=header:return False
        need(mode=='r' and not flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND),'metadata source hash read only')
        frame=sys._getframe(1)
        try:
            while frame:
                if frame.f_code is self.source_verifier_code:
                    return frame.f_locals.get('path')==header and frame.f_locals.get('root')==Path(self.config['source_root'])
                frame=frame.f_back
        finally:del frame
        return False
    def handoff_hash_read(self,path):
        if not (self.all_terminals and self.integrity and str(path) in self.handoff_files):return False
        frame=sys._getframe(1)
        try:
            while frame:
                if frame.f_code is digest.__code__:
                    return Path(frame.f_locals.get('path',''))==path
                frame=frame.f_back
        finally:del frame
        return False
    def audit(self,event,args):
        if event=='ctypes.dlopen':need(args[0] in (None,self.config['elf']),'original Matrix/native helper only');self.loads.append(args[0])
        if event=='subprocess.Popen':
            executable,argv,cwd,env=args
            need(executable in ('git','/usr/bin/git') and os.environ.get('PATH')=='/usr/bin:/bin' and argv in (['git','show','HEAD:chisel/continuous_prefill/tests/qwen2_block.cpp'],['git','rev-parse','HEAD']),'original read-only source queries only')
        if event.startswith('socket.') or event in ('os.system','os.exec','os.spawn'):raise ValueError('network/process outside profile')
        if event=='import' and args[0].split('.')[0] in ('torch','transformers','yaml'):raise ValueError('unneeded runtime/oracle import')
        if event=='exec' and not args[0].co_filename.startswith('<'):
            need(not Path(args[0].co_filename).is_relative_to(Path(self.config['foreign_model_root'])),'other model root execution forbidden in this fresh worker')
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(os.fsdecode(args[0]));mode,flags=args[1:3];write=bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if write:
                need(path.is_absolute() and path.resolve()==path and path.is_relative_to(self.out),'write only new own worker evidence');return
            if path.suffix=='.pyc':raise PermissionError('source-only import cache policy')
            if self.baseline is not None and path.is_relative_to(self.baseline) and path.name not in ('PARENT.json',):
                need(self.all_terminals and (path.name=='TERMINAL.json' or self.reference_qualified or self.integrity),'baseline values unavailable before both terminals/reference qualification')
            is_reference=str(path) in self.config['reference_artifacts']
            if is_reference:need(self.all_terminals and (self.reference_qualified or self.integrity),'retained reference values unavailable before both terminals')
            if path.suffix in ('.f32le','.bf16le','.npz','.bin','.u32le','.binmeta'):
                inputs={v['path'] for v in self.config['inputs'].values()}
                need(str(path) in inputs or self.metadata_hash_read(path,mode,flags) or self.handoff_hash_read(path) or
                     (self.terminal and self.integrity and str(path) in self.config['files']) or
                     (self.all_terminals and self.reference_qualified and (is_reference or path.is_relative_to(self.out) or (self.baseline is not None and path.is_relative_to(self.baseline)))),
                     'payload outside declared frozen input/terminal comparison boundary: '+str(path))
            forbidden={self.config['oracle_harness'],*(v['path'] for v in self.config['reference_sources'].values())}-{self.config['exact_helper'],self.config['buffer_source']}
            if str(path) in forbidden:need(self.integrity,'recipe is not executed; only integrity hashing permitted')
