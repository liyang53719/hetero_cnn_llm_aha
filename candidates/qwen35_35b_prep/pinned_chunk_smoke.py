"""Explicit official fixed-runtime chunk smoke; excluded from Torch-free CI."""
import unittest
from unittest import mock
from . import chunk_reference as r,reference

class PinnedChunkSmoke(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import torch
  cls.torch=torch;reference._runtime(torch)
 def test_zero_fullshape_sequence_boundaries_and_singleton_byte_view(self):
  for tokens in (1,63,64,65,127,128):
   with self.subTest(tokens=tokens):
    values,identity=r.native_chunk(bytes(tokens*51200),tokens)
    self.assertEqual(values['output'],bytes(tokens*8192));self.assertEqual(values['state'],bytes(2097152))
    self.assertEqual(identity['chunks'],(tokens+63)//64);self.assertEqual(identity['pad_size'],(-tokens)%64)
    self.assertIsNone(identity['passed']);self.assertTrue(identity['runtime_verified_before_and_after'])
 def test_no_global_runtime_setters_during_reference(self):
  from contextlib import ExitStack
  with ExitStack() as stack:
   for name in ('set_num_threads','set_num_interop_threads','use_deterministic_algorithms','set_float32_matmul_precision','set_flush_denormal'):
    stack.enter_context(mock.patch.object(self.torch,name,side_effect=AssertionError('reference changed '+name)))
   values,identity=r.native_chunk(bytes(51200),1)
  self.assertEqual(len(values['state']),2097152)
 def test_runtime_and_source_drift_rejected(self):
  with mock.patch.object(self.torch,'are_deterministic_algorithms_enabled',return_value=False):
   with self.assertRaises(ValueError):r.native_chunk(bytes(51200),1)
  with mock.patch.object(r,'SOURCE_SHA','0'*64):
   with self.assertRaises(ValueError):r.native_chunk(bytes(51200),1)
if __name__=='__main__':unittest.main()
