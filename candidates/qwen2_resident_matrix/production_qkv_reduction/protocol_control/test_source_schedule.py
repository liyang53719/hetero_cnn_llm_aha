"""Cold script-schedule checks, not Chisel or protocol execution."""
from pathlib import Path
import unittest,json
R=Path(__file__).resolve().parent
class Schedule(unittest.TestCase):
 def test_hold_is_reduction_only(self):
  s=(R/'source/ProductionQkvProtocolHarness.scala').read_text()
  self.assertIn('val hold=io.reductionResultHeld && router.io.reductionOwns',s)
  self.assertIn('cmd.io.done.valid:=router.io.done.valid && !hold',s)
  self.assertIn('router.io.done.ready:=cmd.io.done.ready && !hold',s)
 def test_ordinary_before_reduction_not_blocked(self):
  for fault in ['held_reset','held_abort']:
   trace=[];requested=True
   for phase,owns,host_ready in [('pc0_norm_reply',False,True),('qkv_held_reply',True,True),('late_fault_still_held',True,True),('release_fault_reply',True,True)]:
    if phase=='release_fault_reply':requested=False
    hold=requested and owns;valid=not hold;ready=host_ready and not hold
    trace.append(dict(case=fault,phase=phase,valid=valid,ready=ready))
   self.assertTrue(trace[0]['ready']);self.assertFalse(trace[1]['ready']);self.assertFalse(trace[2]['ready']);self.assertTrue(trace[3]['ready'])
 def test_selected_cases_have_drive_branches(self):
  s=(R/'source/ProductionQkvProtocolSpec.scala').read_text()
  for case in ['held_reset','held_abort','abort_pending','window_tag','drain_short']:
   self.assertGreaterEqual(s.count('"'+case+'"'),2)
  self.assertIn('noPublish(127);d.io.reductionOffered.valid.expect(false.B)',s)
  self.assertIn('if(fault=="held_abort")d.io.abort.poke(true.B) else d.io.backendReset.poke(true.B)',s)
  self.assertIn('d.io.reductionResultHeld.poke(false.B)',s)
 def test_no_hardware_execution_or_arithmetic_substitute(self):
  s=(R/'source/ProductionQkvProtocolHarness.scala').read_text()
  for name in ['TransposedDenseDownOwner','MatrixPipeline','SiluVectorUnit','QwenOwnerKernel']:
   self.assertNotIn('new '+name,s)
  t=(R/'source/ProductionQkvProtocolSpec.scala').read_text()
  self.assertIn('TreadleBackendAnnotation',t);self.assertNotIn('VerilatorBackendAnnotation',t)
if __name__=='__main__':unittest.main(verbosity=2)
