import argparse, importlib.util, json, unittest
from pathlib import Path
D=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('exporter',D/'export_provider_measurement.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_frozen_summary(self):
  x=json.loads((D/'PROVIDER_ONLY_MEASUREMENT.json').read_text())
  self.assertEqual([p['profile'] for p in x['profiles']],list(range(5)))
  self.assertEqual(len(x['stages']),7)
  self.assertTrue(all(s['process_sample_count']==1 and s['rss_qualification']==m.RSS for s in x['stages']))
  self.assertFalse(x['dut_execution']);self.assertFalse(x['new_reference_execution'])
 def test_tamper_rejected(self):
  for b in (b'{}',b'{"path":"/private/a"}',b'x'*65537):
   with self.assertRaises(ValueError):m.extract(b)
 def test_numeric_bounds(self):
  for v in (True,-1,float('nan'),float('inf'),10**13,'/private/a'):
   with self.assertRaises(ValueError):m.num(v)
 def test_no_paths(self):
  x=json.loads((D/'PROVIDER_ONLY_MEASUREMENT.json').read_text())
  def walk(v):
   if isinstance(v,dict):
    for k,w in v.items():self.assertNotIn(k,('path','pid','argv'));walk(w)
   elif isinstance(v,list):
    for w in v:walk(w)
   elif isinstance(v,str):self.assertNotIn('/',v);self.assertNotIn('\\',v)
  walk(x)
if __name__=='__main__':unittest.main()
