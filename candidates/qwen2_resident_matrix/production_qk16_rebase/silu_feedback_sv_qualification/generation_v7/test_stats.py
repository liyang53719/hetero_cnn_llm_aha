import tempfile,unittest
from pathlib import Path
from leader_stats import stat_fields,sample,read_bounded

def stat(pid=17,start=100,group=17):
 v=['S','1',str(group),'17']+['0']*18
 v[11]='123';v[12]='45';v[19]=str(start)
 return f'{pid} (name with ) chars) '+' '.join(v)+'\n'
class Cold(unittest.TestCase):
 def test_stat(self):
  x=stat_fields(stat(),17);self.assertEqual((x['user_ticks'],x['system_ticks'],x['start_ticks']),(123,45,100))
 def test_wrong_leader(self):
  with self.assertRaises(ValueError):stat_fields(stat(group=5),17)
 def test_sample_and_identity(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'17';p.mkdir();(p/'stat').write_text(stat());(p/'status').write_text('Name: f\nVmRSS: 123 kB\nVmHWM: 456 kB\n')
   key,x=sample(17,root=root);self.assertEqual(x['VmHWM_bytes'],456*1024)
   (p/'stat').write_text(stat(start=101))
   with self.assertRaises(ValueError):sample(17,key,root=root)
 def test_zombie_memory_missing(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'17';p.mkdir();(p/'stat').write_text(stat());(p/'status').write_text('Name: f\n')
   _,x=sample(17,root=root);self.assertNotIn('VmHWM_bytes',x)
 def test_read_cap(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'f';p.write_bytes(b'x'*10)
   with self.assertRaises(ValueError):read_bounded(p,9)
if __name__=='__main__':unittest.main()
