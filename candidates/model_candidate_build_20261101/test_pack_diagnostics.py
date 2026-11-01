"""Finite failure diagnostics only. No compiler, ELF or network."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('actual_pack_diagnostics',D/'pack_model_candidate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_original_pack_algorithm_ast_exact_after_stage_markers(self):
  tree=ast.parse((D/'pack_model_candidate.py').read_text());f=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='_pack_impl')
  f.name='pack';self.assertEqual(f.args.args[-1].arg,'_mark');f.args.args.pop()
  marks=[x for x in f.body if isinstance(x,ast.Expr)and isinstance(x.value,ast.Call)and isinstance(x.value.func,ast.Name)and x.value.func.id=='_mark']
  self.assertEqual([x.value.args[0].value for x in marks],['SOURCE_PINS','OBSERVATION','STAGE_RECEIPTS','COMPILE_OUTPUTS','ENRICH','COPY','FINAL'])
  f.body=[x for x in f.body if x not in marks]
  self.assertEqual(hashlib.sha256(ast.dump(f,include_attributes=False).encode()).hexdigest(),'c62ca11efa3c23acfb78c52da14d372c81ff75ccc61a4bd11528864bc23487a1')
 def test_identity_failure_has_no_raw_message_or_path(self):
  with self.assertRaises(m.ModelPackFailure)as cm:m.pack({'artifact_identity':{}},{},{},'/secret/input','/secret/overlay','/secret/out',lambda _:None,{})
  d=cm.exception.model_pack_diagnostic;self.assertEqual(d['phase'],'IDENTITY');self.assertEqual(d['reason'],'STAGE_VALIDATION_FAILED');self.assertNotIn('secret',json.dumps(d));self.assertEqual(set(d),{'schema','phase','reason','exception_class','index','bytes','expected_sha256','actual_sha256'})
 def test_source_hash_mismatch_diagnostic(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'secret-name';p.write_bytes(b'')
   with self.assertRaises(m.ModelPackFailure)as cm:m.check_pins({str(p):'f'*64})
   d=cm.exception.model_pack_diagnostic;self.assertEqual(d['index'],0);self.assertEqual(d['bytes'],0);self.assertEqual(d['reason'],'SOURCE_PIN_HASH_MISMATCH');self.assertEqual(d['actual_sha256'],hashlib.sha256(b'').hexdigest());self.assertNotIn('secret-name',json.dumps(d))
 def test_size_over_limit_is_not_reported_as_in_range(self):
  d=m.ModelPackFailure('SOURCE_PINS','SOURCE_PIN_SIZE',size=(4<<30)+1).model_pack_diagnostic;self.assertIsNone(d['bytes'])
if __name__=='__main__':unittest.main()
