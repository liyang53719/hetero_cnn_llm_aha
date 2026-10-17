import hashlib,json,os,tempfile,unittest
from pathlib import Path
from . import prepare as P
class Tests(unittest.TestCase):
 def test_exact_receipt_scope_and_source(self):
  P.check();e=P.evidence();s=e['records']['summary.json']['value']
  self.assertEqual(s['status'],'PASS_SCALA_CLASS_COMPILE_ONLY');self.assertEqual(s['exit_code'],0);self.assertTrue(s['cleanup_complete'])
  self.assertEqual(len(s['classes']),474);self.assertEqual(s['source_sha256'],e['source_plan']['scala']);self.assertEqual(len(s['source_sha256']),83)
  for n in ('elaboration','rtl','numerical','performance_claim'):self.assertFalse(e[n])
  self.assertEqual(P.sha(P.HERE/'executed_launcher.txt'),e['executed_launcher_sha256'])
  for name in ('summary.json','CALLER.json'):
   record=e['records'][name];data=(json.dumps(record['value'],indent=2,sort_keys=True)+'\n').encode()
   self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256']);self.assertEqual(len(data),record['bytes'])
  self.assertEqual(e['records']['CALLER.json']['value']['observed_outer_exit_code'],0)
 def test_actual_original_receipts_and_classes(self):
  root=os.environ.get('PACKED_OWNER_COMPILE_ORIGINALS')
  if not root:self.skipTest('external originals not supplied')
  root=Path(root);attempt=root/'packed_qk_owner_compile_plan_20261017/attempt';e=P.evidence()
  for n,v in e['records'].items():self.assertEqual(P.sha(attempt/n),v['sha256'])
  classes=attempt/'classes';self.assertEqual({str(p.relative_to(classes)):P.sha(p) for p in classes.rglob('*') if p.is_file()},e['records']['summary.json']['value']['classes'])
  self.assertEqual(P.sha(root/'packed_qk_hardfloat_source_20261017/RESTORATION.json'),e['hardfloat_restoration_sha256'])
 def test_real_source_reconstruction_and_command(self):
  root=os.environ.get('PACKED_OWNER_COMPILE_ORIGINALS')
  if not root:self.skipTest('external source/JAR originals not supplied')
  root=Path(root)
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)/'source';self.assertEqual(len(P.compose(dest,original_root=root/'public-recipe-cloud-be00-20261016/source',hardfloat_root=root/'packed_qk_hardfloat_source_20261017')),83)
   cmd=P.command('/usr/lib/jvm/java-21-openjdk-amd64/bin/java',root/'packed_compile_dependency_cache',dest,Path(d)/'classes')
   self.assertEqual(sum(x.endswith('.scala') for x in cmd),83);self.assertIn('scala.tools.nsc.Main',cmd);self.assertNotIn('ChiselStage',' '.join(cmd))
 def test_original_source_missing_rejects_before_output(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(FileNotFoundError):P.compose(Path(d)/'out',original_root=Path(d)/'missing',hardfloat_root=Path(d)/'hf')
   self.assertFalse((Path(d)/'out').exists())
