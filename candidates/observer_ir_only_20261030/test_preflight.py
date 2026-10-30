import pathlib,tempfile,unittest,os
from unittest.mock import Mock,patch
import run_ir_only as m
class Preflight(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.repo=self.root/'repo';self.work=self.root/'work';self.repo.mkdir();self.work.mkdir();self.sup=Mock();self.sup.execute.return_value={'original':True}
  self.caps=dict(max_entries=20,file_bytes=100,watch_tree_bytes=200,min_free_disk_bytes=0,extra_watch_roots=[str(self.repo),str(self.work)])
 def tearDown(self):self.tmp.cleanup()
 def call(self):return m.admitted_execute(self.sup,['java'],str(self.work/'stage'),str(self.work/'lock'),self.caps,{}, {},resource_gate={'min_available_memory':1,'min_disk_free':0})
 def test_over_entry_no_execute(self):
  for i in range(13):(self.repo/str(i)).write_text('')
  with self.assertRaisesRegex(ValueError,'entry cap'):self.call()
  self.sup.execute.assert_not_called()
 def test_stage_reserve_boundary_original_execute(self):
  for i in range(12):(self.repo/str(i)).write_text('')
  self.assertEqual(self.call(),{'original':True});self.sup.execute.assert_called_once()
  self.assertEqual(self.sup.execute.call_args.kwargs['resource_gate'],{'min_available_memory':1,'min_disk_free':0})
 def test_root_and_inode_dedup_symlink_not_followed(self):
  f=self.repo/'f';f.write_bytes(b'x'*100);os.link(f,self.repo/'hard');(self.repo/'external').symlink_to(self.root/'absent',target_is_directory=True)
  caps=dict(self.caps,extra_watch_roots=[str(self.repo),str(self.repo)])
  r=m.preflight_census([self.repo,self.repo],caps);self.assertEqual(r['bytes'],100);self.assertEqual(r['entries'],3)
 def test_nested_root_not_double_counted(self):
  p=self.repo/'nested';p.mkdir();(p/'f').write_text('x')
  r=m.preflight_census([p,self.repo],self.caps);self.assertEqual(r['entries'],2);self.assertEqual(r['bytes'],1)
 def test_unreadable_walk_no_execute(self):
  def failed_walk(root,**kw):kw['onerror'](PermissionError('unreadable'));return iter(())
  with patch.object(m.os,'walk',side_effect=failed_walk),self.assertRaises(PermissionError):self.call()
  self.sup.execute.assert_not_called()
 def test_file_and_aggregate_limits_no_execute(self):
  f=self.repo/'f';f.write_bytes(b'x'*101)
  with self.assertRaisesRegex(ValueError,'file cap'):self.call()
  self.sup.execute.assert_not_called();f.write_bytes(b'x'*100);(self.repo/'g').write_bytes(b'x'*100);(self.repo/'h').write_bytes(b'x')
  with self.assertRaisesRegex(ValueError,'aggregate tree cap'):self.call()
  self.sup.execute.assert_not_called()
 def test_disk_reserve_no_execute(self):
  with patch.object(m.shutil,'disk_usage',return_value=Mock(free=0)):
   self.caps['min_free_disk_bytes']=1
   with self.assertRaisesRegex(ValueError,'disk reserve'):self.call()
  self.sup.execute.assert_not_called()
 def test_nonregular_no_execute(self):
  os.mkfifo(self.repo/'fifo')
  with self.assertRaisesRegex(ValueError,'nonregular'):self.call()
  self.sup.execute.assert_not_called()
if __name__=='__main__':unittest.main()
