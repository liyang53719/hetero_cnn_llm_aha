"""New M2-only loading bridge. No top-level DUT/native import or execution."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time
from m2_authority import checked, load_source, need, parse, require_actual_runtime


def initialize(state):
    require_actual_runtime('initialize_m2_runtime')
    base=state['base'];manifest=state['source_manifest'];prep=manifest['preparation_files']
    raw=checked(base/'RUNTIME_PINS.json',prep['RUNTIME_PINS.json'],cap=1<<20)
    runtime=parse(raw);state['runtime_pins']=runtime
    need(len(runtime['files'])==1638,'fixed runtime inventory')
    for name,pin in runtime['files'].items():
        checked(Path(name),pin,retain=False)
    for prefix,hashes,sizes,count in (
        ('source',manifest['source_sha256'],manifest['source_bytes'],306),
        ('selected',manifest['selected_source_sha256'],manifest['selected_source_bytes'],9),
        ('support',manifest['support_sha256'],manifest['support_bytes'],6)):
        need(len(hashes)==count and hashes.keys()==sizes.keys(),'exact source inventory')
        for name,digest in hashes.items():
            checked(base/prefix/name,dict(bytes=sizes[name],sha256=digest),retain=False,cap=2<<20)
    for name,pin in prep.items():checked(base/name,pin,retain=False,cap=2<<20)
    sys.path[:0]=[str(base),str(base/'source')]
    pre=load_source(base/'assembly_preflight.py','assembly_preflight',prep['assembly_preflight.py'])
    layout=pre.frozen_layout(manifest)
    # Only frozen metadata is read. No input/provenance/reference payload is needed.
    sys.dont_write_bytecode=True
    os.environ['QWEN2_FIXED93_SOURCE_MANIFEST_SHA256']=state['own']['base']['manifest']['sha256']
    binding=checked(base/'source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json')
    os.environ['QWEN2_FIXED93_FROZEN_BINDING_SHA256']=hashlib.sha256(binding).hexdigest()
    os.environ['QWEN2_FIXED93_ARTIFACTS_SHA256']=layout.identity('work/qwen2_recovered_inputs/ARTIFACTS.json')['sha256']
    layout.finish()
    # Import stdlib ctypes itself before the guarded DUT path; its interpreter
    # process handle is initialization, not model execution or an ELF load.
    import ctypes
    from m2_io import CalibrationIO
    guard=CalibrationIO(state,layout)
    sys.addaudithook(guard.audit)
    original=load_source(base/'admission.py','_m2_pinned_initializer',prep['admission.py'])
    need(not any(n.split('.')[0] in ('numpy','yaml','torch') for n in sys.modules),'early numerical package import')
    for key,value in runtime['git_environment'].items():
        need(key not in os.environ,'inherited Git override');os.environ[key]=value
    original._load_genuine_git(runtime)
    sys.path[:0]=list(dict.fromkeys(str(Path(v['path']).parent.parent) for v in runtime['package_roots'].values()))
    from integration.runtime_support import runtime_adapter
    runtime_adapter.initialize()
    from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as r
    previous,new=r.runtime()
    # Match the successful source-bound startup imports before ELF/context setup.
    # r.runtime() initializes the legacy dense chain, not these fixed93 modules.
    from candidates.qwen2_fixed93_attention.binding import Fixed93PublicExecution,Fixed93ReductionDriver
    from candidates.qwen2_fixed93_attention.owner import Fixed93AttentionOwner
    from observation.fullblock_attention import Fixed93FullblockAttentionObservation
    (modules,dense,observer,native)=previous
    helper,original,fixtures,public,prefix,_,scalar,suffix,*_=modules
    owner_module,binding,profiles,execution,observation,_=new
    context=dict(r=r,dense=dense,native=native,helper=helper,original=original,fixtures=fixtures,
                 public=public,prefix=prefix,scalar=scalar,owner_module=owner_module,binding=binding,
                 profiles=profiles,execution=execution,suffix=suffix,observation=observation)
    adapter=load_source(Path(__file__).with_name('native_adapter.py'),'_m2_native_adapter',state['own']['files']['native_adapter.py'])
    guard.bind_context(context)
    library,built,reuse=adapter.load(dense)
    context.update(built=built,reuse=reuse)
    F=load_source(base/'fullblock_runtime.py','_m2_pinned_fullblock_bindings',prep['fullblock_runtime.py'])
    return context,library,adapter,F,guard


def observer(state):
    from observation.fullblock_attention import Fixed93FullblockAttentionObservation
    if state['arm']=='old':return Fixed93FullblockAttentionObservation
    name='observation.narrow_fullblock_attention'
    path=Path(__file__).with_name('narrow_fullblock_attention.py')
    module=load_source(path,name,state['own']['files']['narrow_fullblock_attention.py'])
    return module.Fixed93FullblockAttentionObservation
