"""One dedicated process, one JVM version-only child, fixed CLASS WNOWAIT reuse."""
import argparse,hashlib,json,resource,signal,sys,time,types
from pathlib import Path

GATE_BYTES=12457
GATE_SHA='dddc212e4acf5d7fe3851f57a12c41b31d82a84e4a05cb45a61ef4dc7218c3f3'
PROJECTION_SHA='bec911354938d955cf16fa808ec346a9f38604e149f00eaa9efa594468d0840f'


def require(ok,why):
    if not ok:raise ValueError(why)


def load_gate(directory):
    path=directory/'run_class_gate.py'
    require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),'fixed CLASS source path')
    require(path.stat().st_size==GATE_BYTES,'CLASS source size')
    raw=path.read_bytes();require(len(raw)==GATE_BYTES and hashlib.sha256(raw).hexdigest()==GATE_SHA,'CLASS source SHA')
    module=types.ModuleType('fixed_CLASS_source_for_version_only');module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def usage():
    r=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'user_cpu_seconds':r.ru_utime,'system_cpu_seconds':r.ru_stime,
            'maxrss_kib':r.ru_maxrss,'major_faults':r.ru_majflt,'minor_faults':r.ru_minflt,
            'voluntary_context_switches':r.ru_nvcsw,'involuntary_context_switches':r.ru_nivcsw}


def probe_argv(mode,java,cache,jars):
    base=[str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1']
    if mode=='java-version':return base+['-version']
    require(mode=='scala-version','fixed mode')
    cp=':'.join(str(cache/p['relative_destination']) for p in sorted(jars['artifacts'],key=lambda p:p['relative_destination']))
    return base+['-cp',cp,'scala.tools.nsc.Main','-version']


def expired(_signal,_frame):raise TimeoutError('startup shared deadline')


def main():
    entry=time.monotonic();stop=entry+20;pre_stop=entry+4;work_latest=entry+14
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--class-gate',type=Path,required=True);p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--mode',choices=('java-version','scala-version'),required=True)
    p.add_argument('--jar-artifacts',type=Path,required=True);p.add_argument('--java',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute-reviewed-startup',action='store_true')
    args=p.parse_args();require(args.execute_reviewed_startup,'separate startup approval required')
    require(sys.platform=='linux','Linux RSS units required')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing timer refused')
    previous=signal.signal(signal.SIGALRM,expired);g=None;runner=None;created=False;failure=None;record=None
    try:
        remaining=pre_stop-time.monotonic();require(remaining>0,'preflight deadline');signal.setitimer(signal.ITIMER_REAL,remaining)
        g=load_gate(args.class_gate.absolute());plan,sources,jars,deps,projected=g.configuration(args.repo)
        require(hashlib.sha256(projected).hexdigest()==PROJECTION_SHA,'unchanged CLASS WNOWAIT projection')
        output=g.clean(args.output);cache=g.clean(args.jar_artifacts);java=g.clean(args.java)
        require(output.parent.is_dir() and not output.exists(),'fresh output required')
        require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (g.clean(args.repo),cache,g.clean(args.class_gate),Path(__file__).resolve().parent)),'disjoint probe output')
        g.verified_file(java,deps['java_sha256'],1024*1024)
        g.verified_file(java.parent.parent/'release',deps['java_release_sha256'],1024*1024)
        if args.mode=='scala-version':
            for item in jars['artifacts']:g.verified_file(cache/item['relative_destination'],item['sha256'],item['max_transfer_bytes']-1,known_size=item['known_size_bytes'])
        before=usage();require(before['user_cpu_seconds']==0 and before['system_cpu_seconds']==0 and before['maxrss_kib']==0,'dedicated process must have no prior child usage')
        output.mkdir(mode=0o700);created=True;runner=g.supervisor(projected);argv=probe_argv(args.mode,java,cache,jars)
        runner['save'](output/'STARTED.json',{'status':'STARTED_NOT_QUALIFIED','mode':args.mode,'argv':argv,'entry_total_seconds':20,'child_max_work_seconds':10,'AS_bytes':4294967296,'heap_bytes':1073741824,'cpu_affinity_count':1,'rusage_children_before':before,'supervisor_projection_sha256':PROJECTION_SHA})
        require(time.monotonic()<pre_stop,'4s preflight budget');work_stop=min(work_latest,time.monotonic()+10);g.arm(work_stop)
        try:record,log=runner['bounded']('startup',argv,output,output,work_stop-time.monotonic(),10)
        except BaseException as error:failure=error
        after=usage()  # After the existing WNOWAIT cleanup/reap; unique child scope.
        g.arm(stop)
        result={'status':'STARTUP_EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,'mode':args.mode,
                'rusage_children_before':before,'rusage_children_after':after,
                'usage_scope':'only reaped child including preexec and whole JVM lifetime; not Scala phase or JVM-only memory',
                'maxrss_is_cumulative_peak_not_difference':True,'child_cleanup_confirmed':record['cleanup_confirmed'] if record is not None else None,
                'cleanup_receipt':'startup.json',
                'failure_type':None if failure is None else type(failure).__name__,
                'entry_to_postflight_seconds':time.monotonic()-entry,'source_compiled':False,'rtl_generated':False}
        runner['save'](output/'RESULT.json',result)
        require(time.monotonic()<stop,'startup result deadline')
        if failure is not None:raise failure
        expected=b'21.0.12.1' if args.mode=='java-version' else b'Scala compiler version 2.13.16'
        require(expected in log,'expected fixed version output absent')
        require(time.monotonic()<stop,'startup final deadline')
        print(json.dumps(result,sort_keys=True))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
