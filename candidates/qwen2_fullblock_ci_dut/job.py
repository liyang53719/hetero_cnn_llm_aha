"""Single CI job orchestration. External review files are mandatory, never generated."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from candidates.qwen2_fullblock_ci_execution import bootstrap, inputs
from . import closure
ROOT=Path(__file__).resolve().parents[2]
AUTH='candidates/qwen2_ci_dut_authorization'
LOGS='work/ci_dut_logs'
OUT='work/qwen2_fullblock_ci_dut_numeric/ci01'
PACKAGE='candidates/qwen2_fullblock_ci_dut'


def need(ok,message):
    if not ok:raise ValueError(message)


def authorize():
    need(ROOT==inputs.CI_ROOT,'fixed CI root')
    path=inputs.safe_path(ROOT,AUTH+'/DUT_REVIEW.json')
    need(0<path.stat().st_size<=16384,'bounded independent source review')
    value=json.loads(path.read_bytes())
    policy=dict(schema=1,status='APPROVED_SINGLE_CI_M128_MODEL',job_total_minutes=75,
        reference_inner_seconds=120,reference_outer_seconds=122,dut_inner_seconds=3300,
        dut_outer_seconds=3330,maximum_invocations=1,no_retry=True)
    need(type(value) is dict and set(value)==set(policy)|{'source_closure_sha256','reference_certificate_sha256',
        'reference_source_closure_sha256','reviewer'},'exact external review schema')
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in policy.items()),'fixed externally reviewed scope/budget')
    need(type(value['reviewer']) is str and value['reviewer'].startswith('/root/review_'),'independent reviewer identity')
    for name in ('source_closure_sha256','reference_certificate_sha256','reference_source_closure_sha256'):
        need(type(value[name]) is str and re.fullmatch('[0-9a-f]{64}',value[name]) and value[name]!='0'*64,'external SHA256')
    need(closure.digest(ROOT)==value['source_closure_sha256'],'reviewed current DUT sources')
    need(value['reference_source_closure_sha256']==closure.BOOTSTRAP_SHA,'unchanged official reference closure')
    need(os.environ.get('GITHUB_RUN_ATTEMPT')=='1','single CI attempt only')
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    need(actual==os.environ.get('GITHUB_SHA'),'checked out CI source commit')
    expected=value['source_closure_sha256']
    need(os.environ.get('QWEN2_DUT_SOURCE_CLOSURE_SHA256') in (None,'',expected),'DUT closure environment conflict')
    os.environ['QWEN2_DUT_SOURCE_CLOSURE_SHA256']=expected
    certificate=value['reference_certificate_sha256']
    need(os.environ.get('QWEN2_BOOTSTRAP_CERTIFICATE_SHA256') in (None,'',certificate),'reference certificate environment conflict')
    os.environ['QWEN2_BOOTSTRAP_CERTIFICATE_SHA256']=certificate
    return value


def reference_authority(value):
    # Explicit sibling authorization location only; the frozen reference code is unchanged.
    bootstrap.AUTH=AUTH;bootstrap.AUTH_CERT=AUTH+'/SOURCE_CERTIFICATE.json'
    bootstrap.AUTH_PINS=AUTH+'/EXTERNAL_PINS.json'
    pins,_=bootstrap.external_authorization()
    need(pins==dict(schema=1,certificate_sha256=value['reference_certificate_sha256'],
        source_closure_sha256=value['reference_source_closure_sha256']),'same independently reviewed reference authority')


def admit():
    value=authorize();reference_authority(value)
    bootstrap.admit()
    return 'SINGLE_JOB_SOURCE_ADMITTED'


def capture():
    value=authorize();reference_authority(value)
    bootstrap.capture()
    return 'FRESH_REFERENCE_VERIFIED_LOCALLY'


def bind():
    authorize()
    from . import recipe
    seal=inputs.safe_path(ROOT,recipe.REFERENCE+'/SEAL.json')
    need(0<seal.stat().st_size<=262144,'bounded current reference seal')
    result=recipe.bind_bootstrap(seal_sha256=hashlib.sha256(seal.read_bytes()).hexdigest(),execute=True)
    need(result['status']==recipe.STATUS and result['reference_outputs_checked']==29,'new local oracle binding')
    return result


def actual():
    value=authorize()
    from . import recipe
    # Preserve the successful binder's returned SHA in this process. Never
    # recompute a replacement launch pin from a possibly changed binding file.
    bound=bind()
    os.environ[recipe.BINDING_ENV]=bound['binding_sha256']
    probe=inputs.safe_path(ROOT,LOGS+'/initialized-control.log')
    probe.parent.mkdir(parents=True,exist_ok=True)
    with probe.open('xb') as stream:
        result=subprocess.run([sys.executable,'-B',str(ROOT/PACKAGE/'audit_probe.py'),'--initialized-only'],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=90,check=False)
    need(result.returncode==0,'initialized control admission failed')
    output=inputs.safe_path(ROOT,OUT)
    need(not output.exists(),'single fresh actual output')
    output.parent.mkdir(parents=True,exist_ok=True)
    log=inputs.safe_path(ROOT,LOGS+'/actual-launch.log')
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('xb') as stream:
        child=subprocess.run([sys.executable,'-B',str(ROOT/PACKAGE/'launch.py'),'--actual',
            '--data','work/qwen2_live_qkv_inputs_m128/ci01',
            '--reference',recipe.REFERENCE,'--out',str(output),
            '--reviewed-source-manifest',value['source_closure_sha256']],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=False)
    need(child.returncode==0,'bounded actual process failed')
    return 'ACTUAL_PROCESS_COMPLETED_REQUIRES_AGGREGATE'


def aggregate():
    value=authorize()
    from . import aggregate as summary
    result=summary.collect(execute=True,source_digest=value['source_closure_sha256'])
    path=inputs.safe_path(ROOT,'work/qwen2_fullblock_ci_dut_summary.json')
    with path.open('x') as stream:
        json.dump(result,stream,sort_keys=True,allow_nan=False);stream.write('\n')
    return 'ALLOWLISTED_AGGREGATE_READY'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('admit','capture','actual','aggregate'))
    args=parser.parse_args(argv)
    try:print({'admit':admit,'capture':capture,'actual':actual,'aggregate':aggregate}[args.action]())
    except Exception:
        print('CI_DUT_STAGE_FAILED_LOCAL_DETAILS_ONLY');return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
