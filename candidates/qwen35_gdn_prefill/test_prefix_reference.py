import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from . import prefix_reference as p


class PrefixReferenceTests(unittest.TestCase):
    def test_pinned_original_class_and_two_fp32_methods(self):
        raw = (p.ROOT / p.SOURCE).read_bytes()
        cls = p.original_rms_class(raw, SimpleNamespace(nn=SimpleNamespace(Module=object)))
        self.assertEqual(cls.__name__, 'Qwen3_5RMSNorm')
        self.assertEqual(set(('_norm', 'forward')) - set(cls.__dict__), set())

    def test_source_drift_refused_before_execution(self):
        raw = (p.ROOT / p.SOURCE).read_bytes()
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            p.original_rms_class(raw.replace(b'1.0 + self.weight.float()', b'0.0 + self.weight.float()'), None)

    def test_signed_zero_diagnostics_keep_raw_difference(self):
        report = p.compare_bf16(bytes.fromhex('0000803f'), bytes.fromhex('0080803f'))
        self.assertEqual(report['bit_mismatches'], 1)
        self.assertEqual(report['signed_zero_only_mismatches'], 1)
        self.assertEqual(report['max_abs'], 0)
        self.assertEqual(report['max_bf16_ulp'], 0)
        self.assertEqual(report['first_bit_mismatch'], 0)
        self.assertIn('NO_NEW_STAGE_THRESHOLD', report['acceptance'])

    def test_nonzero_difference_and_full_shape_required(self):
        report = p.compare_bf16(bytes.fromhex('803f'), bytes.fromhex('813f'))
        self.assertEqual(report['max_bf16_ulp'], 1)
        self.assertEqual(report['max_abs'], 1 / 128)
        for a, b in ((b'', b''), (b'0', b'0'), (b'00', b'0000')):
            with self.assertRaises(ValueError): p.compare_bf16(a, b)

    def test_nonfinite_not_silently_dropped(self):
        for raw in (bytes.fromhex('807f'), bytes.fromhex('c07f'), bytes.fromhex('80ff')):
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                p.compare_bf16(raw, bytes.fromhex('0000'))

    def test_existing_native_thresholds_remain_real_failure(self):
        self.assertTrue(p.original_prefix_gate(bytes.fromhex('803f'),bytes.fromhex('803f'))['passed'])
        report=p.original_prefix_gate(bytes.fromhex('803f'),bytes.fromhex('883f'))
        self.assertFalse(report['passed'])
        self.assertEqual(report['thresholds'],{'max_abs':0.03125,'mean_abs':0.005})

    def test_independent_c_projection_row_column_layout_and_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt=p.build_projection_reference(Path(temporary)/'ref')
            a=np.full((2,1024),0x3f00,dtype='<u2'); a[1]=0x3f80
            b=np.full((3,1024),0x3f00,dtype='<u2'); b[1]=0xbf00; b[2]=0
            raw=p.projection_reference(receipt,a.tobytes(),b.tobytes(),2,3)
            expected=np.array([[0x4380,0xc380,0],[0x4400,0xc400,0]],dtype='<u2')
            self.assertEqual(raw,expected.tobytes())
            with self.assertRaisesRegex(ValueError,'identity drift'):
                p.projection_reference(dict(receipt,library_sha256='0'*64),a.tobytes(),b.tobytes(),2,3)
            with self.assertRaisesRegex(ValueError,'raw BF16'):
                p.projection_reference(receipt,a.tobytes()[:-2],b.tobytes(),2,3)
            b[0,0]=0x7fc0
            with self.assertRaisesRegex(ValueError,'arithmetic failure'):
                p.projection_reference(receipt,a.tobytes(),b.tobytes(),2,3)


if __name__ == '__main__':
    unittest.main()
