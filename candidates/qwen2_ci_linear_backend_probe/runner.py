"""Bounded synthetic branch observation; detailed native logs stay local."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from . import parser
ROOT=Path(__file__).resolve().parents[2]
MODES=('enabled','disabled')
LIMIT_SECONDS=50
MAX_LOG=131072
STOP=False

def request_stop(signum,frame):
    global STOP
    STOP=True

def checked(value):
    if type(value) is not dict or set(value)!={'schema','status','synthetic_only','numeric_acceptance_claimed','cases'}:
        raise ValueError('probe summary schema')
    if type(value['schema']) is not int or value['schema']!=1 or value['status'] not in ('OBSERVED','INCOMPLETE') or value['synthetic_only'] is not True or value['numeric_acceptance_claimed'] is not False:
        raise ValueError('probe summary values')
    if type(value['cases']) is not list or len(value['cases'])!=2:raise ValueError('probe cases')
    for mode,case in zip(MODES,value['cases']):
        if type(case) is not dict or set(case)!={'mode','execution','observation'} or case['mode']!=mode or case['execution'] not in ('COMPLETED','FAILED','TIMEOUT','LOG_LIMIT'):
            raise ValueError('probe case schema')
        parser.checked(case['observation'])
    if (value['status']=='OBSERVED')!=all(x['execution']=='COMPLETED' for x in value['cases']):raise ValueError('probe terminal mismatch')
    return value

def run_case(mode,directory):
    if mode not in MODES:raise ValueError('fixed mode')
    env=dict(os.environ)
    env.update(ONEDNN_VERBOSE='1',DNNL_VERBOSE='1')
    # This comparison changes only the explicit mkldnn enabled flag, not ISA caps.
    for key in ('ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR'):
        if key in env:raise ValueError('undeclared backend environment')
    out=directory/(mode+'.stdout');err=directory/(mode+'.stderr')
    child=None;execution='FAILED';start=time.monotonic()
    try:
        with out.open('xb') as stdout,err.open('xb') as stderr:
            child=subprocess.Popen([sys.executable,'-B','-m','candidates.qwen2_ci_linear_backend_probe.worker','--mode',mode],cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            while child.poll() is None:
                if STOP:
                    execution='FAILED';break
                if out.stat().st_size+err.stat().st_size>MAX_LOG:
                    execution='LOG_LIMIT';break
                if time.monotonic()-start>LIMIT_SECONDS:
                    execution='TIMEOUT';break
                time.sleep(.05)
            if child.poll() is not None:execution='COMPLETED' if child.returncode==0 else 'FAILED'
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)
    text=''
    if out.stat().st_size+err.stat().st_size<=MAX_LOG:
        text=out.read_text(errors='replace')+'\n'+err.read_text(errors='replace')
    else:execution='LOG_LIMIT'
    if execution=='COMPLETED':
        receipts=[]
        for line in text.splitlines():
            try:value=json.loads(line)
            except (ValueError,TypeError):continue
            if type(value) is dict and value.get('status')=='SYNTHETIC_LINEAR_COMPLETED':receipts.append(value)
        if receipts!=[dict(schema=1,status='SYNTHETIC_LINEAR_COMPLETED',mode=mode)] or type(receipts[0]['schema']) is not int:execution='FAILED'
    observation=parser.parse(text)
    return dict(mode=mode,execution=execution,observation=observation)

def main():
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,request_stop)
    directory=ROOT/'work/ci_linear_backend_probe'
    directory.mkdir(parents=True,exist_ok=False)
    cases=[]
    for mode in MODES:
        if STOP:cases.append(dict(mode=mode,execution='FAILED',observation=parser.parse('')))
        else:cases.append(run_case(mode,directory))
    result=checked(dict(schema=1,status='OBSERVED' if all(c['execution']=='COMPLETED' for c in cases) else 'INCOMPLETE',synthetic_only=True,numeric_acceptance_claimed=False,cases=cases))
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status']=='OBSERVED' else 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('{"schema":1,"status":"PROBE_FAILED"}')
        raise SystemExit(1)
