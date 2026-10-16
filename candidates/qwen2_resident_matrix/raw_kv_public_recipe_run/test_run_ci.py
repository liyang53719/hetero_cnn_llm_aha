"""Cold launch tests: mocked originals and tiny cleanup children, no native math."""
from contextlib import ExitStack,redirect_stdout,redirect_stderr
import ast
import copy
from dataclasses import asdict
import io
import json
import re
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock,mock_open,patch
from . import run_ci as run
# Imported by the existing cold workflow test target; no workflow trigger change.
from .test_numeric_progress import ProgressTests,OriginalTraceRegressionTests

COMMIT='a'*40
SOURCES={'original.py':'1'*64}
FROZEN=dict(contract_sha256='2'*64,sources=SOURCES,original_sources=SOURCES,generated={},git_blobs={})


def cpu_bytes(*records):
    return ('\n\n'.join('processor : %d\nvendor_id : CONTROL_ONLY\nflags : %s'%(index,' '.join(flags))
        for index,flags in enumerate(records or (run.CPU_FLAGS,)))).encode('ascii')


def cpu_record(*,eligible=True):
    return run.cpu_eligibility(cpu_bytes(run.CPU_FLAGS if eligible else run.CPU_FLAGS[1:]),
        system='Linux',machine='x86_64',override_absent=True)


def eligible_fixture(summary):
    summary['phase']='cpu_qualification';summary['cpu_eligibility']=cpu_record()
    return summary['cpu_eligibility']


def actual():
    stages={name:dict(metrics={'finite':True},observed_elements=1,verdict=
        dict(passed=None,status='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE') if name=='softmax_fp32' else dict(passed=True))
        for name in run.assets.shapes() if name!='mask'}
    host=dict(accepted=dict(completion_fire=21,request_fire=17,owner_result_fire=17,result_fire=1,raw_kv_parent_edges=7),
        launch_result=dict(status=None,completed=21,jobs=17),reset_required=False,
        completions=[dict(pc=i,status=None) for i in range(21)])
    return dict(status='PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES',native_acceptance='PASS_OBSERVED_ONLY',
        actual_dataflow_pass=True,full_29_node_acceptance=False,rows=128,enable_raw_kv=True,fresh_profile=True,
        old_pass_inherited=False,rtl_executed=False,scala_executed=False,source_sha256=SOURCES,source_sha256_after=SOURCES,
        comparison=dict(fixed_arithmetic_pass=True,full_29_node_acceptance=False,
            acceptance_requires_all_assigned_official_observed_node_gates=True,official_target='official_self_cache',
            methods={'official_self_cache':dict(failed_stages=[],numerical_status='PASS_OBSERVED_ONLY',stages=stages)}),
        execution=dict(status='PUBLIC21_PC0_20_SOFTWARE_EXECUTED',full_block_software_model_executed=True,
            same_owner_and_banks=True,same_physical_memory_and_services=True,host=host,
            reports=[dict(kind='Attention',pcs=[10,11,12],report=dict(accepted=dict(requests=10,responses=10),
                final_ack_fence=dict(terminal_strictly_after_final_ack=True,final_ack_tick=5,terminal_tick=6)))]))


def original_profile_report():
    """Original report method/profile over a CONTROL_ONLY inert parent report.

    No Matrix service is constructed and no arithmetic is executed. The real
    pinned method preserves the profile's nested tuples in the returned dict.
    """
    prefix='candidates/qwen2_resident_matrix/dense_block_reduce/'
    pins=run.assets.read_json(run.ROOT/'candidates/qwen2_resident_matrix/raw_kv_public_fresh/pins.json')
    for name in ('profile.py','matrix_binding.py'):
        if run.assets.file_sha(run.ROOT/prefix/name)!=pins['source_sha256'][prefix+name]:
            raise ValueError('original serialization fixture source drift')
    profile_path=run.ROOT/prefix/'profile.py'
    namespace={'__name__':__name__,'__file__':str(profile_path)}
    exec(compile(ast.parse(profile_path.read_text()),str(profile_path),'exec'),namespace)
    path=run.ROOT/prefix/'matrix_binding.py'
    cls=next(node for node in ast.parse(path.read_text()).body
             if isinstance(node,ast.ClassDef) and node.name=='ProfiledMatrixService')
    cls=copy.deepcopy(cls)
    cls.body=[node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='report']
    class ControlOnlyReportBase:
        def report(self):return {'fixture_kind':'CONTROL_ONLY'}
    namespace.update(OfficialMatrixService=ControlOnlyReportBase,asdict=asdict)
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(path),'exec'),namespace)
    service=namespace['ProfiledMatrixService']()
    service.profile=namespace['QWEN2_QKV_PROFILE']
    return service.report()


def original_report_bytes(value):
    """Execute the pinned original entry chain's JSON encoder, without imports."""
    name='candidates/qwen2_resident_matrix/ffn_public/check_prefix_numeric.py'
    pins=run.assets.read_json(run.ROOT/'candidates/qwen2_resident_matrix/raw_kv_public_fresh/pins.json')
    path=run.ROOT/name
    if run.assets.file_sha(path)!=pins['source_sha256'][name]:
        raise ValueError('original report encoder source drift')
    node=next(node for node in ast.parse(path.read_text()).body
              if isinstance(node,ast.FunctionDef) and node.name=='encoded')
    namespace={'json':json}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return namespace['encoded'](value)


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(run.assets.encoded(value))


def context(private,evidence):
    start=time.monotonic_ns()
    return dict(schema=1,private=str(private),evidence=str(evidence),checkout_commit=COMMIT,started_ns=start,
        deadline_ns=start+run.TOTAL*10**9,contract_sha256=FROZEN['contract_sha256'],source_sha256=SOURCES,
        generated_sha256={},git_blobs={'original.py':'b'*40,run.CONTRACT:'c'*40},cpu_eligibility=cpu_record())


def bound_snapshot(ctx,receipt_sha256,snapshot=None):
    value=dict(snapshot or {'source_sha256':SOURCES})
    value[run.launch.SNAPSHOT_KEY]=dict(profile=run.launch.PROFILE,checkout_commit=ctx['checkout_commit'],
        launch_contract_sha256=ctx['contract_sha256'],setup_receipt_sha256=receipt_sha256,
        m16_evidence_sha256=run.launch.M16_EVIDENCE_SHA256)
    return value


def control_only_bind(snapshot,identity,ctx):
    """Control fixture only; real source/admission binding has separate tests."""
    return bound_snapshot(ctx,identity.receipt_sha256,snapshot)


def complete(private,ctx,value=None):
    value=actual() if value is None else value
    write_json(private/'actual/summary.json',value)
    write_json(private/'assets/SETUP.json',{'status':run.setup.SETUP_STATUS})
    write_json(private/'snapshot/SNAPSHOT.json',bound_snapshot(ctx,run.assets.file_sha(private/'assets/SETUP.json')))
    result=run.validate_actual(actual(),SOURCES)
    result.update(schema=1,status=run.PASS,rows=128,enable_raw_kv=True,fresh_profile=True,
        launch_contract_sha256=ctx['contract_sha256'],setup_receipt_sha256=run.assets.file_sha(private/'assets/SETUP.json'),
        actual_receipt_sha256=run.assets.file_sha(private/'actual/summary.json'),snapshot_sha256=run.assets.file_sha(private/'snapshot/SNAPSHOT.json'),
        source_manifest_sha256=run.assets.sha(run.assets.encoded(SOURCES)),actual_source_manifest_sha256=run.assets.sha(run.assets.encoded(SOURCES)))
    write_json(private/'numeric.complete.json',result)
    return result


