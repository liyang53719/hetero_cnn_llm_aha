"""Prepare a fresh CI workspace. Reference authority is supplied separately.

This stage installs nothing and never creates review or GO documents. It uses
already-installed pinned runtime, fixed checkpoint acquisition and fresh strict
native compilation. All detailed records stay in the isolated CI workspace.
"""
import argparse
import json
from pathlib import Path
import sys
import subprocess
from . import inputs, native, platform
ROOT=Path(__file__).resolve().parents[2]
RESULT='work/qwen2_fullblock_ci_execution/PREPARED.json'

def current_platform():
    # Keep the parent stdlib-only: inputs preflight deliberately rejects imported Torch.
    executable=platform.location(ROOT)
    pins=platform.sources(ROOT)
    run=subprocess.run([str(executable),'-B','-m','candidates.qwen2_fullblock_ci_execution.platform','--initialize'],
        cwd=ROOT,capture_output=True,text=True,timeout=120,check=True)
    inputs.need(len(run.stdout)<=16384 and len(run.stderr)<=65536,'bounded runtime initialization output')
    value=json.loads(run.stdout)
    inputs.need(platform.same(value,platform._expected(pins)),'new process platform summary drift')
    return value

def prepare(*,execute=False,download=False):
    if not execute and not download:return dict(status='NOT_EXECUTED')
    inputs.need(execute is True and download is True,'both explicit preparation opt-ins required')
    inputs.preflight(ROOT)
    path=inputs.safe_path(ROOT,RESULT)
    inputs.need(not path.exists(),'preparation record must be fresh')
    # An actual platform failure must precede raw network or native compilation.
    runtime=current_platform()
    materialized=inputs.prepare(execute=True,download=True)
    compiled=native.build(execute=True)
    result=dict(schema=1,status='PREPARED_PENDING_REFERENCE_REVIEW',runtime=runtime,
        inputs=materialized,native=compiled,reference_executed=False,dut_executed=False,
        rtl_executed=False,independently_approved=False)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        json.dump(result,stream,sort_keys=True,allow_nan=False);stream.write('\n')
    return dict(status=result['status'],reference_executed=False,dut_executed=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--download',action='store_true')
    a=p.parse_args();print(json.dumps(prepare(execute=a.execute,download=a.download),sort_keys=True))
if __name__=='__main__':main()
