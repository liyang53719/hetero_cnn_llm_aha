"""No model data, libraries, execution or network in archive tests."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from . import validate as v
HERE=Path(__file__).resolve().parent

class EvidenceTests(unittest.TestCase):
    def setUp(self):self.e=v.load(HERE/'EVIDENCE.json')
    def test_exact_archive(self):self.assertEqual(v.validate(self.e)['source_count'],184)
    def test_executed_observer_manifest(self):self.assertTrue(v.verify_observer(HERE.parents[2]))
    def test_no_broader_pass(self):
        for key in self.e['claims']:
            e=deepcopy(self.e);e['claims'][key]=True
            with self.assertRaises(ValueError):v.validate(e)
    def test_failure_cannot_inherit_success(self):
        for key,value in (('status','PASS'),('owner_job_started',True),('returncode',0),('capture_sha256','0'*64)):
            e=deepcopy(self.e);e['failed_attempt'][key]=value
            with self.assertRaises(ValueError):v.validate(e)
    def test_field_deletion_and_extra_payload(self):
        for name in v.FIELDS:
            e=deepcopy(self.e);del e['cases'][0]['observation']['fields'][name]
            with self.assertRaises(ValueError):v.validate(e)
        e=deepcopy(self.e);e['weights']=[0]
        with self.assertRaises(ValueError):v.validate(e)
    def test_packed_counts_are_not_legacy_repeats(self):
        for name in ('softmax_fp32','prob_bf16','normalizer'):
            e=deepcopy(self.e);e['cases'][1]['observation']['fields'][name]['writes']*=8
            with self.assertRaises(ValueError):v.validate(e)
    def test_identity_and_receipt_mutations(self):
        for key in ('observer_pins_sha256','source_manifest_sha256','git_head','library_sha256','harness_sha256'):
            e=deepcopy(self.e);e[key]='0'*len(e[key])
            with self.assertRaises(ValueError):v.validate(e)
        for value in (True,float('nan'),float('inf'),-1,21):
            e=deepcopy(self.e);e['success_postflight']['elapsed_seconds']=value
            with self.assertRaises(ValueError):v.validate(e)
    def test_strict_bytes_and_size(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'e.json'
            for raw in (b'{}',b'{'*25000,(HERE/'EVIDENCE.json').read_bytes()+b' ',b'{"x":1,"x":2}'):
                p.write_bytes(raw)
                with self.assertRaises(ValueError):v.load(p)
    def test_shape_and_terminal_mutation(self):
        for field in ('shape','observed_words','writes','identical_repeats'):
            e=deepcopy(self.e);e['cases'][0]['observation']['fields']['dot_parts'][field]=None
            with self.assertRaises(ValueError):v.validate(e)
        e=deepcopy(self.e);e['cases'][0]['observation']['accepted_retirement']['memory_pending']=True
        with self.assertRaises(ValueError):v.validate(e)

if __name__=='__main__':unittest.main()
