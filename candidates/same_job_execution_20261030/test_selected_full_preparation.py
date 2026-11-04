"""Synthetic selected FULL admission/launch wiring; no model/DUT invocation.
Approval fixtures are local test inputs only, not authority for a real launch.
"""
import ast, copy, itertools, json, pathlib, tempfile, types, unittest
from unittest.mock import patch
import cloud_budget as budget
import execution_mode as mode
import profile_policy as policy
import prepare_cloud_execution as prepare
import test_fullprefill_supervision as base
from test_fullprefill_ready_queue import queue_doc
D=pathlib.Path(__file__).resolve().parent

class SelectedAuthority(unittest.TestCase):
 def setUp(self):
  self.real=base.RealCloudCandidateV2Admission();self.real.setUp();self.addCleanup(self.real.doCleanups)
  self.f=self.real.f;self.c=self.real.c
  self.original_doc=copy.deepcopy(self.f.doc)
 def selected(self,selected=(1,2,3,4),avx=False):
  f=self.f;c=self.c;b=f.b
  f.doc=queue_doc(self.original_doc,selected)
  b['execution_policy']=policy.selected_policy(list(selected))
  b['pins'][str(D/'profile_policy.py')]=mode.sha(D/'profile_policy.py')
  b['full_block_budget']=f.f.fixture.write('selected-full.json',f.doc)
  cloud=json.loads(pathlib.Path(b['cloud_budget']['path']).read_text())
  host=json.loads(pathlib.Path(cloud['host_identity']['path']).read_text());host['avx512f']=avx
  cloud['host_identity']=c.put('selected-host',host)
  b['identity']['host_identity_sha256']=cloud['host_identity']['sha256']
  cloud.update(full_block_budget=b['full_block_budget'],execution_policy=b['execution_policy'])
  b['cloud_budget']=c.put('selected-budget',cloud)
  approval=json.loads(pathlib.Path(b['execution_approval']['path']).read_text())
  approval.update(budget_sha256=b['cloud_budget']['sha256'],host_identity_sha256=cloud['host_identity']['sha256'])
  b['execution_approval']=c.put('selected-approval',approval)
  self.cloud=cloud;self.approval=approval
  return b
 def reapprove(self):
  self.f.b['cloud_budget']=self.c.put('selected-budget',self.cloud)
  self.approval['budget_sha256']=self.f.b['cloud_budget']['sha256']
  self.f.b['execution_approval']=self.c.put('selected-approval',self.approval)
 def test_actual_approval_chain_without_p0_cpu(self):
  b=self.selected();admitted=budget.admit(b);a=mode.admit(b)
  self.assertEqual(admitted['execution_policy'],policy.selected_policy([1,2,3,4]))
  self.assertEqual(base.tail.execution_profiles(b,a),[1,2,3,4]);self.assertEqual(a['budget_version'],3)
  self.assertEqual(b['execution_policy']['registered_profiles'],list(range(5)))
 def test_all_nonempty_subsets_keep_exact_queue(self):
  for n in range(1,6):
   for ids in itertools.combinations(range(5),n):
    with self.subTest(ids=ids):
     b=self.selected(ids,0 in ids);a=mode.admit(b)
     self.assertEqual(base.tail.execution_profiles(b,a),list(ids))
 def test_any_p0_selection_preserves_original_cpu_requirement(self):
  for ids in ((0,),(0,1,2,3,4)):
   with self.subTest(ids=ids),self.assertRaisesRegex(ValueError,'P0 original AVX512'):budget.admit(self.selected(ids,False))
 def test_new_binding_policy_without_new_approved_budget_rejected(self):
  b=self.selected();self.cloud.pop('execution_policy');self.reapprove()
  with self.assertRaisesRegex(ValueError,'externally approved policy'):budget.admit(b)
 def test_new_budget_pin_without_new_approval_rejected(self):
  b=self.selected();self.cloud['execution_policy']=policy.selected_policy([1])
  b['cloud_budget']=self.c.put('unapproved-selection',self.cloud)
  with self.assertRaises(ValueError):budget.admit(b)
 def test_binding_policy_must_equal_budget_and_queue(self):
  b=self.selected();b['execution_policy']=policy.selected_policy([1])
  with self.assertRaises(ValueError):budget.admit(b)
  self.cloud['execution_policy']=b['execution_policy'];self.reapprove()
  with self.assertRaisesRegex(ValueError,'selections must match'):budget.admit(b)
 def test_policy_source_pin_required(self):
  b=self.selected();del b['pins'][str(D/'profile_policy.py')]
  with self.assertRaisesRegex(ValueError,'source pin'):budget.admit(b)
 def test_legacy_v2_cannot_opt_into_subset(self):
  b=self.selected();b['full_block_budget']=self.f.f.fixture.write('old-v2',self.original_doc)
  self.cloud['full_block_budget']=b['full_block_budget'];self.reapprove()
  with self.assertRaisesRegex(ValueError,'V3 ready queue'):mode.admit(b)
 def test_selected_cannot_use_calibration_stage_first_fault(self):
  for context in (None,'CLOUD_EXECUTOR_V1'):
   for name in (mode.CALIBRATION,mode.STAGE,mode.FIRST_FAULT):
    with self.subTest(context=context,name=name),self.assertRaisesRegex(ValueError,'ordinary cloud FULL'):
     mode.admit(dict(execution_context=context,execution_mode=name,execution_policy=policy.selected_policy([1]),calibration_seconds={str(i):1 for i in range(5)}))
 def test_tail_does_not_expand_selected_queue(self):
  b=self.selected();a=mode.admit(b);b['execution_policy']=policy.selected_policy([1])
  with self.assertRaises(ValueError):base.tail.execution_profiles(b,a)
 def test_launcher_uses_only_independently_pinned_budget_selection(self):
  b=self.selected();self.assertEqual(prepare.preparation_policy({'cloud_budget':b['cloud_budget']},b['pins'],policy),b['execution_policy'])
  self.cloud['execution_policy']['eligible_profiles']=[True]
  b['cloud_budget']=self.c.put('bad-policy',self.cloud)
  with self.assertRaises(ValueError):prepare.preparation_policy({'cloud_budget':b['cloud_budget']},b['pins'],policy)
 def test_host_observation_is_truthful_not_cpu_emulation(self):
  b=self.selected();host=json.loads(pathlib.Path(self.cloud['host_identity']['path']).read_text())
  self.assertFalse(budget.host_observation(host,b['identity'],b['execution_policy'])['avx512f'])
  with self.assertRaises(ValueError):budget.host_observation(host,b['identity'])
  for fake in (0,1,None,'false'):
   h=dict(host,avx512f=fake)
   with self.subTest(fake=fake),self.assertRaises(ValueError):budget.host_observation(h,b['identity'],b['execution_policy'])


