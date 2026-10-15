"""Cold source/receipt tests; never a numerical run or a review certificate."""
import ast
from array import array
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from . import accounting as A,retention as R,runner,comparator

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def function(path,name):
    return next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name==name)


def exact_records():
    result=[]
    for pc,n in ((1,1536),(4,256)):
        fmas=128*n*1536;output=128*n
        result.append(dict(job=dict(tag=0x70000|pc,m=128,n=n,k=1536),terminal=dict(status=None,useful_macs=fmas,
            executed_macs=fmas,write_bytes=output*4),scope=A.SCOPE,performance='NO_GO',
            hardware_mapping='NOT_IMPLEMENTED',tiles_output_acked=output//64,
            memory=dict(read_bytes=128*(96+n//64*3072)*64,write_bytes=output*4,
                read_requests=128*(96+n//64*3072),write_requests=output//16,acks=output//16),kernel_delta=dict(fmas=fmas,adds=output*64,tiles_started=output//64),
            matrix_counter_delta={},actual_dense_fma_calls_delta=0,actual_normal_fma_calls_delta=0,
            partial_bytes=16384,final_ack_fence=dict(terminal_strictly_after_final_ack=True,held_ticks=5)))
    return result


def v_records():
    e=A.V_EXPECTED
    return [dict(original_public_job=dict(tag=0x70007),partials=[{}]*4,drains=[{}]*2,
        accepted=dict(backend_step_fire=e['wide_matrix_steps']),
        terminal={k:e[k] for k in ('useful_macs','executed_macs')}|{'write_bytes':e['raw_qkv_ack_bytes']},
        actual_dense_fma_calls_delta=e['actual_c_fma_calls'],shared_vector=dict(add_requests=e['vector_add_requests']))]


class Cold(unittest.TestCase):
    def test_retention_wrapper_is_explicit_and_old_verifier_unchanged(self):
        from candidates.qwen2_retention_shape_canonical import retention as canonical
        self.assertIs(runner.retention,canonical)
        self.assertIs(runner.retention.verify,R.verify)
        self.assertIsNot(runner.retention.seal,R.seal)

    def test_original_run_business_math_ast_unchanged_after_stage_instrumentation(self):
        class StripStages(ast.NodeTransformer):
            def visit_Assign(self,node):
                if any(isinstance(t,ast.Name) and t.id in ('stage_log','stage_context') for t in node.targets):return None
                return self.generic_visit(node)
            def visit_Expr(self,node):
                f=node.value.func if isinstance(node.value,ast.Call) else None
                if (isinstance(f,ast.Attribute) and isinstance(f.value,ast.Name) and f.value.id in ('stage_log','stage_context') or
                    isinstance(f,ast.Name) and f.id=='stage_failure'):return None
                return self.generic_visit(node)
            def visit_Call(self,node):
                self.generic_visit(node)
                if isinstance(node.func,ast.Name) and node.func.id=='StageCheckedTelemetry':
                    node.func=ast.Attribute(value=ast.Name(id='telemetry',ctx=ast.Load()),attr='SparseTelemetry',ctx=ast.Load())
                    node.keywords=[k for k in node.keywords if k.arg!='stage_log']
                return node
        tree=StripStages().visit(function(HERE/'runner.py','run'))
        # Full run() AST of published 5e14980830b937cb49a681bc9872e36d259c19a1.
        # Only the enumerated stage plumbing above is removed. No numerical,
        # handshake, every-edge, output, original guard or comparison is removed.
        digest=hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()
        self.assertEqual(digest,'17e790ecc4136c15b3d858e53677aac60149125d87bf37b21d50eba2615b0f9c')

    def test_cpu_limit_is_exact_approved_budget_after_execution_gate(self):
        text=(HERE/'runner.py').read_text();body=text[text.index('def main('):]
        self.assertLess(body.index('gates.require_execution()'),body.index('resource.setrlimit(resource.RLIMIT_CPU'))
        self.assertIn("resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],limits['cpu_seconds']))",body)
        self.assertNotIn('SIGPROF',text);self.assertNotIn('ITIMER_PROF',text)
        self.assertEqual(set(runner.TAIL_STAGE_NAMES.values()),{'PC12_RELEASE','PC13_O','PC14_RESIDUAL',
            'PC15_NORM','PC16_18_FFN','PC19_DOWN','PC20_RESIDUAL','LAUNCH_RESULT'})

    def test_actual_runner_stage_order_and_complete_tail_callback_mapping(self):
        tree=function(HERE/'runner.py','run')
        calls=sorted((n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
            and isinstance(n.func.value,ast.Name) and n.func.value.id=='stage_log'),key=lambda n:(n.lineno,n.col_offset))
        self.assertEqual([n.func.attr for n in calls],['begin','transition','transition','transition','transition','transition','transition','finish'])
        self.assertEqual([ast.unparse(n.args[0]) for n in calls[:-1]],
            ["'SETUP'",'stages.OWNER_STAGES[pc]',"'PC9_KV_APPEND'","'PC10_12_ATTENTION'",
             'TAIL_STAGE_NAMES[name]',"'FINAL_SEAL'","'POSTSEAL_COMPARISON'"])
        expected=('PC12_RELEASE','PC13_O','PC14_RESIDUAL','PC15_NORM','PC16_18_FFN','PC19_DOWN',
            'PC20_RESIDUAL','LAUNCH_RESULT')
        self.assertEqual(tuple(runner.TAIL_STAGE_NAMES.values()),expected)
        tail=function(ROOT/'candidates/qwen2_fullblock_ci_dut/tail.py','execute_tail')
        callbacks=sorted((n for n in ast.walk(tail) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
            and n.func.id=='stage'),key=lambda n:n.lineno)
        literals=[n.args[0].value for n in callbacks if isinstance(n.args[0],ast.Constant)]
        self.assertEqual(literals,['pc12_release','pc16_18_resident_ffn','pc19_down','pc20_residual','launch_result_hold_retire'])
        # The remaining callback is the original pc13/14/15 loop, with no new
        # subdivision of fused Attention or FFN into fictitious durations.
        loops=[n for n in ast.walk(tail) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple)]
        self.assertEqual(ast.literal_eval(loops[0].iter),((13,'Dense'),(14,'Add'),(15,'Norm')))
        after_finish=(HERE/'runner.py').read_text().split('stage_log.finish(counters=stage_counters(stage_context))',1)[1]
        normal=after_finish.split('except BaseException as e:',1)[0]
        self.assertNotIn('progress.mark',normal);self.assertNotIn('progress.emit',normal)

    def test_stage_snapshot_reads_only_real_cumulative_counters(self):
        context=dict(x=SimpleNamespace(host=SimpleNamespace(completed=12,jobs=11),
            counts=dict(result_fire=0,host_model_ticks=100)),
            physical=SimpleNamespace(counts=dict(read_bytes=64,write_ack_bytes=128)),
            service=SimpleNamespace(counts=dict(dense_steps=4,normal_steps=5),lib=SimpleNamespace(
                matrix_dense_fmas=lambda:512,matrix_normal_fmas=lambda:256)),
            projection=SimpleNamespace(kernel=SimpleNamespace(report=lambda:dict(fmas=96,adds=64))),
            shared=SimpleNamespace(calls=dict(add=2,multiply=3)),silu=SimpleNamespace(calls=7))
        self.assertEqual(runner.stage_counters(context),dict(completed=12,jobs=11,accepted_results=0,host_ticks=100,
            read_bytes=64,write_ack_bytes=128,dense_steps=4,normal_steps=5,dense_fma=512,normal_fma=256,
            exact64_fma=96,exact64_add=64,scalar_calls=5,silu_calls=7))
        self.assertEqual(runner.stage_counters({}),dict.fromkeys(runner.stages.COUNTER_LIMITS,0))

    def test_failed_counter_or_logger_never_masks_original_exception(self):
        original=RuntimeError('PRIVATE_BUSINESS_DETAIL')
        log=SimpleNamespace(active=('PC19_DOWN',0,0),failure=lambda *a,**k:(_ for _ in ()).throw(OSError('PRIVATE_LOG')))
        for counters in ({'x':object()},{}):
            try:
                try:raise original
                except BaseException as error:
                    self.assertFalse(runner.stage_failure(log,counters,error));raise
            except BaseException as caught:self.assertIs(caught,original)

    def test_sparse_cpu_check_precedes_original_emit_without_model_calls(self):
        log=SimpleNamespace(check=lambda:(_ for _ in ()).throw(TimeoutError('CPU budget exceeded')))
        progress=runner.StageCheckedTelemetry(Path('unused'),started=0,cpu=0,budget=5700,stage_log=log)
        with patch.object(runner.telemetry.SparseTelemetry,'emit',side_effect=AssertionError('must not emit after budget')):
            with self.assertRaises(TimeoutError):progress.emit('attention_loop')

    def test_cold_import_does_not_load_tensor_runtime(self):
        code='from candidates.qwen2_exact64_diagnostic_fullblock import runner; import sys; assert not any(x.split(".")[0] in ("numpy","torch","transformers") for x in sys.modules)'
        p=subprocess.run([sys.executable,'-B','-c',code],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
    def test_actual_gate_module_is_new_diagnostic_source(self):
        from . import gates
        self.assertIs(runner.OracleGate,gates.OracleGate)
        self.assertEqual(gates.require_execution.__module__,'candidates.qwen2_exact64_diagnostic_fullblock.gates')
    def test_default_is_no_execution(self):
        p=subprocess.run([sys.executable,'-B',str(HERE/'runner.py')],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);r=json.loads(p.stdout)
        self.assertEqual(r['status'],'NOT_EXECUTED');self.assertFalse(r['actual_execution_authorized'])
        self.assertEqual(r['performance'],'NO_GO');self.assertFalse(r['fullblock_pass'])
    def test_actual_rejected_before_any_input_or_runtime(self):
        with patch.object(runner,'dependencies',side_effect=AssertionError('runtime opened')):
            with self.assertRaises(ValueError):
                runner.run('missing','missing','missing',reviewed_source_manifest='a'*64,kernel_library='missing')
            with self.assertRaises(ValueError):
                runner.main(['--actual'])
    def test_actual_arguments_without_optin_are_rejected(self):
        with self.assertRaises(ValueError):runner.main(['--out','work/private'])
    def test_prior_publication_sources_unchanged(self):
        p=subprocess.run(['git','diff','--exit-code','--','candidates/qwen2_official_platform_fullblock',
            'candidates/qwen2_fullblock_ci_dut','candidates/qwen2_attention_shared_a_integration'],cwd=ROOT,capture_output=True)
        self.assertEqual(p.returncode,0)
    def test_cache_and_acceptance_math_ast_retained(self):
        old=ROOT/'candidates/qwen2_official_platform_fullblock/comparator.py'
        for name in ('same_live','checked_cache','accepted'):
            self.assertEqual(ast.dump(function(old,name)),ast.dump(function(HERE/'comparator.py',name)))
        self.assertIn('result=old.official(', (HERE/'comparator.py').read_text())
        self.assertIn('verdict=native.stage_verdict(', (HERE/'comparator.py').read_text())
    def test_only_qk_new_owner_and_tracked_tail(self):
        text=(HERE/'runner.py').read_text()
        self.assertIn('if pc in (1,4):',text)
        self.assertIn('driver=DiagnosticVReductionDriver(x,physical,job)',text)
        self.assertIn('from candidates.qwen2_fullblock_ci_dut import tail',text)
        self.assertNotIn('qwen2_fullblock_recovery',text)
        self.assertNotIn('full_4096_opportunity_count=exact',text)
    def test_retention_then_seal_then_oracle(self):
        text=(HERE/'runner.py').read_text()
        order=[text.index(x) for x in ("retention.seal(","report['actual_outputs_sealed']=True",
            "gate.open_after_seal(","gates.validate_references(","compare.official(")]
        self.assertEqual(order,sorted(order))
        self.assertIn('actual_owner_jobs=x.host.jobs,accepted_launch_results=x.counts[\'result_fire\']',text)
    def test_diagnostic_result_cannot_claim_formal_pass(self):
        text=(HERE/'runner.py').read_text()+(HERE/'comparator.py').read_text()
        self.assertNotIn('PASS_M128_OFFICIAL_OBSERVED_FULLBLOCK_PUBLIC21',text)
        self.assertNotIn('fullblock_pass=passed',text)
        self.assertIn("report['acceptance_sealed']=False",text)
        self.assertIn('diagnostic_numeric_pass=passed',text)


class Accounting(unittest.TestCase):
    def test_fixed_separate_actual_totals(self):
        self.assertEqual(A.v_totals(v_records()),A.V_EXPECTED)
        self.assertEqual(A.exact64_totals(exact_records()),A.EXACT_EXPECTED)
    def test_no_exact64_fake_matrix_steps(self):
        for field in ('dense_steps','normal_steps'):
            r=exact_records();r[0]['matrix_counter_delta'][field]=1
            with self.assertRaises(ValueError):A.exact64_totals(r)
    def test_counters_fence_identity_and_width_are_not_optional(self):
        for key,value in [('fmas',301989887),('adds',0),('tiles_started',False)]:
            r=exact_records();r[0]['kernel_delta'][key]=value
            with self.assertRaises(ValueError):A.exact64_totals(r)
        r=exact_records();r[0]['partial_bytes']=32768
        with self.assertRaises(ValueError):A.exact64_totals(r)
        r=exact_records();r[0]['final_ack_fence']['terminal_strictly_after_final_ack']=False
        with self.assertRaises(ValueError):A.exact64_totals(r)
        with self.assertRaises(ValueError):A.exact64_totals(exact_records()[::-1])
    def test_old_whole_qkv_report_is_rejected(self):
        r=v_records()*3
        with self.assertRaises(ValueError):A.v_totals(r)
    def test_extra_software_and_shared_a_debts_are_explicit(self):
        scratch=SimpleNamespace(owner=None,pending=None,held=None,valid=bytearray(2))
        attention=SimpleNamespace(scratch=scratch,local_pending=False,local_request=None,deferred_finish=None)
        x=SimpleNamespace(attention_router=None,attention_owner=attention,exact64_projection=None,
            owner=SimpleNamespace(bank_guard=SimpleNamespace(lease=None)))
        projection=SimpleNamespace(state='idle',poison=False,request=None,result=None,kernel=SimpleNamespace(state='idle'))
        self.assertFalse(any(A.debts(x,projection).values()))
        for target,key,value in ((x,'exact64_projection',object()),(projection,'poison',True),
                (x.owner.bank_guard,'lease',object()),(scratch,'pending',object()),
                (attention,'deferred_finish',(None,None))):
            previous=getattr(target,key);setattr(target,key,value)
            self.assertTrue(any(A.debts(x,projection).values()));setattr(target,key,previous)
        scratch.valid[0]=1;self.assertTrue(A.debts(x,projection)['shared_a_valid_lines'])
    def test_whole_reconciles_actual_kernels(self):
        e=A.WHOLE_EXPECTED
        matrix=dict(counters=dict(dense_steps=e['dense_steps'],normal_steps=e['normal_steps']),
            dense_fma_calls=e['dense_fma'],normal_fma_calls=e['normal_fma'])
        stats=dict(full_fixed_array_issued_cell_opportunities=e['opportunities'])
        launch=dict(useful_macs=e['whole_useful_macs'],executed_macs=e['whole_executed_macs'])
        silu=SimpleNamespace(calls=71680,sf_calls=lambda:71680,sf_failures=lambda:0)
        counts=dict(dense_steps=1363968,dense_groups=162,dense_results=800,owner_acquires=114,owner_releases=114,dense_seed_acks=144)
        intervals=[dict(name='pc16_18_resident_ffn',accepted_counter_delta=dict(matrix=counts))]
        result=A.whole(matrix,stats,launch,silu,intervals,A.EXACT_EXPECTED)
        self.assertEqual(result['exact64_matrix_stream_steps'],0)
        stats['full_fixed_array_issued_cell_opportunities']+=A.EXACT_EXPECTED['fmas']
        with self.assertRaises(ValueError):A.whole(matrix,stats,launch,silu,intervals,A.EXACT_EXPECTED)


class Retention(unittest.TestCase):
    def prepare(self,out):
        actual={n:array('I',[0x3f800000]) for n in R.ACTUAL_NAMES};silu=b'\0\0\x80?'
        sealed={}
        for name,raw in [(n,v.tobytes()) for n,v in actual.items()]+[('silu',silu)]:
            (out/('actual_'+name+'.f32le')).write_bytes(raw)
            sealed[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        fields={n:dict(observed=b'\x01') for n in R.ATTENTION_NAMES}
        capture=SimpleNamespace(closed=True,active=False,fields=fields,_bytes=lambda n,kind=None:b'\1\0' if kind else b'\0\0\x80?')
        obs=dict(status='COMPLETE_SYNTHETIC_COLD_ONLY');directory=out/'attention_observation';directory.mkdir()
        for n in fields:
            (directory/(n+'.u32le')).write_bytes(capture._bytes(n))
            (directory/(n+'.presence')).write_bytes(b'\x01')
            (directory/(n+'.count.u16le')).write_bytes(capture._bytes(n,'frequency'))
        (directory/'summary.json').write_text(json.dumps(obs))
        report=dict(whole_block_terminal=True,finalfence=True,actual_outputs_sealed=False,observation=obs,
            sealed_actual_outputs=sealed,execution=dict(host=dict(launch_result=dict(completed=21,jobs=17),
            accepted=dict(completion_fire=21,owner_result_fire=17,result_fire=1))))
        return actual,silu,capture,report
    def test_complete_local_actuals_and_all_ten_fields_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);args=self.prepare(out);receipt=R.seal(out,*args)
            self.assertEqual(len(receipt['inventory']),51);self.assertFalse(receipt['upload_authorized'])
            self.assertTrue(R.verify(out,receipt));self.assertFalse(receipt['oracle_payloads_read'])
    def test_missing_n1_or_sparse_observation_rejected(self):
        for name in ('actual_n1.f32le','attention_observation/prob_bf16.presence'):
            with tempfile.TemporaryDirectory() as t:
                out=Path(t);args=self.prepare(out);(out/name).unlink()
                with self.assertRaises(ValueError):R.seal(out,*args)
    def test_wrong_actual_and_postseal_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);args=self.prepare(out);receipt=R.seal(out,*args)
            (out/'actual_gate.f32le').write_bytes(b'changed')
            with self.assertRaises(ValueError):R.verify(out,receipt)
    def test_no_early_or_repeated_seal(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);args=self.prepare(out);args[-1]['actual_outputs_sealed']=True
            with self.assertRaises(ValueError):R.seal(out,*args)
            args[-1]['actual_outputs_sealed']=False;R.seal(out,*args)
            with self.assertRaises(FileExistsError):R.seal(out,*args)
    def test_incomplete_terminal_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);args=self.prepare(out);args[-1]['execution']['host']['launch_result']['jobs']=16
            with self.assertRaises(ValueError):R.seal(out,*args)

if __name__=='__main__':unittest.main()