class LaunchTests(unittest.TestCase):
    def setUp(self):
        guard=patch.object(run,'qualify_cpu',side_effect=eligible_fixture)
        guard.start();self.addCleanup(guard.stop)

    def exercise(self,root,*,child=None,setup_result=None,check=None):
        private=root/'private';evidence=root/'safe';private.mkdir();evidence.mkdir();(private/'logs').mkdir();(private/'tmp').mkdir()
        ctx=context(private,evidence);write_json(private/'context.json',ctx);calls=[]
        def command(budget,argv,**kw):
            calls.append((argv,kw))
            if kw.get('end_ns') is not None:budget.arm(kw['end_ns']-int(run.RECEIPT*10**9))
            if child:return child(private,ctx,kw)
            complete(private,ctx);return 0
        with patch.object(run,'expected_entry_sources',return_value=SOURCES),patch.object(run,'check_context',return_value=FROZEN,side_effect=check),patch.object(run.setup,'run',return_value=setup_result or (0,{'status':run.setup.SETUP_STATUS})),patch.object(run.Budget,'command',command):
            result=run.resume(ctx,private,evidence)
        return (*result,calls,ctx,private,evidence)

    def test_one_setup_one_numeric_child_and_exact_deadlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls,ctx,private,evidence=self.exercise(Path(tmp))
            self.assertEqual((code,summary['status']),(0,run.PASS));self.assertEqual(len(calls),1)
            argv,kw=calls[0];self.assertEqual(kw['cap'],2430)
            self.assertEqual(argv[0],str(private/'assets/venv/bin/python'))
            self.assertIn('--internal-numeric',argv)
            deadline=int(kw['extra_env']['QWEN2_PUBLIC_NUMERIC_DEADLINE_NS'])
            self.assertLessEqual(deadline,ctx['deadline_ns'])
            self.assertEqual(summary['assigned_official_gates'],27)
            self.assertFalse(summary['full_29_node_acceptance'])
            self.assertNotEqual(json.loads((evidence/'progress.json').read_text())['status'],run.PASS)

    def test_setup_has_no_inherited_alarm_and_deadline_only_shortens(self):
        def setup(*args,**kw):
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
            self.assertLessEqual(kw['deadline_ns']-time.monotonic_ns(),900*10**9)
            return 1,{'status':'SETUP_TIMEOUT'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(run.setup,'run',side_effect=setup) as called:
            root=Path(tmp);private=root/'private';private.mkdir();evidence=root/'safe';evidence.mkdir();ctx=context(private,evidence)
            with patch.object(run,'check_context',return_value=FROZEN),patch.object(run.Budget,'command') as child:
                code,summary=run.resume(ctx,private,evidence)
            self.assertNotEqual(code,0);called.assert_called_once();child.assert_not_called()
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_failed_setup_never_runs_numeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls,*_=self.exercise(Path(tmp),setup_result=(1,{'status':'SETUP_FAILED'}))
            self.assertNotEqual(code,0);self.assertFalse(calls)

    def test_child_zero_without_actual_terminal_is_not_pass(self):
        def child(private,ctx,kw):
            complete(private,ctx,{'status':run.setup.SETUP_STATUS});return 0
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),child=child)
            self.assertNotEqual(code,0);self.assertNotEqual(summary['status'],run.PASS)

    def test_nonzero_or_timeout_child_cannot_use_complete_receipt(self):
        for error in (RuntimeError('raw=[1,2] /private https://signed'),subprocess.TimeoutExpired(['SECRET'],1)):
            def child(private,ctx,kw):complete(private,ctx);raise error
            with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as tmp:
                code,summary,*_=self.exercise(Path(tmp),child=child)
                self.assertNotEqual(code,0)
                for forbidden in ('SECRET','raw=','/private','https://'):self.assertNotIn(forbidden,json.dumps(summary))

    def test_public_projection_never_copies_private_actual_fields(self):
        private_text='/private/token raw_tensor=[1,2,3] https://cdn/?signature=SECRET'
        def child(private,ctx,kw):
            value=actual();value['error']=private_text;value['snapshot']=private_text;complete(private,ctx,value);return 0
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls,ctx,private,evidence=self.exercise(Path(tmp),child=child)
            self.assertEqual(code,0)
            public=json.dumps(summary)+''.join(p.read_text() for p in evidence.iterdir())
            for forbidden in ('SECRET','raw_tensor','/private/token','https://',tmp):self.assertNotIn(forbidden,public)

    def test_timeout_exports_last_child_phase_without_any_postflight_receipt(self):
        def child(private,ctx,kw):
            with run.numeric_progress.session(private,ctx,SOURCES) as writer:
                with writer.phase('actual_execute'):
                    run.numeric_progress.stage('public_suffix')
                    run.numeric_progress.host('REQUEST',12,10,11,10,10,0)
                    raise subprocess.TimeoutExpired(['PRIVATE_NOT_EXPORTED'],1)
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls,ctx,private,evidence=self.exercise(Path(tmp),child=child)
            self.assertEqual((code,summary['status']),(1,'TIMEOUT'))
            value=summary['numeric_progress']
            self.assertEqual((value['phase'],value['stage'],value['operator'],value['ordinal']),
                             ('actual_execute','public_suffix','Attention',12))
            self.assertEqual(value['phase_state'],'ENTERED')
            self.assertFalse(value['numerical_acceptance']);self.assertFalse(summary['postflight_complete'])
            self.assertFalse((private/'numeric.validated.json').exists())
            self.assertFalse((private/'numeric.complete.json').exists())
            self.assertEqual(set(path.name for path in evidence.iterdir()),{'summary.json','progress.json'})
            self.assertNotIn('PRIVATE_NOT_EXPORTED',(evidence/'summary.json').read_text())

    def test_malicious_child_progress_cannot_change_summary_or_source_proof(self):
        def child(private,ctx,kw):
            with run.numeric_progress.session(private,ctx,SOURCES) as writer:
                bad=dict(writer.value,payload='SECRET',status='PASS',numerical_acceptance=True)
                (private/run.numeric_progress.FILE).write_bytes(run.assets.encoded(bad))
            raise TimeoutError()
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),child=child)
            self.assertEqual((code,summary['status']),(1,'TIMEOUT'))
            self.assertTrue(summary['numeric_progress_unavailable'])
            self.assertNotIn('numeric_progress',summary);self.assertNotIn('SECRET',json.dumps(summary))
            self.assertFalse(summary['numerical_acceptance']);self.assertNotIn('source_sha256',summary)

    def test_source_drift_after_child_prevents_pass(self):
        calls=0
        def check(*args,**kwargs):
            nonlocal calls
            calls+=1
            return FROZEN if calls<3 else dict(FROZEN,sources={'changed.py':'f'*64})
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),check=check)
            self.assertNotEqual(code,0);self.assertNotEqual(summary['status'],run.PASS)

    def test_strict_original_receipt_negative_fields_and_host_retirement(self):
        variants=[]
        for field,bad in (('rows',True),('enable_raw_kv',1),('fresh_profile',False),('full_29_node_acceptance',True),
                          ('old_pass_inherited',True),('actual_dataflow_pass',False),('status','PASS')):
            value=actual();value[field]=bad;variants.append(value)
        value=actual();value['comparison']['methods']['official_self_cache']['stages']['q']['verdict']['passed']=False;variants.append(value)
        value=actual();value['execution']['host']['accepted']['raw_kv_parent_edges']=0;variants.append(value)
        value=actual();value['execution']['host']['accepted']['completion_fire']=20;variants.append(value)
        value=actual();value['execution']['reports'][0]['report']['final_ack_fence']['terminal_tick']=5;variants.append(value)
        value=actual();value['comparison']['fixed_arithmetic_pass']=1;variants.append(value)
        value=actual();value['execution']['host']['completions'][0]['pc']=False;variants.append(value)
        value=actual();value['execution']['reports'][0]['report']['accepted']=dict(requests=1,responses=True);variants.append(value)
        for index,value in enumerate(variants):
            with self.subTest(index=index),self.assertRaises((ValueError,KeyError)):run.validate_actual(value,SOURCES)

    def test_context_preserves_original_origin_and_rejects_future_expired_or_changed_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';evidence=root/'safe';private.mkdir();evidence.mkdir();ctx=context(private,evidence)
            path=private/'context.json';write_json(path,ctx)
            restored,_,_=run.context_read(path,run.assets.file_sha(path))
            self.assertEqual((restored['started_ns'],restored['deadline_ns']),(ctx['started_ns'],ctx['deadline_ns']))
            for kind in ('future','expired','extra_budget','bool','missing_git'):
                bad=copy.deepcopy(ctx)
                if kind=='future':bad['started_ns']=time.monotonic_ns()+10**9;bad['deadline_ns']=bad['started_ns']+run.TOTAL*10**9
                if kind=='expired':bad['deadline_ns']=time.monotonic_ns()-1;bad['started_ns']=bad['deadline_ns']-run.TOTAL*10**9
                if kind=='extra_budget':bad['deadline_ns']+=1
                if kind=='bool':bad['started_ns']=True
                if kind=='missing_git':bad['git_blobs']={}
                write_json(path,bad)
                with self.subTest(kind=kind),self.assertRaises(ValueError):run.context_read(path,run.assets.file_sha(path))

    def test_run_attempt_two_and_missing_opt_in_fail_before_bootstrap(self):
        for args,attempt in (([], '1'),(['--execute','--private','p','--evidence','s','--checkout-commit',COMMIT],'2')):
            with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':attempt}),patch.object(run,'bootstrap') as call,redirect_stdout(io.StringIO()):
                self.assertNotEqual(run.main(args),0);call.assert_not_called()

    def test_resume_checks_identity_before_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';evidence=root/'safe';private.mkdir();evidence.mkdir();ctx=context(private,evidence)
            with patch.object(run,'check_context',side_effect=ValueError('different commit')),patch.object(run.setup,'run') as setup:
                code,summary=run.resume(ctx,private,evidence)
            self.assertNotEqual(code,0);setup.assert_not_called()

    def test_admission_consuming_child_deadline_prevents_original_import(self):
        from . import admission
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ctx={'deadline_ns':time.monotonic_ns()+10**9,'checkout_commit':COMMIT}
            deadline=time.monotonic_ns()+30_000_000
            def admit(*args,**kwargs):time.sleep(.05);return object()
            with patch.object(run,'check_context',return_value=FROZEN),patch.object(admission,'verify_setup',side_effect=admit),patch.object(run.importlib,'import_module') as imported:
                with self.assertRaises(TimeoutError):run.numeric(ctx,root,deadline_ns=deadline)
                imported.assert_not_called()

    def test_numeric_calls_original_prepare_run_once_with_revalidation(self):
        from . import admission
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);ctx={'deadline_ns':time.monotonic_ns()+10**9,'checkout_commit':COMMIT,'contract_sha256':FROZEN['contract_sha256']}
            identity=types.SimpleNamespace(library_receipt=private/'library.json',manifest=private/'ASSETS.json',manifest_sha256='3'*64,receipt_sha256='4'*64)
            calls=[];value=actual();snapshot={'source_sha256':SOURCES}
            value['execution']['matrix']=original_profile_report()
            self.assertEqual(value['execution']['matrix']['qkv_reduction_profile']['ranges'],((0,1024),(1024,1536)))
            def prepare(*args,**kwargs):
                calls.append(('prepare',args,kwargs));write_json(private/'snapshot/SNAPSHOT.json',snapshot);return private/'snapshot/SNAPSHOT.json',snapshot
            def execute(*args,**kwargs):
                calls.append(('run',args,kwargs))
                target=private/'actual/summary.json';target.parent.mkdir();target.write_bytes(original_report_bytes(value))
                disk=run.assets.read_json(private/'actual/summary.json')
                self.assertNotEqual(disk,value)
                self.assertEqual(disk['execution']['matrix']['qkv_reduction_profile']['ranges'],[[0,1024],[1024,1536]])
                return value
            entry=types.SimpleNamespace(prepare=prepare,run=execute,source_hashes=lambda **kw:SOURCES)
            with patch.object(run,'expected_entry_sources',return_value=SOURCES),patch.object(run,'check_context',return_value=FROZEN),patch.object(admission,'verify_setup',return_value=identity),patch.object(admission,'revalidate',side_effect=lambda x:calls.append(('revalidate',None,None))),patch.object(run.importlib,'import_module',return_value=entry),patch.object(run.launch,'bind_snapshot',side_effect=control_only_bind):
                result=run.numeric(ctx,private,deadline_ns=ctx['deadline_ns'])
            self.assertEqual([x[0] for x in calls],['prepare','revalidate','run','revalidate'])
            self.assertEqual(calls[2][2],dict(wall_budget=2400,enable_raw_kv=True,fresh_profile=True))
            self.assertEqual(calls[0][2]['rows'],128);self.assertIsNone(calls[0][1][2]);self.assertIsNone(calls[0][1][3])
            self.assertEqual(result['status'],run.PASS)

    def test_original_nested_tuple_report_matches_its_real_json_serialization(self):
        value=actual();value['execution']['matrix']=original_profile_report()
        raw=original_report_bytes(value);disk=run.assets.json_bytes(raw)
        self.assertNotEqual(disk,value)
        self.assertEqual(run.canonical_actual(value),disk)
        self.assertIs(type(value['execution']['matrix']['qkv_reduction_profile']['ranges']),tuple)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'summary.json';path.write_bytes(raw)
            self.assertEqual(run.check_actual_json(path,value,SOURCES),run.assets.sha(raw))

    def test_actual_json_equality_rejects_boolean_integer_and_float_aliases(self):
        for runtime,disk_value in ((True,1),(False,0),(1,1.0)):
            with self.subTest(runtime=runtime,disk_value=disk_value),tempfile.TemporaryDirectory() as tmp:
                value=actual();value['serialization_probe']={'nested':(runtime,)}
                disk=run.assets.json_bytes(original_report_bytes(value))
                disk['serialization_probe']['nested'][0]=disk_value
                # Ordinary Python equality would hide this metadata drift.
                self.assertEqual(disk,run.assets.json_bytes(original_report_bytes(value)))
                path=Path(tmp)/'summary.json';path.write_bytes(original_report_bytes(disk))
                with self.assertRaises(ValueError):run.check_actual_json(path,value,SOURCES)
        for side in ('runtime','disk'):
            with self.subTest(side=side),tempfile.TemporaryDirectory() as tmp:
                value=actual();disk=copy.deepcopy(value)
                (value if side=='runtime' else disk)['enable_raw_kv']=1
                path=Path(tmp)/'summary.json';path.write_bytes(original_report_bytes(disk))
                with self.assertRaises(ValueError):run.check_actual_json(path,value,SOURCES)

    def test_canonical_actual_rejects_nonfinite_and_oversized_metadata(self):
        for item in (float('nan'),float('inf'),-float('inf')):
            with self.subTest(item=item),self.assertRaises((ValueError,TypeError)):
                run.canonical_actual({'nested':(item,)})
        with self.assertRaises(ValueError):run.canonical_actual({'oversized':'x'*(2*1024*1024)})

    def test_actual_json_hash_binds_the_same_bytes_that_were_compared(self):
        value=actual();value['execution']['matrix']=original_profile_report()
        raw=original_report_bytes(value)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'summary.json';path.write_bytes(raw);parse=run.assets.json_bytes
            def mutate(data,**kwargs):
                result=parse(data,**kwargs)
                if data==raw:path.write_bytes(b'{}')
                return result
            with patch.object(run.assets,'json_bytes',side_effect=mutate):
                self.assertEqual(run.check_actual_json(path,value,SOURCES),run.assets.sha(raw))
            self.assertNotEqual(run.assets.file_sha(path),run.assets.sha(raw))

    def test_late_numeric_failure_preserves_only_validated_actual_checkpoint(self):
        """CONTROL_ONLY entry fixtures exercise real numeric/resume failure paths."""
        from . import admission
        for failure in ('json','admission','source','validation'):
            def child(private,ctx,kw):
                write_json(private/'assets/SETUP.json',{'fixture_kind':'CONTROL_ONLY'})
                identity=types.SimpleNamespace(library_receipt=private/'library.json',manifest=private/'ASSETS.json',
                    manifest_sha256='3'*64,receipt_sha256=run.assets.file_sha(private/'assets/SETUP.json'))
                value=actual();value['execution']['matrix']=original_profile_report()
                value['private_details']='/private/SECRET raw_tensor=[1,2] https://signed'
                if failure=='validation':value['actual_dataflow_pass']=False
                snapshot={'source_sha256':SOURCES};revalidations=0;checks=0
                def prepare(*args,**kwargs):
                    write_json(private/'snapshot/SNAPSHOT.json',snapshot)
                    return private/'snapshot/SNAPSHOT.json',snapshot
                def execute(*args,**kwargs):
                    disk=copy.deepcopy(value)
                    if failure=='json':disk['execution']['matrix']['qkv_reduction_profile']['pair_reverse']=1
                    target=private/'actual/summary.json';target.parent.mkdir();target.write_bytes(original_report_bytes(disk))
                    return value
                def revalidate(*args):
                    nonlocal revalidations
                    revalidations+=1
                    if failure=='admission' and revalidations==2:raise ValueError('PRIVATE postflight drift')
                def check(*args,**kwargs):
                    nonlocal checks
                    checks+=1
                    if failure=='source' and checks==2:raise ValueError('PRIVATE source drift')
                    return FROZEN
                entry=types.SimpleNamespace(prepare=prepare,run=execute,source_hashes=lambda **kw:SOURCES)
                with patch.object(run,'check_context',side_effect=check),patch.object(admission,'verify_setup',return_value=identity),patch.object(admission,'revalidate',side_effect=revalidate),patch.object(run.importlib,'import_module',return_value=entry),patch.object(run.launch,'bind_snapshot',side_effect=control_only_bind):
                    run.numeric(ctx,private,deadline_ns=int(kw['extra_env']['QWEN2_PUBLIC_NUMERIC_DEADLINE_NS']))
                self.fail('injected failure did not reject the numerical child')
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as tmp:
                code,summary,calls,ctx,private,evidence=self.exercise(Path(tmp),child=child)
                self.assertEqual((code,summary['status']),(1,'FAILED'))
                self.assertFalse((private/'numeric.complete.json').exists())
                self.assertNotIn('actual_dataflow_pass',summary)
                if failure=='validation':
                    self.assertNotIn('validated_actual',summary)
                    self.assertFalse((private/'numeric.validated.json').exists())
                else:
                    partial=summary['validated_actual']
                    self.assertEqual(partial['status'],'VALIDATED_ACTUAL_POSTFLIGHT_INCOMPLETE')
                    self.assertIs(partial['postflight_complete'],False)
                    self.assertIs(partial['numerical_acceptance'],False)
                    self.assertEqual((partial['assigned_official_gates'],partial['observed_fields']),(27,28))
                    self.assertIs(partial['full_29_node_acceptance'],False)
                public=json.dumps(summary)+''.join(path.read_text() for path in evidence.iterdir())
                for text in ('SECRET','PRIVATE','/private/','raw_tensor','https://',tmp,run.PASS):
                    self.assertNotIn(text,public)

    def test_forged_or_noncanonical_validated_checkpoint_is_not_projected(self):
        mutations=(('postflight_complete',0),('numerical_acceptance',0),('rows',True),
            ('status',run.PASS),('launch_contract_sha256','f'*64),('setup_receipt_sha256','f'*64),
            ('snapshot_sha256','f'*64),('source_manifest_sha256','f'*64),
            ('actual_source_manifest_sha256','f'*64),('runtime_actual_sha256','not-a-hash'),
            ('private_payload','/private/SECRET raw_tensor=[1,2]'))
        for key,bad in mutations:
            def child(private,ctx,kw):
                write_json(private/'assets/SETUP.json',{'fixture_kind':'CONTROL_ONLY'})
                write_json(private/'snapshot/SNAPSHOT.json',bound_snapshot(ctx,run.assets.file_sha(private/'assets/SETUP.json')))
                value=dict(run.validate_actual(actual(),SOURCES),schema=1,
                    status='VALIDATED_ACTUAL_POSTFLIGHT_INCOMPLETE',rows=128,enable_raw_kv=True,fresh_profile=True,
                    postflight_complete=False,numerical_acceptance=False,
                    runtime_actual_sha256=run.assets.sha(run.assets.encoded(actual())),
                    launch_contract_sha256=ctx['contract_sha256'],
                    setup_receipt_sha256=run.assets.file_sha(private/'assets/SETUP.json'),
                    snapshot_sha256=run.assets.file_sha(private/'snapshot/SNAPSHOT.json'),
                    source_manifest_sha256=run.assets.sha(run.assets.encoded(SOURCES)),
                    actual_source_manifest_sha256=run.assets.sha(run.assets.encoded(SOURCES)))
                value[key]=bad;write_json(private/'numeric.validated.json',value)
                raise RuntimeError('CONTROL_ONLY injected postflight failure')
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                code,summary,calls,ctx,private,evidence=self.exercise(Path(tmp),child=child)
                self.assertEqual((code,summary['status']),(1,'FAILED'))
                self.assertNotIn('validated_actual',summary)
                self.assertFalse((private/'numeric.complete.json').exists())
                public=json.dumps(summary)+''.join(path.read_text() for path in evidence.iterdir())
                for text in ('SECRET','/private/','raw_tensor',run.PASS):self.assertNotIn(text,public)

    def test_real_term_resistant_child_is_reaped_inside_same_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);(private/'logs').mkdir();(private/'tmp').mkdir();pidfile=private/'pid'
            script='import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('+repr(str(pidfile))+').write_text(str(os.getpid()));time.sleep(30)'
            with patch.object(run,'TOTAL',1),patch.object(run,'GRACE',.1),patch.object(run,'RECEIPT',.05):
                start=time.monotonic_ns();budget=run.Budget(start,start+10**9)
                try:
                    with self.assertRaises(subprocess.TimeoutExpired):budget.command([sys.executable,'-c',script],private=private,cwd=private,phase='numeric',cap=.3)
                finally:budget.close()
            pid=int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):os.killpg(pid,0)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_numeric_postflight_cannot_escape_same_numeric_deadline(self):
        original=run.safe_numeric_receipt
        for kind in ('receipt','source'):
            checks=0
            def check(*args,**kwargs):
                nonlocal checks
                checks+=1
                if kind=='source' and checks==3:time.sleep(.5)
                return FROZEN
            def slow(*args,**kwargs):
                if kind=='receipt':time.sleep(.5)
                return original(*args,**kwargs)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp,patch.object(run,'NUMERIC_BUDGET',.18),patch.object(run,'GRACE',.03),patch.object(run,'RECEIPT',.02),patch.object(run,'safe_numeric_receipt',side_effect=slow):
                start=time.monotonic();code,summary,*_=self.exercise(Path(tmp),check=check)
                self.assertEqual((code,summary['status']),(1,'TIMEOUT'))
                self.assertLess(time.monotonic()-start,.45)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_setup_diagnostic_projection_keeps_cause_without_private_extra_fields(self):
        value=dict(status='SETUP_FAILED',phase='acquisition',reason='phase_failed',
            diagnostic=dict(phase='acquisition',exception='ValueError',frames=[dict(source='original.py',line=7)]),
            error='/private/path https://signed raw_tensor=[1,2]')
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),setup_result=(1,value))
            self.assertEqual(code,1);self.assertEqual(summary['setup_phase'],'acquisition')
            self.assertEqual(summary['diagnostic']['exception'],'ValueError')
            self.assertNotIn('/private/path',json.dumps(summary))
        bad=copy.deepcopy(value);bad['diagnostic']['payload']='SECRET'
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),setup_result=(1,bad))
            self.assertEqual(code,1);self.assertNotIn('SECRET',json.dumps(summary))

    def test_numeric_failure_diagnostic_is_bounded_and_allowlisted(self):
        for malicious in (False,True):
            def child(private,ctx,kw):
                value=dict(phase='numeric',exception='ValueError',frames=[dict(source='original.py',line=8)])
                if malicious:value.update(error='/private SECRET',payload=[1,2])
                write_json(private/'numeric.failure.json',value)
                error=RuntimeError('PRIVATE RAW');error.exit_code=1;raise error
            with self.subTest(malicious=malicious),tempfile.TemporaryDirectory() as tmp:
                code,summary,*_=self.exercise(Path(tmp),child=child)
                self.assertEqual(code,1);self.assertEqual(summary['diagnostic']['exit_code'],1)
                self.assertEqual(summary['diagnostic']['exception'],'RuntimeError' if malicious else 'ValueError')
                for text in ('PRIVATE','SECRET','/private','payload'):self.assertNotIn(text,json.dumps(summary))

    def test_mutually_forged_empty_actual_source_maps_are_rejected(self):
        def child(private,ctx,kw):
            result=complete(private,ctx)
            value=actual();value['source_sha256']={};value['source_sha256_after']={}
            write_json(private/'actual/summary.json',value);write_json(private/'snapshot/SNAPSHOT.json',bound_snapshot(ctx,run.assets.file_sha(private/'assets/SETUP.json'),{'source_sha256':{}}))
            result.update(actual_receipt_sha256=run.assets.file_sha(private/'actual/summary.json'),
                snapshot_sha256=run.assets.file_sha(private/'snapshot/SNAPSHOT.json'),
                actual_source_manifest_sha256=run.assets.sha(run.assets.encoded({})))
            write_json(private/'numeric.complete.json',result);return 0
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),child=child)
            self.assertNotEqual(code,0);self.assertNotEqual(summary['status'],run.PASS)

    def test_launch_contract_delegation_binds_loaded_runner_and_full_closure(self):
        originals={'input%d.py'%i:'1'*64 for i in range(run.launch.SOURCE_COUNT-2)}
        originals[run.OWN[0]]=run.IMPORTED_SHA256
        generated={name:'f'*64 for name in list(originals)[:run.launch.GENERATED_COUNT]}
        sources=dict(originals);sources[run.CONTRACT]='2'*64
        frozen=dict(contract_sha256='2'*64,sources=sources,original_sources=originals,
            generated=generated,git_blobs={name:'a'*40 for name in sources},inputs=sources)
        with patch.object(run.launch,'contract_snapshot',return_value=frozen) as called:
            result=run.contract_snapshot()
            called.assert_called_once_with(composed=False)
            self.assertEqual(result['sources'],sources)
            self.assertEqual(run.expected_entry_sources(result),sources)
        composed=copy.deepcopy(frozen);composed['sources'].update(generated)
        with patch.object(run.launch,'contract_snapshot',return_value=composed):
            self.assertEqual(run.contract_snapshot(composed=True)['sources'],composed['sources'])
        for mutate in (lambda v:v['sources'].pop('input0.py'),
                       lambda v:v['sources'].__setitem__(run.OWN[0],'f'*64),
                       lambda v:v['git_blobs'].pop(run.CONTRACT),
                       lambda v:v['sources'].__setitem__(run.CONTRACT,'f'*64)):
            bad=copy.deepcopy(frozen);mutate(bad)
            with self.subTest(bad=bad),patch.object(run.launch,'contract_snapshot',return_value=bad):
                with self.assertRaises(ValueError):run.contract_snapshot()

    def test_snapshot_binding_requires_all_five_exact_fields(self):
        ctx=dict(checkout_commit=COMMIT,contract_sha256='2'*64)
        good=bound_snapshot(ctx,'4'*64)
        run.validate_snapshot_binding(good,ctx,'4'*64)
        variants=[{},dict(good,**{run.launch.SNAPSHOT_KEY:None})]
        for key in good[run.launch.SNAPSHOT_KEY]:
            for mode in ('missing','different','bool'):
                bad=copy.deepcopy(good)
                if mode=='missing':del bad[run.launch.SNAPSHOT_KEY][key]
                else:bad[run.launch.SNAPSHOT_KEY][key]=False if mode=='bool' else 'f'*64
                variants.append(bad)
        bad=copy.deepcopy(good);bad[run.launch.SNAPSHOT_KEY]['payload']='/private/SECRET';variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                run.validate_snapshot_binding(bad,ctx,'4'*64)

    def test_m16_actual_receipt_cannot_satisfy_m128_profile(self):
        value=actual();value['rows']=16
        with self.assertRaises(ValueError):run.validate_actual(value,SOURCES)
        self.assertEqual((run.SETUP_BUDGET,run.WALL_BUDGET,run.NUMERIC_BUDGET,run.TOTAL),(900,2400,2430,3420))

    def test_bootstrap_clone_and_reexec_preserve_origin_without_global_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);commands=[]
            def command(budget,argv,**kw):commands.append((argv,kw));return 0
            with patch.object(run,'contract_snapshot',return_value=FROZEN),patch.object(run,'git_identity'),patch.object(run.Budget,'command',command),patch.object(run.os,'chdir') as chdir,patch.object(run.os,'execve',side_effect=RuntimeError('test intercepted exec')) as execve:
                code,summary=run.bootstrap(root/'private',root/'safe',COMMIT)
            self.assertEqual(code,1)
            self.assertEqual(commands[0][0][:4],['git','clone','--no-local','--no-checkout'])
            self.assertEqual(commands[1][0][-2:],['--detach',COMMIT])
            self.assertIn('--internal-compose',commands[2][0])
            ctx=json.loads((root/'private/context.json').read_text())
            self.assertEqual(ctx['deadline_ns']-ctx['started_ns'],3420*10**9)
            self.assertIn('--resume',execve.call_args.args[1])
            self.assertEqual(execve.call_args.args[1][-1],run.assets.file_sha(root/'private/context.json'))
            chdir.assert_called_once_with(root/'private/checkout')
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_missing_launch_contract_fails_before_clone_or_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(run.launch,'contract_snapshot',side_effect=FileNotFoundError),patch.object(run,'git_identity') as git,patch.object(run.Budget,'command') as child:
                code,summary=run.bootstrap(root/'private',root/'safe',COMMIT)
            self.assertNotEqual(code,0);git.assert_not_called();child.assert_not_called()
            self.assertFalse((root/'private').exists());self.assertFalse((root/'safe').exists())

    def test_git_environment_disallows_lazy_network_and_inherited_config(self):
        with patch.dict(os.environ,{'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'url.bad.insteadOf','GIT_CONFIG_VALUE_0':'file:'}):
            env=run.environment(Path('/unused'))
        self.assertNotIn('GIT_CONFIG_COUNT',env);self.assertEqual(env['GIT_ALLOW_PROTOCOL'],'file')
        self.assertEqual(env['GIT_NO_LAZY_FETCH'],'1');self.assertEqual(env['GIT_TERMINAL_PROMPT'],'0')

    def test_original_public_acceptance_execution_and_budget_ast_are_unchanged(self):
        prefix='candidates/qwen2_resident_matrix/raw_kv_public_m128_run/'
        contract=run.assets.read_json(run.ROOT/(prefix+'launch-contract.json'))
        raw=(run.ROOT/(prefix+'run_ci.py')).read_bytes()
        self.assertEqual(run.assets.sha(raw),contract['source_sha256'][prefix+'run_ci.py'])
        original=ast.parse(raw);current=ast.parse(Path(run.__file__).read_bytes())
        names={'validate_actual','canonical_actual','check_actual_json','numeric','Budget'}
        def selected(tree):
            return {node.name:ast.dump(node) for node in tree.body
                    if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names}
        self.assertEqual(set(selected(original)),names)
        # Strip only the exact additive diagnostic context managers. All original
        # arithmetic calls, checks, receipt writes, ordering and budgets must match.
        class StripDiagnostics(ast.NodeTransformer):
            def visit_With(self,node):
                self.generic_visit(node)
                if len(node.items)!=1:return node
                item=node.items[0];call=item.context_expr
                if not isinstance(call,ast.Call):return node
                signature=ast.unparse(call)
                if signature=="numeric_progress.session(private, context, before['sources'])":
                    self.assert_session=ast.dump(item.optional_vars)==ast.dump(ast.Name(id='progress',ctx=ast.Store()))
                    if not self.assert_session:raise ValueError('diagnostic binding drift')
                    return node.body
                if isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=='progress':
                    if (call.func.attr!='phase' or item.optional_vars is not None or call.keywords or len(call.args)!=1
                            or not isinstance(call.args[0],ast.Constant) or call.args[0].value not in run.numeric_progress.PHASES):
                        raise ValueError('diagnostic scope drift')
                    return node.body
                return node
        current=StripDiagnostics().visit(current)
        self.assertEqual(selected(current),selected(original))

    def test_safe_receipt_parses_the_exact_actual_and_snapshot_bytes_it_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            private=Path(d);ctx=dict(checkout_commit=COMMIT,contract_sha256=FROZEN['contract_sha256'])
            complete(private,ctx)
            original_read=run.read_bytes;original_json=run.assets.read_json
            def metadata(path,**kwargs):
                self.assertEqual(Path(path).name,'numeric.complete.json')
                return original_json(path,**kwargs)
            with patch.object(run,'expected_entry_sources',return_value=SOURCES), \
                 patch.object(run.assets,'read_json',side_effect=metadata), \
                 patch.object(run,'read_bytes',wraps=original_read) as reads:
                self.assertEqual(run.safe_numeric_receipt(private,ctx,FROZEN)['status'],run.PASS)
                self.assertEqual([call.args[0] for call in reads.call_args_list],
                    [private/'actual/summary.json',private/'snapshot/SNAPSHOT.json'])
            for target in (private/'actual/summary.json',private/'snapshot/SNAPSHOT.json'):
                def drift(path,limit=2*1024*1024):
                    raw=original_read(path,limit)
                    return raw+b' ' if Path(path)==target else raw
                with self.subTest(target=target.name),patch.object(run,'expected_entry_sources',return_value=SOURCES), \
                     patch.object(run,'read_bytes',side_effect=drift),self.assertRaises(ValueError):
                    run.safe_numeric_receipt(private,ctx,FROZEN)

    def test_workflow_has_exactly_two_sequential_cpu_only_placements(self):
        raw=(run.ROOT/run.WORKFLOW).read_text()
        self.assertEqual(re.findall(r'^  ([a-z0-9-]+):$',raw.split('jobs:\n',1)[1],re.M),['placement-1','placement-2'])
        first,second=raw.split('  placement-1:\n',1)[1].split('  placement-2:\n')
        self.assertIn("paths: ['"+run.WORKFLOW+"']",raw)
        self.assertIn("    needs: placement-1\n    if: always() && github.run_attempt == 1 && needs.placement-1.result == 'success' && needs.placement-1.outputs.status == 'CPU_UNSUITABLE'\n",second)
        prefix='work/'+Path(run.WORKFLOW).stem
        for index,job in enumerate((first,second),1):
            self.assertIn('timeout-minutes: 60',job);self.assertIn('timeout-minutes: 59',job)
            self.assertIn('timeout-minutes: 2',job);self.assertIn('runs-on: ubuntu-24.04',job)
            self.assertIn('--placement-status',job);self.assertIn('continue-on-error: true',job)
            paths=[line.strip() for line in job.splitlines() if line.strip().startswith(prefix+'-')]
            self.assertEqual(paths,[prefix+'-safe/'+name for name in run.OUTPUTS])
            self.assertNotIn('pip install',job);self.assertNotIn(prefix+'-private/',job)
            allowed=('if [ "$status" = "CPU_UNSUITABLE" ]; then exit 0; fi\n' if index==1 else '')+'test "$status" = "'+run.PASS+'"'
            self.assertIn(allowed,job.replace('\n          ','\n'))
            for status in ('CPU_UNSUITABLE',run.PASS,'PASS_NATIVE_QKV_QK_M16_M128','FAILED','TIMEOUT','NOT_RUN'):
                result=subprocess.run(['sh','-c','status='+status+'; '+allowed],capture_output=True,timeout=2)
                self.assertEqual(result.returncode,0 if status==run.PASS or index==1 and status=='CPU_UNSUITABLE' else 1)


class CpuPlacementTests(unittest.TestCase):
    def fixture(self,out,*,passed=False):
        sources=dict(SOURCES,**{run.OWN[0]:run.IMPORTED_SHA256,run.CONTRACT:'2'*64})
        generated={'original.py':'f'*64}
        frozen=dict(contract_sha256='2'*64,sources=sources,
            original_sources={k:v for k,v in sources.items() if k!=run.CONTRACT},
            generated=generated,git_blobs={k:'b'*40 for k in sources})
        summary=run.summary_new(time.monotonic_ns())
        summary.update(status=run.PASS if passed else 'CPU_UNSUITABLE',elapsed_seconds=.5,
            phase='finalize' if passed else 'cpu_qualification',checkout_commit=COMMIT,
            launch_contract_sha256=frozen['contract_sha256'],cpu_eligibility=cpu_record(eligible=passed))
        if passed:
            for key in run.STARTED+('postflight_complete','numerical_acceptance'):summary[key]=True
            summary.update(assigned_official_gates=27,observed_fields=28,full_29_node_acceptance=False,
                native_acceptance='PASS_OBSERVED_ONLY',actual_dataflow_pass=True,fixed_arithmetic_pass=True,
                setup_receipt_sha256='3'*64,actual_receipt_sha256='4'*64,snapshot_sha256='5'*64)
            identity=run.assets.sha(run.assets.encoded(dict(sources,**generated)))
            summary.update(source_manifest_sha256=identity,actual_source_manifest_sha256=identity)
        else:summary['diagnostic']=run.diagnostic(run.CpuUnsuitable(),'cpu_qualification',sources)
        source=dict(schema=1,launch_contract_sha256=frozen['contract_sha256'],source_sha256=sources,generated_sha256=generated)
        write_json(out/'source_hashes.json',source);run.publish(out,summary)
        return summary,source,frozen

    def test_required_intersection_and_amx_union_across_processors(self):
        self.assertEqual(run.CPU_FLAGS,('avx512f','avx512vl','avx512bw','avx512dq','fma','avx512_bf16'))
        self.assertEqual(run.CPU_EXCLUDED,('amx_tile','amx_bf16','amx_int8'))
        result=cpu_record();self.assertEqual(result['status'],'ELIGIBLE_FOR_BACKEND_CHECK')
        self.assertTrue(result['eligibility_only']);self.assertFalse(result['backend_qualified'])
        for flag in run.CPU_FLAGS:
            partial=tuple(f for f in run.CPU_FLAGS if f!=flag)
            value=run.cpu_eligibility(cpu_bytes(run.CPU_FLAGS,partial),system='Linux',machine='x86_64',override_absent=True)
            self.assertEqual(value['status'],'CPU_UNSUITABLE');self.assertFalse(value['flags'][flag])
        for flag in run.CPU_EXCLUDED:
            for records in ((run.CPU_FLAGS,(*run.CPU_FLAGS,flag)),((*run.CPU_FLAGS,flag),run.CPU_FLAGS)):
                value=run.cpu_eligibility(cpu_bytes(*records),system='Linux',machine='x86_64',override_absent=True)
                self.assertEqual(value['status'],'CPU_UNSUITABLE');self.assertTrue(value['excluded_flags'][flag])
                self.assertTrue(all(value['flags'].values()))
        self.assertNotIn('CONTROL_ONLY',json.dumps(result))

    def test_cpu_parser_and_schema_reject_malformed_or_noncanonical_data(self):
        raw=cpu_bytes()
        for bad in (b'',raw.decode(),b'\xff',raw+b'\x00',b'x'*(run.CPU_LIMIT+1),
                    raw.replace(b'processor : 0',b'processor : 00'),raw+b'\nflags : avx512f',
                    raw+b'\nno colon',raw.replace(b'flags :',b'absent :'),raw+b'\n\n'+raw,
                    raw.replace(b'fma',b'fma fma'),raw.replace(b'fma',b'FMA'),
                    cpu_bytes(*([run.CPU_FLAGS]*4097)),cpu_bytes(tuple('flag'+str(i) for i in range(4097)))):
            with self.subTest(size=len(bad)),self.assertRaises((ValueError,UnicodeError)):
                run.cpu_eligibility(bad,system='Linux',machine='x86_64',override_absent=True)
        for system,machine,override in (('Darwin','x86_64',True),('Linux','aarch64',True),('Linux','x86_64',False),('Linux','x86_64',1)):
            with self.assertRaises(ValueError):run.cpu_eligibility(raw,system=system,machine=machine,override_absent=override)
        good=cpu_record()
        for key,bad in (('schema',True),('processor_records',True),('processor_records',4097),
                        ('eligibility_only',1),('backend_qualified',0),('status','CPU_UNSUITABLE'),('extra','SECRET')):
            with self.subTest(key=key),self.assertRaises(ValueError):run.validate_cpu_eligibility(dict(good,**{key:bad}))
        for group in ('flags','excluded_flags'):
            changed=copy.deepcopy(good);changed[group][next(iter(changed[group]))]=1
            with self.assertRaises(ValueError):run.validate_cpu_eligibility(changed)
            changed=copy.deepcopy(good);changed[group]['foreign']=False
            with self.assertRaises(ValueError):run.validate_cpu_eligibility(changed)

    def test_cpu_read_and_timer_are_bounded_and_late_miss_is_timeout(self):
        opened=mock_open(read_data=cpu_bytes());summary={}
        with patch.object(run,'open',opened,create=True),patch.object(run.platform,'system',return_value='Linux'), \
             patch.object(run.platform,'machine',return_value='x86_64'),patch.dict(os.environ,{},clear=True):
            run.qualify_cpu(summary)
        opened.assert_called_once_with('/proc/cpuinfo','rb');opened().read.assert_called_once_with(run.CPU_LIMIT+1)
        with patch.object(run,'open',mock_open(read_data=cpu_bytes()),create=True),patch.object(run.platform,'system',return_value='Linux'), \
             patch.object(run.platform,'machine',return_value='x86_64'),patch.dict(os.environ,{'ATEN_CPU_CAPABILITY':''}),self.assertRaises(ValueError):
            run.qualify_cpu({})
        for end in (12*10**9,100*10**9):
            budget=Mock(end=end)
            with patch.object(run.time,'monotonic_ns',return_value=10*10**9),patch.object(run,'qualify_cpu',return_value=cpu_record()):
                run.run_cpu_qualification({},budget)
            self.assertEqual(budget.arm.call_args_list,[unittest.mock.call(min(end,15*10**9)),unittest.mock.call()])
        for error in (None,run.CpuUnsuitable()):
            budget=Mock(end=100*10**9);budget.remaining.side_effect=TimeoutError()
            with patch.object(run.time,'monotonic_ns',return_value=10*10**9),patch.object(run,'qualify_cpu',side_effect=error,return_value=cpu_record()),self.assertRaises(TimeoutError):
                run.run_cpu_qualification({},budget)
            budget.remaining.assert_called_once_with(15*10**9)

    def test_cpu_miss_is_after_sources_git_and_evidence_before_any_work(self):
        for kind in ('unfit','malformed','late'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);events=[]
                def qualify(summary):
                    self.assertEqual(events,['sources','git'])
                    self.assertEqual({p.name for p in (root/'safe').iterdir()},set(run.OUTPUTS))
                    summary['phase']='cpu_qualification'
                    if kind=='malformed':raise ValueError('SECRET cpu payload')
                    summary['cpu_eligibility']=cpu_record(eligible=False)
                    if kind=='late':time.sleep(.04)
                    raise run.CpuUnsuitable()
                with patch.object(run,'contract_snapshot',side_effect=lambda:(events.append('sources'),FROZEN)[1]), \
                     patch.object(run,'git_identity',side_effect=lambda *a:events.append('git')), \
                     patch.object(run,'qualify_cpu',side_effect=qualify),patch.object(run.Budget,'command') as command, \
                     patch.object(run.setup,'run') as setup_call,patch.object(run,'numeric') as numeric_call, \
                     patch.object(run,'CPU_SECONDS',.02 if kind=='late' else 5):
                    code,summary=run.bootstrap(root/'private',root/'safe',COMMIT)
                command.assert_not_called();setup_call.assert_not_called();numeric_call.assert_not_called()
                self.assertEqual((code,summary['status']),(2,'CPU_UNSUITABLE') if kind=='unfit' else (1,'TIMEOUT' if kind=='late' else 'FAILED'))
                self.assertTrue(all(summary[key] is False for key in run.STARTED+('postflight_complete','numerical_acceptance')))
                self.assertFalse((root/'private/checkout').exists());self.assertFalse((root/'private/assets').exists())
                self.assertNotIn('SECRET',json.dumps(summary));self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        with tempfile.TemporaryDirectory() as d,patch.object(run,'contract_snapshot',side_effect=ValueError), \
             patch.object(run,'qualify_cpu') as cpu:
            self.assertEqual(run.bootstrap(Path(d)/'private',Path(d)/'safe',COMMIT)[0],1);cpu.assert_not_called()

    def test_placement_cpu_only_exact_source_git_status_and_false_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);good,source,frozen=self.fixture(out)
            with patch.object(run,'contract_snapshot',return_value=frozen),patch.object(run,'git_identity') as git:
                self.assertEqual(run.placement_status(out,COMMIT,'failure'),'CPU_UNSUITABLE')
                git.assert_called_once_with(COMMIT,frozen['git_blobs'],out)
                for key,bad in (('schema',True),('profile','foreign'),('checkout_commit','b'*40),('launch_contract_sha256','0'*64),
                    ('phase','setup'),('cpu_eligibility',cpu_record()),('elapsed_seconds',True),('elapsed_seconds',float('inf')),
                    ('elapsed_seconds',-1),('elapsed_seconds',3421),('extra','SECRET'))+tuple((key,True) for key in run.STARTED+('postflight_complete','numerical_acceptance')):
                    changed=copy.deepcopy(good);changed[key]=bad
                    if key=='elapsed_seconds' and bad==float('inf'):
                        (out/'summary.json').write_text(json.dumps(changed))
                    else:run.publish(out,changed)
                    with self.subTest(key=key),self.assertRaises(ValueError):run.placement_status(out,COMMIT,'failure')
                run.publish(out,good)
                for outcome in ('success','cancelled','skipped',True):
                    with self.assertRaises(ValueError):run.placement_status(out,COMMIT,outcome)
                for key,bad in (('schema',True),('launch_contract_sha256','0'*64),('source_sha256',{}),('generated_sha256',{})):
                    write_json(out/'source_hashes.json',dict(source,**{key:bad}))
                    with self.assertRaises(ValueError):run.placement_status(out,COMMIT,'failure')
                write_json(out/'source_hashes.json',source)
            changed=copy.deepcopy(frozen);changed['sources'][run.OWN[0]]='0'*64
            with patch.object(run,'contract_snapshot',return_value=changed),patch.object(run,'git_identity') as git,self.assertRaises(ValueError):
                run.placement_status(out,COMMIT,'failure')
            git.assert_not_called()

    def test_placement_missing_extra_symlink_progress_or_diagnostic_cannot_retry(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);good,source,frozen=self.fixture(out)
            with patch.object(run,'contract_snapshot',return_value=frozen),patch.object(run,'git_identity'):
                for name in run.OUTPUTS:
                    path=out/name;raw=path.read_bytes();path.unlink()
                    with self.assertRaises(ValueError):run.placement_status(out,COMMIT,'failure')
                    path.symlink_to('missing')
                    with self.assertRaises((ValueError,OSError)):run.placement_status(out,COMMIT,'failure')
                    path.unlink();path.write_bytes(raw)
                (out/'private.log').write_text('SECRET')
                with self.assertRaises(ValueError):run.placement_status(out,COMMIT,'failure')
                (out/'private.log').unlink()
                for changed in (dict(good,diagnostic=dict(phase='cpu_qualification',exception='ValueError',frames=[])),
                    dict(good,diagnostic=dict(phase='cpu_qualification',exception='OtherError',frames=[dict(source='foreign.py',line=1)])),
                    dict(good,clone_started=0)):
                    run.publish(out,changed)
                    with self.assertRaises(ValueError):run.placement_status(out,COMMIT,'failure')
                run.publish(out,good);progress=run.assets.read_json(out/'progress.json');progress['status']='RUNNING';write_json(out/'progress.json',progress)
                with self.assertRaises(ValueError):run.placement_status(out,COMMIT,'failure')

    def test_placement_success_is_only_exact_complete_public_pass(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);good,source,frozen=self.fixture(out,passed=True)
            with patch.object(run,'contract_snapshot',return_value=frozen),patch.object(run,'git_identity'):
                self.assertEqual(run.placement_status(out,COMMIT,'success'),run.PASS)
                with self.assertRaises(ValueError):run.placement_status(out,COMMIT,'failure')
                for key,bad in (('assigned_official_gates',26),('observed_fields',True),('source_manifest_sha256','0'*64),
                    ('actual_source_manifest_sha256','0'*64),('actual_receipt_sha256','bad'),('phase','numeric'),
                    ('cpu_eligibility',cpu_record(eligible=False)),('numerical_acceptance',1)):
                    run.publish(out,dict(good,**{key:bad}))
                    with self.subTest(key=key),self.assertRaises(ValueError):run.placement_status(out,COMMIT,'success')
                for status in ('PASS','PASS_NATIVE_QKV_QK_M16_M128','VALIDATED_ACTUAL_POSTFLIGHT_INCOMPLETE','FAILED','TIMEOUT','INTERRUPTED','NOT_RUN'):
                    run.publish(out,dict(good,status=status,postflight_complete=False,numerical_acceptance=False))
                    self.assertEqual(run.placement_status(out,COMMIT,'failure'),'FAILED')

    def test_eligible_setup_and_native_failures_never_allow_another_placement(self):
        for phase in ('environment','native16','native128'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as d:
                root=Path(d);out=root/'safe';out.mkdir();private=root/'private';private.mkdir()
                _,_,frozen=self.fixture(out,passed=True);ctx=context(private,out)
                with patch.object(run,'check_context',return_value=frozen), \
                     patch.object(run.setup,'run',return_value=(1,dict(status='SETUP_FAILED',phase=phase,reason='phase_failed'))), \
                     patch.object(run.Budget,'command') as numeric:
                    code,summary=run.resume(ctx,private,out)
                numeric.assert_not_called();self.assertEqual((code,summary['status']),(1,'FAILED'))
                self.assertTrue(summary['clone_started']);self.assertTrue(summary['setup_started'])
                self.assertFalse(summary['numeric_started'])
                with patch.object(run,'contract_snapshot',return_value=frozen),patch.object(run,'git_identity'):
                    self.assertEqual(run.placement_status(out,COMMIT,'failure'),'FAILED')

    def test_placement_cli_cannot_execute_or_accept_conflicting_modes(self):
        args=['--placement-status','--evidence','/CONTROL_ONLY/safe','--checkout-commit',COMMIT,'--attempt-outcome','failure']
        with patch.object(run,'placement_status',return_value='CPU_UNSUITABLE') as gate,patch.object(run,'bootstrap') as bootstrap,redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run.main(args),0);self.assertEqual(output.getvalue().strip(),'CPU_UNSUITABLE');bootstrap.assert_not_called()
        for extra in (['--execute'],['--resume'],['--internal-compose'],['--internal-numeric'],['--private','p'],['--context','c']):
            with patch.object(run,'placement_status') as gate,redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(run.main(args+extra),1);gate.assert_not_called()


class BackendProjectionTests(unittest.TestCase):
    def test_nested_diagnostic_only_on_environment_failure(self):
        with tempfile.TemporaryDirectory() as d:
            private=Path(d);(private/'assets').mkdir()
            value={'schema':1,'fixed':'CONTROL_ONLY'}
            (private/'assets/backend.failure.json').write_text(json.dumps(value))
            summary={'status':'FAILED','setup_phase':'environment'}
            with patch.object(run.launch,'validate_backend_failure',return_value=value) as check:
                run.project_backend_failure(summary,private,SOURCES)
                check.assert_called_once_with(value,SOURCES)
            self.assertEqual(summary['backend_preflight'],value)
            self.assertEqual(summary['status'],'FAILED')
            self.assertEqual(set(summary),{'status','setup_phase','backend_preflight'})
            with patch.object(run.launch,'validate_backend_failure',side_effect=ValueError('PRIVATE_DO_NOT_COPY')):
                rejected={'status':'FAILED','setup_phase':'environment'}
                run.project_backend_failure(rejected,private,SOURCES)
                self.assertEqual(rejected,{'status':'FAILED','setup_phase':'environment'})
            with patch.object(run.launch,'validate_backend_failure') as check:
                other={'status':'FAILED','setup_phase':'references'}
                run.project_backend_failure(other,private,SOURCES);check.assert_not_called()
                self.assertNotIn('backend_preflight',other)

    def test_nested_diagnostic_missing_large_or_symlink_does_not_mask_failure(self):
        with tempfile.TemporaryDirectory() as d:
            private=Path(d);(private/'assets').mkdir();path=private/'assets/backend.failure.json'
            for mode in ('missing','large','symlink'):
                if path.exists() or path.is_symlink():path.unlink()
                if mode=='large':path.write_text('x'*4097)
                if mode=='symlink':path.symlink_to(private/'missing')
                summary={'status':'FAILED','setup_phase':'environment'}
                run.project_backend_failure(summary,private,SOURCES)
                self.assertEqual(summary,{'status':'FAILED','setup_phase':'environment'})



class NativeProjectionTests(unittest.TestCase):
    def fixture(self,private,tokens=128,cause='budget'):
        from ..raw_kv_native_qk_run import phase
        from ..raw_kv_native_qk_run.test_phase import fixture,diagnostic_controls
        value,kw=fixture(tokens,cause)
        sources=dict(kw['source_sha256'],**{run.CONTRACT:'5'*64})
        kw.update(source_sha256=sources,generated_module_sha256=run.launch.GENERATED_MODULE_SHA256)
        value['identity']['runner_sha256']=run.launch.GENERATED_MODULE_SHA256
        workspace=private/'assets';name='native'+str(tokens);role='native_m16' if tokens==16 else 'native'
        # Only source bytes are real. All native receipt metadata is CONTROL_ONLY.
        from ..raw_kv_native_qk import prepare
        from ..raw_kv_native_qk_run import runtime
        generated=private/'gate_source';prepare.prepare(generated)
        runtime.apply_dispatch_patch(generated,{'sources':{runtime.DISPATCH_PATCH:phase.kernel.sha(runtime.read_source(runtime.DISPATCH_PATCH))}})
        gate=workspace/'generated/qwen2_layer0_model_gate.py';gate.parent.mkdir(parents=True)
        gate.write_bytes((generated/phase.kernel.ORIGINAL).read_bytes())
        if tokens==128:
            write_json(workspace/'native_m16/RESULT.json',{'fixture':'CONTROL_ONLY'})
            value['m16_gate_sha256']=run.assets.file_sha(workspace/'native_m16/RESULT.json')
        capture,cpu,environment,backend,payload=diagnostic_controls(tokens)
        write_json(workspace/'payload/manifest.json',payload)
        value['payload_manifest_sha256']=run.assets.file_sha(workspace/'payload/manifest.json')
        write_json(workspace/role/'RESULT.json',value)
        kw.update(result_sha256=run.assets.file_sha(workspace/role/'RESULT.json'),
            payload_manifest_sha256=value['payload_manifest_sha256'],m16_result_sha256=value['m16_gate_sha256'])
        report=phase.project_result(value,**kw)
        observation=phase.diagnostic_record({k:kw[k] for k in ('source_sha256','contract_sha256','generated_module_sha256')},
            tokens,kw['library'],kw['qkv_library'],capture,cpu,phase.backend_build(backend),environment,(value,report,payload))
        write_json(workspace/('phase_'+name+'.json'),report)
        write_json(workspace/('phase_'+name+'_diagnostics.json'),observation)
        return phase,kw,sources,report,observation

    def project(self,private,phase,kw,sources,tokens=128):
        summary={'status':'FAILED','setup_phase':'native'+str(tokens)}
        with patch.object(phase.kernel,'verify',return_value=kw['library']), \
             patch.object(phase.qkv_kernel,'verify',return_value=kw['qkv_library']):
            run.project_native_failure(summary,private,sources)
        return summary

    def test_both_failure_sizes_use_exact_generated_result_and_metadata_bytes(self):
        for tokens in (16,128):
            with self.subTest(tokens=tokens),tempfile.TemporaryDirectory() as d:
                private=Path(d);phase,kw,sources,report,observation=self.fixture(private,tokens)
                summary=self.project(private,phase,kw,sources,tokens)
                self.assertEqual(summary['status'],'FAILED')
                safe=summary['native_failure']
                self.assertEqual(safe['status'],'NATIVE_PRODUCER_FAILURE_DIAGNOSTIC')
                self.assertEqual(safe['report'],report)
                self.assertIs(safe['numerical_acceptance'],False)
                self.assertIs(safe['postflight_complete'],False)
                self.assertEqual(safe['diagnostics']['sha256'],run.assets.file_sha(private/('assets/phase_native'+str(tokens)+'_diagnostics.json')))
                self.assertEqual(safe['diagnostics']['capture']['bf16']['exec_records'],9)
                for secret in ('PRIVATE','DO_NOT_LEAK','/private/',d):self.assertNotIn(secret,json.dumps(safe))
                self.assertLessEqual(len(run.assets.encoded(safe)),24576)

    def test_numerical_pass_with_failed_setup_never_becomes_public_success(self):
        with tempfile.TemporaryDirectory() as d:
            private=Path(d);phase,kw,sources,report,observation=self.fixture(private,cause=None)
            summary=self.project(private,phase,kw,sources)
            self.assertEqual(summary['status'],'FAILED')
            self.assertTrue(summary['native_failure']['report']['native_acceptance'])
            self.assertFalse(summary['native_failure']['numerical_acceptance'])
            self.assertFalse(summary['native_failure']['actual_chain_executed'])

    def test_missing_malformed_large_symlink_stale_and_untyped_metadata_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            private=Path(d);phase,kw,sources,report,observation=self.fixture(private)
            path=private/'assets/phase_native128.json';raw=path.read_bytes()
            diag=private/'assets/phase_native128_diagnostics.json';diagraw=diag.read_bytes()
            result=private/'assets/native/RESULT.json';result_raw=result.read_bytes()
            gate=private/'assets/generated/qwen2_layer0_model_gate.py';gate_raw=gate.read_bytes()
            for mode in ('missing','malformed','large','symlink','source','contract','gate','result','bool','nonfinite','extra','diagnostics'):
                if path.exists() or path.is_symlink():path.unlink()
                path.write_bytes(raw);diag.write_bytes(diagraw);result.write_bytes(result_raw);gate.write_bytes(gate_raw)
                current=dict(sources)
                if mode=='missing':path.unlink()
                elif mode=='malformed':path.write_text('SECRET raw_tensor=[1,2]')
                elif mode=='large':path.write_bytes(b'x'*(phase.MAX_REPORT+1))
                elif mode=='symlink':path.unlink();path.symlink_to(private/'missing')
                elif mode=='source':current.pop(phase.SOURCE)
                elif mode=='contract':current[run.CONTRACT]='a'*64
                elif mode=='gate':gate.write_bytes(gate_raw+b' ')
                elif mode=='result':result.write_bytes(result_raw+b' ')
                elif mode in ('bool','nonfinite','extra'):
                    changed=copy.deepcopy(report)
                    if mode=='bool':changed['native_acceptance']=0
                    elif mode=='nonfinite':changed['bf16_stages']['q']['max_abs']=float('inf')
                    else:changed['secret']='PRIVATE /private/tensor'
                    path.write_text(json.dumps(changed))
                else:
                    changed=copy.deepcopy(observation);changed['result_sha256']='a'*64;write_json(diag,changed)
                with self.subTest(mode=mode):
                    summary=self.project(private,phase,kw,current)
                    self.assertEqual(summary,{'status':'FAILED','setup_phase':'native128',
                        'native_failure':{'status':'DIAGNOSTIC_UNAVAILABLE','numerical_acceptance':False}})

    def test_other_phases_never_read_native_artifacts(self):
        with patch.object(run,'read_bytes',side_effect=AssertionError('unexpected artifact read')):
            summary={'status':'FAILED','setup_phase':'references'}
            run.project_native_failure(summary,Path('/unused'),SOURCES)
        self.assertEqual(summary,{'status':'FAILED','setup_phase':'references'})

    def test_safe_summary_bound_covers_diagnostic_without_extra_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);summary={'schema':1,'status':'FAILED','phase':'setup','elapsed_seconds':1.0,
                'native_failure':{'CONTROL_ONLY':'x'*24576}}
            run.publish(out,summary)
            self.assertEqual(json.loads((out/'summary.json').read_text()),summary)
            self.assertEqual({p.name for p in out.iterdir()},{'summary.json','progress.json'})

if __name__=='__main__':unittest.main()
