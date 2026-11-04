"""Pure validator/source checks. No network, native process, compile or workflow."""
import unittest,copy,json,hashlib,ast
from pathlib import Path
import validate_launch as v
O=Path(__file__).resolve().parent;S=(O/'compile_only.py').read_text();W=(O/'compile_only_workflow.yml').read_text()
class Tests(unittest.TestCase):
 def good(self):
  source='a'*40;head='b'*40;wh='c'*64
  event=dict(ref='refs/heads/main',before=source,after=head)
  m=dict(schema=v.SCHEMA,source_sha=source,nonce=v.NONCE,generation_sha256=v.GENERATION,workflow_sha256=wh)
  return [event,m,'1',head,source,'A\t'+v.LAUNCH+'\n',wh]
 def test_exact_two_commit(self):self.assertEqual(v.validate(*self.good()),'a'*40)
 def test_source_only_cannot_activate(self):
  a=self.good();a[5]='A\t'+v.WORKFLOW+'\n'
  with self.assertRaises(ValueError):v.validate(*a)
 def test_reject_replay(self):
  for attempt in ('0','2','3'):
   a=self.good();a[2]=attempt
   with self.assertRaises(ValueError):v.validate(*a)
 def test_reject_nonce(self):
  a=self.good();a[1]['nonce']='different'
  with self.assertRaises(ValueError):v.validate(*a)
 def test_retry1_rejects_historical_once_nonce(self):
  a=self.good();a[1]['nonce']='gdn32_compile_only_20261104_once'
  with self.assertRaises(ValueError):v.validate(*a)
 def test_retry1_rejects_historical_once_path(self):
  a=self.good();a[5]='A\tci_launch/gdn32_compile_only_20261104_once.json\n'
  with self.assertRaises(ValueError):v.validate(*a)
 def test_workflow_only_new_nonce_path(self):
  self.assertIn('paths: [ci_launch/gdn32_compile_only_20261104_retry1.json]',W);self.assertNotIn('paths: [ci_launch/gdn32_compile_only_20261104_once.json]',W);self.assertIn("identity['nonce']=='gdn32_compile_only_20261104_retry1'",S)
 def test_reject_extra_change(self):
  a=self.good();a[5]+='M\t'+v.WORKFLOW+'\n'
  with self.assertRaises(ValueError):v.validate(*a)
 def test_reject_modified_launch(self):
  a=self.good();a[5]='M\t'+v.LAUNCH+'\n'
  with self.assertRaises(ValueError):v.validate(*a)
 def test_reject_wrong_parent(self):
  a=self.good();a[4]='d'*40
  with self.assertRaises(ValueError):v.validate(*a)
 def test_reject_unrelated_push(self):
  for key,value in [('ref','refs/heads/dev'),('before','d'*40),('after','e'*40)]:
   a=self.good();a[0][key]=value
   with self.assertRaises(ValueError):v.validate(*a)
 def test_reject_identity_hashes(self):
  for key in ('generation_sha256','workflow_sha256'):
   a=self.good();a[1][key]='e'*64
   with self.assertRaises(ValueError):v.validate(*a)
 def test_reject_manifest_extras(self):
  a=self.good();a[1]['numeric_execution_authorized']=True
  with self.assertRaises(ValueError):v.validate(*a)
 def test_python_parse(self):ast.parse(S);ast.parse((O/'validate_launch.py').read_text())
 def test_no_manual_unknown_jdk_pin(self):
  self.assertNotIn('java-sha256',S);self.assertNotIn('workflow_dispatch',W);self.assertIn('JAVA_HOME_21_X64',W);self.assertIn('inventory_runner_jdk.py',S);self.assertIn('fresh-host-contract',S)
 def test_fresh162_no_old_classes(self):
  self.assertIn("len(sources)==162 and sources.count(selection['helper'])==1",S);self.assertIn("all(x.endswith('.jar')",S)
 def test_no_upload_or_side_effect_step(self):
  active='\n'.join(x for x in W.splitlines()if not x.lstrip().startswith('#'))
  for word in ('upload-artifact','download-artifact','actions/cache','git push','ChiselStage'):self.assertNotIn(word,active)
 def test_dormant_exact_push_only(self):
  self.assertIn('paths: ['+v.LAUNCH+']',W);self.assertIn('fetch-depth: 2',W);self.assertIn('steps.launch.outputs.source_sha',W);self.assertIn('cancel-in-progress: false',W)
 def test_tool_pins(self):
  d=json.loads((O/'TOOL_PINS.json').read_text())
  for n,h in d['local'].items():self.assertEqual(hashlib.sha256((O/n).read_bytes()).hexdigest(),h)
 def test_provenance_not_old_pass(self):self.assertIn("inventory['old_pass_transfer'] is False",S);self.assertIn('NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION',S)
 def test_no_private_scratch_paths(self):
  for p in (O/'compile_only.py',O/'validate_launch.py',O/'compile_only_workflow.yml',O/'TOOL_PINS.json'):
   self.assertNotIn('/workspace/scratch',p.read_text())

