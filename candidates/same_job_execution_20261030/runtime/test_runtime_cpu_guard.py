"""Mocked entry-boundary tests only: no install, model import, or host qualification."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('phase_under_test',HERE/'runtime_phase.py')
phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
class ReachedPins(Exception):pass
class Pins:
 def items(self):raise ReachedPins('guard passed; stop before installation')
class GuardTests(unittest.TestCase):
 def call(self,key,flags='avx2',version=(3,12,0),machine='x86_64'):
  with patch.object(phase,'sys',types.SimpleNamespace(version_info=version)),patch.object(phase.platform,'machine',return_value=machine),patch.object(Path,'read_text',return_value=flags) as cpu:
   phase.install({'pins':Pins()},key)
 def test_qwen35_without_avx512(self):
  for key in ('qwen35_08b','qwen35_35b'):
   with self.subTest(key=key),self.assertRaises(ReachedPins):self.call(key)
 def test_qwen35_with_avx512(self):
  for key in ('qwen35_08b','qwen35_35b'):
   with self.subTest(key=key),self.assertRaises(ReachedPins):self.call(key,'avx512f avx2')
 def test_p0_with_avx512(self):
  with self.assertRaises(ReachedPins):self.call('qwen2','avx512f avx2')
 def test_p0_without_avx512(self):
  with self.assertRaisesRegex(ValueError,'P0 AVX512'):self.call('qwen2')
 def test_p0_exact_flag(self):
  with self.assertRaisesRegex(ValueError,'P0 AVX512'):self.call('qwen2','notavx512f avx512fp16')
 def test_unknown_keys(self):
  for key in ('qwen35','qwen35_4b','qwen2_extra','',None,True):
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,'selected runtime'):self.call(key,'avx512f')
 def test_wrong_python(self):
  for key in ('qwen2','qwen35_08b','qwen35_35b'):
   for version in ((3,11,0),(3,13,0),(2,12,0)):
    with self.subTest(key=key,version=version),self.assertRaisesRegex(ValueError,'installation ABI'):self.call(key,'avx512f',version)
 def test_wrong_machine(self):
  for key in ('qwen2','qwen35_08b','qwen35_35b'):
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,'installation ABI'):self.call(key,'avx512f',machine='aarch64')
 def test_qwen35_no_p0_cpu_read(self):
  with patch.object(phase,'sys',types.SimpleNamespace(version_info=(3,12,0))),patch.object(phase.platform,'machine',return_value='x86_64'),patch.object(Path,'read_text',side_effect=PermissionError('must not read P0 flag')):
   for key in ('qwen35_08b','qwen35_35b'):
    with self.subTest(key=key),self.assertRaises(ReachedPins):phase.install({'pins':Pins()},key)
 def test_p0_unreadable_cpu_fails_closed(self):
  with patch.object(phase,'sys',types.SimpleNamespace(version_info=(3,12,0))),patch.object(phase.platform,'machine',return_value='x86_64'),patch.object(Path,'read_text',side_effect=PermissionError('mock')):
   with self.assertRaises(PermissionError):phase.install({'pins':Pins()},'qwen2')
if __name__=='__main__':unittest.main()
