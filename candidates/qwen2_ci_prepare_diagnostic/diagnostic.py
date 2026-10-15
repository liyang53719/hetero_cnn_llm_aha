"""Opt-in prepare-only diagnostics; only fixed-schema enum JSON leaves local logs."""
import argparse
import contextlib
import functools
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_execution import prepare as original

ROOT = Path(__file__).resolve().parents[2]
LOCAL = 'work/qwen2_ci_prepare_diagnostic/ci01'
PHASES = {'PRECHECK', 'PLATFORM', 'QKV_ACQUIRE', 'QKV_MATERIALIZE', 'QKV_VERIFY',
          'TAIL_ACQUIRE', 'TAIL_MATERIALIZE', 'INPUT_VERIFY', 'NATIVE', 'COMPLETE'}
ERROR_TYPES = {ValueError:'VALUE_ERROR', TypeError:'TYPE_ERROR', KeyError:'KEY_ERROR',
    OSError:'OS_ERROR', FileNotFoundError:'FILE_NOT_FOUND', PermissionError:'PERMISSION_ERROR',
    ImportError:'IMPORT_ERROR', ModuleNotFoundError:'MODULE_NOT_FOUND',
    RuntimeError:'RUNTIME_ERROR', AssertionError:'ASSERTION_ERROR',
    subprocess.CalledProcessError:'CHILD_FAILED', subprocess.TimeoutExpired:'CHILD_TIMEOUT'}
MODULE_FILES = {
 'PREPARE':'candidates/qwen2_fullblock_ci_execution/prepare.py',
 'PLATFORM':'candidates/qwen2_fullblock_ci_execution/platform.py',
 'INPUTS':'candidates/qwen2_fullblock_ci_execution/inputs.py',
 'NATIVE':'candidates/qwen2_fullblock_ci_execution/native.py',
 'INITIALIZE_PLATFORM':'candidates/qwen2_fullblock_ci_prepare/initialize_platform.py',
 'PLATFORM_INVENTORY':'candidates/qwen2_fullblock_ci_prepare/platform_inventory.py',
 'QKV_RECIPE':'candidates/qwen2_live_qkv_inputs_m128/recipe.py',
 'TAIL_ACQUISITION':'candidates/qwen2_live_tail_acquisition_m128/acquire.py',
 'FRESH_TAIL':'candidates/qwen2_fullblock_ci_prepare/fresh_tail.py',
 'TAIL_RECIPE':'candidates/qwen2_live_tail_inputs_m128/recipe.py',
 'DIAGNOSTIC':'candidates/qwen2_ci_prepare_diagnostic/diagnostic.py'}
EXCEPTIONS = set(ERROR_TYPES.values()) | {'NONE', 'OTHER'}
MODULES = set(MODULE_FILES) | {'NONE', 'OTHER'}
KEYS = {'schema','status','phase','exception','module','line',
        'platform_exception','platform_module','platform_line'}


def checked(value):
    if type(value) is not dict or set(value) != KEYS:
        raise ValueError('diagnostic schema')
    if type(value['schema']) is not int or value['schema'] != 1:
        raise ValueError('diagnostic schema version')
    if value['status'] not in ('NOT_EXECUTED','PREPARED','FAILED') or value['phase'] not in PHASES:
        raise ValueError('diagnostic status/phase')
    for prefix in ('','platform_'):
        if value[prefix+'exception'] not in EXCEPTIONS or value[prefix+'module'] not in MODULES:
            raise ValueError('diagnostic enum')
        number = value[prefix+'line']
        if type(number) is not int or not 0 <= number <= 1000000:
            raise ValueError('diagnostic line')
    return value


def record(status='NOT_EXECUTED', phase='PRECHECK'):
    return checked(dict(schema=1,status=status,phase=phase,exception='NONE',module='NONE',line=0,
                        platform_exception='NONE',platform_module='NONE',platform_line=0))


def sanitize(error):
    # Never use str/repr(error), exception attributes, module names or source text.
    result = dict(exception=ERROR_TYPES.get(type(error),'OTHER'),module='OTHER',line=0)
    approved = {str(ROOT/path): name for name,path in MODULE_FILES.items()}
    tb = error.__traceback__
    while tb is not None:
        module = approved.get(tb.tb_frame.f_code.co_filename)
        if (module is not None and tb.tb_frame.f_code.co_name not in ('need','require')
                and type(tb.tb_lineno) is int and 0 < tb.tb_lineno <= 1000000):
            result.update(module=module,line=tb.tb_lineno)
        tb = tb.tb_next
    return result


def wrap(function, phase, state):
    @functools.wraps(function)
    def call(*args, **kwargs):
        depth=state.get('depth',0)
        if depth==0:state['phase']=phase
        state['depth']=depth+1
        try:return function(*args, **kwargs)
        finally:state['depth']=depth
    return call


