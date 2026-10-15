"""Single reviewed reference-only diagnostic; export fixed enums and source lines."""
import argparse
import contextlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch
from . import bootstrap as B
ROOT=Path(__file__).resolve().parents[2]
AUTH='candidates/qwen2_ci_reference_diagnostic_authorization'
PHASES={'ADMIT','PRECHECK','BINDINGS','ISSUER','GUARD','AGGREGATE','COMPLETE'}
FILES={
 'BOOTSTRAP':'candidates/qwen2_fullblock_ci_execution/bootstrap.py',
 'DIAGNOSTIC':'candidates/qwen2_fullblock_ci_execution/reference_diagnostic.py',
 'RECIPE':'candidates/qwen2_fullblock_ci_reference/recipe.py',
 'ISSUER':'candidates/qwen2_fullblock_ci_reference/issuer.py',
 'GUARD':'candidates/qwen2_fullblock_ci_reference/guard.py',
 'LIFECYCLE':'candidates/qwen2_fullblock_ci_reference/lifecycle.py',
 'ORIGINAL_RECIPE':'candidates/qwen2_fullblock_reference_m128/recipe.py',
 'ORIGINAL_GUARD':'candidates/qwen2_fullblock_reference_m128/guard.py',
 'CAPTURE':'candidates/qwen2_fullblock_reference_m128/capture.py',
 'FRESH_TAIL':'candidates/qwen2_fullblock_ci_prepare/fresh_tail.py'}
LABELS={'fresh_bindings':'BINDINGS','policy_expansion':'ISSUER','reference_guard':'GUARD',
        'certificate_validation':'ADMIT'}


def checked(v):
    B.inputs.need(type(v) is dict and set(v)=={'schema','status','phase','module','line'},'diagnostic schema')
    B.inputs.need(type(v['schema']) is int and v['schema']==1 and v['status'] in ('NOT_EXECUTED','SUCCESS','FAILED'), 'diagnostic state')
    B.inputs.need(v['phase'] in PHASES and v['module'] in set(FILES)|{'NONE','OTHER'},'diagnostic enums')
    B.inputs.need(type(v['line']) is int and 0<=v['line']<=1000000,'diagnostic source line')
    return v


def location(error):
    found=('OTHER',0);approved={str(ROOT/p):k for k,p in FILES.items()};tb=error.__traceback__
    while tb:
        name=approved.get(tb.tb_frame.f_code.co_filename)
        if name and tb.tb_frame.f_code.co_name not in ('need','require'):
            found=(name,tb.tb_lineno)
        tb=tb.tb_next
    return found


def log_location(label):
    # Never return exception strings, source lines or arbitrary filenames.
    B.inputs.need(label in LABELS,'fixed child label')
    path=B.inputs.safe_path(ROOT,B.LOGS+'/'+label+'.log')
    if not path.is_file() or path.stat().st_size>16*(1<<20):return ('OTHER',0)
    text=path.read_text(errors='replace');found=('OTHER',0)
    approved={str(ROOT/p):k for k,p in FILES.items()}
    for path,line,function in re.findall(r'^  File "([^"\n]+)", line ([0-9]{1,7}), in ([^\n]+)$',text,re.M):
        if path in approved and function not in ('need','require') and 0<int(line)<=1000000:found=(approved[path],int(line))
    return found


def run(action=None):
    result=dict(schema=1,status='NOT_EXECUTED',phase='PRECHECK',module='NONE',line=0)
    if action is None:return checked(result)
    B.inputs.need(action in ('admit','capture'),'fixed action')
    B.AUTH=AUTH;B.AUTH_CERT=AUTH+'/SOURCE_CERTIFICATE.json';B.AUTH_PINS=AUTH+'/EXTERNAL_PINS.json'
    B.inputs.need(__import__('os').environ.get('GITHUB_RUN_ATTEMPT')=='1','single attempt')
    original=B.call;child_failed=False
    def call(name,args,label):
        nonlocal child_failed
        B.inputs.need(label in LABELS,'fixed stage')
        result['phase']=LABELS[label]
        try:
            value=original(name,args,label)
            if label=='reference_guard':result['phase']='AGGREGATE'
            return value
        except Exception:
            child_failed=True
            result['module'],result['line']=log_location(label)
            raise
    local=B.inputs.safe_path(ROOT,'work/ci_reference_diagnostic/'+action+'.log')
    local.parent.mkdir(parents=True,exist_ok=True)
    with local.open('x') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        try:
            with patch.object(B,'call',call):
                result['phase']='ADMIT' if action=='admit' else 'PRECHECK'
                (B.admit if action=='admit' else B.capture)()
            result.update(status='SUCCESS',phase='COMPLETE')
        except Exception as error:
            result['status']='FAILED'
            if not child_failed:result['module'],result['line']=location(error)
    return checked(result)


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self,message):raise ValueError('invalid diagnostic arguments')
    parser=Parser(description=__doc__)
    parser.add_argument('action',choices=('admit','capture'),nargs='?')
    try:
        args=parser.parse_args(argv)
        result=run(args.action)
    except Exception as error:
        module,line=location(error)
        result=checked(dict(schema=1,status='FAILED',phase='PRECHECK',module=module,line=line))
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return int(result['status']=='FAILED')
if __name__=='__main__':raise SystemExit(main())
