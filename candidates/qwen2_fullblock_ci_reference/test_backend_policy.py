import sys,types,unittest
from unittest.mock import patch
from . import backend_policy as B
class BackendTests(unittest.TestCase):
 def recipe(self,selected):
  def need(ok,message):
   if not ok:raise ValueError(message)
  return types.SimpleNamespace(need=need,dependency=lambda _:types.SimpleNamespace(mkldnn_enabled=lambda:selected))
 def torch(self,enabled=True):return types.SimpleNamespace(backends=types.SimpleNamespace(mkldnn=types.SimpleNamespace(enabled=enabled)))
 def test_default_no_import_or_change(self):
  t=self.torch()
  with patch.dict(sys.modules,{'torch':t}):B.before_stage(self.recipe(None),B.START)
  self.assertTrue(t.backends.mkldnn.enabled)
 def test_candidate_sets_before_arithmetic(self):
  t=self.torch()
  with patch.dict(sys.modules,{'torch':t}):B.before_stage(self.recipe(False),B.START)
  self.assertIs(t.backends.mkldnn.enabled,False)
 def test_future_stage_rejects_drift(self):
  with patch.dict(sys.modules,{'torch':self.torch()}):
   with self.assertRaises(ValueError):B.before_stage(self.recipe(False),'official-prefix-execution')
 def test_does_not_preimport(self):
  with patch.dict(sys.modules,{'torch':None}):B.before_stage(self.recipe(False),'raw13-load')
 def test_missing_torch_fails(self):
  with patch.dict(sys.modules,{'torch':None}):
   with self.assertRaises(ValueError):B.before_stage(self.recipe(False),B.START)
 def test_no_truthy_backend(self):
  with patch.dict(sys.modules,{'torch':self.torch(0)}):
   with self.assertRaises(ValueError):B.before_stage(self.recipe(False),'official-tail-execution')