@contextlib.contextmanager
def instrument(state):
    # Patch only function entry points, never pins, validators, arguments or returns.
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(original,'current_platform',wrap(original.current_platform,'PLATFORM',state)))
        stack.enter_context(patch.object(original.native,'build',wrap(original.native.build,'NATIVE',state)))
        stack.enter_context(patch.object(original.inputs,'preflight',wrap(original.inputs.preflight,'PRECHECK',state)))
        identity=original.inputs.identity
        def identify(root, role):
            if role!='tail_raw':state['phase']='INPUT_VERIFY'
            return identity(root,role)
        stack.enter_context(patch.object(original.inputs,'identity',identify))
        contracts = original.inputs.contracts
        def load_contracts(*args, **kwargs):
            result = contracts(*args, **kwargs)
            q,pins,tail,a,n,tp = result
            for key,phase in [('acquire','QKV_ACQUIRE'),('materialize','QKV_MATERIALIZE'),
                              ('read_subset','QKV_VERIFY'),('read_inputs','QKV_VERIFY')]:
                stack.enter_context(patch.dict(q,{key:wrap(q[key],phase,state)}))
            stack.enter_context(patch.object(a,'acquire',wrap(a.acquire,'TAIL_ACQUIRE',state)))
            for key,phase in [('materialize','TAIL_MATERIALIZE'),('input_metadata','INPUT_VERIFY')]:
                stack.enter_context(patch.dict(tail,{key:wrap(tail[key],phase,state)}))
            return result
        stack.enter_context(patch.object(original.inputs,'contracts',load_contracts))
        yield


@contextlib.contextmanager
def local_output(path):
    # Capture Python and native/subprocess inherited stdout/stderr, exclusively.
    with path.open('x') as log:
        sys.stdout.flush();sys.stderr.flush()
        saved = [os.dup(1),os.dup(2)]
        try:
            os.dup2(log.fileno(),1);os.dup2(log.fileno(),2)
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                yield log
        finally:
            log.flush()
            for target,source in zip((1,2),saved):
                os.dup2(source,target);os.close(source)


def log_error(error, log):
    traceback.print_exception(type(error),error,error.__traceback__,file=log)
    if type(error) in (subprocess.CalledProcessError,subprocess.TimeoutExpired):
        for value in (error.stdout,error.stderr):
            if value is not None:log.write(str(value)+'\n')


def child_platform():
    # Entry is explicit and still uses every original platform execution gate.
    result = record('FAILED','PLATFORM')
    path = original.inputs.safe_path(ROOT,LOCAL+'/platform-detail.log')
    with local_output(path) as log:
        try:
            original.platform.initialize(ROOT,execute=True)
            result = record('PREPARED','PLATFORM')
        except BaseException as error:
            result.update(sanitize(error));log_error(error,log)
    return checked(result)


def platform_diagnostic(log):
    try:
        child = subprocess.run([sys.executable,'-B','-m',
            'candidates.qwen2_ci_prepare_diagnostic.diagnostic','--platform-child','--execute'],
            cwd=ROOT,capture_output=True,text=True,timeout=60,check=False)
        log.write(child.stdout);log.write(child.stderr)
        if len(child.stdout)>4096:raise ValueError('diagnostic child size')
        value=checked(json.loads(child.stdout))
        if value['phase']!='PLATFORM' or child.returncode != (2 if value['status']=='FAILED' else 0):
            raise ValueError('diagnostic child phase/exit')
        return {k:value[k] for k in ('exception','module','line')}
    except BaseException as error:
        log_error(error,log)
        return sanitize(error)


def diagnose(*,execute=False,download=False):
    if not execute and not download:return record()
    state={'phase':'PRECHECK'};result=record('FAILED')
    try:
        original.inputs.need(execute is True and download is True,'both diagnostic opt-ins required')
        original.inputs.preflight(ROOT)
        directory=original.inputs.safe_path(ROOT,LOCAL)
        original.inputs.need(not directory.exists(),'fresh diagnostic directory required')
        directory.parent.mkdir(parents=True,exist_ok=True);directory.mkdir(exist_ok=False)
        with local_output(directory/'prepare-detail.log') as log:
            try:
                with instrument(state):
                    original.prepare(execute=execute,download=download)
                result=record('PREPARED','COMPLETE')
            except BaseException as error:
                result=record('FAILED',state['phase']);result.update(sanitize(error));log_error(error,log)
                if state['phase']=='PLATFORM':
                    detail=platform_diagnostic(log)
                    result.update({'platform_'+k:v for k,v in detail.items()})
    except BaseException as error:
        result=record('FAILED',state['phase']);result.update(sanitize(error))
    return checked(result)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid diagnostic arguments')


def main(argv=None):
    p=SafeParser(description=__doc__,add_help=False)
    p.add_argument('--execute',action='store_true');p.add_argument('--download',action='store_true')
    p.add_argument('--platform-child',action='store_true',help=argparse.SUPPRESS)
    try:a=p.parse_args(argv)
    except BaseException as error:
        result=record('FAILED');result.update(sanitize(error))
        print(json.dumps(checked(result),sort_keys=True));return 2
    if a.platform_child:
        if not a.execute or a.download:
            result=record('FAILED','PLATFORM');result['exception']='VALUE_ERROR'
        else:
            try:result=child_platform()
            except BaseException as error:
                result=record('FAILED','PLATFORM');result.update(sanitize(error))
    else:result=diagnose(execute=a.execute,download=a.download)
    print(json.dumps(checked(result),sort_keys=True))
    return 2 if result['status']=='FAILED' else 0


if __name__=='__main__':
    try:code=main()
    except BaseException as error:
        fallback=record('FAILED');fallback.update(sanitize(error))
        print(json.dumps(checked(fallback),sort_keys=True));code=2
    raise SystemExit(code)