class SelectedControllerWiring(unittest.TestCase):
 def test_actual_fresh_branch_selects_only_reviewed_wrappers(self):
  flow=base.flow
  run=next(n for n in ast.parse((D/'controller/cloud_flow.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='run')
  branch=next(n for n in run.body if isinstance(n,ast.If)and n.orelse and any(isinstance(x,ast.Assign)and any(isinstance(y,ast.Name)and y.id=='reference'for y in x.targets)for x in n.orelse))
  for selected in ([1],[2],[3],[4],[1,2,3,4]):
   with self.subTest(selected=selected),tempfile.TemporaryDirectory()as tmp:
    job=pathlib.Path(tmp);(job/'bindings').mkdir();events=[]
    b=dict(execution_context='CLOUD_EXECUTOR_V1',execution_policy=policy.selected_policy(selected),profiles=list(range(5)),tokens=128,reserved_other_owner_bytes=5<<30,stage_resources={})
    def stage(name,argv,*args,**kwargs):
     self.assertEqual(name,'weights');self.assertEqual(pathlib.Path(argv[2]),D/'runtime/selected_acquisition.py');self.assertIn('--execute',argv)
     wb=pathlib.Path(argv[argv.index('--binding')+1]);body=json.loads(wb.read_text());self.assertEqual(body,dict(b,output=str(job/'runs/weights/output')))
     self.assertEqual(argv[argv.index('--sha256')+1],flow.sha(wb));self.assertEqual(kwargs['extra_pins'],{str(wb):flow.sha(wb)})
     root=pathlib.Path(body['output']);root.mkdir(parents=True);flow.save(root/'SUMMARY.json',{'synthetic':True});folder=root/'synthetic';folder.mkdir();(folder/'weight.bin').write_bytes(b'x');flow.save(folder/'weight.receipt.json',dict(actual_bytes=1,actual_sha256=flow.sha(folder/'weight.bin')));events.append(name);return {'synthetic_native':True}
    def verifier(binding,rows,payload,summary):
     self.assertIs(binding,b);self.assertEqual(summary,{'synthetic':True});self.assertEqual(len(rows),1);events.append('selected_weight_verification');return rows
    def reference(binding,stage_function):
     self.assertEqual(binding['execution_policy'],b['execution_policy']);self.assertEqual(binding['profiles'],list(range(5)));self.assertEqual(binding['tokens'],128);self.assertIs(stage_function,stage);events.append('selected_original_reference_wrapper');return {str(i):{'synthetic':True}for i in selected}
    def mod(name,path):
     if path==D/'runtime/selected_acquisition.py':return types.SimpleNamespace(verify_weights=verifier)
     self.assertEqual(path,D/'runtime/selected_reference_job.py');return types.SimpleNamespace(run=reference)
    env=dict(flow.__dict__,job=job,b=b,repo=D.parents[1],runtime=D/'runtime',py='python',q={'weights':1,'reference':1},execution_policy=b['execution_policy'],owner_root=job/'materials',owner_module=D/'runtime/runtime_reuse.py',owner_pin={'synthetic':True},identity={'synthetic':True},pins={},limit=1,stage=stage,ok=lambda value:None,mod=mod)
    exec(compile(ast.Module(body=[branch],type_ignores=[]),'actual_selected_fresh_branch','exec'),env)
    self.assertEqual(events,['weights','selected_weight_verification','selected_original_reference_wrapper']);self.assertEqual(set(env['references']),set(map(str,selected)))

if __name__=='__main__':unittest.main()
