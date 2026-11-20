"""Tests against the pinned original command tables, plus fail-closed mutations."""
import json
import os
from pathlib import Path
import tempfile
import unittest

import first_projection_contract as c

ROOT = Path(os.getenv("HETERO_M128_WORKSPACE", str(Path(__file__).resolve().parents[2]))).resolve()
INDEX = json.loads(c.pinned(ROOT, c.MAP_PATH, c.MAP_SHA))
def profile(i):
    p = INDEX['profiles'][i]
    return p, *(c.pinned(ROOT,s['file'],s['sha256'],s['bytes']) for s in p['segments'][:2])
def mutate(data,index,bit):
    off = 16*index + bit//8
    return data[:off] + bytes([data[off] ^ (1 << (bit % 8))]) + data[off+1:]

class TestContract(unittest.TestCase):
    def test_exact_five(self):
        out = c.evaluate(ROOT)
        self.assertIsNone(out["whole_block_utilization"])
        self.assertFalse(out["hardware_executed"] or out["weight_payload_bytes_read"])
        self.assertEqual([x['expected_successful_pc1_useful_mac_delta'] for x in out['rows']],
                         [301989888,805306368,536870912,2147483648,2147483648])
        self.assertEqual([x['hard_lower_bound_matrix_cycles'] for x in out['rows']],
                         [73728,196608,131072,524288,524288])
        for row in out['rows']:
            for n, d in [(80, (4,5)), (90, (9,10))]:
                t = row[f'max_pc1_only_cycles_for_{n}_pct']
                useful = row['expected_successful_pc1_useful_mac_delta']
                self.assertGreaterEqual(useful*d[1], c.MACS*t*d[0])
                self.assertLess(useful*d[1], c.MACS*(t+1)*d[0])

    def test_original_feeder_lower_bound_and_target_rate(self):
        rows = [x['dense_feeder_envelope'] for x in c.evaluate(ROOT)['rows']]
        self.assertEqual([x['original_m_cohorts'] for x in rows], [[80,48]]*5)
        self.assertEqual([x['mandatory_ideal_A_then_weight_epochs_cycle_floor'] for x in rows],
                         [307200,401406,270334,1064958,1064958])
        self.assertEqual([x['weight_only_fraction_upper_bound_64B_per_cycle'] for x in rows],
                         ['1/4']+['1/2']*4)
        self.assertEqual([x['weight_only_bytes_per_cycle_needed_for_90_pct'] for x in rows],
                         ['1152/5']+['576/5']*4)
        self.assertEqual(c.page_requests(0,1024,4,512),4)
        self.assertEqual(c.page_requests(576,1024,4,512),8)
        self.assertEqual(c.page_requests(64,1024,4,1024),8)
        self.assertTrue(all(x['extra_logical_FP32_accumulator_payload_bytes_to_hold_eight_not_five_m16n256_contexts']
                         == 49152 for x in rows))
        with self.assertRaisesRegex(ValueError,'envelope'):
            c.streaming_envelope(127,8192,2048,2,2)

    def test_bad_dependency_and_wrong_opcode(self):
        p,cmd,ds = profile(0)
        for bit in (0,24,40):
            with self.subTest(bit=bit), self.assertRaisesRegex(ValueError, 'event dependency'):
                c.extract(p,mutate(cmd,1,bit),ds)

    def test_wrong_matrix_dimension_after_valid_tensor(self):
        p,cmd,ds = profile(0)
        with self.assertRaisesRegex(ValueError,'policy shape'):
            c.extract(p,cmd,mutate(ds,13,88))

    def test_wrong_cold_phase_after_valid_matrix(self):
        for i in range(1,5):
            p,cmd,ds = profile(i)
            with self.subTest(profile=i), self.assertRaisesRegex(ValueError,'cold role-0'):
                c.extract(p,cmd,mutate(ds,22,80))

    def test_wrong_endian_root_and_padding(self):
        p,cmd,ds = profile(0)
        with self.assertRaisesRegex(ValueError,'kind'):
            c.extract(p,mutate(cmd,1,56),ds)
        with self.assertRaisesRegex(ValueError,'padding'):
            c.extract(p,cmd[:-1]+b'\x01',ds)

    def test_no_weight_matching_metadata(self):
        p,cmd,ds = profile(1)
        p = dict(p,segments=p['segments'][:2])
        with self.assertRaisesRegex(ValueError,'readonly weight segment'):
            c.extract(p,cmd,ds)

    def test_wrong_pinned_bytes_or_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            f=root/'data'; f.write_bytes(b'0')
            (root/'link').symlink_to(f)
            with self.assertRaisesRegex(ValueError,'SHA'):
                c.pinned(root,'data','00'*32,1)
            with self.assertRaisesRegex(ValueError,'workspace-relative'):
                c.pinned(root,'link','00'*32,1)

if __name__ == '__main__':
    unittest.main()
