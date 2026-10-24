"""Finite M2 calibration I/O guard, not a sandbox for adversarial native code.

No official input/raw/reference read is ever admitted. Exactly pinned source,
runtime and metadata files are readable; writes belong only to this new arm.
"""
import errno
import importlib.util
import os
from pathlib import Path
import sys
import shutil
import types
from m2_authority import checked, need, parse


def git_profile_read_specs(runtime,manifest,base):
    """Exact transitive source-only Git verify reads; no directory admission.

    Original verify checks all these files again under the installed hook. The
    sole non-runtime entry is a historical C++ mirror witness, whose content must
    equal the current selected source C++ file. It is not an input or reference.
    """
    lineage_path=Path(runtime['git_profile_root'])/'LINEAGE.json'
    lineage_pin=runtime['files'].get(str(lineage_path))
    need(type(lineage_pin) is dict and set(lineage_pin)=={'bytes','sha256'},
         'exact runtime-pinned Git lineage manifest')
    lineage=parse(checked(lineage_path,lineage_pin,cap=1<<20))
    need(lineage.get('profile')=='genuine_public_git_dir_bound_to_exact_mirror_sources_v1' and
         len(lineage['git_metadata'])==6 and len(lineage['object_lineage'])==6,
         'fixed Git provenance route shape')
    specs=[lineage['git'],*lineage['git_metadata'],
           *(item['artifact'] for item in lineage['object_lineage']),
           lineage['committed_cpp'],lineage['mirror_cpp']]
    need(len(specs)==15 and len({item['path'] for item in specs})==15,'fifteen unique Git source reads')
    relative='chisel/continuous_prefill/tests/qwen2_block.cpp'
    cpp_pin=dict(bytes=manifest['source_bytes'][relative],sha256=manifest['source_sha256'][relative])
    need({k:lineage['committed_cpp'][k] for k in ('bytes','sha256')}==cpp_pin,
         'committed and current C++ source content must agree')
    result={};extra=[]
    for item in specs:
        need(type(item) is dict and set(item)=={'path','bytes','sha256'},'exact provenance spec fields')
        path=Path(item['path']);pin={k:item[k] for k in ('bytes','sha256')}
        need(path.is_absolute() and path.resolve()==path and
             not any(q.is_symlink() for q in (path,*path.parents)),'unaliased Git source route')
        if str(path) in runtime['files']:
            need(runtime['files'][str(path)]==pin,'runtime/provenance pin mismatch')
        else:
            need(item==lineage['mirror_cpp'] and pin==cpp_pin,'only current-C++ equal mirror may extend read set')
            checked(path,pin,retain=False,cap=1<<20)
            extra.append(str(path))
        result[str(path)]=pin
    need(extra==[lineage['mirror_cpp']['path']],'exact one historical C++ witness addition')
    return result


