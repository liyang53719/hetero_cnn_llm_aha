"""Read-only build evidence; optional original receipt check never loads ELF."""
import hashlib,json,os,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class EvidenceTests(unittest.TestCase):
 def test_scope_and_sources(self):
  e=json.loads((HERE/'EVIDENCE.json').read_bytes())
  self.assertEqual((e['status'],e['attempts'],e['exit_code']),('PASS_STRICT_COMBINED_BUILD_ONLY',1,0))
  self.assertFalse(e['native_numerical_executed']);self.assertFalse(e['full_public_admitted']);self.assertFalse(e['rtl_executed'])
  self.assertLess(e['external_wall_seconds'],35);self.assertLess(e['build_verify_seconds'],e['external_wall_seconds'])
  from ..attention_packed_m16 import prepare
  p=prepare.check();expected={**p['sources'],**p['own'],**p['generated']}
  self.assertEqual(e['installed_source_sha256'],expected)
  self.assertEqual(e['executed_pins_sha256'],sha(prepare.HERE/'pins.json'))
  self.assertEqual(e['strict_flags'],['-shared','-fPIC','-O2','-ffp-contract=off','-fno-fast-math'])
  self.assertEqual(len(e['compile_source_sha256']),4)
 @unittest.skipUnless(os.environ.get('PACKED_M16_BUILD_RECEIPTS'),'external original receipts required')
 def test_original_receipts(self):
  e=json.loads((HERE/'EVIDENCE.json').read_bytes());r=Path(os.environ['PACKED_M16_BUILD_RECEIPTS'])
  for name,h in e['original_sha256'].items():self.assertEqual(sha(r/name),h,name)
  b=json.loads((r/'BUILD.json').read_bytes());s=json.loads((r/'SUPERVISOR.json').read_bytes());c=json.loads((r/'library/official_bf16_compile.json').read_bytes())
  self.assertEqual(b['source_sha256'],e['installed_source_sha256']);self.assertEqual(c['source_sha256'],e['compile_source_sha256'])
  self.assertEqual(sha(Path(c['library'])),e['library_sha256']);self.assertEqual(s['wall_seconds'],e['external_wall_seconds'])
  self.assertEqual(b['elapsed_seconds'],e['build_verify_seconds']);self.assertEqual(c['compiler'],e['compiler'])
  self.assertEqual(c['argv'][1:6],e['strict_flags']);self.assertEqual(c['status'],'PASS')
  for n,h in e['installed_source_sha256'].items():self.assertEqual(sha(r/'source'/n),h,n)
  self.assertEqual(json.loads((r/'source_before.json').read_bytes()),b['source_sha256'])
if __name__=='__main__':unittest.main()
