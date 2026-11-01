"""Light file-only diagnostics; no census, job, supervisor or DUT execution."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('disk_flow',D/'controller/cloud_flow.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
EXPECTED_BASE_AST='6007e2b7aa04308f9b4c51287ce7ce027da9f53348c4ac0a83f97b10e71c96e2'
class Tests(unittest.TestCase):
 def snap(self,free):return dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1',complete=True,bytes=4<<30,free_bytes=free,roots=['SECRET_PAYLOAD_PATH'],error='SECRET_ERROR')
 def test_insufficient_prelaunch_saved_before_original_rejection(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);receipt=root/'BINDING.json.UPFRONT_DISK.json';required=f.TREE-(4<<30)+(8<<30)
   with self.assertRaisesRegex(ValueError,'remaining aggregate growth plus unchanged free8GiB'):f.upfront_disk_admission(self.snap(required-3109000000),receipt,'a'*64)
   r=json.loads(receipt.read_text());self.assertEqual(r['shortfall_bytes'],3109000000);self.assertEqual(r['required_free_bytes'],required);self.assertFalse(r['job_created']);self.assertEqual(list(root.iterdir()),[receipt]);self.assertNotIn('SECRET',receipt.read_text());self.assertLess(receipt.stat().st_size,2048)
 def test_success_return_unchanged_and_exclusive_receipt(self):
  with tempfile.TemporaryDirectory()as t:
   receipt=pathlib.Path(t)/'disk.json';snapshot=self.snap(20<<30);original=f.upfront_disk_admission(snapshot);self.assertEqual(f.upfront_disk_admission(snapshot,receipt,'b'*64),original)
   self.assertEqual(json.loads(receipt.read_text())['shortfall_bytes'],0)
   with self.assertRaises(FileExistsError):f.upfront_disk_admission(snapshot,receipt,'b'*64)
 def test_invalid_snapshot_original_gate_before_receipt(self):
  for edit in ({'complete':False},{'bytes':True},{'bytes':f.TREE+1},{'free_bytes':-1}):
   with self.subTest(edit=edit),tempfile.TemporaryDirectory()as t:
    receipt=pathlib.Path(t)/'disk.json'
    with self.assertRaises(ValueError):f.upfront_disk_admission(dict(self.snap(20<<30),**edit),receipt,'c'*64)
    self.assertFalse(receipt.exists())
 def test_local_receipt_is_bounded_and_does_not_change_gate(self):
  with tempfile.TemporaryDirectory()as t:
   receipt=pathlib.Path(t)/'disk.json';snap=self.snap(2**10000)
   self.assertEqual(f.upfront_disk_admission(snap,receipt,'secret'),f.upfront_disk_admission(snap));r=json.loads(receipt.read_text());self.assertIsNone(r['observed_free_bytes']);self.assertIsNone(r['binding_sha256']);self.assertLess(receipt.stat().st_size,2048)
 def test_actual_call_is_binding_sibling_before_job_creation(self):
  text=(D/'controller/cloud_flow.py').read_text();self.assertIn("P(binding_path).with_name(P(binding_path).name+'.UPFRONT_DISK.json'),binding_sha",text);self.assertLess(text.index(' disk_admission=upfront_disk_admission('),text.index(' job.mkdir()'))
 def test_only_diagnostic_delta_ast(self):
  tree=ast.parse((D/'controller/cloud_flow.py').read_text())
  definitions=[n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='upfront_disk_admission']
  calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='upfront_disk_admission']
  conditions=[n for n in ast.walk(tree)if isinstance(n,ast.If)and ast.unparse(n.test)=='evidence_path is not None']
  self.assertEqual(len(definitions),1);self.assertEqual(len(calls),1);self.assertEqual(len(conditions),1)
  function=definitions[0];call=calls[0];diagnostic=conditions[0]
  self.assertIn(diagnostic,function.body)
  self.assertEqual(ast.unparse(function.args),'snapshot, evidence_path=None, binding_sha=None')
  self.assertEqual(ast.unparse(call),"upfront_disk_admission(snapshot, P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), binding_sha)")
  self.assertEqual(hashlib.sha256(ast.dump(diagnostic,include_attributes=False).encode()).hexdigest(),'c3bb48f0d043a3b02d43bfb69ab5a0a77a81b9938434cde2e836b573d72ba9ad')
  function.args.args=function.args.args[:1];function.args.defaults=[];function.body.remove(diagnostic);call.args=call.args[:1]
  self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),EXPECTED_BASE_AST)
if __name__=='__main__':unittest.main()
