"""Pinned 92-source classcompile. --preflight-only never starts Java."""
import argparse,hashlib,json,signal,shutil,time
from contextlib import contextmanager
from pathlib import Path
import owned_compile
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
TOTAL_SECONDS=120
WORK_SECONDS=108
CLEANUP_STOP_SECONDS=116

@contextmanager
def alarm_until(deadline):
    if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('preexisting alarm')
    def alarm(signum,frame):raise TimeoutError('absolute stage deadline')
    previous=signal.signal(signal.SIGALRM,alarm)
    try:
        if time.monotonic()>=deadline:raise TimeoutError('stage budget exhausted')
        signal.setitimer(signal.ITIMER_REAL,max(.001,deadline-time.monotonic()))
        yield
        if time.monotonic()>=deadline:raise TimeoutError('stage deadline')
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

def run(output,preflight_only,source_root,dependency_cache,java_path):
    start=time.monotonic();stop=start+TOTAL_SECONDS;work_stop=start+WORK_SECONDS;cleanup_stop=start+CLEANUP_STOP_SECONDS
    with alarm_until(work_stop):
        output=output.absolute()
        if output.exists() or output.is_symlink():raise ValueError('fresh attempt output required')
        pins=json.loads((HERE/'PLANNED_SOURCE_PINS.json').read_text());deps=json.loads((HERE/'dependency_pins.json').read_text())
        runner=json.loads((HERE/'RUNNER_PINS.json').read_text())
        cache=dependency_cache.resolve();java=java_path.resolve();source_root=source_root.resolve()
        report=dict(status='NOT_COMPLETED',scala_class_compile_pass=False,compiler_started=False,elaboration=False,rtl=False,numerical=False,
            protocol_validation=False,source_count=len(pins),source_sha256=pins,total_absolute_seconds=120,work_seconds=108,
            cleanup_deadline_seconds=116,postcheck_deadline_seconds=120,java_heap_limit_bytes=1024*1024*1024,
            whole_process_memory_hard_limit=None,jvm_active_processor_count=1,child_cpu_affinity_count=1,
            runner_manifest_sha256=sha(HERE/'RUNNER_PINS.json'))
        def verify(src):
            for rel,h in runner.items():
                if sha(HERE/rel)!=h:raise ValueError('runner pin drift: '+rel)
            for rel,h in deps['jars'].items():
                if sha(cache/rel)!=h:raise ValueError('jar drift: '+rel)
            if sha(java)!=deps['java_sha256'] or sha(java.parent.parent/'release')!=deps['java_release_sha256']:raise ValueError('JDK drift')
            actual={str(p.relative_to(src)):sha(p) for p in src.rglob('*.scala')}
            if actual!=pins or len(pins)!=92:raise ValueError('92-source closure drift')
            if any(p.is_symlink() for p in src.rglob('*')):raise ValueError('source symlink')
        verify(source_root)
        if preflight_only:
            print(json.dumps(dict(preflight_pass=True,source_count=92,jar_count=len(deps['jars']),compiler_started=False,
                                 runner_manifest_sha256=report['runner_manifest_sha256'])));return
        output.mkdir(parents=True,exist_ok=False)
        (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
        src=output/'scala';shutil.copytree(source_root,src);verify(src)
        classes=output/'classes';classes.mkdir()
        cp=':'.join(str(cache/n) for n in sorted(deps['jars']))
        plugin=cache/'org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
        argv=[str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,
              '-Xplugin:'+str(plugin),'-language:reflectiveCalls','-d',str(classes)]+[str(src/n) for n in sorted(pins)]
        (output/'argv.json').write_text(json.dumps(argv,indent=2)+'\n')
        report['compiler_start_attempted']=True
        (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
        log=(output/'compiler.log').open('wb')
    with log:
        report.update(owned_compile.execute(argv,cwd=output,classes=classes,log=log,cleanup_helper=HERE/'strict_cleanup.py',
                                           absolute_stop=cleanup_stop,work_stop=work_stop))
    # No JVM remains before this stage; same entry deadline, never restarted.
    with alarm_until(stop):
        verify(source_root);verify(src)
        if owned_compile.tree_size(classes)>owned_compile.TREE_SOFTCAP_BYTES:raise ValueError('final class softcap')
        report['classes']={str(p.relative_to(classes)):sha(p) for p in classes.rglob('*.class')}
        report['class_count']=len(report['classes']);report['inputs_reverified']=True
        report['scala_class_compile_pass']=report['exit_code']==0 and report['cleanup_complete'] and report['error'] is None
        report['status']='PASS_SCALA_CLASS_COMPILE_ONLY' if report['scala_class_compile_pass'] else 'FAIL_SCALA_CLASS_COMPILE'
        report['elapsed_seconds']=time.monotonic()-start
        temp=output/'receipt.pending.json';temp.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        if time.monotonic()>=stop:raise TimeoutError('receipt deadline')
        temp.replace(output/'receipt.json')
        print(json.dumps({k:v for k,v in report.items() if k not in ('classes','source_sha256','cleanup_proof')},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--preflight-only',action='store_true');mode.add_argument('--execute-approved-once',action='store_true')
    p.add_argument('--source-root',required=True,type=Path);p.add_argument('--dependency-cache',required=True,type=Path);p.add_argument('--java',required=True,type=Path)
    x=p.parse_args();run(x.output,x.preflight_only,x.source_root,x.dependency_cache,x.java)
