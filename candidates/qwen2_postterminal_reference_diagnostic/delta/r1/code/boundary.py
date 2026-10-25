"""Read-only archived-evidence boundary; no target imports or arithmetic."""
import hashlib,importlib.util,json,os,sys
from pathlib import Path
from primitives import need,digest
from durable import atomic_json
from module_inventory import collect_modules,validate_modules

def verify_pins(config):
    for name,pin in config['files'].items():
        p=Path(name);need(p.is_absolute() and p.resolve(strict=True)==p and p.is_file(),'unaliased pinned file')
        need(p.stat().st_size==pin['bytes'] and digest(p)==pin['sha256'],'file drift '+name)

def load_bound(path,name,config):
    path=Path(path);need(name not in sys.modules and digest(path)==config['files'][str(path)]['sha256'],'source binding')
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    need(Path(module.__file__).resolve()==path and digest(path)==config['files'][str(path)]['sha256'],'loaded source identity')
    return module

class Boundary:
    def __init__(self,config,out):self.config=config;self.out=Path(out);self.reference_complete=False;self.integrity=False
    def audit(self,event,args):
        if event=='ctypes.dlopen' or event=='subprocess.Popen' or event.startswith('socket.') or event in ('os.system','os.exec','os.spawn'):
            raise ValueError('no dynamic native/DUT/process/network work in reference recovery')
        if event=='import' and args[0].split('.')[0] in ('ctypes','numpy','yaml','torch','transformers','candidates','heteronpu'):
            raise ValueError('target or external numerical runtime import forbidden: '+args[0])
        if event in ('os.remove','os.rmdir','os.mkdir','os.rename','os.link','os.symlink'):
            count=2 if event in ('os.rename','os.link','os.symlink') else 1
            need(event!='os.symlink','no output symlinks')
            for value in args[:count]:
                p=Path(os.fsdecode(value));need(p.is_absolute() and p.is_relative_to(self.out) and p.resolve()==p,'filesystem mutation only in new output')
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=Path(os.fsdecode(args[0]));mode,flags=args[1:3]
            writing=bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing:
                need(p.is_absolute() and p.is_relative_to(self.out) and p.resolve()==p,'writes only to new recovery output');return
            if str(p).startswith('/proc/') or str(p).startswith('/sys/'):
                need(str(p) in ('/proc/self/maps','/proc/self/stat','/proc/sys/kernel/random/boot_id'),'only self runtime metadata');return
            if p.is_relative_to(self.out):
                need(self.reference_complete or bool(flags&os.O_DIRECTORY),'new reference artifacts read only after recipe completion');return
            need(p.suffix!='.pyc','source-only runtime, no cache reads')
            need(str(p) in self.config['files'],'unreviewed read path: '+str(p))
            if p.is_relative_to(Path(self.config['original_attempt'])):
                need(self.reference_complete,'saved DUT evidence unavailable to reference computation')
            if p.suffix in ('.bin','.f32le','.bf16le','.npz','.npy','.safetensors','.u32le','.binmeta') and str(p) not in {v['path'] for v in self.config['inputs'].values()}:
                need(self.reference_complete and (p.is_relative_to(Path(self.config['original_attempt'])) or self.integrity),'non-input payload outside completed comparison/integrity')

def audit_runtime(config,out,phase):
    directory=Path(out)/('RUNTIME_'+phase);directory.mkdir()
    snapshot=dict(sys.modules)
    report=collect_modules(snapshot,config['files'],namespaces=config['namespace_packages'],registered_objects=config['registered_module_objects'])
    atomic_json(directory/'MODULE_AUDIT.json',report)
    raw=Path('/proc/self/maps').read_text();(directory/'MAPS_RAW.txt').write_text(raw)
    rows=[]
    for line in raw.splitlines():
        parts=line.split(maxsplit=5)
        if len(parts)!=6 or not parts[5].startswith('/'):continue
        p=Path(parts[5]);pin=config['files'].get(str(p));row=dict(path=str(p),mapped_inode=parts[4],match=False)
        forbidden=any(p==Path(x) or p.is_relative_to(Path(x)) for x in config['forbidden_native_paths'])
        if pin is not None and str(p) in config['mapping_allowlist'] and not forbidden:
            st=p.stat();row['sha256']=digest(p)
            row['match']=st.st_size==pin['bytes'] and row['sha256']==pin['sha256'] and st.st_ino==int(parts[4]) and (os.major(st.st_dev),os.minor(st.st_dev))==tuple(int(x,16) for x in parts[3].split(':'))
        rows.append(row)
    atomic_json(directory/'MAP_AUDIT.json',dict(mappings=rows,failures=[r for r in rows if not r['match']]))
    validate_modules(report);need(rows and all(r['match'] for r in rows),'exact reference runtime map audit')
    need(not any(n.split('.')[0] in ('ctypes','numpy','yaml','torch','transformers','candidates','heteronpu') for n in snapshot),'no target/external runtime loaded')
    atomic_json(directory/'SUMMARY.json',dict(status='PASS_PINNED_REFERENCE_RUNTIME',phase=phase,modules=len(snapshot),mapped_files=len(set(r['path'] for r in rows))))
