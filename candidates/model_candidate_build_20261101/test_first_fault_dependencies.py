"""Independent parser/capture contract tests. No compiler/EDA invocation.
Use DEPENDENCY_TEST_SOURCE for an explicit checkout; default is the containing repository.
Actual GCC evidence is separately pinned.
"""
import ast,contextlib,copy,hashlib,importlib.util,io,json,os,pathlib,sys,unittest
from unittest import mock
P=pathlib.Path
SOURCE=P(os.environ.get('DEPENDENCY_TEST_SOURCE',str(P(__file__).resolve().parent.parents[1]))).resolve()
C=SOURCE/'candidates/model_candidate_build_20261101'
PP=SOURCE/'candidates/ci_frontend_pipeline_r2_20261029'
sys.path[:0]=[str(C),str(PP)]
import first_fault_compilation as new
import candidate_dependency_proof as proof
import first_fault_policy as policy

def tree(name):return ast.parse((C/name).read_text())
def function(name,fn):return next(n for n in tree(name).body if isinstance(n,ast.FunctionDef) and n.name==fn)
def dump(n):return ast.dump(n,include_attributes=False)
CAPTURE_AST_SHA={
 'first_fault_compilation.py':'c04185f23ea0a28bdefa7afa8e44f8362a609948589a945e5c85d494816152f3',
 'candidate_dependency_proof.py':'f4ee88b953604b1ee6122cca600efabcbdd5a9525ad81bd90c425ec62a8ce1eb',
}
def capture_exact(name,module):
 functions=[n for n in module.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='capture']
 if len(functions)!=1 or hashlib.sha256(dump(functions[0]).encode()).hexdigest()!=CAPTURE_AST_SHA[name]:
  raise ValueError('exact reviewed complete unique capture AST')
 return functions[0]
