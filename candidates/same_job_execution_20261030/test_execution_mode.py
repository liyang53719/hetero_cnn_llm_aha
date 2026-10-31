"""Synthetic budget tests only; no actual calibration admission or DUT execution."""
import hashlib,json,pathlib,tempfile,unittest,copy
from unittest.mock import patch
import execution_mode as m
import profile_policy
D=pathlib.Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.t.name)
 def tearDown(self):self.t.cleanup()
 def pin(self,p):return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 def fixture(self):
  ev=self.root/'synthetic.json';ev.write_text('{"synthetic_only":true}')
  doc=dict(schema='FIVE_M128_FULL_EXECUTION_BUDGET_V1',ready=True,scope='WATCHDOG_ADMISSION_ONLY_NOT_NUMERICAL_ACCEPTANCE',tokens=128,matrix_macs=4096,vector_lanes=32,hardware_baseline_sha256=m.sha(D.parent/'ci_frontend_materialization_r2_20261029/OBSERVER_BASELINE_ACCEPTANCE.json'),driver_sha256=m.sha(D.parent/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'),basis=dict(calibration_summary=self.pin(ev),independent_budget_review=self.pin(ev)),profiles={str(i):dict(wall_seconds=500,max_active_cycles=100000,estimated_complete_active_cycles=90000,estimated_required_wall_seconds=450)for i in range(5)})
  return doc
 def admit_fixture(self,doc):
  path=self.root/'budget.json';path.write_text(json.dumps(doc));pin=self.pin(path)
  with patch.object(m,'ACCEPTED_FULL_ADMISSION_SHA256',pin['sha256']):return m.admit(dict(execution_mode=m.FULL,execution_policy=profile_policy.policy(),full_block_budget=pin))
 def test_calibration_compatible_explicit(self):
  r=m.admit({'calibration_seconds':{str(i):300 for i in range(5)}});self.assertEqual(r['profile_seconds']['0'],300);self.assertIsNone(r['profile_max_active_cycles'])
 def test_real_full_pending_before_file_or_default(self):
  with self.assertRaisesRegex(ValueError,'PENDING'):m.admit(dict(execution_mode=m.FULL,full_block_budget=None))
  self.assertIsNone(m.ACCEPTED_FULL_ADMISSION_SHA256)
 def test_synthetic_full_allfive_two_explicit_limits(self):
  r=self.admit_fixture(self.fixture());self.assertEqual(r['profile_seconds'],{str(i):500 for i in range(5)});self.assertEqual(r['profile_max_active_cycles']['4'],100000)
 def test_missing_bool_bounds_predictions_and_hardware_fail(self):
  original=self.fixture()
  variants=[]
  for key,value in [('wall_seconds',None),('wall_seconds',True),('wall_seconds',18001),('max_active_cycles',1000000001),('estimated_complete_active_cycles',100001),('estimated_required_wall_seconds',501)]:
   x=copy.deepcopy(original);x['profiles']['2'][key]=value;variants.append(x)
  x=copy.deepcopy(original);del x['profiles']['4'];variants.append(x)
  x=copy.deepcopy(original);x['ready']=False;variants.append(x)
  x=copy.deepcopy(original);x['driver_sha256']='0'*64;variants.append(x)
  for doc in variants:
   with self.subTest(doc=doc),self.assertRaises(ValueError):self.admit_fixture(doc)
 def test_evidence_must_exist_and_hash_match(self):
  x=self.fixture();x['basis']['calibration_summary']['sha256']='0'*64
  with self.assertRaises(ValueError):self.admit_fixture(x)
 def test_defer_never_full_five(self):
  with self.assertRaisesRegex(ValueError,'all five'):m.admit(dict(execution_mode=m.FULL,execution_policy=profile_policy.policy(profile_policy.DEFER)))
 def test_only_two_limits_can_change(self):
  original=dict(wall_seconds=20000,cpu_seconds=18000,max_active_cycles=1000000000,address_space_bytes=12<<30,file_bytes=64<<20)
  before=dict(original);r=m.consumer_limits(original,self.admit_fixture(self.fixture()),2)
  self.assertEqual(original,before);self.assertEqual({k for k in original if original[k]!=r[k]},{'wall_seconds','max_active_cycles'})
  with self.assertRaises(ValueError):m.consumer_limits(dict(original,max_active_cycles=999),self.admit_fixture(self.fixture()),2)
 def test_transport_follows_full_aggregate_only(self):
  for status,passed,code in [('PASS_FIVE_FULL128_EXACT_REFERENCE',True,0),('FAIL_EXACT_REFERENCE',False,1),('INCOMPLETE',False,2)]:
   q=dict(status=status,numerical_pass=passed);self.assertEqual(m.transport_exit(m.FULL,q),code);self.assertEqual(m.transport_exit(m.CALIBRATION,q),2)
  with self.assertRaises(ValueError):m.transport_exit(m.FULL,dict(status='INCOMPLETE',numerical_pass=True))
 def test_full_budget_forbidden_in_calibration(self):
  with self.assertRaises(ValueError):m.admit(dict(full_block_budget={},calibration_seconds={str(i):300 for i in range(5)}))
if __name__=='__main__':unittest.main()
