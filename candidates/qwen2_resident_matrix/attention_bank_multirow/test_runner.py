import json,tempfile,unittest,io
from contextlib import redirect_stdout
from types import SimpleNamespace
from ..attention_scheduled_numeric.controller import Result
from . import check_sources,profile
from pathlib import Path
from unittest.mock import patch
from . import run_calibration as runner


class RunnerTests(unittest.TestCase):
    def test_m128_never_admitted(self):
        for rows in (True,0,3,128):
            with self.assertRaises(ValueError):runner.run(rows)

    def test_timeout_is_explicit_failure_without_math(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.json'
            args=['calibrate','--rows','4','--seconds','1','--output',str(path)]
            with patch('sys.argv',args),patch.object(runner,'run',side_effect=TimeoutError),redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(),1)
            receipt=json.loads(path.read_text())
            self.assertEqual(receipt['status'],'FAILED_CALIBRATION')
            self.assertFalse(receipt['numerical_acceptance'])
            self.assertFalse(receipt['m128_executed'])
            self.assertIsInstance(receipt['source_sha256'],dict)
            self.assertFalse(receipt['source_postflight_complete'])

    def test_success_report_uses_actual_result_schema_control_only(self):
        output=(0,)*(4*1536);scores=(0,)*120
        counts=dict(matrix_steps=404,scratch_read_requests=840,scratch_write_requests=0,scratch_edges=2522)
        actual=Result(output,scores,tuple(sorted(counts.items())),12345)
        trace=SimpleNamespace(hexdigest=lambda:'0'*64)
        oracle=SimpleNamespace(run=lambda:output,scores=lambda:(scores,scores),
            scalar=SimpleNamespace(trace=trace),requests=range(1920))
        candidate=SimpleNamespace(run=lambda *args:actual)
        with patch.object(check_sources,'check'),patch.object(check_sources,'snapshot',return_value={'fixture':'control-only'}), \
             patch.object(runner,'fixture',return_value=((),(),())),patch.object(runner,'Oracle',return_value=oracle), \
             patch.object(profile,'Controller',return_value=candidate),redirect_stdout(io.StringIO()):
            result=runner.run(4)
        self.assertEqual(result['modeled_ticks'],12345)
        self.assertEqual(result['status'],'PASS_MULTIROW_FRACTION_CALIBRATION')
        self.assertFalse(result['native_arithmetic'])
        self.assertFalse(result['m128_executed'])

    def test_word_digest_order_and_shape(self):
        self.assertNotEqual(runner.words_hash((1,2)),runner.words_hash((2,1)))
        self.assertEqual(len(runner.words_hash((0,))),64)

if __name__=='__main__':unittest.main()
