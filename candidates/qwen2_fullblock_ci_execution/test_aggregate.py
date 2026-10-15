import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_execution import aggregate as a
class AggregateTests(unittest.TestCase):
    def fixture(self,root):
        out=root/a.OUT;out.mkdir(parents=True)
        names={n+'.f32le' for n in a.summary.specs()}|{'mask.bf16le','BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json',
            'WRAPPER_BEFORE.json','WRAPPER_AFTER.json','BOOTSTRAP_REFERENCE.json','GO.json','OBSERVATIONS.json',
            'STAGES.jsonl','stdout.log','stderr.log'}
        for name in names:(out/name).write_bytes(b'fixture')
        resources=dict(returncode=0,limit_reason=None,cleanup_pids=[],descendant_cleanup={'remaining_descendants':{}},
            overall_wall_limit_seconds=120,external_watchdog_deadline_seconds=122,independent_overall_watchdog_enabled=True,
            overall_elapsed_seconds=1)
        record=dict(wrapper_boundary_unchanged=True,dut_executed=False,status='BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT',stage='bootstrap',resources=resources,
            outputs={n:a.file_identity(out/(n+'.f32le')) for n in a.summary.specs()})
        (out/'BOOTSTRAP_REFERENCE.json').write_text(json.dumps(record))
        seal=dict(status='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED',mode='bootstrap',run_id='ci01',manifest='BOOTSTRAP_REFERENCE.json',
            numerical_acceptance_claimed=False,dut_executed=False,retries=0,resources=resources,
            files={n:a.file_identity(out/n) for n in names})
        (out/'SEAL.json').write_text(json.dumps(seal))
        return out,record,seal
    def invoke(self,root):
        with patch.object(a,'ROOT',root),patch.object(a.inputs,'CI_ROOT',root),patch.object(a.closure,'digest',return_value='a'*64),patch.object(a.summary,'checked_aggregate',return_value={'fixed':'aggregate'}):
            return a.collect(git_sha='b'*40,source_digest='a'*64)
    def test_sealed_fake_inventory_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);self.assertEqual(self.invoke(root),{'fixed':'aggregate'})
    def test_resealed_payload_cannot_keep_old_observation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out,record,seal=self.fixture(root)
            (out/'act.f32le').write_bytes(b'changed');seal['files']['act.f32le']=a.file_identity(out/'act.f32le');(out/'SEAL.json').write_text(json.dumps(seal))
            with self.assertRaisesRegex(ValueError,'record/payload'):self.invoke(root)
    def test_unknown_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out,_,_=self.fixture(root);(out/'extra').write_text('x')
            with self.assertRaisesRegex(ValueError,'inventory'):self.invoke(root)
    def test_failed_resource(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out,record,seal=self.fixture(root);seal['resources']['returncode']=1
            (out/'SEAL.json').write_text(json.dumps(seal))
            with self.assertRaisesRegex(ValueError,'completion'):self.invoke(root)
if __name__=='__main__':unittest.main()
