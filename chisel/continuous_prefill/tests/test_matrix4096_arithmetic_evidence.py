#!/usr/bin/env python3
"""Reject altered copies of a real arithmetic probe; preserve all test copies."""
import os,shutil,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_matrix4096_arithmetic import verify

class ArithmeticEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=Path(os.environ['MATRIX4096_PROBE_EVIDENCE']).resolve()
        cls.workspace=Path(tempfile.mkdtemp(prefix='matrix4096_evidence_',dir=os.environ.get('MATRIX4096_TEST_DIR')))
        verify(cls.base)
    def copy(self):
        root=Path(tempfile.mkdtemp(prefix='case_',dir=self.workspace))
        for rel in ('simulation.exit','run.log','generated/Matrix4096ArithmeticProbe.sv','outputs/actual.f32le','outputs/reference.f32le','outputs/all_elements.csv'):
            dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.base/rel,dst)
        return root
    def test_complete_real_outputs(self):
        r=verify(self.base);self.assertEqual(r['checked_fp32'],102400);self.assertEqual(r['physical_512mac_slices'],8)
    def test_equal_but_wrong_actual_and_reference(self):
        d=self.copy()
        for name in ('actual.f32le','reference.f32le'):
            p=d/'outputs'/name;b=bytearray(p.read_bytes());b[100]^=1;p.write_bytes(b)
        with self.assertRaises(ValueError):verify(d)
    def test_missing_output(self):
        d=self.copy();p=d/'outputs/actual.f32le';p.rename(d/'outputs/actual.withheld')
        with self.assertRaises(OSError):verify(d)
    def test_missing_csv_row(self):
        d=self.copy();p=d/'outputs/all_elements.csv';rows=p.read_text().splitlines();p.write_text('\n'.join(rows[:-1])+'\n')
        with self.assertRaises(ValueError):verify(d)
    def test_nonzero_simulator(self):
        d=self.copy();(d/'simulation.exit').write_text('139\n')
        with self.assertRaises(ValueError):verify(d)
    def test_wrong_physical_topology(self):
        d=self.copy();p=d/'generated/Matrix4096ArithmeticProbe.sv'
        text=p.read_text();self.assertIn('qwen2_matrix_command_endpoint',text)
        p.write_text(text.replace('qwen2_matrix_command_endpoint','unbound_arithmetic_leaf'))
        with self.assertRaises(ValueError):verify(d)
    def test_duplicate_pass_marker(self):
        d=self.copy();p=d/'run.log';text=p.read_text();line=[x for x in text.splitlines() if x.startswith('MATRIX4096_ARITHMETIC_PASS ')][0];p.write_text(text+line+'\n')
        with self.assertRaises(ValueError):verify(d)
if __name__=='__main__':unittest.main(verbosity=2)
