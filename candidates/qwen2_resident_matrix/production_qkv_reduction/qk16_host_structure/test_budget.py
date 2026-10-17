"""No child execution: mock spawn to inspect the inherited environment."""
import os,signal,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import owned_compile as o
import run_structure as r
P=Path(__file__).resolve().parent
class Probe(Exception):pass
class Budget(unittest.TestCase):
 def test_input_loading_under_alarm(self):
  class Args:execute=True;out=Path('/path-that-is-not-used')
  def read(*a,**k):
   self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],0);raise Probe()
  with patch.object(Path,'read_text',read),self.assertRaises(Probe):r.run(Args())
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
 def test_helper_load_has_live_alarm(self):
  def load(*a):
   self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],0)
   self.assertNotIn(signal.SIGALRM,signal.pthread_sigmask(signal.SIG_BLOCK,set()))
   raise Probe()
  with tempfile.TemporaryDirectory() as d,open(Path(d)/'log','wb') as log,patch.object(o,'helper',load):
   result=o.execute(['/not/executed'],cwd=d,log=log,cleanup_helper=P/'strict_cleanup.py',absolute_stop=time.monotonic()+3,stage_stop=time.monotonic()+1,cleanup_seconds=1)
  self.assertEqual(result['error'],'Probe')
 def test_child_environment_is_fixed(self):
  observed=[]
  def spawn(*a,**k):observed.append(k['env']);raise Probe()
  with tempfile.TemporaryDirectory() as d,open(Path(d)/'log','wb') as log:
   with patch.dict(os.environ,{'JAVA_TOOL_OPTIONS':'bad','JDK_JAVA_OPTIONS':'bad','LD_PRELOAD':'bad','PYTHONPATH':'bad'}),patch.object(o.subprocess,'Popen',spawn):
    result=o.execute(['/not/executed'],cwd=d,log=log,cleanup_helper=P/'strict_cleanup.py',absolute_stop=time.monotonic()+3,stage_stop=time.monotonic()+1,cleanup_seconds=1)
  self.assertEqual(result['error'],'Probe');self.assertEqual(observed,[{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC'}]);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
if __name__=='__main__':unittest.main()
