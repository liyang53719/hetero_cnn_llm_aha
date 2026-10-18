"""One bounded read-only static check of the preserved Host93 SV; never emits."""
import argparse,hashlib,json,os,resource,signal,stat,sys,time,types
from pathlib import Path
CHECKER_BYTES=31470
CHECKER_SHA='33820c6f28dbc1e90185bbe8cdb3911acb41934a01ec4adc0c933901a2fdf676'
SV_BYTES=76366612
SV_SHA='2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'
GENERATION_REVIEW_SHA='b170f06c47d83c3dfd75e5f83962168aad16765305e2292f54ae9d30a0a5cc46'
REPORT_CAP=2*1024*1024
PHASE='unarmed'


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def clean(path):
    path=Path(path).absolute()
    require('..' not in path.parts and not any(p.is_symlink() for p in (path,*path.parents)),'unsafe path')
    return path


def source(path):
    path=clean(path);require(path.is_file() and path.stat().st_size==CHECKER_BYTES,'checker size')
    with path.open('rb') as stream:raw=stream.read(CHECKER_BYTES+1)
    require(len(raw)==CHECKER_BYTES and sha(raw)==CHECKER_SHA,'checker source SHA')
    return raw


def load_checker(path):
    raw=source(path);module=types.ModuleType('fixed_readonly_host93_structure');module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def read_sv(path,keep):
    path=clean(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);require(stat.S_ISREG(before.st_mode) and before.st_size==SV_BYTES,'exact regular SV size')
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        h=hashlib.sha256();count=0;raw=None
        with os.fdopen(fd,'rb',closefd=False) as stream:
            if keep:
                raw=stream.read(SV_BYTES+1);count=len(raw);h.update(raw)
            else:
                while True:
                    block=stream.read(min(65536,SV_BYTES-count+1))
                    if not block:break
                    count+=len(block);require(count<=SV_BYTES,'SV grew');h.update(block)
        require(count==SV_BYTES and h.hexdigest()==SV_SHA,'exact original SV SHA')
        after=os.fstat(fd);require(identity(before)==identity(after),'SV changed while reading')
        return raw,identity(after)
    finally:os.close(fd)


def usage():
    r=resource.getrusage(resource.RUSAGE_SELF)
    return {'user_cpu_seconds':r.ru_utime,'system_cpu_seconds':r.ru_stime,'maxrss_kib':r.ru_maxrss,
            'scope':'dedicated Python checker process including preflight, parser and postflight; no child',
            'maxrss_is_whole_process_peak_not_difference':True}


def arm(stop,phase):
    global PHASE
    PHASE=phase;left=stop-time.monotonic();require(left>0,'shared structure deadline exhausted')
    signal.setitimer(signal.ITIMER_REAL,left)


def expired(_sig,_frame):raise TimeoutError('structure '+PHASE+' deadline')


def limits():
    allowed=os.sched_getaffinity(0);require(bool(allowed),'empty affinity');os.sched_setaffinity(0,{min(allowed)})
    resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
    resource.setrlimit(resource.RLIMIT_CPU,(80,80))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(REPORT_CAP,REPORT_CAP))


def save(path,value):
    raw=(json.dumps(value,sort_keys=True)+'\n').encode();require(len(raw)<=REPORT_CAP,'report 2MiB cap')
    with path.open('xb') as stream:stream.write(raw);stream.flush()


def execute(args,entry):
    stop=entry+90;pre_stop=entry+10;latest_check=entry+80
    require(sys.platform=='linux','Linux RSS and resource units required')
    require(len(GENERATION_REVIEW_SHA)==64 and all(c in '0123456789abcdef' for c in GENERATION_REVIEW_SHA),'generation inventory review PENDING')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing timer refused')
    old=signal.signal(signal.SIGALRM,expired);created=False;identity=None
    try:
        arm(pre_stop,'preflight10s');limits()
        sv=clean(args.sv);checker_path=clean(args.checker);output=clean(args.output)
        require(output.parent.is_dir() and not output.exists(),'fresh report directory required')
        require(not any(output.is_relative_to(p) or p.is_relative_to(output) for p in (sv.parent,checker_path.parent,Path(__file__).resolve().parent)),'disjoint report output')
        checker=load_checker(checker_path);before=usage();raw,identity=read_sv(sv,True)
        output.mkdir(mode=0o700);created=True
        require(time.monotonic()<pre_stop,'preflight10s exhausted')
        arm(min(latest_check,time.monotonic()+70),'check70s')
        result=checker.check_bytes(raw)
        require(result['status']=='PASS' and result['bytes']==SV_BYTES and result['sha256']==SV_SHA,'same-buffer checker result identity')
        del raw;arm(stop,'postflight90s')
        _,post_identity=read_sv(sv,False);require(post_identity==identity,'original SV metadata changed')
        source(checker_path)
        evidence={'status':'STATIC_STRUCTURE_EVIDENCE_PENDING_OUTER_EXIT0','terminal_success':False,
            'generation_inventory_review_sha256':GENERATION_REVIEW_SHA,'checker_sha256':CHECKER_SHA,
            'sv_sha256':SV_SHA,'sv_bytes':SV_BYTES,'structure':result,'before_usage':before,'after_usage':usage(),
            'entry_to_postflight_seconds':time.monotonic()-entry,'sv_unchanged':True,
            'acceptance_requires':'original outer exit0 and elapsed<=90 and independent static-structure-only actual review',
            'no_elaboration_or_rtl_or_host_execution':True,
            'qualified_scope':'SAME_SV_FIXED_INTERFACE_EXTERNAL_BOUNDARY_TAP_STATIC_ONLY',
            'dpi_provider_and_linkage_qualification':'PENDING',
            'full_metadata_reverse_projection_qualification':'PENDING'}
        save(output/'STRUCTURE_EVIDENCE.json',evidence);require(time.monotonic()<stop,'final evidence deadline')
        return evidence
    except BaseException as error:
        # Every partial report is non-success. Hard CPU/AS/OS failure may prevent
        # this best-effort record; original outer termination remains authoritative.
        kind=type(error).__name__;message=str(error)[:1000];failed_phase=PHASE
        if created:
            try:
                arm(stop,'failure_postflight90s');unchanged=False;post_error=None
                try:
                    _,post_identity=read_sv(sv,False);unchanged=post_identity==identity;source(checker_path)
                except BaseException as post:post_error=type(post).__name__+': '+str(post)[:500]
                save(output/'FAILURE.json',{'status':'INCOMPLETE_STATIC_STRUCTURE','terminal_success':False,'error_type':kind,'error':message,
                    'phase':failed_phase,'sv_sha256_expected':SV_SHA,'sv_unchanged_rechecked':unchanged,'postcheck_error':post_error,
                    'usage':usage(),'retained_sv':True,'no_retry_or_regeneration':True})
            except BaseException:pass
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)


def main():
    entry=time.monotonic();p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checker',type=Path,required=True);p.add_argument('--sv',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--execute-reviewed-readonly',action='store_true');args=p.parse_args()
    if args.execute_reviewed_readonly:
        require(args.sv is not None and args.output is not None,'explicit SV and output required');r=execute(args,entry)
        print(json.dumps({k:r[k] for k in ('status','terminal_success','sv_sha256','sv_unchanged')},sort_keys=True))
    else:
        require(args.sv is None and args.output is None,'source preflight takes checker only');source(args.checker)
        print(json.dumps({'status':'SOURCE_ONLY','checker_sha256':CHECKER_SHA,'generation_review_sha256':GENERATION_REVIEW_SHA,'actual_sv_read':False},sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
