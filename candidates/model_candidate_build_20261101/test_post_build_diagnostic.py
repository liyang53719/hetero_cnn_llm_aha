"""Finite diagnostic projection only; no subprocess/compiler/ELF execution."""
import ast,hashlib,json,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent

# Exact inverse of the independently reviewed read-only build branch only.
FIRST_FAULT_INVERSE = [(" from first_fault_policy import binding_policy,expected_driver_sha\n diagnostic=binding_policy(b)\n need(b['pins'][b['driver']]==expected_driver_sha(b),'fixed final-state driver')\n", " need(b['pins'][b['driver']]=='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61','V3 final-state driver')\n", '69162cfdddbbbbd1f57bc3f1342165493d8e8e6d3de151341a1080af978b314a'), ("  argv=[b['verilator'],*['+incdir+'+x for x in b['idma_include_dirs']],*['+define+'+x for x in b['idma_defines']],'--cc','--exe','--no-std','--relative-includes','--hierarchical','--build-jobs','1','--verilate-jobs','1','--threads','1','--top-module','HostBlockTopV4','--prefix','VHostBlockTopV4','--Mdir',str(obj),'-Wno-fatal',b['hierarchy'],*([str(repo/diagnostic['probe_config']['repo_path'])] if diagnostic is not None else []),*b['provider_sources'],str(host),str(subset),b['driver'],'-CFLAGS','-std=c++17 -I'+b['driver_include'],'-LDFLAGS','-lcrypto']\n", "  argv=[b['verilator'],*['+incdir+'+x for x in b['idma_include_dirs']],*['+define+'+x for x in b['idma_defines']],'--cc','--exe','--no-std','--relative-includes','--hierarchical','--build-jobs','1','--verilate-jobs','1','--threads','1','--top-module','HostBlockTopV4','--prefix','VHostBlockTopV4','--Mdir',str(obj),'-Wno-fatal',b['hierarchy'],*b['provider_sources'],str(host),str(subset),b['driver'],'-CFLAGS','-std=c++17 -I'+b['driver_include'],'-LDFLAGS','-lcrypto']\n", 'c28ec11c89c4f9b70dd92eda4c46e7c052b98a23b4ab06717bbbc4926ec04476'), ("  if diagnostic is not None:\n   # Pure bounded declaration/provenance work inside original whole-job envelope.\n   # Never modifies SV or generated C++; all actual products enter prebuild pins.\n   from first_fault_probe import generate\n   disk_gate(256<<10)\n   need(time.monotonic()-start<job_budget,'remaining original build budget before probe generation')\n   evidence=out/'readonly-probe-evidence.json'\n   generated=generate(repo/diagnostic['probe_schema']['repo_path'],repo/diagnostic['probe_config']['repo_path'],obj/'VHostBlockTopV4___024root.h',obj/'readonly_first_fault_access.hpp',evidence)\n   b['readonly_probe_evidence']={'path':str(evidence),'bytes':evidence.stat().st_size,'sha256':sha(evidence)}\n   b['pins'][str(evidence)]=sha(evidence)\n   b['pins'][str(obj/'readonly_first_fault_access.hpp')]=generated['accessor']['sha256']\n   b['pins'][str(obj/'VHostBlockTopV4___024root.h')]=generated['root_header']['sha256']\n   disk_gate()\n", '', '6c0d0d8a1e2abe3076700a4c449b8b27fcb05582f928b63789911bb7eeec365b')]

