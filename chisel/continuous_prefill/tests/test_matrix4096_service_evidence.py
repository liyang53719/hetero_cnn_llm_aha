#!/usr/bin/env python3
"""Reject altered diagnostic evidence; not a new RTL execution.

Set MATRIX_SERVICE_EVIDENCE to the completed service gate output. All negative
copies are preserved under MATRIX_SERVICE_NEGATIVE_ROOT (or a fresh /tmp dir).
"""
from pathlib import Path
import os,shutil,struct,tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_matrix4096_service import check

class ServiceEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=Path(os.environ['MATRIX_SERVICE_EVIDENCE']).resolve()
        cls.out=Path(os.environ.get('MATRIX_SERVICE_NEGATIVE_ROOT',tempfile.mkdtemp(prefix='matrix_service_neg_')))
        cls.out.mkdir(parents=True,exist_ok=True)
    def copied(self,label):
        target=self.out/label
        if target.exists():raise RuntimeError('preserve prior negative test '+label)
        target.mkdir();(target/'outputs').mkdir()
        for name in ('simulation.exit','run.log','outputs/actual.f32le','outputs/reference.f32le','outputs/all_elements.csv'):
            shutil.copyfile(self.base/name,target/name)
        return target
    def test_complete(self):
        r=check(self.base);self.assertEqual(r['checked_fp32'],1048576)
        self.assertFalse(r['scope']['host_idma_included'])
    def test_nonzero_exit(self):
        p=self.copied('exit');(p/'simulation.exit').write_text('1\n')
        with self.assertRaises(ValueError):check(p)
    def test_one_changed_actual(self):
        p=self.copied('actual')
        with (p/'outputs/actual.f32le').open('r+b') as f:f.write(b'\x00'*4)
        with self.assertRaises(ValueError):check(p)
    def test_identically_changed_actual_reference(self):
        p=self.copied('both')
        for n in ('actual','reference'):
            with (p/f'outputs/{n}.f32le').open('r+b') as f:f.write(b'\x00'*4)
        with self.assertRaises(ValueError):check(p)
    def test_truncated_csv(self):
        p=self.copied('csv');q=p/'outputs/all_elements.csv';q.write_text(q.read_text().splitlines()[0]+'\n')
        with self.assertRaises(ValueError):check(p)
    def test_duplicate_receipt(self):
        p=self.copied('duplicate');q=p/'run.log';s=q.read_text();q.write_text(s+s.splitlines()[-1]+'\n')
        with self.assertRaises(ValueError):check(p)
    def test_wrong_service_period(self):
        p=self.copied('period');q=p/'run.log';q.write_text(q.read_text().replace('steady_period_min=10','steady_period_min=1',1))
        with self.assertRaises(ValueError):check(p)
    def test_scope_inflation(self):
        p=self.copied('scope');q=p/'run.log';q.write_text(q.read_text().replace('host_idma=0','host_idma=1'))
        with self.assertRaises(ValueError):check(p)
if __name__=='__main__':unittest.main(verbosity=2)
