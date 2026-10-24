"""Reuse-only worker. Invoked solely by one-use supervised launch.py."""
import argparse,ctypes,hashlib,json,os,resource,signal,struct,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from harness import need,digest,load_exact,run_owner,compare_original
from admission import validate_review
from runtime_closure import verify_graph


def check_manifest(config):
    need(config['commit']=='a672a56feef9b661f6682bedfcbd702d1ddbc3fa','published owner binding')
    need(config['profile']=='reuse_qk2_legacy_pv0_attention_component','profile')
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
            # Prevent reading any reference data except the three explicitly
            # declared operator inputs, even after terminal comparison.
            if path.suffix in ('.f32le','.bf16le','.npz','.bin'):
                need(str(path) in {x['path'] for x in self.config['inputs'].values()} or (self.terminal and self.integrity and str(path) in self.config['files']), 'reference/weight payload outside component input boundary')
            if not self.terminal and str(path)==self.config['oracle_harness']:
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
        path=Path(parts[5]);row=dict(path=str(path),mapped_inode=parts[4],mapped_device=parts[3])
        try:
            with path.open('rb') as stream:magic=stream.read(4)
            row['elf']=magic==b'\x7fELF'
            if not row['elf']:continue
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


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--review',required=True);p.add_argument('--review-sha',required=True);p.add_argument('--sha',required=True);p.add_argument('--m',type=int,choices=(1,2),required=True);p.add_argument('--out',required=True);a=p.parse_args()
    need(os.environ.get('ORDERED_NATIVE_PARENT')==str(os.getppid()),'supervised worker required')
    need(digest(a.config)==a.sha,'config identity');config,review=validate_review(a.config,a.review,a.review_sha,HERE);check_manifest(config)
    need(len(os.sched_getaffinity(0))==1 and resource.getrlimit(resource.RLIMIT_AS)[0]==1<<30,'resource caps')
    need(not any(k.startswith('LD_') for k in os.environ),'loader override')
    global RUN_OUT
    out=Path(a.out);RUN_OUT=out;identity=process_identity();(out/'IDENTITY.json').write_text(json.dumps(identity,indent=2)+'\n')
    for k,v in config['git_environment'].items():os.environ[k]=v
    sys.path[:0]=[config['source_root'],config['numpy_root']]
    # No DUT or reference classes have executed at this point.
    guard=Isolation(config);sys.addaudithook(guard.audit)
    inputs=[]
    for name,width in [('qr',1536),('kr',256),('v',256)]:
        pin=config['inputs'][name];need(digest(pin['path'])==pin['sha256'],'input recheck')
        with open(pin['path'],'rb') as f:raw=f.read(a.m*width*4)
        need(len(raw)==a.m*width*4,'input prefix size');inputs.append(struct.unpack('<%dI'%(a.m*width),raw))
    emit(out,'INPUTS_VERIFIED',dict(m=a.m,input_sha256={n:p['sha256'] for n,p in config['inputs'].items()}))
    exact=load_exact(config['exact_helper']);lib,loaded=load_library(config,out)
    emit(out,'NATIVE_LOADED',loaded)
    arms=[]
    for enabled in (False,True):
        emit(out,'ARM_START',dict(ordered=enabled))
        arm=run_owner(lib,inputs,a.m,enabled,exact);arms.append(arm)
        summary={k:v for k,v in arm.items() if k not in ('output','scores')}
        summary.update(ordered=enabled,output_sha256=hashlib.sha256(struct.pack('<%dI'%len(arm['output']),*arm['output'])).hexdigest(),scores_sha256=hashlib.sha256(struct.pack('<%dI'%len(arm['scores']),*arm['scores'])).hexdigest())
        emit(out,'ARM_TERMINAL_ACKED',summary)
    # No oracle execute/read before both original client terminal ACKs.
    guard.terminal=True
    emit(out,'REFERENCE_COMPARE_START',{})
    comparison=compare_original(config,a.m,inputs,arms)
    emit(out,'REFERENCE_COMPARE_PASS',comparison)
    guard.integrity=True
    try:check_manifest(config)
    finally:guard.integrity=False
    for module in tuple(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and ('candidates.qwen2_resident_matrix' in getattr(module,'__name__','')):
            need(str(Path(path).resolve()) in config['files'],'unbound runtime module')
    import numpy
    need(str(Path(numpy.__file__).resolve()) in config['files'],'actual NumPy origin')
    loaded['all_mapped_elf_files']=verify_maps(config,out)
    emit(out,'POSTFLIGHT_MAPS_PASS',dict(mapped_elf_count=len(loaded['all_mapped_elf_files'])))
    summaries=[]
    for arm in arms:
        summaries.append({k:v for k,v in arm.items() if k not in ('output','scores')})
    report=dict(status='PASS_REAL_NATIVE_ATTENTION_COMPONENT_ONLY',m=a.m,identity=identity,loaded=loaded,arms=summaries,comparison=comparison,inputs_reverified=True,reference_after_both_terminals=True,fullblock=False,rtl=False,hardware_cycles=False)
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
    RUN_OUT=None
    try:main()
    except BaseException as error:
        if RUN_OUT is not None:
            emit(RUN_OUT,'FAILED_RETAINED',dict(error_type=type(error).__name__,detail=str(error)))
            (RUN_OUT/'MAPS_ON_FAILURE.txt').write_text(Path('/proc/self/maps').read_text())
        raise