# Exact V2-only inverse; original whole-function baselines below remain unchanged.
TERMINAL_INVERSE = [("  argv=[b['verilator'],*['+incdir+'+x for x in b['idma_include_dirs']],*['+define+'+x for x in b['idma_defines']],'--cc','--exe','--no-std','--relative-includes','--hierarchical','--build-jobs','1','--verilate-jobs','1','--threads','1','--top-module','HostBlockTopV4','--prefix','VHostBlockTopV4','--Mdir',str(obj),'-Wno-fatal',b['hierarchy'],*([str(repo/diagnostic['probe_config']['repo_path'])]+([str(repo/diagnostic['terminal_probe_config']['repo_path'])] if diagnostic.get('schema')=='FIRST_FAULT_DRIVER_CONTRACT_V2' else []) if diagnostic is not None else []),*b['provider_sources'],str(host),str(subset),b['driver'],'-CFLAGS','-std=c++17 -I'+b['driver_include'],'-LDFLAGS','-lcrypto']\n", "  argv=[b['verilator'],*['+incdir+'+x for x in b['idma_include_dirs']],*['+define+'+x for x in b['idma_defines']],'--cc','--exe','--no-std','--relative-includes','--hierarchical','--build-jobs','1','--verilate-jobs','1','--threads','1','--top-module','HostBlockTopV4','--prefix','VHostBlockTopV4','--Mdir',str(obj),'-Wno-fatal',b['hierarchy'],*([str(repo/diagnostic['probe_config']['repo_path'])] if diagnostic is not None else []),*b['provider_sources'],str(host),str(subset),b['driver'],'-CFLAGS','-std=c++17 -I'+b['driver_include'],'-LDFLAGS','-lcrypto']\n", 'c1d0701b02b54a15751376b525070ab2e83b9728c54109bd2edc06f420cfa126'), ("   if diagnostic['schema']=='FIRST_FAULT_DRIVER_CONTRACT_V2':\n    from terminal_finite_probe import generate as generate_terminal\n    disk_gate(8<<20)\n    need(time.monotonic()-start<job_budget,'remaining original build budget before terminal generation')\n    terminal_evidence=out/'terminal-probe-evidence.json'\n    terminal_generated=generate_terminal(repo/diagnostic['terminal_probe_schema']['repo_path'],repo/diagnostic['terminal_probe_config']['repo_path'],obj/'VHostBlockTopV4___024root.h',obj/'readonly_terminal_finite_access.hpp',terminal_evidence)\n    need(terminal_generated['root_header']==generated['root_header'],'same actual scalar/terminal header')\n    b['terminal_probe_evidence']={'path':str(terminal_evidence),'bytes':terminal_evidence.stat().st_size,'sha256':sha(terminal_evidence)}\n    b['pins'][str(terminal_evidence)]=sha(terminal_evidence)\n    b['pins'][str(obj/'readonly_terminal_finite_access.hpp')]=terminal_generated['accessor']['sha256']\n    need(time.monotonic()-start<job_budget,'remaining original build budget after terminal generation')\n", '', 'b7ba6af9e4b55036b6e3e7a73fb39c80a25761b6c1e872a2722495b5f17bcfa7')]
def terminal_inverse(text):
 for added,original,expected in TERMINAL_INVERSE:
  if hashlib.sha256(added.encode()).hexdigest()!=expected or text.count(added)!=1:raise ValueError('unique fixed terminal addition')
  text=text.replace(added,original,1)
 return text

def first_fault_inverse(text):
 text=terminal_inverse(text)
 for added,original,expected in FIRST_FAULT_INVERSE:
  if hashlib.sha256(added.encode()).hexdigest()!=expected or text.count(added)!=1:raise ValueError("unique exact first-fault addition")
  text=text.replace(added,original,1)
 return text

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
  self.tree=ast.parse(first_fault_inverse((D/'one_job_model_candidate.py').read_text()))
  prints=[n for n in ast.walk(self.tree)if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='print'and 'MODEL_POST_BUILD_DIAGNOSTIC' in ast.unparse(n)]
  self.assertEqual(len(prints),1)
  class Strip(ast.NodeTransformer):
   def visit_FunctionDef(self,n):return None if n.name=='post_build_failure_diagnostic'else self.generic_visit(n)
   def visit_Expr(self,n):return None if n in prints else self.generic_visit(n)
  tree=Strip().visit(self.tree);self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),'7709b2e5dd4cf7f3c777d96d5d6f73c68e4f563f6fea7307628cee6575bc0496')
 def test_first_fault_inverse_rejects_duplicate_or_mutated_addition(self):
  text=(D/'one_job_model_candidate.py').read_text();added=FIRST_FAULT_INVERSE[0][0]
  with self.assertRaises(ValueError):first_fault_inverse(text+added)
  with self.assertRaises(ValueError):first_fault_inverse(text.replace(added,added.replace('first_fault','wrong_fault',1),1))
 def test_terminal_inverse_rejects_duplicate_and_mutated_additions(self):
  text=(D/'one_job_model_candidate.py').read_text()
  for added,_,_ in TERMINAL_INVERSE:
   with self.assertRaises(ValueError):terminal_inverse(text+added)
   with self.assertRaises(ValueError):terminal_inverse(text.replace(added,added.replace('terminal','changed_terminal',1),1))
if __name__=='__main__':unittest.main()
