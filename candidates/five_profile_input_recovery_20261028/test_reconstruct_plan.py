from pathlib import Path
import json,shutil,tempfile,unittest
import reconstruct_plan as r
class Reconstruction(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.p=Path(self.t.name)/'bundle';shutil.copytree(r.HERE,self.p)
 def tearDown(self):self.t.cleanup()
 def mutate(self,name,fn):
  p=self.p/name;x=json.loads(p.read_text());fn(x);p.write_text(json.dumps(x))
 def reject(self):
  with self.assertRaises(ValueError):r.verified_plan(self.p)
 def test_normal(self):self.assertEqual(len(r.verified_plan(self.p)['specs']),70)
 def test_float_workers(self):self.mutate('ACQUISITION_PLAN.json',lambda x:x.update(workers=2.0));self.reject()
 def test_wrong_offset(self):self.mutate('ACQUISITION_PLAN.json',lambda x:x['specs'][0].update(start=0));self.reject()
 def test_wrong_name(self):self.mutate('ACQUISITION_PLAN.json',lambda x:x['specs'][0].update(name='mtp.layers.0.fake'));self.reject()
 def test_missing_expert(self):self.mutate('ACQUISITION_PLAN.json',lambda x:x['specs'].pop());self.reject()
 def test_path_escape(self):self.mutate('ACQUISITION_PLAN.json',lambda x:x['headers'][0]['header'].update(json_text='../outside'));self.reject()
 def test_changed_header(self):
  f=next((self.p/'headers').glob('*.json'));f.write_bytes(f.read_bytes()+b' ');self.reject()
 def test_changed_original_pin(self):
  f=self.p/'pins/layer0_payload_pin.json';f.write_bytes(f.read_bytes()+b' ');self.reject()
 def test_changed_revision(self):self.mutate('ACQUISITION_PLAN.json',lambda x:x['specs'][0].update(revision='main'));self.reject()
 def test_changed_shape(self):self.mutate('ACQUISITION_PLAN.json',lambda x:x['specs'][0].update(shape=[1]));self.reject()
if __name__=='__main__':unittest.main()
