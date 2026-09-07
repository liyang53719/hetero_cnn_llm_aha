#!/usr/bin/env python3
"""Read-only sealer regression tests against preserved actual tiny DUT evidence."""
import csv
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SCRIPT=Path(os.environ.get('OWNER_SEAL_SCRIPT', str(HERE.parent/'scripts/seal_owner_block_delivery.py')))
spec=importlib.util.spec_from_file_location('owner_seal', SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
EVIDENCE=Path(os.environ.get('OWNER_EVIDENCE', '/nonexistent/owner_tiny_proof')).resolve()
REPO=Path(os.environ.get('OWNER_REPO', str(HERE.parents[2]))).resolve()
COMMIT=(EVIDENCE/'source_base_commit.txt').read_text().strip() if (EVIDENCE/'source_base_commit.txt').is_file() else ''

@unittest.skipUnless('OWNER_EVIDENCE' in os.environ, 'set OWNER_EVIDENCE to an actual tiny16 owner proof')
class SealerTest(unittest.TestCase):
    def test_actual_csv_matches_all_19968_words(self):
        self.assertEqual(m.compare_csv(EVIDENCE),19968)
    def test_actual_source_and_public_parser_identity(self):
        identity=m.source_identity(REPO,EVIDENCE,COMMIT)
        self.assertGreaterEqual(len(identity),228)
    def test_full_actual_tiny_evidence(self):
        self.assertEqual(m.validate_case(REPO,EVIDENCE,COMMIT,64,128)['checked_fp32'],19968)
    def test_wrong_required_geometry(self):
        with self.assertRaisesRegex(ValueError,'geometry'):
            m.validate_case(REPO,EVIDENCE,COMMIT,1536,8960)
    def test_invalid_source_identity(self):
        for bad in ('main','x',COMMIT.upper()):
            with self.subTest(value=bad),self.assertRaises(ValueError):
                m.source_identity(REPO,EVIDENCE,bad)
    def test_unsafe_paths(self):
        for bad in ('/etc/passwd','../fixture/manifest.json','tensors/../../xx'):
            with self.subTest(path=bad),self.assertRaises(ValueError):
                m.read_safe(EVIDENCE,bad)
    def test_missing_csv_rejected(self):
        with patch.object(Path,'is_file',return_value=False),self.assertRaises(ValueError):
            m.compare_csv(EVIDENCE)
    def mutate_rows(self, transform):
        with gzip.open(EVIDENCE/'all_owner_elements.csv.gz','rt') as stream:
            raw=stream.read()
        rows=list(csv.reader(io.StringIO(raw)));transform(rows)
        buf=io.StringIO();csv.writer(buf).writerows(rows);text=buf.getvalue()
        with patch.object(m.gzip,'open',return_value=io.StringIO(text)):
            with self.assertRaises(ValueError):m.compare_csv(EVIDENCE)
    def test_csv_header(self):self.mutate_rows(lambda r:r[0].__setitem__(0,'wrong'))
    def test_csv_missing_row(self):self.mutate_rows(lambda r:r.pop())
    def test_csv_extra_row(self):self.mutate_rows(lambda r:r.append(r[-1]))
    def test_csv_reordered_row(self):self.mutate_rows(lambda r:r.__setitem__(slice(1,3),[r[2],r[1]]))
    def test_csv_false_reference(self):self.mutate_rows(lambda r:r[1].__setitem__(4,'00000000'))
    def test_wrong_recorded_hash(self):
        original=m.read_safe
        def altered(base,relative):
            data=original(base,relative)
            if relative=='sources.sha256.json':
                obj=json.loads(data);obj[next(iter(obj))]='0'*64;return json.dumps(obj).encode()
            return data
        with patch.object(m,'read_safe',side_effect=altered),self.assertRaises(ValueError):
            m.source_identity(REPO,EVIDENCE,COMMIT)
    def test_failed_gate(self):
        original=m.read_safe
        def altered(base,relative):return b'1\n' if relative=='gate.exit' else original(base,relative)
        with patch.object(m,'read_safe',side_effect=altered),self.assertRaises(ValueError):
            m.validate_case(REPO,EVIDENCE,COMMIT,64,128)
    def test_wrong_commit(self):
        with self.assertRaises(ValueError):m.source_identity(REPO,EVIDENCE,'0'*40)

if __name__=='__main__':unittest.main()
