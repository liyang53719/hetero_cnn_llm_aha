"""Cold stdlib-only tests. No original producer, payload or retained ELF is opened."""
from contextlib import ExitStack, nullcontext, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from . import launch as L, receipt as V, supervisor as S
from ..attention_packed_m16_assets import reuse as R


def scope():
    return dict(schema=1,profile=V.PROFILE,status=V.STATUS,rows=16,past_tokens=0,
        contract_sha256=R.PINS_SHA256,preparation_source_sha256=R.snapshot(),origin={},readonly={},
        origin_table={},origin_native_m16={},producers={},current_backend_verified=True,
        packed_source_profile_linked=False,ready_for_actual=False,elapsed_seconds=1,**R.contract()['claims'])


def ack():
    stdout='\n'.join(f'SOFTWARE_RECIPE_STAGE phase={i} name={name} values={16*width}'
        for i,(name,width) in enumerate(R.STAGES))+'\n'
    stdout+='SOFTWARE_RECIPE_COMPLETE tokens=16 stages=15\nSOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10\n'
    stdout+='CARRIED_LIFETIME readonly_exact=1 cache_prefix_exact=1 unused_sentinels_exact=1\n'
    return stdout,dict(phase_receipts_exactly_once_in_order=True,process_completion_ack=True,
        scope='software file/process contract only',hardware_ack_verified=False)


