import os,json,tempfile,unittest
from pathlib import Path
from . import reproduce as P
class Tests(unittest.TestCase):
 def test_exact_safe_reconstruction(self):
  s,p,launcher=P.reconstructed();e=P.evidence()
  self.assertEqual(len(e['class_sha256_delta']),3);self.assertEqual(len(e['source_sha256_delta']),2)
  self.assertEqual(s['status'],'PASS_SCALA_CLASS_COMPILE_ONLY');self.assertEqual(s['exit_code'],0);self.assertTrue(s['cleanup_complete'])
  self.assertEqual(e['caller']['outer_exit_code'],0)
  for k in ('elaboration','rtl','numerical','performance_claim'):self.assertFalse(e[k])
  self.assertIn('scala.tools.nsc.Main',launcher);self.assertEqual(p['route_pins_sha256'],e['executed_route_pins_sha256'])
 def test_original_receipts_and_classes(self):
  root=os.environ.get('PACKED_QK16_COMPILE_ORIGINALS')
  if not root:self.skipTest('original receipts not supplied')
  x=Path(root)/'packed_qk16_owner_compile_plan_20261017';s,p,launcher=P.reconstructed();e=P.evidence()
  self.assertEqual((x/'attempt/summary.json').read_bytes(),P.encoded(s));self.assertEqual((x/'PLAN.json').read_bytes(),P.encoded(p));self.assertEqual((x/'launch.py').read_text(),launcher)
  self.assertEqual((x/'attempt/CALLER.json').read_bytes(),P.encoded(e['caller']));self.assertEqual((x/'FILEMAP.json').read_bytes(),P.encoded(e['filemap']))
  self.assertEqual(P.sha(x/'attempt/compiler.log'),e['compiler_log_sha256']);self.assertEqual((x/'attempt/compiler.log').stat().st_size,0)
  classes=x/'attempt/classes';self.assertEqual({str(f.relative_to(classes)):P.sha(f) for f in classes.rglob('*') if f.is_file()},s['classes'])
 def test_real_rebuild_and_command(self):
  root=os.environ.get('PACKED_QK16_COMPILE_ORIGINALS')
  if not root:self.skipTest('original sources/JARs not supplied')
  w=Path(root)
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'source';self.assertEqual(len(P.compose(out,original_root=w/'public-recipe-cloud-be00-20261016/source',hardfloat_root=w/'packed_qk_hardfloat_source_20261017')),83)
   cmd=P.command('/usr/lib/jvm/java-21-openjdk-amd64/bin/java',w/'packed_compile_dependency_cache',out,Path(d)/'classes');self.assertEqual(sum(x.endswith('.scala') for x in cmd),83);self.assertIn('scala.tools.nsc.Main',cmd)
 def test_dependency_drift_rejected(self):
  from unittest.mock import patch
  with patch.object(P,'sha',return_value='0'*64):
   with self.assertRaisesRegex(ValueError,'own evidence drift'):P.check()
