"""Synthetic operator-input tests; not host, ELF, resource or numerical qualification."""
import copy,hashlib,importlib.util,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('tested_cloud_budget',D/'cloud_budget.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Budget(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.t.name)
  self.host=self.put('host',dict(schema='CLOUD_EXECUTOR_HOST_OBSERVATION_V1',boot_id='b',architecture='x86_64',python_version=[3,12],avx512f=True,physical_memtotal_bytes=10<<30,observed_memavailable_bytes=8<<30,observed_monotonic=1));ev=self.put('review',{'synthetic':True})
  self.identity=dict(boot_id='b',started_monotonic=2,source_commit='a'*40,execution_id='b'*36,host_identity_sha256=self.host['sha256'])
  self.doc=dict(runtime_mode='FRESH_ORIGINAL_RUNTIME_INSTALL',archive_mode='DOWNLOAD_ORIGINAL_ARCHIVES',runtime_reuse_manifest=None,stage_resources={k:dict(rss_bytes=2684354560,as_bytes=2684354560)for k in ('install','reference')},resource_scope='CURRENT_HOST_BOUNDED_RESOURCE_DIAGNOSTIC',consumer_address_space_bytes=512<<20,reserved_other_owner_bytes=5<<30,schema='FIVE_M128_CLOUD_LIFECYCLE_BUDGET_V1',ready=True,source_commit='a'*40,host_identity=self.host,artifact_manifest_sha256='c'*64,basis=dict(resource_audit=ev,independent_review=ev),job_budget_seconds=12300,budgets=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,parent=600,calibration_seconds={str(i):300 for i in range(5)}),dut_rss_bytes=2684354560,dut_address_space_bytes=2684354560,numeric_reserved_increment_bytes=512<<20,execution_mode='BOUNDED_CALIBRATION',full_block_budget=None)
  self.budget=self.put('budget',self.doc)
  self.ap=dict(schema='OPERATOR_REVIEWED_CLOUD_INVOCATION_V1',approved=True,authority='USER_AUTHORIZED_OPERATOR_REVIEW',purpose='BOUNDED_CALIBRATION',source_commit='a'*40,budget_sha256=self.budget['sha256'],artifact_manifest_sha256='c'*64,execution_id='b'*36,host_identity_sha256=self.host['sha256'],review_evidence=ev)
  self.b=dict(execution_context='CLOUD_EXECUTOR_V1',identity=self.identity,artifact_manifest={'sha256':'c'*64},cloud_budget=self.budget,execution_approval=self.put('approval',self.ap))
 def tearDown(self):self.t.cleanup()
 def put(self,n,v):
  p=self.d/n;p.write_text(json.dumps(v));return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 def reapprove(self):
  self.b['cloud_budget']=self.put('budget',self.doc);self.ap['budget_sha256']=self.b['cloud_budget']['sha256'];self.b['execution_approval']=self.put('approval',self.ap)
 def test_readonly_reuse_manifest_must_be_bound_by_approved_budget(self):
  self.doc.update(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES',runtime_reuse_manifest=self.put('reuse',{'synthetic_inventory_not_qualification':True}));self.reapprove()
  actual=m.admit(self.b);self.assertEqual(actual['runtime_reuse_manifest'],self.doc['runtime_reuse_manifest'])
  self.doc['runtime_reuse_manifest']['sha256']='0'*64;self.reapprove()
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_reuse_cannot_silently_download_original_archives(self):
  self.doc.update(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',runtime_reuse_manifest=self.put('reuse',{}));self.reapprove()
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_fresh_install_cannot_carry_hidden_reuse_input(self):
  self.doc['runtime_reuse_manifest']=self.put('reuse',{});self.reapprove()
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_explicit_synthetic_input(self):self.assertEqual(m.admit(self.b)['job_budget_seconds'],12300)
 def test_no_approval(self):
  del self.b['execution_approval']
  with self.assertRaisesRegex(ValueError,'OPERATOR_APPROVED'):m.admit(self.b)
 def test_independent_approval_digest(self):
  self.b['execution_approval']['sha256']='0'*64
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_artifact_identity_mismatch(self):
  self.b['artifact_manifest']['sha256']='0'*64
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_repin_budget_not_authorized(self):
  self.doc['job_budget_seconds']=999999;self.b['cloud_budget']=self.put('budget',self.doc)
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_wrong_execution_uuid(self):
  self.b['identity']['execution_id']='different'
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_wrong_host(self):
  self.b['identity']['host_identity_sha256']='0'*64
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_wrong_mode_approval(self):
  self.ap['purpose']='FULL_BLOCK_ACCEPTANCE';self.b['execution_approval']=self.put('approval',self.ap)
  with self.assertRaises(ValueError):m.admit(self.b)
 def test_bool_deadline_rejected_even_reapproved(self):
  self.doc['job_budget_seconds']=True;self.b['cloud_budget']=self.put('budget',self.doc);self.ap['budget_sha256']=self.b['cloud_budget']['sha256'];self.b['execution_approval']=self.put('approval',self.ap)
  with self.assertRaises(ValueError):m.admit(self.b)
if __name__=='__main__':unittest.main()
