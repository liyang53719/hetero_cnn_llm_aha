"""Negative tests for the fixed real16 evidence gate; fixtures are not RTL results."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_qwen2_real16.py'
spec = importlib.util.spec_from_file_location('real16_verifier', SCRIPT)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def fixture_log():
    rows = []
    for i, (name, width) in enumerate(v.STAGES):
        count = width * 16
        rows += [f'STAGE_CHECK phase={i} name={name} values={count} max_abs=0 rel_l2=0 bit_diffs=0 cycle={100+i*100}',
                 f'STAGE_MEMORY phase={i} reads=1 write_acks={count//16} visible_bytes={count*4} write_trace_fnv=1234']
    rows += ['DDR_GUARD_PASS visible_write_bytes=2654208 host_intermediate_writes=0',
             'CONTINUOUS_QWEN2_BLOCK_PASS tokens=16 hidden=1536 ffn=8960 heads=12 kv_heads=2 phases=15 checked_fp32=663552 bit_diffs=0 max_abs=0 cycles=1501 macs=749101056 read_bytes=960 write_bytes=2654208 request_stalls=1 response_delay_cycles=1 hash=1234 host_intermediate_writes=0 full_model=0 canonical_512_array=0 executed_macs=749101056']
    return '\n'.join(rows)+'\n'


class Real16EvidenceTests(unittest.TestCase):
    def test_accepts_complete_well_formed_log_fixture(self):
        stages, memory, final = v.parse_log(fixture_log())
        self.assertEqual(len(stages), 15)
        self.assertEqual(len(memory), 15)
        self.assertEqual(int(final['checked_fp32']), v.EXPECTED_VALUES)

    def test_rejects_every_incomplete_stage_prefix(self):
        for n in range(15):
            with self.subTest(last_phase=n):
                lines = fixture_log().splitlines()
                with self.assertRaises(ValueError):
                    v.parse_log('\n'.join(lines[:2*n]+lines[-2:]))

    def test_rejects_duplicate_stage(self):
        text = fixture_log()
        with self.assertRaises(ValueError):
            v.parse_log(text + text.splitlines()[0] + '\n')

    def test_rejects_reordered_stages(self):
        lines=fixture_log().splitlines(); lines[0],lines[2]=lines[2],lines[0]
        with self.assertRaises(ValueError):v.parse_log('\n'.join(lines))

    def test_rejects_duplicate_completion(self):
        text=fixture_log()
        with self.assertRaises(ValueError):v.parse_log(text+text.splitlines()[-1]+'\n')

    def test_rejects_tiny_shape(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('hidden=1536','hidden=64'))

    def test_rejects_wrong_token_count(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('tokens=16','tokens=1'))

    def test_rejects_single_changed_word(self):
        text=fixture_log().replace('bit_diffs=0','bit_diffs=1',1)
        with self.assertRaises(ValueError):v.parse_log(text)

    def test_rejects_nonzero_numeric_error(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('max_abs=0','max_abs=1e-12',1))

    def test_rejects_nan_numeric_error(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('rel_l2=0','rel_l2=nan',1))

    def test_rejects_short_write_ack(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('write_acks=1536','write_acks=1535',1))

    def test_rejects_wrong_stage_name(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('name=gate','name=up'))

    def test_rejects_host_intermediate_write(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('host_intermediate_writes=0','host_intermediate_writes=1'))

    def test_rejects_wrong_mac_budget(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('macs=749101056','macs=1'))

    def test_rejects_unexpected_backend(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('canonical_512_array=0','canonical_512_array=1'))

    def test_rejects_missing_memory_row(self):
        lines=fixture_log().splitlines();del lines[1]
        with self.assertRaises(ValueError):v.parse_log('\n'.join(lines))

    def test_rejects_missing_ddr_guards(self):
        text='\n'.join(x for x in fixture_log().splitlines() if not x.startswith('DDR_GUARD_PASS'))
        with self.assertRaises(ValueError):v.parse_log(text)

    def test_rejects_no_backpressure(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('request_stalls=1','request_stalls=0'))

    def test_rejects_fatal_even_with_pass(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log()+'BLOCK_FAIL: unexpected\n')

    def test_rejects_conflicting_duplicate_log_fields(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('tokens=16','tokens=1 tokens=16'))

    def test_rejects_wrong_guard_count(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('DDR_GUARD_PASS visible_write_bytes=2654208','DDR_GUARD_PASS visible_write_bytes=64'))

    def test_rejects_memory_read_disagreement(self):
        with self.assertRaises(ValueError):v.parse_log(fixture_log().replace('read_bytes=960','read_bytes=1'))

    def test_optimized_python_cannot_disable_checks(self):
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/'probe.py'
            script.write_text('import importlib.util\n'
                f's=importlib.util.spec_from_file_location("v",{str(SCRIPT)!r})\n'
                'v=importlib.util.module_from_spec(s);s.loader.exec_module(v)\n'
                f'v.parse_log({fixture_log().replace("tokens=16","tokens=1")!r})\n')
            for flags in [[],['-O'],['-OO']]:
                result=subprocess.run([sys.executable,*flags,str(script)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('wrong tokens',result.stderr)


if __name__=='__main__':unittest.main()
