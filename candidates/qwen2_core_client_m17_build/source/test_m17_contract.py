"""Bounded stdlib synthetic/source controls. No compiler, native ELF or DUT."""
import importlib.util,re,unittest
from pathlib import Path
from fractions import Fraction
P=Path(__file__).resolve().parent

def load(name):
 sp=importlib.util.spec_from_file_location(name,P/(name+'.py'));m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
r=load('reference_events');c=load('check_m17_log');g=load('generate_reference')

def driver_descriptor(ordinal):
 if type(ordinal) is not int or not 0<=ordinal<216:raise ValueError('ordinal')
 if ordinal<192:return ordinal//12,ordinal%12,0,ordinal//12+1
 t=ordinal-192;return 16,t//2,(t%2)*16,1 if t%2 else 16

def exact_binary(bits,expbits,fracbits,bias):
 exponent=(bits>>fracbits)&((1<<expbits)-1);fraction=bits&((1<<fracbits)-1)
 if exponent==0:return Fraction(fraction,1<<fracbits)*Fraction(2)**(1-bias)
 if exponent==(1<<expbits)-1:raise ValueError('nonfinite')
 return (1+Fraction(fraction,1<<fracbits))*Fraction(2)**(exponent-bias)

def fixture():
 lines=[c.READY];cycle=100;last=None
 for e in r.vector_events():
  key=(e['token'],e['head'],e['keyBase']);cycle+=1 if key==last else 100;last=key
  lines.append('OBS cycle=%d token=%d head=%d keyBase=%d phase=%d lane=%d selected=%d faults=0 scoreWrite=%s scoreIndex=%d scoreData=0 max=%d resultReady=false'%(cycle,e['token'],e['head'],e['keyBase'],e['phase'],e['lane'],e['selected'],str(e['scoreWrite']).lower(),e['scoreIndex'],e['maxScore']))
 lines.append('VERILATOR_CORE_CASE_PASS case=normal_m17 m=17 cycles=200000 groups=216 qkAcceptedSteps=1728 accounting512Steps=28512 results=216 dones=216 scoreWrites=1836 targetPrefix='+','.join(map(str,range(17)))+' ownerAccepts=1 pvRequests=14688 pvReturns=14688 requestHoldChecks=4 holdChecksByPort=(group,1),(memory,1),(pv,1),(step,1) memoryAccepted=32640 memoryReturned=32640 outputBytes=104448 checkedGroups=216 checkedMemory=32640 checkedPv=14688 checkedVector=8964 numerical_matrix_verified=false')
 lines.append('VERILATOR_CORE_DONE case=normal_m17 completed=true total_rising_edges=200003 reset_clocks=3')
 return ('\n'.join(lines)+'\n').encode()

