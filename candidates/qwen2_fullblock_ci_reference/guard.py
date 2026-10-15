#!/usr/bin/env python3
"""Verified original supervisor/capture; fresh CI bootstrap requires independent go."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode = True
import recipe as R
import lifecycle as L
G = R.legacy('guard.py')
R.need(G.R is R and G.L is L,'explicit CI recipe/lifecycle import binding')

def worker(fd,mode,out):
    try:
        R.need(mode == 'bootstrap','frozen CI capture not reviewed')
        R.need(sys.modules.get('lifecycle') is L,'capture lifecycle binding drift')
        C = R.legacy('capture.py')
        C.capture(R.ROOT,R.load_pins(),Path(out),stage=mode,recipe=R,capability_fd=int(fd))
        return 0
    except BaseException as error:
        print(json.dumps(dict(status='WORKER_FAILED_UNSEALED',error_type=type(error).__name__,
            error=str(error)),allow_nan=False),file=sys.stderr,flush=True)
        return 2
G.worker = worker
if __name__ == '__main__': raise SystemExit(G.main())
