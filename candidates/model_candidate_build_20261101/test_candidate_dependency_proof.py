"""Source-only grammar/contract tests. No new artifact or actual compiler PASS."""
import ast,hashlib,importlib.util,json,pathlib,unittest
from unittest import mock
D=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('tested_candidate_proof',D/'candidate_dependency_proof.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_original_grammar_ast_exact(self):
  tree=ast.parse((D/'candidate_dependency_proof.py').read_text());pins=json.loads((D/'ORIGINAL_GRAMMAR_AST_PINS.json').read_text())
  for name,want in pins.items():
   n=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name)
   self.assertEqual(hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest(),want,name)
 def policy(self,schema='ACTUAL_FRESH_DRIVER_DEPENDENCY_V2',status='UNREVIEWED_MODEL_BUILD'):
  r={'schema':schema,'cpp_build_policy':m.CPP_O1_POLICY,'cpp_build_overrides':m.CPP_O1_OVERRIDES};return r,dict(r),dict(r,schema='MODEL_CANDIDATE_BUILD_RECEIPT_V1',status=status)
 def test_unfrozen_contract_refuses(self):
  with mock.patch.object(m,'CANDIDATE_IMPLEMENTATION_PINS',{}):
   with self.assertRaises(ValueError):m.compilation_policy(*self.policy())
 def test_explicit_candidate_policy(self):
  pins={k:'d'*64 for k in m.CANDIDATE_REQUIRED_IMPLEMENTATIONS};pins[m.COLLECTOR_PATH]=m.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA
  with mock.patch.object(m,'CANDIDATE_IMPLEMENTATION_PINS',pins):
   p,o,i=m.compilation_policy(*self.policy());self.assertEqual(p,m.CPP_O1_POLICY);self.assertEqual(set(i),m.CANDIDATE_REQUIRED_IMPLEMENTATIONS)
 def test_no_historical_or_accepted_fallback(self):
  pins={k:'d'*64 for k in m.CANDIDATE_REQUIRED_IMPLEMENTATIONS};pins[m.COLLECTOR_PATH]=m.O1_PRODUCER_DEPENDENCY_CAPTURE_SHA
  with mock.patch.object(m,'CANDIDATE_IMPLEMENTATION_PINS',pins):
   for args in [self.policy(schema='ACTUAL_FRESH_DRIVER_DEPENDENCY_V1'),self.policy(status='ACCEPTED')]:
    with self.assertRaises(ValueError):m.compilation_policy(*args)
 def test_collector_identity_cannot_change(self):
  with mock.patch.object(m,'CANDIDATE_IMPLEMENTATION_PINS',{k:'d'*64 for k in m.CANDIDATE_REQUIRED_IMPLEMENTATIONS}):
   with self.assertRaises(ValueError):m.compilation_policy(*self.policy())
 def test_header_ports_exact_storage(self):
  self.assertEqual(m.header_ports('VL_IN8(&clock,0,0);\nVL_OUTW(&data,511,0,16);'),{'clock':['input',1],'data':['output',512]})
  for t in ['VL_IN8(&clock,0,0);VL_IN8(&clock,0,0);','VL_OUTW(&data,511,0,15);','VL_IN8(&clock,1,1);','VL_IN16(&wrong,7,0);','VL_INBAD(&clock,0,0);']:
   with self.assertRaises(ValueError):m.header_ports(t)
 def test_compile_recipe_whitespace_not_shell(self):
  text='driver.o: /repo/driver.cpp\n\t$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST)  -c -o $@ $<\n';m.verify_driver_compile_recipe(text,'driver','/repo/driver.cpp')
  for t in [text.replace('$<','$<; true'),text+'\tbad\n',text.replace('$(OPT_FAST)','-Ofast')]:
   with self.assertRaises(ValueError):m.verify_driver_compile_recipe(t,'driver','/repo/driver.cpp')
if __name__=='__main__':unittest.main()
