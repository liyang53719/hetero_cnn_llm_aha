"""Cold tests: synthetic control/metadata only; no authentic payloads or producers."""
import copy
import io
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

from . import reuse as R
from . import producer as P


def synthetic_native():
    """Metadata fixture; zero-valued metrics are invented and are not evidence."""
    shapes=R.shapes();exports=R.export_shapes()
    policy={'operator':{'max_abs':0.03125,'mean_abs':0.005},
            'block':{'max_abs':0.05,'mean_abs':0.01},
            'sha256':'5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'}
    value=dict(status='PASS_BF16_STAGE_BUDGET',tokens=16,carried=False,m16_gate_sha256=None,
        torch_threads=4,payload_manifest_sha256='a'*64,official_framework_forward=True,policy=policy,
        rtl_execution=False,hardware_recipe_acceptance=False,logits=False,full_model_quality=False,
        manifest_whole_checkpoint_hash_verified=False,modes={})
    declared={'producer':'qwen2-native-qkv-qk-pair-generated-v1','outputs':{}}
    for mode in R.MODES:
        stages={};declared['outputs'][mode]={method:{} for method in R.METHODS}
        for name,shape in shapes.items():
            stage=dict(shape=shape,elements=math.prod(shape),finite=True,bit_exact=True,max_abs=0.0,mean_abs=0.0)
            if name=='mask':stage.update(contract='exact_causal_mask',passed=True)
            elif mode=='fp32' or name=='softmax_fp32':
                stage.update(contract=None,passed=None,status='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE')
            else:
                level='block' if name=='y' else 'operator'
                stage.update(contract='spec/numerical_contract.md:'+level,limits=policy[level],passed=True)
            for method,prefix in zip(R.METHODS,('native','independent')):
                path='%s/phase_0/%s_%s.f32le'%(mode,prefix,name)
                stage.update({prefix+'_file':path,prefix+'_export_shape':exports[name],prefix+'_file_sha256':'b'*64})
                declared['outputs'][mode][method][name]=dict(path='native_m16/'+path,bytes=4*math.prod(shape),sha256='b'*64)
            stages[name]=stage
        semantics={name:True for name in ('mask_exact','native_fp32_probability_sum_within_2e_5',
            'independent_fp32_probability_sum_within_2e_5','native_cache_append_k_exact','native_cache_append_v_exact',
            'independent_cache_append_k_exact','independent_cache_append_v_exact',
            'native_future_probability_zero','independent_future_probability_zero')}
        phase=dict(phase=0,past_tokens=0,token_ids=list(range(16)),position_ids=list(range(16)),
            semantics=semantics,all_semantics_exact=True,stages=stages,failed_stages=[],
            status='PASS_BF16_STAGE_BUDGET' if mode=='bf16' else 'DIAGNOSTIC_FP32')
        value['modes'][mode]={'phases':[phase]}
    return value,declared


