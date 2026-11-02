import importlib.util,unittest
from unittest.mock import patch
from pathlib import Path
s=importlib.util.spec_from_file_location('p',Path(__file__).with_name('first_fault_records.py'));p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
def sample(slot='previous_healthy',valid=1,values=None,cycle=3):
 if values is None:
  values=[0]*114
  if slot=='current_fault':values[next(i for i,r in enumerate(p.schema()['signals'])if r['module']=='HostBlockTopV4'and r['sv_var']=='io_resetRequired')]=1
 return f'HOST_FIRST_FAULT_SLOT_V1 slot={slot} valid={valid} cycle={cycle} active_cycle=0 completions=0 values='+','.join(map(str,values if values is not None else[0]*114))+'\n'
def rows():return[p.HEADER+'\n',sample(),sample('current_fault')]
class Test(unittest.TestCase):
 def test_positive(self):
  r=p.parse_records(rows());self.assertEqual(r['record_count'],3);self.assertEqual(r['status'],'PRESENT_VALID');self.assertTrue(r['fault_observed']);self.assertFalse(r['fault_cause_established']);self.assertIsNotNone(r['current_fault'])
 def test_absent(self):self.assertEqual(p.parse_records(iter(['other\n']*1000))['status'],'ABSENT')
 def test_nohistory(self):
  x=rows();x[1]=sample(valid=0,cycle=0);self.assertIsNone(p.parse_records(x)['samples']['previous_healthy'])
 def test_bad(self):
  cases=[];r=rows()
  cases += [r[:1],r[:2],r+r,r[1:], [r[0],r[2],r[1]], [r[0]+'x',*r[1:]]]
  for bad in ['-1','01','1.0','18446744073709551616']:
   cases.append([r[0],sample(values=[bad]+[0]*113),r[2]])
  cases += [[r[0],sample(values=[0]*113),r[2]],[r[0],sample(values=[0]*115),r[2]],[r[0],sample(valid=0),r[2]],[r[0],r[1],sample('current_fault',0,cycle=0)],['HOST_FIRST_FAULT_UNKNOWN\n'],[r[0],r[1],r[2].replace('\n','\r\n')],['HOST_FIRST_FAULT'+('x'*8192)]]
  for x in cases:
   with self.subTest(x=str(x)[:90]):
    with self.assertRaises(ValueError):p.parse_records(x)
 def test_each_width(self):
  for i,r in enumerate(p.schema()['signals']):
   vals=[0]*114;vals[i]=1<<r['width_bits']
   with self.subTest(i=i),self.assertRaisesRegex(ValueError,'signal width'):p.parse_records([p.HEADER,sample(values=vals),sample('current_fault')])
 def test_schema_tamper(self):
  with patch.object(p.Path,'read_bytes',return_value=b'{}'),self.assertRaisesRegex(ValueError,'schema pin'):p.parse_records([])
 def test_unsigned_max(self):
  v=[(1<<r['width_bits'])-1 for r in p.schema()['signals']]
  self.assertEqual(p.parse_records([p.HEADER,sample(valid=0,cycle=0),sample('current_fault',values=v,cycle=(1<<64)-1)])['record_count'],3)
 def test_semantic_mismatches(self):
  idx=next(i for i,r in enumerate(p.schema()['signals'])if r['module']=='HostBlockTopV4'and r['sv_var']=='io_resetRequired')
  badprev=[0]*114;badprev[idx]=1
  cases=[[p.HEADER,sample(values=badprev),sample('current_fault')],[p.HEADER,sample(),sample('current_fault',values=[0]*114)],[p.HEADER,sample(cycle=4),sample('current_fault',cycle=3)],[p.HEADER,sample(),sample('current_fault').replace('active_cycle=0','active_cycle=4')],[p.HEADER,sample().replace('completions=0','completions=1'),sample('current_fault')],[p.HEADER,sample().replace('active_cycle=0','active_cycle=1'),sample('current_fault')]]
  for lines in cases:
   with self.subTest(lines=lines),self.assertRaises(ValueError):p.parse_records(lines)
 def test_interspersed(self):self.assertEqual(p.parse_records([rows()[0],'other\n',*rows()[1:]])['record_count'],3)
if __name__=='__main__':unittest.main()
