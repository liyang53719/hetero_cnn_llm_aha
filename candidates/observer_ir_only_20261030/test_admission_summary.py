import copy,pathlib,tempfile,unittest
from unittest.mock import Mock,patch
import run_ir_only as m
import summarize_ir as s
class Admission(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.caps=dict(max_entries=100000,file_bytes=10,watch_tree_bytes=20,min_free_disk_bytes=0,extra_watch_roots=[str(self.root)]);self.record={};self.sup=Mock();self.sup.execute.return_value={}
 def tearDown(self):self.tmp.cleanup()
 def call(self):return m.admitted_execute(self.sup,[],str(self.root/'new'),str(self.root/'lock'),self.caps,{}, {},{},self.record)
 def test_admitted_records_exact_census(self):
  (self.root/'f').write_text('abc');self.call();self.assertEqual(self.record['entries_observed'],1);self.assertEqual(self.record['bytes_observed'],3);self.assertTrue(self.record['census_complete']);self.assertTrue(self.record['execute_called']);self.assertEqual(s.admission_projection(self.record),self.record)
 def test_entry_rejection_partial_no_execute(self):
  self.caps['max_entries']=8;(self.root/'f').write_text('a')
  with self.assertRaises(ValueError):self.call()
  self.assertEqual(self.record['entries_observed'],1);self.assertEqual(self.record['reason'],'ENTRY_CAP');self.assertFalse(self.record['census_complete']);self.assertFalse(self.record['execute_called']);self.sup.execute.assert_not_called()
 def test_unreadable_partial_no_execute(self):
  def bad(*args,**kw):kw['onerror'](PermissionError('DO_NOT_UPLOAD'));return iter(())
  with patch.object(m.os,'walk',side_effect=bad),self.assertRaises(PermissionError):self.call()
  self.assertEqual(self.record['reason'],'CENSUS_UNREADABLE');self.assertFalse(self.record['census_complete']);self.assertNotIn('DO_NOT_UPLOAD',str(s.admission_projection(self.record)));self.sup.execute.assert_not_called()
 def test_summary_rejects_arbitrary_and_impossible(self):
  self.call()
  for key,value in [('reason','arbitrary error path'),('entry_cap','payload'),('execute_called',False),('census_complete',False)]:
   with self.assertRaises(ValueError):s.admission_projection(dict(self.record,**{key:value}))
 def test_failed_stage_admission_projection(self):
  self.call();record=dict(self.record,status='REJECTED',reason='ENTRY_CAP',census_complete=False,execute_called=False,entries_observed=99993)
  row=dict(name='jdk',native_exit=None,error_count=1,elapsed_seconds=None,observed_peak_rss=None,complete=False,admission=record)
  identity=dict(source_commit='a'*40,launch_commit='b'*40,launch_manifest_blob_sha='c'*40,run_id=1)
  out=s.project(dict(status='FAILED_OR_INCOMPLETE',stages=[row]),identity);self.assertEqual(out['stages'][0]['admission'],record)
 def test_admitted_over_cap_rejected(self):
  self.call()
  with self.assertRaises(ValueError):s.admission_projection(dict(self.record,entries_observed=99993))
 def test_successful_stage_cannot_claim_rejected_admission(self):
  self.call();record=dict(self.record,status='REJECTED',reason='ENTRY_CAP',census_complete=False,execute_called=False,entries_observed=99993)
  identity=dict(source_commit='a'*40,launch_commit='b'*40,launch_manifest_blob_sha='c'*40,run_id=1)
  for fields in (dict(native_exit=0,error_count=0,complete=True),dict(native_exit=1,error_count=1,complete=False),dict(native_exit=None,error_count=0,complete=False)):
   row=dict(name='jdk',elapsed_seconds=None,observed_peak_rss=None,admission=record,**fields)
   with self.assertRaises(ValueError):s.project(dict(status='FAILED_OR_INCOMPLETE',stages=[row]),identity)
if __name__=='__main__':unittest.main()
