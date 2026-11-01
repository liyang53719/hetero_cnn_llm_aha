"""Real cloud admission with synthetic pinned review authority; no filesystem reuse."""
import unittest
import test_stage_coverage as stage
import test_cloud_budget as legacy
class ReferenceBudget(unittest.TestCase):
 def setUp(self):
  self.s=stage.Stage();self.s.setUp();self.addCleanup(self.s.tearDown)
  s=self.s;row=s.h.put('reference_reuse',{'synthetic_only':True})
  s.b['reference_data_reuse']=row;s.doc['reference_data_reuse']=row;s.ap['reference_data_reuse_sha256']=row['sha256'];s.doc['aggregate_tree_cap_bytes']=12037043872;s.doc.update(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES',runtime_reuse_manifest=s.h.put('runtime_reuse',{'synthetic':True}));s.reapprove()
 def test_initial_stub_derives_exact_cap_and_identity(self):
  s=self.s;r=s.cloud.admit(s.b)
  self.assertEqual(r['aggregate_tree_cap_bytes'],12037043872);self.assertEqual(r['reference_data_reuse'],s.b['reference_data_reuse'])
  s.b['aggregate_tree_cap_bytes']=r['aggregate_tree_cap_bytes'];self.assertEqual(s.cloud.admit(s.b),r)
 def test_missing_cap_rejected(self):
  s=self.s;del s.doc['aggregate_tree_cap_bytes'];s.reapprove()
  with self.assertRaises(ValueError):s.cloud.admit(s.b)
 def test_false_and_different_caps_rejected(self):
  s=self.s
  for v in (False,True,12037043873,12081306272,12037043872.0):
   s.doc['aggregate_tree_cap_bytes']=v;s.reapprove()
   with self.subTest(v=v),self.assertRaises(ValueError):s.cloud.admit(s.b)
 def test_binding_cap_mismatch_rejected(self):
  for v in (False,12037043873,12037043872.0):
   self.s.b['aggregate_tree_cap_bytes']=v
   with self.subTest(v=v),self.assertRaises(ValueError):self.s.cloud.admit(self.s.b)
 def test_approval_and_pin_must_match(self):
  s=self.s;s.ap['reference_data_reuse_sha256']='0'*64;s.reapprove()
  with self.assertRaises(ValueError):s.cloud.admit(s.b)
 def test_null_pin_rejected(self):
  self.s.b['reference_data_reuse']=None
  with self.assertRaises(ValueError):self.s.cloud.admit(self.s.b)
 def test_legacy_reuse_or_cap_rejected(self):
  h=legacy.Budget();h.setUp();self.addCleanup(h.tearDown)
  h.b['reference_data_reuse']=h.put('reference',{})
  with self.assertRaisesRegex(ValueError,'requires stage candidate'):self.s.cloud.admit(h.b)
  del h.b['reference_data_reuse'];h.b['aggregate_tree_cap_bytes']=12037043872
  with self.assertRaisesRegex(ValueError,'requires reference'):self.s.cloud.admit(h.b)
 def test_no_reference_cap_not_generic_optional(self):
  s=self.s;del s.b['reference_data_reuse'];del s.doc['reference_data_reuse'];del s.ap['reference_data_reuse_sha256'];s.reapprove()
  with self.assertRaisesRegex(ValueError,'exact cloud lifecycle'):s.cloud.admit(s.b)
 def test_reference_fresh_or_download_rejected(self):
  s=self.s;s.doc.update(runtime_mode='FRESH_ORIGINAL_RUNTIME_INSTALL',archive_mode='DOWNLOAD_ORIGINAL_ARCHIVES',runtime_reuse_manifest=None);s.reapprove()
  with self.assertRaisesRegex(ValueError,'reference reuse requires'):s.cloud.admit(s.b)
  s.doc.update(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',runtime_reuse_manifest=s.h.put('runtime_reuse',{'synthetic':True}));s.reapprove()
  with self.assertRaisesRegex(ValueError,'reference reuse requires'):s.cloud.admit(s.b)
 def test_no_reference_stage_fresh_still_accepted(self):
  s=stage.Stage();s.setUp();self.addCleanup(s.tearDown)
  self.assertEqual(s.cloud.admit(s.b)['runtime_mode'],'FRESH_ORIGINAL_RUNTIME_INSTALL')
if __name__=='__main__':unittest.main()
