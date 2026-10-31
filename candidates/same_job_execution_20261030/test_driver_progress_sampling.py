"""Source-only telemetry schedule tests; no C++/DUT/weights execution."""
from pathlib import Path
import hashlib,re,unittest
D=Path(__file__).resolve().parent
REL=Path('candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp')
ORIGINAL_SHA='f4f00dffd348e1822e7fcb5ac59602579d693d7a8d04e221cdd3f0255b56b04c'
NEW=next(root/REL for root in (D/'source',D,*D.parents)if (root/REL).is_file())
OLD_LOOP='  while(!d.io_result_valid&&activeCycles<maxCycles){step();if((activeCycles&0xfffff)==0)trace("running");}'
NEW_LOOP='''  // Read-only host telemetry: one immediate low-cycle sample, then at most
  // one clock query per64 active cycles and one running line per steady second.
  // No DUT step, completion condition, arithmetic, input or ABI is changed.
  bool progressSeen=false;auto lastProgress=std::chrono::steady_clock::time_point{};
  while(!d.io_result_valid&&activeCycles<maxCycles){step();
   if(!progressSeen||(activeCycles&63ULL)==0){
    const auto now=std::chrono::steady_clock::now();
    if(!progressSeen||now-lastProgress>=std::chrono::seconds(1)){
     trace("running");lastProgress=now;progressSeen=true;
    }
   }
  }'''
def schedule(max_cycle,clock_ns,complete_at=None):
 # Literal policy model; source lock test ensures this is the exact C++ schedule.
 active=1;seen=False;last=0;steps=[];queries=[];lines=[]
 while not(complete_at is not None and active>=complete_at)and active<max_cycle:
  active+=1;steps.append(active)
  if not seen or (active&63)==0:
   now=clock_ns(active);queries.append(active)
   if not seen or now-last>=1000000000:
    lines.append((active,now));last=now;seen=True
 return steps,queries,lines
class ProgressSampling(unittest.TestCase):
 def test_entire_driver_other_than_include_and_loop_unchanged(self):
  s=NEW.read_text();self.assertEqual(s.count(NEW_LOOP),1);s=s.replace(NEW_LOOP,OLD_LOOP).replace('#include <charconv>\n#include <chrono>','#include <charconv>');self.assertEqual(hashlib.sha256(s.encode()).hexdigest(),ORIGINAL_SHA)
 def test_step_and_stop_conditions_unchanged(self):
  for bound in [1,2,3,63,64,65,128,257]:
   for completion in [None,1,2,63,128,1000]:
    steps,_,_=schedule(bound,lambda c:0,completion);expected=list(range(2,min(bound,completion if completion is not None else bound)+1));self.assertEqual(steps,expected)
 def test_first_low_cycle_sample(self):
  _,queries,lines=schedule(3,lambda c:c*2000000000);self.assertEqual(queries,[2]);self.assertEqual(lines,[(2,4000000000)])
 def test_clock_only_first_or_multiple64(self):
  _,queries,_=schedule(10000,lambda c:c*1000000);self.assertEqual(queries,[2]+list(range(64,10001,64)));self.assertEqual(len(queries),1+10000//64)
 def test_stationary_clock_one_line_only(self):
  _,queries,lines=schedule(10000,lambda c:0);self.assertEqual(len(lines),1);self.assertEqual(len(queries),157)
 def test_exact_one_second_boundary(self):
  def clock(c):return 0 if c==2 else 999999999 if c==64 else 1000000000
  _,_,lines=schedule(128,clock);self.assertEqual(lines,[(2,0),(128,1000000000)])
 def test_max_one_running_per_steady_second(self):
  for ns_per_cycle in [1,1000000,15625000,1000000000,2000000000]:
   _,_,lines=schedule(10000,lambda c:c*ns_per_cycle)
   self.assertTrue(all(b[1]-a[1]>=1000000000 for a,b in zip(lines,lines[1:])))
   self.assertLessEqual(len(lines),1+(lines[-1][1]-lines[0][1])//1000000000)
 def test_original_terminal_and_exception_behavior_preserved(self):
  s=NEW.read_text();old=s.replace(NEW_LOOP,OLD_LOOP).replace('#include <charconv>\n#include <chrono>','#include <charconv>');self.assertEqual(s[s.index('  trace("terminal");'):],old[old.index('  trace("terminal");'):]);self.assertEqual(s[s.index(' void trace('):s.index(' void step(')],old[old.index(' void trace('):old.index(' void step(')])
 def test_no_added_dut_or_host_data_writes_in_scheduler(self):
  # The only assignments in the inserted scheduler are local telemetry state.
  self.assertEqual(re.findall(r'(?<![=!<>])\b([A-Za-z_][A-Za-z0-9_]*)=(?!=)',NEW_LOOP),['progressSeen','lastProgress','now','lastProgress','progressSeen']);self.assertEqual(NEW_LOOP.count('step();'),1);self.assertNotIn('d.',NEW_LOOP[NEW_LOOP.index('{step();')+9:])
if __name__=='__main__':unittest.main()
