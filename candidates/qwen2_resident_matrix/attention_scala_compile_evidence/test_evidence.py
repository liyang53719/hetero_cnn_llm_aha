import hashlib,json,os,tempfile,unittest
from pathlib import Path
from . import prepare as P
class EvidenceTests(unittest.TestCase):
 def test_exact_evidence_and_scope(self):
  P.check();e=P.evidence();self.assertEqual(len(e['source_sha256']),18)
  self.assertEqual(P.sha(P.HERE/'executed_launcher.txt'),e['executed_launch_sha256'])
  a=e['records']['failed_summary']['value'];b=e['records']['success_summary']['value']
  self.assertEqual(a['exit_code'],1);self.assertFalse(a['scala_compiled']);self.assertTrue(a['cleanup_complete'])
  self.assertEqual(b['status'],'PASS_SCALA_CLASS_COMPILE_ONLY');self.assertEqual(b['exit_code'],0);self.assertTrue(b['cleanup_complete'])
  self.assertEqual(b['source_sha256'],e['source_sha256']);self.assertEqual(len(b['classes']),129)
  self.assertEqual(e['records']['caller']['value']['observed_outer_exit_code'],0)
  for k in ('elaboration','rtl','numerical','hardware_performance'):self.assertFalse(e['claims'][k])
  for key in ('failed_summary','success_summary','caller'):
   record=e['records'][key];raw=(json.dumps(record['value'],indent=2,sort_keys=True)+'\n').encode()
   self.assertEqual(hashlib.sha256(raw).hexdigest(),record['sha256']);self.assertEqual(len(raw),record['bytes'])
 def test_exact_originals_when_supplied(self):
  root=os.environ.get('PACKED_COMPILE_ORIGINALS')
  if not root:self.skipTest('external original receipts not supplied')
  root=Path(root);e=P.evidence()
  names={'failed_summary':'packed_compile_plan_20261017/attempt/summary.json','failed_log':'packed_compile_plan_20261017/attempt/compiler.log','success_summary':'packed_compile_plan_seed_closure_20261017/attempt/summary.json','success_log':'packed_compile_plan_seed_closure_20261017/attempt/compiler.log','caller':'packed_compile_plan_seed_closure_20261017/attempt/CALLER.json'}
  for key,name in names.items():self.assertEqual(P.sha(root/name),e['records'][key]['sha256'])
  classes=root/'packed_compile_plan_seed_closure_20261017/attempt/classes'
  self.assertEqual({str(p.relative_to(classes)):P.sha(p) for p in classes.rglob('*') if p.is_file()},e['records']['success_summary']['value']['classes'])
 def test_actual_source_and_dependency_reconstruction(self):
  root=os.environ.get('PACKED_COMPILE_ORIGINALS')
  if not root:self.skipTest('external original sources/cache not supplied')
  root=Path(root)
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'scala';self.assertEqual(P.compose(out,original_root=root/'public-recipe-cloud-be00-20261016/source'),P.evidence()['source_sha256'])
   cp=P.dependencies(P.ROOT/'chisel/rope_hardware_oracle/maven-lock.json',root/'packed_compile_dependency_cache')
   cmd=P.command('/usr/lib/jvm/java-21-openjdk-amd64/bin/java',cp,root/'packed_compile_dependency_cache',out,Path(d)/'classes')
   self.assertEqual(sum(x.endswith('.scala') for x in cmd),18);self.assertIn('scala.tools.nsc.Main',cmd);self.assertNotIn('ChiselStage',' '.join(cmd))
 def test_missing_real_controller_rejected_before_composition(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(FileNotFoundError):P.compose(Path(d)/'out',original_root=Path(d)/'missing')
   self.assertFalse((Path(d)/'out').exists())