class Tests(unittest.TestCase):
 def parse(self,text):return new.parse_dependencies(text,'/obj','/src/driver.cpp')
 def reject(self,text,reason):
  out=io.StringIO()
  with contextlib.redirect_stdout(out),self.assertRaises(ValueError):self.parse(text)
  prefix='FIRST_FAULT_DEPENDENCY_DIAGNOSTIC '
  self.assertTrue(out.getvalue().startswith(prefix));self.assertLessEqual(len(out.getvalue().encode()),2048)
  d=json.loads(out.getvalue()[len(prefix):]);self.assertEqual(set(d),{'schema','reason','raw_count','unique_token_count','repeated_token_count'})
  self.assertEqual(d['reason'],reason);self.assertNotIn('/src',out.getvalue());self.assertNotIn('SECRET',out.getvalue())
 def test_exact_repeat_first_order_and_raw_unchanged(self):
  text='driver.o: /src/driver.cpp /inc/sparse_write_memory.hpp /inc/h.h /inc/h.h\n';before=text.encode()
  self.assertEqual(self.parse(text),['/src/driver.cpp','/inc/sparse_write_memory.hpp','/inc/h.h']);self.assertEqual(text.encode(),before)
  with self.assertRaisesRegex(ValueError,'unique bounded dependencies'):proof.parse_dependencies(text,'/obj','/src/driver.cpp')
 def test_actual_gcc_duplicate_preserved_to_sparse_gate(self):
  # Exact existing native0 GCC output, no edited text presented as compiler output.
  # Verbatim native0 tiny GCC .d; retained text is evidence, not new compilation.
  raw=b'driver.o: \\\n /workspace/scratch/f28987e955ed/gcc_dep_duplicate_fixture_20261102T1305/real_verilated_then_dpi/driver.cpp \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilated.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilatedos.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilated_config.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilated_types.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilated_funcs.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilated_dpi.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilated.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/verilated_sym_props.h \\\n /workspace/scratch/f28987e955ed/verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr/share/verilator/include/vltstd/svdpi.h\n'
  p=P('/workspace/scratch/f28987e955ed/gcc_dep_duplicate_fixture_20261102T1305/real_verilated_then_dpi/case.d')
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'77e4639b0e39baaf6718b93dd1d103d1f636c660f6ce91ba05fdcc81f8578f7e')
  text=raw.decode();driver=next(x for x in text.replace('\\\n',' ').split() if x.endswith('/driver.cpp'))
  with self.assertRaisesRegex(ValueError,'unique bounded dependencies'):proof.parse_dependencies(text,str(p.parent),driver)
  out=io.StringIO()
  with contextlib.redirect_stdout(out),self.assertRaisesRegex(ValueError,'SPARSE_DEPENDENCY'):new.parse_dependencies(text,str(p.parent),driver)
  d=json.loads(out.getvalue().split(' ',1)[1]);self.assertEqual(d['raw_count'],10);self.assertEqual(d['repeated_token_count'],1)
  # Explicit synthetic extension adds required product sparse header, not a new actual GCC sample.
  extended=text.rstrip()+' /inc/sparse_write_memory.hpp\n'
  self.assertEqual(len(new.parse_dependencies(extended,str(p.parent),driver)),10)
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'77e4639b0e39baaf6718b93dd1d103d1f636c660f6ce91ba05fdcc81f8578f7e')
 def test_continuation(self):self.assertEqual(len(self.parse('driver.o: /src/driver.cpp \\\n /inc/sparse_write_memory.hpp\n')),2)
 def test_text_forms(self):
  for t in ['',None,'driver.o: /SECRET\r\n','driver.o: $(SECRET)\n','driver.o: /SECRET;\n','driver.o: /SECRET#\n','driver.o: /SECRET\x00\n','driver.o: /é\n','driver.o: /SECRET']:
   with self.subTest(t=t):self.reject(t,'TEXT_FORMAT')
 def test_over_megabyte(self):self.reject('driver.o: '+'a'*(1024**2)+'\n','TEXT_FORMAT')
 def test_backslash(self):self.reject('driver.o: /SECRET\\foo\n','CONTINUATION')
 def test_rule_forms(self):
  for t in ['driver.o: a\nother.o: b\n','driver.o: a:b\n']:
   with self.subTest(t=t):self.reject(t,'ONE_RULE')
 def test_target(self):self.reject('other.o: /src/driver.cpp /inc/sparse_write_memory.hpp\n','OBJECT_TARGET')
 def test_empty(self):self.reject('driver.o:\n','EMPTY')
 def test_parent(self):self.reject('driver.o: /src/driver.cpp /SECRET/../sparse_write_memory.hpp\n','PARENT_TRAVERSAL')
 def test_normalized_alias(self):self.reject('driver.o: /src/driver.cpp /inc/sparse_write_memory.hpp /inc/h.h /inc/./h.h\n','NORMALIZED_COLLISION')
 def test_missing_driver(self):self.reject('driver.o: /inc/sparse_write_memory.hpp\n','DRIVER_DEPENDENCY')
 def test_sparse(self):
  for text in ['driver.o: /src/driver.cpp\n','driver.o: /src/driver.cpp /a/sparse_write_memory.hpp /b/sparse_write_memory.hpp\n']:
   self.reject(text,'SPARSE_DEPENDENCY')
 def test_raw4097_not_dedup_limit(self):self.reject('driver.o: /src/driver.cpp /inc/sparse_write_memory.hpp '+' '.join(['/inc/h.h']*4095)+'\n','TOKEN_LIMIT')
 def test_raw4096_allowed(self):self.assertEqual(len(self.parse('driver.o: /src/driver.cpp /inc/sparse_write_memory.hpp '+' '.join(['/inc/h.h']*4094)+'\n')),3)
 def test_capture_complete_ast_fixed(self):
  for name in CAPTURE_AST_SHA:
   with self.subTest(name=name):capture_exact(name,tree(name))
 def test_capture_duplicate_function_reject(self):
  for name in CAPTURE_AST_SHA:
   module=tree(name);module.body.append(copy.deepcopy(capture_exact(name,module)))
   with self.subTest(name=name),self.assertRaises(ValueError):capture_exact(name,module)
 def test_capture_duplicate_statement_reject(self):
  for name in CAPTURE_AST_SHA:
   module=tree(name);f=capture_exact(name,module);f.body.insert(-1,copy.deepcopy(f.body[-2]))
   with self.subTest(name=name),self.assertRaises(ValueError):capture_exact(name,module)
 def test_capture_mutated_gate_reject(self):
  for name in CAPTURE_AST_SHA:
   module=tree(name);f=capture_exact(name,module)
   call=next(n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='need')
   call.args[0]=ast.Constant(value=True)
   with self.subTest(name=name),self.assertRaises(ValueError):capture_exact(name,module)
 def test_capture_legacy_binding_rejected_before_files(self):
  with self.assertRaisesRegex(ValueError,'explicit readonly dependency collector'):new.capture({},None,None,[])
 def test_producer_exact_selector(self):
  f=function('candidate_build_producer.py','run')
  nodes=[n for n in ast.walk(f) if isinstance(n,ast.If) and 'first_fault_driver_contract' in ast.unparse(n.test)]
  self.assertEqual(len(nodes),1);n=nodes[0]
  self.assertEqual(ast.unparse(n.test),"'first_fault_driver_contract' in b")
  self.assertEqual(ast.unparse(n.body[0]),'from first_fault_compilation import capture')
  self.assertEqual(ast.unparse(n.orelse[0]),'from driver_dependency_proof import capture')
 def test_unknown_policy_old_manifest_rejected(self):
  r={'schema':'ACTUAL_FRESH_DRIVER_DEPENDENCY_V2','cpp_build_policy':proof.CPP_O1_POLICY,'cpp_build_overrides':proof.CPP_O1_OVERRIDES,'dependency_rule_policy':'UNKNOWN'}
  receipt=dict(r,schema='MODEL_CANDIDATE_BUILD_RECEIPT_V1',status='UNREVIEWED_MODEL_BUILD')
  with self.assertRaisesRegex(ValueError,'legacy dependency rule unchanged'):proof.compilation_policy(r,r,receipt)
 def test_old_policy_map_preserved(self):
  r={'schema':'ACTUAL_FRESH_DRIVER_DEPENDENCY_V2','cpp_build_policy':proof.CPP_O1_POLICY,'cpp_build_overrides':proof.CPP_O1_OVERRIDES}
  receipt=dict(r,schema='MODEL_CANDIDATE_BUILD_RECEIPT_V1',status='UNREVIEWED_MODEL_BUILD')
  self.assertEqual(proof.compilation_policy(r,r,receipt)[2],proof.OLD_CANDIDATE_IMPLEMENTATION_PINS)
 def test_new_policy_real_artifact_contract(self):
  raw=(C/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes();contract=policy.decode_contract(raw);cp='/repo/'+policy.CONTRACT_REPO_PATH
  row={'path':cp,'bytes':len(raw),'sha256':policy.CONTRACT_SHA,'text':raw.decode()}
  r={'schema':'ACTUAL_FRESH_DRIVER_DEPENDENCY_V2','cpp_build_policy':proof.CPP_O1_POLICY,'cpp_build_overrides':proof.CPP_O1_OVERRIDES,'dependency_rule_policy':new.DEPENDENCY_RULE_POLICY}
  m=dict(r,sv_sha256=policy.ORIGINAL_SV_SHA,driver_sha256=contract['diagnostic_driver']['sha256'],generation_input_pins={cp:policy.CONTRACT_SHA},readonly_probe={'schema':'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1','status':'OBSERVED_UNREVIEWED','contract':row,'accessor_generation':{}})
  manifest={'schema':policy.FIRST_FAULT_MANIFEST_SCHEMA,'scope':policy.FIRST_FAULT_SCOPE,'readonly_probe_contract':{'bytes':len(raw),'sha256':policy.CONTRACT_SHA},'common':{'sv':{'sha256':policy.ORIGINAL_SV_SHA},'driver':{'sha256':m['driver_sha256']}}}
  rec=dict(r,schema='MODEL_CANDIDATE_BUILD_RECEIPT_V1',status='UNREVIEWED_MODEL_BUILD')
  self.assertEqual(proof.compilation_policy(r,m,rec,manifest)[2],proof.FIRST_FAULT_IMPLEMENTATION_PINS)
  for invalid in [None,'UNKNOWN',1]:
   bad=dict(r,dependency_rule_policy=invalid)
   with self.assertRaisesRegex(ValueError,'explicit readonly GCC prerequisite policy'):proof.compilation_policy(bad,m,rec,manifest)
  bad=copy.deepcopy(manifest);bad['scope']='UNKNOWN'
  with self.assertRaises(ValueError):proof.compilation_policy(r,m,rec,bad)
if __name__=='__main__':unittest.main()
