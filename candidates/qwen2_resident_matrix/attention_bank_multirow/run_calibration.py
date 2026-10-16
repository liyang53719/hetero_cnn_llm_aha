"""Opt-in bounded Fraction calibration, one genuine multirow job per case."""
import argparse,hashlib,json,resource,signal,struct,time,sys,platform
from pathlib import Path
from .oracle import Oracle
from ..attention_matrix_batch.test_model import ExactScalar,fixture,ref_fma,exp_negative
from ..attention_scheduled_numeric.controller import Timing


def words_hash(words):
    digest=hashlib.sha256()
    for word in words:digest.update(struct.pack('<I',word))
    return digest.hexdigest()


def run(rows):
    if type(rows) is not int or rows not in (4,8,16):raise ValueError('calibration shape')
    from .check_sources import check,snapshot
    from .profile import Controller
    check();before=snapshot();started=time.monotonic();cpu_started=time.process_time()
    data=fixture(rows)
    oracle=Oracle(rows,*data)
    phase=time.monotonic();cpu=time.process_time();expected=oracle.run();oracle_seconds=time.monotonic()-phase
    oracle_cpu_seconds=time.process_time()-cpu
    print(json.dumps(dict(phase='reference_complete',rows=rows,elapsed_seconds=time.monotonic()-started)),flush=True)
    scalar=ExactScalar(object())
    # Packed vector lanes do not have the original sequential score-boundary adjacency.
    # Hash every candidate primitive; scores come from its completed result.
    from .oracle import ScalarTrace
    scalar.trace=ScalarTrace(capture_scores=False)
    candidate=Controller(scalar,ref_fma,lambda x:exp_negative(scalar,scalar.client,x),
                         timing=Timing(2,3,0,0),scratch_enabled=True)
    phase=time.monotonic();cpu=time.process_time();actual=candidate.run(rows,*data);candidate_seconds=time.monotonic()-phase
    candidate_cpu_seconds=time.process_time()-cpu
    if actual.output!=expected or actual.scores!=oracle.scores()[1]:raise ValueError('actual original owner mismatch')
    counts=dict(actual.counts);pairs=6*rows*(rows+1)
    if (len(expected)!=1536*rows or len(actual.scores)!=pairs or len(oracle.requests)!=16*pairs or
        counts['matrix_steps']!=96*rows+rows*(rows+1) or
        counts['scratch_read_requests']+counts['scratch_write_requests']!=7*pairs or
        counts['scratch_edges']!=21*pairs+2):raise ValueError('whole-job operation accounting')
    check()
    if snapshot()!=before:raise ValueError('source changed during calibration')
    return dict(status='PASS_MULTIROW_FRACTION_CALIBRATION',rows=rows,one_job_per_pass=True,
        reference_seconds=oracle_seconds,candidate_seconds=candidate_seconds,elapsed_seconds=time.monotonic()-started,
        reference_cpu_seconds=oracle_cpu_seconds,candidate_cpu_seconds=candidate_cpu_seconds,cpu_seconds=time.process_time()-cpu_started,
        runtime=dict(python_version=platform.python_version(),implementation=platform.python_implementation(),machine=platform.machine(),
                     interpreter_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()),
        output_sha256=words_hash(actual.output),scores_sha256=words_hash(actual.scores),
        reference_scalar_sha256=oracle.scalar.trace.hexdigest(),candidate_scalar_sha256=scalar.trace.hexdigest(),
        counts=counts,reference_matrix_requests=len(oracle.requests),
        modeled_ticks=actual.hypothetical_ticks,modeled_ticks_are_hardware=False,
        source_sha256=before,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        native_arithmetic=False,rtl_execution=False,m128_executed=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rows',type=int,choices=(4,8,16),required=True)
    parser.add_argument('--seconds',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 1<=args.seconds<=60:raise SystemExit('calibration budget must be1..60seconds')
    start=time.monotonic()
    def timeout(*_):raise TimeoutError('calibration deadline')
    old=signal.signal(signal.SIGALRM,timeout)
    signal.setitimer(signal.ITIMER_REAL,args.seconds)
    frozen_sources=None
    try:
        from .check_sources import check,snapshot
        check();frozen_sources=snapshot()
        result=run(args.rows)
        if time.monotonic()-start>=args.seconds:raise TimeoutError('late calibration result')
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print(json.dumps(dict(status=result['status'],rows=args.rows,elapsed_seconds=time.monotonic()-start)),flush=True)
    except (ValueError,ArithmeticError,TimeoutError,AttributeError,TypeError,RuntimeError,OSError,KeyError,IndexError) as exc:
        result=dict(status='FAILED_CALIBRATION',rows=args.rows,error_class=type(exc).__name__,elapsed_seconds=time.monotonic()-start,
                    numerical_acceptance=False,m128_executed=False,source_sha256=frozen_sources,source_postflight_complete=False)
        args.output.write_text(json.dumps(result,sort_keys=True)+'\n');print(json.dumps(result),flush=True)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    return 0

if __name__=='__main__':raise SystemExit(main())
