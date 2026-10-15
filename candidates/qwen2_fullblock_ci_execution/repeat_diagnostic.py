"""Two separately authorized fresh failures; private native-byte reproducibility."""
import contextlib
import json
import hashlib
import os
from pathlib import Path
import subprocess
import signal
import sys
from . import bootstrap as B, runtime_profile
from ..qwen2_fullblock_ci_reference import repeat_observation as O
ROOT=B.ROOT
RUNS=('ci01','ci02')
AUTH='candidates/qwen2_ci_reference_repeat_authorization'
TOTAL_CAP=69*1024*1024

@contextlib.contextmanager
def configured(run):
    B.inputs.need(run in RUNS and runtime_profile.mkldnn_enabled() is False,'explicit disabled repeat profile')
    keys=('QWEN2_REFERENCE_REPEAT_RUN','QWEN2_BOOTSTRAP_CERTIFICATE_SHA256','QWEN2_BOOTSTRAP_SOURCE_CLOSURE_SHA256')
    old={k:os.environ.get(k) for k in keys}
    attrs={k:getattr(B,k) for k in ('AUTH','AUTH_CERT','AUTH_PINS','CERTIFICATE','LOGS')}
    try:
        os.environ['QWEN2_REFERENCE_REPEAT_RUN']=run
        for k in keys[1:]:os.environ.pop(k,None)
        B.AUTH=AUTH+'/'+run;B.AUTH_CERT=B.AUTH+'/SOURCE_CERTIFICATE.json';B.AUTH_PINS=B.AUTH+'/EXTERNAL_PINS.json'
        B.CERTIFICATE=B.WORK+'/EXTERNAL_'+run+'.json';B.LOGS='work/ci_repeat_logs/'+run
        yield
    finally:
        for k,v in old.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
        for k,v in attrs.items():setattr(B,k,v)

def arguments(flag,run):
    cert,source=B.pins()
    return [flag,'--certificate',B.CERTIFICATE,'--certificate-sha256',cert,'--source-closure-sha256',source,'--run-id',run]

def admit():
    for run in RUNS:
        with configured(run):
            cert,_=B.pins();_,raw=B.external_authorization()
            path=B.inputs.safe_path(ROOT,B.CERTIFICATE);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(raw)
            B.call('issuer.py',arguments('--validate-only',run),'certificate_validation')
    return {'schema':1,'status':'PAIR_SOURCE_ADMITTED','numeric_acceptance_claimed':False}

def private_out(run):return B.inputs.safe_path(ROOT,B.WORK+'/'+run+'/bootstrap')

def disk_gate():
    total=0
    for run in RUNS:
        directory=B.inputs.safe_path(ROOT,B.WORK+'/'+run)
        if directory.exists():
            for path in directory.rglob('*'):
                B.inputs.need(not path.is_symlink(),'pair output alias')
                if path.is_file():total+=path.stat().st_size
    B.inputs.need(total<=TOTAL_CAP,'pair aggregate disk bound')

def file_identity(path):
    B.inputs.need(path.is_file() and not path.is_symlink() and path.stat().st_nlink==1,'regular private receipt/payload')
    total=0;digest=hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            block=stream.read(1024*1024)
            if not block:break
            total+=len(block);B.inputs.need(total<=34*1024*1024,'private file bound');digest.update(block)
    return dict(bytes=total,sha256=digest.hexdigest())

def verify_partial_files(out,failure):
    values=failure.get('partial_files')
    B.inputs.need(type(values) is dict,'guard partial inventory required')
    for name in (*O.FILES,O.META):
        relative=O.DIRECTORY+'/'+name
        spec=values.get(relative)
        B.inputs.need(type(spec) is dict and set(spec)=={'bytes','sha256'} and type(spec['bytes']) is int and type(spec['sha256']) is str,'exact retained guard identity')
        B.inputs.need(file_identity(out/relative)==spec,'private observation differs from retained guard inventory')

