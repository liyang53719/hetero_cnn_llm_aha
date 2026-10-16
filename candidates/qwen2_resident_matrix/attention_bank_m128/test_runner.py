import io,json,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ..attention_scheduled_numeric.controller import Result
from . import check_sources,controller,run_numeric as runner

class RunnerTests(unittest.TestCase):
    def receipt(self):
        e=runner.expected_counts(32)
        return dict(status='PASS_BANK_TILED_ATTENTION',rows=32,one_job_per_pass=True,native_arithmetic=False,rtl_execution=False,
          source_postflight_complete=True,source_sha256={'a':'b'},output_sha256='0'*64,scores_sha256='1'*64,
          counts=dict(matrix_steps=e['matrix_steps'],matrix_returns=e['matrix_steps'],matrix_groups=e['matrix_groups'],
            matrix_result_acks=e['matrix_groups'],selected_fmas=e['selected_fmas'],scratch_acks=e['transactions'],scratch_edges=e['bank_edges']))
    def test_exact_shape_counts(self):
        for rows,steps,groups,pairs in ((17,2034,250,1836),(32,5664,640,6336),(128,71808,7168,99072)):
            e=runner.expected_counts(rows)
            self.assertEqual((e['matrix_steps'],e['matrix_groups'],e['pairs']),(steps,groups,pairs))
            self.assertEqual(e['transactions'],7*pairs)
        for rows in (True,16,0,129):
            with self.assertRaises(ValueError):runner.expected_counts(rows)
    def test_m128_requires_same_source_m32_before_fixture(self):
        with patch.object(check_sources,'check'),patch.object(check_sources,'snapshot',return_value={}),patch.object(runner,'fixture') as fixture:
            with self.assertRaises(ValueError):runner.run(128)
            fixture.assert_not_called()
    def test_prerequisite_typed_counts_sources_and_digest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m32.json';good=self.receipt();p.write_text(json.dumps(good))
            self.assertEqual(len(runner.prerequisite(p,{'a':'b'})),64)
            for key,value in (('rows',True),('source_postflight_complete',1),('source_sha256',{}),('output_sha256','X'*64)):
                bad=self.receipt();bad[key]=value;p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):runner.prerequisite(p,{'a':'b'})
            bad=self.receipt();bad['counts']['matrix_steps']=5664.0;p.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):runner.prerequisite(p,{'a':'b'})
    def test_success_real_result_schema_control_only(self):
        e=runner.expected_counts(17);output=(0,)*(1536*17);scores=(0,)*e['pairs']
        counts=dict(matrix_steps=e['matrix_steps'],matrix_returns=e['matrix_steps'],matrix_groups=e['matrix_groups'],matrix_result_acks=e['matrix_groups'],
          selected_fmas=e['selected_fmas'],scratch_read_requests=e['transactions'],scratch_write_requests=0,scratch_acks=e['transactions'],scratch_edges=e['bank_edges'],scalar_packets=1,scalar_packet_acks=1)
        actual=Result(output,scores,tuple(sorted(counts.items())),123)
        oracle=SimpleNamespace(run=lambda:output,scores=lambda:(scores,scores),requests=range(e['legacy_requests']),scalar=SimpleNamespace(trace=SimpleNamespace(hexdigest=lambda:'0'*64)))
        with patch.object(check_sources,'check'),patch.object(check_sources,'snapshot',return_value={}),patch.object(runner,'fixture',return_value=((),(),())),patch.object(runner,'Oracle',return_value=oracle),patch.object(controller,'Controller',return_value=SimpleNamespace(run=lambda *a:actual)),redirect_stdout(io.StringIO()):
            report=runner.run(17)
        self.assertEqual(report['modeled_ticks'],123);self.assertEqual(report['status'],'PASS_BANK_TILED_ATTENTION')
    def test_timeout_retains_source_identity_no_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json'
            with patch('sys.argv',['run','--rows','17','--seconds','1','--output',str(p)]),patch.object(runner,'run',side_effect=TimeoutError),redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(),1)
            r=json.loads(p.read_bytes());self.assertFalse(r['numerical_acceptance']);self.assertFalse(r['source_postflight_complete']);self.assertIsInstance(r['source_sha256'],dict)
    def test_source_mutation_rejects(self):
        original=Path.read_bytes
        target=check_sources.ROOT/'candidates/qwen2_resident_matrix/attention_bank_multirow/oracle.py'
        def changed(path):return original(path)+(b'\n' if path==target else b'')
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaises(ValueError):check_sources.check()
if __name__=='__main__':unittest.main()
