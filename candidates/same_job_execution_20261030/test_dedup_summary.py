import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
P=pathlib.Path;D=P(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('summary',D/'summarize_same_job.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.work=P(self.tmp.name);self.path=self.work/'PACK_DEDUPLICATION.json'
 def tearDown(self):self.tmp.cleanup()
 def fixture(self,status='COMPLETE'):
  ps='BOTH_PATHS_RETAINED_SAME_INODE'if status=='COMPLETE'else'PENDING'
  return dict(schema='EXACT_TWO_COPY_DEDUPLICATION_V1',scope='LIFECYCLE_ONLY_NOT_NUMERICAL_PASS',status=status,logical_saved_bytes=123 if status=='COMPLETE'else 0,build_result_sha256='a'*64,physical_space_saved='NOT_MEASURED',pairs=[dict(role=role,status=ps,source='/PRIVATE/secret',target='/PRIVATE/target',owner_uid=123)for role in ('sv','binary')],writer_census={'secret':'/PRIVATE/maps'},exception='/PRIVATE/error')
 def put(self,r):self.path.write_text(json.dumps(r))
 def check(self,r):self.put(r);return m.pack_deduplication(self.work)
 def test_absent_is_not_observed(self):
  self.assertEqual(m.pack_deduplication(self.work)['status'],'NOT_OBSERVED')
 def test_complete_safe_projection(self):
  r=self.check(self.fixture());self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['logical_saved_bytes'],123);self.assertEqual(r['physical_space_saved'],'NOT_MEASURED');self.assertNotIn('PRIVATE',json.dumps(r));self.assertNotIn('owner_uid',json.dumps(r));self.assertEqual(len(r['receipt_sha256']),64)
 def test_all_noncomplete_states_retained(self):
  for status in ('PREPARED','NO_OP_MODE_MISMATCH','VERIFIED_BACKUPS_RETAINED','RECOVERY_REQUIRED','ROLLED_BACK'):
   with self.subTest(status=status):self.assertEqual(self.check(self.fixture(status))['status'],status)
 def test_unknown_state_no_exception_text(self):
  r=self.fixture();r['status']='/PRIVATE/exception';out=self.check(r);self.assertEqual(out['status'],'INVALID_FIELDS');self.assertNotIn('PRIVATE',json.dumps(out))
 def test_bool_negative_huge_or_excess_bytes(self):
  for v in (True,-1,362153112,10**400):
   r=self.fixture();r['logical_saved_bytes']=v
   with self.subTest(value=str(v)[:20]):self.assertEqual(self.check(r)['status'],'INVALID_FIELDS')
 def test_noncomplete_cannot_claim_savings(self):
  r=self.fixture('ROLLED_BACK');r['logical_saved_bytes']=1;self.assertEqual(self.check(r)['status'],'INVALID_FIELDS')
 def test_pair_roles_and_states_bounded(self):
  for value in ([],[{'role':'sv','status':'PENDING'}]*2,[{'role':'sv','status':'/PRIVATE/err'},{'role':'binary','status':'PENDING'}]):
   r=self.fixture();r['pairs']=value;self.assertEqual(self.check(r)['status'],'INVALID_FIELDS')
 def test_complete_requires_pair_completion(self):
  r=self.fixture();r['pairs'][1]['status']='PENDING';self.assertEqual(self.check(r)['status'],'INVALID_FIELDS')
 def test_bad_build_hash(self):
  r=self.fixture();r['build_result_sha256']='/PRIVATE';self.assertEqual(self.check(r)['status'],'INVALID_FIELDS')
 def test_claimed_physical_saving_rejected(self):
  r=self.fixture();r['physical_space_saved']=123;self.assertEqual(self.check(r)['status'],'INVALID_FIELDS')
 def test_invalid_json_and_schema(self):
  self.path.write_text('{');self.assertEqual(m.pack_deduplication(self.work)['status'],'INVALID_FIELDS')
  self.assertEqual(self.check([])['status'],'INVALID_FIELDS');r=self.fixture();r['schema']='other';self.assertEqual(self.check(r)['status'],'INVALID_FIELDS')
 def test_oversize_and_symlink(self):
  self.path.write_bytes(b'x'*65537);self.assertEqual(m.pack_deduplication(self.work)['status'],'INVALID_FIELDS');self.path.unlink();target=self.work/'target';target.write_text(json.dumps(self.fixture()));self.path.symlink_to(target);self.assertEqual(m.pack_deduplication(self.work)['status'],'INVALID_FIELDS')
 def test_failure_projection_does_not_drop_stage(self):
  self.put(self.fixture('RECOVERY_REQUIRED'));stage=self.work/'runs/archives';stage.mkdir(parents=True);(stage/'RESULT.json').write_text(json.dumps(dict(native_exit=0,errors=[],cleanup_proof=None,log_capture=None)))
  with patch.object(m,'stage_resources',return_value={'fixture':True}):out=m.summarize(self.work,{})
  self.assertEqual(out['pack_deduplication']['status'],'RECOVERY_REQUIRED');self.assertEqual(out['stages'][0]['phase'],'archive');self.assertFalse(out['numeric_pass'])
 def test_size_fallback_preserves_dedup_and_snapshots(self):
  self.put(self.fixture('ROLLED_BACK'));out=m.summarize(self.work,{});out['installation_resource_snapshots']=[{'status':'UNAVAILABLE'}];out['build']={'stages':[dict(stage='host',diagnostics='x'*70000)]};raw=m.encode(out);decoded=json.loads(raw);self.assertLessEqual(len(raw.encode()),65536);self.assertEqual(decoded['pack_deduplication']['status'],'ROLLED_BACK');self.assertEqual(decoded['installation_resource_snapshots'],[{'status':'UNAVAILABLE'}]);self.assertFalse(decoded['numeric_pass'])
if __name__=='__main__':unittest.main()
