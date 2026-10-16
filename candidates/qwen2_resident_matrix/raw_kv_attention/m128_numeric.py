"""Explicit single M128 synthetic Attention; original arithmetic, no full block."""
import argparse
import json
import math
import os
from pathlib import Path
import time
from . import profile_numeric

WORKFLOW = '.github/workflows/raw-kv-attention-m128.yml'
INPUTS = ('m128_numeric.py', 'test_m128_numeric.py', 'run_m128_ci.py', 'test_m128_ci.py', 'run_calibration_ci.py', 'test_calibration_ci.py')
PHASES = ('preflight', 'reference', 'direct', 'loan', 'complete')


def source_snapshot():
    from .run_numeric_ci import PREFIX,digest,repository_path
    sources=profile_numeric.source_snapshot()
    for name in (*(PREFIX+n for n in INPUTS),WORKFLOW):
        sources[name]=digest(repository_path(name))
    return dict(sorted(sources.items()))


class Progress:
    """Atomic bounded counters only; never output operands, results or PASS."""
    def __init__(self,path):
        self.path=Path(path);self.start=time.monotonic();self.last=-math.inf;self.sequence=0;self.previous=None
        if self.path.exists() or self.path.is_symlink() or not self.path.parent.is_dir():
            raise ValueError('fresh progress required')

    def __call__(self,phase,loan,events,scalar_operations,matrix_packets,*,force=False):
        now=time.monotonic()
        if not force and now-self.last<5:return
        if type(phase) is not str or phase not in PHASES or loan is not None and type(loan) is not bool:
            raise ValueError('progress phase')
        expected_loan=None if phase in ('preflight','reference') else phase!='direct'
        if loan is not expected_loan:raise ValueError('progress identity')
        if self.previous and PHASES.index(phase)<PHASES.index(self.previous['phase']):
            raise ValueError('progress regression')
        limits=(32*1585152+10000,55480320,1585152)
        if any(type(x) is not int or not 0<=x<=limit for x,limit in zip((events,scalar_operations,matrix_packets),limits)):
            raise ValueError('progress count')
        if self.previous and self.previous['phase']==phase:
            if any(value<self.previous[name] for name,value in zip(('events','scalar_operations','matrix_packets'),(events,scalar_operations,matrix_packets))):
                raise ValueError('progress counter regression')
        elapsed=now-self.start
        if not math.isfinite(elapsed) or not 0<=elapsed<=2400:raise ValueError('progress time')
        if phase in ('preflight','reference') and any((events,scalar_operations,matrix_packets)):
            raise ValueError('progress preflight counters')
        if phase=='complete' and not (events>0 and scalar_operations==55480320 and matrix_packets==1585152):
            raise ValueError('progress incomplete counts')
        self.sequence+=1
        if self.sequence>1024:raise ValueError('progress count limit')
        value=dict(schema=1,status='PROGRESS',phase=phase,tokens=128,loan=loan,
                   events=events,scalar_operations=scalar_operations,matrix_packets=matrix_packets,
                   elapsed_seconds=elapsed,sequence=self.sequence)
        raw=json.dumps(value,sort_keys=True,allow_nan=False).encode()
        if len(raw)>1024:raise ValueError('progress size')
        temporary=self.path.with_suffix('.pending')
        # The wrapper supplies a fresh evidence directory, then revalidates this
        # fixed schema after child retirement before final evidence publication.
        with temporary.open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,self.path)
        directory=os.open(self.path.parent,os.O_RDONLY | os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
        self.last=now;self.previous=value


def run_m128(progress):
    progress('preflight',None,0,0,0,force=True)
    return profile_numeric._run_profiles((128,),seconds=2400.0,
                                        snapshot=source_snapshot,progress=progress)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-m128',action='store_true',required=True)
    parser.add_argument('--progress',type=Path,required=True)
    args=parser.parse_args(argv)
    try:code,result=run_m128(Progress(args.progress))
    except Exception as error:
        code,result=1,dict(status='FAIL',reason=type(error).__name__,m128_completed=False)
    print(json.dumps(result,sort_keys=True,allow_nan=False));return code


if __name__=='__main__':raise SystemExit(main())
