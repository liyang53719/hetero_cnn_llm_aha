import importlib.util,json,os,pathlib,tempfile,unittest,hashlib,shutil
P=pathlib.Path
D=P(__file__).resolve().parent
R=P(os.environ.get('TERMINAL_TEST_REPO',str(D.parents[2])))
SCHEMA=R/'candidates/model_candidate_build_20261101/TERMINAL_FINITE_RECORD_SCHEMA.json'
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('terminal_test',D/'terminal_finite_records.py')
def record(**kw):
 s=json.loads(SCHEMA.read_text());r={k:0 for k in s['record_proposed_fields']};r.update(schema_sha256=m.SCHEMA_SHA256,mapping='NONE',first_nonfinite_kind='NONE',first_nonfinite_region='NONE',first_nonfinite_index=4096);r.update(kw)
 return m.PREFIX+' '+' '.join(k+'='+str(r[k])for k in s['record_proposed_fields'])+'\n'
def good(**kw):
 r=dict(sample_valid=1,accepted_samples=1,cycle=10,active_cycle=8,pc=1,completions=1,ng=160,context=0,result_last=1,mapping='SUPPORTED',words=4096,finite=4096,effective_words=4096,fault_pc=1,fault_at_target_pc=1);r.update(kw);return record(**r)
class Tests(unittest.TestCase):
 def parse(self,lines):return m.parse_records(lines,SCHEMA)
 def test_empty_and_absent(self):
  self.assertEqual(self.parse([])['status'],'ABSENT');self.assertEqual(self.parse([record(fault_pc=2)])['status'],'PRESENT_VALID')
 def test_finite_and_effective_nonfinite(self):
  for line in (good(),good(finite=4095,nan=1,nonfinite_effective=1,first_nonfinite_index=3,first_nonfinite_kind='NAN',first_nonfinite_region='EFFECTIVE')):
   r=self.parse([line]);self.assertEqual(r['status'],'PRESENT_VALID');self.assertIs(r['numerical_pass'],False);self.assertIs(r['fault_cause_established'],False)
 def test_unknown_and_later_fault(self):
  r=self.parse([good(ng=161,mapping='UNSUPPORTED_MAPPING',effective_words=0,unknown_region_words=4096,finite=4095,negative_infinity=1,nonfinite_unknown_region=1,first_nonfinite_index=9,first_nonfinite_kind='NEG_INF',first_nonfinite_region='UNKNOWN',fault_pc=2,fault_at_target_pc=0)])
  self.assertEqual(r['sample']['fault_pc'],2);self.assertEqual(r['sample']['pc'],1)
 def test_max_unsigned_samples_no_static_cap(self):self.assertEqual(self.parse([good(accepted_samples=(1<<64)-1)])['sample']['accepted_samples'],(1<<64)-1)
 def test_bad_fields_and_partitions(self):
  cases=[dict(words=4095),dict(finite=4095),dict(effective_words=4095),dict(mapping='UNSUPPORTED_MAPPING'),dict(first_nonfinite_index=0),dict(pc=2),dict(active_cycle=11),dict(sample_valid=2),dict(context=8),dict(ng=65536),dict(fault_at_target_pc=0),dict(finite=4095,nan=1,nonfinite_padding=1,first_nonfinite_index=0,first_nonfinite_kind='NAN',first_nonfinite_region='PADDING'),dict(finite=4094,nan=2,nonfinite_effective=2,first_nonfinite_index=4095,first_nonfinite_kind='NAN',first_nonfinite_region='EFFECTIVE')]
  for kw in cases:
   with self.subTest(kw=kw),self.assertRaises(ValueError):self.parse([good(**kw)])
 def test_bad_syntax(self):
  line=good()
  for lines in ([line,line],[line.replace('words=4096','words=04096')],[line.replace('words=4096','words=-1')],[line.replace('words=4096','words=18446744073709551616')],[line.replace(' finite=', ' x=')],[line.replace('\n','\r\n')],[line+'secret'],['HOST_TERMINAL_FINITE_BOGUS\n'],[line+'x'*1024]):
   with self.subTest(lines=str(lines)[:70]),self.assertRaises(ValueError):self.parse(lines)
 def test_empty_sample_not_arbitrary(self):
  for kw in (dict(words=4096),dict(accepted_samples=1),dict(cycle=1),dict(mapping='SUPPORTED')):
   with self.assertRaises(ValueError):self.parse([record(**kw)])
 def test_original_parser_ignores_distinct_prefix(self):
  old=load('old_records',R/'candidates/same_job_execution_20261030/numeric/first_fault_records.py');s=old.schema();idx=next(i for i,r in enumerate(s['signals'])if r['module']=='HostBlockTopV4'and r['sv_var']=='io_resetRequired');vals=[0]*114;cur=vals.copy();cur[idx]=1
  rows=[old.HEADER+'\n','HOST_FIRST_FAULT_SLOT_V1 slot=previous_healthy valid=1 cycle=10 active_cycle=8 completions=1 values='+','.join(map(str,vals))+'\n','HOST_FIRST_FAULT_SLOT_V1 slot=current_fault valid=1 cycle=11 active_cycle=9 completions=1 values='+','.join(map(str,cur))+'\n']
  self.assertEqual(old.parse_records(rows),old.parse_records(rows+[good()]));self.assertEqual(old.parse_records(rows)['status'],'PRESENT_VALID')
if __name__=='__main__':unittest.main()
