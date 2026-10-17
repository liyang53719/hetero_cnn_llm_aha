"""Deterministic tests; real process fixtures are explicitly opt-in separately."""
import copy
import hashlib
from pathlib import Path
import subprocess
import types
import unittest
from unittest import mock

SOURCE=Path(__file__).with_name('strict_cleanup.py')
BUFFER=SOURCE.read_bytes()
strict=types.ModuleType('strict_cleanup')
strict.__file__=str(SOURCE)
strict._ADMITTED_SOURCE_SHA256=hashlib.sha256(BUFFER).hexdigest()
exec(compile(BUFFER,str(SOURCE),'exec'),strict.__dict__)


def row(pid=100,start=1000,group=100,session=100,state='Z',ppid=10):
    return dict(pid=pid,ppid=ppid,group=group,start=start,session=session,state=state)


class Clock:
    def __init__(self):self.value=1.0
    def now(self):return self.value
    def sleep(self,value):self.value+=value


class Kernel:
    parent=10
    parent_group=10
    def __init__(self,clock,frames=None,code=-9):
        self.clock=clock;self.frames=frames if frames is not None else [[],[]]
        self.process=types.SimpleNamespace(pid=100,returncode=None)
        self.owner=dict(process=self.process,identity={k:row()[k] for k in strict.OWNER_KEYS})
        self.events=[];self.killed=False;self.index=0;self.code=code
        self.reap_timeout=False;self.scan_error=False;self.missing_leader=False
        self.incomplete_leader=False;self.peek_error=False;self.scan_delay=.001
        self.alarm_error=False;self.leader=row();self.armed=False
    def boot(self):return '12345678-1234-1234-1234-123456789abc'
    def read(self,pid):
        self.events.append(('read',pid,self.clock.now()));self.clock.value+=.000001
        return copy.deepcopy(self.leader) if pid==100 else None
    def peek(self,process):
        self.events.append(('peek',process.pid,self.clock.now()))
        if self.peek_error:raise ChildProcessError('not a waitable child')
        return types.SimpleNamespace(si_pid=100) if self.killed else None
    def kill_group(self,pid):
        self.events.append(('kill',pid,self.clock.now()));self.killed=True
    def arm(self,stop,now):
        self.events.append(('arm',stop,now()));self.armed=True
    def disarm(self):self.armed=False
    def scan(self,tracked,group,stop,now):
        self.events.append(('scan',group,now()))
        if self.alarm_error:
            self.clock.value=stop
            raise strict._Deadline('original cleanup deadline alarm')
        rows=copy.deepcopy(self.frames[min(self.index,len(self.frames)-1)]);self.index+=1
        started=now();self.clock.value+=self.scan_delay
        bypid={r['pid']:r for r in rows};bypid[100]=copy.deepcopy(self.leader)
        captured={str(pid):copy.deepcopy(bypid.get(pid)) for pid in tracked}
        if self.incomplete_leader:captured['100']=None
        members=[] if self.missing_leader else [copy.deepcopy(self.leader)]
        members += [r for r in rows if r['group']==group or r['pid'] in tracked]
        return dict(started=started,finished=now(),complete=not self.scan_error,
                    captured=captured,members=members,vanished=[],error='injected' if self.scan_error else None)
    def reap(self,process,timeout):
        self.events.append(('reap',timeout,self.clock.now()))
        if self.reap_timeout:raise subprocess.TimeoutExpired(['fixture'],timeout)
        process.returncode=self.code;return self.code