class MetadataTests(unittest.TestCase):
    def test_contract_is_preparation_only(self):
        pins=R.contract()
        self.assertIs(pins['execution']['allowed_by_this_contract'],False)
        self.assertFalse(any(pins['claims'].values()))
        self.assertEqual(pins['rows'],16)
        self.assertEqual(pins['origin_rows'],128)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e999}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):R.strict_json(raw)

    def test_json_bound(self):
        with self.assertRaises(ValueError):R.strict_json(b' '* (R.MAX_JSON+1))

    def test_canonical_equality(self):
        self.assertFalse(R.same(True,1));self.assertFalse(R.same([1.0],[1]))
        self.assertTrue(R.same({'a':1},{'a':1}))

    def test_exact_m16_shapes(self):
        self.assertEqual(len(R.shapes()),29)
        self.assertEqual(len(R.output_inventory()),22)
        self.assertEqual(R.shapes()['q'],[1,12,16,128])
        self.assertEqual(R.export_shapes()['q'],[1,16,1536])
        self.assertEqual(R.output_inventory()['scores.f32le'],12288)
        self.assertEqual(R.output_inventory()['phase_0_n0_recipe.f32le'],98304)

    def test_synthetic_native_metadata(self):
        value,declared=synthetic_native()
        R.validate_native(value,declared,'a'*64)

    def test_native_rejects_mode_scope_claims(self):
        for key,new in [('tokens',128),('tokens',True),('carried',True),('torch_threads',8),
                        ('rtl_execution',True),('hardware_recipe_acceptance',True),('full_model_quality',True)]:
            value,declared=synthetic_native();value[key]=new
            with self.subTest(key=key,new=new),self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_producer_relabel(self):
        value,declared=synthetic_native();declared['producer']='scripts.qwen2_layer0_model_gate.run_gate'
        with self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_shape_bool_and_m128(self):
        for shape in ([True,16,1536],[1,128,1536]):
            value,declared=synthetic_native();value['modes']['bf16']['phases'][0]['stages']['x']['shape']=shape
            with self.subTest(shape=shape),self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_export_layout(self):
        value,declared=synthetic_native()
        value['modes']['bf16']['phases'][0]['stages']['q']['native_export_shape']=[1,12,16,128]
        with self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_export_path_and_size(self):
        for key,new in [('path','native/phase_0/x.f32le'),('bytes',True),('bytes',786432)]:
            value,declared=synthetic_native();declared['outputs']['bf16']['official_self_cache']['x'][key]=new
            with self.subTest(key=key),self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_changed_limits(self):
        value,declared=synthetic_native();value['policy']['operator']['max_abs']=10.0
        with self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_original_gate_failure(self):
        value,declared=synthetic_native();value['modes']['bf16']['phases'][0]['stages']['x']['max_abs']=0.03126
        with self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_mask_failure(self):
        value,declared=synthetic_native();value['modes']['bf16']['phases'][0]['stages']['mask']['bit_exact']=False
        with self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_diagnostic_promoted_to_gate(self):
        for mode,name in [('bf16','softmax_fp32'),('fp32','x')]:
            value,declared=synthetic_native();value['modes'][mode]['phases'][0]['stages'][name]['passed']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)

    def test_native_rejects_semantics_or_tokens(self):
        value,declared=synthetic_native();value['modes']['bf16']['phases'][0]['semantics']['mask_exact']=False
        with self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)
        value,declared=synthetic_native();value['modes']['bf16']['phases'][0]['token_ids'][0]=False
        with self.assertRaises(ValueError):R.validate_native(value,declared,'a'*64)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.path=self.root/'synthetic.bin';self.path.write_bytes(b'cold fixture')
        self.item=dict(path=self.path.name,bytes=12,sha256=R.sha(b'cold fixture'))
    def tearDown(self):self.tmp.cleanup()

    def test_metadata_mode_does_not_hash_payload(self):
        with patch.object(R,'file_hash',side_effect=AssertionError('no byte reads')):
            self.assertEqual(R.checked(self.root,self.item,content=False),self.path)

    def test_hash_mode_checks_tiny_synthetic_bytes(self):
        R.checked(self.root,self.item,content=True)
        bad=dict(self.item,sha256='0'*64)
        with self.assertRaises(ValueError):R.checked(self.root,bad,content=True)

    def test_size_bool_and_traversal_rejected(self):
        for item in (dict(self.item,bytes=True),dict(self.item,path='../escape'),dict(self.item,path='/escape'),
                     dict(self.item,path='./synthetic.bin'),dict(self.item,path='a//b')):
            with self.subTest(item=item),self.assertRaises(ValueError):R.checked(self.root,item,content=False)

    def test_symlink_rejected(self):
        link=self.root/'link.bin';link.symlink_to(self.path)
        with self.assertRaises(ValueError):R.checked(self.root,dict(self.item,path=link.name),content=False)

    def test_hardlink_alias_rejected(self):
        link=self.root/'hard.bin';os.link(self.path,link)
        with self.assertRaises(ValueError):R.no_aliases([self.path,link])

    def test_path_alias_rejected(self):
        with self.assertRaises(ValueError):R.no_aliases([self.path,self.path])

    def test_metadata_digest_failure(self):
        p=self.root/'fake.json';p.write_bytes(b'{}')
        with self.assertRaises(ValueError):R.read_metadata(self.root,p.name,{'bytes':2,'sha256':'0'*64})


