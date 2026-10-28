import ast
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import run_reference as r
import stimulus as s


class PreparationTests(unittest.TestCase):
    def test_exact_five_profiles(self):
        profiles = [r.load_profile(i) for i in range(5)]
        self.assertEqual([p['width'] for p in profiles], [1536, 1024, 1024, 2048, 2048])
        self.assertEqual([p['layer'] for p in profiles], [0, 0, 3, 0, 3])

    def test_invalid_profile(self):
        for i in (-1, 5, True):
            with self.assertRaises(ValueError): r.load_profile(i)

    def test_original_35b_generator(self):
        raw = s.bf16_bytes(2048, 0x35b00380)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'c32e36dd356244838b17f8aebd8a0e647c5a09198365ad32c6f7996adef237bb')

    def test_storage_widen_exact(self):
        raw = bytes.fromhex('0000803f80800080')
        self.assertEqual(s.storage_bytes(raw, 'FP32'), bytes.fromhex('000000000000803f0000808000000080'))
        self.assertEqual(s.storage_bytes(raw, 'BF16'), raw)

    def test_bad_storage(self):
        for raw, dtype in ((b'\0', 'FP32'), (b'\0\0', 'FP16')):
            with self.assertRaises(ValueError): s.storage_bytes(raw, dtype)

    def test_finite_generator(self):
        for i in range(5):
            p = r.load_profile(i); raw = s.bf16_bytes(p['width'], p['seed'])
            self.assertEqual(len(raw), 128*p['width']*2)
            self.assertTrue(all((x[0] & 0x7f80) != 0x7f80 for x in struct.iter_unpack('<H', raw)))

    def test_input_export_fresh_only(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/'new'
            m = s.emit(r.load_profile(0), target)
            self.assertEqual(m['files']['hidden.storage.bin']['bytes'], 128*1536*4)
            with self.assertRaises(FileExistsError): s.emit(r.load_profile(0), target)

    def test_exact_tensor_count_geometry(self):
        p = json.loads((r.HERE/'tensor_acquisition_plan.json').read_text())
        counts=[]
        for i in range(5):
            profile=r.load_profile(i)
            rows=[x for x in p[profile['model']]['tensors'] if f".layers.{profile['layer']}." in x['name']]
            counts.append(len(rows))
        self.assertEqual(counts, [12,14,11,18,15])

    def test_incomplete_payload_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5):
                with self.assertRaises(ValueError): r.tensor_records(d, r.load_profile(i))

    def test_final_component_symlink_rejected(self):
        profile=r.load_profile(0)
        plan=json.loads((r.HERE/'tensor_acquisition_plan.json').read_text())[profile['model']]
        row=next(x for x in plan['tensors'] if x['name'].endswith('input_layernorm.weight'))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); folder=root/profile['model']; folder.mkdir()
            raw=b'\0'*row['bytes']; real=folder/'real.bin'; real.write_bytes(raw)
            link=folder/'link.bin'; link.symlink_to(real)
            rec=dict(row, status='ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT',
                     revision=profile['checkpoint_revision'], model=profile['model'],
                     file=str(link.relative_to(root)), actual_bytes=len(raw), actual_sha256=hashlib.sha256(raw).hexdigest())
            (folder/(row['name']+'.receipt.json')).write_text(json.dumps(rec))
            with self.assertRaisesRegex(ValueError,'symlink'): r.tensor_records(root,profile)

    def test_no_torch_import_on_prepare(self):
        import sys
        self.assertNotIn('torch', sys.modules)

    def test_no_arithmetic_replacement_or_expert_injection(self):
        source=(r.HERE/'run_reference.py').read_text()
        tree=ast.parse(source)
        targets=[n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Store)]
        self.assertNotIn('forward',targets)
        self.assertNotIn('topk',targets)
        self.assertNotIn('torch_chunk_gated_delta_rule',targets)
        self.assertNotIn('selected_experts',targets)
        self.assertIn('CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY',source)


if __name__ == '__main__': unittest.main()
