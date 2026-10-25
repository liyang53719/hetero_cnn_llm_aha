"""Stdlib only; no compiler, SV parse, tool or simulation invocation."""
import importlib.util,json,re,unittest
from pathlib import Path
R=Path(__file__).resolve().parent
def load(name):
 spec=importlib.util.spec_from_file_location('harness_contract_'+name,R/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=load('check_m1_log');g=load('generate_abi')
def synthetic():
 lines=[c.READY]
 for head in range(12):
  for offset in range(34):
   phase=1 if offset<16 else 2 if offset<32 else 3 if offset==32 else 4
   lane=offset if offset<16 else offset-16 if offset<32 else 15
   lines.append(f'OBS cycle={10+head*40+offset} token=0 head={head} phase={phase} lane={lane} selected=0 faults=0 scoreWrite={str(phase==4).lower()} scoreIndex=0 scoreData=0 max=0 resultReady=false')
 counts=dict(c.EXPECTED,cycles=500,requestHoldChecks=1,hold_group=0,hold_memory=1,hold_pv=0,hold_step=0)
 terminal='VERILATOR_CORE_CASE_PASS case=normal_m1 m=1 cycles=500 groups=12 qkAcceptedSteps=96 accounting512Steps=864 results=12 dones=12 scoreWrites=12 targetPrefix= ownerAccepts=1 pvRequests=96 pvReturns=96 requestHoldChecks=1 holdChecksByPort=(group,0),(memory,1),(pv,0),(step,0) memoryAccepted=384 memoryReturned=384 outputBytes=6144 numerical_matrix_verified=false'
 return ('\n'.join(lines+[terminal,'VERILATOR_CORE_DONE case=normal_m1 completed=true total_rising_edges=503 reset_clocks=3'])+'\n').encode()
class EventContract(unittest.TestCase):
 def reject(self,raw):
  with self.assertRaises(ValueError):c.check(raw)
 def test_synthetic_positive_not_runtime_proof(self):
  r=c.check(synthetic());self.assertFalse(r['runtime_provenance_verified']);self.assertIsNone(r['matrix_mac_utilization']);self.assertEqual(r['uncovered_request_hold_ports'],['group','pv','step'])
 def test_missing_done(self):self.reject(synthetic().rsplit(b'VERILATOR_CORE_DONE',1)[0])
 def test_extra_done(self):self.reject(synthetic()+b'VERILATOR_CORE_DONE case=normal_m1 completed=true total_rising_edges=503 reset_clocks=3\n')
 def test_old_treadle_markers(self):self.reject(synthetic().replace(b'VERILATOR_CORE_SIM_READY',b'CORE_SIM_READY'))
 def test_non_m1(self):self.reject(synthetic().replace(b'normal_m1',b'normal_m2'))
 def test_reset_mismatch(self):self.reject(synthetic().replace(b'reset_clocks=3',b'reset_clocks=2'))
 def test_total_edge_mismatch(self):self.reject(synthetic().replace(b'total_rising_edges=503',b'total_rising_edges=502'))
 def test_count_mac_confusion(self):self.reject(synthetic().replace(b'accounting512Steps=864',b'accounting512Steps=192'))
 def test_missing_pv(self):self.reject(synthetic().replace(b'pvRequests=96',b'pvRequests=0'))
 def test_memory_count(self):self.reject(synthetic().replace(b'memoryAccepted=384',b'memoryAccepted=383'))
 def test_hold_over_cycles(self):self.reject(synthetic().replace(b'(memory,1)',b'(memory,501)').replace(b'requestHoldChecks=1 ',b'requestHoldChecks=501 '))
 def test_zero_aggregate_hold(self):self.reject(synthetic().replace(b'(memory,1)',b'(memory,0)').replace(b'requestHoldChecks=1 ',b'requestHoldChecks=0 '))
 def test_unknown_obs_marker(self):self.reject(synthetic().replace(b'OBS cycle=10 ',b'OBS_BAD cycle=10 '))
 def test_stale_head(self):self.reject(synthetic().replace(b'head=11',b'head=10'))
 def test_fault(self):self.reject(synthetic().replace(b'faults=0',b'faults=1',1))
 def test_nonzero_score(self):self.reject(synthetic().replace(b'scoreWrite=true scoreIndex=0 scoreData=0',b'scoreWrite=true scoreIndex=0 scoreData=1',1))
 def test_early_release(self):self.reject(synthetic().replace(b'resultReady=false',b'resultReady=true',1))
 def test_hardware_error_not_hidden(self):self.reject(b'%Error: synthetic model failure\n'+synthetic())
 def test_ansi(self):self.reject(b'\x1b'+synthetic())
 def test_extra_observation(self):self.reject(synthetic().replace(c.READY.encode(),c.READY.encode()+b'\nOBS cycle=1 token=0 head=0 phase=1 lane=0 selected=0 faults=0 scoreWrite=false scoreIndex=0 scoreData=0 max=0 resultReady=false'))
class SourceContract(unittest.TestCase):
 def test_independent_reviewed_abi_reproduction(self):
  ports=json.loads((R.parent/'qwen2_core_client_verilator_source_review_20261025T2045/TOP_ABI.json').read_text())['ports'];header,mapping=g.generate(ports)
  self.assertEqual(header,(R/'generated_abi.hpp').read_text());self.assertEqual(mapping,json.loads((R/'ABI_MAPPING.json').read_text()));self.assertEqual(len(mapping['qk_tile_row_major_ports']),4096)
 def test_row_major_full_bijection(self):
  m=json.loads((R/'ABI_MAPPING.json').read_text());pairs=[tuple(map(int,re.search(r'value_(\d+)_(\d+)$',x).groups())) for x in m['qk_tile_row_major_ports']]
  self.assertEqual(pairs,[(r,col) for r in range(16) for col in range(256)]);self.assertEqual(len(set(pairs)),4096)
 def test_normal_tile_poison_selector(self):
  for row in range(16):
   active=[col for col in range(256) if not (col//16>0 or col%16!=row)];self.assertEqual(active,[row])
 def test_unsigned_address_no_wrap(self):
  cpp=(R/'m1_main.cpp').read_text();self.assertNotIn('at+64',cpp)
  for base,size in ((0x100000,6144),(0x200000,1024),(0x300000,1024),(0x400000,6144)):
   for at in (0,base-1,base,base+1,base+size-65,base+size-64,base+size-63,base+size,2**64-64,2**64-1):
    exact=at%64==0 and at>=base and at+64<=base+size
    subtract=at%64==0 and at>=base and at<=base+size-64
    self.assertEqual(exact,subtract)
  for term in ('at<=dst+6144-64','at<=q+6144-64','at<=k+1024-64','at<=v+1024-64'):self.assertIn(term,cpp)
 def test_bounded_case_startup_and_no_internal_access(self):
  cpp=(R/'m1_main.cpp').read_text()
  for term in ('cap=99997','clock();clock();clock();d.reset=0','clockEdges==cycles+3','clockEdges<=100000','need(argc==1','ctx->randReset(0)','ctx->threads(1)'):self.assertIn(term,cpp)
  for term in ('system(','popen(','fork(','rootp','__DOT__'):self.assertNotIn(term,cpp)
 def test_direct_port_names_and_writes(self):
  ports=json.loads((R.parent/'qwen2_core_client_verilator_source_review_20261025T2045/TOP_ABI.json').read_text())['ports'];cpp=(R/'m1_main.cpp').read_text()
  for name in set(re.findall(r'\bd\.((?:io_|observation_|testScoreWrite_)[A-Za-z0-9_]+)',cpp)):self.assertIn(name,ports)
  for name in re.findall(r'\bd\.((?:io_|observation_|testScoreWrite_)[A-Za-z0-9_]+)(?:\[[^\]]+\])?\s*=(?!=)',cpp):self.assertEqual(ports[name]['direction'],'input')
if __name__=='__main__':unittest.main(verbosity=2)
