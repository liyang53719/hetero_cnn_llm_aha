"""Offline producer metadata must not consult executor aliases; no tool executes."""
import hashlib,importlib.util,pathlib,tempfile,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('builder_dep',D/'driver_dependency_proof.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Paths(unittest.TestCase):
 def test_nonexistent_builder_path_no_resolve(self):
  p='/old-builder-only/usr/bin/g++';t=dict(compile_tools={'cxx':p},pins={p:'a'*64})
  with patch.object(pathlib.Path,'resolve',side_effect=AssertionError('executor path lookup forbidden')):self.assertEqual(m.builder_tool_pin(t,'cxx'),p)
 def test_executor_alias_not_interpreted(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'compiler';p.symlink_to('/different-host/compiler')
   v=dict(compile_tools={'cxx':str(p)},pins={str(p):'a'*64})
   self.assertEqual(m.builder_tool_pin(v,'cxx'),str(p))
 def test_noncanonical(self):
  for p in ('relative','/a/../b','/a/./b','/a//b','/a/','//a','/a x'):
   with self.subTest(p=p),self.assertRaises(ValueError):m.builder_tool_pin(dict(compile_tools={'cxx':p},pins={p:'a'*64}),'cxx')
 def test_requires_original_pin(self):
  with self.assertRaises(ValueError):m.builder_tool_pin(dict(compile_tools={'cxx':'/a'},pins={}), 'cxx')
 def test_producer_copy_exact(self):
  p=D.parents[1]/'ci_frontend_pipeline_r2_20261029/driver_dependency_proof.py'
  self.assertEqual((D/'driver_dependency_proof.py').read_bytes(),p.read_bytes())
if __name__=='__main__':unittest.main()
