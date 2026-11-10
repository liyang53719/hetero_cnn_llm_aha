import unittest,json
from pathlib import Path
import emit_cold128_programs as program
class FullBinding(unittest.TestCase):
 def test_profile2_complete_program(self):
  b,_=program.common(2);cb,db,m=b.finish()
  self.assertEqual(m['launch']['profileId'],2);self.assertEqual(len(cb)//16,22)
  self.assertEqual(m['schedule'][-1]['name'],'final_fence')
  self.assertEqual([x['name'] for x in m['schedule'] if x['name'] in ('q','k','v')],['q','k','v'])
  for n in ['input_norm','q','k','v','context']:self.assertFalse(m['tensors'][n]['readonly'])
 def test_actual_bind_readonly_coverage(self):
  j=json.loads(Path(__file__).with_name('FULL_BINDING.json').read_text());names={x['name'] for x in j['segments']}
  self.assertEqual(names,{n for n,t in j['tensors'].items() if t['readonly']})
  self.assertTrue({'o_weight','gate_weight','up_weight','down_weight'}<=names)
  self.assertTrue(j['trig_contract_validated']);self.assertFalse(j['hardware_executed'])
if __name__=='__main__':unittest.main()