class StrictUnitTests(unittest.TestCase):
    def make(self,frames=None,code=-9):
        clock=Clock();return clock,Kernel(clock,frames,code)
    def run_cleanup(self,kernel,stop=2):
        return strict._cleanup(kernel.owner,stop,kernel,kernel.clock.now,kernel.clock.sleep)
    def failure(self,kernel,stop=2,pattern=None):
        with self.assertRaises(strict.CleanupFailure) as caught:self.run_cleanup(kernel,stop)
        self.assertFalse(caught.exception.evidence['cleanup_complete'])
        self.assertNotIn('strict_cleanup_proof',kernel.owner)
        if pattern:self.assertRegex(str(caught.exception),pattern)
        return caught.exception.evidence
    def test_source_requires_admitted_buffer_digest(self):
        with self.assertRaises(ImportError):exec(compile(BUFFER,str(SOURCE),'exec'),{'__file__':str(SOURCE)})
        self.assertEqual(strict.SOURCE_SHA256,hashlib.sha256(BUFFER).hexdigest())
    def test_stat_non_ascii_and_nested_command(self):
        fields=['Z','10','100','100']+['0']*15+['1000']+['0']*30
        parsed=strict.parse_stat(b'100 (odd )\xff (name)) '+(' '.join(fields)).encode())
        self.assertEqual(parsed,row())
    def test_stat_rejects_unknown_truncated_bad_numeric_and_oversize(self):
        fields=['Z','10','100','100']+['0']*15+['1000']+['0']*30
        good=b'100 (name) '+(' '.join(fields)).encode()
        for raw in (good.replace(b' Z ',b' ? '),good[:-100],good.replace(b' 1000 ',b' +1000 '),b'x'*4097,good.replace(b'100 (',b'0 (',1)):
            with self.subTest(raw=raw[:50]),self.assertRaises(strict._Invalid):strict.parse_stat(raw)
    def test_malformed_owner_is_typed_failure(self):
        c,k=self.make()
        for owner in (None,[],{},dict(process=None,identity=None)):
            with self.subTest(owner=owner),self.assertRaises(strict.CleanupFailure):strict._cleanup(owner,2,k,c.now,c.sleep)
    def test_invalid_deadline_is_typed_failure(self):
        for stop in (True,None,float('nan'),float('inf'),-1):
            c,k=self.make();self.failure(k,stop,'finite original absolute stop')
    def test_zero_nonzero_and_signal_status_cleanup_independent(self):
        for code in (0,7,-9):
            with self.subTest(code=code):
                c,k=self.make(code=code);proof=self.run_cleanup(k)
                self.assertEqual(proof['direct_exit_code'],code)
                self.assertIs(strict._validate_proof(proof,k.owner,2,10),proof)
                self.assertFalse(k.armed)
    def test_empty_group_requires_two_complete_scans_before_reap(self):
        c,k=self.make();proof=self.run_cleanup(k)
        events=[e[0] for e in k.events]
        self.assertEqual(events.count('scan'),2)
        self.assertLess(events.index('kill'),events.index('scan'))
        self.assertGreater(events.index('reap'),max(i for i,e in enumerate(events) if e=='scan'))
        self.assertEqual(events.count('kill'),1)
        self.assertLess(proof['completed_at'],2)
        self.assertFalse(proof['grandchildren_reaped_by_this_helper'])
    def test_all_live_states_block_then_disappear(self):
        for state in 'RSDTtIKWP':
            with self.subTest(state=state):
                c,k=self.make([[row(pid=101,start=1001,state=state)],[],[]])
                proof=self.run_cleanup(k);report=k.owner['strict_cleanup_observation']
                self.assertTrue(report['observed_live_nonleader']);self.assertEqual(k.index,3)
                self.assertLess(proof['barrier_at'],2)
    def test_defunct_states_block_until_disappeared(self):
        for state in 'ZXx':
            with self.subTest(state=state):
                c,k=self.make([[row(pid=101,start=1001,state=state)],[],[]]);self.run_cleanup(k)
                report=k.owner['strict_cleanup_observation']
                self.assertTrue(report['observed_dead_nonleader']);self.assertFalse(report['observed_live_nonleader'])
                self.assertEqual(k.index,3)
    def test_persistent_live_and_defunct_fail_at_original_stop(self):
        for state in 'RSDTtIZXx':
            with self.subTest(state=state):
                c,k=self.make([[row(pid=101,start=1001,state=state)]])
                report=self.failure(k,1.05,'deadline')
                self.assertEqual(c.now(),1.05)
                self.assertTrue(report['scans'][0]['nonleader_present'])
    def test_scan_failure_cannot_suppress_safety_kill(self):
        c,k=self.make();k.scan_error=True;report=self.failure(k,pattern='incomplete')
        events=[e[0] for e in k.events]
        self.assertEqual(len(report['signals']),1);self.assertLess(events.index('kill'),events.index('scan'))
    def test_expired_entry_no_signal_no_scan_and_no_grace(self):
        c,k=self.make();report=self.failure(k,1,'deadline')
        self.assertEqual(len(report['signals']),0);self.assertEqual(k.index,0);self.assertEqual(c.now(),1)
        self.assertTrue(all(e[1]==0 for e in k.events if e[0]=='reap'))
    def test_alarm_expiry_is_cleanup_failure(self):
        c,k=self.make();k.alarm_error=True;report=self.failure(k,1.1,'alarm')
        self.assertEqual(c.now(),1.1);self.assertFalse(k.armed)
        self.assertTrue(all(e[1]==0 for e in k.events if e[0]=='reap'))
    def test_scan_crossing_stop_fails(self):
        c,k=self.make();k.scan_delay=.5;self.failure(k,1.25,'deadline')
    def test_missing_leader_independent_read_fails(self):
        c,k=self.make();k.incomplete_leader=True;self.failure(k,pattern='identity')
    def test_missing_leader_full_enumeration_fails(self):
        c,k=self.make();k.missing_leader=True;self.failure(k,pattern='missing from full enumeration')
    def test_original_identity_group_and_session_escape_fail(self):
        for changed in (dict(group=101),dict(session=101)):
            c,k=self.make([[row(pid=101,start=1001,state='S')],[row(pid=101,start=1001,state='S',**changed)]])
            self.failure(k,pattern='escaped')
    def test_same_pid_new_start_same_original_group_fails(self):
        c,k=self.make([[row(pid=101,start=1001)],[row(pid=101,start=1002)]])
        self.failure(k,pattern='reused tracked PID still in original group')
    def test_same_pid_new_start_unrelated_group_marks_old_absent(self):
        c,k=self.make([[row(pid=101,start=1001)],[row(pid=101,start=1002,group=200,session=200)]])
        self.run_cleanup(k)
        self.assertIn('identity_reused_unrelated',[r['classification'] for r in k.owner['strict_cleanup_observation']['scans'][-1]['identities']])
    def test_new_member_not_previously_tracked_blocks(self):
        c,k=self.make([[],[row(pid=102,start=1003)],[],[]]);self.run_cleanup(k)
        self.assertEqual(k.index,4)
    def test_member_older_than_leader_is_ambiguous(self):
        c,k=self.make([[row(pid=101,start=999)]]);self.failure(k,pattern='ambiguous')
    def test_group_member_wrong_session_is_ambiguous(self):
        c,k=self.make([[row(pid=101,start=1001,session=200)]]);self.failure(k,pattern='ambiguous')
    def test_unknown_member_state_fails(self):
        c,k=self.make([[row(pid=101,start=1001,state='?')]]);self.failure(k,pattern='identity fields')
    def test_reaped_owner_never_authorizes_signal(self):
        c,k=self.make();k.process.returncode=0;self.failure(k,pattern='unreaped')
        self.assertFalse(any(e[0]=='kill' for e in k.events))
    def test_not_waitable_owner_never_authorizes_signal(self):
        c,k=self.make();k.peek_error=True;self.failure(k,pattern='not a waitable')
        self.assertFalse(any(e[0]=='kill' for e in k.events))
    def test_changed_leader_identity_never_authorizes_signal(self):
        c,k=self.make();k.leader['start']+=1;self.failure(k,pattern='exact retained')
        self.assertFalse(any(e[0]=='kill' for e in k.events))
    def test_failed_reap_retains_exact_handle_and_never_resignals(self):
        c,k=self.make();k.reap_timeout=True;report=self.failure(k,pattern='timed out')
        self.assertTrue(report['direct_handle_retained_for_supervisor']);self.assertIs(k.owner['process'],k.process)
        self.assertEqual(sum(e[0]=='kill' for e in k.events),1)
    def test_no_signal_after_reap_even_proof_fails(self):
        c,k=self.make()
        with mock.patch.object(strict,'_validate_proof',side_effect=strict._Invalid('injected proof failure')):
            report=self.failure(k,pattern='injected proof')
        self.assertTrue(report['leader_reaped']);self.assertTrue(report['authority_released'])
        events=[e[0] for e in k.events];self.assertNotIn('kill',events[events.index('reap')+1:])
    def test_proof_shape_source_owner_stop_parent_and_order_negatives(self):
        for key,value in (('schema',True),('status','truthy'),('source_sha256','0'*64),('parent_pid',11),
                          ('session',True),('stop',3),('barrier_at',1.5),('reaped_at',1.0),
                          ('empty_complete_scans',True),('direct_exit_code',True),
                          ('grandchildren_reaped_by_this_helper',True),('boot_id','x'*36),
                          ('no_nonleader_identities_at_barrier',1),('scan_evidence_sha256','0'*64)):
            with self.subTest(key=key):
                c,k=self.make();proof=self.run_cleanup(k);proof[key]=value;k.owner['strict_cleanup_seal']=strict._sha(proof)
                with self.assertRaises(strict._Invalid):strict._validate_proof(proof,k.owner,2,10)
        c,k=self.make();proof=self.run_cleanup(k);proof['extra']=1;k.owner['strict_cleanup_seal']=strict._sha(proof)
        with self.assertRaises(strict._Invalid):strict._validate_proof(proof,k.owner,2,10)
    def test_proof_copy_and_unsealed_mutation_rejected(self):
        c,k=self.make();proof=self.run_cleanup(k)
        with self.assertRaises(strict._Invalid):strict._validate_proof(copy.deepcopy(proof),k.owner,2,10)
        proof['direct_exit_code']=0
        with self.assertRaises(strict._Invalid):strict._validate_proof(proof,k.owner,2,10)
    def test_proof_original_stop_and_owner_binding(self):
        c,k=self.make();proof=self.run_cleanup(k)
        with self.assertRaises(strict._Invalid):strict._validate_proof(proof,k.owner,3,10)
        k.owner['identity']['start']+=1
        with self.assertRaises(strict._Invalid):strict._validate_proof(proof,k.owner,2,10)
    def test_complete_scan_evidence_mutation_fails(self):
        c,k=self.make();proof=self.run_cleanup(k)
        k.owner['strict_cleanup_observation']['scans'][-1]['complete']=False
        with self.assertRaises(strict._Invalid):strict._validate_proof(proof,k.owner,2,10)
    def test_public_validator_converts_invalid_proof_to_typed_failure(self):
        with self.assertRaises(strict.CleanupFailure):strict.validate_cleanup_proof({},owner={},stop=2)
    def test_arm_error_has_no_fresh_identity_reads_or_group_signal(self):
        c,k=self.make()
        with mock.patch.object(k,'arm',side_effect=RuntimeError('injected arm failure')):
            report=self.failure(k,pattern='injected arm failure')
        self.assertFalse(any(event[0] in ('read','peek','kill','scan') for event in k.events))
        self.assertEqual(report['containment_signal_skipped'],'cleanup_alarm_not_established')
        self.assertFalse(report['cleanup_complete'])
    def test_disarm_error_is_typed_failure_clears_proof_and_success(self):
        c,k=self.make()
        with mock.patch.object(k,'disarm',side_effect=RuntimeError('injected disarm failure')):
            report=self.failure(k,pattern='injected disarm failure')
        self.assertTrue(report['leader_reaped']);self.assertTrue(report['authority_released'])
        self.assertIn('alarm_finalization_error',report)
    def test_disarm_crossing_original_stop_cannot_publish_proof(self):
        c,k=self.make()
        def disarm():c.value=2;k.armed=False
        with mock.patch.object(k,'disarm',side_effect=disarm):report=self.failure(k,pattern='after alarm finalization')
        self.assertTrue(report['leader_reaped']);self.assertNotIn('proof',report)
    def test_cumulative_record_budget_exhaustion_fails_closed(self):
        c,k=self.make()
        with mock.patch.object(strict,'MAX_EVIDENCE_RECORDS',7):report=self.failure(k,pattern='evidence budget')
        self.assertLessEqual(report['evidence_records'],7);self.assertTrue(report['evidence_budget_exhausted'])
        self.assertEqual(len(report['scans']),1)
    def test_cumulative_byte_budget_exhaustion_fails_closed(self):
        c,k=self.make()
        with mock.patch.object(strict,'MAX_EVIDENCE_BYTES',1):report=self.failure(k,pattern='evidence budget')
        self.assertEqual(report['evidence_bytes'],0);self.assertTrue(report['evidence_budget_exhausted'])
    def test_resealed_scan_time_shape_signal_order_and_finite_negatives(self):
        for position,key,value in ((0,'started',0),(0,'finished',float('inf')),
                                   (0,'finished',.5),(1,'started',.5),(1,'finished',1.9)):
            with self.subTest(position=position,key=key,value=value):
                c,k=self.make();proof=self.run_cleanup(k);scans=k.owner['strict_cleanup_observation']['scans'][-2:]
                scans[position][key]=value
                proof['complete_scan_bounds']=[[scan['started'],scan['finished']] for scan in scans]
                if value==float('inf'):
                    # JSON sealing itself must reject non-finite evidence.
                    with self.assertRaises(ValueError):strict._sha(scans)
                    continue
                proof['scan_evidence_sha256']=strict._sha(scans);k.owner['strict_cleanup_seal']=strict._sha(proof)
                with self.assertRaises(strict._Invalid):strict._validate_proof(proof,k.owner,2,10)
    def signal_mock(self,pending=False):
        events=[];state={'mask':set(),'pending':{strict.signal.SIGALRM} if pending else set()}
        def mask(how,values):
            old=set(state['mask']);events.append(('mask',how,set(values)))
            state['mask']=state['mask']|set(values) if how==strict.signal.SIG_BLOCK else set(values)
            return old
        def timer(which,value):events.append(('timer',value));return (0.0,0.0)
        def handler(signum,value):events.append(('handler',value));return strict.signal.SIG_IGN
        def consume(signals,timeout):events.append(('consume',timeout));state['pending']=set()
        patches=mock.patch.multiple(strict.signal,getitimer=mock.Mock(return_value=(0.0,0.0)),
            getsignal=mock.Mock(return_value=strict.signal.SIG_IGN),pthread_sigmask=mask,
            setitimer=timer,signal=handler,sigpending=lambda:set(state['pending']),sigtimedwait=consume)
        return events,state,patches
    def test_alarm_arm_disarm_mask_order_and_no_timer_revival(self):
        events,state,patches=self.signal_mock();api=strict._Linux()
        with patches:
            api.arm(2,lambda:1);api.disarm()
        self.assertEqual(events[0],('mask',strict.signal.SIG_BLOCK,{strict.signal.SIGALRM}))
        self.assertEqual([item[1] for item in events if item[0]=='timer'],[1,0])
        self.assertFalse(state['mask']);self.assertFalse(api.alarm_installed)
    def test_pending_alarm_finalization_consumed_and_rejected_with_restored_mask(self):
        events,state,patches=self.signal_mock();api=strict._Linux()
        with patches:
            api.arm(2,lambda:1);state['pending']={strict.signal.SIGALRM}
            with self.assertRaisesRegex(strict._Invalid,'pending original deadline'):api.disarm()
        self.assertIn(('consume',0),events);self.assertFalse(state['pending']);self.assertFalse(state['mask'])
    def test_preexisting_pending_alarm_rejected_and_restored(self):
        events,state,patches=self.signal_mock(pending=True);api=strict._Linux()
        with patches:
            with self.assertRaisesRegex(strict._Invalid,'preexisting pending'):api.arm(2,lambda:1)
            with self.assertRaises(strict._Invalid):api.disarm()
        self.assertFalse(state['mask']);self.assertFalse(api.alarm_installed)
    def test_no_assert_statements_in_production_source(self):
        import ast
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(BUFFER))))


if __name__=='__main__':unittest.main(verbosity=2)
