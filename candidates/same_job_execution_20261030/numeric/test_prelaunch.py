import ast,copy,json,os,pathlib,signal,tempfile,types,unittest,hashlib
from unittest.mock import patch
P=pathlib.Path;D=P(__file__).resolve().parent
source=ast.parse((D/'numeric_tail.py').read_text())
selected=[n for n in source.body if isinstance(n,ast.FunctionDef)and n.name in ('sha','save','complete','prelaunch_rejection','require_cleanup')or isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id.startswith('PRELAUNCH_')for t in n.targets)]
ns=dict(P=P,json=json,hashlib=hashlib,signal=signal)
exec(compile(ast.Module(body=selected,type_ignores=[]),'numeric_tail.py','exec'),ns)
REVIEWED_STAGE_INVERSE = {'numeric/numeric_tail.py': [('bdcea0b9485bc538800ae32c592d6a6c4249b1a1913f741bbccbe3a540492a0c',
                              "for key in ('executor_adaptation', 'workspace_loader', "
                              "'model_candidate_review', 'stage_coverage_budget', 'p0_provider_reuse'):\n"
                              "    need(controller.get(key) == b.get(key), 'retained tail/controller "
                              "optional ' + key)",
                              "for key in ('executor_adaptation', 'workspace_loader', "
                              "'model_candidate_review'):\n"
                              "    need(controller.get(key) == b.get(key), 'retained tail/controller "
                              "optional ' + key)"),
                             ('bed00c36a34e5ccd3a72c41f9418cf2fe621c191907aa35e04166f1eb43760e6',
                              "need(admitted.get('stage_coverage_budget') == b.get('stage_coverage_budget'), "
                              "'tail exact approved stage coverage budget')\n"
                              "need(admitted.get('p0_provider_reuse') == b.get('p0_provider_reuse'), 'tail "
                              "exact approved P0 input reuse')\n"
                              "if b.get('p0_provider_reuse') is not None:\n"
                              "    need(b['execution_mode'] == execution_mode.STAGE and "
                              "b.get('model_candidate_review') is not None, 'P0 reuse only approved "
                              "candidate stage coverage')",
                              ''),
                             ('62abe71a79bdafe96809503b4f9bc5e99220c351dba8ab329721a93bf49e9b00',
                              'def execution_command(generated, b, admission, profile):\n'
                              "    need(generated[1] == str(D / 'consumer_owned.py'), 'explicit owned "
                              "consumer handoff')\n"
                              "    need(not any((flag in generated for flag in ('--execution-mode', "
                              "'--calibration-wall-seconds', '--full-block-budget', "
                              "'--full-block-budget-sha256', '--stage-coverage-budget', "
                              "'--stage-coverage-budget-sha256'))), 'no stale or duplicate execution mode "
                              "arguments')\n"
                              "    argv = list(generated) + ['--execution-mode', admission['mode']]\n"
                              "    if admission['mode'] == execution_mode.CALIBRATION:\n"
                              "        argv += ['--calibration-wall-seconds', "
                              "str(admission['profile_seconds'][str(profile)])]\n"
                              "    elif admission['mode'] == execution_mode.STAGE:\n"
                              "        need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and "
                              "b.get('full_block_budget') is None, 'stage coverage is cloud-only, not full "
                              "acceptance')\n"
                              "        budget = b['stage_coverage_budget']\n"
                              "        argv += ['--stage-coverage-budget', budget['path'], "
                              "'--stage-coverage-budget-sha256', budget['sha256']]\n"
                              '    else:\n'
                              "        need(admission['mode'] == execution_mode.FULL, 'explicit execution "
                              "mode')\n"
                              "        budget = b['full_block_budget']\n"
                              "        argv += ['--full-block-budget', budget['path'], "
                              "'--full-block-budget-sha256', budget['sha256']]\n"
                              "    if b.get('execution_context') == 'CLOUD_EXECUTOR_V1':\n"
                              "        invocation = b['controller_binding']\n"
                              '        material.checked(invocation)\n'
                              "        flags = ('--cloud-binding', '--cloud-binding-sha256')\n"
                              '        if any((flag in argv for flag in flags)):\n'
                              "            need(all((argv.count(flag) == 1 for flag in flags)), 'exact one "
                              "paired generated cloud invocation')\n"
                              '            need(all((argv.index(flag) + 1 < len(argv) for flag in flags)), '
                              "'generated cloud invocation values')\n"
                              "            need(argv[argv.index(flags[0]) + 1] == invocation['path'] and "
                              "argv[argv.index(flags[1]) + 1] == invocation['sha256'], 'generated cloud "
                              "invocation unchanged')\n"
                              '        else:\n'
                              "            argv += ['--cloud-binding', invocation['path'], "
                              "'--cloud-binding-sha256', invocation['sha256']]\n"
                              "    return (argv, admission['profile_seconds'][str(profile)] + 30)\n"
                              'def mode_budget_fields(admission):\n'
                              "    if admission['mode'] == execution_mode.STAGE:\n"
                              '        return dict(full_budget_sha256=None, '
                              "stage_budget_sha256=admission['reviewed_budget_sha256'])\n"
                              "    need(admission['mode'] in (execution_mode.CALIBRATION, "
                              "execution_mode.FULL), 'explicit numeric execution mode')\n"
                              "    return dict(full_budget_sha256=admission['reviewed_budget_sha256'])",
                              'def execution_command(generated, b, admission, profile):\n'
                              "    need(generated[1] == str(D / 'consumer_owned.py'), 'explicit owned "
                              "consumer handoff')\n"
                              "    need(not any((flag in generated for flag in ('--execution-mode', "
                              "'--calibration-wall-seconds', '--full-block-budget', "
                              "'--full-block-budget-sha256'))), 'no stale or duplicate execution mode "
                              "arguments')\n"
                              "    argv = list(generated) + ['--execution-mode', admission['mode']]\n"
                              "    if admission['mode'] == execution_mode.CALIBRATION:\n"
                              "        argv += ['--calibration-wall-seconds', "
                              "str(admission['profile_seconds'][str(profile)])]\n"
                              '    else:\n'
                              "        need(admission['mode'] == execution_mode.FULL, 'explicit execution "
                              "mode')\n"
                              "        budget = b['full_block_budget']\n"
                              "        argv += ['--full-block-budget', budget['path'], "
                              "'--full-block-budget-sha256', budget['sha256']]\n"
                              "    if b.get('execution_context') == 'CLOUD_EXECUTOR_V1':\n"
                              "        invocation = b['controller_binding']\n"
                              '        material.checked(invocation)\n'
                              "        flags = ('--cloud-binding', '--cloud-binding-sha256')\n"
                              '        if any((flag in argv for flag in flags)):\n'
                              "            need(all((argv.count(flag) == 1 for flag in flags)), 'exact one "
                              "paired generated cloud invocation')\n"
                              '            need(all((argv.index(flag) + 1 < len(argv) for flag in flags)), '
                              "'generated cloud invocation values')\n"
                              "            need(argv[argv.index(flags[0]) + 1] == invocation['path'] and "
                              "argv[argv.index(flags[1]) + 1] == invocation['sha256'], 'generated cloud "
                              "invocation unchanged')\n"
                              '        else:\n'
                              "            argv += ['--cloud-binding', invocation['path'], "
                              "'--cloud-binding-sha256', invocation['sha256']]\n"
                              "    return (argv, admission['profile_seconds'][str(profile)] + 30)"),
                             ('14c45709306421c7eb9c1d7586bf2f0a7d73e60bbbbc44659fe65c77307a0667',
                              "save(out / 'REGISTERED_FIVE.json', "
                              "dict(execution_policy=profile_policy.checked(b), profiles=b['profiles'], "
                              "tokens=128, execution_mode=admission['mode'], "
                              "profile_seconds=admission['profile_seconds'], "
                              '**mode_budget_fields(admission), '
                              "scope='CHISEL_EMITTED_SV_SIMULATION_NOT_FINAL_RTL', numeric_pass=False))",
                              "save(out / 'REGISTERED_FIVE.json', "
                              "dict(execution_policy=profile_policy.checked(b), profiles=b['profiles'], "
                              "tokens=128, execution_mode=admission['mode'], "
                              "profile_seconds=admission['profile_seconds'], "
                              "full_budget_sha256=admission['reviewed_budget_sha256'], "
                              "scope='CHISEL_EMITTED_SV_SIMULATION_NOT_FINAL_RTL', numeric_pass=False))"),
                             ('248fbf4be67bf4368a057bbf852337fd07575088a5c54d838fe4f402557e539a',
                              "material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], provider_stage, "
                              "pins, p0_provider_reuse=b.get('p0_provider_reuse') if i == 0 else None)",
                              "material.prepare(b['repo'], b['materializer'], profile, i, "
                              "runtime['wrapper'], b['payload'], b['references'][str(i)], provider_stage, "
                              'pins)'),
                             ('11da7ba6b6bc4260b1e29ff4c005dfa915a4fffea63b4a69b7f7c23ee5c30b04',
                              "if admission['mode'] in (execution_mode.FULL, execution_mode.STAGE):\n"
                              "    report = json.loads((profile / 'dut_result/RESULT.json').read_text())\n"
                              "    actual = report['execution_admission']\n"
                              "    need(actual['execution_mode'] == admission['mode'] and "
                              "actual['reviewed_budget_sha256'] == admission['reviewed_budget_sha256'], "
                              "'actual consumer full-mode budget identity')\n"
                              "    scope = 'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' if "
                              "admission['mode'] == execution_mode.STAGE else "
                              "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'\n"
                              "    need(actual['scope'] == scope and actual['outer_cleanup_proof_required'] "
                              "is True, 'actual explicit execution scope')\n"
                              "    if admission['mode'] == execution_mode.STAGE:\n"
                              "        need(actual.get('stage_budget_sha256') == "
                              "admission['reviewed_budget_sha256'], 'actual stage coverage budget "
                              "identity')\n"
                              "    expected_limits = report_effective_limits(actual['original_limits'], b, "
                              'admission, i)\n'
                              "    need(actual['effective_limits'] == expected_limits, 'actual full watchdog "
                              "limits')",
                              "if admission['mode'] == execution_mode.FULL:\n"
                              "    report = json.loads((profile / 'dut_result/RESULT.json').read_text())\n"
                              "    actual = report['execution_admission']\n"
                              "    need(actual['execution_mode'] == admission['mode'] and "
                              "actual['reviewed_budget_sha256'] == admission['reviewed_budget_sha256'], "
                              "'actual consumer full-mode budget identity')\n"
                              "    need(actual['scope'] == "
                              "'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE' and "
                              "actual['outer_cleanup_proof_required'] is True, 'actual full execution "
                              "scope')\n"
                              "    expected_limits = report_effective_limits(actual['original_limits'], b, "
                              'admission, i)\n'
                              "    need(actual['effective_limits'] == expected_limits, 'actual full watchdog "
                              "limits')"),
                             ('7ab78476782ee6a7a55c1fbfe868d9f131a7d019fb7a45a3e086710e4c11b930',
                              "save(out / 'RESULT.json', dict(execution_mode=admission['mode'], "
                              '**mode_budget_fields(admission), qualification=qualification, '
                              "execution_policy=profile_policy.checked(b), status=qualification['status'], "
                              "scope='CHISEL_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=allstage, "
                              "profiles=b['profiles'], actual_dut_reports=dut_records, "
                              "numerical_pass=qualification['numerical_pass'], "
                              "moe_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE', "
                              'uploaded_payloads=False))',
                              "save(out / 'RESULT.json', dict(execution_mode=admission['mode'], "
                              "full_budget_sha256=admission['reviewed_budget_sha256'], "
                              'qualification=qualification, execution_policy=profile_policy.checked(b), '
                              "status=qualification['status'], "
                              "scope='CHISEL_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL', stages=allstage, "
                              "profiles=b['profiles'], actual_dut_reports=dut_records, "
                              "numerical_pass=qualification['numerical_pass'], "
                              "moe_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE', "
                              'uploaded_payloads=False))')]}