class ReviewFixTests(unittest.TestCase):
 def test_actual_host_inventory_and_admitted_pins(self):
  for needle in ("host_script=HERE/'fresh_compile_host.py'","host_receipt=supervise_multiroot.execute(","commonpins.update(host['pins'])","host_aliases=host['aliases']","finally:check_host_aliases()","caps['jdk_aliases']=list(segments.values())"):
   self.assertIn(needle,S)
 def test_stream_hash_no_whole_jdk_read(self):
  self.assertIn("hashlib.file_digest(f,'sha256')",S);self.assertNotIn('read_bytes()',S)
 def test_derivative_pin_and_no_verilator_requirement(self):
  d=json.loads((O/'FRESH_HOST_BASE.json').read_text());self.assertEqual(hashlib.sha256((O/'fresh_compile_host.py').read_bytes()).hexdigest(),d['candidate_sha256'])
  h=(O/'fresh_compile_host.py').read_text();self.assertIn('def inventory(contract,java_home,verilator_root=None)',h);self.assertIn('targets=tools+',h);self.assertIn("if vr is not None else []",h)
  for guard in ('resolve_dependency','loaded_python_zero_needed_class','reject_injection(os.environ)',"sys.version_info[:2]==(3,12)",'jdk_query_context','dependency_paths(output)'):self.assertIn(guard,h)
 def test_safe_error_locations_no_raw_message(self):
  import tempfile,gzip,safe_compile_summary as d
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'log.gz';known='/trusted/candidates/Test.scala';body=(known+':12: error: type mismatch; password=verysecret\n'+ '  injected source line\n ^\n/private/no.scala:4: error: not found: leak\n'+known+':18:2: error: not found: value hidden\n').encode()
   with gzip.open(p,'wb')as f:f.write(body)
   x=d.summarize_stage('SCALA_COMPILE',dict(native_exit=1,errors=['ValueError: wall cap']),p,{known:'candidates/Test.scala'});encoded=json.dumps(x)
   self.assertEqual([r['kind']for r in x['compiler_errors']],['TYPE_MISMATCH','SYMBOL_NOT_FOUND']);self.assertEqual(x['compiler_errors'][0]['line'],12)
   for secret in ('verysecret','injected','/private','/trusted','password','hidden'):self.assertNotIn(secret,encoded)
   self.assertEqual(x['supervisor_codes'],['WALL_CAP'])
 def test_diagnostic_caps(self):
  import tempfile,gzip,safe_compile_summary as d
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'log.gz';known='/trusted/Test.scala'
   with gzip.open(p,'wb')as f:f.write(''.join(known+':'+str(i)+': error: type mismatch;\n'for i in range(1,30)).encode())
   x=d.scan(p,{known:'candidates/Test.scala'});self.assertEqual(len(x['compiler_errors']),8)
 def test_unknown_path_cannot_enter_summary(self):
  import safe_compile_summary as d
  self.assertFalse(d.safe_sources({'/absolute/T.scala':'../../T.scala'}));self.assertFalse(d.safe_sources({'relative/T.scala':'T.scala'}))

if __name__=='__main__':unittest.main(verbosity=2)