class Reference(unittest.TestCase):
 def test_counts(self):
  self.assertEqual((len(list(r.group_events())),len(list(r.memory_events())),len(list(r.pv_events())),len(list(r.vector_events()))),(216,32640,14688,8964))
  self.assertEqual(r.counts()['accounting512Steps'],8*1728+14688)
 def test_driver_reference_independent_full_ordinal(self):
  for n,e in enumerate(r.group_events()):self.assertEqual(driver_descriptor(n),(e['token'],e['head'],e['base'],e['count']))
  for x in (-1,216,217,2**64-1):
   with self.assertRaises(ValueError):driver_descriptor(x)
  self.assertEqual([driver_descriptor(x) for x in (191,192,193,214,215)],[(15,11,0,16),(16,0,0,16),(16,0,16,1),(16,11,0,16),(16,11,16,1)])
 def test_memory_ordinal_closed_form(self):
  # Independent decomposition of accepted ordinal, not chunk iterator reuse.
  offset=0
  rows=list(r.memory_events())
  for n,e in enumerate(rows):
   t=0;left=n
   while left>=12*(16+16*(t+1)):left-=12*(16+16*(t+1));t+=1
   h,inside=divmod(left,16+16*(t+1));size=t+1
   if inside<8:kind='Q';address=0x100000+6144*t+512*h+64*inside;write=False
   elif inside<8+8*size:
    kpos=inside-8
    if t<16:depth,key=divmod(kpos,size)
    elif kpos<128:depth,key=divmod(kpos,16)
    else:depth,key=kpos-128,16
    kind='K';address=0x200000+1024*key+512*(h//6)+64*depth;write=False
   else:
    col,key=divmod(inside-8-8*size,size+1)
    if key==size:kind='OUTPUT';address=0x400000+6144*t+512*h+64*col;write=True
    else:kind='V';address=0x300000+1024*key+512*(h//6)+64*col;write=False
   self.assertEqual((e['kind'],e['address'],e['write']),(kind,address,write),n)
 def test_pv_ordinal(self):
  for n,e in enumerate(r.pv_events()):
   t=0;left=n
   while left>=96*(t+1):left-=96*(t+1);t+=1
   h,inside=divmod(left,8*(t+1));col,key=divmod(inside,t+1)
   self.assertEqual((e['token'],e['head'],e['outputChunk'],e['key'],e['clear'],e['last']),(t,h,col,key,key==0,key==t),n)
 def test_rne_all17_independent_nearest(self):
  for n in range(1,18):
   x=Fraction(1,n);f=r.rational_f32_rne(x);b=r.uniform_bf16(n)
   self.assertEqual(f,min((f-1,f,f+1),key=lambda k:(abs(exact_binary(k,8,23,127)-x),k&1)))
   candidates=[(exp<<7)|mant for exp in range(121,128) for mant in range(128)]
   self.assertEqual(b,min(candidates,key=lambda k:(abs(exact_binary(k,8,7,127)-x),k&1)))
  self.assertEqual(r.uniform_bf16(17),0x3d71)
 def test_vector_second_chunk(self):
  es=[x for x in r.vector_events() if x['token']==16 and x['head']==0]
  self.assertEqual(len(es),83);self.assertEqual([x['scoreIndex'] for x in es if x['scoreWrite']],list(range(17)))
  tail=es[49:];self.assertEqual(len(tail),34)
  self.assertTrue(all(x['keyBase']==16 and x['maxScore']==0 and x['selected']==0 for x in tail));self.assertEqual(tail[-1]['scoreIndex'],16)
 def test_full_padding(self):
  total_zero=0
  for n in range(216):
   t,h,b,count=driver_descriptor(n);zeros=0
   for row in range(16):
    for col in range(256):
     word=0x7fc00000 if col//16>=count or col%16!=row else 0
     self.assertEqual(word==0,(col//16<count and col%16==row));zeros+=word==0
   self.assertEqual(zeros,16*count);total_zero+=zeros
  self.assertEqual(total_zero,29376)
 def test_header_reproducible(self):self.assertEqual((P/'expected_m17.hpp').read_text(),g.render())
 def test_no_shared_driver_oracle_index(self):
  d=(P/'stimulus_m17.hpp').read_text();ref=(P/'reference_events.py').read_text();gen=(P/'generate_reference.py').read_text()
  for token in ('observation_','reference::','expected_m17'):self.assertNotIn(token,d)
  self.assertNotIn('stimulus_m17',ref+gen);self.assertNotIn('driver_descriptor',ref+gen)
 def test_source_original_addresses_and_clock(self):
  s=(P/'m17_main.cpp').read_text();self.assertIn('m=17,cap=499997,q=0x100000,k=0x200000,v=0x300000,dst=0x400000',s)
  self.assertNotIn('0x500000',s);self.assertNotIn('targetToken',s);self.assertIn('clockEdges<=500000',s);self.assertIn('argc==1',s)
 def test_passive_global_base(self):
  s=(P/'m17_main.cpp').read_text();self.assertIn('U(d.observation_key)==e.base',s);self.assertIn('U(d.testScoreWrite_bits_index)==e.index',s);self.assertIn('stimulus::descriptor(groups)',s);self.assertIn('reference::groups[checkedGroups]',s)
 def test_abi_unchanged(self):self.assertEqual((P/'generated_abi.hpp').read_bytes(),(P.parent/'qwen2_core_client_verilator_m3_prepare_20261025T2350/generated_abi.hpp').read_bytes())

class Log(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.raw=fixture()
 def test_good_cross_chunk_gap(self):
  got=c.check(self.raw);self.assertEqual(got['observations'],8964);self.assertEqual(got['phase_counts'],{'1':3456,'2':3456,'3':216,'4':1836})
 def test_mutations(self):
  for a,b in [(b'checkedGroups=216',b'checkedGroups=215'),(b'checkedMemory=32640',b'checkedMemory=32639'),(b'checkedPv=14688',b'checkedPv=14687'),(b'checkedVector=8964',b'checkedVector=8963'),(b'keyBase=16',b'keyBase=0'),(b'scoreIndex=16',b'scoreIndex=0'),(b'targetPrefix=0,1,2,3',b'targetPrefix=0,2,1,3'),(b'faults=0',b'faults=1'),(b'numerical_matrix_verified=false',b'numerical_matrix_verified=true'),(b'total_rising_edges=200003',b'total_rising_edges=200002'),(b'normal_m17',b'normal_m3')]:
   with self.subTest(a=a):
    self.assertIn(a,self.raw)
    with self.assertRaises(ValueError):c.check(self.raw.replace(a,b,1))
 def test_second_chunk_max_must_inherit(self):
  lines=self.raw.splitlines();i=next(i for i,x in enumerate(lines) if b'keyBase=16' in x);lines[i]=lines[i].replace(b'max=0',b'max=4286578688')
  with self.assertRaises(ValueError):c.check(b'\n'.join(lines)+b'\n')
 def test_nan_valid_score(self):
  lines=self.raw.splitlines();i=next(i for i,x in enumerate(lines) if b'scoreWrite=true' in x);lines[i]=lines[i].replace(b'scoreData=0',b'scoreData=2143289344')
  with self.assertRaises(ValueError):c.check(b'\n'.join(lines)+b'\n')
 def test_chunk_inside_gap_rejected(self):
  lines=self.raw.splitlines();i=next(i for i,x in enumerate(lines) if b'keyBase=16' in x)+1;m=re.search(rb'cycle=(\d+)',lines[i]);lines[i]=lines[i].replace(m[0],b'cycle='+str(int(m[1])+1).encode())
  with self.assertRaises(ValueError):c.check(b'\n'.join(lines)+b'\n')
 def test_bad_log_boundaries(self):
  for raw in [self.raw+b'%Error assertion\n',self.raw+self.raw,self.raw.replace(b'OBS cycle=',b'OBS\tcycle=',1),b'\n'.join(self.raw.splitlines()[1:])+b'\n']:
   with self.assertRaises(ValueError):c.check(raw)
 def test_clock_cap(self):
  for a,b in [(b'cycles=200000',b'cycles=499998'),(b'total_rising_edges=200003',b'total_rising_edges=500001')]:
   with self.assertRaises(ValueError):c.check(self.raw.replace(a,b))
 def test_scalar_probability_domain(self):
  for n in (0,18,True,1.0):
   with self.assertRaises(ValueError):r.uniform_bf16(n)

if __name__=='__main__':unittest.main()
