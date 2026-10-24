"""One fresh explicitly admitted success-M2 arm; never a fullblock runner."""
import argparse
import hashlib
import json
import math
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
    if not ok: raise ValueError(message)


def bootstrap(expected):
    raw=(HERE/'SOURCE_MANIFEST.json').read_bytes()
    need(len(raw)<1<<20 and hashlib.sha256(raw).hexdigest()==expected,'explicit source pin required')
    value=json.loads(raw)
    spec=value['files']['m2_authority.py'];path=HERE/'m2_authority.py'
    raw=path.read_bytes()
    need(len(raw)==spec['bytes'] and hashlib.sha256(raw).hexdigest()==spec['sha256'], 'authority source pin')
    need('m2_authority' not in sys.modules,'no preloaded M2 authority')
    module=types.ModuleType('m2_authority');module.__file__=str(path);module.__package__=''
    sys.modules[module.__name__]=module
    exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),vars(module))
    return module


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual',action='store_true')
    for name in ('arm','base','out','admission','admission-sha','manifest-sha'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv)
    need(args.actual,'no default actual execution')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'-I -S -B required')
    wall,cpu=time.monotonic(),time.process_time()
    authority=bootstrap(args.manifest_sha)
    state=authority.admit(arm=args.arm,base=args.base,out=args.out,admission=args.admission,
                          admission_sha=args.admission_sha,manifest_sha=args.manifest_sha)
    budget=state['budget'];deadline=state['lease']['work_stop']
    need(deadline>time.monotonic(),'current shared work deadline')
    resource.setrlimit(resource.RLIMIT_AS,(budget['rss_bytes'],budget['rss_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE,(budget['file_bytes'],budget['file_bytes']))
    resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    def expired(*_): raise TimeoutError('shared calibration work deadline')
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,max(0.001,deadline-time.monotonic()))
    sys.path.insert(0,str(HERE))
    modules={}
    for name in ('m2_io','m2_runtime','m2_context','success_driver'):
        modules[name]=authority.load_source(HERE/(name+'.py'),name,state['own']['files'][name+'.py'])
    out=state['out'];(out/'tmp').mkdir();tempfile.tempdir=str(out/'tmp')
    context=None;guard=None;report=None;timings={}
    timed=modules['success_driver'].timed
    try:
        runtime,library,adapter,F,guard=timed(timings,'source_runtime_and_existing_elf_load',
            lambda:modules['m2_runtime'].initialize(state))
        value,_=adapter.pins()
        import ctypes
        def native_check():
            need(time.monotonic()<deadline,'shared deadline before native identity check')
            need(adapter._LOADED is library,'same existing library object')
            fresh=adapter._loaded_receipt(library,value,state['runtime_pins'],ctypes)
            need(fresh==runtime['reuse'],'loaded native receipt changed')
            return fresh,ctypes.CDLL
        declaration={'files':dict(state['source_manifest']['preparation_files'],
                                 **{'SOURCE_MANIFEST.json':state['own']['base']['manifest']})}
        context=timed(timings,'real_lazy_context_constructor_and_binding',lambda:
            modules['m2_context'].construct_m2_context(F=F,runtime_context=runtime,
                source_manifest=state['source_manifest'],declaration=declaration,library=library,
                out=out,trace_limits=budget['wholeblock_trace_limits'],
                attention_trace_limits=budget['attention_trace_limits'],
                root_guard=authority.require_actual_runtime,deadline=deadline,native_check=native_check))
        Capture=modules['m2_runtime'].observer(state)
        timed(timings,'preloop_context_verification',context['verify_context'])
        report=modules['success_driver'].run_one(variant=args.arm,Capture=Capture,
            whole=context['whole'],owner=context['owner'],Job=context['Job'],Response=context['Response'],
            source_root=context['source_root'],source_manifest=context['source_manifest'],
            trace_limits=budget['attention_trace_limits'],out=out,deadline=deadline,
            root_guard=authority.require_actual_runtime)
        timed(timings,'postseal_context_verification',context['verify_context'])
        need(time.monotonic()<deadline,'shared deadline after sealed case')
        for name,pin in state['own']['files'].items():
            authority.checked(HERE/name,pin,retain=False,cap=2<<20)
        result=dict(status='PASS_LIMITED_SUCCESS_M2_ARM_PENDING_PAIR_DIFF',arm=args.arm,
            scope='INCOMPLETE_WHOLEBLOCK',actual_owner_M=2,fullblock_pass=False,M128_execution=False,
            numerical_acceptance=False,source_manifest_sha256=args.manifest_sha,
            base_source_manifest_sha256=authority.BASE_MANIFEST_SHA,
            admission_sha256=args.admission_sha,budget_sha256=state['own']['files']['BUDGET.json']['sha256'],
            observer_policy=('original-full-identity-every-watched-callback' if args.arm=='old' else 'op-evidence-boundary-v1'),
            policy_sha256=state['own']['files']['POLICY.json']['sha256'],
            process=authority.process(os.getpid()),parent=state['parent'],
            constructor_contains_native_reset_and_guard_probes=True,
            official_input_payload_read=False,reference_payload_read=False,compilation_performed=False,
            timings=timings,total_child_wall_seconds=time.monotonic()-wall,
            total_child_cpu_seconds=time.process_time()-cpu,case=report,
            exact_read_routes=sorted(guard.reads),native_initialization_events=guard.native_events,
            frozen_external_metadata_terminal=guard.layout.finish(),
            fixture_cleanup_directory_reads=guard.cleanup_directory_reads,
            native_identity=runtime['reuse'],callback_counter_added=False,
            callback_counter_reason='No production callback wrapper or observer source change; real event and step counts retained')
        modules['success_driver'].save(out/'ARM_RESULT.json',result)
        print(json.dumps({k:result[k] for k in ('status','arm','scope','total_child_wall_seconds','total_child_cpu_seconds')},sort_keys=True))
        return 0
    finally:
        # No continuation/retry after a failed arm. Closing observation is not
        # advertised as draining an aborted model; parent terminates the process.
        if context is not None: context['whole'].close()
        signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':
    raise SystemExit(main())
