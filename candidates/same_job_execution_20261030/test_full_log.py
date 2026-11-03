"""Synthetic host-only streaming tests. No hardware or numerical PASS evidence."""
import hashlib
import importlib.util
import json
import os
import pathlib
import resource
import signal
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

D=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(D/'numeric'))
import full_log as m
import summary_progress as progress
from test_progress import line


def fixture(log, raw, value=None):
    value=value or dict(m.POLICY)
    archive, receipt=m.paths(log)
    writer=m.Writer(archive,value)
    for off in range(0,len(raw),m.CHUNK):writer.write(raw[off:off+m.CHUNK])
    writer.finish();writer.close()
    body=dict(schema=m.SCHEMA,policy=value,pid=123,consumer_pid=122,native_exit=0,termination_reason='NATIVE_EXIT',errors=[],pipe_eof_observed=True,gzip_finalized=True,raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),gzip_bytes=archive.stat().st_size,gzip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),raw_crc32=f'{zlib.crc32(raw):08x}',retained_read_bytes=len(raw),pipe_read_bytes=len(raw),pipe_read_sha256=hashlib.sha256(raw).hexdigest(),complete=True)
    receipt.write_text(json.dumps(body))
    return body


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.log=self.root/'profile0.log'
    def tearDown(self):self.temp.cleanup()
    def run_pipe(self,code,value=None,wall=10):
        p=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0,start_new_session=True)
        try:return m.capture(p,self.log,value or dict(m.POLICY),wall)
        finally:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    def decode(self,body,complete=True):return b''.join(m.chunks(self.log,body,require_complete=complete))
    def mutate(self,body,data):
        archive,receipt=m.paths(self.log);archive.write_bytes(data)
        body=dict(body,gzip_bytes=len(data),gzip_sha256=hashlib.sha256(data).hexdigest());receipt.write_text(json.dumps(body));return body
    def test_effective_policy_requires_per_profile_review(self):
        admission=dict(mode='FULL_BLOCK_ACCEPTANCE',budget_version=2,log_policy=m.POLICY,profile_log_raw_bytes={'0':96<<20})
        self.assertEqual(m.effective_policy(admission,0,64<<20)['raw_bytes'],96<<20)
        for change in ({'budget_version':1},{'mode':'BOUNDED_CALIBRATION'},{'profile_log_raw_bytes':{'0':True}},{'profile_log_raw_bytes':{'0':(16<<30)+1}},{'profile_log_raw_bytes':{}}):
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):m.effective_policy(dict(admission,**change),0,64<<20)
    def test_deterministic_single_member_round_trip(self):
        raw=bytes(range(256))*1000;body=fixture(self.log,raw)
        self.assertEqual(self.decode(body),raw)
        second=self.root/'other.log';fixture(second,raw)
        self.assertEqual(m.paths(self.log)[0].read_bytes(),m.paths(second)[0].read_bytes())
    def test_actual_native_zero_preserves_stdout_and_stderr(self):
        body=self.run_pipe("import os;os.write(1,b'out\\n');os.write(2,b'err\\n')")
        self.assertEqual(self.decode(body),b'out\nerr\n');self.assertTrue(body['complete']);self.assertEqual(body['native_exit'],0)
    def test_actual_native_failure_not_timeout(self):
        body=self.run_pipe("import os;os.write(1,b'resetRequired\\n');os._exit(2)")
        self.assertEqual(self.decode(body),b'resetRequired\n');self.assertEqual(body['native_exit'],2);self.assertEqual(body['termination_reason'],'NATIVE_EXIT')
    def test_actual_signal_preserved(self):
        body=self.run_pipe("import os,signal;os.write(1,b'before\\n');os.kill(os.getpid(),signal.SIGTERM)")
        self.assertEqual(body['native_exit'],-signal.SIGTERM);self.assertTrue(body['complete']);self.assertEqual(self.decode(body),b'before\n')
    def test_actual_timeout_keeps_bytes_and_native_kill(self):
        body=self.run_pipe("import os,time;os.write(1,b'before\\n');time.sleep(30)",wall=1)
        self.assertEqual(body['termination_reason'],'WALL_TIMEOUT');self.assertEqual(body['native_exit'],-signal.SIGKILL);self.assertFalse(body['complete']);self.assertTrue(body['pipe_eof_observed'])
        self.assertEqual(self.decode(body,False),b'before\n')
        with self.assertRaises(ValueError):self.decode(body)
    def test_actual_raw_cap_never_discards_read_bytes(self):
        value=dict(m.POLICY,raw_bytes=128<<10)
        body=self.run_pipe("import os;data=os.urandom(65536)\nwhile True:os.write(1,data)",value)
        self.assertEqual(body['termination_reason'],'LOG_LIMIT');self.assertFalse(body['complete']);self.assertLessEqual(body['raw_bytes'],value['raw_bytes'])
        self.assertEqual(body['pipe_read_bytes'],body['retained_read_bytes']);self.assertEqual(body['pipe_read_sha256'],body['raw_sha256']);self.assertEqual(len(self.decode(body,False)),body['raw_bytes'])
    def test_exact_raw_cap_native_zero_observes_eof(self):
        body=self.run_pipe("import os;os.write(1,b'exact');os._exit(0)",dict(m.POLICY,raw_bytes=5))
        self.assertTrue(body['complete']);self.assertEqual(body['native_exit'],0);self.assertEqual(self.decode(body),b'exact')
    def test_exact_raw_cap_waits_for_native_exit_and_timeout(self):
        body=self.run_pipe("import os,time;os.write(1,b'exact');time.sleep(30)",dict(m.POLICY,raw_bytes=5),wall=1)
        self.assertFalse(body['complete']);self.assertEqual(body['termination_reason'],'WALL_TIMEOUT');self.assertTrue(body['pipe_eof_observed']);self.assertEqual(self.decode(body,False),b'exact')
    def test_actual_compressed_cap_never_discards_read_bytes(self):
        value=dict(m.POLICY,compressed_bytes=32768)
        body=self.run_pipe("import os\nwhile True:os.write(1,os.urandom(8192))",value)
        self.assertEqual(body['termination_reason'],'LOG_LIMIT');self.assertLessEqual(body['gzip_bytes'],32768)
        self.assertEqual(body['pipe_read_bytes'],body['retained_read_bytes']);self.assertEqual(len(self.decode(body,False)),body['raw_bytes'])
    def test_descendant_retained_pipe_fails_closed(self):
        body=self.run_pipe("import os,time\nif os.fork()==0:time.sleep(30)\nelse:os.write(1,b'parent\\n');os._exit(0)")
        self.assertEqual(body['native_exit'],0);self.assertEqual(body['termination_reason'],'PIPE_EOF_TIMEOUT');self.assertFalse(body['pipe_eof_observed']);self.assertFalse(body['complete']);self.assertEqual(self.decode(body,False),b'parent\n')
    def test_late_descendant_bytes_are_not_dropped(self):
        body=self.run_pipe("import os,time\nif os.fork()==0:time.sleep(.1);os.write(1,b'late\\n');os._exit(0)\nelse:os.write(1,b'parent\\n');os._exit(0)")
        self.assertEqual(self.decode(body),b'parent\nlate\n')
    def test_storage_failure_records_consumed_vs_retained(self):
        original=m.Writer.write
        def broken(writer,data):raise OSError('synthetic write failure')
        with patch.object(m.Writer,'write',broken),self.assertRaises(OSError):self.run_pipe("import os;os.write(1,b'not silently retained\\n')")
        body=json.loads(m.paths(self.log)[1].read_text());self.assertFalse(body['complete']);self.assertEqual(body['termination_reason'],'CAPTURE_ERROR');self.assertGreater(body['pipe_read_bytes'],body['retained_read_bytes'])
    def test_partial_disk_write_is_never_complete(self):
        original=m.Writer._write
        def partial(writer,data):
            if writer.raw_bytes==0 and not getattr(writer,'injected',False):
                writer.injected=True;writer.file.write(data[:7]);raise OSError('synthetic partial disk write')
            return original(writer,data)
        with patch.object(m.Writer,'_write',partial),self.assertRaises(OSError):self.run_pipe("import os;os.write(1,b'partial write evidence\\n')")
        body=json.loads(m.paths(self.log)[1].read_text());self.assertFalse(body['complete']);self.assertGreater(body['pipe_read_bytes'],body['retained_read_bytes'])
        with self.assertRaises(ValueError):self.decode(body,False)
    def test_consumer_spawn_failure_restores_memory_and_keeps_empty_gzip(self):
        import consumer_owned as consumer
        import types
        runtime=self.root/'runtime';runtime.write_bytes(b'not executed')
        restored=[]
        limits=dict(address_space_bytes=128<<20,cpu_seconds=10,file_bytes=64<<20,max_active_cycles=100,wall_seconds=5)
        with patch.object(consumer,'FULL_LOG_POLICY',dict(m.POLICY)),patch.object(consumer,'CLOUD_MEMORY',types.SimpleNamespace(after_popen=lambda:restored.append(True))),patch.object(consumer,'runtime_abi_module',return_value=types.SimpleNamespace(clean_env=lambda:{})),patch.object(consumer.subprocess,'Popen',side_effect=OSError('synthetic spawn failure')):
            with self.assertRaises(OSError):consumer.execute_streaming(pathlib.Path(sys.executable),runtime,self.root/'output',self.log,limits)
        self.assertEqual(restored,[True]);self.assertFalse(self.log.with_suffix('.started.json').exists());self.assertFalse(m.paths(self.log)[1].exists());self.assertEqual(zlib.decompress(m.paths(self.log)[0].read_bytes(),31),b'')
    def test_truncated_corrupt_appended_and_multi_member_rejected(self):
        body=fixture(self.log,b'real\n');raw=m.paths(self.log)[0].read_bytes()
        cases=(raw[:-1],raw[:-8],raw[:8],bytes([raw[0]^1])+raw[1:],raw[:-8]+bytes([raw[-8]^1])+raw[-7:],raw+b'\0',raw+b'junk',raw+raw)
        for data in cases:
            with self.subTest(length=len(data)):
                changed=self.mutate(body,data)
                with self.assertRaises(ValueError):self.decode(changed)
    def test_raw_hash_count_crc_and_gzip_hash_each_bound(self):
        original=fixture(self.log,b'hello\n')
        for key,value in (('raw_sha256','a'*64),('raw_bytes',5),('raw_crc32','00000000'),('gzip_sha256','b'*64),('gzip_bytes',1)):
            changed=dict(original,**{key:value});m.paths(self.log)[1].write_text(json.dumps(changed))
            with self.subTest(key=key),self.assertRaises(ValueError):self.decode(changed)
    def test_excess_decompressed_payload_rejected(self):
        body=fixture(self.log,b'x'*100000)
        body['policy']=dict(body['policy'],raw_bytes=1000);body.update(raw_bytes=1000,retained_read_bytes=1000,pipe_read_bytes=1000)
        m.paths(self.log)[1].write_text(json.dumps(body))
        with self.assertRaises(ValueError):self.decode(body)
    def test_decompression_cpu_bound(self):
        body=fixture(self.log,b'hello\n')
        with patch.object(m.time,'process_time',side_effect=(0,m.READ_CPU_SECONDS+1)),self.assertRaises(ValueError):self.decode(body)
    def test_symlink_archive_or_parent_rejected(self):
        body=fixture(self.log,b'hello\n');archive,_=m.paths(self.log);target=self.root/'actual';archive.rename(target);archive.symlink_to(target)
        with self.assertRaises(ValueError):self.decode(body)
    def test_change_during_stream_rejected(self):
        body=fixture(self.log,b'x\n'*100000);stream=m.chunks(self.log,body);next(stream)
        archive,_=m.paths(self.log)
        with archive.open('ab') as f:f.write(b'junk')
        with self.assertRaises(ValueError):list(stream)
    def test_changed_receipt_rejected(self):
        body=fixture(self.log,b'hello\n');changed=dict(body,native_exit=2);m.paths(self.log)[1].write_text(json.dumps(changed))
        with self.assertRaises(ValueError):self.decode(body)
    def test_bounded_lines_and_invalid_unicode_rejected(self):
        for data in (b'x'*8193+b'\n',b'x'*8193,b'\xff\n'):
            with self.subTest(data=data[:4]):
                for p in m.paths(self.log):
                    if p.exists():p.unlink()
                body=fixture(self.log,data)
                with self.assertRaises((ValueError,UnicodeError)):m.LogView(self.log,body).verify()
    def test_marker_counts_match_legacy_text(self):
        text='noise\r\nMARK test\nMARK MARK\nHOST_ROUTER_RAW_SCORE_V1 one\n'
        body=fixture(self.log,text.encode());view=m.LogView(self.log,body).verify()
        self.assertEqual(view.count('MARK'),text.count('MARK'));self.assertEqual(list(view.splitlines()),text.splitlines())
        with self.assertRaises(ValueError):view.count('MARK\n')
    def test_malformed_progress_and_nonmonotonic_rejected(self):
        for raw in (line()[:-1],line()+line(0),line().replace(b'pc=0',b'pc=bad'),line().replace(b'pc=0',b'cycles=1')):
            for p in m.paths(self.log):
                if p.exists():p.unlink()
            body=fixture(self.log,raw)
            with self.assertRaises(ValueError):progress.parse_log(self.log,self.root,body)
    def test_reset_and_native_classification_preserved(self):
        raw=line(0,'reset')+line(10,'terminal').replace(b'reset_required=0',b'reset_required=1');body=fixture(self.log,raw)
        body['native_exit']=2;m.paths(self.log)[1].write_text(json.dumps(body))
        row=progress.parse_log(self.log,self.root,body);self.assertEqual(row['process_classification'],'RESET_REQUIRED');self.assertEqual(row['native_dut_exit'],2)
    def test_timeout_does_not_masquerade_as_reset_or_native_success(self):
        body=fixture(self.log,line(10));body.update(native_exit=-9,termination_reason='WALL_TIMEOUT',complete=False);m.paths(self.log)[1].write_text(json.dumps(body))
        row=progress.parse_log(self.log,self.root,body);self.assertEqual(row['process_classification'],'TIMEOUT_INCOMPLETE');self.assertFalse(row['log_complete'])
    def test_actual_consumer_execute_streaming_receipt_join(self):
        runtime=self.root/'runtime.py';runtime.write_text("import os;os.write(1,b'COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=0 ok\\n')\n")
        script=r"""
import json,os,pathlib,sys,types
sys.path.insert(0,sys.argv[1]);import consumer_owned as c
c.runtime_abi_module=lambda:types.SimpleNamespace(clean_env=lambda:dict(os.environ))
c.FULL_LOG_POLICY=dict(c.full_log_module().POLICY)
binary=pathlib.Path(sys.executable);runtime=pathlib.Path(sys.argv[2]);log=pathlib.Path(sys.argv[3])
rc=c.execute_streaming(binary,runtime,log.parent/'output',log,dict(address_space_bytes=128<<20,cpu_seconds=10,file_bytes=64<<20,max_active_cycles=100,wall_seconds=5))
started=c.verify_current_observation_round(log,binary,runtime);capture=c.full_log_module().read_capture(log)
if started['pid']!=capture['pid'] or capture['consumer_pid']!=os.getpid():raise RuntimeError('process round join')
print(json.dumps(dict(rc=rc,capture=capture)))
"""
        cp=subprocess.run([sys.executable,'-c',script,str(D/'numeric'),str(runtime),str(self.log)],capture_output=True,text=True,start_new_session=True,timeout=15)
        self.assertEqual(cp.returncode,0,cp.stderr);body=json.loads(cp.stdout);self.assertEqual(body['rc'],0);self.assertEqual(self.decode(body['capture']),b'COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=0 ok\n')
    def test_production_full_log_evidence_join_and_rejections(self):
        import dut_evidence as evidence
        body=fixture(self.log,b'whole log\n')
        report=dict(candidate_scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL',execution_admission=dict(budget_version=2,execution_mode='FULL_BLOCK_ACCEPTANCE',log_policy=body['policy']))
        row=dict(exit_code=0,log_capture=body);start=dict(pid=123,consumer_pid=122)
        self.assertEqual(evidence.verified_full_log(self.root,0,report,row,start,body['policy']),body)
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,report,row,start)
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,dict(report,execution_admission={}),row,start,body['policy'])
        for changed in (dict(row,exit_code=2),dict(row,log_capture=dict(body,raw_sha256='a'*64))):
            with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,report,changed,start,body['policy'])
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,report,row,dict(start,pid=124),body['policy'])
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,{},row,start)
        self.assertIsNone(evidence.verified_full_log(self.root,0,{},dict(exit_code=0),start))
    def test_production_timeout_evidence_requires_timeout_class(self):
        import dut_evidence as evidence
        body=fixture(self.log,b'before timeout\n');body.update(native_exit=-9,termination_reason='WALL_TIMEOUT',complete=False);m.paths(self.log)[1].write_text(json.dumps(body))
        report=dict(candidate_scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL',execution_admission=dict(budget_version=2,execution_mode='FULL_BLOCK_ACCEPTANCE',log_policy=body['policy']))
        row=dict(log_capture=body,error_class='TimeoutError');start=dict(pid=123,consumer_pid=122)
        self.assertEqual(evidence.verified_full_log(self.root,0,report,row,start,body['policy']),body)
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,report,row,start)
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,dict(report,execution_admission={}),row,start,body['policy'])
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,report,dict(row,error_class='ValueError'),start,body['policy'])
        with self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,report,dict(row,execution_evidence={'unique_clean_terminal':True}),start,body['policy'])
    def test_unique_moe_marker_scan_retains_at_most_first_line(self):
        import moe_score_compare as moe
        class InfiniteMarkers:
            def splitlines(self):
                yield 'HOST_ROUTER_RAW_SCORE_V1 first'
                yield 'HOST_ROUTER_RAW_SCORE_V1 second'
                raise RuntimeError('must reject before reading third')
        with self.assertRaisesRegex(ValueError,'unique'):moe.unique_marker_line(InfiniteMarkers(),'HOST_ROUTER_RAW_SCORE_V1','unique')
        self.assertEqual(moe.unique_marker_line('noise\nHOST_ROUTER_SELECTED_SCORE_V2 one\n','HOST_ROUTER_SELECTED_SCORE_V2','unique'),'HOST_ROUTER_SELECTED_SCORE_V2 one')
        with self.assertRaises(ValueError):moe.unique_marker_line('none','HOST_ROUTER_SELECTED_SCORE_V2','unique')
    def test_verified_marker_index_uses_one_pass_and_exact_counts(self):
        import moe_score_compare as moe
        text='noise\r\nAAA AAA\nHOST_ROUTER_RAW_SCORE_V1 one\nCOMPLETE profile=0 ok\n'
        body=fixture(self.log,text.encode())
        with patch.object(m,'chunks',wraps=m.chunks) as stream:
            view=m.LogView(self.log,body,['AAA','COMPLETE profile=0 '],['HOST_ROUTER_RAW_SCORE_V1','COMPLETE profile=0 ']).verify()
            self.assertEqual(view.count('AAA'),text.count('AAA'));self.assertEqual(view.count_prefix('COMPLETE profile=0 '),1)
            self.assertEqual(moe.unique_marker_line(view,'HOST_ROUTER_RAW_SCORE_V1','unique'),'HOST_ROUTER_RAW_SCORE_V1 one')
            self.assertEqual(stream.call_count,1)
        with self.assertRaises(ValueError):view.count('undeclared')
        with self.assertRaises(ValueError):m.LogView(self.log,body,['AAA']).count('AAA')
    def test_index_duplicate_markers_and_corrupt_tail_never_pass(self):
        import moe_score_compare as moe
        body=fixture(self.log,b'HOST_ROUTER_RAW_SCORE_V1 one\n'*10)
        view=m.LogView(self.log,body,[],['HOST_ROUTER_RAW_SCORE_V1']).verify()
        self.assertEqual(view.count_prefix('HOST_ROUTER_RAW_SCORE_V1'),10);self.assertEqual(len(view.first_lines),1)
        with self.assertRaises(ValueError):moe.unique_marker_line(view,'HOST_ROUTER_RAW_SCORE_V1','unique')
        body=self.mutate(body,m.paths(self.log)[0].read_bytes()[:-1]);view=m.LogView(self.log,body,['HOST_ROUTER_RAW_SCORE_V1'])
        with self.assertRaises(ValueError):view.verify()
        with self.assertRaises(ValueError):view.count('HOST_ROUTER_RAW_SCORE_V1')
    def test_postprocess_wall_and_cpu_watchdogs_restore_timers(self):
        import time
        for kind in ('wall','CPU'):
            budget=m.PostprocessBudget(dict(wall_seconds=3 if kind=='CPU' else 1,cpu_seconds=1)).start()
            try:
                with self.assertRaisesRegex(m.PostprocessBudgetExceeded,kind):
                    if kind=='wall':time.sleep(2)
                    else:
                        while True:sum(range(10000))
            finally:observed=budget.stop()
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.));self.assertGreater(observed['wall_seconds'],0);self.assertTrue(observed['budget_exceeded'])
        for bad in ({'wall_seconds':1,'cpu_seconds':2},{'wall_seconds':True,'cpu_seconds':1},{'wall_seconds':3601,'cpu_seconds':1}):
            with self.assertRaises(ValueError):m.PostprocessBudget(bad)
    def test_pending_or_unhandled_budget_expiration_remains_failure(self):
        budget=m.PostprocessBudget(dict(wall_seconds=3,cpu_seconds=3)).start()
        with patch.object(m.time,'monotonic',return_value=budget.started+4):observed=budget.stop()
        self.assertTrue(observed['budget_exceeded']);self.assertFalse(issubclass(m.PostprocessBudgetExceeded,ValueError))
    def test_postprocess_rejects_blocked_and_preserves_pending_signals(self):
        signals={signal.SIGALRM,signal.SIGPROF};mask=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
        try:
            with self.assertRaisesRegex(ValueError,'unblocked'):m.PostprocessBudget(dict(wall_seconds=1,cpu_seconds=1)).start()
            os.kill(os.getpid(),signal.SIGALRM)
            with self.assertRaises(ValueError):m.PostprocessBudget(dict(wall_seconds=1,cpu_seconds=1)).start()
            self.assertIn(signal.SIGALRM,signal.sigpending());signal.sigtimedwait({signal.SIGALRM},0)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,mask)
    def test_postprocess_rejects_foreign_timer_without_cancelling(self):
        old=signal.getsignal(signal.SIGALRM);signal.signal(signal.SIGALRM,lambda *a:None);signal.setitimer(signal.ITIMER_REAL,20)
        try:
            with self.assertRaisesRegex(ValueError,'unused host watchdog timers'):m.PostprocessBudget(dict(wall_seconds=1,cpu_seconds=1)).start()
            remaining,interval=signal.getitimer(signal.ITIMER_REAL);self.assertTrue(0<remaining<=20);self.assertEqual(interval,0)
        finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    def test_postprocess_drains_owned_late_blocked_expiry(self):
        import time
        signals={signal.SIGALRM,signal.SIGPROF};old={s:signal.getsignal(s)for s in signals};seen=[]
        try:
            for s in signals:signal.signal(s,lambda *a:seen.append(True))
            budget=m.PostprocessBudget(dict(wall_seconds=1,cpu_seconds=1)).start()
            signal.pthread_sigmask(signal.SIG_BLOCK,signals);time.sleep(1.1);observed=budget.stop()
            self.assertTrue(observed['budget_exceeded']);self.assertEqual(seen,[]);self.assertFalse(signals.intersection(signal.sigpending()));self.assertFalse(signals.intersection(signal.pthread_sigmask(signal.SIG_BLOCK,set())))
        finally:
            for s,handler in old.items():signal.signal(s,handler)
    def test_postprocess_preserves_unrelated_mask_changes_and_pending_signal(self):
        unrelated=signal.SIGUSR1;old_handler=signal.getsignal(unrelated)
        old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set());seen=[];budget=None
        signal.signal(unrelated,lambda *args:seen.append(True))
        try:
            signal.pthread_sigmask(signal.SIG_UNBLOCK,{unrelated})
            budget=m.PostprocessBudget(dict(wall_seconds=5,cpu_seconds=5)).start()
            signal.pthread_sigmask(signal.SIG_BLOCK,{unrelated});os.kill(os.getpid(),unrelated)
            observed=budget.stop();budget=None
            self.assertFalse(observed['budget_exceeded']);self.assertEqual(seen,[])
            self.assertIn(unrelated,signal.pthread_sigmask(signal.SIG_BLOCK,set()));self.assertIn(unrelated,signal.sigpending())
            signal.sigtimedwait({unrelated},0)
            # A caller's unrelated unblock must likewise not be reverted.
            budget=m.PostprocessBudget(dict(wall_seconds=5,cpu_seconds=5)).start()
            signal.pthread_sigmask(signal.SIG_UNBLOCK,{unrelated});budget.stop();budget=None
            self.assertNotIn(unrelated,signal.pthread_sigmask(signal.SIG_BLOCK,set()))
        finally:
            if budget is not None:budget.stop()
            if unrelated in signal.sigpending():signal.sigtimedwait({unrelated},0)
            signal.signal(unrelated,old_handler);signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
    def test_postprocess_nonowner_stop_rejects_before_any_state_change(self):
        import threading
        budget=m.PostprocessBudget(dict(wall_seconds=5,cpu_seconds=5)).start()
        owned={s:signal.getsignal(s)for s in (signal.SIGALRM,signal.SIGPROF)};errors=[];masks=[]
        def foreign():
            masks.append(signal.pthread_sigmask(signal.SIG_BLOCK,set()))
            try:budget.stop()
            except Exception as error:errors.append(error)
            masks.append(signal.pthread_sigmask(signal.SIG_BLOCK,set()))
        try:
            thread=threading.Thread(target=foreign);thread.start();thread.join(2)
            self.assertFalse(thread.is_alive());self.assertEqual(len(errors),1)
            self.assertIsInstance(errors[0],ValueError);self.assertIn('owning main-thread',str(errors[0]))
            self.assertTrue(budget.running);self.assertEqual(masks[0],masks[1])
            self.assertTrue(all(signal.getsignal(s)==handler for s,handler in owned.items()))
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],0);self.assertGreater(signal.getitimer(signal.ITIMER_PROF)[0],0)
        finally:budget.stop()
    def test_postprocess_reentrant_unrelated_handler_mask_is_preserved(self):
        owned={signal.SIGALRM,signal.SIGPROF};real_mask=signal.pthread_sigmask
        old_mask=real_mask(signal.SIG_BLOCK,set());old_handler=signal.getsignal(signal.SIGUSR1)
        try:
            for phase in ('start','stop'):
                real_mask(signal.SIG_UNBLOCK,{signal.SIGUSR1,signal.SIGUSR2});seen=[]
                def unrelated(number,frame):
                    real_mask(signal.SIG_BLOCK,{signal.SIGUSR2});seen.append(number)
                signal.signal(signal.SIGUSR1,unrelated)
                budget=m.PostprocessBudget(dict(wall_seconds=5,cpu_seconds=5))
                if phase=='stop':budget.start()
                def intercept(how,which):
                    previous=real_mask(how,which)
                    if how==signal.SIG_BLOCK and set(which)==owned and not seen:os.kill(os.getpid(),signal.SIGUSR1)
                    return previous
                try:
                    with patch.object(signal,'pthread_sigmask',side_effect=intercept):
                        budget.start()if phase=='start'else budget.stop()
                    self.assertEqual(seen,[signal.SIGUSR1]);self.assertIn(signal.SIGUSR2,real_mask(signal.SIG_BLOCK,set()))
                finally:
                    if budget.running:budget.stop()
        finally:
            signal.signal(signal.SIGUSR1,old_handler);real_mask(signal.SIG_SETMASK,old_mask)
    def test_postprocess_start_real_expiry_cleans_owner(self):
        import time
        owned={signal.SIGALRM,signal.SIGPROF}
        initial=signal.pthread_sigmask(signal.SIG_BLOCK,set());handlers={s:signal.getsignal(s)for s in owned}
        budget=m.PostprocessBudget(dict(wall_seconds=1,cpu_seconds=1));original_restore=budget._restore_owned_mask;delayed=False
        def restore(entry_mask):
            nonlocal delayed
            if not delayed:delayed=True;time.sleep(1.1)
            return original_restore(entry_mask)
        try:
            with patch.object(budget,'_restore_owned_mask',side_effect=restore):
                with self.assertRaises(m.PostprocessBudgetExceeded):budget.start()
            self.assertTrue(delayed);self.assertFalse(budget.running)
            self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK,set()),initial)
            self.assertFalse(owned&signal.sigpending())
            for timer in (signal.ITIMER_REAL,signal.ITIMER_PROF):self.assertEqual(signal.getitimer(timer),(0.,0.))
            for signum,handler in handlers.items():self.assertIs(signal.getsignal(signum),handler)
        finally:
            if budget.running:budget.stop()
    def test_postprocess_start_reentrant_failure_preserves_caller_state(self):
        class ExternalFailure(RuntimeError):pass
        owned={signal.SIGALRM,signal.SIGPROF};real=signal.pthread_sigmask
        initial=real(signal.SIG_BLOCK,set());old_usr1=signal.getsignal(signal.SIGUSR1)
        try:
            for kind in ('owned_start','foreign_timer','blocked_entry'):
                with self.subTest(kind=kind):
                    real(signal.SIG_UNBLOCK,owned|{signal.SIGUSR1,signal.SIGUSR2})
                    if kind=='blocked_entry':real(signal.SIG_BLOCK,{signal.SIGALRM})
                    if kind=='foreign_timer':signal.setitimer(signal.ITIMER_REAL,20,1)
                    handlers={s:signal.getsignal(s)for s in owned};entry_mask=real(signal.SIG_BLOCK,set());seen=[]
                    def external_handler(signum,frame):
                        real(signal.SIG_BLOCK,{signal.SIGUSR2});seen.append(signum)
                        raise ExternalFailure('actual reentrant signal during startup restoration')
                    signal.signal(signal.SIGUSR1,external_handler)
                    budget=m.PostprocessBudget(dict(wall_seconds=5,cpu_seconds=5));original_restore=budget._restore_owned_mask
                    state=dict(restoring=False,injected=False)
                    def restore(mask):
                        state['restoring']=True
                        try:return original_restore(mask)
                        finally:state['restoring']=False
                    def interleave(how,signals):
                        previous=real(how,signals)
                        if state['restoring']and not state['injected']:
                            state['injected']=True;os.kill(os.getpid(),signal.SIGUSR1)
                        return previous
                    try:
                        with patch.object(budget,'_restore_owned_mask',side_effect=restore),patch.object(signal,'pthread_sigmask',side_effect=interleave):
                            with self.assertRaises(ExternalFailure):budget.start()
                        self.assertEqual(seen,[signal.SIGUSR1]);self.assertFalse(budget.running)
                        self.assertEqual(real(signal.SIG_BLOCK,set()),entry_mask|{signal.SIGUSR2})
                        self.assertFalse(owned&signal.sigpending())
                        for signum,handler in handlers.items():self.assertIs(signal.getsignal(signum),handler)
                        if kind=='foreign_timer':
                            remaining,interval=signal.getitimer(signal.ITIMER_REAL);self.assertTrue(0<remaining<=20);self.assertEqual(interval,1)
                        else:self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
                        self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
                    finally:
                        if budget.running:budget.stop()
                        signal.setitimer(signal.ITIMER_REAL,0);signal.setitimer(signal.ITIMER_PROF,0)
        finally:
            signal.signal(signal.SIGUSR1,old_usr1);real(signal.SIG_SETMASK,initial)
    def test_full_execution_evidence_requires_bounded_postprocess_receipt(self):
        import dut_evidence as evidence
        body=fixture(self.log,b'whole log\n')
        report=dict(candidate_scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL',execution_admission=dict(budget_version=2,execution_mode='FULL_BLOCK_ACCEPTANCE',log_policy=body['policy'],postprocess_limits=dict(wall_seconds=10,cpu_seconds=5)))
        row=dict(exit_code=0,log_capture=body,execution_evidence={'unique_clean_terminal':True},postprocess_observed=dict(wall_seconds=1.,cpu_seconds=.1,budget_exceeded=False));start=dict(pid=123,consumer_pid=122)
        self.assertEqual(evidence.verified_full_log(self.root,0,report,row,start,body['policy']),body)
        for observed in (None,{},dict(row['postprocess_observed'],budget_exceeded=True),dict(row['postprocess_observed'],wall_seconds=11),dict(row['postprocess_observed'],cpu_seconds=float('nan')),dict(row['postprocess_observed'],cpu_seconds=-1),dict(row['postprocess_observed'],cpu_seconds=10**1000),dict(row['postprocess_observed'],cpu_seconds=True),dict(row['postprocess_observed'],cpu_seconds=float('inf'))):
            with self.subTest(observed=observed),self.assertRaises(ValueError):evidence.verified_full_log(self.root,0,report,dict(row,postprocess_observed=observed),start,body['policy'])
    def test_indexed_moe_diagnostics_equal_legacy_str(self):
        import struct,moe_score_compare as moe
        data=struct.pack('<I',0x3b800000)*32768;scores=struct.pack('<I',0x3b800000)*1024
        ids=b''.join(struct.pack('<I',i%8) for i in range(1024));official=b''.join(struct.pack('<q',i%8) for i in range(1024));route=b''.join(struct.pack('<Q',(i//8)<<34|(i%8)<<31|(i%8)<<23|i//8) for i in range(1024))
        for name,value in [('router_selection_scores.fp32.actual.bin',data),('router_selected_scores.fp32.actual.bin',scores),('router_selected_ids.u32.actual.bin',ids)]: (self.root/name).write_bytes(value)
        terminal='COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=3 '
        text='HOST_ROUTER_RAW_SCORE_V1 profile=3 transaction=0 owner=9 values=32768 bytes=131072 dtype=FP32 source=SELECTION_INPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\n'+terminal+'cycles=1\nHOST_ROUTER_SELECTED_SCORE_V2 profile=3 transaction=0 owner=9 values=1024 score_bytes=4096 id_bytes=4096 dtype=FP32 index_dtype=UINT32 source=SELECTION_OUTPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\n'
        body=fixture(self.log,text.encode());view=m.LogView(self.log,body,[terminal],[terminal,'HOST_ROUTER_RAW_SCORE_V1','HOST_ROUTER_SELECTED_SCORE_V2']).verify()
        self.assertEqual(moe.observe(self.root,view,3,data,route,official),moe.observe(self.root,text,3,data,route,official))
    def test_summary_reuses_progress_inside_same_profile_budget(self):
        # Synthetic receipt wiring only. Admission and RSS-proof validation are
        # explicit test doubles; native gzip/evidence/progress paths are real.
        sys.path.insert(0,str(D/'acceptance_tests'))
        from test_safe_summary_join import Tests as Fixture,ID
        import dut_evidence as evidence,required_acceptance as acceptance
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
        mode=load('summary_mode_fixture',D/'execution_mode.py');summary=load('summary_stream_fixture',D/'summarize_same_job.py')
        maps=lambda v:dict.fromkeys(map(str,range(5)),v)
        admission=dict(mode=mode.FULL,budget_version=2,budget_contract=mode.FULL_V2_CONTRACT,completion_guaranteed=False,reviewed_budget_sha256='a'*64,log_policy=m.POLICY,profile_log_raw_bytes=maps(1<<20),profile_seconds=maps(100),profile_cpu_seconds=maps(100),profile_max_active_cycles=maps(1000),profile_postprocess_wall_seconds=maps(10),profile_postprocess_cpu_seconds=maps(5),profile_summary_verification_wall_seconds=maps(10),profile_summary_verification_cpu_seconds=maps(10))
        mode._summary_execution_binding=dict(supervisor_dir='/synthetic/test-only',pins={str(D/'summary_progress.py'):hashlib.sha256((D/'summary_progress.py').read_bytes()).hexdigest()})
        work=self.root/'job';work.mkdir();root=Fixture().setup_fixture(work);records=[]
        for i in range(5):
            out=root/f'profile{i}/material/dut_result';report_path=out/'RESULT.json';report=json.loads(report_path.read_text());start=json.loads((out/f'profile{i}.started.json').read_text());outer=root/f'runs/p{i}_dut/RESULT.json'
            body=fixture(out/f'profile{i}.log',line(0,'reset')+line(100),mode.expected_log_policy(admission,i));body.update(pid=start['pid'],consumer_pid=start['consumer_pid']);m.paths(out/f'profile{i}.log')[1].write_text(json.dumps(body))
            original=dict(wall_seconds=20000,cpu_seconds=18000,file_bytes=64<<20,address_space_bytes=16<<30,max_active_cycles=1000000000)
            report.update(candidate_scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL',execution_admission=dict(execution_mode=mode.FULL,reviewed_budget_sha256=admission['reviewed_budget_sha256'],scope='FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE',outer_cleanup_proof_required=True,original_limits=original,effective_limits=mode.consumer_limits(original,admission,i),budget_version=2,log_policy=body['policy'],postprocess_limits=dict(wall_seconds=10,cpu_seconds=5)))
            report['profiles'][0].update(log_capture=body,postprocess_observed=dict(wall_seconds=.1,cpu_seconds=.01,budget_exceeded=False));report_path.write_text(json.dumps(report));outer_row=json.loads(outer.read_text());outer_row['elapsed_seconds']=101;outer.write_text(json.dumps(outer_row))
            record=evidence.verify(out,i,report['artifact_manifest_sha256'],report['runtime_bundle_sha256'],start['binary_sha256'],start['runtime_sha256'],evidence.pin(outer),expected_log_policy=body['policy']);records.append(record);(root/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(record))
        qualification=acceptance.aggregate(records);numeric=root/'RESULT.json';numeric.write_text(json.dumps(dict(execution_mode=mode.FULL,full_budget_sha256=admission['reviewed_budget_sha256'],actual_dut_reports=records,qualification=qualification,status=qualification['status'],numerical_pass=qualification['numerical_pass'])))
        flow_path=work/'FLOW_RESULT.json';flow=json.loads(flow_path.read_text());flow.update(execution_mode=mode.FULL,transport_exit_code=mode.transport_exit(mode.FULL,qualification),numeric_result=evidence.pin(numeric),qualification=qualification,status=qualification['status'],execution_binding={'sha256':'b'*64});flow_path.write_text(json.dumps(flow))
        with patch.object(summary,'full_execution_admission',return_value=(mode,admission,'c'*64)),patch.object(mode,'verify_supervisor_telemetry',return_value={}) as rss:
            result=summary.summarize(work,ID)
        self.assertEqual(result['numeric_qualification']['status'],'VERIFIED_REAGGREGATED');self.assertEqual(rss.call_count,5)
        self.assertEqual([r['sample_count'] for r in result['execution_progress']['profiles']],[2]*5)
        self.assertTrue(all(r['outer_elapsed_seconds']==101 for r in result['execution_progress']['profiles']))
        self.assertNotIn('full_execution_progress',result['numeric_qualification']);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
    def test_more_than_64MiB_and_100000_samples_under_64MiB_AS(self):
        # Generate/write/read incrementally in a separate finite host process.
        script=r'''
import hashlib,json,pathlib,resource,sys,zlib
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,str(pathlib.Path(sys.argv[1])/'numeric'))
import full_log as m,summary_progress as p
from test_progress import line
resource.setrlimit(resource.RLIMIT_AS,(64<<20,64<<20))
log=pathlib.Path(sys.argv[2]);w=m.Writer(m.paths(log)[0],m.POLICY);h=hashlib.sha256();crc=0;n=0
for i in range(160001):
 data=line(i);w.write(data);h.update(data);crc=zlib.crc32(data,crc);n+=len(data)
w.finish();w.close()
body=dict(schema=m.SCHEMA,policy=m.POLICY,pid=123,consumer_pid=122,native_exit=0,termination_reason='NATIVE_EXIT',errors=[],pipe_eof_observed=True,gzip_finalized=True,raw_bytes=n,raw_sha256=h.hexdigest(),gzip_bytes=w.gzip_bytes,gzip_sha256=w.gzip_hash.hexdigest(),raw_crc32=f'{crc:08x}',retained_read_bytes=n,pipe_read_bytes=n,pipe_read_sha256=h.hexdigest(),complete=True)
m.paths(log)[1].write_text(json.dumps(body));r=p.parse_log(log,log.parent,body)
if r['sample_count']!=160001 or r['log_bytes']<=64<<20:raise RuntimeError('large fixture scope')
if m.LogView(log,body).verify().count('HOST_PROGRESS ')!=160001:raise RuntimeError('lossless markers')
print(json.dumps(dict(samples=r['sample_count'],raw_bytes=n,gzip_bytes=w.gzip_bytes,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,as_bytes=64<<20)))
'''
        cp=subprocess.run([sys.executable,'-c',script,str(D),str(self.log)],capture_output=True,text=True,timeout=120)
        self.assertEqual(cp.returncode,0,cp.stderr);row=json.loads(cp.stdout);self.assertGreater(row['raw_bytes'],64<<20);self.assertLess(row['max_rss_kib']*1024,64<<20)
        print('BOUNDED_MEMORY_FIXTURE',json.dumps(row,sort_keys=True))

if __name__=='__main__':unittest.main()
