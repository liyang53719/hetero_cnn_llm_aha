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

# Invert only the independently reviewed finite stage-error diagnostic delta.
# Every modified node is fingerprinted before inversion; older baselines below
# remain unchanged. Any unrelated caller delta remains for those hashes to reject.
def finite_stage_diagnostic_inverse(tree):
 import copy
 tree=copy.deepcopy(tree)
 def exact(name,kind,wanted):
  rows=[n for n in ast.walk(tree)if isinstance(n,kind)and (getattr(n,'name',None)==name if kind is ast.FunctionDef else any(isinstance(t,ast.Name)and t.id==name for t in n.targets))]
  if len(rows)!=1 or rows[0]not in tree.body or hashlib.sha256(ast.dump(rows[0],include_attributes=False).encode()).hexdigest()!=wanted:raise ValueError('unique exact finite diagnostic addition: '+name)
  return rows[0]
 mapping=exact('BUILD_ERROR_CODES',ast.Assign,'a729e7597bafab5f6701ae9d1c1da3baf400055353220bb043d6f2a94d0fbab0')
 helper=exact('build_error_details',ast.FunctionDef,'250067d1136c1f9a4bf536748426ef7a90c6350430ce421e7241fbcee0ef29bb')
 projection=exact('build_stage_diagnostic',ast.FunctionDef,'d4f21a1995a62cb703ae6f39a943f428613e12d74a5b06484e9825ce37670bc4')
 remove=set(['ValueError: proc enumeration cap', 'ValueError: observed process cap', 'ValueError: tracked PID reused within owned set', 'ValueError: RSS telemetry 64MiB cap', 'ValueError: output link forbidden', 'ValueError: nonregular output', 'ValueError: observed identities remain after group cleanup', 'InterruptedError: signal 2', 'InterruptedError: signal 15'])
 pairs=[(k,v)for k,v in zip(mapping.value.keys,mapping.value.values)if ast.literal_eval(k)not in remove]
 if len(mapping.value.keys)-len(pairs)!=len(remove):raise ValueError('exact finite reason additions')
 mapping.value.keys=[k for k,v in pairs];mapping.value.values=[v for k,v in pairs]
 if hashlib.sha256(ast.dump(mapping,include_attributes=False).encode()).hexdigest()!='4dafad7e30bf9fe6b37c7c8ccf39bd00c6a32e78da15d47a62eada98de6aa65a':raise ValueError('original finite reason map restored')
 calls=[n.value for n in projection.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='result'for t in n.targets)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='dict']
 if len(calls)!=1:raise ValueError('unique finite result projection')
 keys=('error_details','error_details_truncated')
 if any(sum(k.arg==name for k in calls[0].keywords)!=1 for name in keys):raise ValueError('exact finite detail keywords')
 calls[0].keywords=[k for k in calls[0].keywords if k.arg not in keys]
 if hashlib.sha256(ast.dump(projection,include_attributes=False).encode()).hexdigest()!='95cb21dc353efc0491dfaab9134bb31e769fabfcfe1aecafaa4f23e6a8c53c29':raise ValueError('original finite projection restored')
 tree.body.remove(helper)
 return tree

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
  self.check_original_caller_ast((D/'one_job_model_candidate.py').read_text())
 def check_original_caller_ast(self,text):
  self.tree=finite_stage_diagnostic_inverse(ast.parse(first_fault_inverse(text)))
  prints=[n for n in ast.walk(self.tree)if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='print'and 'MODEL_POST_BUILD_DIAGNOSTIC' in ast.unparse(n)]
  self.assertEqual(len(prints),1)
  class Strip(ast.NodeTransformer):
   def visit_FunctionDef(self,n):return None if n.name=='post_build_failure_diagnostic'else self.generic_visit(n)
   def visit_Expr(self,n):return None if n in prints else self.generic_visit(n)
  tree=Strip().visit(self.tree);self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),'7709b2e5dd4cf7f3c777d96d5d6f73c68e4f563f6fea7307628cee6575bc0496')
 def test_finite_stage_inverse_rejects_missing_duplicate_and_mutated_nodes(self):
  original=ast.parse((D/'one_job_model_candidate.py').read_text())
  for change in ('missing_helper','duplicate_helper','extra_reason','changed_keyword'):
   import copy
   tree=copy.deepcopy(original)
   helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='build_error_details')
   if change=='missing_helper':tree.body.remove(helper)
   elif change=='duplicate_helper':tree.body.append(copy.deepcopy(helper))
   elif change=='extra_reason':
    mapping=next(n for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='BUILD_ERROR_CODES'for t in n.targets));mapping.value.keys.append(ast.Constant('ValueError: arbitrary'));mapping.value.values.append(ast.Constant('ARBITRARY'))
   else:
    projection=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='build_stage_diagnostic');keyword=next(n for n in ast.walk(projection)if isinstance(n,ast.keyword)and n.arg=='error_details_truncated');keyword.value=ast.Constant(False)
   with self.subTest(change=change),self.assertRaises(ValueError):finite_stage_diagnostic_inverse(tree)
 def test_unrelated_caller_delta_still_rejected_by_original_hash(self):
  text=(D/'one_job_model_candidate.py').read_text()
  with self.assertRaises(AssertionError):self.check_original_caller_ast(text+'\nUNRELATED_UNREVIEWED_CHANGE=True\n')
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
