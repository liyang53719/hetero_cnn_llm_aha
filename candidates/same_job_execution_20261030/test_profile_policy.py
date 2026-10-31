"""Tiny metadata/fake-stage tests ONLY; no framework, weights, native build or DUT."""
import ast,contextlib,copy,hashlib,importlib.util,json,pathlib,sys,tempfile,time,types,unittest
from unittest.mock import patch
PKG=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(PKG/'numeric'))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('policy_under_test',PKG/'profile_policy.py')
r=load('reference_under_test',PKG/'runtime/reference_job.py')
o=load('owner_under_test',PKG/'runtime/owner_fresh.py')
f=load('flow_under_test',PKG/'controller/flow.py')
with patch.dict(sys.modules,{k:types.ModuleType(k)for k in ['live_budget','dut_evidence','provider_from_frozen']}):n=load('numeric_under_test',PKG/'numeric/numeric_tail.py')
B={'execution_policy':p.policy(p.DEFER)}
summary=load('safe_summary_under_test',PKG/'summarize_same_job.py')
class Tests(unittest.TestCase):
 def test_summary_selection_bounded_and_fail_closed(self):
  with tempfile.TemporaryDirectory()as tmp:
   work=pathlib.Path(tmp)/'work';work.mkdir();binding=work.parent/'work-BINDING.json';failure=work.parent/'work-CONTROLLER_FAILURE.json'
   self.assertEqual(summary.execution_policy_summary(work),{'state':'UNOBSERVED_NOT_QUALIFIED'})
   binding.write_text(json.dumps(dict(B,secret_path='/DO_NOT_EXPORT')))
   result=summary.summarize(work,{})
   self.assertFalse(result['numeric_pass']);self.assertEqual(result['execution_selection']['policy'],B['execution_policy']);self.assertNotIn('/DO_NOT_EXPORT',summary.encode(result))
   failure.write_text(json.dumps({'execution_policy':p.policy()}))
   self.assertEqual(summary.execution_policy_summary(work)['state'],'INVALID_OR_CONFLICTING_NOT_QUALIFIED')
 def test_installer_selects_only_eligible_loops(self):
  source=(PKG/'runtime/install_job.py').read_text();tree=ast.parse(source)
  run=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='run')
  key_loops=[x for x in ast.walk(run)if isinstance(x,ast.For)and isinstance(x.target,ast.Name)and x.target.id=='k']
  self.assertEqual(len(key_loops),2)
  self.assertTrue(all(isinstance(x.iter,ast.Name)and x.iter.id=='keys'for x in key_loops))
  self.assertIn('keys=profile_policy.runtimes(b)',source)
  # Conservative three-install/full-five time reservations intentionally unchanged.
  self.assertIn("3*(b['install_wall_seconds']+30)",source)

 def test_policy_source_pin_required(self):
  with self.assertRaises(ValueError):p.require_source_pin({})
  p.require_source_pin({str(PKG/'profile_policy.py'):r.sha(PKG/'profile_policy.py')})
 def test_full_legacy_default_and_explicit(self):
  self.assertEqual(p.eligible({}),list(range(5)));self.assertEqual(p.runtimes({}),('qwen2','qwen35_08b','qwen35_35b'))
  p.require_same({}, {'execution_policy':p.policy()})
  with self.assertRaisesRegex(ValueError,'AVX512'):p.require_cpu({},[])
  p.require_cpu({},['avx512f'])
 def test_deferred_cpu_does_not_qualify_p0(self):
  p.require_cpu(B,[]);self.assertEqual(p.runtimes(B),('qwen35_08b','qwen35_35b'))
  self.assertEqual(p.checked(B)['blocked_profiles'],{'0':'BLOCKED_ORIGINAL_HOST_POLICY'})
  self.assertEqual(p.checked(B)['selection_reason'],'EXPLICIT_POLICY_DEFERRAL_NOT_CPU_OBSERVATION');self.assertEqual(p.checked(B)['cpu_avx512_observation'],'NOT_ASSERTED_BY_SELECTION');self.assertEqual(p.checked(B)['p0_numeric_qualification'],'UNTESTED_IN_THIS_MODE')
  with self.assertRaises(ValueError):p.require_profile(B,0)
 def test_policy_tampering(self):
  for key,val in [('eligible_profiles',[0,1,2,3,4]),('registered_profiles',[1,2,3,4]),('blocked_profiles',{'0':'PASS'}),('schema','V2'),('eligible_profiles',[True,2,3,4]),('mode','arbitrary')]:
   bad=copy.deepcopy(B);bad['execution_policy'][key]=val
   with self.subTest(key=key,val=val),self.assertRaises(ValueError):p.checked(bad)
  with self.assertRaises(ValueError):p.require_same(B,{})
 def test_receipts_exact_no_fabricated_p0(self):
  good={str(i):{}for i in range(1,5)};p.require_references(B,good)
  for bad in [dict(good,**{'0':{}}),{k:v for k,v in good.items()if k!='4'}]:
   with self.assertRaises(ValueError):p.require_references(B,bad)
  with self.assertRaises(ValueError):p.require_references({},good)
 def test_blocked_owner_lease_no_lock_or_receipt(self):
  with patch.object(o,'verify',return_value=(B,None)),self.assertRaisesRegex(ValueError,'blocked'):
   with o.lease('/unused/manifest','unused','/tmp',0,'/tmp'):self.fail('lease granted')
 def test_numeric_validate_same_caps_all_five_registration(self):
  b=dict(B,schema='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,upload_payloads=False,final_rtl_replay=False,references={str(i):{}for i in range(1,5)},calibration_seconds={str(i):300 for i in range(5)},job_started_monotonic=time.monotonic(),reserved_material_seconds=2580,reserved_cleanup_seconds=1530,reserved_parent_seconds=600,tree_cap=12_081_306_272,rss_bytes=8<<30,address_space_bytes=12<<30,phase_extra_bytes=512<<20,provider_wall_seconds=180)
  n.validate(b)
  for key,val in [('profiles',[1,2,3,4]),('matrix_macs',512),('vector_lanes',16),('references',{str(i):{}for i in range(5)}),('tree_cap',1)]:
   with self.subTest(key=key),self.assertRaises(ValueError):n.validate(dict(b,**{key:val}))
 def test_reservations_remain_full_five(self):
  q=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,build=7200,parent=600,calibration_seconds={str(i):300 for i in range(5)})
  self.assertEqual(f.reservations(dict(budgets=q)),f.reservations(dict(B,budgets=q)))
 def reference_case(self,mode=p.DEFER,fail=None,cleanup=True):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=pathlib.Path(tmp.name);owner=root/'owner.py';owner.write_text('# tiny fake owner metadata\n');src=root/'candidates/independent_block_reference_prepare_v3_20261028T2312/run_reference.py';src.parent.mkdir(parents=True);src.write_text('# never executed\n');p0=root/'candidates/independent_reference_p0_cache_arm_20261028T2313/run_reference.py';p0.parent.mkdir();p0.write_text('# never executed\n')
  policy=p.policy(mode);calls=[];active=[]
  @contextlib.contextmanager
  def lease(*args):
   i=args[-2];p.require_profile({'execution_policy':policy},i);active.append(i)
   try:yield {p.MAP[i]:dict(wrapper='/never-executed',receipt=dict(path='/never',sha256='0'*64),sidecar=dict(path='/never',sha256='0'*64))}
   finally:active.remove(i)
  fake=types.SimpleNamespace(verify=lambda *a:({'execution_policy':policy,'identity':{'fixture':'metadata-only'}},None),lease=lease)
  loader=types.SimpleNamespace(create_module=lambda spec:fake,exec_module=lambda m:None)
  spec=importlib.util.spec_from_loader('fake_owner_fixture',loader)
  def stage(name,argv,*args,**kwargs):
   i=int(name.removeprefix('reference'));self.assertEqual(active,[i]);calls.append(i)
   home=kwargs['output_root'];home.mkdir();(home/'FAILURE_PRESERVED.txt').write_text('metadata fixture only')
   if i!=fail:
    dest=home/'reference';dest.mkdir();(dest/'RESULT.json').write_text(json.dumps(dict(profile={'profile':i},complete_block_tokens=128,exact_baseline_observer_output_equal=True,hardware_executed=False,router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',tensor_records={})))
   return dict(native_exit=1 if i==fail else 0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'if cleanup else'UNKNOWN'},log_capture={'pipe_eof_observed':cleanup,'gzip_finalized':cleanup})
  b=dict(execution_policy=policy,profiles=list(range(5)),tokens=128,repo=str(root),output=str(root/'references'),owner_root=str(root),owner_module=str(owner),owner_manifest=dict(path='/fake',sha256='f'*64),pins={str(x):r.sha(x)for x in [owner,src,p0,PKG/'profile_policy.py']},identity={'fixture':'metadata-only'},payload='/never',wall_seconds=1)
  with patch.object(r.importlib.util,'spec_from_file_location',return_value=spec),patch.object(r.signal,'pause',side_effect=RuntimeError('fixture hold observed')):
   if fail is not None or not cleanup:
    with self.assertRaises((ValueError,RuntimeError)):r.run(b,stage)
    self.assertFalse((root/'references/REFERENCES.json').exists());self.assertTrue((root/f'references/profile{calls[-1]}/actual/FAILURE_PRESERVED.txt').is_file())
    if not cleanup:self.assertTrue((root/f'references/profile{calls[-1]}/OWNERSHIP_INCOMPLETE.json').is_file())
   else:
    refs=r.run(b,stage);self.assertEqual(set(refs),set(map(str,policy['eligible_profiles'])))
    summary=json.loads((root/'references/REFERENCES.json').read_text());self.assertEqual(summary['execution_policy'],policy)
  self.assertEqual(active,[])
  if mode==p.DEFER:self.assertFalse((root/'references/profile0').exists())
  return calls
 def test_reference_four_selected_lifecycle(self):self.assertEqual(self.reference_case(),[1,2,3,4])
 def test_reference_full_five_default_equivalent(self):self.assertEqual(self.reference_case(p.FULL),[0,1,2,3,4])
 def test_native_failure_preserves_evidence_no_following_work(self):self.assertEqual(self.reference_case(fail=2),[1,2])
 def test_cleanup_unknown_holds_and_no_continuation(self):self.assertEqual(self.reference_case(cleanup=False),[1])
 def test_source_guards_no_image_relaxation_no_hardware_changes(self):
  for rel in ['prepare_and_run.py','controller/flow.py']:
   self.assertIn("os.environ.get('ImageVersion')=='20261026.354.1'",(PKG/rel).read_text())
  self.assertIn("if profile==0:need('avx512f'",(PKG/'runtime/owner_fresh.py').read_text())
  for path in PKG.rglob('*.py'):ast.parse(path.read_text())
if __name__=='__main__':unittest.main(verbosity=2)
