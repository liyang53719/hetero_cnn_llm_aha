import json,pathlib,subprocess,sys,tempfile,time,unittest
import numeric_tail as n
class T(unittest.TestCase):
 def test_real_none_shapes(self):
  for r in ({'cleanup_proof':None,'log_capture':None},{'cleanup_proof':None,'log_capture':{}},{'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':None},{}):self.assertIs(n.complete(r),False)
 def test_none_holds_parent_lease(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);marker=root/'HELD';released=root/'RELEASED'
   code="import contextlib,pathlib,sys;sys.path.insert(0,sys.argv[1]);import numeric_tail as n\n@contextlib.contextmanager\ndef lease():\n try:yield\n finally:pathlib.Path(sys.argv[3]).write_text('released')\nwith lease():n.require_cleanup({'cleanup_proof':None,'log_capture':None},pathlib.Path(sys.argv[2]))\n"
   p=subprocess.Popen([sys.executable,*(['-O'] if not __debug__ else []),'-B','-c',code,str(pathlib.Path(n.__file__).parent),str(marker),str(released)])
   try:
    until=time.monotonic()+3
    while not marker.exists()and p.poll()is None and time.monotonic()<until:time.sleep(.02)
    self.assertTrue(marker.exists());self.assertIsNone(p.poll());self.assertFalse(released.exists());self.assertEqual(json.loads(marker.read_text())['status'],'HOLD_PARENT_LEASE_NO_CONTINUATION')
   finally:
    if p.poll()is None:p.kill()
    p.wait(timeout=3)
   self.assertFalse(released.exists())
if __name__=='__main__':unittest.main()
