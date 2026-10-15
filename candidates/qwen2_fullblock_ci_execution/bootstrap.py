"""Explicit two-stage CI bootstrap launcher; no model or automatic approval."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from . import inputs,closure,aggregate
ROOT=Path(__file__).resolve().parents[2]
PACKAGE='candidates/qwen2_fullblock_ci_reference'
WORK='work/qwen2_fullblock_ci_reference'
CERTIFICATE=WORK+'/EXTERNAL_SOURCE_CERTIFICATE.json'
LOGS='work/ci_bootstrap_logs'
AUTH='candidates/qwen2_ci_bootstrap_authorization'
AUTH_CERT=AUTH+'/SOURCE_CERTIFICATE.json'
AUTH_PINS=AUTH+'/EXTERNAL_PINS.json'

def external_authorization():
    cert_path=inputs.safe_path(ROOT,AUTH_CERT);pin_path=inputs.safe_path(ROOT,AUTH_PINS)
    inputs.need(0<cert_path.stat().st_size<=262144 and 0<pin_path.stat().st_size<=4096,'bounded external authorization')
    values=json.loads(pin_path.read_bytes())
    inputs.need(type(values) is dict and set(values)=={'schema','certificate_sha256','source_closure_sha256'} and
        type(values['schema']) is int and values['schema']==1,'exact external pin schema')
    from .summary import digest
    digest(values['certificate_sha256']);digest(values['source_closure_sha256'])
    raw=cert_path.read_bytes()
    inputs.need(hashlib.sha256(raw).hexdigest()==values['certificate_sha256'],'external certificate bytes drift')
    return values,raw

def pins():
    inputs.need(ROOT==inputs.CI_ROOT and ROOT.resolve()==ROOT,'fixed CI bootstrap root')
    values,_=external_authorization()
    expected=values['source_closure_sha256'];certificate=values['certificate_sha256']
    inputs.need(closure.digest(ROOT)==expected,'external source closure drift')
    for key,value in (('QWEN2_BOOTSTRAP_CERTIFICATE_SHA256',certificate),('QWEN2_BOOTSTRAP_SOURCE_CLOSURE_SHA256',expected)):
        inputs.need(os.environ.get(key) in (None,'',value),'external pin environment conflict')
        os.environ[key]=value
    return certificate,expected

def call(name,args,label):
    script=inputs.safe_path(ROOT,PACKAGE+'/'+name)
    log=inputs.safe_path(ROOT,LOGS+'/'+label+'.log')
    log.parent.mkdir(parents=True,exist_ok=True)
    # Original guard has its own process-group supervision and 120/122 second limit.
    # Detailed errors remain local; never stream them into GitHub logs.
    with log.open('xb') as stream:
        result=subprocess.run([str(Path(sys.executable).resolve()),'-B',str(script),*args],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=False)
    inputs.need(result.returncode==0,'bootstrap stage failed; inspect local retained log')

def issuer_args(flag):
    certificate,source=pins()
    return [flag,'--certificate',CERTIFICATE,'--certificate-sha256',certificate,
        '--source-closure-sha256',source,'--run-id','ci01']

def admit():
    certificate,_=pins()
    _,raw=external_authorization()
    inputs.need(0<len(raw)<=262144 and hashlib.sha256(raw).hexdigest()==certificate,'external certificate bytes required')
    path=inputs.safe_path(ROOT,CERTIFICATE)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)
    call('issuer.py',issuer_args('--validate-only'),'certificate_validation')
    return 'BOOTSTRAP_SOURCE_POLICY_ADMITTED'

def capture():
    certificate,source=pins()
    path=inputs.safe_path(ROOT,CERTIFICATE)
    inputs.need(hashlib.sha256(path.read_bytes()).hexdigest()==certificate,'external certificate changed')
    git_sha=os.environ.get('GITHUB_SHA')
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    inputs.need(git_sha==actual,'CI source commit identity drift')
    call('recipe.py',['--prepare-bindings'],'fresh_bindings')
    call('issuer.py',issuer_args('--execute'),'policy_expansion')
    call('guard.py',['--mode','bootstrap','--run-id','ci01','--go',WORK+'/ci01/GO.json'],'reference_guard')
    aggregate.collect(git_sha=git_sha,source_digest=source)
    return 'BOOTSTRAP_AGGREGATE_READY_PENDING_REVIEW'

def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group()
    g.add_argument('--admit',action='store_true');g.add_argument('--capture',action='store_true');a=p.parse_args()
    try:print(admit() if a.admit else capture() if a.capture else 'NOT_EXECUTED')
    except Exception:
        # Do not leak rejected per-tensor observations/metadata through CI logs.
        print('BOOTSTRAP_STAGE_FAILED_LOCAL_DETAILS_ONLY');return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
