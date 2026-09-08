#!/usr/bin/env python3
"""Tests of the evidence checker only; never count these as RTL simulation.

All created directories are deliberately preserved for review.
"""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_pipeline_components import bf16,pipeline_values,check_outputs


class EvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(tempfile.mkdtemp(prefix='pipeline_auditor_',dir=os.environ.get('PIPELINE_TEST_DIR')))
        cls.expected=pipeline_values(0x85,2,3)

    def fixture(self):
        d=Path(tempfile.mkdtemp(prefix='case_',dir=self.root));(d/'outputs').mkdir()
        (d/'simulation.exit').write_text('0\n');(d/'run.log').write_text('TEST_CHECKER_FIXTURE_ONLY\n')
        for n in ('actual','reference'):(d/'outputs'/f'{n}.f32le').write_bytes(self.expected.astype('<f4').tobytes())
        return d

    def test_complete_fixed_vector(self):
        r=check_outputs(self.fixture(),self.expected)
        self.assertEqual(r['checked_fp32'],24576)

    def test_changed_actual_and_reference(self):
        d=self.fixture()
        for n in ('actual','reference'):
            p=d/'outputs'/f'{n}.f32le';x=bytearray(p.read_bytes());x[101]^=1;p.write_bytes(x)
        with self.assertRaises(ValueError):check_outputs(d,self.expected)

    def test_changed_reference(self):
        d=self.fixture();p=d/'outputs/reference.f32le';x=bytearray(p.read_bytes());x[51]^=1;p.write_bytes(x)
        with self.assertRaises(ValueError):check_outputs(d,self.expected)

    def test_short_output(self):
        d=self.fixture();p=d/'outputs/actual.f32le';p.write_bytes(p.read_bytes()[:-4])
        with self.assertRaises(ValueError):check_outputs(d,self.expected)

    def test_nonfinite(self):
        d=self.fixture();p=d/'outputs/actual.f32le';p.write_bytes(struct.pack('<I',0x7fc00001)+p.read_bytes()[4:])
        with self.assertRaises(ValueError):check_outputs(d,self.expected)

    def test_successful_failure_recovery_is_not_a_failure(self):
        d=self.fixture();(d/'run.log').write_text('PIPELINE_FAILURE_GATE_PASS cases=5\n')
        self.assertEqual(check_outputs(d,self.expected)['bit_differences'],0)

    def test_nonzero_exit(self):
        d=self.fixture();(d/'simulation.exit').write_text('139\n')
        with self.assertRaises(ValueError):check_outputs(d,self.expected)

    def test_failure_log(self):
        d=self.fixture();(d/'run.log').write_text('MATRIX_PIPELINE_FAIL: forced\n')
        with self.assertRaises(ValueError):check_outputs(d,self.expected)

    def test_symlink_output(self):
        d=self.fixture();p=d/'outputs/actual.f32le';saved=p.with_suffix('.saved');p.rename(saved);p.symlink_to(saved)
        with self.assertRaises(ValueError):check_outputs(d,self.expected)

    def test_bf16_rne_ties_and_signed_zero(self):
        u=np.array([0,0x80000000,0x3f808000,0x3f818000,0xbf808000,0xbf818000],dtype='<u4')
        want=np.array([0,0x80000000,0x3f800000,0x3f820000,0xbf800000,0xbf820000],dtype='<u4')
        self.assertTrue(np.array_equal(bf16(u.view('<f4')).view('<u4'),want))

    def test_unselected_columns_stay_zero(self):
        x=self.expected.reshape(6,16,256)
        for c in range(256):
            if not ((0x85>>(c//32))&1):self.assertTrue(np.all(x[:,:,c].view('<u4')==0))

if __name__=='__main__':unittest.main(verbosity=2)
