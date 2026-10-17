"""Verify compact actual admission evidence; never execute a model or load data."""
import hashlib,json,os,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
EXPECTED='af7c8b8d41190ceb809ca2a02d79161490d3480c9ac48999410e82df9694435f'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def projection(raw):
 if digest(raw)!=EXPECTED:raise ValueError('original probe receipt differs')
 p=json.loads(raw);sources=p['source_sha256']
 return dict(schema=1,status=p['status'],original_probe_sha256=digest(raw),original_probe_bytes=len(raw),
  elapsed_seconds=p['elapsed_seconds'],success=p['success'],negatives=p['negatives'],
  source_count=len(sources),source_manifest_sha256=digest((json.dumps(sources,sort_keys=True,separators=(',',':'))+'\n').encode()),
  snapshot_sha256=p['snapshot_sha256'],numerical_jobs=p['numerical_jobs'],native_forward_executed=p['native_forward_executed'],
  rtl_executed=False,full_public_run=False,full_29_node_acceptance=False)
class Tests(unittest.TestCase):
 def test_fixed_compact_scope(self):
  p=json.loads((HERE/'EVIDENCE.json').read_bytes())
  self.assertEqual(p['original_probe_sha256'],EXPECTED);self.assertEqual(p['source_count'],350)
  self.assertEqual(len(p['negatives']['cases']),13);self.assertEqual(p['success']['runtime_calls'],2)
  self.assertTrue(p['success']['real_snapshot_verified']);self.assertFalse(p['success']['output_directory_created'])
  self.assertEqual(p['numerical_jobs'],0)
  for k in ('native_forward_executed','rtl_executed','full_public_run','full_29_node_acceptance'):self.assertIs(p[k],False)
  self.assertNotIn('/workspace/',json.dumps(p))
  for c in p['negatives']['cases']:self.assertIn(c['runtime_calls'],(0,1))
 def test_exact_original_optional(self):
  path=os.environ.get('PACKED_M128_ADMISSION_PROBE')
  if not path:self.skipTest('exact private original receipt not supplied')
  raw=Path(path).read_bytes();self.assertEqual(projection(raw),json.loads((HERE/'EVIDENCE.json').read_bytes()))
  with self.assertRaises(ValueError):projection(raw+b' ')
if __name__=='__main__':unittest.main()
