"""Real source-bound module loading, stopped before model ELF adapter loading.

Only the initialization-purpose authority is a declared test fixture. The full
initialize CodeType, import graph, installed CalibrationIO policy and original
factory module/descriptor/class checks execute. No ADMISSION or consumed state
is created. The original runtime M16 metadata packer and two fixed Git source
queries execute; no tensor payload or model constructor executes. Runtime C extensions may load; no model ELF/reset/job is allowed.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import tempfile
import time
import types

HERE=Path(__file__).resolve().parent


def need(ok,message):
    if not ok: raise AssertionError(message)


class BeforeModelAdapter(Exception):
    pass


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--manifest-sha',required=True)
    args=p.parse_args();started=time.monotonic();cpu=time.process_time()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(512<<20,)*2);resource.setrlimit(resource.RLIMIT_CPU,(30,)*2)
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('module-load preflight 30s')))
    signal.setitimer(signal.ITIMER_REAL,30)
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[key]='1'
    events=[];denied=[];blocked_calls=[];metadata_calls=[];git_queries=[]
    base=Path(args.base)
    def audit(event,argv):
        if event=='ctypes.dlopen':
            events.append(dict(event=event,target=argv[0]))
            if argv[0] is None:return  # stdlib ctypes process handle only
        elif event=='subprocess.Popen':
            executable,argv,cwd,env=argv
            expected=([ 'git','show','HEAD:chisel/continuous_prefill/tests/qwen2_block.cpp'],['git','rev-parse','HEAD'])
            need(executable in ('git','/usr/bin/git') and argv in expected and Path(cwd)==base/'source',
                 'only exact original source-provenance Git queries')
            need(env is None and all(os.environ.get(k)==v for k,v in state['runtime_pins']['git_environment'].items()),
                 'original exact fixed Git environment inherited')
            need(len(git_queries)<2 and argv==expected[len(git_queries)],'exact Git query order/count')
            git_queries.append(list(argv));return
        elif event=='import' and argv[1] and str(argv[1]).endswith('.so'):
            events.append(dict(event='runtime_extension_import',path=argv[1]));return
        elif not (event.startswith(('ctypes.','socket.','subprocess.')) or event in
                  ('os.system','os.exec','os.spawn','os.fork','os.posix_spawn')):
            return
        denied.append(event);raise RuntimeError('module-load preflight execution denied: '+event)
    sys.addaudithook(audit)
    raw=(HERE/'SOURCE_MANIFEST.json').read_bytes()
    need(hashlib.sha256(raw).hexdigest()==args.manifest_sha,'new source manifest')
    own=json.loads(raw);base=Path(args.base)
    need(str(base)==own['base']['path'],'exact source base')
    raw=(HERE/'m2_authority.py').read_bytes();pin=own['files']['m2_authority.py']
    need(dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())==pin,'authority source')
    a=types.ModuleType('m2_authority');a.__file__=str(HERE/'m2_authority.py');sys.modules[a.__name__]=a
    exec(compile(raw,a.__file__,'exec',dont_inherit=True),vars(a))
    manifest=a.parse(a.checked(base/'SOURCE_MANIFEST.json',own['base']['manifest']))
    state=dict(base=base,source_manifest=manifest,own=own,manifest_sha256=args.manifest_sha,
        parent=dict(pid=os.getppid()),out=HERE/'cold03'/'import_metadata',arm='old')
    need(not state['out'].exists(),'fresh metadata-only test directory')
    (state['out']/'tmp').mkdir(parents=True)
    tempfile.tempdir=str(state['out']/'tmp')
    a.load_source(HERE/'m2_io.py','m2_io',own['files']['m2_io.py'])
    bridge=a.load_source(HERE/'m2_runtime.py','_m2_import_closure_bridge',own['files']['m2_runtime.py'])
    # Match the actual previously successful startup statements, not an alias.
    startup=ast.parse(a.checked(base/'integration/runner.py',manifest['preparation_files']['integration/runner.py']))
    newtree=ast.parse(a.checked(HERE/'m2_runtime.py',own['files']['m2_runtime.py']))
    wanted={'candidates.qwen2_fixed93_attention.binding','candidates.qwen2_fixed93_attention.owner',
            'observation.fullblock_attention'}
    oldimports=[ast.dump(n) for n in ast.walk(startup) if isinstance(n,ast.ImportFrom) and n.module in wanted]
    initialize=next(n for n in newtree.body if isinstance(n,ast.FunctionDef) and n.name=='initialize')
    newimports=[ast.dump(n) for n in initialize.body if isinstance(n,ast.ImportFrom) and n.module in wanted]
    need(newimports==oldimports and len(newimports)==3,'exact successful runner import order')
    purposes=[];seen={};original_load=bridge.load_source
    def purpose(value):
        need(not purposes and value=='initialize_m2_runtime','test only one initialization-purpose fixture')
        purposes.append(value);return state
    def stop_before_adapter(path,name,pin):
        if Path(path)==HERE/'native_adapter.py':
            frame=sys._getframe(1)
            need(frame.f_code is bridge.initialize.__code__ and name=='_m2_native_adapter' and
                 pin==own['files']['native_adapter.py'],'exact pre-adapter stop')
            need(not seen,'one stop');seen.update(context=frame.f_locals['context'],guard=frame.f_locals['guard'])
            raise BeforeModelAdapter()
        return original_load(path,name,pin)
    bridge.require_actual_runtime=purpose;bridge.load_source=stop_before_adapter
    fixture_path=base/'source/candidates/qwen2_resident_matrix/ffn_public/fixture.py'
    runtime_path=base/'source/candidates/qwen2_resident_matrix/ffn_public/check_fullgraph_numeric.py'
    def exact_function(path,name):
        rel=str(path.relative_to(base/'source'))
        raw=a.checked(path,dict(bytes=manifest['source_bytes'][rel],sha256=manifest['source_sha256'][rel]))
        return next(c for c in compile(raw,str(path),'exec',dont_inherit=True).co_consts if type(c) is types.CodeType and c.co_name==name)
    fixture_code=exact_function(fixture_path,'make_qwen2_21_fixture')
    caller_code=exact_function(runtime_path,'runtime')
    def profile(frame,event,arg):
        if frame.f_code==fixture_code:
            if event=='call':
                need(frame.f_back.f_code==caller_code and not metadata_calls and
                     {k:frame.f_locals[k] for k in ('rows','epoch','relocate','max_tokens')}==
                     dict(rows=16,epoch=7,relocate=0,max_tokens=1024),'only original M16 metadata fixture')
                metadata_calls.append(dict(rows=16,epoch=7,relocate=0,max_tokens=1024))
            elif event=='return':
                need(arg.scope=='QWEN2_21_METADATA_ONLY' and arg.provenance['tensor_payloads_materialized'] is False,
                     'metadata-only fixture return')
                metadata_calls[0]['returned_scope']=arg.scope
            return
        if event!='call':return
        filename=frame.f_code.co_filename
        if filename.startswith(str(base/'source')+'/') and (frame.f_code.co_name in
            ('make_qwen2_21_fixture','advance','tick','accept_step','_op') or
            (frame.f_code.co_name=='__init__' and frame.f_code.co_qualname.split('.')[0] in
             ('Fixed93AttentionOwner','MatrixService','ProfiledMatrixService','ScalarService','PhysicalMemory'))):
            blocked_calls.append(frame.f_code.co_qualname)
            raise RuntimeError('model/constructor body forbidden in module-load preflight')
    sys.setprofile(profile)
    try:
        try:bridge.initialize(state)
        except BeforeModelAdapter:pass
        else:raise AssertionError('missing pre-adapter sentinel')
        need(seen and purposes==['initialize_m2_runtime'] and a._STATE is None and not a._PURPOSES,
             'no actual authority created or consumed')
        need(not seen['guard'].native_events and '_m2_native_adapter' not in sys.modules,
             'model adapter/ELF never loaded before static verification')
        # The hard stop has returned from initialize. All following calls are
        # pinned F source/module/class validation; no model body is invoked.
        # Keep both audit hooks installed, avoid profiling these static checks.
        sys.setprofile(None)
        F=a.load_source(base/'fullblock_runtime.py','_m2_preflight_exact_factory',manifest['preparation_files']['fullblock_runtime.py'])
        context=seen['context']
        # _modules only checks keys and source identities; these placeholders are
        # explicitly NOT native receipts and no _native/native_check is called.
        context=dict(context,built=None,reuse=None)
        explicit=F._modules(context)
        closure=F.LoadedClosure({str(base/'source'/k):v for k,v in manifest['source_sha256'].items()})
        anchors=a.parse(a.checked(base/'capture/anchors.json',manifest['preparation_files']['capture/anchors.json']))
        codes=a.parse(a.checked(base/'observation/TRACE_CODES.json',manifest['preparation_files']['observation/TRACE_CODES.json']))['loaded_code_descriptors']
        need(len(anchors)==50 and len(codes)==24,'50+24 descriptor inventory')
        rows=[]
        def descriptor(key,relative,qualname,expected=None):
            module=F._resolve(relative,explicit);d=closure.function(module,qualname)
            if expected:need(d['sha256']==expected['sha256'] and d['firstlineno']==expected['firstlineno'],'anchor source')
            rows.append(dict(key=key,relative_path=relative,module_name=module.__name__,loaded_path=module.__file__,
                qualname=qualname,sha256=d['sha256'],firstlineno=d['firstlineno'],route='explicit_dynamic' if relative in explicit else 'canonical'))
        for key,spec in anchors.items():descriptor(key,spec['relative_path'],spec['qualname'],spec)
        for i,(name,cls,member) in enumerate(codes):descriptor('attention_'+str(i),name.replace('.','/')+'.py',(cls+'.' if cls else '')+member)
        # Reuse the exact class selection declarations, not a second loose list.
        tree=ast.parse(a.checked(HERE/'m2_context.py',own['files']['m2_context.py']))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='construct_m2_context')
        select=[]
        for node in fn.body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('names','modules','selected_classes'):
                select.append(node)
        need(len(select)==3,'exact class-module source declarations')
        ns=dict(F=F,explicit=explicit)
        exec(compile(ast.Module(body=select,type_ignores=[]),str(HERE/'m2_context.py'),'exec',dont_inherit=True),ns)
        need(len(ns['names'])==9 and len(ns['selected_classes'])==11,'nine modules/eleven classes')
        for module,name in ns['selected_classes']:closure.cls(vars(module)[name])
        from observation import source_guard
        from observation.event_stream import load_codec
        from capture.wholeblock import WholeblockObservation
        from capture import token_encoder
        declaration=dict(files=manifest['preparation_files'])
        need(F._check_observation_helpers(declaration) is source_guard,'real observation helper checks')
        F._check_token_helpers(declaration)
        closure.revalidate()
        need(len({r['relative_path'] for r in rows})==16,'sixteen descriptor modules')
        external=seen['guard'].layout.finish()
        need(not denied and not blocked_calls and not seen['guard'].native_events,
             'no model native/reset/constructor/loop attempt')
        need('_m2_native_adapter' not in sys.modules and len(metadata_calls)==1 and len(git_queries)==2,
             'adapter never imported/exact metadata and provenance initialization')
        need(not any(x.is_file() for x in state['out'].rglob('*')),'normal metadata cleanup completed')
        result=dict(status='PASS_REAL_MODULE_DESCRIPTOR_LOAD_ONLY',source_manifest_sha256=args.manifest_sha,
            descriptor_count=len(rows),descriptor_module_count=16,descriptor_rows=rows,
            selected_class_count=11,selected_module_paths={k:v.__file__ for k,v in ns['modules'].items()},
            helper_checks=['source_guard','event_stream','fixed_token_table','token_encoder'],
            native_model_ELF_loaded=False,native_reset_executed=False,model_fixture_constructed=False,metadata_fixture_calls=metadata_calls,git_queries=git_queries,model_job_executed=False,
            authority_scope='Only initialize purpose mocked; actual authority state remains None; no ADMISSION/LEASE/CONSUMED',
            native_receipt_placeholders='built=None/reuse=None used solely for _modules key check, not native evidence',
            stopped_before='native_adapter.py source import and adapter.load',runtime_initialization_events=events,
            denied_attempts=denied,blocked_model_calls=blocked_calls,external_layout=external,
            wall_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            actual_M2_executed=False,M128_pass=False,numerical_pass=False)
        print(json.dumps(result,sort_keys=True))
    finally:
        sys.setprofile(None);signal.setitimer(signal.ITIMER_REAL,0)
    return 0


if __name__=='__main__':raise SystemExit(main())