class PreparationTests(unittest.TestCase):
    def test_plan_has_no_side_effects(self):
        with (patch.object(R,'verify_reuse',side_effect=AssertionError('not requested')),
              patch.object(P,'produce',side_effect=AssertionError('producer execution prohibited'))):
            value=P.plan('/synthetic-origin','/synthetic-output')
        self.assertFalse(value['ready_for_actual']);self.assertFalse(value['packed_source_profile_linked'])
        self.assertFalse(value['payload_copy']);self.assertFalse(value['actual_chain_executed'])

    def test_cli_default_is_plan_only(self):
        with (patch.object(P,'produce',side_effect=AssertionError('no execution')),
             patch.object(R,'verify_reuse',side_effect=AssertionError('no metadata requested')),
             patch('sys.stdout',new_callable=io.StringIO) as out):
            P.main(['--origin','/synthetic-origin','--output','/synthetic-output'])
        self.assertEqual(json.loads(out.getvalue())['status'],'PLAN_ONLY_NO_PRODUCERS_EXECUTED')

    def test_cli_has_no_execute_flag(self):
        with patch('sys.stderr',new_callable=io.StringIO),self.assertRaises(SystemExit):
            P.main(['--origin','/synthetic-origin','--output','/synthetic-output','--execute'])

    def test_cli_metadata_request_never_enables_bytes(self):
        with (patch.object(R,'verify_reuse',return_value={'status':'SYNTHETIC'}) as verify,
              patch('sys.stdout',new_callable=io.StringIO)):
            P.main(['--origin','/synthetic-origin','--output','/synthetic-output','--check-metadata'])
        verify.assert_called_once_with('/synthetic-origin',metadata_only=True)

    def test_plan_rejects_overlap(self):
        for output in ('/origin','/origin/child','/'):
            with self.subTest(output=output),self.assertRaises(ValueError):P.plan('/origin',output)

    def test_plan_distinguishes_logical_and_export_qk_shapes(self):
        value=P.plan('/synthetic-origin','/synthetic-output')
        self.assertEqual(value['sequential_logical_shapes']['q'],[1,12,16,128])
        self.assertEqual(value['sequential_export_shapes']['q'],[1,16,1536])
        self.assertEqual(value['sequential_logical_shapes']['k'],[1,2,16,128])
        self.assertEqual(value['sequential_export_shapes']['k'],[1,16,256])

    def test_output_must_be_new_and_disjoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);origin=root/'origin';origin.mkdir()
            self.assertEqual(P.output_root(origin,root/'fresh'),root/'fresh')
            with self.assertRaises(ValueError):P.output_root(origin,origin/'fresh')
            with self.assertRaises(ValueError):P.output_root(origin,origin)

    def test_budget_cannot_increase(self):
        for seconds in (True,0,121,120.0):
            with self.subTest(seconds=seconds),self.assertRaises(ValueError):
                with P.deadline(seconds):pass

    def test_expired_remaining(self):
        with self.assertRaises(TimeoutError):P.remaining(0,30)

    def test_interrupted_fake_process_is_killed_and_reaped(self):
        with tempfile.TemporaryDirectory() as temp:
            process=Mock(pid=123);process.wait.side_effect=[subprocess.TimeoutExpired('synthetic',1),0]
            with (patch.object(P.subprocess,'Popen',return_value=process),patch.object(P.os,'killpg') as kill,
                  patch.object(P,'remaining',return_value=1)):
                with self.assertRaises(subprocess.TimeoutExpired):P.run_original(['synthetic-only'],Path(temp),1)
            kill.assert_called_once_with(123,P.signal.SIGKILL)
            self.assertEqual(process.wait.call_count,2)

    def test_sigterm_handler_raises_and_is_restored(self):
        import signal
        original=signal.getsignal(signal.SIGTERM)
        with self.assertRaises(InterruptedError):
            with P.deadline(1):
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
        self.assertIs(signal.getsignal(signal.SIGTERM),original)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_reap_ignores_alarm_and_repeat_termination(self):
        import signal
        failure=InterruptedError('synthetic original termination')
        with tempfile.TemporaryDirectory() as temp:
            process=Mock(pid=123)
            def wait(*,timeout):
                if timeout != 5:
                    raise failure
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
                for sig in (signal.SIGALRM,signal.SIGTERM,signal.SIGINT):
                    self.assertEqual(signal.getsignal(sig),signal.SIG_IGN)
                    os.kill(os.getpid(),sig)  # Ignored: no process/numerical work.
                return 0
            process.wait.side_effect=wait
            with (patch.object(P.subprocess,'Popen',return_value=process),patch.object(P.os,'killpg'),
                  patch.object(P,'remaining',return_value=1),P.deadline(1)):
                with self.assertRaises(InterruptedError) as caught:
                    P.run_original(['synthetic-only'],Path(temp),1)
            self.assertIs(caught.exception,failure)
            self.assertEqual(process.wait.call_count,2)

    def test_receipt_write_fsync_failure_leaves_no_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'M16_REFERENCES.json'
            with patch.object(P.os,'fsync',side_effect=OSError('synthetic fsync failure')):
                with self.assertRaises(OSError):P.save(path,{'fixture':True})
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_interrupted_rename_revokes_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'M16_REFERENCES.json';replace=os.replace
            def interrupted(old,new):
                replace(old,new)
                raise InterruptedError('synthetic interrupted publication')
            with patch.object(P.os,'replace',side_effect=interrupted):
                with self.assertRaises(InterruptedError):P.save(path,{'fixture':True})
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_failure_after_publication_revokes_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            with self.assertRaises(InterruptedError):
                with P.failed_publication(output):
                    P.save(output/'M16_REFERENCES.json',{'fixture':True})
                    raise InterruptedError('synthetic terminal failure')
            self.assertEqual(list(output.iterdir()),[])


if __name__=='__main__':unittest.main()
