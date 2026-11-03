import ast,copy,gzip,hashlib,importlib.util,json,pathlib,tempfile,unittest
from unittest import mock
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('ird',D/'original_ir_diagnostic.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

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
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=pathlib.Path(self.t.name);self.r=dict(native_exit=1,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
 def put(self,raw):
  (self.p/'frontend.log.gz').write_bytes(gzip.compress(raw.encode()if isinstance(raw,str)else raw))
 def read(self):return json.loads(m.project(self.p,self.r))
 def test_known(self):
  self.put('HOST_PHASE official.low.begin wall_ns=123 process_cpu_ns=456\nHOST_ARTIFACT original-high.fir bytes=100 sha256='+('a'*64)+'\nException in thread "main" firrtl2.transforms.CheckCombLoops$CombLoopException: secret net/path\n\tat firrtl2.transforms.CheckCombLoops.run(CheckCombLoops.scala:130)\n');d=self.read();self.assertTrue(d['scan_complete']);self.assertEqual(d['phases'][0]['phase'],'official.low.begin');self.assertEqual(d['exceptions'][0]['category'],'CHECK_COMB_LOOPS');self.assertEqual(d['stack'][0],dict(basename='CheckCombLoops.scala',function='run',line=130));self.assertNotIn('secret',json.dumps(d))
 def test_malicious(self):
  self.put('HOST_PHASE SECRET.begin wall_ns=1 process_cpu_ns=1\nHOST_ARTIFACT /private/token bytes=4 sha256='+('a'*64)+'\njava.lang.SecretToken: private\n\tat firrtl2.Secret.token(Secret.scala:5)\n<rawannotation secret>\n');d=self.read();self.assertEqual([d[x]for x in ('phases','artifacts','exceptions','stack')],[[],[],[],[]]);self.assertNotIn('private',json.dumps(d))
 def test_no_eof_never_opens(self):
  self.r['log_capture']['pipe_eof_observed']=False
  with mock.patch.object(m.gzip,'open',side_effect=AssertionError('must not open')):d=self.read()
  self.assertEqual(d['reason'],'CLOSED_CAPTURE_REQUIRED')
 def test_no_cleanup_never_opens(self):
  self.r['cleanup_proof']=None;self.assertEqual(self.read()['status'],'UNAVAILABLE')
 def test_missing_gzip(self):self.assertEqual(self.read()['reason'],'LOG_FILE_UNAVAILABLE')
 def test_bad_gzip(self):
  (self.p/'frontend.log.gz').write_bytes(b'private non gzip');d=self.read();self.assertEqual(d['reason'],'GZIP_INVALID');self.assertFalse(d['scan_complete']);self.assertNotIn('private',json.dumps(d))
 def test_truncated_gzip(self):
  self.put('HOST_PHASE elaborate.begin wall_ns=1 process_cpu_ns=2\n');p=self.p/'frontend.log.gz';p.write_bytes(p.read_bytes()[:-6]);self.assertEqual(self.read()['reason'],'GZIP_INVALID')
 def test_oversize_line(self):
  self.put('private'*(m.MAX_LINE//7+1));d=self.read();self.assertEqual(d['reason'],'SCAN_BOUND');self.assertFalse(d['scan_complete']);self.assertNotIn('private',json.dumps(d))
 def test_raw_cap(self):
  self.put('a\n'*100)
  with mock.patch.object(m,'MAX_RAW',30):self.assertEqual(self.read()['reason'],'SCAN_BOUND')
 def test_compressed_cap(self):
  self.put('x')
  with mock.patch.object(m,'MAX_COMPRESSED',2):self.assertEqual(self.read()['reason'],'LOG_FILE_UNAVAILABLE')
 def test_symlink_refused(self):
  self.put('x');p=self.p/'frontend.log.gz';p.rename(self.p/'target');p.symlink_to(self.p/'target');self.assertEqual(self.read()['reason'],'LOG_FILE_UNAVAILABLE')
 def test_oversize_known_output_bounded(self):
  rows=['HOST_ARTIFACT '+n+' bytes=100 sha256='+('f'*64)for n in sorted(m.ARTIFACTS)]
  rows+=['HOST_PHASE '+n+' wall_ns=1 process_cpu_ns=2'for n in sorted(m.PHASES)]
  rows += [x+': private'for x in m.EXCEPTIONS]
  rows += ['\tat firrtl2.X.secretFunction('+n+':100)'for n in m.FILES]
  self.put('\n'.join(rows)*5);raw=m.project(self.p,self.r);self.assertLessEqual(len(raw.encode()),8192);self.assertNotIn('secretFunction',raw);self.assertNotIn('private',raw)
 def test_require_enum_only(self):
  self.put('java.lang.IllegalArgumentException: requirement failed: SECRET\n');self.assertEqual(self.read()['exceptions'],[dict(exception_class='java.lang.IllegalArgumentException',category='REQUIREMENT_REJECTED')])
 def test_report_not_mutated(self):
  r=copy.deepcopy(self.r);self.put('x');self.read();self.assertEqual(r,self.r)
 def test_caller_ast_preserved(self):
  self.check_original_caller_ast((D/'one_job_model_candidate.py').read_text())
 def check_original_caller_ast(self,text):
  tree=finite_stage_diagnostic_inverse(ast.parse(first_fault_inverse(text)))
  # The separately reviewed finite post-build projector is diagnostic-only.
  # Require its exact AST before removing it; retain the original caller hash.
  additions=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)and n.name=='post_build_failure_diagnostic']
  self.assertEqual(len(additions),1);added=additions[0]
  self.assertEqual(hashlib.sha256(ast.dump(added,include_attributes=False).encode()).hexdigest(),'97ab9c6aa36387fc2c32779c6a62744c37352f7d0c42b540b75e8d842312e31f')
  expression=ast.parse('print("MODEL_POST_BUILD_DIAGNOSTIC "+json.dumps(post_build_failure_diagnostic(phase,exc),sort_keys=True),flush=True)').body[0]
  expected=ast.dump(expression,include_attributes=False)
  self.assertEqual(sum(ast.dump(n,include_attributes=False)==expected for n in ast.walk(tree)),1)
  class Strip(ast.NodeTransformer):
   def visit_FunctionDef(self,n):return None if n.name=='post_build_failure_diagnostic'else self.generic_visit(n)
   def visit_Expr(self,n):return None if ast.dump(n,include_attributes=False)==expected else self.generic_visit(n)
   def visit_If(self,n):
    if ast.unparse(n.test)=="name == 'original_high'"and any(isinstance(x,ast.ImportFrom)and x.module=='original_ir_diagnostic'for x in n.body):return None
    return self.generic_visit(n)
  got=hashlib.sha256(ast.dump(Strip().visit(tree),include_attributes=False).encode()).hexdigest();self.assertEqual(got,'ddd182da38eb18363d491a68faca437e81010b4bf9abfa92cf91456b24cc544b')
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
