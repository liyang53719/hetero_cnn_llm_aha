"""Tiny source/text controls only; never build or execute model/C++/EDA."""
import importlib.util,re,unittest,hashlib
from pathlib import Path
P=Path(__file__).parent
OLD=P.parent/'qwen2_core_client_verilator_m1_prepare_20261025T2044'
def load(n):
 s=importlib.util.spec_from_file_location(n,P/(n+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load('reference_events');c=load('check_m2_log');g=load('generate_reference')
def fixture():
 lines=[c.READY];cycle=100;previous=None
 for e in r.vector_events(2):
  pair=(e['token'],e['head'])
  cycle+=1 if pair==previous else 100;previous=pair
  lines.append('OBS cycle=%d token=%d head=%d phase=%d lane=%d selected=%d faults=0 scoreWrite=%s scoreIndex=%d scoreData=0 max=%d resultReady=false'%(cycle,e['token'],e['head'],e['phase'],e['lane'],e['selected'],str(e['scoreWrite']).lower(),e.get('scoreIndex',0),e['maxScore']))
 lines.append('VERILATOR_CORE_CASE_PASS case=normal_m2 m=2 cycles=10000 groups=24 qkAcceptedSteps=192 accounting512Steps=1824 results=24 dones=24 scoreWrites=36 targetPrefix= ownerAccepts=1 pvRequests=288 pvReturns=288 requestHoldChecks=4 holdChecksByPort=(group,1),(memory,1),(pv,1),(step,1) memoryAccepted=960 memoryReturned=960 outputBytes=12288 checkedMemory=960 checkedPv=288 checkedVector=828 numerical_matrix_verified=false')
 lines.append('VERILATOR_CORE_DONE case=normal_m2 completed=true total_rising_edges=10003 reset_clocks=3')
 return ('\n'.join(lines)+'\n').encode()
class Contract(unittest.TestCase):
 def test_good(self):self.assertEqual(c.check(fixture())['phase_counts'],{'1':384,'2':384,'3':24,'4':36})
 def test_mutations(self):
  raw=fixture()
  for a,b in [(b'checkedMemory=960',b'checkedMemory=959'),(b'checkedPv=288',b'checkedPv=289'),(b'checkedVector=828',b'checkedVector=827'),(b'ownerAccepts=1',b'ownerAccepts=2'),(b'pvRequests=288',b'pvRequests=192'),(b'accounting512Steps=1824',b'accounting512Steps=1728'),(b'memoryReturned=960',b'memoryReturned=959'),(b'outputBytes=12288',b'outputBytes=6144'),(b'faults=0',b'faults=1'),(b'resultReady=false',b'resultReady=true'),(b'phase=4 lane=15 selected=1',b'phase=4 lane=15 selected=0'),(b'max=0 ',b'max=4286578688 '),(b'scoreIndex=1',b'scoreIndex=0'),(b'case=normal_m2',b'case=normal_m3'),(b'total_rising_edges=10003',b'total_rising_edges=10002'),(b'reset_clocks=3',b'reset_clocks=2')]:
   with self.subTest(a=a):
    self.assertIn(a,raw)
    with self.assertRaises(ValueError):c.check(raw.replace(a,b,1))
 def test_unknown_and_missing(self):
  raw=fixture()
  for changed in (raw+b'%Error assertion failed\n',raw.replace(b'OBS cycle=',b'OBS\tcycle=',1),b'\n'.join(raw.splitlines()[1:])+b'\n',raw+raw,raw.replace(b'scoreWrite=true',b'scoreWrite=false',1)):
   with self.assertRaises(ValueError):c.check(changed)
 def test_zero_port_allowed_scope(self):
  raw=fixture().replace(b'requestHoldChecks=4',b'requestHoldChecks=3').replace(b'(group,1)',b'(group,0)');self.assertEqual(c.check(raw)['uncovered_request_hold_ports'],['group'])
 def test_header_reproducible(self):self.assertEqual((P/'expected_m2.hpp').read_text(),g.render())
 def test_abi_byteidentical(self):self.assertEqual((P/'generated_abi.hpp').read_bytes(),(OLD/'generated_abi.hpp').read_bytes())
 def test_fixed_case_no_parameters(self):
  s=(P/'m2_main.cpp').read_text();self.assertIn('static constexpr U m=2,cap=99997,',s);self.assertIn('need(argc==1,"no runtime case/parameter override")',s);self.assertNotIn('getenv(',s);self.assertNotIn('normal_m3',s)
 def test_unchanged_drive_and_queue(self):
  old=(OLD/'m1_main.cpp').read_text();new=(P/'m2_main.cpp').read_text()
  for begin,end in [('  void settle()', '  void step()'),('    d.io_memory_ready=', '    hold(0,'),('    clock();++cycles;', '\n  void run()'),('    const auto result=','    need(clockEdges==')]:
   self.assertEqual(old[old.index(begin):old.index(end,old.index(begin))],new[new.index(begin):new.index(end,new.index(begin))])
 def test_new_passive_observations(self):
  s=(P/'m2_main.cpp').read_text()
  for token in ['checkedMemory<reference::memory.size()','checkedPv<reference::pv.size()','checkedVector<reference::vector.size()','reference::other_pv_operands_zero(d)','d.observation_maxScore)==e.max','d.io_memory_bits_tag)==e.tag','checkedMemory==reference::memory.size()']:self.assertIn(token,s)
 def test_operand_fields_exact(self):
  s=(P/'expected_m2.hpp').read_text();fields=re.findall(r'd\.io_matrixRequest_bits_([ab]_\d+)==0',s);self.assertEqual(fields,['a_'+str(i) for i in range(1,16)]+['b_'+str(i) for i in range(256)])
 def test_memory_table_full(self):
  s=(P/'expected_m2.hpp').read_text();rows=re.findall(r'\{0x([0-9a-f]+)ULL,0x([0-9a-f]+)ULL,(true|false)\}',s)
  self.assertEqual(len(rows),960)
  for n,(row,e) in enumerate(zip(rows,r.memory_events(2))):self.assertEqual((int(row[0],16),int(row[1],16),row[2]=='true'),(e['address'],(7<<32)+n,e['write']))
 def test_reference_is_not_driver(self):
  s=(P/'reference_events.py').read_text();self.assertNotIn('observation_',s);self.assertNotIn('m2_main',s);self.assertNotIn('ctypes',s);self.assertNotIn('subprocess',s)
if __name__=='__main__':unittest.main()
