import copy
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from . import preflight_diagnostic as D


class DiagnosticTests(unittest.TestCase):
    def test_strict_schema_and_no_arbitrary_data(self):
        good=D.record('BIND')
        for key,value in (('path','secret'),('line',True),('error','private'),('phase','private'),
                          ('module','private'),('dut_started',True),('schema',True)):
            bad={**good,key:value}
            with self.assertRaises(ValueError):D.checked(bad)
        with self.assertRaises(ValueError):D.checked({**good,'error':'NONE'})

    def test_trace_projection_skips_assertion_helpers_without_error_text(self):
        class Poison(ValueError):
            def __str__(self):raise AssertionError('must not read error text')
            def __repr__(self):raise AssertionError('must not read repr')
        ns={'error':Poison()}
        source='def need():\n raise error\ndef metadata():\n need()\nmetadata()\n'
        try:exec(compile(source,str(D.ROOT/'candidates/qwen2_official_platform_fullblock/recipe.py'),'exec'),ns)
        except Poison as error:result=D.project(error,'BIND')
        self.assertEqual((result['module'],result['line'],result['error']),('RECIPE',4,'VALUE_ERROR'))

    def test_unknown_source_is_not_echoed(self):
        try:exec(compile('raise ValueError("secret")','/unapproved/secret.py','exec'))
        except ValueError as error:result=D.project(error,'BIND')
        self.assertNotIn('secret',json.dumps(result));self.assertEqual(result['module'],'OTHER')

    def test_child_parser_only_valid_marker_and_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'log'
            p.write_text('private traceback\n'+D.PREFIX+json.dumps(D.record('BIND'))+'\n'+
                D.PREFIX+json.dumps({**D.record('PROBE'),'path':'private'})+'\n')
            self.assertEqual(D.read_child(p),D.record('PROBE'))
            p.write_text(D.PREFIX+json.dumps(D.record('PROBE',error='VALUE_ERROR',module='GATES',line=10))+'\n')
            self.assertEqual(D.read_child(p)['module'],'GATES')

    def test_remaining_budget_is_bounded(self):
        for raw in ('','secret','9999999999999','-1','1000'):
            with patch.dict(os.environ,{D.DEADLINE_ENV:raw}),patch.object(D.time,'time',return_value=1000):
                with self.assertRaises(ValueError):D.remaining()
        with patch.dict(os.environ,{D.DEADLINE_ENV:'1091'}),patch.object(D.time,'time',return_value=1000):
            self.assertEqual(D.remaining(),91)

    def test_explicit_no_dut_policy_and_separate_authority(self):
        from . import job,recipe
        old=copy.deepcopy(job.POLICY)
        with patch.object(job,'AUTH',job.AUTH),patch.object(recipe,'AUTH',recipe.AUTH),\
             patch.object(job,'POLICY',copy.deepcopy(old)):
            configured,_=D.configure()
            self.assertEqual(configured.AUTH,D.AUTH)
            self.assertEqual(configured.POLICY['job_total_minutes'],15)
            for key in ('maximum_invocations','dut_invocations','dut_inner_seconds','dut_outer_seconds'):
                self.assertEqual(configured.POLICY[key],0)
            self.assertIs(configured.POLICY['diagnostic_only'],True)
            self.assertNotEqual(configured.POLICY,old)

    def test_oversized_child_log_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'log';p.write_bytes(b'x'*(4*1024*1024+1))
            self.assertEqual(D.read_child(p),D.record('PROBE'))

    def test_outer_log_failure_still_has_safe_record(self):
        out=io.StringIO()
        with patch.object(D,'run',side_effect=PermissionError('private path')),patch('sys.stdout',out):
            code=D.main(['preflight'])
        self.assertEqual(code,2);value=D.checked(json.loads(out.getvalue()))
        self.assertEqual(value['phase'],'AUTHORIZE');self.assertNotIn('private',out.getvalue())

    def test_child_failure_emits_safe_marker_without_replacing_local_trace(self):
        from . import audit_probe
        out,err=io.StringIO(),io.StringIO()
        with patch.object(audit_probe,'main',side_effect=ValueError('private reason')),\
             patch('sys.stdout',out),patch('sys.stderr',err):
            code=D.child()
        self.assertEqual(code,2);self.assertIn('private reason',err.getvalue())
        self.assertNotIn('private',out.getvalue())
        value=D.checked(json.loads(out.getvalue().strip()[len(D.PREFIX):]))
        self.assertEqual(value['phase'],'PROBE')

    def test_trace_print_failure_cannot_hide_child_projection(self):
        from . import audit_probe
        out=io.StringIO()
        with patch.object(audit_probe,'main',side_effect=ValueError('private')),\
             patch.object(D.traceback,'print_exc',side_effect=OSError('log failure')),patch('sys.stdout',out):
            self.assertEqual(D.child(),2)
        value=D.checked(json.loads(out.getvalue().strip()[len(D.PREFIX):]))
        self.assertEqual(value['error'],'VALUE_ERROR')

    def test_trace_print_failure_cannot_hide_parent_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            job,recipe=self.fixture(directory)
            def fail():raise ValueError('private')
            job.bind=fail
            with patch.object(D,'ROOT',Path(directory)),patch.object(D,'configure',return_value=(job,recipe)),\
                 patch.object(D,'remaining',return_value=200),\
                 patch.object(D.traceback,'print_exc',side_effect=OSError('log failure')):
                result=D.run()
            self.assertEqual(result['phase'],'BIND');self.assertEqual(result['error'],'VALUE_ERROR')

    def fixture(self,directory):
        recipe=types.SimpleNamespace(STATUS='BOUND',BINDING_ENV='COLD_TEST_BINDING')
        def need(ok,message):
            if not ok:raise ValueError(message)
        job=types.SimpleNamespace(need=need,authorize=lambda:{},bind=lambda:dict(status='BOUND',
            reference_outputs_checked=29,policy_conditions_satisfied=True,binding_sha256='a'*64))
        return job,recipe

    def test_bind_failure_is_projected_and_no_child_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            job,recipe=self.fixture(directory)
            def fail():raise ValueError('private tensor metadata')
            job.bind=fail
            with patch.object(D,'ROOT',Path(directory)),patch.object(D,'configure',return_value=(job,recipe)),\
                 patch.object(D,'remaining',return_value=200),patch.object(D.subprocess,'run') as child:
                result=D.run()
            self.assertEqual(result['phase'],'BIND');self.assertFalse(child.called)
            self.assertNotIn('private',json.dumps(result))

    def test_insufficient_budget_refuses_child(self):
        with tempfile.TemporaryDirectory() as directory:
            job,recipe=self.fixture(directory)
            with patch.object(D,'ROOT',Path(directory)),patch.object(D,'configure',return_value=(job,recipe)),\
                 patch.object(D,'remaining',side_effect=(150,91)),patch.object(D.subprocess,'run') as child:
                result=D.run()
            self.assertEqual(result['phase'],'PROBE');self.assertFalse(child.called)

    def test_insufficient_step_budget_refuses_child(self):
        with tempfile.TemporaryDirectory() as directory:
            job,recipe=self.fixture(directory)
            with patch.object(D,'ROOT',Path(directory)),patch.object(D,'configure',return_value=(job,recipe)),\
                 patch.object(D,'remaining',return_value=200),patch.object(D.time,'monotonic',side_effect=(0,30)),\
                 patch.object(D.subprocess,'run') as child:
                result=D.run()
            self.assertEqual(result['phase'],'PROBE');self.assertFalse(child.called)

    def test_actual_child_failure_location_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            job,recipe=self.fixture(directory)
            safe=D.record('PROBE',error='PERMISSION_ERROR',module='GATES',line=17)
            def child(*args,**kwargs):
                kwargs['stdout'].write((D.PREFIX+json.dumps(safe)+'\n').encode())
                return types.SimpleNamespace(returncode=2)
            with patch.object(D,'ROOT',Path(directory)),patch.object(D,'configure',return_value=(job,recipe)),\
                 patch.object(D,'remaining',return_value=200),patch.object(D.subprocess,'run',side_effect=child):
                self.assertEqual(D.run(),safe)

    def test_launch_admission_failure_is_distinct_and_no_dut(self):
        with tempfile.TemporaryDirectory() as directory:
            job,recipe=self.fixture(directory)
            def child(command,**kwargs):
                kwargs['stdout'].write((D.PREFIX+json.dumps(D.record('PROBE',success=True))+'\n').encode())
                return types.SimpleNamespace(returncode=0)
            with patch.object(D,'ROOT',Path(directory)),patch.object(D,'configure',return_value=(job,recipe)),\
                 patch.object(D,'remaining',return_value=200),patch.object(D.subprocess,'run',side_effect=child),\
                 patch.object(D,'launch_admission',side_effect=ValueError('private')):
                result=D.run()
            self.assertEqual(result['phase'],'LAUNCH_ADMISSION');self.assertIs(result['dut_started'],False)

    def test_success_never_starts_dut(self):
        with tempfile.TemporaryDirectory() as directory:
            job,recipe=self.fixture(directory);commands=[]
            def child(command,**kwargs):
                commands.append(command)
                kwargs['stdout'].write((D.PREFIX+json.dumps(D.record('PROBE',success=True))+'\n').encode())
                return types.SimpleNamespace(returncode=0)
            with patch.object(D,'ROOT',Path(directory)),patch.object(D,'configure',return_value=(job,recipe)),\
                 patch.object(D,'remaining',return_value=200),patch.object(D.subprocess,'run',side_effect=child),\
                 patch.object(D,'launch_admission'):
                result=D.run()
            self.assertEqual(result,D.record('COMPLETE',success=True));self.assertEqual(len(commands),1)
            self.assertEqual(commands[0][-1],'child');self.assertNotIn('--actual',commands[0])


if __name__=='__main__':unittest.main()