class ContractTests(unittest.TestCase):
    def test_frozen_contract(self):
        raw=(L.HERE/'contract.json').read_bytes()
        value=L.load_contract(R.sha(raw))
        self.assertEqual(value['asset_sources'],R.snapshot())
        self.assertEqual(value['work_seconds']+value['cleanup_seconds'],125)
        self.assertEqual(value['outer_seconds'],126)
    def test_wrong_contract_digest(self):
        with self.assertRaises(ValueError):L.load_contract('0'*64)
    def test_default_cli_never_executes(self):
        with patch.object(L,'load_contract',return_value={'asset_sources':{}}),patch.object(L,'launch') as run,redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(L.main(['--origin','/private/origin','--workspace','/private/output','--python','/fixture/python','--contract-sha256','a'*64]),0)
        run.assert_not_called()
        self.assertEqual(json.loads(stream.getvalue())['status'],'PLAN_ONLY_NO_EXECUTION')
    def test_bad_cli_contract_does_not_expose_paths(self):
        with patch.object(L,'load_contract',side_effect=ValueError('/private/SECRET PAYLOAD')),redirect_stdout(io.StringIO()) as stream:
            code=L.main(['--origin','/private/origin','--workspace','/private/output','--python','/fixture/python','--contract-sha256','/private/SECRET'])
        self.assertEqual(code,1)
        self.assertNotIn('SECRET',stream.getvalue());self.assertNotIn('/private',stream.getvalue())
        self.assertIsNone(json.loads(stream.getvalue())['contract_sha256'])
    def test_threads_and_minimal_environment(self):
        value=L.environment(Path('/private/control'),{'OMP_NUM_THREADS':'99','UNRELATED_SECRET':'secret'})
        self.assertTrue(all(value[k]=='4' for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')))
        self.assertNotIn('UNRELATED_SECRET',value);self.assertNotIn('ATEN_CPU_CAPABILITY',value)
    def test_runtime_overrides_rejected(self):
        for key in ('ATEN_CPU_CAPABILITY','LD_PRELOAD','LD_LIBRARY_PATH','PYTHONHOME','PYTHONPATH',
                    'ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR'):
            with self.subTest(key=key),self.assertRaises(ValueError):L.environment(Path('/tmp'),{key:'unreviewed'})
    def test_interpreter_regular_and_symlink_topology(self):
        with tempfile.TemporaryDirectory() as d:
            origin=Path(d);parent=origin/'private/assets/venv/bin';parent.mkdir(parents=True)
            binary=parent/'python3.12';binary.write_bytes(b'fixture interpreter only')
            (parent/'python').symlink_to('python3');(parent/'python3').symlink_to('python3.12')
            contract={'python':{'bytes':binary.stat().st_size,'sha256':R.file_hash(binary)}}
            self.assertEqual(L.interpreter(origin,contract,parent/'python'),parent/'python')
            binary.write_bytes(b'mutation')
            with self.assertRaises(ValueError):L.interpreter(origin,contract,parent/'python')
    def test_interpreter_hash_bound(self):
        with tempfile.TemporaryDirectory() as d:
            origin=Path(d);parent=origin/'private/assets/venv/bin';parent.mkdir(parents=True)
            (parent/'python').write_bytes(b'fixture')
            contract={'python':{'bytes':7,'sha256':'0'*64}}
            with self.assertRaises(ValueError):L.interpreter(origin,contract,parent/'python')
    def test_child_is_isolated_original_producer_only(self):
        self.assertIn('P.produce(origin,output,work_seconds=120)',L.CHILD)
        self.assertNotIn('download',L.CHILD);self.assertNotIn('build_library',L.CHILD)
        compile(L.CHILD,'<isolated-child>','exec')


class ReceiptTests(unittest.TestCase):
    def test_nonzero_exit_fails_before_artifact_read(self):
        with patch.object(R,'safe_path',side_effect=AssertionError('must not read')) as read:
            for code in (-9,1,True,None):
                with self.subTest(code=code),self.assertRaises(ValueError):
                    V.validate('/not/read','/not/read',child_returncode=code,sources={},origin_before={})
        read.assert_not_called()
    def test_preparation_scope_exact(self):
        value=scope();V.validate_scope(value,R.snapshot())
        for key in (*R.contract()['claims'],'ready_for_actual','packed_source_profile_linked'):
            changed=deepcopy(value);changed[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):V.validate_scope(changed,R.snapshot())
    def test_receipt_schema_type_and_source_fail_closed(self):
        value=scope()
        for key,new in (('schema',True),('rows',128),('past_tokens',1),('current_backend_verified',False),
                        ('elapsed_seconds',float('inf')),('preparation_source_sha256',{}),('status','READY_FOR_ACTUAL')):
            changed=deepcopy(value);changed[key]=new
            with self.subTest(key=key),self.assertRaises(ValueError):V.validate_scope(changed,R.snapshot())
        changed=deepcopy(value);changed['unexpected']='hidden'
        with self.assertRaises(ValueError):V.validate_scope(changed,R.snapshot())
    def test_timing_bounds(self):
        for value in (True,-1,121,float('nan'),'1'):
            with self.subTest(value=value),self.assertRaises(ValueError):V.seconds(value,120)
        V.seconds(120,120)
    def test_exact_ack(self):
        stdout,value=ack();V.validate_ack(stdout,value)
        for text in (stdout.replace('tokens=16','tokens=128'),stdout+stdout,stdout.replace('phase=1 ','phase=9 '),
                     stdout.replace('cache_prefix_exact=1','cache_prefix_exact=0')):
            with self.assertRaises(ValueError):V.validate_ack(text,value)
        value['hardware_ack_verified']=True
        with self.assertRaises(ValueError):V.validate_ack(stdout,value)
    def test_logical_and_token_major_exports_remain_distinct(self):
        self.assertEqual(R.shapes()['q'],[1,12,16,128]);self.assertEqual(R.export_shapes()['q'],[1,16,1536])
        self.assertEqual(R.shapes()['k'],[1,2,16,128]);self.assertEqual(R.export_shapes()['k'],[1,16,256])
        self.assertEqual(len(R.output_inventory()),22);self.assertEqual(len(R.shapes()),29)
    def test_safe_summary_allowlist(self):
        with patch.object(L.time,'monotonic',return_value=2):
            value=L.safe_summary('FAILED_CHILD','child',1,'a'*64,exit_code=-9,cleanup=True)
        self.assertEqual(set(value),{'schema','profile','status','phase','elapsed_seconds','contract_sha256',
            'numerical_acceptance','full_29_node_acceptance','ready_for_actual','child_exit_code','cleanup_complete'})
        self.assertFalse(value['ready_for_actual'])
    def test_failure_classifications_ignore_exception_text(self):
        for error,status in ((InterruptedError('/secret'),'CANCELLED'),(KeyboardInterrupt(),'CANCELLED'),
                            (TimeoutError('/secret'),'TIMED_OUT'),(ValueError('/secret'),'FAILED_CHILD')):
            self.assertEqual(L.classify(error,'child'),status)
        self.assertEqual(L.classify(ValueError('/secret'),'postflight'),'FAILED_RECEIPT')
    def test_safe_summary_invalid_public_status(self):
        for status in ('PASS_BF16_STAGE_BUDGET','/private/error'):
            with self.assertRaises(ValueError):L.safe_summary(status,'child',0,'a'*64)


def proc(pid,ppid,group=None,start=1):
    return dict(pid=pid,ppid=ppid,group=pid if group is None else group,start=start,state='S')


class SupervisorTests(unittest.TestCase):
    def test_transitive_descendants(self):
        table={1:proc(1,0),2:proc(2,1),3:proc(3,2),4:proc(4,0)}
        self.assertEqual(set(S.descendants(table,1)),{1,2,3})
    def test_subreaped_orphan_owned(self):
        child=S.Child(Mock(pid=10));table={10:proc(10,99),11:proc(11,99),12:proc(12,11),20:proc(20,90)}
        with patch.object(S,'process_table',return_value=table),patch.object(S.os,'getpid',return_value=99):
            self.assertEqual(set(child.observe()),{10,11,12})
    def test_pid_reuse_rejected(self):
        child=S.Child(Mock(pid=10))
        with patch.object(S,'process_table',side_effect=[{10:proc(10,99,start=1)},{10:proc(10,99,start=2)}]),patch.object(S.os,'getpid',return_value=99):
            child.observe()
            with self.assertRaises(ValueError):child.observe()
    def test_cannot_signal_launcher_group(self):
        child=S.Child(Mock(pid=10))
        with patch.object(child,'observe',return_value={10:proc(10,99,group=99)}),patch.object(S.os,'getpgrp',return_value=99),patch.object(S.os,'killpg') as kill:
            with self.assertRaises(ValueError):child.signal_groups(signal.SIGKILL)
        kill.assert_not_called()
    def test_term_primary_then_kill_all_groups(self):
        child=S.Child(Mock(pid=10));owned={10:proc(10,99),11:proc(11,10)}
        with patch.object(child,'observe',return_value=owned),patch.object(S.os,'getpgrp',return_value=99),patch.object(S.os,'killpg') as kill:
            child.signal_groups(signal.SIGTERM,primary_only=True)
            self.assertEqual(kill.call_args_list[0].args,(10,signal.SIGTERM))
            child.signal_groups(signal.SIGKILL)
            self.assertEqual({x.args for x in kill.call_args_list[1:]},{(10,signal.SIGKILL),(11,signal.SIGKILL)})
    def test_five_second_cleanup_reserve_before_fallback(self):
        child=S.Child(Mock(pid=10));clock=[120.0];signals=[]
        def kill(sig,**kwargs):signals.append((sig,clock[0]))
        def observe():return {} if len(signals)>1 else {10:proc(10,99)}
        with patch.object(S,'protected_cleanup',side_effect=lambda:nullcontext()),patch.object(S.time,'monotonic',side_effect=lambda:clock[0]),patch.object(S.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)),patch.object(child,'observe',side_effect=observe),patch.object(child,'reap'),patch.object(child,'signal_groups',side_effect=kill):
            self.assertTrue(child.terminate(126))
        self.assertEqual(signals[0],(signal.SIGTERM,120));self.assertGreaterEqual(signals[1][1],125)
        self.assertLess(signals[1][1],125.26);self.assertEqual(signals[1][0],signal.SIGKILL)
    def test_successful_child_cleanup_needs_no_kill(self):
        child=S.Child(Mock(pid=10))
        with patch.object(S,'protected_cleanup',side_effect=lambda:nullcontext()),patch.object(S.time,'monotonic',return_value=1),patch.object(child,'observe',side_effect=[{10:proc(10,99)},{}]),patch.object(child,'reap'),patch.object(child,'signal_groups') as signals:
            self.assertTrue(child.terminate(126))
        signals.assert_called_once_with(signal.SIGTERM,primary_only=True)
    def test_wait_deadline(self):
        child=S.Child(Mock(pid=10))
        with patch.object(child,'observe',return_value={}),patch.object(S.time,'monotonic',return_value=121):
            with self.assertRaises(TimeoutError):child.wait(120)
    def test_constructor_cannot_throw_after_spawn(self):
        with patch.object(S,'process_table',side_effect=AssertionError('no observation during assignment')):
            self.assertEqual(S.Child(Mock(pid=10)).tracked,{})


class MockedLaunchTests(unittest.TestCase):
    """Parent control flow only: Popen, original data reads and signals are mocked."""
    def run_failure(self,*,cancel_on_unblock=False,wait_error=None,cleanup=True,save_error=False):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            root=Path(d);origin=root/'origin';origin.mkdir();work=root/'new'
            contract={'asset_sources':{},'origin_commit':'fixture','python':{'sha256':'a'*64}}
            stack.enter_context(patch.object(L,'load_contract',return_value=contract))
            stack.enter_context(patch.object(L,'environment',return_value={}))
            stack.enter_context(patch.object(L,'interpreter',return_value=Path('/fixture/python')))
            stack.enter_context(patch.object(L,'interpreter_identity',return_value={'fixture':'private runtime paths'}))
            stack.enter_context(patch.object(L.R,'verify_reuse',return_value={'origin_commit':'fixture'}))
            stack.enter_context(patch.object(L.P,'deadline',side_effect=lambda n:nullcontext(120)))
            stack.enter_context(patch.object(L.P,'protected_cleanup',side_effect=lambda:nullcontext()))
            stack.enter_context(patch.object(L.supervisor,'enable_subreaper',return_value=object()))
            restore=stack.enter_context(patch.object(L.supervisor,'restore_subreaper'))
            process=Mock(pid=42)
            spawn=stack.enter_context(patch.object(L.subprocess,'Popen',return_value=process))
            child=Mock();child.wait.side_effect=wait_error or ValueError('/private/payload secret')
            child.terminate.return_value=cleanup
            construct=stack.enter_context(patch.object(L.supervisor,'Child',return_value=child))
            def mask(action,signals):
                if cancel_on_unblock and action==signal.SIG_SETMASK:
                    self.assertTrue(construct.called)
                    raise InterruptedError('/private/interrupt')
                return set()
            stack.enter_context(patch.object(L.signal,'pthread_sigmask',side_effect=mask))
            stack.enter_context(patch.object(L.signal,'signal'))
            stack.enter_context(patch.object(L.signal,'setitimer'))
            if save_error:
                original=L.P.save
                def save(path,value):
                    if path.name=='summary.json':raise OSError('/private/disk failure')
                    return original(path,value)
                stack.enter_context(patch.object(L.P,'save',side_effect=save))
            value=L.launch(origin,work,contract_sha256='a'*64,python_path='/fixture/python')
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
            self.assertEqual(spawn.call_args.args[0][1:3],['-I','-B'])
            child.terminate.assert_called_once()
            self.assertNotIn('secret',json.dumps(value));self.assertNotIn('/private',json.dumps(value))
            if cleanup:restore.assert_called_once()
            return value
    def test_child_failure_private(self):
        self.assertEqual(self.run_failure()['status'],'FAILED_CHILD')
    def test_pending_cancellation_after_spawn_has_owned_child(self):
        self.assertEqual(self.run_failure(cancel_on_unblock=True)['status'],'CANCELLED')
    def test_timeout_cleaned(self):
        self.assertEqual(self.run_failure(wait_error=TimeoutError('/private'))['status'],'TIMED_OUT')
    def test_cleanup_failure_cannot_look_successful(self):
        value=self.run_failure(cleanup=False);self.assertEqual(value['status'],'FAILED_CLEANUP');self.assertFalse(value['cleanup_complete'])
    def test_summary_write_failure_is_sanitized(self):
        self.assertEqual(self.run_failure(save_error=True)['status'],'FAILED_CLEANUP')


class FullReceiptFixture:
    """Tiny synthetic artifacts with production schemas; no original data access."""
    def __enter__(self):
        self.stack=ExitStack();directory=self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root=Path(directory);self.origin=self.root/'origin';self.out=self.root/'references'
        assets=self.origin/'private/assets';assets.mkdir(parents=True);self.out.mkdir()
        for name in ('readonly','sequential','reduced','tmp'):(self.out/name).mkdir()
        self.sources=R.snapshot();self.before={'fixture':'all bytes verified in mocked origin'}
        pins=deepcopy(R.contract());pins['metadata']={'private/assets/ASSETS.json':{}}
        self.assets={'readonly':{},'native_m16':{'producer':'explicit retained fixture native'}}
        def put(root,name,raw):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            return dict(path=name,bytes=len(raw),sha256=R.sha(raw))
        self.put=put;origin_records=[]
        table=put(assets,'table.bin',b'fixture table');origin_records.append(table)
        self.assets['readonly']['table']=table;pins['m16_readonly']['table']={k:table[k] for k in ('bytes','sha256')}
        readonly={}
        for key,name in (('arena','readonly_arena.f32le'),('input_x','input_x.f32le')):
            readonly[key]=put(self.out,'readonly/'+name,('fixture '+key).encode())
            pins['m16_readonly'][key]={k:readonly[key][k] for k in ('bytes','sha256')}
        readonly_identity=dict(token_ids=list(range(16)),position_ids=list(range(16)),past_tokens=0,
            readonly_sha256=readonly['arena']['sha256'],input_x_sha256=readonly['input_x']['sha256'],
            intermediate_preloads=0,rope_table_sha256=table['sha256'],
            rope_recipe='FP32 exponent/powf/reciprocal/phase multiply/sinf/cosf then BF16; positions0..255 only')
        self.inventory={name:4 for name in R.output_inventory()}
        self.shapes={name:[1] for name in R.shapes()}
        producers={};stdout,software_ack=ack()
        for role in ('sequential','reduced'):
            executable=put(assets,role+'/candidate',b'fixture executable '+role.encode())
            compile_record=put(assets,role+'/compile.json',b'{}\n');origin_records.extend((executable,compile_record))
            self.assets[role]=dict(producer='fixture-original-'+role,executable=executable,compile=compile_record)
            directory=self.out/role;rawdir=directory/'raw_stages';rawdir.mkdir();empty=directory/'empty_cache.bin'
            result=dict(schema=1,status='FRESH_M16_REFERENCE_ONLY',producer=self.assets[role]['producer'],
                origin_compile_receipt=compile_record,origin_executable=executable,origin_receipts_rewritten=False,
                argv=[str(assets/executable['path']),str(self.out/'readonly/readonly_arena.f32le'),'16',
                      str(rawdir),'0',str(empty),str(empty)],software_ack=software_ack,
                outputs={name:put(self.out,role+'/raw_stages/'+name,b'\0'*4) for name in self.inventory},
                stdout=put(self.out,role+'/stdout.log',stdout.encode()),stderr=put(self.out,role+'/stderr.log',b''),
                empty_cache=put(self.out,role+'/empty_cache.bin',b''),readonly=readonly_identity,
                actual_chain_executed=False,returncode=0,elapsed_seconds=0.1,requested_timeout_seconds=30)
            if role=='sequential':
                tensors={name:put(self.out,role+'/tensors/candidate_'+name+'.f32le',b'\0'*4) for name in self.shapes}
                exported=[dict(name=name,path='candidate_'+name+'.f32le',shape=[1],export_shape=[1],
                    sha256=tensors[name]['sha256']) for name in sorted(self.shapes)]
                result['export_receipt']=put(self.out,role+'/export.json',R.encoded(exported));result['tensors']=tensors
            producers[role]=result
        self.value=scope();self.value.update(origin=self.before,readonly=readonly,origin_table=table,
            origin_native_m16=self.assets['native_m16'],producers=producers)
        self.stack.enter_context(patch.object(R,'contract',return_value=pins))
        self.stack.enter_context(patch.object(R,'verify_reuse',return_value=self.before))
        self.stack.enter_context(patch.object(R,'read_metadata',return_value=self.assets))
        self.stack.enter_context(patch.object(R,'reuse_records',return_value=origin_records))
        self.stack.enter_context(patch.object(R,'output_inventory',return_value=self.inventory))
        self.stack.enter_context(patch.object(R,'shapes',return_value=self.shapes))
        self.stack.enter_context(patch.object(R,'export_shapes',return_value=self.shapes))
        self.publish();return self
    def publish(self):
        for role,result in self.value['producers'].items():
            result['run']=self.put(self.out,role+'/run.json',R.encoded({k:v for k,v in result.items() if k!='run'}))
        self.put(self.out,'M16_REFERENCES.json',R.encoded(self.value))
    def verify(self):
        return V.validate(self.origin,self.out,child_returncode=0,sources=self.sources,origin_before=self.before)
    def __exit__(self,*args):return self.stack.__exit__(*args)


class FullReceiptTests(unittest.TestCase):
    def test_complete_synthetic_schema_and_hash_check(self):
        with FullReceiptFixture() as f:
            result=f.verify();self.assertEqual(result['fresh_artifacts'],85);self.assertEqual(result['origin_artifacts'],5)
            self.assertFalse(result['ready_for_actual'])
    def test_original_compile_receipt_cannot_be_rewritten(self):
        with FullReceiptFixture() as f:
            f.value['producers']['sequential']['origin_compile_receipt']={};f.publish()
            with self.assertRaises(ValueError):f.verify()
    def test_m128_invocation_rejected(self):
        with FullReceiptFixture() as f:
            f.value['producers']['reduced']['argv'][2]='128';f.publish()
            with self.assertRaises(ValueError):f.verify()
    def test_m16_native_origin_cannot_be_replaced(self):
        with FullReceiptFixture() as f:
            f.value['origin_native_m16']={};f.publish()
            with self.assertRaises(ValueError):f.verify()
    def test_missing_raw_file_rejected(self):
        with FullReceiptFixture() as f:
            (f.out/'reduced/raw_stages'/next(iter(f.inventory))).unlink()
            with self.assertRaises(ValueError):f.verify()
    def test_extra_raw_file_rejected(self):
        with FullReceiptFixture() as f:
            (f.out/'sequential/raw_stages/extra.bin').write_bytes(b'')
            with self.assertRaises(ValueError):f.verify()
    def test_changed_raw_bytes_rejected(self):
        with FullReceiptFixture() as f:
            (f.out/'reduced/raw_stages'/next(iter(f.inventory))).write_bytes(b'xxxx')
            with self.assertRaises(ValueError):f.verify()
    def test_export_shape_rejected(self):
        with FullReceiptFixture() as f:
            path=f.out/'sequential/export.json';value=json.loads(path.read_text());value[0]['export_shape']=[2]
            f.value['producers']['sequential']['export_receipt']=f.put(f.out,'sequential/export.json',R.encoded(value));f.publish()
            with self.assertRaises(ValueError):f.verify()
    def test_run_json_top_level_mismatch_rejected(self):
        with FullReceiptFixture() as f:
            path=f.out/'sequential/run.json';path.write_text('{}\n')
            with self.assertRaises(ValueError):f.verify()
    def test_original_artifact_drift_rejected(self):
        with FullReceiptFixture() as f,patch.object(R,'verify_reuse',return_value={'fixture':'drift'}):
            with self.assertRaises(ValueError):f.verify()
    def test_source_drift_rejected(self):
        with FullReceiptFixture() as f,patch.object(R,'snapshot',return_value={}):
            with self.assertRaises(ValueError):f.verify()
    def test_symlink_export_rejected(self):
        with FullReceiptFixture() as f:
            paths=list((f.out/'sequential/tensors').iterdir());paths[0].unlink();paths[0].symlink_to(paths[1].name)
            with self.assertRaises(ValueError):f.verify()


class LaunchEvidenceTests(unittest.TestCase):
    def test_private_completion_binds_exit_sources_and_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            work=Path(d);(work/'control').mkdir();(work/'references').mkdir()
            for name in ('control/child_exit.json','control/context.json','references/M16_REFERENCES.json'):
                (work/name).write_bytes(b'{}\n')
            contract=dict(launcher_sources={'fixture':'b'*64},asset_sources={'fixture':'c'*64},
                origin_commit='fixture',python={'sha256':'d'*64})
            verified=dict(receipt_sha256=R.sha(b'{}\n'),fresh_artifacts=85,origin_artifacts=151,
                numerical_acceptance=False,ready_for_actual=False,full_29_node_acceptance=False)
            value=L.completion(work,contract,'a'*64,42,verified,{'lexical_path':'/fixture/python','resolved_path':'/fixture/target'})
            self.assertEqual(value['child']['returncode'],0)
            self.assertTrue(value['child']['cleanup_complete'])
            self.assertTrue(value['caller_must_observe_launcher_exit'])
            self.assertEqual(value['references']['sha256'],verified['receipt_sha256'])
            self.assertEqual(value['launcher_source_sha256'],contract['launcher_sources'])
            self.assertEqual(value['asset_source_sha256'],contract['asset_sources'])
            self.assertTrue(all(value[k] is False for k in R.contract()['claims']))
    def test_summary_cannot_export_private_artifact_count(self):
        with self.assertRaises(ValueError):
            L.safe_summary('COMPLETE_REFERENCE_PREPARATION_ONLY','complete',0,'a'*64,
                verified=dict(receipt_sha256='a'*64,fresh_artifacts='/private',origin_artifacts=151))


class ReviewRegressionTests(unittest.TestCase):
    def test_real_control_child_resets_inherited_blocked_mask(self):
        signals={signal.SIGALRM,signal.SIGTERM,signal.SIGINT}
        prefix=L.CHILD.split('code,origin,output,control,expected_json,python_json=sys.argv[1:]')[0]
        probe=prefix+"print(json.dumps([int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK,set())]))"
        # The child is a tiny stdlib-only control probe. It never imports or
        # calls the producer, original backend, payload or executable.
        old=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
        try:
            result=subprocess.run([sys.executable,'-I','-B','-c',probe],capture_output=True,text=True,
                timeout=2,check=True,start_new_session=True)
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,old)
        self.assertFalse(signals.intersection(json.loads(result.stdout)))
    def test_json_parse_uses_the_bytes_that_are_hashed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'fixture.json';path.write_bytes(b'{"x":1}\n')
            item=dict(path='fixture.json',bytes=8,sha256=R.sha(b'{"x":1}\n'))
            original=R.checked
            def mutate_after_stat(root,record,*,content):
                self.assertFalse(content)
                value=original(root,record,content=content)
                path.write_bytes(b'{"x":2}\n')
                return value
            with patch.object(R,'checked',side_effect=mutate_after_stat),self.assertRaises(ValueError):
                V.read_record(root,item)
    def test_log_parse_uses_the_bytes_that_are_hashed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'fixture.log';path.write_bytes(b'changed')
            item=dict(path='fixture.log',bytes=7,sha256=R.sha(b'initial'))
            with self.assertRaises(ValueError):V.bound_bytes(root,item,16384)


