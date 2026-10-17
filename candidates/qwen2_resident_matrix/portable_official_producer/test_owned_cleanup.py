"""Cold caller-level strict-cleanup routing and first-failure regressions."""
import ast
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RUN_TREE=ast.parse((HERE/'owned_commands.py').read_bytes())
RUN=next(n for n in RUN_TREE.body if isinstance(n,ast.FunctionDef) and n.name=='run')
LAUNCH=ROOT/'candidates/qwen2_resident_matrix/portable_official_producer_launch/launch.py'


class CleanupFailure(RuntimeError):
    pass


class CallerBoundary(unittest.TestCase):
    def invoke(self,*,work_error=None,code=0,cleanup_error=None,validation_error=None,reap=True,protect_error=None,restore_error=None,mask_error=None,arm_error=None,teardown_expiry=False,restore_expiry=False,blocked_entry=False,blocked_proof=False,final_clock_sequence=False):
        calls=[];captured={};clock=[100.0];blocked=[blocked_entry];restored=[False];final_reads=[0]
        def handler(signum,value):
            calls.append(('handler',(signum,value)))
            if value=='original' and restore_expiry:clock[0]=120.0
            if value=='original' and restore_error is not None:raise restore_error
        def mask(operation,value):
            if operation==2:restored[0]=True
            if value and mask_error is not None:raise mask_error
            return {14} if blocked[0] else set()
        def protect():
            calls.append(('protect_cleanup',))
            if teardown_expiry and sum(row[0]=='protect_cleanup' for row in calls)>1:clock[0]=120.0
            if protect_error is not None:raise protect_error
        signal=SimpleNamespace(SIG_BLOCK=1,SIG_SETMASK=2,ITIMER_REAL=3,SIGALRM=14,
            getitimer=lambda _: (0.0,0.0),getsignal=lambda _: 'original',
            signal=handler,setitimer=lambda *args:None,
            pthread_sigmask=mask)
        def spawn(owner,*args,**kwargs):
            owner.update(process=SimpleNamespace(pid=42,returncode=None),identity={'fixture':'exact'})
            captured['owner']=owner;calls.append(('spawn',))
        def observe(*args):
            calls.append(('observe',))
            if work_error is not None:raise work_error
            return code
        def cleanup(owner,stop):
            calls.append(('strict_cleanup',stop))
            blocked[0]=blocked_proof
            if reap:owner['process'].returncode=0
            if cleanup_error is not None:raise cleanup_error
            proof={'fixture':'parent-owned'};owner['strict_cleanup_proof']=proof
            return proof
        def validate(proof,*,owner,stop):
            calls.append(('strict_validate',stop))
            if validation_error is not None:raise validation_error
            self.assertIs(proof,owner['strict_cleanup_proof'])
            return proof
        def arm(stop):
            calls.append(('proof_arm',stop))
            if arm_error is not None:raise arm_error
        strict=SimpleNamespace(cleanup_owned=cleanup,validate_cleanup_proof=validate,CleanupFailure=CleanupFailure)
        helper=SimpleNamespace(CONTROL_SIGNALS={10,12,14},spawn_owned=spawn,observe_exit=observe,
            protect_cleanup=protect,arm_receipt_deadline=arm,strict_cleanup=strict,
            cleanup_owned=lambda *args: (_ for _ in ()).throw(AssertionError('legacy cleanup called')))
        def monotonic():
            if final_clock_sequence and restored[0]:
                final_reads[0]+=1;calls.append(('final_clock',final_reads[0]))
                return 119.0 if final_reads[0]==1 else 121.0
            return clock[0]
        ns=dict(Path=Path,signal=signal,time=SimpleNamespace(monotonic=monotonic),
            os=SimpleNamespace(environ={}),load_owner=lambda _:helper,EXEC_BOOTSTRAP='fixture')
        exec(compile(ast.Module(body=[RUN],type_ignores=[]),str(HERE/'owned_commands.py'),'exec'),ns)
        with tempfile.TemporaryDirectory() as t:
            try:
                result=ns['run'](ROOT,['/usr/bin/python3','-c','unused'],cwd=Path(t),
                    log=Path(t)/'owned.log',end_ns=120*10**9)
            except BaseException as error:
                return None,error,calls,captured
        return result,None,calls,captured

    def test_success_requires_strict_proof_before_return(self):
        result,error,calls,_=self.invoke()
        self.assertIsNone(error);self.assertIs(result['cleanup_complete'],True)
        self.assertLess(calls.index(('strict_cleanup',120.0)),calls.index(('strict_validate',120.0)))
        self.assertEqual(result['observed_exit_code'],0)

    def test_primary_timeout_preserved_with_cleanup_failure(self):
        primary=InterruptedError('owned command interrupted');secondary=CleanupFailure('fixture private message')
        result,error,calls,_=self.invoke(work_error=primary,cleanup_error=secondary)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertIs(error.owned_command_cleanup_failure,secondary)
        self.assertEqual(str(error),'owned command interrupted')
        evidence=error.owned_command_control
        self.assertEqual(evidence['status'],'CLEANUP_FAILED');self.assertFalse(evidence['cleanup_complete'])
        self.assertEqual(evidence['cleanup_failure_class'],'CleanupFailure')
        self.assertTrue(evidence['authority_released']);self.assertEqual(evidence['original_stop'],120.0)
        self.assertFalse(evidence['downstream_work_permitted']);self.assertNotIn('private',str(evidence))

    def test_primary_timeout_after_successful_cleanup_still_fails(self):
        primary=InterruptedError('owned command interrupted')
        result,error,_,_=self.invoke(work_error=primary)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertTrue(error.owned_command_control['cleanup_complete'])
        self.assertFalse(error.owned_command_control['cleanup_failed'])
        self.assertTrue(error.owned_command_control['proof_available'])
        self.assertFalse(error.owned_command_control['downstream_work_permitted'])

    def test_cleanup_failure_without_primary_propagates_typed_failure(self):
        secondary=CleanupFailure('fixture')
        result,error,_,_=self.invoke(cleanup_error=secondary,reap=False)
        self.assertIsNone(result);self.assertIs(error,secondary)
        self.assertFalse(error.owned_command_control['cleanup_complete'])
        self.assertFalse(error.owned_command_control['leader_reaped'])
        self.assertFalse(error.owned_command_control['authority_released'])

    def test_proof_validation_failure_cannot_grant_success(self):
        secondary=CleanupFailure('bad proof')
        result,error,_,_=self.invoke(validation_error=secondary)
        self.assertIsNone(result);self.assertIs(error,secondary)
        self.assertFalse(error.owned_command_control['cleanup_complete'])
        self.assertTrue(error.owned_command_control['cleanup_failed'])

    def test_nonzero_work_remains_primary_if_cleanup_also_fails(self):
        secondary=CleanupFailure('fixture')
        result,error,_,_=self.invoke(code=7,cleanup_error=secondary)
        self.assertIsNone(result);self.assertIs(type(error),ValueError)
        self.assertEqual(str(error),'owned command failed or expired')
        self.assertIs(error.owned_command_cleanup_failure,secondary)
        self.assertFalse(error.owned_command_control['downstream_work_permitted'])

    def test_unexpected_cleanup_class_has_fixed_bounded_code(self):
        result,error,_,_=self.invoke(cleanup_error=RuntimeError('PRIVATE_SENTINEL'))
        self.assertIsNone(result)
        self.assertEqual(error.owned_command_control['cleanup_failure_class'],'OTHER_CONTROL_FAILURE')
        self.assertNotIn('PRIVATE_SENTINEL',str(error.owned_command_control))

    def test_protect_failure_keeps_primary_and_blocks_barrier(self):
        primary=InterruptedError('owned command interrupted');secondary=RuntimeError('protect')
        result,error,calls,_=self.invoke(work_error=primary,protect_error=secondary)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertIs(error.owned_command_cleanup_failure,secondary)
        self.assertFalse(error.owned_command_control['cleanup_complete'])
        self.assertFalse(any(row[0]=='strict_cleanup' for row in calls))

    def test_handler_restoration_failure_keeps_primary(self):
        primary=InterruptedError('owned command interrupted');secondary=RuntimeError('restore')
        result,error,_,_=self.invoke(work_error=primary,restore_error=secondary)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertIs(error.owned_command_cleanup_failure,secondary)
        self.assertFalse(error.owned_command_control['cleanup_complete'])
        self.assertTrue(error.owned_command_control['proof_available'])

    def test_mask_failure_keeps_primary(self):
        primary=InterruptedError('owned command interrupted');secondary=RuntimeError('mask')
        result,error,_,_=self.invoke(work_error=primary,mask_error=secondary)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertIs(error.owned_command_cleanup_failure,secondary)
        self.assertFalse(error.owned_command_control['cleanup_complete'])

    def test_epilogue_failure_alone_cannot_return_success(self):
        for option in ('protect_error','restore_error','mask_error'):
            with self.subTest(option=option):
                secondary=RuntimeError('epilogue')
                result,error,_,_=self.invoke(**{option:secondary})
                self.assertIsNone(result);self.assertIs(error,secondary)
                self.assertFalse(error.owned_command_control['cleanup_complete'])
                self.assertFalse(error.owned_command_control['downstream_work_permitted'])

    def test_proof_timer_failure_keeps_primary_and_blocks_success(self):
        primary=InterruptedError('owned command interrupted');secondary=RuntimeError('proof timer')
        result,error,_,_=self.invoke(work_error=primary,arm_error=secondary)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertIs(error.owned_command_cleanup_failure,secondary)
        self.assertFalse(error.owned_command_control['cleanup_complete'])

    def test_proof_timer_teardown_cannot_discard_deadline_into_success(self):
        result,error,_,_=self.invoke(teardown_expiry=True)
        self.assertIsNone(result);self.assertIs(type(error),TimeoutError)
        self.assertFalse(error.owned_command_control['cleanup_complete'])

    def test_late_handler_restore_keeps_primary_but_clears_completion(self):
        primary=InterruptedError('owned command interrupted')
        result,error,_,_=self.invoke(work_error=primary,restore_expiry=True)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertIs(type(error.owned_command_cleanup_failure),TimeoutError)
        self.assertFalse(error.owned_command_control['cleanup_complete'])
        self.assertTrue(error.owned_command_control['cleanup_failed'])

    def test_blocked_entry_alarm_rejected_before_spawn(self):
        result,error,calls,_=self.invoke(blocked_entry=True)
        self.assertIsNone(result);self.assertIs(type(error),ValueError)
        self.assertFalse(any(row[0]=='spawn' for row in calls))

    def test_blocked_proof_alarm_preserves_work_failure(self):
        primary=InterruptedError('owned command interrupted')
        result,error,calls,_=self.invoke(work_error=primary,blocked_proof=True)
        self.assertIsNone(result);self.assertIs(error,primary)
        self.assertFalse(error.owned_command_control['cleanup_complete'])
        self.assertFalse(any(row[0]=='proof_arm' for row in calls))

    def test_return_elapsed_uses_checked_final_timestamp(self):
        result,error,calls,_=self.invoke(final_clock_sequence=True)
        self.assertIsNone(error);self.assertEqual(result['elapsed_seconds'],19.0)
        self.assertEqual([row for row in calls if row[0]=='final_clock'],[('final_clock',1)])

    def test_both_active_cleanup_sites_validate_strict_not_legacy(self):
        launch_tree=ast.parse(LAUNCH.read_bytes())
        finish=next(n for n in launch_tree.body if isinstance(n,ast.FunctionDef) and n.name=='finish_owned')
        for node,prefix in ((RUN,'helper'),(finish,'control')):
            calls=[ast.unparse(n.func) for n in ast.walk(node) if isinstance(n,ast.Call)]
            self.assertIn(prefix+'.strict_cleanup.cleanup_owned',calls)
            self.assertIn(prefix+'.strict_cleanup.validate_cleanup_proof',calls)
            self.assertNotIn(prefix+'.cleanup_owned',calls)

    def test_source_loaders_bind_admitted_execution_buffer(self):
        load=next(n for n in RUN_TREE.body if isinstance(n,ast.FunctionDef) and n.name=='load_owner')
        self.assertIn("strict.__dict__['_ADMITTED_SOURCE_SHA256'] = STRICT_CLEANUP_SHA",ast.unparse(load))
        launch=ast.parse(LAUNCH.read_bytes())
        checked=next(n for n in launch.body if isinstance(n,ast.FunctionDef) and n.name=='load_checked')
        helper=next(n for n in launch.body if isinstance(n,ast.FunctionDef) and n.name=='helper')
        self.assertIn("module.__dict__['_ADMITTED_SOURCE_SHA256'] = expected",ast.unparse(checked))
        self.assertIn('bind_source=True',ast.unparse(helper))
        self.assertNotIn('module.cleanup_owned =',ast.unparse(helper))


