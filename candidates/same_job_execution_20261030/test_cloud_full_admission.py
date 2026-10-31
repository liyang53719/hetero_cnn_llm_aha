"""Synthetic external approval chain; no actual budget, host or numerical evidence."""
import hashlib,importlib.util,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cloud_budget_fixture',D/'test_cloud_budget.py');fx=importlib.util.module_from_spec(spec);spec.loader.exec_module(fx)
spec=importlib.util.spec_from_file_location('cloud_full_mode',D/'execution_mode.py');mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode)
class Full(unittest.TestCase):
 def setUp(self):
  self.f=fx.Budget();self.f.setUp();f=self.f
  evidence=f.put('synthetic-calibration',{'synthetic':True})
  full=dict(schema='FIVE_M128_FULL_EXECUTION_BUDGET_V1',ready=True,scope='WATCHDOG_ADMISSION_ONLY_NOT_NUMERICAL_ACCEPTANCE',tokens=128,matrix_macs=4096,vector_lanes=32,hardware_baseline_sha256=mode.sha(D.parent/'ci_frontend_materialization_r2_20261029/OBSERVER_BASELINE_ACCEPTANCE.json'),driver_sha256=mode.sha(D.parent/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'),basis={'calibration_summary':evidence,'independent_budget_review':evidence},profiles={str(i):dict(wall_seconds=400,max_active_cycles=1000000,estimated_complete_active_cycles=999999,estimated_required_wall_seconds=399)for i in range(5)})
  fullpin=f.put('full-budget',full);f.doc.update(execution_mode=mode.FULL,full_block_budget=fullpin,resource_scope='FULL_BLOCK_MEASURED_RESOURCE_PLAN');f.b['cloud_budget']=f.put('budget',f.doc);f.ap.update(purpose=mode.FULL,budget_sha256=f.b['cloud_budget']['sha256']);f.b['execution_approval']=f.put('approval',f.ap)
  f.b.update(execution_mode=mode.FULL,full_block_budget=fullpin,pins={str(D/'cloud_budget.py'):mode.sha(D/'cloud_budget.py')})
 def tearDown(self):self.f.tearDown()
 def test_external_approval_no_builder_source_mutation(self):
  self.assertIsNone(mode.ACCEPTED_FULL_ADMISSION_SHA256)
  a=mode.admit(self.f.b);self.assertEqual(a['profile_seconds'],{str(i):400 for i in range(5)})
 def test_no_operator_approval_rejected(self):
  del self.f.b['execution_approval']
  with self.assertRaisesRegex(ValueError,'OPERATOR_APPROVED'):mode.admit(self.f.b)
 def test_full_budget_not_approved_rejected(self):
  self.f.b['full_block_budget']=dict(self.f.b['full_block_budget'],sha256='0'*64)
  with self.assertRaises(ValueError):mode.admit(self.f.b)
 def test_source_pin_required(self):
  self.f.b['pins']={}
  with self.assertRaises(ValueError):mode.admit(self.f.b)
if __name__=='__main__':unittest.main()
