"""Finite diagnostic projection only; no subprocess/compiler/ELF execution."""
import ast,hashlib,json,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def setUp(self):
  self.tree=ast.parse((D/'one_job_model_candidate.py').read_text());nodes=[n for n in self.tree.body if isinstance(n,ast.FunctionDef)and n.name in ('need','post_build_failure_diagnostic')]
  self.ns={'json':json};exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'projection','exec'),self.ns);self.project=self.ns['post_build_failure_diagnostic']
 def error(self,**change):
  e=ValueError('/secret/path token=do-not-export');e.model_pack_diagnostic=dict(schema='MODEL_PACK_FAILURE_V1',phase='SOURCE_PINS',reason='SOURCE_PIN_HASH_MISMATCH',exception_class='ValueError',index=2,bytes=0,expected_sha256='0'*64,actual_sha256='1'*64);e.model_pack_diagnostic.update(change);return e
 def test_exact_finite_reason(self):
  d=self.project('pack',self.error());self.assertEqual(d['bytes'],0);self.assertEqual(d['reason'],'SOURCE_PIN_HASH_MISMATCH');self.assertFalse(d['numerical_pass']);self.assertLess(len(json.dumps(d)),2048)
 def test_no_raw_exception_or_paths(self):
  text=json.dumps(self.project('pack',self.error()));self.assertNotIn('secret',text);self.assertNotIn('token',text);self.assertNotIn('/path',text)
 def test_extra_key_invalidates_untrusted_payload(self):
  d=self.project('pack',self.error(path='/hidden'));self.assertEqual(d['reason'],'UNCLASSIFIED');self.assertIsNone(d['index'])
 def test_bad_field_types_do_not_mask_original(self):
  for v in ([],{},True,3.5,None):
   d=self.project(v,self.error(phase=v,reason=v,index=v,bytes=v,expected_sha256=v));self.assertEqual(d['pack_phase'],'UNKNOWN');self.assertIsNone(d['expected_sha256'])
 def test_bounds_do_not_turn_overflow_into_valid_value(self):
  d=self.project('pack',self.error(index=1000001,bytes=(4<<30)+1));self.assertIsNone(d['index']);self.assertIsNone(d['bytes']);self.assertEqual(d['reason'],'SOURCE_PIN_HASH_MISMATCH')
 def test_unknown_exception_not_disclosed(self):
  class SecretCustomException(Exception):pass
  d=self.project('pack',SecretCustomException('secret'));self.assertEqual(d['exception_class'],'OTHER');self.assertEqual(d['reason'],'UNCLASSIFIED')
 def test_unknown_payload_exception_class_uses_actual(self):
  d=self.project('pack',self.error(exception_class='Secret'));self.assertEqual(d['exception_class'],'ValueError')
 def test_structured_wrapped_error_preserves_finite_underlying_class(self):
  class ModelPackFailure(ValueError):pass
  e=ModelPackFailure('not exported');e.model_pack_diagnostic=self.error().model_pack_diagnostic
  self.assertEqual(self.project('pack',e)['exception_class'],'ValueError')
 def test_only_one_projection_print_and_original_raise_remains(self):
  prints=[n for n in ast.walk(self.tree)if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='print'and 'MODEL_POST_BUILD_DIAGNOSTIC' in ast.unparse(n)]
  self.assertEqual(len(prints),1)
  class Strip(ast.NodeTransformer):
   def visit_FunctionDef(self,n):return None if n.name=='post_build_failure_diagnostic'else self.generic_visit(n)
   def visit_Expr(self,n):return None if n in prints else self.generic_visit(n)
  tree=Strip().visit(self.tree);self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),'7709b2e5dd4cf7f3c777d96d5d6f73c68e4f563f6fea7307628cee6575bc0496')
if __name__=='__main__':unittest.main()