def validated_failure(run):
    out=private_out(run)
    B.inputs.need(not (out/'SEAL.json').exists() and not (out/'WATCHDOG.json').exists(),'pair requires unsealed bounded failure')
    p=out/'FAILURE.json';B.inputs.need(p.stat().st_size<=262144,'bounded failure receipt')
    f=json.loads(p.read_bytes(),object_pairs_hook=O._unique);r=f.get('resources')
    B.inputs.need(f.get('status')=='FAILED_UNSEALED' and f.get('run_id')==run and f.get('stage')=='observations29-and-semantic-validation' and f.get('before_captured') is True and f.get('automatic_retry') is False and f.get('completion_seal_written') is False and f.get('numerical_acceptance_claimed') is False,'exact failure stage')
    B.inputs.need(type(r) is dict and type(r.get('returncode')) is int and r['returncode']==2 and r.get('limit_reason') is None and r.get('overall_wall_limit_seconds')==120 and r.get('external_watchdog_deadline_seconds')==122 and type(r.get('overall_elapsed_seconds')) in (float,int) and 0<=r['overall_elapsed_seconds']<=122,'bounded worker failure required')
    records=[]
    p=out/'stderr.log';B.inputs.need(p.stat().st_size<=65536,'bounded worker log')
    for line in p.read_text().splitlines():
        try:value=json.loads(line)
        except ValueError:continue
        if type(value) is dict and value.get('status')=='CI_REFERENCE_FAILURE':records.append(value)
    B.inputs.need(records==[dict(schema=1,status='CI_REFERENCE_FAILURE',origin='WORKER',error='VALUE_ERROR',module='ORIGINAL_CAPTURE',line=265)],'exact original comparison failure required')
    directory=out/'REPEAT_OBSERVATION_LOCAL'
    O.compare(directory,directory) # Complete private observation and readback gate.
    verify_partial_files(out,f)
    disk_gate()
    return directory

def capture():
    B.inputs.need(os.environ.get('GITHUB_SHA')==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source commit identity')
    dirs=[];failures=[]
    for index,run in enumerate(RUNS):
        with configured(run):
            B.pins()
            if index==0:B.call('recipe.py',['--prepare-bindings'],'fresh_bindings')
            B.call('issuer.py',arguments('--execute',run),'policy_expansion')
            script=B.inputs.safe_path(ROOT,B.PACKAGE+'/guard.py');log=B.inputs.safe_path(ROOT,B.LOGS+'/reference_guard.log')
            with log.open('xb') as stream:
                child=subprocess.Popen([str(Path(sys.executable).resolve()),'-B',str(script),'--mode','bootstrap','--run-id',run,'--go',B.WORK+'/'+run+'/GO.json'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                try:code=child.wait(timeout=130)
                except BaseException:
                    if child.poll() is None:
                        os.killpg(child.pid,signal.SIGTERM)
                        try:child.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)
                    raise
            B.inputs.need(code==2,'original guard failure must be preserved')
            dirs.append(validated_failure(run))
            failures.append(file_identity(private_out(run)/'FAILURE.json'))
    disk_gate()
    for run,identity in zip(RUNS,failures):
        B.inputs.need(file_identity(private_out(run)/'FAILURE.json')==identity,'retained failure receipt drift')
        validated_failure(run)
    result=O.compare(*dirs)
    for run,identity in zip(RUNS,failures):
        B.inputs.need(file_identity(private_out(run)/'FAILURE.json')==identity,'retained failure receipt drift')
        validated_failure(run)
    return result

def main():
    try:
        B.inputs.need(len(sys.argv)==2 and sys.argv[1] in ('admit','capture') and os.getenv('GITHUB_RUN_ATTEMPT')=='1','explicit single pair action')
        local=ROOT/'work/ci_repeat_logs';local.mkdir(parents=True,exist_ok=True)
        with (local/(sys.argv[1]+'.log')).open('x') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            result=admit() if sys.argv[1]=='admit' else capture()
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        print('{"schema":1,"status":"PAIR_INCOMPLETE","numeric_acceptance_claimed":false}');return 1
if __name__=='__main__':raise SystemExit(main())
