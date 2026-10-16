"""No automatic CDLL or numerical execution in cold tests."""
import subprocess,sys,tempfile,unittest
from pathlib import Path
from . import prepare
class Tests(unittest.TestCase):
 def test_exact_selector_and_installed_closure(self):
  with tempfile.TemporaryDirectory() as d:
   old=prepare.prior.compose(Path(d)/'old');new=prepare.compose(Path(d)/'new')
   self.assertEqual((new/prepare.TARGET).read_text(),prepare.alter((old/prepare.TARGET).read_text()))
   code="import ctypes;ctypes.CDLL=lambda *a,**k:(_ for _ in ()).throw(AssertionError('no native'));from candidates.qwen2_resident_matrix.attention_packed_tiled_transport import prepare;print(len(prepare.verify_installed()))"
   r=subprocess.run([sys.executable,'-B','-c',code],cwd=new,capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr);self.assertGreater(int(r.stdout),170)
 def test_only_visible_response_edges_count_as_ack_stalls(self):
  from .fixture import ResponseHold
  h=ResponseHold();r=object()
  for _ in range(4):self.assertTrue(h.stall(None))
  self.assertEqual(h.count,0)
  self.assertTrue(h.stall(r))
  with self.assertRaises(AssertionError):h.stall(object())
  for _ in range(6):self.assertTrue(h.stall(r))
  self.assertEqual(h.count,7);self.assertFalse(h.stall(r))
 def test_invalid_shapes_reject_before_library(self):
  from .fixture import actual_case
  for n in (True,1,2,16,128):
   with self.assertRaises(ValueError):actual_case('missing',n)
 def test_runner_case_selection_without_native(self):
  from unittest.mock import patch
  from . import run_small
  with patch.object(run_small.prepare,'verify_installed',return_value={}),patch.object(run_small.Path,'read_bytes',return_value=b'x'),patch.object(run_small.hashlib,'sha256') as h,patch.object(run_small,'actual_case',return_value={}) as case:
   h.return_value.hexdigest.return_value=run_small.LIB_SHA
   x=run_small.run('missing',17);self.assertEqual(len(x['cases']),3)
   self.assertEqual([c.kwargs.get('fault') for c in case.call_args_list],[None,'panel_abort','panel_ddr_error'])
if __name__=='__main__':unittest.main()