# Exact inverse of the reviewed stage-coverage / P0 data-only additions.
# Mandatory unique full-AST snippet matches; original historical whole-AST hashes
# below remain unchanged. No arbitrary mode branch or dependency gate is skipped.
def undo_reviewed_stage_delta(test,tree,relative):
 import copy
 for digest,new_text,old_text in REVIEWED_STAGE_INVERSE[relative]:
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  test.assertEqual(hashlib.sha256(ast.dump(ast.Module(body=want,type_ignores=[]),include_attributes=False).encode()).hexdigest(),digest)
  count=0
  def visit(node):
   nonlocal count
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     i=0
     while i<=len(value)-len(want):
      if [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==[ast.dump(n,include_attributes=False)for n in want]:
       value[i:i+len(want)]=copy.deepcopy(replacement);count+=1;i+=len(replacement)
      else:i+=1
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree);test.assertEqual(count,1,'exact reviewed inverse snippet matched once: '+digest)
 return tree

class Held(Exception):pass

def receipt():
 return dict(argv=['synthetic'],caps={},cleanup_proof=None,elapsed_seconds=0.1,errors=['ValueError: locked memory gate'],limitations=[],native_exit=None,observed_cpu_seconds=0,observed_peak_rss=0,observed_processes=[],peak_file_bytes=0,peak_tree_bytes=0,reader_join_barrier={'complete':True,'alive':False,'reader_finally_done':False},scope='ORIGINAL_PROCESS_GROUP_AND_OBSERVED_DESCENDANTS_ONLY',status='FAIL_OR_INCOMPLETE',supervisor_cpu_scope='synthetic',supervisor_cpu_seconds=0.1,worker_started=False)

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name);self.run=self.root/'absent';self.supervisor=self.root/'supervisor.py';self.supervisor.write_text('synthetic');self.marker=self.root/'HOLD.json'
 def held(self,r,run=None,source=None):
  with patch.object(signal,'pause',side_effect=Held),patch.dict(ns,sha=lambda p:ns['PRELAUNCH_SUPERVISOR_SHA']):
   with self.assertRaises(Held):ns['require_cleanup'](r,self.marker,self.run if run is None else run,self.supervisor if source is None else source)
  self.assertEqual(json.loads(self.marker.read_text())['status'],'HOLD_PARENT_LEASE_NO_CONTINUATION');self.marker.unlink()
  self.assertFalse(self.marker.with_name('PRELAUNCH_REJECTED_'+self.marker.name).exists())
 def test_exact_prelaunch_three_errors(self):
  for error in ns['PRELAUNCH_ERRORS']:
   r=receipt();r['errors']=[error]
   with patch.dict(ns,sha=lambda p:ns['PRELAUNCH_SUPERVISOR_SHA']):
    with self.assertRaisesRegex(ValueError,'before worker launch; INCOMPLETE'):ns['require_cleanup'](r,self.marker,self.run,self.supervisor)
   marker=self.marker.with_name('PRELAUNCH_REJECTED_'+self.marker.name);self.assertFalse(self.marker.exists());self.assertFalse(self.run.exists());self.assertFalse(json.loads(marker.read_text())['numerical_pass']);marker.unlink()
 def test_unknown_or_started_evidence_holds(self):
  changes=[{'worker_started':0},{'worker_started':True},{'native_exit':0},{'cleanup_proof':{}},{'observed_processes':[{'pid':1}]},{'observed_processes':()}, {'owner_identity':None},{'log_capture':None},{'errors':['ValueError: leader identity mismatch']},{'errors':['ValueError: locked memory gate','extra']},{'observed_peak_rss':1},{'reader_join_barrier':{'complete':True,'alive':False,'reader_finally_done':True}},{'reader_join_barrier':{'complete':1,'alive':0,'reader_finally_done':False}},{'unknown_process_identity':1}]
  for delta in changes:
   with self.subTest(delta=delta):r=receipt();r.update(delta);self.held(r)
 def test_existing_run_and_dangling_symlink_hold(self):
  self.run.mkdir();self.held(receipt());self.run.rmdir();self.run.symlink_to(self.root/'missing');self.held(receipt())
 def test_post_popen_pre_flag_failure_holds(self):
  self.run.mkdir();(self.run/'frontend.log.gz').write_bytes(b'')
  r=receipt();r['errors']=['ValueError: leader verification'];self.held(r)
 def test_missing_arguments_or_bad_source_hold(self):
  with patch.object(signal,'pause',side_effect=Held):
   with self.assertRaises(Held):ns['require_cleanup'](receipt(),self.marker)
  self.marker.unlink()
  with patch.object(signal,'pause',side_effect=Held):
   with self.assertRaises(Held):ns['require_cleanup'](receipt(),self.marker,self.run,self.supervisor)
 def test_complete_unchanged(self):
  r={'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  ns['require_cleanup'](r,self.marker);self.assertFalse(self.marker.exists())
 def test_actual_retained_return_and_source_order(self):
  if not os.environ.get('ACTUAL_RETURN')or not os.environ.get('SUPERVISOR_SOURCE'):self.skipTest('optional actual read-only evidence paths not supplied')
  actual=P(os.environ['ACTUAL_RETURN']);supervisor=P(os.environ['SUPERVISOR_SOURCE'])
  self.assertEqual(hashlib.sha256(actual.read_bytes()).hexdigest(),'c89287a9aa298fc602d172b6cab4b6ff2653730989fc4517250d339ad3495fa9')
  r=json.loads(actual.read_text());actual_run=actual.parent.parent/'runs'/actual.name.removesuffix('_SUPERVISOR_RETURN.json');self.assertTrue(ns['prelaunch_rejection'](r,actual_run,supervisor));self.assertTrue(ns['prelaunch_rejection'](r,self.run,supervisor))
  text=supervisor.read_text();self.assertEqual(ns['sha'](supervisor),ns['PRELAUNCH_SUPERVISOR_SHA'])
  self.assertLess(text.index("'locked memory gate'"),text.index('run.mkdir()'));self.assertLess(text.index("'locked disk gate'"),text.index('run.mkdir()'));self.assertLess(text.index("'prelaunch work deadline'"),text.index('run.mkdir()'));self.assertLess(text.index('run.mkdir()'),text.index('p=subprocess.Popen('));self.assertLess(text.index('p=subprocess.Popen('),text.index("report['worker_started']=True"))
 def test_all_other_production_ast_unchanged(self):
  t=undo_reviewed_stage_delta(self,copy.deepcopy(source),'numeric/numeric_tail.py')
  t.body=[n for n in t.body if not(isinstance(n,ast.FunctionDef)and n.name=='prelaunch_rejection')and not(isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id.startswith('PRELAUNCH_')for x in n.targets))]
  old=ast.parse("def require_cleanup(r,marker):\n if not complete(r):\n  save(marker,dict(status='HOLD_PARENT_LEASE_NO_CONTINUATION'))\n  while True:signal.pause()\n").body[0]
  t.body=[old if isinstance(n,ast.FunctionDef)and n.name=='require_cleanup'else n for n in t.body]
  for n in ast.walk(t):
   if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require_cleanup':n.args=n.args[:2]
  # Undo ONLY exact independently reviewed candidate additions. Each match is
  # mandatory once; every remaining AST node is still checked by the old hash.
  def replace_statements(new_text,old_text):
   want=ast.parse(new_text).body;replacement=ast.parse(old_text).body;count=0
   def visit(node):
    nonlocal count
    for field,value in ast.iter_fields(node):
     if isinstance(value,list):
      i=0
      while i<=len(value)-len(want):
       if list(map(lambda n:ast.dump(n,include_attributes=False),value[i:i+len(want)]))==list(map(lambda n:ast.dump(n,include_attributes=False),want)):
        value[i:i+len(want)]=copy.deepcopy(replacement);count+=1;i+=len(replacement)
       else:i+=1
      for item in value:
       if isinstance(item,ast.AST):visit(item)
     elif isinstance(value,ast.AST):visit(value)
   visit(t);self.assertEqual(count,1,new_text)
  replace_statements("if b.get('model_candidate_review')is not None:need(controller['source_pins']==b['source_pins'],'candidate tail/controller exact source catalog')",'')
  replace_statements("need(admitted.get('model_candidate_review')==b.get('model_candidate_review'),'tail exact approved candidate review')\nif b.get('model_candidate_review')is not None:module('tail_model_candidate',D/'candidate_admission.py',b['pins']).verify(b['model_candidate_review'],b)",'')
  replace_statements("""
candidate=frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
proof=module('split_build_proof',D/('candidate_artifact_handoff.py'if candidate else'artifact_handoff.py'),pins)
kwargs=dict(executor_adaptation=b.get('executor_adaptation'))
if candidate:kwargs.update(model_candidate_review=b.get('model_candidate_review'),current_source_pins_pin=b['source_pins'],repo=b['repo'])
proof.verify(b['builder_handoff']['path'],b['builder_handoff']['sha256'],manifest,sha(manifest),frozen,cloud,**kwargs)
""","""
proof=module('split_build_proof',D/'artifact_handoff.py',pins)
proof.verify(b['builder_handoff']['path'],b['builder_handoff']['sha256'],manifest,sha(manifest),frozen,cloud,executor_adaptation=b.get('executor_adaptation'))
""")
  pairs=[("('executor_adaptation','workspace_loader','model_candidate_review')","('executor_adaptation','workspace_loader')"),("('DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS'if b.get('model_candidate_review')is not None else'REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT')","'REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT'")]
  for new_text,old_text in pairs:
   new=ast.parse(new_text,mode='eval').body;old=ast.parse(old_text,mode='eval').body;hits=[]
   class Normalize(ast.NodeTransformer):
    def visit(self,node):
     if ast.dump(node,include_attributes=False)==ast.dump(new,include_attributes=False):hits.append(True);return copy.deepcopy(old)
     return super().visit(node)
   t=Normalize().visit(t);self.assertEqual(len(hits),1,new_text)
  self.assertEqual(hashlib.sha256(ast.dump(t,include_attributes=False).encode()).hexdigest(),'d9dac3f15753fab0b3a137a9baee460061b0f15c9a3a6a8d777631793573d171')
 def test_actual_stage_passes_real_output_and_supervisor_source(self):
  calls=[n for n in ast.walk(source)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require_cleanup']
  self.assertEqual(len(calls),1);self.assertEqual(ast.unparse(calls[0].args[2]),'run_dir');self.assertEqual(ast.unparse(calls[0].args[3]),'P(supervisor.__file__)')
class InverseNegativeTests(unittest.TestCase):
 def test_reviewed_delta_mutation_and_duplicate_rejected(self):
  for relative,rows in REVIEWED_STAGE_INVERSE.items():
   root=D.parent if D.name=='numeric'else D
   original=ast.parse((root/relative).read_text())
   # An additional copy cannot silently disappear: unique match count must fail.
   duplicate=ast.parse((root/relative).read_text());duplicate.body.extend(ast.parse(rows[0][1]).body)
   with self.subTest(relative=relative,case='duplicate'),self.assertRaises(AssertionError):undo_reviewed_stage_delta(self,duplicate,relative)
   # Mutating the stage discriminator anywhere is not accepted as the reviewed delta.
   hit=False
   for n in ast.walk(original):
    if isinstance(n,ast.Constant)and n.value=='STAGE_COVERAGE_DIAGNOSTIC':n.value='UNREVIEWED_STAGE_MODE';hit=True
   if not hit:
    for n in ast.walk(original):
     if isinstance(n,ast.Attribute)and n.attr=='STAGE':n.attr='UNREVIEWED_STAGE';hit=True
   self.assertTrue(hit)
   with self.subTest(relative=relative,case='changed gate'),self.assertRaises(AssertionError):undo_reviewed_stage_delta(self,original,relative)

if __name__=='__main__':unittest.main()