class PortableProposalTests(unittest.TestCase):
    def test_contract_contains_no_runtime_absolute_path_or_historical_claim(self):
        value=json.loads((L.HERE/'contract.json').read_text())
        self.assertEqual(value['profile'],'qwen2-packed-m16-reference-launch-portable-v1')
        self.assertEqual(value['status'],'REPRODUCIBLE_PROPOSAL_EXECUTION_UNAUTHORIZED')
        self.assertIs(value['historical_execution_claim'],False)
        self.assertNotIn('resolved_path',value['python'])
        self.assertEqual(value['python']['version'],[3,12,14])
        def walk(x):
            if isinstance(x,dict):return all(walk(v) for v in x.values())
            if isinstance(x,list):return all(walk(v) for v in x)
            return not (isinstance(x,str) and x.startswith('/'))
        self.assertTrue(walk(value))
    def test_interpreter_runtime_argument_is_exact(self):
        with tempfile.TemporaryDirectory() as d:
            origin=Path(d);parent=origin/'private/assets/venv/bin';parent.mkdir(parents=True)
            (parent/'python').write_bytes(b'fixture')
            contract={'python':{'bytes':7,'sha256':R.sha(b'fixture')}}
            with self.assertRaises(ValueError):L.interpreter(origin,contract,parent/'different-python')
    def test_runtime_identity_is_private_and_rechecks_target(self):
        with tempfile.TemporaryDirectory() as d:
            parent=Path(d);(parent/'target').write_bytes(b'fixture');(parent/'python').symlink_to('target')
            value=L.interpreter_identity(parent/'python')
            self.assertEqual(value,dict(lexical_path=str(parent/'python'),resolved_path=str(parent/'target'),
                bytes=7,sha256=R.sha(b'fixture')))
            public=L.safe_summary('FAILED_PREFLIGHT','preflight',0,'a'*64)
            self.assertNotIn(str(parent),json.dumps(public))
    def test_child_checks_version_and_hash_before_producer(self):
        version=L.CHILD.index('list(sys.version_info[:3])==python_expected')
        digest=L.CHILD.index("R.file_hash(Path(sys.executable).resolve())==python_expected['sha256']")
        producer=L.CHILD.index('result=P.produce')
        self.assertLess(version,producer);self.assertLess(digest,producer)
    def test_bad_version_prevents_mocked_child_producer(self):
        import types
        expected=dict(implementation='cpython',version=[0,0,0],sha256='a'*64)
        producer=types.SimpleNamespace(produce=Mock(side_effect=AssertionError('must not run')),save=Mock())
        reuse=types.SimpleNamespace(strict_json=R.strict_json,need=R.need,same=R.same,snapshot=lambda:{},file_hash=lambda p:'a'*64)
        args=['child','/fixture/code','/fixture/origin','/fixture/output','/fixture/control','{}',json.dumps(expected)]
        with patch.dict(sys.modules,{'reuse':reuse,'producer':producer}),patch.object(sys,'argv',args):
            with self.assertRaises(ValueError):exec(compile(L.CHILD,'<portable-child-fixture>','exec'),{})
        producer.produce.assert_not_called()
    def test_bad_hash_prevents_mocked_child_producer(self):
        import types
        expected=dict(implementation=sys.implementation.name,version=list(sys.version_info[:3]),sha256='b'*64)
        producer=types.SimpleNamespace(produce=Mock(side_effect=AssertionError('must not run')),save=Mock())
        reuse=types.SimpleNamespace(strict_json=R.strict_json,need=R.need,same=R.same,snapshot=lambda:{},file_hash=lambda p:'a'*64)
        args=['child','/fixture/code','/fixture/origin','/fixture/output','/fixture/control','{}',json.dumps(expected)]
        with patch.dict(sys.modules,{'reuse':reuse,'producer':producer}),patch.object(sys,'argv',args):
            with self.assertRaises(ValueError):exec(compile(L.CHILD,'<portable-child-fixture>','exec'),{})
        producer.produce.assert_not_called()


if __name__=='__main__':unittest.main()
