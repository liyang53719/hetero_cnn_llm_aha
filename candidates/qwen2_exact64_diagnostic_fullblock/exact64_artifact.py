"""Fresh exact64 code artifact. This identity never enters official reference pins."""
import hashlib
import json
import os
import time
from pathlib import Path
import subprocess
from candidates.qwen2_exact64_projection_integration import kernel
from . import native_artifact as N
ROOT=N.ROOT
DIRECTORY=ROOT/'work/qwen2_exact64_diagnostic_native/ci01'
LIBRARY=DIRECTORY/'exact64.so'
RECEIPT=DIRECTORY/'compile.json'
FLAGS=('-std=c++17','-O2','-shared','-fPIC','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize')
STATUS='VERIFIED_FRESH_EXACT64_DIAGNOSTIC_CODE'
def need(ok,message):
    if not ok:raise ValueError(message)
def identity_file(path):
    raw=N.canonical(Path(path)).read_bytes()
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def compiler():
    path=Path('/usr/bin/g++').resolve(strict=True)
    value=identity_file(path)
    version=subprocess.check_output([str(path),'--version'],text=True,timeout=10).splitlines()[0]
    return dict(path=str(path),version=version,**value)
def argv():
    return ['/usr/bin/g++',*FLAGS,str(kernel.HERE/'kernel.cpp'),'-o',str(LIBRARY)]
def verify(*,compiler_probe=False):
    need(N.canonical(RECEIPT).stat().st_size<=262144,'bounded exact64 receipt')
    value=json.loads(RECEIPT.read_bytes())
    need(type(value) is dict and set(value)=={'schema','status','compiler','argv','sources','library','scope'},'exact64 receipt schema')
    need(type(value['schema']) is int and value['schema']==1 and value['status']==STATUS and value['scope']=='DIAGNOSTIC_SOFTWARE_OWNER','exact64 receipt scope')
    need(value['argv']==argv() and value['sources']==kernel.source_check(),'exact64 source/invocation drift')
    comp=value['compiler'];need(type(comp) is dict and set(comp)=={'path','version','bytes','sha256'},'exact64 compiler schema')
    need(type(comp['version']) is str and comp['version'] and comp['path']==str(Path('/usr/bin/g++').resolve(strict=True)),'exact fixed compiler')
    need(type(comp['bytes']) is int and identity_file(Path(comp['path']))=={k:comp[k] for k in ('bytes','sha256')},'exact64 compiler ELF drift')
    if compiler_probe:need(comp==compiler(),'exact64 compiler version drift')
    with N.canonical(LIBRARY).open('rb') as stream:
        need(stream.read(6)==b'\x7fELF\x02\x01','exact64 requires little-endian ELF64')
    expected=dict(path=str(LIBRARY.relative_to(ROOT)),**identity_file(LIBRARY))
    need(type(value['library']) is dict and type(value['library'].get('bytes')) is int and value['library']==expected,'exact64 ELF drift')
    return dict(receipt=dict(path=str(RECEIPT.relative_to(ROOT)),**identity_file(RECEIPT)),library=expected)
def build():
    need(not DIRECTORY.exists(),'single fresh exact64 build directory')
    before=kernel.source_check();comp=compiler()
    DIRECTORY.mkdir(parents=True,exist_ok=False)
    # Own the compiler process group so a bounded build cannot orphan cc1/as/ld.
    from candidates.qwen2_live_attention_model_m128_bounded.v2.launch import terminate_group,group_exists
    from candidates.qwen2_supervisor_recovery.observation import SignalScope
    child=None;signals=SignalScope();deadline=time.monotonic()+30
    log_path=DIRECTORY/'build.log';log=log_path.open('xb')
    try:
        signals.start()
        child=subprocess.Popen(argv(),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        signals.check()
        while child.poll() is None:
            signals.check()
            need(time.monotonic()<deadline,'exact64 compiler wall timeout')
            need(log_path.stat().st_size<=1048576,'exact64 compiler log cap')
            time.sleep(.05)
        signals.check()
        need(child.returncode==0,'exact64 compile failed')
    finally:
        signals.cleaning()
        try:
            if child is not None and group_exists(child.pid):
                terminate_group(child,cleanup_deadline=time.monotonic()+3)
                need(not group_exists(child.pid),'exact64 compiler cleanup incomplete')
        finally:
            signals.stop();log.close()
    need(kernel.source_check()==before and compiler()==comp,'exact64 build boundary changed')
    value=dict(schema=1,status=STATUS,compiler=comp,argv=argv(),sources=before,
        library=dict(path=str(LIBRARY.relative_to(ROOT)),**identity_file(LIBRARY)),scope='DIAGNOSTIC_SOFTWARE_OWNER')
    with RECEIPT.open('x') as stream:json.dump(value,stream,sort_keys=True,allow_nan=False);stream.write('\n')
    return verify(compiler_probe=True)
def identity():
    # Independent binding digest comes only from the successful current binder.
    expected=os.environ.get(N.BINDING_ENV,'')
    need(len(expected)==64 and set(expected)<=set('0123456789abcdef') and expected!='0'*64,'explicit exact64 binding identity')
    need(N.canonical(N.BINDING).stat().st_size<=262144,'bounded exact64 binding')
    raw=N.BINDING.read_bytes();need(hashlib.sha256(raw).hexdigest()==expected,'exact64 binding drift')
    binding=json.loads(raw)
    need(binding.get('status')=='LOCAL_SAME_JOB_PAIR_POLICY_CONDITIONS_SATISFIED_ORACLE_ONLY','fresh oracle-only binding')
    current=verify()
    need(binding['context']['exact64_artifact']==current,'bound exact64 artifacts drift')
    return {role:{**spec,'path':str(ROOT/spec['path'])} for role,spec in current.items()}
