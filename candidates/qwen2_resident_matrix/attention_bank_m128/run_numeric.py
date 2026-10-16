"""Opt-in single-job M17/M32/M128 exact behavioral checks, no RTL/native math."""
import argparse,hashlib,json,resource,signal,struct,time,sys,platform
from pathlib import Path
from ..attention_bank_multirow.oracle import Oracle,ScalarTrace
from ..attention_bank_multirow.run_calibration import words_hash
from ..attention_matrix_batch.test_model import ExactScalar,fixture,ref_fma,exp_negative
from ..attention_scheduled_numeric.controller import Timing


def expected_counts(rows):
    if type(rows) is not int or rows not in (17,32,128):raise ValueError('whole-job shape')
    pairs=6*rows*(rows+1)
    qk_groups=12*sum((keys+15)//16 for keys in range(1,rows+1))
    return dict(pairs=pairs,matrix_steps=8*qk_groups+rows*(rows+1),matrix_groups=qk_groups+2*rows,
                legacy_requests=16*pairs,selected_fmas=256*pairs,transactions=7*pairs,bank_edges=21*pairs+2)


def prerequisite(path,sources):
    if path is None:raise ValueError('same-source M32 prerequisite required')
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>131072:raise ValueError('bounded M32 receipt')
    raw=path.read_bytes();receipt=json.loads(raw)
    if (type(receipt) is not dict or receipt.get('status')!='PASS_BANK_TILED_ATTENTION' or
        type(receipt.get('rows')) is not int or receipt['rows']!=32 or
        receipt.get('one_job_per_pass') is not True or receipt.get('native_arithmetic') is not False or
        receipt.get('rtl_execution') is not False or receipt.get('source_postflight_complete') is not True or
        receipt.get('source_sha256')!=sources):raise ValueError('M32 prerequisite identity')
    expected=expected_counts(32);counts=receipt.get('counts')
    if type(counts) is not dict:raise ValueError('M32 counts')
    checks={'matrix_steps':expected['matrix_steps'],'matrix_returns':expected['matrix_steps'],
            'matrix_groups':expected['matrix_groups'],'matrix_result_acks':expected['matrix_groups'],
            'selected_fmas':expected['selected_fmas'],'scratch_acks':expected['transactions'],
            'scratch_edges':expected['bank_edges']}
    if any(type(counts.get(k)) is not int or counts[k]!=v for k,v in checks.items()):raise ValueError('M32 whole-job counts')
    for key in ('output_sha256','scores_sha256'):
        value=receipt.get(key)
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('M32 full-output digest')
    return hashlib.sha256(raw).hexdigest()


def run(rows, *, m32_receipt=None):
    expected=expected_counts(rows)
    from .check_sources import check,snapshot
    from .controller import Controller
    check();before=snapshot()
    prior=prerequisite(m32_receipt,before) if rows==128 else None
    started=time.monotonic();cpu_started=time.process_time()
    data=fixture(rows);oracle=Oracle(rows,*data)
    phase=time.monotonic();cpu=time.process_time();output=oracle.run()
    reference_seconds=time.monotonic()-phase;reference_cpu=time.process_time()-cpu
    print(json.dumps(dict(phase='reference_complete',rows=rows,elapsed_seconds=time.monotonic()-started)),flush=True)
    scalar=ExactScalar(object());scalar.trace=ScalarTrace(capture_scores=False)
    candidate=Controller(scalar,ref_fma,lambda x:exp_negative(scalar,scalar.client,x),
                         timing=Timing(2,3,0,0),scratch_enabled=True)
    phase=time.monotonic();cpu=time.process_time();actual=candidate.run(rows,*data)
    candidate_seconds=time.monotonic()-phase;candidate_cpu=time.process_time()-cpu
    if actual.output!=output or actual.scores!=oracle.scores()[1]:raise ValueError('original whole-job numerical mismatch')
    counts=dict(actual.counts)
    if (len(output)!=1536*rows or len(actual.scores)!=expected['pairs'] or len(oracle.requests)!=expected['legacy_requests'] or
        counts['matrix_steps']!=expected['matrix_steps'] or counts['matrix_returns']!=expected['matrix_steps'] or
        counts['matrix_groups']!=expected['matrix_groups'] or counts['matrix_result_acks']!=expected['matrix_groups'] or
        counts['selected_fmas']!=expected['selected_fmas'] or
        counts['scratch_read_requests']+counts['scratch_write_requests']!=expected['transactions'] or
        counts['scratch_acks']!=expected['transactions'] or counts['scratch_edges']!=expected['bank_edges'] or
        counts['scalar_packets']!=counts['scalar_packet_acks']):raise ValueError('whole-job resource accounting')
    check()
    if snapshot()!=before:raise ValueError('numerical source drift')
    return dict(status='PASS_BANK_TILED_ATTENTION',rows=rows,one_job_per_pass=True,
        reference_seconds=reference_seconds,candidate_seconds=candidate_seconds,elapsed_seconds=time.monotonic()-started,
        reference_cpu_seconds=reference_cpu,candidate_cpu_seconds=candidate_cpu,cpu_seconds=time.process_time()-cpu_started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        runtime=dict(python_version=platform.python_version(),implementation=platform.python_implementation(),machine=platform.machine(),
                     interpreter_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()),
        output_sha256=words_hash(actual.output),scores_sha256=words_hash(actual.scores),
        reference_scalar_sha256=oracle.scalar.trace.hexdigest(),candidate_scalar_sha256=scalar.trace.hexdigest(),
        counts=counts,reference_matrix_requests=len(oracle.requests),modeled_ticks=actual.hypothetical_ticks,
        modeled_ticks_are_hardware=False,source_sha256=before,source_postflight_complete=True,
        m32_prerequisite_sha256=prior,native_arithmetic=False,rtl_execution=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rows',type=int,choices=(17,32,128),required=True)
    parser.add_argument('--seconds',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--m32-receipt',type=Path);args=parser.parse_args()
    caps={17:25,32:75,128:1200}
    if not 1<=args.seconds<=caps[args.rows]:raise SystemExit('bounded shape budget')
    start=time.monotonic();sources=None
    def timeout(*_):raise TimeoutError('numerical deadline')
    old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,args.seconds)
    try:
        from .check_sources import check,snapshot
        check();sources=snapshot()
        result=run(args.rows,m32_receipt=args.m32_receipt)
        if time.monotonic()-start>=args.seconds:raise TimeoutError('late numerical result')
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print(json.dumps(dict(status=result['status'],rows=args.rows,elapsed_seconds=time.monotonic()-start)),flush=True)
    except (ValueError,ArithmeticError,TimeoutError,AttributeError,TypeError,RuntimeError,OSError,KeyError,IndexError) as exc:
        result=dict(status='FAILED_BANK_TILED_ATTENTION',rows=args.rows,error_class=type(exc).__name__,elapsed_seconds=time.monotonic()-start,
                    numerical_acceptance=False,source_sha256=sources,source_postflight_complete=False)
        args.output.write_text(json.dumps(result,sort_keys=True)+'\n');print(json.dumps(result),flush=True)
        return 1
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    return 0

if __name__=='__main__':raise SystemExit(main())
