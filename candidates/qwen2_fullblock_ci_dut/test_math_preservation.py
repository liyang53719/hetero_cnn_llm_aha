"""Byte-level unchanged numerical driver body checks, without executing it."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'candidates/qwen2_live_fullblock_model_m128'
NEW=Path(__file__).resolve().parent

class MathPreservationTests(unittest.TestCase):
    def test_tail_identical(self):
        self.assertEqual((OLD/'tail.py').read_bytes(),(NEW/'tail.py').read_bytes())
    def test_runner_only_explicit_bindings_and_preimports(self):
        original=(OLD/'runner.py').read_text()
        expected=original.replace('work/qwen2_live_fullblock_numeric_m128_20261014','work/qwen2_fullblock_ci_dut_numeric')
        expected=expected.replace('from candidates.qwen2_live_attention_model_m128_bounded import native_artifact',
            'from candidates.qwen2_fullblock_ci_dut import native_artifact')
        expected=expected.replace('from candidates.qwen2_live_fullblock_model_m128 import telemetry, statistics, compare',
            'from candidates.qwen2_live_fullblock_model_m128 import telemetry, compare\nfrom candidates.qwen2_fullblock_ci_dut import statistics')
        for module in ('gates','tail'):
            expected=expected.replace('from candidates.qwen2_live_fullblock_model_m128 import '+module,
                'from candidates.qwen2_fullblock_ci_dut import '+module)
        actual=(NEW/'runner.py').read_text()
        actual=actual.replace('    from candidates.qwen2_fullblock_ci_dut import runtime_adapter\n    runtime_adapter.initialize()\n','',1)
        self.assertEqual(expected,actual)
if __name__=='__main__':unittest.main()
