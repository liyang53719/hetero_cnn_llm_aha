import hashlib,json,pathlib,unittest
R=pathlib.Path(__file__).resolve().parents[1]
class Source(unittest.TestCase):
 def test_result_pins(self):
  for x in json.loads((R/'BASE_AND_RESULT_PINS.json').read_text())['files']:
   self.assertEqual(hashlib.sha256((R/x['name']).read_bytes()).hexdigest(),x['result_sha256'])
 def test_event_exclusivity_and_actual_output(self):
  s=(R/'source/UnifiedMoeRouterNumericalOwnerV2.scala').read_text()
  for v in ('val selectStart=ss(5);val selectFeed=ss(6);val selectRead=ss(7)','io.selection.in.valid:=state===selectFeed','io.selection.out.ready:=state===selectRead && !quarantine','assert(!(io.selection.in.fire && io.selection.out.fire))','io.selection.out.bits.score,io.selection.in.bits.score'):
   self.assertIn(v,s)
 def test_bits_and_protocol(self):
  a=json.loads((R/'ABI_SCHEMA_V2.json').read_text());self.assertEqual(sum(a['fields'].values()),259);self.assertEqual(len(a['fields']),10)
  h=(R/'driver/moe_raw_score_observation.hpp').read_text();self.assertIn('selected_[outputs_]=b.score;ids_[outputs_]=b.expert;',h)
  self.assertNotIn('require(b.score==input_',h);self.assertIn('!d.io_rawScoreObservation_valid',(R/'driver/host_axi_driver_non_dpi.cpp').read_text())
if __name__=='__main__':unittest.main()
