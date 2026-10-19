"""Regression tests for primary-error priority and bounded final evidence time."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import ast,copy,io,json,os,tempfile,types
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock
checks=[]
def need(ok,why):
    if not ok:raise ValueError(why)
class NativeA(ValueError):pass
class ReceiptB(ValueError):pass
class TimerB(ValueError):pass
fixture=read(ROOT/'test_continuation_cold.py',PINS['test_continuation_cold.py'])
node=next(n for n in ast.parse(fixture).body if isinstance(n,ast.FunctionDef) and n.name=='coordinator_case')
lines=fixture.splitlines(keepends=True);function=b''.join(lines[node.lineno-1:node.end_lineno])+b'\n'
replacements=(
 (b"def save(path,value):saved[path.name]=copy.deepcopy(value);path.write_text(json.dumps(value));return pin(path.read_bytes())",b"def save(path,value):\n            fault_events.append({'at':'receipt','already_recorded_failure_type':value['failure_type'],'clock':dict(value['clock'])});saved[path.name]=copy.deepcopy(value);path.write_text(json.dumps(value))\n            if fault_mode=='save':raise ReceiptB('synthetic secondary evidence write B')\n            if fault_mode=='tail':clock[0]=value['clock']['report_stop']\n            return pin(path.read_bytes())"),
 (b"native.append(name);limits_seen.append((name,deadline));",b"native.append(name);limits_seen.append((name,deadline));\n            if name=='fresh_make' and fault_primary:\n                clock[0]=fault_at;fault_events.append({'at':'native','failure_type':'NativeA','now':clock[0]});raise NativeA('synthetic primary native A')\n            "),
 (b"if bad:rejects(call,bad)",b"if bad:call()"),
 (b"mock.patch.object(continuation.signal,'setitimer',return_value=None)",b"mock.patch.object(continuation.signal,'setitimer',side_effect=fault_timer)"),
 (b"mock.patch.object(continuation.signal,'signal',return_value=None)",b"mock.patch.object(continuation.signal,'signal',side_effect=fault_signal)"),
 (b"patches=[mock.patch.object(continuation,'inherited_fifo'",b"patches=[mock.patch.object(continuation.os,'umask',side_effect=fault_umask),mock.patch.object(continuation,'inherited_fifo'"),
)
for old,new in replacements:
    need(function.count(old)==1,'one synthetic failure fixture anchor');function=function.replace(old,new)
start=1000.;stop=7600.;times=continuation.budget(start,stop)
exec(compile(function,'synthetic_v2_evidence_fault_fixture','exec'),globals())
def exercise(mode,primary=True,at=start,expected=None):
    global fault_mode,fault_primary,fault_at,fault_events,fault_timers,fault_restores
    fault_mode=mode;fault_primary=primary;fault_at=at;fault_events=[];fault_timers=[];fault_restores=[]
    observed=None
    try:coordinator_case('synthetic_fault')
    except BaseException as error:observed=error
    if expected is not None:need(type(observed) is expected,'expected '+expected.__name__+' got '+str(type(observed)))
    if primary and expected is NativeA:need(str(observed)=='synthetic primary native A','exact original native error retained')
    if mode not in ('arm','restore'):
        receipt=next(e for e in fault_events if e['at']=='receipt');clock=receipt['clock'];now=at if primary else start
        need(clock['report_stop']==min(stop,now+120),'report stop clipped by single total deadline and 120')
        need(receipt['already_recorded_failure_type']==('NativeA' if primary else None),'first error recorded before secondary write/tail')
        need(fault_timers[-1]==0,'timer disabled after evidence attempt')
    need(fault_restores==['timer','sigalrm','sigterm','umask'],'every fixed restoration attempted once despite previous error')
    return observed,copy.deepcopy(fault_events),list(fault_timers)
def fault_timer(kind,value):
    fault_timers.append(value)
    if value==0:fault_restores.append('timer')
    if fault_mode=='arm' and value==min(stop,fault_at+120)-fault_at:raise TimerB('synthetic final timer arm B')
    if fault_mode=='restore' and value==0:raise TimerB('synthetic final timer restore B')
def fault_signal(kind,handler):
    if handler is None:
        name='sigalrm' if kind==continuation.signal.SIGALRM else 'sigterm';fault_restores.append(name)
        if fault_mode==name:raise TimerB('synthetic '+name+' restore B')
    return None
def fault_umask(mask):
    if mask!=0o077:
        fault_restores.append('umask')
        if fault_mode=='umask':raise TimerB('synthetic umask restore B')
    return 0o022
for mode in ('save','tail'):
    exercise(mode,expected=NativeA);checks.append('primary_native_preserved_over_'+mode+'_failure')
    exercise(mode,primary=False,expected=ReceiptB if mode=='save' else ValueError);checks.append('without_primary_'+mode+'_error_becomes_primary')
exercise('none',expected=NativeA);checks.append('early_native_failure_report_stop_is_now_plus120')
exercise('none',at=stop-30,expected=NativeA);checks.append('near_total_stop_report_tail_clipped_to_remaining30')
exercise('tail',at=stop-30,expected=NativeA);checks.append('near_total_tail_exhaustion_preserves_native_and_never_extends_total')
for mode in ('arm','restore','sigalrm','sigterm','umask'):
    exercise(mode,expected=NativeA);checks.append('primary_native_preserved_over_'+mode+'_error_all_restores_attempted')
    exercise(mode,primary=False,expected=TimerB);checks.append('without_primary_'+mode+'_error_primary_all_restores_attempted')
print(json.dumps({'status':'PASS_PRIMARY_ERROR_AND_EVIDENCE_TAIL_SYNTHETIC_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False},sort_keys=True))
TEST_RESULTS.append({'module':'test_fault_cold.py','tests':len(checks),'checks':checks})
