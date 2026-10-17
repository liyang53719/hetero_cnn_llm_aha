import hashlib,json,unittest
from pathlib import Path
P=Path(__file__).resolve().parent
class Portable(unittest.TestCase):
 def test_operational_pins(self):
  for n,h in json.loads((P/'OPERATIONAL_PINS.json').read_text()).items():self.assertEqual(hashlib.sha256((P/n).read_bytes()).hexdigest(),h,n)
 def test_projection(self):
  r=json.loads((P/'STRUCTURE_PASS_PROJECTION.json').read_text());self.assertEqual(r['status'],'PASS_PRODUCTION_CHIRRTL_STRUCTURE_ONLY');self.assertEqual(len(r['classes']),548);self.assertEqual(r['structure']['bytes'],39580497);self.assertEqual(r['structure']['definition_count'],689);self.assertFalse(r['protocol_execution']);self.assertIsNone(r['actual_job_m'])
 def test_safe_payload(self):
  for p in P.rglob('*'):
   if not p.is_file():continue
   self.assertNotIn(p.suffix,['.class','.jar','.fir','.sv','.bin','.log']);s=p.read_text();self.assertNotIn('/'+'workspace'+'/',s);self.assertNotIn('/'+'home'+'/'+'agent'+'/',s)
  for n in ['STRUCTURE_PASS_PROJECTION.json','FAILURE_HISTORY_PROJECTION.json']:
   s=(P/n).read_text()
   for k in ['"parent_pid"','"boot_id"','"owner_identity"','"session"','"stop"']:self.assertNotIn(k,s)
 def test_failures_preserved(self):
  a=json.loads((P/'FAILURE_HISTORY_PROJECTION.json').read_text());self.assertEqual([x['version'] for x in a],[3,4]);self.assertEqual(a[1]['diagnostic']['bytes'],39580497)
if __name__=='__main__':unittest.main()
