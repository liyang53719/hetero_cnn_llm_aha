"""Tiny source/text controls only; never build or execute model/C++/EDA."""
import importlib.util,re,unittest,hashlib
from pathlib import Path
P=Path(__file__).parent
OLD=P.parent/'qwen2_core_client_verilator_m2_prepare_20261025T2307'
def load(n):
 s=importlib.util.spec_from_file_location(n,P/(n+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load('reference_events');c=load('check_m3_log');g=load('generate_reference')
def fixture():
 lines=[c.READY];cycle=100;previous=None
 for e in r.vector_events(3):
  pair=(e['token'],e['head'])
  cycle+=1 if pair==previous else 100;previous=pair
  lines.append('OBS cycle=%d token=%d head=%d phase=%d lane=%d selected=%d faults=0 scoreWrite=%s scoreIndex=%d scoreData=0 max=%d resultReady=false'%(cycle,e['token'],e['head'],e['phase'],e['lane'],e['selected'],str(e['scoreWrite']).lower(),e.get('scoreIndex',0),e['maxScore']))
 lines.append('VERILATOR_CORE_CASE_PASS case=normal_m3 m=3 cycles=10000 groups=36 qkAcceptedSteps=288 accounting512Steps=2880 results=36 dones=36 scoreWrites=72 targetPrefix=0,1,2 ownerAccepts=1 pvRequests=576 pvReturns=576 requestHoldChecks=4 holdChecksByPort=(group,1),(memory,1),(pv,1),(step,1) memoryAccepted=1728 memoryReturned=1728 outputBytes=18432 checkedMemory=1728 checkedPv=576 checkedVector=1260 numerical_matrix_verified=false')
 lines.append('VERILATOR_CORE_DONE case=normal_m3 completed=true total_rising_edges=10003 reset_clocks=3')
 return ('\n'.join(lines)+'\n').encode()
class Contract(unittest.TestCase):
 def test_good(self):self.assertEqual(c.check(fixture())['phase_counts'],{'1':576,'2':576,'3':36,'4':72})
 def test_mutations(self):
  raw=fixture()
  for a,b in [(b'checkedMemory=1728',b'checkedMemory=1727'),(b'checkedPv=576',b'checkedPv=575'),(b'checkedVector=1260',b'checkedVector=1259'),(b'ownerAccepts=1',b'ownerAccepts=2'),(b'pvRequests=576',b'pvRequests=288'),(b'accounting512Steps=2880',b'accounting512Steps=1824'),(b'memoryReturned=1728',b'memoryReturned=1727'),(b'outputBytes=18432',b'outputBytes=12288'),(b'faults=0',b'faults=1'),(b'resultReady=false',b'resultReady=true'),(b'phase=4 lane=15 selected=1',b'phase=4 lane=15 selected=0'),(b'max=0 ',b'max=4286578688 '),(b'scoreIndex=1',b'scoreIndex=0'),(b'case=normal_m3',b'case=normal_m2'),(b'total_rising_edges=10003',b'total_rising_edges=10002'),(b'reset_clocks=3',b'reset_clocks=2'),(b'targetPrefix=0,1,2',b'targetPrefix=0,2,1')]:
   with self.subTest(a=a):
    self.assertIn(a,raw)
    with self.assertRaises(ValueError):c.check(raw.replace(a,b,1))
 def test_unknown_and_missing(self):
  raw=fixture()
  for changed in (raw+b'%Error assertion failed\n',raw.replace(b'OBS cycle=',b'OBS\tcycle=',1),b'\n'.join(raw.splitlines()[1:])+b'\n',raw+raw,raw.replace(b'scoreWrite=true',b'scoreWrite=false',1)):
   with self.assertRaises(ValueError):c.check(changed)
 def test_zero_port_allowed_scope(self):
  raw=fixture().replace(b'requestHoldChecks=4',b'requestHoldChecks=3').replace(b'(group,1)',b'(group,0)');self.assertEqual(c.check(raw)['uncovered_request_hold_ports'],['group'])
 def test_header_reproducible(self):self.assertEqual((P/'expected_m3.hpp').read_text(),g.render())
 def test_abi_byteidentical(self):self.assertEqual((P/'generated_abi.hpp').read_bytes(),(OLD/'generated_abi.hpp').read_bytes())
 def test_fixed_case_no_parameters(self):
  s=(P/'m3_main.cpp').read_text();self.assertIn('static constexpr U m=3,cap=99997,',s);self.assertIn('need(argc==1,"no runtime case/parameter override")',s);self.assertNotIn('getenv(',s);self.assertNotIn('normal_m2',s)
 def test_unchanged_drive_and_queue(self):
  old=(OLD/'m2_main.cpp').read_text();new=(P/'m3_main.cpp').read_text()
  for begin,end in [('  void settle()', '  void step()'),('    d.io_memory_ready=', '    hold(0,'),('    clock();++cycles;', '\n  void run()'),('    const auto result=','    need(clockEdges==')]:
   self.assertEqual(old[old.index(begin):old.index(end,old.index(begin))],new[new.index(begin):new.index(end,new.index(begin))])
 def test_new_passive_observations(self):
  s=(P/'m3_main.cpp').read_text()
  for token in ['checkedMemory<reference::memory.size()','checkedPv<reference::pv.size()','checkedVector<reference::vector.size()','reference::other_pv_operands_zero(d)','d.observation_maxScore)==e.max','d.io_memory_bits_tag)==e.tag','checkedMemory==reference::memory.size()']:self.assertIn(token,s)
 def test_operand_fields_exact(self):
  s=(P/'expected_m3.hpp').read_text();fields=re.findall(r'd\.io_matrixRequest_bits_([ab]_\d+)==0',s);self.assertEqual(fields,['a_'+str(i) for i in range(1,16)]+['b_'+str(i) for i in range(256)])
 def test_memory_table_full(self):
  s=(P/'expected_m3.hpp').read_text();rows=re.findall(r'\{0x([0-9a-f]+)ULL,0x([0-9a-f]+)ULL,(true|false)\}',s)
  self.assertEqual(len(rows),1728)
  for n,(row,e) in enumerate(zip(rows,r.memory_events(3))):self.assertEqual((int(row[0],16),int(row[1],16),row[2]=='true'),(e['address'],(7<<32)+n,e['write']))
 def test_reference_is_not_driver(self):
  s=(P/'reference_events.py').read_text();self.assertNotIn('observation_',s);self.assertNotIn('m3_main',s);self.assertNotIn('ctypes',s);self.assertNotIn('subprocess',s)
 def test_actual_target_prefix_record(self):
  text=(P/'m3_main.cpp').read_text()
  self.assertIn('if(d.observation_token==2 && d.observation_head==0)',text)
  self.assertIn('targetWrites.size()<3',text)
  self.assertIn('targetWrites.push_back(d.testScoreWrite_bits_index)',text)
  self.assertIn('targetWrites==std::vector<U>({0,1,2})',text)
  self.assertIn("targetWrites[0]<<','<<targetWrites[1]<<','<<targetWrites[2]",text)
 def test_third_probability_exact_integer_distance(self):
  from fractions import Fraction
  a=r.rational_f32_rne(Fraction(1,3));self.assertEqual(a,0x3eaaaaab)
  self.assertEqual(Fraction(1,3)-Fraction(0xaaaaaa,1<<25),Fraction(1,50331648))
  self.assertEqual(Fraction(0xaaaaab,1<<25)-Fraction(1,3),Fraction(1,100663296))
  # BF16 direct neighbors at exponent -2: 170/512 and171/512.
  self.assertLess(Fraction(171,512)-Fraction(1,3),Fraction(1,3)-Fraction(170,512))
  self.assertEqual(r.uniform_bf16(3),0x3eab)
 def test_m3_reference_unchanged(self):self.assertEqual((P/'reference_events.py').read_bytes(),(OLD/'reference_events.py').read_bytes())
if __name__=='__main__':unittest.main()
