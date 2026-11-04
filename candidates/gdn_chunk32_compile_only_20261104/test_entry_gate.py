"""Real main entry replay; git identity mocked, supervisor intercepted before native.
Use a source046a byte-verified repository fixture, never the old compatibility base.
"""
import contextlib,importlib.util,json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest import mock
O=Path(__file__).resolve().parent
sys.path.insert(0,str(O));import compile_only as c
sys.path.insert(0,str(O/'supervisor'));import supervise_multiroot
B=Path(os.environ['GDN32_ACTUAL_REPO']).resolve()
ORIGINAL=Path(os.environ.get('GDN32_ORIGINAL_REPO',str(B))).resolve()
SOURCE='046a1096ab7deb60bea6d8c2b274c0cf3326bafb'
class BeforeNative(Exception):pass
class Tests(unittest.TestCase):
 def call_main(self,mod,identity_change=None,env_change=None,repo=None):
  base=B if repo is None else repo
  identity=dict(schema='GDN32_COMPILE_JOB_IDENTITY_V1',run_id=41778903739,source_commit=SOURCE,launch_commit='ee7f7b9a93fea191593a8baf519662a44513cd36',generation_sha256='2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52',workflow_sha256=c.sha(base/'.github/workflows/gdn32-compile-only.yml'),nonce='gdn32_compile_only_20261104_retry2')
  if identity_change:identity.update(identity_change)
  env=dict(GITHUB_RUN_ID='41778903739',GITHUB_SHA='ee7f7b9a93fea191593a8baf519662a44513cd36',GITHUB_RUN_ATTEMPT='1')
  if env_change:env.update(env_change)
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);f=root/'identity.json';f.write_text(json.dumps(identity))
   args=['compile_only.py','--repo',str(base),'--candidate',str(base/'candidates/gdn_chunk32_actual_v2_20261104'),'--output',str(root/'out'),'--java','/usr/bin/java','--identity',str(f)]
   with mock.patch.dict(os.environ,env,clear=True),mock.patch.object(sys,'argv',args),mock.patch.object(mod.subprocess,'check_output',return_value=SOURCE+'\n'),mock.patch.object(supervise_multiroot,'execute',side_effect=BeforeNative)as native:
    try:mod.main()
    except Exception as e:return e,native.call_count
  self.fail('must stop before native')
 def test_original_published_main_actual_failure(self):
  spec=importlib.util.spec_from_file_location('original046a_compile_entry',ORIGINAL/'candidates/gdn_chunk32_compile_only_20261104/compile_only.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
  e,count=self.call_main(old,dict(nonce='gdn32_compile_only_20261104_retry1'),repo=ORIGINAL);self.assertEqual(count,0);self.assertIsInstance(e,ValueError);self.assertEqual(str(e),'repository tool source drift')
 def test_actual_remote_tool_bytes(self):
  fixture=json.loads((O/'ACTUAL046A_TOOL_DRIFT.json').read_text())
  for row in fixture['mismatches']:self.assertEqual(c.sha(B/row['path']),row['actual_sha256'])
 def test_original_failed_gate_exact_real_tools(self):
  # Original first repo pin conflict, not a fabricated arbitrary wrong hash.
  row=json.loads((O/'ACTUAL046A_TOOL_DRIFT.json').read_text())['mismatches'][0]
  with self.assertRaises(c.GateFailure)as cm:c.check_tool_pin(B/row['path'],row['old_sha256'],'REPOSITORY_TOOL',row['path'])
  result=c.failure_summary(cm.exception);self.assertEqual(result['reason'],'TOOL_PIN_DRIFT');self.assertEqual(result['pin_failure']['actual_sha256'],row['actual_sha256'])
 def test_real_main_corrected_reaches_first_supervisor(self):
  e,count=self.call_main(c);self.assertIsInstance(e,BeforeNative);self.assertEqual(count,1);self.assertEqual(c.PHASE,'JDK_INVENTORY')
 def test_real_main_wrong_nonce_fails_before_native(self):
  e,count=self.call_main(c,dict(nonce='gdn32_compile_only_20261104_once'));self.assertEqual(count,0);self.assertEqual(c.failure_summary(e)['phase'],'IDENTITY');self.assertEqual(c.failure_summary(e)['reason'],'EXACT_LAUNCH_IDENTITY')
 def test_real_main_attempt2_fails_before_native(self):
  e,count=self.call_main(c,env_change=dict(GITHUB_RUN_ATTEMPT='2'));self.assertEqual(count,0);self.assertEqual(c.failure_summary(e)['reason'],'ACTUAL_FIRST_OWNING_JOB')
 def test_real_main_original_pins_regression(self):
  # Apply only original two reviewed expected digests; every other pin stays.
  original=c.check_tool_pin;rows={r['path']:r['old_sha256']for r in json.loads((O/'ACTUAL046A_TOOL_DRIFT.json').read_text())['mismatches']}
  def stale(path,expected,role,label):return original(path,rows.get(label,expected),role,label)
  with mock.patch.object(c,'check_tool_pin',side_effect=stale):e,count=self.call_main(c)
  r=c.failure_summary(e);self.assertEqual(count,0);self.assertEqual(r['phase'],'TOOL_PINS');self.assertEqual(r['reason'],'TOOL_PIN_DRIFT');self.assertEqual(r['pin_failure']['label'],next(iter(rows)))
 def test_fetch_python_entry_verify_only(self):
  # Same wrapper and repo/candidate args as fetch stage; only verify-only flag
  # differs to prohibit dependency download/native compiler in this pure test.
  r=subprocess.run([sys.executable,'-B',str(O/'restore_compile_inputs.py'),'--repo',str(B),'--candidate',str(B/'candidates/gdn_chunk32_actual_v2_20261104'),'--verify-only'],capture_output=True,text=True,timeout=30,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'})
  self.assertEqual(r.returncode,0);self.assertLess(len(r.stdout),4096);d=json.loads(r.stdout);self.assertEqual(d['status'],'SOURCE162_AND_MODEL159_JAR_INVENTORY_VERIFIED_ONLY');self.assertEqual(d['source_count'],162);self.assertEqual(d['verified_jar_count'],0);self.assertFalse(d['compiler_executed'])
 def test_exception_text_not_exposed(self):
  s=json.dumps(c.failure_summary(ValueError('SECRET /private/path\x1b[31m')));self.assertNotIn('SECRET',s);self.assertNotIn('/private',s);self.assertIn('UNCLASSIFIED_EXCEPTION',s)
 def test_unsafe_label_rejected(self):
  with self.assertRaises(c.GateFailure):c.check_tool_pin(B/'notread','0'*64,'REPOSITORY_TOOL','../private')
if __name__=='__main__':unittest.main(verbosity=2)
