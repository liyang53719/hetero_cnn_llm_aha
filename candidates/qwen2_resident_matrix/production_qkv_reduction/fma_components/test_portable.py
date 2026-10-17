import json,unittest,tempfile
from pathlib import Path
import prepare_firtool
P=Path(__file__).resolve().parent
class Portable(unittest.TestCase):
 def test_evidence_scope(self):
  r=json.loads((P/'SAFE_EVIDENCE.json').read_text());self.assertEqual(r['source_count'],93);self.assertEqual(len(r['classes']),553);self.assertEqual(len(r['components']['files']),4);self.assertFalse(r['numerical']);self.assertFalse(r['protocol_execution']);self.assertEqual(r['components']['total_module_definitions'],8)
 def test_no_identity_or_payload(self):
  s=(P/'SAFE_EVIDENCE.json').read_text()
  for word in ['boot_id','parent_pid','/workspace/','/tmp/','owner_identity','"session"']:self.assertNotIn(word,s)
  for f in P.rglob('*'):
   if f.is_file():self.assertNotIn(f.suffix,['.sv','.fir','.class','.jar','.log'])
 def test_archive_rejection(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);a=p/'archive';a.write_bytes(b'not official');o=p/'out'
   with self.assertRaises(ValueError):prepare_firtool.prepare(a,o)
   self.assertFalse(o.exists())
 def test_cleanup_projection(self):
  r=json.loads((P/'SAFE_EVIDENCE.json').read_text())
  for s in r['stages']:
   self.assertTrue(s['cleanup_complete']);self.assertTrue(s['cleanup']['absence_barrier_before_reap']);self.assertEqual(s['exit_code'],0)
if __name__=='__main__':unittest.main()