class CalibrationIO:
    def __init__(self,state,layout):
        self.state=state;self.layout=layout;self.out=state['out'];self.reads=set();self.native_events=[];self.fenv=None
        self.allowed={}
        base=state['base'];m=state['source_manifest'];runtime=state['runtime_pins']
        self.allowed.update({str(base/k):v for k,v in m['preparation_files'].items()})
        self.allowed[str(base/'SOURCE_MANIFEST.json')]=state['own']['base']['manifest']
        for prefix,hashes,sizes in (('source',m['source_sha256'],m['source_bytes']),
                ('selected',m['selected_source_sha256'],m['selected_source_bytes']),
                ('support',m['support_sha256'],m['support_bytes'])):
            self.allowed.update({str(base/prefix/k):dict(bytes=sizes[k],sha256=v) for k,v in hashes.items()})
        self.allowed.update(runtime['files'])
        self.git_profile_read_specifications=git_profile_read_specs(runtime,m,base)
        self.allowed.update(self.git_profile_read_specifications)
        here=Path(__file__).resolve().parent
        self.allowed.update({str(here/k):v for k,v in state['own']['files'].items()})
        self.allowed[str(here/'SOURCE_MANIFEST.json')]={'sha256':state['manifest_sha256']}
        self.allowed[str(self.out.parent/'ADMISSION.json')]={}
        self.allowed[str(self.out.parent/'LEASE.json')]={}
        native=parse(checked(base/'NATIVE_REUSE_PINS.json',m['preparation_files']['NATIVE_REUSE_PINS.json']))
        self.allowed.update({v['path']:v for v in native['files'].values()})
        self.elf=Path(native['files']['elf']['path'])
        budget=parse(checked(base/'BUDGET_PROPOSAL.json',m['preparation_files']['BUDGET_PROPOSAL.json']))
        codec=Path(budget['attention_trace_limits']['codec_root'])
        pins=parse(checked(base/'capture/CODEC_PINS.json',m['preparation_files']['capture/CODEC_PINS.json']))
        self.allowed.update({str(codec/n):{'sha256':v} for n,v in pins.items()})
        # Reference and actual tensors never enter this allowlist. Only ARTIFACTS
        # is needed by the existing package-origin verifier after initialization.
        logical='work/qwen2_recovered_inputs/ARTIFACTS.json'
        self.allowed[str(layout.path(logical))]=layout.identity(logical)
        self.input_roots=tuple(layout.frozen_roots)
        self.shutil_path=Path(shutil.__file__).resolve()
        self.shutil_pin=runtime['files'][str(self.shutil_path)]
        code=compile(checked(self.shutil_path,self.shutil_pin),str(self.shutil_path),'exec',dont_inherit=True,optimize=0)
        expected=[c for c in code.co_consts if isinstance(c,types.CodeType) and c.co_name=='_rmtree_safe_fd']
        need(len(expected)==1 and expected[0]==shutil._rmtree_safe_fd.__code__,'pinned shutil cleanup code')
        self.expected_cleanup=shutil._rmtree_safe_fd.__code__
        self.cleanup_directory_reads=[]
        self.environment_code=None
        self.init_code=None
        import ctypes
        self.ctypes=ctypes
        self.ctypes_codes={n:getattr(ctypes.CDLL,n).__code__ for n in ('__init__','__getitem__','__getattr__')}
        self.allowed_proc={'/proc/self/maps','/proc/self/stat','/proc/self/statm','/proc/self/status',
                           '/proc/'+str(state['parent']['pid'])+'/stat','/proc/'+str(os.getpid())+'/stat'}

    def bind_context(self,context):
        need(self.environment_code is None and self.init_code is None,'FENV binding once')
        self.environment_code=context['scalar'].ScalarService._check_environment.__code__
        self.init_code=context['scalar'].ScalarService.__init__.__code__

    def readonly(self,mode,flags):
        need((mode is None or not any(x in mode for x in 'wax+')) and
             (type(flags) is not int or not flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)),
             'calibration source/runtime is read-only')

    def environment_frames(self,frame,method):
        need(frame.f_code is self.ctypes_codes[method],'original ctypes frame required')
        if method=='__getitem__':
            frame=frame.f_back;need(frame.f_code is self.ctypes_codes['__getattr__'],'original ctypes getattr')
        frame=frame.f_back
        need(frame is not None and frame.f_code is self.environment_code and
             frame.f_back is not None and frame.f_back.f_code is self.init_code,'original Scalar FENV call chain')

    def cleanup_directory(self,raw,mode,flags,frame):
        # Same narrow omitted-dir_fd resolution as the source-pinned original
        # gate: only original shutil directory cleanup inside this arm's output.
        if (Path(raw).is_absolute() or frame.f_globals is not shutil.__dict__ or
                frame.f_code is not self.expected_cleanup):
            return False
        need(mode is None and type(flags) is int and
             flags & ~getattr(os,'O_CLOEXEC',0)==os.O_RDONLY|os.O_NONBLOCK,'cleanup flags')
        need(raw not in ('','.','..') and Path(raw).name==raw and
             frame.f_locals.get('name')==raw,'exact cleanup entry')
        fd=frame.f_locals.get('dirfd')
        need(type(fd) is int and fd>=0,'original live cleanup dirfd')
        parent=Path(os.readlink('/proc/self/fd/'+str(fd)))
        path=parent/raw
        need(parent.is_absolute() and path.resolve()==path and
             not any(p.is_symlink() for p in (path,*path.parents)) and
             parent.is_relative_to(self.out) and path!=self.out and path.is_relative_to(self.out) and
             path.is_dir() and Path(frame.f_locals['path']).resolve()==path,'cleanup inside new arm')
        checked(self.shutil_path,self.shutil_pin,retain=False)
        need(len(self.cleanup_directory_reads)<16,'bounded fixture cleanup')
        self.cleanup_directory_reads.append(str(path.relative_to(self.out)))
        return True

    def audit(self,event,args):
        if event=='ctypes.dlopen':
            if args[0] is None:
                need(self.fenv is None,'single Scalar FENV handle')
                frame=sys._getframe(1);self.environment_frames(frame,'__init__');self.fenv=id(frame.f_locals['self'])
            else:
                need(Path(os.fsdecode(args[0]))==self.elf and not any(
                     x['event']=='ctypes.dlopen' and x.get('target') is not None for x in self.native_events),
                     'only one pinned existing ELF load')
            self.native_events.append({'event':event,'target':args[0]});return
        if event=='ctypes.dlsym' and getattr(args[0],'_name','not-none') is None:
            need(id(args[0])==self.fenv and args[1]=='fegetround','only original FENV symbol')
            self.environment_frames(sys._getframe(1),'__getitem__')
            self.native_events.append({'event':event,'symbol':args[1]});return
        if event=='subprocess.Popen':
            executable,argv,cwd,env=args
            need(executable in ('git','/usr/bin/git') and argv in (
                 ['git','show','HEAD:chisel/continuous_prefill/tests/qwen2_block.cpp'],
                 ['git','rev-parse','HEAD']) and Path(cwd)==self.state['base']/'source',
                 'only two source recipe Git queries; no compiler/other child')
            return
        if event.startswith('socket.') or event in ('os.system','os.exec','os.spawn'):
            raise ValueError('network/process action outside calibration')
        if event=='import' and args[0].split('.')[0] in ('torch','transformers'):
            raise ValueError('official numerical oracle import forbidden')
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        raw=os.fsdecode(args[0]);mode,flags=args[1:3]
        if self.cleanup_directory(raw,mode,flags,sys._getframe(1)):return
        if raw in self.allowed_proc:self.readonly(mode,flags);return
        p=Path(raw)
        need(p.is_absolute(),'relative file open forbidden in calibration')
        need(not any(q.is_symlink() for q in (p,*p.parents)),'aliased calibration file')
        if p.is_relative_to(self.out):return
        self.readonly(mode,flags)
        if p.suffix=='.pyc':
            try:source=importlib.util.source_from_cache(str(p))
            except ValueError:source=None
            if source in self.allowed:raise FileNotFoundError(errno.ENOENT,'pinned source only',str(p))
        need(str(p) in self.allowed,'unlisted calibration read: '+str(p))
        need(len(self.reads)<4096 or str(p) in self.reads,'bounded route set')
        self.reads.add(str(p))
