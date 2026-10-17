import unittest
import tempfile
import subprocess
import sys
import json
import hashlib
from pathlib import Path
from fractions import Fraction
import budget as b

class BudgetTests(unittest.TestCase):
    def test_fixed_identity(self):
        self.assertEqual(b.IDEAL,1468464)
        self.assertEqual((b.PAIRS,b.ROWS,b.VECTORS),(99072,1536,71680))
    def test_gates_are_exact_and_floor(self):
        self.assertEqual(b.gate(80)['max_integer_cycles'],1835580)
        self.assertEqual(b.gate(90),dict(numerator=4894880,denominator=3,max_integer_cycles=1631626))
        self.assertLess(Fraction(b.USEFUL,4096*1631627),Fraction(9,10))
    def test_profiles_never_share_pv_work_by_accident(self):
        raw,qk,packed=[b.counts(p) for p in b.PROFILES]
        self.assertEqual((raw['qk_issues'],raw['pv_issues']),(792576,792576))
        self.assertEqual((qk['qk_issues'],qk['pv_issues']),(55296,792576))
        self.assertEqual((packed['qk_issues'],packed['pv_issues']),(55296,16512))
        self.assertEqual(raw['normalize'],792576)
        self.assertEqual(qk['normalize'],792576)
        self.assertEqual(packed['normalize'],99072)
    def test_scalar_work(self):
        c=b.counts('packed_qk_pv')
        self.assertEqual(c['fold_add'],1585152)
        p=b.scalar_bound('packed_qk_pv')
        self.assertEqual(p['scalar_interacceptance_slot_sum'],6310656)
        self.assertEqual(p['scalar_service_lower_bound'],6310655)
        self.assertEqual(p['serial_wall_lower_bound'],7844735)
        self.assertEqual(b.scalar_bound('qk16_only')['scalar_service_lower_bound']-p['scalar_service_lower_bound'],7*b.PAIRS*3)
    def test_full_exp_is_conditional(self):
        self.assertEqual(b.scalar_bound('packed_qk_pv',b.PAIRS)['scalar_interacceptance_slot_sum'],7968768)
        self.assertNotIn('nondivision_state_slots',b.silu_bounds())
        self.assertEqual(b.silu_bounds(b.VECTORS)['nondivision_state_slots'],1576960)
        self.assertEqual(b.silu_bounds(b.VECTORS)['conditional_front_sfu_down_lower_bound'],2250880)
        for x in (-1,b.VECTORS+1,True):
            with self.assertRaises(ValueError):b.silu_bounds(x)
        with self.assertRaises(ValueError):b.scalar_bound('packed_qk_pv',0)
    def test_barriers(self):
        s=b.silu_bounds()
        self.assertEqual(s['front_matrix_barrier'],243840)
        self.assertEqual(s['options0_with_front_down_lower_bound'],2465920)
    def test_reject_measurement_upgrades(self):
        p=b.scalar_bound('packed_qk_pv')
        self.assertTrue(b.validate_claim(p))
        for key in ('rtl_measured','accepted_80','accepted_90','ideal_feed_is_hardware','service_slots_are_wall_cycles'):
            with self.assertRaises(ValueError):b.validate_claim(dict(p,**{key:True}))
        with self.assertRaises(ValueError):b.validate_claim(dict(p,evidence_kind='rtl_measured'))
    def test_invalid_profile_and_gate(self):
        with self.assertRaises(ValueError):b.counts('packed')
        with self.assertRaises(ValueError):b.gate(95)
    def test_missing_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,"source pins mismatch"):
                b.verify_pins(dict(production_source=root,candidate_tree=root,qk16_source=root))
    def test_roots_are_explicit_and_complete(self):
        for roots in (None, {}, {'candidate_tree':'.'}, '.'):
            with self.assertRaisesRegex(ValueError,'explicit source roots required'):
                b.verify_pins(roots)
    def test_portable_cli_does_not_infer_roots(self):
        script=Path(b.__file__).resolve()
        with tempfile.TemporaryDirectory() as cwd:
            run=subprocess.run([sys.executable,'-B',str(script)],cwd=cwd,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIsNone(json.loads(run.stdout)['source_pins_verified_count'])
            partial=subprocess.run([sys.executable,'-B',str(script),'--candidate-tree',cwd],cwd=cwd,capture_output=True,text=True)
            self.assertNotEqual(partial.returncode,0)
            self.assertIn('all three explicit source roots',partial.stderr)
    def test_source_control_edge_traces(self):
        for op,spacing in [('add',3),('mul',3),('cutoff_exp',3),('full_exp',20)]:
            trace=b.control_trace(op)
            self.assertEqual(len(trace)-1,spacing)
            self.assertEqual(trace[-2],'done_ack')
            self.assertEqual(len(trace)-2,spacing-1)
        for latency,spacing in ((25,28),(26,29)):
            self.assertEqual(len(b.control_trace('div',latency))-1,spacing)
        with self.assertRaises(ValueError):b.control_trace('div',14)
    def test_source_pin_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'source';path.write_bytes(b'original')
            expected=hashlib.sha256(b'original').hexdigest()
            self.assertTrue(b.pinned_file_matches(path,expected))
            path.write_bytes(b'tampered')
            self.assertFalse(b.pinned_file_matches(path,expected))
    def test_branch_counts_and_threshold_sides(self):
        for count in (None,b.ROWS,b.PAIRS):
            self.assertGreater(b.scalar_bound('packed_qk_pv',count)['scalar_service_lower_bound'],b.gate(80)['max_integer_cycles'])
        for count in (True,1.0,b.PAIRS+1):
            with self.assertRaises(ValueError):b.scalar_bound('packed_qk_pv',count)
        for p in (80,90):
            limit=b.gate(p)['max_integer_cycles']
            self.assertGreaterEqual(Fraction(b.USEFUL,b.MACS*limit),Fraction(p,100))
            self.assertLess(Fraction(b.USEFUL,b.MACS*(limit+1)),Fraction(p,100))
    def test_dense_dimensions(self):
        self.assertEqual((b.FRONT_DENSE_ISSUES,b.GATE_UP_ISSUES,b.DOWN_ISSUES),(172032,860160,430080))
        self.assertEqual(b.DENSE_ISSUES,1462272)
    def test_report_never_certifies(self):
        r=b.report()
        self.assertFalse(r['rtl_measured']);self.assertFalse(r['accepted_80']);self.assertFalse(r['accepted_90'])

if __name__=='__main__':unittest.main()
