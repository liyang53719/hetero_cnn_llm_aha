"""New header controller's real export/seal boundary, entirely mocked execution."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import run_header_repair as controller
import header_repair_export as export
from fixture_gate import FixtureMismatch


class HeaderControllerTests(unittest.TestCase):
    def exercise(self,mode='success',fault=None):
        affinity=sorted(os.sched_getaffinity(0));calls=[];held=set();flock=controller.fcntl.flock
        def track(fd,operation):
            flock(fd,operation)
            if operation&controller.fcntl.LOCK_UN:held.discard(fd)
            else:held.add(fd)
        def write(p,v):p.write_text(json.dumps(v,allow_nan=False)+'\n')
        def supervisor(argv,run,lock,caps,env,pins,resource_gate):
            calls.append(argv);self.assertIn('header_probe.py',argv[3]);self.assertEqual(caps['job_cpu_budget_seconds'],60)
            self.assertEqual(caps['file_bytes'],1<<20);self.assertEqual(caps['rss_bytes'],256<<20)
            self.assertNotIn('GH_TOKEN',env);self.assertNotIn('ATEN_CPU_CAPABILITY',env)
            out=run/'output';out.mkdir(parents=True)
            d=dict(schema='P0_HEADER_DIAGNOSTIC_V1',status='PASS_HEADER_ONLY',failure_point='COMPLETE',failure_code='NONE',http_status=206,
                   final_host='HF_US_AWS_CDN',response_bytes=38536,observed_header_sha256=export.HEADER_SHA,header_sha_equal=True,geometry_checked=12,redirect_count=1)
            report=dict(native_exit=0,errors=[],status='PASS_PROCESS_ONLY',cleanup_proof={'status':export.COMPLETE},observed_remaining=[],
                log_capture={'pipe_eof_observed':True,'gzip_finalized':True},reader_join_barrier={'complete':True},rss_telemetry={'all_written_bytes_verified':True},
                elapsed_seconds=.1,observed_cpu_seconds=.01,supervisor_cpu_seconds=.001,observed_peak_rss=1000,peak_tree_bytes=1000,minimum_free_disk_bytes=8<<30,minimum_MemAvailable_bytes=4<<30)
            if mode=='http_failure':
                d.update(status='FAIL',failure_point='REQUEST',failure_code='HTTP_ERROR',http_status=403,final_host='HUGGINGFACE',response_bytes=None,observed_header_sha256=None,header_sha_equal=None,geometry_checked=0,redirect_count=0)
                report.update(native_exit=1,status='FAIL_OR_INCOMPLETE')
            elif mode=='incomplete':
                report.update(status='FAIL_OR_INCOMPLETE',cleanup_proof=None,observed_remaining=[{'pid':123,'start':456}],reader_join_barrier={'complete':False},log_capture={'pipe_eof_observed':False,'gzip_finalized':False})
            write(out/'HEADER_DIAGNOSTIC.json',d);return report
        with tempfile.TemporaryDirectory(prefix='header-controller-mock-') as temp:
            root=Path(temp);work=root/'p0-header-repair-123';identity=dict(schema='P0_HEADER_REPAIR_IDENTITY_V1',run_id=123,source_commit='a'*40,launch_commit='b'*40,source_manifest_sha256='c'*64,nonce='d'*32,failed_run_id=41720209902)
            write(root/'identity.json',identity);write(root/'start.json',dict(schema='P0_HEADER_REPAIR_START_V1',run_id=123,launch_commit='b'*40,started_monotonic=time.monotonic(),job_budget_seconds=180))
            args=SimpleNamespace(repo=root,output=work,identity=root/'identity.json',job_start=root/'start.json')
            try:
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(os.environ,{'RUNNER_TEMP':str(root),'GITHUB_RUN_ID':'123'}));stack.enter_context(patch.object(controller,'identity_check'))
                    stack.enter_context(patch.object(controller,'verify_source',return_value={}))
                    stack.enter_context(patch.object(controller,'host_evidence',return_value=(dict(architecture='x86_64',python_version='3.12.3',python_sha256='e'*64,affinity=affinity),'f'*64)))
                    stack.enter_context(patch.object(controller,'available_memory',return_value=4<<30));stack.enter_context(patch.object(controller.shutil,'disk_usage',return_value=SimpleNamespace(free=8<<30)))
                    stack.enter_context(patch.object(controller.fcntl,'flock',side_effect=track));stack.enter_context(patch.object(controller.supervise_multiroot,'execute',side_effect=supervisor))
                    for name in ('Popen','run','check_output'):stack.enter_context(patch.object(controller.subprocess,name,side_effect=AssertionError('NO SUBPROCESS IN MOCK')))
                    if fault:
                        original=export.write_exports
                        def injected(*a,**k):
                            result=original(*a,**k)
                            if fault=='deadline':stack.enter_context(patch.object(controller.time,'monotonic',return_value=time.monotonic()+181))
                            else:controller.signal.getsignal(controller.signal.SIGALRM)(controller.signal.SIGALRM,None)
                            return result
                        stack.enter_context(patch.object(export,'write_exports',side_effect=injected))
                        with self.assertRaises(FixtureMismatch):controller.run(args)
                        self.assertFalse((work/'TERMINAL.json').exists())
                        with self.assertRaises((ValueError,FileNotFoundError)):export.verify_sealed(work,identity,'failure')
                        return
                    result=controller.run(args)
                self.assertEqual(len(calls),1)
                outcome='success' if mode=='success' else 'failure';files=export.verify_sealed(work,identity,outcome)
                self.assertEqual(set(p.name for p in (work/'export').iterdir()),set(export.FILES))
                if mode=='success':
                    self.assertEqual(result,0)
                    with self.assertRaises(ValueError):export.verify_sealed(work,identity,'failure')
                else:self.assertEqual(result,1)
                return files
            finally:
                for fd in held:flock(fd,controller.fcntl.LOCK_UN);os.close(fd)

    def test_success_header_only(self):
        files=self.exercise();self.assertEqual(files['RESULT.json']['status'],'PASS_HEADER_ONLY')
        self.assertEqual(files['CHECKS.json']['diagnostic']['geometry_checked'],12)
        self.assertFalse(files['RESULT.json']['reference_executed']);self.assertFalse(files['RESULT.json']['original_failure_cause_proven'])

    def test_http_error_fixed_summary(self):
        files=self.exercise('http_failure');self.assertEqual(files['RESULT.json']['reason'],'PROBE_FAILURE')
        self.assertEqual(files['CHECKS.json']['diagnostic']['http_status'],403)
        self.assertEqual(files['CHECKS.json']['diagnostic']['failure_code'],'HTTP_ERROR')

    def test_incomplete_owned_cleanup(self):
        files=self.exercise('incomplete');self.assertEqual(files['RESULT.json']['status'],'INCOMPLETE')
        self.assertEqual(files['HOST_RESOURCES.json']['cleanup'],'INCOMPLETE')

    def test_post_export_deadline_is_not_transport_pass(self):self.exercise(fault='deadline')
    def test_post_export_alarm_is_not_transport_pass(self):self.exercise(fault='alarm')

    def test_fixed_export_unknown_nan_bool_host_rejection(self):
        files=self.exercise();r,c,h=(files[n] for n in export.FILES)
        for target,key,value in ((0,'unknown','signed-url'),(0,'run_id',True),(1,'unknown',[1,2]),(2,'job_cpu_seconds',float('nan')),(2,'native_exit',True)):
            values=copy.deepcopy([r,c,h]);values[target][key]=value
            with self.assertRaises(ValueError):export.validate(*values)
        value=copy.deepcopy(c);value['diagnostic']['final_host']='arbitrary.example'
        with self.assertRaises(ValueError):export.validate(r,value,h)
        value=copy.deepcopy(c);value['diagnostic']['signed_url']='https://example.test/?secret=REDACTED'
        with self.assertRaises(ValueError):export.validate(r,value,h)

if __name__=='__main__':unittest.main()
