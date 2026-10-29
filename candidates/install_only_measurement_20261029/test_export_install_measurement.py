import argparse,hashlib,json,tempfile,unittest
from pathlib import Path
import export_install_measurement as m
ap=argparse.ArgumentParser();ap.add_argument('--measurement',type=Path,required=True);args,rest=ap.parse_known_args()
class Tests(unittest.TestCase):
 def test_actual(self):
  r=m.export(args.measurement);self.assertEqual(r['final_unique_inode_logical_bytes'],3506537745);self.assertEqual(len(r['stages']),4);self.assertFalse(r['scope']['peak_is_mathematical_upper_bound'])
 def test_drift(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.json';p.write_bytes(args.measurement.read_bytes()+b' ')
   with self.assertRaises(ValueError):m.export(p)
 def test_export_is_bounded_and_path_free(self):
  r=m.export(args.measurement);s=json.dumps(r);self.assertLess(len(s.encode()),16384)
  for forbidden in ['/workspace/','/tmp/','path','argv','pid','owner_identity']:self.assertNotIn(forbidden,s)
  self.assertEqual(max(x['process_sample_max_gap_seconds'] for x in r['stages']),12.176789747005387)
if __name__=='__main__':unittest.main(argv=['test_export_install_measurement.py',*rest])
