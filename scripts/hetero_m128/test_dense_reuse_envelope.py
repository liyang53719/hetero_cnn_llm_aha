import unittest
from fractions import Fraction
from pathlib import Path
import os
import tempfile

import dense_reuse_envelope as s

ROOT=Path(os.environ.get("HETERO_M128_WORKSPACE", Path(__file__).resolve().parents[2]))

class TestStaticModel(unittest.TestCase):
    def test_original_first_projection_cases(self):
        a=s.verified(ROOT/"round_20261120T1433/mac_contract/RESULT.json",s.PINNED["pc1"])
        b=s.verified(ROOT/"round_20261120T1433/qwen2_whole_roof/RESULT.json",s.PINNED["qwen2"])
        result=s.study(a,b)
        self.assertFalse(result["whole_block_utilization"])
        self.assertEqual([Fraction(p["scenarios"][0]["read_bytes_per_cycle_required"]["90"]) for p in result["pc1"]],
                         [Fraction(624,5),Fraction(294,5),Fraction(297,5),Fraction(117,2),Fraction(117,2)])
        self.assertTrue(all(r["scenarios"][0]["extra_logical_accumulator_bytes_vs_original"]==49152
                            for r in result["pc1"]))

    def test_reuse_once_both_precisions(self):
        a=s.evaluate(1536,1536,4,1)
        self.assertEqual(a["both_reads_optimistically_overlapped_with_compute"]["64"]["dense_only_utilization_upper"], "6/13")
        self.assertEqual(a["weight_only_bytes_per_cycle_required"]["90"],"576/5")
        b=s.evaluate(8192,2048,2,1)
        self.assertEqual(b["weight_only_bytes_per_cycle_required"]["90"],"288/5")
        self.assertEqual(b["both_reads_optimistically_overlapped_with_compute"]["64"]["dense_only_utilization_upper"],"64/65")
        self.assertEqual(b["output_bytes_omitted_from_read_envelope"],2<<20)

    def test_down_projection_requires_activation_reread_or_large_c(self):
        rows=s.pareto([s.evaluate(1536,8960,4,g) for g in range(1,7)])
        self.assertEqual([r["serial_n_groups"] for r in rows],[6,3,2,1])
        self.assertEqual([r["n_tiles_per_group"] for r in rows],[1,2,3,6])
        self.assertTrue(all(r["cached_m_rows"]==32 for r in rows))
        self.assertEqual(rows[0]["a_external_bytes"],(32+96*6)*8960*4)
        self.assertEqual(rows[-1]["accumulator_logical_bytes"], 768*1024)
        self.assertEqual(rows[-1]["a_external_bytes"],128*8960*4)
        self.assertEqual(len({r["unique_weight_bytes"] for r in rows}),1)

    def test_pareto_does_not_charge_unnecessary_accumulators(self):
        rows=s.pareto([s.evaluate(4096,1024,2,g) for g in range(1,17)])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["cached_m_rows"],128)
        self.assertEqual(rows[0]["a_external_bytes"],128*1024*2)

    def test_bad_pin_and_unsupported(self):
        with self.assertRaisesRegex(ValueError,"geomet"):
            s.evaluate(1537,1024,4,1)
        with self.assertRaisesRegex(ValueError,"concurrent"):
            s.evaluate(256,1024,4,2)
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"bad"
            f.write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError,"pin mismatch"):
                s.verified(f,"00"*32)

if __name__=="__main__":
    unittest.main()
