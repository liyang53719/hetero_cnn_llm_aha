import unittest,tempfile,pathlib,os
from live_bytes import census,admit,SETUP_FREE,TREE_CAP,RESERVE
P=pathlib.Path
class T(unittest.TestCase):
 def test_actual_census_hardlinks_and_nested_roots(self):
  with tempfile.TemporaryDirectory()as d:
   p=P(d);(p/'sub').mkdir();(p/'sub/a').write_bytes(b'x'*64);os.link(p/'sub/a',p/'b');(p/'alias').symlink_to(p/'sub',target_is_directory=True)
   r=census([p,p/'sub']);self.assertEqual(r['path_count_logical_bytes'],128);self.assertEqual(r['unique_inode_logical_bytes'],64);self.assertEqual(r['symlinks_not_followed'],1)
 def test_preserved_setup_gate(self):
  r={'unique_inode_logical_bytes':0,'disk':{'free_bytes':SETUP_FREE-1}}
  for phase in ('runtime_setup','weight_acquisition'):
   with self.assertRaises(ValueError):admit(r,phase,0,1000,100)
 def test_missing_bound_and_wall(self):
  r={'unique_inode_logical_bytes':100,'disk':{'free_bytes':SETUP_FREE+1}}
  for n in (None,-1,True):
   with self.assertRaises(ValueError):admit(r,'reference',n,1000,100)
  with self.assertRaises(ValueError):admit(r,'dut',0,100,100)
 def test_tree_and_free(self):
  with self.assertRaises(ValueError):admit({'unique_inode_logical_bytes':TREE_CAP,'disk':{'free_bytes':SETUP_FREE}},'provider',1,1000,100)
  with self.assertRaises(ValueError):admit({'unique_inode_logical_bytes':0,'disk':{'free_bytes':RESERVE}},'provider',1,1000,100)
  self.assertTrue(admit({'unique_inode_logical_bytes':0,'disk':{'free_bytes':SETUP_FREE}},'provider',100,1000,100)['continuous_supervisor_still_required'])
if __name__=='__main__':unittest.main()
