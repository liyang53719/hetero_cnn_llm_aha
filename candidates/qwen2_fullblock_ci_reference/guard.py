#!/usr/bin/env python3
"""Verified original supervisor/capture; fresh CI bootstrap requires independent go."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode = True
import recipe as R
import lifecycle as L
import failure_diagnostic as D
import comparison_diagnostic as CDF
import all_comparisons as ACD
import backend_policy as BP
G = R.legacy('guard.py')
R.need(G.R is R and G.L is L,'explicit CI recipe/lifecycle import binding')

def emit_failure(error,origin,all_expected=None):
    # Failure telemetry must never replace the original exception or cleanup.
    try:
        print(json.dumps(D.project(error,origin,R.ROOT),sort_keys=True,allow_nan=False),
              file=sys.stderr,flush=True)
    except BaseException:
        pass
    try:
        if origin == 'WORKER':BP.before_stage(R,'observations29-and-semantic-validation')
        comparison = CDF.project(error, R.ROOT) if origin == 'WORKER' else None
        if comparison is not None:
            print(json.dumps(comparison, sort_keys=True, allow_nan=False), file=sys.stderr, flush=True)
    except BaseException:
        pass

    try:
        if origin == 'WORKER':BP.before_stage(R,'observations29-and-semantic-validation')
        comparison = ACD.project(error, R.ROOT, all_expected) if origin == 'WORKER' and all_expected is not None else None
        if comparison is not None:
            print(json.dumps(comparison, sort_keys=True, allow_nan=False), file=sys.stderr, flush=True)
    except BaseException:
        pass


def comparison_expectations():
    # Existing tracked expectations are read before capture; never publish values.
    relative='candidates/qwen2_fullblock_reference_m128/FROZEN_CONTRACT.json'
    raw=R.safe_path(R.ROOT,relative).read_bytes()
    R.need(len(raw)==19978 and R.sha(raw)=='64835641b2c0c16d83beb75fbcd9d1c83ade8676fbd825f5e6ab646167af723f',
           'fixed diagnostic expectations identity')
    return R.parse(raw)['outputs']

_original_run = G.run
def observed_run(*args,**kwargs):
    try:return _original_run(*args,**kwargs)
    except BaseException as error:
        emit_failure(error,'SUPERVISOR')
        raise

def worker(fd,mode,out):
    all_expected=None
    try:
        R.need(mode == 'bootstrap','frozen CI capture not reviewed')
        R.need(sys.modules.get('lifecycle') is L,'capture lifecycle binding drift')
        C = R.legacy('capture.py')
        try:all_expected=comparison_expectations()
        except BaseException:pass
        C.capture(R.ROOT,R.load_pins(),Path(out),stage=mode,recipe=R,capability_fd=int(fd))
        return 0
    except BaseException as error:
        emit_failure(error,'WORKER',all_expected)
        print(json.dumps(dict(status='WORKER_FAILED_UNSEALED',error_type=type(error).__name__,
            error=str(error)),allow_nan=False),file=sys.stderr,flush=True)
        return 2
G.worker = worker
G.run = observed_run
if __name__ == '__main__': raise SystemExit(G.main())
