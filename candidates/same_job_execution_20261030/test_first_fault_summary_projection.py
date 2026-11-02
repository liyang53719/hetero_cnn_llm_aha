"""Real finite parser plus real summary scanner; synthetic text, no DUT authority."""
import ast,hashlib,json,pathlib,tempfile,types,unittest
W=pathlib.Path(__file__).resolve().parent;D=W/'source'if(W/'source/summarize_cloud_execution.py').is_file()else W
m=types.ModuleType('summary_test');m.__file__=str(D/'summarize_cloud_execution.py');exec(compile((D/'summarize_cloud_execution.py').read_bytes(),m.__file__,'exec'),m.__dict__)
parser=m.load('parser',D/'numeric/first_fault_records.py');schema=parser.schema();SH=parser.SCHEMA_SHA256
class Test(unittest.TestCase):
 def call(self,text):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'profile0.log';p.write_text(text)
   b={'pins':{str(f):m.sha(f)for f in (D/'numeric/first_fault_records.py',D/'numeric/FIXED_NONHIER_SCHEMA.json')}}
   r=m.first_fault_snapshot(p,b);self.assertEqual(r['log_sha256'],hashlib.sha256(text.encode()).hexdigest());self.assertEqual(r['log_bytes'],len(text.encode()));return r
 def records(self):
  z=','.join(['0']*114);c=['0']*114;idx=next(i for i,x in enumerate(schema['signals'])if x['module']=='HostBlockTopV4'and x['sv_var']=='io_resetRequired');c[idx]='1'
  return f'HOST_FIRST_FAULT_V1 schema_sha256={SH} fields=114 extra_eval=0 extra_clock=0\nHOST_FIRST_FAULT_SLOT_V1 slot=previous_healthy valid=0 cycle=0 active_cycle=0 completions=0 values={z}\nHOST_FIRST_FAULT_SLOT_V1 slot=current_fault valid=1 cycle=10 active_cycle=8 completions=1 values={",".join(c)}\n'
 def test_present_after_full_scan(self):
  r=self.call('unrelated_before\n'+self.records()+'unrelated_after\n');self.assertEqual(r['status'],'PRESENT_VALID');self.assertIsNone(r['previous_healthy']);self.assertFalse(r['fault_cause_established']);self.assertTrue(r['fault_observed'])
 def test_absent_not_pass(self):
  r=self.call('ORIGINAL_HOST_REPLAY_FAIL: bounded Host did not finish\n');self.assertEqual(r['status'],'ABSENT');self.assertFalse(r['numerical_pass'])
 def test_malformed_keeps_bounded_status(self):
  r=self.call(self.records()+'HOST_FIRST_FAULT_INJECT never_export_this_payload\n');self.assertEqual(r['status'],'MALFORMED');self.assertNotIn('never_export',json.dumps(r))
 def test_excess_records_are_not_absent(self):self.assertEqual(self.call(self.records()*20)['status'],'MALFORMED')
 def test_line_cap_rejects(self):
  with self.assertRaises(ValueError):self.call('a'*8193+'\n')
if __name__=='__main__':unittest.main()
