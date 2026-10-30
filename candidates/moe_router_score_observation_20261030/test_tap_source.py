from pathlib import Path
import hashlib,json,unittest
R=Path(__file__).parent
class Source(unittest.TestCase):
 def test_frozen_provenance(self):
  for x in json.loads((R/'BASE_AND_RESULT_PINS.json').read_text())['files']:
   self.assertEqual(hashlib.sha256((R/x['name']).read_bytes()).hexdigest(),x['result_sha256'])
 def test_real_fire_and_no_feedback(self):
  t=(R/'source/UnifiedMoeRouterNumericalOwnerV2.scala').read_text()
  self.assertIn('io.rawScoreObservation.valid:=io.selection.in.fire',t)
  self.assertIn('io.rawScoreObservation.bits.score:=io.selection.in.bits.score',t)
  self.assertIn('io.rawScoreObservation.bits.token:=token',t)
  for f in (R/'source').glob('*.scala'):
   for line in f.read_text().splitlines():
    if 'rawScoreObservation' in line:self.assertNotIn('ready',line)
 def test_terminal_rejects_uncaptured_tail_event(self):
  t=(R/'driver/host_axi_driver_non_dpi.cpp').read_text()
  quiet=t.split('auto terminalQuiet=[&](){',1)[1].split('};',1)[0]
  self.assertIn('!d.io_rawScoreObservation_valid',quiet)
 def test_p0_interface_preserved(self):
  t=(R/'source/HostBlockTopV4.scala').read_text()
  self.assertIn('io.residentObservation:=owner.io.residentObservation',t)
  self.assertIn('io.rawScoreObservation:=moeLoop.io.rawScoreObservation',t)
if __name__=='__main__':unittest.main()
