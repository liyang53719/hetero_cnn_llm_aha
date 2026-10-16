"""Opt-in fresh M16 asset setup. No actual Public owner, Scala or RTL execution.

Only this supervisor owns the absolute 600-second setup budget. All producer
output, package logs and detailed metadata stay in a separate private workspace.
The CLI is inert without --execute-setup; cold tests never invoke producers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import traceback

from . import assets

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MODULE = 'candidates.qwen2_resident_matrix.raw_kv_public_fresh.setup'
TOTAL_SECONDS = 600
CLEANUP_SECONDS = 5
RECEIPT_SECONDS = 1
PHASE_LIMITS = {'preflight':20, 'environment':120, 'acquisition':420,
                'references':100, 'native':60, 'library':40, 'seal':20}
PHASES = tuple(PHASE_LIMITS)
OUTPUTS = ('progress.json', 'summary.json')
MAX_PROGRESS_BYTES = 1024
MAX_SUMMARY_BYTES = 8192
SETUP_SOURCES = tuple('candidates/qwen2_resident_matrix/raw_kv_public_fresh/' + name
                      for name in ('setup.py','test_setup.py','SETUP_PLAN.md'))
PROFILE = 'qwen2-public-fresh-setup-v1'
SETUP_STATUS = 'COMPLETE_FRESH_SETUP'
BASE_COMMIT = 'ba4d56cd5c56acdae70667f40b8e7bbfe17cf17c'
PROFILE_PATH = 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup_profile.json'
IMPORTED_SETUP_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
BASE_VERIFIER_SHA256 = {
    'candidates/qwen2_resident_matrix/raw_kv_public_fresh/'+name:identity for name,identity in {
    'assets.py':'8d88c830d2d4f3de58035566bbb4549905914adb1a9b0f81b8b58362d7eec6d1',
    'official_entry.patch':'ce4a7c43de8e4c22375a6f3bb7048d10b3649443c5947c2b105f1c8d9bea3f81',
    'public_entry.patch':'c5b2311767fe5de6f5f345c0964e27f45a82d4b2cc7ba4382ba054a30447ae16',
    'prepare.py':'42b7b76e0fcadf00351fd3fe521e6130b2a0b11dfe27236f1c700be91c521dce',
    'pins.json':'5011c92bc395871b2f71822ec8dd0e2cae6d483cc92e75ecd1755b32f4c447fc',
    'README.md':'faeb63b9b3edfe10f04ad0372cb8ef3653593409be09b32b4a91f5438e8df2bb',
    'test_assets.py':'9abe88ebde0fdddbe97496369aff0ff9b526751b961608cc2a58815107771171'}.items()}
TORCH_COMMIT = '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0'
EXCEPTIONS = frozenset(('ValueError','TypeError','KeyError','OSError','FileNotFoundError',
    'PermissionError','ImportError','ModuleNotFoundError','RuntimeError','TimeoutError',
    'TimeoutExpired','CalledProcessError','InterruptedError','KeyboardInterrupt','SetupError'))
REASONS = frozenset(('invalid_request','fresh_directory_required','path_alias',
    'source_pin_not_installed','source_drift','checkout_identity','phase_failed',
    'phase_receipt','deadline','interrupted','unsafe_evidence','cleanup_failed',
    'unexpected_descendant','backend_identity','setup_failed'))


class SetupError(ValueError):
    def __init__(self, reason):
        self.reason = reason if reason in REASONS else 'setup_failed'
        super().__init__(self.reason)


def need(ok, reason):
    if not ok:
        raise SetupError(reason)


def canonical_commit(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{40}', value) is not None


def finite(value, maximum):
    return type(value) in (int,float) and math.isfinite(value) and 0 <= value <= maximum


def digest(path):
    return assets.file_sha(path)


def no_symlinks(path):
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        if component.exists() or component.is_symlink():
            need(not component.is_symlink(), 'unsafe_evidence')
    return path


def fresh_directories(workspace, evidence):
    workspace, evidence = map(no_symlinks, (workspace,evidence))
    need(not workspace.exists() and not evidence.exists(), 'fresh_directory_required')
    need(workspace != evidence and not workspace.is_relative_to(evidence) and
         not evidence.is_relative_to(workspace), 'path_alias')
    workspace.mkdir(parents=True)
    evidence.mkdir(parents=True)
    need(not os.path.samefile(workspace,evidence), 'path_alias')
    return workspace, evidence


def atomic_json(path, value, limit):
    """Durable exact-name replacement; never follows an existing staging entry."""
    path = Path(path)
    raw = assets.encoded(value)
    need(len(raw) <= limit and not path.is_symlink(), 'unsafe_evidence')
    temporary = path.with_name(path.name + '.pending')
    need(not temporary.exists() and not temporary.is_symlink(), 'unsafe_evidence')
    with temporary.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_diagnostic(error, *, phase, sources=(), exit_code=None):
    """No exception text, locals, commands, external frames or arbitrary names."""
    phase = phase if phase in PHASES else 'preflight'
    kind = type(error).__name__ if type(error).__name__ in EXCEPTIONS else 'OtherError'
    result = dict(phase=phase, exception=kind, frames=[])
    if type(exit_code) is int and -128 <= exit_code <= 255:
        result['exit_code'] = exit_code
        if exit_code < 0:
            result['signal'] = -exit_code
    permitted = set(sources) | set(SETUP_SOURCES)
    tb = error.__traceback__
    while tb is not None:
        path = Path(tb.tb_frame.f_code.co_filename)
        try:
            relative = str(path.resolve().relative_to(ROOT.resolve()))
        except (OSError,ValueError):
            relative = None
        if relative in permitted and type(tb.tb_lineno) is int and 0 < tb.tb_lineno < 100000:
            result['frames'].append(dict(source=relative,line=tb.tb_lineno))
        tb = tb.tb_next
    result['frames'] = result['frames'][-3:]
    return result


def validate_diagnostic(value, phase, sources):
    need(type(value) is dict and set(value) <= {'phase','exception','frames','exit_code','signal'}
         and {'phase','exception','frames'} <= set(value), 'phase_receipt')
    need(value['phase'] == phase and value['exception'] in EXCEPTIONS | {'OtherError'} and
         type(value['frames']) is list and len(value['frames']) <= 3, 'phase_receipt')
    for frame in value['frames']:
        need(type(frame) is dict and set(frame) == {'source','line'} and
             frame['source'] in set(sources) | set(SETUP_SOURCES) and
             type(frame['line']) is int and 0 < frame['line'] < 100000, 'phase_receipt')
    if 'exit_code' in value:
        need(type(value['exit_code']) is int and -128 <= value['exit_code'] <= 255, 'phase_receipt')
    if 'signal' in value:
        need(type(value['signal']) is int and 1 <= value['signal'] <= 128 and
             value.get('exit_code') == -value['signal'], 'phase_receipt')
    return value


def save_evidence(evidence, summary):
    need({p.name for p in evidence.iterdir()} <= set(OUTPUTS), 'unsafe_evidence')
    progress = {key:summary[key] for key in ('schema','status','phase','elapsed_seconds','completed_phases')}
    atomic_json(evidence/'progress.json',progress,MAX_PROGRESS_BYTES)
    atomic_json(evidence/'summary.json',summary,MAX_SUMMARY_BYTES)


def _group_exists(pid):
    try:
        os.killpg(pid,0)
        return True
    except ProcessLookupError:
        return False


def _cleanup(proc, grace):
    """Cleanup has no competing alarm and cannot be interrupted by a second TERM."""
    handlers = {sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
    for sig in handlers:
        signal.signal(sig,signal.SIG_IGN)
    end = time.monotonic() + grace
    term_end = end-min(1.0,grace/2)  # Reserve bounded time to reap after KILL.
    try:
        try: os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        if proc.poll() is None:
            try: proc.wait(timeout=max(.001,term_end-time.monotonic()))
            except subprocess.TimeoutExpired: pass
        # Kill descendants even if their leader exited on TERM before them.
        try: os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        if proc.poll() is None:
            try: proc.wait(timeout=max(.001,end-time.monotonic()))
            except subprocess.TimeoutExpired as error:
                raise SetupError('cleanup_failed') from error
    finally:
        for sig,handler in handlers.items(): signal.signal(sig,handler)


def run_group(command, *, cwd, env, log, timeout, grace):
    proc = subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        code = proc.wait(timeout=timeout)
        # A successful leader may not leave any background producer behind.
        if _group_exists(proc.pid):
            raise SetupError('unexpected_descendant')
        return code
    except BaseException:
        _cleanup(proc,grace)
        raise


def source_snapshot(enabled):
    """One-way setup profile; the immutable 183-input asset closure stays intact."""
    need(type(enabled) is bool, 'invalid_request')
    path=ROOT/PROFILE_PATH
    need(path.is_file() and not path.is_symlink(), 'source_pin_not_installed')
    path=assets.safe_path(path)
    need(path.stat().st_size<=16384,'source_pin_not_installed')
    with path.open('rb') as stream:profile_raw=stream.read(16385)
    profile=assets.json_bytes(profile_raw,limit=16384)
    keys={'schema','profile','base_commit','base_profile','base_verifier_sha256',
          'setup_source_sha256','rows','past_tokens','total_budget'}
    need(type(profile) is dict and set(profile)==keys and
         type(profile['schema']) is int and profile['schema']==1 and
         profile['profile']==PROFILE and profile['base_commit']==BASE_COMMIT and
         profile['base_profile']==assets.PROFILE and
         type(profile['rows']) is int and profile['rows']==16 and
         type(profile['past_tokens']) is int and profile['past_tokens']==0 and
         type(profile['total_budget']) is int and profile['total_budget']==600 and
         profile['base_verifier_sha256']==BASE_VERIFIER_SHA256 and
         type(profile['setup_source_sha256']) is dict and
         set(profile['setup_source_sha256'])==set(SETUP_SOURCES), 'source_pin_not_installed')
    sources=assets.source_snapshot(enable_raw_kv=enabled)
    need(len(sources)==183 and all(sources.get(name)==value for name,value in BASE_VERIFIER_SHA256.items()),
         'source_drift')
    need(not (set(SETUP_SOURCES)|{PROFILE_PATH}) & set(sources), 'source_pin_not_installed')
    for name,value in profile['setup_source_sha256'].items():
        need(assets.digest(value) and digest(assets.safe_path(ROOT/name))==value, 'source_drift')
    need(profile['setup_source_sha256'][SETUP_SOURCES[0]]==IMPORTED_SETUP_SHA256, 'source_drift')
    return dict(sources, **profile['setup_source_sha256'], **{PROFILE_PATH:assets.sha(profile_raw)})


def asset_sources(sources):
    return {name:value for name,value in sources.items() if name not in set(SETUP_SOURCES)|{PROFILE_PATH}}


def phase_command(phase, workspace):
    python = sys.executable if phase in ('preflight','environment') else str(workspace/'venv/bin/python')
    return [python,'-B','-m',MODULE,'--internal-phase',phase,'--context',str(workspace/'context.json')]


def child_environment(workspace):
    env = dict(os.environ)
    for name in tuple(env):
        if name in ('PYTHONPATH','PYTHONHOME','PYTHONOPTIMIZE','ATEN_CPU_CAPABILITY') or name.startswith('PIP_'):
            env.pop(name,None)
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',OPENBLAS_NUM_THREADS='4',
        OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PIP_CONFIG_FILE='/dev/null',
        QWEN2_FRESH_SETUP_CHILD='1',TMPDIR=str(workspace/'tmp'))
    return env


def phase_receipt(workspace, phase, sources):
    path = workspace/(phase+'.complete.json')
    value = assets.read_json(path,limit=4096)
    keys = {'schema','phase','status','source_manifest_sha256'} | ({'manifest_sha256'} if phase=='seal' else set())
    need(type(value) is dict and set(value) == keys and type(value['schema']) is int and value['schema']==1 and
         value['phase']==phase and value['status']=='COMPLETE_SETUP_PHASE' and
         value['source_manifest_sha256']==assets.sha(assets.encoded(sources)), 'phase_receipt')
    if phase == 'seal':
        need(assets.digest(value['manifest_sha256']) and digest(workspace/'ASSETS.json')==value['manifest_sha256'],
             'phase_receipt')
    return value


def run(workspace, evidence, *, checkout_commit, enable_raw_kv=False, deadline_ns=None):
    """One bounded attempt; no public output ever contains private producer text."""
    started = time.monotonic(); end = started + TOTAL_SECONDS
    summary = dict(schema=1,status='NOT_RUN',phase='preflight',elapsed_seconds=0.0,completed_phases=[],
        total_budget_seconds=TOTAL_SECONDS,cleanup_grace_seconds=CLEANUP_SECONDS,
        actual_chain_executed=False,numerical_acceptance=False)
    if not canonical_commit(checkout_commit) or type(enable_raw_kv) is not bool or \
       (deadline_ns is not None and (type(deadline_ns) is not int or not 0 < deadline_ns < 1 << 63)):
        summary['reason']='invalid_request'; return 2,summary
    if deadline_ns is not None: end = min(end,deadline_ns/1_000_000_000)
    work_end = end-CLEANUP_SECONDS-RECEIPT_SECONDS
    if time.monotonic() >= work_end:
        summary['reason']='deadline'; return 2,summary
    old_alarm,old_term = signal.getsignal(signal.SIGALRM),signal.getsignal(signal.SIGTERM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if old_timer != (0.0,0.0):
        summary['reason']='invalid_request'; return 2,summary
    def expired(signum,frame): raise TimeoutError()
    def interrupted(signum,frame): raise InterruptedError()
    signal.signal(signal.SIGALRM,expired); signal.signal(signal.SIGTERM,interrupted)
    def arm(target=None):
        remaining = (work_end if target is None else target)-time.monotonic()
        if remaining <= 0: raise TimeoutError()
        signal.setitimer(signal.ITIMER_REAL,remaining)
    sources={}; out=None; code=1
    try:
        arm()
        # Reject the unreviewed pin layer before installation or other side effects.
        sources=source_snapshot(enable_raw_kv)
        need(os.environ.get('ATEN_CPU_CAPABILITY') is None,'backend_identity')
        workspace,out=fresh_directories(workspace,evidence)
        (workspace/'tmp').mkdir(); (workspace/'logs').mkdir()
        context=dict(schema=1,workspace=str(workspace),checkout_commit=checkout_commit,
            enable_raw_kv=enable_raw_kv,source_sha256=sources,asset_source_sha256=asset_sources(sources),
            work_deadline_ns=int(work_end*1_000_000_000))
        atomic_json(workspace/'context.json',context,131072)
        env=child_environment(workspace)
        summary.update(status='SETUP_RUNNING',source_manifest_sha256=assets.sha(assets.encoded(sources)))
        for phase in PHASES:
            summary.update(phase=phase,elapsed_seconds=round(time.monotonic()-started,6))
            save_evidence(out,summary)
            need(source_snapshot(enable_raw_kv)==sources,'source_drift')
            signal.setitimer(signal.ITIMER_REAL,0)
            remaining=work_end-time.monotonic()
            if remaining <= 0: raise TimeoutError()
            timeout=min(PHASE_LIMITS[phase],remaining)
            with (workspace/'logs'/(phase+'.log')).open('xb') as log:
                rc=run_group(phase_command(phase,workspace),cwd=ROOT,env=env,log=log,
                             timeout=timeout,grace=CLEANUP_SECONDS)
            arm()
            need(type(rc) is int and -128 <= rc <= 255,'phase_failed')
            if rc != 0:
                error=SetupError('phase_failed')
                diagnostic=safe_diagnostic(error,phase=phase,sources=sources,exit_code=rc)
                failure=workspace/(phase+'.failure.json')
                if failure.is_file() and not failure.is_symlink():
                    try: diagnostic=validate_diagnostic(assets.read_json(failure,limit=2048),phase,sources)
                    except Exception: pass
                    diagnostic['exit_code']=rc
                    if rc<0: diagnostic['signal']=-rc
                summary['diagnostic']=diagnostic
                raise error
            result=phase_receipt(workspace,phase,sources)
            need(source_snapshot(enable_raw_kv)==sources,'source_drift')
            summary['completed_phases'].append(phase)
            if phase=='seal':summary['manifest_sha256']=result['manifest_sha256']
        arm()
        need(summary['completed_phases']==list(PHASES),'phase_receipt')
        summary.update(status='SETUP_VERIFYING',reason='fresh_assets_verified');code=0
    except (TimeoutError,subprocess.TimeoutExpired) as error:
        summary.update(status='SETUP_TIMEOUT',reason='deadline')
        summary['diagnostic']=safe_diagnostic(error,phase=summary['phase'],sources=sources)
    except (InterruptedError,KeyboardInterrupt) as error:
        summary.update(status='SETUP_INTERRUPTED',reason='interrupted')
        summary['diagnostic']=safe_diagnostic(error,phase=summary['phase'],sources=sources)
    except Exception as error:
        reason=error.reason if type(error) is SetupError else 'setup_failed'
        summary.update(status='SETUP_FAILED',reason=reason)
        summary.setdefault('diagnostic',safe_diagnostic(error,phase=summary['phase'],sources=sources))
    finally:
        # run_group has completed whole-group cleanup before control reaches here.
        # Keep our handlers until the bounded final write, never an inherited timer.
        signal.setitimer(signal.ITIMER_REAL,0)
        try:
            summary['source_recheck']='NOT_STARTED'
            if sources:
                if time.monotonic()>=work_end:
                    summary['source_recheck']='NOT_COMPLETED_DEADLINE'
                    if code==0:
                        code=1;summary.update(status='SETUP_TIMEOUT',reason='deadline')
                else:
                    try:
                        arm()
                        need(source_snapshot(enable_raw_kv)==sources,'source_drift')
                        if 'manifest_sha256' in summary:
                            need(digest(workspace/'ASSETS.json')==summary['manifest_sha256'],'source_drift')
                        summary['source_recheck']='UNCHANGED'
                    except BaseException as error:
                        summary['source_recheck']='NOT_COMPLETED_DEADLINE' if isinstance(error,TimeoutError) else 'FAILED'
                        summary['postflight_reason']='deadline' if isinstance(error,TimeoutError) else 'source_drift'
                        if code==0:
                            code=1
                            summary.update(status='SETUP_TIMEOUT' if isinstance(error,TimeoutError) else 'SETUP_FAILED',
                                           reason=summary['postflight_reason'])
                            summary['diagnostic']=safe_diagnostic(error,phase=summary['phase'],sources=sources)
                        # Preserve the first producer/timeout diagnostic on failure.
                    finally:
                        signal.setitimer(signal.ITIMER_REAL,0)
            if code==0:
                need(summary['source_recheck']=='UNCHANGED' and summary['completed_phases']==list(PHASES),'phase_receipt')
                summary.update(status=SETUP_STATUS,setup_profile=PROFILE,
                               setup_profile_sha256=sources[PROFILE_PATH],
                               asset_source_manifest_sha256=assets.sha(assets.encoded(asset_sources(sources))))
            summary['elapsed_seconds']=round(time.monotonic()-started,6)
            if out is not None:
                arm(end)
                # Only our exact staging entries are removed after an interrupted write.
                for name in OUTPUTS:(out/(name+'.pending')).unlink(missing_ok=True)
                provisional=dict(summary)
                if code==0:provisional.update(status='SETUP_VERIFYING',reason='awaiting_private_commit')
                save_evidence(out,provisional)
                if code==0:
                    info=workspace.stat()
                    receipt=dict(schema=1,profile=PROFILE,status=SETUP_STATUS,base_commit=BASE_COMMIT,
                        base_profile=assets.PROFILE,base_verifier_sha256=BASE_VERIFIER_SHA256,
                        setup_profile_sha256=sources[PROFILE_PATH],source_sha256=sources,
                        source_manifest_sha256=assets.sha(assets.encoded(sources)),
                        asset_source_manifest_sha256=summary['asset_source_manifest_sha256'],
                        asset_manifest_sha256=summary['manifest_sha256'],enable_raw_kv=enable_raw_kv,
                        rows=16,past_tokens=0,workspace=dict(path=str(workspace),device=info.st_dev,inode=info.st_ino),
                        checkout_commit=checkout_commit,completed_phases=list(PHASES),source_recheck='UNCHANGED',
                        deadline_monotonic_ns=int(end*1e9),elapsed_seconds=round(time.monotonic()-started,6),
                        total_budget_seconds=TOTAL_SECONDS,actual_chain_executed=False,numerical_acceptance=False)
                    # This private final commit marker is mandatory for later admission.
                    # Its absence makes even a previously saved public summary incomplete.
                    atomic_json(workspace/'SETUP.json',receipt,131072)
                    summary['setup_receipt_sha256']=assets.sha(assets.encoded(receipt))
                    # The summary links the private commit. Progress stays provisional
                    # and is never accepted as a readiness credential.
                    atomic_json(out/'summary.json',summary,MAX_SUMMARY_BYTES)
                if time.monotonic()>=end:raise TimeoutError()
        except BaseException as error:
            code=1
            reason='deadline' if isinstance(error,TimeoutError) else 'unsafe_evidence'
            summary['finalization_reason']=reason
            if summary['status'] in (SETUP_STATUS,'SETUP_VERIFYING','SETUP_RUNNING'):
                summary.update(status='SETUP_TIMEOUT' if reason=='deadline' else 'SETUP_FAILED',reason=reason)
                summary.setdefault('diagnostic',safe_diagnostic(error,phase=summary['phase'],sources=sources))
            # Revoke only this attempt's commit marker, never arbitrary existing data.
            if out is not None:
                try:(workspace/'SETUP.json').unlink(missing_ok=True)
                except OSError:pass
                try:(out/'summary.json').unlink(missing_ok=True)
                except OSError:pass
                # Best effort only within the original deadline. A retained provisional
                # summary cannot authorize execution without the final private marker.
                if time.monotonic()<end:
                    try:
                        arm(end)
                        for name in OUTPUTS:(out/(name+'.pending')).unlink(missing_ok=True)
                        summary.pop('setup_receipt_sha256',None)
                        save_evidence(out,summary)
                    except BaseException:pass
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,old_alarm);signal.signal(signal.SIGTERM,old_term)
    return code,summary


def _read_context(path):
    context=assets.read_json(path,limit=131072)
    need(type(context) is dict and set(context)=={'schema','workspace','checkout_commit','enable_raw_kv',
         'source_sha256','asset_source_sha256','work_deadline_ns'} and type(context['schema']) is int and context['schema']==1 and
         canonical_commit(context['checkout_commit']) and type(context['enable_raw_kv']) is bool and
         type(context['work_deadline_ns']) is int and context['work_deadline_ns']>time.monotonic_ns(), 'invalid_request')
    workspace=assets.safe_path(context['workspace'],directory=True)
    need(assets.safe_path(path)==workspace/'context.json','invalid_request')
    need(source_snapshot(context['enable_raw_kv'])==context['source_sha256'] and
         context['asset_source_sha256']==asset_sources(context['source_sha256']),'source_drift')
    return context,workspace


def remaining(context, ceiling):
    value=min(ceiling,(context['work_deadline_ns']-time.monotonic_ns())/1_000_000_000)
    if value<=0:raise TimeoutError()
    return value


def private_json(path,value):
    atomic_json(path,value,2*1024*1024)


def file_record(workspace,path):
    path=assets.safe_path(path)
    need(path.is_relative_to(workspace),'invalid_request')
    return dict(path=str(path.relative_to(workspace)),bytes=path.stat().st_size,sha256=digest(path))


def _phase_preflight(context,workspace):
    need(sys.version_info[:2]==(3,12) and sys.flags.optimize==0,'backend_identity')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,timeout=remaining(context,10)).strip()
    need(head==context['checkout_commit'],'checkout_identity')
    # The selected source manifest admits only exact reviewed overlay bytes.
    need(source_snapshot(context['enable_raw_kv'])==context['source_sha256'],'source_drift')
    canonical='chisel/continuous_prefill/tests/qwen2_block.cpp'
    raw=subprocess.check_output(['git','show','HEAD:'+canonical],cwd=ROOT,timeout=remaining(context,10))
    need(raw==(ROOT/canonical).read_bytes(),'checkout_identity')
    # New orchestration must also be checked-in exact bytes; approved overlays
    # remain admitted through their existing source manifests, never a clean-tree shortcut.
    for name in (*SETUP_SOURCES,PROFILE_PATH):
        raw=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT,timeout=remaining(context,10))
        need(assets.sha(raw)==context['source_sha256'][name],'checkout_identity')
    import shutil
    need(shutil.disk_usage(workspace).free>=4*1024**3,'invalid_request')


def backend_identity():
    """Re-evaluated in the process that will execute the official forward."""
    import numpy as np
    import torch
    from scripts import qwen2_layer0_model_gate as native
    need(sys.version_info[:2]==(3,12) and sys.flags.optimize==0 and np.__version__=='2.3.5' and
         torch.__version__=='2.10.0+cpu' and torch.version.git_version==TORCH_COMMIT and
         torch.backends.cpu.get_cpu_capability()=='AVX512' and os.getenv('ATEN_CPU_CAPABILITY') is None,
         'backend_identity')
    _,identity=native.runtime_identity(ROOT)
    config=torch.__config__.show()
    need(torch.backends.mkldnn.enabled and '3.7.1' in config and
         '8d263e693366ef8db40acc569cc7d8edf644556d' in config,'backend_identity')
    return torch,identity


def backend_threads(torch):
    need(torch.get_num_threads()==4 and torch.get_num_interop_threads()==1 and
         torch.are_deterministic_algorithms_enabled() and torch.backends.mkldnn.enabled,'backend_identity')


def backend_preflight(context_path):
    context,workspace=_read_context(context_path)
    torch,identity=backend_identity()
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    backend_threads(torch)
    private_json(workspace/'backend.json',dict(identity=identity,torch_commit=TORCH_COMMIT,
        cpu_capability='AVX512',intraop_threads=4,interop_threads=1,deterministic=True))
    remaining(context,1)


def _phase_environment(context,workspace):
    import venv
    venv.EnvBuilder(with_pip=True).create(workspace/'venv')
    python=str(workspace/'venv/bin/python')
    common=[python,'-m','pip','--disable-pip-version-check','install','--no-input','--no-cache-dir','--retries','0','--timeout','30']
    for command in (common+['--index-url','https://download.pytorch.org/whl/cpu','torch==2.10.0'],
                    common+['--index-url','https://pypi.org/simple','numpy==2.3.5','transformers==4.40.1']):
        subprocess.run(command,cwd=ROOT,check=True,timeout=remaining(context,120))
    code='from pathlib import Path; from '+MODULE+' import backend_preflight; backend_preflight(Path('+repr(str(workspace/'context.json'))+'))'
    subprocess.run([python,'-B','-c',code],cwd=ROOT,check=True,timeout=remaining(context,30))


def _phase_acquisition(context,workspace):
    sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
    from qwen2_layer0_payload import collect,load_payload
    collect(ROOT,workspace/'payload')
    load_payload(ROOT,workspace/'payload')
    remaining(context,1)


def _phase_references(context,workspace):
    """Original producers only; source generation never reads native goldens."""
    sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
    from qwen2_layer0_payload import load_payload
    from scripts import qwen2_rms_rope_prefill_candidate as rms
    from candidates.qwen2_resident_matrix.dense_block_reduce.reference import builder as b
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
    _,payload=load_payload(ROOT,workspace/'payload')
    original,header,_=b.regenerate_sources(ROOT)
    reduced,_=b.transform(original,(ROOT/b.PROFILE_REL).read_bytes())
    need(assets.sha(original)==assets.CPP_SHA256['sequential'] and
         assets.sha(reduced)==assets.CPP_SHA256['reduced'] and assets.sha(header)==assets.HEADER_SHA256,'source_drift')
    compiler=dense_silu.compiler_identity()
    for role,raw in (('sequential',original),('reduced',reduced)):
        directory=workspace/role;directory.mkdir()
        cpp=directory/'candidate.cpp';cpp.write_bytes(raw)
        hdr=directory/'block_layout.h';hdr.write_bytes(header)
        binary=directory/'candidate'
        command=[compiler['path'],*b.FLAGS,str(cpp),'-o',str(binary)]
        timeout=remaining(context,10);started=time.monotonic()
        subprocess.run(command,cwd=directory,check=True,timeout=timeout)
        private_json(directory/'compile.json',dict(schema=1,status='COMPILED',producer=assets.PRODUCERS[role],
            argv=command,compiler=compiler,returncode=0,source_sha256=context['asset_source_sha256'],
            cpp_sha256=digest(cpp),header_sha256=digest(hdr),binary_sha256=digest(binary),
            elapsed_seconds=time.monotonic()-started,requested_timeout_seconds=timeout))
    readonly=workspace/'readonly';readonly.mkdir()
    table=readonly/'rope_full.f32le';rms.generate_tables(workspace/'sequential/candidate',table)
    layout=rms.R.make_layout();rms.G.validate_layout(layout)
    rms.write_arena(layout,payload,16,0,readonly,table)
    need(digest(table)==assets.TABLE_SHA256 and digest(readonly/'readonly_arena.f32le')==assets.ARENA_SHA256 and
         digest(readonly/'input_x.f32le')==assets.INPUT_X_SHA256,'source_drift')
    rms.runtime_tools(workspace/'sequential/candidate')
    for role in ('sequential','reduced'):
        directory=workspace/role;rawdir=directory/'raw_stages';rawdir.mkdir()
        empty=directory/'empty_cache.bin';empty.write_bytes(b'')
        command=[str(directory/'candidate'),str(readonly/'readonly_arena.f32le'),'16',str(rawdir),'0',str(empty),str(empty)]
        timeout=remaining(context,30);started=time.monotonic()
        done=subprocess.run(command,cwd=directory,capture_output=True,timeout=timeout,check=False)
        (directory/'stdout.log').write_bytes(done.stdout);(directory/'stderr.log').write_bytes(done.stderr)
        ack=rms.software_ack(done.stdout.decode('utf-8'),16,done.returncode)
        need({p.name for p in rawdir.iterdir()}==set(assets.output_inventory()),'phase_receipt')
        outputs={}
        for name,size in assets.output_inventory().items():
            item=file_record(workspace,rawdir/name);need(item['bytes']==size,'phase_receipt');outputs[name]=item['sha256']
        private_json(directory/'run.json',dict(schema=1,status='COMPLETE_REFERENCE_ONLY',producer=assets.PRODUCERS[role],
            argv=command,returncode=done.returncode,software_ack=ack,readonly_sha256=assets.ARENA_SHA256,
            input_x_sha256=assets.INPUT_X_SHA256,table_sha256=assets.TABLE_SHA256,output_sha256=outputs,
            actual_chain_executed=False,stdout=file_record(workspace,directory/'stdout.log'),
            empty_cache=file_record(workspace,empty),elapsed_seconds=time.monotonic()-started,requested_timeout_seconds=timeout))
        # Original shape/dtype/cache/semantic verification, no reference reads.
        actual=rms.C.load_actual(rawdir,readonly/'readonly_arena.f32le',readonly/'input_x.f32le',layout,16)
        for name in ('cache_k','cache_v'):
            need(actual[name].transpose(0,2,1,3).copy().tobytes()==(rawdir/(name+'.f32le')).read_bytes(),'phase_receipt')
        need(all(rms.N.audit_semantics(actual,None,rms.G.config_for(layout),'bf16').values()),'phase_receipt')
        if role=='sequential':
            tensors=directory/'tensors';tensors.mkdir()
            private_json(directory/'export.json',rms.C.export_actual(actual,tensors))
    remaining(context,1)


def _phase_native(context,workspace):
    from scripts import qwen2_layer0_model_gate as native
    torch,_=backend_identity()
    result=native.run_gate(ROOT,workspace/'payload',workspace/'native',tokens=16,carried=False,threads=4)
    backend_threads(torch)
    need(result['status']=='PASS_BF16_STAGE_BUDGET','phase_failed')
    remaining(context,1)


def _phase_library(context,workspace):
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
    dense_silu.build_library(workspace/'library')
    dense_silu.verify_library(workspace/'library/official_bf16_compile.json')
    remaining(context,1)


def _phase_seal(context,workspace):
    rec=lambda p:file_record(workspace,p)
    ro=workspace/'readonly'
    value=dict(schema=1,profile=assets.PROFILE,status=assets.STATUS,rows=16,past_tokens=0,
        source_sha256=context['asset_source_sha256'],source_manifest_sha256=assets.sha(assets.encoded(context['asset_source_sha256'])),
        payload=dict(manifest=rec(workspace/'payload/manifest.json'),tensors={name:rec(workspace/'payload'/(name+'.bin')) for name in assets.TENSOR_PINS}),
        readonly=dict(arena=rec(ro/'readonly_arena.f32le'),table=rec(ro/'rope_full.f32le'),
            input_x=rec(ro/'input_x.f32le'),input_x_sha256=assets.INPUT_X_SHA256,intermediate_preloads=0),
        library=dict(receipt=rec(workspace/'library/official_bf16_compile.json'),binary=rec(workspace/'library/official_bf16_matrix_silu.so')))
    for role in ('sequential','reduced'):
        d=workspace/role
        value[role]=dict(producer=assets.PRODUCERS[role],cpp=rec(d/'candidate.cpp'),header=rec(d/'block_layout.h'),
            executable=rec(d/'candidate'),compile=rec(d/'compile.json'),run=rec(d/'run.json'),
            outputs={name:rec(d/'raw_stages'/name) for name in assets.output_inventory()})
    value['sequential'].update(export_receipt=rec(workspace/'sequential/export.json'),
        tensors={name:rec(workspace/'sequential/tensors'/('candidate_'+name+'.f32le')) for name in assets.shapes()})
    value['native']=dict(producer=assets.NATIVE_PRODUCER,result=rec(workspace/'native/RESULT.json'),outputs={
        mode:{method:{name:rec(workspace/'native'/mode/'phase_0'/(prefix+'_'+name+'.f32le')) for name in assets.shapes()}
              for method,prefix in zip(assets.METHODS,('native','independent'),strict=True)} for mode in assets.MODES})
    assets.validate_manifest(value)
    candidate=workspace/'ASSETS.candidate.json'
    private_json(candidate,value)
    identity=digest(candidate)
    assets.verify(candidate,identity,rows=16,enable_raw_kv=context['enable_raw_kv'])
    remaining(context,1)
    os.replace(candidate,workspace/'ASSETS.json')
    fd=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return identity


PRODUCERS={'preflight':_phase_preflight,'environment':_phase_environment,'acquisition':_phase_acquisition,
           'references':_phase_references,'native':_phase_native,'library':_phase_library,'seal':_phase_seal}


def internal_phase(phase,context_path):
    context={};workspace=None
    try:
        need(os.environ.get('QWEN2_FRESH_SETUP_CHILD')=='1' and phase in PHASES,'invalid_request')
        context,workspace=_read_context(context_path)
        result=PRODUCERS[phase](context,workspace)
        need(source_snapshot(context['enable_raw_kv'])==context['source_sha256'],'source_drift')
        remaining(context,1)
        receipt=dict(schema=1,phase=phase,status='COMPLETE_SETUP_PHASE',
            source_manifest_sha256=assets.sha(assets.encoded(context['source_sha256'])))
        if phase=='seal':receipt['manifest_sha256']=result
        private_json(workspace/(phase+'.complete.json'),receipt)
        return 0
    except BaseException as error:
        # Detailed traceback is captured only by the supervisor's private log.
        traceback.print_exc()
        if workspace is not None:
            private_json(workspace/(phase+'.failure.json'),safe_diagnostic(error,phase=phase,sources=context.get('source_sha256',{})))
        return 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-setup',action='store_true')
    parser.add_argument('--workspace',type=Path);parser.add_argument('--evidence',type=Path)
    parser.add_argument('--checkout-commit');parser.add_argument('--enable-raw-kv',action='store_true')
    parser.add_argument('--internal-phase',choices=PHASES);parser.add_argument('--context',type=Path)
    args=parser.parse_args(argv)
    if args.internal_phase:
        if args.execute_setup or args.context is None:return 2
        return internal_phase(args.internal_phase,args.context)
    if not args.execute_setup or args.workspace is None or args.evidence is None or args.checkout_commit is None:
        return 2
    code,summary=run(args.workspace,args.evidence,checkout_commit=args.checkout_commit,enable_raw_kv=args.enable_raw_kv)
    print(json.dumps(summary,sort_keys=True,allow_nan=False))
    return code


if __name__=='__main__':
    raise SystemExit(main())
