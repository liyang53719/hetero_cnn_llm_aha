import io,json,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ..attention_scheduled_numeric.controller import Result
from . import check_sources,controller,run_numeric as runner
class RunnerTests(unittest.TestCase):
    def test_shape_counts_and_m128_denied(self):
        for rows,steps,groups,transactions in ((17,2034,250,864),(32,5664,640,2304)):
            e=runner.expected_counts(rows);self.assertEqual((e['matrix_steps'],e['matrix_groups'],e['transactions']),(steps,groups,transactions))
            self.assertEqual(e['bank_edges'],3*transactions+2)
        for rows in (True,0,16,128):
            with self.assertRaises(ValueError):runner.run(rows)
    def test_actual_result_schema_control_only(self):
        e=runner.expected_counts(17);output=(0,)*(17*1536);scores=(0,)*e['pairs']
        counts=dict(matrix_steps=e['matrix_steps'],matrix_returns=e['matrix_steps'],matrix_groups=e['matrix_groups'],matrix_result_acks=e['matrix_groups'],selected_fmas=e['selected_fmas'],scratch_read_requests=e['transactions']//2,scratch_write_requests=e['transactions']//2,scratch_acks=e['transactions'],scratch_edges=e['bank_edges'],scalar_packets=1,scalar_packet_acks=1)
        actual=Result(output,scores,tuple(sorted(counts.items())),123)
        oracle=SimpleNamespace(run=lambda:output,scores=lambda:(scores,scores),requests=range(e['legacy_requests']),scalar=SimpleNamespace(trace=SimpleNamespace(hexdigest=lambda:'0'*64)))
        with patch.object(check_sources,'check'),patch.object(check_sources,'snapshot',return_value={}),patch.object(runner,'fixture',return_value=((),(),())),patch.object(runner,'Oracle',return_value=oracle),patch.object(controller,'Controller',return_value=SimpleNamespace(run=lambda *a:actual)),redirect_stdout(io.StringIO()):
            result=runner.run(17)
        self.assertEqual(result['modeled_ticks'],123);self.assertEqual(result['proposed_extra_panel_bytes'],384);self.assertFalse(result['m128_executed'])
    def test_timeout_safe_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json'
            with patch('sys.argv',['run','--rows','17','--seconds','1','--output',str(p)]),patch.object(runner,'run',side_effect=TimeoutError),redirect_stdout(io.StringIO()):self.assertEqual(runner.main(),1)
            r=json.loads(p.read_bytes());self.assertFalse(r['numerical_acceptance']);self.assertFalse(r['source_postflight_complete'])
    def test_actual_dependency_drift_rejects(self):
        read=Path.read_bytes;target=check_sources.ROOT/'candidates/qwen2_resident_matrix/attention_bank_m128/controller.py'
        with patch.object(Path,'read_bytes',lambda p:read(p)+(b'\n' if p==target else b'')):
            with self.assertRaises(ValueError):check_sources.check()
if __name__=='__main__':unittest.main()