class FinishBoundary(unittest.TestCase):
    def invoke(self,*,expired=False,read_expiry=False,invalid_proof=False,teardown_expiry=False,arm_error=None,blocked_alarm=False,blocked_proof=False):
        calls=[];now=[120.0 if expired else 100.0];blocked=[blocked_alarm]
        identity=dict(pid=42,ppid=7,group=42,start=9)
        owner={'process':SimpleNamespace(pid=42,returncode=None),'identity':identity}
        def remaining(stop):
            if now[0]>=stop:raise TimeoutError('absolute cleanup stop')
            return stop-now[0]
        def read(pid):
            calls.append(('identity',pid))
            if read_expiry:now[0]=120.0
            return identity
        def cleanup(owner,stop):
            calls.append(('strict',stop))
            blocked[0]=blocked_proof
            if now[0]>=stop:raise CleanupFailure('expired strict barrier')
            owner['process'].returncode=0
            proof={'strict':'fixture'};owner['strict_cleanup_proof']=proof
            return proof
        def validate(proof,**kwargs):
            calls.append(('validate',))
            if invalid_proof:raise CleanupFailure('proof rejected')
        def protect():
            calls.append(('protect',))
            if teardown_expiry and any(row[0]=='validate' for row in calls):now[0]=120.0
        def arm(stop):
            calls.append(('arm',stop))
            if arm_error is not None:raise arm_error
        strict=SimpleNamespace(cleanup_owned=cleanup,validate_cleanup_proof=validate)
        control=SimpleNamespace(protect_cleanup=protect,
            arm_receipt_deadline=arm,
            process_identity=read,observe_exit=lambda *args:0,strict_cleanup=strict)
        os=SimpleNamespace(P_PID=1,WEXITED=2,WNOHANG=4,WNOWAIT=8,
            waitid=lambda *args:calls.append(('waitid',)),getpid=lambda:7,getpgrp=lambda:5,
            killpg=lambda *args:calls.append(('signal',*args)))
        def need(value,reason):
            if not value:raise ValueError(reason)
        node=next(n for n in ast.parse(LAUNCH.read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name=='finish_owned')
        ns=dict(os=os,signal=SimpleNamespace(SIGTERM=15,SIGALRM=14,SIG_BLOCK=1,
            pthread_sigmask=lambda *args:{14} if blocked[0] else set()),need=need,remaining=remaining,
            time=SimpleNamespace(monotonic=lambda:now[0]))
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(LAUNCH),'exec'),ns)
        try:return ns['finish_owned'](control,owner,120.0,cancel=True),None,calls
        except BaseException as error:return None,error,calls

    def test_expired_entry_never_reads_identity_or_signals(self):
        result,error,calls=self.invoke(expired=True)
        self.assertIsNone(result);self.assertIs(type(error),TimeoutError)
        self.assertFalse(any(row[0] in ('identity','signal','waitid','arm') for row in calls))
        self.assertIn(('strict',120.0),calls)

    def test_identity_reads_are_after_original_stop_alarm(self):
        result,error,calls=self.invoke()
        self.assertIs(result,True);self.assertIsNone(error)
        self.assertLess(calls.index(('arm',120.0)),calls.index(('identity',42)))
        self.assertLess(calls.index(('strict',120.0)),calls.index(('validate',)))

    def test_expiry_during_identity_read_never_signals(self):
        result,error,calls=self.invoke(read_expiry=True)
        self.assertIsNone(result);self.assertIs(type(error),TimeoutError)
        self.assertFalse(any(row[0]=='signal' for row in calls))

    def test_boolean_completion_requires_valid_strict_proof(self):
        result,error,calls=self.invoke(invalid_proof=True)
        self.assertIsNone(result);self.assertIs(type(error),CleanupFailure)
        self.assertIn(('validate',),calls)


    def test_finish_proof_timer_teardown_checks_remaining_stop(self):
        result,error,calls=self.invoke(teardown_expiry=True)
        self.assertIsNone(result);self.assertIs(type(error),TimeoutError)

    def test_finish_timer_failure_cannot_qualify(self):
        primary=RuntimeError('timer fixture')
        result,error,calls=self.invoke(arm_error=primary)
        self.assertIsNone(result);self.assertIs(error,primary)


    def test_blocked_cancellation_alarm_skips_reads_and_signals(self):
        result,error,calls=self.invoke(blocked_alarm=True)
        self.assertIsNone(result);self.assertIs(type(error),ValueError)
        self.assertFalse(any(row[0] in ('identity','signal','waitid') for row in calls))
        self.assertIn(('strict',120.0),calls)

    def test_blocked_proof_alarm_cannot_return_completion(self):
        result,error,calls=self.invoke(blocked_proof=True)
        self.assertIsNone(result);self.assertIs(type(error),ValueError)
        self.assertFalse(any(row[0]=='validate' for row in calls))


if __name__=='__main__':unittest.main(verbosity=2)
