"""Cold recovery gates; synthetic records only, no owner or Torch execution."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import audit as a,reference,supervise
from candidates.qwen2_m16_stage_diagnostic import geometry as g

def fixture():
    records=[]
    for pc,n in ((1,1536),(4,256)):
        fmas=16*n*1536;adds=16*n*64;reads=16*(96+n//64*3072);writes=n
        records.append(dict(job=dict(tag=pc,m=16,n=n,k=1536),kernel_delta=dict(fmas=fmas,adds=adds,tiles_started=n//4),
          tiles_output_acked=n//4,memory=dict(read_bytes=reads*64,write_bytes=writes*64,read_requests=reads,write_requests=writes,acks=writes),
          terminal=dict(status=None,write_bytes=16*n*4,useful_macs=fmas,executed_macs=fmas),partial_bytes=16384,
          actual_dense_fma_calls_delta=0,actual_normal_fma_calls_delta=0,matrix_counter_delta={},
          final_ack_fence=dict(terminal_strictly_after_final_ack=True,held_ticks=5)))
    v=dict(original_public_job=dict(tag=7),partials=[0]*4,drains=[0]*2,accepted=dict(backend_step_fire=12288),
      terminal=dict(useful_macs=g.V['useful_macs'],executed_macs=g.V['executed_macs'],write_bytes=g.V['raw_qkv_ack_bytes']),
      actual_dense_fma_calls_delta=g.V['actual_c_fma_calls'],shared_vector=dict(add_requests=256))
    matrix=dict(counters=dict(dense_steps=g.WHOLE['dense_steps'],normal_steps=g.WHOLE['normal_steps']),dense_fma_calls=g.WHOLE['dense_fma'],normal_fma_calls=g.WHOLE['normal_fma'])
    launch=dict(status=None,completed=21,jobs=17,useful_macs=g.WHOLE['useful_macs'],executed_macs=g.WHOLE['executed_macs'])
    tail=dict(dense_steps=1363968,dense_groups=162,dense_results=800,owner_acquires=114,owner_releases=114,dense_seed_acks=144)
    stats=dict(total=dict(native=dict(silu_calls=8960,silu_failures=0)),full_fixed_array_issued_cell_opportunities=g.WHOLE['matrix_opportunities'],
      intervals=[dict(name='pc19_down',accepted_counter_delta=dict(matrix=tail))])
    silu=a.SimpleNamespace(calls=8960,sf_calls=lambda:8960,sf_failures=lambda:0)
    host=dict(accepted=dict(completion_fire=21,request_fire=17,owner_result_fire=17,result_fire=1),launch_result=launch,
      reset_required=False,completions=[dict(pc=i,status=None) for i in range(21)],events=list(range(22)),requests=[0]*17,qkv_reductions=[v])
    return dict(status='M16_MODEL_FAILED',model_completed=False,actual_outputs_sealed=False,error_type='ValueError',error='saved observer receipt differs',
      whole_block_terminal=True,finalfence=True,fullblock_pass=False,formal_reference_contract=False,reference_executed=False,
      old_wrapper_optimizations_loaded=False,execution=dict(host=host),backend_debts=dict(a=False),failed_debts=dict(a=False),
      exact64_projections=records,statistics=stats,failure_counters=dict(silu_calls=8960),matrix=matrix,
      whole_accounting=g.whole(matrix,launch,silu,stats))

class Cold(unittest.TestCase):
    def test_original_failure_preserved(self):
        r=fixture();before=copy.deepcopy(r);self.assertTrue(a.validate_execution(r));self.assertEqual(r,before)
    def test_status_and_posthoc_negatives(self):
        for key,value in (('status','PASS'),('model_completed',True),('actual_outputs_sealed',True),('error','different'),('finalfence',False),('reference_executed',True)):
            r=fixture();r[key]=value
            with self.assertRaises(ValueError):a.validate_execution(r)
        for key in ('native_after','artifact_after','source_post_verified','input_post_verified','native_post_verified','local_retention'):
            r=fixture();r[key]={}
            with self.assertRaises(ValueError):a.validate_execution(r)
    def test_terminal_debt_negative(self):
        for key in ('completion_fire','owner_result_fire','request_fire','result_fire'):
            r=fixture();r['execution']['host']['accepted'][key]-=1
            with self.assertRaises(ValueError):a.validate_execution(r)
        for key in ('backend_debts','failed_debts'):
            r=fixture();r[key]['a']=True
            with self.assertRaises(ValueError):a.validate_execution(r)
    def test_arithmetic_count_negative(self):
        r=fixture();r['exact64_projections'][0]['kernel_delta']['fmas']-=1
        with self.assertRaises(ValueError):a.validate_execution(r)
        r=fixture();r['statistics']['intervals'][0]['accepted_counter_delta']['matrix']['dense_seed_acks']-=1
        with self.assertRaises(ValueError):a.validate_execution(r)
    def test_seal_is_distinct_and_exact(self):
        checked=dict(status='RECOVERED_M16_DIAGNOSTIC',original_run='FAIL',original_inprocess_postchecks='NOT_REACHED')
        seal={**checked,'posthoc_utc':'2026-10-15T00:00:00+00:00'};self.assertTrue(a.validate_seal(seal,checked))
        for key,value in (('original_run','PASS'),('original_inprocess_postchecks','PASS'),('posthoc_utc','2026-10-15')):
            bad=dict(seal);bad[key]=value
            with self.assertRaises(ValueError):a.validate_seal(bad,checked)
    def test_fixed_evidence_pins(self):
        self.assertEqual(len(a.FIXED),6)
        self.assertEqual(a.FIXED[str((a.MODEL/'RESULT.json').relative_to(a.ROOT))],'361eeebec7241dfbbf69ee9a4eb052b8cb3138518e0ca37a4cef4121aa599b06')
        self.assertTrue(all(len(value)==64 for value in a.FIXED.values()))
    def test_no_alias_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'real';p.write_bytes(b'x');link=Path(d)/'alias';link.symlink_to(p)
            self.assertEqual(a.file_spec(p)['bytes'],1)
            with self.assertRaises(ValueError):a.file_spec(link)
    def test_default_no_execution(self):
        with patch.object(a,'inspect',side_effect=AssertionError('must stay cold')),patch.object(a,'sealed',side_effect=AssertionError('must stay cold')):
            for module in (a,reference,supervise):self.assertEqual(module.main([]),0)
    def test_no_old_complete_gate_patch(self):
        text=Path(supervise.__file__).read_text();self.assertIn('a.sealed()',text)
        self.assertNotIn('model.SUPERVISOR',text)
        text=Path(reference.__file__).read_text();self.assertIn('old.capture(',text);self.assertIn('old.compare_actuals(',text)
        self.assertNotIn('old.run(',text);self.assertNotIn('old.model_seal(',text)
if __name__=='__main__':unittest.main()
